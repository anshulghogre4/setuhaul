---
title: SetuHaul Source and Provenance Map
type: provenance
status: authoritative
scope: repository
last_verified: 2026-08-07
---

# Source map

| Topic | Authoritative evidence |
| --- | --- |
| Product scope | `PROJECT.md`, `docs/SetuHaul_FDE_Challenge.pdf` |
| Delivery order and ADRs | `plans/implementation-master-plan.md`, `plans/branches/*.md` |
| Architecture | `docs/ARCHITECTURE.md`, `plans/branches/solution-architecture.md` |
| Runtime AI behavior | `docs/AGENTS.md`, `plans/branches/ai-engineering.md` |
| Database | `supabase/migrations/*.sql`, `supabase/seed.sql`, `supabase/tests/database/*.sql`, `docs/DATABASE.md` |
| API intent | `docs/API.md` |
| Deployment intent | `docs/DEPLOYMENT.md`, `supabase/config.toml` |
| Agent workflow | root `AGENTS.md`, `CLAUDE.md`, `GEMINI.md`, `.cursor/rules/setuhaul.mdc`, `wiki/AGENTS.md` |
| Session history | `CHANGELOG.md`, `wiki/log.md`, `wiki/handoff.md` |
| Knowledge graph | `graphify-out/GRAPH_REPORT.md`, `graphify-out/graph.json` when present |

Executable source and fresh verification outrank summaries when they disagree.

