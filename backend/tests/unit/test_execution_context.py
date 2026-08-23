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
