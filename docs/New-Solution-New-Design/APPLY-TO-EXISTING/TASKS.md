# SetuHaul — apply to existing project (tasks)

> Roadmap step 5 of 5: SOLUTION_DESIGN (done) → UI/UX (done) → tech stack (done) → **apply to existing
> project** → deployment. Reordered ahead of the deployment doc at the owner's direction — you cannot
> write a real deployment plan without knowing what gets deployed and in what sequence, and that sequence
> is this document.
>
> **Shape borrowed from spec-kit's `tasks.md`** (evaluated in the UI/UX phase, not installed — see
> `UI-UX/README.md`'s "Spec-kit evaluation"): phased, file-path-mapped, `[P]` marks parallel-safe tasks,
> checkpoints gate each phase.
>
> ## ⚠️ Written doc-only — no live code read for this pass
>
> The owner confirmed staying doc-only rather than opening `backend/`, `frontend/`, `supabase/` for this
> draft (matching this workspace's scope discipline throughout). Every file path below is one of two
> kinds, marked inline:
> - **[G]rounded** — cited in `SOLUTION_DESIGN.md` itself (its §6.1/§9 audit already read the live schema
>   and migrations) or in this session's own prior verified work (the AgentCore codezip-staging incident,
>   the Upstash region incident — both real, both already in `CHANGELOG.md`).
> - **[A]ssumed** — a conventional path inferred from the project's own naming pattern, **not verified this
>   pass**. Phase 0 below exists specifically to convert every `[A]` to confirmed-or-corrected before any
>   other phase starts.

---

## Decisions at a glance

| Concern | Decision |
|---|---|
| **Sequencing principle** | Database (D1's correctness bedrock) before tools before UI before background jobs — nothing renders a promise state the schema can't yet enforce |
| **Parallelism** | Marked `[P]` per spec-kit's convention — safe to run concurrently because the files don't overlap |
| **Migration safety** | §9.3 step 1 (backup) is **non-negotiable and blocks everything** — this runs on production, no branch (D16) |
| **AgentCore deploy discipline** | `AGENTS.md`'s hard rule carried forward verbatim: `stage_agentcore_codezip.py` immediately before every `agentcore.cmd deploy`, no exceptions |
| **Verification standard** | §10's 6-part proof suite is the exit gate for this whole document, not a nice-to-have |

---

## Phase 0 — Setup: convert every `[A]` to confirmed (blocks all other phases)

This phase **is** the scope-expansion the owner deferred. Nothing past it should proceed on an assumed
path.

| # | Task | Verifies |
|---|---|---|
| 0.1 | Read `backend/app/` structure — confirm `assistant/tools.py`, `assistant/prompts.py`, `scheduling/{feasibility,allocation}.py`, `db/session.py` exist at the paths this document assumes **[A]** | Every backend file path used below |
| 0.2 | Read `frontend/src/` structure — confirm current routing, component layout, and whether any of the six UI-UX surfaces already have a partial live implementation to reconcile against, rather than assuming greenfield | Every frontend file path used below |
| 0.3 | ~~**Confirm Supabase project region is `ap-south-1`**~~ — ✅ **CONFIRMED 2026-08-21** via Supabase MCP: project `setuhaul` (`kujffzgqjmqphkmrbawy`), `region: ap-south-1`, `ACTIVE_HEALTHY`, PostgreSQL **17.6.1** | `TECH_STACK.md` §2, §11 |
| 0.4 | ~~**Confirm Upstash Redis region is `ap-south-1`**~~ — ✅ **CONFIRMED 2026-08-21** via the Upstash console: AWS **Mumbai, India (`ap-south-1`)**, Free Tier, **Global** replication mode | `TECH_STACK.md` §3 |
| 0.5 | Re-run `SOLUTION_DESIGN.md` §6.1/§9's live-schema audit — confirm applied-migration count, `btree_gist` status, and column types (`text` vs `timestamptz`) are still what the 2026-08-19 audit found, since time has passed | §9.3 steps 2–4 |
| 0.6 | Re-count the D12 worklist sizes (85 `REQUIRES_TIME_RESOLUTION`, 116 `REQUIRES_DOCK_REASSIGNMENT`) — §9.3 step 6 explicitly flags these "will need re-measuring at execution time" | §9.3 step 6 |

**Checkpoint 0**: every `[A]` marker in this document has been replaced with a confirmed path or a
corrected one, in a follow-up pass. **Do not proceed to Phase 1 on an unconfirmed database region** — a
migration against the wrong assumption about co-location is the one mistake in this whole plan that isn't
cleanly reversible.

> ✅ **The region half of Checkpoint 0 is met (2026-08-21).** Both data stores are in `ap-south-1`, so the
> co-location argument underpinning `TECH_STACK.md` §2–§3 and `SOLUTION_DESIGN.md` Appendix A **holds on
> verified fact rather than assumption**. With Vertex `asia-south1` for inference (`TECH_STACK.md` §7),
> **every tier of the design is now in-region**. 0.1, 0.2, 0.5, and 0.6 remain open — they need the
> codebase, which is still out of scope by owner instruction.
>
> ⚠️ **Two things to confirm when the codebase opens**, both visible in the Upstash console screenshot:
> 1. The database is named **"langsmith test"** and is on the **Free Tier**. Verify this is genuinely the
>    store SetuHaul uses rather than a leftover scratch database — a name like that is worth one check
>    before a production path depends on it.
> 2. It runs in **Global** replication mode. Primary is Mumbai, which is what matters for writes, but
>    Global adds read replicas elsewhere. Confirm that is intended: it is a **residency surface** (§11)
>    even though session state is bounded, non-authoritative, and 24 h TTL.

### Method note — one check that produced a false signal

Before the console screenshot settled 0.4, region was inferred from **REST round-trip latency** (285 ms →
"not Mumbai"). **That inference was wrong.** A control measurement against Supabase — already confirmed
`ap-south-1` — returned **403 ms**, i.e. *slower* than the endpoint being accused of being overseas; a
US reference returned 3,727 ms. The dev machine's uplink dominated every number, so none of them carried
regional signal.

**Recorded because the lesson generalises**: latency measured from a developer laptop cannot establish
server region. Only a control against a known-region endpoint exposes that — and the control here is the
sole reason a false finding did not reach these documents. **Verify region from the provider's own
metadata** (MCP, console, or API), never by timing.

---

## Phase 1 — Database migration (§9.3, blocking, foundational)

**Blocks every other phase.** D1's `dock_occupancy` + exclusion constraint is the correctness bedrock every
tool, every UI state, and every test in this document assumes exists. This phase is §9.3 verbatim,
sequenced — not reinterpreted.

| # | Task | File(s) |
|---|---|---|
| 1.1 | **Backup** — Supabase dashboard snapshot or `pg_dump` of the live project. Non-negotiable; this is the only safety net for a migration running directly on production (D16) | — |
| 1.2 | Reconcile migration drift — `20260817040000_escalation_resolution_note.sql` **[G]** (named directly in §9.3 step 2) was on disk but unapplied as of the last audit. Resolve before adding anything on top | `supabase/migrations/` |
| 1.3 | `CREATE EXTENSION IF NOT EXISTS btree_gist;` | New migration file |
| 1.4 | Convert `text` → `timestamptz` across `appointment_slots`, `appointments`, `shipments`, `eta_updates`, `facility_checkins`, `dock_status_events` — existing values are ISO-8601 with `+05:30`, a type change not a reformat | New migration file |
| 1.5 | Create `dock_occupancy` with the D1 exclusion constraint (exact DDL already in `SOLUTION_DESIGN.md` §0's "D1 in concrete terms"); backfill one row per active appointment | New migration file |
| 1.6 | Route backfill conflicts to the D12 worklist — 85 `REQUIRES_TIME_RESOLUTION`, 116 `REQUIRES_DOCK_REASSIGNMENT` (D15). **Never silently fixed** | Backfill script |
| 1.7 | Rebase Layer A onto the 2026-08-13 snapshot (D14) — shift every Layer A timestamp by the same delta; re-run the id/offset assertion from §9.1 | Migration + assertion script |
| 1.8 | Add the remaining §11.3 imperfections — capacity incidents beyond Jaipur, intraday facility rules, location-spelling variety | Seed/backfill script |

> **§9.3's own warning, carried forward exactly**: *"Steps 3 and 4 are not optional cleanup — they are
> load-bearing for D1. Attempting step 5 without them fails on the first `CREATE TABLE dock_occupancy`
> (no `btree_gist`) or the first insert into a `tstzrange` column built on `text` data."*

**Checkpoint 1**: `dock_occupancy` exists with the exclusion constraint live; a manual two-row overlap
insert fails as expected; the D12 worklist is populated and queryable, not silently discarded.

---

## Phase 2 — Backend tool catalogs (§7.5, depends on Phase 1)

One sub-phase per catalog. §7.5.2 (gate/yard) and §7.5.4 (driver) already existed before this
redesign — this phase is **extending** four catalogs, not building six from scratch. Mostly `[P]`-safe;
two real cross-catalog dependencies are called out.

| # | Task | Catalog | Parallel? |
|---|---|---|---|
| 2.1 | Extend §7.5.1 — add `block_dock` / `end_dock_block`, writing `dock_status_events` | Planner | `[P]` with 2.2–2.4 |
| 2.2 | Implement §7.5.5 in full — `get_escalation_queue`, `acknowledge_escalation`, `reassign_escalation`, `take_over_thread`, `hand_back_thread`, `resolve_escalation`, `cancel_escalation`, `request_sequencer_proposal` | Ops (new) | `[P]` with 2.1, 2.3, 2.4 |
| 2.3 | Implement §7.5.6 in full — five read-only tools, `carrier_id`-scoped | Carrier portal (new) | `[P]` — no dependency on any other catalog |
| 2.4 | Implement §7.5.7 in full — **13 tools** (11 table rows; `deactivate_user`/`reactivate_user` and `create_facility_rule`/`update_facility_rule` are each one row covering two tools) across users/roles, facility rules, policy, audit. **Corrected 2026-08-22** — this row previously said "ten," found wrong in a consistency sweep against the actual §7.5.7 table | Admin (new) | `[P]` — no dependency on any other catalog |
| 2.5 | **Wire the one real cross-catalog dependency**: `request_sequencer_proposal` (2.2) delegates to §7.5.3's existing `propose_facility_schedule`, not a parallel implementation — the incident and the run must stay linkable via `scheduling_run_id`/`escalation_id` | Ops → Sequencer | **Not parallel** — depends on 2.2 landing first |
| 2.6 | Confirm §7.5.3's `apply_schedule_proposal` is reachable from the planner surface being built in Phase 4 — this is the other half of the ops→planner capacity-incident handoff | Sequencer ↔ Planner | Sequencing note, not new code |
| 2.7 | Implement §7.5.8 in full — the shared/cross-cutting catalog found 2026-08-22, checking the finished UI-UX mockup work against this document's tool catalogs: `search_records`, `get_notifications`, `mark_notifications_read`, `get_notification_preferences`/`update_notification_preferences`, `get_account_profile`, `request_password_reset`, `sign_out_everywhere` | Shared shell (new) | `[P]` — no dependency on any other catalog, **except 2.8** |
| 2.8 | **`search_records` composes, never queries directly** — implement as calls into each contributing module's own existing read method (Exception Intake's shipment lookup, Allocation's appointment lookup, Identity & RBAC's driver/carrier lookup, Capacity & Rules Admin's facility lookup), composed at the API layer per `SYSTEM_DESIGN.md` §3's "search is not a thirteenth module" decision. **Not parallel** — depends on 2.1–2.4 landing first, since it calls their read paths | Cross-module composition | Depends on 2.1–2.4 |
| 2.9 | **Implement `sign_out_everywhere` and the plain "Sign out" button as two explicitly different calls** — `signOut({ scope: 'global' })` for the former, `signOut({ scope: 'local' })` for the latter. Supabase's own default is `global`, so the plain button **must** pass `local` explicitly or it silently becomes the other action | Shared shell / Identity | `[P]` with 2.7, but flagged because the failure mode (both buttons doing the same thing) is silent and easy to miss in review |

**Checkpoint 2**: every tool named in §7.5.1–§7.5.8 has a callable implementation; `acknowledge_escalation`
and `confirm_request`'s transactional race behaviour (§7.5.1's own text) is unit-tested per §9.2's
`pending_expiry_vs_planner_confirm` case *before* Phase 5's sweeper exists to trigger it live. **§7.5.8
checkpoint addition**: a manual test confirms the plain "Sign out" button does *not* revoke sessions on
other devices — this is the one place in Phase 2 where a passing unit test could still hide a real defect
if the two `signOut` calls were accidentally swapped.

---

## Phase 3 — Background jobs (`TECH_STACK.md` §5–§6, depends on Phase 1, informs Phase 2's race tests)

| # | Task | Depends on |
|---|---|---|
| 3.1 | EventBridge Scheduler, 1-minute rate, `ap-south-1` — the expiry sweeper trigger | Phase 1 (needs `dock_occupancy`) |
| 3.2 | Internal authenticated FastAPI endpoint the sweeper calls — HELD expiry (D2) and PENDING expiry (D9) in the **same transaction** as any concurrent `confirm_request`, per §7.5.1's stated race resolution | 3.1, Phase 2.1 (`confirm_request` must exist) |
| 3.3 | Thread the **injectable clock** (§9.1) through the sweeper, the engine, and the sequencer — this is what makes `pending_expiry_vs_planner_confirm` reproducible on demand for `TESTING_STRATEGY.md`'s suite, not timing luck | 3.2 |
| 3.4 | Outbox drain job, same scheduler mechanism — `notification_outbox` → delivery, status into `operational_messages` | 3.1 |
| 3.5 | Web push (VAPID) provider wiring | `[P]` with 3.6 |
| 3.6 | SES email provider wiring (warehouse notifications) | `[P]` with 3.5 |
| 3.7 | **Remove SMS from the notification code path** — if any SMS provider wiring exists in the current live code, this is a deletion task, not a no-op. Confirm in Phase 0.1 whether it does | Phase 0.1's finding |

**Checkpoint 3**: a manually-created `HELD` row with a past `expires_at` transitions to `EXPIRED` within
one sweeper cycle, without needing a read to trigger it; a queued outbox row is delivered without a
request-path wait.

---

## Phase 4 — Frontend surfaces (all six UI-UX surfaces, depends on Phase 2)

One sub-phase per surface, `[P]`-safe **except** the shared queue component, which two surfaces consume.

| # | Task | Parallel? |
|---|---|---|
| 4.0 | Build the **shared queue component** (U23, `components.md` §19 — selection/bulk-action model, 3-tier destructive-action tiering, product-wide keyboard map) once | **Blocks 4.2 and 4.3** |
| 4.1 | `01-driver-chat/` — reconcile against whatever driver-chat UI already exists live (Phase 0.2's finding); assistant-ui binding (U56), custom runtime adapter (`TECH_STACK.md` §9) | `[P]` |
| 4.2 | `02-ops-exception-console/` — three-pane shell (U89), co-pilot (U57) | Depends on 4.0, then `[P]` |
| 4.3 | `03-planner-dock-board/` — two-tab shell (U102), Kibo UI Gantt (**verify zoom/virtualisation — still an open item from U52**) | Depends on 4.0, then `[P]` |
| 4.4 | `04-gate-yard-kiosk/` — two device layouts (U108), `spacious` density | `[P]` |
| 4.5 | `05-carrier-portal/` — single dashboard (U114) | `[P]` |
| 4.6 | `06-admin-console/` — four tabs (U117) | `[P]` |
| 4.7 | Wire every surface's data calls to its confirmed §7.5.x tool set (Phase 2) — no surface should call a tool name that isn't actually implemented | Depends on the matching Phase 2 sub-task |
| 4.8 | **Shared shell** — sign-in (extended with the role picker and password-reset flow), the user menu, the notifications panel, the search palette, and the account/settings page (`00-foundations/mockup-shared-shell.html`, 29 artboards). This is cross-role chrome, not a seventh persona surface, so it's built once and consumed by all six | Depends on 2.7–2.9; `[P]` internally except the search palette, which depends on 2.8 specifically |

**Checkpoint 4**: each surface's `mockup.html` states remain reproducible from the live build with real
data substituted for the mockup's fixtures — the token values should not have drifted, since the design
system was built to be the actual implementation source, not a reference to redraw from. **4.8's addition**:
the notifications panel and notification preferences are verified as two distinct, separately-wired pieces
— a build that only wires one and silently reuses it for the other has not actually implemented both.

---

## Phase 5 — Identity and scope (`TECH_STACK.md` §4, can start once Phase 1 lands, gates Phase 4's real data)

| # | Task |
|---|---|
| 5.1 | Confirm Supabase Auth JWT issuance is unchanged (it should be — this redesign doesn't touch identity issuance, only consumption) |
| 5.2 | Implement server-side scope resolution from `user_scopes` in the **repository layer** — not the router, not the tool schema (M15's explicit requirement) |
| 5.3 | Audit every §7.5.x tool for the M15 violation pattern named in §7.5's own opening: a tool accepting `facility_id`/`carrier_id` as a scope-*deciding* argument rather than a scope-*validated-against* one |
| 5.4 | Wire AgentCore Identity for inbound Runtime authorization — a separate concern from 5.1–5.3, answering "may this caller invoke the agent," not "what may they see" |

**Checkpoint 5**: a request scoped to Facility A, given a crafted `facility_id` for Facility B, is refused
server-side — not merely hidden client-side. This is the concrete, executable version of the inference-risk
rule `auth-and-scoping.md` states throughout.

---

## Phase 6 — Observability (`TECH_STACK.md` §8, can run alongside Phase 2–4)

| # | Task |
|---|---|
| 6.1 | Verify LangSmith's thread-grouping metadata key against current docs (`session_id`/`thread_id`/`conversation_id`) — open item carried from `TECH_STACK.md` |
| 6.2 | Map `chat_threads.thread_id` to the confirmed key — no new identifier |
| 6.3 | Construct nested child spans for LLM calls and tool calls inside the manual loop — confirm what LangSmith's SDK gives free vs. what needs explicit run-tree construction, since there's no executor doing this automatically |
| 6.4 | Background flush, bounded queue, drop-not-block — never awaited in the request path |

**Checkpoint 6**: one driver turn that calls two tools produces a single LangSmith thread containing three
nested spans (2 tools + 1 final LLM call) in execution order, not three unrelated top-level runs.

---

## Phase 7 — Testing (`TESTING_STRATEGY.md`, depends on Phases 1–6 landing)

| # | Task | Source |
|---|---|---|
| 7.1 | Four Locust suites — `same_interval_race`, `hold_expiry_vs_confirm`, `pending_expiry_vs_planner_confirm`, `ordinal_staleness` | `TESTING_STRATEGY.md` §3a |
| 7.2 | Locust load profiles — the §7.3 spike and §11.1 volume | §3b |
| 7.3 | Seven Playwright multi-context suites, one per named UI race, **with distinct `storageState` paths per role** (the documented pitfall) | §4 |
| 7.4 | The cross-layer test — two driver PWA contexts racing one slot | §5 |
| 7.5 | Determinism assertion — same snapshot + policy version, byte-identical output, run twice | §6 |
| 7.6 | §9.2's 19 named stress fixtures as pytest cases, each with the coverage-is-asserted-mechanically property (§10 item 4 — a case with no test fails the suite) | `SOLUTION_DESIGN.md` §9.2 |

**Checkpoint 7**: every suite in `TESTING_STRATEGY.md` exists and has been **run at least once** — not
just written. `TESTING_STRATEGY.md` §9 item 1 is explicit that nothing in it has an execution record yet;
this phase is what changes that.

---

## Phase 8 — Verification (§10, the exit gate for this entire document)

`SOLUTION_DESIGN.md` §10, *"the thing a reviewer will actually push on,"* run in full — not a subset:

1. **Concurrency harness** — N=50 simultaneous `request_slot`, assert 1 `HELD` / 49 `SLOT_CONFLICT_REFRESH_REQUIRED` / zero 5xx / zero orphaned holds after TTL.
2. **Invariant queries in CI**: no two `dock_occupancy` rows overlap for one dock in a capacity-consuming state · no shipment has >1 current active appointment · no confirmed appointment overlaps an outage window · no late start without approval where the facility defines the rule · every reefer on a refrigerated dock · every weight-eligible dock match — run against the shipped seed, must return **exactly** the two known §6.2 #7 violations and nothing else.
3. **Idempotency replay** — `THR001`/`THR009`, same `dedupe_key` → exactly one exception, one booking attempt, one notification.
4. **Scenario replay** — all 29 seeded cases, mechanically-asserted coverage.
5. **Determinism proof** — byte-identical, twice.
6. **Chaos-lite** — kill Redis mid-conversation; the next turn answers correctly from Postgres alone.

**This document is not done when the code compiles. It is done when §10 passes.**

---

## AgentCore deploy discipline (applies to every deploy from Phase 2 onward)

Carried forward verbatim from `AGENTS.md`, because this project has already been bitten by skipping it
once (2026-08-17, a prompt fix "redeployed successfully" but kept reproducing because the codezip snapshot
was never re-staged):

> Any AgentCore Runtime deploy must be immediately preceded by `python docs/scripts/stage_agentcore_codezip.py`.
> `agentcore.cmd deploy` packages `agentcore/codezip/app/` — a separate copied snapshot of `backend/app/`,
> not the live source. No exceptions, no "it's a small change so skip it."

**Also research before the first deploy in this plan**: AgentCore's **direct code deployment** capability
(shipped Nov 2025, per public AWS release notes) may remove this footgun's root cause entirely rather than
requiring the staging script forever. Verify whether it applies here before assuming the manual staging
step is still required — but do not skip staging on an unverified assumption that it's been superseded.

---

## Open items — carried, not assumed

| # | Item | From |
|---|---|---|
| 1 | Every `[A]`-marked path in Phases 1–4, pending Phase 0 | This document |
| 2 | ~~The LLM model bake-off~~ — **closed 2026-08-21**: `gemini-3.7-flash` on Vertex `asia-south1`, verified by spike | `TECH_STACK.md` §7 |
| 2a | **`langchain-google-genai` ≥ 4.x requires `langchain-core` 1.x** — decide against the real `backend/uv.lock`. 2.x **breaks the multi-turn tool loop** (`thought_signature`); a proven raw-SDK fallback exists | `TECH_STACK.md` §7, open item 1b |
| 2b | **Vertex must be configured with ADC + explicit `location="asia-south1"`** — the API-key path may silently use the global endpoint, losing in-region latency *and* residency | `TECH_STACK.md` §7, open item 1a |
| 3 | OpenAI's current model naming/pricing — unconfirmed (**fallback path only** now) | `TECH_STACK.md` §7, open item 2a |
| 4 | Kibo Gantt zoom/virtualisation | `TECH_STACK.md` open item 8, restated at 4.3 |
| 5 | ~~AgentCore direct code deployment vs. the codezip-staging requirement~~ — **closed, found stale in a 2026-08-22 consistency sweep**: `DEPLOYMENT.md` §2.2 already answers this "no" — *"Direct code deployment does not fix this by itself... the defect is not zip-vs-container — it is that a manually-synced duplicate of the source exists at all."* Staging stays required regardless of deployment mode | `DEPLOYMENT.md` §2.2, its own open item 1 |
| 6 | Whether any current live code already implements pieces of driver-chat, gate/yard, or the notification outbox that this plan would otherwise duplicate | Phase 0.1–0.2 |
| 7 | ~~**`request_password_reset`'s phone path**~~ — **closed 2026-08-22: email-only for v1**, owner decision. Phone-registered accounts (drivers) have no self-service reset path; defensible because the driver session is already long-lived with silent refresh, so re-entering a password is rare. Fallback if it's ever needed: admin-assisted reset via the existing `update_user` tool (§7.5.7), not a new OTP flow | `SOLUTION_DESIGN.md` §7.5.8 |
