import logging
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent

# SOLUTION_DESIGN.md Appendix A co-location rule: compute, Postgres and Redis live in
# one region and only the model may be remote. Supabase Postgres and Upstash Redis are
# provisioned in ap-south-1, so an AWS_REGION default of us-east-1 silently splits the
# chatty tier across a continent (~200 ms per DB/Redis round trip, and this turn makes
# roughly a dozen of them). Fail toward the decided region, not AWS's historical one.
DESIGNED_AWS_REGION = "ap-south-1"

# E4.1 (issue #31), TECH_STACK.md section 7, decision D-4: Vertex AI is the only evaluated
# provider that serves Gemini in-region from India at all -- Bedrock/OpenAI both leave India
# (~200-250ms), Bedrock's own APAC profiles land in a different country. `asia-south1` (Mumbai)
# is therefore not an arbitrary regional preference, it is the entire reason Vertex was chosen
# over the Developer API's simpler API-key auth, which Google's own docs warn can silently route
# through the global endpoint regardless of configured location.
DESIGNED_GCP_VERTEX_LOCATION = "asia-south1"


class RegionMismatchError(RuntimeError):
    """Startup guard failure: compute is not co-located with Postgres/Redis."""


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
    # E4.1 (issue #31): the Vertex AI credential is a GCP project + ADC (Application Default
    # Credentials resolved from the environment -- a service account key file, workload identity,
    # or `gcloud auth application-default login`), not a string this app holds directly the way
    # `google_api_key` above is. `gcp_project` being set is therefore what "Gemini is configured"
    # actually means now; `google_api_key` alone is deliberately no longer sufficient (see
    # `llm.py::resolve_llm` -- the Developer/API-key path this project used before is exactly the
    # "trap" TECH_STACK.md section 7 warns can silently forfeit the in-region guarantee).
    gcp_project: str = ""
    gcp_vertex_location: str = DESIGNED_GCP_VERTEX_LOCATION
    llm_provider: str = "auto"  # auto | gemini | openai | openrouter
    llm_model: str = ""  # optional override; defaults per provider
    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""
    # E4.4 (issue #34): Upstash's native Redis-protocol connection string (`rediss://...`), a
    # different credential from the REST URL+token above -- opt-in, not derived from them. When
    # unset, the chat turn's two hot-path Redis calls (`load_turn_context`/`append_turn`) fall
    # back to the existing REST client, exactly today's behaviour. When set, they use
    # `redis.asyncio` instead: a real non-blocking round trip rather than a synchronous HTTPS
    # call that stalls the event loop for every concurrent request during a chat turn.
    upstash_redis_native_url: str = ""
    langsmith_api_key: str = ""
    langsmith_tracing: bool = False
    langsmith_project: str = "setuhaul-agentcore"

    # Blank locally and on first hosted BFF. Set only after AgentCore is deployed (step 9).
    agentcore_runtime_arn: str = ""
    aws_region: str = DESIGNED_AWS_REGION
    # Deliberate, temporary escape hatch for an out-of-region deploy (the live us-east-1
    # stack until the M1 migration lands). Off by default so assert_region_alignment()
    # fails startup loudly instead of emitting a log line that scrolls past.
    allow_region_mismatch: bool = False

    # M8 expiry sweeper (SOLUTION_DESIGN.md D2/D9, TECH_STACK.md section 5). The scheduled caller is
    # a machine with no Supabase identity, so the internal jobs endpoint authenticates on a shared
    # secret instead of a JWT -- an EventBridge connection's API-key authorization is exactly this
    # shape (AWS "Connections for API targets": basic, OAuth, API Key). Blank by default and the
    # endpoint refuses to run while it is blank, so an unconfigured deploy cannot expose an
    # unauthenticated capacity-releasing route.
    job_auth_token: str = ""
    # public.users.user_id the sweeper attributes its audit_logs rows to. audit_logs.user_id is
    # NOT NULL REFERENCES users(user_id), so an automated transition still needs a real row; the
    # honest answer is a dedicated service account, not a human planner's id borrowed for the
    # occasion. Blank means refuse, for the same reason as job_auth_token.
    job_actor_user_id: str = ""
    pending_confirmation_ttl_minutes: int = 15  # D9
    held_slot_ttl_seconds: int = 90  # D2
    expiry_sweep_batch_limit: int = 50

    # E4.4 (issue #34, M4): no timeout ceiling existed anywhere on the LLM path before this --
    # a slow provider response had nothing bounding it. `llm_call_timeout_seconds` bounds one
    # provider round trip (passed to the LangChain client itself); `turn_deadline_seconds` bounds
    # the whole driver turn (prefetch + every LLM call + every tool call across all rounds), so a
    # provider that times out on every retry still can't hang a request past a hard wall clock.
    # 30s per call is generous versus NFR-002's 2.5s target turn -- the point is a ceiling that
    # only fires on genuine provider trouble, not a budget tuned to the happy path.
    llm_call_timeout_seconds: float = 30.0
    turn_deadline_seconds: float = 45.0

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
    def resolved_aws_region(self) -> str:
        """This process's own region - the one its DB, Redis and AWS calls run from."""
        return (self.aws_region or "").strip()

    @property
    def agentcore_arn_region(self) -> str | None:
        """The region of the remote AgentCore runtime, read from its ARN, or None.

        Deliberately separate from resolved_aws_region. A live resource in the wrong
        region is a real co-location violation, but it is not *this* process being
        mis-regioned and it cannot be fixed by config - only by redeploying the runtime.
        Treating them as one number would make the BFF unbootable until that redeploy.
        """
        parts = (self.agentcore_runtime_arn or "").strip().split(":")
        if len(parts) >= 4 and parts[3].strip():
            return parts[3].strip()
        return None

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
    def ready_gemini(self) -> bool:
        """E4.1 (issue #31): `gcp_project` set, not `google_api_key` -- Vertex/ADC is the only
        Gemini path this app resolves to now; see the field's own comment for why."""
        return bool((self.gcp_project or "").strip())

    @property
    def ready_llm(self) -> bool:
        return bool(
            (self.openai_api_key or "").strip()
            or (self.openrouter_api_key or "").strip()
            or self.ready_gemini
        )

    @property
    def ready_upstash(self) -> bool:
        return bool(self.upstash_redis_rest_url and self.upstash_redis_rest_token)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def assert_region_alignment(
    settings: Settings | None = None,
    *,
    expected: str = DESIGNED_AWS_REGION,
) -> str:
    """Fail startup when compute is not co-located with Postgres/Redis.

    Called from every process entrypoint (FastAPI lifespan and the AgentCore handler)
    because each resolves its region independently. Raises rather than logs: a wrong
    region returns correct answers while costing ~200 ms on every DB and Redis round
    trip, so it cannot be allowed to fail quietly. Set ALLOW_REGION_MISMATCH=true to
    run out of region on purpose; that path logs CRITICAL and names the cost.

    A remote AgentCore runtime in another region is reported at CRITICAL rather than
    raised - see Settings.agentcore_arn_region for why the two are not one check.
    """
    resolved_settings = settings or get_settings()
    resolved = resolved_settings.resolved_aws_region
    arn_region = resolved_settings.agentcore_arn_region
    if arn_region and arn_region != expected:
        logger.critical(
            "AgentCore runtime is in %s but the design requires %s: every driver turn "
            "crosses a region boundary to reach the assistant. Fixed by redeploying the "
            "runtime, not by config.",
            arn_region,
            expected,
        )

    if resolved == expected:
        logger.info("region check ok: compute=%s (co-located with Postgres/Redis)", resolved)
        return resolved

    detail = (
        f"AWS region mismatch: resolved={resolved or '<unset>'} expected={expected}. "
        "Compute must share a region with Postgres and Redis (SOLUTION_DESIGN.md "
        f"Appendix A). Set AWS_REGION to {expected}, or set ALLOW_REGION_MISMATCH=true "
        "to accept the cross-region latency deliberately."
    )
    if resolved_settings.allow_region_mismatch:
        logger.critical("%s Continuing because ALLOW_REGION_MISMATCH is set.", detail)
        return resolved
    raise RegionMismatchError(detail)
