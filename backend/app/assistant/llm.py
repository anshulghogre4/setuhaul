"""Multi-provider chat model factory (Gemini / OpenAI / OpenRouter).

E4.1 (issue #31), TECH_STACK.md section 7, decision D-4: Gemini (`gemini-3.7-flash`) is the
**primary** provider, served from **Vertex AI `asia-south1`** via ADC (Application Default
Credentials). OpenAI is the one documented fallback (`AUTO_ORDER` below), kept for exactly the
reason TECH_STACK.md names: running out of GCP credit mid-demo needs an escape hatch, even though
that fallback leaves India (SS11).

OWNER RULING 2026-09-01 (issue #103): Gemini now has **two** credential shapes, not one. E4.1 had
excluded the Developer/AI-Studio `GOOGLE_API_KEY` path because Google's own docs warn it can
silently route through the global endpoint regardless of configured location; the owner has
re-admitted it for the POC ("if ADC is not working we can simply use API key based with no
worries") after it was verified serving `gemini-3.7-flash` through this module's own SDK
dependency. `resolve_llm` still **prefers** Vertex whenever it is configured, because that is the
only shape that keeps inference in India -- the key path relaxes the SS11 residency goal by
explicit decision, and that relaxation is recorded, not forgotten.

Naming note (2026-08-25): Google now markets "Vertex AI" as part of the Gemini Enterprise Agent
Platform (Cloud Next 2026), which does include a real agent-hosting surface (Agent Engine). This
module does not use it -- `build_chat_model` below is a plain model-inference call, nothing more.
AWS AgentCore stays the agent-hosting runtime (owner's AWS-credit constraint, TECH_STACK.md
section 2), unaffected by this rebrand. See TECH_STACK.md section 7's own naming note for detail.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.core.errors import AppError
from app.core.settings import DESIGNED_GCP_VERTEX_LOCATION, Settings

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

DEFAULT_MODELS = {
    "gemini": "gemini-3.7-flash",
    "openai": "gpt-4o-mini",
    "openrouter": "openai/gpt-4o-mini",
}

# Gemini first: D-4's primary provider, not the historical last-tried fallback -- with Gemini
# last (as this constant read before this epic), OpenAI silently won on key precedence in every
# deployment where both keys happened to be set, which is exactly how driver PII was leaving
# India by default despite Vertex being the intended path (COMPARISON-ai-assistant.md section 0).
AUTO_ORDER = ("gemini", "openai", "openrouter")


# Vertex locations this app will serve Gemini from. `asia-south1` (Mumbai) is the design target
# and stays the default. `global` is admitted because of an empirical finding on issue #103
# (2026-09-01, coordinator's probe through this app's own SDK dependency): `gemini-3.7-flash`
# serves on Vertex `global` today, while the regional subdomain still 404s -- which was #31's
# original blocker, root-caused there as a Google-side rollout gap, not a code defect. Admitted as
# an *explicit* opt-in only: nothing here ever defaults to `global`, because falling back to it
# silently would forfeit SS11 residency without anyone deciding to.
ALLOWED_VERTEX_LOCATIONS = (DESIGNED_GCP_VERTEX_LOCATION, "global")


# The three Gemini credential shapes, in preference order. Named rather than inferred from which
# fields happen to be populated, because two of them look identical at a glance (both carry an API
# key) while needing opposite constructor arguments -- see `build_chat_model`.
GEMINI_VERTEX_ADC = "vertex_adc"  # project + ADC/service-account. In-region, E4.1's design target.
GEMINI_VERTEX_EXPRESS = "vertex_express"  # API key, served BY Vertex ("express mode").
GEMINI_AI_STUDIO = "ai_studio"  # API key, served by generativelanguage.googleapis.com.
GEMINI_VERTEX_BACKENDS = (GEMINI_VERTEX_ADC, GEMINI_VERTEX_EXPRESS)


@dataclass(frozen=True)
class ResolvedLLM:
    provider: str
    model: str
    # Carries the OpenAI/OpenRouter key, and -- since the 2026-09-01 owner ruling on #103 -- the
    # Gemini API key too. Which Gemini shape it belongs to is `gemini_backend`, never inferred
    # from this field being set.
    api_key: str | None = None
    base_url: str | None = None
    gcp_project: str | None = None
    gcp_location: str | None = None
    # One of the GEMINI_* constants above for provider="gemini"; None for every other provider.
    gemini_backend: str | None = None

    @property
    def vertex(self) -> bool:
        """Served by Vertex AI, whether authenticated by ADC or by an express-mode API key."""
        return self.gemini_backend in GEMINI_VERTEX_BACKENDS


def _is_ready(settings: Settings, provider: str, *, mode: str = "auto") -> bool:
    if provider == "openai":
        return bool((settings.openai_api_key or "").strip())
    if provider == "openrouter":
        return bool((settings.openrouter_api_key or "").strip())
    if provider == "gemini":
        # Owner ruling 2026-09-02: in AUTO, Gemini means the free API key -- a host with only
        # Vertex credentials falls through to openai/openrouter rather than auto-selecting the
        # Vertex path (explicit LLM_PROVIDER=gemini still honours Vertex config).
        if mode == "auto":
            return settings.ready_gemini_api_key
        return settings.ready_gemini
    return False


def _assert_vertex_region(settings: Settings) -> str:
    """E4.1 (issue #31): "Assert the resolved Vertex endpoint region at startup." `asia-south1`
    is not a preference -- it is the entire reason Vertex was chosen over every other evaluated
    provider (TECH_STACK.md section 7's own routing table: everything else leaves India or lands
    in a different APAC country). A static config check, not a live probe of Vertex's own
    metadata: the same shape `assert_region_alignment` already uses for AWS, and the only one
    verifiable without live GCP credentials, which this issue is itself blocked on. Scoped to the
    moment Gemini is actually resolved as the active provider, not every app boot unconditionally
    -- unlike Postgres/Redis, the LLM provider is optional and varies by deployment, so a
    misconfigured GCP location must not fail app startup for a deployment not using Gemini at all.

    Widened on #103 (2026-09-01) from "must equal asia-south1" to `ALLOWED_VERTEX_LOCATIONS`, so
    that `global` can be selected deliberately while `gemini-3.7-flash` is still rolling out on the
    regional subdomain -- see that constant for the evidence. `asia-south1` remains the default and
    the design target; `global` has to be typed into config by a human to take effect.
    """
    location = (settings.gcp_vertex_location or "").strip()
    if location not in ALLOWED_VERTEX_LOCATIONS:
        raise AppError(
            f"GCP Vertex location mismatch: resolved={location or '<unset>'} "
            f"expected one of {', '.join(ALLOWED_VERTEX_LOCATIONS)}. Gemini is only in-region "
            f"(SS11 residency) when served from {DESIGNED_GCP_VERTEX_LOCATION}; set "
            f"GCP_VERTEX_LOCATION to that value, or to 'global' to accept out-of-region serving "
            "deliberately, or choose a different provider.",
            code="LLM_UNAVAILABLE",
            status_code=503,
        )
    if location != DESIGNED_GCP_VERTEX_LOCATION:
        # Loud, once per model build, and never silent: this is a residency decision.
        logger.warning(
            "Vertex location is %r, not the designed %r -- Gemini inference leaves India. "
            "Deliberate per issue #103 while gemini-3.7-flash rolls out regionally; revert to "
            "%r once it serves there.",
            location,
            DESIGNED_GCP_VERTEX_LOCATION,
            DESIGNED_GCP_VERTEX_LOCATION,
        )
    return location


# google-genai discards an express-mode API key when it finds implicit project/location in the
# environment (`_api_client.py:756-768` in the pinned 2.19.0: "Implicit project/location takes
# precedence over implicit api_key"). These are the two variables that trigger it.
_EXPRESS_DEFEATING_ENV = ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION")


def _gemini_key_backend() -> str:
    """AI Studio by default (owner ruling 2026-09-02); express mode is explicit opt-in.

    History, because this preference has now flipped twice and the next reader deserves the
    whole arc: E4.1 mandated Vertex/ADC and excluded the API key; the 2026-09-01 owner ruling
    re-admitted the key, and Vertex EXPRESS mode (`vertexai=True` + key, no project/location)
    measured fastest of the three shapes (~4x faster warm than AI Studio) so it became the key
    path's default. The 2026-09-02 owner ruling then simplified again: **stick to the free
    Gemini API** -- express mode is served by Vertex and bills as Vertex, while the AI Studio
    key has the free tier, and for this POC cost predictability beats the latency delta.

    Express remains available as an explicit opt-in (GEMINI_KEY_BACKEND=vertex_express) because
    the code path is built, tested, and was live-verified in production on 2026-09-01 -- do not
    delete it; flipping back is a config act. The opt-in inherits the same silent-failure guard:
    in the pinned google-genai 2.19.0, `vertexai=True` discards the API key if project/location
    are present explicitly (`_api_client.py:749-755`) or via GOOGLE_CLOUD_PROJECT /
    GOOGLE_CLOUD_LOCATION (`:756-768`), stranding the client on ADC a container does not have.
    """
    requested = (os.environ.get("GEMINI_KEY_BACKEND") or "").strip().lower()
    if requested == GEMINI_VERTEX_EXPRESS:
        defeated = [n for n in _EXPRESS_DEFEATING_ENV if (os.environ.get(n) or "").strip()]
        if defeated:
            logger.warning(
                "GEMINI_KEY_BACKEND=vertex_express requested but %s is set, which makes the "
                "google-genai client discard the API key and fall back to ADC. Serving from "
                "AI Studio instead; unset it to get Vertex express.",
                " and ".join(defeated),
            )
            return GEMINI_AI_STUDIO
        return GEMINI_VERTEX_EXPRESS
    return GEMINI_AI_STUDIO


def resolve_llm(settings: Settings) -> ResolvedLLM:
    """Pick provider/model/credentials from settings. Raises AppError if none configured."""
    mode = (settings.llm_provider or "auto").strip().lower() or "auto"
    override = (settings.llm_model or "").strip()

    candidates = AUTO_ORDER if mode == "auto" else (mode,)
    if mode != "auto" and mode not in DEFAULT_MODELS:
        raise AppError(
            f"Unknown LLM_PROVIDER={mode!r}. Use auto|gemini|openai|openrouter.",
            code="LLM_UNAVAILABLE",
            status_code=503,
        )

    for provider in candidates:
        if not _is_ready(settings, provider, mode=mode):
            if mode != "auto":
                env_name = {
                    "gemini": "either GOOGLE_API_KEY (AI Studio), or -- preferred, and the only "
                    "in-region path -- GCP_PROJECT plus a Vertex credential (GCP_SA_KEY_JSON, or "
                    "an ADC file reachable via GOOGLE_APPLICATION_CREDENTIALS / `gcloud auth "
                    "application-default login`)",
                    "openai": "OPENAI_API_KEY",
                    "openrouter": "OPENROUTER_API_KEY",
                }[mode]
                raise AppError(
                    f"{env_name} is required when LLM_PROVIDER={mode}.",
                    code="LLM_UNAVAILABLE",
                    status_code=503,
                )
            continue

        if provider == "gemini":
            model = override or DEFAULT_MODELS["gemini"]
            # Owner ruling 2026-09-02: AUTO never selects Vertex -- the free API key is the
            # Gemini path (then openai, then openrouter). Vertex/ADC remains reachable ONLY by
            # explicit LLM_PROVIDER=gemini with Vertex configured: an operator who names the
            # provider and provisions GCP credentials has said what they want, and the built,
            # live-verified Vertex code stays a config flip rather than a rebuild. This also
            # fixes a real local failure: a laptop with leftover gcloud ADC + GCP_PROJECT was
            # auto-selecting vertex_adc and dying on the asia-south1 3.7 rollout 404 (#31).
            if mode != "auto" and settings.ready_gemini_vertex:
                return ResolvedLLM(
                    provider="gemini", model=model, gemini_backend=GEMINI_VERTEX_ADC,
                    gcp_project=settings.gcp_project.strip(),
                    gcp_location=_assert_vertex_region(settings),
                )
            # Both remaining shapes use the same API key; only the serving endpoint differs.
            # Express mode is preferred -- it is real Vertex serving, so it keeps more of E4.1's
            # intent than generativelanguage.googleapis.com does, and measured faster besides
            # (2026-09-01 probes on #103: express ~2.5-3.0s vs AI Studio ~3.9-8.6s cold).
            # Deliberately carries no project/location; see `_gemini_key_backend`.
            return ResolvedLLM(
                provider="gemini", model=model, gemini_backend=_gemini_key_backend(),
                api_key=(settings.google_api_key or "").strip(),
            )
        return ResolvedLLM(
            provider=provider, model=override or DEFAULT_MODELS[provider],
            api_key=_key_for(settings, provider), base_url=_base_url_for(provider),
        )

    raise AppError(
        "No LLM configured. Set GOOGLE_API_KEY, or GCP_PROJECT + a Vertex credential "
        "(GCP_SA_KEY_JSON or an ADC file), or OPENAI_API_KEY, or OPENROUTER_API_KEY.",
        code="LLM_UNAVAILABLE",
        status_code=503,
    )


# Guards `_adc_path` below. This app is effectively single-process, but `build_chat_model` is
# called from request handlers, and FastAPI runs sync dependencies in a thread pool -- two
# concurrent first-turns would otherwise race to mkstemp and leave one orphaned key file on disk.
_adc_lock = threading.Lock()
_adc_path: str | None = None


def ensure_vertex_adc(settings: Settings) -> str | None:
    """Materialize GCP_SA_KEY_JSON to a 0600 file and point ADC at it. Returns the path or None.

    Issue #103, option (a). Why this exists at all: the AgentCore container has no gcloud ADC file
    and no GCE metadata server, and E4.1 forbids the bare `GOOGLE_API_KEY` Developer-API path
    (it can silently route out of `asia-south1`, forfeiting the SS11 residency guarantee that is
    the whole reason Vertex was chosen). So the only remaining way to authenticate Vertex in that
    container is a service-account key -- and google-auth accepts a key only as a *file path* via
    GOOGLE_APPLICATION_CREDENTIALS, never as inline JSON, so something has to write the file.

    Idempotent and lazy by design:

    - Returns None untouched when GOOGLE_APPLICATION_CREDENTIALS is already set. A real mounted
      key, a laptop's `gcloud auth application-default login`, or the future Workload Identity
      Federation config (#103 option (b)) all arrive that way and must win over this fallback.
    - Writes at most once per process. The file is intentionally *not* deleted afterwards: the
      Vertex client re-reads it on every token refresh for the life of the process, so cleaning it
      up early would break the second hour of an uptime, and the container filesystem is discarded
      wholesale at shutdown anyway.
    - Never logs the key, the file's contents, or its path.
    """
    global _adc_path

    raw = (settings.gcp_sa_key_json or "").strip()
    if not raw:
        return None
    if (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip():
        return None

    with _adc_lock:
        # Re-checked inside the lock: another thread may have won the race between the guard
        # above and here, in which case reuse its file rather than writing a second one.
        if _adc_path and os.path.isfile(_adc_path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = _adc_path
            return _adc_path
        if (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip():
            return None

        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            # Fail soft, not loud: a malformed key must degrade to the documented OpenAI fallback,
            # not take the chat surface down. The message names the env var and nothing else.
            logger.error(
                "GCP_SA_KEY_JSON is set but is not valid JSON; leaving ADC unset. "
                "Vertex will be skipped and AUTO_ORDER falls through to the next provider."
            )
            return None
        if not isinstance(parsed, dict) or not parsed.get("type"):
            logger.error(
                "GCP_SA_KEY_JSON does not look like a GCP credential file (no 'type' field); "
                "leaving ADC unset."
            )
            return None

        fd, path = tempfile.mkstemp(prefix="setuhaul-adc-", suffix=".json")
        try:
            # mkstemp already creates 0600 on POSIX; the explicit chmod documents the intent and
            # covers a permissive umask. On Windows chmod only toggles the read-only bit, which is
            # why this is best-effort -- container-local POSIX is the deployment that matters.
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(raw)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except OSError:
            with contextlib.suppress(OSError):
                os.unlink(path)
            logger.exception("Could not write the Vertex ADC key file; leaving ADC unset.")
            return None

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = path
        _adc_path = path
        logger.info("Vertex ADC materialized from GCP_SA_KEY_JSON (%d bytes).", len(raw))
        return path


def _key_for(settings: Settings, provider: str) -> str:
    if provider == "openai":
        return (settings.openai_api_key or "").strip()
    if provider == "openrouter":
        return (settings.openrouter_api_key or "").strip()
    return ""


def _base_url_for(provider: str) -> str | None:
    if provider == "openrouter":
        return OPENROUTER_BASE_URL
    return None


def thinking_config_for(model: str) -> dict[str, Any] | None:
    """D-4a's "reason hard" setting, expressed in whichever knob the model generation accepts.

    Found live on issue #103, not by reading a changelog: a real `gemini-2.5-flash` Vertex call in
    `asia-south1` returns `400 INVALID_ARGUMENT -- thinking_level is not supported by this model`.
    The two generations use different, mutually exclusive parameters, which the pinned
    langchain-google-genai 4.3.5 states in its own `ChatGoogleGenerativeAI` docstring: "Gemini 3+
    models use `thinking_level`", "Gemini 2.5 models use `thinking_budget` (an integer token
    count) ... `-1` for dynamic thinking".

    That collision is load-bearing for #103 rather than cosmetic: item 3 of that issue pins
    `LLM_MODEL=gemini-2.5-flash` until Google ships `gemini-3.7-flash` on the regional Vertex
    surface, so without this mapping every single production Gemini turn would 400 the moment the
    credentials start working -- credentials that this same change is what makes work.

    D-4a's intent is preserved, not re-decided: `thinking_level="high"` still goes to Gemini 3+,
    which is the D-4 pin `DEFAULT_MODELS` still names. `-1` (dynamic) is the nearest honest 2.5
    analogue -- a fixed token budget would be a number nobody measured. OWNER FORK: if the 2.5 pin
    turns out to under-think tool selection (the specific cost D-4a was guarding against), the
    lever is a concrete `thinking_budget` here, and that is a tuning decision with evidence
    attached, not something to guess now.

    Unknown/other model names get no thinking config at all rather than a guess -- the failure
    mode being avoided is precisely sending a parameter a model rejects.
    """
    name = (model or "").strip().lower()
    if name.startswith("gemini-2.5"):
        return {"thinking_budget": -1}
    # gemini-3.x and later, including the D-4 pin gemini-3.7-flash.
    if name.startswith("gemini-3") or name.startswith("gemini-4"):
        return {"thinking_level": "high"}
    return None


def build_chat_model(settings: Settings) -> BaseChatModel:
    """Return a chat model that supports bind_tools for run_assistant.

    Three Gemini shapes, in the preference order `resolve_llm` applies:

    - `vertex_adc` → `vertexai=True` + project + explicit `location`, authenticated by ADC. The
      only in-region (`asia-south1`) path, and the only one that satisfies SS11 unrelaxed.
    - `vertex_express` → `vertexai=True` + `google_api_key`, and **no** project/location. Vertex
      serving on an API key.
    - `ai_studio` → `google_api_key` alone, served by generativelanguage.googleapis.com.

    The last two were re-admitted by the 2026-09-01 owner ruling on #103. openai / openrouter →
    `ChatOpenAI` (OpenRouter via OpenAI-compatible base_url), unchanged.
    """
    resolved = resolve_llm(settings)
    # E4.4 (issue #34): no timeout ceiling existed on the LLM path before this -- a slow
    # provider response had nothing bounding it. Both client classes accept `timeout` and pass it
    # straight to their underlying httpx client, so this is a real per-request ceiling, not just
    # a connect timeout.
    timeout = settings.llm_call_timeout_seconds
    if resolved.provider == "gemini":
        gemini_kwargs: dict[str, Any] = {
            "model": resolved.model,
            "temperature": 0,
            "timeout": timeout,
        }
        if resolved.gemini_backend == GEMINI_VERTEX_ADC:
            # Issue #103. `ensure_vertex_adc` is placed here, and only here, because this is the
            # narrowest point that still provably runs before any Vertex credential is resolved:
            #   * `google.auth.default()` re-reads GOOGLE_APPLICATION_CREDENTIALS from os.environ
            #     on every call and caches nothing at module level, so setting it now is honoured.
            #   * the pinned google-genai (2.19.0) resolves ADC *lazily* -- `BaseApiClient` only
            #     calls `load_auth()` eagerly when no project is supplied, and we always supply
            #     one, so the real resolution happens in `_access_token()` on the first request.
            #     Constructing the client below therefore cannot beat this line.
            # No app-boot hook is needed as a result, and a deployment that never selects this
            # shape never touches the key material at all -- including the two key-based branches
            # below, which must not write a service-account file they will never use.
            ensure_vertex_adc(settings)
            gemini_kwargs["vertexai"] = True
            gemini_kwargs["project"] = resolved.gcp_project
            gemini_kwargs["location"] = resolved.gcp_location
        elif resolved.gemini_backend == GEMINI_VERTEX_EXPRESS:
            # Vertex express mode: Vertex serving, authenticated by an API key instead of ADC.
            # `project`/`location` are omitted *deliberately and load-bearingly* -- passing either
            # one makes google-genai discard the key and demand ADC instead
            # (`_api_client.py:749-755`), which is not a theory: passing location='asia-south1'
            # here raised "Could not resolve project using application default credentials" in a
            # live 2026-09-01 probe, while omitting both returned in 2.51s. Google's own express
            # example passes neither. `langchain_google_genai` 4.3.5 hands the key to the SDK via
            # a temporarily-set GOOGLE_API_KEY env var rather than a constructor argument
            # (chat_models.py:2760-2782) -- an implementation detail worth knowing, because it is
            # why the key never appears in the `Client(...)` call.
            gemini_kwargs["vertexai"] = True
            gemini_kwargs["google_api_key"] = resolved.api_key
        else:
            # Plain AI Studio (generativelanguage.googleapis.com). `vertexai`/`project`/`location`
            # are omitted entirely rather than set to None: the SDK's backend detection keys off
            # their presence.
            gemini_kwargs["google_api_key"] = resolved.api_key
        # D-4a: reasoning pinned high, not left at the SDK default. Deliberately declines
        # TECH_STACK.md section 10 lever 6 ("lower effort for routine turns") -- the measured
        # tradeoff is hop count, not per-call effort (a mis-selected tool costs a full extra round
        # trip), recorded so a later reader does not "fix" this as an oversight. Which *parameter*
        # carries that intent depends on the model generation; see `thinking_config_for`. Applies
        # to both Gemini shapes -- it is a property of the model, not of the endpoint serving it.
        # Omitted entirely rather than sent as None for an unrecognised model, because the pinned
        # client forwards the key either way and the API rejects parameters it does not know.
        thinking = thinking_config_for(resolved.model)
        if thinking is not None:
            gemini_kwargs["thinking_config"] = thinking
        return ChatGoogleGenerativeAI(**gemini_kwargs)

    kwargs: dict[str, Any] = {
        "model": resolved.model,
        "temperature": 0,
        "api_key": resolved.api_key,
        "timeout": timeout,
    }
    if resolved.base_url:
        kwargs["base_url"] = resolved.base_url
    return ChatOpenAI(**kwargs)
