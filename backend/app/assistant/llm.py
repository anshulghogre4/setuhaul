"""Multi-provider chat model factory (OpenAI / OpenRouter / Gemini)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.core.errors import AppError
from app.core.settings import Settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "openrouter": "openai/gpt-4o-mini",
    # gemini-2.0-flash shut down 2026-06-01; use current Flash for bind_tools POC
    "gemini": "gemini-2.5-flash",
}

AUTO_ORDER = ("openai", "openrouter", "gemini")


@dataclass(frozen=True)
class ResolvedLLM:
    provider: str
    model: str
    api_key: str
    base_url: str | None


def _key_for(settings: Settings, provider: str) -> str:
    if provider == "openai":
        return (settings.openai_api_key or "").strip()
    if provider == "openrouter":
        return (settings.openrouter_api_key or "").strip()
    if provider == "gemini":
        return (settings.google_api_key or "").strip()
    return ""


def _base_url_for(provider: str) -> str | None:
    if provider == "openrouter":
        return OPENROUTER_BASE_URL
    return None


def _validate_gemini_key(api_key: str) -> None:
    """Google AI Studio keys are not OpenAI sk-/sk-proj- tokens."""
    lower = api_key.lower()
    if lower.startswith("sk-") or lower.startswith("sk-or-"):
        raise AppError(
            "GOOGLE_API_KEY looks like an OpenAI/OpenRouter key. "
            "Use a Google AI Studio key (typically starts with AIza) from "
            "https://aistudio.google.com/apikey and ChatGoogleGenerativeAI.",
            code="LLM_UNAVAILABLE",
            status_code=503,
        )


def resolve_llm(settings: Settings) -> ResolvedLLM:
    """Pick provider/model/key from settings. Raises AppError if none configured."""
    mode = (settings.llm_provider or "auto").strip().lower() or "auto"
    override = (settings.llm_model or "").strip()

    if mode == "auto":
        for provider in AUTO_ORDER:
            key = _key_for(settings, provider)
            if not key:
                continue
            if provider == "gemini":
                _validate_gemini_key(key)
            return ResolvedLLM(
                provider=provider,
                model=override or DEFAULT_MODELS[provider],
                api_key=key,
                base_url=_base_url_for(provider),
            )
        raise AppError(
            "No LLM API key configured. Set OPENAI_API_KEY, OPENROUTER_API_KEY, or GOOGLE_API_KEY.",
            code="LLM_UNAVAILABLE",
            status_code=503,
        )

    if mode not in DEFAULT_MODELS:
        raise AppError(
            f"Unknown LLM_PROVIDER={mode!r}. Use auto|openai|openrouter|gemini.",
            code="LLM_UNAVAILABLE",
            status_code=503,
        )

    key = _key_for(settings, mode)
    if not key:
        env_name = {
            "openai": "OPENAI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
            "gemini": "GOOGLE_API_KEY",
        }[mode]
        raise AppError(
            f"{env_name} is required when LLM_PROVIDER={mode}.",
            code="LLM_UNAVAILABLE",
            status_code=503,
        )

    if mode == "gemini":
        _validate_gemini_key(key)

    return ResolvedLLM(
        provider=mode,
        model=override or DEFAULT_MODELS[mode],
        api_key=key,
        base_url=_base_url_for(mode),
    )


def build_chat_model(settings: Settings) -> BaseChatModel:
    """Return a chat model that supports bind_tools for run_assistant.

    - openai / openrouter → ChatOpenAI (OpenRouter via OpenAI-compatible base_url)
    - gemini → ChatGoogleGenerativeAI (native LangChain Google integration)
    """
    resolved = resolve_llm(settings)
    if resolved.provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=resolved.model,
            temperature=0,
            google_api_key=resolved.api_key,
        )

    kwargs: dict[str, Any] = {
        "model": resolved.model,
        "temperature": 0,
        "api_key": resolved.api_key,
    }
    if resolved.base_url:
        kwargs["base_url"] = resolved.base_url
    return ChatOpenAI(**kwargs)
