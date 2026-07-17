import pytest
from teachback.validators import ContractError, validate_audit


def test_supported_requires_anchor():
    with pytest.raises(ContractError):
        validate_audit({"claims": [{"claimId": "claim-01", "learnerText": "x", "verdict": "supported", "probe": "p", "sourceAnchorIds": []}]}, {"photosynthesis-v1-span-01"})


def test_duplicate_claim_ids_rejected():
    item = {"claimId": "claim-01", "learnerText": "x", "verdict": "needs_human_review", "probe": "p", "sourceAnchorIds": []}
    with pytest.raises(ContractError):
        validate_audit({"claims": [item, item]}, set())
