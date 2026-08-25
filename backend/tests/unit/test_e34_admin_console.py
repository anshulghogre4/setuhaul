"""E3.4 (issue #28, M3) tests for the SS7.5.7 admin console: users/roles, facility rules,
policy simulate/publish, and audit.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.core.settings import Settings
from app.services import admin_governance_service, admin_user_service

FACILITY = "FAC-JAI-01"


def _admin_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="r", auth_subject="s", user_id="USR-ADMIN-1", email="admin@setuhaul.com",
        full_name="Admin", role_id="ROL008", role_name=RoleName.ADMIN,
    )


def _non_admin_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="r", auth_subject="s", user_id="USR-OPS-1", email="ops@setuhaul.com",
        full_name="Ops", role_id="ROL002", role_name=RoleName.OPERATIONS_EXECUTIVE, facility_id=FACILITY,
    )


def _session_with(*results) -> AsyncMock:
    mocks = []
    for r in results:
        m = MagicMock()
        if isinstance(r, list):
            m.mappings.return_value.all.return_value = r
        else:
            m.mappings.return_value.first.return_value = r
            m.mappings.return_value.one.return_value = r
        mocks.append(m)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=mocks)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _settings() -> Settings:
    return Settings(supabase_url="https://proj.supabase.co", supabase_service_role_key="service-key-not-real")


@pytest.fixture(autouse=True)
def _no_idempotency_replay(monkeypatch):
    monkeypatch.setattr(admin_user_service, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(admin_user_service, "store_idempotency", AsyncMock())
    monkeypatch.setattr(admin_governance_service, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(admin_governance_service, "store_idempotency", AsyncMock())


# ---------------------------------------------------------------------------------------------
# Role gate -- every admin tool refuses a non-admin, checked once as a representative sample.
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_users_refuses_a_non_admin():
    session = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_user_service.list_users(session, _non_admin_ctx())
    assert exc.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_simulate_policy_weights_refuses_a_non_admin():
    session = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_governance_service.simulate_policy_weights(
            session, _non_admin_ctx(), weights={},
            window_start=datetime.now(timezone.utc), window_end=datetime.now(timezone.utc) + timedelta(days=7),
        )
    assert exc.value.code == "FORBIDDEN"


# ---------------------------------------------------------------------------------------------
# invite_user / Supabase Auth Admin API proxy
# ---------------------------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code=200, json_body=None, text=""):
        self.status_code = status_code
        self._json = json_body or {}
        self.text = text

    def json(self):
        return self._json


class _FakeAsyncClient:
    calls: list[dict] = []
    post_response: _FakeResponse = _FakeResponse(json_body={"id": "auth-uuid-1"})
    delete_response: _FakeResponse = _FakeResponse()

    def __init__(self, *_a, **_k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def post(self, url, **kwargs):
        _FakeAsyncClient.calls.append({"method": "post", "url": url, **kwargs})
        return _FakeAsyncClient.post_response

    async def delete(self, url, **kwargs):
        _FakeAsyncClient.calls.append({"method": "delete", "url": url, **kwargs})
        return _FakeAsyncClient.delete_response


@pytest.fixture(autouse=True)
def _reset_fake_client():
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.post_response = _FakeResponse(json_body={"id": "auth-uuid-1"})
    _FakeAsyncClient.delete_response = _FakeResponse()
    yield


@pytest.mark.asyncio
async def test_invite_user_creates_the_auth_identity_and_the_local_row_together(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    session = _session_with(
        {"facility_id": FACILITY},  # _validate_scope facility existence check
        {"role_id": "ROL003"},  # _resolve_role_id
        None,  # INSERT users
        None,  # INSERT audit_logs
    )

    result = await admin_user_service.invite_user(
        session, _admin_ctx(), _settings(), email="new.planner@setuhaul.com", role="WAREHOUSE_PLANNER", scope=FACILITY,
    )

    assert result["code"] == "INVITED"
    invite_call = next(c for c in _FakeAsyncClient.calls if c["method"] == "post")
    assert invite_call["url"].endswith("/auth/v1/invite")
    assert invite_call["json"] == {"email": "new.planner@setuhaul.com"}


@pytest.mark.asyncio
async def test_invite_user_rejects_an_unknown_role_before_calling_auth():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_user_service.invite_user(
            session, _admin_ctx(), _settings(), email="x@setuhaul.com", role="SUPERUSER", scope=None,
        )
    assert exc.value.code == "INVALID_ROLE"
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_invite_user_requires_a_scope_for_a_facility_scoped_role():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_user_service.invite_user(
            session, _admin_ctx(), _settings(), email="x@setuhaul.com", role="WAREHOUSE_PLANNER", scope=None,
        )
    assert exc.value.code == "SCOPE_REQUIRED"


@pytest.mark.asyncio
async def test_invite_user_rejects_a_facility_that_does_not_exist():
    session = _session_with(None)  # facility existence check returns nothing
    with pytest.raises(AppError) as exc:
        await admin_user_service.invite_user(
            session, _admin_ctx(), _settings(), email="x@setuhaul.com", role="WAREHOUSE_PLANNER", scope="FAC-GHOST",
        )
    assert exc.value.code == "INVALID_SCOPE"


@pytest.mark.asyncio
async def test_invite_user_accepts_a_global_role_with_no_scope(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    # ADMIN is a global role: _validate_scope returns immediately with no DB call, so only
    # resolve_role_id + INSERT users + INSERT audit_logs run.
    session = _session_with({"role_id": "ROL008"}, None, None)
    result = await admin_user_service.invite_user(
        session, _admin_ctx(), _settings(), email="admin2@setuhaul.com", role="ADMIN", scope=None,
    )
    assert result["code"] == "INVITED"


@pytest.mark.asyncio
async def test_invite_user_reports_auth_failure_without_touching_postgres(monkeypatch):
    import httpx
    _FakeAsyncClient.post_response = _FakeResponse(status_code=422, text="email already registered")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    # validate_scope's facility check, then resolve_role_id -- both run before the Auth call.
    session = _session_with({"facility_id": FACILITY}, {"role_id": "ROL003"})

    with pytest.raises(AppError) as exc:
        await admin_user_service.invite_user(
            session, _admin_ctx(), _settings(), email="dup@setuhaul.com", role="WAREHOUSE_PLANNER", scope=FACILITY,
        )
    assert exc.value.code == "AUTH_INVITE_FAILED"


# ---------------------------------------------------------------------------------------------
# update_user / deactivate / reactivate
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_user_changes_role_and_scope():
    session = _session_with({"user_id": "USR1"}, {"facility_id": FACILITY}, {"role_id": "ROL005"}, None)
    result = await admin_user_service.update_user(session, _admin_ctx(), user_id="USR1", role="FACILITY_MANAGER", scope=FACILITY)
    assert result["code"] == "UPDATED"


@pytest.mark.asyncio
async def test_update_user_raises_not_found():
    session = _session_with(None)
    with pytest.raises(AppError) as exc:
        await admin_user_service.update_user(session, _admin_ctx(), user_id="USR-GHOST")
    assert exc.value.code == "NOT_FOUND"


@pytest.mark.asyncio
async def test_deactivate_then_reactivate_user():
    session = _session_with({"user_id": "USR1", "is_active": 0})
    result = await admin_user_service.deactivate_user(session, _admin_ctx(), "USR1")
    assert result["code"] == "DEACTIVATED"

    session2 = _session_with({"user_id": "USR1", "is_active": 1})
    result2 = await admin_user_service.reactivate_user(session2, _admin_ctx(), "USR1")
    assert result2["code"] == "REACTIVATED"


# ---------------------------------------------------------------------------------------------
# remove_user
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_remove_user_requires_an_idempotency_key():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_user_service.remove_user(session, _admin_ctx(), _settings(), user_id="USR1", idempotency_key="")
    assert exc.value.code == "IDEMPOTENCY_KEY_REQUIRED"


@pytest.mark.asyncio
async def test_remove_user_deletes_the_auth_identity_and_deactivates_locally(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    session = _session_with({"user_id": "USR1", "auth_user_id": "auth-uuid-1"}, None, None)

    result = await admin_user_service.remove_user(session, _admin_ctx(), _settings(), user_id="USR1", idempotency_key="rm-1")

    assert result["code"] == "REMOVED"
    delete_call = next(c for c in _FakeAsyncClient.calls if c["method"] == "delete")
    assert "auth-uuid-1" in delete_call["url"]


@pytest.mark.asyncio
async def test_remove_user_treats_an_already_gone_auth_identity_as_success(monkeypatch):
    import httpx
    _FakeAsyncClient.delete_response = _FakeResponse(status_code=404)
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)
    session = _session_with({"user_id": "USR1", "auth_user_id": "auth-uuid-gone"}, None, None)

    result = await admin_user_service.remove_user(session, _admin_ctx(), _settings(), user_id="USR1", idempotency_key="rm-2")
    assert result["code"] == "REMOVED"


# ---------------------------------------------------------------------------------------------
# facility rules
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_facility_rule_rejects_an_unregistered_rule_type():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_governance_service.create_facility_rule(
            session, _admin_ctx(), facility_id=FACILITY, rule_type="MADE_UP_RULE", rule_value="1",
        )
    assert exc.value.code == "INVALID_RULE_TYPE"
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_facility_rule_accepts_a_registered_rule_type():
    session = _session_with({
        "rule_id": "RULE1", "facility_id": FACILITY, "rule_type": "NO_SHOW_GRACE_MIN",
        "rule_value": "15", "effective_from": None, "effective_to": None,
    })
    result = await admin_governance_service.create_facility_rule(
        session, _admin_ctx(), facility_id=FACILITY, rule_type="no_show_grace_min", rule_value="15",
    )
    assert result["code"] == "CREATED"


@pytest.mark.asyncio
async def test_update_facility_rule_raises_not_found():
    session = _session_with(None)
    with pytest.raises(AppError) as exc:
        await admin_governance_service.update_facility_rule(session, _admin_ctx(), rule_id="RULE-GHOST")
    assert exc.value.code == "NOT_FOUND"


# ---------------------------------------------------------------------------------------------
# simulate_policy_weights -- the formula-parity guard.
# ---------------------------------------------------------------------------------------------


def test_score_formula_matches_feasibility_pys_rank_slot_exactly():
    """The drift guard `admin_governance_service.py`'s own docstring promises: this module
    duplicates feasibility.py's scoring formula rather than importing it (deliberately, to avoid
    touching the live booking hot path) -- this test pins the two to the same output so a future
    edit to either without the other is caught, not silently diverging."""
    from app.scheduling.feasibility import _rank_slot

    shipment = {
        "shipment_id": "SHP-TEST", "priority_code": "HIGH",
        "original_eta_ts": "2026-08-25T10:00:00+00:00", "required_dock_type": "STANDARD",
    }
    eta_dt = datetime(2026, 8, 25, 10, 30, tzinfo=timezone.utc)
    candidate = {"dock_type": "STANDARD", "slot_id": "SLOT-TEST"}
    feasible_start = datetime(2026, 8, 25, 11, 0, tzinfo=timezone.utc)
    feasible_end = datetime(2026, 8, 25, 11, 45, tzinfo=timezone.utc)
    slot_end = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)

    live_score, _ = _rank_slot(
        shipment=shipment, eta_dt=eta_dt, candidate=candidate,
        feasible_start=feasible_start, feasible_end=feasible_end, slot_end=slot_end,
    )

    from app.scheduling.constraints import load_scheduling_constraints
    policy = load_scheduling_constraints().ranking_policy
    weights = policy.score_weights
    priority_scores = policy.priority_scores or admin_governance_service.DEFAULT_PRIORITY_SCORES

    lateness_minutes = max(0, int((eta_dt - datetime.fromisoformat(shipment["original_eta_ts"])).total_seconds() // 60))
    wait_after_eta_minutes = max(0, int((feasible_start - eta_dt).total_seconds() // 60))
    fit_slack_minutes = max(0, int((slot_end - feasible_end).total_seconds() // 60))

    copied_score = admin_governance_service._score(
        priority_code="HIGH", lateness_minutes=lateness_minutes, wait_after_eta_minutes=wait_after_eta_minutes,
        fit_slack_minutes=fit_slack_minutes, exact_dock_type_match=True, weights=weights, priority_scores=priority_scores,
    )

    assert copied_score == live_score


@pytest.mark.asyncio
async def test_publish_policy_version_requires_an_idempotency_key():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await admin_governance_service.publish_policy_version(session, _admin_ctx(), weights={"lateness_per_minute": 4}, idempotency_key="")
    assert exc.value.code == "IDEMPOTENCY_KEY_REQUIRED"


@pytest.mark.asyncio
async def test_publish_policy_version_clears_the_prior_active_row_first():
    session = _session_with(None, None)  # UPDATE clear prior active, INSERT new version
    result = await admin_governance_service.publish_policy_version(
        session, _admin_ctx(), weights={"lateness_per_minute": 5}, idempotency_key="pub-1"
    )
    assert result["code"] == "PUBLISHED"
    first_sql = str(session.execute.call_args_list[0].args[0])
    assert "is_active = 0" in first_sql


# ---------------------------------------------------------------------------------------------
# audit log
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_audit_log_applies_the_actor_filter():
    session = _session_with([])
    await admin_governance_service.get_audit_log(session, _admin_ctx(), actor="USR1")
    params = session.execute.call_args.args[1]
    assert params["actor"] == "USR1"


@pytest.mark.asyncio
async def test_export_audit_log_returns_csv_with_a_header_row():
    rows = [{"audit_id": "AUD1", "user_id": "USR1", "action_type": "CREATE", "entity_name": "users", "entity_id": "USR2", "created_at": "2026-08-25T00:00:00+00:00"}]
    session = _session_with(rows)
    csv_text = await admin_governance_service.export_audit_log(session, _admin_ctx())
    assert csv_text.splitlines()[0] == "audit_id,user_id,action_type,entity_name,entity_id,created_at"
    assert "AUD1" in csv_text
