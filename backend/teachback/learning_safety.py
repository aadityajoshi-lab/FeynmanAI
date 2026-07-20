"""Domain-specific guardrails for goal-attached source workspaces.

The learning runtime can help someone analyze academic medical or finance
material, but it must not turn a source-grounded notebook into personal
clinical or investment advice.  Keeping this small and deterministic means
the provider never has to infer the boundary after it has seen a sensitive
request.
"""

from __future__ import annotations

import re


_PERSONAL_MEDICAL = (
    r"\b(?:diagnose|diagnosis|treat|treatment|prescribe|prescription|dose|dosage|take)\b.*\b(?:me|my|i|patient)\b",
    r"\b(?:my|i have|i'm having|i am having)\b.*\b(?:symptom|pain|rash|fever|condition|illness|medication)\b",
    r"\b(?:what should i|should i)\b.*\b(?:take|do|use|seek|treat)\b",
)

_PERSONAL_FINANCE = (
    r"\b(?:should i|what should i)\b.*\b(?:buy|sell|invest|trade|hold)\b",
    r"\b(?:my|i have|i'm holding|i am holding)\b.*\b(?:portfolio|stock|shares|crypto|investment|position)\b",
    r"\b(?:recommend|pick)\b.*\b(?:stock|fund|crypto|investment|trade)\b",
)


def personal_decision_boundary(domain: str, question: str) -> str | None:
    """Return a clear educational-only response for a personal decision ask.

    The caller supplies the already-classified learning-goal domain, so an
    ordinary notebook is unaffected.  Academic prompts such as "explain how
    diagnosis works" do not match unless they ask about a person's decision.
    """

    normalized = " ".join(str(question or "").casefold().split())
    if domain == "medical" and any(re.search(pattern, normalized) for pattern in _PERSONAL_MEDICAL):
        return (
            "This learning workspace can explain the academic material and cite its "
            "sources, but it cannot diagnose, recommend treatment, or make a personal "
            "clinical decision. For an individual concern, consult a qualified clinician."
        )
    if domain == "finance" and any(re.search(pattern, normalized) for pattern in _PERSONAL_FINANCE):
        return (
            "This learning workspace can analyze the source material for education, but "
            "it cannot recommend a personal trade, investment, or portfolio decision. "
            "Consider a qualified financial professional for individual guidance."
        )
    return None
