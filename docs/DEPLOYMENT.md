# DEPLOYMENT.md

# SetuHaul AI - Deployment Guide

Version: 1.0

---

# Deployment Objective

This document defines how the SetuHaul AI application should be configured, built, executed, and deployed.

The application must be fully containerized and capable of running in both local development and production environments with minimal configuration.

Deployment should be reproducible using Docker Compose.

---

# Technology Stack

## Frontend

- React 19
- TypeScript
- Vite
- TailwindCSS
- Shadcn UI

Runs on

http://localhost:5173

---

## Backend

- FastAPI
- Python 3.12+
- Uvicorn

Runs on

http://localhost:8000

Swagger

http://localhost:8000/docs

---

## Database

Supabase PostgreSQL

The project must connect to an existing Supabase database.

No local PostgreSQL container should be created.

All migrations should use Alembic.

---

## Cache

Redis

Runs locally using Docker.

Port

6379

Redis is responsible for

- LangChain checkpointing
- Session storage
- Conversation cache
- Frequently accessed operational data

---

## AI Services

Google Gemini

LangChain

LangSmith, AgentCore, CloudWatch

---

# Project Structure

```
SetuHaul-AI/

backend/

frontend/

database/

docs/

tests/

docker/

.env

.env.example

requirements.txt

Dockerfile

docker-compose.yml

README.md
```

---

# Environment Variables

Generate both

.env

and

.env.example

The following variables are mandatory.

```env
APP_NAME=SetuHaul AI

APP_ENV=development

DEBUG=True

HOST=0.0.0.0

PORT=8000



DATABASE_URL=

SUPABASE_URL=

SUPABASE_ANON_KEY=

SUPABASE_SERVICE_ROLE_KEY=



REDIS_URL=redis://redis:6379/0



GOOGLE_API_KEY=



LANGCHAIN_API_KEY=

LANGCHAIN_TRACING_V2=true

LANGCHAIN_PROJECT=SetuHaul-AI



JWT_SECRET=

JWT_ALGORITHM=HS256

ACCESS_TOKEN_EXPIRE_MINUTES=1440
```

Never hardcode any credentials.

---

# Python Environment

Python Version

3.12+

Create virtual environment automatically.

Windows

```
python -m venv .venv
```

Linux

```
python3 -m venv .venv
```

---

# Dependency Installation

Generate

requirements.txt

Install using

```
pip install -r requirements.txt
```

---

# requirements.txt

Should include compatible versions for

FastAPI

Uvicorn

SQLAlchemy

Alembic

Pydantic

Redis

Supabase

LangChain

Google Generative AI

LangSmith, AgentCore, CloudWatch

python-dotenv

passlib

bcrypt

python-jose

httpx

pytest

pytest-asyncio

black

ruff

---

# Backend Startup

Development

```
uvicorn app.main:app --reload
```

Production

```
uvicorn app.main:app \
--host 0.0.0.0 \
--port 8000
```

---

# Frontend Startup

Install

```
npm install
```

Development

```
npm run dev
```

Production

```
npm run build
```

Preview

```
npm run preview
```

---

# Redis

UpStash Redis Connection

Redis must automatically reconnect if the connection drops.

---

# LangChain Checkpointer

Conversation state should be stored inside Redis.

Every conversation thread should persist.

Checkpoint key

```
thread_id
```

---

# Supabase

Use

Supabase Authentication

Supabase PostgreSQL

Supabase Storage (future)

Do not recreate business tables.

Use the supplied SQL schema.

Apply Alembic only for future migrations.

---

# Database Initialization

Execute

schema.sql

seed.sql

through Supabase SQL Editor.

Do not generate schema from ORM.

The supplied SQL is the source of truth.

---

# Authentication

Authentication

Supabase Auth

Authorization

Role Based Access Control

After login

Create JWT

Store securely

Frontend stores

Access Token

Refresh Token

User Profile

Role

---

# Logging

Generate

logs/

Directory

Application Logs

Error Logs

Audit Logs

API Logs

Example

```
logs/

application.log

error.log

api.log
```

---

# API Documentation

Swagger

```
/docs
```

ReDoc

```
/redoc
```

Must be automatically available.

---

# Docker

Generate

Dockerfile

for

Backend

Frontend

Generate

docker-compose.yml

Services

backend

frontend

redis

Example

```
Frontend

↓

Backend

↓

Redis

↓

Supabase
```

Supabase is external.

Do not create PostgreSQL container.

---

# Health Checks

Generate endpoint

```
GET /health
```

Returns

```json
{
    "status":"healthy"
}
```

Also include

Redis

Database

Gemini

Connectivity

---

# Production Build

Backend

```
docker compose up --build
```

Frontend

Accessible

Backend

Accessible

Redis

Connected

Supabase

Connected

Gemini

Configured

---

# Error Handling

Every API returns

```json
{
  "success":true,
  "message":"Operation completed successfully.",
  "data":{},
  "errors":[],
  "timestamp":"",
  "request_id":""
}
```

---

# Security

Enable

CORS

JWT

Password hashing

Rate Limiting

Request Validation

Environment Variables

SQL Injection Protection

Prompt Injection Protection

Never expose

Supabase Service Key

Google API Key

JWT Secret

---

# Monitoring

Integrate

LangSmith

Track

Conversation

Latency

Token Usage

Errors

Prompt Execution

---

# Testing

Generate

Unit Tests

API Tests

Integration Tests

Coverage should exceed

80%

---

# Deployment Targets

The application should be deployable to

Render

Railway

Azure App Service

Docker

Ubuntu Server

DigitalOcean

No platform-specific code should be written.

---

# CI/CD (Optional)

Generate GitHub Actions workflow.

Pipeline

Lint

↓

Tests

↓

Build

↓

Docker

↓

Deploy

---

# Final Deliverables

The completed project must include

✓ Frontend

✓ Backend

✓ LangChain Agent

✓ FastAPI

✓ Supabase Integration

✓ UpStash Redis Integration

✓ Docker

✓ Docker Compose

✓ Environment Files

✓ API Documentation

✓ Logging

✓ Testing

✓ Production-ready Folder Structure

✓ Deployment Documentation

The application should start successfully after running

```
docker compose up --build
```

without requiring any manual code changes.