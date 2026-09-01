"""E7.2 / issue #46 — Sentry, backend half.

`DEPLOYMENT.md` §8 (D-3) makes Sentry responsible for unhandled exceptions with stack traces, the
one signal neither CloudWatch (rates, infra) nor LangSmith (inside a turn) produces. Issue #46's
own rollback note says the feature must be safe to disable by clearing the DSN, with no code
revert -- so the tests here are as much about the *off* path as the on one.

Two of these earn their place by checking something that could plausibly have been wrong:

* `test_an_unhandled_500_actually_reaches_sentry` -- this app registers a catch-all
  `app.add_exception_handler(Exception, ...)`, which is exactly the shape that usually *swallows*
  an error before an outer observer sees it. It works here only because Starlette's
  `ServerErrorMiddleware` re-raises after its handler has produced the response ("We always
  continue to raise the exception", verified in the installed starlette source), and Sentry's ASGI
  middleware is installed outside it. That is a two-library interaction, not something to assume.

* `test_empty_dsn_does_not_even_import_the_sdk` -- "gated on a setting" usually means `init()` is
  skipped. Issue #46 asks for less than that: no import, so no `sys.excepthook`, no patched ASGI
  app and no background transport thread in a deployment that never configured Sentry.
"""

from __future__ import annotations

import sys

import pytest
from fastapi.testclient import TestClient

from app.assistant.observability import init_sentry, sentry_before_send
from app.core.settings import Settings

_FAKE_DSN = "https://examplekey@o0.ingest.sentry.io/0"


@pytest.fixture
def sentry_events():
    """Initialise Sentry against an in-memory transport, and always tear it back down.

    `sentry_sdk.init` sets a process-global client, so without the teardown this fixture would
    leave every later test in the session reporting into it. Re-initialising with an empty DSN
    yields an inactive client, which is the SDK's own documented "disabled" state.
    """
    import sentry_sdk

    captured: list[dict] = []
    yield captured, sentry_sdk
    sentry_sdk.init(dsn="")


def _init_with_capture(sentry_sdk, captured, settings):
    """Run the real `init_sentry`, then swap only the egress for an in-memory sink.

    Swapping `client.transport` after the fact rather than re-initialising with
    `init(**client.options)`: the client's options dict is *computed*, and carries derived keys
    (`data_collection`) that `init()` rejects as unknown -- so a round trip through it fails, and
    would in any case be testing a configuration `init_sentry` never produced. This way every
    assertion below is about the options the production path actually chose.
    """
    from sentry_sdk.transport import Transport

    class _CapturingTransport(Transport):
        # Subclassing `Transport` is what the SDK documents; the older "pass a callable" form is
        # marked DEPRECATED in `_FunctionTransport`'s own docstring in the pinned 2.68.1.
        def capture_envelope(self, envelope) -> None:
            event = envelope.get_event()
            if event is not None:
                captured.append(event)

    assert init_sentry(settings) is True
    sentry_sdk.get_client().transport = _CapturingTransport()


# --------------------------------------------------------------------------------------------
# The off path -- every environment today
# --------------------------------------------------------------------------------------------


def test_empty_dsn_does_not_even_import_the_sdk(monkeypatch, caplog):
    """Blocking the import proves the DSN check happens *before* it.

    `sys.modules[name] = None` makes any `import name` raise `ImportError`, so if `init_sentry`
    reached its import statement this call would take the warning branch and log. It returns False
    silently instead, which is what "ships dark" has to mean.
    """
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)

    with caplog.at_level("WARNING"):
        assert init_sentry(Settings(sentry_dsn="")) is False

    assert caplog.records == []


def test_a_whitespace_only_dsn_counts_as_absent(monkeypatch):
    """SSM parameters routinely arrive with a trailing newline. A DSN of "\\n" is not a DSN, and
    treating it as one would send `sentry_sdk.init` a malformed URL at startup."""
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)

    assert init_sentry(Settings(sentry_dsn="   \n ")) is False
    assert Settings(sentry_dsn="   \n ").sentry_enabled is False
    assert Settings(sentry_dsn=_FAKE_DSN).sentry_enabled is True


def test_a_configured_dsn_with_no_sdk_installed_warns_rather_than_crashing(monkeypatch, caplog):
    """A real deployment mistake -- worth a log line, never worth refusing to boot the API."""
    monkeypatch.setitem(sys.modules, "sentry_sdk", None)

    with caplog.at_level("WARNING"):
        assert init_sentry(Settings(sentry_dsn=_FAKE_DSN)) is False

    assert any("sentry-sdk is not installed" in r.message for r in caplog.records)


def test_a_malformed_dsn_does_not_stop_the_api_from_starting(caplog):
    """Observability must never be the reason the service is down."""
    with caplog.at_level("WARNING"):
        assert init_sentry(Settings(sentry_dsn="not-a-url")) is False

    assert any("sentry init failed" in r.message for r in caplog.records)


def test_create_app_still_builds_with_no_dsn():
    """The realistic startup path today: `create_app` calls `init_sentry`, which no-ops."""
    from app.core.settings import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    app = create_app()

    assert "/api/v1/chat" in set(app.openapi()["paths"])


# --------------------------------------------------------------------------------------------
# The on path
# --------------------------------------------------------------------------------------------


def test_init_carries_environment_release_and_a_small_sample_rate(sentry_events):
    _captured, sentry_sdk = sentry_events
    settings = Settings(
        sentry_dsn=_FAKE_DSN,
        environment="production",
        sentry_release="abc1234",
        sentry_traces_sample_rate=0.1,
    )

    assert init_sentry(settings) is True

    options = sentry_sdk.get_client().options
    assert options["environment"] == "production"
    assert options["release"] == "abc1234"
    assert options["traces_sample_rate"] == 0.1


def test_a_blank_release_defers_to_sentrys_own_detection_never_an_empty_string(sentry_events):
    """Found by running this, not by reading the docs: a blank setting is *better* than expected.

    Passing `release=None` makes Sentry call its own `get_default_release()`, which reads
    `SENTRY_RELEASE` and then falls back to the git HEAD SHA -- so in this repo an unset
    `sentry_release` already yields the current commit, correctly-versioned, with no deploy-script
    work at all. What must never happen is `release=""`, which Sentry would take as a real release
    name and group every event ever sent under it. Asserted as "not empty" rather than "equals the
    SHA", because a container built without a `.git` directory legitimately produces `None`.
    """
    _captured, sentry_sdk = sentry_events

    assert init_sentry(Settings(sentry_dsn=_FAKE_DSN, sentry_release="  ")) is True

    release = sentry_sdk.get_client().options["release"]
    assert release != ""
    assert release is None or isinstance(release, str)


def test_pii_and_request_bodies_are_never_sent(sentry_events):
    """The residency-sensitive assertion.

    Sentry's own FastAPI quickstart sets `send_default_pii=True`; this project must not. Driver
    names, phone numbers and shipment references are exactly what these endpoints carry, and
    `max_request_body_size="never"` closes the same hole one layer down for a 500 on a booking
    write.
    """
    _captured, sentry_sdk = sentry_events

    assert init_sentry(Settings(sentry_dsn=_FAKE_DSN)) is True

    options = sentry_sdk.get_client().options
    assert options["send_default_pii"] is False
    assert options["max_request_body_size"] == "never"


def test_an_unhandled_500_actually_reaches_sentry(sentry_events):
    """End to end through the real app, past the catch-all exception handler.

    Ordering matters and is the reason this is not a unit test of `init_sentry`: the
    Starlette/FastAPI integrations patch middleware construction, so the app has to be built
    *after* init -- which is precisely why `create_app` calls `init_sentry` before `FastAPI(...)`
    rather than from the lifespan.
    """
    captured, sentry_sdk = sentry_events
    from app.core.settings import get_settings
    from app.main import create_app

    _init_with_capture(sentry_sdk, captured, Settings(sentry_dsn=_FAKE_DSN))

    get_settings.cache_clear()
    app = create_app()

    @app.get("/__boom__")
    async def _boom() -> dict:
        raise RuntimeError("dock allocator exploded")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/__boom__")

    # The driver still gets the project's own error envelope, unchanged by Sentry's presence.
    assert response.status_code == 500
    sentry_sdk.get_client().flush()
    assert any(
        "dock allocator exploded" in str(event.get("exception", "")) for event in captured
    ), f"no Sentry event carried the exception; captured={[e.get('level') for e in captured]}"


def test_a_handled_http_error_is_not_reported_as_a_crash(sentry_events):
    """404 is the product working. If routine refusals were events, the signal D-3 wants would
    drown in them."""
    captured, sentry_sdk = sentry_events
    from app.core.settings import get_settings
    from app.main import create_app

    _init_with_capture(sentry_sdk, captured, Settings(sentry_dsn=_FAKE_DSN))
    get_settings.cache_clear()
    client = TestClient(create_app(), raise_server_exceptions=False)

    assert client.get("/no-such-route").status_code == 404

    sentry_sdk.get_client().flush()
    assert captured == []


# --------------------------------------------------------------------------------------------
# Redaction
# --------------------------------------------------------------------------------------------


def test_secret_shaped_values_are_redacted_before_an_event_leaves():
    """`send_default_pii=False` stops headers and bodies; it says nothing about stack-frame
    locals, which Sentry sends by default and which on this codebase can hold a service-role key.

    The rule reused here is the one LangSmith traces already apply, so the two channels cannot
    drift apart into two different definitions of "secret".
    """
    event = {
        "exception": {"values": [{"stacktrace": {"frames": [{"vars": {
            "supabase_service_role_key": "sb-secret-value",
            "authorization": "Bearer abc.def.ghi",
            "shipment_id": "SHP-001",
        }}]}}]},
        "extra": {"api_key": "sk-live-123", "dock_id": "DCK-7"},
    }

    scrubbed = sentry_before_send(event)

    frame_vars = scrubbed["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]
    assert frame_vars["supabase_service_role_key"] == "[redacted]"
    assert frame_vars["authorization"] == "[redacted]"
    assert scrubbed["extra"]["api_key"] == "[redacted]"
    # Operational identifiers are not secrets and must survive -- a redacted event nobody can act
    # on is as useless as no event.
    assert frame_vars["shipment_id"] == "SHP-001"
    assert scrubbed["extra"]["dock_id"] == "DCK-7"


def test_redaction_fails_closed(monkeypatch, caplog):
    """Losing one crash report is recoverable. Publishing a service-role key to a third party is
    not, so a scrubber that raises must drop the event rather than pass it through."""
    from app.assistant import observability as obs

    def _explode(_value):
        raise RuntimeError("scrubber broke")

    monkeypatch.setattr(obs, "sanitize_for_trace", _explode)

    with caplog.at_level("WARNING"):
        assert obs.sentry_before_send({"extra": {"api_key": "sk-live-123"}}) is None

    assert any("redaction failed" in r.message for r in caplog.records)


# --------------------------------------------------------------------------------------------
# Deployment wiring
# --------------------------------------------------------------------------------------------


def test_the_agentcore_ssm_map_carries_the_sentry_dsn_parameter():
    """AgentCore never runs the FastAPI lifespan, so it hydrates its own secrets. Without this
    entry the agent process -- where the LLM turn actually runs -- would be the one place Sentry
    could not see a crash."""
    from app.assistant.agentcore_main import _SSM_ENV

    assert ("/setuhaul/sentry-dsn", "SENTRY_DSN") in _SSM_ENV


def test_sentry_ships_in_the_agentcore_codezip_dependency_list():
    """`stage_agentcore_codezip.py` builds the artifact's requirements from
    `[project.dependencies]`. If sentry-sdk were an extra instead, the deployed agent would import
    nothing and #46 would be half-delivered without any test noticing."""
    import tomllib
    from pathlib import Path

    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    deps = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["dependencies"]

    assert any(d.startswith("sentry-sdk") for d in deps)
