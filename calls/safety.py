"""Hard-coded call safety: the fixed disclosure and the emergency phrase detector.

Nothing here calls a model. The call agent runs `safety_check` on every resident
utterance before any LLM sees it.
"""

from __future__ import annotations

import re
import unicodedata
from types import MappingProxyType

from schemas import SafetyVerdict

DEFAULT_LANGUAGE = "en"

# Fixed text, read-only at runtime. The model never generates or edits these lines.
# Non-English lines are fixed translations, reviewed like code; they are never produced by a model.
DISCLOSURE_TEMPLATES = MappingProxyType({
    "en": (
        "This is an automated call from Relay for the recovery team. "
        "To confirm this call is real, call us back at {callback_number}."
    ),
    "zh": "这是Relay代表灾后恢复团队打来的自动电话。如需确认这通电话的真实性，请回拨{callback_number}。",
})

EMERGENCY_LINES = MappingProxyType({
    "en": "Please hang up and call 911 now. I'm alerting a person on the recovery team.",
    "zh": "请立即挂断电话，拨打911。我正在通知恢复团队的工作人员。",
})

# Every language's list is checked on every utterance: residents switch languages
# mid-call, and a false alarm is cheaper than a missed emergency.
EMERGENCY_PHRASES = MappingProxyType({
    "en": (
        "i fell", "i've fallen", "i have fallen", "fell down", "can't get up", "cant get up",
        "cannot get up", "can't breathe", "cant breathe", "cannot breathe", "can not breathe",
        "trouble breathing", "hard to breathe", "not breathing", "chest pain", "my chest hurts",
        "heart attack", "stroke", "unconscious", "passed out", "bleeding", "smell gas",
        "gas leak", "fire", "call 911", "ambulance", "emergency", "kill myself",
        "want to die", "overdose",
    ),
    "es": (
        "me caí", "me cai", "no puedo respirar", "dolor de pecho", "dolor en el pecho",
        "ataque al corazón", "ataque al corazon", "derrame", "inconsciente", "sangrando",
        "huele a gas", "fuego", "incendio", "llame al 911", "ambulancia", "emergencia",
    ),
    "zh": (
        "摔倒", "跌倒", "喘不过气", "不能呼吸", "胸口痛", "胸痛", "心脏病", "中风", "昏迷",
        "流血", "煤气", "着火", "救命", "急救",
    ),
})

# Everyday phrases that contain a trigger but are not emergencies.
NOT_EMERGENCIES = ("i fell asleep", "i fell behind")

_CALLBACK_NUMBER = re.compile(r"^\+?[0-9][0-9 ().-]{6,}$")
_CJK = re.compile(r"[぀-ヿ㐀-鿿]")


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().replace("’", "'")
    return " " + " ".join(re.sub(r"[^\w']+", " ", text).split()) + " "


def safety_check(utterance: str, language: str = DEFAULT_LANGUAGE) -> SafetyVerdict:
    """Phrase-list emergency check. Runs before the LLM on every resident utterance.

    `language` is accepted for the shared interface; every language's list is checked anyway.
    On a hit, `reason` is the matched phrase.
    """
    text = _normalize(utterance)
    for phrase in NOT_EMERGENCIES:
        text = text.replace(f" {phrase} ", " ")
    for phrases in EMERGENCY_PHRASES.values():
        for phrase in phrases:
            # CJK has no word spaces, so match those as substrings; everything else on word boundaries.
            if (phrase in text) if _CJK.search(phrase) else (f" {phrase} " in text):
                return SafetyVerdict(emergency=True, reason=phrase)
    return SafetyVerdict(emergency=False)


def disclosure(language: str, callback_number: str) -> str:
    """The fixed opening line. Falls back to English, never to generated text."""
    if not _CALLBACK_NUMBER.match(callback_number or ""):
        raise ValueError("callback_number must be a real phone number")
    template = DISCLOSURE_TEMPLATES.get(language, DISCLOSURE_TEMPLATES[DEFAULT_LANGUAGE])
    return template.format(callback_number=callback_number)


def emergency_line(language: str) -> str:
    return EMERGENCY_LINES.get(language, EMERGENCY_LINES[DEFAULT_LANGUAGE])
