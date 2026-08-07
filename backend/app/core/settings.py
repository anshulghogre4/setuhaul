from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Prefer repo-root env files when API is started from backend/
        env_file=(".env", ".env.local", "../.env", "../.env.local"),
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
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""
    langsmith_api_key: str = ""
    langsmith_tracing: bool = False

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
