from db.fakes import FakeDatabase
from memory.lessons import LessonStore


def lesson(lesson_id, text="Check in a day before a landlord's deadline"):
    """A schemas.Lesson."""
    return {"lesson_id": lesson_id, "text": text, "metric_values": {"promises_on_time_pct": 0.4}, "approved": False}


def test_a_lesson_is_added_once_and_approval_only_moves_forward():
    lessons = LessonStore(FakeDatabase())
    assert lessons.add(lesson("l-1"), run_id="relay-1", scenario_id="s1", ts=30.0)
    assert lessons.approve("l-1")
    assert not lessons.add(lesson("l-1", text="rewritten"), run_id="relay-1", scenario_id="s1", ts=30.0)  # replay
    assert not lessons.approve("l-1") and not lessons.approve("l-missing")
    [kept] = lessons.visible("relay-1", "s1", as_of_ts=100.0)
    assert kept["approved"] and kept["text"] == lesson("l-1")["text"]


def test_a_run_only_sees_lessons_it_could_have_had_by_then():
    lessons = LessonStore(FakeDatabase())
    learned = [("own-early", "relay-2", "s1", 10.0), ("own-later", "relay-2", "s1", 90.0),
               ("same-scenario-other-run", "relay-1", "s1", 5.0), ("other-scenario", "relay-0", "s0", 500.0),
               ("never-approved", "relay-0", "s0", 1.0)]
    for lesson_id, run_id, scenario_id, ts in learned:
        lessons.add(lesson(lesson_id), run_id=run_id, scenario_id=scenario_id, ts=ts)
        if lesson_id != "never-approved":
            lessons.approve(lesson_id)
    visible = [item["lesson_id"] for item in lessons.visible("relay-2", "s1", as_of_ts=50.0)]
    assert visible == ["own-early", "other-scenario"]
