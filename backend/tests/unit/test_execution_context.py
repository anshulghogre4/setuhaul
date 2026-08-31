from app.core.deps import GATE_KIOSK_ROLES, OPS_PORTAL_ROLES, ROLE_PERMISSIONS
from app.core.envelope import fail, ok
from app.core.execution_context import ExecutionContext, RoleName


def test_success_envelope_shape():
    body = ok({"hello": "world"}, "req-1")
    assert body["success"] is True
    assert body["request_id"] == "req-1"
    assert body["data"]["hello"] == "world"


def test_error_envelope_shape():
    body = fail("Nope", "req-2", code="FORBIDDEN")
    assert body["success"] is False
    assert body["errors"][0]["code"] == "FORBIDDEN"


def test_admin_can_read_any_facility():
    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR999",
        email="admin@setuhaul.com",
        full_name="Admin",
        role_id="ROL008",
        role_name=RoleName.ADMIN,
    )
    assert ctx.can_read_facility("FAC-JAI-01")
    assert ctx.can_read_facility("FAC-OTHER")


def test_operator_is_facility_scoped():
    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR101",
        email="priya.mehta@setuhaul.com",
        full_name="Priya",
        role_id="ROL002",
        role_name=RoleName.OPERATIONS_EXECUTIVE,
        facility_id="FAC-JAI-01",
    )
    assert ctx.can_read_facility("FAC-JAI-01")
    assert not ctx.can_read_facility("FAC-DEL-01")


def test_facility_ops_roles_are_operator_scoped():
    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR102",
        email="rahul.verma@setuhaul.com",
        full_name="Rahul",
        role_id="ROL003",
        role_name=RoleName.WAREHOUSE_PLANNER,
        facility_id="FAC-JAI-01",
    )
    assert ctx.is_operator
    assert not ctx.is_admin
    assert ctx.can_read_facility("FAC-JAI-01")
    assert not ctx.can_read_facility("FAC-GGN-01")


def test_global_read_only_roles_have_global_read_but_no_write_authority():
    """Issue #10: TRANSPORT_MANAGER / REGIONAL_OPERATIONS_HEAD hold only *_read_global
    permissions, so is_admin (the flag every mutating path checks) must be False for them
    while global read reach is preserved via has_global_read_scope."""
    for role_id, role in (
        ("ROL007", RoleName.REGIONAL_OPERATIONS_HEAD),
        ("ROL006", RoleName.TRANSPORT_MANAGER),
    ):
        ctx = ExecutionContext(
            request_id="r",
            auth_subject="sub",
            user_id="USR106",
            email="neha.bansal@setuhaul.com",
            full_name="Neha",
            role_id=role_id,
            role_name=role,
        )
        assert not ctx.is_admin, f"{role} must not be write-authorised"
        assert not ctx.is_operator
        assert ctx.has_global_read_scope, f"{role} must keep global read reach"
        assert ctx.can_read_facility("FAC-JAI-01")


def test_admin_retains_write_authority_and_global_read():
    """Guards against over-correcting issue #10 into locking real admins out of writes."""
    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR999",
        email="admin@setuhaul.com",
        full_name="Admin",
        role_id="ROL008",
        role_name=RoleName.ADMIN,
    )
    assert ctx.is_admin
    assert ctx.has_global_read_scope
    assert not ctx.is_operator


def test_carrier_reads_only_its_own_fleet():
    """E2.3 (issue #23): a carrier's read reach never falls back to has_global_read_scope."""
    ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR301",
        email="carrier@fleetco.example",
        full_name="Fleet Carrier",
        role_id="ROL009",
        role_name=RoleName.CARRIER,
        carrier_id="CAR001",
    )
    assert ctx.is_carrier
    assert ctx.can_read_carrier("CAR001")
    assert not ctx.can_read_carrier("CAR002")
    assert not ctx.can_read_carrier(None)
    # A carrier persona must never be treated as facility-scoped or globally read-capable --
    # it is a third, independent scoping dimension (facility / carrier / driver), not a variant
    # of either existing one.
    assert not ctx.is_operator
    assert not ctx.has_global_read_scope
    assert not ctx.can_read_facility("FAC-JAI-01")


def _gate_officer_ctx(facility_id: str | None = "FAC-JAI-01") -> ExecutionContext:
    return ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR-GATE-01",
        email="gate.jaipur@setuhaul.com",
        full_name="Jaipur Gate Kiosk",
        role_id="ROL010",
        role_name=RoleName.GATE_OFFICER,
        facility_id=facility_id,
    )


def test_gate_officer_is_facility_scoped_but_not_an_operator():
    """Issue #79: the kiosk role reads its own facility and nothing else.

    The `not ctx.is_operator` assertion is the load-bearing one. `is_operator` is what
    `repositories.scope`'s escalation/takeover write gates check, and
    `UI-UX/00-foundations/auth-and-scoping.md`'s "What each role never sees" table gives this
    persona "Scheduling controls" as a never -- so a GATE_OFFICER that answered True here would
    have silently inherited exactly the authority the role was added to withhold.
    """
    ctx = _gate_officer_ctx()
    assert ctx.is_gate_officer
    assert not ctx.is_operator
    assert not ctx.is_admin
    assert not ctx.has_global_read_scope
    assert not ctx.is_driver
    assert not ctx.is_carrier
    assert ctx.can_read_facility("FAC-JAI-01")
    assert not ctx.can_read_facility("FAC-GGN-01")
    assert not ctx.can_read_carrier("CAR001")


def test_gate_officer_with_no_facility_mapping_reads_nothing():
    """A kiosk account whose facility was never set must refuse, not fall back to everything."""
    ctx = _gate_officer_ctx(facility_id=None)
    assert ctx.is_gate_officer
    assert not ctx.can_read_facility("FAC-JAI-01")
    assert not ctx.can_read_facility(None)


def test_no_other_role_is_a_gate_officer():
    for role in RoleName:
        if role is RoleName.GATE_OFFICER:
            continue
        ctx = ExecutionContext(
            request_id="r",
            auth_subject="sub",
            user_id="USR-X",
            email="x@setuhaul.com",
            full_name="X",
            role_id="ROL-X",
            role_name=role,
        )
        assert not ctx.is_gate_officer, role


def test_gate_officer_is_outside_the_ops_portal_role_group():
    """The narrowing half of issue #79.

    Adding GATE_OFFICER is only an improvement on the borrowed WAREHOUSE_PLANNER credential if
    the new role is strictly narrower. `OPS_PORTAL_ROLES` is the appointment confirm/reject,
    exception-console and search gate (`routers/scheduling.py`, `routers/operations.py`); the
    kiosk role must not be in it, now or later.
    """
    assert RoleName.GATE_OFFICER in GATE_KIOSK_ROLES
    assert RoleName.GATE_OFFICER not in OPS_PORTAL_ROLES
    # The kiosk gate is a strict narrowing of the ops portal in one direction only: every other
    # role that may work a kiosk is an ops-portal role too.
    assert set(GATE_KIOSK_ROLES) - {RoleName.GATE_OFFICER} < set(OPS_PORTAL_ROLES)


def test_gate_officer_permissions_carry_no_scheduling_or_rules_authority():
    """`auth-and-scoping.md`: "Gate officer never sees: Scheduling controls." """
    perms = ROLE_PERMISSIONS[RoleName.GATE_OFFICER]
    assert perms, "GATE_OFFICER must have an explicit permission list, not fall through to []"
    assert not [p for p in perms if p.startswith(("schedule:", "rules:", "operations:"))]
    assert not [p for p in perms if p.endswith("_global")]
    assert "checkin:write_facility" in perms


def test_non_carrier_roles_never_pass_can_read_carrier():
    """A cross-carrier-id refusal must be unconditional for every non-CARRIER role, including
    global-read roles -- can_read_carrier must not accidentally inherit has_global_read_scope."""
    admin_ctx = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR999",
        email="admin@setuhaul.com",
        full_name="Admin",
        role_id="ROL008",
        role_name=RoleName.ADMIN,
    )
    assert not admin_ctx.can_read_carrier("CAR001")

    carrier_ctx_no_scope = ExecutionContext(
        request_id="r",
        auth_subject="sub",
        user_id="USR302",
        email="carrier2@fleetco.example",
        full_name="Unscoped Carrier User",
        role_id="ROL009",
        role_name=RoleName.CARRIER,
        # carrier_id intentionally omitted -- e.g. a CARRIER user whose user_scopes row is
        # missing or not yet provisioned.
    )
    assert not carrier_ctx_no_scope.can_read_carrier("CAR001")
