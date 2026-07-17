from __future__ import annotations
import uuid
from django.db import transaction
from django.http import Http404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .dynamic import LEARNING_MODE_IDS, concept_dict, ensure_catalog, module_dict, profile_dict, profile_for_key, recommendation, subject_dict
from .models import AttemptCheckpoint, Concept, LearnerMemory, LearnerProfile, LearningAttempt, Module, SkillEvidence, SubjectPack
from .providers import AuditRequest, ClarificationRequest, FixtureProvider, ProviderUnavailable, provider_for
from .validators import ContractError, validate_audit, validate_question, validate_repair


def _err(message, code="invalid_request", http=422):
    return Response({"error": {"code": code, "message": message}}, status=http)


def _profile_id(profile):
    return profile.anonymous_key


def _profile_for_path(learner_id):
    profile = LearnerProfile.objects.filter(anonymous_key=learner_id).first()
    if not profile:
        raise Http404("Unknown learner")
    return profile


def _attempt(value):
    try:
        return LearningAttempt.objects.select_related("profile", "module", "concept", "module__subject_pack").get(attempt_id=uuid.UUID(str(value)))
    except (ValueError, LearningAttempt.DoesNotExist):
        raise Http404("Unknown attempt")


def _attempt_payload(attempt):
    data = dict(attempt.record or {})
    data.update({"attemptId": str(attempt.attempt_id), "learnerId": _profile_id(attempt.profile), "subjectId": attempt.module.subject_pack.subject_id, "moduleId": attempt.module.module_id, "conceptId": attempt.concept.concept_id if attempt.concept else None, "learningMode": attempt.learning_mode, "state": attempt.state, "recordVersion": attempt.record_version, "providerMode": "codex_fixture", "sourcePackVersion": attempt.module.subject_pack.metadata.get("sourcePackVersion", ""), "learnerText": attempt.learner_text, "checkpoints": [{"checkpointId": c.checkpoint_id, "kind": c.kind, "state": c.state, "response": c.response} for c in attempt.checkpoints.order_by("id")]})
    return data


def _runtime_metadata(attempt):
    return {
        "providerMode": "codex_fixture",
        "sourcePackVersion": attempt.module.subject_pack.metadata.get("sourcePackVersion", ""),
        "recordVersion": attempt.record_version,
    }


def _update_skills(profile, subject_id, skill_ids, signal="audit", score=None):
    for skill_id in skill_ids or []:
        skill, _ = SkillEvidence.objects.get_or_create(profile=profile, subject_id=subject_id, skill_id=skill_id)
        skill.evidence_count += 1
        if score is not None:
            skill.mastery_score = max(0.0, min(1.0, float(score)))
        elif signal in {"supported", "repaired"}:
            skill.mastery_score = min(1.0, skill.mastery_score * 0.7 + 0.3)
        elif signal in {"misconception", "needs_precision"}:
            skill.mastery_score = max(0.0, skill.mastery_score * 0.7)
        skill.recent_signal = signal
        skill.status = "strong" if skill.mastery_score >= 0.8 else "struggling" if skill.mastery_score < 0.4 and skill.evidence_count > 0 else "emerging"
        skill.save()


@method_decorator(csrf_exempt, name="dispatch")
class SubjectListView(APIView):
    def get(self, request):
        ensure_catalog()
        return Response({"subjects": [subject_dict(s) for s in SubjectPack.objects.filter(active=True).order_by("title")]})


@method_decorator(csrf_exempt, name="dispatch")
class SubjectDetailView(APIView):
    def get(self, request, subject_id):
        ensure_catalog()
        subject = SubjectPack.objects.filter(subject_id=subject_id, active=True).first()
        if not subject:
            return _err("Unknown subject", "not_found", 404)
        return Response(subject_dict(subject, include_concepts=True))


@method_decorator(csrf_exempt, name="dispatch")
class SubjectModulesView(APIView):
    def get(self, request, subject_id):
        ensure_catalog()
        subject = SubjectPack.objects.filter(subject_id=subject_id, active=True).first()
        if not subject:
            return _err("Unknown subject", "not_found", 404)
        return Response({"subjectId": subject_id, "modules": [module_dict(m) for m in subject.modules.all()]})


@method_decorator(csrf_exempt, name="dispatch")
class ModuleDetailView(APIView):
    def get(self, request, subject_id, module_id):
        ensure_catalog()
        module = Module.objects.filter(subject_pack__subject_id=subject_id, module_id=module_id).first()
        if not module:
            return _err("Unknown module", "not_found", 404)
        return Response(module_dict(module))


@method_decorator(csrf_exempt, name="dispatch")
class ModuleManifestView(APIView):
    def get(self, request, module_id):
        ensure_catalog()
        module = Module.objects.filter(module_id=module_id).first()
        if not module:
            return _err("Unknown module", "not_found", 404)
        return Response({"manifestVersion": 1, "module": module_dict(module), "sourceBound": bool(module.concepts.filter(source_pack__approved=True).exists()), "attemptsEndpoint": f"/api/v1/modules/{module.module_id}/attempts"})


@method_decorator(csrf_exempt, name="dispatch")
class AnonymousLearnerView(APIView):
    def post(self, request):
        requested = request.data.get("learnerId") if isinstance(request.data, dict) else None
        profile, created = profile_for_key(requested or request.headers.get("X-Learner-ID"))
        response = Response({**profile_dict(profile), "created": created}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        response["X-Learner-ID"] = profile.anonymous_key
        return response


@method_decorator(csrf_exempt, name="dispatch")
class LearnerProfileView(APIView):
    def get(self, request, learner_id):
        return Response(profile_dict(_profile_for_path(learner_id)))

    def patch(self, request, learner_id):
        profile = _profile_for_path(learner_id)
        body = request.data if isinstance(request.data, dict) else {}
        if "displayName" in body:
            if not isinstance(body["displayName"], str) or len(body["displayName"]) > 120:
                return _err("displayName is invalid")
            profile.display_name = body["displayName"].strip()
        if "memoryEnabled" in body:
            profile.memory_enabled = bool(body["memoryEnabled"])
            if not profile.memory_enabled:
                profile.memory_items.update(enabled=False)
        if "preferences" in body:
            if not isinstance(body["preferences"], dict):
                return _err("preferences must be an object")
            profile.preferences = {**profile.preferences, **body["preferences"]}
        profile.save()
        return Response(profile_dict(profile))

    def delete(self, request, learner_id):
        profile = _profile_for_path(learner_id)
        profile.delete()
        return Response({"deleted": True, "learnerId": learner_id})


@method_decorator(csrf_exempt, name="dispatch")
class LearnerPreferencesView(APIView):
    def get(self, request, learner_id):
        return Response({"learnerId": learner_id, "preferences": _profile_for_path(learner_id).preferences})

    def patch(self, request, learner_id):
        profile = _profile_for_path(learner_id)
        if not isinstance(request.data, dict):
            return _err("preferences must be an object")
        profile.preferences = {**profile.preferences, **request.data}
        profile.save(update_fields=["preferences", "updated_at"])
        return Response({"learnerId": learner_id, "preferences": profile.preferences})


@method_decorator(csrf_exempt, name="dispatch")
class LearnerMemoryView(APIView):
    def get(self, request, learner_id):
        profile = _profile_for_path(learner_id)
        return Response({"learnerId": learner_id, "memoryEnabled": profile.memory_enabled, "items": [{"key": m.key, "kind": m.kind, "content": m.content, "enabled": m.enabled} for m in profile.memory_items.filter(enabled=True)]})

    def post(self, request, learner_id):
        profile = _profile_for_path(learner_id)
        body = request.data if isinstance(request.data, dict) else {}
        if not profile.memory_enabled:
            return _err("Memory is disabled for this learner", "memory_disabled", 403)
        key, content = body.get("key"), body.get("content")
        if not isinstance(key, str) or not key.strip() or not isinstance(content, str) or not content.strip() or len(content) > 4000:
            return _err("key and content are required")
        if body.get("consent") is not True:
            return _err("Explicit consent is required to save memory", "consent_required", 403)
        item, _ = LearnerMemory.objects.update_or_create(profile=profile, key=key.strip()[:160], defaults={"kind": str(body.get("kind", "preference"))[:40], "content": content.strip(), "enabled": True, "consented": True})
        return Response({"key": item.key, "kind": item.kind, "content": item.content, "enabled": item.enabled}, status=201)

    def patch(self, request, learner_id):
        profile = _profile_for_path(learner_id)
        if "memoryEnabled" not in (request.data or {}):
            return _err("memoryEnabled is required")
        profile.memory_enabled = bool(request.data["memoryEnabled"])
        if not profile.memory_enabled:
            profile.memory_items.update(enabled=False)
        profile.save(update_fields=["memory_enabled", "updated_at"])
        return Response({"learnerId": learner_id, "memoryEnabled": profile.memory_enabled})

    def delete(self, request, learner_id):
        profile = _profile_for_path(learner_id)
        deleted, _ = profile.memory_items.all().delete()
        return Response({"learnerId": learner_id, "deleted": deleted})


@method_decorator(csrf_exempt, name="dispatch")
class LearnerMemoryExportView(APIView):
    def get(self, request, learner_id):
        profile = _profile_for_path(learner_id)
        return Response({
            "learnerId": learner_id,
            "profile": profile_dict(profile),
            "memory": {
                "enabled": profile.memory_enabled,
                "items": [{"key": m.key, "kind": m.kind, "content": m.content, "consented": m.consented} for m in profile.memory_items.all()],
            },
            "skills": [{"subjectId": s.subject_id, "skillId": s.skill_id, "status": s.status, "masteryScore": s.mastery_score, "evidenceCount": s.evidence_count} for s in profile.skills.all()],
            "attempts": [{"attemptId": str(a.attempt_id), "learnerId": learner_id, "subjectId": a.module.subject_pack.subject_id, "moduleId": a.module.module_id, "recordVersion": a.record_version, "state": a.state} for a in profile.attempts.select_related("module__subject_pack").all()],
        })


@method_decorator(csrf_exempt, name="dispatch")
class RecommendationView(APIView):
    def get(self, request, learner_id):
        return Response(recommendation(_profile_for_path(learner_id), request.query_params.get("subjectId")))


@method_decorator(csrf_exempt, name="dispatch")
class SkillEvidenceView(APIView):
    def get(self, request, learner_id):
        profile = _profile_for_path(learner_id)
        return Response({"learnerId": learner_id, "skills": [{"subjectId": s.subject_id, "skillId": s.skill_id, "status": s.status, "masteryScore": s.mastery_score, "evidenceCount": s.evidence_count, "recentSignal": s.recent_signal} for s in profile.skills.all()]})

    def post(self, request, learner_id):
        profile = _profile_for_path(learner_id)
        body = request.data if isinstance(request.data, dict) else {}
        subject_id, skill_id = body.get("subjectId"), body.get("skillId")
        if not isinstance(subject_id, str) or not isinstance(skill_id, str) or not subject_id or not skill_id:
            return _err("subjectId and skillId are required")
        _update_skills(profile, subject_id, [skill_id], str(body.get("signal", "observed")), body.get("masteryScore"))
        skill = profile.skills.get(subject_id=subject_id, skill_id=skill_id)
        return Response({"subjectId": skill.subject_id, "skillId": skill.skill_id, "status": skill.status, "masteryScore": skill.mastery_score, "evidenceCount": skill.evidence_count})


@method_decorator(csrf_exempt, name="dispatch")
class ModuleAttemptsView(APIView):
    def post(self, request, module_id):
        ensure_catalog()
        module = Module.objects.filter(module_id=module_id).first()
        if not module:
            return _err("Unknown module", "not_found", 404)
        body = request.data if isinstance(request.data, dict) else {}
        profile, _ = profile_for_key(body.get("learnerId") or request.headers.get("X-Learner-ID"))
        if body.get("conceptId"):
            concept = module.concepts.filter(concept_id=body.get("conceptId")).first()
        else:
            # Prefer the current source-bound concept when older fixture rows
            # remain referenced by append-only attempts.
            concept = module.concepts.exclude(source_pack=None).order_by("id").first() or module.concepts.order_by("id").first()
        text = body.get("learnerText", "")
        if not isinstance(text, str) or len(text) > 12000:
            return _err("learnerText must be <= 12000 characters")
        mode = body.get("learningMode") or recommendation(profile, module.subject_pack.subject_id)["mode"]
        allowed_modes = set(concept.metadata.get("allowedLearningModes", [])) if concept else set()
        if allowed_modes and mode not in allowed_modes:
            return _err("learningMode is not allowed for this concept", "invalid_learning_mode")
        attempt = LearningAttempt.objects.create(profile=profile, module=module, concept=concept, learner_text=text, learning_mode=mode, state="draft", record_version=1)
        payload = _attempt_payload(attempt)
        response = Response(payload, status=201)
        response["X-Learner-ID"] = profile.anonymous_key
        return response


def _checkpoint_response(attempt, checkpoint_id, kind, body):
    manifest_checkpoints = (attempt.module.metadata or {}).get("checkpoints", [])
    manifest = next((item for item in manifest_checkpoints if item.get("checkpointId") == checkpoint_id), None)
    if manifest_checkpoints and manifest is None:
        return {"checkpointId": checkpoint_id, "state": "needs_human_review", "reasonCode": "unknown_checkpoint", "sourceAnchorIds": [], **_runtime_metadata(attempt)}
    checkpoint, _ = AttemptCheckpoint.objects.update_or_create(attempt=attempt, checkpoint_id=checkpoint_id, defaults={"kind": kind, "state": "complete", "payload": body, "response": {}})
    source_pack = attempt.concept.source_pack if attempt.concept else None
    source_spans = source_pack.spans if source_pack else []
    try:
        provider = provider_for()
    except ProviderUnavailable:
        return {"checkpointId": checkpoint_id, "state": "needs_human_review", "reasonCode": "provider_unavailable", "sourceAnchorIds": [], **_runtime_metadata(attempt)}
    if kind == "predict":
        answer = {"checkpointId": checkpoint_id, **provider.evaluate_checkpoint({"kind": "predict", "prediction": body.get("prediction", ""), "manifest": manifest or {}})}
    else:
        if source_pack is not None and not source_pack.approved:
            answer = {"checkpointId": checkpoint_id, "state": "needs_human_review", "reasonCode": "source_pack_not_approved", "sourceAnchorIds": []}
        else:
            answer = {"checkpointId": checkpoint_id, **provider.evaluate_checkpoint({"kind": "explain", "explanation": body.get("explanation", ""), "manifest": manifest or {}})}
            if not answer.get("sourceAnchorIds"):
                answer["sourceAnchorIds"] = [s.get("spanId") for s in source_spans[:2]]
    checkpoint.response = answer
    checkpoint.save(update_fields=["response", "state", "updated_at"])
    attempt.record = {**(attempt.record or {}), "lastCheckpoint": answer}
    attempt.record_version += 1
    attempt.save(update_fields=["record", "record_version", "updated_at"])
    return {**answer, **_runtime_metadata(attempt)}


@method_decorator(csrf_exempt, name="dispatch")
class CheckpointView(APIView):
    def post(self, request, attempt_id, checkpoint_id, kind):
        attempt = _attempt(attempt_id)
        body = request.data if isinstance(request.data, dict) else {}
        if kind == "explain" and (not attempt.concept or not attempt.concept.source_pack or not attempt.concept.source_pack.approved):
            return Response({"checkpointId": checkpoint_id, "state": "abstained", "reasonCode": "source_pack_not_approved", "sourceAnchorIds": [], **_runtime_metadata(attempt)})
        return Response(_checkpoint_response(attempt, checkpoint_id, kind, body))


@method_decorator(csrf_exempt, name="dispatch")
class AttemptLearningModeView(APIView):
    def post(self, request, attempt_id):
        attempt = _attempt(attempt_id)
        mode = request.data.get("learningMode") if isinstance(request.data, dict) else None
        if mode not in LEARNING_MODE_IDS:
            return _err("learningMode must be one of the versioned subject-pack learning modes")
        attempt.learning_mode = mode
        attempt.record_version += 1
        attempt.save(update_fields=["learning_mode", "record_version", "updated_at"])
        return Response(_attempt_payload(attempt))


@method_decorator(csrf_exempt, name="dispatch")
class AttemptClarificationView(APIView):
    def post(self, request, attempt_id):
        attempt = _attempt(attempt_id)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            question = validate_question(body.get("question"))
        except ContractError as exc:
            return _err(str(exc))
        claim = body.get("claim") or {"claimId": "claim-dynamic", "learnerText": attempt.learner_text, "verdict": "needs_precision"}
        source_pack = attempt.concept.source_pack if attempt.concept else None
        if source_pack is None:
            return Response({"attemptId": str(attempt.attempt_id), "state": "abstained", "reasonCode": "source_pack_missing", "sourceAnchorIds": [], **_runtime_metadata(attempt)})
        if not source_pack.approved:
            return Response({"attemptId": str(attempt.attempt_id), "state": "abstained", "reasonCode": "source_pack_not_approved", "sourceAnchorIds": [], **_runtime_metadata(attempt)})
        try:
            provider = provider_for()
        except ProviderUnavailable:
            return Response({"attemptId": str(attempt.attempt_id), "state": "needs_human_review", "reasonCode": "provider_unavailable", "sourceAnchorIds": [], **_runtime_metadata(attempt)})
        result = provider.clarify(ClarificationRequest(claim, question, source_pack.spans, str(attempt.attempt_id)))
        result.update({"attemptId": str(attempt.attempt_id), **_runtime_metadata(attempt)})
        return Response(result)


@method_decorator(csrf_exempt, name="dispatch")
class AttemptRevisionView(APIView):
    def post(self, request, attempt_id):
        attempt = _attempt(attempt_id)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            repair = validate_repair(body.get("learnerRepair"))
        except ContractError as exc:
            return _err(str(exc))
        expected = body.get("expectedVersion")
        if expected is not None and expected != attempt.record_version:
            return _err("expectedVersion is stale", "stale_version", 409)
        attempt.learner_text = repair
        attempt.state = "updated"
        attempt.record_version += 1
        attempt.record = {**(attempt.record or {}), "repairedText": repair}
        attempt.save(update_fields=["learner_text", "state", "record_version", "record", "updated_at"])
        _update_skills(attempt.profile, attempt.module.subject_pack.subject_id, attempt.concept.skill_ids if attempt.concept else [], "repaired", 0.75)
        return Response({"attemptId": str(attempt.attempt_id), "state": "updated", "before": body.get("before", ""), "after": repair, **_runtime_metadata(attempt), "record": _attempt_payload(attempt)})


@method_decorator(csrf_exempt, name="dispatch")
class AttemptRecordView(APIView):
    def get(self, request, attempt_id):
        return Response(_attempt_payload(_attempt(attempt_id)))


@method_decorator(csrf_exempt, name="dispatch")
class AttemptInspectionView(APIView):
    def get(self, request, attempt_id):
        attempt = _attempt(attempt_id)
        return Response({"attemptId": str(attempt.attempt_id), "learnerId": attempt.profile.anonymous_key, "subjectId": attempt.module.subject_pack.subject_id, "moduleId": attempt.module.module_id, "recordVersion": attempt.record_version, "providerMode": "codex_fixture", "sourceBound": bool(attempt.concept and attempt.concept.source_pack), "checkpointCount": attempt.checkpoints.count(), "skillEvidence": [{"skillId": s.skill_id, "status": s.status, "masteryScore": s.mastery_score} for s in attempt.profile.skills.filter(subject_id=attempt.module.subject_pack.subject_id)]})
