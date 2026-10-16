from datetime import date

from runtime.clock import SimClock
from runtime.extract import extract

DAY0 = date(2026, 9, 28)  # a Monday; simulated hour 0 is its midnight
MONDAY_11 = 11.0
CLOCK = SimClock(DAY0)


def end_of(day: date) -> float:
    return ((day - DAY0).days + 1) * 24.0


def due(text: str) -> float | None:
    promises = extract(text, MONDAY_11, CLOCK).promises
    return promises[0].due_ts if promises else None


def test_household_reference_and_promise():
    found = extract("Visit note: Mrs. Chen at 41 Orchard St. Her landlord promised to fix the boiler by "
                    "Thursday.", MONDAY_11, CLOCK)
    assert found.household_ref == {"address": "41 Orchard St", "name": "Mrs Chen"}
    [promise] = found.promises
    assert promise.due_ts == end_of(date(2026, 10, 1)) == 96.0
    assert promise.keywords == {"landlord", "boil"}  # stemmed; name, address, cue and calendar words dropped


def test_deadline_phrases():
    assert due("Her son will bring groceries by 2026-10-05.") == end_of(date(2026, 10, 5))
    assert due("Con Ed said power will be restored by Oct 3rd.") == end_of(date(2026, 10, 3))
    assert due("The super promised to call back within 2 days.") == MONDAY_11 + 48
    assert due("Her daughter will visit tomorrow.") == end_of(date(2026, 9, 29))
    assert due("The landlord promised to come by Monday.") == end_of(date(2026, 10, 5))  # next Monday


def test_non_promises_are_not_guessed():
    assert due("Her son will visit soon.") is None  # no deadline
    assert due("The landlord will not fix the boiler by Friday.") is None  # negated
    assert due("Will the landlord fix the boiler by Friday?") is None  # a question


def test_fulfilment_statements():
    assert extract("The boiler was finally repaired.", MONDAY_11, CLOCK).fulfilments == (
        frozenset({"boil", "finally"}),)
    assert extract("The landlord still hasn't repaired the boiler.", MONDAY_11, CLOCK).fulfilments == ()
