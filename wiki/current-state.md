---
title: SetuHaul Current Verified State
type: state
status: authoritative
scope: repository
last_verified: 2026-08-07
---

# Current state

## Verified

- Sprint 1 exit gate COMPLETE (2026-08-07 17:55 IST).
- **Sprint 2 exit gate COMPLETE (2026-08-07 19:35 IST).**
- React 19 `frontend/` (renamed from `web/` 2026-08-08) + FastAPI + Supabase PG SoT + Upstash 24h chat memory + LangChain `ChatOpenAI.bind_tools` manual loop.
- Multi-provider LLM: OpenAI + OpenRouter + Gemini live invoke **PASS** (2026-08-07 20:25 IST). Gemini = `ChatGoogleGenerativeAI` default `gemini-2.5-flash`.
- Unit tests: **20 passed**.

## Verify before claiming

- Formal Playwright suite in CI (local one-shot smoke only).
- LangSmith UI trace inspection (env tracing enabled; UI not opened this session).
- Live chat with OpenRouter or Gemini (keys not set locally as of 20:00 IST).
- Sprint 3 scheduling mutations remain absent by design.

Related: [[implementation]], [[testing]], [[handoff]], [[ai-system]], [[database]].
