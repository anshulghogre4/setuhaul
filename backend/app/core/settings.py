from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Load gitignored local env consistently whether API starts from repo root,
        # backend/, or a tool-specific working directory.
        env_file=(
            BACKEND_DIR / ".env",
            BACKEND_DIR / ".env.local",
            REPO_DIR / ".env",
            REPO_DIR / ".env.local",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "SetuHaul API"
    environment: str = "development"
    api_prefix: str = "/api/v1"

    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_audience: str = "authenticated"
    database_url: str = ""

    # Sprint 2+ — declared so .env.example keys do not break settings load
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    google_api_key: str = ""
    llm_provider: str = "auto"  # auto | openai | openrouter | gemini
    llm_model: str = ""  # optional override; defaults per provider
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""
    langsmith_api_key: str = ""
    langsmith_tracing: bool = False
    langsmith_project: str = "setuhaul-agentcore"

    # Blank locally and on first hosted BFF. Set only after AgentCore is deployed (step 9).
    agentcore_runtime_arn: str = ""
    aws_region: str = "us-east-1"

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    # Starlette regex; allows Vercel preview/prod *.vercel.app without knowing the URL yet.
    cors_origin_regex: str = r"https://.*\.vercel\.app"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def agentcore_enabled(self) -> bool:
        return bool((self.agentcore_runtime_arn or "").strip())

    @property
    def supabase_issuer(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1"

    @property
    def supabase_jwks_url(self) -> str:
        return f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def ready_database(self) -> bool:
        return bool(self.database_url)

    @property
    def ready_auth(self) -> bool:
        return bool(self.supabase_url)

    @property
    def ready_openai(self) -> bool:
        """Backward-compatible alias: True if any ChatOpenAI-compatible key is set."""
        return self.ready_llm

    @property
    def ready_llm(self) -> bool:
        return bool(
            (self.openai_api_key or "").strip()
            or (self.openrouter_api_key or "").strip()
            or (self.google_api_key or "").strip()
        )

    @property
    def ready_upstash(self) -> bool:
        return bool(self.upstash_redis_rest_url and self.upstash_redis_rest_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()
