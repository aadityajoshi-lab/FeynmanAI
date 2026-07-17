"""Load the approved source pack from contracts/v1 with a safe fallback."""
import json
from pathlib import Path
from django.conf import settings
from .models import SourcePack

FALLBACK = {
    "sourcePackId": "photosynthesis-v1", "lessonId": "photosynthesis", "version": 1,
    "title": "Where does a plant's mass come from?", "topic": "photosynthesis",
    "license": {"name": "CC BY 4.0", "holder": "Feynman AI project", "notice": "Project-authored source pack."},
    "spans": [
        {"spanId": "photosynthesis-v1-span-01", "section": "The mass question", "text": "A plant's dry mass is made mostly from carbon-containing compounds built from carbon dioxide and water during photosynthesis."},
        {"spanId": "photosynthesis-v1-span-02", "section": "Carbon dioxide supplies carbon", "text": "During photosynthesis, carbon dioxide enters leaves and supplies carbon atoms that become part of sugars."},
        {"spanId": "photosynthesis-v1-span-03", "section": "Water is raw material", "text": "Water supplies hydrogen and oxygen atoms and is a raw material used to make sugars."},
        {"spanId": "photosynthesis-v1-span-04", "section": "Light supplies energy", "text": "Light provides energy for photosynthesis; light is not converted into the plant's dry mass."},
        {"spanId": "photosynthesis-v1-span-05", "section": "Minerals are a small fraction", "text": "Mineral nutrients from soil are essential for growth, but they account for only a small fraction of most plant dry mass."},
        {"spanId": "photosynthesis-v1-span-06", "section": "Carbon is not primarily from soil", "text": "The carbon in a plant's sugars is not taken primarily from soil; it is fixed from carbon dioxide in air."},
        {"spanId": "photosynthesis-v1-span-07", "section": "The transformation", "text": "Photosynthesis uses light energy to combine carbon dioxide and water into sugars, releasing oxygen as a by-product."},
        {"spanId": "photosynthesis-v1-span-08", "section": "Matter versus energy", "text": "A useful explanation should distinguish matter inputs (carbon dioxide, water, minerals) from an energy input (light)."},
    ],
}


def load_pack() -> dict:
    path = settings.BASE_DIR.parent / "contracts" / "v1" / "source_pack.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return FALLBACK


def ensure_pack() -> SourcePack:
    data = load_pack()
    pack, _ = SourcePack.objects.update_or_create(
        lesson_id=data["lessonId"],
        defaults={
            "title": data["title"], "description": data.get("topic", ""),
            "version": str(data.get("version", 1)),
            "source_url": data.get("sourceDocument", {}).get("path", ""),
            "license_text": data.get("license", {}).get("name", ""),
            "approved": True, "spans": data.get("spans", []),
        },
    )
    return pack


def pack_dict(pack: SourcePack) -> dict:
    source = load_pack()
    return {
        "sourcePackId": source.get("sourcePackId", "photosynthesis-v1"),
        "lessonId": pack.lesson_id, "version": int(pack.version), "title": pack.title,
        "topic": source.get("topic", "photosynthesis"), "license": source.get("license", {}),
        "spans": pack.spans,
    }


def lesson_dict(pack: SourcePack) -> dict:
    return {
        "lessonId": pack.lesson_id,
        "title": pack.title,
        "prompt": "Teach back where most of a plant's dry mass comes from and how photosynthesis makes that possible.",
        "sourcePackId": "photosynthesis-v1",
        "learningGoal": "Distinguish matter inputs from energy inputs in photosynthesis.",
        "estimatedMinutes": 8,
        "constraints": ["Use the approved source pack as your evidence boundary.", "Explain matter inputs separately from energy."],
        "sourcePack": pack_dict(pack),
    }
