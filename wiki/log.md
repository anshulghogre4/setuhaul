---
title: SetuHaul Wiki Operation Log
type: log
status: append-only
scope: wiki
last_updated: 2026-08-22
---

# Wiki log

## 2026-08-22 07:46 IST | process | Adopted the AI Collaboration Field Guide into `AGENTS.md`; installed `gh` CLI

- Mapped the guide's 15 habits against existing `AGENTS.md` rules before adding anything — most already covered (handover, decisions-with-reasoning, architecture docs, constraints, test checklist, diff review, session handoff all pre-existed under other names). Added a new `## AI-collaboration discipline` section stating the mapping plus the genuinely new rules: code comments on non-obvious logic, explicit plan-before-implement for code changes, execution-tracing for non-trivial changes, a rollback note requirement for risky live-code changes, model version-pinning in changelog entries, "own the mental model," requests scaled to risk.
- Installed GitHub CLI (`gh` 2.98.0, `winget`) for planned milestone/epic/issue tracking on the apply-to-existing work; `gh auth login` left for the owner.
- Root `AGENTS.md` change — not workspace-exempt, hence this entry. The session's six `COMPARISON-*.md` docs stay exempt (read-only against `backend/`/`frontend`/`supabase/`).

## 2026-08-20 09:48 IST | design | `02-ops-exception-console/` written; spec-kit evaluated; recompare closed a real `SOLUTION_DESIGN.md` gap

- Candidate-overhaul work in `docs/New-Solution-New-Design/` (isolated workspace; production `docs/` and app untouched). Evaluated `github/spec-kit` against first-party sources — not installed (per-feature `spec.md` slicing mismatches this whole-product spec; Constitution redundant with `AGENTS.md`), two document shapes borrowed for future roadmap steps (tech-stack doc, apply-to-existing doc), Constitution Check gate adopted as a per-doc habit now.
- Wrote `UI-UX/02-ops-exception-console/` in full: `screens`, `components`, `flows-and-states`, `edge-cases`, `accessibility`, `mockup.html` (U89–U96). Three-pane persistent layout (queue/detail+thread/co-pilot) as a scoped, recorded exception to the existing inline-expansion rule; co-pilot draft→approve→send two-gate model; explicit acknowledge/takeover/hand-back/resolve/cancel lifecycle.
- Grep-verified recompare against `SOLUTION_DESIGN.md` found §7.5 (tool catalogs) had planner/gate/sequencer/driver but no ops catalog — every new surface action sat on an undefined backend contract. Closed by adding `### 7.5.5 Ops console` to `SOLUTION_DESIGN.md` (8 tools, one delegating to the existing sequencer-proposal tool to preserve the propose/apply split across the ops→planner handoff) plus a flagged-as-assumption reason-code enum for Resolve/Cancel.
- Same pass closed 4 unaddressed §7.4 escalation reasons and, after the owner asked directly whether the project's design-review skills were actually running, a real (not just cited) `checklist-design` audit — found one genuine gap (escalation-queue bulk actions, resolved as deliberately none) and caught the mockup's icon rail carrying two undefined placeholder icons. `UI-UX/README.md` decisions log now U1–U101, verified no gaps. Process fix recorded in `.claude/agents/ui-ux-designer.md` and persistent memory: invoke skills via the `Skill` tool, don't recall them.
- Docs-only. Synced CHANGELOG, [[handoff]].

## 2026-08-17 18:40 IST | docs | Built a 5-slide dark-theme SetuHaul overview deck

- Owner asked for a presentation (tech stack, essential tools only, whole scheduling architecture, LangSmith/AgentCore/CloudWatch tracking), 4-5 slides, styled to match the app's current dark theme. Generated `docs/SetuHaul_System_Overview.pptx` with `python-pptx`, using the real tokens from `frontend/src/App.css` (`--bg`, `--panel`, `--accent`, `--primary`, `--warn`, `--outline`) rather than an invented palette.
- Content grounded via an Explore-agent pass over `backend/app/assistant/tools.py`, `backend/app/scheduling/{feasibility,allocation}.py`, [[ai-system]], [[architecture]], `plans/sprint-4-hosting.md`, `docs/AI_TOOLING.md`: 23 typed tools (read vs. confirm-gated write), scheduling flow React 19 → FastAPI (ECS) → bind_tools loop (no agent framework) → typed tool → feasibility/allocation services → Postgres, Upstash Redis as 24h non-authoritative memory, Ops dashboard reading the same Postgres. Observability slide states LangSmith as fully implemented, AWS AgentCore Runtime as deployed/live, and CloudWatch as only partially wired (platform span visible via Transaction Search; in-app tool-level spans still blocked by an open ADOT credential-recursion bug, so fine-grained tracing stays LangSmith-only).
- Verified by rendering every slide to PNG via PowerPoint COM automation and visually reviewing; fixed a title-slide chip overflow, a tech-stack card/footer collision, and an architecture-diagram connector that cut through box text before finalizing. Docs/presentation-only, no application code changed. Synced CHANGELOG, [[handoff]].

## 2026-08-17 15:35 IST | docs | Removed the "For judges / presenters" table added at 15:20 IST

- Owner asked for the just-added judges/presenters link table removed from root `README.md` immediately after the 15:20 IST refresh introduced it. Removed the section and its links; linked docs (`PRESENTATION_CHECKLIST.md`, `PRESENTATION_QA_ANSWERS.md`, `DEMO_MANUAL_RUNBOOK.md`, `DEMO_DAY_READINESS.md`) are untouched. `git diff` confirms only that section's lines changed. Synced CHANGELOG.
- Agent/surface: Claude Code.

## 2026-08-17 15:20 IST | docs | Refreshed root README.md as the presentation front door

- Reworked root `README.md`: added a judges/presenters quick-nav table at the top; corrected the Status section (Sprint 4 hosting now accurately described as operationally live with the gate still open, matching AgentCore `agentRuntimeVersion=9` verification); synced "what you can demo / do not claim" with `docs/PRESENTATION_QA_ANSWERS.md`'s honest gaps; converted the bold Hosted line to a real anchorable heading; linked the four on-disk docs that weren't in the Documentation table yet. Diagrams/tech-stack/standards sections re-verified unchanged. Docs-only. Synced [[handoff]].

## 2026-08-17 15:05 IST | docs | Added presentation Q&A prep doc for PDF §11.2/§12.1

- Added `docs/PRESENTATION_QA_ANSWERS.md`: every §11.2 stress scenario and §12.1 judge question answered with a code reference and the exact `docs/DEMO_MANUAL_RUNBOOK.md` phase to demo it. Two honest out-of-scope gaps flagged (§12.1 Q8 OR-Tools, §11.2 #11 warehouse-reply-conflict); two scenarios flagged as tested-but-not-staged (§11.2 #2, #9). Grounded in the existing PDF re-read in [[current-state]]/`docs/DEMO_DAY_READINESS.md` (poppler unavailable this session for a fresh PDF render) plus fresh greps confirming code references. Linked from [[index]]. Docs-only. Synced [[handoff]].

## 2026-08-17 (post-09:25 IST) | correction | AgentCore v9 confirmed genuinely fixed; prior "still stale" claim was outdated

- Owner said they'd already deployed and were still seeing the bug, contradicting the prior entry's claim that AgentCore was on stale `agentRuntimeVersion=7`. Re-checked directly via AWS CLI (`get-agent-runtime`, `list-agent-runtime-endpoints`) and by downloading and grepping the live S3 artifact zip: `agentRuntimeVersion=9`, DEFAULT endpoint live on `9`, and both the wording fix (`prompts.py`) and pool_size fix (`session.py`) are genuinely present in the deployed code. The earlier claim was accurate when written but the owner's subsequent redeploy made it stale before it was corrected. If the bug still shows up live now, the leading suspect is session-level (Redis 24h history or AgentCore warm-container stickiness) rather than a deploy gap — retest on a fresh chat session. Synced [[handoff]] and [[current-state]].

## 2026-08-17 (post-09:25 IST) | diagnosis | Confirmed live screenshot repro is the known wording-regression bug, not new

- Owner shared a chat screenshot reproducing the 09:25 IST "confirm updating the ETA to None" wording bug against the hosted driver chat, then replied `None` to the confirmation prompt. Diagnosed as expected: the fix (commit `a590663`) shipped to ECS (`:10`) but AgentCore Runtime is still on `agentRuntimeVersion=7` (08:40 IST), predating the fix — confirmed via `git log`/`CHANGELOG.md` showing no `agentcore.cmd deploy` since. Flagged risk of continuing to confirm the `None` ETA prompt (real two-step write). Next action: `agentcore.cmd deploy --yes` (codezip already re-staged), then re-test live. No code changed. Synced [[handoff]] and [[current-state]] "Verify before claiming".

## 2026-08-17 09:25 IST | fix + incident | Escalation wording regression + live DB connection-pool exhaustion

- Wording regression: escalate_exception replies borrowed ETA vocabulary ("confirm updating the ETA to None") because the confirm-gate prompt explicitly compared it to `report_delay_or_update_eta`. Confirmed via direct `escalation_queue` query that zero rows were written — confirm-gate held, this was cosmetic. Made the escalate_exception description fully self-contained, forbidding ETA/timestamp language.
- Live incident: `cancel_appointment` and `escalate_exception` both started failing with generic "system limitation" errors. Diagnosed as `EMAXCONNSESSION` — the session-mode pooler's fixed 15-connection budget was fully exhausted; confirmed by being unable to get a debug connection through the app's own `DATABASE_URL` after 5 retries. Root cause: `backend/app/db/session.py` never set explicit `pool_size`/`max_overflow`, so SQLAlchemy's defaults let one process alone claim the entire budget. Fixed: `pool_size=3, max_overflow=2`.
- Immediate relief: connected via Supavisor's transaction-mode port (a separate pool) to inspect `pg_stat_activity`, found 12 stuck Supavisor-proxied backends (9 leaked `idle in transaction` on a bare `BEGIN;`), terminated all via `pg_terminate_backend`; verified the session-mode pooler works again.
- Added `docs/scripts/free_stuck_db_connections.py` (dry-run default, `--confirm` to act) as a self-serve fix, wired into `docs/PRESENTATION_CHECKLIST.md` §7 Recovery.
- ECS redeployed for both fixes (`:10` wording, `:11` pool-size). AgentCore redeploy for the pool-size fix still owed. Leak's root cause not fully diagnosed — smaller pool_size caps blast radius, doesn't prevent recurrence. Synced CHANGELOG, [[handoff]], [[current-state]], [[contradictions]].

## 2026-08-17 08:40 IST | deploy | AgentCore v7 + ECS :9 redeployed and artifact-verified for the confirm-gate

- Owner ran `agentcore.cmd deploy --yes`; this agent independently verified by downloading the actual live S3 zip (`agentRuntimeVersion=7`) and grepping the extracted source — `EscalateExceptionArgs.confirmed=False` default, `CONFIRMATION_REQUIRED` gate, and sharpened prompt all present. This agent rebuilt/pushed `setuhaul-api:latest` and rolled ECS Express (task-def `:9`, canary completed cleanly, `/health/live` 200). Given the earlier 07:20 IST false-positive, this round both sides were confirmed by inspecting deployed artifact content rather than trusting CLI status alone. Still open: an actual hosted chat turn re-testing Phase B against this deploy. Synced CHANGELOG and [[handoff]]/[[current-state]].

## 2026-08-17 08:10 IST | fix | escalate_exception made a two-step confirm write

- Verified the redeploy genuinely shipped the false-escalation prompt fix (downloaded and inspected the live S3 artifact zip directly) — yet the bug still reproduced live on a fresh session, meaning the LLM (hosted `gpt-4o-mini`) still misjudges intent by blending the context-lock line with the preceding delay/ETA-report turn. Prompt wording alone confirmed insufficient after failing twice. Added a structural safety net: `escalate_exception` now requires `confirmed=true` to actually write, mirroring `report_delay_or_update_eta`. `EscalateExceptionCommand.confirmed` defaults `True` (system/ops callers — `persist_noslot_escalation`, `/operations/escalate` REST — unaffected); the driver-chat tool's arg defaults `False`, so a misfired LLM call now returns `CONFIRMATION_REQUIRED` with zero DB writes. New test asserts zero `session.execute` calls when unconfirmed. Backend units 87 passed; compile PASS. Re-staged `agentcore/codezip/`. Not yet redeployed to either hosted target or live-verified. Synced CHANGELOG, [[handoff]], [[current-state]].

## 2026-08-17 07:35 IST | fix + process | AgentCore codezip staging gap found; deploy rule added

- Owner re-tested Phase B live after the 07:20 IST "redeploy" and the false-escalation bug reproduced identically. Root cause: `agentcore.cmd deploy` builds from `agentcore/codezip/app/`, a separate copy of `backend/app/` staged by `docs/scripts/stage_agentcore_codezip.py` — that script was never run before the deploy, so it shipped the stale pre-fix prompt while `agentcore.cmd status`/`deploy` reported success (confirmed via grep on the codezip copy). Re-ran the staging script (local only, no AWS); codezip now has the fix. Owner still needs to run `agentcore.cmd deploy --yes` again. Added a mandatory staging-before-deploy rule to `AGENTS.md` Delivery rules and `plans/sprint-4-hosting.md` §5.6 (first deploy) + §5.11 (day-2 table and command block) so this "deploy succeeds, bug persists" failure mode can't recur silently. Corrected `wiki/contradictions.md` and [[current-state]] with the accurate root cause (the earlier "redeployed and live" claim was wrong for AgentCore). Synced CHANGELOG and [[handoff]].

## 2026-08-17 07:20 IST | deploy | AgentCore + ECS BFF redeployed for the false-escalation fix

- Split deploy: owner ran `agentcore.cmd deploy --yes` (Runtime `READY` confirmed via `agentcore.cmd status`, ARN unchanged); this agent built/pushed `setuhaul-api:latest` to ECR (`118490268011.dkr.ecr.us-east-1.amazonaws.com`) and rolled ECS Express via `aws ecs update-express-gateway-service` on `service/default/setuhaul-api`. Canary rollout (5%/3min bake) completed cleanly: new task-def `default-setuhaul-api:8` is the sole PRIMARY deployment, old `:7` fully drained, `/health/live` 200 throughout. Still open: an actual hosted chat verification of the fix (`docs/HOSTED_SMOKE_CHAT_SCRIPT.md` §1 step 3), and cleanup of the stray `ESC-53B8A6EA0A37` escalation. Synced CHANGELOG and [[handoff]].

## 2026-08-17 07:05 IST | docs | README scheduling algorithm section + Mermaid diagram

- Added a `## Scheduling algorithm` section to root `README.md` explaining `find_feasible_slots` (`backend/app/scheduling/feasibility.py`) as a pure deterministic function of PostgreSQL state plus editable `backend/app/scheduling/constraints.json` policy weights, with a Mermaid flowchart tracing the exact implemented pipeline: facility-scoped candidate query → six ordered hard constraints (slot open/unoccupied, dock active/no overlapping event, dock-type match, refrigeration/weight, ETA+unload fits window, facility hours) → deterministic `rank_score` (priority + lateness×4 capped 720m + wait-after-ETA×-6 + fit-slack×1 capped 120m ± dock-match penalty) → sort → `REC-` fingerprinted options or `escalation_queue` NOSLOT → transactional `request_slot`/`reschedule_appointment` revalidation. Every node was cross-checked against current source, not inferred from names. Docs-only; no application code or policy weights changed. Synced CHANGELOG.
- Agent/surface: Claude Code.

## 2026-08-17 06:35 IST | fix | False-escalation prompt bug (context-lock line mis-firing escalate_exception)

- Live hosted chat testing caught `I need help with shipment SHP-D16-RAVI.` (the standard Phase B/C/H context-lock line) creating a real `OPEN`/`HIGH` escalation (`ESC-53B8A6EA0A37`) instead of a zero-write context lock. Root cause: `prompts.py`'s escalate_exception rule treated "driver asks for help" as an independent trigger instead of gating on `NO_FEASIBLE_SLOTS`. Fixed: escalate_exception now requires an explicit escalate ask or a just-returned NO_FEASIBLE_SLOTS; naming/opening a shipment is explicitly non-escalating. Backend units 86 passed (text-only change; no deterministic test possible for LLM tool selection — live chat is the verification). **Not yet redeployed**; stray escalation record not yet cleaned up. Updated the runbook (Phase B1), driver chat script (row A), hosted smoke script (§1), and contradictions ledger. Synced CHANGELOG and master-plan Living deltas (added as TODO, not struck).

## 2026-08-17 06:20 IST | implementation | Ops dashboard appointment-confirm button

- Added `GET /api/v1/operations/pending-confirmations` (facility-scoped, admin can pass `facility_id`, 403 cross-facility) and wired an Ops dashboard **Pending confirmations** panel (`OpsHomes.tsx`) with a **Confirm** button calling the pre-existing `POST .../appointments/{id}/confirm` route (idempotency-keyed). Reject/expire remain REST/`/docs`-only. Backend units 86 passed (2 new); frontend build PASS. Corrected stale "Swagger-only" guidance in the runbook (Phase F4/H4), driver chat script §7, and demo-day readiness. Extended `docs/HOSTED_SMOKE_CHAT_SCRIPT.md` §4 to cover this button hosted — unverified there so far, same as the 05:35 IST infra fixes. Master plan Living deltas updated; Sprint 3 gate unchanged, Sprint 4 gate still OPEN. Synced CHANGELOG and [[handoff]]/[[current-state]].

## 2026-08-17 06:05 IST | docs | Hosted-only smoke chat script

- Authored `docs/HOSTED_SMOKE_CHAT_SCRIPT.md` after reading the runbook, driver chat script, and presentation checklist. Targets the verification gap in the 05:35 IST entry: the four hosted fixes (event-loop entrypoint, Upstash region+batching, Supavisor session-mode pooler, resolution-note persistence) are live-verified only via `agentcore.cmd invoke` CLI, not the real hosted browser path. Script: hosted health prep, read-path smoke on the two exact previously-broken tools, ETA write path, Mark-Resolved→`get_exception_status` resolution-note round trip, multi-tool scheduling turn, and a latency check vs the 28.6s baseline. Docs-only; no hosted run performed this turn. Synced CHANGELOG and [[handoff]]/[[current-state]]/[[index]].

## 2026-08-17 05:35 IST | fix + deploy | Upstash region/batching + Supavisor session-mode pooler fix

- Owner found via CloudWatch that Upstash (`ap-south-1`) was cross-region from `us-east-1` compute (~190ms/call, ~25 calls/turn). Created new `us-east-1` Upstash DB; SSM updated. Batched `redis_memory.py`: pipelined `load_turn_context()` (history+summaries+session in one round trip), pipelined `append_turn()`'s 5 writes, `maybe_summarize_history` skips its own `LLEN`. ~10 sequential calls/turn → ~2. Separately hit a live `DuplicatePreparedStatementError` on `get_driver_operational_context`/`get_exception_status`. First fix (`poolclass=NullPool`) deployed but did not resolve it live (3/3 identical failures) despite a clean local stress test. Root-caused via direct `pg_prepared_statements` inspection: Supavisor transaction-mode pooler (6543) swaps physical backends mid-session without reset, so asyncpg's sequentially-named handshake statements collide across unrelated clients — independent of `statement_cache_size`. Real fix: `DATABASE_URL` → Supavisor session-mode pooler (5432); reverted `NullPool`; restored `pool_pre_ping`. Verified live: 35 connect/query/close cycles zero errors (vs 100% failure before); `agentcore.cmd invoke` reproduces both original failing scenarios cleanly and repeatedly against the `DRV-RS-01` sandbox. Three ECS redeploys + two AgentCore redeploys. Backend units 84 passed throughout. Synced [[handoff]], [[current-state]], master plan Living deltas, CHANGELOG.

## 2026-08-17 04:35 IST | deploy | applied escalation resolution_note migration live

- Applied `supabase/migrations/20260817040000_escalation_resolution_note.sql` to live project `kujffzgqjmqphkmrbawy` via direct PostgreSQL connection (Supavisor pooler) since Supabase CLI was installed but not linked/authenticated in this environment. Verified `resolution_note text NULL` on `escalation_queue` and `driver_exceptions` via `information_schema.columns`; row counts unaffected. Created `supabase/CHANGELOG.md` (new, per the migration guide's own instruction) with the full deployment record plus the moved baseline entry. Caveat recorded: applied outside CLI/MCP so Supabase's migration-history tracking doesn't know about it — reconcile before next `db push`. Synced [[handoff]], [[current-state]], CHANGELOG.

## 2026-08-17 04:10 IST | fix | AgentCore event-loop TOOL_ERROR + escalation resolution-note gap

- Debugged LangSmith `TOOL_ERROR` (`Task ... got Future ... attached to a different loop`) on hosted Driver-chat DB tools. Root cause: `agentcore_main.py`'s sync `invoke_agent` wrapped `asyncio.run(_run_turn(...))`, creating a new event loop per invocation while the process-level `db` asyncpg pool stayed bound to whichever loop created it first (fails once on loop mismatch, retry succeeds after pool eviction — matches reported behavior exactly). Fixed by making `invoke_agent` a native async entrypoint so it runs on the Bedrock AgentCore SDK's own persistent per-container worker loop instead of spinning a fresh one every call. Also audited freshly-pulled `be62264` (Aman) end to end: Ops "Mark Resolved" remark was accepted by the API but never persisted — added migration `20260817040000_escalation_resolution_note.sql` + threaded `resolution_note` through `resolve_escalation()` and the `get_exception_status` tool SELECT. Backend units 84 passed, 3 skipped; import smoke PASS. Not yet live-verified — needs migration apply + ECS `setuhaul-api` redeploy + AgentCore Runtime redeploy (owner deploying separately). Synced [[handoff]], [[current-state]], master plan Living deltas, CHANGELOG.

## 2026-08-17 02:39 IST | ingest | stash conflict: keep Incoming changelog

- Resolved `CHANGELOG.md` stash-pop conflict by keeping Incoming (stashed 2026-08-16 21:30 IST reschedule-demo entry). Retained the already-on-main 2026-08-17 02:34 IST Driver Appointment Panel entry (append-only). Removed leftover `>>>>>>> origin/main` markers in `CHANGELOG.md` and this log. Synced [[handoff]], CHANGELOG. App tests not run.

## 2026-08-16 21:30 IST | fix + tooling | reschedule-demo sandbox driver + reschedule_appointment stale-hash bug

- Bulk-book-every-shipment request found infeasible live (563/667 terminal, only 19/104 eligible bookable, 13 of those are demo cast). Built isolated `DRV-RS-01`/`FAC-GGN-01` sandbox instead (`supabase/demo/seed_reschedule_driver.py` + rollback), all writes via production `request_slot`/`confirm_appointment`. Found and fixed a real bug in `reschedule_appointment`: nested `request_slot` re-validated the pre-cancel recommendation hash against a post-cancel option set it had just changed itself, so every reschedule failed `SLOT_OPTIONS_STALE` on first try — affects the live driver-chat tool identically, previously uncovered by any test. Fixed by not re-passing the recommendation id/policy version to the nested call. Live verified: seed PASS, isolation PASS (cast untouched, +4 shipments only), reschedule PASS post-fix on pending + confirmed appointments, negative stale-check still PASS, unit 81 passed, live cast/10x4 integration 2 passed. Also found + fixed a pre-existing `reset_demo_day.py --mode full` FK-crash risk: `appointments.shipment_id`/`slot_id` are `ON DELETE NO ACTION`, so any surviving non-D16 appointment (live chat booking, Dispatch Console auto-book, or the new sandbox) would abort the whole reset transaction; confirmed already reproducible today via an existing Dispatch Console booking. Fixed both DELETEs to skip still-referenced rows; corrected dry-run preview counts to match. `--mode cast` unaffected. Synced [[handoff]], [[current-state]], [[testing]], CHANGELOG, master plan Living deltas.

## 2026-08-16 21:05 IST | deploy | unified traces Runtime v3

- ADOT 0.18+ pin, UNIFIED_TRACES env, timed A2 28.6s, platform Invoke span in Transaction Search, ADOT recursion remains. Synced [[handoff]], [[current-state]], [[testing]], [[ai-system]], CHANGELOG, master plan Living.

## 2026-08-16 20:25 IST | decision | latency vs LangSmith MCP

- MCP for traces only. Synced [[skills-and-mcp]], [[handoff]], CHANGELOG, `docs/AI_TOOLING.md`.

## 2026-08-16 20:20 IST | verification | hosted LLM is OpenAI-first auto

- `AUTO_ORDER` OpenAI → OpenRouter → Gemini. Hosted SSM has OpenAI + Gemini only. Synced [[handoff]], CHANGELOG.

## 2026-08-16 20:15 IST | verification | Ravi no-appointment playbook

- MCP reconfirm: DRV001 rail empty is correct (RACE-A + RAVI unbound). SHP1017 still CONFIRMED `APT-A086CEB8CAB7`. UI walkthrough updated. Synced [[handoff]], CHANGELOG.

## 2026-08-16 20:10 IST | verification | FDE PDF demo/stress vs runbook

- Required §12.2 beats SHOW in code + runbook Phases A–F. §11.2: 9 SHOW / 2 PARTIAL (compare/leave-by/priority-later) / 2 NOT YET (dock-close UI, warehouse-reply channel). §7.3 OR-Tools optional NOT YET. Authored `docs/UI_TEST_WALKTHROUGH.md`. Synced [[handoff]], [[current-state]], DEMO_DAY_READINESS, CHANGELOG.

## 2026-08-16 20:05 IST | verification | tools catalog PDF vs code

- Compared `docs/Scheduling Algo and tools/SetuHaul_AI_Complete_23_Tools_Catalog.pdf` to `backend/app/assistant/tools.py` + live MCP schema. 23 names match; example IDs and `facility_schedules` do not. Logged in [[contradictions]]. Synced [[handoff]], [[source-map]], CHANGELOG.

## 2026-08-16 20:00 IST | docs | full Driver tool catalog

- Documented all 23 `build_driver_tools` entries (mutate vs read, codes, Ravi 3-shipment default) on [[ai-system]]. Synced [[handoff]], CHANGELOG.

## 2026-08-16 19:55 IST | verification | live Ravi 3 shipments, no rail appointment

- MCP SQL: DRV001 actives `SHP-D16-RACE-A` / `SHP-D16-RAVI` (no current apt) + `SHP1017` (`APT-A086CEB8CAB7` CONFIRMED). Context primary is RACE-A so UI shows no appointment. Phase B still valid if chat names `SHP-D16-RAVI`. Synced [[handoff]], [[current-state]], CHANGELOG, presentation checklist.

## 2026-08-16 19:50 IST | decision | presentation 17 Aug + tool inventory

- Owner moved the show from 16 Aug to **2026-08-17**. Demo SQL/cast stay frozen 16 Aug (ETA-relative feasibility in `feasibility.py`). Authored `docs/PRESENTATION_CHECKLIST.md`. Reconciled Driver tool allowlist (23) from `backend/app/assistant/tools.py` with Graphify `explain build_driver_tools()`. Synced [[handoff]], [[current-state]], [[ai-system]], [[contradictions]], CHANGELOG.
- Verification: code read + Graphify explain; app tests **not run**.

## 2026-08-14 03:30 IST | docs | root README Sprint 3–4 refresh

- Hosted URLs, dual-mode, AgentCore/Locust/Docker commands, remaining work. Synced [[handoff]], CHANGELOG, master plan Living line.

## 2026-08-14 03:26 IST | docs | Locust commands in READMEs

- Root README Testing + loadtests README + demo runbook. Synced [[handoff]], CHANGELOG.

## 2026-08-14 03:22 IST | decision | runbook vs Locust scorecards

- Phase A–G Sign-off is reply/invariant; Suite A is HTTP health; Suite B is double-book. Synced runbook, [[handoff]], CHANGELOG.

## 2026-08-14 03:18 IST | verification | Locust Suite A hosted

- 5 users, web UI `:8089`, 3 min. auth_me 5/5; one C2 503. Suite B not run. Synced [[handoff]], [[current-state]], [[testing]], CHANGELOG, master plan. Gate not struck.

## 2026-08-14 03:20 IST | implementation | Locust files from demo runbook

- Authored `loadtests/` Suite A chat + Suite B CONTEND REST. Prompts unit-tested against `docs/DEMO_MANUAL_RUNBOOK.md`. Live Locust not run. Synced [[handoff]], [[current-state]], [[testing]], [[implementation]], CHANGELOG, master plan, scoreboard §5.8. Gate not struck.

## 2026-08-14 03:04 IST | decision | Locust scope and ECS cost

- Suite A short chat; Suite B scarce REST. Express idle ~$0.08/hr. Locust not run. Synced scoreboard §5.8, [[handoff]], CHANGELOG.

## 2026-08-14 02:59 IST | verification | owner pushed 9cabf48 to main

- Step 8–9 files on `origin/main`. No secrets in the commit. Synced [[handoff]], CHANGELOG. Gate not struck.

## 2026-08-14 02:52 IST | verification | Sprint 4 Step 9 BFF ARN

- Express ARN set; hosted Ravi chat through Runtime; CW logs + LangSmith `setuhaul.chat`. Synced [[handoff]], [[current-state]], [[testing]], [[implementation]], CHANGELOG, master plan, scoreboard. Gate not struck.

## 2026-08-14 02:28 IST | verification | Sprint 4 Step 8 AgentCore

- Runtime READY; CLI invoke real Ravi reply (`list_active_shipments`). ARN local-only. BFF ARN blank. Synced [[handoff]], [[current-state]], [[testing]], [[implementation]], CHANGELOG, master plan, scoreboard. Gate not struck.

## 2026-08-14 01:51 IST | verification | Sprint 4 Step 7 Vercel

- PR #5 on `main`; login routes 200; hosted Ravi chat 200. Synced [[handoff]], [[current-state]], [[testing]], [[implementation]], CHANGELOG, master plan, scoreboard. Gate not struck.

## 2026-08-14 01:46 IST | decision | hosting→main merge lock lifted

- Vercel production tracks `main`. Exit gate still requires Steps 7–10 evidence. Synced scoreboard, master plan, [[implementation]], [[contradictions]], [[handoff]], [[current-state]], CHANGELOG.

## 2026-08-14 01:43 IST | decision | main-only merge repercussions

- Full merge not required. vercel.json-on-main is the small escape hatch. Synced [[handoff]], CHANGELOG.

## 2026-08-14 01:40 IST | verification | Vercel main deploy inspected

- `setuhaul-roan.vercel.app` READY from main; `/` 200; login routes 404. Synced [[handoff]], [[current-state]], [[testing]], CHANGELOG.

## 2026-08-14 01:37 IST | decision | no merge hosting→main

- Preview-deploy `hosting` instead. Production Branch may stay `main`. Synced [[handoff]], CHANGELOG.

## 2026-08-14 01:32 IST | decision | Vercel branch via Settings → Git

- Import `main` chip opens GitHub. Production Branch is set after create. Synced [[handoff]], CHANGELOG.

## 2026-08-14 01:30 IST | decision | Vercel Import must be frontend-only

- Do not Deploy the default main/monorepo/25-env Import. Synced [[handoff]], CHANGELOG. Gate not struck.

## 2026-08-14 01:24 IST | decision | Step 7 use Vercel portal

- `origin/hosting` is `39ec4c9 mid hosting`. Prefer portal Import over CLI. Synced [[handoff]], [[current-state]], CHANGELOG. Gate not struck.

## 2026-08-14 01:20 IST | decision | Step 7 no Git Import yet

- Do not Import `setuhaul` on Vercel until `hosting` Step 1–6 code is pushed. Synced [[handoff]], [[current-state]], CHANGELOG. Gate not struck.

## 2026-08-14 01:04 IST | verification | BFF public DNS ready

- 8.8.8.8/1.1.1.1 resolve Express URL; health 200. Laptop resolver still NXDOMAIN. Synced [[handoff]], [[current-state]], [[testing]], CHANGELOG. Gate not struck.

## 2026-08-14 01:00 IST | verification | Sprint 4 Step 6 BFF

- App Runner rejected; Express Mode health 200. Synced [[handoff]], [[current-state]], [[implementation]], [[testing]], CHANGELOG, master plan, scoreboard. Gate not struck.

## 2026-08-14 00:45 IST | verification | Sprint 4 Step 5 ECR

- Pushed `setuhaul-api:latest` to ECR `us-east-1`. Synced [[handoff]], [[current-state]], [[implementation]], [[testing]], CHANGELOG, master plan, scoreboard. Gate not struck.

## 2026-08-14 00:28 IST | verification | Sprint 4 Step 4 SSM

- Owner `aws login` root `us-east-1`. Eight `/setuhaul/*` names written; values not logged. CDK bootstrap already present. Synced [[handoff]], [[current-state]], [[implementation]], [[testing]], CHANGELOG, master plan, scoreboard. Gate not struck.

## 2026-08-14 00:25 IST | blocker | Step 4 AWS CLI session expired

- `get-caller-identity` failed; SSM not written. Synced [[handoff]], CHANGELOG. Gate not struck.

## 2026-08-14 00:20 IST | verification | Sprint 4 Step 3 Docker smoke

- `setuhaul-api:step1` `:18000` health 200 + Ravi `/chat/message` 200. Container stopped. Synced [[handoff]], [[current-state]], [[implementation]], [[testing]], CHANGELOG, master plan, scoreboard. Gate not struck.

## 2026-08-14 00:16 IST | verification | Sprint 4 Step 2 browser chat

- Owner-login Vite Driver home: composer → `POST /api/v1/chat/message` 200; no active appointment. Synced [[handoff]], [[current-state]], [[testing]], CHANGELOG, master plan, scoreboard. Gate not struck.

## 2026-08-14 00:12 IST | verification | Sprint 4 Step 2 local smoke

- Ravi login + REST + `POST /api/v1/chat/message` on Vite `:5173` / uvicorn `:8000`, ARN blank. Roster file used for Driver bucket (no secrets written). Synced [[handoff]], [[current-state]], [[implementation]], [[testing]], CHANGELOG, master plan, scoreboard. Gate not struck.

## 2026-08-13 23:50 IST | implementation | Sprint 4 Step 1 code

- Host-readiness: chat alias, dual-mode ARN switch, CORS regex, Dockerfile, vercel.json, observability, thin AgentCore host. Units 77 passed. Synced [[handoff]], [[current-state]], [[implementation]], CHANGELOG, master plan (gate not struck).

## 2026-08-13 23:32 IST | ingest | Day-2 update commands

- Scoreboard §5.11: laptop redeploy commands; GHA CI-only. Synced [[handoff]], CHANGELOG.

## 2026-08-13 23:28 IST | ingest | ARN vs hosted URL

- Scoreboard now states Vercel uses BFF URL only; ARN is BFF env for chat at step 9. Synced [[handoff]], CHANGELOG.

## 2026-08-13 23:25 IST | ingest | Sprint 4 path locked

- Owner: stick to `plans/sprint-4-hosting.md`. GHA remains CI-only. Synced [[handoff]], CHANGELOG, master plan Living refresh. Gate not struck.

## 2026-08-13 23:20 IST | ingest | Hosting first-to-last order

- `plans/sprint-4-hosting.md` now has an explicit Step 1 FIRST → Step 10 LAST (Locust) table plus pass/fail checks. Synced [[handoff]], CHANGELOG, master plan Living refresh. Gate not struck.

## 2026-08-13 23:15 IST | ingest | Sprint 4 hosting scoreboard

- Added `plans/sprint-4-hosting.md` (branch `hosting`). App Runner closed to new customers → ECS Express Mode fallback. Punch-list documented, not implemented. Synced [[handoff]], [[current-state]], [[implementation]], [[architecture]], [[source-map]], [[contradictions]], CHANGELOG, master plan Living status (gate not struck).

## 2026-08-13 21:52 IST | ops | Owner will push locally

- Stopped agent commit/push. Owner will push demo-hardening on `setuhal-santosh`. Synced [[handoff]], CHANGELOG.

## 2026-08-13 21:51 IST | query | Teammate commit compatibility

- Aman’s Dispatch/Ops/tools/UI commits intact on `setuhal-santosh`. Local demo-hardening did not modify `frontend/`. Dispatch auto-book still present; REC id now passed. Synced [[handoff]], [[current-state]], CHANGELOG.

## 2026-08-13 21:44 IST | query | Demo remaining scoreboard

- Classroom product blockers closed. Remaining: live runbook rehearsal; optional polish; intentional PDF NOT YET. Synced [[handoff]] + `docs/DEMO_DAY_READINESS.md` + CHANGELOG.

## 2026-08-13 21:39 IST | implementation | PDF demo-hardening four blockers

- Cast reset leaves `D16-APT-RAVI-OLD` historical; chat mutation keys per turn; Redis stale without REC; reschedule restore on nested claim failure.
- Living scoreboard struck with unit evidence (65 passed). Sprint 3 gate unchanged; Sprint 4 PLANNED.
- Synced [[handoff]], [[current-state]], [[contradictions]], CHANGELOG.

## 2026-08-13 21:26 IST | ops | Restore Ravi Driver Auth password

- Live password-grant: Ravi **400 invalid_credentials**, Amit **200** on the same Driver bucket. Mapping `USR001`/`DRV001` intact.
- Admin-API reset only Ravi; re-smoke Ravi **200**; local `/api/v1/auth/me` **200** `USR001`/`DRIVER`/`DRV001`.
- Synced [[handoff]], [[current-state]], CHANGELOG. No application code. Passwords not recorded.

## 2026-08-13 01:25 IST | implementation | Dispatch Console, Fixed Viewport Layout & Bounded LOV Select with Click-Outside Dismissal

- Implemented Dispatch Console (`DispatchHome.tsx`, `dispatch_service.py`, `dispatch.py`) allowing Person A (Dispatch) to create shipments and auto-book initial appointments for assigned drivers.
- Implemented `DriverLayout.css` with fixed viewport height bounds where only `.chat-history` scrolls vertically.
- Added human-readable timestamp formatting and conditional `Updated ETA` field under Primary Shipment card.
- Implemented `BoundedLOVSelect` with `useRef` + `mousedown` click-outside dismissal and `max-height: 210px` scrollable search overlay.
- Verification: `npm run build` PASS (built in 587ms, 95 modules transformed); zero TypeScript lint errors.

## 2026-08-12 02:40 IST | implementation | 5 New Database Tools, Kwargs Unpacking Fix & Driver UI Typing Animation

- Added 5 new database-backed tools (`get_vehicle_and_carrier_details`, `get_gate_and_queue_status`, `get_facility_rules_and_restrictions`, `report_vehicle_breakdown_or_incident`, `get_dock_maintenance_alerts`) in `driver_reads.py` and `tools.py`.
- Fixed `TypeError` in `tools.py` for unpacked keyword arguments from LangChain `StructuredTool.from_function`.
- Fixed tool loop termination in `run_assistant.py` on `CONFIRMATION_REQUIRED` and `PERSISTED` to guarantee non-empty responses.
- Added animated typing indicator bubble in `DriverHome.tsx` and keyframe styles in `App.css`.
- Verification: 48 backend unit tests PASS (`PYTHONPATH=. pytest tests/unit`); Vite build PASS (`built in 588ms`); Live assistant execution verified for all 5 new tools (**200 OK**).

## 2026-08-12 02:16 IST | index | Graphify update after demo reset

- Incremental graph rebuild for reset script + Sprint 3/demo docs; outputs in `graphify-out/` (1192 nodes / 2096 edges).
- Synced [[handoff]] + CHANGELOG. App tests not run.

## 2026-08-12 01:18 IST | query | PDF challenge bug audit

- Read-only defect review of scheduling/chat/cast paths against FDE PDF stress cases.
- Durable findings synced to [[handoff]] + CHANGELOG; Sprint gates unchanged (1–3 COMPLETE, 4 PLANNED).
- Verification: unit suite 56 passed; no application code changes.

## 2026-08-12 01:05 IST | ops | Cast reset Ravi DB safety review

- Live table/FK review for cast mode; hardened appointment wipe for self-FK + ops messages; rollback proof PASS.
- Synced [[handoff]] + CHANGELOG. Confirm write not run.

## 2026-08-12 01:00 IST | ops | Demo-day cast reset script

- Added `supabase/demo/reset_demo_day.py` (cast/full, dry-run, confirm, Redis clear); docs in demo README, DEMO_MANUAL_RUNBOOK Prep, root README.
- Synced [[handoff]], [[current-state]], CHANGELOG. Live dry-run PASS; confirm write not run; app tests not run.

## 2026-08-12 00:40 IST | docs | Manual FDE demo + stress runbook

- Created `docs/DEMO_MANUAL_RUNBOOK.md`; refreshed driver chat script + DEMO_DAY_READINESS post-gate notes; README link.
- Synced [[handoff]] + CHANGELOG. Application tests not run.

## 2026-08-12 00:35 IST | docs | Architecture Mermaid exact-usage diagrams

- README + `docs/ARCHITECTURE.md` now show system/chat/allocation Mermaid for Sprint 3 reality.
- Synced [[handoff]] + CHANGELOG. Application tests not run.

## 2026-08-12 00:30 IST | docs | Root README aligned through Sprint 3

- Updated `README.md` for Sprint 1–3 COMPLETE status, demo cast, scheduling capabilities, and deferred Sprint 4 notes.
- Synced [[handoff]] + CHANGELOG. Application tests not run.

## 2026-08-12 00:25 IST | gate | Sprint 3 exit gate COMPLETE

- Struck Sprint 3 exit gate with live evidence: 10×4 load + D16 cast smoke; migration applied; units 56 passed.
- Auth hardening post-demo deferred; facility-wide OR-Tools deferred with later design note; Sprint 4 remains PLANNED.
- Updated [[current-state]], [[handoff]], [[implementation]], DEMO_DAY_READINESS, Living master plan, CHANGELOG.

## 2026-08-12 00:15 IST | ingest | Sprint 4 hosting plan written into master plan

- Added Living Sprint 4 row + §8.1 checklist to `plans/implementation-master-plan.md` (Vercel, App Runner default, AgentCore, CloudWatch, LangSmith, Locust).
- Promoted Locust 10×3–4 + AgentCore/CloudWatch from Sprint 3/§12 deferred into Sprint 4; Sprint 3 remains IN PROGRESS / gate OPEN.
- Updated [[implementation]], [[handoff]], [[current-state]], `plans/README.md`, CHANGELOG. Documentation only; app tests not run.

## 2026-08-12 00:02 IST | implementation | Driver tool kwargs + history route + SHP1017 no-feasible

- Fixed StructuredTool kwargs binding for Driver tools; feasibility CAST bind for text slot timestamps; chat history route after clean uvicorn restart; UI console tool results.
- Browser: `find_feasible_slots:NO_FEASIBLE_SLOTS` for SHP1017. Further chat/facility/refresh tests deferred; local servers killed.
- Updated [[handoff]], [[ai-system]], CHANGELOG, Living sprint note. Exit gate still OPEN.

## 2026-08-11 23:45 IST | ingest | Master-plan Living Sprint 3 reconcile

- Struck completed Sprint 3 items with dated evidence; added remaining-vs-deferred scoreboard and refreshed §13 next actions.
- Exit gate remains OPEN. Documentation-only; tests not rerun.

## 2026-08-11 23:34 IST | ingest | Demo-day 16 Aug dataset + Auth cast

- Timestamptz `v_latest_eta` migration applied; demo SQL applied; 12 Driver Auth users created (same shared password, no resets).
- Live smoke: RAVI feasible options PASS; NOSLOT escalation PASS; IDOR 403 PASS.
- Updated [[database]], [[current-state]], [[handoff]], DEMO_DAY_READINESS. Sprint 3 exit gate still open (load proof / stale matrix / escalation UI).

## 2026-08-11 23:25 IST | implementation | Appointment cancel and confirm lifecycle

- Added authorized, idempotent, row-locked cancel and confirm transitions in `backend/app/scheduling/allocation.py`, with audit and post-commit authoritative rereads.
- Mounted shipment/appointment-scoped REST routes; enabled Driver LangChain cancellation and kept confirmation ops/admin-only.
- Updated [[implementation]], [[current-state]], [[database]], [[testing]], [[handoff]], `docs/API.md`, the Living sprint plan, and root CHANGELOG.
- Verification: focused scheduling tests 10 passed; full backend 50 passed, 1 live integration skipped; OpenAPI paths, compile, IDE lints, and `git diff --check` PASS. Live database/API/chat smoke not run.

## 2026-08-11 23:16 IST | ingest | Chat UI restore from Redis

- Active conversation pointer + `GET /api/v1/chat/history`; DriverHome hydrates on login within 24h TTL.
- Slot question guidance: shipment-feasible `find_feasible_slots`, not unrestricted facility open-slot dump (FDE §7.1 / §9.1).
- Updated [[handoff]], [[ai-system]], root CHANGELOG. Verification: redis unit 7 passed; frontend lint PASS.

## 2026-08-11 22:54 IST | query | Demo-day readiness from FDE PDF

- Mapped PDF §§8 / 11.2 / 12.1–12.2 to current SHOW/ANSWER/PARTIAL/NOT YET capabilities.
- Added `docs/DEMO_DAY_READINESS.md`; updated [[handoff]] and root CHANGELOG. No code change.

## 2026-08-11 22:42 IST | ingest | Redis rolling summaries (ERICA-style)

- Added `:summaries` key + `maybe_summarize_history` to `ConversationMemory`; wired into `run_assistant`.
- Policy: summarize oldest 5 when raw ≥ 10; inject ≤5 summaries + ≤5 raw turns; 24h TTL; non-authoritative.
- Updated [[ai-system]], constraints allowed_uses, prompts/tool copy. Verification: backend tests 47 passed.

## 2026-08-11 22:34 IST | query | SetuHaul vs ERICA Redis memory

- Compared SetuHaul `ConversationMemory` (Upstash REST, scoped keys, 24h TTL, session JSON, degrade path) to `erica_vscode_core` (`redis` URL, thread-only LPUSH + LLM summarize).
- Updated [[ai-system]] Memory layers. No code change; Sprint 3 unchanged. Verification: source read only.

## 2026-08-11 22:35 IST | ingest | Facility contacts column + Ravi sync proof

- Fixed `driver_reads.get_facility_details` column `role_title` → `contact_role`.
- Live proof: MCP SQL FAC-JAI-01 contacts; browser Ravi session `/driver` context SHP1017; chat tool `get_facility_details` 200.
- Added `docs/DEMO_DRIVER_CHAT_SCRIPT.md`; deferred AgentCore/CloudWatch in master plan §12.
- Updated [[database]], [[handoff]], root CHANGELOG. Verification: unit 45 passed; passwords not logged.

## 2026-08-11 22:27 IST | query | FDE PDF system message + stress tests

- Re-extracted all 20 pages of `docs/SetuHaul_FDE_Challenge.pdf`.
- Compiled AI must/must-not, cannot-guess, human-control, and §11.2 stress scenarios into [[ai-system]].
- No code change; Sprint 3 status unchanged. Verification: document analysis only.

## 2026-08-10 23:21 IST | query | Login preflight hang

- Stuck `/api/v1/auth/me` preflight was caused by dead/crashed backend venv, not duplicate frontend auth calls.
- Backend restarted healthy; CORS OPTIONS verified. Sprint status unchanged.

## 2026-08-10 23:12 IST | ingest | POC roster moved to local share file

- Team share file: gitignored `POC_TEAM_ACCOUNTS.local.md` (all 8 roles × 14 users + 3 shared passwords).
- Cleared POC credentials from `.env` / `.env.local`. No passwords in wiki.
- Sprint status unchanged.

## 2026-08-10 23:05 IST | ingest | Full Auth inventory + remove reset script

- Created Auth for USR102–USR106 using existing role-shared `.env.local` passwords; live `auth.users=14` all mapped.
- Expanded ops portal/permissions for deferred roles; deleted `docs/scripts/create_poc_auth_users.py`.
- Updated [[database]] full inventory table. No passwords in wiki.
- Verification: password-grant PASS; execution_context unit tests PASS (6). Sprint 3 status unchanged.

## 2026-08-10 22:39 IST | configuration | Local Gemini key and Flash Latest default

- Stored the provided Gemini key in gitignored `.env.local`, selected `LLM_PROVIDER=gemini`, and set `LLM_MODEL=gemini-flash-latest`.
- Updated the backend Gemini default and active docs from `gemini-2.5-flash` to `gemini-flash-latest` after Google REST reported older pinned Flash models unavailable to this key.
- Verification: LLM factory unit tests PASS, direct Gemini REST smoke PASS. LangChain live invoke timed out locally and remains a restart/recheck item.

## 2026-08-10 22:31 IST | implementation | Authenticated ops dashboard polish

- Refined `frontend/src/features/operator/OpsHomes.tsx`, `frontend/src/layouts/ProtectedLayout.tsx`, and `frontend/src/App.css` for a more enterprise-looking authenticated ops dashboard and profile menu.
- Preserved the POC boundary: no maps, no user management, no scheduling mutation controls, and no invented operations data.
- Verification: frontend lint/build PASS; local frontend and backend readiness checks PASS; live Arvind Nair login/profile/ops summary/exceptions API checks PASS. Headless screenshot capture was attempted but blocked by local command policy.

## 2026-08-10 22:20 IST | correction | Redis-only memory architecture

- Owner clarified that SetuHaul has no project Memory MCP; Redis is the only memory layer and is limited to application conversation/session memory.
- Removed Memory MCP server configs and preserved Cursor Supabase MCP only.
- Updated active agent instructions, tooling docs, and wiki topic pages to stop requiring Memory MCP startup/writeback or degraded-memory handoff notes.
- Verification: documentation/config change only; app tests not run.

## 2026-08-10 22:11 IST | operations | Extra POC Auth accounts and Redis env

- Created six additional live Supabase Auth POC accounts for real-name Driver, Ops, and Admin personas, mapped them to `public.users.auth_user_id`, and verified password-grant login status `200` for each.
- Added gitignored local env files for backend/frontend execution. Root env includes Supabase + Upstash Redis REST configuration; frontend env contains only browser-safe Vite values.
- Verified Upstash Redis through REST (`/ping`, short-lived set/get). `redis-cli` is unavailable in this sandbox. No app tests run because this was credential/data setup only.

## 2026-08-10 18:29 IST | ingest | Role-specific login hero assets

- Added generated Driver portal hero `frontend/src/assets/setuhaul-driver-eta-hero.png` and updated `LoginForm` so Driver and Ops login screens use distinct imagery, copy, and metrics.
- Ops continues to use `frontend/src/assets/setuhaul-dock-command-hero.png`; Driver now focuses on ETA/exception reporting and single-truck context.
- Verification: `npm run lint` PASS; `npm run build` PASS; screenshots `tmp/ui-polish/driver-login-role-hero.png` and `tmp/ui-polish/ops-login-role-hero.png` visually spot-checked. Sprint status unchanged.

## 2026-08-10 18:22 IST | ingest | Generated login hero asset

- Replaced the weak abstract/fake-map login right panel with a generated dock-command hero image saved as `frontend/src/assets/setuhaul-dock-command-hero.png`.
- Updated `LoginForm` and `App.css` so the image carries the visual while overlay copy and classroom-scale metrics remain readable.
- Verification: `npm run lint` PASS; `npm run build` PASS; `tmp/ui-polish/driver-login-dock-hero.png` visually spot-checked. Sprint status unchanged.

## 2026-08-10 18:12 IST | ingest | Frontend UI polish

- Implemented UI polish in `frontend/src/App.css`, `frontend/src/index.css`, `frontend/src/features/auth/LoginForm.tsx`, `frontend/src/features/driver/DriverHome.tsx`, `frontend/src/features/operator/OpsHomes.tsx`, and `frontend/src/layouts/ProtectedLayout.tsx`.
- Scope stayed within the two-portal POC: login aesthetics, structured driver context, ops metric/status presentation, typography, shell layout, and hook warning cleanup; no booking, map/GPS, user-management, or scheduling mutation behavior added.
- Verification: `npm run lint` PASS; `npm run build` PASS; unauthenticated login screenshots captured and visually checked. Authenticated screens not live-smoked because local env files are absent and pasted secrets were not persisted.

## 2026-08-10 17:51 IST | query | FDE challenge PDF analysis

- Analyzed `docs/SetuHaul_FDE_Challenge.pdf` across all 20 pages; rendered representative pages 1, 10, and 18.
- Durable conclusion: the brief leaves implementation choices open, but FDE challenge readiness requires Sprint 3 evidence for deterministic feasibility, allocation semantics, same-slot competition, stale option handling, idempotent retries, and no-feasible-slot escalation.
- Updated [[implementation]], [[current-state]], [[handoff]], and CHANGELOG. Checked-in context is authoritative.

## 2026-08-08 13:45 IST | ingest | Rename web â†’ frontend

- Directory `web/` renamed to `frontend/`; CI/README/package updated; build PASS. Updated [[handoff]], CHANGELOG, master-plan scaffold wording.

## 2026-08-08 13:35 IST | ingest | Root GET / health ping

- FastAPI `GET /` returns alive JSON; README Quick start note. Smoke PASS. Updated [[handoff]], CHANGELOG.

## 2026-08-07 20:25 IST | verify | Gemini live PASS

- Google key saved gitignored; `gemini-2.5-flash` invoke PASS via `ChatGoogleGenerativeAI`. All three providers live-verified. Updated [[handoff]], [[current-state]], CHANGELOG, Memory.

## 2026-08-07 20:20 IST | verify | OpenAI+OpenRouter smoke; Gemini native class

- Live invoke: OpenAI PASS, OpenRouter PASS; Gemini key was OpenAI-shaped (FAIL). Switched Gemini to `ChatGoogleGenerativeAI`. Unit 20 passed. Updated [[handoff]], [[ai-system]], [[current-state]], CHANGELOG, Memory.

## 2026-08-07 20:00 IST | ingest | README + multi-provider LLM

- README Quick start for Sprint 1â€“2 POC; demo login emails + password env-var names (passwords OOB).
- `assistant/llm.py` ChatOpenAI factory (`auto` OpenAI â†’ OpenRouter â†’ Gemini); settings + `.env.example` extended.
- Unit 18 passed; OpenRouter/Gemini live smoke pending keys. Updated [[handoff]], [[current-state]], [[ai-system]], CHANGELOG, Memory MCP.

## 2026-08-07 19:35 IST | ingest | Sprint 2 exit gate COMPLETE

- Struck Sprint 2 Living Â§7 build + exit gate with API `DEMO_PATH_PASS` and browser localhost:5173 evidence.
- Fixed write path (`UPDATE_ETA`, `DELAY`, JWT leeway, tzdata, env BOM, stale uvicorn). Credentials remain gitignored; rotation recommended in [[handoff]].
- Updated [[handoff]], [[current-state]], [[implementation]], [[ai-system]], master plan, root CHANGELOG, Memory MCP.

## 2026-08-07 19:26 IST | verify | Sprint 2 Living re-baseline

- Inspected dirty-tree Sprint 2 code + live smoke. Struck only verified Â§7 items (repair/ETA distinction; services+tools; role allowlists; bind_tools loop).
- Blocker recorded: confirmed ETA write 500 on audit `ETA_UPDATE` vs `UPDATE_ETA`.
- Living â†’ Sprint 2 ACTIVE / IN PROGRESS; exit gate open. Updated [[handoff]], [[current-state]], [[implementation]], master plan, root CHANGELOG, Memory MCP.

## 2026-08-07 18:36 IST | ingest | .gitignore noise reduction

- Ignored `graphify-out/` and common generated/OS/editor artifacts. Secrets/tmp/venv unchanged. Updated [[handoff]], root CHANGELOG.

## 2026-08-07 17:55 IST | verify | Sprint 1 exit gate COMPLETE

- Exit gate struck: Admin browser global RO, wrong-portal, API 401/IDOR/scope, no mutations, CORS both origins, baseline a11y, minimal CI.
- Deferred honestly: deep SQLAlchemy repos; fuller a11y/responsive; CI DB/Docker expansion.
- Living status â†’ Sprint 2 ACTIVE. Updated [[handoff]], [[current-state]], [[implementation]], [[testing]], [[contradictions]], root CHANGELOG, master plan, Memory MCP.

## 2026-08-07 17:04 IST | ingest | Living sprint catch-up + cross-IDE writeback

- Master plan Living status re-baselined; Sprint 1 mostly complete (exit open); Sprint 2 TODO.
- Root `AGENTS.md` + Claude/Gemini/Cursor/wiki pointers require Living status at startup and checklist strikethrough on durable progress.
- Memory MCP synced (16:53 smoke + policy). Updated [[handoff]], [[implementation]], [[current-state]], root CHANGELOG.

## 2026-08-07 16:53 IST | verify | Browser smoke PASS + pooler fix

- Two-portal UI smoke on `localhost:5173`: Driver login â†’ chat shell â†’ logout; Ops login â†’ dashboard.
- Fixed Vite import path, asyncpg `statement_cache_size=0` for PgBouncer, Stitch chat/ops skeleton polish.
- Screenshots: `tmp/poc-screenshots/01`â€“`04` (gitignored). Updated [[current-state]], [[handoff]], [[testing]], root CHANGELOG, Memory MCP.

## 2026-08-07 16:35 IST | verify | /health/ready + /auth/me PASS

- User saved `.env`; `DATABASE_URL` + service role non-empty. Backend ready; DB ping true.
- `/api/v1/auth/me` PASS for USR001 / USR101 / USR999 with expected roles and scopes.
- Updated [[current-state]], [[handoff]], root CHANGELOG, Memory MCP. Browser smoke still TODO.

## 2026-08-07 16:32 IST | verify | Auth/me blocked â€” empty DATABASE_URL on disk

- Proceed: `/health/live` PASS; `/health/ready` degraded; on-disk `DATABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` empty (anon present).
- Settings now loads `.env.local` paths. `/auth/me` not re-proved.
- Updated [[handoff]], root CHANGELOG, Memory MCP.

## 2026-08-07 16:45 IST | verify | Anon keys + JWT/JWKS; auth/me DB blocked

- MCP `get_publishable_keys` / `get_project_url`: anon populated locally (gitignored). Service role + `DATABASE_URL` **not** available via MCP.
- Password-grant + `JwtVerifier` JWKS **PASS** (Driver/Operator/Admin). `/health/live` PASS; `/auth/me` FAIL 503 `DB_UNAVAILABLE`.
- Updated [[current-state]], [[handoff]], [[implementation]], [[testing]], master plan Sprint 1 evidence notes, root CHANGELOG, Memory MCP.
- Sprint 1 exit gate still open pending `DATABASE_URL` + browser smoke.

## 2026-08-07 16:25 IST | ingest | Auth mapped + two-portal UI

- Live MCP after re-auth: created 3 Auth users + identities; mapped USR001/USR101/USR999 `auth_user_id`. Proof: `auth.users=3`, all mapped.
- Web consolidated to `/driver/login` + `/ops/login`; Operator+Admin share `/ops`. AI lock: `ChatOpenAI` + `bind_tools` + manual loop.
- Passwords only in gitignored `.env.local` (OOB). Anon keys still empty â†’ `/auth/me` not run.
- Updated [[current-state]], [[contradictions]], [[handoff]], [[skills-and-mcp]], [[database]], root CHANGELOG, Memory MCP.
- Verification: MCP SQL proof + backend unit tests 4 passed; JWT e2e not run.

## 2026-08-07 16:20 IST | ingest | Two-portal UI code + Auth create blocked

- Consolidated `web/src` to `/driver/login` + `/ops/login` / `/driver` + `/ops`; Operator+Admin share ops shell; legacy aliases redirect. ADR 005 + master plan checklist updated.
- AI lock unchanged: `ChatOpenAI` + `bind_tools` + manual loop (ADR 011 / [[ai-system]]); no Erica.
- Auth: passwords in gitignored `.env.local`; create/map **not** completed â€” Supabase MCP `fetch failed` / connection timeout. Script loads `.env.local`.
- Updated [[current-state]], [[contradictions]], [[handoff]], [[skills-and-mcp]], root CHANGELOG, Memory MCP.
- Verification: backend unit tests 4 passed; Auth e2e / `/auth/me` not run.

## 2026-08-07 16:05 IST | scope | Two-portal POC + bind_tools reconcile

- Owner POC UI: `/driver/login` + `/ops/login`; shared ops dashboard; prefer Driver + Ops accounts.
- AI: restored `ChatOpenAI` + `bind_tools` + manual loop (ADR 011). Supersedes 16:00 no-`bind_tools` interrupt for this writeback.
- Complementary MCP diagnosis already in [[database]]: Cursor server id `project-0-Setuhaul-supabase` (not config key `supabase`); live counts + auth.users=0 re-proved ~15:55.
- Updated [[current-state]], [[implementation]], [[architecture]], [[ai-system]], [[contradictions]], [[handoff]], plans (master/design-review/branches), root CHANGELOG, Memory MCP.
- Scaffold three-login routes remain an open contradiction until code consolidates.
- Verification: docs + prior live MCP; app tests not run.

## 2026-08-07 16:00 IST | decision | ChatOpenAI LLM invoke only (no bind_tools)

- Owner interrupt: conversational LLM is `ChatPromptTemplate | ChatOpenAI` only; no `bind_tools` / agent loops; no private-project naming.
- Updated [[ai-system]], [[architecture]], [[handoff]], [[current-state]], [[contradictions]], [[index]], [[skills-and-mcp]], ADR 011, plans/docs.
- Sprint 1 scaffolds remain; Auth mapping still the blocker.

## 2026-08-07 15:55 IST | decision | ChatOpenAI+bind_tools lock + MCP re-proof

- Owner clarification: tools via `ChatOpenAI.bind_tools` + manual invoke loop; not create_agent. Upstash 24h non-authoritative memory from Sprint 2. Tool matrix ~18â€“25 / 26 named with sprint placement.
- [[ai-system]], [[architecture]], [[contradictions]], [[current-state]], [[handoff]], [[database]], [[skills-and-mcp]], [[index]] updated; Erica absent (already stripped).
- Live MCP `project-0-Setuhaul-supabase`: counts + auth_user_id + auth.users=0. Earlier failures = wrong server name / not loaded.
- Verification: MCP SQL; app tests not run.

## 2026-08-07 15:45 IST | ingest | Live DB + Sprint 1 scaffold + ChatOpenAI lock

- Live MCP inspection recorded in [[database]]; [[current-state]] and [[handoff]] refreshed.
- [[ai-system]] / [[architecture]] / [[contradictions]]: LLM invoke is `ChatPromptTemplate | ChatOpenAI`; no agent loops; no private-project naming.
- Sprint 1 scaffolds in repo; Auth mapping still blocked (`auth.users` empty).
- Verification: MCP SQL; unit tests 4 passed; e2e not run.

## 2026-08-07 15:30 IST | blocker | Supabase MCP still not loaded (follow-up)

- Re-checked `.cursor/mcp.json` (project_ref only; no secrets printed) and MCP catalog via pattern `supabase|memory`, full catalog, and server=`supabase`.
- Catalog still: `cursor-ide-browser`, `user-memory` only. Supabase not found â€” cannot `mcp_auth`. Live counts/Auth/persona verification still blocked.
- Repo-only: baseline `users` lacks `auth_user_id`; seed defines USR001/USR101/USR999. Sprint 1 ordered next steps refreshed in [[handoff]].
- Updated [[handoff]], [[current-state]], [[skills-and-mcp]], [[database]], root CHANGELOG; Memory MCP observations appended.
- Verification: MCP enumeration only. Tests not run.

## 2026-08-07 15:23 IST | blocker | Supabase MCP not loaded in Cursor

- Inspected `.cursor/mcp.json`: Supabase remote MCP URL present with project_ref `kujffzgqjmqphkmrbawy`.
- Agent MCP catalog lacked `supabase`; live project/table/auth inspection stopped per policy.
- Memory MCP: empty SetuHaul search; project entity write succeeded.
- Repo-only: baseline lacks `auth_user_id`; seed personas USR001/USR101/USR999; ADR 005 Admin global RO; untracked `web/` scaffold in dirty tree.
- Updated [[handoff]], [[current-state]], [[skills-and-mcp]], root CHANGELOG.

## 2026-08-07 15:50 IST | scope | Owner two-portal POC contract

- Owner vision locked for Sprint 1â€“2 UI: `/driver/login` â†’ chat/profile/logout; `/ops/login` â†’ one read-only ops dashboard for Operator (facility) and Admin (global RO). Prefer Driver + Ops Auth accounts; three seed personas may share two entries.
- Explicitly out of POC: maps, GPS, user management, booking mutations. Scheduling mutations remain Sprint 3.
- AI locks aligned: `ChatOpenAI` + `bind_tools` + manual loop; no `create_agent` / `AgentExecutor`; Upstash 24h in Sprint 2; Sprint 1 = auth + shells + reads.
- Updated master plan, POC design review, full-stack/business-analysis/solution-architecture branches, [[current-state]], [[implementation]], [[architecture]], [[contradictions]], [[handoff]], root CHANGELOG.
- Scaffold still exposes three login routes â€” recorded as open contradiction until code consolidates.
- Verification: docs only; tests not run. Memory MCP write attempted.

## 2026-08-07 14:50 IST | scope | Three-persona Sprint 1-2 POC contract

- Triple-checked the POC through solution-architecture, full-stack, AI-engineering, and business-analysis reviews and verified the seed contains Driver (`ROL001`), Operations Executive (`ROL002`), and Admin (`ROL008`) identities.
- Expanded Sprint 1-2 to distinct Driver/Operator/Admin portal entry screens sharing one Supabase Auth implementation; added server-authoritative routing, safe profile/logout, read-only Operator schedule/dock/rule views, and a read-only Admin overview.
- Added the boundary that all Sprint 1-2 schedule/dock/slot/constraint visibility is observational and timestamped. Feasibility, booking, rescheduling, cancellation, confirmation, and appointment/capacity mutation remain absent until Sprint 3.
- Added an atomic ETA/exception command, explicit role/scope and failure-state checks, and an end-to-end Driver-to-Operator-to-Admin team-demo gate.
- Verification: 58 actionable open plan items, 3 verified foundation-presence items, zero stale two-account/early-scheduling plan references, and zero disallowed orchestration-framework references. Tests not run because no runtime/schema changed and application code does not yet exist.
- Memory MCP write was retried and failed with the known relative-path `ENOENT`; checked-in context is synchronized and replay remains pending path repair.

## 2026-08-07 14:37 IST | rebaseline | Living implementation sprint tracker

- Re-analyzed the implementation state against checked-in code, the master plan, database artifacts, and supplied designs.
- Converted all three sprint build sections and exit gates into evidence-based checklists: Sprint 1 is active/incomplete; Sprints 2-3 remain gated TODOs; no sprint is struck through.
- Preserved post-Sprint-3 scope as explicit unchecked `TODO (DEFERRED)` entries and recorded the distinction between present foundation files and executed/verified implementation.
- Found four Stitch design sets and retained set 2 as the current POC decision; corrected the final outdated supplied-design orchestration reference to LangChain.
- Verification: 0 application files, 2 database SQL test files, 4 design sets, 51 actionable open plan items, 3 checked foundation-presence items, and 0 remaining non-LangChain orchestration-framework mentions. Tests not run because no application runtime exists and no database behavior changed.
- Memory MCP degradation: search was callable, but write failed with `ENOENT` because the relative storage path resolved under npm's temporary package directory. Checked-in context is complete; memory replay is pending configuration repair.

## 2026-08-07 14:30 IST | configure | Cursor and Antigravity MCP compatibility

- Verified current native discovery rules: Cursor uses `.cursor/mcp.json`; Google Antigravity uses workspace `.agents/mcp_config.json` and reads `GEMINI.md`/`AGENTS.md`.
- Added both Memory MCP files with the same pinned server and ignored shared JSONL path used by Claude, Codex, and Gemini CLI.
- Result: instruction and Memory MCP configuration now cover Anti-Gravity, Cursor, Codex, Claude, and Gemini CLI.

## 2026-08-07 14:20 IST | rules | Per-prompt atomic context synchronization

- Updated root and native client rules so every prompt runs a context-sync check.
- Durable prompts must update affected wiki pages, [[handoff]], this log, root `CHANGELOG.md`, and Memory MCP before the final response.
- Pure no-op/read-only conversation does not create empty history entries.
- Memory MCP was not callable inside the current already-running Codex session; recorded the required next-session retry in [[handoff]].

## 2026-08-07 14:00 IST | ingest | LLMWiki, Memory MCP, and Graphify initialization

- Compiled initial project knowledge from `PROJECT.md`, plans, docs, Supabase artifacts, and the Slicematic LLMWiki pattern.
- Added [[index]], [[current-state]], [[source-map]], [[contradictions]], system topic pages, [[handoff]], and this operation log.
- Added cross-client Memory MCP configuration with ignored local persistence.
- Completed the initial Graphify build from 13 canonical wiki documents: 26 nodes, 41 edges, 4 labeled communities, plus HTML/report/JSON and incremental manifest.
## 2026-08-10 18:55 IST | implementation | Sprint 3 constraints registry

- Added `backend/app/scheduling/constraints.json` as the single editable scheduling policy source for authority boundaries, feasibility hard constraints, deterministic ranking, lifecycle semantics, option invalidation, no-slot escalation, Redis boundaries, and write-safety rules.
- Added strict Pydantic loader `backend/app/scheduling/constraints.py` and unit coverage in `backend/tests/unit/test_scheduling_constraints.py`.
- Updated [[current-state]], [[implementation]], [[ai-system]], [[testing]], [[handoff]], root CHANGELOG, and the Living sprint scoreboard. Sprint 3 is now IN PROGRESS; no exit gate or allocator item was struck because deterministic feasibility/allocation is not complete.
- Verification: backend unit tests PASS, 25 passed, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit` from `backend/`; `git diff --check` PASS with only an existing CRLF warning on `CHANGELOG.md`.
-
## 2026-08-10 19:12 IST | implementation | LangChain feasible slot search

- Added `backend/app/scheduling/feasibility.py` for deterministic Sprint 3 slot feasibility/ranking using checked constraints, latest ETA, facility hours, slot/dock compatibility, active appointments, dock events, and no-slot escalation payloads.
- Added `backend/app/api/v1/routers/scheduling.py` with `GET /api/v1/shipments/{shipment_id}/slots/feasible`, wired the router into `backend/app/main.py`, and registered `find_feasible_slots` in `backend/app/assistant/tools.py`.
- Updated the assistant prompt so slot search is enabled as informational non-reserved options while booking/hold/reschedule/cancel/confirm mutations remain disabled.
- Verification: backend unit tests PASS, 30 passed, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit` from `backend/`; `git diff --check` PASS with line-ending warnings only. Live authenticated smoke not run because local env files are absent and pasted secrets were not persisted.
-
## 2026-08-10 19:31 IST | implementation | Transactional request_slot flow

- Added `backend/app/scheduling/allocation.py` with `request_slot`: idempotency lookup/store, driver ownership checks, row locks, slot revalidation, `PENDING_CONFIRMATION` insert, `BOOK_APPOINTMENT` audit, commit, and authoritative reread.
- Extended `backend/app/api/v1/routers/scheduling.py` with `POST /api/v1/shipments/{shipment_id}/slots/{slot_id}/request` requiring `Idempotency-Key`, and registered the Driver LangChain `request_slot` tool.
- Updated the assistant prompt so exact selected slot requests are enabled as pending confirmation only; reschedule/cancel/confirm remain disabled.
- Verification: backend unit tests PASS, 33 passed, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit`; FastAPI import smoke PASS; `git diff --check` PASS with line-ending warnings only. Live authenticated smoke and concurrency tests not run because local env files are absent and pasted secrets were not persisted.
-
## 2026-08-10 19:38 IST | implementation | Appointment request status read path

- Added `get_appointment_request_status` in `backend/app/scheduling/allocation.py` for scope-safe, read-only status checks after `request_slot`.
- Exposed `GET /api/v1/shipments/{shipment_id}/appointment-request/status` and registered the Driver LangChain `get_appointment_request_status` tool.
- Updated the assistant prompt so pending confirmation remains distinct from confirmed booking, and updated [[current-state]], [[implementation]], [[ai-system]], [[testing]], [[handoff]], root CHANGELOG, and the Living sprint scoreboard.
- Verification: backend unit tests PASS, 35 passed, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit`; FastAPI import smoke PASS; `git diff --check` PASS with line-ending warnings only. Live authenticated smoke and concurrency tests not run because local env files are absent and pasted secrets were not persisted.
-
## 2026-08-10 19:50 IST | implementation | Allocation race conflict mapping

- Hardened `request_slot` so PostgreSQL allocation partial unique violations for `ux_active_appointment_per_slot` and `ux_current_active_appointment_per_shipment` return `SLOT_CONFLICT_REFRESH_REQUIRED` instead of raw database errors.
- Updated the scheduling route to return HTTP 409 for conflict-refresh outcomes while preserving refreshed options in the response body.
- Added unit coverage for allocation unique-constraint translation and updated [[current-state]], [[implementation]], [[database]], [[testing]], [[handoff]], root CHANGELOG, and the Living sprint scoreboard.
- Verification: backend unit tests PASS, 38 passed, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit`; FastAPI import smoke PASS; `git diff --check` PASS with line-ending warnings only. Live authenticated smoke and real parallel contention tests not run because local env files are absent and pasted secrets were not persisted.
-
## 2026-08-10 19:59 IST | implementation | Redis conversation memory tool

- Added `ConversationMemory.snapshot(...)` for bounded current-thread Upstash Redis session/history snapshots with explicit 24-hour TTL, non-authoritative status, and degraded-state reporting.
- Registered Driver LangChain `get_conversation_memory` and passed the existing assistant memory instance into the tool builder.
- Updated the assistant prompt to use Redis only for chat/session continuity and to verify operational facts through PostgreSQL-backed tools.
- Updated [[current-state]], [[ai-system]], [[testing]], [[handoff]], root CHANGELOG, and the Living sprint scoreboard.
- Verification: backend unit tests PASS, 40 passed, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit`; FastAPI import smoke PASS; `git diff --check` PASS with line-ending warnings only. Live Upstash smoke not run because Redis env values are not configured/persisted.
## 2026-08-10 20:16 IST | implementation | Deterministic slot ranking algorithm

- Upgraded `find_feasible_slots` from earliest feasible slot ordering to explicit deterministic scoring.
- Added `rank_score` and `ranking_factors` for priority, lateness, wait after ETA, fit slack, dock match, operational disruption score, and stable shipment/slot tie-breaker.
- Added editable `ranking_policy.priority_scores` and `ranking_policy.score_weights` to `backend/app/scheduling/constraints.json` so ranking behavior can change without scattering constants across services.
- Updated scheduling feasibility/constraints unit coverage and synchronized [[current-state]], [[implementation]], [[testing]], [[handoff]], root CHANGELOG, and the Living sprint scoreboard.
- Verification: backend unit tests PASS, 41 passed, via `$env:PYTHONPATH=(Get-Location).Path; uv --system-certs run --with pytest pytest tests\unit`; FastAPI import smoke PASS; `git diff --check` PASS with line-ending warnings only. Live authenticated smoke and real parallel contention tests not run.
## 2026-08-10 20:23 IST | verification | Live Supabase database catalog inspection

- Connected to the live Supabase PostgreSQL database through direct read-only asyncpg and inspected public schema metadata plus seeded operational counts.
- Verified PostgreSQL 17.6, `auth.users=3`, public schema 23 tables and 4 views.
- Verified key seeded counts: `shipments=21`, `appointment_slots=106`, `appointments=22`, `driver_exceptions=12`, `eta_updates=14`, `docks=9`, `facilities=2`, `users=10`, `roles=8`, and `idempotency_requests=2`.
- Confirmed Sprint 3-relevant live state: open/blocked slot inventory, current confirmed and pending-confirmation appointments, active exceptions, and allocation guard indexes `ux_active_appointment_per_slot` + `ux_current_active_appointment_per_shipment`.
- No schema, data, grant, RLS, or migration changes were made. Supabase changelog checked; Data API public-table auto-exposure change does not affect this direct Postgres inspection.
## 2026-08-10 20:35 IST | verification | Live same-slot concurrency proof

- Added `backend/tests/integration/test_live_scheduling_concurrency.py`, guarded by `DATABASE_URL` and `SETUHAUL_RUN_LIVE_DB_TESTS=1`.
- The test creates temporary live Supabase `CODX` shipment/slot fixtures, runs two independent async sessions through the real `request_slot` service against the same slot, and verifies exactly one `SLOT_REQUESTED` winner plus one `SLOT_CONFLICT_REFRESH_REQUIRED` loser.
- Verified one active appointment on the contested slot, one booking audit row, two idempotency rows, and zero leftover `CODX` idempotency/appointment/slot/shipment rows after cleanup.
- Added `pytest-asyncio` to `backend/pyproject.toml` and kept generated `backend/uv.lock` for reproducible async integration testing.
- Verification: default backend tests PASS, 41 passed and 1 live integration skipped; explicit live concurrency proof PASS, 1 passed. Supabase changelog checked; no schema/RLS/Data API change made.

## 2026-08-10 22:46 IST | planning | Implementation master plan reconciliation

- Refreshed the Living sprint scoreboard in `plans/implementation-master-plan.md` from the beginning through current UI/auth/Redis/Gemini/scheduling work.
- Struck completed evidence for role-specific login visuals, authenticated Ops dashboard polish, Redis-only application memory clarification, current Gemini default configuration, individual POC Auth users, deterministic feasibility/ranking, fresh non-reserved options, and live two-client same-slot proof.
- Kept Sprint 3 IN PROGRESS and the exit gate open for authenticated scheduling/chat smoke, lifecycle transitions, stale-choice invalidation, no-slot escalation, ops takeover views, broader load proof, enterprise auth hardening, and formal Playwright/CI.
- Updated [[implementation]], [[current-state]], [[handoff]], and root CHANGELOG. No Memory MCP sync is expected; SetuHaul durable context is checked-in docs/source, and Redis is runtime app memory only.
- Verification: documentation-only reconciliation; no application tests run. `git diff --check` run after writeback.

## 2026-08-10 23:01 IST | implementation | Redis session-scoped chat memory

- Added `/api/v1/chat` `session_id` support and returned the normalized session id from `run_assistant`.
- Updated `ConversationMemory` so Upstash Redis history, structured session state, snapshots, and duplicate `client_message_id` checks are scoped by authenticated `user_id`, normalized browser `session_id`, and `thread_id`.
- Updated the Driver UI to create a stable `sessionStorage` session id and send it with chat turns; the id is not an authorization source.
- Updated [[ai-system]], [[implementation]], [[current-state]], [[testing]], [[handoff]], the Living sprint scoreboard, and root CHANGELOG.
- Verification: focused backend tests PASS, 18 passed; full backend tests PASS, 43 passed and 1 skipped; frontend lint PASS; frontend build PASS; `git diff --check` run after writeback.

## 2026-08-10 23:24 IST | implementation | Driver chat env and greeting fix

- Hardened `backend/app/core/settings.py` so `.env` and `.env.local` load from source-relative backend/repo paths, fixing the local chat `No LLM API key configured` state after backend restart.
- Changed Driver chat welcome rendering so it uses the verified live driver context name instead of a stale initial auth-profile name.
- Updated [[current-state]], [[implementation]], [[testing]], [[handoff]], the Living sprint scoreboard, and root CHANGELOG.
- Verification: env smoke PASS from both repo root and `backend/` with `ready_llm=True`/Gemini model visible and no secrets printed; focused backend tests PASS, 14 passed; full backend tests PASS, 43 passed and 1 skipped; frontend lint PASS; frontend build PASS. Stale port-8000 backend process was stopped; local policy blocked hidden restart, so manual backend restart is required before browser retest.

## 2026-08-12 00:00 IST | implementation | Sprint 3 lifecycle, stale recommendation, and escalation queue

- Added the `EXPIRED` appointment migration and an RLS-protected backend-only `escalation_queue`; widened constrained audit actions for lifecycle evidence.
- Added `REC-` feasibility fingerprints, 24-hour ephemeral Redis stale markers after ETA commits, lifecycle services/routes/tools, and operations escalation/dock/queue takeover reads with a minimal dashboard list.
- Updated [[database]], [[implementation]], [[current-state]], [[testing]], [[handoff]], and the Living sprint scoreboard.
- Verification: focused lifecycle/stale/escalation units PASS (29), `python -m compileall app` PASS, frontend lint/build PASS. Migration was not applied; live migration/API/E2E proof remains TODO.

## 2026-08-22 15:07 IST | planning | GitHub tracking scaffold for the New-Solution-New-Design overhaul

- Installed `gh` CLI, adopted the AI Collaboration Field Guide as an `AGENTS.md` section (mapped against existing files, 6 new rules added), and authored `docs/New-Solution-New-Design/APPLY-TO-EXISTING/EXECUTION-PLAN.md` from the six COMPARISON-*.md passes.
- Created 18 labels, 7 milestones (M0-M6), 33 epics, and 7 M0 sub-issues on `anshulghogre4/setuhaul`; linked M0's two multi-item epics to their real sub-issue numbers; fixed one MSYS path-mangled issue title (#11).
- Updated [[handoff]] and root CHANGELOG. No master-plan Living sprint status change — tracking infrastructure only, no live-codebase progress this turn. No live code read or changed.
- Verification: `gh issue list --state all` confirms 39 issues (#6-#44) across 7 milestones, no gaps/duplicates, title fix confirmed.

## 2026-08-22 15:21 IST | planning | GitHub-tracker-check and UPIV added as standing rules

- Confirmed via grep that neither rule existed despite UPIV being the originally-requested framework: added `AGENTS.md` startup step 7 (check `gh issue list --state all` before planning overhaul-related work) and a new `### UPIV` subsection mapping Understand/Plan/Implement/Verify onto existing rules.
- Cross-referenced both from `EXECUTION-PLAN.md` §5, kept in sync rather than reworded separately.
- Updated [[handoff]] and root CHANGELOG. No master-plan Living sprint status change.
- Verification: grep-confirmed wording present in both files.

## 2026-08-22 15:34 IST | planning | Seventh comparison pass (deployment/infra) and M7

- Added `.claude/agents/deployment-engineer.md` and ran it; produced `COMPARISON-deployment.md`. Confirmed AgentCore and ECS both live in `us-east-1` against a designed `ap-south-1` (AgentCore confirmed at the live-ARN layer), ECS on `amd64` not ARM64, Sentry entirely absent, Vercel confirmed as the live (non-gap) frontend host.
- New original finding: Upstash Redis is live-wired to `us-east-1`; the `ap-south-1` instance `TECH_STACK.md` "confirmed" is almost certainly the orphaned, superseded instance per `wiki/handoff.md`'s 2026-08-17 migration record.
- Added M7 to `EXECUTION-PLAN.md` (E7.1 region-correctness migration, blocked on #31/#32; E7.2 Sentry, independent). Created GitHub milestone M7 and issues #45-#46.
- Updated [[handoff]] and root CHANGELOG. No master-plan Living sprint status change.
- Verification: `gh issue list --state all` confirms 8 milestones, 41 issues (#6-#46), no gaps/duplicates/mangled titles.

## 2026-08-22 15:38 IST | planning | Full-repo file inventory: loadtests/ epic fix, two blockers surfaced

- Full `git ls-files` inventory across every top-level directory (not just backend/frontend/supabase) found `loadtests/` (real Locust suites overlapping M6/E6.1, never cited) and `designs/` (dead Stitch exports, confirmed superseded, not a gap). Updated issue #42 (E6.1) to cite and extend `loadtests/locust_slot_contention.py` rather than rebuild from scratch.
- Surfaced two real blockers, not yet fixed, both needing an owner decision: `docs/New-Solution-New-Design/` + `.claude/` + `.mcp.json` are entirely untracked by git (74+ files, no backup beyond the working directory); `backend/app/assistant/observability.py`/`run_assistant.py` carry real uncommitted work (the 2026-08-20 LangSmith upgrade #32 already cites as "landed") that overlaps M0/E0.2's target file.
- No commit made — requires explicit owner request per standing instruction.
- Updated [[handoff]] and root CHANGELOG.

## 2026-08-22 17:49 IST | implementation | M0 implemented (E0.1, E0.2, E0.3) — uncommitted, pending review

- Two parallel specialist-agent dispatches (fullstack-engineer, latency-engineer) implemented all of milestone M0 (#6-#15) on disjoint files; every change independently re-verified against the real diff and a real test run (124 passed, 0 failed) before being trusted.
- Notable root-cause finding: #10's actual bug was in `ExecutionContext.is_admin` itself (conflated write-authority with global read-reach), not the three routers the issue named — fixed at the property plus every real consumer.
- Real deploy consequence flagged, not yet acted on: the live ECS/AgentCore stacks will refuse to boot after this deploys unless `ALLOW_REGION_MISMATCH=true` is set first or the region migration (#45/E7.1) happens first.
- E0.3 honestly records two current limitations (TTFT = whole turn, no LLM network/inference split) rather than fabricating numbers neither installed provider SDK actually exposes.
- Updated [[handoff]] and root CHANGELOG. No master-plan Living sprint status change (different, already-complete scope). Nothing committed or pushed yet.

## 2026-08-23 05:34 IST | planning | Decision: ap-south-1 confirmed, migration not escape hatch

- Owner confirmed `ap-south-1` as the production region target; the path is the E7.1 migration (#45), not `ALLOW_REGION_MISMATCH=true` as a standing workaround. E7.1 remains blocked on #31/#32 (M4) per its existing dependency note — this decision doesn't change that ordering, just confirms the destination.
- Updated [[handoff]]. No code/infra changed.
