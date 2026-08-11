# SetuHaul AI
# API Specification

Version: 1.0

---

# Overview

This document defines every REST API required for the SetuHaul AI platform.

The backend is implemented using FastAPI.

All APIs return JSON.

Authentication uses JWT issued by Supabase Authentication.

Every API response must follow the same response format.

---

# Base URL

/api/v1

---

# Standard Response

Success

{
    "success": true,
    "message": "Operation completed successfully.",
    "data": {},
    "timestamp": "",
    "request_id": ""
}

Failure

{
    "success": false,
    "message": "Validation failed.",
    "errors": [],
    "timestamp": "",
    "request_id": ""
}

---

# Authentication

Authorization

Bearer <JWT_TOKEN>

Roles

Driver

Operations Executive

Warehouse Planner

Facility Manager

Transport Manager

Regional Operations Head

Admin

---

# Module 1

Authentication

------------------------------------------------

POST

/auth/login

Description

Authenticate user.

Returns

JWT

User

Role

Permissions

------------------------------------------------

POST

/auth/logout

Description

Logout current user.

------------------------------------------------

GET

/auth/me

Description

Returns current authenticated user.

------------------------------------------------

POST

/auth/refresh

Description

Refresh JWT.

------------------------------------------------

POST

/auth/change-password

Description

Change password.

------------------------------------------------

POST

/auth/forgot-password

Description

Generate password reset.

---

# Module 2

AI Chat

------------------------------------------------

POST

/chat

Description

Primary AI endpoint.

Accepts natural language.

Example

"I'll reach by 7 PM."

Returns

AI response

Suggested actions

Updated conversation

------------------------------------------------

GET

/chat/history

Returns

Conversation history.

------------------------------------------------

GET

/chat/history/{thread_id}

Returns

Entire thread.

------------------------------------------------

DELETE

/chat/history/{thread_id}

Deletes conversation history.

------------------------------------------------

POST

/chat/feedback

User feedback on AI response.

---

# Module 3

Driver APIs

------------------------------------------------

GET

/driver/profile

Driver details.

------------------------------------------------

GET

/driver/current-shipment

Current shipment.

------------------------------------------------

GET

/driver/appointments

Current appointment.

------------------------------------------------

GET

/driver/facility

Assigned facility.

------------------------------------------------

GET

/driver/eta

Current ETA.

------------------------------------------------

POST

/driver/update-eta

Update ETA.

------------------------------------------------

GET

/driver/history

Past shipments.

---

# Module 4

Shipment APIs

------------------------------------------------

GET

/shipments

List shipments.

Supports

Pagination

Filtering

Sorting

------------------------------------------------

GET

/shipments/{shipment_id}

Shipment details.

------------------------------------------------

GET

/shipments/{shipment_id}/timeline

Shipment timeline.

------------------------------------------------

GET

/shipments/{shipment_id}/eta

Latest ETA.

------------------------------------------------

GET

/shipments/search

Search shipments.

---

# Module 5

Appointment APIs

------------------------------------------------

GET

/appointments

List appointments.

------------------------------------------------

GET

/appointments/{appointment_id}

Appointment details.

------------------------------------------------

POST

/appointments/book

Book appointment.

------------------------------------------------

POST

/appointments/reschedule

Reschedule appointment.

------------------------------------------------

POST

/appointments/cancel

Cancel appointment.

------------------------------------------------

POST

/shipments/{shipment_id}/appointments/{appointment_id}/cancel

Cancel an active in-scope appointment. Requires `Idempotency-Key`.

Allowed: assigned Driver, scoped Operations, Admin.

------------------------------------------------

POST

/shipments/{shipment_id}/appointments/{appointment_id}/confirm

Confirm a pending appointment. Requires `Idempotency-Key`.

Allowed: scoped Operations and Admin only.

------------------------------------------------

GET

/appointments/available-slots

Returns

Available dock slots.

---

# Module 6

Scheduling APIs

------------------------------------------------

POST

/scheduler/find-slots

Returns

Top available slots.

------------------------------------------------

POST

/scheduler/recommend

Returns

AI ranked recommendations.

------------------------------------------------

POST

/scheduler/validate

Validate appointment.

------------------------------------------------

POST

/scheduler/book

Book validated slot.

---

# Module 7

Facilities

------------------------------------------------

GET

/facilities

All facilities.

------------------------------------------------

GET

/facilities/{facility_id}

Facility details.

------------------------------------------------

GET

/facilities/{facility_id}/docks

Dock status.

------------------------------------------------

GET

/facilities/{facility_id}/queue

Current queue.

------------------------------------------------

GET

/facilities/{facility_id}/rules

Facility rules.

---

# Module 8

Drivers

------------------------------------------------

GET

/drivers

List drivers.

------------------------------------------------

GET

/drivers/{driver_id}

Driver profile.

------------------------------------------------

GET

/drivers/{driver_id}/shipments

Driver shipments.

------------------------------------------------

GET

/drivers/{driver_id}/exceptions

Driver exceptions.

---

# Module 9

Exceptions

------------------------------------------------

GET

/exceptions

All exceptions.

------------------------------------------------

GET

/exceptions/{exception_id}

Exception details.

------------------------------------------------

POST

/exceptions/create

Create exception.

------------------------------------------------

POST

/exceptions/update

Update exception.

------------------------------------------------

POST

/exceptions/resolve

Resolve exception.

---

# Module 10

Dashboard

------------------------------------------------

GET

/dashboard/summary

Returns

KPIs.

------------------------------------------------

GET

/dashboard/recent-activity

Recent events.

------------------------------------------------

GET

/dashboard/charts

Dashboard charts.

---

# Module 11

Analytics

------------------------------------------------

GET

/analytics/delay-trend

------------------------------------------------

GET

/analytics/dock-utilization

------------------------------------------------

GET

/analytics/carrier-performance

------------------------------------------------

GET

/analytics/driver-performance

------------------------------------------------

GET

/analytics/facility-performance

------------------------------------------------

GET

/analytics/heatmap

---

# Module 12

Notifications

------------------------------------------------

GET

/notifications

------------------------------------------------

POST

/notifications/read

------------------------------------------------

POST

/notifications/send

(Admin only)

---

# Module 13

Users

------------------------------------------------

GET

/users

------------------------------------------------

GET

/users/{user_id}

------------------------------------------------

POST

/users

------------------------------------------------

PUT

/users/{user_id}

------------------------------------------------

DELETE

/users/{user_id}

Admin only.

---

# Module 14

Roles

------------------------------------------------

GET

/roles

------------------------------------------------

POST

/roles

------------------------------------------------

PUT

/roles/{role_id}

------------------------------------------------

DELETE

/roles/{role_id}

---

# Module 15

Audit Logs

------------------------------------------------

GET

/audit-logs

Supports

Date

User

Action

Entity

---

# Module 16

API Logs

------------------------------------------------

GET

/api-logs

Supports

Date

Endpoint

Status

Execution Time

---

# Error Codes

400

Validation Error

401

Unauthorized

403

Forbidden

404

Resource Not Found

409

Conflict

422

Validation Failed

429

Rate Limit

500

Internal Server Error

---

# Pagination

Query Parameters

?page=1

&page_size=20

&sort_by=created_at

&sort_order=desc

---

# Filtering

Supported

status

priority

facility

carrier

driver

shipment

date

---

# API Documentation

FastAPI must automatically expose

/docs

Swagger UI

/redoc

ReDoc Documentation

---

# Logging

Every request must generate

Request ID

Execution Time

User

Endpoint

Status

Audit Log (when applicable)

API Log

---

# Security

JWT Authentication

Role Based Authorization

Input Validation

SQL Injection Protection

Rate Limiting

CORS Protection

HTTPS Only

---

# Performance Targets

Average API Response

< 500 ms

AI Response

< 5 seconds

Dashboard

< 2 seconds

---

# Future APIs

The architecture should support future additions without breaking existing APIs.

Examples

WhatsApp Integration

Slack Integration

Microsoft Teams

Email Notifications

Voice Assistant

OCR

Document Upload

Vehicle Tracking

GPS Integration

ERP Integration