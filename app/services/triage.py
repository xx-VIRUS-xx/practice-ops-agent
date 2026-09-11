"""
Intake triage: a STRUCTURED (not free-text-only) intake form is converted
into a retrieval-grounded urgency/routing suggestion.

Hard requirement: this must never present itself as clinical advice or a
diagnosis. Every response carries an explicit, unavoidable disclaimer, and
the output vocabulary is deliberately routing-oriented ("suggest scheduling
within X", "suggest same-day/urgent-care referral") rather than diagnostic
language.
"""
from app.services.domain_knowledge import search_knowledge

DISCLAIMER = (
    "This tool provides non-clinical routing suggestions only. It does NOT diagnose, "
    "does NOT provide medical advice, and does NOT replace the judgment of a licensed "
    "clinician. If this may be a medical emergency, call your local emergency number "
    "immediately."
)

# Structured severity flags a front-desk / intake form can capture without
# requiring free-text symptom description (though a free-text `reason_for_visit`
# field is also accepted as supporting context for retrieval).
_EMERGENCY_FLAGS = {
    "chest_pain",
    "difficulty_breathing",
    "severe_bleeding",
    "loss_of_consciousness",
    "stroke_symptoms",
    "severe_allergic_reaction",
}
_URGENT_FLAGS = {
    "high_fever",
    "severe_pain",
    "persistent_vomiting",
    "injury_with_visible_deformity",
}


def suggest_routing(
    reason_for_visit: str,
    symptom_flags: list[str],
    duration_days: int | None = None,
    pain_level: int | None = None,
) -> dict:
    flags = {f.strip().lower() for f in symptom_flags}

    if flags & _EMERGENCY_FLAGS:
        urgency = "emergency"
        routing = "Advise the patient to seek emergency care immediately (call emergency services or go to the ER)."
    elif flags & _URGENT_FLAGS or (pain_level is not None and pain_level >= 8):
        urgency = "urgent"
        routing = "Suggest a same-day or next-day urgent appointment."
    elif duration_days is not None and duration_days >= 14:
        urgency = "routine_soon"
        routing = "Suggest scheduling within the next week; symptoms have persisted for an extended period."
    else:
        urgency = "routine"
        routing = "Suggest scheduling a routine appointment at the patient's convenience."

    query = f"{reason_for_visit} {' '.join(sorted(flags))}".strip()
    grounding = search_knowledge(query, category="triage", limit=3) if query else []

    return {
        "urgency": urgency,
        "routing_suggestion": routing,
        "matched_flags": sorted(flags),
        "sources": grounding,
        "disclaimer": DISCLAIMER,
        "not_medical_advice": True,
    }
