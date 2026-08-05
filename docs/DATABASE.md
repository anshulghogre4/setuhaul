# DATABASE.md

# SetuHaul AI Database Design

Version: 1.0

---

# Purpose

This document explains the database architecture used by SetuHaul AI.

The project is built on top of the provided SetuHaul freight operations database.

The existing business schema must remain unchanged.

Only the following additional tables have been introduced:

- roles
- users
- audit_logs
- api_logs

These tables provide authentication, authorization and application logging without modifying the operational freight data.

---

# Database Technology

Primary Database

Supabase PostgreSQL

ORM

SQLAlchemy

Migration Tool

Alembic

Authentication

Supabase Authentication

Cache

Redis

---

# Design Principles

The project follows these principles.

- Existing freight tables are the system of record.
- AI never writes directly into business tables.
- Business updates always occur through backend services.
- Conversation state is stored in Redis.
- Authentication is handled separately from operational data.
- Historical data is never deleted.

---

# High-Level Database Architecture

                    Supabase PostgreSQL

                            │

     ┌──────────────────────┼────────────────────────┐

     │                      │                        │

Operational Tables     Authentication         Application Logs

     │                      │                        │

Shipments              Users                 Audit Logs

Drivers                Roles                 API Logs

Appointments

Facilities

ETA Updates

Exceptions

Chat Threads

Chat Messages

---

# Existing Business Tables

The following tables are part of the supplied SetuHaul dataset.

These tables must not be modified.

## Master Tables

carriers

drivers

vehicle_types

vehicles

facilities

docks

facility_contacts

facility_rules

---

## Operational Tables

shipments

appointments

appointment_slots

eta_updates

facility_checkins

dock_status_events

driver_exceptions

operational_messages

---

## Conversation Tables

chat_threads

chat_messages

---

# Additional Application Tables

## roles

Purpose

Stores system roles used for Role Based Access Control.

Example

Driver

Operations Executive

Warehouse Planner

Operations Manager

Facility Manager

Transport Manager

Regional Operations Head

Administrator

Relationship

roles

↓

users

---

## users

Purpose

Represents authenticated users of the application.

A user may be

Driver

Operations Executive

Warehouse Planner

Operations Manager

Facility Manager

Transport Manager

Regional Operations Head

Administrator

Drivers reference

drivers.driver_id

Operations users do not.

---

## audit_logs

Purpose

Stores every important business action.

Examples

User Login

ETA Updated

Appointment Booked

Appointment Cancelled

Shipment Viewed

Driver Message Sent

This table is append-only.

Never update historical audit records.

---

## api_logs

Purpose

Stores application API activity.

Examples

Chat Request

Slot Search

Appointment Booking

Dashboard Request

Useful for

Monitoring

Performance

AI Debugging

Production Support

---

# Relationships

roles

↓

users

↓

audit_logs

↓

api_logs

users

↓

drivers

users

↓

facilities

api_logs

↓

chat_threads

Business tables remain independent.

---

# Read vs Write Access

## Read Only

AI may read

drivers

shipments

vehicles

appointments

appointment_slots

eta_updates

facilities

docks

facility_rules

facility_checkins

driver_exceptions

chat_threads

chat_messages

operational_messages

views

AI must never modify these tables directly.

---

## Writable Tables

The backend services may insert or update

appointments

eta_updates

chat_messages

driver_exceptions

audit_logs

api_logs

All updates must pass through validation.

---

# Database Views

Existing Views

v_latest_eta

v_slot_availability

v_inbound_operational_state

v_current_facility_queue

Always prefer using views instead of manually joining multiple operational tables whenever possible.

---

# AI Data Access

The AI Assistant never executes raw SQL.

Instead, it communicates through backend tools.

Example

Driver asks

"I'll reach around 8 PM."

↓

LangChain

↓

update_eta()

↓

Backend Service

↓

eta_updates

↓

Audit Log

↓

AI Response

---

Driver asks

"What is my appointment?"

↓

get_current_appointment()

↓

Database View

↓

Appointment Details

↓

AI Response

---

# Redis Usage

Redis is not a source of truth.

Redis stores temporary application state.

Examples

Conversation Memory

Session Cache

LangChain Checkpoints

Frequently Used Queries

User Context

Suggested Slots Cache

Redis data can always be recreated from PostgreSQL.

---

# Database Transactions

The following operations must execute inside database transactions.

Booking Appointment

Cancelling Appointment

Rescheduling Appointment

ETA Update

Driver Exception Resolution

User Creation

Role Assignment

Audit Logging

---

# Index Strategy

Existing indexes should remain unchanged.

Additional indexes

users(role_id)

users(driver_id)

users(facility_id)

audit_logs(user_id)

audit_logs(created_at)

api_logs(user_id)

api_logs(thread_id)

api_logs(created_at)

---

# Soft Delete Policy

Application tables should not use hard delete.

If records need to be retired,

use

is_active

or

status

Historical operational records must never be deleted.

---

# Audit Policy

Every business action generates an audit record.

Examples

Login

Logout

ETA Update

Appointment Booking

Appointment Cancellation

Profile Update

Every API request generates an API log.

---

# Future Enhancements

Potential future tables

notifications

saved_reports

user_preferences

ai_feedback

feature_flags

These are intentionally excluded from Version 1.

---

# Backup Strategy

Supabase automated backups

Daily backup

Point-in-time recovery

Audit logs retained permanently.

---

# Security

Passwords are not stored directly.

Supabase Authentication manages authentication.

The users table stores application profile information.

Sensitive data should never be returned to the frontend.

---

# Claude / Gemini Implementation Rules

Do not modify the supplied business schema.

Reuse every existing table.

Reuse existing views.

Do not duplicate operational data.

Always access business data through services.

Never expose raw SQL to the AI agent.

All business writes must pass through backend validation.

Use SQLAlchemy ORM.

Use Alembic migrations.

Use Redis only for caching and conversation state.

Treat PostgreSQL as the single source of truth.

Follow enterprise coding standards.
