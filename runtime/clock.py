"""Simulated time: hours since the scenario's day 0, mapped onto wall-clock dates."""

from __future__ import annotations

import math
from datetime import date, datetime, time, timedelta

HOURS_PER_DAY = 24.0


class SimClock:
    """`day0` is the wall-clock start of hour 0 (`RunMeta.day0`, e.g. "2021-09-01T20:00:00")."""

    def __init__(self, day0: datetime | date | str):
        if isinstance(day0, str):
            day0 = datetime.fromisoformat(day0)
        elif not isinstance(day0, datetime):
            day0 = datetime.combine(day0, time())
        self.day0 = day0.replace(tzinfo=None)

    def at(self, ts: float) -> datetime:
        return self.day0 + timedelta(hours=ts)

    def ts(self, when: datetime) -> float:
        return (when - self.day0).total_seconds() / 3600

    def end_of_day(self, day: date) -> float:
        """Due hour of a date-only deadline: the end of the simulated day holding `day`'s noon.

        With a midnight day 0 that is the end of `day`; with the storm's 20:00 day 0 it is 20:00 on
        `day`, which is how the scenario's ground truth dates "by Tuesday".
        """
        noon = self.ts(datetime.combine(day, time(12)))
        return (math.floor(noon / HOURS_PER_DAY) + 1) * HOURS_PER_DAY
