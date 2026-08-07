# SetuHaul session handoff compatibility note

Last updated: 2026-08-07

The canonical LLMWiki handoff is now `wiki/handoff.md`. This file remains as a compatibility pointer for earlier documentation and should not receive independent session history.

## Current state

- Planning and database-baseline work exists; broad application implementation has not started.
- `plans/implementation-master-plan.md` is the implementation source of truth. Sprint exit gates must be completed in order.
- React 19 remains the decided frontend under ADR 012. The first build target is the Sprint 1 trusted walking skeleton, not the full dashboard or broad chatbot.
- Supabase migrations, seed data, and database tests already exist under `supabase/`.
- Root instruction adapters now cover Codex (`AGENTS.md`), Claude Code (`CLAUDE.md`), Gemini/Google Antigravity (`GEMINI.md`), and Cursor (`.cursor/rules/setuhaul.mdc`).

## Recent work

- Established a shared startup and writeback protocol based on the proven Slicematic FullStack pattern.
- Added an append-only project changelog and this handoff file.
- Documented skill routing and staged MCP adoption without committing credentials or activating infrastructure prematurely.

## Decisions and cautions

- Do not duplicate policies independently across agent files; `AGENTS.md` is canonical and the native files import it.
- `docs/AGENTS.md` describes the runtime SetuHaul logistics assistant. Root `AGENTS.md` governs coding agents. Keep those responsibilities distinct.
- Upstash application memory is non-authoritative and expires after 24 hours; PostgreSQL remains the business source of truth.
- Upstash and LangSmith MCPs are optional developer tooling. They are not runtime dependencies and must not receive committed credentials.
- Existing uncommitted planning and documentation changes predate this initialization work; preserve them.

## Verification

- Documentation-only initialization: application tests not run.
- Before the first build, verify each client reports the expected root instruction file and confirm local skills/MCP availability.

## Next safe action

Run the architecture decision session identified in section 13 of `plans/implementation-master-plan.md`, then implement Sprint 1's shared Supabase demo-login current-driver-context vertical slice.
