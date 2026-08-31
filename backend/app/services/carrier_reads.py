"""Read-only carrier-portal payloads (`E3.3`, issue #27, `SOLUTION_DESIGN.md` §7.5.6).

The five functions here are §7.5.6's whole catalog. That catalog has **no mutating tool by
design** ("the persona table lists no write job for this role, and none should be invented"), so
this module contains no write path, no `session.commit()`, and no idempotency handling -- there is
nothing here for an idempotency key to protect. If a write ever belongs on this surface, it is a
design change to §7.5.6 first, not a new function here.

Layering follows `operations_reads.py` (post-E2.2), not the older inline-SQL shape of
`driver_reads.py`: router -> this service (resolve scope, assemble payload) -> `repositories.carrier`
(SQL). Scope resolves exactly once per call, through `repositories.scope.resolve_carrier_scope`,
which takes no client input at all -- §7.5.6 requires every tool here to be "scope-derived from the
caller's own `carrier_id` (M15), never accepted as an argument", so none of these functions has a
`carrier_id` parameter to be passed one.

**No comparative framing, anywhere** (`U28`; `UI-UX/00-foundations/auth-and-scoping.md`, "The
inference risk, stated plainly"). No response assembled here contains a rank, a benchmark, a peer
average, a facility-wide total, or any count over rows this carrier does not own. The only
comparison any of it makes is this carrier's own 30-day window against its own prior 30-day window
(`UI-UX/05-carrier-portal/components.md` §1) -- own-vs-own across time, which leaks nothing about
anyone else.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext
from app.repositories import carrier as carrier_repo
from app.repositories.scope import assert_shipment_in_carrier_fleet, resolve_carrier_scope
from app.scheduling import holds

# `list_fleet_shipments(status_filter?)`'s accepted values, split by why they are or are not here.
#
# `UI-UX/05-carrier-portal/flows-and-states.md` Flow 2 names four promise states plus "has open
# exception". Two of those four -- SHOWN and HELD -- are not `appointments.appointment_status`
# values and never will be: that check constraint allows PENDING_CONFIRMATION/CONFIRMED/
# IN_PROGRESS/COMPLETED/CANCELLED/NO_SHOW/REJECTED/EXPIRED and nothing else (verified against the
# live constraint 2026-08-23), and #53's migration deliberately declines to add 'HELD' to it
# because §4 is explicit that *"Held is not booked: no `appointments` row exists yet"*.
#
# Issue #87 separated the two, because they were never the same problem:
#
#   * **HELD is answerable** once the D2 hold path is on. A hold is a `dock_occupancy` row, #85
#     taught both fleet reads to derive it, and the filter now runs on that derived
#     `promise_state` rather than on the raw column -- which is the only place HELD can be
#     expressed. With the flag off it is still refused, because no hold can exist and the
#     underlying columns may not even be readable.
#   * **SHOWN is not answerable, at all, in any flag state.** It is a UI-only concept: §0.8/§4
#     define it as what `find_feasible_slots` returned to a caller, and that call reserves nothing
#     and writes no row anywhere in the product. There is no table to select from, so it stays
#     refused rather than being given an invented mapping.
#
# Both refusals are 400s with a stated reason rather than a silently empty list -- an empty result
# would tell a carrier "you have no held shipments", which is not what the system actually knows.
_APPOINTMENT_STATUS_FILTERS = frozenset(
    {"PENDING_CONFIRMATION", "CONFIRMED", "IN_PROGRESS", "COMPLETED", "CANCELLED", "REJECTED", "EXPIRED", "NO_SHOW"}
)
_EXCEPTION_FILTER = "HAS_OPEN_EXCEPTION"
_HOLD_FILTER = holds.HOLD_PROMISE_STATE  # "HELD" -- the same constant the reads project.
_SHOWN_FILTER = "SHOWN"
_SHOWN_UNSUPPORTED_REASON = (
    "SHOWN is a presentation-only promise state with no persisted counterpart anywhere in the "
    "product: it is what find_feasible_slots returned to one caller, and that read reserves "
    "nothing and writes no row (SOLUTION_DESIGN.md §0.8, §4). There is nothing to select on, so "
    "this filter is refused rather than answered with a misleading empty list."
)
_HOLD_FILTER_DISABLED_REASON = (
    "HELD is only answerable while the D2 two-phase hold path is enabled. A hold is a "
    "dock_occupancy row rather than an appointment status (SOLUTION_DESIGN.md §4: 'Held is not "
    "booked: no appointments row exists yet'), and with TWO_PHASE_HOLD_ENABLED off no hold can "
    "exist and the hold columns may not be readable at all. Refused rather than answered with an "
    "empty list that would read as 'you have none'."
)

# §7.5.6 gives `get_carrier_on_time_performance` a `window` argument with a `30d` default, and
# `UI-UX/05-carrier-portal/screens.md`'s checklist section fixes the window at 30 days by decision
# ("a picker would imply a flexibility this surface deliberately doesn't offer"). `30d` is
# therefore the only value the design names, and the only one accepted -- widening this is one
# entry in this dict, but it is a design decision rather than an implementation detail.
_SUPPORTED_WINDOWS: dict[str, int] = {"30d": 30}
_DEFAULT_WINDOW = "30d"

_NON_COMPARATIVE_NOTE = (
    "Own-carrier data only. No cross-carrier comparison, benchmark, rank or shared-facility total "
    "is computed or returned (U28)."
)


def _as_of() -> str:
    return datetime.now(timezone.utc).isoformat()


def _scope_block(carrier_id: str) -> dict[str, Any]:
    return {"carrier_id": carrier_id, "read_only": True}


def _percent(on_time: int, arrivals: int) -> float | None:
    """`None`, never `0.0`, when there is nothing to measure.

    A carrier with no arrivals in the window has an unknown on-time rate, not a 0% one, and the
    difference matters: `0.0` would render as a catastrophic tile and a sparkline trough for a
    carrier that simply had a quiet fortnight.
    """
    if arrivals <= 0:
        return None
    return round(on_time * 100.0 / arrivals, 1)


def _windows(window: str) -> tuple[datetime, datetime, datetime]:
    """(`prior_start`, `start`, `end`) for a validated window key.

    The two windows abut exactly at `start`, so no arrival is counted in both or dropped between
    them -- the delta in `get_fleet_overview` is only meaningful if the periods partition cleanly.
    """
    days = _SUPPORTED_WINDOWS[window]
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    return start - timedelta(days=days), start, end


def _validate_window(window: str | None) -> str:
    resolved = (window or _DEFAULT_WINDOW).strip()
    if resolved not in _SUPPORTED_WINDOWS:
        raise AppError(
            f"Unsupported window '{resolved}'.",
            code="WINDOW_UNSUPPORTED",
            status_code=400,
            detail=f"Supported windows: {', '.join(sorted(_SUPPORTED_WINDOWS))}.",
        )
    return resolved


def _supported_filters(holds_enabled: bool) -> frozenset[str]:
    """The filter vocabulary this call can honestly answer, for the "unknown filter" message.

    Flag-dependent on purpose: telling a carrier that HELD is simply unknown while the D2 path is
    off would be a different (and wrong) statement from telling them it is currently unanswerable.
    Those are two distinct refusals below and the enumeration has to agree with them.
    """
    supported = _APPOINTMENT_STATUS_FILTERS | {_EXCEPTION_FILTER}
    return frozenset(supported | {_HOLD_FILTER}) if holds_enabled else frozenset(supported)


def _validate_status_filter(
    status_filter: str | None, *, holds_enabled: bool
) -> tuple[str | None, bool]:
    """Return (`promise_state`, `only_with_open_exception`) for a validated filter.

    Filtering is membership-only (Flow 2: "never re-fetches the on-time/exception-count tiles"),
    which is why this returns query inputs rather than anything the overview call also consumes.

    The first element is a **promise state**, not an appointment status (issue #87). For the eight
    `appointment_status` values the two coincide; `HELD` is the one that does not, and the
    repository is what resolves the difference -- with holds on it filters the derived
    `promise_state`, with holds off it filters the raw column exactly as it always has.
    """
    if not status_filter:
        return None, False
    value = status_filter.strip().upper()
    if value == _EXCEPTION_FILTER:
        return None, True
    if value == _SHOWN_FILTER:
        raise AppError(
            f"Filter '{value}' is not supported against the live schema.",
            code="FILTER_UNSUPPORTED",
            status_code=400,
            detail=_SHOWN_UNSUPPORTED_REASON,
        )
    if value == _HOLD_FILTER and not holds_enabled:
        raise AppError(
            f"Filter '{value}' is not available right now.",
            code="FILTER_UNSUPPORTED",
            status_code=400,
            detail=_HOLD_FILTER_DISABLED_REASON,
        )
    if value not in _supported_filters(holds_enabled):
        raise AppError(
            f"Unknown status filter '{value}'.",
            code="FILTER_UNSUPPORTED",
            status_code=400,
            detail=f"Supported filters: {', '.join(sorted(_supported_filters(holds_enabled)))}.",
        )
    return value, False


async def get_fleet_overview(session: AsyncSession, ctx: ExecutionContext) -> dict[str, Any]:
    """§7.5.6 `get_fleet_overview` -- arguments: none, carrier derived from identity.

    Returns the portal's summary strip: active shipment count, open exception count, and the
    current on-time figure with its prior-period delta (`components.md` §1 -- the on-time tile is
    the only one with a delta, because the two counts are point-in-time facts with no trend).
    """
    carrier_id = resolve_carrier_scope(ctx)
    prior_start, start, end = _windows(_DEFAULT_WINDOW)

    active = await carrier_repo.count_active_shipments(session, carrier_id)
    open_exceptions = await carrier_repo.count_open_exceptions(session, carrier_id)
    current = await carrier_repo.get_on_time_totals(
        session, carrier_id, window_start=start, window_end=end
    )
    previous = await carrier_repo.get_on_time_totals(
        session, carrier_id, window_start=prior_start, window_end=start
    )

    current_pct = _percent(current["on_time"], current["arrivals"])
    previous_pct = _percent(previous["on_time"], previous["arrivals"])
    # A delta needs both periods to have data. Reporting "+91pp" because the prior window was
    # empty would invent a trend out of an absence.
    delta = (
        round(current_pct - previous_pct, 1)
        if current_pct is not None and previous_pct is not None
        else None
    )

    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "scope": _scope_block(carrier_id),
        "active_shipment_count": active,
        "open_exception_count": open_exceptions,
        "on_time_performance": {
            "window": _DEFAULT_WINDOW,
            "percent": current_pct,
            "arrivals": current["arrivals"],
            "previous_percent": previous_pct,
            "previous_arrivals": previous["arrivals"],
            "delta_percentage_points": delta,
        },
        "freshness": "live",
        "note": _NON_COMPARATIVE_NOTE,
    }


async def list_fleet_shipments(
    session: AsyncSession, ctx: ExecutionContext, status_filter: str | None = None
) -> dict[str, Any]:
    """§7.5.6 `list_fleet_shipments` -- arguments: `status_filter?`.

    Cross-facility always: §7.5.6 states carriers are not facility-scoped, unlike every other
    role, so there is deliberately no facility argument here and none is derived from `ctx`.

    `empty_reason` exists because `FR-CAR-006` and `edge-cases.md` #5 require the client to tell
    "no active shipments right now" from "no shipments on record yet" from "no matches for this
    filter" -- three different copy strings the client cannot choose between from an empty array
    alone. The lifetime-count query that distinguishes the first two only runs when the list is
    actually empty and unfiltered, so the common path stays at one round trip.
    """
    carrier_id = resolve_carrier_scope(ctx)
    # Resolved once and passed to both the validator and the repository, so the filter cannot be
    # accepted under one reading of the flag and then executed under another (issue #87).
    holds_enabled = holds.hold_reads_enabled()
    promise_state, only_with_open_exception = _validate_status_filter(
        status_filter, holds_enabled=holds_enabled
    )
    filtered = promise_state is not None or only_with_open_exception

    items = await carrier_repo.list_fleet_shipments(
        session,
        carrier_id,
        promise_state=promise_state,
        only_with_open_exception=only_with_open_exception,
        # Issue #85: with the D2 flag on, `promise_state` is composed from `dock_occupancy` as well
        # as `appointments`, so a held shipment reads HELD instead of silently reading as though it
        # had no promise at all. Off, the statement is the one that shipped -- which it must be,
        # since the columns do not exist until the D2 migration is applied.
        include_holds=holds_enabled,
    )

    empty_reason: str | None = None
    if not items:
        if filtered:
            empty_reason = "NO_MATCH_FOR_FILTER"
        else:
            ever = await carrier_repo.count_shipments_ever(session, carrier_id)
            empty_reason = "NONE_YET" if ever == 0 else "NONE_RIGHT_NOW"

    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "scope": _scope_block(carrier_id),
        "status_filter": (promise_state or (_EXCEPTION_FILTER if only_with_open_exception else None)),
        "items": items,
        "empty_reason": empty_reason,
        "freshness": "live",
        "note": _NON_COMPARATIVE_NOTE,
    }


async def get_shipment_detail(
    session: AsyncSession, ctx: ExecutionContext, shipment_id: str
) -> dict[str, Any]:
    """§7.5.6 `get_shipment_detail` -- arguments: `shipment_id`.

    **Validates carrier ownership server-side and refuses rather than hides** (§7.5.6, `U28`,
    `M15`): a cross-carrier id raises a 403, it does not return an empty or partial payload the
    client is trusted to discard. The refusal is also identical for a shipment id that does not
    exist at all -- `edge-cases.md` #1 requires this surface to never confirm or deny existence
    outside scope, so a 404-for-missing / 403-for-other-carrier split would itself be the leak.

    The `shipment_id` argument is *not* a scope identifier and does not violate M15: it names a
    row, and the carrier that row must belong to still comes from the verified identity.
    """
    carrier_id = resolve_carrier_scope(ctx)
    shipment = await carrier_repo.get_fleet_shipment(
        session, carrier_id, shipment_id, include_holds=holds.hold_reads_enabled()
    )
    # `shipment` is None for both "no such shipment" and "another carrier's shipment", and this
    # single call refuses both identically. Do not add a NOT_FOUND branch above it.
    assert_shipment_in_carrier_fleet(
        ctx, shipment_carrier_id=shipment["carrier_id"] if shipment else None
    )
    if shipment is None:
        # Unreachable: the call above always raises on a None carrier id. Kept as a real branch
        # rather than a bare `assert` so the refusal survives `python -O`, which strips asserts.
        raise AppError("This shipment isn't in your fleet.", code="FORBIDDEN", status_code=403)

    history = await carrier_repo.list_shipment_history(session, carrier_id, shipment_id)
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "scope": _scope_block(carrier_id),
        "shipment": shipment,
        "history": history,
        "freshness": "live",
        "note": _NON_COMPARATIVE_NOTE,
    }


async def list_fleet_exceptions(session: AsyncSession, ctx: ExecutionContext) -> dict[str, Any]:
    """§7.5.6 `list_fleet_exceptions` -- arguments: none.

    Status only. §7.5.6 forbids "another carrier's queue position or why a contested interval was
    lost", and `components.md` §3 forbids the owner name, SLA clock and stepper an ops coordinator
    sees; `repositories.carrier.list_open_exceptions`'s column allowlist is where both are
    enforced, so this function has no filtering left to do.
    """
    carrier_id = resolve_carrier_scope(ctx)
    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "scope": _scope_block(carrier_id),
        "items": await carrier_repo.list_open_exceptions(session, carrier_id),
        "freshness": "live",
        "note": _NON_COMPARATIVE_NOTE,
    }


async def get_carrier_on_time_performance(
    session: AsyncSession, ctx: ExecutionContext, window: str | None = None
) -> dict[str, Any]:
    """§7.5.6 `get_carrier_on_time_performance` -- arguments: `window` (`30d` default).

    This carrier's own series for the sparkline (`U33`/`U66`) and nothing else. §7.5.6 is explicit
    that this is "**never a cross-carrier comparison, benchmark, or rank**, not even as an
    aggregate count that would let one be inferred" -- so there is no denominator here drawn from
    any row this carrier does not own, and the series carries only this carrier's own arrivals.
    """
    carrier_id = resolve_carrier_scope(ctx)
    resolved_window = _validate_window(window)
    _, start, end = _windows(resolved_window)

    totals = await carrier_repo.get_on_time_totals(
        session, carrier_id, window_start=start, window_end=end
    )
    series = await carrier_repo.get_on_time_daily_series(
        session, carrier_id, window_start=start, window_end=end
    )

    return {
        "as_of": _as_of(),
        "source": "postgresql",
        "scope": _scope_block(carrier_id),
        "window": resolved_window,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "percent": _percent(totals["on_time"], totals["arrivals"]),
        "arrivals": totals["arrivals"],
        "series": [
            {
                "day": point["day"],
                "arrivals": point["arrivals"],
                "percent": _percent(point["on_time"], point["arrivals"]),
            }
            for point in series
        ],
        "freshness": "live",
        "note": _NON_COMPARATIVE_NOTE,
    }
