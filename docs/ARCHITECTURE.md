# SetuHaul AI
# System Architecture

Version: 1.0

---

# Purpose

This document defines the complete technical architecture of the SetuHaul AI platform.

It explains:

- Overall system architecture
- Application layers
- Component responsibilities
- AI architecture
- Authentication flow
- Database interactions
- Redis usage
- LangChain integration
- Monitorin with LangSmith, AgentCore, CloudWatch
- Folder structure
- Deployment architecture

This document does not define API contracts or database schemas. Those are documented separately.

---

# High Level Architecture

Status through **Sprint 3** (gate COMPLETE 2026-08-12): two React portals, one FastAPI BFF, LangChain `bind_tools` + bounded manual loop, deterministic scheduling services, Supabase PostgreSQL SoT, Upstash Redis 24h conversation memory only.

## How we use it (exact)

| Actor | Entry | What happens |
|---|---|---|
| Driver | `/driver/login` → chat | Supabase Auth → JWT → FastAPI builds `ExecutionContext` → `POST /api/v1/chat` → `run_assistant` → LLM with role-scoped tools → services → PostgreSQL / Redis |
| Ops / Admin | `/ops/login` → dashboard | Same Auth path → Ops REST (summary, exceptions, escalation queue, dock/queue status) + confirm/reject/expire appointment REST |
| LLM | never | Never executes SQL, never invents ETA/slot/capacity facts, never marks appointments `CONFIRMED` |
| Scheduling engine | `feasibility` + `allocation` | Pure deterministic code + `constraints.json`; Postgres unique indexes enforce one active claim per slot/shipment |

## System context (Mermaid)

```mermaid
flowchart TB
  subgraph clients [React 19 portals]
    Driver["Driver<br/>/driver/login → chat"]
    Ops["Ops / Admin<br/>/ops/login → dashboard"]
  end

  subgraph fastapi [FastAPI /api/v1]
    Auth["JWT verify → ExecutionContext<br/>role + facility/driver scope"]
    Chat["POST /chat<br/>run_assistant"]
    Sched["Scheduling REST<br/>feasible · request · status<br/>cancel · reschedule · confirm · reject · expire"]
    OpsAPI["Ops REST<br/>summary · exceptions<br/>escalation-queue · dock/queue status"]
  end

  subgraph assistant [LangChain assistant]
    LLM["ChatOpenAI / OpenRouter / Gemini<br/>bind_tools + bounded manual loop"]
    Tools["Role-scoped tools<br/>ETA · feasibility · request_slot<br/>status · cancel · reschedule · escalate · memory"]
  end

  subgraph services [Deterministic services]
    Eta["eta_service"]
    Feas["feasibility.py<br/>+ constraints.json"]
    Alloc["allocation.py<br/>locks · idempotency · audit"]
    Esc["escalation_service"]
    Mem["ConversationMemory"]
  end

  PG[(Supabase PostgreSQL<br/>SoT)]
  Redis[(Upstash Redis<br/>24h TTL · non-authoritative)]
  SBAuth[(Supabase Auth)]

  Driver --> Auth
  Ops --> Auth
  Driver --> Chat
  Driver --> Sched
  Ops --> OpsAPI
  Ops --> Sched
  Auth --> SBAuth
  Chat --> LLM
  LLM --> Tools
  Tools --> Eta
  Tools --> Feas
  Tools --> Alloc
  Tools --> Esc
  Tools --> Mem
  Sched --> Feas
  Sched --> Alloc
  OpsAPI --> Esc
  Eta --> PG
  Feas --> PG
  Alloc --> PG
  Esc --> PG
  Mem --> Redis
  Chat --> Mem
```

## Driver chat turn (Mermaid)

```mermaid
sequenceDiagram
  participant UI as Driver UI
  participant API as FastAPI /chat
  participant RA as run_assistant
  participant LLM as LLM bind_tools
  participant T as Typed tool
  participant S as Service
  participant PG as PostgreSQL
  participant R as Redis

  UI->>API: Bearer JWT + message + session_id
  API->>API: Verify JWT → ExecutionContext
  API->>RA: thread_id + user message
  RA->>R: load history / summaries / session
  RA->>LLM: system prompt + context + tools
  loop bounded tool loop
    LLM-->>RA: tool_calls
    RA->>T: StructuredTool kwargs
    T->>S: Pydantic command
    S->>PG: scoped read/write + audit/idempotency
    PG-->>S: authoritative reread
    S-->>RA: ToolMessage JSON
  end
  LLM-->>RA: final assistant text
  RA->>R: append history (+ maybe summarize)
  RA-->>UI: reply + tool results + session/thread ids
```

## Scarce-capacity allocation (Mermaid)

```mermaid
flowchart LR
  A["find_feasible_slots"] --> B["Ranked options<br/>DISPLAYED_NOT_RESERVED<br/>+ REC- recommendation_id"]
  B --> C{"Driver picks exact slot_id"}
  C --> D["request_slot / reschedule<br/>Idempotency-Key"]
  D --> E{"Revalidate + row locks<br/>REC- still current?"}
  E -->|stale / taken| F["409 SLOT_OPTIONS_STALE<br/>or CONFLICT_REFRESH<br/>+ refreshed options"]
  E -->|ok| G["PENDING_CONFIRMATION<br/>unique slot + shipment guards"]
  G --> H{"Ops"}
  H --> I["confirm → CONFIRMED"]
  H --> J["reject / expire → free slot"]
  G --> K["driver/ops cancel → free slot"]
  A -->|zero options| L["escalation_queue NOSLOT<br/>Ops takeover list"]
```

ASCII sketch (same topology):

```
Driver / Ops (React 19)
        │
        ▼
   FastAPI (/api/v1)  ← JWT ExecutionContext
        │
   ┌────┼────────────┐
   ▼    ▼            ▼
 Chat  Scheduling   Redis
(tools) + Ops REST  (24h memory)
   │     │
   └─────┼─────► Supabase PostgreSQL (SoT)
               feasibility · allocation · escalation_queue
```

---

# Architecture Principles

The application follows the following principles.

- Modular
- Layered
- Service Oriented
- AI First
- Stateless APIs
- Role Based Access
- Production Ready

---

# Technology Stack

## Frontend

React

TypeScript

Vite

TailwindCSS

Shadcn UI

React Query

React Router

Chart.js

Hero Icons

---

## Backend

FastAPI

Python 3.12+

Pydantic

SQLAlchemy

Alembic

---

## AI

LangChain

OpenAI (ChatOpenAI via LangChain)

LangSmith, CloudWatch, AgentCore

---

## Database

Supabase PostgreSQL

---

## Cache

Redis with UpStash

---

## Deployment

Docker

Docker Compose

NGINX

---

# Application Layers

```
Frontend

↓

API Layer

↓

Authentication

↓

Business Services

↓

AI Layer

↓

Tool Layer

↓

Database

↓

Redis
```

Each layer has one responsibility.

---

# Frontend Architecture

```
frontend/

resources/

src/

components/

pages/

layouts/

hooks/

services/

types/

assets/

styles/

utils/

router/
```

The existing Stitch generated HTML/CSS must be converted into reusable React components.

No UI redesign is required.

---

# Backend Architecture

```
backend/

app/

api/

routers/

services/

ai/runtime/

tools/

database/

models/

schemas/

middleware/

auth/

config/

prompts/

utils/

core/

main.py
```

---

# Layer Responsibilities

## API Layer

Responsibilities

- Receive HTTP requests
- Validate input
- Return responses

No business logic.

---

## Service Layer

Responsibilities

- Business rules
- Database operations
- Validation
- Transactions

---

## Tool Layer

LangChain tools call the Service Layer.

Examples

- Lookup Shipment
- Lookup Driver
- Update ETA
- Book Appointment
- Cancel Appointment
- Find Available Slots

Tools must never execute raw SQL.

---

## AI Layer

The AI layer is responsible for

- Intent Detection
- Context Management
- Tool Selection
- Response Generation

The AI layer never directly modifies the database.

---

# AI Architecture

Runtime shape (ADR 011): **not** `create_agent` / AgentExecutor. One assistant per request uses `bind_tools` on a curated Driver allowlist and a custom bounded invoke loop.

```mermaid
flowchart TD
  M[User message] --> C[Load Redis history + summaries]
  C --> P[Build messages: system + summaries + recent raw + user]
  P --> L[LLM.invoke with bind_tools]
  L --> Q{tool_calls?}
  Q -->|yes| T[Execute StructuredTool → service]
  T --> V[ToolMessage with JSON result]
  V --> L
  Q -->|no| F[Final assistant text]
  F --> S[Persist to Redis 24h]
  S --> R[Return reply to UI]
```

Tool calls always land in application services (`eta_service`, `feasibility`, `allocation`, `escalation_service`, `driver_reads`, `ConversationMemory`). Services enforce scope from `ExecutionContext`, never from client-supplied ownership IDs.

---

# LangChain LLM Invoke Flows

Exact loop implemented in `backend/app/assistant/run_assistant.py`:

```mermaid
flowchart TD
  Start[START] --> LoadUser[Trusted ExecutionContext from JWT]
  LoadUser --> LoadMem[Load Redis history/summaries/session]
  LoadMem --> Build[Assemble prompt + role-scoped tools]
  Build --> Invoke[LLM.invoke]
  Invoke --> Need{Need tool?}
  Need -->|clarification only| Ask[Ask user · no write]
  Need -->|tool_calls| Pick[Select typed tool]
  Pick --> Exec[Service executes command]
  Exec --> Persist[PostgreSQL write + audit/idempotency OR Redis memory]
  Persist --> Reread[Authoritative reread]
  Reread --> Invoke
  Need -->|final text| End[Return assistant reply]
  Ask --> End
```

Clarification (e.g. repair duration ≠ ETA) happens before mutation tools commit. Scheduling tools never invent slots; zero options escalate to `escalation_queue`.

---

# AI Tools

The assistant uses deterministic, role-scoped tools. Driver allowlist (Sprint 3) includes:

- `get_driver_profile` / operational context reads
- `get_latest_eta`, `get_eta_history`, `get_current_appointment`
- `get_facility_details`, `get_exception_status`
- `report_delay_or_update_eta` (confirm exact ETA before write)
- `find_feasible_slots` (non-reserved options + `REC-` id)
- `request_slot`, `get_appointment_request_status`
- `cancel_appointment`, `reschedule_appointment`
- `escalate_exception`
- `get_conversation_memory`

Ops appointment confirm / reject / expire are REST (ops/admin), not Driver chat tools. Each tool calls the corresponding service; the LLM never runs SQL.

---

# Authentication Architecture

Authentication uses Supabase Authentication.

After successful login

```
User

↓

Supabase Auth

↓

JWT Token

↓

FastAPI

↓

User Lookup

↓

Role Validation

↓

Response
```

The application should never store plaintext passwords.

---

# Role Based Access

## Driver

Accessible Pages

- Login
- AI Assistant

---

## Operations Users

Accessible Pages

- Login
- AI Assistant
- Operations

---

## Administrator

Full access.

---

# Operations Module

Operations consists of tab-based pages.

```
Operations

├── Dashboard

├── Shipments

├── Appointments

├── Drivers

├── Facilities

├── Exceptions

├── Analytics

└── Settings
```

---

# Redis Architecture

Redis will be used for

## Conversation Memory

Store active conversations.

TTL: 24 hours

---

## LangChain Conversation Memory

Persist bounded conversation history and session context in Upstash Redis with a 24-hour TTL.

The assistant uses `ChatOpenAI.bind_tools(role_scoped_tools)` plus a custom bounded invoke loop per request (`invoke` → tool_calls → service-backed ToolMessages → final text). Do not use `create_agent`, `AgentExecutor`, or `create_react_agent`. Tools call FastAPI application services only (no SQL); PostgreSQL remains SoT; the LLM never invents operational facts.

---

## Session Cache

Store user sessions.

---

## Frequently Used Queries

Cache

- Dashboard KPIs
- Facility Summary
- Available Slots
- Driver Details

---

# Database Access

All database operations follow

```
Router

↓

Service

↓

Repository

↓

SQLAlchemy

↓

PostgreSQL
```

Routers never execute SQL.

---

# Logging

Three types of logging are required.

Application Logs

Python logging.

Audit Logs

Stored in audit_logs.

API Logs

Stored in api_logs.

---

# Error Handling

All APIs return

```json
{
  "success": true,
  "message": "",
  "data": {},
  "errors": [],
  "timestamp": "",
  "request_id": ""
}
```

---

# Folder Structure

```
SetuHaul-AI/

frontend/

│

├── resources/

├── src/

│ ├── components/

│ ├── pages/

│ ├── layouts/

│ ├── services/

│ ├── hooks/

│ ├── router/

│ ├── assets/

│ └── types/

backend/

│

├── app/

│ ├── api/

│ ├── auth/

│ ├── ai/runtime/

│ ├── services/

│ ├── tools/

│ ├── routers/

│ ├── middleware/

│ ├── database/

│ ├── models/

│ ├── schemas/

│ ├── prompts/

│ ├── utils/

│ └── core/

database/

docs/

tests/

.env

requirements.txt

README.md
```

---

# Sequence Diagram

```
Driver

↓

React

↓

FastAPI

↓

LangChain

↓

Tool

↓

Service

↓

Repository

↓

PostgreSQL

↓

Tool

↓

LangChain

↓

FastAPI

↓

React
```

---

# Non Functional Requirements

- Response time under 2 seconds for standard queries.
- Modular architecture.
- Scalable backend.
- Stateless APIs.
- Secure authentication.
- Structured logging.
- Type-safe backend.
- Reusable frontend components.
- Docker-ready deployment.

---

# Future Enhancements

The architecture should support future additions without major refactoring.

Potential enhancements include:

- WhatsApp integration
- Microsoft Teams integration
- Voice-based driver assistant
- Live GPS integration
- Real-time notifications
- OR-Tools scheduling engine
- Multi-tenant deployment
- Multi-language support
- Predictive ETA models
- AI-powered operational analytics

These enhancements should integrate with the existing architecture without requiring significant changes to the core system.
