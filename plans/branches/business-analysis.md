# Business analysis branch

## Primary outcome

Success is not “the chatbot answered.” Success is a feasible, current, clearly communicated operating plan that does not conflict with another driver.

## Primary actors

- Driver: report, clarify, compare, select, change, cancel, and check status.
- Operations executive: triage exceptions and monitor ETA/appointment outcomes.
- Warehouse planner/facility manager: own capacity, rules, queues, and human takeover.
- Transport/regional managers: monitor fleet/facility performance and policy outcomes.
- Administrator: manage identities/configuration, not silently override operational policy.
- Carrier/customer contacts: receive updates or provide approvals outside driver chat.

## MVP scope

The team POC at Sprint 2 is a simple internal POC: two login entries (Driver + Ops), authenticated Driver chat/profile/logout, atomic exception and ETA/status coordination, plus one timestamped read-only Ops dashboard (Operator facility-scoped and/or Admin global RO via JWT) of stored schedules, docks, slots, rules, and constraints. It does not claim feasibility, change appointment/capacity state, expose maps/GPS, or include user management.

The Sprint 3 challenge MVP then adds:

- Authenticated context and minimal disambiguation.
- Exception thread and ETA history.
- Deterministic feasibility and explainable ranking.
- Explicit option/request/pending/confirmed/cancelled/conflicted language.
- Atomic request/reschedule/cancel and manual escalation.
- Operations exception visibility and audit trail.
- Supplied UI conversion, RBAC, API logging, and concurrency proof.

## Business policy to ratify

Hard feasibility precedes every priority rule. Protect committed/in-progress work, then consider service priority, actual waiting/lateness, earliest feasible arrival, and stable request order. Overrides require named permission, reason, and audit.

## Demonstration acceptance

Sprint 2 POC acceptance:

- Driver and Ops use two entry screens (`/driver/login`, `/ops/login`) but are authorized only by their verified server-side identity. Operator and Admin share one dashboard UI; JWT sets facility vs global RO scope.
- Driver profile/context, logout, ETA clarification/confirmation, retry, return-later status, and cross-driver denial work.
- Ops dashboard shows the matching ETA/exception and timestamped schedule/dock/rule state for the caller's scope.
- A slot request receives an explicit deferred-capability/operations response and creates no appointment write.
- No maps, GPS, user management, or booking mutations in the POC.

Sprint 3 challenge acceptance:

- A driver provides an incomplete delay report and is asked only for missing information.
- Repair duration is not misrepresented as the new ETA.
- Several requests compete for one facility window.
- Two users choose one slot and exactly one succeeds.
- A displayed option changes/disappears and is safely refreshed.
- A no-feasible-slot case ends in human escalation.
