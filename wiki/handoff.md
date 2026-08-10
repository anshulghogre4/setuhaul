---
title: SetuHaul Session Handoff
type: handoff
status: authoritative
scope: repository
last_updated: 2026-08-08
---

# Session handoff

## Latest work

- **2026-08-08 23:58 IST:** Completed Sprint 3 Deterministic Feasibility & Capacity Engine and Scheduling Package (`feasibility.py`, `booking.py`, `escalation.py`, `assistant/tools.py`, `api/v1/routers/scheduling.py`). All 5 REST endpoints and assistant tools end-to-end verified.
- **2026-08-08 18:28 IST:** Bound `.env` and `frontend/.env.local` to `https://kujffzgqjmqphkmrbawy.supabase.co`. `/health/ready` verified `database_reachable: true`. Backend (:8000) & Frontend (:5173) active.
- **2026-08-08 17:45 IST:** Configured python venv, resolved Vite 6 compatibility for Node v20.17.0, built frontend, created `.env` files, started FastAPI backend (`:8000`) and Vite frontend (`:5173`).
- **2026-08-08 13:45 IST:** Renamed `web/` → `frontend/`; CI/README/gitignore/package name updated; `npm run build` PASS.
- **2026-08-08 13:35 IST:** Added `GET /` root alive health ping (no more 404 on `:8000/`). README note; `/health/live` + `/health/ready` unchanged.
- **2026-08-07 20:25 IST:** Gemini live **PASS** with `ChatGoogleGenerativeAI` + default `gemini-2.5-flash` (2.0 retired). OpenAI + OpenRouter + Gemini all live-verified.

## Current state

See [[current-state]]. Sprint 3 Scheduling Core complete. **Backend (:8000) and Frontend (:5173) active and running.**

## Decisions and blockers

- Product AI: `ChatOpenAI.bind_tools` for OpenAI/OpenRouter; **`ChatGoogleGenerativeAI`** for Gemini; same bind_tools manual loop. Default Gemini model **`gemini-2.5-flash`**.
- JWT verify uses `leeway=300` for local clock skew vs Supabase `iat`.
- Concurrency & Row Locking: PostgreSQL `SELECT ... FOR UPDATE` on `appointment_slots` and `appointments` with HTTP 409 mapping.
- **Security:** keys pasted in chat → rotate after POC; never commit. README emails only; passwords OOB.

## Verification

- Unit: **23 passed** (`PYTHONPATH=. pytest tests/unit`).
- Frontend: `npm run build` **PASS**.
- Live servers: FastAPI (`http://127.0.0.1:8000/`) PASS; Vite (`http://localhost:5173/`) PASS.
- Live HTTP Endpoints: Slot Search 200 OK, Booking 200 OK, Reschedule 200 OK, Escalation 200 OK.
- Memory MCP: **UNAVAILABLE** in current environment session; recorded degradation and synchronized checked-in wiki & handoff context.


## Next action

1. Begin Sprint 3 only when ready: feasibility, ranking, concurrent allocation.
2. Optionally rotate chat-pasted API keys after POC sharing risk review.


Related: [[current-state]], [[implementation]], [[ai-system]], [[testing]].
