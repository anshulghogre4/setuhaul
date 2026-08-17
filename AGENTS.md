# SetuHaul repository instructions

These instructions apply to Codex, Claude Code, Gemini CLI/Google Antigravity, Cursor, and any other coding agent working in this repository.

## Required startup sequence

Before planning, editing, or running a material command:

1. Read `wiki/index.md`, `wiki/handoff.md`, and `wiki/current-state.md`.
2. Read `PROJECT.md` for product scope and `plans/README.md` plus `plans/implementation-master-plan.md` for delivery order.
3. **Report Living sprint status** from `plans/implementation-master-plan.md` (Sprint 1 vs Sprint 2 vs Sprint 3 table + whether the active exit gate is open) before starting new work.
4. Read `wiki/contradictions.md` and the task-specific wiki/source documents selected through `wiki/source-map.md`.
5. Inspect `git status --short`. Preserve teammate changes and do not overwrite unrelated work.
6. Check available skills and MCP tools. Invoke a relevant skill when its trigger matches; do not claim a skill or MCP was used when unavailable.

If two documents disagree, do not silently choose one. Prefer verified code/migrations for current behavior, the master plan for intended implementation order, and record the contradiction in `docs/HANDOFF.md` before proceeding.

## Delivery rules

- Complete sprint exit gates in order. Do not broaden the build beyond the active vertical slice.
- React 19 is the frontend. Do not create an Angular variant unless the owner explicitly changes ADR 012.
- Reuse the supplied Stitch resources; do not redesign the product without explicit approval.
- FastAPI routers stay thin. Business rules belong in services; persistence belongs in repositories.
- The LLM orchestrates typed tools and never executes SQL or directly mutates business tables.
- PostgreSQL is the business source of truth. Upstash Redis holds bounded, non-authoritative conversation/session state with a 24-hour TTL.
- Supabase Auth identity and permissions are derived server-side from verified tokens. Ignore client-supplied ownership or scope identifiers.
- Never invent shipment, ETA, dock, appointment, capacity, or operational data.
- Never commit secrets, tokens, shared demo credentials, service-role keys, or MCP credentials.
- Database changes require the Supabase and Postgres best-practice skills, a migration, parity review, and relevant database tests.
- Material behavior changes require proportional tests and documentation updates.
- Any AgentCore Runtime deploy (`agentcore.cmd deploy`, first deploy or day-2) must be immediately preceded by `python docs/scripts/stage_agentcore_codezip.py`. `agentcore.cmd deploy` packages `agentcore/codezip/app/`, a separate copied snapshot of `backend/app/`, not the live source — editing `backend/app/**` alone does nothing for AgentCore until that snapshot is refreshed. Skipping this silently ships stale code while `agentcore.cmd deploy`/`status` still report success (confirmed live 2026-08-17: a prompt bug fix was "redeployed" successfully but kept reproducing because the codezip copy was never re-staged). No exceptions, no "it's a small change so skip it."

## Mandatory writeback and changelog

At the end of **every user prompt**, run the context-sync check before responding. If the prompt changed files, implementation state, a decision, requirement, blocker, verification result, or any other durable project context, the agent must finish the same turn by updating:

1. `CHANGELOG.md` with a timestamped entry describing the outcome, affected files, verification, and agent/surface when known.
2. Affected `wiki/*.md` topic pages, `wiki/handoff.md`, and append-only `wiki/log.md` under the rules in `wiki/AGENTS.md`.
3. Any affected authored source-of-truth document or plan.
5. **`plans/implementation-master-plan.md` Living sprint status** whenever implementation progress changed: refresh the status table, strike through newly verified checklist items with dated evidence (`- [x] ~~â€¦~~`), leave unverified work as `TODO`, and never strike a sprint exit gate without full gate evidence.

If a prompt is purely conversational/read-only and creates no durable project context, do not create noisy empty entries. State remains unchanged and no writeback is required. A prompt that performs research, reaches a decision, diagnoses a blocker, or verifies project state is durable even when it changes no application code and therefore requires writeback.

The writeback targets are one atomic context-sync operation. Do not update only the changelog, and do not skip the master-plan checklist when sprint progress changed. Redis is application runtime memory only; do not use or wait for a project Memory MCP.

Documentation-only changes still require a changelog entry when they alter team workflow, architecture, requirements, or implementation decisions. Trivial formatting-only edits may be grouped into the nearest material entry. Never rewrite or delete prior changelog history; correct mistakes with a new entry.

Use timestamps in `YYYY-MM-DD HH:mm IST` format. Do not mark tests as passing unless they were run; use `not run` with the reason instead. Do not strike plan items from inference aloneâ€”require objective verification evidence.

## Skill routing

Use the smallest relevant set and follow each skill's own instructions:

- System structure or ADR work: `software-architecture-design`.
- Any Supabase task: `supabase`; load `supabase-postgres-best-practices` before changing PostgreSQL schema, SQL, RLS, indexes, functions, or migrations.
- React UI creation/refinement: `frontend-design` or `interface-design` as appropriate; use `web-design-guidelines` for accessibility/UX audits.
- Browser/E2E verification: `playwright`.
- Codebase knowledge questions or graph refreshes: `graphify` when available.
- Current OpenAI/Codex guidance: `openai-docs`.
- Skill discovery: `find-skills`; verify source reputation and quality before installation.

Skills guide work; they do not override the master plan, security boundaries, database invariants, or explicit user instructions. Record materially influential skill usage in the changelog entry.

## MCP and memory rules

- MCP configuration is per client and may be absent. Check availability before use and degrade gracefully.
- Use MCP for live external documentation/resources or authorized operational inspection, not as a replacement for checked-in project truth.
- Upstash Redis is the only memory layer for SetuHaul application conversation/session context. It is implemented and tested in code with a 24-hour TTL and is not the business source of truth.
- Do not use a project Memory MCP for SetuHaul context. Durable project context lives in checked-in docs, changelog, plans, tests, and source files.
- LangSmith MCP is deferred until observability work needs trace, run, dataset, experiment, or billing inspection. Application tracing remains part of the planned LangSmith integration.
- Graphify artifacts, when present, are an indexâ€”not authoritative truth. Reconcile graph results with source files.
- Never place credentials in `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, MCP JSON, examples, logs, or the changelog. Use environment variables or the client's secure credential mechanism.

See `docs/AI_TOOLING.md` for client-specific setup and the approved MCP adoption sequence.

## Verification and handoff

Before declaring completion:

- Review the diff and confirm unrelated teammate work is intact.
- Run the narrowest relevant checks, then broader checks in proportion to risk.
- Report exactly what was and was not verified.
- Complete the mandatory writeback above (including Living sprint status when progress changed).
- Do not send the final response for a durable prompt until changelog, wiki, handoff, and master plan (when progress changed) are synchronized.
