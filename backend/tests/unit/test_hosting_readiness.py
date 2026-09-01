"""Sprint 4 step-1 host-readiness: CORS, chat alias, ARN switch, observability."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.assistant.agentcore_runtime import runtime_session_id
from app.assistant.observability import (
    child_invoke_config,
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
    cfg = observe_input(9, thread_id="THR-1", session_id="web-1")
    assert cfg["run_name"] == "setuhaul.chat"
    assert cfg["metadata"]["history_size_bucket"] == "9+"
    assert cfg["metadata"]["thread_id"] == "THR-1"
    assert cfg["metadata"]["session_id"] == "web-1"
    child = child_invoke_config(cfg, extra_metadata={"last_result_code": "answered"})
    assert "run_name" not in child
    assert child["metadata"]["thread_id"] == "THR-1"
    assert child["metadata"]["last_result_code"] == "answered"


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
        # Parameter names are kebab-case; env keys are UPPER_SNAKE. Asserted as a shape rather
        # than an allowlist of substrings (the old form here) because that allowlist would have
        # rejected GCP_PROJECT purely for not containing the word KEY/URL/TOKEN.
        assert name == name.lower()
        assert " " not in name
        assert env_key.isupper()
        assert env_key.replace("_", "").isalnum()
    # One env var must not be fed from two parameters -- last-write-wins would be silent.
    env_keys = [env_key for _, env_key in _SSM_ENV]
    assert len(env_keys) == len(set(env_keys))


def test_agentcore_ssm_map_carries_both_vertex_credentials():
    """Issue #103: the container had a Gemini provider and no Gemini credential, so AUTO_ORDER
    fell through to OpenAI on every production turn. These two entries are what make the Vertex
    leg reachable; the exact parameter names are the contract with the owner's SSM puts."""
    from app.assistant.agentcore_main import _SSM_ENV

    mapping = dict(_SSM_ENV)
    assert mapping["/setuhaul/gcp-project"] == "GCP_PROJECT"
    assert mapping["/setuhaul/gcp-sa-key"] == "GCP_SA_KEY_JSON"


def test_agentcore_ssm_env_keys_are_real_settings_fields():
    """A hydrated env var that no Settings field reads is a silent no-op -- which is the failure
    mode #103 is about, one layer down. GOOGLE_API_KEY/DATABASE_URL etc. all map to fields, and
    so must the two new Vertex ones."""
    from app.assistant.agentcore_main import _SSM_ENV
    from app.core.settings import Settings

    fields = set(Settings.model_fields)
    for _, env_key in _SSM_ENV:
        assert env_key.lower() in fields, f"{env_key} hydrates into nothing Settings reads"


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
