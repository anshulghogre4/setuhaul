import logging
import os
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

# Name of the gcloud CLI's config directory, and the ADC filename inside it. These are not our
# invention -- they mirror google-auth's own `_cloud_sdk.get_config_path()` /
# `get_application_default_credentials_path()` (verified against the pinned google-auth 2.56.3),
# and Google's ADC documentation names the same two locations explicitly:
# `$HOME/.config/gcloud/application_default_credentials.json` (POSIX) and
# `%APPDATA%\gcloud\application_default_credentials.json` (Windows), with `CLOUDSDK_CONFIG`
# overriding the directory. Re-stated here rather than imported because `_cloud_sdk` is a private
# module of that library; see `gcloud_adc_file()` for why we need the path at all.
_GCLOUD_CONFIG_DIR_NAME = "gcloud"
_GCLOUD_ADC_FILENAME = "application_default_credentials.json"


def gcloud_adc_file() -> Path:
    """Where `gcloud auth application-default login` writes ADC. The file may not exist.

    Second step of the three-step ADC chain google-auth walks (GOOGLE_APPLICATION_CREDENTIALS ->
    this file -> the GCE/Cloud Run metadata server). SetuHaul needs to *predict* that chain's
    outcome, not just let it run: issue #103's production incident was that the AgentCore
    container has none of the three, so `resolve_llm` picked Gemini on `gcp_project` alone and
    the failure only surfaced deep inside the first Vertex call. `Settings.gcp_adc_available`
    below turns that into a readiness check made before a provider is chosen.
    """
    override = (os.environ.get("CLOUDSDK_CONFIG") or "").strip()
    if override:
        return Path(override) / _GCLOUD_ADC_FILENAME
    if os.name == "nt":
        root = os.environ.get("APPDATA") or os.environ.get("SystemDrive") or "C:"
        return Path(root) / _GCLOUD_CONFIG_DIR_NAME / _GCLOUD_ADC_FILENAME
    return Path.home() / ".config" / _GCLOUD_CONFIG_DIR_NAME / _GCLOUD_ADC_FILENAME


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
    # AI Studio (generativelanguage.googleapis.com) key. E4.1/issue #31 had excluded this path as
    # the "trap" TECH_STACK.md section 7 warns about -- it can silently forfeit the in-region
    # guarantee. OWNER RULING 2026-09-01 (recorded on #103) re-admits it for the POC, in
    # production and locally, as the credential that needs no provisioning work because it is
    # already in SSM. See `ready_gemini_api_key` for the tradeoff being accepted.
    google_api_key: str = ""
    # E4.1 (issue #31): the Vertex AI credential is a GCP project + ADC (Application Default
    # Credentials resolved from the environment -- a service account key file, workload identity,
    # or `gcloud auth application-default login`), not a string this app holds directly the way
    # `google_api_key` above is. Vertex remains the *preferred* Gemini path whenever it is
    # configured (`resolve_llm` picks it over the key), because it is the only one that keeps
    # inference in `asia-south1`; the key path is the fallback the owner ruling re-admitted, not a
    # replacement for this one.
    gcp_project: str = ""
    # Issue #103 option (a) -- the deliberately *pragmatic POC* credential mechanism, recorded as
    # such rather than presented as the right long-term answer. A GCP service-account key JSON
    # carried as a string (SSM SecureString `/setuhaul/gcp-sa-key` -> env `GCP_SA_KEY_JSON`),
    # because the AgentCore container has no gcloud ADC file and no GCE metadata server, so every
    # step of google-auth's ADC chain comes up empty there and Gemini silently loses to OpenAI --
    # the exact production incident #103 records (LangSmith, 2026-09-01: gpt-4o-mini, P50 7.2s).
    # `llm.ensure_vertex_adc` materializes this to a 0600 container-local file and points
    # GOOGLE_APPLICATION_CREDENTIALS at it.
    #
    # The tradeoff being accepted: this is a long-lived key at rest in SSM. The recorded upgrade is
    # #103 option (b), Workload Identity Federation from the AgentCore execution role -- no key
    # material at all. That upgrade needs no change to this module: WIF also advertises itself
    # through GOOGLE_APPLICATION_CREDENTIALS (as an external-account config file), which
    # `gcp_adc_available` below already accepts, so switching means dropping this param and adding
    # that one env var.
    gcp_sa_key_json: str = ""
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
    # D2's four-state promise lifecycle (SOLUTION_DESIGN.md section 4 / section 7.1, issue #53).
    # OFF by default, and that default is the point rather than timidity: the schema change this
    # feature needs (20260829134929_d2_held_state_dock_occupancy.sql) can be applied to production
    # with *zero* behaviour change while this stays false, because request_slot keeps committing
    # straight to PENDING_CONFIRMATION exactly as it does today. Applying a migration and switching
    # on a booking-path behaviour change are then two separately revertible decisions instead of
    # one. Flip to true only after the migration is applied AND the driver-chat HELD screens
    # (E5.1's 4 gated screens) are ready to render the intermediate state -- turning it on sooner
    # would leave `request_slot` returning a `HELD` outcome no UI knows how to display.
    # Flipped to True 2026-08-31 by owner decision, after: the D2 migration was applied to
    # production and verified (613 rows backfilled, exclusion predicate in place), all SIX
    # consuming reads became hold-aware (#83 driver tools, #84 planner displacement+snapshot,
    # #85 carrier derivation, #86 driver /context + assistant prefetch, #87 carrier filter),
    # and the flag-off path was proven byte-identical throughout. request_slot now creates a
    # HELD row first (D2's two-phase contract); confirm_held_slot and the M8 HELD sweeper leg
    # are live. Rolling back to False restores single-phase booking instantly with no schema
    # change -- but note holds live at that moment stay invisible to reads for up to one TTL
    # (90s) while still consuming capacity (documented in holds.hold_reads_enabled()).
    two_phase_hold_enabled: bool = True

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
    def gcp_adc_available(self) -> bool:
        """True when google-auth's ADC chain will actually resolve credentials in this process.

        Checks the same first two steps google-auth checks, in the same order:
        GOOGLE_APPLICATION_CREDENTIALS (a *path* to a service-account key or an external-account /
        Workload-Identity config -- the variable never carries inline JSON), then the gcloud
        well-known file. The third step, the GCE/Cloud Run metadata server, is deliberately not
        probed: it needs a network round trip, and SetuHaul's compute is AgentCore on AWS where it
        can never succeed. If this app is ever hosted on GCP, that omission becomes a real gap and
        this is the line to revisit.

        The env var is only honoured when the file it names exists -- a stale
        GOOGLE_APPLICATION_CREDENTIALS pointing at nothing makes `google.auth.default()` raise
        rather than fall through, so treating "set" as "ready" would recreate #103's failure shape
        (Gemini selected, blows up on the first Vertex call) instead of degrading to OpenAI.
        """
        explicit = (os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or "").strip()
        if explicit and Path(explicit).is_file():
            return True
        try:
            return gcloud_adc_file().is_file()
        except OSError:  # unresolvable HOME/APPDATA -- treat as "no ADC", never as a crash
            return False

    @property
    def ready_gemini_vertex(self) -> bool:
        """The Vertex shape: a project *and* a credential ADC can actually resolve.

        Issue #103 tightened this from "project id set". Before, `GCP_PROJECT` alone made
        `resolve_llm` choose Gemini, and the missing credential only surfaced as a
        `DefaultCredentialsError` from inside the first live Vertex call -- a 503 mid-turn instead
        of the documented fallback. Requiring a credential *shape* too means an under-provisioned
        deployment falls through AUTO_ORDER cleanly, which is what the fallback exists for.
        """
        if not (self.gcp_project or "").strip():
            return False
        return bool((self.gcp_sa_key_json or "").strip()) or self.gcp_adc_available

    @property
    def ready_gemini_api_key(self) -> bool:
        """The `GOOGLE_API_KEY` shape, whichever endpoint ends up serving it.

        OWNER RULING 2026-09-01 (recorded on issue #103) re-admits this path, which E4.1/issue #31
        had deliberately excluded: "if ADC is not working we can simply use API key based with no
        worries." Verified empirically the same day through this app's own
        `ChatGoogleGenerativeAI` dependency -- the key serves `gemini-3.7-flash` today.

        One key, two possible endpoints, chosen in `llm._gemini_key_backend`: Vertex **express
        mode** (preferred -- genuinely Vertex-served, so it keeps more of E4.1's intent) or plain
        AI Studio at generativelanguage.googleapis.com.

        The tradeoff, stated plainly rather than buried: neither is pinned to `asia-south1`. E4.1
        chose regional Vertex precisely because every alternative leaves India, so selecting a key
        path relaxes the SS11 data-residency goal. Relaxed by an explicit owner decision for the
        POC -- not forgotten, and not a bug for a later reader to "fix" silently.
        `ready_gemini_vertex` is preferred over this whenever both are configured.
        """
        return bool((self.google_api_key or "").strip())

    @property
    def ready_gemini(self) -> bool:
        """Either Gemini credential shape. Vertex is preferred at resolve time; see `resolve_llm`."""
        return self.ready_gemini_vertex or self.ready_gemini_api_key

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
