import pytest

from app.models.orm import Appointment, AppointmentStatus
from app.services.scheduling import find_conflicts, intervals_overlap, suggest_available_slots
from tests.conftest import dt


def _make_appt(db_session, practice_id, provider, start, end, status=AppointmentStatus.confirmed):
    appt = Appointment(
        practice_id=practice_id,
        provider_name=provider,
        start_time=start,
        end_time=end,
        status=status,
    )
    db_session.add(appt)
    db_session.commit()
    db_session.refresh(appt)
    return appt


def test_intervals_overlap_true_for_overlapping_ranges():
    assert intervals_overlap(dt(9), dt(10), dt(9, 30), dt(10, 30)) is True


def test_intervals_overlap_false_for_adjacent_ranges():
    # back-to-back appointments (end == start) should NOT count as a conflict
    assert intervals_overlap(dt(9), dt(10), dt(10), dt(11)) is False


def test_intervals_overlap_false_for_disjoint_ranges():
    assert intervals_overlap(dt(9), dt(10), dt(11), dt(12)) is False


def test_find_conflicts_detects_overlap_same_provider(db_session, practice):
    _make_appt(db_session, practice.id, "Dr. Smith", dt(9), dt(10))

    conflicts = find_conflicts(db_session, practice.id, "Dr. Smith", dt(9, 30), dt(10, 30))

    assert len(conflicts) == 1


def test_find_conflicts_ignores_different_provider(db_session, practice):
    _make_appt(db_session, practice.id, "Dr. Smith", dt(9), dt(10))

    conflicts = find_conflicts(db_session, practice.id, "Dr. Jones", dt(9), dt(10))

    assert conflicts == []


def test_find_conflicts_ignores_cancelled_appointments(db_session, practice):
    _make_appt(db_session, practice.id, "Dr. Smith", dt(9), dt(10), status=AppointmentStatus.cancelled)

    conflicts = find_conflicts(db_session, practice.id, "Dr. Smith", dt(9), dt(10))

    assert conflicts == []


def test_find_conflicts_ignores_different_practice(db_session, practice):
    _make_appt(db_session, practice.id, "Dr. Smith", dt(9), dt(10))

    conflicts = find_conflicts(db_session, "some-other-practice-id", "Dr. Smith", dt(9), dt(10))

    assert conflicts == []


def test_find_conflicts_excludes_given_appointment_id(db_session, practice):
    appt = _make_appt(db_session, practice.id, "Dr. Smith", dt(9), dt(10))

    # Checking the same appointment against itself (e.g. during an update)
    # should not report a self-conflict when excluded.
    conflicts = find_conflicts(
        db_session, practice.id, "Dr. Smith", dt(9), dt(10), exclude_appointment_id=appt.id
    )

    assert conflicts == []


def test_find_conflicts_raises_for_invalid_range(db_session, practice):
    with pytest.raises(ValueError):
        find_conflicts(db_session, practice.id, "Dr. Smith", dt(10), dt(9))


def test_suggest_available_slots_skips_booked_slot(db_session, practice):
    _make_appt(db_session, practice.id, "Dr. Smith", dt(9), dt(9, 30))

    slots = suggest_available_slots(db_session, practice.id, "Dr. Smith", dt(9), dt(10), slot_minutes=30)

    starts = [s["start_time"] for s in slots]
    assert dt(9) not in starts
    assert dt(9, 30) in starts


def test_suggest_available_slots_full_day_no_bookings(db_session, practice):
    slots = suggest_available_slots(db_session, practice.id, "Dr. Smith", dt(9), dt(11), slot_minutes=30)

    assert len(slots) == 4


def test_suggest_available_slots_raises_for_invalid_window(db_session, practice):
    with pytest.raises(ValueError):
        suggest_available_slots(db_session, practice.id, "Dr. Smith", dt(11), dt(9))
