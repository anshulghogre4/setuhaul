---
title: SetuHaul AI System
type: topic
status: compiled
scope: ai
last_verified: 2026-08-07
---

# AI system

Locked runtime (owner clarification 2026-08-07; supersedes a brief conflicting “no bind_tools” interrupt):

- LangChain **`ChatOpenAI`** with **`bind_tools(...)`** on a curated, role-scoped tool list.
- Custom bounded `run_assistant` loop: `model.invoke` → on `tool_calls`, run typed Pydantic tool functions that call FastAPI application services → append `ToolMessage`s → final text.
- Provider factory `backend/app/assistant/llm.py` (2026-08-07): `LLM_PROVIDER=auto|openai|openrouter|gemini`. **`auto`** uses first configured key **OpenAI → OpenRouter → Gemini**. OpenAI/OpenRouter use `ChatOpenAI` (OpenRouter via OpenAI-compatible base URL). **Gemini uses `ChatGoogleGenerativeAI`** (`langchain-google-genai`) with a Google AI Studio / Gemini API key — not an OpenAI `sk-`/`sk-proj-` token. Default Gemini model: **`gemini-2.5-flash`** (`gemini-2.0-flash` shut down 2026-06-01). Live invoke PASS for all three providers 2026-08-07 20:25 IST.
- **Not** `create_agent`, `AgentExecutor`, or `create_react_agent`. Explicit: **`bind_tools` + manual invoke loop ≠ `create_agent`**.
- Tools never contain SQL; PostgreSQL is SoT; LLM never invents operational facts.
- Do not name private reference projects in SetuHaul docs.
- Sprint 3 scheduling policy constraints now live in `backend/app/scheduling/constraints.json` and are loaded by deterministic backend code. LangChain tools must call services that apply this policy; the model must not interpret the JSON as permission to mutate data or invent slot facts.
- Driver LangChain tools now include `find_feasible_slots` (2026-08-10), which calls the deterministic feasibility service and returns non-reserved options or escalation. Appointment mutation intents still use `scheduling_capability_disabled` until transaction-safe allocation services exist.
- Driver LangChain tools now also include `request_slot` (2026-08-10), which can request an exact selected `slot_id` and create `PENDING_CONFIRMATION` through deterministic backend code. It does not confirm appointments; reschedule/cancel/confirm intents remain disabled until their services exist.
- Driver LangChain tools now also include `get_appointment_request_status` (2026-08-10), which reads the authoritative appointment request lifecycle after `request_slot` and reports pending/confirmed/closed/no-request states without mutating appointments.
- Driver LangChain tools now also include `get_conversation_memory` (2026-08-10), which reads bounded current-thread Upstash Redis chat/session context. It is infrastructure memory only, 24-hour TTL, non-authoritative, and never replaces PostgreSQL-backed operational tools.

## Tool count and sprint placement

Matrix in `plans/implementation-master-plan.md` §5.2: **26** named capabilities; planning band **~18–25** (owner ~18–20 ≈ role-scoped / POC-facing).

| Sprint | Placement |
|---|---|
| Sprint 1 | Observational **services/REST** for ~9 read capabilities. No chat mount; no model tool registration; **Upstash not required**. |
| Sprint 2 | Register POC tools via `bind_tools`; add ETA/exception tools; **Upstash required** (24h non-authoritative conversation/session memory). **COMPLETE** 2026-08-07 19:35 IST. |
| Sprint 3 | `find_feasible_slots`, `request_slot`, and `get_appointment_request_status` registered 2026-08-10. `get_conversation_memory` registered as infrastructure memory context. Remaining scheduling/search/report tools require deterministic services before registration. |

Two Sprint 2 rows (`record_eta_update`, `create_or_update_exception`) are internal—not direct model registration. Infra (history, audit, authz, idempotency, redaction) is not model-selectable.

## Memory layers

- **Application memory:** Upstash Redis conversation history/session context with a **24-hour TTL**, non-authoritative. PostgreSQL refreshes business facts. Implemented in `ConversationMemory` (`backend/app/services/redis_memory.py`); `get_conversation_memory` exposes a bounded current-thread snapshot to the Driver LangChain tool loop.
- **Coding-agent memory:** project Memory MCP knowledge graph in ignored `.agent-memory/memory.jsonl`.
- **Repository memory:** checked-in LLMWiki, changelog, plans, and source files.

LangSmith tracing is enabled when `LANGSMITH_TRACING=true` and the API key is set (gitignored env). Trace payloads must be sanitized.

## Sprint 2 verified runtime (2026-08-07 19:35 IST)

- Package: `backend/app/assistant/` (`run_assistant.py`, `tools.py`, `prompts.py`).
- Routes: `POST /api/v1/chat`, `POST /api/v1/shipments/{id}/eta-updates`.
- Live evidence: API demo tool_calls + `DEMO_PATH_PASS`; browser chat tools observed (`get_current_user_context`, `list_active_shipments`, `get_current_appointment`, `get_shipment_details`); scheduling denial via `scheduling_capability_disabled`.

Evidence: `plans/branches/ai-engineering.md`, `plans/implementation-master-plan.md` §5.2 / Sprint 2, `docs/adrs/SPRINT1_ADRS.md` ADR 011.

Related: [[architecture]], [[skills-and-mcp]], [[testing]], [[implementation]].
