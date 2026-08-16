---
title: SetuHaul AI System
type: topic
status: compiled
scope: ai
last_verified: 2026-08-16
---

# AI system

## System message (from FDE challenge brief)

`docs/SetuHaul_FDE_Challenge.pdf` does **not** prescribe a literal prompt string. Pages 6–10 and 14 define the AI role; pages 17–19 define stress/demo proof. Runtime prompt lives in `backend/app/assistant/prompts.py` (`SYSTEM_PROMPT`); `docs/PROMPTS.md` is the broader authored library.

**AI must (p8–9):** understand messy multi-turn driver text; ask only for missing/ambiguous info; keep thread context; map intent to tools/services; explain options/constraints/status simply; continue the same thread later.

**AI must not decide (p9 §6.3):** same-capacity promises to two drivers; vehicle/dock physical compatibility; scarce-capacity priority when rules conflict; whether a booking committed in SoT; safety/legal/penalty/commercial exceptions.

**Cannot be guessed (p7–8):** which shipment; whether delay minutes equal ETA shift; latest ETA; gate arrival; feasible slots; whether a slot is still available under concurrency; whether warehouse confirmed (proposed ≠ committed).

**Human control (p14 §9.3):** no-feasible-slot → escalate, never invent; contradictory/regulated/emergency → manual takeover.

**Required stress scenarios (p17 §11.2)** that the *system* (deterministic services + DB), not the prompt alone, must survive: 10 drivers / 3–4 slots; mixed early/late/unloading/ETA-not-arrived; two drivers same option in seconds; capacity cut after options shown; cancellation frees slot mid-conversation; duplicate messages; multi-shipment disambiguation; 90-min repair ≠ 90-min ETA; later higher-priority load; no same-day feasible slot; warehouse reply vs stored schedule conflict.

**Success (p19):** not “chatbot answered” — exception → feasible, current, clearly communicated plan with **zero conflict for another driver**.

Locked runtime (owner clarification 2026-08-07; supersedes a brief conflicting “no bind_tools” interrupt):

- LangChain **`ChatOpenAI`** with **`bind_tools(...)`** on a curated, role-scoped tool list.
- Custom bounded `run_assistant` loop: `model.invoke` → on `tool_calls`, run typed Pydantic tool functions that call FastAPI application services → append `ToolMessage`s → final text.
- Provider factory `backend/app/assistant/llm.py` (updated 2026-08-10): `LLM_PROVIDER=auto|openai|openrouter|gemini`. **`auto`** uses first configured key **OpenAI → OpenRouter → Gemini**. OpenAI/OpenRouter use `ChatOpenAI` (OpenRouter via OpenAI-compatible base URL). **Gemini uses `ChatGoogleGenerativeAI`** (`langchain-google-genai`) with a Google AI Studio / Gemini API key — not an OpenAI `sk-`/`sk-proj-` token. Default Gemini model: **`gemini-flash-latest`** because the provided key rejected older pinned Flash models. Direct Gemini REST smoke PASS for `gemini-flash-latest` on 2026-08-10.
- **Not** `create_agent`, `AgentExecutor`, or `create_react_agent`. Explicit: **`bind_tools` + manual invoke loop ≠ `create_agent`**.
- Tools never contain SQL; PostgreSQL is SoT; LLM never invents operational facts.
- Do not name private reference projects in SetuHaul docs.
- Sprint 3 scheduling policy constraints now live in `backend/app/scheduling/constraints.json` and are loaded by deterministic backend code. LangChain tools must call services that apply this policy; the model must not interpret the JSON as permission to mutate data or invent slot facts.
- Driver LangChain tools now include `find_feasible_slots` (2026-08-10), which calls the deterministic feasibility service and returns non-reserved options or escalation. **2026-08-12:** tool coroutines must accept expanded kwargs (`**kwargs` + Pydantic `model_validate`); a single `args: Model` parameter caused runtime `unexpected keyword argument` TOOL_ERRORs for appointment/facility/slot tools. Chat responses expose tool `result`/`result_preview` for browser console inspection.

- Driver LangChain tools now also include `request_slot` (2026-08-10), which can request an exact selected `slot_id` and create `PENDING_CONFIRMATION` through deterministic backend code. It does not confirm appointments; warehouse confirm remains ops/admin REST.
- Driver LangChain tools now also include `get_appointment_request_status` (2026-08-10), which reads the authoritative appointment request lifecycle after `request_slot` and reports pending/confirmed/closed/no-request states without mutating appointments.
- Driver LangChain tools now also include `get_conversation_memory` (2026-08-10), which reads bounded Upstash Redis chat/session context scoped by authenticated user, browser session id, and thread id. It is infrastructure memory only, 24-hour TTL, non-authoritative, and never replaces PostgreSQL-backed operational tools.
- **Verified Driver allowlist (2026-08-16):** `build_driver_tools` in `backend/app/assistant/tools.py` registers **23** `StructuredTool`s (22 real + leftover `scheduling_capability_disabled` for driver confirmation). Sprint 3 mutations `cancel_appointment` / `reschedule_appointment` / `escalate_exception` are registered. Extra reads (2026-08-12): vehicle/carrier, gate/queue, facility rules, breakdown incident, dock alerts. Ops/Dispatch capabilities stay REST, not model-selectable.

## Driver tool catalog (model-selectable)

All tools are scoped by the verified JWT (`ExecutionContext`). The LLM never executes SQL. Ravi currently has **3 active shipments**, so any tool that can omit `shipment_id` may default to `SHP-D16-RACE-A` (newest `updated_at`) — name `SHP-D16-RAVI` in chat.

| # | Tool | Mutates? | What it does |
|---|---|---|---|
| 1 | `get_current_user_context` | No | Returns authenticated `user_id`, name, email, `role_name`, `driver_id`, `facility_id`, permissions. |
| 2 | `get_conversation_memory` | No | Bounded Upstash Redis history/session/summaries for this user+browser session+thread. 24h TTL, labeled non-authoritative. Never use as shipment/ETA/slot truth. |
| 3 | `get_driver_operational_context` | No | Full driver snapshot: all shipments, `active_shipments`, primary shipment, that primary’s appointment/ETA/facility. Rail uses this. |
| 4 | `list_active_shipments` | No | Subset of (3): non-`COMPLETED`/`CANCELLED` shipments only. |
| 5 | `get_shipment_details` | No | One in-scope shipment plus related driver/vehicle/carrier rows. 403 if another driver’s id. |
| 6 | `get_latest_eta` | No | Newest `eta_updates` row for that shipment. |
| 7 | `get_eta_history` | No | ETA history list for that shipment. |
| 8 | `get_current_appointment` | No | Current (`is_current=1`) appointment + slot/dock window, or none. |
| 9 | `get_facility_details` | No | Facility hours/grace + `facility_contacts`. Driver must have a shipment to that facility (`FAC-JAI-01` for Ravi). |
| 10 | `get_exception_status` | No | Driver’s `driver_exceptions` (optional shipment filter), newest first. |
| 11 | `get_vehicle_and_carrier_details` | No | Registration, capacity kg, reefer flag, carrier phone/email. If `shipment_id` omitted, uses first active (Ravi → RACE-A). |
| 12 | `get_gate_and_queue_status` | No | `facility_checkins`: gate-in, yard queue, dock-in, queue position. Null if not checked in. |
| 13 | `get_facility_rules_and_restrictions` | No | Active `facility_rules` + hours/grace/default unload. |
| 14 | `get_dock_maintenance_alerts` | No | Open `dock_status_events` (outage/maintenance) for a facility/dock. |
| 15 | `report_delay_or_update_eta` | Yes, after confirm | Delay/ETA write. Repair minutes are never an ETA (`REPAIR_IS_NOT_ETA`). First call returns `CONFIRMATION_REQUIRED` preview; only `confirmed=true` with matching timestamp writes (`PERSISTED`). Multiple actives → `CLARIFICATION_REQUIRED`. |
| 16 | `report_vehicle_breakdown_or_incident` | Yes | Inserts OPEN `driver_exceptions` (`INCIDENT_REPORTED`). Does **not** book a slot or change ETA. |
| 17 | `find_feasible_slots` | No booking; may persist NOSLOT escalation | Deterministic ranked options, labeled not reserved, with `REC-` id. Empty list → `NO_FEASIBLE_SLOTS` + durable `escalation_queue` (never invents a slot). |
| 18 | `request_slot` | Yes | Exact `slot_id` only. Revalidates in a transaction → `PENDING_CONFIRMATION` (`SLOT_REQUESTED`). Conflict → `SLOT_CONFLICT_REFRESH_REQUIRED`. Stale `REC-` → `SLOT_OPTIONS_STALE`. Existing current apt → `ACTIVE_APPOINTMENT_EXISTS`. Never warehouse-confirms. |
| 19 | `get_appointment_request_status` | No | Pending vs confirmed vs cancelled/rejected/none. Use after request: pending ≠ confirmed. |
| 20 | `cancel_appointment` | Yes | Driver cancels own current apt with reason → `CANCELLED`, slot freed. Needs exact `appointment_id`. |
| 21 | `reschedule_appointment` | Yes | Cancel-and-claim new slot in one flow → new `PENDING_CONFIRMATION`. Still not warehouse-confirmed. |
| 22 | `escalate_exception` | Yes | Writes durable ops `escalation_queue` (NOSLOT/human). Ops UI lists it. |
| 23 | `scheduling_capability_disabled` | No | Leftover stub: driver **cannot confirm**. Do not present as a product feature. |

Warehouse confirm / reject / expire are Ops REST only, not Driver tools.

## Tool count and sprint placement

Matrix in `plans/implementation-master-plan.md` §5.2: **26** named capabilities; planning band **~18–25** (owner ~18–20 ≈ role-scoped / POC-facing).

| Sprint | Placement |
|---|---|
| Sprint 1 | Observational **services/REST** for ~9 read capabilities. No chat mount; no model tool registration; **Upstash not required**. |
| Sprint 2 | Register POC tools via `bind_tools`; add ETA/exception tools; **Upstash required** (24h non-authoritative conversation/session memory). **COMPLETE** 2026-08-07 19:35 IST. |
| Sprint 3 | `find_feasible_slots`, `request_slot`, `get_appointment_request_status`, `cancel_appointment`, `reschedule_appointment`, `escalate_exception` registered. Extra operational reads registered 2026-08-12. Ops search/report remain REST. |

Two Sprint 2 rows (`record_eta_update`, `create_or_update_exception`) are internal—not direct model registration. Infra (history, audit, authz, idempotency, redaction) is not model-selectable.

## Memory layers

- **Application memory:** Upstash Redis conversation history/session context with a **24-hour TTL**, non-authoritative. PostgreSQL refreshes business facts. Implemented in `ConversationMemory` (`backend/app/services/redis_memory.py`); keys are normalized and scoped by verified `user_id`, client-provided browser `session_id`, and `thread_id`. `get_conversation_memory` exposes only that bounded scoped snapshot to the Driver LangChain tool loop.
- **UI restore (2026-08-11):** each chat turn also writes `setuhaul:chat:{user_id}:active` pointing at the latest `session_id`+`thread_id`. `GET /api/v1/chat/history` loads those Redis bubbles for the authenticated driver so the React chat panel can rehydrate after logout/login within the 24h TTL. This is still ephemeral Redis memory, not Supabase `chat_messages` SoT.
- **Client:** Upstash REST SDK (`upstash-redis`) with `UPSTASH_REDIS_REST_URL` + `UPSTASH_REDIS_REST_TOKEN`. Degrades gracefully when unset (`UPSTASH_NOT_CONFIGURED`); chat still works without Redis.
- **Key shapes:** `setuhaul:chat:{uid}:session:{sid}:thread:{tid}:history` (list, rpush+ltrim 40, expire 24h) and `...:state` (JSON string SET with TTL) for structured session context (`driver_id`, `last_intent`, pending ETA confirmation fields, etc.).
- **Uses today:** load recent raw turns + rolling summaries into the LLM message list; append user/assistant after each turn; when raw history reaches 10 messages, LLM-summarize the oldest 5 and keep them under `:summaries` (ERICA-style); duplicate `client_message_id` short-circuit; optional tool snapshot. **Not used for:** slot locks, booking authority.
- **Contrast with ERICA classroom core** (`14.1.1 .../erica_vscode_core`, analyzed 2026-08-11; summarization adopted 2026-08-11): ERICA uses standard `redis` + `REDIS_URL`, thread-only keys, LPUSH message dicts, and LLM rolling summaries. SetuHaul now also rolls summaries, but keeps Upstash REST, auth+session+thread keys, 24h TTL, structured session JSON, degrade-safe chat, and non-authoritative labeling.
- **Repository memory:** checked-in LLMWiki, changelog, plans, and source files.

There is no project Memory MCP workflow for SetuHaul. Redis is the only runtime memory service, and it is scoped to application chat/session continuity.

LangSmith tracing is enabled when `LANGSMITH_TRACING=true` and the API key is set (gitignored env). Trace payloads must be sanitized.

**CloudWatch vs LangSmith (2026-08-16 21:05 IST):** Portal Tracing Enable is the switch — do not set non-Runtime `OTEL_EXPORTER_*`. Runtime v3 has ADOT 0.19 + `UNIFIED_TRACES_DESTINATION_ENABLED=true`. Transaction Search ingests the **platform** span `AgentCore.Runtime.Invoke`. In-app LangChain/tool spans still fail ADOT `aws_auth_session` credential recursion. Use LangSmith `setuhaul-agentcore` / `setuhaul.chat` for the agent path. Timed hosted A2: chat **28.6s**, BFF `/auth/me` **2.9s**.

## Sprint 2 verified runtime (2026-08-07 19:35 IST)

- Package: `backend/app/assistant/` (`run_assistant.py`, `tools.py`, `prompts.py`).
- Routes: `POST /api/v1/chat`, `POST /api/v1/shipments/{id}/eta-updates`.
- Live evidence: API demo tool_calls + `DEMO_PATH_PASS`; browser chat tools observed (`get_current_user_context`, `list_active_shipments`, `get_current_appointment`, `get_shipment_details`); scheduling denial via `scheduling_capability_disabled`.

Evidence: `plans/branches/ai-engineering.md`, `plans/implementation-master-plan.md` §5.2 / Sprint 2, `docs/adrs/SPRINT1_ADRS.md` ADR 011.

Related: [[architecture]], [[skills-and-mcp]], [[testing]], [[implementation]].
