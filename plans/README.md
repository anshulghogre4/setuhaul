# SetuHaul implementation plans

This folder is the implementation source of truth that turns the challenge brief into gated vertical delivery sprints (Sprint 1–3 for POC/challenge readiness; Sprint 4 for hosting/AgentCore/observability/Locust).

## Start here

- [Master implementation plan](implementation-master-plan.md) - architecture, decisions, sprint gates, edge cases, and acceptance criteria.
- [POC design review](poc-design-review.md) - selected Stitch direction, retained POC elements, and deferred visual scope.
- [Solution architecture branch](branches/solution-architecture.md) - boundaries, runtime topology, transaction model, and ADRs.
- [Business analysis branch](branches/business-analysis.md) - outcomes, actors, scope, workflows, and business acceptance criteria.
- [Full-stack branch](branches/full-stack.md) - application structure, API slices, testing, and the first working milestone.
- [AI engineering branch](branches/ai-engineering.md) - agent boundary, state, tools, evaluation, and failure behaviour.

## Delivery rule

Complete each sprint's exit gate before starting the next sprint. The challenge is won by proving safe behaviour under concurrent slot demand, not by maximizing page or chatbot feature count. Sprint 3 exit gate is **COMPLETE**. Post-gate demo-hardening (cast reset vs Phase B, chat cancel→rebook idempotency, stale REC when omitted, reschedule orphan) is **COMPLETE** as of 2026-08-13 21:39 IST. Sprint 4 (Vercel + App Runner + Bedrock AgentCore + CloudWatch/LangSmith + Locust) stays PLANNED until the owner promotes hosting.

The master plan is the **cross-agent Living sprint scoreboard** (Cursor, Claude, Codex, Gemini). Unchecked items remain `TODO`, active items are labeled `IN PROGRESS`, and verified completed items are checked and struck through with dated evidence. Deferred work remains as explicit unchecked `TODO (DEFERRED)` entries. Never strike a sprint heading or exit gate until its complete objective evidence exists. Every durable session must refresh this Living status when implementation progress changes (root `AGENTS.md` writeback).

