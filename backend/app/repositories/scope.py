"""The single implementation of SetuHaul's server-side scope rules (`NFR-020`).

Deliberately session-free: these are pure predicates over the trusted `ExecutionContext` plus
already-fetched row fields, so they can be unit-tested across every role without a database and
called from a service, a repository read, or the scheduling layer alike.

`resolve_facility_scope_with_user_scopes` is the one exception, and it is an exception rather than
a new convention. Issue #106: `user_scopes` is the identity model's source of truth for scope
(E2.3) and the admin console can genuinely grant a user two facilities (#72, shipped), but the
`ExecutionContext` carries only the single `users.facility_id` mirror -- so the second facility was
unreachable on every surface. Deciding that needs a row nobody has fetched yet, which is why that
one function takes a session. The pure form below is unchanged and remains what every caller with
no client-supplied facility uses.

Read vs write tiers are kept distinct on purpose (see `ExecutionContext.is_admin`): read paths
gate on `has_global_read_scope`, write paths on `is_admin`. TRANSPORT_MANAGER and
REGIONAL_OPERATIONS_HEAD hold only `*_read_global` permissions, so collapsing the two tiers back
into one flag would silently hand them cross-facility write access. Do not merge them.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext

# Message text for "this caller has no facility on their identity at all", keyed by the error code
# the calling surface reports. The REST operations surface distinguishes SCOPE_MISSING (broken
# identity mapping) from FORBIDDEN (asked for someone else's facility); the assistant-facing
# service paths have always reported FORBIDDEN for both. Preserving both codes is intentional --
# converging them is a client-visible API change and belongs in its own issue, not in E2.2.
_UNMAPPED_MESSAGE = {
    "FORBIDDEN": "Facility not in scope.",
    "SCOPE_MISSING": "Operator facility scope missing.",
}


def resolve_facility_scope(
    ctx: ExecutionContext,
    requested_facility_id: str | None,
    *,
    require_facility: bool = False,
    unmapped_code: str = "FORBIDDEN",
) -> str | None:
    """Return the facility id a read should actually filter by, or raise if out of scope.

    `requested_facility_id` is a client-supplied *request*, never the answer (`M15`/`NFR-019`):
    a global-read persona may use it to narrow their view, everyone else may only pass their own
    facility or nothing at all.

    Returns `None` only for a global-read persona that asked for no particular facility, meaning
    "no facility filter". Pass `require_facility=True` when the caller's SQL binds `:facility_id`
    unconditionally and therefore cannot run unscoped.
    """
    if ctx.has_global_read_scope:
        scope = requested_facility_id
    else:
        scope = ctx.facility_id
        if scope is None:
            raise AppError(
                _UNMAPPED_MESSAGE.get(unmapped_code, _UNMAPPED_MESSAGE["FORBIDDEN"]),
                code=unmapped_code,
                status_code=403,
            )
        if requested_facility_id and requested_facility_id != scope:
            raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)

    if require_facility and scope is None:
        raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)
    return scope


async def user_holds_facility_scope(
    session: AsyncSession, *, user_id: str, facility_id: str
) -> bool:
    """Does this user carry an explicit `user_scopes` FACILITY grant for this facility?

    One indexed probe: `user_scopes` carries `UNIQUE (user_id, scope_type, scope_value)`
    (`20260823090000_e23_identity_model.sql`), so this is an exact-match lookup on that unique
    index, not a scan of the user's grants. `LIMIT 1` is belt-and-braces on a unique key.

    Reads `user_scopes` and never `users.facility_id`: the column is the *mirror*
    (`admin_user_service`'s header states the two-place split), the table is the source of truth,
    and a user with two facilities has two rows here and only one of them in the column.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT 1
                FROM public.user_scopes
                WHERE user_id = :user_id
                  AND scope_type = 'FACILITY'
                  AND scope_value = :facility_id
                LIMIT 1
                """
            ),
            {"user_id": user_id, "facility_id": facility_id},
        )
    ).first()
    return row is not None


async def resolve_facility_scope_with_user_scopes(
    session: AsyncSession,
    ctx: ExecutionContext,
    requested_facility_id: str | None,
    *,
    require_facility: bool = False,
    unmapped_code: str = "FORBIDDEN",
) -> str | None:
    """`resolve_facility_scope`, plus the `user_scopes` FACILITY grants (issue #106).

    Same contract, same refusals, one addition: a **non**-global-read caller may name any facility
    their own `user_scopes` grants, not only the single `users.facility_id` mirror on their token.
    That is what makes #72's shipped multi-facility assignment usable -- before this, a coordinator
    granted Jaipur *and* Gurugram could select the second in #99's switcher and every read answered
    403, because scope resolution compared against the mirror alone and never consulted the table
    E2.3 made authoritative.

    Still `M15`/`NFR-019`-clean: `requested_facility_id` remains a *request*, and the only thing
    that can turn it into an answer is a row the server itself holds for this verified `user_id`.
    Nothing about the client's claim is trusted; anything outside the grants is still refused with
    the identical code and message the pure resolver produces.

    **Round trips, traced rather than assumed** (`deps.py` builds one `ExecutionContext` per
    request and caches nothing across requests, so an unconditional read here would be a real extra
    trip on every scoped read in the product):

      * global-read persona                      -> 0 queries (the parameter already narrows)
      * no `facility_id` requested               -> 0 queries (nothing to validate)
      * requested facility == the token's mirror -> 0 queries (the pure rule already allows it)
      * anything else                            -> exactly 1 indexed probe

    So the query fires only in the case that is currently a wrong 403, and never on the paths that
    already answered correctly. The last branch deliberately falls through to the pure resolver on
    a miss rather than raising here, so there is one place that decides what a refusal looks like.
    """
    if (
        ctx.has_global_read_scope
        or not requested_facility_id
        or requested_facility_id == ctx.facility_id
    ):
        return resolve_facility_scope(
            ctx,
            requested_facility_id,
            require_facility=require_facility,
            unmapped_code=unmapped_code,
        )
    if await user_holds_facility_scope(
        session, user_id=ctx.user_id, facility_id=requested_facility_id
    ):
        return requested_facility_id
    return resolve_facility_scope(
        ctx,
        requested_facility_id,
        require_facility=require_facility,
        unmapped_code=unmapped_code,
    )


def assert_shipment_visible(
    ctx: ExecutionContext,
    *,
    shipment_driver_id: str | None,
    shipment_facility_id: str | None,
    require_write: bool = False,
) -> None:
    """Driver-owns-it / operator-in-its-facility / global-persona gate for one shipment.

    `require_write=True` is mandatory for callers that mutate (cancel, reschedule): the global
    tier then demands `is_admin` rather than mere global visibility, so the global *read-only*
    personas can still see a cross-facility shipment but cannot act on it. A driver who owns the
    shipment passes either tier -- that is the pre-existing behaviour and is intentional.
    """
    if ctx.is_driver:
        if shipment_driver_id != ctx.driver_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
        return
    if ctx.is_operator:
        if shipment_facility_id != ctx.facility_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
        return
    if ctx.is_admin if require_write else ctx.has_global_read_scope:
        return
    raise AppError("Insufficient permissions.", code="FORBIDDEN", status_code=403)


def assert_facility_visible(
    ctx: ExecutionContext,
    facility_id: str,
    *,
    driver_serves_facility: bool = False,
) -> None:
    """Read gate for one facility record.

    A driver's claim on a facility cannot be decided from the context alone -- it depends on
    whether any of their shipments is bound for it -- so the caller resolves that with
    `repositories.facilities.driver_serves_facility` and passes the answer in. Keeping the
    predicate here rather than the query means the rule stays in one place while the SQL stays
    in the facility repository.
    """
    if ctx.is_driver:
        if not driver_serves_facility:
            raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)
        return
    if ctx.is_operator:
        if ctx.facility_id != facility_id:
            raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)
        return
    if ctx.has_global_read_scope:
        return
    raise AppError("Insufficient permissions.", code="FORBIDDEN", status_code=403)


def resolve_carrier_scope(ctx: ExecutionContext) -> str:
    """Return the carrier id a carrier-portal read must filter by (`E3.3`, §7.5.6, `M15`).

    Deliberately takes **no** `requested_carrier_id` parameter, unlike `resolve_facility_scope`
    above. That asymmetry is the point: §7.5.6 states every carrier tool is "scope-derived from
    the caller's own `carrier_id` (M15), never accepted as an argument", so there is no client
    input for this function to validate -- the only carrier id that can reach a query is the one
    on the verified identity. Adding a parameter here later would reintroduce exactly the
    client-supplied-scope shape M15 exists to forbid.

    Raises rather than returning `None` on an unmapped identity: unlike a global-read facility
    persona, "no carrier filter" is never a legal carrier-portal outcome, so an unmapped
    carrier-portal user must be refused, not silently served the whole fleet table.

    That second guard is what keeps issue #101's role widening honest. `ctx.is_carrier` now admits
    TRANSPORT_MANAGER as well as CARRIER, and TRANSPORT_MANAGER *does* hold `has_global_read_scope`
    over facilities -- so if this function had ever fallen through to "no filter" for an unmapped
    identity, widening the role set would have turned the carrier portal into a cross-carrier read
    for that persona. It does not: no `user_scopes(scope_type='CARRIER')` row, no reach.
    """
    if not ctx.is_carrier:
        raise AppError("Insufficient permissions.", code="FORBIDDEN", status_code=403)
    if not ctx.carrier_id:
        raise AppError(
            "Carrier scope missing.",
            code="CARRIER_UNMAPPED",
            status_code=403,
            detail="This account is not linked to a carrier.",
        )
    return ctx.carrier_id


def assert_shipment_in_carrier_fleet(
    ctx: ExecutionContext, *, shipment_carrier_id: str | None
) -> None:
    """Refuse a shipment that is not in the caller's own fleet (§7.5.6 `get_shipment_detail`).

    Callers must pass `shipment_carrier_id=None` for a shipment id that returned no row at all,
    **not** raise `NOT_FOUND` first. `UI-UX/05-carrier-portal/edge-cases.md` #1 requires that this
    surface "never confirms or denies whether the shipment exists at all outside their scope", so
    a missing id and another carrier's id must be indistinguishable to the client -- same code,
    same status, same message. A 404-then-403 pair would leak existence by response code alone.
    """
    if not ctx.can_read_carrier(shipment_carrier_id):
        raise AppError(
            "This shipment isn't in your fleet.",
            code="FORBIDDEN",
            status_code=403,
            detail="This shipment isn't in your fleet.",
        )


def assert_facility_write_scope(ctx: ExecutionContext, facility_id: str) -> None:
    """Write gate for an *ops-portal* action recorded against a facility (e.g. an escalation).

    `is_admin`, not `has_global_read_scope`: this guards a mutation.

    Deliberately unchanged by issue #79: `GATE_OFFICER` does **not** pass this gate. The gate
    kiosk's own writes use `assert_gate_write_scope` below instead, so a new role could not
    inherit escalation/takeover authority merely by being facility-scoped.
    """
    if ctx.is_admin or (ctx.is_operator and ctx.facility_id == facility_id):
        return
    raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)


def assert_gate_write_scope(ctx: ExecutionContext, facility_id: str) -> None:
    """Write gate for the SS7.5.2 gate/yard check-in writes (issue #79, `FR-GATE-004..008`).

    Same shape as `assert_facility_write_scope` plus `GATE_OFFICER`, and kept as a *separate*
    function rather than a widened one on purpose. `assert_facility_write_scope` is shared by
    escalation raise/resolve, thread takeover and the planner writes; widening it would have
    granted the gate kiosk every one of those the moment the role existed -- the exact "silent
    scope widening" this module's own docstring and `ExecutionContext.is_admin` both warn about.
    Two functions, two blast radii.

    `WAREHOUSE_PLANNER`/`FACILITY_MANAGER` still pass (via `is_operator`): the 2026-08-24 mapping
    that let them work a kiosk is not being revoked here, only stopped from being the *only* way
    in. A gate officer's reach is its own facility and nothing else -- `ADMIN` remains the single
    cross-facility case, matching what `gate_yard_reads.resolve_facility_scope` already grants on
    the read side, so read reach and write reach still agree by construction.
    """
    if ctx.is_admin:
        return
    if (ctx.is_operator or ctx.is_gate_officer) and ctx.facility_id == facility_id:
        return
    raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)
