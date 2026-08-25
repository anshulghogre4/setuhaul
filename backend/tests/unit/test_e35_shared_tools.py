"""E3.5 (issue #29, M3) tests for the SS7.5.8 shared/cross-cutting tools: account profile,
password reset, sign-out-everywhere, notifications/preferences, and search_records.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.core.settings import Settings
from app.services import account_service, notification_service, search_service

FACILITY = "FAC-JAI-01"


def _ops_ctx(*, role: RoleName = RoleName.OPERATIONS_EXECUTIVE, facility_id: str | None = FACILITY, user_id: str = "USR-OPS-1") -> ExecutionContext:
    return ExecutionContext(
        request_id="req-1", auth_subject="sub-1", user_id=user_id, email="ops@setuhaul.com",
        full_name="Ops Coordinator", role_id="ROL002", role_name=role, facility_id=facility_id,
    )


def _session_with(*results) -> AsyncMock:
    mocks = []
    for r in results:
        m = MagicMock()
        if isinstance(r, list):
            m.mappings.return_value.all.return_value = r
            m.scalars.return_value.all.return_value = r
        else:
            m.mappings.return_value.first.return_value = r
        mocks.append(m)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=mocks)
    session.commit = AsyncMock()
    return session


# ---------------------------------------------------------------------------------------------
# get_account_profile
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_account_profile_returns_identity_and_scoped_facilities():
    user_row = {
        "user_id": "USR-OPS-1", "full_name": "Ops Coordinator", "email": "ops@setuhaul.com",
        "phone_number": None, "employee_code": "EMP-1", "role_name": "OPERATIONS_EXECUTIVE",
        "facility_id": FACILITY, "driver_id": None, "is_active": 1, "last_login_ts": None,
    }
    session = _session_with(user_row, ["FAC-JAI-01", "FAC-GGN-01"])
    result = await account_service.get_account_profile(session, _ops_ctx())
    assert result["user_id"] == "USR-OPS-1"
    assert result["scoped_facility_ids"] == ["FAC-JAI-01", "FAC-GGN-01"]


@pytest.mark.asyncio
async def test_get_account_profile_raises_not_found_for_a_missing_user():
    session = _session_with(None)
    with pytest.raises(AppError) as exc:
        await account_service.get_account_profile(session, _ops_ctx())
    assert exc.value.code == "NOT_FOUND"


# ---------------------------------------------------------------------------------------------
# request_password_reset / sign_out_everywhere -- Supabase Auth proxies.
# ---------------------------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class _FakeAsyncClient:
    """Records every request made through it; `_FakeAsyncClient.calls` is class-level so the
    test can inspect it after the `async with` block exits."""

    calls: list[dict] = []
    response: _FakeResponse = _FakeResponse()
    raise_on_post: Exception | None = None

    def __init__(self, *_a, **_k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_a):
        return False

    async def post(self, url, **kwargs):
        _FakeAsyncClient.calls.append({"url": url, **kwargs})
        if _FakeAsyncClient.raise_on_post:
            raise _FakeAsyncClient.raise_on_post
        return _FakeAsyncClient.response


@pytest.fixture(autouse=True)
def _reset_fake_client():
    _FakeAsyncClient.calls = []
    _FakeAsyncClient.response = _FakeResponse()
    _FakeAsyncClient.raise_on_post = None
    yield


def _settings() -> Settings:
    return Settings(supabase_url="https://proj.supabase.co", supabase_anon_key="anon-key-not-real")


@pytest.mark.asyncio
async def test_request_password_reset_calls_recover_with_the_anon_key(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    result = await account_service.request_password_reset(_settings(), "driver@setuhaul.com")

    assert result.code == "RESET_REQUESTED"
    assert len(_FakeAsyncClient.calls) == 1
    call = _FakeAsyncClient.calls[0]
    assert call["url"].endswith("/auth/v1/recover")
    assert call["json"] == {"email": "driver@setuhaul.com"}
    assert call["headers"]["apikey"] == "anon-key-not-real"


@pytest.mark.asyncio
async def test_request_password_reset_returns_the_same_result_on_a_transport_failure(monkeypatch):
    """Enumeration-safety: a network hiccup must not be distinguishable from a real send."""
    import httpx
    _FakeAsyncClient.raise_on_post = httpx.ConnectError("boom")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    result = await account_service.request_password_reset(_settings(), "nobody@setuhaul.com")

    assert result.code == "RESET_REQUESTED"


@pytest.mark.asyncio
async def test_sign_out_everywhere_uses_the_callers_own_bearer_token_not_service_role(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    result = await account_service.sign_out_everywhere(_settings(), "caller-own-access-token")

    assert result.code == "SIGNED_OUT_EVERYWHERE"
    call = _FakeAsyncClient.calls[0]
    assert "scope=global" in call["url"]
    assert call["headers"]["Authorization"] == "Bearer caller-own-access-token"
    assert "service" not in call["headers"].get("apikey", "").lower()


@pytest.mark.asyncio
async def test_sign_out_everywhere_raises_on_a_supabase_error_response(monkeypatch):
    import httpx
    _FakeAsyncClient.response = _FakeResponse(status_code=401, text="invalid token")
    monkeypatch.setattr(httpx, "AsyncClient", _FakeAsyncClient)

    with pytest.raises(AppError) as exc:
        await account_service.sign_out_everywhere(_settings(), "bad-token")
    assert exc.value.code == "AUTH_SIGN_OUT_FAILED"


# ---------------------------------------------------------------------------------------------
# notifications / preferences
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_notifications_scopes_to_the_callers_own_feed():
    rows = [
        {"notification_id": "N1", "category": "ESCALATION", "title": "t", "body": "b",
         "related_entity_type": None, "related_entity_id": None, "is_read": 0,
         "created_at": "2026-08-25T00:00:00+00:00", "read_at": None},
    ]
    session = _session_with(rows)
    result = await notification_service.get_notifications(session, _ops_ctx())
    assert result["items"][0]["notification_id"] == "N1"
    params = session.execute.call_args.args[1]
    assert params["user_id"] == "USR-OPS-1"


@pytest.mark.asyncio
async def test_mark_notifications_read_is_a_no_op_for_an_empty_list():
    session = AsyncMock()
    session.execute = AsyncMock()
    result = await notification_service.mark_notifications_read(session, _ops_ctx(), [])
    assert result["marked_count"] == 0
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_mark_notifications_read_reports_the_rowcount():
    session = AsyncMock()
    exec_result = MagicMock()
    exec_result.rowcount = 2
    session.execute = AsyncMock(return_value=exec_result)
    session.commit = AsyncMock()
    result = await notification_service.mark_notifications_read(session, _ops_ctx(), ["N1", "N2"])
    assert result["code"] == "READ"
    assert result["marked_count"] == 2


@pytest.mark.asyncio
async def test_get_notification_preferences_fills_in_defaults_for_unset_categories():
    session = _session_with([{"category": "ESCALATION", "channel_web_push": 0, "channel_email": 1, "digest_mode": 1, "updated_at": "x"}])
    result = await notification_service.get_notification_preferences(session, _ops_ctx())
    by_category = {c["category"]: c for c in result["categories"]}
    assert by_category["ESCALATION"]["channel_web_push"] == 0
    assert by_category["APPOINTMENT"]["channel_web_push"] == 1  # default, never saved
    assert set(by_category) == {"ESCALATION", "APPOINTMENT", "SYSTEM"}


@pytest.mark.asyncio
async def test_update_notification_preferences_rejects_an_unknown_category():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await notification_service.update_notification_preferences(
            session, _ops_ctx(), [{"category": "MARKETING"}]
        )
    assert exc.value.code == "INVALID_CATEGORY"


@pytest.mark.asyncio
async def test_update_notification_preferences_requires_at_least_one_category():
    session = AsyncMock()
    with pytest.raises(AppError) as exc:
        await notification_service.update_notification_preferences(session, _ops_ctx(), [])
    assert exc.value.code == "INVALID_PREFERENCES"


# ---------------------------------------------------------------------------------------------
# search_records
# ---------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_records_refuses_a_driver():
    driver_ctx = ExecutionContext(
        request_id="r", auth_subject="s", user_id="USR001", email="d@setuhaul.com",
        full_name="Driver", role_id="ROL001", role_name=RoleName.DRIVER, driver_id="DRV001",
    )
    session = AsyncMock()
    with pytest.raises(AppError) as exc:
        await search_service.search_records(session, driver_ctx, "SHP1017")
    assert exc.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_search_records_rejects_a_too_short_query():
    session = AsyncMock()
    with pytest.raises(AppError) as exc:
        await search_service.search_records(session, _ops_ctx(), "a")
    assert exc.value.code == "QUERY_TOO_SHORT"


@pytest.mark.asyncio
async def test_search_records_rejects_an_unknown_entity_type():
    session = AsyncMock()
    with pytest.raises(AppError) as exc:
        await search_service.search_records(session, _ops_ctx(), "SHP1017", ["invoices"])
    assert exc.value.code == "INVALID_ENTITY_TYPE"


@pytest.mark.asyncio
async def test_search_records_composes_only_the_requested_entity_types(monkeypatch):
    shipments_mock = AsyncMock(return_value=[{"shipment_id": "SHP1017"}])
    drivers_mock = AsyncMock(return_value=[{"driver_id": "DRV001"}])
    monkeypatch.setattr(search_service, "_search_shipments", shipments_mock)
    monkeypatch.setattr(search_service, "_search_drivers", drivers_mock)
    session = AsyncMock()

    result = await search_service.search_records(session, _ops_ctx(), "SHP1017", ["shipments"])

    assert "shipments" in result["results"]
    assert "drivers" not in result["results"]
    shipments_mock.assert_awaited_once()
    drivers_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_records_scopes_to_the_callers_own_facility(monkeypatch):
    shipments_mock = AsyncMock(return_value=[])
    drivers_mock = AsyncMock(return_value=[])
    monkeypatch.setattr(search_service, "_search_shipments", shipments_mock)
    monkeypatch.setattr(search_service, "_search_drivers", drivers_mock)
    session = AsyncMock()

    await search_service.search_records(session, _ops_ctx(facility_id=FACILITY), "SHP1017")

    assert shipments_mock.await_args.kwargs["facility_id"] == FACILITY
