"""Multi-provider chat model factory (Gemini / OpenAI / OpenRouter).

E4.1 (issue #31), TECH_STACK.md section 7, decision D-4: Gemini (`gemini-3.7-flash`) is the
**primary** provider, served from **Vertex AI `asia-south1`** via ADC (Application Default
Credentials) -- not the Gemini Developer API's simpler `GOOGLE_API_KEY` path, which Google's own
docs warn can silently route through the global endpoint regardless of configured location. OpenAI
is the one documented fallback (`AUTO_ORDER` below), kept for exactly the reason TECH_STACK.md
names: running out of GCP credit mid-demo needs an escape hatch, even though that fallback leaves
India (SS11).

Naming note (2026-08-25): Google now markets "Vertex AI" as part of the Gemini Enterprise Agent
Platform (Cloud Next 2026), which does include a real agent-hosting surface (Agent Engine). This
module does not use it -- `build_chat_model` below is a plain model-inference call, nothing more.
AWS AgentCore stays the agent-hosting runtime (owner's AWS-credit constraint, TECH_STACK.md
section 2), unaffected by this rebrand. See TECH_STACK.md section 7's own naming note for detail.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.core.errors import AppError
from app.core.settings import DESIGNED_GCP_VERTEX_LOCATION, Settings

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


@dataclass(frozen=True)
class ResolvedLLM:
    provider: str
    model: str
    # OpenAI/OpenRouter only -- Gemini/Vertex has no API-key string this app holds; see
    # `Settings.gcp_project`'s own comment for why ADC replaces it entirely.
    api_key: str | None = None
    base_url: str | None = None
    gcp_project: str | None = None
    gcp_location: str | None = None


def _is_ready(settings: Settings, provider: str) -> bool:
    if provider == "openai":
        return bool((settings.openai_api_key or "").strip())
    if provider == "openrouter":
        return bool((settings.openrouter_api_key or "").strip())
    if provider == "gemini":
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
    """
    location = (settings.gcp_vertex_location or "").strip()
    if location != DESIGNED_GCP_VERTEX_LOCATION:
        raise AppError(
            f"GCP Vertex location mismatch: resolved={location or '<unset>'} "
            f"expected={DESIGNED_GCP_VERTEX_LOCATION}. Gemini is only in-region (SS11 residency) "
            f"when served from {DESIGNED_GCP_VERTEX_LOCATION}; set GCP_VERTEX_LOCATION to that "
            "value, or choose a different provider.",
            code="LLM_UNAVAILABLE",
            status_code=503,
        )
    return location


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
        if not _is_ready(settings, provider):
            if mode != "auto":
                env_name = {
                    "gemini": "GCP_PROJECT (Vertex AI + ADC, not GOOGLE_API_KEY -- see this "
                    "module's docstring)",
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
            location = _assert_vertex_region(settings)
            return ResolvedLLM(
                provider="gemini", model=override or DEFAULT_MODELS["gemini"],
                gcp_project=settings.gcp_project.strip(), gcp_location=location,
            )
        return ResolvedLLM(
            provider=provider, model=override or DEFAULT_MODELS[provider],
            api_key=_key_for(settings, provider), base_url=_base_url_for(provider),
        )

    raise AppError(
        "No LLM configured. Set GCP_PROJECT (Vertex AI), OPENAI_API_KEY, or OPENROUTER_API_KEY.",
        code="LLM_UNAVAILABLE",
        status_code=503,
    )


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


def build_chat_model(settings: Settings) -> BaseChatModel:
    """Return a chat model that supports bind_tools for run_assistant.

    - gemini → `ChatGoogleGenerativeAI` in **Vertex mode** (`vertexai=True`, ADC, explicit
      `location`) -- not the Developer API's `google_api_key` path.
    - openai / openrouter → `ChatOpenAI` (OpenRouter via OpenAI-compatible base_url).
    """
    resolved = resolve_llm(settings)
    # E4.4 (issue #34): no timeout ceiling existed on the LLM path before this -- a slow
    # provider response had nothing bounding it. Both client classes accept `timeout` and pass it
    # straight to their underlying httpx client, so this is a real per-request ceiling, not just
    # a connect timeout.
    timeout = settings.llm_call_timeout_seconds
    if resolved.provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=resolved.model,
            temperature=0,
            timeout=timeout,
            vertexai=True,
            project=resolved.gcp_project,
            location=resolved.gcp_location,
            # D-4a: pinned high, not left at the SDK default. Deliberately declines TECH_STACK.md
            # section 10 lever 6 ("lower effort for routine turns") -- the measured tradeoff is
            # hop count, not per-call effort (a mis-selected tool costs a full extra round trip),
            # recorded so a later reader does not "fix" this as an oversight.
            thinking_config={"thinking_level": "high"},
        )

    kwargs: dict[str, Any] = {
        "model": resolved.model,
        "temperature": 0,
        "api_key": resolved.api_key,
        "timeout": timeout,
    }
    if resolved.base_url:
        kwargs["base_url"] = resolved.base_url
    return ChatOpenAI(**kwargs)
