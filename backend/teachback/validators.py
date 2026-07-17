import re


class ContractError(ValueError):
    def __init__(self, message: str, errors: list[str] | None = None, code: str = "invalid_output"):
        super().__init__(message)
        self.errors = errors or [message]
        self.code = code


CLAIM_RE = re.compile(r"^claim-[a-z0-9-]+$")


def validate_audit(result: dict, allowed_source_ids: set[str]) -> list[dict]:
    if not isinstance(result, dict) or not isinstance(result.get("claims"), list):
        raise ContractError("Invalid audit output: claims must be an array", code="invalid_output")
    if len(result["claims"]) > 12:
        raise ContractError("Invalid audit output: at most 12 claims")
    claims: list[dict] = []
    seen: set[str] = set()
    for index, claim in enumerate(result["claims"]):
        if not isinstance(claim, dict):
            raise ContractError(f"Claim {index + 1} is not an object", code="invalid_output")
        required = ("claimId", "learnerText", "verdict", "probe", "sourceAnchorIds")
        if any(not claim.get(key) and key != "sourceAnchorIds" for key in required):
            raise ContractError(f"Claim {index + 1} is missing required fields", code="invalid_output")
        claim_id = claim["claimId"]
        if not isinstance(claim_id, str) or not CLAIM_RE.match(claim_id) or claim_id in seen:
            raise ContractError(f"Invalid or duplicate claimId: {claim_id}", code="invalid_output")
        seen.add(claim_id)
        verdict = claim["verdict"]
        if verdict not in {"supported", "misconception", "needs_precision", "needs_human_review"}:
            raise ContractError(f"Unknown verdict: {verdict}", code="invalid_output")
        if verdict == "misconception" and claim.get("misconceptionType") not in {"source_of_matter", "causal_mechanism", "terminology"}:
            raise ContractError("Misconception claims require a valid misconceptionType", code="invalid_output")
        anchors = claim.get("sourceAnchorIds")
        if not isinstance(anchors, list) or any(x not in allowed_source_ids for x in anchors):
            raise ContractError(f"Claim {claim_id} contains an unknown source anchor", code="invalid_source_anchor")
        if verdict in {"supported", "misconception", "needs_precision"} and not anchors:
            raise ContractError(f"Claim {claim_id} requires a source anchor", code="invalid_source_anchor")
        if not isinstance(claim.get("learnerText"), str) or not claim["learnerText"].strip() or len(claim["learnerText"]) > 2000:
            raise ContractError(f"Claim {claim_id} has invalid learnerText", code="invalid_output")
        claims.append({
            "claimId": claim_id, "learnerText": claim["learnerText"].strip(), "verdict": verdict,
            "misconceptionType": claim.get("misconceptionType"), "probe": str(claim["probe"])[:500],
            "sourceAnchorIds": list(dict.fromkeys(anchors)),
        })
    return claims


def validate_question(question: object) -> str:
    if not isinstance(question, str) or not question.strip() or len(question) > 2000:
        raise ContractError("question must be a non-empty string up to 2000 characters")
    return question.strip()


def validate_repair(repair: object) -> str:
    if not isinstance(repair, str) or not repair.strip() or len(repair) > 2000:
        raise ContractError("learnerRepair must be a non-empty string up to 2000 characters")
    return repair.strip()
