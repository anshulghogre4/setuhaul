# 🚚 SetuHaul AI

> AI-Powered Driver Exception Management & Dock Scheduling Platform

![Python](https://img.shields.io/badge/Python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.116-green)
![React](https://img.shields.io/badge/React-19-blue)
![LangChain](https://img.shields.io/badge/LangChain-Latest-orange)
![Gemini](https://img.shields.io/badge/Google-Gemini-purple)
![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-green)
![Redis](https://img.shields.io/badge/Redis-Cache-red)
![Docker](https://img.shields.io/badge/Docker-Ready-blue)

---

# 📖 Overview

SetuHaul AI is an enterprise AI-powered logistics platform that enables truck drivers and warehouse operations teams to collaborate through a conversational AI assistant.

Instead of calling warehouse coordinators or manually rescheduling appointments, drivers interact with an AI assistant to:

- Report delays
- Update ETA
- Request a new dock appointment
- View shipment information
- Ask operational questions

Operations users receive an AI-powered dashboard for managing shipments, appointments, driver exceptions, dock utilization, and facility operations.

This project is based on the SetuHaul FDE Challenge and extends it into a production-ready AI SaaS platform.

---

# ✨ Features

## Driver Portal

- AI Chat Assistant
- Shipment Information
- ETA Updates
- Appointment Status
- Slot Requests
- Facility Information
- Suggested Questions
- Conversation History

---

## Operations Portal

- AI Operations Assistant
- Dashboard
- Shipments
- Appointments
- Drivers
- Facilities
- Exceptions
- Analytics
- Settings

---

## AI Features

- LangChain Multi-Step Workflow
- Google Gemini
- Context-aware Conversations
- Structured Tool Calling
- Conversation Memory
- Prompt Templates
- Role-aware Responses

---

## Backend Features

- FastAPI
- SQLAlchemy
- Pydantic
- Alembic
- JWT Authentication
- Redis Cache with upstash
- Supabase PostgreSQL
- Audit Logging
- API Logging

---

# 🏗️ Architecture

```
                   Driver / Operations

                           │

                           ▼

                  React Frontend

                           │

                           ▼

                     FastAPI Backend

                           │

          ┌────────────────┼────────────────┐

          ▼                ▼                ▼

      LangChain        Business API      Redis

          │                                 │

          └──────────────┬──────────────────┘

                         ▼

                Supabase PostgreSQL

```

---

# 🖥️ Screens

## Driver

- Login
- AI Assistant

---

## Operations

- Login
- AI Assistant
- Dashboard
- Shipments
- Appointments
- Drivers
- Facilities
- Exceptions
- Analytics
- Settings

---

# 🛠️ Technology Stack

| Layer | Technology |
|---------|------------|
| Frontend | React + TypeScript |
| Styling | TailwindCSS + Shadcn UI |
| Backend | FastAPI |
| AI | LangChain + Gemini |
| Database | Supabase PostgreSQL |
| Cache | Redis |
| ORM | SQLAlchemy |
| Authentication | Supabase Auth + JWT |
| Deployment | Docker |

---

# 📂 Project Structure

```
SetuHaul-AI

frontend/
│
├── resources/
├── src/
│
backend/
│
├── app/
│
database/
│
docs/
│
tests/
│
.env.example
requirements.txt
README.md
PROJECT.md
```

---

# 🚀 Getting Started

## Clone Repository

```bash
git clone https://github.com/<your-username>/SetuHaul-AI.git

cd SetuHaul-AI
```

---

## Create Environment

```bash
python -m venv .venv
```

Windows

```bash
.venv\Scripts\activate
```

Linux / Mac

```bash
source .venv/bin/activate
```

---

## Install Dependencies

```bash
pip install -r requirements.txt
```

---

## Configure Environment

Copy

```
.env.example
```

to

```
.env
```

Update

- Supabase
- Redis
- Gemini API Key
- LangSmith

---

## Start Backend

```bash
uvicorn app.main:app --reload
```

---

## Start Frontend

```bash
npm install

npm run dev
```

---

# 🔐 Demo Users

| Role | Email |
|--------|--------|
| Driver | ravi.kumar@setuhaul.com |
| Operations Executive | priya.mehta@setuhaul.com |
| Warehouse Planner | rahul.verma@setuhaul.com |
| Facility Manager | deepak.joshi@setuhaul.com |
| Admin | admin@setuhaul.com |

---

# 📚 Documentation

| File | Description |
|------|-------------|
| PROJECT.md | Master Project Specification |
| docs/ARCHITECTURE.md | System Architecture |
| docs/DATABASE.md | Database Design |
| docs/API.md | API Specification |
| docs/AGENTS.md | LangChain Design |
| docs/PROMPTS.md | Prompt Library |
| docs/DEPLOYMENT.md | Deployment Guide |
| docs/TASKS.md | Development Roadmap |

---

# 🧪 Testing

```bash
pytest
```

---

# 📦 Deployment

```bash
docker compose up --build
```

---

# 👨‍💻 Coding Standards

- Modular Architecture
- Repository Pattern
- Service Layer
- Dependency Injection
- Type Hints
- PEP8
- Enterprise Logging
- Clean Code
- Unit Testing

---

# 📄 License

This project is created for educational and portfolio purposes based on the SetuHaul FDE Challenge.

---

# 🙏 Acknowledgements

- FDE Academy
- SetuHaul Challenge
- LangChain 
- Google Gemini
- FastAPI
- Supabase
- Redis
- Monitoring with LangSmith, CloudWatch & AgentCore