---
title: SetuHaul Implementation Flow
type: topic
status: compiled
scope: delivery
last_verified: 2026-08-07
---

# Implementation

The master plan defines three gated vertical sprints. Owner POC UI for Sprint 1–2 is a **simple two-portal** contract:

| Entry | After login |
|---|---|
| `/driver/login` | Chat (+ light context/quick actions), profile, logout. Chat mounts in Sprint 2 (`DriverHome` → `POST /api/v1/chat`). |
| `/ops/login` | One read-only ops **dashboard** (shipments/exceptions/schedule/docks/rules). Operator facility-scoped and Admin global RO share this shell; JWT decides scope. Logout. |

Prefer shared Driver + Ops Auth accounts. Seeded Operator/Admin may both use `/ops/login`. No maps, GPS, user management, or booking mutations in the POC. Scheduling mutations are Sprint 3 only.

Sprint goals:

1. Trusted walking skeleton: two entry screens, verified role routing, driver profile/logout shell, current-driver context, read-only ops dashboard, and CI baseline. **No chat mount.** **COMPLETE** (exit gate 2026-08-07 17:55 IST).
2. Conversational exception and ETA/status coordination POC: `ChatOpenAI` + `bind_tools` + manual bounded invoke loop, clarification, one atomic typed ETA/exception command path, Redis 24h conversation state, LangSmith traces, and populated read-only Ops dashboard of stored schedule/dock/rule facts. **COMPLETE** (exit gate 2026-08-07 19:35 IST).
3. Deterministic feasibility and concurrency-safe allocation. **IN PROGRESS** — started after Sprint 2 gate; exit gate remains open.

Do not build maps, user management, booking mutations, or the full chatbot tool catalogue before the active exit gate passes.

The plan is the **cross-IDE Living sprint scoreboard**. Every Cursor/Claude/Codex/Gemini session must report Living status at startup and strike verified checklist items on durable writeback (root `AGENTS.md`).

**Living status (2026-08-07 19:35 IST):** Sprint 1 **COMPLETE**. Sprint 2 **COMPLETE**. Sprint 3 **TODO** (active next).

**Living status refresh (2026-08-10 18:55 IST):** Sprint 3 moved to **IN PROGRESS** after adding `backend/app/scheduling/constraints.json`, the typed constraints loader, and unit coverage. No Sprint 3 exit gate item was completed or struck; feasibility engine, mutation tools/routes, and concurrency proof remain TODO.

## Challenge brief analysis

Verified against `docs/SetuHaul_FDE_Challenge.pdf` on 2026-08-10: the classroom brief defines the core problem as driver exception chat plus simultaneous scarce dock-capacity coordination. It intentionally does not prescribe agent framework, tool list, storage design, concurrency mechanism, allocation algorithm, or deployment pattern.

The brief's expected demonstration requires: driver delay clarification, later-slot comparison, several requests against the same facility schedule, at least two requests competing for the same capacity, stale/disappearing option handling, and at least one no-feasible-slot escalation. This confirms the master plan's sequencing: Sprint 1-2 POC is valid as an internal ETA/exception/read-model proof, but FDE challenge readiness depends on Sprint 3 feasibility, allocation semantics, idempotent concurrency, conflict recovery, and escalation evidence.

## UI polish

On 2026-08-10, the React frontend was aesthetically tightened without expanding POC scope: the login screens gained role-specific generated hero assets (`frontend/src/assets/setuhaul-driver-eta-hero.png` for Driver and `frontend/src/assets/setuhaul-dock-command-hero.png` for Ops) plus security badges; the driver assistant gained a console header and structured context fields instead of raw JSON; the ops dashboard gained accented metric cards and proportional status bars; the app shell and typography were aligned with the selected Stitch design set. This did not add booking, map/GPS, user-management, or scheduling mutation behavior.

Immediate action: build the pure feasibility engine against the constraints registry and PostgreSQL read models.

## Sprint 3 constraints registry

On 2026-08-10, Sprint 3 started with an editable deterministic constraints registry at `backend/app/scheduling/constraints.json`. The file centralizes the project constraints that must shape implementation: PostgreSQL authority, LangChain-only typed orchestration, Redis as 24-hour non-authoritative state, no invented operational data, feasibility hard constraints, deterministic ranking, appointment lifecycle semantics, option invalidation triggers, no-slot escalation payloads, and required write-safety controls.

The registry is loaded through `backend/app/scheduling/constraints.py` using strict Pydantic models. This is a foundation for the pure feasibility engine; it does not yet expose scheduling mutation routes or claim appointment capacity.

Related: [[current-state]], [[architecture]], [[testing]], [[ai-system]].
