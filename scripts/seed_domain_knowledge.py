"""
Seed the `domain_knowledge` Qdrant collection with generic, non-patient-
specific reference material: common billing code explanations, scheduling
policy templates, and generic triage routing guidance.

IMPORTANT: This data must never resemble real PHI. Everything here is
generic reference material a practice could find in public coding/billing
guides or general triage protocols — no real patient scenarios.

Run with: python -m scripts.seed_domain_knowledge
(requires Qdrant to be reachable at QDRANT_URL)
"""
from app.services.domain_knowledge import stable_id, upsert_knowledge
from app.services.qdrant_client import ensure_collections

BILLING_DOCS = [
    (
        "cpt-99213",
        "CPT 99213: Established patient office visit, low-to-moderate complexity, "
        "typically 20-29 minutes of total time. Commonly denied when documentation "
        "does not support the time or complexity billed, or when billed for a new "
        "patient (should be 992x2 series for new patients). Ensure documentation "
        "supports medical necessity and time spent.",
    ),
    (
        "cpt-99214",
        "CPT 99214: Established patient office visit, moderate complexity, typically "
        "30-39 minutes. Frequently flagged by payers for overuse; ensure chart notes "
        "justify the complexity level (e.g. multiple chronic conditions managed, "
        "moderate risk decision making).",
    ),
    (
        "cdt-d0120",
        "CDT D0120: Periodic oral evaluation for an established dental patient. "
        "Usually covered at 100% under preventive care but may be denied if billed "
        "more than twice in a 12-month period for the same patient without "
        "documented medical necessity.",
    ),
    (
        "modifier-25",
        "Modifier 25: Indicates a significant, separately identifiable evaluation "
        "and management service by the same provider on the day of a procedure. "
        "Missing this modifier when billing an E/M code alongside a minor procedure "
        "is one of the most common causes of claim denial.",
    ),
    (
        "prior-authorization-general",
        "Many payers require prior authorization for advanced imaging, certain "
        "specialist referrals, and non-emergency procedures above a cost threshold. "
        "Claims submitted without a required prior authorization on file are "
        "commonly denied outright regardless of medical necessity.",
    ),
    (
        "out-of-network-general",
        "Claims for out-of-network providers are frequently denied or reimbursed "
        "at a significantly reduced rate unless the plan offers out-of-network "
        "benefits or an in-network exception was pre-approved.",
    ),
]

SCHEDULING_DOCS = [
    (
        "policy-new-patient-slot-length",
        "Scheduling policy: new patient appointments should generally be allotted "
        "45-60 minutes to allow time for intake paperwork, history review, and "
        "the visit itself, roughly double a standard follow-up slot.",
    ),
    (
        "policy-double-booking",
        "Scheduling policy: double-booking a provider should only be done for "
        "very short, well-defined visits (e.g. a quick recheck) and requires "
        "explicit staff approval — it should never be suggested automatically.",
    ),
    (
        "policy-reminder-window",
        "Scheduling policy: appointment reminders are typically sent 48 hours and "
        "again 3 hours before the scheduled time to reduce no-show rates.",
    ),
    (
        "policy-cancellation-window",
        "Scheduling policy: patients are generally asked to cancel or reschedule "
        "at least 24 hours in advance to avoid a late-cancellation fee, per common "
        "practice policy templates.",
    ),
]

TRIAGE_DOCS = [
    (
        "triage-general-routing",
        "General non-clinical routing guidance: visits involving reported chest "
        "pain, difficulty breathing, severe bleeding, loss of consciousness, "
        "stroke-like symptoms, or severe allergic reaction should be routed to "
        "seek emergency care immediately rather than scheduled as a routine visit.",
    ),
    (
        "triage-urgent-routing",
        "General non-clinical routing guidance: high fever, severe pain, "
        "persistent vomiting, or an injury with visible deformity are commonly "
        "routed to a same-day or next-day urgent appointment slot rather than "
        "routine scheduling.",
    ),
    (
        "triage-routine-routing",
        "General non-clinical routing guidance: mild, non-urgent, short-duration "
        "concerns are typically routed to routine scheduling at the patient's "
        "convenience; concerns persisting two weeks or longer are often routed to "
        "be seen sooner rather than left on a fully routine timeline.",
    ),
    (
        "triage-not-medical-advice",
        "Any structured intake routing tool must clearly disclose that it does "
        "not diagnose and does not replace clinical judgment; ambiguous or "
        "concerning combinations of symptoms should default to a more urgent "
        "routing suggestion rather than a less urgent one.",
    ),
]


def main() -> None:
    ensure_collections()

    for doc_id, text in BILLING_DOCS:
        upsert_knowledge(stable_id(doc_id), text, category="billing")
    for doc_id, text in SCHEDULING_DOCS:
        upsert_knowledge(stable_id(doc_id), text, category="scheduling")
    for doc_id, text in TRIAGE_DOCS:
        upsert_knowledge(stable_id(doc_id), text, category="triage")

    total = len(BILLING_DOCS) + len(SCHEDULING_DOCS) + len(TRIAGE_DOCS)
    print(f"Seeded {total} domain-knowledge documents.")


if __name__ == "__main__":
    main()
