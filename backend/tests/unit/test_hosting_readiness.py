"""Sprint 4 step-1 host-readiness: CORS, chat alias, ARN switch, observability."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.assistant.agentcore_runtime import runtime_session_id
from app.assistant.observability import (
    get_history_size_bucket,
    observe_input,
    sanitize_for_trace,
    tool_outcome_metadata,
)
from app.core.execution_context import ExecutionContext, RoleName
from app.core.settings import Settings, get_settings
from app.main import create_app


def _driver_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="req-1",
        auth_subject="auth-1",
        user_id="USR001",
        email="ravi.kumar@setuhaul.com",
        full_name="Ravi Kumar",
        role_id="ROL001",
        role_name=RoleName.DRIVER,
        driver_id="DRV001",
        facility_id="FAC-JAI-01",
        permissions=["chat:own"],
    )


def test_agentcore_disabled_when_arn_blank():
    s = Settings(agentcore_runtime_arn="")
    assert s.agentcore_enabled is False


def test_agentcore_enabled_when_arn_set():
    s = Settings(agentcore_runtime_arn="arn:aws:bedrock-agentcore:us-east-1:123:runtime/x")
    assert s.agentcore_enabled is True


def test_langsmith_project_default():
    s = Settings()
    assert s.langsmith_project == "setuhaul-agentcore"


def test_runtime_session_id_is_long_and_stable():
    a = runtime_session_id("USR001", "web-abc")
    b = runtime_session_id("USR001", "web-abc")
    assert a == b
    assert len(a) >= 33
    assert "USR001" in a
    assert "Bearer" not in a


def test_history_buckets():
    assert get_history_size_bucket(0) == "0"
    assert get_history_size_bucket(3) == "1-4"
    assert get_history_size_bucket(7) == "5-8"
    assert get_history_size_bucket(12) == "9+"


def test_sanitize_redacts_secret_keys():
    out = sanitize_for_trace({"api_key": "secret", "shipment_id": "SHP1", "nested": {"token": "x"}})
    assert out["api_key"] == "[redacted]"
    assert out["shipment_id"] == "SHP1"
    assert out["nested"]["token"] == "[redacted]"


def test_observe_input_langsmith_shape():
    cfg = observe_input(9)
    assert cfg["run_name"] == "setuhaul.chat"
    assert cfg["metadata"]["history_size_bucket"] == "9+"


def test_tool_outcome_metadata_eta():
    meta = tool_outcome_metadata(
        [{"name": "confirm_eta", "result": {"status": "PERSISTED", "code": "ETA_UPDATED"}}],
        "persisted_success",
    )
    assert meta["eta_persisted"] is True
    assert meta["last_result_code"] == "ETA_UPDATED"


def test_chat_routes_include_message_alias():
    get_settings.cache_clear()
    app = create_app()
    paths = set(app.openapi()["paths"])
    assert "/api/v1/chat" in paths
    assert "/api/v1/chat/message" in paths
    assert "post" in app.openapi()["paths"]["/api/v1/chat"]
    assert "post" in app.openapi()["paths"]["/api/v1/chat/message"]


@pytest.mark.asyncio
async def test_driver_chat_blank_arn_uses_in_process():
    from app.api.v1.routers.chat import ChatRequest, _driver_chat

    settings = Settings(agentcore_runtime_arn="")
    body = ChatRequest(message="hello", session_id="web-1")
    request = MagicMock()
    request.state.request_id = "req-1"
    expected = {"thread_id": "THR-1", "session_id": "web-1", "response": "hi"}
    with (
        patch("app.api.v1.routers.chat.run_assistant", new_callable=AsyncMock, return_value=expected) as run,
        patch("app.api.v1.routers.chat.invoke_agentcore", new_callable=AsyncMock) as invoke,
    ):
        result = await _driver_chat(body, request, _driver_ctx(), MagicMock(), settings)
    run.assert_awaited_once()
    invoke.assert_not_called()
    assert result["data"]["response"] == "hi"


@pytest.mark.asyncio
async def test_driver_chat_arn_set_invokes_agentcore():
    from app.api.v1.routers.chat import ChatRequest, _driver_chat

    settings = Settings(agentcore_runtime_arn="arn:aws:bedrock-agentcore:us-east-1:1:runtime/x")
    body = ChatRequest(message="hello", session_id="web-1")
    request = MagicMock()
    request.state.request_id = "req-1"
    expected = {"thread_id": "THR-1", "session_id": "web-1", "response": "hosted"}
    with (
        patch("app.api.v1.routers.chat.run_assistant", new_callable=AsyncMock) as run,
        patch("app.api.v1.routers.chat.invoke_agentcore", new_callable=AsyncMock, return_value=expected) as invoke,
    ):
        result = await _driver_chat(body, request, _driver_ctx(), MagicMock(), settings)
    invoke.assert_awaited_once()
    run.assert_not_called()
    assert result["data"]["response"] == "hosted"


def test_cors_localhost_and_vercel_regex():
    get_settings.cache_clear()
    app = create_app()
    client = TestClient(app)
    local = client.options(
        "/health/live",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert local.headers.get("access-control-allow-origin") == "http://localhost:5173"
    vercel = client.options(
        "/health/live",
        headers={
            "Origin": "https://setuhaul-abc.vercel.app",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert vercel.headers.get("access-control-allow-origin") == "https://setuhaul-abc.vercel.app"


def test_agentcore_ssm_map_is_names_only():
    from app.assistant.agentcore_main import _SSM_ENV

    assert _SSM_ENV
    for name, env_key in _SSM_ENV:
        assert name.startswith("/setuhaul/")
        assert env_key.isupper()
        assert "KEY" in env_key or "URL" in env_key or "TOKEN" in env_key or env_key == "DATABASE_URL"


def test_agentcore_unwraps_cli_prompt_file_json():
    from app.assistant.agentcore_main import _normalize_runtime_payload

    inner = {
        "message": "Show my shipment",
        "execution_context": {"user_id": "USR001", "role_name": "DRIVER"},
    }
    wrapped = {"prompt": json.dumps(inner)}
    out = _normalize_runtime_payload(wrapped)
    assert out["message"] == "Show my shipment"
    assert out["execution_context"]["user_id"] == "USR001"
    already = _normalize_runtime_payload(inner)
    assert already is inner
