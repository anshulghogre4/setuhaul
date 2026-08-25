# SetuHaul — deployment

> Roadmap step 4 of 5 — **the final design document**. Completes: SOLUTION_DESIGN → UI/UX (6 surfaces) →
> tech stack + testing → **deployment** → apply-to-existing (`APPLY-TO-EXISTING/TASKS.md`, written ahead
> of this one so there was a real sequence to describe shipping).
>
> **Deliberately scoped to what isn't already written.** Regression gates and rollback strategy live in
> `ARCHITECTURE/SYSTEM_DESIGN.md` §9; the apply sequence lives in `TASKS.md`. This document owns
> environments, the deploy mechanism, CI/CD, secrets, monitoring, and the runbooks — and **cross-references
> rather than duplicates**, because two copies of a rollback procedure is how one of them goes stale.

---

## Decisions at a glance

| Concern | Decision |
|---|---|
| **Environments** | **Local + production only** — no staging tier (reasoning in §1, consistent with D16) |
| **Backend host** | **AWS ECS Fargate, `ap-south-1`, always-on, ARM64** — REST for the five non-chat surfaces (§0) |
| **Agent host** | **AgentCore Runtime, `ap-south-1`, ARM64** — driver chat only, via `/invocations` |
| **Agent deploy** | **AgentCore direct code deployment** (zip → S3), not container/ECR |
| **The codezip footgun** | **Make the sync atomic** — fold staging into the deploy command. ⚠️ *Do not delete the staging directory* — see the correction in §2.2 |
| **Frontend** | ⚠️ **Unsettled** — Cloudflare Pages *or* Vercel. Turns on a licensing question, not performance (§0, open item 7) |
| **LLM** | **Vertex AI `asia-south1`** — in-region, via ADC with an explicit `location` (`TECH_STACK.md` §7) |
| **Secrets** | AWS SSM Parameter Store — never in the repo, never in the changelog |
| **Migrations** | Production-direct behind a backup (D16); **forward-fix only** |
| **First deploy order** | Database → backend → frontend. Never frontend-first |

---

## 0 · Hosting targets — where each piece runs, and why

The brief was: **fast, containerised, data in-region (India), zero out-of-pocket cost.** Three of those
four pull together. The fourth pulls against them.

### The free-tier trap

**Free tiers are free precisely because they scale to zero** — and scale-to-zero means cold starts, which
are directly hostile to `NFR-001` (TTFT p95 < 1.2 s). A driver at a roadside hitting a cold container does
not experience a 1.2 s first token; they experience several seconds of nothing.

So "free" and "fast" are not independently satisfiable here. They are reconciled by **spending credits
rather than a free tier** — always-on compute, paid for, but not out of pocket.

| Option | In-region (India) | Genuinely free | Cold start |
|---|---|---|---|
| **AWS ECS Fargate, `ap-south-1`** | ✅ | **covered by AWS credits** | ❌ **none — always-on** |
| Google Cloud Run, `asia-south1` | ✅ | ❌ **free tier is US-regions-only** | Yes, unless paid min-instances |
| Azure Container Apps, Central India | ✅ | ✅ real free tier | Yes, unless min-replicas |
| Fly.io `bom` | ✅ | ❌ **free tier discontinued 2026** | Fast |

**D-1 — Backend: AWS ECS Fargate, `ap-south-1`, always-on, ARM64.** Prior measurement puts it at
≈ $0.07–0.08/hr ≈ **$50–60/month**, comfortably inside the AWS credits. ARM64 because AgentCore requires
it (§2) and matching keeps **one build artifact** rather than two.

**D-5 — Fallback if AWS credits run out: Azure Container Apps, Central India.** The only in-region option
with a genuine free tier. Accept the cold start, or pay for one min-replica.

> **The GCP credit does not change this.** The ~$1,000 credit reads *"Trial credit for GenAI App Builder"*,
> usage scope *"Certain usage"* — it is **product-scoped and will almost certainly not fund Cloud Run or
> Compute**. Whether it covers raw Vertex AI inference is an open item, not an assumption
> (`TECH_STACK.md` §13).

### D-2 — Frontend: ⚠️ unsettled (Cloudflare Pages or Vercel)

| | Cloudflare Pages | Vercel | Netlify |
|---|---|---|---|
| PoPs | **330+, deep India peering** | ~100 | ~100 |
| Free bandwidth | **Unlimited** | 100 GB | 100 GB |

> ⚠️ **This table does not justify the decision, and should not be read as if it does** (open item 7).
> Both rows fail against our own numbers: 100 GB is never binding at 6 facilities with a service-worker-
> cached PWA (realistically single-digit GB/month), and PoP count is near-irrelevant when every user is in
> one metro that *both* networks serve from Mumbai. **All three hosts are sub-100 ms for static assets in
> India.**
>
> **The one genuine differentiator is licensing**: Vercel's Hobby tier is licensed for **non-commercial
> personal use only** — client work and revenue-generating sites require Pro at $20/user/month — while
> Cloudflare Pages' free tier **permits commercial use**. So the decision turns on a product question,
> not a performance one: *does SetuHaul stay a classroom build, or serve real carriers?* **Unsettled by
> owner decision (2026-08-21); revisit before first deploy.**

What *does* matter for latency is what the frontend **doesn't** do: the PWA calls the `ap-south-1` origin
**directly**, never proxied through an edge function. For SSE especially, an intermediary risks buffering
the stream — which would destroy TTFT no matter how fast the CDN serves the shell.

### D-4 — LLM: Vertex AI `asia-south1`

`gemini-3.7-flash`, in-region. This is the deployment-side consequence of `TECH_STACK.md` §7: **the model
hop no longer leaves India** (~5–15 ms rather than ~200 ms), which also resolves the residency exposure.

⚠️ **Deploy-time requirement**: configure via **ADC with an explicit `project` and
`location="asia-south1"`** — *not* `api_key` with `vertexai=True`, which may silently route to the global
endpoint and forfeit both the latency and the residency guarantee. **Assert the resolved region at
startup**; this failure mode returns correct answers while being wrong.

### CDN and load balancing

| Layer | Choice | Honest scope |
|---|---|---|
| Static assets | The chosen host's CDN (D-2) | Genuine benefit — and equivalent on either candidate |
| In front of ECS | **ALB** | **TLS termination and health checks — not load distribution.** At 5 concurrent coordinators there is nothing to distribute. It earns its place as the health-check and rolling-deploy mechanism, not as a scaling device |

Naming this plainly matters: an ALB justified as "for scale" invites someone to later add autoscaling
complexity the workload does not need (`SYSTEM_DESIGN.md` §6).

---

## 1 · Environments — local and production only

**No staging tier.** This is a deliberate call, not an omission, and it follows the posture the design
already took in **D16**: *"Schema migration runs directly on production, behind a backup — no Supabase
branch. Simpler and free; recovery is a restore rather than a branch discard."*

| Environment | Purpose | Data |
|---|---|---|
| **Local** | Development, the full test suite, Playwright multi-context races | Seeded fixtures; injectable clock (§9.1) |
| **Production** | The live system | The real Supabase project |

### Why this is defensible here

- **Cost** — the LLM budget is $5 + $5 (`TECH_STACK.md`); a staging tier would consume it on non-user traffic.
- **The test suite is the gate, not an environment** — `TESTING_STRATEGY.md`'s Locust and Playwright suites plus §10's invariant queries run locally and in CI. A staging tier that isn't exercised by real traffic adds confidence theatre, not confidence.
- **Consistency** — D16 already decided production-direct-behind-a-backup for the riskiest operation in the project (the schema migration). A staging tier for deploys but not for migrations would be incoherent.

### When to revisit

Add a staging tier when **any** of these becomes true: real carriers depend on uptime · more than one person deploys · a change needs soak time under real traffic before full exposure. **Feature flags** (`SYSTEM_DESIGN.md` §9.2) are the cheaper answer to the third case and should be tried first.

---

## 2 · Agent deployment — AgentCore

### 2.1 Two mechanisms, and the recommendation

AgentCore Runtime supports two deployment modes:

| Mode | Mechanism | Fit here |
|---|---|---|
| **Container** | Docker image → ECR | Suits established container CI/CD; requires Dockerfile and image management |
| **Direct code (zip)** | Code + dependencies zipped → S3 → create/update runtime | **Recommended** — no Docker, faster iteration; first deploy installs dependencies, subsequent updates **reuse the zipped dependencies** |

**Decision: direct code deployment.** One team, no existing container pipeline, and iteration speed matters more than image-level control. Python is supported (Node.js was added later, not needed here).

**Runtime contract** (unchanged by mode), verified against AWS's service-contract and HTTP-protocol-contract
docs:

| Property | Value |
|---|---|
| **Mount paths** | **`/invocations` (POST) · `/ws` (optional) · `/ping` (GET)** — and nothing else |
| Port / host | **8080** / `0.0.0.0` |
| **Platform** | **ARM64 required** — not a preference |
| Streaming | **SSE supported on `/invocations`** — the streaming decision (`TECH_STACK.md` §9) holds |
| Entrypoint | `@app.entrypoint` from the AgentCore Python SDK, **or** implement `POST /invocations` and `GET /ping` directly |

**Two consequences worth stating plainly**, because both look like details and are not:

1. **AgentCore is not a general REST host.** The three fixed mount paths mean planner, ops, gate, carrier,
   and admin routes *cannot* be served from it — hence ECS Fargate in §0 and the two-target topology in
   `SYSTEM_DESIGN.md` §3.
2. **ARM64 is mandatory, so ECS matches it.** Building `linux/amd64` for ECS and `linux/arm64` for
   AgentCore would mean two artifacts diverging from one source — the same class of defect as §2.2's
   staging drift, one layer down. **Build ARM64 once, deploy twice.**

### 2.2 The codezip footgun — what actually fixes it

`AGENTS.md` carries a hard rule born from a real 2026-08-17 incident:

> `agentcore.cmd deploy` packages `agentcore/codezip/app/` — a **separate copied snapshot** of
> `backend/app/`, not the live source. Editing `backend/app/**` alone does nothing for AgentCore until
> that snapshot is refreshed. Skipping the staging script silently ships stale code **while
> `deploy`/`status` still report success.**

**Direct code deployment does not fix this by itself, and it would be wrong to assume it does.** The defect
is not zip-vs-container — it is that **a manually-synced duplicate of the source exists at all**. If the
deploy zips `agentcore/codezip/app/` rather than `backend/app/`, the identical failure survives the switch.

### ⚠️ Correction — an earlier draft of this section was wrong

This section previously recommended, as its **first-choice fix**, *"eliminate the staging directory — point
the deploy at the real source path so there is no copy to go stale."* **That advice is withdrawn.** It is
recorded here rather than quietly deleted, so nobody re-derives it and deletes a load-bearing directory.

**Why it was wrong**: `agentcore/codezip/app/` is a copy of `backend/app/` **because the same code deploys
to two runtimes** (§0, `SYSTEM_DESIGN.md` §3). AgentCore mounts only `/invocations`, `/ws`, and `/ping`, so
it cannot host the REST surfaces; ECS Fargate serves those from the same source. The staging directory is
the artifact of that split. It is **structural, not cruft** — removing it breaks the AgentCore deploy path
outright.

The original draft attached a caveat to that advice: *"why the staging directory exists here is unknown
from documentation alone — confirm before removing it."* **That caution was correct and the confident
recommendation above it was not.** Worth remembering as a pattern: the hedge was doing the real work.

**The actual fix, in order of preference:**

1. **Make staging part of the deploy command** — one command that cannot succeed without syncing first, so
   there is no separate script a human can forget. This removes the *human* failure mode, which is the one
   that actually fired on 2026-08-17. **Built (E4.2/issue #32, 2026-08-26)**: `docs/scripts/agentcore_deploy.py`
   is now that one command. It stages, gates on the backend test suite + `agentcore package` (both must pass
   before anything ships), deploys, then confirms via `agentcore/.cli/deployed-state.json`'s `deployHash`
   that the deployed content actually changed. `AGENTS.md` now requires it in place of calling
   `agentcore deploy` directly.
2. **Add a post-deploy artifact assertion** (§2.3) — verify the deployed zip contains the expected code
   rather than trusting the CLI's exit status. **Partially built**: the `deployHash` before/after comparison
   above is a real content-change signal from the tool's own authoritative record, not the CLI's exit code —
   but it is not yet the literal "download the S3 zip and diff its extracted files against `backend/app/`"
   this section originally asked for. That deeper check needs a live AWS session to discover the exact S3
   artifact location (blocked this session -- `aws sts get-caller-identity` failed with an expired session);
   `deployHash` was chosen as the practical, buildable-now equivalent rather than left undone.
3. **Until either lands, `AGENTS.md`'s rule stands verbatim**: run the staging script immediately before
   every deploy. No exceptions. **Superseded by item 1** — the wrapper does this automatically now; this
   line stays as the historical record of the interim manual rule.

**Do not** attempt option 1 by repointing the deploy at `backend/app/` directly — the two runtimes need
different packaging, which is what the directory provides.

### 2.3 Failure mode to watch for

The 2026-08-17 incident's signature: **`deploy` and `status` both report success while the old code keeps
running.** Verification must therefore inspect the *deployed artifact*, not the CLI's exit code — as was
eventually done that day by downloading the live S3 artifact and grepping its contents.

---

## 3 · Frontend deployment

| Concern | Decision |
|---|---|
| Host | ⚠️ **Unsettled** — Cloudflare Pages or Vercel, static build output either way (§0, open item 7). **Nothing below depends on which**: both do atomic deploys, instant rollback, and per-branch previews |
| Edge functions | **None.** Nothing server-side runs at the edge, so there is no function region to pin |
| API traffic | **Direct to the `ap-south-1` origin** — *not* proxied through an edge function (`TECH_STACK.md` §9: a proxy adds a full hop for zero benefit, and risks buffering SSE) |
| Build | Vite production build, route-split per surface (`SYSTEM_DESIGN.md` §7) |
| PWA | Service worker + manifest ship with the build; **cache-busting on deploy is mandatory** — a stale service worker serving an old bundle against a new API is a real failure mode |

---

## 4 · Database deployment

Migrations follow `SOLUTION_DESIGN.md` §9.3 and `TASKS.md` Phase 1 — **not restated here**. Deployment-side
rules only:

| Rule | Detail |
|---|---|
| **Backup precedes every migration** | D16 — the only safety net, since this runs production-direct |
| **Forward-fix only** | `SYSTEM_DESIGN.md` §9.2 — the D1 GiST constraint migration cannot be cleanly reversed once data depends on it |
| **Migration before code** | A deploy that expects `dock_occupancy` must not precede the migration that creates it |
| **Drift check first** | §9.3 step 2 — a migration on disk but unapplied must be reconciled before adding another on top |

---

## 5 · Secrets and configuration

| Concern | Decision |
|---|---|
| Store | **AWS SSM Parameter Store**, `ap-south-1` |
| Never | In the repo, in the changelog, in `AGENTS.md`/`CLAUDE.md`, in MCP JSON, or in logs (`AGENTS.md` delivery rule) |
| Agent → AWS services | **IAM role**, not stored keys |
| LLM provider key | SSM; rotated independently of deploys |
| Frontend | **Only genuinely public values** in the client bundle — anything in a Vite `VITE_*` var is shipped to the browser and is not a secret |

**Configuration that is not secret but is environment-specific**: region, model id, provider selection,
feature flags, rate limits. These belong in SSM too, so a change doesn't require a redeploy.

---

## 6 · CI/CD pipeline

```
push → lint + typecheck → unit tests → integration (§9.2 fixtures)
     → invariant queries (§10) → build → [manual gate] → deploy → post-deploy verify
```

| Stage | Gate | Source |
|---|---|---|
| Lint / typecheck | Includes **module-boundary import linting** (`SYSTEM_DESIGN.md` §3) | Boundaries stay conventions until enforced |
| Unit | The deterministic engine | `TESTING_STRATEGY.md` §1 |
| Integration | §9.2's 19 named stress fixtures, coverage mechanically asserted | §9.2 |
| **Invariant queries** | §10's set — **run continuously, not only at release** | §10 |
| Determinism | Byte-identical ranking on replay | `TESTING_STRATEGY.md` §6 |
| Build | Frontend bundle + agent zip | — |
| **Manual gate** | A human approves production deploy | No staging tier means the gate is a person |
| Post-deploy verify | §7 below | — |

**Not in the per-push pipeline**: Locust load suites and Playwright multi-context races. Both are slow and
some consume LLM budget — run them **pre-release and on a schedule**, not on every commit.

---

## 7 · Deploy runbook

**Order matters. Database → backend → frontend.** A frontend expecting a tool that isn't deployed fails in
the user's face; a backend ahead of the frontend is invisible.

| # | Step | Verify |
|---|---|---|
| 1 | Backup the database (D16) | Snapshot exists and is restorable |
| 2 | Apply migrations | Target objects exist; invariant queries pass |
| 3 | **Stage the agent package** — per §2.2. The staging directory is **permanent**, so this step never goes away; the fix is folding it into the deploy command | Package content matches the intended source |
| 4 | Deploy agent to AgentCore | **Inspect the deployed artifact, not the CLI exit code** (§2.3) |
| 5 | **Deploy REST backend to ECS Fargate** | Task reaches steady state; ALB health check green; **ARM64 image** |
| 6 | Deploy frontend to the chosen static host | Build succeeds; service worker cache-busted |
| 7 | Post-deploy smoke | §7.1 below |

⚠️ **Steps 4 and 5 deploy the same source to two runtimes.** They must ship the *same* commit — a split
deploy puts the driver chat and the REST surfaces on different code against one shared database, which is
the one way this topology could bite. Deploy them together or not at all.

### 7.1 Post-deploy smoke — minimum viable check

1. **One real driver turn end-to-end** — message in, tool call, option set rendered. Proves the whole path: frontend → API → agent loop → tool → Postgres → response.
2. **Invariant queries** — especially no overlapping `dock_occupancy` rows.
3. **One sweeper cycle observed** — a lapsed `HELD` row transitions without a read triggering it (proves the scheduled path, §2 of `TECH_STACK.md` §5).
4. **One trace in LangSmith** — thread-scoped, with nested tool spans (`TECH_STACK.md` §8).

**A deploy is not verified because it deployed.** The 2026-08-17 incident is precisely a case where every
status check was green and the wrong code was running.

---

## 8 · Monitoring and alerting

**D-3 — the stack is CloudWatch + Sentry + LangSmith.** Three tools, three non-overlapping jobs:

| Tool | Owns | Why not something else |
|---|---|---|
| **CloudWatch** | Infrastructure and application metrics, logs, alarms — ECS task health, DB connections, sweeper liveness | Native to ECS and AgentCore; zero integration cost, no extra egress |
| **Sentry** | **Unhandled exceptions with stack traces**, frontend *and* backend | This is the gap the table below names. Logs tell you an error rate rose; Sentry tells you which line |
| **LangSmith** | LLM traces — thread-scoped, nested tool spans, hop count, token spend | `TECH_STACK.md` §8. Nothing else sees inside a turn |

**Prometheus and Splunk were considered and declined.** Prometheus duplicates CloudWatch's job and adds a
service to run; Splunk is log analytics at a scale this project does not have. Neither covers a gap the
three above leave open — **a fourth tool that overlaps two others is operational cost, not coverage.**

Distinguishes what `TECH_STACK.md` §8 already covers (LLM tracing) from what nothing covered before
(application health, now CloudWatch + Sentry).

| Signal | Source | Alert when |
|---|---|---|
| **Double-booked capacity** | §10 invariant query | **Ever. Non-zero is a P0** — this is M6 |
| API error rate | Application logs | Sustained 5xx |
| LLM circuit-breaker state | Application metric | Breaker OPEN (`SYSTEM_DESIGN.md` §6.3) |
| TTFT p95 | Traces | Exceeds 1.2 s (NFR-001) |
| **Hop count per turn** | LangSmith | Rises above baseline — Appendix A: a latency regression *"no amount of infrastructure tuning will fix"* |
| Sweeper liveness | Job execution | No successful run in >2 cycles — silent sweeper failure means capacity is never released |
| Outbox depth | Queue length | Growing — deliveries failing |
| DB connections | Pool metrics | Near ceiling (this project has hit exhaustion before) |
| LLM spend | Provider | Approaching budget (`FR-SYS-030`) |

~~**Application-level error tracking is a gap**~~ — **closed by D-3 above**: Sentry owns unhandled
exceptions (frontend and backend), CloudWatch owns infrastructure signals. LangSmith never covered either —
it traces LLM calls, not crashes.

**One addition worth alerting on**, from `TECH_STACK.md` §7: **the resolved Vertex endpoint region**. If it
is not `asia-south1`, the deployment has silently lost both in-region latency and data residency while
continuing to return correct answers. Assert it at startup and fail loudly rather than alerting after
the fact.

---

## 9 · Rollback

**Owned by `ARCHITECTURE/SYSTEM_DESIGN.md` §9.2** — not restated. The deployment-side summary:

| Layer | Rollback |
|---|---|
| Frontend | Instant rollback to the prior deployment (both candidate hosts support this) |
| Agent | Redeploy the prior artifact |
| **REST backend** | ECS rolling update back to the prior task definition |
| ⚠️ **Both backends together** | Roll back AgentCore **and** ECS to the same commit — see §7's warning about split deploys |
| **Database** | **Forward-fix only** — no clean reverse for the GiST constraint migration |
| **Policy** | Free — `policy_versions` is append-only (D7); revert = publish the prior version |

---

## 10 · Constitution Check

| `AGENTS.md` rule | Check |
|---|---|
| AgentCore deploy must be preceded by codezip staging | ✅ §2.2 carries it verbatim. An earlier draft proposed deleting the staging directory; **that is withdrawn and the reversal is recorded in place** rather than edited away |
| Never commit secrets | ✅ §5 — SSM only, IAM for AWS access |
| Database changes require a migration + tests | ✅ §4, §6 |
| Do not mark tests as passing unless run | ✅ §6 distinguishes per-push gates from scheduled suites; §7.1 verifies artifacts, not exit codes |
| Report what was and wasn't verified | ✅ §7.1 states explicitly that a green status is not verification |

**No conflicts found.**

---

## 11 · Open items

| # | Item | Blocks |
|---|---|---|
| 1 | ~~**Why the codezip staging directory exists**~~ | **Closed** — it is load-bearing: the same source deploys to two runtimes with different packaging (§2.2). The "eliminate it" advice is withdrawn |
| 2 | ~~**Application error tracking not chosen**~~ | **Closed by D-3** — CloudWatch + Sentry + LangSmith (§8) |
| 2a | **Does `location="asia-south1"` actually pin Vertex in-region?** (§0) — **same open item as `TECH_STACK.md` §13 item 1a**, cross-referenced 2026-08-22 | ~5–15 ms vs ~200 ms, *and* data residency. Assert at startup; do not trust config. Resolving it here resolves it there too — update both, or neither |
| 2b | **Does the GCP credit cover Vertex inference?** — product-scoped to "GenAI App Builder" (§0) — **same open item as `TECH_STACK.md` §13 item 2**, cross-referenced 2026-08-22 | Whether the LLM path is credit-funded or out-of-pocket. Resolving it here resolves it there too — update both, or neither |
| 3 | **RTO/RPO undefined** — carried from `SYSTEM_DESIGN.md` §9.3 and `GAP_ANALYSIS.md` Gap 5 | A real DR policy |
| 4 | **Backup cadence** — D16 covers the pre-migration backup; routine backup schedule is unspecified | Recovery beyond migrations |
| 5 | ~~**Supabase / Upstash region** — unverified~~ | ✅ **CONFIRMED 2026-08-21** — both `ap-south-1`. With Vertex `asia-south1` (§0), **every tier of the design is in-region** |
| 5a | **Upstash runs in Global replication mode** — primary Mumbai, read replicas elsewhere | A residency surface (`TECH_STACK.md` §11). Bounded by 24 h TTL and non-authoritative status, but should be a decision rather than a default |
| 7 | **Frontend host: Cloudflare Pages vs Vercel — deliberately unsettled** | ⚠️ **The justification currently in §0 is weak.** The bandwidth (100 GB is never binding at this scale) and PoP-count (all users in one metro; both serve Mumbai) arguments do not survive the workload math. The **only real differentiator is licensing**: Vercel's Hobby tier is non-commercial-use-only, Cloudflare Pages' free tier permits commercial use. **Decide by whether SetuHaul stays a classroom build or serves real carriers** — not by the table in §0. Revisit before first deploy |
| 6 | **Alert routing** — who is notified, through what channel, for a P0 double-booking | On-call being real rather than nominal |
