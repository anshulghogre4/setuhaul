"""Unit tests for multi-provider LLM factory."""

from __future__ import annotations

import pytest
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.assistant.llm import OPENROUTER_BASE_URL, build_chat_model, resolve_llm
from app.core.errors import AppError
from app.core.settings import Settings


def _settings(**kwargs) -> Settings:
    base = {
        "openai_api_key": "",
        "openrouter_api_key": "",
        "google_api_key": "",
        "llm_provider": "auto",
        "llm_model": "",
    }
    base.update(kwargs)
    return Settings(**base)


def test_auto_prefers_openai_when_present():
    s = _settings(openai_api_key="sk-openai", openrouter_api_key="sk-or", google_api_key="AIza-fake")
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


def test_auto_falls_back_to_gemini():
    s = _settings(google_api_key="AIza-fake-google")
    r = resolve_llm(s)
    assert r.provider == "gemini"
    assert r.model == "gemini-flash-latest"
    assert r.base_url is None


def test_auto_raises_when_no_keys():
    with pytest.raises(AppError) as ei:
        resolve_llm(_settings())
    assert ei.value.code == "LLM_UNAVAILABLE"
    assert ei.value.status_code == 503


def test_explicit_openrouter_requires_key():
    with pytest.raises(AppError) as ei:
        resolve_llm(_settings(llm_provider="openrouter", openai_api_key="sk-openai"))
    assert "OPENROUTER_API_KEY" in str(ei.value)


def test_explicit_gemini_uses_google_key():
    s = _settings(llm_provider="gemini", google_api_key="AIza-fake", llm_model="gemini-flash-latest")
    r = resolve_llm(s)
    assert r.provider == "gemini"
    assert r.api_key == "AIza-fake"


def test_gemini_rejects_openai_shaped_key():
    with pytest.raises(AppError) as ei:
        resolve_llm(_settings(llm_provider="gemini", google_api_key="sk-proj-not-google"))
    assert "Google AI Studio" in str(ei.value)


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
    s = _settings(google_api_key="AIza-fake", llm_provider="gemini")
    chat = build_chat_model(s)
    assert isinstance(chat, ChatGoogleGenerativeAI)
