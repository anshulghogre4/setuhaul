---
title: SetuHaul Contradictions and Staleness Ledger
type: ledger
status: authoritative
scope: repository
last_updated: 2026-08-16
---

# Contradictions and staleness ledger

## Open

- **False-escalation prompt bug, fixed but not redeployed (2026-08-17 06:35 IST)** — live driver-chat testing (owner, hosted screenshots) caught `escalate_exception` firing on the plain context-lock line `I need help with shipment X`, creating a real `OPEN`/`HIGH` escalation (`ESC-53B8A6EA0A37` for `SHP-D16-RAVI` at `FAC-JAI-01`). Root cause: `backend/app/assistant/prompts.py`'s escalation rule read "...when the driver asks for help or escalation" as an independent trigger instead of gated by `NO_FEASIBLE_SLOTS`. Fixed in prompt text; backend units 86 passed; **not yet redeployed to hosted/local-restarted**, so the bug may still reproduce until redeploy. The stray escalation record itself has not been resolved/deleted — expect it in Ops's escalation list until cleared.
- **Tools catalog PDF vs `tools.py` (2026-08-16)** — `docs/Scheduling Algo and tools/SetuHaul_AI_Complete_23_Tools_Catalog.pdf` names all 23 registered Driver tools correctly. Do not use its example IDs in a Ravi demo: `SHP1002` and `SHP-D16-RACE-B` are Amit (`DRV002`) → 403; `SLT-*` / `APT-0892` are invented. There is no `facility_schedules` table. `request_slot` creates `PENDING_CONFIRMATION`, not a warehouse booking. Prefer code + [PRESENTATION_CHECKLIST.md](../docs/PRESENTATION_CHECKLIST.md) for live prompts.
- **Presentation 2026-08-17 vs demo SQL 2026-08-16** — owner moved the show to 17 Aug; live slots/ETAs/cast IDs remain a frozen 16 Aug scenario. Feasibility compares `slot_end` to shipment ETA, not wall-clock now, so the 16 Aug script still works. Do not claim the data is “today” unless `generate_demo_day.py --demo-day 2026-08-17` is generated and applied.
- `PROJECT.md` and older architecture documentation describe the intended product broadly; `plans/implementation-master-plan.md` narrows delivery to gated vertical slices. Agents must follow the master plan for implementation order.
- `docs/DEPLOYMENT.md` still describes Docker Compose / local Redis as the deployment shape. Sprint 4 hosting truth is `plans/sprint-4-hosting.md` (Vercel + App Runner probe / ECS Express Mode + AgentCore). Prefer the scoreboard until `docs/HOSTING.md` is folded after hosted smoke.
- `docs/AGENTS.md` names the runtime logistics assistant, while root `AGENTS.md` governs coding agents. Do not conflate them. `docs/AGENTS.md` may still contain older Gemini/AgentExecutor wording in places; prefer ADR 011 + master plan §5.2 + [[ai-system]] for runtime shape until that doc is fully refreshed.
- The seed contains `OPERATIONS_MANAGER` (`ROL004`) while `PROJECT.md` does not list it as a primary user. Treat it as a later persona until product scope is ratified; do not silently inherit another role's permissions.

## Resolved

- **`hosting` vs `main` merge lock** — resolved 2026-08-14 01:46 IST: owner lifted the “merge only after Step 10” branch rule so Vercel production can track `main`. Step order and Sprint 4 exit-gate evidence are unchanged.
- **Cast reset vs Phase B** — resolved 2026-08-13 21:39 IST: `--mode cast` restores `D16-APT-RAVI-OLD` as CANCELLED / not current; Phase B `request_slot` is unblocked; `APT1017` remains CONFIRMED for SHP1017 disambiguation.
- Frontend ambiguity is resolved by ADR 012 in the master plan: React 19, not Angular, unless the owner explicitly changes the decision.
- Admin POC scope resolved as global read-only (ADR 005) — moved from Open on 2026-08-07.
- Product AI runtime locked: LangChain `ChatOpenAI` + `bind_tools(role_scoped_tools)` + custom bounded `run_assistant` invoke loop. Forbidden: `create_agent` / `AgentExecutor` / `create_react_agent`. The 16:00 “no bind_tools” changelog line is historical and superseded (16:05+ / ADR 011). Do not reference external private projects by name.
- Three-portal Sprint 1–2 UI wording superseded by owner two-portal POC contract — plans/wiki 2026-08-07; **web scaffold consolidated** 2026-08-07 to `/driver/login` + `/ops/login` (legacy redirects).
- Auth users empty / unmapped — resolved 2026-08-07 ~16:25 IST: `auth.users=3`, USR001/USR101/USR999 mapped.
- **Live `/auth/me` DB_UNAVAILABLE** — resolved 2026-08-07 16:35 IST after local `DATABASE_URL` save; all three roles PASS. Stale open-ledger claim removed 2026-08-07 17:55 IST.
- Sprint 1 exit gate open — resolved 2026-08-07 17:55 IST (struck with evidence).
