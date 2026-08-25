"""Unit tests for multi-provider LLM factory."""

from __future__ import annotations

import pytest
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from app.assistant.llm import OPENROUTER_BASE_URL, build_chat_model, resolve_llm
from app.core.errors import AppError
from app.core.settings import DESIGNED_GCP_VERTEX_LOCATION, Settings


def _settings(**kwargs) -> Settings:
    base = {
        "openai_api_key": "",
        "openrouter_api_key": "",
        "gcp_project": "",
        "gcp_vertex_location": DESIGNED_GCP_VERTEX_LOCATION,
        "llm_provider": "auto",
        "llm_model": "",
    }
    base.update(kwargs)
    return Settings(**base)


def test_auto_prefers_gemini_when_present():
    s = _settings(openai_api_key="sk-openai", openrouter_api_key="sk-or", gcp_project="proj-x")
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
    s = _settings(llm_provider="gemini", gcp_project="proj-x", llm_model="gemini-3.7-flash")
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
        resolve_llm(_settings(llm_provider="gemini", gcp_project="proj-x", gcp_vertex_location="us-central1"))
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
    s = _settings(gcp_project="proj-x", llm_provider="gemini")
    chat = build_chat_model(s)
    assert isinstance(chat, ChatGoogleGenerativeAI)


def test_build_chat_model_gemini_uses_vertex_not_api_key():
    s = _settings(gcp_project="proj-x", llm_provider="gemini")
    chat = build_chat_model(s)
    assert chat.vertexai is True
    assert chat.project == "proj-x"
    assert chat.location == DESIGNED_GCP_VERTEX_LOCATION
    assert chat.thinking_config == {"thinking_level": "high"}
