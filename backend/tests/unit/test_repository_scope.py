"""E2.2 (issue #22) characterisation tests for the consolidated scope tier.

The point of these tests is not to assert what the author *believes* the scope rules are. Each
`_legacy_*` helper below is the pre-refactor implementation copied verbatim from the call site it
came from (file + line cited on each), and the matrix tests assert the new
`app.repositories.scope` functions produce the identical outcome -- same return value, same error
code, same HTTP status -- for every role in `RoleName` and every input shape.

That matters because the pre-existing suite covered exactly one of these paths
(`get_pending_confirmations`); `get_exception_queue`, `get_dock_status`, `get_queue_status`, the
operations router's `_resolve_facility` and the whole shipment-visibility idiom had no
scope-refusal coverage at all, so a silent widening during the refactor would have gone unnoticed.
`NFR-019` requires scope refusal to be tested; this is that test.
"""

from __future__ import annotations

import pytest

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.repositories.scope import (
    assert_facility_visible,
    assert_facility_write_scope,
    assert_gate_write_scope,
    assert_shipment_visible,
    resolve_facility_scope,
)

OWN_FACILITY = "FAC-GGN-01"
OTHER_FACILITY = "FAC-JAI-01"
OWN_DRIVER = "DRV001"
OTHER_DRIVER = "DRV999"


def _ctx(role: RoleName, *, facility_id: str | None = None, driver_id: str | None = None) -> ExecutionContext:
    return ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR-TEST",
        email="test@setuhaul.com",
        full_name="Test User",
        role_id="ROL-TEST",
        role_name=role,
        facility_id=facility_id,
        driver_id=driver_id,
    )


def _every_role_context() -> list[ExecutionContext]:
    """One context per role, each carrying the identity fields that role realistically holds."""
    contexts = []
    for role in RoleName:
        if role is RoleName.DRIVER:
            contexts.append(_ctx(role, driver_id=OWN_DRIVER, facility_id=None))
        elif role in {RoleName.ADMIN, RoleName.TRANSPORT_MANAGER, RoleName.REGIONAL_OPERATIONS_HEAD}:
            contexts.append(_ctx(role, facility_id=None))
        else:
            contexts.append(_ctx(role, facility_id=OWN_FACILITY))
        # Also exercise the "identity has no facility mapping" variant for facility-scoped roles.
        if role not in {RoleName.DRIVER}:
            contexts.append(_ctx(role, facility_id=None))
    return contexts


def _outcome(fn, *args, **kwargs):
    """Normalise a call into a comparable outcome: value, or (code, status) on refusal."""
    try:
        return ("ok", fn(*args, **kwargs))
    except AppError as exc:
        return ("error", exc.code, exc.status_code)


# --------------------------------------------------------------------------------------------
# Legacy implementations, copied verbatim from the pre-E2.2 call sites.
# --------------------------------------------------------------------------------------------


def _legacy_operations_resolve_facility(ctx: ExecutionContext, facility_id: str | None) -> str | None:
    """Verbatim from app/api/v1/routers/operations.py:39-48 before E2.2."""
    if ctx.has_global_read_scope:
        return facility_id
    if not ctx.facility_id:
        raise AppError("Operator facility scope missing.", code="SCOPE_MISSING", status_code=403)
    if facility_id and facility_id != ctx.facility_id:
        raise AppError("Cross-facility access denied.", code="FORBIDDEN", status_code=403)
    return ctx.facility_id


def _legacy_exception_queue_scope(ctx: ExecutionContext, facility_id: str | None) -> str | None:
    """Verbatim from app/services/escalation_service.py:169-173 before E2.2."""
    scope = facility_id if ctx.has_global_read_scope else ctx.facility_id
    if not ctx.has_global_read_scope:
        if not scope or (facility_id and facility_id != scope):
            raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)
    return scope


def _legacy_required_facility_scope(ctx: ExecutionContext, facility_id: str | None) -> str | None:
    """Verbatim from escalation_service.py:281-283 / 307-309 / 330-332 before E2.2."""
    scope = facility_id if ctx.has_global_read_scope else ctx.facility_id
    if not scope or (not ctx.has_global_read_scope and facility_id and facility_id != scope):
        raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)
    return scope


def _legacy_shipment_visible_chain(ctx: ExecutionContext, driver_id, facility_id) -> None:
    """Verbatim from app/api/v1/routers/shipments.py:48-55 before E2.2 (if/elif form)."""
    if ctx.is_driver:
        if driver_id != ctx.driver_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
    elif ctx.is_operator:
        if facility_id != ctx.facility_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
    elif not ctx.has_global_read_scope:
        raise AppError("Insufficient permissions.", code="FORBIDDEN", status_code=403)


def _legacy_shipment_visible_sequential(ctx: ExecutionContext, driver_id, facility_id) -> None:
    """Verbatim from shipments.py:82-87 and services/driver_reads.py:151-156 before E2.2."""
    if ctx.is_driver and driver_id != ctx.driver_id:
        raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
    if ctx.is_operator and facility_id != ctx.facility_id:
        raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
    if not (ctx.is_driver or ctx.is_operator or ctx.has_global_read_scope):
        raise AppError("Insufficient permissions.", code="FORBIDDEN", status_code=403)


def _legacy_scheduling_shipment_scope(ctx: ExecutionContext, driver_id, facility_id, *, require_write=False) -> None:
    """Verbatim from app/scheduling/allocation.py:181-201 (and feasibility.py:572-584) before E2.2."""
    if ctx.is_driver:
        if driver_id != ctx.driver_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
        return
    if ctx.is_operator:
        if facility_id != ctx.facility_id:
            raise AppError("Shipment not in scope.", code="FORBIDDEN", status_code=403)
        return
    if ctx.is_admin if require_write else ctx.has_global_read_scope:
        return
    raise AppError("Insufficient permissions.", code="FORBIDDEN", status_code=403)


def _legacy_facility_details_scope(ctx: ExecutionContext, facility_id: str, driver_owns: bool) -> None:
    """Verbatim from services/driver_reads.py:247-265 before E2.2 (with the DB probe inlined)."""
    if ctx.is_driver:
        if not driver_owns:
            raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)
    elif ctx.is_operator and ctx.facility_id != facility_id:
        raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)
    elif not (ctx.is_driver or ctx.is_operator or ctx.has_global_read_scope):
        raise AppError("Insufficient permissions.", code="FORBIDDEN", status_code=403)


def _legacy_ops_write_scope(ctx: ExecutionContext, facility_id: str) -> None:
    """Verbatim from services/escalation_service.py:40-43 before E2.2."""
    if ctx.is_admin or (ctx.is_operator and ctx.facility_id == facility_id):
        return
    raise AppError("Facility not in scope.", code="FORBIDDEN", status_code=403)


# --------------------------------------------------------------------------------------------
# Equivalence matrices
# --------------------------------------------------------------------------------------------

REQUESTED_FACILITIES = [None, OWN_FACILITY, OTHER_FACILITY]


@pytest.mark.parametrize("requested", REQUESTED_FACILITIES)
def test_resolve_facility_scope_matches_operations_router_legacy(requested):
    for ctx in _every_role_context():
        new = _outcome(
            resolve_facility_scope, ctx, requested, require_facility=False, unmapped_code="SCOPE_MISSING"
        )
        old = _outcome(_legacy_operations_resolve_facility, ctx, requested)
        assert new == old, f"{ctx.role_name} facility={ctx.facility_id} requested={requested}"


@pytest.mark.parametrize("requested", REQUESTED_FACILITIES)
def test_resolve_facility_scope_matches_exception_queue_legacy(requested):
    for ctx in _every_role_context():
        new = _outcome(resolve_facility_scope, ctx, requested)
        old = _outcome(_legacy_exception_queue_scope, ctx, requested)
        assert new == old, f"{ctx.role_name} facility={ctx.facility_id} requested={requested}"


@pytest.mark.parametrize("requested", REQUESTED_FACILITIES)
def test_resolve_facility_scope_matches_required_facility_legacy(requested):
    for ctx in _every_role_context():
        new = _outcome(resolve_facility_scope, ctx, requested, require_facility=True)
        old = _outcome(_legacy_required_facility_scope, ctx, requested)
        assert new == old, f"{ctx.role_name} facility={ctx.facility_id} requested={requested}"


@pytest.mark.parametrize("driver_id", [OWN_DRIVER, OTHER_DRIVER, None])
@pytest.mark.parametrize("facility_id", [OWN_FACILITY, OTHER_FACILITY, None])
def test_assert_shipment_visible_matches_every_legacy_read_form(driver_id, facility_id):
    for ctx in _every_role_context():
        new = _outcome(
            assert_shipment_visible,
            ctx,
            shipment_driver_id=driver_id,
            shipment_facility_id=facility_id,
        )
        for legacy in (
            _legacy_shipment_visible_chain,
            _legacy_shipment_visible_sequential,
            _legacy_scheduling_shipment_scope,
        ):
            old = _outcome(legacy, ctx, driver_id, facility_id)
            assert new == old, f"{legacy.__name__} {ctx.role_name} d={driver_id} f={facility_id}"


@pytest.mark.parametrize("driver_id", [OWN_DRIVER, OTHER_DRIVER, None])
@pytest.mark.parametrize("facility_id", [OWN_FACILITY, OTHER_FACILITY, None])
def test_assert_shipment_visible_write_tier_matches_legacy(driver_id, facility_id):
    for ctx in _every_role_context():
        new = _outcome(
            assert_shipment_visible,
            ctx,
            shipment_driver_id=driver_id,
            shipment_facility_id=facility_id,
            require_write=True,
        )
        old = _outcome(_legacy_scheduling_shipment_scope, ctx, driver_id, facility_id, require_write=True)
        assert new == old, f"{ctx.role_name} d={driver_id} f={facility_id}"


@pytest.mark.parametrize("driver_owns", [True, False])
@pytest.mark.parametrize("facility_id", [OWN_FACILITY, OTHER_FACILITY])
def test_assert_facility_visible_matches_legacy(driver_owns, facility_id):
    for ctx in _every_role_context():
        new = _outcome(assert_facility_visible, ctx, facility_id, driver_serves_facility=driver_owns)
        old = _outcome(_legacy_facility_details_scope, ctx, facility_id, driver_owns)
        assert new == old, f"{ctx.role_name} f={facility_id} owns={driver_owns}"


@pytest.mark.parametrize("facility_id", [OWN_FACILITY, OTHER_FACILITY])
def test_assert_facility_write_scope_matches_legacy(facility_id):
    for ctx in _every_role_context():
        new = _outcome(assert_facility_write_scope, ctx, facility_id)
        old = _outcome(_legacy_ops_write_scope, ctx, facility_id)
        assert new == old, f"{ctx.role_name} f={facility_id}"


# --------------------------------------------------------------------------------------------
# Explicit refusal assertions (NFR-019) -- these state the rule directly, not just "unchanged".
# --------------------------------------------------------------------------------------------


def test_operator_cannot_widen_scope_with_a_client_supplied_facility_id():
    """M15/NFR-019: a client-supplied facility id is a request, never the answer."""
    ctx = _ctx(RoleName.OPERATIONS_EXECUTIVE, facility_id=OWN_FACILITY)
    with pytest.raises(AppError) as exc:
        resolve_facility_scope(ctx, OTHER_FACILITY)
    assert exc.value.code == "FORBIDDEN"
    assert exc.value.status_code == 403
    # ...and omitting it does not fall back to "everything".
    assert resolve_facility_scope(ctx, None) == OWN_FACILITY


def test_carrier_persona_has_no_facility_read_reach():
    """CARRIER (E2.3) is neither driver, operator, nor global-read: every facility path refuses."""
    ctx = _ctx(RoleName.CARRIER)
    with pytest.raises(AppError) as exc:
        assert_shipment_visible(ctx, shipment_driver_id=OWN_DRIVER, shipment_facility_id=OWN_FACILITY)
    assert exc.value.code == "FORBIDDEN"
    with pytest.raises(AppError):
        assert_facility_visible(ctx, OWN_FACILITY)
    with pytest.raises(AppError):
        resolve_facility_scope(ctx, None)


def test_global_read_only_personas_can_read_but_not_write_across_facilities():
    """The read/write tier split must survive consolidation (issue #10 regression guard)."""
    for role in (RoleName.TRANSPORT_MANAGER, RoleName.REGIONAL_OPERATIONS_HEAD):
        ctx = _ctx(role)
        assert resolve_facility_scope(ctx, OTHER_FACILITY) == OTHER_FACILITY
        assert_shipment_visible(ctx, shipment_driver_id=OWN_DRIVER, shipment_facility_id=OTHER_FACILITY)
        with pytest.raises(AppError) as exc:
            assert_shipment_visible(
                ctx,
                shipment_driver_id=OWN_DRIVER,
                shipment_facility_id=OTHER_FACILITY,
                require_write=True,
            )
        assert exc.value.code == "FORBIDDEN", role
        with pytest.raises(AppError):
            assert_facility_write_scope(ctx, OTHER_FACILITY)


# --------------------------------------------------------------------------------------------
# assert_gate_write_scope (issue #79) -- the gate/yard write tier.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize("facility_id", [OWN_FACILITY, OTHER_FACILITY])
def test_assert_gate_write_scope_differs_from_the_ops_write_tier_by_exactly_one_role(facility_id):
    """The two write predicates must agree on every role except GATE_OFFICER.

    Written as a difference test rather than a list of expectations so that adding a role to
    `assert_gate_write_scope` later cannot pass silently -- any second divergence fails here with
    the offending role named.
    """
    diverged = []
    for ctx in _every_role_context():
        gate = _outcome(assert_gate_write_scope, ctx, facility_id)
        ops = _outcome(assert_facility_write_scope, ctx, facility_id)
        if gate != ops:
            diverged.append((ctx.role_name, ctx.facility_id, gate, ops))
    assert all(role is RoleName.GATE_OFFICER for role, _, _, _ in diverged), diverged
    if facility_id == OWN_FACILITY:
        # The one divergence: a mapped gate officer, on its own facility, only.
        assert [(role, fac) for role, fac, _, _ in diverged] == [
            (RoleName.GATE_OFFICER, OWN_FACILITY)
        ], diverged
    else:
        assert diverged == [], diverged


def test_gate_officer_may_write_only_its_own_facility():
    ctx = _ctx(RoleName.GATE_OFFICER, facility_id=OWN_FACILITY)
    assert_gate_write_scope(ctx, OWN_FACILITY)
    with pytest.raises(AppError) as exc:
        assert_gate_write_scope(ctx, OTHER_FACILITY)
    assert exc.value.code == "FORBIDDEN"
    assert exc.value.status_code == 403


def test_unmapped_gate_officer_is_refused_rather_than_defaulting_to_any_facility():
    """A kiosk account with no `users.facility_id` must not fall through to "everything"."""
    ctx = _ctx(RoleName.GATE_OFFICER, facility_id=None)
    for facility in (OWN_FACILITY, OTHER_FACILITY):
        with pytest.raises(AppError) as exc:
            assert_gate_write_scope(ctx, facility)
        assert exc.value.code == "FORBIDDEN"
    # And the read side refuses too, rather than resolving to an unfiltered search.
    with pytest.raises(AppError):
        resolve_facility_scope(ctx, None)


def test_gate_officer_has_no_ops_write_reach_at_all():
    """Issue #79's narrowing guarantee, asserted against the *shared* write gate.

    `assert_facility_write_scope` is what escalation raise/resolve, thread takeover and the
    planner writes call. A gate officer must fail it on its own facility, not merely on someone
    else's -- otherwise the role would have gained escalation authority by being facility-scoped.
    """
    ctx = _ctx(RoleName.GATE_OFFICER, facility_id=OWN_FACILITY)
    for facility in (OWN_FACILITY, OTHER_FACILITY):
        with pytest.raises(AppError) as exc:
            assert_facility_write_scope(ctx, facility)
        assert exc.value.code == "FORBIDDEN"
    # ...and it is not visible to the ops read idioms either.
    with pytest.raises(AppError):
        assert_shipment_visible(
            ctx, shipment_driver_id=OWN_DRIVER, shipment_facility_id=OWN_FACILITY
        )
    with pytest.raises(AppError):
        assert_facility_visible(ctx, OWN_FACILITY)


def test_ops_kiosk_roles_still_pass_the_gate_write_tier():
    """The 2026-08-24 mapping is superseded, not revoked: planners can still work a kiosk."""
    for role in (RoleName.WAREHOUSE_PLANNER, RoleName.FACILITY_MANAGER):
        assert_gate_write_scope(_ctx(role, facility_id=OWN_FACILITY), OWN_FACILITY)
        with pytest.raises(AppError):
            assert_gate_write_scope(_ctx(role, facility_id=OWN_FACILITY), OTHER_FACILITY)
    # ADMIN keeps its cross-facility reach, matching what the search side already grants it.
    assert_gate_write_scope(_ctx(RoleName.ADMIN), OTHER_FACILITY)


def test_driver_sees_only_their_own_shipment():
    ctx = _ctx(RoleName.DRIVER, driver_id=OWN_DRIVER)
    assert_shipment_visible(ctx, shipment_driver_id=OWN_DRIVER, shipment_facility_id=OTHER_FACILITY)
    with pytest.raises(AppError) as exc:
        assert_shipment_visible(ctx, shipment_driver_id=OTHER_DRIVER, shipment_facility_id=OTHER_FACILITY)
    assert exc.value.code == "FORBIDDEN"
