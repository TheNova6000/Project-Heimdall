"""
Simulation time-step driver.

Architecture.md: "A tick-based or event-based clock that advances the
world over simulated time" -- Phase 1 uses ticks, one tick = one
simulated day (Architecture.md's simulation loop pseudocode is written
per-day). No wall-clock time is ever read (Rules.md #6: determinism --
"no wall-clock time... anywhere in the core loop"); every timestamp is
derived purely from `start_date` + elapsed simulated days.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass


@dataclass
class SimClock:
    start_date: datetime.date
    day: int = 0  # ticks elapsed, 0-indexed

    @property
    def current_date(self) -> datetime.date:
        return self.start_date + datetime.timedelta(days=self.day)

    @property
    def day_of_month(self) -> int:
        return self.current_date.day

    def timestamp(self, hour: int = 12, minute: int = 0, second: int = 0) -> str:
        """
        ISO 8601 UTC timestamp for an event occurring on the current
        simulated day.

        MODELING ASSUMPTION: Phase 1's loop is per-day, not per-second
        (Architecture.md), so there is no real intraday clock to sample
        from. Callers pass an hour/minute/second (typically derived from
        the run's seeded RNG so distinct same-day events still get
        distinct, deterministic timestamps) rather than this method
        inventing time-of-day on its own -- this file makes no claim
        about *when during the day* things happen, only about which
        simulated day they happen on.
        """
        dt = datetime.datetime.combine(
            self.current_date,
            datetime.time(hour=hour, minute=minute, second=second),
            tzinfo=datetime.timezone.utc,
        )
        return dt.isoformat()

    def advance(self) -> None:
        self.day += 1
