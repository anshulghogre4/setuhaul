"""The internal jobs endpoint the M8 sweeper is triggered through (GitHub issue #20 / E1.5).

The point of these tests is that the route is *real and callable* and that its authentication fails
closed: an endpoint that releases dock capacity must not be reachable because a deploy forgot an
environment variable.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.routers import internal
from app.core.errors import AppError
from app.core.settings import Settings, get_settings
from app.main import create_app
from app.scheduling.expiry import HeldSweepResult, SweepResult


def _request() -> MagicMock:
    request = MagicMock()
    request.state.request_id = "req-sweep-1"
    return request


def _empty_sweep() -> SweepResult:
    return SweepResult(
        as_of="2026-08-13T06:30:00+00:00",
        pending_ttl_minutes=15,
        pending_deadline="2026-08-13T06:15:00+00:00",
        batch_limit=50,
        held=HeldSweepResult(supported=False, ttl_seconds=90, unsupported_reason="not yet"),
    )


def test_route_is_registered_on_the_app():
    get_settings.cache_clear()
    app = create_app()
    paths = app.openapi()["paths"]

    assert "/internal/jobs/expiry-sweep" in paths
    assert "post" in paths["/internal/jobs/expiry-sweep"]
    # No request body at all, and specifically no caller-supplied `now` -- see app/core/clock.py.
    assert "requestBody" not in paths["/internal/jobs/expiry-sweep"]["post"]


def test_unconfigured_token_refuses_with_503_rather_than_running_open():
    with pytest.raises(AppError) as exc:
        internal.require_job_token(Settings(job_auth_token=""), "anything")

    assert exc.value.code == "JOB_AUTH_UNCONFIGURED"
    assert exc.value.status_code == 503


def test_missing_token_header_is_rejected():
    with pytest.raises(AppError) as exc:
        internal.require_job_token(Settings(job_auth_token="s3cret"), None)

    assert exc.value.code == "JOB_AUTH_INVALID"
    assert exc.value.status_code == 401


def test_wrong_token_is_rejected():
    with pytest.raises(AppError) as exc:
        internal.require_job_token(Settings(job_auth_token="s3cret"), "s3cre")

    assert exc.value.code == "JOB_AUTH_INVALID"
    assert exc.value.status_code == 401


def test_correct_token_is_accepted_and_tolerates_surrounding_whitespace():
    settings = Settings(job_auth_token="s3cret")
    assert internal.require_job_token(settings, " s3cret ") is settings


@pytest.mark.asyncio
async def test_sweep_refuses_when_the_audit_actor_is_unconfigured():
    settings = Settings(job_auth_token="s3cret", job_actor_user_id="")

    with pytest.raises(AppError) as exc:
        await internal.run_expiry_sweep(_request(), settings, AsyncMock())

    assert exc.value.code == "SWEEPER_ACTOR_UNCONFIGURED"
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_sweep_passes_the_configured_ttls_and_batch_limit_through():
    settings = Settings(
        job_auth_token="s3cret",
        job_actor_user_id="USR-SYS",
        pending_confirmation_ttl_minutes=15,
        held_slot_ttl_seconds=90,
        expiry_sweep_batch_limit=25,
    )
    with patch(
        "app.api.v1.routers.internal.sweep_expired_appointments",
        new_callable=AsyncMock,
        return_value=_empty_sweep(),
    ) as sweep:
        response = await internal.run_expiry_sweep(_request(), settings, AsyncMock())

    sweep.assert_awaited_once()
    kwargs = sweep.await_args.kwargs
    assert kwargs["actor_user_id"] == "USR-SYS"
    assert kwargs["pending_ttl_minutes"] == 15
    assert kwargs["held_ttl_seconds"] == 90
    assert kwargs["batch_limit"] == 25
    # No `clock` argument crosses the HTTP boundary: the handler must not let a caller decide `now`.
    assert "clock" not in kwargs
    assert response["success"] is True
    assert response["data"]["pending_expired"] == 0


@pytest.mark.asyncio
async def test_sweep_rolls_back_and_re_raises_on_failure():
    settings = Settings(job_auth_token="s3cret", job_actor_user_id="USR-SYS")
    session = AsyncMock()
    with patch(
        "app.api.v1.routers.internal.sweep_expired_appointments",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    ), pytest.raises(RuntimeError):
        await internal.run_expiry_sweep(_request(), settings, session)

    session.rollback.assert_awaited_once()
