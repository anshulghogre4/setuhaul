# SetuHaul AI
## AI-Powered Driver Exception & Dock Scheduling Platform

Version: 1.0

---

# Project Overview

SetuHaul AI is an enterprise AI-powered logistics platform built for warehouse operations and freight transportation.

The application enables truck drivers to communicate with warehouse operations using natural language instead of phone calls or emails.

Drivers can

- Report delays
- Update ETA
- Request new appointment slots
- Cancel appointments
- Ask shipment-related questions
- Get facility information

Operations users can

- Monitor all shipments
- Manage dock appointments
- Review driver exceptions
- View facility status
- Generate operational reports
- Use an AI assistant for operational tasks

The AI assistant acts as the conversational interface.

Business decisions such as dock allocation, appointment booking and scheduling are performed through deterministic backend services.

---

# Project Goals

The objective is to build a production-quality AI application demonstrating

- Enterprise Software Architecture
- AI Agents
- LangChain
- FastAPI
- Supabase PostgreSQL
- Redis
- Modern React Frontend
- Enterprise Authentication
- Role Based Access Control
- Operational Dashboards

The application should be portfolio-quality and deployable.

---

# Primary Users

## Driver

Responsibilities

- Report delays
- Update ETA
- View appointment
- Ask shipment questions
- Request another slot
- Receive AI assistance

Visible Pages

- Login
- AI Assistant

---

## Operations Executive

Responsibilities

- Monitor driver exceptions
- Handle ETA updates
- Manage appointments

Visible Pages

- Login
- AI Assistant
- Operations

---

## Warehouse Planner

Responsibilities

- View dock schedules
- Allocate appointments
- Manage dock capacity

Visible Pages

- Login
- AI Assistant
- Operations

---

## Facility Manager

Responsibilities

- Monitor warehouse activity
- Review dock utilization
- Review queues

Visible Pages

- Login
- AI Assistant
- Operations

---

## Transport Manager

Responsibilities

- Monitor fleet
- Review driver performance
- Resolve transportation issues

Visible Pages

- Login
- AI Assistant
- Operations

---

## Regional Operations Head

Responsibilities

- Review facility performance
- Review KPIs
- Analytics

Visible Pages

- Login
- AI Assistant
- Operations

---

## Administrator

Responsibilities

- User Management
- Role Management
- System Configuration
- AI Configuration

Visible Pages

- Login
- AI Assistant
- Operations

---

# Technology Stack

## Frontend

React 19

TypeScript

Vite

TailwindCSS

Shadcn UI

React Query

React Router

Hero Icons

Chart.js

The frontend resources generated using Stitch are available inside

frontend/resources

These HTML/CSS/UI resources should be reused wherever possible.

Do not redesign the UI.

Convert the Stitch pages into reusable React components.

---

## Backend

FastAPI

Python 3.12+

Pydantic

SQLAlchemy

Alembic

---

## AI Stack

LangChain

Google Gemini

LangSmith

amazon bedrock agentcore

amazon bedrock cloudwatch
---

## Database

Supabase PostgreSQL

Existing SetuHaul database schema must remain unchanged.

Only the following additional tables have been added

- roles
- users
- audit_logs
- api_logs

Do not modify existing business tables.

---

## Cache

Redis

Redis should be used for

- Session Cache
- LangChain Checkpointer
- Frequently Used Queries
- AI Conversation State

---

# Authentication

Use Supabase Authentication.

Application users are stored in the users table.

Role Based Access Control must be implemented.

Permissions are determined by role.

Drivers can access

- AI Assistant

Operations users can access

- AI Assistant
- Operations

---

# AI Assistant

The AI Assistant is the primary interface of the application.

It should support

Drivers

- Update ETA
- View Appointment
- Request Slot
- Shipment Status
- Facility Details
- Appointment Status

Operations

- Delayed Shipments
- Driver Exceptions
- Available Docks
- Facility Summary
- Shipment Lookup
- Generate Reports

The AI Assistant must never directly modify business data.

All updates must occur through backend services.

---

# Operations Module

Operations should contain the following tabs

Dashboard

Shipments

Appointments

Drivers

Facilities

Exceptions

Analytics

Settings

---

# Dashboard

Display

- Active Shipments
- Delayed Shipments
- Waiting Trucks
- Available Docks
- Dock Utilization
- Average Delay

Charts

Shipment Status

ETA Trend

Dock Utilization

Driver Exceptions

Recent Activities

---

# Project Structure

SetuHaul-AI/

frontend/

backend/

database/

docs/

tests/

.env

.env.example

requirements.txt

README.md

PROJECT.md

---

# Environment Variables

The project must automatically generate

.env.example

including

SUPABASE_URL

SUPABASE_KEY

SUPABASE_SERVICE_KEY

DATABASE_URL

REDIS_URL

GOOGLE_API_KEY

LANGCHAIN_API_KEY

LANGCHAIN_PROJECT

LANGCHAIN_TRACING_V2

JWT_SECRET

APP_ENV

---

# Requirements

Automatically generate

requirements.txt

with compatible package versions.

---

# Logging

Application logging must use

Python logging

Audit Logs

API Logs

Error Logs

---

# Error Handling

Every API should return

success

message

data

errors

timestamp

request_id

---

# Coding Standards

Use

PEP8

Type Hints

Docstrings

Dependency Injection

Repository Pattern

Service Layer

Router Layer

Schema Layer

Model Layer

No business logic inside routers.

---

# Testing

Create

Unit Tests

Integration Tests

API Tests

---

# Deployment

The application should be fully Dockerized.

Generate

Dockerfile

docker-compose.yml

The project should run using

docker compose up

---

# Deliverables

The completed project must include

✔ Frontend

✔ Backend

✔ AI Agent

✔ Database

✔ Authentication

✔ Dashboard

✔ Chatbot

✔ Docker

✔ Documentation

✔ API Documentation

✔ README

✔ Production Ready Folder Structure

---

# Important Instructions

Do not redesign the supplied Stitch UI.

Reuse all frontend resources.

Keep the existing database schema intact.

Only use the additional tables provided.

The project should be production-ready, modular, clean, and easy to maintain.

Prioritize readability, scalability, and enterprise coding standards over shortcuts.