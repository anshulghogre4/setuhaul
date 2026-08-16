---
title: SetuHaul Source and Provenance Map
type: provenance
status: authoritative
scope: repository
last_verified: 2026-08-16
---

# Source map

| Topic | Authoritative evidence |
| --- | --- |
| Product scope | `PROJECT.md`, `docs/SetuHaul_FDE_Challenge.pdf` |
| Delivery order and ADRs | `plans/implementation-master-plan.md`, `plans/branches/*.md`, `plans/sprint-4-hosting.md` (Sprint 4 hosting command book) |
| Architecture | `docs/ARCHITECTURE.md`, `plans/branches/solution-architecture.md`, `plans/sprint-4-hosting.md` |
| Deployment intent | `docs/DEPLOYMENT.md`, `plans/sprint-4-hosting.md`, `supabase/config.toml` |
| Runtime AI behavior | `docs/AGENTS.md`, `plans/branches/ai-engineering.md` |
| Database | `supabase/migrations/*.sql`, `supabase/seed.sql`, `supabase/tests/database/*.sql`, `docs/DATABASE.md` |
| API intent | `docs/API.md` |
| Agent workflow | root `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursor/rules/setuhaul.mdc`, `wiki/AGENTS.md` |
| Session history | `CHANGELOG.md`, `wiki/log.md`, `wiki/handoff.md` |
| Hosted Locust (Step 10) | `loadtests/README.md`, `loadtests/locust_runbook_chat.py`, `loadtests/locust_slot_contention.py`, `docs/DEMO_MANUAL_RUNBOOK.md` |
| 17 Aug presentation | `docs/PRESENTATION_CHECKLIST.md`, `docs/DEMO_MANUAL_RUNBOOK.md`, `docs/DEMO_DAY_READINESS.md` |
| Knowledge graph | `graphify-out/GRAPH_REPORT.md`, `graphify-out/graph.json` when present |

Executable source and fresh verification outrank summaries when they disagree.

