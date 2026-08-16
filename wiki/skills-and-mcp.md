---
title: SetuHaul Skills and MCP
type: topic
status: authoritative
scope: agent-tooling
last_verified: 2026-08-16
---

# Skills and MCP

## Redis memory boundary

SetuHaul does not use a project Memory MCP. Application conversation/session memory uses Upstash Redis only, implemented in `backend/app/services/redis_memory.py` and exposed to Driver LangChain through `get_conversation_memory`.

Redis memory rules:

- Store bounded current-thread chat/session context only.
- Use a 24-hour TTL.
- Treat Redis as non-authoritative and rebuildable.
- Refresh shipments, ETA, appointments, docks, facilities, and user permissions from PostgreSQL.
- Never store credentials or use Redis as durable project memory.

## Supabase MCP

`.cursor/mcp.json` declares a remote Supabase MCP scoped to project_ref `kujffzgqjmqphkmrbawy`. In the Cursor agent catalog the server id is **`project-0-Setuhaul-supabase`** (not bare `supabase`). Earlier agent failures used the config key `supabase` or hit a catalog where the server was not yet loaded/approved.

**Re-verified 2026-08-07 ~15:55 IST:** `execute_sql` + `list_migrations` succeeded (live counts, `auth_user_id`, `auth.users=0`). Prefer server id `project-0-Setuhaul-supabase`.

**Degraded mid-turn 2026-08-07 ~16:15 IST** (`fetch failed` / discovery error); **recovered via `mcp_auth`**. Auth create completed ~16:25 IST (`auth.users=3`, POC rows mapped).

## LangSmith MCP

Adopted 2026-08-16 for trace inspection (latency diagnosis). `.cursor/mcp.json` points at the hosted remote server `https://api.smith.langchain.com/mcp` (OAuth, no API key in git). Application traces remain `LANGSMITH_TRACING` → project `setuhaul-agentcore`, run name `setuhaul.chat`. MCP does not change chat latency.

## Graphify

`graphify-out/` contains a generated knowledge graph for the wiki corpus. Treat as an index—not authoritative truth. Reconcile with source files. May still contain stale “Gemini agent” labels until regenerated.

## Skills

Project-local locked skills are recorded in `skills-lock.json`. Root `AGENTS.md` defines routing for architecture, Supabase/Postgres, frontend/interface, accessibility, Playwright, Graphify, provider docs, and skill discovery.

Related: [[AGENTS]], [[ai-system]], [[source-map]], [[database]].
