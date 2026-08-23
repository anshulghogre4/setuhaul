"""The one injectable clock (SOLUTION_DESIGN.md section 9.1, "Deterministic clock").

Why this exists at all: section 9.1 says *"Every test must inject `now` rather than read the wall
clock, or the entire suite starts failing the day after it is written -- and the failures will look
like scheduling bugs. One injected clock, threaded through the engine, the TTL sweepers and the
sequencer."* It is the prerequisite section 9.2 #3 (`pending_expiry_vs_planner_confirm`) needs to be
reproducible on demand rather than by timing luck, and the prerequisite
`feasibility.py::check_facility_rules` names in its own docstring for the NO_SHOW_GRACE_MIN rule it
currently cannot enforce.

It lives in `app.core` rather than `app.scheduling` deliberately: the sweeper, the engine and the
(not yet built) sequencer are three different packages, and section 9.1 asks for *one* clock across
all three. Putting it under the package that happened to need it first would guarantee a move later.

**How it is threaded.** By explicit keyword argument, never by a module-level mutable global. A
global would be shared across concurrently running requests in the same process, so one test
freezing time would silently move every other in-flight caller's clock -- the opposite of the
determinism this is for.

**What deliberately does not accept a clock: the HTTP boundary.** The internal sweeper endpoint takes
no caller-supplied `now`. A client-supplied instant deciding which appointments expire is the same
hazard class as M15's client-supplied scope id, and expiry releases real capacity. Tests that need to
force the race call `sweep_expired_appointments(...)` directly with a `FrozenClock`, which is why
that function takes the clock as an argument rather than reading one from settings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Anything that can answer "what time is it now, in UTC"."""

    def now(self) -> datetime:  # pragma: no cover - protocol declaration
        ...


class SystemClock:
    """Production clock: the real wall clock, always timezone-aware UTC.

    Returns UTC rather than local time because every timestamp column this project compares
    against is `timestamptz` after the E1.1 conversion, and a naive datetime compared against a
    `timestamptz` is the exact defect class section 9.1 is warning about.
    """

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True)
class FrozenClock:
    """Test clock pinned to one instant.

    Rejects a naive `instant` on construction rather than quietly normalising it: a test that
    forgets the tzinfo would otherwise pass while comparing a naive value against `timestamptz`
    columns, which is precisely the failure that "looks like a scheduling bug".
    """

    instant: datetime

    def __post_init__(self) -> None:
        if self.instant.tzinfo is None or self.instant.tzinfo.utcoffset(self.instant) is None:
            raise ValueError(
                "FrozenClock requires a timezone-aware instant; a naive datetime compared "
                "against a timestamptz column is the defect SOLUTION_DESIGN.md section 9.1 "
                "exists to prevent."
            )

    def now(self) -> datetime:
        return self.instant.astimezone(timezone.utc)

    def shifted(self, delta: timedelta) -> FrozenClock:
        """A new clock `delta` later. Used to step a test across a TTL boundary."""
        return FrozenClock(self.instant + delta)


SYSTEM_CLOCK = SystemClock()


def resolve_clock(clock: Clock | None) -> Clock:
    """Default any optional clock argument to the real one, in a single place."""
    return clock if clock is not None else SYSTEM_CLOCK
