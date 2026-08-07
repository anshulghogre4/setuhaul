---
title: SetuHaul Skills and MCP
type: topic
status: authoritative
scope: agent-tooling
last_verified: 2026-08-07
---

# Skills and MCP

## Memory MCP

Configured project-wide through `.mcp.json` (Claude), `.cursor/mcp.json` (Cursor), `.codex/config.toml` (Codex), `.gemini/settings.json` (Gemini CLI), and `.agents/mcp_config.json` (Google Antigravity); Claude project approval is enabled by `.claude/settings.json`. All clients point to ignored `.agent-memory/memory.jsonl`.

The server is pinned to `@modelcontextprotocol/server-memory@2025.11.25`. Developers need Node/npm and must approve project MCP execution. Run client-specific MCP listing/status commands after cloning.

Cursor session 2026-08-07: Memory MCP (`user-memory`) ready. Product AI lock is `ChatOpenAI` + `bind_tools` + manual loop (not create_agent).

## Supabase MCP

`.cursor/mcp.json` declares a remote Supabase MCP scoped to project_ref `kujffzgqjmqphkmrbawy`. In the Cursor agent catalog the server id is **`project-0-Setuhaul-supabase`** (not bare `supabase`). Earlier agent failures used the config key `supabase` or hit a catalog where the server was not yet loaded/approved.

**Re-verified 2026-08-07 ~15:55 IST:** `execute_sql` + `list_migrations` succeeded (live counts, `auth_user_id`, `auth.users=0`). Prefer server id `project-0-Setuhaul-supabase`.

**Degraded mid-turn 2026-08-07 ~16:15 IST** (`fetch failed` / discovery error); **recovered via `mcp_auth`**. Auth create completed ~16:25 IST (`auth.users=3`, POC rows mapped).

## Graphify

`graphify-out/` contains a generated knowledge graph for the wiki corpus. Treat as an index—not authoritative truth. Reconcile with source files. May still contain stale “Gemini agent” labels until regenerated.

## Skills

Project-local locked skills are recorded in `skills-lock.json`. Root `AGENTS.md` defines routing for architecture, Supabase/Postgres, frontend/interface, accessibility, Playwright, Graphify, provider docs, and skill discovery.

Related: [[AGENTS]], [[ai-system]], [[source-map]], [[database]].
