# SetuHaul AI

> AI-Powered Driver Exception Management & Dock Scheduling Platform (FDE POC)

![Python](https://img.shields.io/badge/Python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116-green)
![React](https://img.shields.io/badge/React-19-blue)
![LangChain](https://img.shields.io/badge/LangChain-ChatOpenAI-orange)
![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-green)
![Redis](https://img.shields.io/badge/Upstash-Redis-red)

---

## Quick start (Sprint 1–2 POC)

**Status:** Sprint 1 + Sprint 2 exit gates are **complete**. Sprint 3 (slot allocation / booking) is **not started**.

**What you can demo today**

- Driver chat with typed tools + confirmed ETA write (idempotent)
- Ops/Admin dashboard refresh seeing the matching exception/ETA
- Scheduling / dock booking requests return `CAPABILITY_NOT_ENABLED` (Sprint 3)

**What you cannot demo yet**

- Concurrent appointment allocation, ranked slot search, or booking mutations

### Run locally

Use **`http://localhost:5173`** for the UI (CORS allows both localhost and 127.0.0.1).

```bash
# 1) Env (never commit real secrets)
cp .env.example .env
# Fill Supabase, DATABASE_URL, at least one LLM key, Upstash, and POC passwords.
# Frontend Vite vars also go in frontend/.env.local (see table below).

# 2) Backend
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 3) Frontend (second terminal)
cd frontend
npm install
npm run dev
```

API: `http://127.0.0.1:8000` (root `/` is an alive health ping; also `/health/live`, `/health/ready`, `/docs`) · UI: `http://localhost:5173`

### Environment variables

| Variable | Where | Purpose |
|---|---|---|
| `SUPABASE_URL`, `SUPABASE_ANON_KEY` | root `.env` | Auth / JWKS |
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_BASE_URL` | `frontend/.env.local` | Browser client |
| `SUPABASE_SERVICE_ROLE_KEY`, `DATABASE_URL` | root `.env` only | Backend DB / admin (never in browser) |
| `LLM_PROVIDER`, `LLM_MODEL` | root `.env` | `auto` \| `openai` \| `openrouter` \| `gemini` |
| `OPENAI_API_KEY` / `OPENROUTER_API_KEY` / `GOOGLE_API_KEY` | root `.env` | LLM (`auto` = OpenAI → OpenRouter → Gemini) |
| `UPSTASH_REDIS_REST_URL`, `UPSTASH_REDIS_REST_TOKEN` | root `.env` | Chat memory (24h TTL, non-authoritative) |
| `LANGSMITH_API_KEY`, `LANGSMITH_TRACING` | root `.env` | Optional tracing |
| `SETUHAUL_POC_*_EMAIL` / `SETUHAUL_POC_*_PASSWORD` | root `.env` | Shared demo accounts (passwords private) |
| `CORS_ORIGINS` | root `.env` | Default includes both Vite origins |

Copy from [`.env.example`](.env.example). Never commit real keys or passwords.

### Demo login details

Passwords are **not** in git. Owner shares them privately; put them in local `.env` as the vars below.

| Portal | URL | Email | Role | Password env var |
|---|---|---|---|---|
| Driver | `http://localhost:5173/driver/login` | `ravi.kumar@setuhaul.com` (also amit.singh, vikas.sharma) | DRIVER | `SETUHAUL_POC_DRIVER_PASSWORD` |
| Ops | `http://localhost:5173/ops/login` | `priya.mehta@setuhaul.com` (also kavita.rao, arvind.nair, rahul.verma, anjali.kapoor, deepak.joshi) | facility ops roles | `SETUHAUL_POC_OPERATOR_PASSWORD` |
| Ops | `http://localhost:5173/ops/login` | `admin@setuhaul.com` (also meera.iyer, suresh.menon, sanjay.gupta, neha.bansal) | global ops / admin roles | `SETUHAUL_POC_ADMIN_PASSWORD` |

These emails are seeded in Supabase Auth and mapped via `users.auth_user_id`. Same password per bucket.

### Demo script (happy path)

1. Open Driver login → sign in as Ravi.
2. Chat (e.g. ask about active shipments / appointment). Confirm an ETA update when prompted.
3. Logout.
4. Open Ops login → Operator or Admin → open dashboard → **Refresh**.
5. Confirm the matching shipment exception / ETA appears (seeded demo path uses shipment like `SHP1017` when available).

### LLM providers

Runtime uses a bounded manual `run_assistant` loop with **`bind_tools`** (not `create_agent` / AgentExecutor).

| Provider | Env | LangChain class |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `ChatOpenAI` |
| OpenRouter | `OPENROUTER_API_KEY` | `ChatOpenAI` + OpenRouter base URL |
| Gemini | `GOOGLE_API_KEY` (Google AI Studio / Gemini API) | `ChatGoogleGenerativeAI` (default `gemini-flash-latest`) |

- `LLM_PROVIDER=auto` (default): first available among OpenAI → OpenRouter → Gemini
- Explicit: set `LLM_PROVIDER=openai|openrouter|gemini` and that provider’s key
- Optional `LLM_MODEL` overrides the default model for the chosen provider
- Do **not** put an OpenAI `sk-` / `sk-proj-` key in `GOOGLE_API_KEY`; default Gemini model is `gemini-flash-latest`.

---

## Overview

SetuHaul is an FDE logistics POC: drivers report delays and update ETA through a conversational assistant; operations see scoped facility (or global Admin) dashboards. PostgreSQL (Supabase) is the business source of truth; Upstash Redis holds bounded conversation/session state only.

---

## POC portals

| Portal | Routes |
|---|---|
| Driver | `/driver/login` → driver chat home |
| Operations | `/ops/login` → shared Operator/Admin dashboard (JWT sets facility vs global RO) |

---

## Architecture (simplified)

```
Driver / Ops (React 19)
        │
        ▼
   FastAPI (/api/v1)
        │
   ┌────┼────┐
   ▼    ▼    ▼
 Chat  REST  Redis
(tools) reads  (24h)
   │     │
   └─────┼─────► Supabase PostgreSQL (SoT)
```

AI package: `backend/app/assistant/` (`llm.py` factory, `run_assistant.py`, tools, prompts).

---

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | React 19 + TypeScript + Vite |
| Backend | FastAPI (thin routers → services → repositories) |
| AI | LangChain `ChatOpenAI` + `bind_tools` (OpenAI / OpenRouter / Gemini-compatible) |
| Database | Supabase PostgreSQL |
| Memory | Upstash Redis (24h TTL, non-authoritative) |
| Auth | Supabase Auth + server-side JWT verification |
| Observability | Optional LangSmith |

---

## Project layout

```
SetuHaul/
├── backend/app/          # FastAPI API + assistant + services
├── frontend/             # React 19 frontend
├── supabase/migrations/  # SQL migrations
├── plans/                # Living master plan + branch plans
├── wiki/                 # LLMWiki (handoff, current-state, …)
├── docs/                 # Architecture / ADRs / scripts
├── .env.example
├── PROJECT.md
└── README.md
```

---

## Documentation

| File | Description |
|---|---|
| [PROJECT.md](PROJECT.md) | Product scope |
| [plans/implementation-master-plan.md](plans/implementation-master-plan.md) | Delivery order / living scoreboard |
| [wiki/handoff.md](wiki/handoff.md) | Latest session handoff |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture |
| [docs/DATABASE.md](docs/DATABASE.md) | Database design |
| [AGENTS.md](AGENTS.md) | Agent / writeback policy |

---

## Testing

```bash
cd backend
pytest tests/unit
```

CI runs backend unit tests + frontend `npm run build` (see `.github/workflows/ci.yml`).

---

## Coding standards (POC)

- FastAPI routers stay thin; business rules in services; persistence in repositories
- LLM orchestrates typed tools only — never executes SQL or invents operational facts
- Never commit secrets, service-role keys, or POC passwords
- Identity and scope come from verified JWT claims, not client-supplied ownership IDs

---

## License / acknowledgements

Educational FDE Challenge portfolio work. Thanks to FDE Academy, LangChain, FastAPI, Supabase, and Upstash.
