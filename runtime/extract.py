"""Deterministic regex extraction: the no-LLM fallback for free-text events.

Finds a household reference (honorific + surname and/or street address), promises that carry a
parseable deadline, and fulfilment statements. Anything it cannot parse is left out rather than
guessed; the OpenRouter path (`runtime.llm_paths`) is tried first when a model is configured.
Times are simulated hours since day 0, mapped to dates by a `SimClock`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

from runtime.clock import SimClock

MAX_PROMISE_TEXT = 300

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
_COUNTS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
_UNIT_HOURS = {"hour": 1.0, "day": 24.0, "week": 168.0}

_ABBREVIATION_DOT = re.compile(r"\b(Mrs|Mr|Ms|Mx|Dr|St|Ave|Rd|Blvd|Apt)\.")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?;])\s+|\n+")
_ADDRESS = re.compile(
    r"\b\d{1,5}(?:-\d{1,5})?[A-Z]?(?:\s+(?:[A-Z][a-z]*\.?|\d+(?:st|nd|rd|th))){1,4}?\s+"
    r"(?:St|Street|Ave|Avenue|Rd|Road|Blvd|Pl|Place|Ln|Lane|Dr|Drive|Ct|Court|Ter|Terrace|Way)\b"
)
_NAME = re.compile(r"\b(Mrs|Mr|Ms|Miss|Mx|Dr)\s+(?!(?:Mrs|Mr|Ms|Miss|Mx|Dr)\b)([A-Z][a-z]*(?:['-][A-Z][a-z]+)*)")

_PROMISE_CUE = re.compile(
    r"\b(?:promised|promises|agreed|agrees|committed|commits|pledged|vowed|will|(?:is|are) going to|coming|"
    r"scheduled|set for|arriving|picking|bringing|delivering|sending|dropping|said (?:he|she|they|it) would|"
    r"(?:he|she|they|we|i)'ll)\b", re.IGNORECASE)
_FULFILMENT_CUE = re.compile(
    r"\b(?:delivered|brought|dropped off|fixed|repaired|restored|reconnected|completed|done|arrived|came|"
    r"kept|received|picked (?:\w+ )?up|installed|returned|resolved|removed|corrected|called back)\b", re.IGNORECASE)
_NEGATION = re.compile(r"\b(?:not|never|no|still waiting|yet to)\b|n't\b", re.IGNORECASE)

_WITHIN = re.compile(r"\b(?:within|in)\s+(\d+|an?|one|two|three|four|five|six|seven)\s+(hour|day|week)s?\b",
                     re.IGNORECASE)
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_MONTH_DAY = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|"
    r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", re.IGNORECASE)
_WEEKDAY = re.compile(r"\b(?:(since|last|from)\s+)?(?:(?:by|on|before|until|this|next|coming)\s+)?("
                      + "|".join(_WEEKDAYS) + r")\b", re.IGNORECASE)
_TOMORROW = re.compile(r"\btomorrow\b", re.IGNORECASE)
_TODAY = re.compile(r"\b(?:today|tonight|this (?:morning|afternoon|evening))\b", re.IGNORECASE)

_CUE_WORDS = frozenset((
    "promise", "promised", "promises", "agreed", "agrees", "committed", "commits", "pledged", "vowed",
    "going", "coming", "scheduled", "arriving", "picking", "bringing", "delivering", "sending", "dropping",
    "delivered", "brought", "dropped", "fixed", "repaired", "restored", "reconnected", "completed", "done",
    "arrived", "came", "kept", "received", "picked", "installed", "returned", "resolved", "removed",
    "corrected", "called",
))
_STOPWORDS = frozenset((
    "about", "after", "again", "also", "back", "been", "before", "being", "does", "from", "have", "into",
    "just", "made", "miss", "more", "need", "note", "said", "says", "should", "some", "states", "still",
    "than", "that", "their", "them", "then", "there", "they", "this", "today", "told", "tomorrow", "tonight",
    "until", "visit", "visited", "week", "weeks", "what", "when", "which", "while", "will", "with", "within",
    "would", "your", "hour", "hours", "days", "morning", "afternoon", "evening", "january", "february",
    "march", "april", "june", "july", "august", "sept", "september", "october", "november", "december",
    *_WEEKDAYS,
))


@dataclass(frozen=True)
class PromiseDraft:
    text: str
    due_ts: float
    keywords: frozenset[str]


@dataclass(frozen=True)
class Extraction:
    household_ref: dict[str, str]  # {"name": "Mrs Chen", "address": "41 Orchard St"}, found keys only
    promises: tuple[PromiseDraft, ...]
    fulfilments: tuple[frozenset[str], ...]  # keywords of each fulfilment statement
    kept_promise_ids: tuple[str, ...] = ()  # open promises the model judged kept (LLM path only)


def has_cue(text: str) -> bool:
    """Whether the text talks about a commitment or a delivery at all (gates the LLM path)."""
    return bool(_PROMISE_CUE.search(text) or _FULFILMENT_CUE.search(text))


def extract(text: str, ts: float, clock: SimClock) -> Extraction:
    text = _ABBREVIATION_DOT.sub(r"\1", text)
    ref: dict[str, str] = {}
    if match := _ADDRESS.search(text):
        ref["address"] = " ".join(match[0].split())
    if match := _NAME.search(_ADDRESS.sub(" ", text)):
        ref["name"] = f"{match[1]} {match[2]}"
    exclude = frozenset(re.findall(r"[a-z]+", " ".join(ref.values()).lower()))

    promises: list[PromiseDraft] = []
    fulfilments: list[frozenset[str]] = []
    for sentence in _SENTENCE_BREAK.split(text):
        sentence = sentence.strip()
        if not sentence or sentence.endswith("?"):
            continue
        cue = _PROMISE_CUE.search(sentence)
        due = _deadline(sentence, ts, clock) if cue and not _negated(sentence, cue) else None
        if due is not None:
            promises.append(PromiseDraft(sentence[:MAX_PROMISE_TEXT], due, keywords(sentence, exclude)))
        elif (done := _FULFILMENT_CUE.search(sentence)) and not _negated(sentence, done):
            fulfilments.append(keywords(sentence, exclude))
    return Extraction(ref, tuple(promises), tuple(fulfilments))


def _negated(sentence: str, cue: re.Match) -> bool:
    """"won't", "not", "never" etc. right around the cue ("still hasn't fixed", "will not come")."""
    return bool(_NEGATION.search(sentence[max(0, cue.start() - 20): cue.end() + 8]))


def _deadline(sentence: str, ts: float, clock: SimClock) -> float | None:
    """Due hour of the first deadline phrase; a date-only deadline runs to the end of that day."""
    if match := _WITHIN.search(sentence):
        count = int(match[1]) if match[1].isdigit() else _COUNTS[match[1].lower()]
        return ts + count * _UNIT_HOURS[match[2].lower()]
    today = clock.at(ts).date()
    day: date | None = None
    if match := _ISO_DATE.search(sentence):
        day = _date(int(match[1]), int(match[2]), int(match[3]))
    elif match := _MONTH_DAY.search(sentence):
        month = _MONTHS.index(match[1][:3].lower()) + 1
        day = _date(today.year, month, int(match[2]))
        if day and (today - day).days > 180:  # "by Jan 5" written in December
            day = _date(today.year + 1, month, int(match[2]))
    elif weekday := _next_weekday(sentence, today):
        day = weekday
    elif _TOMORROW.search(sentence):
        day = today + timedelta(days=1)
    elif _TODAY.search(sentence):
        day = today
    return None if day is None else clock.end_of_day(day)


def _next_weekday(sentence: str, today: date) -> date | None:
    for match in _WEEKDAY.finditer(sentence):
        if not match[1]:  # "since Wednesday" looks back, not ahead
            return today + timedelta(days=(_WEEKDAYS.index(match[2].lower()) - today.weekday()) % 7 or 7)
    return None


def _date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


_DIRECTIONS = frozenset({"n", "s", "e", "w", "north", "south", "east", "west"})


def address_key(text: str | None) -> str | None:
    """House number plus street, tolerant of formats: "41-22 Hollow Oak Ln Bsmt" == "4122 HOLLOW OAK LN"."""
    tokens = re.findall(r"[A-Za-z0-9]+(?:-[0-9]+)?", text or "")
    if len(tokens) < 2 or not tokens[0][0].isdigit():
        return None
    street = [t.lower() for t in tokens[1:] if t.lower() not in _DIRECTIONS][:1]
    if not street:
        return None
    return tokens[0].replace("-", "") + "|" + re.sub(r"^(\d+)(st|nd|rd|th)$", r"\1", street[0])


def keywords(sentence: str, exclude: frozenset[str] = frozenset()) -> frozenset[str]:
    """Content words that tie a fulfilment to a promise; names, addresses and cue words excluded."""
    words = re.findall(r"[a-z]+", sentence.lower())
    return frozenset(_stem(word) for word in words
                     if len(word) >= 4 and word not in _STOPWORDS and word not in _CUE_WORDS
                     and word not in exclude)


def _stem(word: str) -> str:
    # "er" needs a longer stem, so "plumber" meets "plumbing" but "water" and "power" stay whole.
    for suffix, replacement, keep in (("ies", "y", 3), ("ing", "", 3), ("ed", "", 3), ("er", "", 4), ("es", "", 3),
                                      ("s", "", 3)):
        if word.endswith(suffix) and len(word) - len(suffix) >= keep:
            return word[: -len(suffix)] + replacement
    return word
