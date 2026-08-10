# SetuHaul session handoff compatibility note

Last updated: 2026-08-10

The canonical LLMWiki handoff is now `wiki/handoff.md`. This file remains as a compatibility pointer for earlier documentation and should not receive independent session history.

## Current state

- `plans/implementation-master-plan.md` is the implementation source of truth. Sprint exit gates must be completed in order.
- Sprint 1 and Sprint 2 are complete. Sprint 3 is in progress with deterministic feasibility/ranking, `request_slot`, request status, session-scoped Redis memory tool context, live two-client same-slot proof, individual POC Auth users, and polished role-specific UI in place.
- Sprint 3 remains open for authenticated scheduling/chat smoke, reschedule/confirm/cancel/reject/expire, stale-choice invalidation, no-slot escalation, ops takeover views, broader load proof, enterprise auth hardening, and formal Playwright/CI.
- React 19 remains the decided frontend under ADR 012.
- Supabase PostgreSQL remains the business source of truth; Upstash Redis is non-authoritative 24-hour application conversation/session memory.

## Recent work

- 2026-08-10 22:46 IST: reconciled the master implementation plan from project beginning through latest work, striking completed items with evidence and listing remaining/deferred next work.
- 2026-08-10 23:01 IST: scoped Redis chat memory by authenticated user, browser session id, and thread id; backend/frontend tests passed.
- 2026-08-10 23:24 IST: fixed local Driver chat LLM env loading and stale welcome-name rendering; backend process on port 8000 was stopped, but hidden restart was blocked by local policy.
- 2026-08-10: completed UI polish, individual POC Auth account expansion, Redis-only architecture correction, Gemini default refresh, and Sprint 3 scheduling/concurrency groundwork.

## Decisions and cautions

- Do not duplicate policies independently across agent files; `AGENTS.md` is canonical and the native files import it.
- `docs/AGENTS.md` describes the runtime SetuHaul logistics assistant. Root `AGENTS.md` governs coding agents. Keep those responsibilities distinct.
- Upstash Redis application memory is non-authoritative and expires after 24 hours; PostgreSQL remains the business source of truth.
- SetuHaul does not use a project Memory MCP. Upstash/Redis diagnostics and LangSmith MCPs are optional developer tooling, not runtime dependencies, and must not receive committed credentials.
- Existing uncommitted planning and documentation changes predate this initialization work; preserve them.

## Verification

- Latest plan reconciliation was documentation-only; application tests were not run for that edit.
- See `wiki/handoff.md` and `wiki/current-state.md` for latest verified test evidence.

## Next safe action

Start/restart the backend, then follow section 13 of `plans/implementation-master-plan.md`: recheck live LangChain Gemini, live-smoke authenticated scheduling/chat paths, then implement appointment lifecycle transitions and escalation/takeover proof.
