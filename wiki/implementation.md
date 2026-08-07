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
3. Deterministic feasibility and concurrency-safe allocation. **TODO** — starts after Sprint 2 gate.

Do not build maps, user management, booking mutations, or the full chatbot tool catalogue before the active exit gate passes.

The plan is the **cross-IDE Living sprint scoreboard**. Every Cursor/Claude/Codex/Gemini session must report Living status at startup and strike verified checklist items on durable writeback (root `AGENTS.md`).

**Living status (2026-08-07 19:35 IST):** Sprint 1 **COMPLETE**. Sprint 2 **COMPLETE**. Sprint 3 **TODO** (active next).

Immediate action: begin Sprint 3 feasibility/ranking/concurrent allocation when the owner starts that slice.

Related: [[current-state]], [[architecture]], [[testing]], [[ai-system]].
