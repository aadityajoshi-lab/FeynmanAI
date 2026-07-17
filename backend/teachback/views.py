from __future__ import annotations
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AuditRun, Claim, Clarification, LearningSession, Revision
from .providers import AuditRequest, ClarificationRequest, ProviderOutputError, ProviderUnavailable, provider_for
from .sourcepack import ensure_pack, lesson_dict, pack_dict
from .validators import ContractError, validate_audit, validate_question, validate_repair


def _session_id(session: LearningSession) -> str:
    return f"sess_{session.pk:08x}"


def _record_id(session: LearningSession) -> str:
    return f"rec_{session.pk:08x}"


def _lookup_session(value: str) -> LearningSession:
    if value.startswith("sess_"):
        value = value[5:]
    try:
        pk = int(value, 16)
        return LearningSession.objects.get(pk=pk)
    except (ValueError, LearningSession.DoesNotExist):
        raise Http404("Unknown session")


def _iso(value):
    return value.isoformat().replace("+00:00", "Z") if value else None


def _record(session: LearningSession, pack=None, warnings=None) -> dict:
    pack = pack or ensure_pack()
    claims = []
    for claim in session.claims.all():
        item = {
            "claimId": claim.claim_id, "learnerText": claim.learner_text, "verdict": claim.verdict,
            "probe": claim.probe, "sourceAnchorIds": claim.source_anchor_ids, "revisionCount": claim.revision_count,
        }
        if claim.misconception_type:
            item["misconceptionType"] = claim.misconception_type
        latest = claim.revisions.order_by("-id").first()
        if latest:
            item["lastRevisionId"] = f"rev_{latest.pk:08x}"
            item["originalText"] = latest.old_text
        claims.append(item)
    artifact_status = "draft" if session.status == "draft" else "ready_to_ship"
    return {
        "recordId": _record_id(session), "sessionId": _session_id(session), "lessonId": session.lesson_id,
        "sourcePackId": "photosynthesis-v1", "recordVersion": max(1, session.record_version),
        "providerMode": session.provider_mode, "state": session.status, "learnerText": session.learner_text,
        "claims": claims, "artifact": {"status": artifact_status, "title": "Photosynthesis teach-back"},
        "warnings": warnings or [], "createdAt": _iso(session.created_at), "updatedAt": _iso(session.updated_at),
    }


def _error(message: str, code: str = "invalid_request", status_code: int = 422, errors=None):
    return Response({"error": {"code": code, "message": message, "details": errors or []}}, status=status_code)


@method_decorator(csrf_exempt, name="dispatch")
class LessonView(APIView):
    def get(self, request, lesson_id: str):
        if lesson_id != "photosynthesis":
            return _error("Unknown lesson", "not_found", 404)
        return Response(lesson_dict(ensure_pack()))


@method_decorator(csrf_exempt, name="dispatch")
class SessionView(APIView):
    def post(self, request):
        body = request.data if isinstance(request.data, dict) else {}
        lesson_id, text, client_id = body.get("lessonId"), body.get("learnerText"), body.get("clientRequestId")
        if lesson_id != "photosynthesis":
            return _error("lessonId must be photosynthesis")
        if not isinstance(text, str) or not text.strip() or len(text) > 12000:
            return _error("learnerText must be a non-empty string up to 12000 characters", "invalid_input")
        if not isinstance(client_id, str) or len(client_id) < 8 or len(client_id) > 100:
            return _error("clientRequestId must be 8-100 characters")
        pack = ensure_pack()
        existing = LearningSession.objects.filter(client_request_id=client_id).first()
        if existing:
            return Response(_record(existing, pack), status=status.HTTP_200_OK)
        session = LearningSession.objects.create(
            lesson_id=lesson_id, learner_text=text.strip(), client_request_id=client_id,
            record_version=1, provider_mode="codex_fixture", status="draft",
        )
        return Response(_record(session, pack), status=status.HTTP_201_CREATED)


@method_decorator(csrf_exempt, name="dispatch")
class RecordView(APIView):
    def get(self, request, session_id: str):
        return Response(_record(_lookup_session(session_id)))


@method_decorator(csrf_exempt, name="dispatch")
class AuditView(APIView):
    def post(self, request, session_id: str):
        session = _lookup_session(session_id)
        body = request.data if isinstance(request.data, dict) else {}
        expected = body.get("recordVersion")
        if expected is not None and expected != session.record_version:
            return _error("recordVersion is stale", "stale_version", 409)
        pack = ensure_pack()
        session.status = "auditing"
        session.save(update_fields=["status", "updated_at"])
        try:
            provider = provider_for()
            source_spans = pack.spans
            result = provider.audit(AuditRequest(_session_text(session), source_spans, _session_id(session)))
            allowed = {span.get("spanId") for span in source_spans}
            claims = validate_audit(result, allowed)
        except ContractError as exc:
            session.status = "needs_human_review"
            session.provider_mode = "human_review"
            session.save(update_fields=["status", "provider_mode", "updated_at"])
            AuditRun.objects.create(session=session, provider_mode="human_review", status="needs_human_review", errors=exc.errors)
            return Response(_record(session, pack, [exc.code, *exc.errors]), status=status.HTTP_200_OK)
        except (ProviderUnavailable, ProviderOutputError, ValueError) as exc:
            session.status = "needs_human_review"
            session.provider_mode = "human_review"
            session.save(update_fields=["status", "provider_mode", "updated_at"])
            AuditRun.objects.create(session=session, provider_mode="human_review", status="needs_human_review", errors=["invalid_output", str(exc)])
            return Response(_record(session, pack, ["invalid_output", "Provider unavailable or invalid output; human review required."]), status=status.HTTP_200_OK)
        with transaction.atomic():
            session.claims.all().delete()
            for position, data in enumerate(claims):
                Claim.objects.create(session=session, position=position, claim_id=data["claimId"], learner_text=data["learnerText"], verdict=data["verdict"], misconception_type=data.get("misconceptionType"), probe=data["probe"], source_anchor_ids=data["sourceAnchorIds"])
            session.status = "ready"
            session.provider_mode = provider.mode
            # The first successful audit creates Evidence Record v1. Only a
            # learner revision advances the record version.
            session.record_version = max(1, session.record_version)
            session.save(update_fields=["status", "provider_mode", "record_version", "updated_at"])
            AuditRun.objects.create(session=session, provider_mode=provider.mode, status="ready")
        return Response(_record(session, pack))


def _session_text(session: LearningSession) -> str:
    return session.learner_text


@method_decorator(csrf_exempt, name="dispatch")
class ClarificationView(APIView):
    def post(self, request, session_id: str, claim_id: str):
        session = _lookup_session(session_id)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            question = validate_question(body.get("question"))
        except ContractError as exc:
            return _error(str(exc), errors=exc.errors)
        expected = body.get("recordVersion")
        if expected != session.record_version:
            return _error("recordVersion is stale", "stale_version", 409)
        claim = session.claims.filter(claim_id=claim_id).first()
        if not claim:
            return _error("Unknown claim", "not_found", 404)
        pack = ensure_pack()
        try:
            provider = provider_for()
            result = provider.clarify(ClarificationRequest({"claimId": claim.claim_id, "learnerText": claim.learner_text, "verdict": claim.verdict, "misconceptionType": claim.misconception_type}, question, pack.spans, _session_id(session)))
            state = result.get("state")
            if state not in {"answered", "abstained", "needs_human_review"}:
                raise ContractError("Invalid clarification state")
            anchors = result.get("sourceAnchorIds", [])
            allowed = {s.get("spanId") for s in pack.spans}
            if any(x not in allowed for x in anchors) or (state == "answered" and not anchors):
                raise ContractError("Clarification contains invalid source anchors")
        except (ProviderUnavailable, ProviderOutputError, ContractError, ValueError) as exc:
            state, result, anchors = "needs_human_review", {"reasonCode": "invalid_output"}, []
        clarification = Clarification.objects.create(session=session, claim=claim, question=question, status=state, answer=result.get("answer", ""), source_anchor_ids=anchors)
        payload = {"sessionId": _session_id(session), "claimId": claim.claim_id, "recordVersion": session.record_version, "providerMode": getattr(provider_for, "mode", session.provider_mode) if False else session.provider_mode, "state": state, "question": question, "sourceAnchorIds": anchors}
        if result.get("answer"):
            payload["answer"] = result["answer"]
        if state != "answered":
            payload["reasonCode"] = result.get("reasonCode", "provider_unavailable")
        return Response(payload)


@method_decorator(csrf_exempt, name="dispatch")
class RevisionView(APIView):
    def post(self, request, session_id: str, claim_id: str):
        session = _lookup_session(session_id)
        body = request.data if isinstance(request.data, dict) else {}
        try:
            repair = validate_repair(body.get("learnerRepair"))
        except ContractError as exc:
            return _error(str(exc), errors=exc.errors)
        expected = body.get("expectedVersion")
        if expected != session.record_version:
            return _error("expectedVersion is stale", "stale_record_version", 409)
        claim = session.claims.filter(claim_id=claim_id).first()
        if not claim:
            return _error("Unknown claim", "not_found", 404)
        old_text, old_verdict = claim.learner_text, claim.verdict
        try:
            provider = provider_for()
            data = provider.classify_claim(repair, claim.claim_id)
            allowed = {s.get("spanId") for s in ensure_pack().spans}
            validate_audit({"claims": [data]}, allowed)
        except (ProviderUnavailable, ProviderOutputError, ContractError, NotImplementedError, ValueError) as exc:
            session.status = "needs_human_review"
            session.provider_mode = "human_review"
            session.save(update_fields=["status", "provider_mode", "updated_at"])
            return Response(_record(session, warnings=["Revision could not be validated; human review required."]), status=200)
        with transaction.atomic():
            claim.learner_text = data["learnerText"]
            claim.verdict = data["verdict"]
            claim.misconception_type = data.get("misconceptionType")
            claim.probe = data["probe"]
            claim.source_anchor_ids = data["sourceAnchorIds"]
            claim.revision_count += 1
            claim.save()
            # Keep the artifact text aligned with the latest ordered claims while
            # preserving append-only revision history for the selected claim.
            session.learner_text = " ".join(c.learner_text for c in session.claims.order_by("position", "id"))
            session.record_version += 1
            session.status = "ready"
            session.save(update_fields=["learner_text", "record_version", "status", "updated_at"])
            # A repair that explicitly spans both matter and energy concepts can
            # affect neighboring claims. We flag it for review while still
            # re-auditing only the selected claim, per the append-only contract.
            normalized_repair = repair.lower()
            cross_claim_recheck = (
                ("light" in normalized_repair or "sunlight" in normalized_repair)
                and ("energy" in normalized_repair)
                and ("carbon dioxide" in normalized_repair or "co2" in normalized_repair)
                and "water" in normalized_repair
            )
            revision_warning = "cross_claim_recheck" if cross_claim_recheck else "Only the selected claim was re-audited."
            revision = Revision.objects.create(session=session, claim=claim, old_text=old_text, new_text=repair, old_verdict=old_verdict, new_verdict=data["verdict"], record_version=session.record_version, warning=revision_warning)
        return Response({"sessionId": _session_id(session), "claimId": claim.claim_id, "revisionId": f"rev_{revision.pk:08x}", "recordVersion": session.record_version, "providerMode": session.provider_mode, "state": "updated", "before": old_text, "after": repair, "crossClaimRecheck": cross_claim_recheck, "warnings": [revision_warning], "record": _record(session)})


@method_decorator(csrf_exempt, name="dispatch")
class InspectionView(APIView):
    def get(self, request, session_id: str):
        session = _lookup_session(session_id)
        provider = provider_for()
        return Response({"sessionId": _session_id(session), "recordVersion": session.record_version, "provider": provider.health(), "audits": [{"id": audit.id, "status": audit.status, "providerMode": audit.provider_mode, "createdAt": _iso(audit.created_at), "errors": audit.errors} for audit in session.audits.order_by("id")], "revisionCount": session.revisions.count()})
