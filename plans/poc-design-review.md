# SetuHaul POC design review

Date: 2026-08-07  
Decision: use `designs/stitch_setuhaul_ai_logistics_platform_2` as the POC visual foundation.  
Owner POC contract (authoritative for Sprint 1–2 UI): **two login screens only** — Driver and Ops (Admin/Operator). Simple internal POC; no maps, GPS, user management, or booking mutations.

## POC users and jobs

- Driver, often on a phone or small cab-mounted screen: report a delay, ask about the active shipment/appointment, update ETA, use light context/quick actions, open **profile**, and **logout**.
- Operator or Admin on desktop via **one ops entry**: view a single read-only **dashboard** with operational detail (shipments, exceptions, schedule, docks, rules). JWT role decides facility vs global RO scope. **Logout** required; user management is out of scope.

The interface should feel calm, trustworthy, and operational. Chat and verified status lead; decorative network intelligence does not.

## Candidate assessment

| Candidate | Strengths | POC concerns | Decision |
|---|---|---|---|
| Stitch set 2 login | Clear hierarchy, conventional form, consistent dark enterprise palette | Decorative KPIs and “access token” wording are unsupported | Reuse with Supabase email/password fields and an Internal POC label; ship as `/driver/login` and `/ops/login` only |
| Stitch set 2 driver assistant | Readable chat, obvious active context, practical quick actions | Three-column density, route/GPS/map and vehicle stats exceed the brief | Selected; reduce to chat plus compact context + profile/logout |
| Stitch set 2 operations dashboard | Most readable dashboard hierarchy and reusable cards | Network graph, fleet scale, and broad navigation are excessive | Selected; one shared ops dashboard for Operator and Admin |
| Stitch set 1 driver assistant | Strong visual identity and focused central chat | Monospaced command-centre style, routing emphasis, dense side rails | Keep as later visual reference |
| Stitch set 1 dashboard | Distinct operations aesthetic | Too dense for the POC and dominated by fictional network/fleet information | Defer |

## POC screen set

### 1. Internal POC Supabase role entry (two screens)

- **Only** `/driver/login` and `/ops/login` (Admin/Operator label on the ops entry is fine). Reuse one compact card and shared authentication form labelled `Internal POC`.
- Prefer shared Driver + shared Ops Auth accounts. Seeded Operator and Admin personas may both exist; they use the **same** `/ops/login` and land on the **same** dashboard shell. Portal/entry choice never grants authority.
- FastAPI `/auth/me` determines the verified role and destination. Wrong-entry sign-in offers the correct entry, and return URLs are local-only.
- Never display or accept a database user/driver ID as ownership evidence; FastAPI maps the verified Supabase subject to fixed seeded context.
- Loading, invalid credentials, rate-limited, expired-session, configuration-error, and connection-error states.
- No decorative operational metrics unless backed by a real read API.
- Do **not** require three distinct branded login UIs. Scaffold `/operator/login` / `/admin/login` should consolidate or redirect to `/ops/login`.

Shared credentials are replaced by individual Supabase accounts before production. The screen and session integration remain reusable.

### 2. Driver after login

- Primary region: conversation transcript and composer (Sprint 2 mounts chat; Sprint 1 ships shell + reads).
- Compact active context: shipment code, latest ETA plus freshness/source, facility, appointment status/time.
- Quick actions: Update ETA, View appointment, Facility details.
- Accessible **profile section/menu**: safe driver identity, carrier/vehicle context when available, facility, session state, and **logout**.
- Tool/action states: thinking, retrieving, clarification required, confirmation required, success, stale data, conflict, escalation, dependency error.
- Clearly label slot options as not reserved until the Sprint 3 lifecycle is implemented.
- Mobile-first responsive treatment: context becomes a drawer/card; no persistent left navigation is required for the POC.
- No maps, GPS, or route planner.

### 3. Ops dashboard (Operator and Admin)

- One shared read-only dashboard shell after `/ops/login`.
- KPI cards and operational detail: active/delayed shipments, waiting trucks, operational docks now, open exceptions, appointment schedule, dock/slot snapshot, facility rules/constraints—each with scope and `as_of`. More observational detail is fine for the POC.
- Compact exception list with shipment, driver, facility, latest ETA, current appointment, status, and age.
- JWT role: Operator = facility-scoped; Admin = global read-only (ADR 005).
- Selecting an exception may open details, but no scheduling or business mutation controls exist in the POC.
- **Logout** required. No separate Admin-only configuration overview in Sprint 1–2.

The POC displays stored schedule and operational facts only. It does not calculate shipment-feasible replacement slots or expose book/reschedule/cancel/confirm actions; those begin in Sprint 3.

## Remove from POC

- Live GPS, maps, alternate routing, route planner, and bypass suggestions.
- Vehicle fuel/tyre telemetry.
- Network topology and fictional fleet scale.
- Predictive maintenance and predictive ETA.
- Full shipment/fleet/analytics/settings navigation and user management.
- Notification centre, exports, advanced charts, and decorative activity feeds.
- Three separately branded portal login experiences.

## Product-specific signature

Use a single “verified operational context” card beside the chat. Every value shows its state and freshness, for example `Latest driver-declared ETA - 19:10 - declared 2 min ago` or `Appointment - pending warehouse confirmation`. This directly expresses the FDE challenge's central distinction between conversation and trustworthy operational truth.

## Acceptance checks

- A driver can understand the active shipment and send a message without navigating elsewhere (Sprint 2).
- No screen implies that a displayed slot is reserved or confirmed.
- Every dashboard value comes from seeded data through an application service.
- Driver and Ops entry routes share one auth implementation and are redirected by the verified backend role, not entry selection.
- Driver and Ops profile/logout flows clear protected browser state and prevent cached back-navigation disclosure.
- Operator aggregates and details are facility-scoped before aggregation; Admin visibility on the same dashboard matches the ratified matrix.
- Schedule, dock, slot, rule, and constraint data is timestamped and observational; no POC control implies feasibility, reservation, or confirmation.
- Missing, stale, pending, conflicted, and unavailable states are visually distinct without relying on color alone.
- Keyboard focus, labels, contrast, and screen-reader announcements cover chat and action status.
- Indian facility names, time zones, and challenge terminology replace the US routing examples in the source designs.
