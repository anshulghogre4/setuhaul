# Comparison — deployment (infrastructure and hosting)

> Scope: `DEPLOYMENT/DEPLOYMENT.md` (read in full) + `TECH-STACK/TECH_STACK.md` §1, §7, §13 against the
> **actually deployed and configured** infrastructure: `agentcore/aws-targets.json`, `agentcore/agentcore.json`,
> `agentcore/.cli/deployed-state.json`, `agentcore/cdk/{bin,lib}`, `backend/Dockerfile`, `deploy/*.json`
> (`ecs-express-infra-trust.json`, `ecs-task-execution-trust.json`, `express-create.json`,
> `express-primary-container.json`, `apprunner-create.json`), `.github/workflows/ci.yml`,
> `frontend/vercel.json`, `backend/app/assistant/observability.py`, `backend/app/core/settings.py`, a
> full-repo grep for `sentry`, and `wiki/handoff.md`'s most recent confirmed-live entries. Read 2026-08-22.
> **Comparison only — nothing under `backend/`, `frontend/`, or `supabase/` was edited.**
>
> This is the seventh comparison pass and the first to check live infrastructure against the deployment
> design — the six prior passes (architecture, backend routers/services, backend core/scheduling/db,
> frontend, AI-assistant, latency) compared application code. Builds on `COMPARISON-ai-assistant.md` and
> `COMPARISON-latency.md` rather than re-deriving their AgentCore/region findings — both already established
> `backend/app/core/settings.py:48`'s `aws_region: str = "us-east-1"` default and its knock-on effects; that
> is issue #31 (E4.1)/#12 (E0.2), owned by the ai-engineer and latency passes, and is cited, not repeated,
> below. This pass's job was to check one layer beneath the code default: **what the deploy-time
> infrastructure configuration itself says**, independent of what the application would default to if that
> config were absent.
>
> **Tags**: **Keep as-is** · **Needs improvement** · **Functional/non-functional requirement mapping** ·
> **Wrong optimisation flag**.

---

## 0 · Method and what was verified against current external docs

Per the mandatory deep-research rule, two claims below were checked against current AWS documentation
rather than asserted from memory or from the design docs' own (undated-at-the-detail-level) tables:

1. **Is AgentCore Runtime actually available in `ap-south-1` today?** Confirmed yes — AWS's own June 2026
   announcement ("Amazon Bedrock AgentCore now available in four additional AWS Regions") and the AgentCore
   release notes place Mumbai among the regions AgentCore Runtime/Identity/Memory/Gateway/Observability
   support, consistent with `TECH_STACK.md` §2's "AgentCore is now available in `ap-south-1`" claim. This
   matters for tag 4 below: the live `us-east-1` deployment is **not** explained by a region-availability
   gap — the target region was reachable the whole time.
   Sources: [Amazon Bedrock AgentCore now available in four additional AWS Regions](https://aws.amazon.com/about-aws/whats-new/2026/06/amazon-bedrock-agentcore-four-additional-regions/),
   [Release notes for Amazon Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/release-notes.html)
2. **Is AWS App Runner actually in maintenance mode, and is `SubscriptionRequiredException` explained by
   that?** Confirmed — AWS's own March 31, 2026 service-availability update states App Runner is closed to
   new customers effective April 30, 2026, and directs migrators to **ECS Express Mode** by name, calling it
   the preserver of "App Runner's operating simplicity." `deploy/apprunner-create.json` exists in this repo
   as a dead artifact of an App Runner attempt that `wiki/handoff.md` (2026-08-14 01:00 IST) records failing
   with exactly `SubscriptionRequiredException` — the account was never grandfathered in. The team's fallback
   to ECS Express Mode is therefore AWS's own currently-recommended migration path, not an ad hoc workaround.
   Sources: [AWS App Runner (Maintenance Mode) tracking issue](https://github.com/hashicorp/terraform-provider-aws/issues/47161),
   [AWS Service Availability Updates, March 2026](https://aws.amazon.com/about-aws/whats-new/2026/03/aws-service-availability/)

Everything else below is read directly from the config files named in the header, or from `wiki/handoff.md`
entries that record a directly-inspected live artifact (an actual ARN, an actual S3 zip, an actual ECS task
definition) rather than a CLI exit code — the same "verify the deployed artifact, not the status" discipline
`DEPLOYMENT.md` §2.3 itself demands.

---

## 1 · AgentCore Runtime is deployed in `us-east-1` — confirmed at three independent layers, not one

`DEPLOYMENT.md` §0/§2, `TECH_STACK.md` §2: **AgentCore Runtime, `ap-south-1`, ARM64.**

Live reality, checked at three layers that would each independently have to be wrong for the design to be
right:

| Layer | File | Value |
|---|---|---|
| Deploy target list | `agentcore/aws-targets.json` | `"region": "us-east-1"` |
| Runtime's own baked env var | `agentcore/agentcore.json` line 30 | `"AWS_REGION": "value": "us-east-1"` |
| **The actual deployed resource** | `agentcore/.cli/deployed-state.json` | `runtimeArn: arn:aws:bedrock-agentcore:us-east-1:118490268011:runtime/SetuHaulAgent_SetuHaulAgent-18B4pX4XF1` |

The third row is not a config file that could be stale relative to reality — it **is** AWS's own record of
where the resource lives, downloaded by the AgentCore CLI itself. There is no interpretation under which
this agent is anywhere but `us-east-1`.

**Keep as-is**: none of this — no part of the current AgentCore region configuration matches the design.

**Needs improvement**: Update `agentcore/aws-targets.json`'s `region` field to `ap-south-1`, and
`agentcore/agentcore.json`'s runtime `envVars` entry for `AWS_REGION` to `ap-south-1`, then run
`agentcore.cmd deploy` (preceded by the mandatory codezip staging per `AGENTS.md`/§2.2 — cite, don't
re-derive: that mechanism is #32/E4.2's territory, not this pass's). This is two JSON edits plus a redeploy,
not a code change — squarely an infrastructure fix. Note this is **independent of and in addition to**
`backend/app/core/settings.py:48`'s code-level default (#31/#12): fixing the code default alone does not
move the deployed runtime, because `agentcore.json`'s baked `envVars` entry overrides whatever the code
would otherwise default to. Both must change together or the code fix is inert for AgentCore specifically.

**Functional/non-functional requirement mapping**: No formal `NFR-*` ID exists for compute/data co-location
today — `COMPARISON-latency.md` F14 already recommended creating one ("Co-location of compute + Postgres +
Redis... No NFR exists — recommend creating one"). This finding is additional evidence for that
recommendation, not a new ask.

**Wrong optimisation flag**: This is the agent definition's own template case, reconfirmed at the
infrastructure-config layer rather than only the code-default layer: nothing about the AgentCore Runtime
*errors*. `agentcore.cmd deploy`/`status` report success, the runtime is `READY`, and per §0 above `ap-
south-1` was reachable the entire time — there was never a technical reason to be in `us-east-1`. The entire
in-region-latency argument that justifies choosing AgentCore + Vertex `asia-south1` + Supabase + Upstash all
in the same region is void while this persists, and it is void at the infrastructure layer even if the
application code is later fixed to *assume* `ap-south-1` — the deployed resource itself has to move.

---

## 2 · The ECS/REST backend is also deployed in `us-east-1` — a second, independently-confirmed target, not a restatement of #1

`DEPLOYMENT.md` §0/D-1, `TECH_STACK.md` §1/§2: **ECS Fargate, `ap-south-1`.**

This is a distinct finding from §1, not the same fact restated: it is the *other* deployment target, and it
is wrong in its own deploy-config files, independent of AgentCore's.

| File | Evidence |
|---|---|
| `deploy/express-create.json` | `"image": "118490268011.dkr.ecr.us-east-1.amazonaws.com/setuhaul-api:latest"`; `{"name": "AWS_REGION", "value": "us-east-1"}` baked directly into the container's `environment` |
| `deploy/express-primary-container.json` | Identical `us-east-1` ECR image reference and `AWS_REGION` env var |
| `deploy/apprunner-create.json` | Same `us-east-1` ECR image reference (dead artifact per §0.2 above, but confirms the ECR repo itself is `us-east-1`) |
| `wiki/handoff.md` (2026-08-14 01:00 IST) | Live URL `https://se-e5cad5d30b1a4f22b9aeea032827f81b.ecs.us-east-1.on.aws` |
| `wiki/handoff.md` (2026-08-17 07:20 IST) | `aws ecs update-express-gateway-service` on `arn:aws:ecs:us-east-1:118490268011:service/default/setuhaul-api` |

So the REST backend isn't merely *at risk* of inheriting a wrong default from `settings.py` — its ECR
repository, its container image tag, and its running ECS service ARN are **all** `us-east-1`, set directly
in the CLI-create payloads and confirmed by the live service ARN.

**Needs improvement**: This means an ECR repository migration (`us-east-1` → `ap-south-1`, a new repo, a
re-push of the image), not just an env var flip. Update the `AWS_REGION` value and the ECR host in
`express-create.json`/`express-primary-container.json`, create the ECS Express service fresh in `ap-south-1`
(Express Mode services are not region-migrated in place), and cut over DNS/`VITE_API_BASE_URL` together with
the AgentCore move in §1 — `DEPLOYMENT.md` §7's "deploy steps 4 and 5 together or not at all" rule applies
here too, since a split migration would put the driver-chat and REST paths in different regions against one
shared `ap-south-1` database, which is worse than the current single-region-wrong state.

**Functional/non-functional requirement mapping**: Same as §1 — feeds the not-yet-formalised co-location NFR.

**Wrong optimisation flag**: Same underlying defeat as §1, but worth stating separately because it means
the region mistake isn't confined to the chat path — **every REST call** (planner, ops, gate, carrier, admin
— the five non-chat surfaces) also crosses `us-east-1` ↔ `ap-south-1` to reach Postgres/Redis today, not
just driver chat.

---

## 3 · ECS is Express Mode via manual CLI-create JSON, with zero IaC — matches the read-only check, and is a defensible choice for a different reason than expected

`DEPLOYMENT.md` §0 contrasts a hand-built "Fargate task+service+ALB stack" against Express Mode without
naming which the live system uses.

**Confirmed**: `deploy/ecs-express-infra-trust.json`, `deploy/ecs-task-execution-trust.json`,
`express-create.json`, and `express-primary-container.json` are IAM trust policies and a single Express
Mode service-create payload — there is no Terraform, CDK, or CloudFormation for ECS anywhere in the repo.
`agentcore/cdk/` exists but is the **AgentCore CLI's own vended scaffold** (`agentcore.json`'s
`"managedBy": "CDK"`; `agentcore/cdk/bin/cdk.ts` reads `agentcore/aws-targets.json` and `agentcore.json`
directly and synthesizes only `AWS::BedrockAgentCore::*` resources — harnesses, payments, gateways). It
provisions **zero** ECS resources. So "ECS has no IaC" is fully confirmed, not partially.

**Keep as-is**: Given §0.2's verified finding (App Runner in maintenance mode, ECS Express Mode is AWS's own
recommended replacement), the *choice* of Express Mode over a hand-rolled Fargate+ALB stack is defensible on
its own terms — Express Mode is meant to trade some IaC-level control for App Runner-like simplicity, which
is exactly what happened here after App Runner rejected the account. `DEPLOYMENT.md`'s ALB section (§0,
"TLS termination and health checks — not load distribution... nothing to distribute") already argues against
building autoscaling complexity this workload doesn't need; Express Mode is consistent with that argument
even though the document doesn't name Express Mode explicitly. This is a case the design didn't anticipate
(it predates knowing App Runner would reject the account) but doesn't need to be treated as a gap.

**Needs improvement**: The `deploy/apprunner-create.json` payload is dead — App Runner will not accept new
customers per §0.2. Leaving it in the repo without a comment risks a future reader trying it again and
re-discovering the `SubscriptionRequiredException` from scratch. A one-line comment or a move to a
`deploy/deprecated/` path would close this cheaply.

**Functional/non-functional requirement mapping**: None directly — this is a process/tooling finding, not a
correctness or latency one.

**Wrong optimisation flag**: None — Express Mode is the right call here for a reason outside the design
docs' own knowledge at time of writing.

---

## 4 · ECS is deployed as `linux/amd64`, not ARM64 — and the design's own stated reason for pairing ECS's architecture to AgentCore doesn't actually apply under AgentCore's chosen deploy mode

`DEPLOYMENT.md` §0/D-1: *"ARM64 because AgentCore requires it (§2) and matching keeps **one build
artifact** rather than two."* `TECH_STACK.md` §2: *"ARM64 is mandatory, so ECS matches it... Build ARM64
once, deploy twice."*

**Confirmed live**: `backend/Dockerfile` has no `--platform` directive and no ARM64-specific base image tag
(`FROM python:3.12-slim-bookworm`, architecture-neutral). `wiki/handoff.md` (2026-08-17 07:20 IST) records
the actual build command used: **`docker build --platform linux/amd64` from `backend/`**, pushed to ECR and
rolled onto ECS. None of `express-create.json`/`express-primary-container.json` set a `runtimePlatform`
block (ECS/Fargate defaults to `X86_64` when this is absent). So the live ECS image is explicitly `amd64`,
not ARM64.

**Needs improvement**: If the ECS/AgentCore region migration in §§1–2 proceeds, add
`--platform linux/arm64` to the Dockerfile build step (or the CI/build script that invokes it) and set
`"runtimePlatform": {"cpuArchitecture": "ARM64", "operatingSystemFamily": "LINUX"}` in
`express-create.json`. This is a genuine cost lever independent of the region question — Graviton
(ARM64) Fargate pricing is materially lower per vCPU-hour than `X86_64`, which is relevant given `DEPLOYMENT.md`
§0's own "spending credits rather than a free tier" framing.

**Functional/non-functional requirement mapping**: None formal — cost, not a stated NFR.

**Wrong optimisation flag**, stated carefully because it cuts against the design doc itself, not just
against live code: **AgentCore's actual deploy mechanism (`"build": "CodeZip"` in `agentcore.json`, matching
`DEPLOYMENT.md` §2.1's own "direct code deployment" decision) does not produce a container image at all** —
it zips Python source, which AWS runs on managed ARM64 compute regardless of what a customer builds
elsewhere. The design's stated rationale for choosing ARM64 on ECS — *"matching keeps one build artifact...
build ARM64 once, deploy twice"* — describes a container-mode AgentCore deployment (§2.1's *other*,
not-chosen mode) and does not describe the CodeZip mode the design itself picked. There was never a shared
container artifact to keep singular: AgentCore's zip and ECS's Docker image are two artifacts by
construction, independent of architecture choice. **This doesn't remove the case for ARM64 on ECS** (the
Graviton cost saving above still stands on its own) — it means the design document's own stated *reason*
for the ARM64 decision doesn't hold given the deploy mode the same document chose one section earlier, and
a future reader shouldn't cite "matching AgentCore's artifact" as the justification when revisiting this.

---

## 5 · CI has no deploy stage at all — narrower gap than `DEPLOYMENT.md` §6's own pipeline describes

`DEPLOYMENT.md` §6: `push → lint + typecheck → unit tests → integration → invariant queries → build →
[manual gate] → deploy → post-deploy verify`.

**Confirmed live**: `.github/workflows/ci.yml` runs exactly two jobs — `backend-unit` (`pytest tests/unit`)
and `frontend-build` (typecheck + Vite build). There is no integration-test job, no invariant-query job, and
no deploy job of any kind (manual-trigger or otherwise) — deploy is 100% outside CI, run by a human from a
local shell per `wiki/handoff.md`'s many `agentcore.cmd deploy --yes` / `aws ecs update-express-gateway-
service` entries.

**Keep as-is**: The **absence of a deploy stage in CI** is not itself a gap — `DEPLOYMENT.md` §1 explicitly
wants a human manual gate ("No staging tier means the gate is a person"), and a fully local/CLI deploy
satisfies that by construction.

**Needs improvement**: The **absence of the integration and invariant-query stages inside CI** is a real
gap against §6's own table, separate from the deploy question — today, a push to `main`/`hosting` is
gated only by unit tests and a frontend build, not by the §9.2 stress fixtures or the §10 invariant queries
that the design places *before* the human deploy gate. This is a testing-pipeline gap, not a hosting-region
or compute-topology one — noted here because it lives in the same file this pass was asked to check
(`.github/workflows/*.yml`), but the actual fix (writing/wiring the integration and invariant-query jobs) is
closer to `TESTING_STRATEGY.md`'s territory than this pass's. Flagged rather than owned.

**Functional/non-functional requirement mapping**: None directly.

**Wrong optimisation flag**: None.

---

## 6 · Frontend host is Vercel — confirmed, and explicitly not a gap

`DEPLOYMENT.md` §0 D-2/§3, `TECH_STACK.md` §9: Cloudflare Pages vs Vercel is **deliberately unsettled**,
turning on licensing rather than performance, "revisit before first deploy."

**Confirmed live**: `frontend/vercel.json` (SPA rewrite rule) plus extensive `wiki/handoff.md` history
(Vercel project `setuhaul`, production URL `setuhaul-roan.vercel.app`, multiple deploys 2026-08-14) show
Vercel is the actual live host today.

**Keep as-is** — exactly per this pass's own instructions: this is not a gap. `DEPLOYMENT.md` itself frames
the choice as open and licensing-driven, not a design target that live reality diverges from. Worth naming
explicitly for the owner: the "revisit before first deploy" open item (`DEPLOYMENT.md` open item 7) has, in
effect, already been superseded by events — there **has** been a first deploy, to Vercel, and it has been
live since at least 2026-08-14. If Cloudflare Pages is still on the table, that decision window has already
closed once by default. This is worth a deliberate yes/no from the owner, not a silent continuation.

**Functional/non-functional requirement mapping**: None — explicitly a licensing decision per the design's
own framing, not a latency or residency one (both hosts are sub-100 ms in India per `DEPLOYMENT.md` §0).

**Wrong optimisation flag**: None.

---

## 7 · Monitoring stack: CloudWatch + LangSmith present and working within a known limitation; Sentry fully absent

`DEPLOYMENT.md` §8 (D-3): **CloudWatch + Sentry + LangSmith**, three non-overlapping jobs — CloudWatch for
infra/app metrics, Sentry for unhandled exceptions with stack traces (frontend and backend), LangSmith for
LLM traces.

**Confirmed live — CloudWatch + LangSmith**: `backend/app/assistant/observability.py` wires OpenTelemetry
histograms (`messages_loaded_metric`, `response_length_metric`) behind a try/except that degrades cleanly
when the distro is absent, plus a LangSmith `trace()` context manager (`chat_turn_trace`) with metadata
sanitisation (`sanitize_for_trace` redacts secret-shaped keys before anything reaches a trace). This
functionally matches §8's CloudWatch+LangSmith half. The known open **ADOT `aws_auth_session`
credential-recursion bug** that limits CloudWatch to the platform-level `AgentCore.Runtime.Invoke` span
(rather than tool-level spans) is already recorded live in `wiki/handoff.md` (2026-08-16 21:05 IST, 2026-08-17
18:40 IST) — cited here per this pass's instructions, not re-discovered as new.

**Confirmed live — Sentry is completely absent**, deepening the read-only pre-check's finding rather than
merely restating it:
- No `sentry-sdk` (or any `sentry*` package) in `backend/pyproject.toml`, `backend/requirements.txt`, or
  `backend/uv.lock`.
- No `sentry` reference anywhere in `backend/app/` (a repo-wide grep excluding vendored/`.venv` paths
  returns zero matches; the only substring hits found via a broader search were false positives inside
  `.venv`-vendored Google protobuf files matching `...DnsEntry`/`...Entry` case-insensitively against
  `sentry`, not real references).
- No `SENTRY_DSN` (or equivalent) field in `backend/app/core/settings.py` — not even declared blank the way
  `openai_api_key`/`langsmith_api_key` are, which would at least signal intent.
- No `@sentry/*` package in `frontend/package.json`.

So this isn't "Sentry is configured but pointed nowhere" — there is no code path, dependency, or settings
field anywhere that Sentry could hang off of. Standing up Sentry here is greenfield work, not a
configuration fix.

**Keep as-is**: The CloudWatch+LangSmith half of D-3.

**Needs improvement**: Add `sentry-sdk` (FastAPI integration) to `backend/pyproject.toml`, a `sentry_dsn: str
= ""` field to `Settings` (SSM-sourced per `DEPLOYMENT.md` §5, following the existing pattern for
`langsmith_api_key`), and `Sentry.init()` at app startup gated on that field being non-empty (same
degrade-safe pattern `observability.py` already uses for OTEL). Add the frontend `@sentry/react` package and
initialise it in the SPA entrypoint. Both are additive, low-risk changes — no existing behavior depends on
Sentry's absence.

**Functional/non-functional requirement mapping**: No `NFR-*` ID names error-observability directly, but
`DEPLOYMENT.md` §8's own signal table lists "API error rate... sustained 5xx" as an alert condition —
without Sentry, that alert has no stack-trace-level source to point at, only an aggregate rate.

**Wrong optimisation flag**: None on the CloudWatch/LangSmith side. On Sentry: none — this is a straightforward
absence, not a misdirected effort.

---

## 8 · Upstash Redis: the live-wired instance is `us-east-1`, not `ap-south-1` — a finding neither prior comparison pass surfaced, because it required cross-checking `wiki/handoff.md` against `TECH_STACK.md`'s own "confirmed" claim rather than taking the claim at face value

This is the pass's most significant original finding, so it's laid out in full rather than compressed.

`TECH_STACK.md` §13 item 4 states: *"~~Is Upstash actually in `ap-south-1`?~~ ✅ **CONFIRMED 2026-08-21** via
the Upstash console — AWS Mumbai (`ap-south-1`), Free Tier, **Global** replication."* `COMPARISON-latency.md`
F14's region-audit table takes this at face value: *"Upstash Redis | `ap-south-1`, native protocol | Region
✅ `ap-south-1`... | §13 item 4."*

**`wiki/handoff.md` tells a different, more recent-to-the-live-system story.** Under the heading
**"2026-08-17 05:35 IST — Upstash region migration"**:

> *"Owner created a new Upstash Redis database with primary region `us-east-1` (previous DB was `ap-south-1`
> Mumbai, ~600ms round-trip from the `us-east-1` AgentCore/ECS compute — confirmed via CloudWatch trace
> deltas showing ~190ms/call). New `UPSTASH_REDIS_REST_URL`/`UPSTASH_REDIS_REST_TOKEN` saved to
> `.env`/`.env.local` and **pushed to SSM via `docs/scripts/put_hosting_ssm.py`**. Old Mumbai DB left in
> place (owner's call whether to delete)."*

The handoff's own "Current state" summary (line 139) reaffirms this as the standing fact, not a
since-superseded one: *"Hosted stack... is now on: async event-loop entrypoint, escalation resolution-note
persistence, **Upstash `us-east-1`** + batched Redis calls..."* Nothing dated after 2026-08-17 in
`wiki/handoff.md` records a reversal.

**The two documents are describing two different Upstash databases, and only one of them is what the
live application's SSM parameters actually point at.** The `ap-south-1` "Mumbai" instance `TECH_STACK.md`
confirmed via the console on 2026-08-21 is very likely the **old, explicitly-orphaned** database — "left in
place" per the quote above, not deleted, and therefore still visible and inspectable in the Upstash console
four days later. The database the live ECS/AgentCore compute actually reads and writes through
`UPSTASH_REDIS_REST_URL`/`UPSTASH_REDIS_REST_TOKEN` in SSM is the **`us-east-1`** one created that same day.

This also directly explains a suspicion `TECH_STACK.md` already raised without connecting it to this cause
— open item 4a: *"Is the Upstash database named 'langsmith test' the right one? It is Free Tier and carries
a scratch-sounding name. Confirm it is SetuHaul's actual store before a production path depends on it."*
That is exactly the symptom of checking the console and finding a plausible-but-possibly-wrong database,
without cross-referencing the one piece of evidence that would resolve it: `wiki/handoff.md`'s own dated
record of which database's credentials were actually written to SSM.

**Keep as-is**: Nothing — the live-wired instance does not match the design target on region, and the
"confirmed" claim in the design doc is very likely checking the wrong (orphaned) resource.

**Needs improvement**: (1) Confirm directly which Upstash database's REST URL is presently in SSM
`/setuhaul/upstash-redis-rest-url` — this resolves both this finding and open item 4a in one check, and
should be done before anything else in this section is acted on. (2) If it is indeed the `us-east-1`
instance, the fix is **not** "move Redis back to `ap-south-1`" in isolation — it is to fix compute's region
(§§1–2 above) and *then* point the app at an `ap-south-1` Upstash instance (either restore the orphaned
Mumbai DB or provision a fresh one), so cache and compute move together rather than the cache chasing
whichever region compute happens to be in. (3) Decide the fate of the orphaned Mumbai DB — delete it (it is
presumably still accruing on the Free Tier, so likely zero cost, but it is a second copy of session-scoped
data sitting unmanaged) or repurpose it as the target of the fix in (2).

**Functional/non-functional requirement mapping**: `TECH_STACK.md` §11 (data residency) — this is a second,
independent residency exposure beyond the compute-region one in §§1–2: driver/session conversational state
now also crosses to `us-east-1`, on top of the primary business database traffic. Feeds the same
not-yet-formal co-location NFR as §1's mapping.

**Wrong optimisation flag** — the clearest one in this pass: the 2026-08-17 fix was reasoned correctly in
isolation (cross-region Redis round trips were real and measured — ~190 ms/call, confirmed via CloudWatch)
but solved the symptom by moving the *cheaper-to-move, bounded, non-authoritative* piece (Redis) to match
the *wrongly-placed, harder-to-move* piece (compute), rather than fixing compute's region and leaving Redis
where the design always wanted it. This is latency lever discipline pointed at the wrong target: it made a
genuinely wrong regional topology internally consistent (Redis now matches compute) instead of correcting
it (both matching Postgres, which never moved). The next region fix must not repeat this pattern — moving
AgentCore/ECS to `ap-south-1` (§§1–2) must be paired with moving Upstash back, in the same change, or the
project will have "fixed" the region problem three times by successively relocating whichever piece is
easiest to relocate.

---

## 9 · Secrets and configuration store — matches design, one gap not yet a gap in practice

`DEPLOYMENT.md` §5: AWS SSM Parameter Store, never in the repo/changelog.

**Confirmed live**: `express-create.json`/`express-primary-container.json` reference secrets exclusively via
`"valueFrom": "/setuhaul/..."` SSM parameter paths (`google-api-key`, `openai-api-key`,
`upstash-redis-rest-url`/`-token`, `langsmith-api-key`, `database-url`, `supabase-url`) — no secret values
appear in any deploy config file in the repo. `wiki/handoff.md` corroborates: `docs/scripts/put_hosting_ssm.py`
is the standing mechanism, and multiple entries confirm SSM writes rather than inline secrets.

**Keep as-is** — this matches `DEPLOYMENT.md` §5 exactly, including the "configuration that is not secret
but is environment-specific... belongs in SSM too" principle: `express-create.json`'s plain `environment`
block (region, port, LangSmith project name, CORS origins) versus its `secrets` block (the SSM-sourced
values) cleanly separates the two categories the design asks for.

**Needs improvement**: None found.

**Functional/non-functional requirement mapping**: None — this is a security/config hygiene practice, not
a latency/residency NFR.

**Wrong optimisation flag**: None.

---

## Summary table

| # | Area | Design target | Live state | Tag(s) |
|---|---|---|---|---|
| 1 | AgentCore region | `ap-south-1` | `us-east-1` (target list, baked env var, **and** the live ARN itself) | Needs improvement · Wrong optimisation flag |
| 2 | ECS/REST region | `ap-south-1` | `us-east-1` (ECR host, baked env var, live service ARN) | Needs improvement · Wrong optimisation flag |
| 3 | ECS compute mode | Fargate-as-code (implied) | Express Mode via manual CLI JSON, zero IaC | Keep as-is (App Runner maintenance mode makes this the AWS-recommended path) |
| 4 | ECS architecture | ARM64 | `linux/amd64` (explicit `--platform` in build history; no `runtimePlatform` in task config) | Needs improvement · Wrong optimisation flag (re: the design's own stated rationale) |
| 5 | CI/CD pipeline | lint→unit→integration→invariant→build→gate→deploy→verify | lint+unit+build only; no integration/invariant stage; deploy fully manual (by design) | Needs improvement (testing stages only; manual deploy is Keep as-is) |
| 6 | Frontend host | Deliberately unsettled (Cloudflare vs Vercel) | Vercel, live since 2026-08-14 | Keep as-is — but flag that the "decide before first deploy" window has already passed |
| 7 | Monitoring | CloudWatch + Sentry + LangSmith | CloudWatch + LangSmith present (known ADOT limitation, already recorded); Sentry entirely absent, front and back | Keep as-is (CW/LangSmith) · Needs improvement (Sentry) |
| 8 | Upstash region | `ap-south-1` | Live-wired instance is `us-east-1` per SSM (2026-08-17); a separate, orphaned `ap-south-1` instance is what `TECH_STACK.md` §13 item 4 most likely actually checked | Needs improvement · Wrong optimisation flag |
| 9 | Secrets/config | SSM only | SSM only, correctly split secret vs non-secret | Keep as-is |

---

## Forks for the owner, not silently decided

1. **Sequencing #1/#2/#8 (region) against #31/#32/E4.1/E4.2/E0.2 (code defaults and deploy hygiene).** The
   code-level `aws_region` default fix (#12/E0.2) and the codezip staging-atomicity fix (#32/E4.2) are
   already tracked elsewhere and are prerequisites for a *safe* redeploy, but they do not by themselves move
   any deployed resource — the three infrastructure-layer changes in §§1, 2, and 8 are independent work
   items that need their own tracked issue(s) if they aren't already implicitly assumed inside M4's "AgentCore
   rebuild" milestone. Confirm whether M4 already scopes the `aws-targets.json`/`agentcore.json`/`deploy/*.json`
   edits, or whether a new issue is needed — this pass found the gap but the milestone plan predates this
   pass's detailed findings.
2. **Which Upstash database is actually live** (§8) needs a direct check (read the current SSM parameter
   value, or the Upstash console's project list) before deciding whether to restore the orphaned Mumbai DB
   or provision fresh — don't guess between the two options above without that one lookup.
3. **The Cloudflare-vs-Vercel decision** (§6) — noting that a live Vercel deployment already exists doesn't
   answer the licensing question `DEPLOYMENT.md` open item 7 poses; it just means "unsettled" has an
   unacknowledged default answer in production right now. Worth an explicit decision either way.
4. **ARM64 timing** (§4) — bundle the Dockerfile/task-definition ARM64 change into the same redeploy as the
   region migration (§§1–2), since both require a fresh image build/push; doing them as separate redeploys
   would double the verification work for no benefit.
