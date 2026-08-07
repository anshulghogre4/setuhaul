# AI coding tools, skills, MCP, and memory

This document defines how the team keeps Codex, Claude Code, Gemini CLI/Google Antigravity, Cursor, and future agents aligned. It does not contain credentials.

## Native instruction files

| Client | Native project file | SetuHaul use |
| --- | --- | --- |
| Codex | `AGENTS.md` | Canonical repository policy. Nested `AGENTS.md` or `AGENTS.override.md` may narrow rules by subtree. |
| Claude Code | `CLAUDE.md` | Imports root `AGENTS.md` and adds only Claude-specific guidance. |
| Gemini CLI / Google Antigravity | `GEMINI.md` | Imports root `AGENTS.md` and adds only Gemini/Antigravity-specific guidance. |
| Cursor | `.cursor/rules/setuhaul.mdc` | Always-applied adapter pointing back to the same canonical policy. |

The correct filenames are uppercase `CLAUDE.md`, `GEMINI.md`, and `AGENTS.md`. Empty placeholder files are intentionally avoided because Codex skips empty instruction files and all clients need actionable context.

## Shared lifecycle

1. Start: read the canonical files listed in `AGENTS.md`, inspect git status, and identify the active sprint gate.
2. Work: use relevant skills, preserve teammate changes, and keep external/live data separate from checked-in truth.
3. Verify: run checks proportional to risk and record failures or skipped tests honestly.
4. Write back: append `CHANGELOG.md`, refresh `docs/HANDOFF.md`, and update affected source-of-truth documents.

This is repository memory. Runtime conversation memory belongs to the SetuHaul application and uses bounded Upstash Redis state; the two must not be mixed.

## Required skill baseline

The repository currently locks project-local architecture and Supabase skills in `skills-lock.json`. Team environments should also provide equivalent capabilities for:

- React/frontend implementation and interface craft.
- Accessibility and web-interface review.
- Playwright browser and E2E verification.
- Graphify codebase indexing/querying.
- Skill discovery and source-quality review.
- Current provider documentation lookup when implementing provider-specific behavior.

Agents must inspect what is actually installed rather than assuming identical global skill catalogs. Install or update a skill only with team approval, pin its source through `skills-lock.json` when project-local reproducibility matters, and review third-party skill instructions before trusting them.

## Graphify

Use Graphify when the repository has enough implementation content to benefit from a knowledge graph.

- Initial build: the canonical LLMWiki graph is generated in `graphify-out/`; expand it after the first meaningful vertical slice.
- Incremental use: refresh after material code/document changes when Graphify is available.
- Query discipline: graph answers are navigation aids; verify claims against source files.
- MCP mode is optional. If enabled, expose the checked-in/project graph to agents through the client-specific MCP configuration and keep generated caches out of reviews unless intentionally versioned.

## MCP adoption sequence

### 1. Documentation and local project context

Prefer official documentation tools/connectors already available in each client. Add MCP only when it provides live data that repository files cannot.

LangChain can consume MCP tools through `langchain-mcp-adapters`, but this is an application architecture choice, not required for coding-agent documentation access. Do not add it to runtime dependencies until a concrete tool integration is accepted in the implementation plan.

### 2. Upstash

Upstash's official guidance prefers its agent skill and `@upstash/cli` for most management workflows; its MCP server is useful for cross-client resource inspection and debugging.

When adopted:

- Configure it per developer/client, using environment variables or secure client storage.
- Start read-only/diagnostic where possible; require explicit approval for provisioning, deletion, flushes, backups, or credential changes.
- Never store account email/API keys in this repository.
- Keep application Redis keys namespaced by environment and tenant/user/thread; enforce TTL and avoid business truth in Redis.

### 3. LangSmith

Add the official LangSmith MCP when observability work begins and the team needs agents to inspect traces, runs, prompts, datasets, experiments, or usage.

- Keep `LANGSMITH_API_KEY`, workspace ID, and endpoint outside the repository.
- Default agents to read/diagnose. Dataset, prompt, or experiment mutations require explicit task scope.
- Redact secrets and sensitive operational payloads before tracing.
- The MCP assists investigation; application instrumentation still uses the approved LangSmith tracing integration.

### 4. Graphify MCP

Enable only after a useful graph exists. Point each client at the absolute local `graphify-out/graph.json`; do not commit machine-specific paths.

## Client verification

After cloning or changing instructions:

- Codex: start a new session and ask it to list loaded instruction sources.
- Claude Code: use its memory/instruction inspection command and confirm `CLAUDE.md` imports `AGENTS.md`.
- Gemini CLI/Antigravity: run `/memory show` or `/memory list`; use `/memory refresh` after edits.
- Cursor: inspect active project rules and confirm `.cursor/rules/setuhaul.mdc` is always applied.
- Cursor MCP: run `cursor-agent mcp list` and confirm `memory` from `.cursor/mcp.json` is connected.
- Google Antigravity MCP: open `/mcp` or MCP Servers and confirm `memory` from `.agents/mcp_config.json` is connected.
- Confirm no MCP secrets appear in `git diff`, logs, screenshots, or changelog entries.

## References

- Codex `AGENTS.md`: <https://learn.chatgpt.com/docs/agent-configuration/agents-md.md>
- Claude Code memory: <https://docs.anthropic.com/en/docs/claude-code/memory>
- Gemini context files: <https://google-gemini.github.io/gemini-cli/docs/cli/gemini-md.html>
- LangChain MCP adapters: <https://docs.langchain.com/oss/python/langchain/mcp>
- LangSmith MCP server: <https://docs.langchain.com/langsmith/langsmith-mcp-server>
- Upstash MCP: <https://upstash.com/docs/agent-resources/mcp>
