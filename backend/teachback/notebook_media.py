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

from .notebook_pipeline import _section_asset_ids, _section_diagram, _section_preview
from .providers import ProviderOutputError, ProviderUnavailable, provider_for
from .remediation_video_views import _generate_voice


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
    for section in pack.get("sections") or []:
        title = str(section.get("title") or "")
        text = _section_text(section)
        words = _tokens(f"{title} {text}")
        score = len(query.intersection(words))
        if query and query.intersection(_tokens(title)):
            score += 4
        if score:
            ranked.append((score, -int(section.get("order") or 0), section))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return [section for _, _, section in ranked[:6]]


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


def _source_context(sections: list[dict]) -> str:
    chunks: list[str] = []
    for section in sections:
        anchor_lines = []
        for block in section.get("blocks") or []:
            if str(block.get("type") or "").casefold() == "image":
                continue
            text = str(block.get("markdown") or "").strip()
            if not text:
                continue
            anchor = str(block.get("sourceAnchor") or block.get("blockId") or section.get("sectionId") or "source")
            page = f" page={block['page']}" if block.get("page") else ""
            anchor_lines.append(f"[{anchor}{page}] {text[:1800]}")
        if anchor_lines:
            chunks.append(f"## {section.get('title') or 'Topic'}\n" + "\n".join(anchor_lines[:8]))
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
    sections = _rank_sections(pack, question)
    web = {"sources": [], "context": ""}
    if allow_web_search and _needs_web(question, sections):
        web = _web_search(question)
    return sections, _source_context(sections), web


def answer_notebook_question(pack: dict, question: str, *, allow_web_search: bool = True) -> dict:
    sections, source_context, web = _context_for_question(pack, question, allow_web_search)
    source_ids = sorted({str(source_id) for section in sections for source_id in section.get("sourceIds") or []})
    allowed_anchors = _anchors_for_sections(sections)
    if not source_context and not web["context"]:
        return {"answer": "I could not find this in the uploaded notebook, and no web result was available. Try naming the topic or enable web fallback.", "sourceIds": [], "sourceAnchorIds": [], "webSources": [], "groundedIn": "insufficient", "fallbackUsed": False}
    try:
        result = provider_for("fireworks").answer_notebook_question({
            "question": question,
            "sourceContext": source_context,
            "webContext": web["context"],
            "allowedAnchorIds": allowed_anchors,
        })
        grounded = str(result.get("groundedIn") or ("mixed" if source_context and web["context"] else "web" if web["context"] else "notebook"))
        return {
            "answer": str(result.get("answer") or "The provider did not return an answer.").strip(),
            "sourceIds": source_ids,
            "sourceAnchorIds": [str(item) for item in result.get("sourceAnchorIds") or [] if str(item) in set(allowed_anchors)],
            "webSources": web["sources"],
            "groundedIn": grounded if grounded in {"notebook", "web", "mixed", "insufficient"} else "notebook",
            "fallbackUsed": bool(web["context"]),
        }
    except (ProviderUnavailable, ProviderOutputError):
        excerpt = _section_preview(sections[0]) if sections else web["context"][:1200]
        return {"answer": excerpt or "The configured teaching model is unavailable right now.", "sourceIds": source_ids, "sourceAnchorIds": allowed_anchors[:3], "webSources": web["sources"], "groundedIn": "notebook" if source_context else "web", "fallbackUsed": bool(web["context"]), "degraded": True}


def _safe_diagram(value: object) -> dict:
    if not isinstance(value, dict):
        return {"nodes": [], "edges": []}
    nodes = [node for node in value.get("nodes") or [] if isinstance(node, dict) and node.get("id")][:8]
    ids = {str(node["id"]) for node in nodes}
    edges = [edge for edge in value.get("edges") or [] if isinstance(edge, dict) and str(edge.get("from")) in ids and str(edge.get("to")) in ids][:12]
    return {"nodes": [{"id": str(node["id"])[:40], "label": str(node.get("label") or node["id"])[:100]} for node in nodes], "edges": edges}


def _local_lesson_manifest(sections: list[dict], question: str, anchor_ids: list[str], asset_ids: list[str], web_context: str) -> dict:
    """Keep the lesson usable during a transient model/JSON failure."""
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
    try:
        manifest = provider_for("fireworks").generate_openmaic_lesson({
            "question": question,
            "sourceContext": source_context,
            "webContext": web["context"],
            "allowedAnchorIds": allowed_anchors,
            "allowedAssetIds": allowed_asset_ids,
        })
    except (ProviderUnavailable, ProviderOutputError):
        manifest = _local_lesson_manifest(sections, question, allowed_anchors, allowed_asset_ids, web["context"])
    raw_slides = manifest.get("slides") if isinstance(manifest, dict) else None
    if not isinstance(raw_slides, list) or not 4 <= len(raw_slides) <= 8:
        manifest = _local_lesson_manifest(sections, question, allowed_anchors, allowed_asset_ids, web["context"])
        raw_slides = manifest["slides"]
    topic_anchors = allowed_anchors[:8]
    per_slide = max(8, requested_duration // len(raw_slides))
    slides: list[dict] = []
    for index, raw in enumerate(raw_slides[:8]):
        if not isinstance(raw, dict):
            continue
        source_anchor_ids = [str(item) for item in raw.get("sourceAnchorIds") or [] if str(item) in set(allowed_anchors)] or topic_anchors
        asset_ids = [str(item) for item in raw.get("assetIds") or [] if str(item) in set(allowed_asset_ids)]
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
    return {
        "kind": "openmaic_lesson",
        "mode": "openmaic_native",
        "engine": "OpenMAIC-adapted slide classroom",
        "title": str(manifest.get("title") or "Narrated study lesson")[:240],
        "question": question,
        "requestedDurationSeconds": requested_duration,
        "actualDurationSeconds": per_slide * len(slides),
        "providerId": "fireworks-qwen3p7-plus",
        "voiceProviderId": "voxcpm-python" if any(slide.get("audio") for slide in slides) else None,
        "slides": slides,
        "assets": pack.get("assets") or [],
        "assetCatalog": asset_catalog,
        "sourceIds": sorted({str(source_id) for section in sections for source_id in section.get("sourceIds") or []}),
        "webSources": web["sources"],
        "groundedIn": "mixed" if source_context and web["context"] else "web" if web["context"] else "notebook",
    }
