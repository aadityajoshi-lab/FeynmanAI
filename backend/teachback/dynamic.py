"""Fixture-backed dynamic subject catalog and anonymous learner state."""
from __future__ import annotations
import json
import re
import uuid
from pathlib import Path
from django.conf import settings
from django.db import transaction
from .models import Concept, LearnerMemory, LearnerProfile, Module, SkillEvidence, SourcePack, SubjectPack
from .sourcepack import ensure_pack

FALLBACK_SUBJECTS = [
    {"subjectId": "photosynthesis", "title": "Photosynthesis", "summary": "Trace matter and energy through a plant.", "version": 1, "modules": [{"moduleId": "plant-mass", "title": "Where does plant mass come from?", "summary": "Matter inputs versus energy inputs.", "position": 1, "concepts": [{"conceptId": "matter-vs-energy", "title": "Matter versus energy", "prompt": "Teach back where most of a plant's dry mass comes from and how photosynthesis makes that possible.", "learningGoal": "Distinguish matter inputs from energy inputs.", "skillIds": ["matter-energy-separation", "causal-explanation"]}, {"conceptId": "carbon-source", "title": "Follow one carbon atom", "prompt": "Explain how carbon dioxide becomes part of a plant sugar.", "learningGoal": "Trace carbon from air into plant biomass.", "skillIds": ["matter-energy-separation"]}]}]},
    {"subjectId": "ai-literacy", "title": "AI literacy", "summary": "Build reliable habits for working with AI systems.", "version": 1, "modules": [{"moduleId": "clear-instructions", "title": "Clear instructions", "summary": "Turn intent into testable instructions.", "position": 1, "concepts": [{"conceptId": "observable-output", "title": "Ask for observable outputs", "prompt": "Rewrite an ambiguous AI request so a reviewer can test its result.", "learningGoal": "Connect instructions to observable checks.", "skillIds": ["specification", "verification"]}]}]},
]
LEARNING_MODE_IDS = {"worked_example", "predict_reveal", "self_explain", "retrieval", "spaced_review", "interleaved_contrast", "concrete_example", "representation_switch", "exam_bridge"}


def _catalog_data() -> list[dict]:
    path = settings.BASE_DIR.parent / "contracts" / "v1" / "subjects.json"
    data = FALLBACK_SUBJECTS[:]
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        # The contract wraps the catalog with a schema/version envelope; keep
        # accepting a bare list for older local fixtures.
        if isinstance(loaded, dict) and isinstance(loaded.get("subjects"), list):
            data = loaded["subjects"]
        elif isinstance(loaded, list):
            data = loaded
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    # DSAP is governed by the v2 subject pack. Overlay that canonical module
    # instead of silently serving the earlier compatibility alias.
    v2_path = settings.BASE_DIR.parent / "contracts" / "v2" / "dsap-sampling-aliasing.json"
    try:
        dsap = json.loads(v2_path.read_text(encoding="utf-8"))
        modules = []
        for module in dsap.get("modules", []):
            concepts = []
            for concept in module.get("concepts", []):
                modes = concept.get("allowedLearningModes", [])
                concepts.append({"conceptId": concept["conceptId"], "title": concept["title"], "prompt": concept.get("title", "Explain this concept."), "learningGoal": concept.get("skillType", ""), "skillIds": [concept["conceptId"]], "allowedLearningModes": modes, "metadata": {"skillType": concept.get("skillType", ""), "allowedLearningModes": modes}})
            modules.append({"moduleId": module["moduleId"], "title": module["title"], "summary": module.get("objective", ""), "objective": module.get("objective", ""), "position": 1, "prerequisites": module.get("prerequisites", []), "mediaAssets": module.get("mediaAssets", []), "checkpoints": module.get("checkpoints", []), "examBridge": module.get("examBridge", []), "concepts": concepts})
        data = [item for item in data if item.get("subjectId") != "dsap"]
        data.append({"subjectId": "dsap", "title": dsap.get("title", "Digital Signal Analysis and Processing"), "summary": dsap.get("domain", "engineering"), "version": 1, "versionLabel": dsap.get("version", "dsap-v1"), "sourcePackVersion": dsap.get("sourcePackVersion", "dsap-sampling-v1"), "domain": dsap.get("domain", "engineering"), "learningModes": dsap.get("learningModes", []), "modules": modules})
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return data


def ensure_catalog() -> list[SubjectPack]:
    """Idempotently materialize the versioned fixture catalog."""
    packs: list[SubjectPack] = []
    source_pack = ensure_pack()
    # DSAP uses its own approved source boundary. Keep it in the same
    # server-owned SourcePack table so checkpoint explanations can never invent
    # anchors from the photosynthesis lesson (or from the browser).
    dsap_source_pack = None
    dsap_path = settings.BASE_DIR.parent / "contracts" / "v2" / "source-pack.json"
    try:
        dsap_data = json.loads(dsap_path.read_text(encoding="utf-8"))
        if isinstance(dsap_data, dict) and dsap_data.get("sourcePackId"):
            dsap_source_pack, _ = SourcePack.objects.update_or_create(
                lesson_id=dsap_data["sourcePackId"],
                defaults={
                    "title": "DSAP sampling and aliasing",
                    "description": "Instructor-authored sampling and aliasing source pack.",
                    "version": str(dsap_data.get("version", "1.0.0")),
                    "source_url": "",
                    "license_text": str(dsap_data.get("license", ""))[:240],
                    "approved": dsap_data.get("approvalStatus") == "approved",
                    "spans": dsap_data.get("spans", []),
                },
            )
    except (FileNotFoundError, json.JSONDecodeError):
        dsap_source_pack = None
    with transaction.atomic():
        for subject_data in _catalog_data():
            subject, _ = SubjectPack.objects.update_or_create(
                subject_id=subject_data["subjectId"],
                defaults={"title": subject_data["title"], "summary": subject_data.get("summary", ""), "version": int(subject_data.get("version", 1)), "active": bool(subject_data.get("active", True)), "metadata": {**subject_data.get("metadata", {}), "versionLabel": subject_data.get("versionLabel", str(subject_data.get("version", 1))), "sourcePackVersion": subject_data.get("sourcePackVersion", "photosynthesis-v1" if subject_data.get("subjectId") == "photosynthesis" else ""), "domain": subject_data.get("domain", ""), "learningModes": subject_data.get("learningModes", [])}},
            )
            packs.append(subject)
            for module_data in subject_data.get("modules", []):
                module, _ = Module.objects.update_or_create(
                    subject_pack=subject, module_id=module_data["moduleId"],
                    defaults={"title": module_data["title"], "summary": module_data.get("summary", ""), "position": int(module_data.get("position", 0)), "version": int(module_data.get("version", 1)), "metadata": {**module_data.get("metadata", {}), "objective": module_data.get("objective", ""), "prerequisites": module_data.get("prerequisites", []), "mediaAssets": module_data.get("mediaAssets", []), "checkpoints": module_data.get("checkpoints", []), "examBridge": module_data.get("examBridge", [])}},
                )
                for concept_data in module_data.get("concepts", []):
                    concept_source_pack = source_pack if subject.subject_id == "photosynthesis" else dsap_source_pack if subject.subject_id == "dsap" else None
                    Concept.objects.update_or_create(
                        module=module, concept_id=concept_data["conceptId"],
                        defaults={"title": concept_data["title"], "prompt": concept_data.get("prompt", concept_data["title"]), "learning_goal": concept_data.get("learningGoal", ""), "learning_mode": (concept_data.get("allowedLearningModes") or [concept_data.get("learningMode", "guided")])[0], "skill_ids": concept_data.get("skillIds", [concept_data.get("conceptId")]), "source_pack": concept_source_pack, "version": int(concept_data.get("version", 1)), "metadata": {**concept_data.get("metadata", {}), "allowedLearningModes": concept_data.get("allowedLearningModes", []), "skillType": concept_data.get("skillType", "")}},
                    )
    return packs


def subject_dict(subject: SubjectPack, include_concepts: bool = False) -> dict:
    data = {"subjectId": subject.subject_id, "title": subject.title, "summary": subject.summary, "version": subject.metadata.get("versionLabel", str(subject.version)), "versionLabel": subject.metadata.get("versionLabel", str(subject.version)), "domain": subject.metadata.get("domain", ""), "sourcePackVersion": subject.metadata.get("sourcePackVersion", ""), "learningModes": subject.metadata.get("learningModes", []), "active": subject.active, "modules": []}
    for module in subject.modules.all():
        item = {"moduleId": module.module_id, "title": module.title, "summary": module.summary, "objective": module.metadata.get("objective", module.summary), "prerequisites": module.metadata.get("prerequisites", []), "version": module.version, "position": module.position, "mediaAssets": module.metadata.get("mediaAssets", []), "checkpoints": module.metadata.get("checkpoints", []), "examBridge": module.metadata.get("examBridge", [])}
        if include_concepts:
            item["concepts"] = [concept_dict(concept) for concept in module.concepts.all()]
        data["modules"].append(item)
    return data


def module_dict(module: Module) -> dict:
    return {"moduleId": module.module_id, "subjectId": module.subject_pack.subject_id, "title": module.title, "summary": module.summary, "objective": module.metadata.get("objective", module.summary), "prerequisites": module.metadata.get("prerequisites", []), "version": module.version, "position": module.position, "mediaAssets": module.metadata.get("mediaAssets", []), "checkpoints": module.metadata.get("checkpoints", []), "examBridge": module.metadata.get("examBridge", []), "concepts": [concept_dict(c) for c in module.concepts.all()]}


def concept_dict(concept: Concept) -> dict:
    data = {"conceptId": concept.concept_id, "moduleId": concept.module.module_id, "subjectId": concept.module.subject_pack.subject_id, "title": concept.title, "prompt": concept.prompt, "learningGoal": concept.learning_goal, "learningMode": concept.learning_mode, "allowedLearningModes": concept.metadata.get("allowedLearningModes", []), "skillType": concept.metadata.get("skillType", ""), "skillIds": concept.skill_ids, "version": concept.version}
    if concept.source_pack:
        data["sourcePackId"] = "photosynthesis-v1" if concept.source_pack.lesson_id == "photosynthesis" else concept.source_pack.lesson_id
        data["sourcePackVersion"] = concept.source_pack.version
    return data


def profile_for_key(key: str | None = None) -> tuple[LearnerProfile, bool]:
    safe = key.strip()[:128] if isinstance(key, str) and key.strip() else None
    if safe:
        existing = LearnerProfile.objects.filter(anonymous_key=safe).first()
        if existing:
            return existing, False
    profile = LearnerProfile.objects.create(anonymous_key=safe or f"anon_{uuid.uuid4().hex}")
    return profile, True


def profile_dict(profile: LearnerProfile) -> dict:
    return {"learnerId": profile.anonymous_key, "profileId": str(profile.profile_id), "displayName": profile.display_name, "preferences": profile.preferences, "memoryEnabled": profile.memory_enabled, "createdAt": profile.created_at.isoformat(), "updatedAt": profile.updated_at.isoformat()}


def recommendation(profile: LearnerProfile, subject_id: str | None = None) -> dict:
    ensure_catalog()
    subject_id = subject_id or "photosynthesis"
    subject = SubjectPack.objects.filter(subject_id=subject_id, active=True).first()
    if not subject:
        return {"subjectId": subject_id, "mode": "guided", "reason": "unknown_subject", "concept": None, "nextAction": "Choose an available subject."}
    skills = list(profile.skills.filter(subject_id=subject_id))
    preferred = profile.preferences.get("learningMode") if isinstance(profile.preferences, dict) else None
    available_modes = [m.get("modeId") for m in subject.metadata.get("learningModes", []) if isinstance(m, dict) and m.get("modeId")]
    valid_modes = set(available_modes) or LEARNING_MODE_IDS
    legacy_modes = set() if available_modes else {"guided", "practice", "build", "repair", "review"}
    if preferred in valid_modes:
        mode, reason = preferred, "learner_preference"
    elif not skills:
        mode, reason = (available_modes[0] if available_modes else "guided"), "no_skill_evidence_yet"
    elif any(skill.status in {"struggling", "repair"} or skill.mastery_score < 0.4 for skill in skills):
        mode, reason = ("retrieval" if available_modes else "repair"), "recent_skill_evidence_needs_repair"
    elif all(skill.mastery_score >= 0.8 for skill in skills):
        mode, reason = ("exam_bridge" if available_modes else "build"), "skills_have_strong_evidence"
    else:
        mode, reason = (available_modes[0] if available_modes else "self_explain"), "skills_are_still_developing"
    # Pick a concept whose authored mode policy supports the recommendation;
    # do not silently replace a learner-evidence recommendation with the first
    # catalog item merely because its allowed modes differ.
    concepts = list(Concept.objects.filter(module__subject_pack=subject).order_by("module__position", "module_id", "id"))
    concept = next((item for item in concepts if mode in item.metadata.get("allowedLearningModes", [])), None) or (concepts[0] if concepts else None)
    concept_payload = concept_dict(concept) if concept else None
    if concept_payload and concept_payload.get("allowedLearningModes") and mode not in concept_payload["allowedLearningModes"] and mode not in legacy_modes:
        mode = concept_payload["allowedLearningModes"][0]
        reason = "concept_allowed_mode"
    next_action = "Predict before the reveal, then explain the evidence." if mode == "predict_reveal" else "Repair one claim, then ship a verified artifact." if mode in {"retrieval", "self_explain"} else "Build a bounded explanation and test it."
    return {"subjectId": subject_id, "mode": mode, "reason": reason, "concept": concept_payload, "nextAction": next_action, "availableModes": subject.metadata.get("learningModes", []), "skillEvidence": [{"skillId": s.skill_id, "status": s.status, "masteryScore": s.mastery_score, "evidenceCount": s.evidence_count} for s in skills]}
