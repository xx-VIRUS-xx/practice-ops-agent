"""
Scheduling domain logic: conflict detection and available-slot suggestion.

Conflict rule: two appointments for the SAME provider, in the SAME practice,
conflict if their [start_time, end_time) intervals overlap. Appointments
for different providers never conflict with each other in this MVP (no
shared-resource/room modeling).

`status == cancelled` appointments never participate in conflict checks.
"""
import datetime

from sqlalchemy.orm import Session

from app.models.orm import Appointment, AppointmentStatus


def _as_utc(value: datetime.datetime) -> datetime.datetime:
    """
    Normalize to an aware UTC datetime.

    SQLite (used for tests / lightweight local dev) does not preserve
    timezone info on round-trip, so datetimes read back from it are naive.
    Postgres (production) does preserve it. We treat any naive datetime as
    already being UTC so comparisons are always apples-to-apples regardless
    of backend.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=datetime.timezone.utc)
    return value.astimezone(datetime.timezone.utc)


def intervals_overlap(
    start_a: datetime.datetime, end_a: datetime.datetime, start_b: datetime.datetime, end_b: datetime.datetime
) -> bool:
    start_a, end_a, start_b, end_b = (_as_utc(v) for v in (start_a, end_a, start_b, end_b))
    return start_a < end_b and start_b < end_a


def find_conflicts(
    db: Session,
    practice_id: str,
    provider_name: str,
    start_time: datetime.datetime,
    end_time: datetime.datetime,
    exclude_appointment_id: str | None = None,
) -> list[Appointment]:
    if end_time <= start_time:
        raise ValueError("end_time must be after start_time")

    query = db.query(Appointment).filter(
        Appointment.practice_id == practice_id,
        Appointment.provider_name == provider_name,
        Appointment.status != AppointmentStatus.cancelled,
    )
    if exclude_appointment_id:
        query = query.filter(Appointment.id != exclude_appointment_id)

    candidates = query.all()
    return [
        appt
        for appt in candidates
        if intervals_overlap(start_time, end_time, appt.start_time, appt.end_time)
    ]


def suggest_available_slots(
    db: Session,
    practice_id: str,
    provider_name: str,
    day_start: datetime.datetime,
    day_end: datetime.datetime,
    slot_minutes: int = 30,
) -> list[dict]:
    """
    Suggest open slots of `slot_minutes` length for a provider within
    [day_start, day_end), by walking the window and skipping any slot that
    conflicts with an existing (non-cancelled) appointment.
    """
    if day_end <= day_start:
        raise ValueError("day_end must be after day_start")

    existing = (
        db.query(Appointment)
        .filter(
            Appointment.practice_id == practice_id,
            Appointment.provider_name == provider_name,
            Appointment.status != AppointmentStatus.cancelled,
            Appointment.start_time < day_end,
            Appointment.end_time > day_start,
        )
        .all()
    )

    slots = []
    cursor = day_start
    delta = datetime.timedelta(minutes=slot_minutes)
    while cursor + delta <= day_end:
        slot_end = cursor + delta
        conflict = any(intervals_overlap(cursor, slot_end, e.start_time, e.end_time) for e in existing)
        if not conflict:
            slots.append({"start_time": cursor, "end_time": slot_end})
        cursor = slot_end

    return slots
