import pytest

from calls.safety import DISCLOSURE_TEMPLATES, EMERGENCY_LINES, disclosure, safety_check


@pytest.mark.parametrize("utterance", [
    "I fell",
    "I fell in the kitchen and I can't get up.",
    "i can’t breathe",
    "My chest hurts",
    "I smell gas in the basement",
    "There's a fire!",
    "Me caí en el baño",
    "No puedo respirar",
    "我摔倒了",
])
def test_emergency_phrases_are_detected(utterance):
    assert safety_check(utterance, "en")["emergency"]


@pytest.mark.parametrize("utterance", [
    "My son never came on Tuesday.",
    "The power is still out.",
    "I fell asleep early last night.",
    "The firefighters pumped out the basement.",
    "I didn't fall, I'm fine.",
])
def test_ordinary_answers_are_not_emergencies(utterance):
    assert not safety_check(utterance, "en")["emergency"]


def test_every_language_is_checked_regardless_of_call_language():
    assert safety_check("I fell", "es")["emergency"]
    assert safety_check("me caí", "en")["emergency"]


def test_disclosure_is_fixed_text_with_callback_number():
    assert disclosure("en", "+1 212-555-0100") == (
        "This is an automated call from Relay for the recovery team. "
        "To confirm this call is real, call us back at +1 212-555-0100."
    )
    assert disclosure("xx", "+1 212-555-0100") == disclosure("en", "+1 212-555-0100")


def test_fixed_lines_cannot_be_rewritten_at_runtime():
    with pytest.raises(TypeError):
        DISCLOSURE_TEMPLATES["en"] = "Hi, it's your friend!"
    with pytest.raises(TypeError):
        EMERGENCY_LINES["en"] = "Try resting for a bit."


@pytest.mark.parametrize("number", ["", "[number]", "call me"])
def test_disclosure_requires_a_real_callback_number(number):
    with pytest.raises(ValueError):
        disclosure("en", number)
