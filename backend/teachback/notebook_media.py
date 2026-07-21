"""OpenMAIC-style notebook copilot and narrated lesson pipeline.

The browser receives only typed answers, approved notebook anchors, web source
metadata, and renderable lesson data. Uploaded material remains the primary
authority; web search is an explicit fallback for questions the notebook does
not cover.
"""
from __future__ import annotations

import json
import re
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from django.conf import settings

from .notebook_pipeline import _section_asset_ids, _section_diagram, _section_preview, build_artifact_payload
from .providers import (
    ProviderOutputError,
    ProviderUnavailable,
    active_generation_configured,
    normalize_model_name,
    provider_for,
    record_provider_failure,
)
from .remediation_video_views import _generate_voice


def _active_provider_metadata() -> tuple[str, str]:
    configured = str(getattr(settings, "LLM_PROVIDER", "fixture") or "fixture").casefold()
    if configured in {"openai", "live_openai"}:
        return "openai", normalize_model_name(getattr(settings, "OPENAI_MODEL", "gpt-5.6-terra-high"), "gpt-5.6-terra-high")
    if configured in {"qwen", "live_qwen"}:
        return "qwen", str(getattr(settings, "FIREWORKS_MODEL", ""))
    if configured in {"fireworks", "live_fireworks"}:
        return "fireworks", str(getattr(settings, "FIREWORKS_MODEL", ""))
    return "local_deterministic", "source-structure-v1"


STOP_WORDS = {
    "about", "after", "also", "and", "are", "can", "does", "from", "give", "how",
    "into", "more", "show", "that", "the", "their", "this", "what", "when", "with",
    "would", "your", "explain", "please", "tell", "make", "lesson", "question",
}
EXTERNAL_MARKERS = ("latest", "today", "current", "recent", "internet", "web", "outside", "according to", "news")


def _tokens(value: str) -> set[str]:
    return {word for word in re.findall(r"[a-zA-Z0-9]{3,}", value.casefold()) if word not in STOP_WORDS}


def _section_text(section: dict) -> str:
    return " ".join(
        str(block.get("markdown") or "")
        for block in section.get("blocks") or []
        if str(block.get("type") or "").casefold() != "image"
    ).strip()


def _rank_sections(pack: dict, question: str) -> list[dict]:
    query = _tokens(question)
    ranked: list[tuple[int, int, dict]] = []
    # Chat is scoped to selected ready sources, not to the narrower set of
    # sections considered suitable for generated study artifacts.  Mistral can
    # correctly extract a short page as a supplementary section; excluding it
    # here made a selected, ready PDF appear empty to source-grounded chat.
    # Keep the existing primary-first ordering while allowing those durable,
    # already selected source blocks to be ranked and cited.
    sections = [
        section
        for collection in (pack.get("sections") or [], pack.get("supplementarySections") or [])
        for section in collection
        if isinstance(section, dict)
    ]
    for section in sections:
        title = str(section.get("title") or "")
        text = _section_text(section)
        words = _tokens(f"{title} {text}")
        score = len(query.intersection(words))
        if query and query.intersection(_tokens(title)):
            score += 4
        if score:
            ranked.append((score, -int(section.get("order") or 0), section))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    if ranked:
        return [section for _, _, section in ranked[:6]]
    # A source-scoped question can be semantically related without sharing an
    # exact token (for example, "scheduler" versus "scheduling"), and a
    # learner may simply ask what their selected source says.  Returning the
    # first bounded sections is safe: callers pass an already validated
    # selected-source pack, so this fallback cannot widen source scope or draw
    # on web/notebook memory outside the learner's explicit selection.
    return sections[:6]


def _retrieve_chunks(sections: list[dict], question: str, *, max_chunks: int = 18) -> list[dict]:
    """Select bounded source chunks for generation while preserving citations.

    This is the notebook's deterministic RAG layer.  It deliberately avoids
    sending an entire OCR dump to Qwen: each candidate is a durable text block,
    scored against the question and its section title, then grouped back into
    the original section shape so existing anchor validation still applies.
    """
    query = _tokens(question)
    candidates: list[tuple[int, int, int, int, dict, dict]] = []
    for section_index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        title_tokens = _tokens(str(section.get("title") or ""))
        for block_index, block in enumerate(section.get("blocks") or []):
            if not isinstance(block, dict) or str(block.get("type") or "").casefold() == "image":
                continue
            text = str(block.get("markdown") or "").strip()
            if not text:
                continue
            block_tokens = _tokens(text)
            score = len(query.intersection(block_tokens))
            score += 3 * len(query.intersection(title_tokens))
            candidates.append((score, -section_index, -block_index, section_index, section, block))

    if not candidates:
        return sections
    candidates.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    matched = [item for item in candidates if item[0] > 0]
    selected = (matched or candidates)[:max_chunks]
    grouped: dict[int, list[dict]] = {}
    for _, _, _, section_index, _, block in selected:
        grouped.setdefault(section_index, []).append(block)

    retrieved: list[dict] = []
    for section_index, section in enumerate(sections):
        blocks = grouped.get(section_index)
        if not blocks:
            continue
        clone = dict(section)
        # Restore document order inside each section even though selection was
        # relevance-first. This makes the prompt readable and deterministic.
        clone["blocks"] = sorted(blocks, key=lambda block: int(block.get("page") or 0))
        retrieved.append(clone)
    return retrieved or sections[:1]


def _retrieval_metadata(sections: list[dict], question: str) -> dict:
    anchors = _anchors_for_sections(sections)
    return {
        "strategy": "deterministic_chunk_rag",
        "queryTerms": sorted(_tokens(question))[:24],
        "sectionCount": len(sections),
        "chunkCount": sum(1 for section in sections for block in section.get("blocks") or [] if isinstance(block, dict) and str(block.get("markdown") or "").strip()),
        "anchorCount": len(anchors),
    }


def _anchors_for_sections(sections: list[dict]) -> list[str]:
    anchors: list[str] = []
    for section in sections:
        for block in section.get("blocks") or []:
            anchor = str(block.get("sourceAnchor") or block.get("blockId") or "").strip()
            if anchor and anchor not in anchors:
                anchors.append(anchor)
        if not any(str(block.get("sourceAnchor") or block.get("blockId") or "").strip() for block in section.get("blocks") or []):
            fallback = str(section.get("sectionId") or "").strip()
            if fallback and fallback not in anchors:
                anchors.append(fallback)
    return anchors[:40]


def _source_context(sections: list[dict], source_catalog: list[dict] | None = None) -> str:
    """Render a bounded, locator-rich context pack for a live provider.

    The model never receives arbitrary notebook memory here. Every line names
    the selected source, document section, durable page/block location, and
    the only citation anchor it may use.
    """
    catalog = {
        str(item.get("sourceId")): " ".join(str(item.get("title") or item.get("filename") or "").split())[:240]
        for item in source_catalog or []
        if isinstance(item, dict) and str(item.get("sourceId") or "").strip()
    }
    chunks: list[str] = []
    for section in sections:
        anchor_lines = []
        source_ids = [str(item) for item in section.get("sourceIds") or [] if str(item)]
        default_source_id = source_ids[0] if source_ids else "unknown-source"
        document_title = catalog.get(default_source_id) or " ".join(str(section.get("title") or "Selected source").split())[:240]
        for block in section.get("blocks") or []:
            if str(block.get("type") or "").casefold() == "image":
                continue
            text = str(block.get("markdown") or "").strip()
            if not text:
                continue
            anchor = str(block.get("sourceAnchor") or block.get("blockId") or section.get("sectionId") or "source")
            block_id = str(block.get("blockId") or anchor)[:200]
            source_id = str(block.get("sourceId") or default_source_id)[:200]
            page = f"{block['page']}" if block.get("page") else "unknown"
            anchor_lines.append(
                f"[sourceId={source_id}; document={document_title}; page={page}; blockId={block_id}; anchorId={anchor}] {text[:1800]}"
            )
        if anchor_lines:
            chunks.append(f"## {document_title} (sourceIds={source_ids})\n" + "\n".join(anchor_lines[:8]))
    return "\n\n".join(chunks)[:24000]


def _assets_for_sections(pack: dict, sections: list[dict]) -> tuple[list[str], list[dict]]:
    ids: list[str] = []
    assets: list[dict] = []
    for section in sections:
        for asset_id in _section_asset_ids(pack, section):
            if asset_id in ids:
                continue
            asset = next((item for item in pack.get("assets") or [] if str(item.get("assetId")) == asset_id), None)
            if not asset:
                continue
            ids.append(asset_id)
            assets.append({
                "assetId": asset_id,
                "alt": str(asset.get("alt") or "Extracted source visual")[:180],
                "page": asset.get("page"),
                "sourceId": asset.get("sourceId"),
            })
    return ids[:24], assets[:24]


def _json_request(url: str, payload: dict | None = None, headers: dict[str, str] | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request_headers = {"Accept": "application/json", **(headers or {})}
    if body is not None:
        request_headers["Content-Type"] = "application/json"
    with urlopen(Request(url, data=body, headers=request_headers, method="POST" if body is not None else "GET"), timeout=settings.WEB_SEARCH_TIMEOUT_SECONDS) as response:
        raw = response.read().decode("utf-8", errors="replace")
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


def _web_search(query: str) -> dict:
    """Use configured Tavily/SearXNG, with a no-key DuckDuckGo fallback."""
    sources: list[dict] = []
    key = str(getattr(settings, "TAVILY_API_KEY", "") or "").strip()
    if key:
        payload = {"api_key": key, "query": query[:500], "search_depth": "advanced", "max_results": 6, "include_answer": True}
        result = _json_request(f"{str(settings.TAVILY_BASE_URL).rstrip('/')}/search", payload)
        for item in result.get("results") or []:
            if isinstance(item, dict) and item.get("url"):
                sources.append({"title": str(item.get("title") or item["url"])[:240], "url": str(item["url"])[:1000], "snippet": str(item.get("content") or "")[:800]})
        answer = str(result.get("answer") or "").strip()
    else:
        base_url = str(getattr(settings, "SEARXNG_BASE_URL", "") or "").strip().rstrip("/")
        if base_url:
            result = _json_request(f"{base_url}/search?q={quote_plus(query[:500])}&format=json")
            answer = ""
            for item in result.get("results") or []:
                if isinstance(item, dict) and item.get("url"):
                    sources.append({"title": str(item.get("title") or item["url"])[:240], "url": str(item["url"])[:1000], "snippet": str(item.get("content") or item.get("snippet") or "")[:800]})
        else:
            result = _json_request(f"https://api.duckduckgo.com/?q={quote_plus(query[:400])}&format=json&no_html=1&skip_disambig=1")
            answer = str(result.get("AbstractText") or "").strip()
            if result.get("AbstractURL"):
                sources.append({"title": str(result.get("Heading") or "Web result")[:240], "url": str(result["AbstractURL"])[:1000], "snippet": answer[:800]})
    context = "\n\n".join(f"[web-{index + 1}] {item['title']}\n{item['snippet']}\nURL: {item['url']}" for index, item in enumerate(sources))
    if answer:
        context = f"[web-summary] {answer}\n\n{context}".strip()
    return {"sources": sources[:6], "context": context[:12000]}


def _needs_web(question: str, matched: list[dict]) -> bool:
    lowered = question.casefold()
    return not matched or any(marker in lowered for marker in EXTERNAL_MARKERS)


def _context_for_question(pack: dict, question: str, allow_web_search: bool) -> tuple[list[dict], str, dict]:
    sections = _retrieve_chunks(_rank_sections(pack, question), question)
    web = {"sources": [], "context": ""}
    if allow_web_search and _needs_web(question, sections):
        web = _web_search(question)
    return sections, _source_context(sections, pack.get("sourceCatalog")), web


def _chat_provider_error_category(error: Exception) -> str:
    """Classify a provider failure without returning an upstream error body."""
    if isinstance(error, ProviderOutputError):
        message = str(error or "").casefold()
        if any(marker in message for marker in ("citation", "anchor", "source id", "source evidence")):
            return "citation_validation_failed"
        return "model_response_invalid"
    message = str(error or "").casefold()
    if any(marker in message for marker in ("timed out", "timeout", "deadline exceeded")):
        return "timeout"
    if any(marker in message for marker in ("401", "403", "unauthorized", "forbidden", "authentication")):
        return "authentication"
    if any(marker in message for marker in ("429", "rate limit", "too many requests")):
        return "rate_limited"
    return "provider_unavailable"


def _source_excerpt_recovery(
    *,
    sections: list[dict],
    source_context: str,
    web: dict,
    source_ids: list[str],
    allowed_anchors: list[str],
    error: Exception,
) -> dict:
    """Return an explicitly labelled source excerpt after a provider failure.

    The fallback is direct, saved source material—not a replacement generated
    answer.  A typed error category lets the UI distinguish a retryable outage
    from an invalid model response or rejected citation.
    """
    category = _chat_provider_error_category(error)
    unavailable = isinstance(error, ProviderUnavailable)
    if category == "citation_validation_failed":
        message = "The teaching model returned citations that could not be validated. This is a source excerpt, not a generated answer."
    elif category == "model_response_invalid":
        message = "The teaching model returned an invalid response. This is a source excerpt, not a generated answer."
    else:
        message = "The teaching model is unavailable. This is a source excerpt, not a generated answer."
    excerpt = _section_preview(sections[0]) if sections else web.get("context", "")[:1200]
    return {
        "answer": excerpt or "The configured teaching model is unavailable right now.",
        "sourceIds": source_ids,
        "sourceAnchorIds": allowed_anchors[:3],
        "webSources": web.get("sources") or [],
        "groundedIn": "notebook" if source_context else "web",
        "fallbackUsed": bool(web.get("context")),
        "degraded": True,
        "provider": _active_provider_metadata()[0],
        "model": _active_provider_metadata()[1],
        "providerStatus": "unavailable" if unavailable else "invalid_response",
        "providerErrorCategory": category,
        "providerUnavailable": unavailable,
        "providerOutputInvalid": not unavailable,
        "citationValidationFailed": category == "citation_validation_failed",
        "providerMessage": message,
        "retryAvailable": True,
        "retryAction": "ask_again",
    }


def answer_notebook_question(pack: dict, question: str, *, allow_web_search: bool = True) -> dict:
    sections, source_context, web = _context_for_question(pack, question, allow_web_search)
    retrieval = _retrieval_metadata(sections, question)
    source_ids = sorted({str(source_id) for section in sections for source_id in section.get("sourceIds") or []})
    allowed_anchors = _anchors_for_sections(sections)
    if not source_context and not web["context"]:
        return {"answer": "I could not find this in the uploaded notebook, and no web result was available. Try naming the topic or enable web fallback.", "sourceIds": [], "sourceAnchorIds": [], "webSources": [], "groundedIn": "insufficient", "fallbackUsed": False, "retrieval": retrieval}
    try:
        provider = provider_for()
        result = provider.answer_notebook_question({
            "question": question,
            "sourceContext": source_context,
            "webContext": web["context"],
            "allowedAnchorIds": allowed_anchors,
        })
        answer = str(result.get("answer") or "").strip()
        if not answer:
            raise ProviderOutputError("The provider did not return an answer.")
        approved_anchors = list(dict.fromkeys(str(item) for item in result.get("sourceAnchorIds") or [] if str(item) in set(allowed_anchors)))
        # A notebook-grounded model answer must carry at least one durable
        # page/block anchor.  Do not silently publish an uncited claim merely
        # because the model's prose looked plausible.
        if source_context and source_ids and not approved_anchors:
            raise ProviderOutputError("Teaching provider response omitted approved source citations")
        grounded = str(result.get("groundedIn") or ("mixed" if source_context and web["context"] else "web" if web["context"] else "notebook"))
        return {
            "answer": answer,
            "sourceIds": source_ids,
            "sourceAnchorIds": approved_anchors,
            "webSources": web["sources"],
            "groundedIn": grounded if grounded in {"notebook", "web", "mixed", "insufficient"} else "notebook",
            "fallbackUsed": bool(web["context"]),
            "provider": _active_provider_metadata()[0],
            "model": _active_provider_metadata()[1],
            "providerStatus": "completed",
            "citationValidation": "passed",
            "retrieval": retrieval,
        }
    except (ProviderUnavailable, ProviderOutputError) as exc:
        record_provider_failure(_active_provider_metadata()[0], _chat_provider_error_category(exc))
        fallback = _source_excerpt_recovery(
            sections=sections,
            source_context=source_context,
            web=web,
            source_ids=source_ids,
            allowed_anchors=allowed_anchors,
            error=exc,
        )
        fallback["retrieval"] = retrieval
        return fallback


def notebook_provider_error_category(error: Exception) -> str:
    """Public, redacted error category for notebook generation endpoints."""
    return _chat_provider_error_category(error)


def _artifact_sections(pack: dict) -> list[dict]:
    """Return every readable section already constrained by ``scoped_knowledge_pack``."""
    sections: list[dict] = []
    for collection in (pack.get("sections") or [], pack.get("supplementarySections") or []):
        for section in collection:
            if not isinstance(section, dict) or not _section_text(section):
                continue
            sections.append(section)
    return sections[:32]


def _anchor_locations(sections: list[dict]) -> dict[str, dict]:
    """Map durable anchors to only their saved source/page/block metadata."""
    locations: dict[str, dict] = {}
    for section in sections:
        section_source_ids = [str(item) for item in section.get("sourceIds") or [] if str(item)]
        fallback_anchor = str(section.get("sectionId") or "").strip()
        fallback_pages = [int(page) for page in section.get("pages") or [] if isinstance(page, int) or str(page).isdigit()]
        for block in section.get("blocks") or []:
            if not isinstance(block, dict) or str(block.get("type") or "").casefold() == "image":
                continue
            anchor = str(block.get("sourceAnchor") or block.get("blockId") or "").strip()
            if not anchor:
                continue
            source_id = str(block.get("sourceId") or (section_source_ids[0] if section_source_ids else "")).strip()
            locations[anchor] = {
                "sourceIds": [source_id] if source_id else section_source_ids,
                "page": int(block["page"]) if isinstance(block.get("page"), int) or str(block.get("page") or "").isdigit() else None,
                "blockId": str(block.get("blockId") or anchor),
            }
        if fallback_anchor and fallback_anchor not in locations:
            locations[fallback_anchor] = {
                "sourceIds": section_source_ids,
                "page": fallback_pages[0] if fallback_pages else None,
                "blockId": fallback_anchor,
            }
    return locations


def _artifact_text(value: object, field: str, *, minimum: int = 3, maximum: int = 1400) -> str:
    raw_text = " ".join(str(value or "").split())
    # Fireworks occasionally returns duplicate-glyph strings (for example
    # ``RReeccuurrrreennccee``) even though the source pack is clean. Apply the
    # same conservative repair used for PDF text layers before exposing model
    # output in a learner-facing artifact. Ordinary words such as ``book``
    # remain untouched because the repair only runs on a strong signal.
    letters = [char for char in raw_text if char.isalpha()]
    duplicate_pairs = sum(
        1
        for left, right in zip(raw_text, raw_text[1:])
        if left.isalpha() and left.casefold() == right.casefold()
    )
    duplicate_ratio = duplicate_pairs / max(len(letters), 1)
    text = raw_text
    if duplicate_ratio >= 0.18:
        # A few provider strings duplicate short chunks after the first pass,
        # e.g. ``Tran-an-an-sformer``. Collapse only exact adjacent alphabetic
        # n-gram repeats and repair common split words such as ``T he``.
        def collapse_glyph_run(match: re.Match[str]) -> str:
            run = match.group(0)
            return match.group(1) * max(1, len(run) // 2)
        text = re.sub(r"([A-Za-z])\1+", collapse_glyph_run, text)
        text = re.sub(r"([.!?,;:])\1+", r"\1", text)
        for size in (4, 3, 2):
            pattern = re.compile(rf"([A-Za-z]{{{size}}})\1")
            previous = None
            while previous != text:
                previous = text
                text = pattern.sub(r"\1", text)
        split_words = {
            "the", "which", "what", "why", "how", "when", "where", "who",
            "it", "to", "of", "in", "is", "as", "an", "on", "at", "by",
            "be", "we", "he", "me", "do", "if", "so", "no", "or", "decode",
            "encoder", "decoder",
        }
        def join_split(match: re.Match[str]) -> str:
            joined = f"{match.group(1)}{match.group(2)}"
            return joined.capitalize() if joined.casefold() in split_words else match.group(0)
        text = re.sub(r"\b([A-Z])\s+([a-z]{1,8})\b", join_split, text)
        # Qwen's duplicated-glyph output has one recurring transposition for
        # this concept name; correct it only in the high-signal repair path.
        text = re.sub(r"\btranasformer(s?)\b", r"Transformer\1", text, flags=re.IGNORECASE)
    # A low-signal model typo can still duplicate an initial capital (for
    # example ``Ooverview``). It is safe to collapse only an uppercase initial
    # pair followed by a normal lowercase word.
    def collapse_initial(match: re.Match[str]) -> str:
        initial = match.group(1)
        return initial.upper() + match.group(3) if initial.isupper() else initial + match.group(3)
    text = re.sub(r"\b([A-Za-z])(\1)([a-z]{3,})\b", collapse_initial, text, flags=re.IGNORECASE)
    text = " ".join(text.split())
    if len(text) < minimum:
        raise ProviderOutputError(f"Fireworks returned an incomplete artifact field: {field}")
    return text[:maximum]


def _artifact_list(value: object, field: str, *, minimum: int = 1, maximum: int = 80) -> list:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ProviderOutputError(f"Fireworks returned an incomplete artifact field: {field}")
    return value


def _artifact_citations(item: dict, anchor_locations: dict[str, dict]) -> tuple[list[str], list[str], list[int]]:
    raw = item.get("sourceAnchorIds") if isinstance(item, dict) else None
    if not isinstance(raw, list) or not raw:
        raise ProviderOutputError("Fireworks artifact omitted source citations")
    requested = [str(anchor).strip() for anchor in raw if str(anchor).strip()]
    invalid = [anchor for anchor in requested if anchor not in anchor_locations]
    if invalid:
        raise ProviderOutputError("Fireworks artifact returned an unapproved source citation")
    anchors = list(dict.fromkeys(requested))[:4]
    source_ids: list[str] = []
    pages: list[int] = []
    for anchor in anchors:
        location = anchor_locations[anchor]
        for source_id in location.get("sourceIds") or []:
            if source_id and source_id not in source_ids:
                source_ids.append(source_id)
        page = location.get("page")
        if isinstance(page, int) and page not in pages:
            pages.append(page)
    if not source_ids:
        raise ProviderOutputError("Fireworks artifact citations could not be bound to a saved source")
    return anchors, source_ids, pages


def _artifact_provenance(*, provider: str, model: str, status: str, citation_validation: str, reason: str | None = None) -> dict:
    payload = {
        "provider": provider,
        "model": model,
        "status": status,
        "citationValidation": citation_validation,
    }
    if reason:
        payload["reason"] = reason
    return payload


def _normalized_provider_artifact(
    raw: dict,
    artifact_type: str,
    *,
    pack: dict,
    anchor_locations: dict[str, dict],
    allowed_asset_ids: list[str],
) -> tuple[str, dict]:
    """Bind a live-provider artifact to server-owned sources and citations."""
    if not isinstance(raw, dict):
        raise ProviderOutputError("The live provider returned an invalid artifact response")
    title = _artifact_text(raw.get("title"), "title", maximum=240)
    provenance = _artifact_provenance(
        provider=_active_provider_metadata()[0],
        model=_active_provider_metadata()[1],
        status="completed",
        citation_validation="passed",
    )
    if artifact_type == "summary":
        sections = []
        for item in _artifact_list(raw.get("sections"), "sections", maximum=24):
            if not isinstance(item, dict):
                raise ProviderOutputError("Fireworks returned an invalid summary section")
            anchors, source_ids, _ = _artifact_citations(item, anchor_locations)
            sections.append({
                "title": _artifact_text(item.get("title"), "section title", maximum=240),
                "summary": _artifact_text(item.get("summary"), "section summary", minimum=16),
                "sourceIds": source_ids,
                "sourceAnchors": anchors,
            })
        return title, {"kind": "summary", "sections": sections, "provenance": provenance}

    if artifact_type == "mcq":
        questions = []
        for index, item in enumerate(_artifact_list(raw.get("questions"), "questions", maximum=30), start=1):
            if not isinstance(item, dict):
                raise ProviderOutputError("Fireworks returned an invalid question")
            anchors, source_ids, _ = _artifact_citations(item, anchor_locations)
            options = [_artifact_text(option, "MCQ option", minimum=1, maximum=320) for option in _artifact_list(item.get("options"), "MCQ options", minimum=3, maximum=4)]
            if len({option.casefold() for option in options}) != len(options):
                raise ProviderOutputError("Fireworks returned duplicate MCQ options")
            answer_index = item.get("answerIndex")
            if isinstance(answer_index, bool) or not isinstance(answer_index, int) or not 0 <= answer_index < len(options):
                raise ProviderOutputError("Fireworks returned an invalid MCQ answer index")
            questions.append({
                "id": f"fireworks-mcq-{index:03d}",
                "topicTitle": _artifact_text(item.get("topicTitle") or "Source topic", "MCQ topic", maximum=240),
                "question": _artifact_text(item.get("question"), "MCQ question", minimum=12, maximum=520),
                "options": options,
                "answerIndex": answer_index,
                "explanation": _artifact_text(item.get("explanation"), "MCQ explanation", minimum=12),
                "sourceIds": source_ids,
                "sourceAnchors": anchors,
                "quality": "fireworks_source_grounded",
                "questionType": "retrieval_transfer",
            })
        return title, {
            "kind": "mcq",
            "questions": questions,
            "instructions": "Answer first; reveal explanations after submitting.",
            "quality": "Fireworks-generated questions with server-validated source citations.",
            "provenance": provenance,
        }

    if artifact_type == "slides":
        slides = []
        allowed_assets = set(allowed_asset_ids)
        for index, item in enumerate(_artifact_list(raw.get("slides"), "slides", maximum=24), start=1):
            if not isinstance(item, dict):
                raise ProviderOutputError("Fireworks returned an invalid slide")
            anchors, source_ids, _ = _artifact_citations(item, anchor_locations)
            bullets = [_artifact_text(value, "slide bullet", minimum=2, maximum=240) for value in _artifact_list(item.get("bullets"), "slide bullets", maximum=5)]
            raw_assets = item.get("assetIds") if isinstance(item.get("assetIds"), list) else []
            asset_ids = [str(asset) for asset in raw_assets if str(asset) in allowed_assets][:3]
            if any(str(asset) not in allowed_assets for asset in raw_assets):
                raise ProviderOutputError("Fireworks returned an unapproved visual asset")
            diagram = _safe_diagram(item.get("diagram"))
            visual_kind = str(item.get("visualKind") or "").strip()
            if visual_kind not in {"text-note", "source-figure", "teaching-diagram"}:
                visual_kind = "source-figure" if asset_ids else "teaching-diagram" if diagram.get("nodes") else "text-note"
            slides.append({
                "index": index,
                "title": _artifact_text(item.get("title"), "slide title", maximum=240),
                "slideLabel": _artifact_text(item.get("slideLabel") or "KEY IDEA", "slide label", maximum=40),
                "body": _artifact_text(item.get("body"), "slide body", minimum=16, maximum=1100),
                "bullets": bullets,
                "teachingNote": _artifact_text(item.get("teachingNote") or "Connect this point to the cited source passage.", "slide teaching note", maximum=240),
                "sourceIds": source_ids,
                "sourceAnchors": anchors,
                "assetIds": asset_ids,
                "diagram": diagram if diagram.get("nodes") else None,
                "visualKind": visual_kind,
                "visualHint": "Fireworks source-grounded teaching structure with validated citations.",
            })
        return title, {"kind": "slides", "slides": slides, "assets": pack.get("assets") or [], "provenance": provenance}

    if artifact_type == "flashcards":
        cards = []
        for index, item in enumerate(_artifact_list(raw.get("cards"), "cards", maximum=80), start=1):
            if not isinstance(item, dict):
                raise ProviderOutputError("Fireworks returned an invalid flashcard")
            anchors, source_ids, _ = _artifact_citations(item, anchor_locations)
            cards.append({
                "id": f"fireworks-card-{index:03d}",
                "front": _artifact_text(item.get("front"), "flashcard prompt", minimum=4, maximum=500),
                "back": _artifact_text(item.get("back"), "flashcard answer", minimum=12),
                "tag": _artifact_text(item.get("tag") or "RECALL", "flashcard tag", maximum=80),
                "sourceIds": source_ids,
                "sourceAnchors": anchors,
            })
        return title, {
            "kind": "flashcards",
            "cards": cards,
            "instructions": "Answer the question aloud before revealing the cited explanation.",
            "provenance": provenance,
        }

    if artifact_type == "important_questions":
        questions = []
        for index, item in enumerate(_artifact_list(raw.get("questions"), "questions", maximum=60), start=1):
            if not isinstance(item, dict):
                raise ProviderOutputError("Fireworks returned an invalid important question")
            anchors, source_ids, _ = _artifact_citations(item, anchor_locations)
            kind = str(item.get("kind") or "").casefold()
            if kind not in {"explain", "apply"}:
                raise ProviderOutputError("Fireworks returned an invalid question kind")
            questions.append({
                "id": f"fireworks-question-{index:03d}",
                "kind": kind,
                "question": _artifact_text(item.get("question"), "important question", minimum=12, maximum=600),
                "answerFocus": _artifact_text(item.get("answerFocus"), "important question focus", minimum=12),
                "sourceIds": source_ids,
                "sourceAnchors": anchors,
            })
        return title, {"kind": "important_questions", "questions": questions, "provenance": provenance}

    if artifact_type == "mind_map":
        raw_nodes = _artifact_list(raw.get("nodes"), "mind-map nodes", maximum=30)
        nodes = [{"id": "notebook-root", "label": _artifact_text(raw.get("rootLabel"), "mind-map root", maximum=240), "kind": "root", "sourceIds": []}]
        id_map: dict[str, str] = {}
        for index, item in enumerate(raw_nodes, start=1):
            if not isinstance(item, dict):
                raise ProviderOutputError("Fireworks returned an invalid mind-map node")
            raw_id = _artifact_text(item.get("id"), "mind-map node ID", maximum=80)
            if raw_id in id_map:
                raise ProviderOutputError("Fireworks returned duplicate mind-map node IDs")
            node_id = f"fireworks-node-{index:02d}"
            id_map[raw_id] = node_id
            anchors, source_ids, _ = _artifact_citations(item, anchor_locations)
            nodes.append({
                "id": node_id,
                "label": _artifact_text(item.get("label"), "mind-map node label", maximum=240),
                "detail": _artifact_text(item.get("detail"), "mind-map node detail", minimum=12, maximum=420),
                "kind": "topic",
                "sourceIds": source_ids,
                "sourceAnchors": anchors,
            })
        edges = []
        seen_edges: set[tuple[str, str]] = set()
        for edge in raw.get("edges") if isinstance(raw.get("edges"), list) else []:
            if not isinstance(edge, dict):
                raise ProviderOutputError("Fireworks returned an invalid mind-map edge")
            source = id_map.get(str(edge.get("from") or ""))
            target = id_map.get(str(edge.get("to") or ""))
            if not source or not target or source == target or (source, target) in seen_edges:
                raise ProviderOutputError("Fireworks returned an invalid mind-map relationship")
            seen_edges.add((source, target))
            edges.append({"from": source, "to": target})
        if not edges:
            edges = [{"from": "notebook-root", "to": node["id"]} for node in nodes[1:]]
        return title, {"kind": "mind_map", "nodes": nodes, "edges": edges, "note": "Fireworks-generated concept structure with server-validated source citations.", "provenance": provenance}

    if artifact_type == "data_table":
        source_text = _source_context(_artifact_sections(pack), pack.get("sourceCatalog")).casefold()
        rows = []
        for item in _artifact_list(raw.get("rows"), "data-table rows", maximum=60):
            if not isinstance(item, dict):
                raise ProviderOutputError("Fireworks returned an invalid data-table row")
            anchors, source_ids, pages = _artifact_citations(item, anchor_locations)
            formulas = [_artifact_text(value, "data-table formula", minimum=1, maximum=400) for value in (item.get("formulas") or []) if str(value).strip()][:4]
            if any(formula.casefold() not in source_text for formula in formulas):
                raise ProviderOutputError("Fireworks returned a data-table formula that is not present in the selected sources")
            rows.append({
                "topic": _artifact_text(item.get("topic"), "data-table topic", maximum=240),
                "pages": pages,
                "keyIdea": _artifact_text(item.get("keyIdea"), "data-table key idea", minimum=12, maximum=420),
                "formulas": formulas,
                "sourceIds": source_ids,
                "sourceAnchors": anchors,
            })
        return title, {"kind": "data_table", "columns": ["Topic", "Pages", "Key idea", "Formulas"], "rows": rows, "note": "Fireworks-organized study table with server-validated source citations.", "provenance": provenance}

    if artifact_type == "formula_sheet":
        source_text = _source_context(_artifact_sections(pack), pack.get("sourceCatalog")).casefold()
        formulas = []
        for index, item in enumerate(_artifact_list(raw.get("formulas"), "formulas", minimum=0, maximum=60), start=1):
            if not isinstance(item, dict):
                raise ProviderOutputError("Fireworks returned an invalid formula entry")
            formula = _artifact_text(item.get("text"), "formula", maximum=600)
            if formula.casefold() not in source_text:
                # Formula sheets are a literal source index. Discard a model
                # candidate that is not present in the selected material and
                # render the explicit empty state if none remain.
                continue
            anchors, source_ids, pages = _artifact_citations(item, anchor_locations)
            formulas.append({
                "formulaId": f"fireworks-formula-{index:03d}",
                "text": formula,
                "label": _artifact_text(item.get("label") or "Source formula", "formula label", maximum=240),
                "sourceId": source_ids[0],
                "page": pages[0] if pages else None,
                "sourceAnchors": anchors,
            })
        note = (
            "Fireworks-curated formulas copied from cited selected-source passages."
            if formulas
            else "No literal equations were found in the selected sources. Add a source containing equations to build a formula sheet."
        )
        return title, {"kind": "formula_sheet", "formulas": formulas, "note": note, "provenance": provenance}

    raise ProviderOutputError("unsupported notebook artifact type")


def generate_notebook_artifact(pack: dict, artifact_type: str) -> tuple[str, dict]:
    """Build a notebook artifact through Fireworks only when explicitly live.

    The deterministic builder is intentionally retained for fixture and
    unconfigured local environments. It is tagged as local source structure so
    no caller can mistake it for a provider-generated result.
    """
    selected_source_ids = [str(item) for item in pack.get("sources") or [] if str(item)]
    if not selected_source_ids:
        raise ValueError("Select at least one ready source with readable extracted content.")
    if not active_generation_configured():
        title, payload = build_artifact_payload(pack, artifact_type)
        payload = dict(payload)
        payload["provenance"] = _artifact_provenance(
            provider="local_deterministic",
            model="source-structure-v1",
            status="local_fallback_active",
            citation_validation="source-derived",
            reason="active_provider_not_configured_or_fixture_mode",
        )
        return title, payload

    sections = _artifact_sections(pack)
    if not sections:
        raise ProviderOutputError("Selected sources have no readable extracted context for provider generation")
    anchor_locations = _anchor_locations(sections)
    allowed_anchor_ids = list(anchor_locations)
    if not allowed_anchor_ids:
        raise ProviderOutputError("Selected sources have no durable page or block anchors")
    allowed_asset_ids, _ = _assets_for_sections(pack, sections)
    selected_section_ids = {str(section.get("sectionId") or "") for section in sections}
    approved_formula_candidates = [
        str(formula.get("text") or "").strip()
        for formula in pack.get("formulas") or []
        if isinstance(formula, dict)
        and str(formula.get("sectionId") or "") in selected_section_ids
        and str(formula.get("text") or "").strip()
    ][:60]
    raw = provider_for().generate_notebook_artifact({
        "artifactType": artifact_type,
        "sourceIds": selected_source_ids,
        "sourceContext": _source_context(sections, pack.get("sourceCatalog")),
        "allowedAnchorIds": allowed_anchor_ids,
        "allowedAssetIds": allowed_asset_ids,
        "approvedFormulaCandidates": approved_formula_candidates,
    })
    return _normalized_provider_artifact(
        raw,
        artifact_type,
        pack=pack,
        anchor_locations=anchor_locations,
        allowed_asset_ids=allowed_asset_ids,
    )


def _safe_diagram(value: object) -> dict:
    if not isinstance(value, dict):
        return {"nodes": [], "edges": []}
    nodes = [node for node in value.get("nodes") or [] if isinstance(node, dict) and node.get("id")][:8]
    ids = {str(node["id"]) for node in nodes}
    edges = [edge for edge in value.get("edges") or [] if isinstance(edge, dict) and str(edge.get("from")) in ids and str(edge.get("to")) in ids][:12]
    return {"nodes": [{"id": str(node["id"])[:40], "label": str(node.get("label") or node["id"])[:100]} for node in nodes], "edges": edges}


def _local_lesson_manifest(sections: list[dict], question: str, anchor_ids: list[str], asset_ids: list[str], web_context: str) -> dict:
    """Deterministic local lesson used only without a configured live provider."""
    source_section = sections[0] if sections else {"title": question[:120], "blocks": []}
    source_title = str(source_section.get("title") or "The requested idea")
    source_body = _section_preview(source_section) or web_context[:900] or "Review the requested idea and connect it to the supplied evidence."
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", source_body) if part.strip()]
    bullets = (sentences[:4] + ["Connect the explanation to the visual before applying it.", "Explain the idea in your own words."])[:4]
    beats = [
        (f"Orienting to {source_title}", f"This lesson addresses {question}. Start by locating the central idea in the source: {source_body}", "Begin with the source definition and identify the quantities or terms involved."),
        (f"Definition: {source_title}", source_body, "Read the definition carefully, then name the relationship it describes."),
        (f"Visual model: {source_title}", f"Use the visual model to connect the parts of {source_title}. {source_body}", "Follow the highlighted flow from the input or cause to the output or result."),
        (f"Apply and transfer {source_title}", f"Apply the same reasoning to a new situation. The key repair is to return to the source explanation: {source_body}", "Explain why the same principle still applies when the example changes."),
    ]
    return {"title": f"{source_title} · guided lesson", "slides": [{
        "slideId": f"local-scene-{index + 1}", "title": title[:160], "slideLabel": "KEY IDEA" if index == 0 else "SOURCE NOTE", "body": body[:1100], "bullets": bullets[:4],
        "teachingNote": narration[:220], "visualKind": "teaching-diagram" if index == 2 else "text-note",
        "narration": narration + " " + " ".join(bullets[:2]), "sourceAnchorIds": anchor_ids[:4], "assetIds": asset_ids[:2],
        "diagram": _section_diagram(source_section) if index == 2 else {"nodes": [], "edges": []},
        "actions": [
            {"kind": "reveal", "label": narration[:160], "target": "body"},
            {"kind": "highlight", "label": bullets[0][:160], "target": "bullet", "targetIndex": 0},
        ],
    } for index, (title, body, narration) in enumerate(beats)]}


def generate_openmaic_lesson(pack: dict, question: str, *, allow_web_search: bool = True, requested_duration: int = 120) -> dict:
    requested_duration = max(60, min(300, int(requested_duration or 120)))
    sections, source_context, web = _context_for_question(pack, question, allow_web_search)
    if not source_context and not web["context"]:
        raise ProviderOutputError("There is no notebook or web context available for this lesson.")
    allowed_anchors = _anchors_for_sections(sections)
    allowed_asset_ids, asset_catalog = _assets_for_sections(pack, sections)
    live_provider = active_generation_configured()
    if live_provider:
        manifest = provider_for().generate_openmaic_lesson({
            "question": question,
            "sourceContext": source_context,
            # Notebook lessons are strictly selected-source scoped. The caller
            # can offer web research elsewhere, but it must never be silently
            # blended into a Fireworks lesson artifact.
            "webContext": "",
            "allowedAnchorIds": allowed_anchors,
            "allowedAssetIds": allowed_asset_ids,
        })
    else:
        manifest = _local_lesson_manifest(sections, question, allowed_anchors, allowed_asset_ids, web["context"])
    raw_slides = manifest.get("slides") if isinstance(manifest, dict) else None
    if not isinstance(raw_slides, list) or not 4 <= len(raw_slides) <= 8:
        if live_provider:
            raise ProviderOutputError("Fireworks returned an incomplete narrated lesson")
        manifest = _local_lesson_manifest(sections, question, allowed_anchors, allowed_asset_ids, web["context"])
        raw_slides = manifest["slides"]
    topic_anchors = allowed_anchors[:8]
    per_slide = max(8, requested_duration // len(raw_slides))
    slides: list[dict] = []
    for index, raw in enumerate(raw_slides[:8]):
        if not isinstance(raw, dict):
            if live_provider:
                raise ProviderOutputError("Fireworks returned an invalid narrated-lesson slide")
            continue
        raw_anchors = raw.get("sourceAnchorIds") if isinstance(raw.get("sourceAnchorIds"), list) else []
        invalid_anchors = [str(item) for item in raw_anchors if str(item) not in set(allowed_anchors)]
        source_anchor_ids = [str(item) for item in raw_anchors if str(item) in set(allowed_anchors)]
        if live_provider and (invalid_anchors or not source_anchor_ids):
            raise ProviderOutputError("Fireworks returned an unapproved or missing lesson citation")
        source_anchor_ids = list(dict.fromkeys(source_anchor_ids)) or topic_anchors
        raw_assets = raw.get("assetIds") if isinstance(raw.get("assetIds"), list) else []
        invalid_assets = [str(item) for item in raw_assets if str(item) not in set(allowed_asset_ids)]
        if live_provider and invalid_assets:
            raise ProviderOutputError("Fireworks returned an unapproved lesson visual asset")
        asset_ids = [str(item) for item in raw_assets if str(item) in set(allowed_asset_ids)]
        if live_provider:
            title = _artifact_text(raw.get("title"), "lesson slide title", maximum=180)
            body = _artifact_text(raw.get("body"), "lesson slide body", minimum=20, maximum=1200)
            narration = _artifact_text(raw.get("narration"), "lesson narration", minimum=40, maximum=1800)
            bullets = [_artifact_text(item, "lesson slide bullet", minimum=2, maximum=240) for item in _artifact_list(raw.get("bullets"), "lesson slide bullets", minimum=2, maximum=5)]
            raw_actions = _artifact_list(raw.get("actions"), "lesson actions", maximum=8)
            actions = []
            for action in raw_actions:
                if not isinstance(action, dict):
                    raise ProviderOutputError("Fireworks returned an invalid lesson action")
                kind = str(action.get("kind") or "").strip()
                label = _artifact_text(action.get("label"), "lesson action label", minimum=2, maximum=180)
                if kind not in {"reveal", "highlight", "draw", "write", "pause"}:
                    raise ProviderOutputError("Fireworks returned an invalid lesson action kind")
                actions.append({"kind": kind, "label": label, "target": str(action.get("target") or "body"), "targetIndex": action.get("targetIndex")})
        else:
            title = " ".join(str(raw.get("title") or f"Teaching scene {index + 1}").split())[:180]
            body = " ".join(str(raw.get("body") or "Review the highlighted idea, then connect it to the source.").split())[:1200]
            narration = " ".join(str(raw.get("narration") or body).split())[:1800]
            bullets = [" ".join(str(item).split())[:240] for item in raw.get("bullets") or [] if str(item).strip()][:5]
            if len(bullets) < 2:
                bullets = ["Follow the highlighted relationship.", "Explain the idea before moving to the next scene."]
            actions = [item for item in raw.get("actions") or [] if isinstance(item, dict) and item.get("kind") and item.get("label")][:8]
            if not actions:
                actions = [{"kind": "reveal", "label": bullet} for bullet in bullets[:3]]
        normalized_actions = []
        for action_index, action in enumerate(actions):
            normalized = {"kind": str(action.get("kind")), "label": " ".join(str(action.get("label") or "").split())[:180]}
            target = str(action.get("target") or "")
            if target not in {"title", "body", "bullet", "diagram", "asset", "canvas"}:
                target = "diagram" if normalized["kind"] == "draw" and raw.get("diagram", {}).get("nodes") else "title" if normalized["kind"] == "write" else "bullet" if normalized["kind"] == "highlight" and bullets else "body"
            normalized["target"] = target
            if target in {"bullet", "diagram", "asset"}:
                try:
                    normalized["targetIndex"] = max(0, int(action.get("targetIndex", action_index)))
                except (TypeError, ValueError):
                    normalized["targetIndex"] = action_index
            normalized_actions.append(normalized)
        actions = normalized_actions
        slide = {
            "index": index,
            "slideId": str(raw.get("slideId") or f"scene-{index + 1}")[:80],
            "title": title,
            "slideLabel": " ".join(str(raw.get("slideLabel") or "SOURCE NOTE").split())[:40],
            "body": body,
            "bullets": bullets,
            "teachingNote": " ".join(str(raw.get("teachingNote") or "Connect this point to the source explanation.").split())[:240],
            "visualKind": str(raw.get("visualKind") or ("source-figure" if asset_ids else "teaching-diagram" if _safe_diagram(raw.get("diagram")).get("nodes") else "text-note")),
            "narration": narration,
            "sourceAnchorIds": source_anchor_ids,
            "assetIds": asset_ids,
            "diagram": _safe_diagram(raw.get("diagram")),
            "actions": actions,
            "durationSeconds": per_slide,
        }
        try:
            voice = _generate_voice(narration)
        except (ProviderUnavailable, OSError):
            voice = None
        if voice:
            slide["audio"] = {**voice, "text": narration}
        slides.append(slide)
    if len(slides) < 4:
        raise ProviderOutputError("OpenMAIC lesson returned too few usable scenes")
    provider_id, provider_model = _active_provider_metadata() if live_provider else ("local_deterministic", "source-structure-v1")
    provider_status = "completed" if live_provider else "local_fallback_active"
    return {
        "kind": "openmaic_lesson",
        "mode": "openmaic_native",
        "engine": "OpenMAIC-adapted slide classroom",
        "title": str(manifest.get("title") or "Narrated study lesson")[:240],
        "question": question,
        "requestedDurationSeconds": requested_duration,
        "actualDurationSeconds": per_slide * len(slides),
        "providerId": provider_id,
        "providerModel": provider_model,
        "providerStatus": provider_status,
    "citationValidation": "passed" if live_provider else "source-derived",
        "provenance": _artifact_provenance(
            provider=provider_id,
            model=provider_model,
            status=provider_status,
            citation_validation="passed" if live_provider else "source-derived",
            reason=None if live_provider else "active_provider_not_configured_or_fixture_mode",
        ),
        "voiceProviderId": "voxcpm-python" if any(slide.get("audio") for slide in slides) else None,
        "slides": slides,
        "assets": pack.get("assets") or [],
        "assetCatalog": asset_catalog,
        "sourceIds": sorted({str(source_id) for section in sections for source_id in section.get("sourceIds") or []}),
        "webSources": web["sources"],
        "groundedIn": "mixed" if source_context and web["context"] else "web" if web["context"] else "notebook",
    }
