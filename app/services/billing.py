"""
Billing support: plain-language explanation + denial-risk flag for a
billing code + claim context, grounded via retrieval from the
`domain_knowledge` collection.

This is intentionally a heuristic, explainable MVP risk flag — not a
real payer-specific denial model — and is always framed as a suggestion
for staff to review, never an auto-submission of anything.
"""
from app.services.domain_knowledge import search_knowledge

# Very small set of heuristic risk signals a claim context might contain.
# Real-world denial prediction would need payer-specific rules; this MVP
# keeps the logic transparent and easy to extend.
_HIGH_RISK_SIGNALS = [
    "missing modifier",
    "no prior authorization",
    "no prior auth",
    "out of network",
    "duplicate claim",
    "missing documentation",
    "incorrect diagnosis pairing",
]
_MEDIUM_RISK_SIGNALS = [
    "new patient",
    "unusual frequency",
    "bundled service",
    "high dollar",
]


def assess_denial_risk(claim_context: str | None) -> tuple[str, list[str]]:
    context = (claim_context or "").lower()
    matched_high = [s for s in _HIGH_RISK_SIGNALS if s in context]
    if matched_high:
        return "high", matched_high

    matched_medium = [s for s in _MEDIUM_RISK_SIGNALS if s in context]
    if matched_medium:
        return "medium", matched_medium

    return "low", []


def explain_billing_code(billing_code: str, claim_context: str | None = None) -> dict:
    query = f"billing code {billing_code} {claim_context or ''}".strip()
    grounding = search_knowledge(query, category="billing", limit=3)

    if grounding:
        explanation = grounding[0]["text"]
        grounding_used = True
    else:
        explanation = (
            f"No specific reference material was found for code '{billing_code}'. "
            "This code could not be matched against known billing documentation; "
            "please verify it manually before submitting the claim."
        )
        grounding_used = False

    risk_level, risk_signals = assess_denial_risk(claim_context)

    return {
        "billing_code": billing_code,
        "explanation": explanation,
        "grounding_used": grounding_used,
        "sources": grounding,
        "denial_risk": risk_level,
        "denial_risk_signals": risk_signals,
        "disclaimer": (
            "This is an automated, non-binding suggestion based on limited heuristics "
            "and reference material. Staff must review and confirm before submitting any claim."
        ),
    }
