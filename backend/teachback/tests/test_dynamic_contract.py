"""Contract-level checks for the dynamic subject catalog and learner state.

These tests intentionally exercise the catalog/state helpers directly while the
HTTP resources are being integrated; route tests can reuse the same fixture
cases without duplicating subject or recommendation semantics.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from teachback.dynamic import ensure_catalog, profile_for_key, recommendation
from teachback.models import LearnerMemory, SkillEvidence
from teachback.validators import ContractError, validate_audit


CASES = json.loads(
    (Path(__file__).resolve().parents[3] / "contracts" / "v1" / "dynamic-evaluation-cases.json").read_text(encoding="utf-8")
)["cases"]


def dynamic_case(case_id: str) -> dict:
    return next(item for item in CASES if item["caseId"] == case_id)


@pytest.mark.django_db
def test_dsap_catalog_and_photosynthesis_source_binding() -> None:
    packs = ensure_catalog()
    assert {pack.subject_id for pack in packs} >= {"photosynthesis", "dsap", "ai-literacy"}
    dsap = next(pack for pack in packs if pack.subject_id == "dsap")
    dsap_concept = dsap.modules.get(module_id="sampling-aliasing").concepts.get(concept_id="alias-frequency")
    assert dsap_concept.skill_ids == ["alias-frequency"]
    assert dynamic_case("dynamic-01-dsap-catalog")["expected"]["sourcePackRequired"] is False

    biology = next(pack for pack in packs if pack.subject_id == "photosynthesis")
    biology_concept = biology.modules.get(module_id="plant-mass").concepts.get(concept_id="matter-vs-energy")
    assert biology_concept.source_pack is not None
    assert biology_concept.source_pack.lesson_id == "photosynthesis"


@pytest.mark.django_db
def test_recommendation_modes_follow_evidence_and_preference() -> None:
    profile, _ = profile_for_key("dynamic-recommendation")
    guided = recommendation(profile, "dsap")
    assert guided["mode"] == dynamic_case("dynamic-04-recommendation-guided")["expected"]["mode"]
    assert guided["reason"] == "no_skill_evidence_yet"

    SkillEvidence.objects.create(profile=profile, subject_id="dsap", skill_id="aliasing", status="struggling", mastery_score=0.2)
    repair = recommendation(profile, "dsap")
    assert repair["mode"] == dynamic_case("dynamic-05-recommendation-repair")["expected"]["mode"]
    assert repair["reason"] == "recent_skill_evidence_needs_repair"

    SkillEvidence.objects.filter(profile=profile).update(status="mastered", mastery_score=0.9)
    build = recommendation(profile, "dsap")
    assert build["mode"] == dynamic_case("dynamic-06-recommendation-build")["expected"]["mode"]
    assert build["reason"] == "skills_have_strong_evidence"

    profile.preferences = {"learningMode": "predict_reveal"}
    profile.save(update_fields=["preferences", "updated_at"])
    preferred = recommendation(profile, "dsap")
    assert preferred["mode"] == "predict_reveal"
    assert preferred["reason"] == "learner_preference"


@pytest.mark.django_db
def test_memory_isolation_and_delete_semantics() -> None:
    profile_a, _ = profile_for_key("dynamic-memory-a")
    profile_b, _ = profile_for_key("dynamic-memory-b")
    memory = LearnerMemory.objects.create(profile=profile_a, key="preferred-mode", kind="preference", content="build", consented=True)
    assert profile_a.memory_items.get(key="preferred-mode").content == "build"
    assert not profile_b.memory_items.filter(key="preferred-mode").exists()
    memory.delete()
    assert not profile_a.memory_items.filter(key="preferred-mode").exists()
    assert dynamic_case("dynamic-07-memory-isolation")["expected"]["bSeesA"] is False
    assert dynamic_case("dynamic-08-memory-delete")["expected"]["memoryAfterDelete"] is False


@pytest.mark.django_db
def test_unknown_source_anchor_is_rejected_for_source_bound_concept() -> None:
    ensure_catalog()
    allowed = {f"photosynthesis-v1-span-{index:02d}" for index in range(1, 9)}
    with pytest.raises(ContractError) as error:
        validate_audit(
            {"claims": [{"claimId": "claim-01", "learnerText": "unsupported", "verdict": "supported", "probe": "why?", "sourceAnchorIds": ["photosynthesis-v1-span-99"]}]},
            allowed,
        )
    assert error.value.code == dynamic_case("dynamic-10-source-bound-audit")["expected"]["errorCode"]
