# SetuHaul — execution plan and GitHub tracking model

> **What this is**: the bridge between 37,270 lines of design across 72 files and actual GitHub
> milestones, epics and issues. Written 2026-08-22 after the six `COMPARISON-*.md` passes finished, so
> every milestone below is grounded in a *measured* gap, not an assumed one.
>
> **Repo**: `github.com/anshulghogre4/setuhaul` · `gh` 2.98.0 authenticated as `anshulghogre4`
> (scopes: `repo`, `workflow`, `read:org`, `gist`).

---

## 0 · What the comparison actually established

Six read-only passes (architecture, backend routers/services, backend core/scheduling/db, frontend,
AI-assistant, latency) read the live `backend/` (43 Python files, ~7,200 lines), `frontend/src/`
(17 files), and `supabase/migrations/` (6 files) against the design workspace. Four facts drive
everything below.

**Fact 1 — the correctness bedrock does not exist.** D1's `dock_occupancy` table with its GiST
`EXCLUDE` constraint has not been migrated: no `btree_gist`, no `dock_occupancy`, every timestamp column
still `TEXT`. Capacity is currently defended by two partial unique indexes that can only stop two rows
claiming the *same slot id* — not two rows claiming *overlapping intervals on different slot rows*, which
is the actual race M6 exists to prevent. `TASKS.md` Phase 1 is accurately described as blocking, and it
has not started.

**Fact 2 — the frontend is three routes, not six surfaces.** `/driver`, `/ops`, `/dispatch` exist.
Planner board, gate/yard kiosk, carrier portal, admin console and the entire shared shell have zero
implementation. Per the owner overhaul decision, the existing UI is **replaced, not reconciled**.

**Fact 3 — one live feature is out of scope by design.** `dispatch_service.py` +
`DispatchHome.tsx` implement shipment-creation-with-driver-assignment, which `SOLUTION_DESIGN.md` §0.9
places on the WON'T list as TMS territory. This is the only finding that is "built the wrong thing"
rather than "not built yet."

**Fact 4 — roughly a dozen lines carry more per-turn latency than everything else combined.** The
latency pass traced one real driver turn end to end: 3 LLM inferences, 2 tool hops, 9 sequential DB round
trips, 3 Upstash HTTPS round trips, 1 blocking JWKS fetch, 1 blocking OTLP flush, 0 bytes streamed. Its
top four remediations total ~12 lines and appear in no other pass, because they are only visible when the
axis is latency rather than correctness.

---

## 1 · Milestones — dependency-ordered, not preference-ordered

Eight milestones. The ordering is forced by real dependencies, with one deliberate exception: **M0 runs
first despite not being architecturally foundational**, because it is cheap, independently verifiable, and
two of its items are live defects rather than gaps.

| # | Milestone | Gate to close it | Blocked by |
|---|---|---|---|
| **M0** | Live defects and cheap latency wins | Breakdown reports persist; read-only roles cannot write; traced turn re-measured | — |
| **M1** | D1 correctness bedrock | 50-way concurrent `request_slot` yields exactly 1 winner | M0 (region/settings only) |
| **M2** | Scope corrections and de-duplication | No route bypasses the repository tier; out-of-scope code removed | M1 |
| **M3** | Tool catalogs §7.5.1–§7.5.8 | Every tool named in §7.5 has a callable implementation | M1, M2 |
| **M4** | AgentCore rebuild | Local-verified turn, then deployed artifact matches source byte-for-byte | M3 |
| **M5** | Frontend — six surfaces + shared shell | Every screen in each surface `mockup.html` renders against live data | M3 |
| **M6** | Verification suites | `SOLUTION_DESIGN.md` §10 six-part proof suite passes | M1–M5 |
| **M7** | Deployment and infrastructure | AgentCore + ECS + Upstash all confirmed `ap-south-1` by live ARN/console, not by config file; Sentry live in both frontend and backend | M4 (region move must follow #31/#32; research can start earlier) |

### Why M7 sits after M4, not earlier or as part of M0

The seventh comparison pass (`COMPARISON-deployment.md`) found AgentCore and the ECS/REST backend are both
actually deployed in `us-east-1` against a designed `ap-south-1` — confirmed at the infrastructure-config
layer and, for AgentCore, at the level of the live resource's own ARN. That looks like it could be an M0-
style "cheap defect," but the comparison itself flags why it is not: moving the deployed region before
`#31` (LLM provider/auth/region-pinning code) and `#32` (deploy-hygiene atomicity) land would mean
redeploying a target that is still mid-fix twice over. M7's *research* (this pass) has already run; M7's
*execution* — the actual region migration — waits for M4.

### Why this order and not another

**M0 before M1** — the region default (`us-east-1` → `ap-south-1`) is a settings change that M1 migration
work will otherwise be measured against wrongly. Fixing it first means every timing taken during M1 is
honest.

**M1 blocks everything real** — `feasibility.py` and `allocation.py` both change in M1. Building tools
(M3) or screens (M5) against a pre-D1 allocation path means rewriting them after. This is the same
reasoning `TASKS.md` already encodes; the comparison confirmed it empirically rather than reversing it.

**M2 before M3** — M3 adds ~25 new tools. Adding them on top of scope-logic that is currently duplicated
four independent ways multiplies the duplication rather than containing it.

**M4 after M3** — the AgentCore rebuild needs the finished tool catalog to deploy. Rebuilding it first
means deploying twice.

**M5 parallel-capable with M4** — the frontend consumes M3 tools, not M4 runtime. Once M3 closes, M4 and
M5 can run concurrently if capacity allows.

---

## 2 · Epics and issues per milestone

GitHub has no native "epic" type. The convention used here: **an epic is a tracking issue with a task
checklist**; each checklist item links a real sub-issue. Labels carry the categorisation.

### M0 — Live defects and cheap latency wins

| Epic | Issues | Source |
|---|---|---|
| **E0.1 Live data-loss and authz defects** | `report_vehicle_breakdown_or_incident` never commits — driver reports silently discarded · `TRANSPORT_MANAGER`/`REGIONAL_OPERATIONS_HEAD` documented read-only but `ctx.is_admin` gates writes for both · `/dispatch/shipments` requires no `Idempotency-Key` and mints a random key internally per call | routers-services pass |
| **E0.2 The twelve lines** | Default `aws_region` to `ap-south-1` + assert resolved region at startup · delete `provider.force_flush()` (blocking OTLP export, 10 s ceiling) · `@lru_cache` the `JwtVerifier` (blocking JWKS fetch on 100% of requests) · stop awaiting `maybe_summarize_history` (a full extra LLM inference on ~1 turn in 3) | latency pass, items 1–4 |
| **E0.3 Baseline measurement** | Instrument §10 six named measurements — nothing above is verifiable without them | latency F5 |

### M1 — D1 correctness bedrock

| Epic | Issues | Source |
|---|---|---|
| **E1.1 Schema migration** | Backup (D16, non-negotiable) · reconcile the unapplied `20260817040000` drift · `CREATE EXTENSION btree_gist` · `text → timestamptz` across six tables · create `dock_occupancy` + GiST `EXCLUDE` · backfill one row per active appointment | `TASKS.md` 1.1–1.5 |
| **E1.2 Backfill conflict handling** | Route conflicts to the D12 worklist (`REQUIRES_TIME_RESOLUTION`, `REQUIRES_DOCK_REASSIGNMENT`) — never silently resolved · re-count worklist sizes at execution time | `TASKS.md` 1.6 |
| **E1.3 Allocation rewrite** | Replace `SELECT … FOR UPDATE` + per-slot unique indexes with the exclusion constraint as the concurrency mechanism · keep the existing idempotency/audit scaffolding, which is correct | architecture F1, core/scheduling pass |
| **E1.4 Feasibility completion** | Stage 0 multi-day horizon (absent — every no-slot is currently `NO_FEASIBLE_SLOT`-shaped) · facility-rule and driver-window checks (missing) · drop the `CAST(… AS timestamptz)` once columns are real timestamps, which is what unblocks `NFR-003` | architecture F2/F3, latency F16 |
| **E1.5 The sweeper (M8)** | Does not exist in any form · EventBridge 1-min trigger · HELD 90 s (D2) and PENDING 15 min (D9) expiry in the same transaction as `confirm_request` · injectable clock for testability | `TASKS.md` 3.1–3.3 |

### M2 — Scope corrections and de-duplication

| Epic | Issues | Source |
|---|---|---|
| **E2.1 Remove out-of-scope capability** | Delete `dispatch_service.py`, `DispatchHome.tsx`, the `/dispatch` route and its frontend entry — WON'T-list per §0.9 | architecture F5 |
| **E2.2 Repository tier** | Introduce the missing repository layer · move scope enforcement into it (currently duplicated four independent ways) · add the import-lint CI check, which currently has nothing to attach to | architecture F4/F6, `NFR-020` |
| **E2.3 Identity model** | Create `user_scopes` (scope currently rides on `users.facility_id`) · add `CARRIER` role + `carrier_id` to `ExecutionContext` — the entire §7.5.6 catalog has nowhere to attach without it | architecture F6, routers-services pass |
| **E2.4 Router de-duplication** | `driver.py` reimplements `driver_reads.py` query-for-query — call the service instead · reconcile the escalation-reason vocabularies (9 canonical vs. 6 live, 1 name overlapping) | routers-services pass |

### M3 — Tool catalogs

| Epic | Issues | Source |
|---|---|---|
| **E3.1 Driver allowlist correction** | 23 tools bound where §7.5.4 specifies 12 · `confirm_held_slot` and `explain_slot_eligibility` do not exist (the latter backs `FR-DRV-006`) · remove `reschedule_appointment`, which contradicts D1 collapse decision | AI-assistant pass §3 |
| **E3.2 Ops console (§7.5.5)** | ~15% built · `acknowledge_escalation`, `reassign_escalation`, `take_over_thread`, `hand_back_thread`, `cancel_escalation`, `request_sequencer_proposal` all absent · no `owner` column to write to | routers-services pass |
| **E3.3 Carrier portal (§7.5.6)** | Five read-only tools, `carrier_id`-scoped — blocked on E2.3 | `TASKS.md` 2.3 |
| **E3.4 Admin console (§7.5.7)** | 13 tools across users/roles, facility rules, policy, audit | `TASKS.md` 2.4 |
| **E3.5 Shared/cross-cutting (§7.5.8)** | `search_records` (composes via module interfaces, never cross-module tables) · notifications · account profile · password reset (email-only per the 2026-08-22 decision) · `sign_out_everywhere` with the explicit `scope: 'local'` vs `'global'` distinction | `SOLUTION_DESIGN.md` §7.5.8 |
| **E3.6 Planner + gate/yard completion** | `block_dock`/`end_dock_block` · all five gate/yard write tools (the `TASKS.md` claim that §7.5.2 "already existed" is wrong — only a read exists) | architecture pass correction |

### M4 — AgentCore rebuild

| Epic | Issues | Source |
|---|---|---|
| **E4.1 Model/provider correction** | `langchain-google-genai` 2.1.12 → ≥ 4.x (2.x breaks the multi-turn loop on `thought_signature`) · ADC + explicit `location="asia-south1"` replacing AI-Studio key auth · `gemini-3.7-flash` replacing `gemini-flash-latest` · provider order currently tries Gemini **last**, so OpenAI wins by default and driver PII leaves India | AI-assistant pass §0–§1 |
| **E4.2 Deploy discipline** | Atomic staging wrapper — one command that cannot succeed without syncing · post-deploy artifact diff against source · **local-verify-before-deploy gate** (owner rule, 2026-08-22) · then clear the currently-stale artifact | AI-assistant §7.3, `DEPLOYMENT.md` §2.2 |
| **E4.3 Latency levers 1–3** | Prefetch `get_driver_operational_context` (1 hop = 2 inferences) · shrink tool surface to 12 · SSE end-to-end, which is what makes `NFR-001` exist at all | latency F1/F2/F3 |
| **E4.4 Loop hardening** | Explicit LLM timeout + wall-clock turn deadline (neither exists) · release the DB session before the LLM call · module-scoped async `redis-py` client | latency F17/F12/F10 |

### M5 — Frontend

One epic per surface. Each epic issues come directly from that surface `mockup.html` screen list — these
are already enumerated and verified, so issue creation is mechanical rather than a fresh design pass.

| Epic | Screens | Mockup |
|---|---|---|
| **E5.0 Shared shell + design system** | 29 artboards — sign-in, role picker, password reset, user menu, notifications, search palette, account/settings | `00-foundations/mockup-shared-shell.html` |
| **E5.1 Driver chat** | 28 | `01-driver-chat/mockup.html` |
| **E5.2 Ops exception console** | 16 | `02-ops-exception-console/mockup.html` |
| **E5.3 Planner dock board** | 30 states | `03-planner-dock-board/mockup.html` |
| **E5.4 Gate/yard kiosk** | 22 | `04-gate-yard-kiosk/mockup.html` |
| **E5.5 Carrier portal** | 9 | `05-carrier-portal/mockup.html` |
| **E5.6 Admin console** | 12 | `06-admin-console/mockup.html` |

E5.0 blocks the rest — the shared queue component (U23) and the shell chrome are consumed by every other
surface. Also in E5.0: the tech-stack conformance gap — Tailwind, shadcn/ui, assistant-ui and Kibo UI
Gantt are all absent from `package.json` today.

### M6 — Verification

| Epic | Issues |
|---|---|
| **E6.1 Race suites** | Four Locust suites: `same_interval_race`, `hold_expiry_vs_confirm`, `pending_expiry_vs_planner_confirm`, `ordinal_staleness` |
| **E6.2 UI races** | Seven Playwright multi-context suites, distinct `storageState` per role |
| **E6.3 Proof suite** | §10 six parts: 50-way concurrency · invariant queries in CI · idempotency replay · 29-scenario replay · determinism (byte-identical, twice) · chaos-lite (kill Redis mid-conversation) |

Note: `COMPARISON-deployment.md` §5 found CI runs only `backend-unit` + `frontend-build` — no integration or
invariant-query stage exists yet. That gap is E6.3's territory (the invariant-queries-in-CI sub-issue
already covers it), not a new M7 item — cited here so the two docs don't drift apart on who owns it.

### M7 — Deployment and infrastructure

| Epic | Issues | Source |
|---|---|---|
| **E7.1 Region correctness migration** | AgentCore Runtime `us-east-1` → `ap-south-1` (deploy target, baked env var, and the live resource itself all currently wrong) · ECS/REST backend `us-east-1` → `ap-south-1` (new ECR repo + re-push, not just an env var flip) · Upstash Redis — confirm which instance is actually live via SSM (`TECH_STACK.md`'s "confirmed `ap-south-1`" almost certainly checked the orphaned, superseded instance) then move compute and cache back to `ap-south-1` **together**, not cache-chasing-compute again · convert ECS from `linux/amd64` to ARM64 in the same redeploy · retire the dead `deploy/apprunner-create.json` artifact | `COMPARISON-deployment.md` §1, §2, §4, §8 |
| **E7.2 Monitoring completion: Sentry** | Add `sentry-sdk` + `sentry_dsn` setting + `Sentry.init()` gated on it being non-empty, matching the existing degrade-safe OTEL pattern · add `@sentry/react` to the frontend and initialise it at the SPA entrypoint | `COMPARISON-deployment.md` §7 |

**E7.1 depends on #31 (E4.1) and #32 (E4.2) landing first** — moving a deployed region while its provider
config and deploy hygiene are still broken means redeploying twice. **E7.2 is independent** and can start
any time.

Two items surfaced by the pass are deliberately **not** epics here:
- The CI integration/invariant-query gap — already E6.3's territory (see the M6 note above).
- The Cloudflare-vs-Vercel decision — `DEPLOYMENT.md` leaves this a licensing call, not an engineering gap.
  Worth flagging to the owner directly (a live Vercel deployment already exists, so "unsettled" currently
  has an unacknowledged default answer in production) but not tracked as work unless a decision changes it.

---

## 3 · Issue taxonomy

### Labels

**Type** — `type:defect` (live, currently broken) · `type:gap` (designed, not built) · `type:wrong-scope`
(built, should not exist) · `type:latency` · `type:verification` · `type:tooling`

**Area** — `area:db` · `area:backend` · `area:frontend` · `area:assistant` · `area:infra` · `area:docs`

**Risk** — `risk:high` (touches D1/auth/migrations — **rollback note required** per `AGENTS.md`) ·
`risk:medium` · `risk:low`

**Source** — `src:comparison` (found by a 2026-08-22 pass) · `src:design` (from the design docs
directly) · `src:incident` (traces to a real recorded incident, e.g. the 2026-08-17 codezip drift)

### Required issue body fields

Every issue carries these, so nothing traces back to "someone said so":

1. **Design citation** — `M*`/`D*`/`U*`/`FR-*`/`NFR-*`/`§` reference
2. **Evidence** — the `COMPARISON-*.md` file and section, or the live `file:line`
3. **Acceptance** — what must be true, stated as a check that can be run
4. **Rollback note** — mandatory on `risk:high`; which commit, which files, what to re-check

### Estimation

Deliberately **not** included. This project own history shows a doc-vs-reality gap that only the
comparison passes caught; sizing work before its blocking dependency lands would repeat that pattern at
the planning layer. Ordering is dependency-based; estimation happens per-milestone when it starts.

---

## 4 · GitHub API usage

Milestones: `gh api repos/:owner/:repo/milestones -f title -f description -f due_on`.
Issues: `gh issue create --milestone --label --title --body-file`.
Epic-to-issue links: task-list checkboxes in the epic body referencing `#N` — GitHub renders progress
automatically and closing a sub-issue ticks its box.

Order of creation matters: **labels → milestones → epics → issues**, because an issue cannot reference a
milestone or label that does not exist yet, and an epic checklist needs its sub-issue numbers.

---

## 5 · What stays true regardless of tracking

- **The design workspace is the target**, not a suggestion. Where live code and design disagree, the
  design wins unless the code reflects a constraint the design missed — in which case the design changes
  explicitly, on the record, not silently.
- **`AGENTS.md` AI-collaboration discipline applies to every issue**: plan before implement, trace
  execution before changing it, one logical change per mutation, rollback notes on risky changes, model
  version-pinned in the changelog.
- **Local verification precedes deployment** (owner rule, 2026-08-22) — "it deployed successfully" is not
  evidence it works. This is the direct lesson of the 2026-08-17 codezip incident, which the AI-assistant
  pass confirmed is *currently recurring*.
- **Every issue is worked through UPIV** (Understand → Plan → Implement → Verify) — see `AGENTS.md`'s
  "AI-collaboration discipline" section for the full definition; keep this line in sync with that wording
  rather than paraphrasing it differently here.
- **The tracker is re-checked at the start of every session that touches this work**, via `gh issue list
  --state all`, not assumed from a prior session's memory or from this document alone (`AGENTS.md` startup
  sequence step 7).
