"""Unit tests for multi-provider LLM factory."""

from __future__ import annotations

import json
import os
import stat

import pytest
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.assistant import llm as llm_module
from app.assistant.llm import (
    GEMINI_AI_STUDIO,
    GEMINI_VERTEX_ADC,
    GEMINI_VERTEX_EXPRESS,
    OPENROUTER_BASE_URL,
    build_chat_model,
    ensure_vertex_adc,
    resolve_llm,
)
from app.core.errors import AppError
from app.core.settings import DESIGNED_GCP_VERTEX_LOCATION, Settings

# A structurally valid service-account key shape. No real key material: `ensure_vertex_adc` only
# parses the JSON and checks for a `type` field, and nothing in these tests ever authenticates.
FAKE_SA_KEY = json.dumps(
    {
        "type": "service_account",
        "project_id": "proj-x",
        "private_key_id": "not-a-real-key-id",
        "client_email": "setuhaul-vertex@proj-x.iam.gserviceaccount.com",
    }
)


@pytest.fixture(autouse=True)
def _hermetic_adc(monkeypatch, tmp_path):
    """Neutralize whatever ADC the *host* happens to have.

    Gemini readiness now depends on real filesystem state (issue #103), so without this the
    suite would pass on the owner's laptop -- which has a `gcloud auth application-default
    login` file from #31 -- and fail in CI, which has neither that file nor GOOGLE_APPLICATION_
    CREDENTIALS. `CLOUDSDK_CONFIG` is the same override google-auth itself honours for the
    well-known path, so pointing it at an empty tmp dir is a faithful "no ADC on this machine".
    Also resets the module-level materialization latch so tests cannot leak into each other.
    """
    monkeypatch.setenv("CLOUDSDK_CONFIG", str(tmp_path / "no-gcloud-here"))
    monkeypatch.setattr(llm_module, "_adc_path", None, raising=False)
    # A host with either of these set would silently push the key path off Vertex express mode
    # onto AI Studio, so clear them for the same reason CLOUDSDK_CONFIG is redirected above.
    for name in llm_module._EXPRESS_DEFEATING_ENV:
        monkeypatch.delenv(name, raising=False)
    # Saved and restored by hand rather than with monkeypatch.delenv: `ensure_vertex_adc` assigns
    # os.environ directly, and monkeypatch only rolls back keys it was told about *before* the
    # assignment -- delenv(raising=False) on an absent key records nothing, so a materialization
    # inside the test would escape into every later test file in the session.
    previous = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
    try:
        yield
    finally:
        written = os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
        if written and written != previous and os.path.isfile(written):
            os.unlink(written)
        if previous is not None:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = previous


def _settings(**kwargs) -> Settings:
    base = {
        "openai_api_key": "",
        "openrouter_api_key": "",
        "google_api_key": "",
        "gcp_project": "",
        "gcp_sa_key_json": "",
        "gcp_vertex_location": DESIGNED_GCP_VERTEX_LOCATION,
        "llm_provider": "auto",
        "llm_model": "",
    }
    base.update(kwargs)
    return Settings(**base)


def _gemini_settings(**kwargs) -> Settings:
    """Gemini configured the way a provisioned container is: project + a credential.

    Issue #103 made `gcp_project` alone insufficient on purpose, so every Gemini test has to say
    which credential shape it is exercising instead of relying on the host's.
    """
    base = {"gcp_project": "proj-x", "gcp_sa_key_json": FAKE_SA_KEY}
    base.update(kwargs)
    return _settings(**base)


def test_auto_prefers_gemini_when_present():
    s = _gemini_settings(openai_api_key="sk-openai", openrouter_api_key="sk-or")
    r = resolve_llm(s)
    assert r.provider == "gemini"
    assert r.model == "gemini-3.7-flash"
    assert r.gcp_project == "proj-x"
    assert r.gcp_location == DESIGNED_GCP_VERTEX_LOCATION


def test_auto_falls_back_to_openai_when_gemini_not_configured():
    s = _settings(openai_api_key="sk-openai", openrouter_api_key="sk-or")
    r = resolve_llm(s)
    assert r.provider == "openai"
    assert r.model == "gpt-4o-mini"
    assert r.base_url is None
    assert r.api_key == "sk-openai"


def test_auto_falls_back_to_openrouter():
    s = _settings(openrouter_api_key="sk-or")
    r = resolve_llm(s)
    assert r.provider == "openrouter"
    assert r.model == "openai/gpt-4o-mini"
    assert r.base_url == OPENROUTER_BASE_URL


def test_auto_raises_when_no_keys():
    with pytest.raises(AppError) as ei:
        resolve_llm(_settings())
    assert ei.value.code == "LLM_UNAVAILABLE"
    assert ei.value.status_code == 503


def test_explicit_openrouter_requires_key():
    with pytest.raises(AppError) as ei:
        resolve_llm(_settings(llm_provider="openrouter", openai_api_key="sk-openai"))
    assert "OPENROUTER_API_KEY" in str(ei.value)


def test_explicit_gemini_uses_vertex_project():
    s = _gemini_settings(llm_provider="gemini", llm_model="gemini-3.7-flash")
    r = resolve_llm(s)
    assert r.provider == "gemini"
    assert r.gcp_project == "proj-x"
    assert r.gcp_location == DESIGNED_GCP_VERTEX_LOCATION
    assert r.api_key is None


def test_explicit_gemini_requires_gcp_project():
    with pytest.raises(AppError) as ei:
        resolve_llm(_settings(llm_provider="gemini"))
    assert "GCP_PROJECT" in str(ei.value)


def test_gemini_rejects_a_misconfigured_vertex_region():
    with pytest.raises(AppError) as ei:
        resolve_llm(_gemini_settings(llm_provider="gemini", gcp_vertex_location="us-central1"))
    assert ei.value.code == "LLM_UNAVAILABLE"
    assert "location mismatch" in str(ei.value).lower()


def test_llm_model_override():
    s = _settings(openai_api_key="sk-openai", llm_model="gpt-4o")
    r = resolve_llm(s)
    assert r.model == "gpt-4o"


def test_build_chat_model_openrouter_sets_base_url():
    s = _settings(openrouter_api_key="sk-or", llm_provider="openrouter")
    chat = build_chat_model(s)
    assert isinstance(chat, ChatOpenAI)
    base = getattr(chat, "openai_api_base", None) or getattr(chat, "base_url", None)
    assert base is not None
    assert "openrouter.ai" in str(base)


def test_build_chat_model_gemini_uses_google_class():
    s = _gemini_settings(llm_provider="gemini")
    chat = build_chat_model(s)
    assert isinstance(chat, ChatGoogleGenerativeAI)


def test_build_chat_model_gemini_uses_vertex_not_api_key():
    s = _gemini_settings(llm_provider="gemini")
    chat = build_chat_model(s)
    assert chat.vertexai is True
    assert chat.project == "proj-x"
    assert chat.location == DESIGNED_GCP_VERTEX_LOCATION
    assert chat.thinking_config == {"thinking_level": "high"}


# -------------------------------------------------------------------------------------------
# Issue #103 -- Vertex credentials inside a credential-less container.
# -------------------------------------------------------------------------------------------


def test_gemini_is_not_ready_on_project_alone():
    """The #103 regression guard. `GCP_PROJECT` with no credential anywhere used to select Gemini
    and then die inside the first live Vertex call; it must now simply not be ready."""
    s = _settings(gcp_project="proj-x")
    assert s.gcp_adc_available is False
    assert s.ready_gemini is False


def test_gemini_is_ready_on_project_plus_sa_key_json():
    assert _settings(gcp_project="proj-x", gcp_sa_key_json=FAKE_SA_KEY).ready_gemini is True


def test_gemini_is_ready_on_project_plus_an_adc_file(monkeypatch, tmp_path):
    """The #31 shape: the owner's laptop, or any host where ADC already exists. No SA key needed,
    and `ensure_vertex_adc` must not overwrite it."""
    adc = tmp_path / "application_default_credentials.json"
    adc.write_text(FAKE_SA_KEY, encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(adc))
    s = _settings(gcp_project="proj-x")
    assert s.gcp_adc_available is True
    assert s.ready_gemini is True


def test_gemini_is_ready_on_the_gcloud_well_known_file(monkeypatch, tmp_path):
    """Second step of google-auth's ADC chain -- `gcloud auth application-default login`."""
    config_dir = tmp_path / "gcloud-config"
    config_dir.mkdir()
    (config_dir / "application_default_credentials.json").write_text(FAKE_SA_KEY, encoding="utf-8")
    monkeypatch.setenv("CLOUDSDK_CONFIG", str(config_dir))
    assert _settings(gcp_project="proj-x").ready_gemini is True


def test_a_stale_credentials_path_is_not_treated_as_ready(monkeypatch, tmp_path):
    """GOOGLE_APPLICATION_CREDENTIALS pointing at nothing makes google.auth.default() raise rather
    than fall through, so "set" must not count as "ready"."""
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(tmp_path / "gone.json"))
    assert _settings(gcp_project="proj-x").gcp_adc_available is False


def test_auto_falls_through_to_openai_when_gemini_has_no_credential():
    """The production incident, asserted as intended behaviour: with a project but no credential,
    AUTO_ORDER must reach OpenAI cleanly rather than raising."""
    s = _settings(gcp_project="proj-x", openai_api_key="sk-openai")
    assert resolve_llm(s).provider == "openai"


def test_auto_raises_when_neither_credential_shape_exists():
    with pytest.raises(AppError) as ei:
        resolve_llm(_settings(gcp_project="proj-x"))
    assert ei.value.code == "LLM_UNAVAILABLE"


def test_ensure_vertex_adc_writes_the_key_once_and_sets_the_env_var():
    s = _gemini_settings()
    first = ensure_vertex_adc(s)

    assert first is not None
    assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == first
    assert json.loads(open(first, encoding="utf-8").read())["type"] == "service_account"
    if os.name != "nt":
        # 0600: the key must not be group- or world-readable inside the container.
        assert stat.S_IMODE(os.stat(first).st_mode) == 0o600

    # Idempotent: a second call is a no-op because the env var is now set, so no orphaned file.
    assert ensure_vertex_adc(s) is None
    assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == first


def test_ensure_vertex_adc_defers_to_an_existing_credentials_path(monkeypatch, tmp_path):
    """A mounted key, laptop ADC, or the future Workload Identity Federation config all arrive via
    GOOGLE_APPLICATION_CREDENTIALS and must win over this POC fallback."""
    existing = tmp_path / "already-there.json"
    existing.write_text(FAKE_SA_KEY, encoding="utf-8")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", str(existing))
    assert ensure_vertex_adc(_gemini_settings()) is None
    assert os.environ["GOOGLE_APPLICATION_CREDENTIALS"] == str(existing)


def test_ensure_vertex_adc_is_a_no_op_without_a_key():
    assert ensure_vertex_adc(_settings(gcp_project="proj-x")) is None
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ


@pytest.mark.parametrize("bad", ["not json at all", '{"no_type_field": true}', "[]"])
def test_ensure_vertex_adc_fails_soft_on_a_malformed_key(bad):
    """Must degrade to the documented OpenAI fallback, not take the chat surface down."""
    assert ensure_vertex_adc(_settings(gcp_project="proj-x", gcp_sa_key_json=bad)) is None
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ


def test_build_chat_model_materializes_adc_before_constructing_the_vertex_client():
    """The whole point of the placement: no boot hook, but ADC is in place by the time a client
    exists -- and google-genai resolves ADC lazily on first request, later still."""
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ
    chat = build_chat_model(_gemini_settings(llm_provider="gemini"))
    assert isinstance(chat, ChatGoogleGenerativeAI)
    assert os.path.isfile(os.environ["GOOGLE_APPLICATION_CREDENTIALS"])


def test_build_chat_model_openai_never_touches_the_gcp_key():
    """A deployment that falls back to OpenAI must not write key material to disk at all."""
    build_chat_model(_settings(openai_api_key="sk-openai", gcp_sa_key_json=FAKE_SA_KEY))
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ


def test_model_pin_resolves_exactly_when_provider_and_model_are_both_set():
    """#103 item 3: the deploy-time pin. `gemini-2.5-flash` is set through env/SSM, never in
    DEFAULT_MODELS -- D-4's `gemini-3.7-flash` stays the code pin and is unpinned in code only
    when Google ships it on the v1beta1 regional surface."""
    from app.assistant.llm import DEFAULT_MODELS

    s = _gemini_settings(llm_provider="gemini", llm_model="gemini-2.5-flash")
    r = resolve_llm(s)
    assert r.provider == "gemini"
    assert r.model == "gemini-2.5-flash"
    assert r.gcp_location == DESIGNED_GCP_VERTEX_LOCATION
    assert DEFAULT_MODELS["gemini"] == "gemini-3.7-flash"
    assert build_chat_model(s).model.endswith("gemini-2.5-flash")


# -------------------------------------------------------------------------------------------
# OWNER RULING 2026-09-01 (#103) -- the AI Studio key path, re-admitted alongside Vertex.
# -------------------------------------------------------------------------------------------


def test_api_key_alone_makes_gemini_ready():
    s = _settings(google_api_key="gk-test")
    assert s.ready_gemini_api_key is True
    assert s.ready_gemini_vertex is False
    assert s.ready_gemini is True


def test_api_key_only_resolves_gemini_ahead_of_openai():
    """The go-live gate itself: /setuhaul/google-api-key is already in SSM and already hydrates,
    so this resolution is the whole production change."""
    s = _settings(google_api_key="gk-test", openai_api_key="sk-openai")
    r = resolve_llm(s)
    assert r.provider == "gemini"
    assert r.model == "gemini-3.7-flash"
    assert r.api_key == "gk-test"
    # Express mode: Vertex-served, but project/location must stay unset or the SDK discards the
    # key and demands ADC instead.
    assert r.gemini_backend == GEMINI_VERTEX_EXPRESS
    assert r.vertex is True
    assert r.gcp_project is None
    assert r.gcp_location is None


def test_express_mode_is_skipped_when_the_environment_would_defeat_it(monkeypatch):
    """google-genai drops an express-mode key when it sees implicit project/location
    (`_api_client.py:756-768`), falling back to ADC a container does not have. Detected as
    config, not discovered as a runtime failure."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "some-other-project")
    r = resolve_llm(_settings(google_api_key="gk-test"))
    assert r.gemini_backend == GEMINI_AI_STUDIO
    assert r.vertex is False
    assert r.api_key == "gk-test"


def test_express_mode_is_also_skipped_for_a_stray_cloud_location(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLOUD_LOCATION", "us-central1")
    assert resolve_llm(_settings(google_api_key="gk-test")).gemini_backend == GEMINI_AI_STUDIO


def test_vertex_adc_is_preferred_over_every_key_shape():
    """Residency decision, made once here rather than left to key precedence -- the same silent
    ordering bug AUTO_ORDER's own comment records. Full Vertex is the only in-region shape."""
    s = _gemini_settings(google_api_key="gk-test", openai_api_key="sk-openai")
    r = resolve_llm(s)
    assert r.provider == "gemini"
    assert r.gemini_backend == GEMINI_VERTEX_ADC
    assert r.vertex is True
    assert r.gcp_project == "proj-x"
    assert r.gcp_location == DESIGNED_GCP_VERTEX_LOCATION
    assert r.api_key is None


def test_neither_gemini_shape_falls_through_to_openai():
    s = _settings(openai_api_key="sk-openai")
    assert resolve_llm(s).provider == "openai"


def test_explicit_gemini_with_only_an_api_key_does_not_raise():
    r = resolve_llm(_settings(llm_provider="gemini", google_api_key="gk-test"))
    assert r.provider == "gemini"
    assert r.gemini_backend == GEMINI_VERTEX_EXPRESS


def test_explicit_gemini_error_names_both_credential_shapes():
    with pytest.raises(AppError) as ei:
        resolve_llm(_settings(llm_provider="gemini"))
    message = str(ei.value)
    assert "GOOGLE_API_KEY" in message
    assert "GCP_PROJECT" in message


def test_build_chat_model_express_shape_is_vertex_with_no_project_or_location():
    """The load-bearing assertion of the express path. Passing project or location makes
    google-genai discard the key and demand ADC -- reproduced live on 2026-09-01 as
    "Could not resolve project using application default credentials"."""
    chat = build_chat_model(_settings(llm_provider="gemini", google_api_key="gk-test"))
    assert isinstance(chat, ChatGoogleGenerativeAI)
    assert chat.google_api_key.get_secret_value() == "gk-test"
    assert chat.vertexai is True
    assert chat.project is None
    assert chat.location is None


def test_build_chat_model_ai_studio_shape_is_not_vertex(monkeypatch):
    """The non-express key path must carry the key and NOTHING Vertex-shaped."""
    monkeypatch.setenv("GOOGLE_CLOUD_PROJECT", "some-other-project")
    chat = build_chat_model(_settings(llm_provider="gemini", google_api_key="gk-test"))
    assert chat.google_api_key.get_secret_value() == "gk-test"
    assert not chat.vertexai
    assert chat.project is None
    assert chat.location is None


def test_api_key_shape_never_materializes_a_service_account_file():
    """A deployment on the key path must not write key material to disk at all."""
    s = _settings(llm_provider="gemini", google_api_key="gk-test", gcp_sa_key_json=FAKE_SA_KEY)
    build_chat_model(s)
    assert "GOOGLE_APPLICATION_CREDENTIALS" not in os.environ


def test_thinking_config_applies_to_the_api_key_shape_too():
    """It is a property of the model, not of the endpoint serving it -- so the 2.5/3.x parameter
    split bites on AI Studio exactly as it does on Vertex."""
    chat = build_chat_model(_settings(llm_provider="gemini", google_api_key="gk-test"))
    assert chat.thinking_config == {"thinking_level": "high"}
    pinned = build_chat_model(
        _settings(llm_provider="gemini", google_api_key="gk-test", llm_model="gemini-2.5-flash")
    )
    assert pinned.thinking_config == {"thinking_budget": -1}


def test_vertex_location_global_is_allowed_explicitly():
    """#103: gemini-3.7-flash serves on Vertex `global` today while the regional subdomain still
    404s. Allowed as an explicit opt-in only."""
    r = resolve_llm(_gemini_settings(llm_provider="gemini", gcp_vertex_location="global"))
    assert r.vertex is True
    assert r.gcp_location == "global"


def test_vertex_location_still_rejects_an_arbitrary_region():
    with pytest.raises(AppError) as ei:
        resolve_llm(_gemini_settings(llm_provider="gemini", gcp_vertex_location="us-central1"))
    assert "location mismatch" in str(ei.value).lower()


def test_asia_south1_remains_the_default_location():
    """`global` must never be reached by default -- that would forfeit SS11 silently."""
    from app.assistant.llm import ALLOWED_VERTEX_LOCATIONS

    assert Settings().gcp_vertex_location == DESIGNED_GCP_VERTEX_LOCATION
    assert ALLOWED_VERTEX_LOCATIONS[0] == DESIGNED_GCP_VERTEX_LOCATION
    assert "global" in ALLOWED_VERTEX_LOCATIONS


def test_thinking_config_matches_the_model_generation():
    """Regression guard for a defect found by a live Vertex call on #103, not by inspection:
    `gemini-2.5-flash` returns 400 INVALID_ARGUMENT for `thinking_level`, which is the exact
    model #103 item 3 pins. The two generations take mutually exclusive parameters."""
    from app.assistant.llm import thinking_config_for

    assert thinking_config_for("gemini-3.7-flash") == {"thinking_level": "high"}
    assert thinking_config_for("gemini-2.5-flash") == {"thinking_budget": -1}
    assert thinking_config_for("gemini-2.5-pro") == {"thinking_budget": -1}
    # Unknown model: send nothing rather than guess a parameter Vertex may reject.
    assert thinking_config_for("some-future-model") is None


def test_build_chat_model_sends_the_2_5_thinking_parameter_not_the_3_x_one():
    # Asserted on `thinking_config` rather than the flat `thinking_budget`/`thinking_level`
    # fields: passing the raw dict (as this module has always done) leaves those flat fields
    # None and forwards the dict verbatim -- which is how the bad `thinking_level` reached
    # Vertex and 400'd in the first place.
    chat = build_chat_model(_gemini_settings(llm_provider="gemini", llm_model="gemini-2.5-flash"))
    assert chat.thinking_config == {"thinking_budget": -1}
    assert "thinking_level" not in chat.thinking_config


def test_build_chat_model_keeps_d4a_high_reasoning_on_the_gemini_3_pin():
    chat = build_chat_model(_gemini_settings(llm_provider="gemini"))
    assert chat.model.endswith("gemini-3.7-flash")
    assert chat.thinking_config == {"thinking_level": "high"}
