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

```
                    +----------------------+
                    |     Driver / Staff   |
                    +----------+-----------+
                               |
                               |
                  React Frontend (Vite)
                               |
                         HTTPS / REST
                               |
                  +------------+------------+
                  |       FastAPI API       |
                  +------------+------------+
                               |
       +-----------------------+-----------------------+
       |                       |                       |
       |                       |                       |
   Authentication         AI Assistant          Operations APIs
       |                       |                       |
       |                       |                       |
       |                LangChain Agent               |
       |                       |                       |
       |             Tool Calling Layer               |
       |                       |                       |
       |       +---------------+---------------+
       |       |               |               |
       |       |               |               |
   PostgreSQL      Redis Cache        Gemini LLM
       |
       |
Supabase PostgreSQL
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

Google Gemini

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

agents/

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

```
User Message

↓

Intent Detection

↓

Retrieve Conversation

↓

Retrieve User Context

↓

Determine Required Tool

↓

Execute Tool

↓

Generate AI Response

↓

Save Conversation

↓

Return Response
```

---

# LangChain Agent Flows

```
START

↓

Load User

↓

Load Conversation

↓

Understand Intent

↓

Need Clarification?

├── YES

│      ↓

│ Ask Question

│

└── NO

       ↓

Tool Selection

↓

Execute Tool

↓

Generate Response

↓

Save Chat

↓

END
```

---

# AI Tools

The AI Agent should use deterministic tools.

Required tools include

- get_driver_profile
- get_shipment
- get_current_appointment
- get_latest_eta
- update_eta
- request_new_slot
- cancel_appointment
- get_available_slots
- get_facility_details
- get_driver_exceptions
- get_dashboard_summary
- generate_daily_report

Each tool should call the corresponding service.

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

## LangChain Checkpoint

Persist graph execution state.

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

│ ├── agents/

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