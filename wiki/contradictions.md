---
title: SetuHaul Contradictions and Staleness Ledger
type: ledger
status: authoritative
scope: repository
last_updated: 2026-08-07
---

# Contradictions and staleness ledger

## Open

- `PROJECT.md` and older architecture documentation describe the intended product broadly; `plans/implementation-master-plan.md` narrows delivery to gated vertical slices. Agents must follow the master plan for implementation order.
- `docs/AGENTS.md` names the runtime logistics assistant, while root `AGENTS.md` governs coding agents. Do not conflate them. `docs/AGENTS.md` may still contain older Gemini/AgentExecutor wording in places; prefer ADR 011 + master plan §5.2 + [[ai-system]] for runtime shape until that doc is fully refreshed.
- The seed contains `OPERATIONS_MANAGER` (`ROL004`) while `PROJECT.md` does not list it as a primary user. Treat it as a later persona until product scope is ratified; do not silently inherit another role's permissions.

## Resolved

- Frontend ambiguity is resolved by ADR 012 in the master plan: React 19, not Angular, unless the owner explicitly changes the decision.
- Admin POC scope resolved as global read-only (ADR 005) — moved from Open on 2026-08-07.
- Product AI runtime locked: LangChain `ChatOpenAI` + `bind_tools(role_scoped_tools)` + custom bounded `run_assistant` invoke loop. Forbidden: `create_agent` / `AgentExecutor` / `create_react_agent`. The 16:00 “no bind_tools” changelog line is historical and superseded (16:05+ / ADR 011). Do not reference external private projects by name.
- Three-portal Sprint 1–2 UI wording superseded by owner two-portal POC contract — plans/wiki 2026-08-07; **web scaffold consolidated** 2026-08-07 to `/driver/login` + `/ops/login` (legacy redirects).
- Auth users empty / unmapped — resolved 2026-08-07 ~16:25 IST: `auth.users=3`, USR001/USR101/USR999 mapped.
- **Live `/auth/me` DB_UNAVAILABLE** — resolved 2026-08-07 16:35 IST after local `DATABASE_URL` save; all three roles PASS. Stale open-ledger claim removed 2026-08-07 17:55 IST.
- Sprint 1 exit gate open — resolved 2026-08-07 17:55 IST (struck with evidence).
