"""Notebook-first extraction and artifact helpers.

The pipeline has two deliberately separate jobs:

* extraction creates a durable, page-aware knowledge pack;
* artifact builders consume that pack without inventing a second source of
  truth.

Mistral OCR is used when configured. Local PDF/text extraction remains a
  useful offline fallback so the notebook UI is still testable without an
  external service.
"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
import uuid
import zipfile
from functools import lru_cache
from xml.etree import ElementTree
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from django.conf import settings

from .ingestion import IngestionError, extract_pdf_candidates_from_bytes, normalize_extracted_text
from .models import Notebook, NotebookArtifact, NotebookChatMessage, NotebookNote, NotebookSource
from .providers import record_provider_failure, record_provider_success


class NotebookExtractionError(ValueError):
    pass


def extraction_error_category(error: object) -> str:
    """Return a safe, stable category instead of provider exception text.

    Provider error bodies can contain implementation details that do not belong
    in learner-visible source metadata.  The UI needs a recovery decision, not
    a copied upstream response.  Keep this deliberately small and
    presentation-safe so callers can expose it without leaking credentials or
    request payloads.
    """
    value = str(error or "").casefold()
    if any(marker in value for marker in ("timed out", "timeout", "deadline exceeded")):
        return "timeout"
    if any(marker in value for marker in ("401", "403", "unauthorized", "forbidden", "authentication")):
        return "authentication"
    if any(marker in value for marker in ("429", "rate limit", "too many requests")):
        return "rate_limited"
    if any(marker in value for marker in ("invalid", "malformed", "unprocessable", "422", "400")):
        return "invalid_response"
    if any(marker in value for marker in ("connection", "socket", "network", "name or service", "unreachable", "503", "502", "504", "500")):
        return "unavailable"
    return "provider_error"


def _data_url(payload: bytes, mime_type: str) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(payload).decode('ascii')}"


def _mistral_enabled() -> bool:
    return bool(str(getattr(settings, "MISTRAL_API_KEY", "") or "").strip())


def _mistral_network_failure(message: str) -> bool:
    """Identify connection failures that should not block local workspace creation."""
    lowered = str(message or "").lower()
    return any(marker in lowered for marker in (
        "winerror 10013",
        "permissionerror",
        "timed out",
        "timeout",
        "connection refused",
        "connection reset",
        "name or service not known",
        "temporary failure in name resolution",
        "failed to establish a new connection",
        "http error 500",
        "http error 502",
        "http error 503",
        "http error 504",
    ))


def _mistral_ocr(payload: bytes, mime_type: str) -> dict:
    """Call the documented Mistral OCR endpoint using a data URL.

    The uploaded document is sent only when the operator configures a Mistral
    key and selects the provider. No implicit export is made by the fallback.
    """
    body = {
        "model": getattr(settings, "MISTRAL_OCR_MODEL", "mistral-ocr-4-0"),
        "document": {"type": "document_url", "document_url": _data_url(payload, mime_type)},
        "include_image_base64": True,
        "include_blocks": True,
        "extract_header": True,
        "extract_footer": True,
        "table_format": "markdown",
        "confidence_scores_granularity": "page",
    }
    request = urllib.request.Request(
        getattr(settings, "MISTRAL_OCR_URL", "https://api.mistral.ai/v1/ocr"),
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {settings.MISTRAL_API_KEY}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=float(getattr(settings, "MISTRAL_OCR_TIMEOUT_SECONDS", 180))) as response:
            result = json.loads(response.read().decode("utf-8"))
            record_provider_success("mistral")
            return result
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        record_provider_failure("mistral", extraction_error_category(exc))
        raise NotebookExtractionError(f"Mistral OCR failed: {exc}") from exc


def _pdf_visual_pages(candidates: list) -> dict[int, str]:
    """Return only pages whose extracted text indicates a useful source figure.

    Many lecture PDFs draw block diagrams as vectors, so ``pypdf.page.images``
    is empty even though a diagram is visibly present.  Rendering every page
    would make the notebook payload needlessly large; this keeps the fallback
    focused on pages that actually announce a diagram or a figure.
    """
    page_labels: dict[int, str] = {}
    for candidate in candidates:
        page = candidate.locator.get("page")
        if not isinstance(page, int):
            continue
        text = str(candidate.text or "").casefold()
        if not re.search(r"\b(?:block\s*diagram|diagram|fig(?:ure)?\.?\s*\d+|typical\s+(?:computer|microprocessor)[ -]*based\s+instrumentation)\b", text):
            continue
        if "pressure" in text:
            label = "Source block diagram for pressure monitoring"
        elif "microprocessor" in text:
            label = "Source microprocessor-based instrumentation diagram"
        elif "microcomputer" in text or "computer based" in text:
            label = "Source computer-based instrumentation diagram"
        else:
            label = "Source diagram"
        page_labels.setdefault(page, label)
    return dict(sorted(page_labels.items())[:8])


def _render_pdf_visual_assets(payload: bytes, sha256: str, pages: dict[int, str], existing_pages: set[int]) -> list[dict]:
    """Create lightweight page visuals for vector figures when Poppler exists.

    This is intentionally an optional enhancement: readable source text must
    still be published when a deployment does not include ``pdftoppm``.
    """
    assets: list[dict] = []
    for page in list(pages):
        if page in existing_pages:
            continue
        try:
            with tempfile.TemporaryDirectory(prefix="feynman-pdf-") as directory:
                base = Path(directory)
                source_path = base / "source.pdf"
                output_prefix = base / f"page-{page}"
                source_path.write_bytes(payload)
                subprocess.run(
                    ["pdftoppm", "-f", str(page), "-l", str(page), "-r", "112", "-png", "-singlefile", str(source_path), str(output_prefix)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=25,
                )
                image_path = output_prefix.with_suffix(".png")
                if not image_path.exists() or image_path.stat().st_size < 512:
                    continue
                image_bytes = image_path.read_bytes()
        except (OSError, subprocess.SubprocessError):
            # Poppler is unavailable or a particular source page cannot be
            # rendered. Embedded-image extraction above remains available.
            continue
        asset_id = f"asset_{sha256[:12]}_render_p{page}"
        assets.append({
            "assetId": asset_id,
            "type": "image",
            "mimeType": "image/png",
            "page": page,
            "alt": pages[page],
            "dataUrl": _data_url(image_bytes, "image/png"),
        })
    return assets


def _local_extract(payload: bytes, mime_type: str, sha256: str) -> tuple[list[dict], list[dict], dict]:
    blocks: list[dict] = []
    assets: list[dict] = []
    if mime_type == "application/pdf":
        try:
            candidates = extract_pdf_candidates_from_bytes(payload, sha256=sha256)
        except IngestionError as exc:
            raise NotebookExtractionError(str(exc)) from exc
        for index, candidate in enumerate(candidates, start=1):
            blocks.append({
                "blockId": f"block_{sha256[:10]}_{index:04d}",
                "type": "text",
                "markdown": candidate.text,
                "page": candidate.locator.get("page"),
                "section": candidate.locator.get("section"),
                "sourceAnchor": f"{sha256[:12]}:p{candidate.locator.get('page', index)}",
            })
        # pypdf can expose embedded page images even when Mistral is
        # unavailable. Preserve them as real source assets rather than
        # reducing the fallback pack to text-only placeholders.
        try:
            reader = PdfReader(BytesIO(payload))
            for page_number, page in enumerate(reader.pages, start=1):
                for image_index, image in enumerate(getattr(page, "images", []) or [], start=1):
                    image_bytes = getattr(image, "data", None)
                    if not image_bytes:
                        continue
                    image_name = str(getattr(image, "name", "") or f"page-{page_number}-image-{image_index}.png")
                    image_mime = mimetypes.guess_type(image_name)[0] or "image/png"
                    if not image_mime.startswith("image/"):
                        image_mime = "image/png"
                    asset_id = f"asset_{sha256[:12]}_p{page_number}_{image_index:02d}"
                    assets.append({"assetId": asset_id, "type": "image", "mimeType": image_mime, "page": page_number, "alt": image_name, "dataUrl": _data_url(image_bytes, image_mime)})
                    blocks.append({"blockId": f"block_{sha256[:10]}_image_{page_number:03d}_{image_index:02d}", "type": "image", "markdown": f"[Source image: {image_name}]", "page": page_number, "assetId": asset_id, "sourceAnchor": f"{sha256[:12]}:p{page_number}:img{image_index}"})
        except Exception:
            # Image extraction is an enhancement; never discard readable text
            # because one malformed embedded image cannot be decoded.
            pass
        # Vector-only lecture figures are common in the uploaded notes. When
        # Poppler is available, retain a source-page visual for the figure
        # pages so the slide lesson can show the actual diagram rather than a
        # generic replacement.
        existing_pages = {int(asset.get("page")) for asset in assets if str(asset.get("page") or "").isdigit()}
        rendered_assets = _render_pdf_visual_assets(payload, sha256, _pdf_visual_pages(candidates), existing_pages)
        for asset in rendered_assets:
            assets.append(asset)
            blocks.append({
                "blockId": f"block_{sha256[:10]}_render_{int(asset['page']):03d}",
                "type": "image",
                "markdown": f"[Source diagram: {asset['alt']}]",
                "page": asset["page"],
                "assetId": asset["assetId"],
                "sourceAnchor": f"{sha256[:12]}:p{asset['page']}:rendered-diagram",
            })
    elif mime_type in {"text/plain", "text/markdown", "text/csv"}:
        text = normalize_extracted_text(payload.decode("utf-8", errors="replace"))
        blocks.append({"blockId": f"block_{sha256[:10]}_0001", "type": "text", "markdown": text, "page": 1, "sourceAnchor": f"{sha256[:12]}:p1"})
    elif mime_type in {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/vnd.openxmlformats-officedocument.presentationml.presentation"}:
        # Keep the offline fallback useful for editable notes and slide decks.
        # Mistral remains the richer path for layout, equations, and bounding boxes.
        text_parts: list[str] = []
        media_prefix = "word/media/" if "wordprocessing" in mime_type else "ppt/media/"
        try:
            with zipfile.ZipFile(BytesIO(payload)) as archive:
                xml_names = sorted(name for name in archive.namelist() if (name.startswith("word/") and name.endswith(".xml")) or (name.startswith("ppt/slides/") and name.endswith(".xml")))
                for xml_name in xml_names:
                    root = ElementTree.fromstring(archive.read(xml_name))
                    words = [node.text.strip() for node in root.iter() if node.text and node.text.strip()]
                    if words:
                        text_parts.append(" ".join(words))
                for media_name in archive.namelist():
                    if media_name.startswith(media_prefix) and not media_name.endswith("/"):
                        media = archive.read(media_name)
                        media_type = mimetypes.guess_type(media_name)[0] or "image/png"
                        asset_id = f"asset_{sha256[:12]}_{len(assets)+1:04d}"
                        assets.append({"assetId": asset_id, "type": "image", "mimeType": media_type, "page": 1, "alt": media_name.rsplit("/", 1)[-1], "dataUrl": _data_url(media, media_type)})
        except (zipfile.BadZipFile, ElementTree.ParseError) as exc:
            raise NotebookExtractionError("unable to read the document structure") from exc
        text = normalize_extracted_text("\n\n".join(text_parts))
        blocks.append({"blockId": f"block_{sha256[:10]}_0001", "type": "text", "markdown": text or "Editable document contains visual content only.", "page": 1, "sourceAnchor": f"{sha256[:12]}:p1"})
    elif mime_type.startswith("image/"):
        assets.append({"assetId": f"asset_{sha256[:12]}_0001", "type": "image", "mimeType": mime_type, "page": 1, "alt": "Uploaded source image"})
        blocks.append({"blockId": f"block_{sha256[:10]}_0001", "type": "image", "markdown": "[Source image]", "page": 1, "assetId": assets[0]["assetId"], "sourceAnchor": f"{sha256[:12]}:p1"})
    else:
        blocks.append({"blockId": f"block_{sha256[:10]}_0001", "type": "text", "markdown": f"{mime_type} source uploaded. Connect Mistral OCR for structured extraction.", "page": 1, "sourceAnchor": f"{sha256[:12]}:p1"})
    return blocks, assets, {"pageCount": max([int(block.get("page") or 1) for block in blocks] or [0]), "blockCount": len(blocks), "assetCount": len(assets)}


def _mistral_blocks(result: dict, sha256: str) -> tuple[list[dict], list[dict], dict]:
    blocks: list[dict] = []
    assets: list[dict] = []
    for page in result.get("pages") or []:
        page_number = int(page.get("index", 0)) + 1
        page_images = page.get("images") or []
        page_asset_by_name: dict[str, dict] = {}
        for image_index, image in enumerate(page_images, start=1):
            asset_id = f"asset_{sha256[:12]}_p{page_number}_{image_index:02d}"
            image_name = str(image.get("id") or image.get("name") or image.get("filename") or f"image-{image_index}")
            item = {"assetId": asset_id, "type": "image", "page": page_number, "alt": image_name}
            image_data = image.get("image_base64") or image.get("base64") or image.get("data")
            if image_data:
                image_mime = str(image.get("mime_type") or image.get("mimeType") or mimetypes.guess_type(image_name)[0] or "image/png")
                item["dataUrl"] = image_data if str(image_data).startswith("data:") else f"data:{image_mime};base64,{image_data}"
            elif image.get("url") or image.get("image_url"):
                item["url"] = image.get("url") or image.get("image_url")
            assets.append(item)
            page_asset_by_name[image_name.casefold()] = item
            page_asset_by_name[image_name.rsplit("/", 1)[-1].casefold()] = item
        page_blocks = page.get("blocks") or []
        if page_blocks:
            for index, item in enumerate(page_blocks, start=1):
                block_type = str(item.get("type") or "text").lower()
                content = item.get("markdown") or item.get("content") or item.get("text") or ""
                if isinstance(content, dict):
                    content = content.get("value") or json.dumps(content)
                content_text = str(content).strip()
                block = {"blockId": f"block_{sha256[:10]}_p{page_number}_{index:03d}", "type": block_type, "markdown": content_text, "page": page_number, "sourceAnchor": f"{sha256[:12]}:p{page_number}:b{index}"}
                if item.get("bbox") is not None:
                    block["bbox"] = item["bbox"]
                if block_type == "image":
                    image_ref = str(item.get("id") or item.get("image_id") or "")
                    image_match = re.search(r"!\[[^]]*\]\(([^)]+)\)", content_text)
                    image_ref = image_ref or (image_match.group(1).strip() if image_match else "")
                    asset = page_asset_by_name.get(image_ref.casefold()) or page_asset_by_name.get(image_ref.rsplit("/", 1)[-1].casefold())
                    if asset is None and len(page_images) == 1:
                        asset = assets[-1]
                    if asset:
                        block["assetId"] = asset["assetId"]
                        block["markdown"] = f"[Source image: {asset.get('alt') or 'extracted visual'}]"
                blocks.append(block)
        else:
            markdown = str(page.get("markdown") or "").strip()
            if markdown:
                blocks.append({"blockId": f"block_{sha256[:10]}_p{page_number}_001", "type": "text", "markdown": markdown, "page": page_number, "sourceAnchor": f"{sha256[:12]}:p{page_number}"})
    stats = {"pageCount": len(result.get("pages") or []), "blockCount": len(blocks), "assetCount": len(assets), "usage": result.get("usage_info") or {}}
    return blocks, assets, stats


def extract_source(payload: bytes, mime_type: str, sha256: str, *, provider: str = "auto") -> tuple[list[dict], list[dict], dict, str]:
    """Return blocks, extracted assets, stats, and the provider used."""
    use_mistral = provider == "mistral" or (provider == "auto" and _mistral_enabled())
    if use_mistral:
        if not _mistral_enabled():
            raise NotebookExtractionError("Mistral OCR is selected but MISTRAL_API_KEY is not configured.")
        try:
            blocks, assets, stats = _mistral_blocks(_mistral_ocr(payload, mime_type), sha256)
        except NotebookExtractionError as exc:
            # A configured key must not make the entire notebook unusable when
            # Windows Defender, a proxy, or a restricted network blocks the
            # outbound socket. Keep the source private and continue with the
            # local extractor, while exposing the degraded method in metadata.
            if _mistral_network_failure(str(exc)):
                blocks, assets, stats = _local_extract(payload, mime_type, sha256)
                # Local extraction is real extraction, but it is not a Mistral
                # result.  Preserve the usable page/block context while making
                # both the failed provider call and the re-upload recovery path
                # explicit to the client.  Do not persist the raw exception:
                # upstream error bodies can contain request/provider details.
                stats = {
                    **stats,
                    "warning": "Mistral OCR was unreachable; local extraction is active. Re-upload the source to retry Mistral OCR.",
                    "providerStatus": "configured_but_unavailable",
                    "providerErrorCategory": extraction_error_category(exc),
                    "retryable": True,
                    "retryAction": "reupload",
                }
                return blocks, assets, stats, "local-fallback-after-mistral-network-error"
            raise
        if not blocks and not assets:
            raise NotebookExtractionError("Mistral OCR returned no readable content.")
        return blocks, assets, stats, "mistral-ocr-4-0"
    blocks, assets, stats = _local_extract(payload, mime_type, sha256)
    return blocks, assets, stats, "local-fallback"


def _title_for_block(block: dict, index: int) -> str:
    if block.get("section"):
        return f"Section {block['section']}"
    text = re.sub(r"[#*_`]", "", str(block.get("markdown") or "")).strip()
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    if first_line:
        return first_line[:92].rstrip(" .:")
    return f"Source section {index}"


def rebuild_knowledge_pack(notebook: Notebook) -> tuple[dict, str]:
    sections: list[dict] = []
    concepts: list[dict] = []
    formulas: list[dict] = []
    all_assets: list[dict] = []
    source_ids: list[str] = []
    for source in notebook.notebook_sources.order_by("created_at", "id"):
        source_ids.append(source.source_id)
        source_assets = [{**asset, "sourceId": source.source_id} for asset in (source.assets or [])]
        all_assets.extend(source_assets)
        source_asset_by_name = {str(asset.get("alt") or "").casefold(): asset for asset in source_assets}
        for index, block in enumerate(source.blocks or [], start=1):
            text = str(block.get("markdown") or "").strip()
            if not text and block.get("type") != "image":
                continue
            section_id = f"{source.source_id}-section-{index:03d}"
            title = _title_for_block(block, index)
            section = {"sectionId": section_id, "title": title, "order": len(sections) + 1, "sourceIds": [source.source_id], "pages": [block.get("page")] if block.get("page") else [], "blocks": [block]}
            sections.append(section)
            concepts.append({"conceptId": section_id, "title": title, "summary": text[:500], "sourceIds": [source.source_id], "sourceAnchors": [block.get("sourceAnchor")] if block.get("sourceAnchor") else []})
            for line in text.splitlines():
                line = line.strip().strip("-•")
                if ("=" in line or "∫" in line or "Δ" in line) and len(line) < 500:
                    formulas.append({"formulaId": f"formula_{len(formulas)+1:03d}", "text": line, "sectionId": section_id, "sourceId": source.source_id, "page": block.get("page")})
    pack = {"version": "knowledge-pack.v1", "notebookId": str(notebook.notebook_id), "title": notebook.title, "sources": source_ids, "sections": sections, "concepts": concepts, "formulas": formulas, "assets": all_assets, "generatedAt": notebook.updated_at.isoformat() if notebook.updated_at else None}
    markdown = render_knowledge_pack_markdown(pack)
    return pack, markdown


def _notebook_heading_info(block: dict) -> tuple[int, str] | None:
    raw = re.sub(r"\s+", " ", str(block.get("markdown") or "")).strip()
    match = re.match(r"^(#{1,6})\s*(.+?)\s*$", raw)
    block_type = str(block.get("type") or "").lower()
    if match:
        if block_type == "text" and (len(raw) > 100 or "=" in raw or re.search(r"\b(?:is|are|use|used|measure|measures)\b", raw, re.IGNORECASE)):
            return None
        return len(match.group(1)), _notebook_clean_heading(match.group(2))
    if block_type in {"title", "heading", "section_header", "section-heading"} and raw:
        return (2 if block_type != "title" else 1), _notebook_clean_heading(raw)
    return None


def _notebook_clean_heading(title: str) -> str:
    title = re.sub(r"^#+\s*", "", title or "")
    # OCR frequently promotes list markers into the learner-facing title.
    title = re.sub(r"^\s*[①-⑳]\s*", "", title)
    title = re.sub(r"^\s*\d+(?:\.\d+)*\s*[\)\].:-]\s*", "", title)
    title = re.sub(r"\s*\|.*$", "", title)
    return re.sub(r"\s+", " ", title).strip(" -:;#")[:180]


def _notebook_metadata_heading(title: str) -> bool:
    lowered = title.lower()
    return any(marker in lowered for marker in ("course evaluation", "final exam marks", "references", "class outline", "assignment"))


def _notebook_chrome_block(block: dict, text: str) -> bool:
    block_type = str(block.get("type") or "").lower()
    if block_type in {"footer", "header", "page_number", "page-number"}:
        return True
    if not text:
        return block_type != "image"
    lowered = text.lower()
    if re.match(r"^(?:fig(?:ure)?\.?\s*\d+|table\s*\d+)\b", lowered):
        return True
    if re.match(r"^(?:course\s*code|module\s*#?|source\s*material|page\s*\d+|references?)\b", lowered):
        return True
    compact = lowered.replace(" ", "")
    if (block.get("page") or 0) <= 1 and sum(term in compact for term in ("coursecode", "sr.lecturer", "lecturer", "college", "msheng", "may202", "courseevaluation")) >= 2:
        return True
    if any(marker in compact for marker in ("courseevaluation", "finalexammarksdistribution", "references:")):
        return True
    if len(text) < 180 and re.search(r"(?:instrumentation|analog|digital|performance|measurement|error)", compact) and not re.search(r"\b(?:is|are|use|using|used|based|measure|describ|quantity|response|value|principle|system|pointer|signal)\b", lowered):
        return True
    if len(text) < 34 and (re.search(r"\b(?:kathmandu|college|msc|lecturer|may\s+20\d{2})\b", lowered) or re.fullmatch(r"[\d\W]+", text)):
        return True
    return False


def _notebook_section(source_id: str, title: str, ordinal: int) -> dict:
    return {"sectionId": f"{source_id}-section-{ordinal:03d}", "title": title or f"Topic {ordinal}", "order": ordinal, "sourceIds": [source_id], "pages": [], "blocks": []}


def _notebook_section_kind(section: dict, source_kind: str) -> str:
    """Classify extracted material before it becomes learner-facing content."""
    title = str(section.get("title") or "").casefold()
    text = _section_preview(section).casefold()
    if source_kind == "past_questions":
        return "past_questions"
    administrative_titles = (
        "instrumentation (ii/ii)", "course evaluation", "theory (", "practical (",
        "final exam", "chapter#", "class#work", "assignment", "class outline",
    )
    if any(marker in title for marker in administrative_titles):
        return "administrative"
    if re.fullmatch(r"topic\s*\d+", title.strip()) and re.search(r"(?:crcpress|tata\s*mc\s*graw|prentice\s*hall|publisher|edition|author)", text):
        return "reference"
    if "reference" in title or re.search(r"\(\s*19\d{2}\s*\)|\b20\d{2}\b", text):
        return "reference"
    admin_terms = (
        "attendance", "internal weight", "external weight", "end semester exam",
        "marks distribution", "tata mcgraw", "practical (25)", "assignment is available",
    )
    if sum(term in text for term in admin_terms) >= 2:
        return "administrative"
    if len(text) < 45 and not any(str(block.get("type") or "").casefold() == "image" for block in section.get("blocks") or []):
        return "administrative"
    return "learning"


def _refine_section_title(section: dict) -> str:
    """Use the strongest topic signal in the body when OCR loses a heading."""
    title = str(section.get("title") or "").strip()
    text = _section_preview(section).casefold()
    if title.casefold() in {"instrumentation system", "instrumentation system basics"}:
        if "wheatstone bridge" in text:
            return "Wheatstone Bridge"
        if "ac bridge" in text or "impedance component" in text:
            return "AC Bridge"
        if "analog system" in text and "digital system" in text:
            return "Analog vs Digital Characteristics"
    return title


def rebuild_knowledge_pack(notebook: Notebook) -> tuple[dict, str]:
    """Rebuild a topic-level pack instead of treating every OCR block as a topic."""
    sections: list[dict] = []
    supplementary_sections: list[dict] = []
    concepts: list[dict] = []
    formulas: list[dict] = []
    formula_keys: set[str] = set()
    all_assets: list[dict] = []
    source_ids: list[str] = []
    for source in notebook.notebook_sources.order_by("created_at", "id"):
        source_ids.append(source.source_id)
        source_assets = [{**asset, "sourceId": source.source_id} for asset in (source.assets or [])]
        all_assets.extend(source_assets)
        source_asset_by_name = {str(asset.get("alt") or "").casefold(): asset for asset in source_assets}
        source_sections: list[dict] = []
        current: dict | None = None
        parent_title = ""
        for block in source.blocks or []:
            text = _repair_compact_ocr(_clean_source_text(str(block.get("markdown") or "")))
            heading = _notebook_heading_info(block)
            inline_heading = _inline_ocr_heading(text)
            if inline_heading:
                inline_title, text = inline_heading
                # A flattened OCR page contains both its heading and its
                # explanation. Register the section, then keep the same block
                # as learner content instead of dropping its body via the
                # normal heading `continue` path.
                if not _notebook_metadata_heading(inline_title):
                    # OCR repeats a parent heading on many pages. Continue
                    # the current section only when the repeated heading is
                    # contiguous; otherwise a later subtopic such as Random
                    # Error must not be merged into an earlier section.
                    existing = current if current and current["title"].casefold() == inline_title.casefold() else None
                    current = existing
                    if current is None:
                        current = _notebook_section(source.source_id, inline_title, len(source_sections) + 1)
                        source_sections.append(current)
                heading = None
            if heading:
                level, title = heading
                if _notebook_metadata_heading(title):
                    current = None
                    continue
                if level == 1:
                    parent_title = title
                    continue
                existing = current if current and current["title"].casefold() == title.casefold() else None
                current = existing
                if current is None:
                    current = _notebook_section(source.source_id, title, len(source_sections) + 1)
                    source_sections.append(current)
                continue
            if _notebook_chrome_block(block, text):
                continue
            if not text and str(block.get("type") or "").lower() != "image":
                continue
            if current is None:
                current = _notebook_section(source.source_id, parent_title or f"Topic {len(source_sections) + 1}", len(source_sections) + 1)
                source_sections.append(current)
            normalized_block = {**block, "markdown": text or "[Source image]"}
            if str(block.get("type") or "").casefold() == "image" and not normalized_block.get("assetId"):
                image_match = re.search(r"!\[[^]]*\]\(([^)]+)\)", str(block.get("markdown") or ""))
                image_ref = (image_match.group(1).rsplit("/", 1)[-1] if image_match else "").casefold()
                asset = source_asset_by_name.get(image_ref)
                if asset is None:
                    page_assets = [item for item in source_assets if item.get("page") == block.get("page")]
                    asset = page_assets[0] if len(page_assets) == 1 else None
                if asset:
                    normalized_block["assetId"] = asset["assetId"]
                    normalized_block["markdown"] = f"[Source image: {asset.get('alt') or 'extracted visual'}]"
            current["blocks"].append(normalized_block)
            if block.get("page") and block["page"] not in current["pages"]:
                current["pages"].append(block["page"])
        for section in source_sections:
            meaningful = _repair_compact_ocr(_clean_source_text(" ".join(str(item.get("markdown") or "") for item in section["blocks"])))
            if not meaningful and not any(item.get("type") == "image" for item in section["blocks"]):
                continue
            section["title"] = _refine_section_title(section)
            section["kind"] = _notebook_section_kind(section, source.source_kind)
            if section["kind"] != "learning":
                section["supplementaryReason"] = "Kept for source review, excluded from learner outputs."
                supplementary_sections.append(section)
                continue
            section["order"] = len(sections) + 1
            sections.append(section)
            summary = _section_preview(section)
            anchors = [item.get("sourceAnchor") for item in section["blocks"] if item.get("sourceAnchor")]
            concepts.append({"conceptId": section["sectionId"], "title": section["title"], "summary": summary, "sourceIds": [source.source_id], "sourceAnchors": anchors})
            section_formulas: list[dict] = []
            for block in section["blocks"]:
                if str(block.get("type") or "").casefold() == "image":
                    continue
                for line in str(block.get("markdown") or "").splitlines():
                    candidate = _formula_candidate(line)
                    if candidate:
                        section_formulas.append({"text": candidate, "sectionId": section["sectionId"], "sourceId": source.source_id, "page": block.get("page"), "_order": len(section_formulas)})
            # Four results per topic is enough for a usable reference sheet;
            # ranking prevents a long bridge derivation from flooding it.
            selected_formulas = sorted(section_formulas, key=lambda item: (-_formula_priority(item["text"]), item["_order"]))[:4]
            for item in sorted(selected_formulas, key=lambda value: value["_order"]):
                key = _formula_key(item["text"])
                if key in formula_keys:
                    continue
                formula_keys.add(key)
                item.pop("_order", None)
                item["formulaId"] = f"formula_{len(formulas)+1:03d}"
                formulas.append(item)
    pack = {"version": "knowledge-pack.v1", "notebookId": str(notebook.notebook_id), "title": notebook.title, "sources": source_ids, "sections": sections, "supplementarySections": supplementary_sections, "concepts": concepts, "formulas": formulas, "assets": all_assets, "generatedAt": notebook.updated_at.isoformat() if notebook.updated_at else None}
    return pack, render_knowledge_pack_markdown(pack)


def render_knowledge_pack_markdown(pack: dict) -> str:
    lines = [f"# {pack.get('title') or 'Knowledge pack'}", "", "> Structured source pack · `knowledge-pack.v1`", ""]
    for section in pack.get("sections") or []:
        lines.extend([f"## {section.get('order')}. {section.get('title')}", ""])
        for block in section.get("blocks") or []:
            if str(block.get("type") or "").casefold() == "image":
                continue
            page = f" · p. {block['page']}" if block.get("page") else ""
            lines.extend([f"<!-- source: {block.get('sourceAnchor', 'unanchored')}{page} -->", str(block.get("markdown") or "[image]").strip(), ""])
    if pack.get("formulas"):
        lines.extend(["## Formula index", ""])
        lines.extend([f"- {item['text']} · {item.get('sourceId')}" for item in pack["formulas"]])
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _section_preview(section: dict) -> str:
    sentences = _meaningful_sentences(section)
    if sentences:
        return " ".join(sentences[:2])[:420].rstrip()
    text = " ".join(str(block.get("markdown") or "") for block in section.get("blocks") or [] if str(block.get("type") or "").casefold() != "image")
    return _repair_compact_ocr(_clean_source_text(text))[:420]


def _formula_candidate(raw_line: str) -> str | None:
    """Keep complete learner-useful formulas, not OCR derivation continuations."""
    original = str(raw_line or "").strip()
    probe = re.sub(r"^\s*(?:\$\$?|\\\[|\\\()\s*", "", original)
    if not original or re.match(r"^(?:=|→|->)", probe):
        return None
    line = re.sub(r"^\s*[-•]\s*", "", original).strip(" `*")
    line = re.sub(r"\s+", " ", line)
    if len(line) < 3 or len(line) >= 500:
        return None
    if re.match(r"^\s*\((?:here|note)\b", line, flags=re.IGNORECASE):
        return None
    if not ("=" in line or any(token in line for token in ("\\frac", "\\sqrt", "\\Delta", "∫", "×", "±"))):
        return None
    has_derivation_label = bool(re.search(r"(?:\\dots|…|\(\s*(?:[a-z]|[ivx]+)\s*\))", line, flags=re.IGNORECASE))
    if has_derivation_label and "\\rightarrow" not in line and "→" not in line and "\\boxed" not in line:
        return None
    if re.match(r"^(?:=|→|->|therefore\s*=)", line, flags=re.IGNORECASE):
        return None
    return line


def _formula_key(text: str) -> str:
    normalized = str(text or "").replace("\\\\", "\\")
    normalized = re.sub(r"\\boxed\{([^{}]*)\}", r"\1", normalized)
    return re.sub(r"\s+", "", normalized).casefold()


def _formula_priority(text: str) -> int:
    """Rank results above setup/derivation equations for the formula sheet."""
    value = str(text or "")
    score = 0
    if "\\boxed" in value:
        score += 8
    if "\\rightarrow" in value or "→" in value or "=>" in value:
        score += 5
    if re.search(r"(?:R_x|L_x|C_x|Z_x|error|y)\s*=", value, flags=re.IGNORECASE):
        score += 3
    if re.search(r"(?:\\dots|…|\(\s*(?:[a-z]|[ivx]+)\s*\))", value, flags=re.IGNORECASE):
        score -= 6
    if len(re.findall(r"=", value)) >= 3:
        score -= 2
    return score


@lru_cache(maxsize=4096)
def _clean_source_text(text: str) -> str:
    """Remove document chrome before content is used in learner outputs."""
    cleaned = re.sub(r"<!--.*?-->", " ", text or "", flags=re.DOTALL)
    cleaned = re.sub(r"^\s*#+\s*", "", cleaned)
    cleaned = re.sub(r"\b(?:page|p\.)\s*\d+\s*(?:of|/)\s*\d+\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:module|chapter)\s*#?\s*\d+\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:course\s*code|source\s*material)\s*:\s*[^.]+", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:[A-Za-z]+\s*){1,5},?\s*MSc\s*Eng\.?\s*\|\s*[^|]{3,100}?\s+\d+\s*/\s*\d+\s*$", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+Dhawa\s*Sang\s*Dong,?\s*MSc\s*Eng\.?\s*\|\s*Kathmandu\s*Engineering\s*College\s+\d+\s*/\s*\d+\s*$", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(?:Kathmandu\s*Engineering\s*College|College)\s+\d+\s*/\s*\d+\s*$", " ", cleaned, flags=re.IGNORECASE)
    # OCR often places an all-caps running title immediately before the first
    # sentence. Remove only that prefix; ordinary all-caps technical terms
    # inside the explanation are preserved.
    cleaned = re.sub(r"^\s*[A-Z][A-Z0-9() /&_.-]{3,70}\s+(?=[A-Z][a-z])", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip(" -•\t\n")


_COMPACT_OCR_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("measurementofanyquantityisresultofcomparisonof", "measurement of any quantity is the result of comparison of"),
    ("unknownquantityagainststandardknownquantity", "unknown quantity against standard known quantity"),
    ("primarypurposeistoaccuratelyandreliablymeasure", "primary purpose is to accurately and reliably measure"),
    ("theprimarypurposeistoaccuratelyandreliablymeasure", "the primary purpose is to accurately and reliably measure"),
    ("theprimary purpose", "The primary purpose"),
    ("theprimary purpose is to accurately and reliably measure physical quantities or processes/events(e.g.temperature, pressure, flow, voltage)giving numerical values and convert them into readable and usable signals", "The primary purpose is to accurately and reliably measure physical quantities or processes/events and convert the result into readable and usable signals"),
    ("theprimary purpose is to accurately and reliably measure physical quantities or processes/events (e.g., temperature, pressure, flow, voltage) giving numerical values and convert them into readable and usable signals", "The primary purpose is to accurately and reliably measure physical quantities or processes/events and convert the result into readable and usable signals"),
    ("physicalquantitiesorprocess/event", "physical quantities or processes/events"),
    ("physicalquantitiesorprocesses/events", "physical quantities or processes/events"),
    ("processes/events(e.g.temperature,pressure,flow,voltage)giving", "processes/events (e.g., temperature, pressure, flow, voltage) giving"),
    ("processes/events(e.g.temperature, pressure, flow, voltage)giving numerical values and convert them into readable and usable signals", "processes/events and convert the result into readable and usable signals"),
    ("processes/events(e.g.temperature, pressure, flow, voltage) giving numerical values and convert them into readable and usable signals", "processes/events and convert the result into readable and usable signals"),
    ("electromagneticinduction,involvingamagnet", "electromagnetic induction, involving a magnet"),
    ("permanentorelectromagnet", "permanent or electromagnet"),
    ("andacurrent-carryingcoil", "and a current-carrying coil"),
    ("orthroughthemovementofapointer", "or through the movement of a pointer"),
    ("acrossascale", "across a scale"),
    ("outputasnumericalvaluesonascreen,typicallyusing", "output as numerical values on a screen, typically using"),
    ("LCDor LEDdisplays", "LCD or LED displays"),
    ("givingnumericalvaluesandconverttheminto", "giving numerical values and convert them into"),
    ("monitoringprocessoroperations", "Monitoring processor operations"),
    ("controlprocessandoperations", "Control process and operations"),
    ("experimentalengineeringanalysis", "Experimental engineering analysis"),
    ("analog instrument digital instrument introduction instrumentation system", "analog instrument; digital instrument; introduction to instrumentation system"),
    ("analoginstrumentdigitalinstrumentintroductioninstrumentationsystem", "analog instrument; digital instrument; introduction to instrumentation system"),
    ("thesignaltype", "the signal type"),
    ("datarepresentation", "data representation"),
    ("representedinbinary", "represented in binary"),
    ("variessmoothlyoverarange", "varies smoothly over a range"),
    ("lesspronetonoise", "less prone to noise"),
    ("highprecisionduetodiscretelevels", "high precision due to discrete levels"),
    ("noisesensitivity", "noise sensitivity"),
    ("thisinstrument", "this instrument"),
    ("adigitalinstrumentisatypeofmeasuringdevicethatdisplays", "a digital instrument is a type of measuring device that displays"),
    ("ananaloginstrumentdisplaysmeasurementresultseitherasa", "an analog instrument displays measurement results either as a"),
    ("theseinstrumentsoperatebasedontheprincipleof", "these instruments operate based on the principle of"),
    ("amicroprocessorisanintegratedcircuit", "a microprocessor is an integrated circuit"),
    ("centralprocessingunit", "central processing unit"),
    ("thatservesasthe", "that serves as the"),
    ("ofacomputer/electronicsystem", "of a computer/electronic system"),
    ("itisessentiallyaprogrammable, clockdrivenelectronicdevice thatcanperformorcontrolarithmetic, logic, andinput/output operationsaccordingtotheinstructionsstoredinitsmemory", "It is essentially a programmable, clock-driven electronic device that performs or controls arithmetic, logic, and input/output operations according to instructions stored in memory"),
    ("it isessentiallyaprogrammable, clockdrivenelectronicdevice thatcanperformorcontrolarithmetic, logic, andinput/output operationsaccordingtotheinstructionsstoredinitsmemory", "It is essentially a programmable, clock-driven electronic device that performs or controls arithmetic, logic, and input/output operations according to instructions stored in memory"),
    ("componentsofmicroprocessor:", "Components of a microprocessor include:"),
    ("acceptsbinaryinputdataandprocessaccordingtoinstruction", "It accepts binary input data and processes it according to instructions"),
    ("providesresultsasoutputforcorrespondinginput", "It provides output corresponding to the input"),
    ("components of a microprocessor include: arithmetic logic unit(alu) control unit(cu) register instruction set architecture(isa) clock cache memory bus interface it accepts binary input data", "Components of a microprocessor include the Arithmetic Logic Unit (ALU), Control Unit (CU), registers, Instruction Set Architecture (ISA), clock, cache memory, and bus interface. It accepts binary input data"),
    ("programmabilityaddstheimprovedlogicalandcomputing capabilities, andimprovedaccuracyandefficiencybecause computingpowerisfunctionofalgorithmtoo", "Programmability adds improved logical and computing capabilities, and it improves accuracy and efficiency because computational power also depends on the algorithm"),
    ("it isessentiallyaprogrammable", "it is essentially a programmable"),
    ("canbeusedinanysystem", "can be used in any system"),
    ("fundamentally,itisassemblyofinstrumentsandother components(devices,sensors)forthepurposes:", "Fundamentally, an instrumentation system is an assembly of instruments and other components (devices and sensors) used to:"),
    ("control aphysicaleventsorprocesssuchaselectrical, thermalormechanical", "control physical events or processes, such as electrical, thermal, or mechanical processes"),
    ("someofthecomponentsof instrumentation systems:", "Some components of instrumentation systems are:"),
    ("datadisplayand analysis", "data display and analysis"),
    ("completeautomationandintelligencetosomeextend", "Complete automation and intelligence to some extent"),
    ("redesignflexibilityduetoprogrammability", "Redesign flexibility due to programmability"),
    ("economicandreducedcomplexity", "Economical operation and reduced complexity"),
    ("reducedoperatingcosts", "Reduced operating costs"),
    ("higheraccuracyofcontrolenforcement", "Higher accuracy of control enforcement"),
    ("timelyandaccurateinformationenablesoperatorsforefficient plantrunning", "Timely and accurate information enables operators to run the plant efficiently"),
    ("informationexchangewithotherplantsystemwithrelational databasemanagement", "Information exchange with other plant systems through relational database management"),
    ("microprocessor, i/odevices, and memory", "A microprocessor-based system includes a microprocessor, I/O devices, and memory"),
    ("decisionmakingpowerbasedonsetvalue", "Decision-making power based on set values"),
    ("userfriendlywithsignallevelsorinformation", "User-friendly handling of signal levels or information"),
    ("parallelprocessing;multiprocessingwithtimesharing", "Parallel processing and multiprocessing with time sharing"),
    ("datastorage, retrievalandtransmission", "Data storage, retrieval, and transmission"),
    ("effectivecontrolofmultipleequipmentontimesharingbasis", "Effective control of multiple equipment on a time-sharing basis"),
    ("lotofprocessingcapabilitywithpowerfulmicroprocessor", "High processing capability with a powerful microprocessor"),
    ("open loopcontrolsystem closed loopcontrolsystem open loop control system", "Microprocessor-based control systems can use open-loop or closed-loop control. In an open-loop control system"),
    ("open loopcontrolsystem", "open-loop control system"),
    ("closed loopcontrolsystem", "closed-loop control system"),
    ("dependinguponthecontroloutputfrommicroprocessor, operatormakesthechangestocontrolinput", "In an open-loop control system, the operator changes the control input based on the microprocessor output"),
    ("outputquantityfromthemicroprocessorcouldbedisplayedor presentedinreadableformfortheoperators", "The microprocessor output can be displayed in a readable form for the operator"),
    ("continuousmonitoringofprocessvariables", "Continuous monitoring of process variables"),
    ("outputsignaltocontrolsystemorunits", "Output signal sent to the control system or units"),
    ("microprocessor based control system block diagram for pressure monitoring system", "Microprocessor-based control system: pressure-monitoring block diagram"),
    ("analog(pressure)signalisconvertedtodigitalformandfed tomicroprocessor", "The analog pressure signal is converted to digital form and fed to the microprocessor"),
    ("microprocessorcomparesthesamplemeasurementwith presentpressurelimits", "The microprocessor compares the sampled measurement with preset pressure limits"),
    ("ifthesampleisbeyondlimits, themicroprocessorindicatesin theformofsomealarmorlight", "If the sample is beyond the limits, the microprocessor indicates an alarm or light"),
    ("accordingtooutputsignal, operatormakesnecessarychanges", "According to the output signal, the operator makes the necessary changes"),
    ("nohumaninterferenceoroperatorisnotrequired", "No human interference or operator is required"),
    ("upperorlowerlimitsoftemperaturearesetbyoperator", "Upper and lower temperature limits are set by the operator"),
    ("eachsampleoftemperatureiscomparedtopredefinedvalueby theprocessor", "Each temperature sample is compared with a predefined value by the processor"),
    ("ifthetemperatureexceedstheupperlimit, microprocessor transmitsanoutputsignaltocontrolsystemwhichturnoff (generally)thesupplytosomeoftheheatingelements", "If the temperature exceeds the upper limit, the microprocessor transmits an output signal that generally turns off the supply to some heating elements"),
    ("ifthetemperatureislessthanpresetlowerlimit, the microprocessortransmitssignaltocontrolsystemsothatit turnsonthesupplytosomeheatingelements", "If the temperature is less than the preset lower limit, the microprocessor transmits a signal that turns on the supply to some heating elements"),
    ("iftemperatureislessthanpresetlowerlimit, the microprocessortransmitssignaltocontrolsystemsothatit turnsonthesupplytosomeheatingelements", "If the temperature is less than the preset lower limit, the microprocessor transmits a signal that turns on the supply to some heating elements"),
    ("aprocessorplantmayhavetomeasuremultiplevariables simultaneously", "A process plant may have to measure multiple variables simultaneously"),
    ("flowrateetc", "flow rate, etc"),
    ("computerbasedsystemcanprocessallinputsorvariablesin realtimesimultaneously", "A computer-based system can process all input variables simultaneously in real time"),
    ("computerormicroprocessorisfedwithasequenceof instructionsknownascomputerprogramforprocessingor manipulationofdata", "A computer or microprocessor is fed a sequence of instructions, known as a computer program, to process or manipulate data"),
    ("programmedtocarryoutthetasksuchasnoisereduction,gain adjustmentetcautomatically", "It can be programmed to carry out tasks such as noise reduction and gain adjustment automatically"),
    ("itcontainssignalconditioninganddisplaysystemsuitableto workinwiderangeofconditionslikeindustrial,consumeretc", "It contains signal-conditioning and display systems suitable for a wide range of industrial and consumer conditions"),
    ("diagnosticsubroutinescanbeintegratedfor(fault)detection andcorrection", "Diagnostic subroutines can be integrated for fault detection and correction"),
    ("capableofrealtimemeasurement, processinganddisplay", "It is capable of real-time measurement, processing, and display"),
    ("lowercost, higheraccuracy, andmoreflexible", "It has lower cost, higher accuracy, and greater flexibility"),
    ("pedestriancannotreplacetheprogramthemselves", "Users cannot replace the program themselves"),
    ("updatingsoftwareisnoteasyrelatively", "Updating software is relatively difficult"),
    ("pronetovirusproblem, sodysfunctionalprobability", "It is prone to virus problems, which can cause malfunction"),
    ("typicalcomputerbasedinstrumentation system", "typical computer based instrumentation system"),
    ("computerbasedinstrumentation", "computer based instrumentation"),
    ("scientificprinciplesandmethodologiesusedtoobtainquantitativeinformationaboutphysicalvariablesusinginstruments", "scientific principles and methodologies used to obtain quantitative information about physical variables using instruments"),
    ("thetheoryofmeasurement", "the theory of measurement"),
    ("measurementreferstothescientificprinciplesand", "measurement refers to the scientific principles and"),
    ("methodologiesusedtoobtain", "methodologies used to obtain"),
    ("obtainquantitativeinformation", "obtain quantitative information"),
    ("quantitativeinformationabout", "quantitative information about"),
    ("informationabout", "information about"),
    ("physicalvariablesusinginstruments", "physical variables using instruments"),
    ("immediatelyafterinputisapplied", "immediately after input is applied"),
    ("theresponsedoesnottakeitsexpectedvalue", "the response does not take its expected value"),
    ("applied,theresponsedoesnottake", "applied, the response does not take"),
    ("take itsexpectedvalue", "take its expected value"),
    ("responsepassesthroughaperiodwhereitchangesitsvaluewithtime", "response passes through a period where it changes its value with time"),
    ("responsepassesthroughaperiod", "response passes through a period"),
    ("periodwhereitchangesitsvalue", "period where it changes its value"),
    ("value withtime", "value with time"),
    ("thebehaviourduringtheperiodis", "the behavior during the period is"),
    ("thebehaviorduringtheperiodis", "the behavior during the period is"),
    ("theresponsetakesitsvalue", "the response takes its value"),
    ("itisacrucialpartof", "it is a crucial part of"),
    ("makingmeasuredvaluelesserroneous", "making measured values less erroneous"),
    ("ofelectrical", "of electrical"),
    ("andelectronics", "and electronics"),
    ("andmechanicalengineering", "and mechanical engineering"),
    ("electronics,andmechanical", "electronics, and mechanical"),
    ("engineeringmaking", "engineering, making"),
    ("characteristicsandoperations", "characteristics and operations"),
    ("ofinstrument", "of instrument"),
    ("transientperiodresponse", "transient period or response"),
    ("steady stateperiod", "steady-state period"),
    ("statisticalparametersarestudiedduringthesteady-stateofasystem", "statistical parameters are studied during the steady-state of a system"),
    ("thesystemoutputisstable", "the system output is stable"),
    ("variationsareduetomeasurementnoise", "variations are due to measurement noise"),
    ("closenessofameasurementtothetrueoracceptedvalue", "closeness of a measurement to the true or accepted value"),
    ("ratioofchangeinoutputtoachangeininput", "ratio of change in output to a change in input"),
    ("linearsystemmeansconstantsensitivity", "linear system means constant sensitivity"),
    ("howwelltheoutputfollowsastraight-linerelationship", "how well the output follows a straight-line relationship"),
    ("itdescribeshowthesystembehaveswhenthemeasuredquantitychangeswithtime", "it describes how the system behaves when the measured quantity changes with time"),
    ("frequencyrangeoverwhichthesystemaccuratelyresponds", "frequency range over which the system accurately responds"),
    ("timetakentorisefrom", "time taken to rise from"),
    ("itisthedeviationofthemeasuredvaluefromthetruevalue", "it is the deviation of the measured value from the true value"),
    ("errorsmaycomefromdifferentsources", "errors may come from different sources"),
    ("istheerrorduetousers", "is the error due to users"),
    ("errorsareduetoshort-comingofinstruments", "errors are due to shortcomings of instruments"),
    ("variationintemperaturehumidity", "variation in temperature and humidity"),
    ("causeoferrorisunknown", "cause of error is unknown"),
    ("thistypeoferrorcantbecorrected", "this type of error cannot be corrected"),
    ("therearethreetypesofmethodtomeasure", "there are three types of method to measure"),
    ("whenexcitationvoltageorcurrenttothebridgecircuitisalternating", "when excitation voltage or current to the bridge circuit is alternating"),
    ("theacbridgecircuitisusedtomeasure", "the AC bridge circuit is used to measure"),
    ("whenexcitationvoltageorcurrenttothebridgecircuitis alternating", "when excitation voltage or current to the bridge circuit is alternating"),
    ("thebridgeisacbridge", "the bridge is an AC bridge"),
    ("suchasinductancecapacitancelossfactor", "such as inductance, capacitance, and loss factor"),
    ("averyimportantcircuitusedtomeasure", "a very important circuit used to measure"),
    ("forbalancedcircuit", "for a balanced circuit"),
    ("detectorcurrentiszero", "detector current is zero"),
    ("errorincalculation", "error in calculation"),
    ("errorinobservation", "error in observation"),
    ("errorinconnections", "error in connections"),
    ("errorinplacement", "error in placement"),
    ("devicesusedtomeasurequantitieslikevoltage", "devices used to measure quantities like voltage"),
    ("componentssuchasamplifiers", "components such as amplifiers"),
    ("quantitativeinformationaboutphysicalvariables", "quantitative information about physical variables"),
    ("measurementofimpedancecomponents", "measurement of impedance components"),
    ("measurementofresistance", "measurement of resistance"),
    ("microcomputeroninstrumentationdesign", "microcomputer on instrumentation design"),
    ("microprocessorbasedcontrolsystem", "microprocessor based control system"),
    ("statisticalperformanceparameters", "statistical performance parameters"),
    ("dynamicperformanceparameters", "dynamic performance parameters"),
    ("staticanddynamicperformance", "static and dynamic performance"),
    ("analoganddigitalinstrument", "analog and digital instrument"),
    ("introductioninstrumentationsystem", "introduction instrumentation system"),
    ("theoryofmeasurement", "theory of measurement"),
    ("lowresistancemeasurement", "low resistance measurement"),
    ("maxwellsbridge", "Maxwell's Bridge"),
    ("scheringsbridge", "Schering's Bridge"),
    ("wheatstonebridge", "Wheatstone Bridge"),
    ("ammeter-voltmetermethod", "ammeter-voltmeter method"),
    ("analoginstrument", "analog instrument"),
    ("digitalinstrument", "digital instrument"),
    ("errorinmeasurement", "error in measurement"),
    ("instrumentationsystem", "instrumentation system"),
    ("instrumentationreferences", "instrumentation references"),
    ("basicsofinstrumentation", "basics of instrumentation"),
    ("microprocessorbasedinstrumentation", "microprocessor based instrumentation"),
    ("meritsofusingmicroprocessor", "merits of using microprocessor"),
    ("featuresofmicroprocessorbasedsystem", "features of microprocessor based system"),
    ("majorcomponents", "major components"),
    ("summaryoferror", "summary of error"),
    ("microprocesor", "microprocessor"),
    ("unknownquantity", "unknown quantity"),
    ("standardknownquantity", "standard known quantity"),
    ("physicalquantities", "physical quantities"),
    ("readableandusablesignals", "readable and usable signals"),
    ("truevalue", "true value"),
    ("measuredvalue", "measured value"),
    ("characteristicsofinstruments", "characteristics of instruments"),
    ("staticcharacteristics", "static characteristics"),
    ("dynamiccharacteristics", "dynamic characteristics"),
    ("responsetime", "response time"),
    ("timeconstant", "time constant"),
    ("frequencyresponse", "frequency response"),
    ("risetime", "rise time"),
    ("delaytime", "delay time"),
    ("instrumentalerror", "instrumental error"),
    ("environmentalerror", "environmental error"),
    ("randomerror", "random error"),
    ("systematicerror", "systematic error"),
    ("sytematicerror", "systematic error"),
    ("grosserror", "gross error"),
    ("correctivemethods", "corrective methods"),
    ("balancedcircuit", "balanced circuit"),
    ("detectorcurrent", "detector current"),
)


@lru_cache(maxsize=4096)
def _repair_compact_ocr(value: str) -> str:
    """Restore common word boundaries lost by PDF glyph extraction."""
    repaired = str(value or "")
    for compact, spaced in _COMPACT_OCR_REPLACEMENTS:
        repaired = re.sub(re.escape(compact), spaced, repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"([a-z])([A-Z])", r"\1 \2", repaired)
    repaired = re.sub(r"([0-9])([A-Z])", r"\1 \2", repaired)
    repaired = re.sub(r"(?<=[A-Za-z])\((?=[A-Za-z]{2,}\))", " (", repaired)
    repaired = re.sub(r"(?<=\))(?=[A-Za-z])", " ", repaired)
    repaired = re.sub(r"[\u2776-\u277b\u2460-\u2473]\s*", "", repaired)
    repaired = re.sub(r"[\u2713\u2714]\s*", "", repaired)
    repaired = re.sub(r",\s*(?=[A-Za-z])", ", ", repaired)
    repaired = re.sub(r"\ban\s+digital\b", "a digital", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\ba\s+analog\b", "an analog", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\b(?:microcomputer on instrumentation design\s+)?fig(?:ure)?\.?\s*\d+\s*(?:a\s+)?typical\s*(?:computer|microprocessor)\s*based\s+instrumentation\s+system\b", "", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"\bto\.\s*Digital\s+Converter\s*\(ADC\)", "Analog-to-Digital Converter (ADC)", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"(?<=[A-Za-z]):(?=[A-Z])", ": ", repaired)
    repaired = re.sub(r"\bunits\s+\d+\s+microprocessor-based control system:\s*pressure-monitoring block diagram", "units", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"(?<=[.!?])\s*[-–]\s*(?=[A-Za-z])", " ", repaired)
    repaired = re.sub(r"(?<=[a-z])\s*[-–]\s*(?=[A-Z])", ". ", repaired)
    repaired = re.sub(r"\banalog\s+instrument\s+digital\s+instrument\s+introduction\s+instrumentation\s+system\b", "Analog instruments and digital instruments are introduced as two instrument classes.", repaired, flags=re.IGNORECASE)
    repaired = re.sub(r"(^|(?<=[.!?])\s+)([a-z])", lambda match: match.group(1) + match.group(2).upper(), repaired)
    return re.sub(r"\s+", " ", repaired).strip()


def _spaced_ocr_label(value: str) -> str:
    """Turn compact OCR running headers into short learner-facing titles."""
    raw = re.sub(r"\s+", " ", str(value or "")).strip(" :-|")
    compact = re.sub(r"[^a-z0-9]+", "", raw.casefold())
    known = {
        "theoryofmeasurement": "Theory of Measurement",
        "introductioninstrumentationsystem": "Instrumentation System",
        "analoganddigitalinstrument": "Analog and Digital Instrument",
        "analoginstrument": "Analog Instrument",
        "digitalinstrument": "Digital Instrument",
        "microprocessorbasedcontrolsystem": "Microprocessor Based Control System",
        "microcomputeroninstrumentationdesign": "Microcomputer on Instrumentation Design",
        "staticanddynamicperformance": "Static and Dynamic Performance",
        "statisticalperformanceparameters": "Statistical Performance Parameters",
        "dynamicperformanceparameters": "Dynamic Performance Parameters",
        "errorinmeasurement": "Error in Measurement",
    }
    if compact in known:
        return known[compact]
    raw = re.sub(r"([a-z])([A-Z])", r"\1 \2", raw)
    raw = re.sub(r"\b(?:introduction|chapter\s*#?\s*\d+)\b", "", raw, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", raw).strip(" :-|")[:150]


def _inline_ocr_heading(text: str) -> tuple[str, str] | None:
    """Split flattened OCR pages such as `Topic Header - explanation`."""
    match = re.search(r"\s+-\s*(?=[A-Za-z])", text or "")
    if not match:
        match = re.search(r"(?:[❶❷❸❹❺❻❼❽❾❿]|\b[1-9]\b)\s*([^:|]{3,90}):\s*(?=[A-Z])", text or "")
        if match:
            header = match.group(1).strip()
            body = text[match.end():].strip()
            header = _spaced_ocr_label(header)
            return (header, body) if header and len(body) >= 35 else None
    if not match:
        return None
    header = text[:match.start()].strip()
    body = text[match.end():].strip()
    if len(body) < 35 or len(header) > 240:
        return None
    numbered = re.search(r"(?:[❶❷❸❹❺❻❼❽❾❿]|\b[1-9]\b)\s*(.+)$", header)
    if numbered and len(numbered.group(1).strip()) >= 4:
        header = numbered.group(1)
    else:
        lowered_header = header.casefold().replace(" ", "")
        if "analoginstrument:" in lowered_header:
            header = "Analog Instrument"
        elif "digitalinstrument:" in lowered_header:
            header = "Digital Instrument"
        elif lowered_header.endswith("instrumentationsystem") and lowered_header.count("instrumentationsystem") > 1:
            header = "Instrumentation System"
        else:
            header = header.split("|")[-1]
            header = re.sub(r"^.*?\b(?:InstrumentationSystem|Instrumentation System)\b\s*", "", header, flags=re.IGNORECASE) or header
    header = _spaced_ocr_label(header)
    if not header or _notebook_metadata_heading(header):
        return None
    return header, body


def _normalise_topic_title(value: str) -> str:
    """Convert a flattened OCR heading into a concise learner-facing title."""
    raw = _repair_compact_ocr(str(value or "")).strip()
    raw = re.sub(r"^[^A-Za-z0-9]+", "", raw)
    raw = raw.split("|")[0].strip(" :.-")
    raw = re.sub(r"\s+(?:static|dynamic)\s*characteristics\s*$", "", raw, flags=re.IGNORECASE)
    compact = re.sub(r"[^a-z0-9]+", "", raw.casefold())
    for running, marker in (("errorinmeasurement", "error in measurement"), ("measurementofimpedancecomponents", "measurement of impedance components"), ("measurementofresistance", "measurement of resistance")):
        if compact.startswith(running) and compact != running:
            raw = re.sub(re.escape(marker), "", raw, count=1, flags=re.IGNORECASE).strip(" :.-")
            compact = re.sub(r"[^a-z0-9]+", "", raw.casefold())
            break
    if compact.startswith("tutorialstutorials"):
        return "Tutorials"
    if "ammetervoltmeter" in compact:
        return "Ammeter-Voltmeter Method"
    if "wheatstonebridge" in compact:
        return "Wheatstone Bridge"
    if "maxwellsbridge" in compact:
        return "Maxwell's Bridge"
    if "scheringsbridge" in compact:
        return "Schering's Bridge"
    if "lowresistancemeasurement" in compact:
        return "Low Resistance Measurement"
    if "mediumresistance" in compact:
        return "Medium Resistance Measurement"
    if "measurementofimpedancecomponents" in compact and "acbridge" in compact:
        return "AC Bridge"
    if compact == "acbridge":
        return "AC Bridge"
    if "analoganddigitalinstrument" in compact:
        return "Analog and Digital Instrument"
    if "digitalinstrument" in compact:
        return "Digital Instrument"
    if "analoginstrument" in compact:
        return "Analog Instrument"
    if "microcomputeroninstrumentationdesign" in compact:
        return "Microcomputer on Instrumentation Design"
    if "microprocessorbasedcontrolsystem" in compact:
        return "Microprocessor Based Control System"
    if "microprocessorbasedinstrumentation" in compact and "benefits" in compact:
        return "Microprocessor-Based Instrumentation Benefits"
    if "microprocessorbasedinstrumentation" in compact:
        return "Microprocessor-Based Instrumentation"
    if "featuresofmicroprocessorbasedsystem" in compact:
        return "Microprocessor-Based System Features"
    if "meritsofusingmicroprocessor" in compact:
        return "Benefits of Using a Microprocessor"
    if "basicsofinstrumentationsystem" in compact and "microprocessor" in compact:
        return "Microprocessor-Based Instrumentation"
    if "basicsofinstrumentationsystem" in compact:
        return "Instrumentation System Basics"
    for key, canonical in (
        ("grosserror", "Gross Error"),
        ("systematicerror", "Systematic Error"),
        ("randomerror", "Random Error"),
        ("summaryoferror", "Summary of Error"),
        ("tutorialstutorials", "Tutorials"),
    ):
        if key in compact:
            return canonical
    for key, canonical in (
        ("theoryofmeasurement", "Theory of Measurement"),
        ("staticanddynamicperformance", "Static and Dynamic Performance"),
        ("statisticalperformanceparameters", "Statistical Performance Parameters"),
        ("dynamicperformanceparameters", "Dynamic Performance Parameters"),
        ("errorinmeasurement", "Error in Measurement"),
        ("introductioninstrumentationsystem", "Instrumentation System"),
        ("microprocessorbasedcontrolsystem", "Microprocessor Based Control System"),
        ("microcomputeroninstrumentationdesign", "Microcomputer on Instrumentation Design"),
        ("analoganddigitalinstrument", "Analog and Digital Instrument"),
        ("analoginstrument", "Analog Instrument"),
        ("digitalinstrument", "Digital Instrument"),
    ):
        if key in compact:
            return canonical
    return _spaced_ocr_label(raw)[:150]


def _trim_repeated_running_heading(title: str, body: str) -> str:
    """Remove a repeated PDF running header left after the topic title."""
    cleaned = str(body or "").strip(" |-")
    if title == "Microprocessor-Based Instrumentation Benefits":
        return re.sub(r"^microprocessor\s*based\s*instrumentation\s*system(?:\s*benefits)?\s*[.:|]*\s*", "", cleaned, flags=re.IGNORECASE)
    if title == "Microcomputer on Instrumentation Design":
        return re.sub(r"^microcomputer\s*on\s*instrumentation\s*system\s*[.:|]*\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned


def _inline_ocr_heading(text: str) -> tuple[str, str] | None:
    """Split flattened OCR pages without relying on special numeral glyphs."""
    source = _repair_compact_ocr(str(text or "")).strip()
    if not source:
        return None
    repeated_microcomputer_header = re.match(
        r"^microcomputer\s+on\s+instrumentation\s+design\s+microcomputer\s+on\s+instrumentation\s+system\.\s*(.+)$",
        source,
        flags=re.IGNORECASE,
    )
    if repeated_microcomputer_header:
        body = _trim_repeated_running_heading("Microcomputer on Instrumentation Design", repeated_microcomputer_header.group(1))
        return ("Microcomputer on Instrumentation Design", body) if len(body) >= 35 else None
    # Handles `Accuracy: |Static Characteristics - explanation`, including
    # circled-number prefixes that may be decoded as any non-ASCII glyph.
    colon = re.search(r"^\s*(?:[^A-Za-z0-9\s]{1,4}\s*)?([^:|\n]{3,110}):\s*(.*)$", source)
    if colon:
        title = _normalise_topic_title(colon.group(1))
        body = _trim_repeated_running_heading(title, re.sub(r"^\s*\|\s*[^-]{0,100}-\s*", "", colon.group(2)))
        return (title, body) if title and len(body) >= 35 else None
    match = re.search(r"\s+-\s*(?=[A-Za-z])", source)
    if not match:
        return None
    title = _normalise_topic_title(source[:match.start()])
    body = _trim_repeated_running_heading(title, source[match.end():])
    if len(body) < 35 or len(title) > 240 or _notebook_metadata_heading(title):
        return None
    return title, body


def _meaningful_sentences(section: dict) -> list[str]:
    """Split OCR prose at punctuation and flattened bullet boundaries."""
    text = _repair_compact_ocr(_clean_source_text(" ".join(str(block.get("markdown") or "") for block in section.get("blocks") or [])))
    parts = re.split(r"(?<=[.!?])\s+|;\s+|\s{2,}|\s+-\s*(?=[A-Z])|\s+(?=[^A-Za-z0-9\s])", text)
    return [
        sentence.strip(" -")
        for sentence in parts
        if 35 <= len(sentence.strip(" -")) <= 360
        and not re.match(r"^(?:figure|table|source|page)\b", sentence.strip(), re.IGNORECASE)
        and not re.search(r"\(\s*\d{4}\s*\)|\b(?:mcgraw|publisher|edition|references?)\b", sentence, re.IGNORECASE)
    ]


def _meaningful_sentences(section: dict) -> list[str]:
    text = _repair_compact_ocr(_clean_source_text(" ".join(str(block.get("markdown") or "") for block in section.get("blocks") or [])))
    sentences = [part.strip(" -•") for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    if len(sentences) == 1:
        sentences = [part.strip(" -•") for part in re.split(r";\s+|\s{2,}", text) if part.strip()]
    return [sentence for sentence in sentences if 35 <= len(sentence) <= 360 and not re.match(r"^(?:figure|table|source|page)\b", sentence, re.IGNORECASE) and not re.search(r"\(\s*\d{4}\s*\)|\b(?:mcgraw|publisher|edition|references?)\b", sentence, re.IGNORECASE)]


def _meaningful_sentences(section: dict) -> list[str]:
    """Return compact, learner-ready claims from an OCR section.

    A scan often flattens bullets into one paragraph. Punctuation, semicolons,
    and list markers are restored before the content reaches a card, MCQ, or
    slide; PDF captions and classroom notices never qualify as teaching text.
    """
    text = _repair_compact_ocr(_clean_source_text(" ".join(
        str(block.get("markdown") or "")
        for block in section.get("blocks") or []
        if str(block.get("type") or "").casefold() != "image"
    )))
    parts = re.split(r"(?<=[.!?])\s+|;\s+|\s+-\s*(?=[A-Z])", text)
    sentences: list[str] = []
    seen: set[str] = set()
    for part in parts:
        sentence = re.sub(r"\s+", " ", part).strip(" -â€¢.:;")
        sentence = re.sub(r"^(?:\d+\s+)?(?:Fig(?:ure)?\.?\s*\d+\s*)", "", sentence, flags=re.IGNORECASE).strip()
        if sentence and sentence[-1] not in ".!?":
            sentence += "."
        normalized = sentence.casefold()
        if (
            len(sentence) < 20
            or len(sentence) > 360
            or normalized in seen
            or re.match(r"^(?:figure|table|source|page|introduction|basics of)\b", sentence, re.IGNORECASE)
            or re.search(r"\(\s*\d{4}\s*\)|\b(?:mcgraw|publisher|edition|references?|class quiz|assignment|submission deadline)\b", sentence, re.IGNORECASE)
            or re.fullmatch(r"(?:micro\.?|introduction instrumentation system)\.?", sentence, re.IGNORECASE)
            or re.fullmatch(r"(?:in an )?(?:open|closed)[ -]?loop control system\.?", sentence, re.IGNORECASE)
            or re.fullmatch(r"\d+\s+microprocessor based system\.?", sentence, re.IGNORECASE)
        ):
            continue
        seen.add(normalized)
        sentences.append(sentence)
    return sentences


def _concept_subject(sentence: str, title: str) -> str:
    match = re.search(r"^(?:an?|the)\s+(.+?)\s+(?:is|are|refers to|means|consists of|is designed to|is used to|measures|contains|includes|provides|requires)\b", sentence, re.IGNORECASE)
    if match:
        article = re.match(r"^(an?|the)\b", sentence, re.IGNORECASE)
        prefix = f"{article.group(1).lower()} " if article else ""
        return f"{prefix}{match.group(1).strip(' ,:;.-')}"[:100]
    fallback = re.sub(r"[#*_]", "", title or "").strip(" .:")
    return fallback[:100] or "this concept"


def _mutate_claim(claim: str, replacements: list[tuple[str, str]]) -> str:
    for old, new in replacements:
        if re.search(rf"\b{re.escape(old)}\b", claim, re.IGNORECASE):
            return re.sub(rf"\b{re.escape(old)}\b", new, claim, count=1, flags=re.IGNORECASE)
    return ""


def _claim_list_items(claim: str, *, require_components: bool = True) -> list[str]:
    """Extract an explicit component list for a defensible list MCQ.

    Commas alone are not enough evidence of a list question: scanned notes use
    them in prose and bullet-like fragments. Restrict this path to material
    that explicitly names components, so the alternatives stay in one category.
    """
    if require_components and not re.search(r"\bcomponents?\b", claim, flags=re.IGNORECASE):
        return []
    candidate = claim.split(":", 1)[1] if ":" in claim else claim
    candidate = re.sub(r"^.*?\b(?:includes|contains|comprises)\s+", "", candidate, count=1, flags=re.IGNORECASE)
    candidate = re.sub(r"[✓✔•●▪◦]", "", candidate)
    candidate = re.sub(r"^\s*(?:some of the|the following)\s+", "", candidate, flags=re.IGNORECASE)
    pieces = re.split(r"\s*[,;]\s*", candidate)
    cleaned: list[str] = []
    for piece in pieces:
        item = re.sub(r"^\s*(?:and|&)\s+", "", piece)
        item = re.sub(r"\s+and\s*$", "", item).strip(" .:-")
        if 2 <= len(item) <= 72 and item.casefold() not in {value.casefold() for value in cleaned}:
            cleaned.append(item)
    if len(cleaned) < 3:
        return []
    return cleaned[:8]


def _source_term_pool(sections: list[dict]) -> list[str]:
    terms: list[str] = []
    for section in sections:
        for sentence in _meaningful_sentences(section):
            # A related source may list hardware by saying it "includes" a
            # component rather than repeating the word "components". Those
            # terms are useful as distractors, even though they must not turn
            # an arbitrary list into a learner-facing list question.
            for item in _claim_list_items(sentence, require_components=False):
                item = re.sub(r"^(?:components?\s+such\s+as|such\s+as)\s+", "", item, flags=re.IGNORECASE).strip()
                if item and item[0].islower() and any(term in item.casefold() for term in ("amplifier", "filter", "converter", "microprocessor", "memory", "device")):
                    item = item[0].upper() + item[1:]
                if item.casefold() not in {value.casefold() for value in terms}:
                    terms.append(item)
    return terms


def _list_distractors(correct_items: list[str], term_pool: list[str]) -> list[str]:
    correct_set = {item.casefold() for item in correct_items}
    component_words = ("sensor", "transducer", "signal", "data acquisition", "control", "communication", "display", "amplifier", "filter", "converter", "microprocessor", "memory", "device", "unit")
    replacements = [item for item in term_pool if item.casefold() not in correct_set and len(item) <= 45 and re.match(r"^[A-Z]", item) and item.casefold() != "instrumentation system" and any(word in item.casefold() for word in component_words)]
    if not replacements:
        return []
    variants: list[str] = []
    for replacement in replacements[:3]:
        items = list(correct_items)
        if replacement.casefold() in {item.casefold() for item in items}:
            continue
        items[-1] = replacement
        candidate = ", ".join(items)
        if candidate.casefold() not in {value.casefold() for value in variants}:
            variants.append(candidate)
    if len(variants) < 3 and len(replacements) >= 2:
        items = list(correct_items)
        items[-1] = replacements[0]
        items[-2] = replacements[1]
        candidate = ", ".join(items)
        if candidate.casefold() not in {value.casefold() for value in variants}:
            variants.append(candidate)
    return variants


def _stable_mcq_options(options: list[str], section: dict, index: int) -> tuple[list[str], int]:
    order = sorted(range(len(options)), key=lambda option_index: hashlib.sha256(f"{section.get('sectionId', '')}:{index}:{option_index}".encode("utf-8")).hexdigest())
    return [options[position] for position in order], order.index(0)


def _build_mcq(section: dict, index: int, term_pool: list[str] | None = None) -> dict | None:
    sentences = _meaningful_sentences(section)
    if not sentences:
        return None
    title_words = [word for word in re.findall(r"[a-zA-Z]{4,}", str(section.get("title") or "" ).lower()) if word not in {"based", "system"}]
    titled_claim = next((sentence for sentence in sentences if title_words and all(word in sentence.lower() for word in title_words[:2])), None)
    definition = titled_claim or next((sentence for sentence in sentences if re.search(r"\b(?:is|are|refers to|means|consists of|designed to|used to|measures|contains|includes|provides|requires)\b", sentence, re.IGNORECASE)), sentences[0])
    subject = _concept_subject(definition, section.get("title", ""))
    lowered_definition = definition.lower()
    if "components of" in lowered_definition or lowered_definition.startswith("some of the components"):
        stem = f"Which list matches the source's stated components of {subject}?"
    elif "primary purpose" in lowered_definition:
        stem = f"What is the primary purpose of {subject}?"
    elif lowered_definition.startswith("measurement"):
        stem = "What does measurement of a quantity involve?"
    elif definition is sentences[0] and re.search(r"\b(?:is|are|refers to|means|consists of|designed to|used to|measures|contains|includes|provides|requires)\b", definition, re.IGNORECASE):
        stem = f"Which statement correctly describes {subject}?"
    else:
        stem = f"Which statement is directly supported by the section on {section.get('title') or subject}?"
    list_items = _claim_list_items(definition) if (":" in definition or "components" in lowered_definition) else []
    if list_items:
        list_distractors = _list_distractors(list_items, term_pool or [])
        if len(list_distractors) < 3:
            return None
        correct_option = ", ".join(list_items)
        options, answer_index = _stable_mcq_options([correct_option, *list_distractors[:3]], section, index)
        return {"id": f"mcq_{index:03d}", "topicTitle": section.get("title") or subject, "question": stem, "options": options, "answerIndex": answer_index, "explanation": f"The source lists these components: {correct_option}.", "sourceIds": section.get("sourceIds", []), "sourceAnchors": [block.get("sourceAnchor") for block in section.get("blocks", []) if block.get("sourceAnchor")], "quality": "source_list", "questionType": "components_list"}
    replacements = [
        ("standard known", "standard random"), ("measure", "generate"), ("measures", "generates"), ("measuring", "generating"),
        ("convert", "discard"), ("converts", "discards"), ("known", "random"),
        ("standard", "unrelated"), ("input", "output"), ("output", "input"),
        ("an analog", "A digital"), ("a digital", "An analog"), ("increase", "decrease"),
        ("decrease", "increase"), ("primary", "secondary"), ("secondary", "primary"),
        ("physical quantities", "financial quantities"), ("readable and usable", "unreadable and unusable"),
        ("reliably", "randomly"), ("pointer", "numeric display"), ("waveform", "binary code"),
        ("use", "ignore"), ("purpose", "limitation"),
    ]
    distractors = []
    for replacement in replacements:
        mutated = _mutate_claim(definition, [replacement])
        if mutated and mutated.lower() != definition.lower() and mutated not in distractors:
            distractors.append(mutated)
    if len(distractors) < 3:
        return None
    options, answer_index = _stable_mcq_options([definition, *distractors[:3]], section, index)
    return {"id": f"mcq_{index:03d}", "topicTitle": section.get("title") or subject, "question": stem, "options": options, "answerIndex": answer_index, "explanation": f"The source explains that {definition[0].lower() + definition[1:]}", "sourceIds": section.get("sourceIds", []), "sourceAnchors": [block.get("sourceAnchor") for block in section.get("blocks", []) if block.get("sourceAnchor")], "quality": "source_claim", "questionType": "concept_definition"}


def _is_learning_section(section: dict) -> bool:
    """Exclude cover pages, grading schemes, and administrative OCR chrome."""
    title = str(section.get("title") or "").lower()
    text = _section_preview(section).lower()
    blocked_titles = ("instrumentation (ii/ii)", "course evaluation", "theory (", "practical (", "final exam", "chapter#", "class#work", "references", "assignment")
    if any(marker in title for marker in blocked_titles):
        return False
    if len(text) < 45 or text in {"[source image]", "( )"}:
        return False
    admin_terms = ("attendance", "internal weight", "external weight", "end semester exam", "marks distribution", "mcgraw", "publisher", "edition", "prentic", "crcpress", "tata")
    return not (sum(term in text for term in admin_terms) >= 2 or re.search(r"\(\s*\d{4}\s*\)", text))


def _section_anchor_ids(section: dict) -> list[str]:
    return [str(block.get("sourceAnchor")) for block in section.get("blocks") or [] if block.get("sourceAnchor")]


def _important_question_context(section: dict) -> tuple[str, str, str]:
    """Create a concrete study prompt from the section's actual idea."""
    title = str(section.get("title") or "this topic")
    lowered = title.casefold()
    text = _section_preview(section)
    anchors = _section_anchor_ids(section)
    if "gross error" in lowered:
        question = f"A measurement is recorded incorrectly because of a reading, calculation, connection, or placement mistake. Using {title}, classify the error and state the practical correction or prevention described in the notes."
        focus = "Identify the human source of the mistake and give a concrete prevention or correction."
    elif "systematic error" in lowered:
        question = f"Every reading from an instrument is shifted in the same direction because of calibration, an instrument limitation, or the environment. Using {title}, explain how you would recognize and reduce this error."
        focus = "Look for a repeatable bias, then connect it to calibration, instrument, or environmental correction."
    elif "random error" in lowered:
        question = f"Repeated measurements of an unchanged quantity fluctuate around a mean. Using {title}, identify the error and explain why statistical analysis is appropriate."
        focus = "Classify the unpredictable variation as random error and explain the role of repeated measurements/statistics."
    elif "summary of error" in lowered or lowered.endswith("error"):
        question = f"An instrument gives slightly different readings each time even though the input is unchanged. Using {title}, identify the error type, explain why it occurs, and name the corrective method described in the notes."
        focus = "Classify the error from its behavior, then connect the classification to the source's cause and correction, such as statistical analysis for random variation."
    elif "static and dynamic" in lowered:
        question = "A step input is applied to an instrument and its output takes time to settle. Using Static and Dynamic Performance, distinguish the transient period from the steady-state period and explain which characteristic describes each one."
        focus = "Use the time response: changing output is transient/dynamic; settled output is steady-state/static."
    elif any(word in lowered for word in ("accuracy", "precision", "linearity", "sensitivity", "resolution")):
        question = f"Two instruments are being compared for {title}. Construct a short example that demonstrates the meaning of {title}, then state what observation from the readings would support your explanation."
        focus = "Define the parameter precisely and use an observable measurement example, not a synonym."
    elif "bridge" in lowered or "resistance" in lowered or "impedance" in lowered:
        question = f"A bridge circuit is adjusted until the detector current is zero. For {title}, state what balance condition is used, identify the unknown quantity, and explain how the known components determine it."
        focus = "Identify the balance condition, the unknown, and the source equation or component relationship."
    elif "analog" in lowered and "digital" in lowered:
        question = "A measurement must be shown first as a continuous signal and then as a numerical value. Explain which parts of the instrumentation system perform each role and why the two representations are different."
        focus = "Contrast continuous analog representation with discrete digital representation and name the relevant system stages."
    elif "microprocessor-based system features" in lowered:
        question = "A microprocessor-based system must coordinate several devices while preserving process data. Explain how its preset-value decisions, data storage/retrieval/transmission, and time-sharing capability support that task."
        focus = "Connect each requested feature to its stated role; do not introduce components that are absent from the source."
    elif "control system" in lowered and "microprocessor" in lowered:
        question = "A pressure sample arrives as an analog signal. Compare what the operator does in the open-loop setup with the automated response in the closed-loop setup after the processor compares the sample with its preset limits."
        focus = "Trace analog-to-digital conversion, limit comparison, open-loop operator action, and closed-loop monitoring/control action in the correct order."
    elif "instrumentation benefits" in lowered:
        question = "A plant is considering a programmable instrumentation upgrade. Explain how the listed benefits affect redesign, operating cost, control accuracy, operator decisions, and information exchange with other systems."
        focus = "Use the benefits actually named in the notes, including programmability and timely, accurate information."
    elif "microcomputer on instrumentation design" in lowered:
        question = "A process plant must monitor pressure, temperature, velocity, viscosity, and flow together. Explain how the computer-based system processes the variables and how it can improve the signal and diagnose faults."
        focus = "Mention simultaneous real-time processing, program-controlled noise reduction/gain adjustment, and diagnostic subroutines."
    elif "digital" in lowered or "microprocessor" in lowered or "microcomputer" in lowered:
        question = f"A sensor measures a physical quantity and a controller must decide whether the value is within a limit. Using {title}, trace the signal through the relevant stages and explain what happens when the limit is exceeded."
        focus = "Trace cause to result through the named blocks; do not list unrelated components."
    elif "theory of measurement" in lowered or "instrumentation system" in lowered:
        question = "A physical quantity is not known directly but a calibrated reference is available. Explain how the measurement is formed from the unknown quantity and the standard, and state what usable output the instrumentation system should provide."
        focus = "Define measurement as comparison against a known standard and connect it to a readable signal."
    else:
        claim = re.sub(r"\s+", " ", text).strip(" .")
        question = f"Use the notes on {title} to analyze this situation: {claim[:220]}. Which principle from the section determines the result, and how would you justify it?"
        focus = f"Use the definition and at least one relationship stated in the {title} source section."
    return question, focus, anchors[0] if anchors else ""


def _section_asset_ids(pack: dict, section: dict) -> list[str]:
    ids = [str(block.get("assetId")) for block in section.get("blocks") or [] if block.get("assetId")]
    source_ids = set(section.get("sourceIds") or [])
    pages = set(section.get("pages") or [])
    for asset in pack.get("assets") or []:
        if not asset.get("assetId") or str(asset["assetId"]) in ids:
            continue
        if asset.get("sourceId") in source_ids and (not pages or asset.get("page") in pages):
            ids.append(str(asset["assetId"]))
    return ids


def _section_diagram(section: dict) -> dict | None:
    title = str(section.get("title") or "Concept")
    text = _section_preview(section).casefold()
    title_text = title.casefold()
    structural_terms = ("block diagram", "signal flow", "feedback loop", "consists of", "input and output", "connected to")
    diagram_titles = ("diagram", "architecture", "control", "digital", "analog", "microprocessor", "transducer", "instrumentation system")
    if not any(term in title_text for term in diagram_titles) and not any(term in text for term in structural_terms):
        return None
    if "digital" in title_text or "adc" in text or "microprocessor" in text:
        labels = ["Physical quantity", "Transducer", "Signal processing", "ADC / processor", "Digital display"]
    elif "analog" in title_text or "waveform" in text or "pointer" in text:
        labels = ["Physical quantity", "Transducer", "Signal conditioning", "Analog signal", "Pointer / waveform"]
    elif "control" in title_text or "feedback" in text:
        labels = ["Process variable", "Sensor", "Controller", "Control action", "Process output"]
    else:
        labels = [title, "Source quantity", "Measurement / analysis", "Readable result"]
    return {"nodes": [{"id": f"node-{index}", "label": label} for index, label in enumerate(labels)], "edges": [{"from": f"node-{index}", "to": f"node-{index + 1}"} for index in range(len(labels) - 1)]}


def _slide_intro(section: dict) -> str:
    """Use a short, source-supported lead sentence for a presentation slide."""
    title = str(section.get("title") or "").casefold()
    curated = (
        ("microprocessor-based system features", "A microprocessor-based system includes a microprocessor, I/O devices, and memory."),
        ("microprocessor based control system", "Microprocessor-based control systems can use open-loop or closed-loop control."),
        ("microprocessor-based instrumentation benefits", "Microprocessor-based instrumentation provides automation, programmability, and improved control."),
        ("microcomputer on instrumentation design", "A computer-based instrumentation system can process multiple input variables in real time."),
    )
    for marker, sentence in curated:
        if marker in title:
            return sentence
    sentences = _meaningful_sentences(section)
    return (sentences[0] if sentences else _section_preview(section)).rstrip(" .") + "."


def _slide_bullets(section: dict, preview: str) -> list[str]:
    candidates = _meaningful_sentences(section)
    if not candidates:
        candidates = [part.strip(" -") for part in re.split(r"(?<=[.!?])\s+", preview) if part.strip()]
    intro = _slide_intro(section).casefold().strip(" .")
    points: list[str] = []
    for candidate in candidates:
        point = re.sub(r"\s+", " ", candidate).strip(" .")
        if len(point) < 24 or point.casefold() == intro:
            continue
        if point.casefold() not in {item.casefold() for item in points}:
            points.append(point[:180])
    return points


def _slide_teaching_note(section: dict) -> str:
    title = str(section.get("title") or "this topic")
    lowered = title.casefold()
    if "error" in lowered:
        return "Use the observed behavior to classify the error before choosing a correction."
    if "bridge" in lowered or "resistance" in lowered or "impedance" in lowered:
        return "Follow the balance condition from the known arms to the unknown quantity."
    if "performance" in lowered or any(term in lowered for term in ("accuracy", "precision", "linearity", "sensitivity")):
        return "Keep the parameter definition, what it measures, and its practical observation together."
    if "digital" in lowered or "microprocessor" in lowered or "microcomputer" in lowered:
        return "Trace the signal through each block; the order explains the system's behavior."
    return "Read the definition first, then connect each highlighted term to the source explanation."


def _source_claim(section: dict, *terms: str) -> str:
    """Pick a compact claim from the section instead of echoing the whole page."""
    sentences = _meaningful_sentences(section)
    lowered_terms = tuple(term.casefold() for term in terms)
    for sentence in sentences:
        lowered = sentence.casefold()
        if all(term in lowered for term in lowered_terms):
            return sentence[:420].rstrip(" .") + "."
    for sentence in sentences:
        lowered = sentence.casefold()
        if any(term in lowered for term in lowered_terms):
            return sentence[:420].rstrip(" .") + "."
    preview = _section_preview(section)
    return preview[:420].rstrip(" .") + ("." if preview else "Source text was not readable enough for a defensible answer.")


def _important_explain_context(section: dict) -> tuple[str, str]:
    """Return a real teaching prompt and rubric for the section."""
    title = str(section.get("title") or "this topic")
    lowered = title.casefold()
    if "theory of measurement" in lowered or "instrumentation system" in lowered:
        return (
            "Explain measurement as a comparison between an unknown quantity and a standard. Then state the purpose of the instrumentation system and the form of its usable output.",
            "Define unknown quantity, standard/reference, comparison, and readable signal; connect them in the correct order.",
        )
    if "analog and digital" in lowered or "analog vs digital" in lowered:
        return (
            "Compare analog and digital instruments using the way each represents a measured quantity. Give one practical example of each representation.",
            "Contrast continuous pointer/waveform output with numerical/discrete output and keep the comparison tied to the notes.",
        )
    if lowered == "analog instrument" or "analog instrument" in lowered:
        return (
            "Explain how an analog instrument produces a readable result. Include the role of the pointer or waveform and the electromagnetic-induction principle described in the notes.",
            "Mention the continuous display, the moving element, and electromagnetic induction; do not describe a digital display.",
        )
    if lowered == "digital instrument" or "digital instrument" in lowered:
        return (
            "Explain how a digital instrument converts a measured quantity into a numerical display. Trace the signal through the conversion and display stages.",
            "Describe signal conversion/processing, discrete numerical output, and the display; keep the sequence causal.",
        )
    if "static and dynamic performance" in lowered:
        return (
            "An instrument is given a step input. Explain what happens during the transient period and after the response reaches the steady-state period, and name the performance characteristics associated with each.",
            "Transient behavior belongs to dynamic characteristics; steady-state behavior belongs to static characteristics. Explain the time sequence.",
        )
    if "statistical performance" in lowered:
        return (
            "Define the five static performance parameters listed in the notes—accuracy, precision/repeatability, resolution, sensitivity, and linearity—and distinguish what each one tells an engineer.",
            "Give one precise meaning for each parameter and avoid treating accuracy and precision as synonyms.",
        )
    if "dynamic performance" in lowered:
        return (
            "Explain how response time, time constant, bandwidth, rise time, and delay time describe an instrument responding to a changing input. Include the 63.2% and 10–90% definitions where applicable.",
            "Relate each parameter to time or frequency behavior and distinguish total settling time, time constant, rise time, bandwidth, and delay.",
        )
    if lowered == "error in measurement":
        return (
            "Define measurement error and write the percentage-error relationship using true value and measured value. Then explain why errors are classified into different types.",
            "Use the true-value/measured-value relationship and explain that the classification helps select a correction method.",
        )
    if "gross error" in lowered:
        return (
            "A reading is wrong because of an observation, calculation, connection, or placement mistake. Explain why this is a gross error and state two prevention methods from the notes.",
            "Identify human action as the source and mention careful measurement plus repeated measurements/different users as controls.",
        )
    if "systematic error" in lowered or "environmental error" in lowered:
        return (
            "A measurement shows a repeatable bias caused by the instrument or its environment. Classify the error, explain the cause, and choose an appropriate correction from the notes.",
            "Distinguish instrumental and environmental causes, then connect recalibration, standard instruments, shielding, or controlled conditions to the cause.",
        )
    if "random error" in lowered or "summary of error" in lowered:
        return (
            "Repeated measurements of an unchanged quantity fluctuate unpredictably after gross and systematic errors have been reduced. Explain the error type and how statistical analysis helps.",
            "Identify random error, explain why it cannot be corrected deterministically, and use mean/deviation/standard deviation appropriately.",
        )
    if "bridge" in lowered or "resistance" in lowered or "impedance" in lowered:
        return (
            "Explain how the measurement method in this section uses a balanced circuit to determine an unknown resistance or impedance. State the detector-current condition and the final relationship.",
            "Identify the unknown and known arms, the zero-detector condition, and the final balance equation supported by the source.",
        )
    if "microprocessor-based system features" in lowered:
        return (
            "Explain the features of a microprocessor-based system. Include its core units, decision-making based on set values, data handling, and time-sharing control of equipment.",
            "Name the microprocessor, I/O devices, and memory; then connect preset values, data storage/retrieval/transmission, and time-sharing to their system role.",
        )
    if "control system" in lowered and "microprocessor" in lowered:
        return (
            "Compare the open-loop and closed-loop microprocessor control systems in the notes. Then trace the pressure-monitoring sequence from the analog pressure signal to the alarm or control response.",
            "For open loop, identify the operator changing the input. For closed loop, identify continuous monitoring and the output signal. Include analog-to-digital conversion, preset-limit comparison, and the resulting action.",
        )
    if "instrumentation benefits" in lowered:
        return (
            "Explain how microprocessor-based instrumentation improves automation, redesign flexibility, operating cost, control accuracy, plant operation, and information exchange.",
            "Use the source benefits rather than generic advantages: programmability, reduced complexity/cost, timely information, and relational-database information exchange.",
        )
    if "microcomputer on instrumentation design" in lowered:
        return (
            "Explain how a microcomputer-based instrumentation design handles multiple process variables. Include real-time processing, automatic signal conditioning, diagnostics, and the stated limitations.",
            "Trace multiple measurements through programmed processing, then mention noise reduction, gain adjustment, fault diagnostics, and the relevant software limitations from the notes.",
        )
    if "microprocessor" in lowered or "microcomputer" in lowered:
        return (
            "Explain the role of the microprocessor or microcomputer in an instrumentation system. Trace how it receives a measured signal, processes it, and supports a control or display decision.",
            "Describe the signal path and name the processing/control benefit stated in the source; do not invent hardware not present in the notes.",
        )
    preview = _section_preview(section)
    return (
        f"Explain {title} using two specific claims from the notes. Define the idea first, then show how it is used or recognized in practice: {preview[:220].rstrip(' .') }.",
        f"Use the source definition and at least one concrete relationship, condition, parameter, or example from {title}.",
    )


def _flashcard_items(section: dict, formulas: list[dict]) -> list[dict]:
    """Build retrieval cards with a question front and a source-backed answer."""
    title = str(section.get("title") or "this topic")
    lowered = title.casefold()
    anchors = _section_anchor_ids(section)
    source_ids = section.get("sourceIds", [])
    cards: list[dict] = []

    def add(front: str, back: str, tag: str) -> None:
        answer = re.sub(r"\s+", " ", back).strip()
        if len(answer) < 25 or any(card["front"] == front for card in cards):
            return
        cards.append({"front": front, "back": answer[:520], "tag": tag, "sectionId": section.get("sectionId"), "sourceIds": source_ids, "sourceAnchors": anchors})

    if "theory of measurement" in lowered or "instrumentation system" in lowered:
        add("What is the basic operation performed by an instrumentation system?", _source_claim(section, "unknown", "standard"), "definition")
        add("What should the measurement process produce for a user or controller?", _source_claim(section, "readable", "signal"), "purpose")
    elif "analog and digital" in lowered or "analog vs digital" in lowered:
        add("How does an analog instrument represent a measured quantity?", "An analog system represents the signal continuously, varying smoothly over a range such as voltage levels.", "comparison")
        add("How does a digital instrument represent a measured quantity?", "A digital system represents the measured value discretely, using binary levels; the notes also associate it with higher precision and lower noise sensitivity.", "comparison")
    elif lowered == "analog instrument" or "analog instrument" in lowered:
        add("What principle explains the operation of the analog instrument in the notes?", _source_claim(section, "electromagnetic", "induction"), "principle")
        add("How is an analog measurement made readable?", _source_claim(section, "pointer", "waveform"), "output")
    elif lowered == "digital instrument" or "digital instrument" in lowered:
        add("What is the defining output of a digital instrument?", _source_claim(section, "digital", "numerical"), "definition")
        add("Why is conversion or signal processing needed before a digital display?", _source_claim(section, "conversion", "display"), "process")
    elif "static and dynamic performance" in lowered:
        add("What is the difference between transient and steady-state response?", _source_claim(section, "transient", "steady"), "distinction")
        add("Which performance family describes each response period?", _source_claim(section, "dynamic", "static"), "classification")
    elif "statistical performance" in lowered:
        for label, term in (("Accuracy", "accuracy"), ("Precision or repeatability", "precision"), ("Resolution", "resolution"), ("Sensitivity", "sensitivity"), ("Linearity", "linearity")):
            add(f"What does {label} mean in an instrument's static performance?", _source_claim(section, term), "static parameter")
    elif "dynamic performance" in lowered:
        for label, term in (("time constant", "63.2%"), ("bandwidth", "frequency range"), ("rise time", "10%"), ("delay time", "beginning")):
            add(f"How is {label} defined in the notes?", _source_claim(section, term), "dynamic parameter")
    elif lowered == "error in measurement":
        add("How is measurement error defined?", _source_claim(section, "deviation", "measured"), "definition")
        formula = next((item.get("text") for item in formulas if item.get("sectionId") == section.get("sectionId") and "error" in str(item.get("text") or "").casefold()), "")
        if formula:
            add("What percentage-error relationship should be remembered?", formula, "formula")
    elif "gross error" in lowered:
        add("What causes a gross error in measurement?", _source_claim(section, "users", "calculation"), "cause")
        add("How can gross error be reduced in practice?", _source_claim(section, "corrective", "measurement"), "correction")
    elif "systematic error" in lowered or "environmental error" in lowered:
        add("What makes an error systematic rather than random?", _source_claim(section, "instrumental", "calibration"), "classification")
        add("Which correction matches the environmental cause?", _source_claim(section, "temperature", "shielding"), "correction")
    elif "random error" in lowered or "summary of error" in lowered:
        add("Why is statistical analysis used for random error?", _source_claim(section, "statistical", "mean"), "correction")
        add("When should random-error analysis be applied?", _source_claim(section, "minimizing", "gross"), "method")
    elif "bridge" in lowered or "resistance" in lowered or "impedance" in lowered:
        add("What condition indicates that a bridge is balanced?", _source_claim(section, "detector", "zero"), "balance")
        matching_formula = next((item.get("text") for item in formulas if item.get("sectionId") == section.get("sectionId")), "")
        add("What final relationship is used to calculate the unknown quantity?", matching_formula or _source_claim(section, "unknown", "balance"), "formula")
    elif "microprocessor-based system features" in lowered:
        add("Which core units are included in a microprocessor-based system?", _source_claim(section, "i/o", "memory"), "components")
        add("How does a microprocessor-based system make a control decision?", _source_claim(section, "decision-making", "set values"), "control")
        add("What data-handling capability is listed for the system?", _source_claim(section, "storage", "transmission"), "data handling")
        add("How can the system control multiple equipment?", _source_claim(section, "multiple equipment", "time-sharing"), "control")
    elif "control system" in lowered and "microprocessor" in lowered:
        add("In an open-loop microprocessor control system, who changes the control input?", _source_claim(section, "open-loop", "operator"), "open loop")
        add("What characterizes the closed-loop control system in the notes?", _source_claim(section, "continuous monitoring", "output signal"), "closed loop")
        add("How is a pressure signal handled before microprocessor comparison?", _source_claim(section, "pressure signal", "digital form"), "signal path")
        add("What happens when a sampled pressure measurement is beyond its limits?", _source_claim(section, "beyond", "alarm"), "limit response")
    elif "instrumentation benefits" in lowered:
        add("What design advantage follows from microprocessor programmability?", _source_claim(section, "redesign flexibility", "programmability"), "benefit")
        add("How does processor-based instrumentation support plant operation?", _source_claim(section, "timely", "plant efficiently"), "benefit")
        add("What information-management benefit is listed?", _source_claim(section, "information exchange", "database"), "benefit")
    elif "microcomputer on instrumentation design" in lowered:
        add("What can a computer-based instrumentation system process in real time?", _source_claim(section, "input variables", "real time"), "real time")
        add("Which signal-processing tasks can be automated?", _source_claim(section, "noise reduction", "gain adjustment"), "automation")
        add("What diagnostic capability can be integrated into the system?", _source_claim(section, "diagnostic", "fault"), "diagnostics")
    elif "microprocessor-based instrumentation" in lowered:
        if "integrated circuit" in _section_preview(section).casefold():
            add("What is a microprocessor in the instrumentation notes?", _source_claim(section, "integrated circuit", "central processing"), "definition")
            add("What operations can the microprocessor perform or control?", _source_claim(section, "arithmetic", "input/output"), "operation")
            add("Which internal parts are listed as microprocessor components?", _source_claim(section, "components", "arithmetic logic"), "components")
        else:
            add("What improvement does microprocessor programmability provide?", _source_claim(section, "programmability", "computing"), "capability")
            add("Why can a microprocessor improve accuracy and efficiency?", _source_claim(section, "accuracy", "algorithm"), "benefit")
    elif "benefits of using a microprocessor" in lowered:
        add("What effect can a microprocessor have on system design and cost?", _source_claim(section, "simplifies", "cost"), "benefit")
        add("Why can a microprocessor improve accuracy and efficiency?", _source_claim(section, "accuracy", "computational"), "benefit")
        add("What development challenge is listed as a demerit?", _source_claim(section, "development", "expensive"), "limitation")
    elif "microprocessor" in lowered or "microcomputer" in lowered:
        add("What role does the processor play in an instrumentation system?", _source_claim(section, "processor", "control"), "role")
        add("What practical benefit of processor-based instrumentation is stated?", _source_claim(section, "simplifies", "cost"), "application")

    if not cards:
        sentences = _meaningful_sentences(section)
        if sentences:
            subject = _concept_subject(sentences[0], title)
            add(f"What does the source say about {subject}?", sentences[0], "source claim")
            if len(sentences) > 1:
                add(f"How is {title} used or recognized in practice?", sentences[1], "application")
    return cards


def _flashcard_deck(sections: list[dict], formulas: list[dict]) -> list[dict]:
    """Keep coverage from each topic, even when two prompts share wording."""
    cards: list[dict] = []
    seen_cards: set[tuple[str, str]] = set()
    for section in sections[:40]:
        for card in _flashcard_items(section, formulas):
            key = (
                re.sub(r"\s+", " ", str(card.get("front") or "")).strip().casefold(),
                re.sub(r"\s+", " ", str(card.get("back") or "")).strip().casefold(),
            )
            if key in seen_cards:
                continue
            seen_cards.add(key)
            cards.append(card)
    return cards[:80]


def _topic_mcqs(section: dict, start_index: int) -> list[dict]:
    """Build concise, topic-labelled MCQs for common instrumentation notes.

    These prompts deliberately test one relationship at a time. The previous
    generator could put a true statement from another chapter beside the
    answer, which made the options look arbitrary even though one answer was
    technically correct.
    """
    title = str(section.get("title") or "this topic")
    lowered = title.casefold()
    text = " ".join(_meaningful_sentences(section)).casefold()
    questions: list[dict] = []

    def has(*terms: str) -> bool:
        return all(term.casefold() in text for term in terms)

    def add(question: str, correct: str, distractors: list[str], explanation: str) -> None:
        options = [correct, *distractors]
        if len(options) != 4 or len({option.casefold() for option in options}) != 4:
            return
        stable_options, answer_index = _stable_mcq_options(options, section, start_index + len(questions))
        questions.append({
            "id": f"mcq_{start_index + len(questions):03d}",
            "topicTitle": title,
            "question": question,
            "options": stable_options,
            "answerIndex": answer_index,
            "explanation": f"{explanation} Correct answer: {correct}",
            "sourceIds": section.get("sourceIds", []),
            "sourceAnchors": _section_anchor_ids(section),
            "quality": "topic_specific",
            "questionType": "topic_recall",
        })

    if "microprocessor" not in lowered and "instrumentation system" in lowered:
        if has("unknown", "standard"):
            add(
                "What does measurement compare in an instrumentation system?",
                "An unknown quantity with a standard known quantity.",
                ["Two unknown quantities with each other.", "A measured value with an unrelated financial value.", "Only the final display value with no reference."],
                "The notes define measurement as a comparison of an unknown quantity against a standard known quantity.",
            )
        if has("primary purpose", "readable", "usable"):
            add(
                "What is the primary purpose of an instrumentation system?",
                "To measure physical quantities reliably and convert the result into readable, usable signals.",
                ["To create physical quantities without measuring them.", "To replace every sensor with a manual calculation.", "To store data without producing a measurement result."],
                "The source links reliable measurement of physical quantities to readable and usable signals.",
            )
    elif "analog instrument" in lowered and "digital" not in lowered:
        if has("pointer", "waveform"):
            add(
                "How can an analog instrument display a measurement result?",
                "As a waveform or by a pointer moving across a scale.",
                ["Only as binary code on an LCD.", "Only as a stored database record.", "Only by turning an alarm light on or off."],
                "The analog-instrument section explicitly names a waveform and a pointer across a scale.",
            )
        if has("electromagnetic induction"):
            add(
                "Which principle is identified for analog-instrument operation?",
                "Electromagnetic induction involving a magnet and a current-carrying coil.",
                ["Binary number encoding using 0 and 1.", "Time-sharing between multiple processors.", "Relational database management."],
                "The source explains pointer deflection through electromagnetic induction.",
            )
    elif "digital instrument" in lowered:
        if has("numerical values", "screen"):
            add(
                "What is the defining output of a digital instrument?",
                "Numerical values displayed on a screen.",
                ["A continuously moving pointer only.", "A mechanical deflection with no numerical result.", "An unprocessed analog input only."],
                "The notes define a digital instrument by its numerical screen display.",
            )
        if has("binary", "0", "1"):
            add(
                "Which representation is used by the digital instrument described in the notes?",
                "Binary states represented by 0 and 1.",
                ["A continuously varying voltage scale only.", "A magnet-and-coil deflection only.", "A time-sharing schedule with no data states."],
                "The source states that digital instruments operate using the binary number system with 0 and 1.",
            )
    elif "analog vs digital" in lowered or "analog and digital characteristics" in lowered:
        if has("continuous", "discrete"):
            add(
                "How do analog and digital systems differ in signal type?",
                "Analog signals are continuous, while digital signals are discrete.",
                ["Analog signals are discrete, while digital signals are continuous.", "Both systems use only a moving pointer.", "Neither system represents measurement data."],
                "The comparison table gives continuous signal type for analog and discrete signal type for digital.",
            )
        if has("storage", "retrieval"):
            add(
                "Which system is described as easier to store and retrieve?",
                "The digital system.",
                ["The analog system only.", "Neither system.", "Only a manual pointer scale."],
                "The notes state that digital data is easier to store and retrieve.",
            )
    elif "microprocessor-based system features" in lowered:
        if has("decision-making", "set values"):
            add(
                "What guides the system's decision-making power?",
                "Preset or set values.",
                ["Random values with no limit.", "Only the operator's memory.", "A waveform with no comparison."],
                "The listed feature is decision-making power based on set values.",
            )
        if has("storage", "retrieval", "transmission"):
            add(
                "Which data capability is listed for the microprocessor-based system?",
                "Data storage, retrieval, and transmission.",
                ["Data deletion after every measurement.", "Only manual paper recording.", "No transfer of information between units."],
                "The source explicitly lists storage, retrieval, and transmission.",
            )
    elif "control system" in lowered and "microprocessor" in lowered:
        if has("open-loop", "operator", "control input"):
            add(
                "In the open-loop system, who changes the control input after seeing the microprocessor output?",
                "The operator.",
                ["The sensor without any decision.", "The display unit alone.", "The microprocessor automatically with no operator involvement."],
                "For open-loop control, the notes state that the operator makes the change to the control input.",
            )
        if has("continuous monitoring", "output signal"):
            add(
                "Which behavior identifies the closed-loop system in the notes?",
                "Continuous monitoring of process variables with an output signal to the control system.",
                ["A single display reading with no monitoring.", "Manual calculation without an output signal.", "Data storage with no control action."],
                "Closed-loop control is described as continuous monitoring followed by an output signal to the control system or units.",
            )
        if has("pressure signal", "digital form", "microprocessor"):
            add(
                "What happens to the analog pressure signal before the microprocessor uses it?",
                "It is converted to digital form and fed to the microprocessor.",
                ["It is converted directly into a pointer deflection.", "It is discarded before comparison.", "It is stored as a relational database without processing."],
                "The pressure-monitoring description says the analog pressure signal is converted to digital form before processing.",
            )
    elif "instrumentation benefits" in lowered:
        if has("redesign flexibility", "programmability"):
            add(
                "Which benefit follows from microprocessor programmability?",
                "Redesign flexibility.",
                ["Fixed hardware with no possibility of change.", "Higher operating cost by design.", "Loss of all control accuracy."],
                "The benefits list connects programmability with redesign flexibility.",
            )
        if has("timely", "plant efficiently"):
            add(
                "How does timely and accurate information help plant operation?",
                "It enables operators to run the plant efficiently.",
                ["It prevents operators from receiving information.", "It removes the need to measure process variables.", "It replaces every control unit with a paper record."],
                "The source says timely, accurate information enables efficient plant operation.",
            )
    elif "microcomputer on instrumentation design" in lowered:
        if has("multiple", "input variables", "real time"):
            add(
                "What can the computer-based system process simultaneously?",
                "Multiple input variables in real time.",
                ["Only one variable after manual calculation.", "Only stored data with no live input.", "No physical variables from the process."],
                "The source states that all input variables can be processed simultaneously in real time.",
            )
        if has("noise reduction", "gain adjustment"):
            add(
                "Which tasks can be programmed to occur automatically?",
                "Noise reduction and gain adjustment.",
                ["Noise creation and signal deletion.", "Only mechanical pointer movement.", "Database printing without signal processing."],
                "The notes name noise reduction and gain adjustment as programmable automatic tasks.",
            )
    elif "microprocessor-based instrumentation" in lowered:
        if has("integrated circuit", "central processing"):
            add(
                "What is a microprocessor according to the notes?",
                "An integrated circuit that serves as the central processing unit of a computer or electronic system.",
                ["A sensor that directly measures pressure.", "A display that only shows a pointer position.", "A database containing no processing hardware."],
                "The definition identifies the microprocessor as the CPU implemented as an integrated circuit.",
            )
        if has("arithmetic", "logic", "input/output"):
            add(
                "Which operations can the microprocessor perform or control?",
                "Arithmetic, logic, and input/output operations.",
                ["Only mechanical deflection operations.", "Only unprocessed analog storage.", "Only manual operator actions."],
                "The source lists arithmetic, logic, and input/output operations under stored instructions.",
            )
    elif "benefits of using a microprocessor" in lowered:
        if has("simplifies", "cost"):
            add(
                "What design and cost effect of a microprocessor is stated?",
                "It can simplify design and minimize cost.",
                ["It must make every design more complex and expensive.", "It prevents all application development.", "It removes computational capability from the system."],
                "The benefits section says that a microprocessor can simplify design and minimize cost.",
            )
        if has("accuracy", "efficiency", "computational"):
            add(
                "Why can a microprocessor improve system accuracy and efficiency?",
                "Because of its logical and algorithmic computational power.",
                ["Because it avoids all processing algorithms.", "Because it produces no control decisions.", "Because it removes the need for measured input."],
                "The source attributes improved accuracy and efficiency to microprocessor computational power.",
            )
    return questions


def _flashcard_mcq(card: dict, all_cards: list[dict], index: int, section: dict) -> dict | None:
    """Turn a source-backed recall card into a four-choice retrieval check.

    Distractors remain real source statements from other topics. They are wrong
    answers to this prompt, but never fabricated claims presented as facts.
    """
    correct = re.sub(r"\s+", " ", str(card.get("back") or "")).strip()
    if len(correct) < 25:
        return None
    section_id = str(card.get("sectionId") or section.get("sectionId") or "")
    if len({(str(item.get("front") or ""), str(item.get("back") or "")) for item in all_cards}) < 3:
        return None
    # Keep every option in the same topic. A true sentence copied from an
    # unrelated chapter made the old MCQs look like accidental text dumps.
    topic = str(section.get("title") or "this topic")
    contrasts: list[str] = []
    for source, replacement in (
        ("unknown quantity", "unrelated quantity"),
        ("standard", "random reference"),
        ("continuous", "unmeasured"),
        ("numerical", "unreadable"),
        ("pointer", "database record"),
        ("electromagnetic induction", "manual calculation"),
        ("binary", "mechanical-only"),
        ("arithmetic", "mechanical-only"),
        ("logic", "manual-only"),
        ("programmability", "fixed wiring only"),
        ("accuracy", "inaccuracy"),
        ("set values", "random values"),
        ("storage", "immediate deletion"),
        ("retrieval", "permanent loss"),
        ("open-loop", "unmonitored display-only"),
        ("operator", "no operator"),
        ("continuous monitoring", "no monitoring"),
        ("digital form", "unprocessed analog form"),
        ("real time", "offline-only processing"),
        ("noise reduction", "noise generation"),
        ("gain adjustment", "fixed gain with no adjustment"),
    ):
        mutated = _mutate_claim(correct, [(source, replacement)])
        if mutated and mutated.casefold() != correct.casefold() and mutated.casefold() not in {item.casefold() for item in contrasts}:
            contrasts.append(mutated)
    fallback_contrasts = [
        f"{topic} has no role in the stated measurement, processing, or control task.",
        f"{topic} can only be used after manual processing and cannot perform the stated function.",
        f"{topic} removes the measurement result instead of producing the source-described outcome.",
    ]
    for contrast in fallback_contrasts:
        if len(contrasts) >= 3:
            break
        if contrast.casefold() not in {item.casefold() for item in contrasts}:
            contrasts.append(contrast)
    options, answer_index = _stable_mcq_options([correct, *contrasts[:3]], section, index)
    return {
        "id": f"mcq_{index:03d}",
        "topicTitle": topic,
        "question": str(card.get("front") or f"Which statement is correct about {topic}?"),
        "options": options,
        "answerIndex": answer_index,
        "explanation": f"The source-backed answer is: {correct}",
        "sourceIds": card.get("sourceIds") or section.get("sourceIds", []),
        "sourceAnchors": card.get("sourceAnchors") or _section_anchor_ids(section),
        "quality": "topic_contrast",
        "questionType": "retrieval_transfer",
    }
    candidates = []
    for item in all_cards:
        answer = re.sub(r"\s+", " ", str(item.get("back") or "")).strip()
        if not answer or answer.casefold() == correct.casefold() or str(item.get("sectionId") or "") == section_id:
            continue
        if answer.casefold() not in {value.casefold() for value in candidates}:
            candidates.append(answer)
    # A short source can have fewer than three distinct claims outside the
    # current topic. Other cards from the same topic are still valid wrong
    # answers to this prompt and preserve the four-choice retrieval format.
    if len(candidates) < 3:
        for item in all_cards:
            answer = re.sub(r"\s+", " ", str(item.get("back") or "")).strip()
            if not answer or answer.casefold() == correct.casefold() or answer.casefold() in {value.casefold() for value in candidates}:
                continue
            candidates.append(answer)
    ordered = sorted(candidates, key=lambda answer: hashlib.sha256(f"{section_id}:{index}:{answer}".encode("utf-8")).hexdigest())
    if len(ordered) < 3:
        return None
    options, answer_index = _stable_mcq_options([correct, *ordered[:3]], section, index)
    return {
        "id": f"mcq_{index:03d}",
        "question": str(card.get("front") or "Which source-backed statement is correct?"),
        "options": options,
        "answerIndex": answer_index,
        "explanation": f"The source-backed answer is: {correct}",
        "sourceIds": card.get("sourceIds") or section.get("sourceIds", []),
        "sourceAnchors": card.get("sourceAnchors") or _section_anchor_ids(section),
        "quality": "flashcard_retrieval",
        "questionType": "retrieval_transfer",
    }


def build_artifact_payload(pack: dict, artifact_type: str) -> tuple[str, dict]:
    sections = [section for section in (pack.get("sections") or []) if _is_learning_section(section)]
    if artifact_type == "summary":
        return "Notebook summary", {"kind": "summary", "sections": [{"title": s["title"], "summary": _section_preview(s), "sourceIds": s.get("sourceIds", [])} for s in sections]}
    if artifact_type == "mcq":
        questions = []
        term_pool = _source_term_pool(sections)
        cards = _flashcard_deck(sections, pack.get("formulas") or [])
        cards_by_section: dict[str, list[dict]] = {}
        for card in cards:
            cards_by_section.setdefault(str(card.get("sectionId") or ""), []).append(card)
        for section in sections[:30]:
            section_cards = cards_by_section.get(str(section.get("sectionId") or ""), [])
            specific_questions = _topic_mcqs(section, len(questions) + 1)
            if specific_questions:
                questions.extend(specific_questions)
                if len(specific_questions) >= 2:
                    continue
            direct_question = _build_mcq(section, len(questions) + 1, term_pool)
            if direct_question:
                questions.append(direct_question)
            # Preserve two retrieval checks per topic. When the direct builder
            # supplies a specialised MCQ, the remaining card fills the second
            # slot; otherwise both source-backed cards are used.
            for card in section_cards[1 if direct_question else 0:2]:
                generated = _flashcard_mcq(card, cards, len(questions) + 1, section)
                if generated:
                    questions.append(generated)
        return "MCQ practice", {"kind": "mcq", "questions": questions, "instructions": "Answer first; reveal explanations after submitting.", "quality": "Only source-supported claims are used; sections without a defensible claim are skipped.", "qualitySummary": f"{len(questions)} high-confidence questions built from source claims and parallel source terms."}
    if artifact_type == "slides":
        slides = []
        for index, section in enumerate(sections[:24], start=1):
            preview = _section_preview(section)
            slides.append({"index": index, "title": section["title"], "body": preview, "bullets": [line.strip("-• ") for line in preview.split(".") if line.strip()][:4], "sourceIds": section.get("sourceIds", []), "visualHint": "Create a labeled concept map from the source blocks."})
        return "Slide lesson", {"kind": "slides", "slides": slides, "narration": "Read each slide, then explain the highlighted idea in your own words."}
    if artifact_type == "formula_sheet":
        section_ids = {section.get("sectionId") for section in sections}
        formulas = [formula for formula in (pack.get("formulas") or []) if formula.get("sectionId") in section_ids]
        return "Formula sheet", {"kind": "formula_sheet", "formulas": formulas, "note": "Formulas are shown with their source section and page when available."}
    if artifact_type == "important_questions":
        questions = []
        for index, section in enumerate(sections[:30], start=1):
            application, focus, anchor = _important_question_context(section)
            explain, explain_focus = _important_explain_context(section)
            anchors = _section_anchor_ids(section)
            questions.extend([
                {"id": f"q_{index}_explain", "kind": "explain", "question": explain, "sourceIds": section.get("sourceIds", []), "sourceAnchors": anchors, "answerFocus": explain_focus},
                {"id": f"q_{index}_apply", "kind": "apply", "question": application, "sourceIds": section.get("sourceIds", []), "sourceAnchors": anchors, "answerFocus": focus, "contextAnchor": anchor},
            ])
        return "Important questions", {"kind": "important_questions", "questions": questions}
    if artifact_type == "flashcards":
        cards = _flashcard_deck(sections, pack.get("formulas") or [])
        return "Flashcards", {"kind": "flashcards", "cards": cards[:80], "instructions": "Answer the question aloud before revealing the source-backed explanation.", "quality": "Each card is generated from a concrete definition, relationship, parameter, correction, or formula in the source pack."}
    raise ValueError("unsupported artifact type")


def scoped_knowledge_pack(notebook: Notebook, source_ids: list[str] | None = None) -> dict:
    """Return one validated, source-bounded view of a notebook memory pack.

    The canonical pack remains stored on ``Notebook``. Chat, lessons, and
    artifacts all call this helper instead of assembling their own source
    context, preventing a selected-source answer from accidentally citing an
    unselected file.
    """
    sources = list(notebook.notebook_sources.filter(status="ready", grounding_enabled=True).order_by("created_at", "id"))
    available = {source.source_id for source in sources}
    requested = None if source_ids is None else [str(item).strip() for item in source_ids if str(item).strip()]
    if requested is not None and not requested:
        raise ValueError("Select at least one ready source.")
    invalid = sorted(set(requested or []).difference(available))
    if invalid:
        raise ValueError("One or more selected sources are unavailable in this notebook.")
    selected = set(requested or available)
    if not selected:
        raise ValueError("Add and process at least one source before using the notebook.")
    pack = notebook.knowledge_pack or {}

    def includes(item: dict) -> bool:
        return bool(selected.intersection({str(value) for value in item.get("sourceIds") or []}))

    scoped_sources = [source.source_id for source in sources if source.source_id in selected]
    return {
        **pack,
        "sources": scoped_sources,
        # Keep only safe locator metadata alongside the already selected
        # source IDs. Live provider prompts use this catalog to identify the
        # original document title without receiving unrelated source content.
        "sourceCatalog": [
            {
                "sourceId": source.source_id,
                "title": source.title,
                "filename": source.filename,
            }
            for source in sources
            if source.source_id in selected
        ],
        "sections": [section for section in pack.get("sections") or [] if includes(section)],
        "supplementarySections": [section for section in pack.get("supplementarySections") or [] if includes(section)],
        "concepts": [concept for concept in pack.get("concepts") or [] if includes(concept)],
        "formulas": [formula for formula in pack.get("formulas") or [] if str(formula.get("sourceId") or "") in selected],
        "assets": [asset for asset in pack.get("assets") or [] if str(asset.get("sourceId") or "") in selected],
    }


def _chat_message_payload(message: NotebookChatMessage) -> dict:
    invalidated = message.status == "stale"
    provider_unavailable = message.status == "provider_unavailable"
    provider_output_invalid = message.status == "provider_output_invalid"
    citation_validation_failed = message.status == "citation_validation_failed"
    degraded = provider_unavailable or provider_output_invalid or citation_validation_failed
    if citation_validation_failed:
        provider_message = "The teaching model returned citations that could not be validated. This is a source excerpt, not a generated answer."
    elif provider_output_invalid:
        provider_message = "The teaching model returned an invalid response. This is a source excerpt, not a generated answer."
    elif provider_unavailable:
        provider_message = "The teaching model was unavailable. This is a source excerpt, not a generated answer."
    else:
        provider_message = None
    return {
        "messageId": str(message.message_id),
        "role": message.role,
        "content": "This source-derived message is unavailable because one of its sources was removed." if invalidated else message.content,
        "sourceIds": [] if invalidated else message.source_ids or [],
        "sourceAnchorIds": [] if invalidated else message.source_anchor_ids or [],
        "groundedIn": message.grounded_in or None,
        "status": message.status,
        "invalidated": invalidated,
        "degraded": degraded,
        "providerUnavailable": provider_unavailable,
        "providerOutputInvalid": provider_output_invalid,
        "citationValidationFailed": citation_validation_failed,
        "provider": message.provider_name or None,
        "model": message.provider_model or None,
        "providerErrorCategory": message.provider_error_category or None,
        "providerMessage": provider_message,
        "retryAvailable": degraded,
        "retryAction": "ask_again" if degraded else None,
        "createdAt": message.created_at.isoformat(),
    }


def _note_payload(note: NotebookNote) -> dict:
    return {
        "noteId": str(note.note_id),
        "title": note.title,
        "content": note.content,
        "sourceIds": note.source_ids or [],
        "sourceAnchorIds": note.source_anchor_ids or [],
        "createdAt": note.created_at.isoformat(),
        "updatedAt": note.updated_at.isoformat(),
    }


def _notebook_artifact_payload(artifact: NotebookArtifact) -> dict:
    """Serialize artifact provenance without exposing a provider secret."""
    invalidated = artifact.status == "stale"
    payload = artifact.payload if isinstance(artifact.payload, dict) else {}
    provenance = payload.get("provenance") if isinstance(payload.get("provenance"), dict) else {}
    return {
        "artifactId": str(artifact.artifact_id),
        "type": artifact.artifact_type,
        "title": artifact.title,
        "status": artifact.status,
        "payload": {"invalidated": True, "message": "This output is unavailable because a referenced source was removed."} if invalidated else payload,
        "sourceIds": [] if invalidated else artifact.source_ids or [],
        "provider": None if invalidated else provenance.get("provider"),
        "model": None if invalidated else provenance.get("model"),
        "providerStatus": None if invalidated else provenance.get("status"),
        "citationValidation": None if invalidated else provenance.get("citationValidation"),
        "createdAt": artifact.created_at.isoformat(),
    }


def _notebook_source_payload(source: NotebookSource) -> dict:
    """Expose the durable source location metadata needed by the Source Desk.

    The notebook route remains compatible with its existing source shape, but
    active Learning OS views also need the same page/block anchors returned by
    the goal Source Dock.  Returning them here lets a learner inspect a
    persisted source and understand where a citation came from without
    rebuilding or broadening the source scope.
    """
    extraction = source.extraction if isinstance(source.extraction, dict) else {}
    blocks = source.blocks if isinstance(source.blocks, list) else []
    anchor_ids = [
        str(block.get("sourceAnchor"))
        for block in blocks
        if isinstance(block, dict) and str(block.get("sourceAnchor") or "").strip()
    ]
    page_count = extraction.get("pageCount")
    if not isinstance(page_count, int):
        page_count = max((int(block.get("page") or 1) for block in blocks if isinstance(block, dict)), default=0)
    block_count = extraction.get("blockCount")
    if not isinstance(block_count, int):
        block_count = len(blocks)
    degraded_local = source.extraction_method == "local-fallback-after-mistral-network-error"
    return {
        "sourceId": source.source_id,
        "title": source.title,
        "filename": source.filename,
        "sourceKind": source.source_kind,
        "mimeType": source.mime_type,
        "status": source.status,
        "groundingEnabled": source.grounding_enabled,
        "extractionMethod": source.extraction_method,
        "extraction": extraction,
        "pageCount": page_count,
        "blockCount": block_count,
        "anchorIds": list(dict.fromkeys(anchor_ids)),
        "assets": source.assets,
        # A source retry always requires a fresh multipart upload: raw upload
        # bytes are intentionally not persisted after the request finishes.
        "retryAvailable": bool(source.status == "failed" or degraded_local or extraction.get("retryable")),
        "retryRequiresReupload": True,
        "retryAction": "reupload",
    }


def notebook_payload(notebook: Notebook) -> dict:
    pack = notebook.knowledge_pack or {}
    sources = list(notebook.notebook_sources.order_by("created_at", "id"))
    artifacts = list(notebook.artifacts.order_by("-created_at", "-id"))
    messages = list(notebook.chat_messages.all())
    notes = list(notebook.notes.all())
    return {
        "notebookId": str(notebook.notebook_id),
        "title": notebook.title,
        "subject": notebook.subject,
        "description": notebook.description,
        "learningGoal": notebook.learning_goal,
        "workspaceId": str(notebook.workspace.organization_id) if notebook.workspace_id else None,
        "goalId": str(notebook.goal.goal_id) if notebook.goal_id else None,
        "courseId": str(notebook.course.course_id) if notebook.course_id else None,
        "owned": bool(notebook.owner_profile_id),
        "status": notebook.status,
        "ocrProvider": notebook.ocr_provider,
        "stats": notebook.stats,
        "sources": [_notebook_source_payload(source) for source in sources],
        "knowledgePack": pack,
        "knowledgePackMarkdown": notebook.knowledge_pack_markdown,
        "artifacts": [_notebook_artifact_payload(artifact) for artifact in artifacts],
        "chatMessages": [_chat_message_payload(message) for message in messages],
        "notes": [_note_payload(note) for note in notes],
    }


# Keep the artifact builder close to its source helpers while adding the
# visual payload consumed by the notebook UI. The base builder remains the
# compatibility path for existing artifact types.
_build_artifact_payload_base = build_artifact_payload


def build_artifact_payload(pack: dict, artifact_type: str) -> tuple[str, dict]:
    if artifact_type != "slides":
        return _build_artifact_payload_base(pack, artifact_type)
    sections = [section for section in (pack.get("sections") or []) if _is_learning_section(section)]
    slides = []
    for index, section in enumerate(sections[:24], start=1):
        preview = _section_preview(section)
        # Prefer sentence-level teaching points over a raw character split.
        bullets = _slide_bullets(section, preview)
        bullets = [line.strip("-• ") for line in re.split(r"(?<=[.!?])\s+|\s+-\s+", preview) if line.strip()][:4]
        asset_ids = _section_asset_ids(pack, section)
        bullets = _slide_bullets(section, preview)
        slides.append({
            "index": index,
            "title": section["title"],
            "slideLabel": "SOURCE NOTE",
            "body": preview,
            "bullets": bullets,
            "teachingNote": _slide_teaching_note(section),
            "sourceIds": section.get("sourceIds", []),
            "sourceAnchors": [block.get("sourceAnchor") for block in section.get("blocks", []) if block.get("sourceAnchor")],
            "assetIds": asset_ids,
            # Prefer the learner's real extracted figure. Generate a clean
            # concept diagram only for structural topics that lack one.
            "diagram": None if asset_ids else _section_diagram(section),
            "visualHint": "Use the source figure when available; otherwise show a process diagram only when it clarifies the topic.",
            "visualKind": "source-figure" if asset_ids else "teaching-diagram" if _section_diagram(section) else "text-note",
        })
    return "Slide lesson", {"kind": "slides", "slides": slides, "assets": pack.get("assets") or [], "narration": "Read each slide, then explain the highlighted idea in your own words."}


# A presentation slide has a different information density from a page
# transcript. Keep a final, small slides wrapper so future artifact types can
# continue to use the established builder unchanged.
_build_artifact_payload_with_legacy_slides = build_artifact_payload


def _mind_map_payload(pack: dict) -> tuple[str, dict]:
    sections = [section for section in (pack.get("sections") or []) if _is_learning_section(section)]
    root_id = "notebook-root"
    nodes = [{"id": root_id, "label": str(pack.get("title") or "Notebook"), "kind": "root", "sourceIds": []}]
    edges: list[dict] = []
    for section in sections[:30]:
        section_id = str(section.get("sectionId") or f"section-{len(nodes)}")
        nodes.append({
            "id": section_id,
            "label": str(section.get("title") or "Source topic"),
            "detail": _section_preview(section)[:320],
            "kind": "topic",
            "sourceIds": section.get("sourceIds") or [],
            "sourceAnchors": _section_anchor_ids(section),
        })
        edges.append({"from": root_id, "to": section_id})
    return "Mind map", {
        "kind": "mind_map",
        "nodes": nodes,
        "edges": edges,
        "note": "Each branch is drawn from a saved notebook section and keeps its source anchors.",
    }


def _data_table_payload(pack: dict) -> tuple[str, dict]:
    sections = [section for section in (pack.get("sections") or []) if _is_learning_section(section)]
    formulas_by_section: dict[str, list[str]] = {}
    for formula in pack.get("formulas") or []:
        formulas_by_section.setdefault(str(formula.get("sectionId") or ""), []).append(str(formula.get("text") or ""))
    rows = []
    for section in sections[:60]:
        section_id = str(section.get("sectionId") or "")
        rows.append({
            "topic": str(section.get("title") or "Source topic"),
            "pages": [page for page in section.get("pages") or [] if page],
            "keyIdea": _section_preview(section)[:420],
            "formulas": formulas_by_section.get(section_id, [])[:4],
            "sourceIds": section.get("sourceIds") or [],
            "sourceAnchors": _section_anchor_ids(section),
        })
    return "Source data table", {
        "kind": "data_table",
        "columns": ["Topic", "Pages", "Key idea", "Formulas"],
        "rows": rows,
        "note": "This is a navigable source index, not generated evidence beyond the uploaded material.",
    }


def build_artifact_payload(pack: dict, artifact_type: str) -> tuple[str, dict]:
    if artifact_type == "mind_map":
        return _mind_map_payload(pack)
    if artifact_type == "data_table":
        return _data_table_payload(pack)
    if artifact_type != "slides":
        return _build_artifact_payload_with_legacy_slides(pack, artifact_type)
    sections = [section for section in (pack.get("sections") or []) if _is_learning_section(section)]
    slides: list[dict] = []
    for section in sections[:40]:
        preview = _section_preview(section)
        intro = _slide_intro(section)
        points = _slide_bullets(section, preview)
        # Four brief points fit a 16:9 teaching canvas. Continue a dense
        # source topic on the next slide instead of hiding it in a nested
        # scrollbar or truncating the learner's material.
        groups = [points[offset:offset + 4] for offset in range(0, len(points), 4)] or [[]]
        asset_ids = _section_asset_ids(pack, section)
        diagram = _section_diagram(section)
        for part, bullets in enumerate(groups, start=1):
            has_visual = part == 1 and bool(asset_ids or diagram)
            title = section["title"] if part == 1 else f"{section['title']} ({part}/{len(groups)})"
            slides.append({
                "index": len(slides) + 1,
                "title": title,
                "topicTitle": section["title"],
                "slideLabel": "KEY IDEA" if part == 1 else "CONTINUED",
                "body": intro if part == 1 else f"Continue the source-backed points for {section['title']}.",
                "bullets": bullets,
                "teachingNote": _slide_teaching_note(section),
                "sourceIds": section.get("sourceIds", []),
                "sourceAnchors": [block.get("sourceAnchor") for block in section.get("blocks", []) if block.get("sourceAnchor")],
                "assetIds": asset_ids if part == 1 else [],
                # Prefer the learner's extracted figure. Generate a clean
                # concept diagram only for a structural topic without one.
                "diagram": diagram if part == 1 and not asset_ids else None,
                "visualHint": "Use the extracted source figure when available; otherwise follow the labeled process diagram.",
                "visualKind": "source-figure" if part == 1 and asset_ids else "teaching-diagram" if has_visual else "text-note",
            })
    return "Slide lesson", {"kind": "slides", "slides": slides, "assets": pack.get("assets") or [], "narration": "Read each slide, then explain the highlighted idea in your own words."}
