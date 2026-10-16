"""Follow-up questions built deterministically from a household's open promises.

This is what makes a call use weeks-old memory: "Her son Wei is coming Tuesday to help" becomes
"Did your son Wei make it on Tuesday?". Nothing here is household-specific or model-generated.
"""

from __future__ import annotations

import re

MAX_QUESTIONS = 3
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_SHORT_DAYS = {"mon": "monday", "tue": "tuesday", "tues": "tuesday", "wed": "wednesday", "thu": "thursday",
               "thur": "thursday", "thurs": "thursday", "fri": "friday", "sat": "saturday", "sun": "sunday"}
_WHEN = (r"(?P<when>(?i:" + "|".join(_DAYS) + "|" + "|".join(sorted(_SHORT_DAYS, key=len, reverse=True))
         + r"|tomorrow|this weekend))")
_RELATION = (r"(?:son|daughter|brother|sister|nephew|niece|grandson|granddaughter|grandchild|husband|wife|"
             r"partner|cousin|neighbou?r|friend|landlord|super|caseworker)")
# "her son Wei is coming Tuesday", "his daughter will come by Friday", "neighbor promised to visit"
_VISIT = re.compile(
    r"\b(?:her|his|their|my|your|a|the)?\s*(?P<who>" + _RELATION + r"(?-i:\s+[A-Z][a-z]+)?)\s+"
    r"(?:is|was|'s)?\s*(?:coming|going to come|will come|will visit|will stop by|promised to (?:come|visit)|"
    r"said (?:he|she|they) would come)\b(?:[^.;]*?\b" + _WHEN + r"\b)?",
    re.IGNORECASE)
# "Con Ed will restore power by Friday", "she will call FEMA tomorrow"
_COMMIT = re.compile(
    r"(?P<who>\b[A-Z][\w&.'-]*(?:\s+[A-Z][\w&.'-]*)*|\b(?:she|he|they))\s+"
    r"(?:will|promised to|agreed to|is going to|are going to|said (?:he|she|they|it) would)\s+"
    r"(?P<action>[a-z][\w' ]*?)(?:\s+(?:(?:by|on|before)\s+)?" + _WHEN + r")?\s*(?:[.,;]|$)")
_PRONOUN_TO_YOU = {"she": "you", "he": "you", "they": "you"}
# Mandarin question templates (fixed text, not model output).
_RELATION_ZH = {"son": "儿子", "daughter": "女儿", "brother": "兄弟", "sister": "姐妹", "nephew": "侄子",
                "niece": "侄女", "grandson": "孙子", "granddaughter": "孙女", "grandchild": "孙辈",
                "husband": "丈夫", "wife": "妻子", "partner": "伴侣", "cousin": "表亲", "neighbor": "邻居",
                "neighbour": "邻居", "friend": "朋友", "landlord": "房东", "super": "大楼管理员",
                "caseworker": "个案工作者"}
_DAY_ZH = {"monday": "星期一", "tuesday": "星期二", "wednesday": "星期三", "thursday": "星期四",
           "friday": "星期五", "saturday": "星期六", "sunday": "星期日", "this weekend": "这个周末"}


def _when_phrase(when: str | None, preposition: str) -> str:
    when = (when or "").lower()
    if not when or when == "tomorrow":
        return ""
    if when == "this weekend":
        return " this weekend"
    return f" {preposition} {_SHORT_DAYS.get(when, when).capitalize()}"


def _day(when: str | None) -> str:
    when = (when or "").lower()
    return _SHORT_DAYS.get(when, when)


def _question_zh(text: str) -> str:
    visit = _VISIT.search(text)
    if visit:
        relation, _, name = visit.group("who").partition(" ")
        who = _RELATION_ZH.get(relation.lower(), relation) + name
        return f"您的{who}{_DAY_ZH.get(_day(visit.group('when')), '')}来了吗？"
    return f"我们的记录显示：“{text.rstrip('.')}”。这件事办好了吗？"


def question_for(promise_text: str, language: str = "en") -> str:
    """One plain-language follow-up question for a promise, or a quoted fallback."""
    text = " ".join(promise_text.split())
    if language == "zh":
        return _question_zh(text)
    visit = _VISIT.search(text)
    if visit:
        who = visit.group("who")
        return f"Did your {who[0].lower()}{who[1:]} make it{_when_phrase(visit.group('when'), 'on')}?"
    commit = _COMMIT.search(text)
    if commit:
        who = _PRONOUN_TO_YOU.get(commit.group("who").lower(), commit.group("who"))
        return f"Did {who} {commit.group('action').strip()}{_when_phrase(commit.group('when'), 'by')}?"
    return f'Our notes say: "{text.rstrip(".")}." Did that happen?'


def build_questions(context: dict, language: str = "en") -> list[str]:
    """Questions for the oldest-due open promises first, at most MAX_QUESTIONS, no repeats."""
    promises = list(context.get("open_promises") or [])
    promises.sort(key=lambda item: item.get("due_ts", float("inf")) if isinstance(item, dict) else float("inf"))
    questions: list[str] = []
    for item in promises:
        text = item.get("text", "") if isinstance(item, dict) else str(item)
        question = question_for(text, language) if text.strip() else None
        if question and question not in questions:
            questions.append(question)
        if len(questions) == MAX_QUESTIONS:
            break
    return questions
