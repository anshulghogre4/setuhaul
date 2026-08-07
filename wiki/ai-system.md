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
- **Not** `create_agent`, `AgentExecutor`, or `create_react_agent`. Explicit: **`bind_tools` + manual invoke loop ≠ `create_agent`**.
- Tools never contain SQL; PostgreSQL is SoT; LLM never invents operational facts.
- Do not name private reference projects in SetuHaul docs.

## Tool count and sprint placement

Matrix in `plans/implementation-master-plan.md` §5.2: **26** named capabilities; planning band **~18–25** (owner ~18–20 ≈ role-scoped / POC-facing).

| Sprint | Placement |
|---|---|
| Sprint 1 | Observational **services/REST** for ~9 read capabilities. No chat mount; no model tool registration; **Upstash not required**. |
| Sprint 2 | Register POC tools via `bind_tools`; add ETA/exception tools; **Upstash required** (24h non-authoritative conversation/session memory). |
| Sprint 3 | Register scheduling/search/report tools (~12 more). |

Two Sprint 2 rows (`record_eta_update`, `create_or_update_exception`) are internal—not direct model registration. Infra (history, audit, authz, idempotency, redaction) is not model-selectable.

## Memory layers

- **Application memory:** Upstash Redis conversation history/session context with a **24-hour TTL**, non-authoritative. PostgreSQL refreshes business facts. Sprint 1 does not need Upstash; Sprint 2 does.
- **Coding-agent memory:** project Memory MCP knowledge graph in ignored `.agent-memory/memory.jsonl`.
- **Repository memory:** checked-in LLMWiki, changelog, plans, and source files.

LangSmith is the planned observability system for prompt/tool traces and later evaluation. Trace payloads must be sanitized.

Evidence: `plans/branches/ai-engineering.md`, `plans/implementation-master-plan.md` §5.2 / Sprint 2, `docs/adrs/SPRINT1_ADRS.md` ADR 011.

Related: [[architecture]], [[skills-and-mcp]], [[testing]], [[implementation]].
