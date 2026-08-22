# SetuHaul — Production-Grade Dock Coordination Platform (Architecture Blueprint)

## Context

**Why this document exists.** You asked, as an architect + BA + AI engineer, what production-level
application can be built on the SetuHaul material: a driver-facing conversational layer, operations
staff, admins, facilities, docks. The inputs are the FDE challenge brief (§1–13), the shipped
classroom database (18 tables, 2 facilities, 9 docks, 106 slots, 21 shipments, seeded edge cases),
and your Scheduling Algorithm report (3-stage engine: hard-constraint filter → weighted scoring →
transactional FCFS).

**The insight that shapes everything below.** The brief says it plainly (§6): the LLM is *not* the
product. The product is a **trustworthy allocation system for scarce dock capacity**, wrapped in a
conversational front door. Success (§13.1) is not "the chatbot answered" — it is *"a driver
exception becomes a feasible, current and clearly communicated operating plan without creating a
conflict for another driver."* Every architectural choice below serves that sentence.

**Intended outcome.** A blueprint you can build against and defend in a review: personas and
surfaces, module map, the promise lifecycle state machine, the decision engine, the concurrency
correctness model, the data-model additions the classroom DB deliberately withheld, the AI layer's
contract, observability, and a phased roadmap with provable acceptance criteria.

---

## 0. Locked decisions (agreed 2026-08-19)

| # | Decision | Consequence |
|---|---|---|
| D1 | **Capacity = dock-time intervals**, not fixed slot rows | `appointment_slots` demotes to a *publishing* layer; a new `dock_occupancy` table becomes the booking authority with a Postgres `EXCLUDE` constraint. Fixes the 75-min-in-60-min defect. |
| D2 | **Soft hold with TTL** between SHOWN and PENDING_CONFIRMATION | Holds live in the *same* table as bookings under the *same* overlap constraint — one source of overlap truth. Lazy expiry + sweeper. |
| D3 | **Per-driver ranking + facility sequencer** (§7.3 in scope) | Rule-based greedy over a rolling horizon first, OR-Tools swappable behind the same interface. Requires fixed-work and plan-stability modelling. |
| D4 | Deliverable shape | **This document.** Requirements and design are agreed; tech stack and deployment remain **deliberately deferred**. The latency and region material is therefore **not binding** and has been moved to Appendix A, marked provisional — it is worked-through reasoning to draw on once a stack is chosen, not a decision this document makes. |
| D5 | **Sequencer proposes; a planner applies** | No automatic re-promising. Sequencer output is a reviewable artifact (`scheduling_runs`), never a silent write. |
| D6 | **Human planner always confirms** PENDING → CONFIRMED | No rules-based auto-confirm, no LLM confirm. Makes the planner console the throughput-critical surface (see below). |
| D7 | **Allocation policy = the scored formula as specified**, no fairness term | Accepted trade-off, monitored rather than mitigated (see below). |
| D8 | **Generate to brief scale** — 6 facilities, 24–32 docks, 600–1000 shipments, 2000–3000 slots, **across a seven-day window** (full volumes in §9.1) | All 29 seeded edge cases preserved verbatim; volume layered on top. The seven days are what make Stage 0's next-day path testable rather than theoretical. |

| D9 | **Pending TTL = 15 min**, then release + escalate | Unactioned requests reach the escalation queue, not the bin. Driver is notified on release either way. |
| D10 | **Changeover buffer = 15 min fixed** | Occupancy window = `expected_unload_min + 15`. Absorbs small overruns instead of cascading them. |
| D11 | **Start granularity = 15-minute grid** | Offers land on :00/:15/:30/:45 — legible, comparable, short option lists. |
| D12 | **Backfill = preserve start, extend to true duration, flag conflicts** | Migration produces a planner worklist. Nothing is silently moved (consistent with D5). Two worklist classes: `REQUIRES_TIME_RESOLUTION` for true-interval overlaps (§6.2 #1; **85 of 655 live active appointments**, D15), and `REQUIRES_DOCK_REASSIGNMENT` for weight violations (§6.2 #7; **116 of 655 live**) — the latter cannot be fixed by shifting time, so it needs a different queue and a different decision from the planner. |
| D13 | **Migrate the live database in place; keep existing history** | The 1,542 chat messages, 264 exceptions and 405 check-ins already in Supabase are real fixtures, not scratch data — regenerating would throw away work rather than fix a defect. See §9.4. |
| D14 | **Rebase Layer A onto the Layer B window; snapshot clock moves to 2026-08-13** | Layer A (2026-08-04, 2 facilities) and Layer B (2026-08-10→16, 6 facilities) never coexist today, so the seeded edge cases can never be demonstrated against realistic multi-facility load. 08-13 sits midweek in the generated window with three days of history behind it and three ahead — see §9.1. |
| D15 | **Keep the live weight/overlap violations as the D12 worklist; add what §11.3 is still missing** | 116 weight violations and 85 true-interval overlaps stay as realistic dirty data proving the backfill path, rather than being cleaned away. Separately, add the imperfections §11.3 requires but the live generator has not yet produced: intraday facility rules (14 rules, zero with `effective_to`), capacity incidents beyond Jaipur (3 events across 25 docks), inconsistent location spellings. |
| D16 | **Schema migration runs directly on production, behind a backup — no Supabase branch** | Simpler and free; recovery is a restore rather than a branch discard. Take the backup immediately before §9.4 step 1. |

### What D10 + D11 do to real capacity — and where contention actually comes from

Occupancy window = unload + 15 min changeover. So a 75-minute unload consumes 90 minutes of dock time;
a 60-minute unload consumes 75. Jaipur runs 06:00–22:00 (960 min) across 4 standard docks (D1–D4),
which is roughly **10–12 trucks per dock per day, ~45 standard movements per day at that facility**.

Now compare with the brief's own numbers (§1.1): 190–240 appointments/day across 6 facilities and 32
docks — about **6–7.5 appointments per dock per day**. Average utilisation therefore sits near 60–70%,
*not* saturation.

**The conclusion matters for D8's generator:** contention in this business is not created by daily
volume. It is created by **demand clustering into a narrow window** — the evening peak, one blocked
reefer dock, one dock down for repairs. If the generator simply raises daily totals, the 10-drivers /
3–4-slots scenario will never occur naturally. It must concentrate demand: a Jaipur evening block
(17:00–21:00) with far more standard-dock ETAs than compatible intervals, while the rest of the day
stays realistically slack. That is what makes the scarcity real rather than staged — and it mirrors
the brief's own framing: *"one delay is manageable, a wave of delays is not."*

### The D2 + D6 interaction — the one real risk in this design

Under D1, a `PENDING_CONFIRMATION` row **occupies dock capacity** via the exclusion constraint. Under
D6, every one of those rows waits for a human. At brief scale that is 190–240 appointments/day against
5 coordinators per shift, with 20–35 messages arriving inside 30 minutes during a disruption spike
(§1.1). Unattended pendings will silently sterilise the evening's capacity.

**Therefore D6 makes three things mandatory, not optional:**

1. **Pending expiry is a correctness feature, not hygiene.** Every `PENDING_CONFIRMATION` carries a
   deadline; on expiry the interval is released and the driver is told. Without it, D6 + D1 deadlocks
   capacity.
2. **The planner console is the highest-throughput surface in the product.** Design it for triage
   speed: one screen, keyboard-driven confirm/reject, bulk confirm for non-conflicting requests,
   ageing indicators, and the decision receipt inline so the planner does not have to reconstruct
   *why* this slot was proposed. Treat it as the primary UI, not an admin afterthought.
3. **Queue-depth and time-to-confirm become tier-1 SLOs.** "Median seconds from PENDING to planner
   action" and "pendings expired unactioned" go on the ops dashboard beside the KPIs in §8.

### D7 — accepted trade-off, made visible

Without a fairness term, a carrier with many CRITICAL loads can repeatedly win scarce evening capacity
(§9.2 "fairness across carriers"). We are accepting that: the policy stays simple, deterministic, and
easy to explain — which has real defensive value in a review. The mitigation is **visibility, not
mechanism**: ship a *carrier concentration* metric (share of contested slots won per carrier per
facility per day) on the analytics surface. If the number turns ugly in practice, the fairness penalty
already has a defined place in the formula and a policy version to land in. Document it as a knowingly
deferred decision rather than an oversight.

### D8 — how the generator must behave

Volume is layered *on top of* the shipped seed, never in place of it. The 29 documented cases
(§6 of the database guide) keep their exact ids and timestamps — SHP1015's impossible reefer,
THR009's duplicate, THR010's ambiguous driver, APT1018's no-show, DEVT001–003. Generated traffic
supplies contention density: enough evening standard-dock demand at Jaipur that the 10-drivers /
3–4-slots scenario (§11.2) arises naturally rather than being staged.

### D1 in concrete terms

Replace "one appointment → one 60-minute slot row" with an interval booking guarded by the database.

**Two preconditions, checked against the live project on 2026-08-19 and currently both false.** Writing
these down converts D1 from a design statement into an executable one — without them, the `CREATE TABLE`
below fails on the first attempt at step 5:

1. **`btree_gist` must be installed.** The live Supabase project shows `installed_version: null`. The
   `CREATE EXTENSION` statement below is already correct; it has simply never been run.
2. **Every timestamp column must be `timestamptz`.** The live project stores `slot_start_ts`,
   `slot_end_ts`, `declared_eta_ts`, `gate_in_ts` and every other timestamp as **`text`**, carried over
   verbatim from the SQLite seed. `tstzrange` and the exclusion constraint below cannot be built on top
   of text columns — the conversion (§9.4) is not optional cleanup, it is load-bearing for D1.

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE dock_occupancy (
    occupancy_id   text PRIMARY KEY,
    dock_id        text NOT NULL REFERENCES docks(dock_id),
    shipment_id    text NOT NULL REFERENCES shipments(shipment_id),
    appointment_id text REFERENCES appointments(appointment_id),
    window         tstzrange NOT NULL,          -- unload + changeover buffer
    state          text NOT NULL
                   CHECK (state IN ('HELD','PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS',
                                    'COMPLETED','CANCELLED','EXPIRED','NO_SHOW','REJECTED')),
    expires_at     timestamptz,                 -- HELD only
    policy_version text NOT NULL,
    created_at     timestamptz NOT NULL DEFAULT now(),

    -- one truck per dock per instant, across every state that occupies capacity
    EXCLUDE USING gist (
        dock_id WITH =,
        window  WITH &&
    ) WHERE (state IN ('HELD','PENDING_CONFIRMATION','CONFIRMED','IN_PROGRESS'))
);
```

Why this is stronger than what shipped: `ux_active_appointment_per_slot` can only prevent two rows
claiming the *same* slot id. It cannot prevent a 75-minute unload booked at 11:00 from colliding with
a booking at 12:00 — because those are different slot rows. The exclusion constraint makes overlap
itself impossible, which is the invariant we actually need.

**What survives from the shipped schema:** `ux_current_active_appointment_per_shipment` (one active
appointment per shipment) stays, unchanged. `appointment_slots` stays as the warehouse's *published
offer grid* — what the facility is willing to sell — while `dock_occupancy` records what is actually
taken. The two are reconciled by the feasibility engine, not by the driver.

**Three things D1 forces us to decide (open, see discussion):** changeover buffer between trucks;
candidate start-time granularity (15 min? free-form?); and how to backfill the four seeded
appointments whose true durations now genuinely conflict.

### D2 in concrete terms

A hold is a `dock_occupancy` row in state `HELD` with `expires_at = now() + ttl`. Because it sits
under the same exclusion constraint, a hold blocks a competing booking automatically — no second
locking mechanism, no drift between "held" and "booked" bookkeeping.

- **Expiry is lazy plus swept.** Every read filters `state='HELD' AND expires_at > now()`; a sweeper
  transitions stale rows to `EXPIRED`. Never depend on the sweeper for correctness — only for hygiene.
- **Default TTL 90 s**, per-facility configurable. A driver on a bad connection who misses the window
  gets a clear "that hold lapsed, here are current options" message, never a silent failure.
- **Holds are never shown as bookings.** The driver sees "reserved for you for 90 seconds" — distinct
  wording from "requested" and from "confirmed".

---

## 0.9 Requirements — what is actually needed

> Tech stack and deployment are deliberately *not* decided here. The latency and region analysis lives in
> **Appendix A** and is provisional — it assumes a stack that has not been chosen.

### The irreducible core

Strip everything optional and the system must still do exactly this:

> Accept a driver's free-text delay message → identify the right shipment and appointment → establish
> a revised arrival time → compute which dock intervals are genuinely feasible → let the driver choose
> one → bind that choice without ever promising the same capacity twice → get a human to confirm it →
> tell the driver the truth at every stage → and escalate to a person when there is no safe answer.

Anything that does not serve that sentence is a **SHOULD** or lower.

### MUST — the system is not credible without these

| # | Requirement | Done when |
|---|---|---|
| M1 | **Identify the conversation's shipment** — including when the driver has more than one | DRV004/THR010 resolves by clarification; never guesses; escalates after 2 failed attempts |
| M2 | **Establish an effective ETA** from plan / driver declaration / gate-in, with confidence | `v_latest_eta` equivalent; gate-in overrides ETA; LOW confidence blocks silent commitment |
| M3 | **Deterministic feasibility** — hard constraints evaluated in code, never by the LLM | Every constraint in §5 Stage 1 enforced; SHP1015 correctly returns zero *same-day* options, by rule rather than by accident |
| M4 | **Deterministic ranking** with a reproducible receipt | Same snapshot + policy version → byte-identical order, twice |
| M5 | **The four-state promise lifecycle** — SHOWN / HELD / PENDING / CONFIRMED, visibly distinct | Each state has its own reviewed template; no state message says "booked" below CONFIRMED |
| M6 | **Capacity can never be double-promised** | DB-enforced (D1 exclusion constraint); 50-way race yields exactly 1 winner |
| M7 | **Human confirms** PENDING → CONFIRMED (D6) | No code path lets the LLM or a rule confirm |
| M8 | **Pending expiry releases capacity** (D9, 15 min) | Unactioned request releases + notifies + escalates |
| M9 | **Idempotent intake** — duplicates and retries cannot double-act | THR001/THR009 → 1 exception, 1 booking attempt, 1 notification |
| M10 | **Stale options are refused, not applied** | Snapshot drift and stale ordinals both rejected with a refresh |
| M11 | **Escalation when no safe automated outcome exists** | Every reason in §7.4 raises an owned, SLA-tracked item |
| M12 | **Ops takeover** — human joins the thread, assistant stands down | Thread → ESCALATED, human posts as OPERATIONS, driver is told |
| M13 | **Gate/yard truth is captured** | gate-in, queue state, dock-in, unload start/end, gate-out all writable |
| M14 | **Audit** — every state change and every agent action is reconstructable | Who, what, when, which policy version, which tool call |
| M15 | **RBAC with scope** | Driver sees only own shipments; carrier only own fleet; facility only own docks |

### SHOULD — needed for the system to be *good*, not merely correct

S1 Facility sequencer (D3/D5) with proposal-and-approve · S2 Planner bulk-confirm under the safe
predicate · S3 Counter-offer affordance · S4 Capacity-incident batching (one incident, not N) ·
S5 Outbound event notifications (expiry, withdrawal, dock down) · S6 Carrier portal ·
S7 KPI/analytics surface (§13.1) · S8 Ops-side assistant co-pilot.

> **S8's original slot (a WhatsApp channel adapter) was cut from v1 scope** — see the UI-UX design's
> "Spec divergence" note (`UI-UX/README.md`). The driver surface is PWA-only; every reference to WhatsApp
> below has been reconciled to match.

### COULD — real value, no dependency

C1 OR-Tools CP-SAT sequencer · C2 Predictive ETA from history · C3 Hindi/Hinglish templates ·
C4 Detention/overtime cost modelling · C5 Carrier scorecards · C6 Voice intake.

### WON'T — explicitly out of scope (§12.3)

National network optimisation · carrier selection and rate negotiation · autonomous driver-safety
decisions · customs, hazmat and legal compliance · commercial penalty approval · live GPS tracking ·
**shipment creation and driver/vehicle assignment**.

Say these out loud in any review. Naming what you deliberately excluded reads as judgement; leaving it
unsaid reads as an oversight.

The last one is easy to leave implicit and shouldn't be: §1 already states the boundary, but it belongs in
this list too, next to the item it is closest to in spirit. "Carrier selection and rate negotiation" is
the *commercial* decision of which carrier gets a load; "shipment creation and driver/vehicle assignment"
is the *operational* decision of which driver and truck a carrier sends — both are TMS/carrier territory,
both happen before SetuHaul ever sees the shipment, and neither has a tool, screen, or role anywhere in
this design that performs it. If that ever needs to change, it is a new integration with the TMS, not an
extension of an existing SetuHaul surface.

### Traceability — the brief's own 13 questions are the acceptance criteria

| §12.1 question | Answered by |
|---|---|
| 1 · What must be collected before options are shown? | M1, M2 + clarification policy (§7.2b) |
| 2 · How is the conversation tied to driver/shipment/appointment? | M1 |
| 3 · How is revised arrival determined and uncertainty communicated? | M2 + confidence framing |
| 4 · What makes a slot feasible? | M3 — Stage 1, eight invariants (two corrected against the data) + four additions |
| 5 · What does "available" mean while others are deciding? | D2 — HELD with TTL; SHOWN reserves nothing |
| 6 · When does an option become hold / request / booking? | M5 — the four-state machine |
| 7 · How are simultaneous requests ordered? | M4 ranking + M6 first-committed-wins |
| 8 · When is a facility-wide schedule recalculated? | S1 — event-driven triggers, debounced |
| 9 · Stale options, cancellations, duplicates, retries? | M9, M10 |
| 10 · What happens when there is no feasible slot? | Stage 0 — `NO_SAME_DAY_SLOT` offers dated next-day options first; M11 escalates only when the whole horizon is exhausted |
| 11 · What is explained when the preferred slot is not granted? | M4 receipt, narrated not invented |
| 12 · Which decisions need human approval? | M7, M12 + §9.3 of the brief |
| 13 · How do you prove no double-booking? | M6 + §10 verification |

**§12.2's expected demonstration** maps to: M1+M2 (report + clarify) · M3+M4 (options + compare) ·
M6 (competing requests) · M10+S5 (option changes or disappears) · M11 (escalation) · S1 (optional
scheduling tool).

### v1 persona scope (agreed)

**In:** Driver · Ops coordinator · Warehouse planner · Gate/yard officer · Carrier manager · Administrator.
**Deferred:** Facility manager · Regional ops head.

Two consequences follow, and both are cheaper to handle now than later:

1. **Multi-tenancy is a v1 concern, not a later one.** Including the carrier manager means carrier
   scoping must be enforced in the data-access layer from the first query — a carrier may see only its
   own drivers, vehicles, shipments and exceptions, and must never see another carrier's ranking
   position, competing requests, or why it lost a contested interval. Retrofitting tenant scoping onto
   a system that assumed a single trusted operator is one of the most expensive rewrites in this class
   of application. M15 therefore moves from "auth requirement" to **foundational architecture**: scope
   is derived from the authenticated identity and enforced in the repository layer, never accepted
   from a client-supplied id.
2. **Deferring the two oversight personas leaves the §13.1 KPIs without an owner.** Resolution: split
   them. The *operational* metrics — queue depth, median time-to-confirm, pending expiry rate,
   escalations by reason — are how a planner runs their own shift, so they belong on the planner/ops
   console in v1. The *strategic* set — cross-facility utilisation trends, priority-policy violations,
   carrier concentration (the D7 canary) — travels with the deferred personas. Do not drop the
   measurement; only the dedicated surface is deferred, so keep emitting the events either way.

### What is genuinely *not* needed (resist building these)

- A second LLM to check the first one — determinism is enforced by code and constraints, not review.
- A slot-hold table separate from bookings — one table, one overlap truth (D2).
- Per-facility custom allocation policies in v1 — one versioned policy (D7).
- A general reporting engine — nine named KPIs, not an ad-hoc query builder.
- Live GPS — the brief excludes it twice, and the data model has no place for it.

---

## 1. What the app is (one paragraph)

**SetuHaul Dock Command** — a multi-facility, multi-tenant dock appointment and driver-exception
platform with three planes:

| Plane | Owner | Responsibility |
|---|---|---|
| **Conversation plane** | Drivers, via chat (PWA; web push for outbound events) | Understand messy free text, clarify, explain, confirm. Never decides. |
| **Decision plane** | Deterministic scheduling engine | Feasibility, ranking, allocation, concurrency. Never interprets free text. |
| **Control plane** | Ops, planners, gate, facility, admin | Confirm/reject, takeover, capacity events, policy, audit. Human authority. |

The hard boundary between planes *is* the architecture. It is what makes the system defensible.

**A fourth boundary sits upstream of all three, and it is just as load-bearing: SetuHaul does not create
shipments or assign drivers and vehicles to them.** Per the brief's own data-flow table (§3), that is TMS
territory — a carrier's Transportation Management System creates the load and assigns a driver and truck
to it (§2.1, stages 1–2) *before* the shipment is anything SetuHaul knows about. SetuHaul's world begins at
stage 3, the warehouse appointment, and everything this document designs — the conversation, the
scheduling engine, the control-plane surfaces — operates on shipments that already carry a `driver_id`,
`vehicle_id` and `carrier_id` as given facts. In this classroom build the generator (§9.1) stands in for
that upstream TMS, producing shipments pre-assigned; no tool, screen or role in this design ever creates
that assignment, and none should.

---

## 2. Personas → surfaces → data backing

Eight roles, five distinct UIs — **six roles in v1**. Do not build eight dashboards; build five
surfaces with RBAC.

| Persona | v1 | Surface | Primary jobs | Tables read/written |
|---|:--:|---|---|---|
| **Driver** | ✅ | Mobile-first chat (PWA) | Report delay, declare ETA, see options, choose, check status, cancel | `chat_threads`, `chat_messages`, `driver_exceptions`, `eta_updates`, `appointments` |
| **Ops coordinator** | ✅ | Exception console — live queue, takeover | Triage exceptions, resolve ambiguity, escalate, manual override | `driver_exceptions`, `escalation_queue`*, `chat_*`, `appointments` |
| **Warehouse planner** | ✅ | Dock board (Gantt, per facility, per day) | Confirm/reject requests, block docks, re-sequence, see conflicts | `appointment_slots`, `appointments`, `docks`, `dock_status_events` |
| **Gate / yard officer** | ✅ | Kiosk / tablet check-in | Gate-in, yard queue, call-to-dock, dock-in, unload start/end, gate-out | `facility_checkins` |
| **Transport / carrier manager** | ✅ | Carrier portal (scoped read) | Own fleet's shipments, exceptions, on-time performance | `shipments`, `drivers`, `vehicles` scoped by `carrier_id` |
| **Administrator** | ✅ | Admin console | Users, roles, `facility_rules`, **policy weights**, audit trail | `users`, `roles`, `user_scopes`*, `facility_rules`, `policy_versions`*, `audit_logs` |
| **Facility manager** | — | Facility health view | Utilisation, queue depth, detention, overtime risk | `v_current_facility_queue`, `facility_checkins`, derived KPIs |
| **Regional ops head** | — | Analytics | KPI trends across facilities, policy violations | Warehouse/mart tables |

`*` = tables you must add (§6). The brief (§10.5) deliberately withholds them — designing them is the
exercise. Note that `users`, `roles`, `audit_logs` and `api_logs` are *not* starred: they already exist in
`setuhaul_schema_and_seed.sql`, which ships 22 tables against the guide's documented 18 (see §6.1).

**Gate/yard is the persona most teams forget.** `facility_checkins` is the only source of *actual*
arrival truth (§5.3, §3). Without a gate surface writing those rows, the scheduler is blind to
reality and the whole "early truck / late truck / currently unloading" scenario (§7.3) is fiction.

---

## 3. Module map

1. **Driver Conversation** — threads, intent, clarification, options presentation, confirmations.
2. **Exception Intake** — free text → structured `driver_exceptions` row (typed, deduped, severity). Only
   when a problem is actually reported: browsing creates a thread and an option set, never an exception
   (§7.2b).
3. **ETA Service** — append-only `eta_updates`; effective ETA + confidence; never mutate history.
4. **Feasibility & Ranking Engine** — the 3-stage engine (§5).
5. **Allocation & Promise Lifecycle** — holds, requests, confirmations, cancellations (§4).
6. **Facility Sequencer** (optional extension, §7.3) — facility-wide re-sequencing across early/late/waiting/incoming trucks.
7. **Gate & Yard** — check-in events, queue state, dock occupancy, unload overrun detection.
8. **Capacity & Rules Admin** — dock status events, blocked slots, `facility_rules`, policy weights.
9. **Escalation & Human Takeover** — queue, SLA timers, ownership, resolution.
10. **Notification / Outbox** — warehouse email, driver web push / in-app, delivery status (`operational_messages`). **SMS was dropped from v1** — not free, and India's DLT registration with TRAI is a multi-step regulatory precondition rather than a config flag (`TECH-STACK/TECH_STACK.md` §6). The outbox keeps a pluggable channel adapter, so adding it later is not a rewrite.
11. **Observability & Audit** — traces, decision receipts, KPI marts.
12. **Identity & RBAC** — users, roles, scope (facility / carrier / driver).

---

## 4. The promise lifecycle — the single most important design

The brief asks it twice (§8.1 "Important interaction rule", §12.1 Q5/Q6): *showing ≠ reserving ≠
confirming.* Make it an explicit, persisted state machine, not an implied one.

```
        find_feasible_slots
                │
                ▼
        ┌───────────────┐   nothing found
        │   SHOWN       │──────────────────► ESCALATED (no feasible slot)
        │ not reserved  │                    → ops takeover queue
        │ + REC- token  │
        └───────┬───────┘
                │ driver picks exact slot_id (+ REC- token)
                ▼
        ┌───────────────┐  token stale / slot taken
        │     HELD      │────────────────────► CONFLICT_REFRESH
        │ soft, TTL 90s │                      (re-rank, re-show)
        └───────┬───────┘
                │ commit within TTL
                ▼
        ┌────────────────────────┐  planner rejects / TTL expires
        │ PENDING_CONFIRMATION   │──────────────────► slot released
        └───────┬────────────────┘
                │ planner confirms
                ▼
           CONFIRMED ──► IN_PROGRESS ──► COMPLETED
                │
                └──► CANCELLED / NO_SHOW (grace period, RULE002/RULE006)
```

**Design decisions to state explicitly (they are graded, §12.1):**

- **SHOWN reserves nothing.** Otherwise 10 drivers browsing freeze the whole evening. Each option
  set carries a `recommendation_id` (`REC-…`) + snapshot hash; presenting is free, cheap, repeatable.
- **HELD is a short, server-side soft lock** (60–120 s), created only when the driver *chooses*.
  It absorbs the "two drivers pick the same slot within seconds" case (§7.2) without holding capacity
  hostage during deliberation. Modelled as a `dock_occupancy` row in state `HELD` with `expires_at`
  (D2) — *not* as a separate hold table, so there is one overlap truth and no drift between "held" and
  "booked" bookkeeping. Held ≠ booked: no `appointments` row exists yet.
- **PENDING_CONFIRMATION is a real appointment row**, and its `dock_occupancy` interval keeps consuming
  capacity under the exclusion constraint. The seeded `APT1013A`/`APT1014A` rows prove the intended
  semantics — a requested slot is not available to anyone else. This is also precisely why D9's expiry is
  a correctness feature rather than hygiene: a pending row that nobody actions sterilises real capacity.
- **CONFIRMED requires a human or a warehouse system reply.** §6.3: the AI must not decide "whether a
  booking is committed successfully in the system of record." `OM004` (FAILED email) is seeded
  precisely to teach that *a sent message is not a confirmation*.
- **What the driver is told at each stage** must differ in wording, and the UI must never show a
  SHOWN option in language that implies a booking. Write the four message templates down; they are
  part of the deliverable.

---

## 5. The decision engine (your 3-stage design, productionised)

Your Scheduling Algorithm report is already the right shape. Keep it and harden it.

### Stage 0 — Search horizon, and why "no slot today" is not the end of the conversation

The shipped seed contains a single day (2026-08-04), and it is easy to inherit that as an architectural
assumption. The brief does not: §11.1 asks for "600–1,000 shipments **across seven days**", §8 lists
*"Do not book 7:30. **Check tomorrow morning**"* as a first-class driver message, and §8's *Fallback*
type is literally *"There is no slot today. What should I do next?"*.

A same-day-only engine has exactly one answer to that question — escalate — and that is the wrong answer.
A human coordinator's first move for a truck that cannot be received tonight is "06:00 tomorrow, D5", and
a system that cannot say that sentence pushes the driver back to a phone call, which is the failure mode
the product exists to remove.

**So the search horizon is explicit and multi-day:**

- `find_feasible_slots` searches a **rolling horizon, default 48 hours** from the effective ETA, bounded
  by each facility's operating calendar. Configurable per facility; never unbounded, because an option
  five days out is noise, not an option.
- **Same-day beats next-day automatically — no new coefficient.** The Stage 2 lateness term already
  charges every minute past the promise, so a 06:00-tomorrow interval scores far below any feasible
  interval tonight. Ordering falls out of the existing policy rather than being special-cased, which
  keeps the receipt explicable and the determinism proof intact.
- **Every offered interval carries its date**, and the SHOWN template renders it. "Dock D5 · 06:00" with
  no date is precisely the ambiguity the banned-phrasings list already forbids (§7.2b: *any operational
  time without its dock and date*). This is the single most likely place for a real-world wrong-day
  booking, and it is a formatting decision, which makes it cheap to get right and embarrassing to get
  wrong.

**Two distinct outcomes, only one of which is an escalation:**

| Outcome | When | Driver sees | Escalation? |
|---|---|---|---|
| `NO_SAME_DAY_SLOT` | Today exhausted, horizon still has capacity | Dated next-day options + an explicit "nothing works today" sentence | **No** |
| `NO_FEASIBLE_SLOT` | The **whole horizon** is exhausted | Escalation notice, named owner, what happens next | Yes (§7.4) |

This reclassification changes the SHP1015 walkthrough, so state the result rather than assuming it:
D5 is blocked 18:00–22:00 on 04 Aug (`DEVT002`) and Jaipur closes at 22:00, so the reefer load has no
*same-day* interval — that much is unchanged and provable. Whether it also escalates now depends on
whether D5 has capacity on 05 Aug, which the single-day seed cannot answer. Under the D8 generator (which
now emits seven days, §9.1) the honest outcome is `NO_SAME_DAY_SLOT` **plus** a next-morning reefer
offer, with escalation reserved for the case where the driver's `latest_acceptable_ts` or the load's
perishability rules that out. Keep a genuine `NO_FEASIBLE_SLOT` fixture in the test set — §12.2 requires
one case that ends in escalation — but build it deliberately rather than relying on a one-day dataset to
produce it as an artifact.

### Stage 1 — Hard constraints (eligibility guard)
Eight invariants from `constraints.json`: ETA + unload fits before slot end; facility operating
hours; dock ACTIVE (no `dock_status_events` overlap); vehicle/dock physical compatibility; cargo &
temperature compatibility; slot capacity available; one active appointment per shipment;
authoritative ETA from the system of record only.

Two corrections to that list, forced by what the data actually contains (§6.2 #7, #8):
**physical compatibility means weight and length only** — clearance height and door type have no columns
and are struck — and **weight compares `shipments.load_weight_kg` against `docks.max_vehicle_weight_kg`**,
per RULE004's wording. Dock ratings are not uniform (D1/D3 20,000 · D2/D4 25,000 · D5 22,000 · D6 35,000),
so "it's a standard dock" is never sufficient.

Add four the dataset demands:
- **Facility rule evaluation with time-bounded effectivity** — `facility_rules.effective_from/to`
  (§11.3: rules effective only part of the day). RULE003 pins reefer to D5; RULE004 pushes >25,000 kg
  to heavy; RULE005 forbids a *new start* after 21:00 without approval.
- **Rule absence is permission, not inheritance.** FAC-GGN-01 defines no `LAST_NEW_START_TIME` and has
  its own grace period (RULE006, 20 min vs Jaipur's 30). An absent rule means unrestricted at that
  facility — it must never be back-filled from another facility's rule set. This matters the moment a
  second facility exists, which is already.
- **The driver's own constraints — both ends.** `driver_exceptions.latest_acceptable_ts` ("I must leave
  by 9 PM", EXC002 = 13:30) *and* `earliest_acceptable_ts`, which is populated in 5 of the 10 seeded
  exceptions (EXC001 = 12:00, plus EXC002/004/005/006) and is just as binding: an interval before the
  driver can physically be there is not an option. A slot that is feasible for the warehouse but breaks
  the driver's next commitment is not a valid option either.
- **Grace/no-show window** — a slot whose start + grace has already passed is not offerable.

### Stage 2 — Deterministic weighted scoring
`Score = S_priority + (w_lateness × Δlateness) + (w_wait × Δwait) + (w_slack × Δslack) − P_dock`
with CRITICAL/HIGH/NORMAL/LOW = 4000/3000/2000/1000, lateness +4/min (cap 720), wait −6/min,
slack +1/min (cap 120), non-exact dock −25. Ties broken by `shipment_id + slot_id`. Zero randomness.

**Productionise it:**
- **Version the weights** in a `policy_versions` table and stamp the version onto every decision.
  §9.2 says the policy is a business trade-off, not a constant — so it must be admin-editable,
  auditable, and reproducible. "Which policy produced this promise?" must be answerable a month later.
- **Emit a decision receipt** per ranked option: which constraints passed, each score term's
  contribution, why option #1 beat option #2. That receipt is what the driver-facing explanation
  (§12.1 Q11 "what is explained when the preferred slot is not granted") is generated *from* — the
  LLM narrates the receipt, it does not invent the reasoning.
- **Reserve a place for fairness, but ship it disabled (D7).** Pure priority scoring lets one carrier with
  many CRITICAL loads repeatedly consume scarce capacity (brief §9.2, "Fairness across carriers"). The
  formula therefore *defines* a per-carrier displacement penalty term with weight `w_fairness = 0`, so the
  shipped policy is exactly the specification above — simple, deterministic, easy to defend — while the
  term has a real home and a policy version to land in if the data turns ugly. The mitigation in v1 is
  **visibility, not mechanism**: the carrier-concentration metric (§8) is the canary. Enabling the term is
  a policy decision with an audit trail, not a code change.

### Stage 3 — Transactional FCFS
Under D1 there is **no slot row to lock**, and that is the point. The winner is decided by the database
itself: both contenders `INSERT` a `dock_occupancy` row for the same dock and overlapping window, and the
GiST `EXCLUDE` constraint admits exactly one. The loser catches the constraint violation, is mapped to
`SLOT_CONFLICT_REFRESH_REQUIRED`, and is handed fresh options — never a corrupted state, never a 5xx.

Why this is stronger than the row-lock design it replaces: `SELECT … FOR UPDATE` on a slot row serialises
contenders for *that row*, which cannot see a 75-minute unload at 11:00 colliding with a booking at 12:00,
because those are two different rows. The exclusion constraint makes the overlap itself unrepresentable,
so correctness no longer depends on every caller remembering to take the right lock first.

What survives from the shipped schema: `ux_current_active_appointment_per_shipment` (one active
appointment per shipment) stays, unchanged. `ux_active_appointment_per_slot` becomes redundant once
`appointment_slots` is a publishing layer — keep it during migration as a belt-and-braces check, drop it
when `dock_occupancy` is authoritative.

Add an **idempotency key** on every mutating call so the seeded duplicate-message case (`THR009`,
`is_duplicate=1`, `dedupe_key`) can never produce two bookings from one intent.

### Stage 4 (the §7.3 extension) — Facility sequencer
Stages 1–3 answer "a slot for *this* driver." §7.3 asks the harder question: given SHP-201 early and
waiting, SHP-202 late and waiting, SHP-203 arriving at 18:35, SHP-204 mid-unload on D1 — what should
the *facility* do? Model it as trucks = jobs, docks = machines, ETA/gate-in = release time,
unload = processing time, appointment = due date, compatibility = eligible machines,
priority = weight, in-progress unload = fixed task.

- **Start rule-based** (the brief explicitly allows this): greedy insertion by the Stage-2 score over
  a rolling horizon. Prove it against competing trucks; upgrade to OR-Tools CP-SAT only if you have
  time. Keep the interface identical so the engine is swappable.
- **Recompute triggers** (rolling horizon, §12.1 Q8): driver ETA update, gate check-in, unload
  complete, cancellation, dock status event, new exception. Nothing else — never on a timer alone.
- **Stability objective matters as much as optimality.** Penalise changing an *already communicated*
  plan. A schedule that is 3% better but reshuffles six promised drivers is worse than one that is
  stable. Persist every run in `scheduling_runs` (input snapshot, proposal, objective values,
  explanation) so a proposal can be reviewed and replayed.

#### 5.1 The sequencer in full

**Classification.** Docks are *not* interchangeable machines — D5 is the only reefer, D6 the only
heavy, and weight limits differ across D1–D4. With driver-declared arrival times this is
`R | r_j, M_j, fixed tasks | weighted objective`: unrelated parallel machines with release dates,
machine-eligibility restrictions, and pinned in-progress work. Naming it correctly matters, because it
tells you immediately that simple EDD or FCFS dispatching will underperform and why.

**Run scope.** One facility, rolling horizon of **4 hours or to `close_time`, whichever is sooner**.
Beyond that, driver-declared ETAs (no GPS, §7.3 data boundary) carry too little information to be
worth optimising — planning further ahead is false precision.

**Job set and parameters**

| Element | Definition | Source |
|---|---|---|
| Job *j* | An inbound shipment needing dock time | `shipments` in horizon |
| Release *r_j* | **`gate_in_ts` if the truck has arrived, else effective ETA** | `facility_checkins` overrides `v_latest_eta` |
| Processing *p_j* | `expected_unload_min + 15` (D10) | `shipments` |
| Eligible docks *M_j* | Stage-1 hard-constraint survivors | `docks`, `facility_rules` |
| Due *d_j* | Current appointment start, if any | `appointments` |
| Weight *w_j* | CRITICAL/HIGH/NORMAL/LOW = 4000/3000/2000/1000 | `shipments.priority_code` |
| Fixed tasks | In-progress unloads pin their dock to expected finish | `facility_checkins.queue_state='IN_DOCK'` |
| Machine downtime | Outage windows as unavailability intervals | `dock_status_events` |

`gate_in` overriding ETA is the rule that makes §7.3's scenario tractable: SHP-201 arrived at 17:05 for
a 17:30 slot, so it is *available now* regardless of what the plan said. A sequencer that keeps using
planned ETA for an arrived truck will leave a truck idling in the yard beside an empty dock.

**Objective — one currency with Stage 2.** This is the part most designs get wrong. If the per-driver
ranker maximises a utility and the sequencer minimises an unrelated cost, the two will recommend
different things and the planner sees the system contradict itself. Use the *same coefficients with
inverted sign* — the sequencer minimises exactly what Stage 2 maximises:

```
minimise   Σ_j [ w_j·max(0, start_j − d_j)          # lateness against the promise
                + 6·(start_j − r_j)                  # driver waiting  (Stage 2: −6/min)
                + 25·[dock_j not exact match] ]      # fallback dock   (Stage 2: −25)
         + P_churn · |{ j : promise communicated ∧ |start_j − promised_j| > 15 min }|
```

Hard, not penalised: operating hours, `LAST_NEW_START_TIME` 21:00 (RULE005), dock eligibility,
no-overlap, fixed tasks.

**Pricing churn.** Set `P_churn` ≈ **30 weighted-minute-equivalents per moved promise**. Rationale
made explicit: moving a communicated promise costs a notification, the driver's re-planning, a real
chance of refusal, and a slice of trust. A move must *pay for itself*. The 15-minute epsilon matches
the D11 grid, so sub-grid jitter never counts as churn. `P_churn` lives in `policy_versions` alongside
the Stage-2 weights (D7) and is stamped on every run.

**Algorithm — rule-based first, CP-SAT swappable.**
1. Freeze fixed tasks and downtime windows.
2. Order jobs by Stage-2 score, descending.
3. Greedy insertion: place each job at the earliest feasible start on the eligible dock with the
   lowest marginal cost.
4. Local improvement: pairwise swaps and single-job reinsertions, accepted only when the total cost
   improves by **more than** the churn any move incurs.
5. Deterministic tie-break on `(shipment_id, dock_id)` — same zero-randomness guarantee as Stage 2.

The CP-SAT upgrade is a drop-in because search is separated from objective: one `IntervalVar` per job,
`NoOverlap` per dock, optional intervals for dock assignment, identical cost expression.

**Recompute triggers** (§12.1 Q8) — event-driven only, never a timer: ETA update · gate check-in ·
unload complete · cancellation · dock status event · new exception · pending expiry (D9).

**Debounce, or the spike will thrash it.** 20–35 messages inside 30 minutes would otherwise fire ~30
runs, each proposing to move the previous one's promises. Coalesce triggers in a **30–60 s window**,
and allow **at most one active run per facility** (serialised). Without this, plan stability is
theoretical.

**What the planner actually receives (D5) — a diff, not a schedule**

> Proposal SR-4471 · Jaipur DC · horizon 17:00–21:00
> **Unchanged 9** · **Moved 2** · **Newly placed 3** · **Unplaceable 1**
> Moved: SHP1013 D2 18:00 → 18:30 *(not yet communicated)* · SHP1009 D4 19:15 → 19:45 *(communicated — driver will be notified)*
> Unplaceable: SHP1015 — no compatible reefer interval before close → escalation
> Effect: total driver waiting −85 min · promises moved 1 · overtime 0

Two rules for applying it:
- **All-or-nothing per run.** Partial application breaks the no-overlap and feasibility guarantees the
  run computed. Cherry-picking rows produces a schedule nobody validated.
- **Snapshot-guarded, exactly like option sets.** Drivers keep booking while the planner reviews, so
  the proposal carries a `snapshot_hash`; on apply, revalidate and re-run on drift. Same staleness
  discipline as §7.1 — one mechanism, used consistently.

**Cascade path.** DEVT001 (D3 down 09:15–13:00) becomes: capacity incident → one run scoped to the
affected docks and window → one proposal → planner applies → notifications batch out. Not N
independent escalations, which is the failure mode §7.4 describes.

---

## 6. Data model: what to add, and what the shipped schema gets wrong

### 6.1 Additions (the brief withholds these on purpose — §10.5)

| Table | Why |
|---|---|
| `dock_occupancy` | The booking authority (D1): dock-time intervals under a GiST `EXCLUDE` constraint. Carries `HELD`, `PENDING_CONFIRMATION`, `CONFIRMED`, `IN_PROGRESS` in one table — **no separate hold table**, so overlap has exactly one source of truth (D2). |
| `slot_recommendations` | The `REC-` token: what was shown, to whom, when, against which snapshot. Enables staleness detection and "you saw X, here's why it changed". |
| `allocation_decisions` | Decision receipt: candidates, constraint outcomes, score terms, policy version, winner, reason. |
| `escalation_queue` | No-feasible-slot, conflicting warehouse reply, regulated load, contradiction. With SLA + owner. |
| `idempotency_keys` | Duplicate/retry safety across chat and REST. |
| `notification_outbox` | Transactional outbox so a booking and its notification cannot diverge; feeds `operational_messages`. |
| `policy_versions` | Versioned allocation weights and rule sets. |
| `user_scopes` | The scoping half of RBAC (facility / carrier / driver). `users`, `roles`, `audit_logs` and `api_logs` **already exist** — see the note below. |
| `agent_actions` | Tool call, arguments, result, trace id — the AI's own accountability trail. |
| `customer_commitments` | §10.4's optional table, and the missing provenance for `priority_code`. D7's entire allocation policy rests on that column; without a recorded basis, CRITICAL is a magic value rather than a commitment anyone can point at in a review. |

**Correction to a common assumption:** the database *guide* lists 18 tables, but
`setuhaul_schema_and_seed.sql` ships **22** — `roles`, `users`, `audit_logs` and `api_logs` are appended
beyond the classroom package, and `roles` is seeded with exactly the eight personas of §2 (`DRIVER`,
`OPERATIONS_EXECUTIVE`, `WAREHOUSE_PLANNER`, `OPERATIONS_MANAGER`, `FACILITY_MANAGER`,
`TRANSPORT_MANAGER`, `REGIONAL_OPERATIONS_HEAD`, `ADMIN`). So identity, role and logging tables are a
*migration* concern (SQLite → Postgres, `password_hash` → Supabase Auth), not a greenfield design task.
What is genuinely absent is `user_scopes` — the carrier/facility scoping that M15 depends on.

### 6.2 Schema issues in the shipped data worth fixing in production

These are real findings from reading the seed, and they are excellent material for a review:

1. **Unload duration exceeds slot length in ~4 of 20 appointments.** `appointments` links a shipment
   to exactly **one** slot, but slots are 60 min (D1–D5) while `expected_unload_min` is 45–90.
   Concretely: SHP1002 (70 min → 60-min SLOT-JAI-015), SHP1005 (75 → SLOT-JAI-030), SHP1009
   (75 → SLOT-JAI-046), SHP1014 (75 → SLOT-JAI-004). Stage-1's "ETA + unload ≤ slot end" would reject
   the facility's *own existing bookings*. The seeded overrun (`DEVT003`, CHK1002 "unload running
   longer than planned") is the symptom.
   **Resolved by D1** — dock-time intervals with a GiST exclusion constraint. Note the migration
   consequence: once true durations are honoured, those four bookings *genuinely* conflict with their
   neighbours. **D12 is that resolution policy** — preserve the start, extend to the true duration, and
   flag the conflict onto the `REQUIRES_TIME_RESOLUTION` worklist rather than compressing or moving
   anything silently. A real data-migration decision, made in the open rather than hidden.
2. **`capacity_units` is documented (§10.2) but absent from the shipped `appointment_slots`.** So the
   real semantics are 1 slot = 1 truck. Under D1 this becomes moot for docks (one truck per dock per
   interval, enforced structurally) — but it returns if a facility ever wants a *yard* or *staging
   area* with genuine multi-unit capacity. Keep it out of v1; note the extension point.
3. **Timestamps are TEXT with a `+05:30` suffix** (SQLite convenience). In Postgres use `timestamptz`
   and store facility-local rendering separately. Multi-facility + DST-free IST is easy today, but the
   brief targets 6 facilities and the model should not encode a single offset.
4. **`facility_checkins.shipment_id` is UNIQUE** — one check-in row per shipment, mutated in place.
   That loses event history. Production wants an append-only `checkin_events` stream with a
   materialised current-state view; the queue view then derives rather than overwrites.
5. **The *seed file* is well under the brief's target scale — the *deployed database* is not.** This
   distinction matters and an earlier draft of this document got it wrong. The classroom seed file
   (`setuhaul_schema_and_seed.sql`) ships 2 facilities / 9 docks / 21 shipments against §11.1's
   6 facilities / 24–32 docks / 600–1,000 shipments. But the live Supabase project has **already been
   generated to those volumes** (audited 2026-08-19):

   | Entity | Live | §11.1 target |
   |---|---:|---|
   | Facilities · docks | 6 · 25 | 6 · 24–32 |
   | Drivers · vehicles | 106 · 105 | 80–120 · 90–140 |
   | Shipments | 671 | 600–1,000 |
   | Appointment slots · appointments | 3,574 · 1,557 | 2,000–3,000 · 900–1,500 |
   | ETA updates · check-ins | 807 · 405 | 800–1,500 · 400–700 |
   | Exceptions · chat messages | 264 · 1,542 | 250–400 · 1,500–3,000 |

   **And Layer A survived verbatim** — all 21 `SHP10xx`, 12 `THR0xx`, 10 `EXC0xx` and 20 `APT10xx` rows
   are present and unmodified. Whoever built that generator already respected the layer separation §9.1
   argues for, which is worth saying plainly rather than treating the work as unstarted.

   What is *not* yet right is covered in §9.1: the seeded cases and the generated volume sit on
   **different dates** and never coexist, and three of §11.3's required imperfections are missing.
6. **Reefer is a single point of failure by rule.** RULE003 pins temperature-controlled loads to D5
   only, and D5 is blocked 18:00–22:00 (`DEVT002`). SHP1015 (ETA 18:30) therefore has *no* feasible
   same-day slot — by construction. This is the intended escalation case (§12.2's "at least one case
   ends in escalation"); make sure the engine reaches that conclusion by rule, not by accident.
7. **Two seeded appointments exceed their dock's weight limit.** The dock ratings are D1 20,000 ·
   D2 25,000 · D3 20,000 · D4 25,000 · D5 22,000 · D6 35,000 kg — they are *not* uniform, which is easy
   to miss.

   | Appointment | Shipment | Load | Vehicle capacity | Slot → dock | Dock max |
   |---|---|---:|---:|---|---:|
   | `APT1005` CONFIRMED | SHP1005 | 20,500 kg | VEH006 22,000 | SLOT-JAI-030 → **D3** | 20,000 |
   | `APT1014A` PENDING | SHP1014 | 21,000 kg | VEH014 21,800 | SLOT-JAI-004 → **D1** | 20,000 |

   Both violate under *either* reading of the column, so the finding does not depend on interpretation.
   This is the same shape of defect as issue 1: Stage 1's `dock_vehicle_compatibility` invariant would
   reject the facility's own current bookings.

   **Two decisions follow.** First, `max_vehicle_weight_kg` is ambiguous — the column name says vehicle,
   RULE004's text says load ("Loads above 25,000 kg must use the heavy dock"). **We compare
   `shipments.load_weight_kg`**, consistent with RULE004 and with how a warehouse actually reasons about
   a dock's floor and leveller rating. Write it down; an unstated choice here silently changes which
   options are feasible. Second, the backfill cannot resolve these the way it resolves issue 1: a weight
   violation needs a *different dock*, not a different hour. Both rows therefore enter the D12 worklist
   as `REQUIRES_DOCK_REASSIGNMENT` for planner action, consistent with D5 — nothing is moved silently.
8. **Physical dimensions do not exist in the schema.** Stage 1 as written in the scheduling report
   requires "truck length, weight capacity, clearance height, and door type". The shipped schema has
   only `max_vehicle_weight_kg`, `dock_type` and `supports_refrigerated`; `vehicle_types.description`
   carries "32-foot" as prose. Yet the brief leans on length repeatedly — §4's "DOCK-04 | max 32-foot",
   and §8's first-class driver question *"Does the 7:30 slot accept a 32-foot vehicle?"*.
   **Resolution:** add `docks.max_vehicle_length_ft` and `vehicle_types.length_ft`, backfilled from the
   existing type codes (`20FT` → 20 · `32FT_SXL` / `32FT_MXL` / `REEFER_32` → 32 · `HEAVY_40` → 40).
   Clearance height and door type are **struck from the Stage 1 clause** — there is no data behind them
   and inventing two more columns to satisfy a sentence is worse than correcting the sentence.
9. **Two sources of "blocked" truth, and they disagree.** `appointment_slots.slot_status='BLOCKED'`
   duplicates `dock_status_events`, and the windows do not match: `DEVT001` takes D3 down
   **09:15–13:00**, but the blocked slots (SLOT-JAI-031/032/033) cover only **10:00–13:00**.
   SLOT-JAI-030 (09:00–10:00) is still `OPEN`, overlaps the outage, and is exactly where `APT1005` sits
   — which is how the seeded SHP1005 stranding case arises. (`DEVT002`/D5 *does* agree, which makes the
   D3 mismatch look like drift rather than design.) **Resolution:** `dock_status_events` is the single
   authority for availability; `slot_status` becomes a derived publishing flag, reconciled by the
   feasibility engine rather than maintained by hand. Two hand-maintained copies of one fact will
   diverge, and here they already have.
10. **`facility_rules` cannot express the intraday effectivity the brief requires.**
    `effective_from`/`effective_to` are seeded as bare dates (`'2026-01-01'`), and `rule_type`/`rule_value`
    are untyped free text with no CHECK constraint. But §11.3 explicitly requires "facility rules
    effective only during part of the day" as a realistic imperfection, and Stage 1 above cites that
    requirement. No seeded rule does it, and the column type cannot hold a time of day.
    **Resolution:** `timestamptz` bounds; a typed rule-type registry so Stage 1 evaluates a known enum
    instead of string-matching free text; and at least one seeded intraday rule so the capability is
    actually exercised.
11. **Two overlapping state machines for the same truck.** `shipments.current_status` and
    `facility_checkins.queue_state` both carry `WAITING` and `IN_DOCK`, with no stated precedence — so
    "is this truck in a dock?" has two answers that can disagree. Extending issue 4's resolution: the
    check-in event stream is **authoritative** for yard and dock state, and `shipments.current_status`
    becomes a derived projection rather than an independently written column.
12. **`shipments.latest_eta_ts` is a denormalised duplicate of `eta_updates`.** `v_latest_eta` already
    COALESCEs around it, which is the tell — it exists only to be stale. Drop it, or make it a derived
    column with no writer. Decide deliberately whether the stale value is the §11.3 "stale
    latest-declared ETA" fixture (in which case keep it, in Layer C, on purpose) or an accident of the
    seed; today the document cannot tell you which, and that ambiguity is itself the bug.

---

## 7. The AI layer contract

**The LLM's job:** parse informal free text, ask *only* what is missing, hold context across
corrections, narrate options and decisions in plain language, and confirm intent before any write.
Your 23-tool catalog is a sound decomposition — reads, one confirmed-write ETA tool, the scheduling
quartet (`find_feasible_slots` / `request_slot` / `get_appointment_request_status` /
`cancel`+`reschedule`), escalation, and an explicit `scheduling_capability_disabled` refusal guard.

**Non-negotiable guardrails (§6.3):**
- No SQL. No invented ETAs, slots, capacity, or confirmations. Every operational fact in a reply
  must be traceable to a tool result in the same turn.
- Never marks an appointment CONFIRMED. Never decides compatibility. Never resolves priority conflicts.
- Every mutation is preview → explicit driver confirmation → idempotent commit.

**Conversation rules the dataset specifically demands:**

| Seeded case | Required behaviour |
|---|---|
| "late by one hour" (MSG005, `confidence_code=LOW`) | Do **not** derive an ETA. Ask: new arrival 11:00, or another hour of delay? `requires_human_review=1`. |
| Repair 45 min ≠ ETA shift 45 min (§11.2) | Ask for arrival time, never arithmetic on repair duration. |
| DRV004 has two shipments (THR010, `shipment_id` NULL) | Disambiguate by order reference before any read that assumes a shipment. |
| Duplicate message retry (THR009 / `dedupe_key`) | Collapse on `dedupe_key`; one exception, one action. |
| "I must leave before 1:30" (EXC002) | Capture as `latest_acceptable_ts` and pass it into Stage 1 as a hard filter. |
| Cancelled shipment asks about slot (THR012) | Refuse to schedule; route to dispatch. |
| Warehouse reply conflicts with stored schedule (§11.2) | Escalate. Never silently reconcile. |

**Memory:** Redis holds 24 h conversation state and is explicitly **non-authoritative**. Postgres is
the only source of operational truth. If Redis is empty, the system must still answer correctly from
the database — test that.

**Channel adapters:** `chat_messages.external_message_id` + `is_duplicate` exist because real drivers
message over a PWA with flaky connectivity and retry when a send appears to fail. Build ingestion
idempotent on external id from day one — the same mechanism protects any channel added later.

### 7.1 Tool-contract gaps introduced by D1/D2/D9

The 23-tool catalog was written against the fixed-slot model. Four contracts change, and one tool is
missing entirely. These are the exact edits:

**`find_feasible_slots` — return contract changes.** It no longer returns slot rows. It returns
*offered intervals*: `{option_rank, dock_id, start_ts, end_ts, unload_min, changeover_min,
score_terms{}, recommendation_id, snapshot_hash, offer_expires_at}`. Two additions matter:
- `snapshot_hash` — what the world looked like when these were computed. The commit path compares it
  and refuses on drift. This is the mechanism behind §12.1 Q9 (stale options).
- `score_terms` — the decision receipt inline, so the assistant explains *from* it (§12.1 Q11) rather
  than inventing a rationale. The LLM narrates; it never reasons about ranking.

**`request_slot` — now a two-phase contract.** Under D2 it takes `(recommendation_id, dock_id,
start_ts, Idempotency-Key)` and returns one of three typed outcomes, never prose:
- `HELD` + `hold_expires_at` (90 s) — capacity is now blocked for this driver.
- `SLOT_CONFLICT_REFRESH_REQUIRED` + a fresh option set — the loser path from Stage 3.
- `SLOT_OPTIONS_STALE` — snapshot drift; re-rank and re-show before accepting any choice.

**Missing tool — `confirm_held_slot`.** There is currently no way to convert a hold into a request,
because holds did not exist when the catalog was written. Needed: takes the hold id, revalidates
inside the transaction, and produces `PENDING_CONFIRMATION`. Without it the driver's chosen slot has
no committed path and the 90-second hold simply lapses.

**`get_appointment_request_status` — must expose the D9 deadline.** Add `pending_expires_at` and
`planner_queue_position`. "Has the warehouse confirmed?" (§8, a first-class conversation type) has
three honest answers now — still pending with time remaining, expired and released, or confirmed —
and the driver must be able to tell them apart.

**Missing tool — `explain_slot_eligibility`.** §8 lists *"Does the 7:30 slot accept a 32-foot vehicle?"*
as a first-class driver message. It looks informational, but the answer *is* a compatibility ruling, and
§6.3 forbids the AI from deciding compatibility. Without a tool, the model will answer it from the dock
description in its context — confidently, and eventually wrongly.

Needed: a **read-only** tool taking `(dock_id | interval, shipment_id)` and returning a per-invariant
verdict — `{invariant, passed, rule_id, actual, limit}` — for every Stage 1 check, with no side effects
and no booking implication. It is the same evaluator Stage 1 runs, exposed for explanation. Two payoffs
beyond correctness: the driver gets *"D4 takes up to 25,000 kg and your load is 21,000 — that one is
fine; D1 caps at 20,000"* instead of a vague yes, and the refusal surface (§7.2) gets a concrete rule id
to name, which is what turns a refusal into a route rather than a dead end.

**Catalog error worth fixing at the source.** Tool 17 (`find_feasible_slots`) lists `facility_schedules`
among its tables. **No such table exists** — not in the shipped schema, not in the guide, not in the
additions of §6.1. It reads as a placeholder that was never reconciled. The real backing objects are
`appointment_slots`, `docks`, `dock_status_events`, `facility_rules` and, post-D1, `dock_occupancy`.

**New system-initiated message class.** D9 means capacity can be released *while nobody is asking*.
The 15-minute expiry, a planner rejection, and a dock going down mid-conversation are all events the
driver must be told about without having sent a message. That is not a tool — it is an **outbound
event → notification outbox → channel adapter** path, and it is the mechanism behind §12.2's
requirement that "the driver is shown what happens when an option changes or disappears." A purely
request/response assistant cannot satisfy that line in the brief.

### 7.2 The refusal surface

`scheduling_capability_disabled` (tool 23) is the right instinct but too narrow — it guards mutation
requests. Under this design the assistant must also refuse, with a clear reason and a route to a human:

| Driver says | Refusal + route |
|---|---|
| "Just confirm it, don't wait for the warehouse" | D6: only a planner confirms. Offer to flag the request as urgent in the planner queue. |
| "Book me the 7:30 even though I get there at 8" | Stage-1 hard constraint. Explain the specific failing invariant, offer feasible alternatives. |
| "I'm carrying something not on the manifest" | Contradiction → escalate (brief §9.3), do not schedule. |
| "My brakes are failing, should I keep driving?" | Safety decision, never the system's (brief §9.3). Route to carrier + ops immediately. |
| "Give me the slot that truck ahead of me has" | No displacement via chat. Explain policy, offer the ranked feasible set. |

Each refusal must name *which* rule applies and *who* can act — a refusal without a route is a dead
end, and dead ends are what drive drivers back to phone calls.

---

## 7.2b Conversation design

### The governing rule: state messages are templated, not generated

§8.1 makes the distinction between *shown*, *reserved* and *confirmed* a graded requirement. If those
four sentences are produced by sampling, a single unlucky generation can tell a driver their slot is
"booked" when it is held for 90 seconds — and that is a broken promise in the business sense, not a
wording nit.

**So: lifecycle transitions emit deterministic templates. The LLM writes the glue around them.**
It clarifies, explains, compares, reassures — but the sentence that declares operational state is
parameterised text the business has reviewed. This also makes translation testable, which matters
given the driver roster (Rajesh, Imran, Mukesh, Gurpreet, Mohammed…) and the realistic need for
Hindi/Hinglish later.

### The four state templates

Each must answer three questions: *what is true now, what happens next, what must I do.*

**1 · SHOWN** — nothing is held
> Three options are open right now at Jaipur DC. **Nothing is held yet** — another driver can take
> any of these.
> 1️⃣ Dock D4 · **Tue 4 Aug** 12:15–13:30
> 2️⃣ Dock D1 · **Tue 4 Aug** 13:00–14:15
> 3️⃣ Dock D2 · **Tue 4 Aug** 14:30–15:45
> Reply with the number to hold one for 90 seconds.

The date is not decoration. Under Stage 0 an option set can mix today and tomorrow, and a driver who reads
"06:00" as this morning rather than tomorrow morning has been mis-promised by a formatting choice. Render
the day on every interval, even when they are all today — a conditional date field is a field that will be
missing on the one occasion it mattered.

**2 · HELD** — yours briefly, not requested
> Option 2 (Dock D1 · 13:00–14:15) is **held for you until 11:42:30** — about 90 seconds.
> This is not a booking yet. Reply CONFIRM to send it to the warehouse.

**3 · PENDING_CONFIRMATION** — requested, not agreed
> Requested: Dock D1 · 13:00–14:15.
> **The warehouse has not confirmed this yet.** A planner will decide by **11:57**.
> If there is no decision by then, the slot is released and I will find you fresh options.

**4 · CONFIRMED** — the only sentence that may say "confirmed"
> ✅ Confirmed — Dock D1 · 13:00–14:15, Jaipur DC. Reference APT-1042.
> You may check in from 12:00 (60 min early limit). If you have not checked in by 13:30 the
> appointment may be marked no-show.

Note how the arrival guidance in (4) is drawn from real rules — RULE001 (60-min early check-in limit)
and RULE002 (30-min no-show grace) — not invented. Confirmation without arrival instructions is where
detention starts.

### Negative-path templates (equally mandatory)

`HOLD_LAPSED` · `PENDING_EXPIRED` (D9) · `SLOT_CONFLICT` (lost the race) · `OPTION_WITHDRAWN`
(dock event mid-conversation) · `NO_SAME_DAY_SLOT` → dated next-day options, *not* an apology ·
`NO_FEASIBLE_SLOT` → escalation · `COUNTER_OFFERED` (planner proposed a different interval) ·
`HUMAN_JOINED` (takeover).

§12.2 explicitly requires demonstrating *"the driver is shown what happens when an option changes or
disappears."* These eight are that requirement.

`NO_SAME_DAY_SLOT` deserves care in the wording, because it is the one negative-path message that carries
good news underneath it:

> Nothing works at Jaipur DC today — the reefer dock is down for maintenance until 22:00 and the site
> closes then. **The earliest I can offer is tomorrow.**
> 1️⃣ Dock D5 · **Wed 5 Aug** 06:00–07:15
> 2️⃣ Dock D5 · **Wed 5 Aug** 07:30–08:45
> Nothing is held yet. If waiting overnight does not work, reply HELP and I'll bring in operations.

Note what it does: names the specific blocking reason, gives dated alternatives, and offers the escalation
route rather than forcing the driver to ask for it.

### Banned phrasings

- "Booked" / "reserved" / "you have" for anything below CONFIRMED.
- A bare "OK" or "Done" after any state change.
- Any operational time without its dock and date.
- Implying warehouse agreement when only a message was *sent* — the OM004 lesson: a FAILED email is
  not a confirmation, and neither is a delivered one.

### The ordinal trap

§8 lists *"Take the second option"* as a first-class driver message. That means ordinals must be
stable — and they are not, across a refresh. **Rule: an ordinal is only valid against the
`recommendation_id` it was displayed with.** If the option set was re-ranked for any reason, an
incoming ordinal must be rejected and the set re-presented. Silently applying "the second one" to a
newly-ranked list books the wrong dock while looking perfectly successful. This is the subtlest
correctness bug in the whole design and it lives entirely in the conversation layer.

### Comparison is read, never computed

§8 lists *"Which option has the shortest expected waiting time?"* as a first-class driver message, and it
is a trap dressed as a pleasantry. The obvious implementation — let the model look at three options and
say which is shortest — quietly moves ranking into the LLM, which §6.3 forbids and M4's determinism
guarantee cannot survive.

**Rule: comparative answers are read off `score_terms` in the option set the driver is already looking
at.** The wait figure, the lateness figure and the dock-match penalty are all already computed and
attached to each offered interval (§7.1). The assistant selects and phrases; it never recomputes, never
re-ranks, and never compares options across two different `recommendation_id`s. If the driver asks about
something the receipt does not contain, that is a missing `score_terms` field — fix the contract, do not
let the model estimate.

This is the same discipline as the §12.1 Q11 explanation path, and for the same reason: the moment a
number in a driver-facing sentence has no tool result behind it, the system is guessing about capacity.

### Not every thread is an exception

`THR011` (DRV001, `ASK_SLOT_OPTIONS`) has **no** `driver_exceptions` row — the database guide's
"ask-only conversation" case. Module 2 as drafted assumes free text → exception row, which would fabricate
an operational incident out of a driver browsing.

**The browse-only path:** thread + option set (with its `REC-` token), and nothing else. No exception, no
`dedupe_key`, no severity, no SLA clock, no escalation timer. It converts to the exception path the moment
the driver reports a problem or chooses an interval — at which point the exception is created with the
thread already attached.

Worth stating explicitly because the failure is silent and expensive: an exceptions queue padded with
people asking questions destroys the automation-coverage metric (§8, "share resolved without escalation")
and buries the real exceptions under noise in the ops console.

### Clarification policy — ask only what blocks the next deterministic step

§13.1 counts *driver clarification turns* as a cost. So: **at most one question per turn**, and only
for a field that blocks the next engine call.

Blocking fields for `find_feasible_slots`: shipment identity → effective ETA → (only if it changes the
answer set) the driver's latest acceptable time. Nothing else is worth a turn.

| Situation | Ask this | Never ask this |
|---|---|---|
| "I am late by one hour" (MSG005, confidence LOW) | *"Does that mean arriving 11:00, or another hour from where you are now?"* | "How late are you?" |
| Repair time given, not arrival | *"What time do you expect to reach the gate?"* | Anything that invites arithmetic on repair duration |
| "I need to leave by 9" (EXC002) | *"Should 9 PM be the latest you leave the gate, or the latest unloading can start?"* | — (MSG004 already models this well) |

The seeded agent messages (MSG002, MSG004, MSG006, MSG013, MSG017) are a good style guide — they are
short, they name the specific ambiguity, and they offer the two readings rather than asking open questions.

### Disambiguation ladder (THR010 / DRV004)

1. **One active shipment → never ask.** Infer and state the assumption: *"For your Kota load to
   IndustrialHub…"* — cheap to correct, costs no turn.
2. **Two or more → ask with human descriptors, not IDs.** *"The Kota load due 08:45, or the later
   Kota load due 18:00?"* MSG017 asks with order references; descriptors are kinder and reference
   numbers can ride along in brackets.
3. **Still ambiguous after two attempts → escalate** as `AMBIGUOUS_SHIPMENT`. Do not guess, and do not
   loop.

### Communicating uncertainty (§12.1 Q3)

`confidence_code` must reach the driver, framed as a choice rather than a hidden risk:

- **HIGH** — proceed normally.
- **MEDIUM** — proceed, state the assumption once.
- **LOW** (SHP1013 / ETA008) — **do not commit silently.** *"I can hold 11:00, but if that time is
  uncertain, the 12:15 window gives you an hour of cushion and avoids a second reschedule."*
  Let the driver price their own risk; that is a decision they are better placed to make than the system.

## 7.3 The planner console — the throughput-critical surface

### Load arithmetic (what the screen must survive)

The pending queue does *not* contain the day's 190–240 planned appointments — those were booked by
`PLANNER` ahead of time. It contains only exception-driven requests (`booking_source` =
`DRIVER_CHAT` / `SCHEDULING_TOOL`): **15–25 on a normal day, and 20–35 inside 30 minutes during a
disruption spike** (§1.1). Against 5 coordinators, a spike is roughly **one decision every 5 minutes
per coordinator**, each under a 15-minute D9 deadline.

That is comfortably achievable — *but only if a decision takes under 30 seconds*. Everything below
follows from that budget.

### The 30-second row

A planner must decide without opening anything. Each queue row carries:

| Field | Why it is on the row |
|---|---|
| Driver · shipment · carrier | Identity, one line |
| Requested interval — dock, start–end | The actual ask |
| **Condensed receipt** — e.g. *"CRITICAL · 70 min late · exact dock · 0 min wait"* | The score terms in words. The planner should never reconstruct why this was proposed. |
| **Displacement check** — "conflicts with none" / "would delay SHP-xxxx" | The single most important field. Confirming must never quietly hurt a third party. |
| ETA confidence | `LOW` (SHP1013, MSG005) means *do not confirm* — ask first |
| Driver's own limit | `latest_acceptable_ts` (EXC002 = 13:30) — confirming past it creates a new exception |
| TTL remaining | The D9 clock, colour-coded |

### Five affordances, not two

Confirm and Reject are not enough. **Reject without an alternative is a dead end** — the driver is
pushed back to a phone call, which is the failure mode the product exists to remove.

1. **Confirm** → CONFIRMED, notify driver.
2. **Counter-offer** → planner picks a different feasible interval; driver gets a new option set. This
   is the affordance most systems omit and the one that keeps the conversation alive.
3. **Reject + reason** → typed reason (capacity, rule, priority conflict); reason text feeds the
   driver explanation, so it is a controlled vocabulary, not free prose.
4. **Hold for information** → pauses the D9 clock once, with a mandatory question routed to the driver.
5. **Escalate** → hands to a senior/regional owner with the thread attached.

### Bulk confirm — how to recover throughput without breaking D6

D6 says no rules-based auto-confirm. Bulk confirm preserves that authority while restoring speed: the
rules *select* the batch, a human *presses the button*. Eligible for the safe batch only when **all**
hold:

- zero displacement (no interval conflict, nothing re-sequenced),
- exact dock-type match (no `P_dock` penalty applied),
- ETA confidence ≠ `LOW`,
- start inside operating hours and before `LAST_NEW_START_TIME` (RULE005),
- no open escalation on the shipment.

Anything failing one predicate falls back to individual review. This is worth writing down explicitly
— it is the honest way to get D6's safety and still clear a 35-request spike.

### Queue ordering — not FIFO

Pure FIFO buries a CRITICAL request that arrived late (§7.2, the seeded SHP1014 case: CRITICAL, entered
the queue *after* lower-priority requests). Pure TTL ordering does the same. Order by a composite
urgency: TTL remaining, priority code, and whether the driver is **physically waiting at the gate**
(`facility_checkins.queue_state` ∈ WAITING_*). A truck burning detention in the yard outranks one
still in transit — that is the §13.1 "average driver waiting" metric expressed as a sort order.

## 7.4 Escalation model

### States and ownership

`OPEN → ACKNOWLEDGED → IN_PROGRESS → RESOLVED` (plus `CANCELLED`). Every escalation has a named owner
from the moment it is acknowledged, and an SLA clock that differs by reason. An escalation with no
owner is just a list.

### Reasons — each grounded in a seeded case

| Reason | Seeded instance | SLA posture |
|---|---|---|
| `NO_FEASIBLE_SLOT` | SHP1015 — reefer pinned to D5 (RULE003), D5 down 18:00–22:00 (DEVT002) | Immediate; §12.1 Q10. **Only when the whole horizon is exhausted** — same-day exhaustion is `NO_SAME_DAY_SLOT`, which is not an escalation (Stage 0) |
| `PENDING_EXPIRED_UNACTIONED` | Created by D9 | Immediate — capacity was just released |
| `AMBIGUOUS_SHIPMENT` unresolved | THR010 / DRV004, two assignments, `shipment_id` NULL | After N clarification turns |
| `LOW_CONFIDENCE_ETA` blocking a decision | SHP1013 / MSG005 "late by one hour" | Soft |
| `WAREHOUSE_REPLY_CONFLICT` | §11.2 — reply contradicts stored schedule | Immediate, never auto-reconcile |
| `NOTIFICATION_FAILED` | **OM004** — FAILED email on the reefer exception | Immediate: a confirmation nobody received is not a confirmation |
| `NOTIFICATION_UNROUTABLE` | **CON005** — GGN night-shift contact exists with a NULL email | Immediate, but a *different* fix and a different owner from the above: this fails **before** any send is attempted, so retrying is pointless and the resolution is to correct the contact record. Detect it when the outbox resolves recipients, not when a send fails |
| `SAFETY_OR_REGULATED` | brief §9.3 | Immediate, human-only |
| `CAPACITY_EVENT_CASCADE` | DEVT001 — D3 leveller failure stranding SHP1005 | Batch (below) |

### Cascade handling — one incident, not N escalations

When DEVT001 takes D3 out from 09:15 to 13:00, every appointment on D3 in that window becomes
infeasible simultaneously. Creating one escalation per shipment gives the planner a queue of
identical, individually-unsolvable items.

**Model it as a single capacity incident** with N affected shipments, re-planned as a batch through
the sequencer (D5: it proposes, the planner applies). This is exactly the brief's "a warehouse blocks
one dock unexpectedly → several appointments may require reconsideration" (§7.2), and it is why the
sequencer earns its place rather than being an optional flourish.

### What ops takeover actually replaces — and the schema already supports it

The shipped schema anticipated this, which is a good signal we are aligned with its intent:
`chat_threads.thread_status` includes `ESCALATED`, and `chat_messages.sender_type` includes
`OPERATIONS`. So takeover is: set the thread to `ESCALATED`, **stop the assistant from auto-replying
on that thread**, and let a human post as `OPERATIONS` in the same conversation the driver is already
reading. THR005 is the seeded example, already sitting in `ESCALATED`.

Two rules that matter:
- **The driver is told a human has joined.** Silent takeover reads as the bot ignoring them.
- **The assistant stays available to the human as a co-pilot** — summarise the thread, fetch context,
  draft a reply for approval. That is the ops-side assistant use case, and it is where the LLM adds
  the most value per token in this whole product.

### Metrics for this surface

Queue depth over time · median time-to-decision · **expiry rate** (the D9 canary) · reject-with-counter-offer
vs reject-flat · escalations by reason · takeover rate · post-takeover resolution time.

---

## 7.5 Role-scoped tool catalogs — the three-quarters of the system that has no tools

The 23-tool catalog is **entirely driver-scoped**. That was reasonable when the driver conversation was
the product, but D6 moved the throughput-critical decision onto a human planner, M13 requires gate and
yard truth to be *writable*, and brief §7.3 frames the scheduling engine explicitly as "a controlled tool"
the agent calls. All three of those surfaces currently have zero tools, which means the most important
actor in the design — the planner clearing a 35-request spike under a 15-minute clock — has no defined
interface at all.

Three principles hold across every tool below, and they are what keep the plane boundary of §1 intact:

1. **Scope is derived from the authenticated identity, never from an argument.** No tool accepts a
   `facility_id` or `carrier_id` that decides what the caller may see (M15). Where an id appears, it
   selects *within* the caller's scope and is validated against it.
2. **Typed outcomes, never prose.** Every mutating tool returns a discriminated result. "It worked" and
   "it didn't" must be distinguishable by code, not by reading a sentence.
3. **Snapshot-guarded and idempotent.** Anything that consumes capacity takes an `Idempotency-Key` and a
   `snapshot_hash`, and refuses on drift — the same staleness discipline as the driver path (M10), for the
   same reason: planners are also looking at a screen that was rendered some seconds ago.

### 7.5.1 Planner console

The five affordances of §7.3 plus bulk confirm, the queue read, and dock-blocking (§2's persona table lists
"block docks" as a core planner job; found with no backing tool anywhere in §7.5 on a 2026-08-20 UI-UX
recompare). These are the throughput path.

| Tool | Arguments | Returns |
|---|---|---|
| `get_planner_queue` | `facility_id`, `horizon?`, `limit?` | Rows ordered by the §7.3 composite urgency (TTL remaining · priority · physically-waiting), each carrying the condensed receipt, displacement check, ETA confidence, `latest_acceptable_ts`, TTL remaining and `snapshot_hash` |
| `confirm_request` | `appointment_id`, `snapshot_hash`, `Idempotency-Key` | `CONFIRMED` · `ALREADY_ACTIONED` (the D9 sweeper or another planner won — see below) · `SNAPSHOT_STALE` · `DISPLACEMENT_DETECTED` (a conflict appeared since render; refuses and re-renders) |
| `counter_offer` | `appointment_id`, `dock_id`, `start_ts`, `reason_code`, `snapshot_hash`, `Idempotency-Key` | `COUNTER_OFFERED` + the new option set sent to the driver · `INTERVAL_UNAVAILABLE` · `SNAPSHOT_STALE`. Revalidates the proposed interval through Stage 1 — a planner may not hand out an infeasible slot by hand |
| `reject_request` | `appointment_id`, `reason_code` (controlled vocabulary: `CAPACITY`, `RULE_VIOLATION`, `PRIORITY_CONFLICT`, `SAFETY`, `DATA_CONFLICT`), `note?`, `Idempotency-Key` | `REJECTED` + released interval + driver notification. `reason_code` is an enum precisely because it is rendered to the driver — free prose here becomes an unreviewed customer-facing message |
| `hold_for_information` | `appointment_id`, `question`, `Idempotency-Key` | `HELD_FOR_INFO` + `new_deadline`. **Pauses the D9 clock exactly once** per request; a second call returns `HOLD_ALREADY_USED`. Without that cap, "hold for info" becomes an unbounded way to sit on capacity |
| `bulk_confirm` | `appointment_ids[]`, `snapshot_hash`, `Idempotency-Key` | Per-id outcome list. **Server-side re-evaluates all five safe-batch predicates** of §7.3 (zero displacement · exact dock match · ETA confidence ≠ LOW · inside hours and before `LAST_NEW_START_TIME` · no open escalation) and refuses any id that fails, rather than trusting the client's selection |
| `escalate_request` | `appointment_id`, `reason`, `owner?` | `ESCALATED` + queue item id, thread attached |
| `block_dock` | `dock_id`, `window`, `reason`, `Idempotency-Key` | `BLOCKED` (writes a `dock_status_events` row — D1's declared single authority for availability, §0.9) · `ALREADY_BLOCKED` (overlapping window). Any `CONFIRMED`/`PENDING_CONFIRMATION`/`IN_PROGRESS` `dock_occupancy` row the new window overlaps is exactly how a `CAPACITY_EVENT_CASCADE` escalation begins (§7.4) — the tool does not silently strand appointments; it reports the affected set in its response so the caller can show it before committing |
| `end_dock_block` | `dock_status_event_id` | `UNBLOCKED` · `NOT_BLOCKED` |

**`bulk_confirm` is where D6 could quietly be violated,** so the design point deserves stating: the rules
*select* the batch, a human *presses the button*, and the server re-checks the predicates at press time
rather than at render time. That keeps the human authority real instead of ceremonial, and still clears a
spike. A client-side-only predicate check would be auto-confirmation wearing a button.

**The nastiest race in the product lives here** (§9.2 #3): `confirm_request` and the D9 expiry sweeper
firing on the same row. Both actors believe they acted. Resolution: the sweeper's transition and the
confirm both take the row under the same transaction, exactly one commits, and the loser gets
`ALREADY_ACTIONED` with the winning transition named. The audit log must show which won and why — a
planner who clicks Confirm and sees the slot vanish deserves a reason, not a refresh.

### 7.5.2 Gate and yard

M13's writes. `facility_checkins` is the only source of *actual* arrival truth, and today nothing can
write it — which makes the early/late/waiting/unloading scenario of brief §7.3 unimplementable and leaves
the sequencer's release-time input (`gate_in_ts` overriding ETA) permanently null.

| Tool | Arguments | Returns |
|---|---|---|
| `record_gate_in` | `shipment_id`, `ts`, `Idempotency-Key` | `GATE_IN_RECORDED` + computed `arrival_state` (EARLY/ON_TIME/LATE, derived from the appointment and RULE001's 60-minute early limit) · `ALREADY_CHECKED_IN` · `NO_ACTIVE_APPOINTMENT` |
| `update_queue_state` | `shipment_id`, `queue_state`, `queue_position?` | `QUEUE_UPDATED` · `INVALID_TRANSITION` (the state machine is enforced server-side, not by the kiosk) |
| `record_dock_in` | `shipment_id`, `dock_id`, `ts` | `DOCK_IN_RECORDED` · `DOCK_OCCUPIED` (another truck's interval is live — this is a real operational catch, not a theoretical one) · `DOCK_MISMATCH` (arriving at a dock other than the confirmed one; allowed, but recorded as a deviation) |
| `record_unload_start_end` | `shipment_id`, `phase` (`START`\|`END`), `ts` | `RECORDED` + on `END`, an **overrun delta** against `expected_unload_min`, which is the trigger for the DEVT003-style re-sequence and the input to churn pricing |
| `record_gate_out` | `shipment_id`, `ts` | `COMPLETED` + dwell time (`gate_out − gate_in`), the raw material for the detention metric of §8 |

Per §6.2 #11, these write an **append-only event stream**; the current-state view is derived. The shipped
`facility_checkins` row with its UNIQUE `shipment_id` becomes that view, not the write target.

### 7.5.3 Sequencer

D5 says the sequencer proposes and a planner applies, so these are planner-scoped, not agent-scoped. The
agent may *read* a proposal to explain it; it may never apply one.

| Tool | Arguments | Returns |
|---|---|---|
| `propose_facility_schedule` | `facility_id`, `horizon_end?`, `trigger_reason` | `scheduling_run_id`, the §5.1 diff (unchanged / moved / newly placed / unplaceable), objective values, `snapshot_hash` · `RUN_ALREADY_ACTIVE` (one run per facility, serialised — §5.1's debounce rule expressed as a return value) |
| `apply_schedule_proposal` | `scheduling_run_id`, `snapshot_hash`, `Idempotency-Key` | `APPLIED` (all-or-nothing) + notification batch id · `SNAPSHOT_DRIFT` → re-run required · `PARTIALLY_INFEASIBLE` → refuses entirely. **There is deliberately no "apply these three rows" argument** — cherry-picking produces a schedule nobody validated (§5.1) |
| `get_scheduling_run` | `scheduling_run_id` | The stored run: input snapshot, proposal, objective values, explanation — replayable a month later, which is what makes §8's "how the business can trust the allocation" answerable |

### 7.5.4 The driver allowlist, enumerated

Appendix A argues for shrinking the driver tool surface to ~8–10 of the 23, on the grounds that every
schema is input tokens on every call and a wider surface degrades selection accuracy. That claim is only
actionable if the list is named. **Driver allowlist:**

`get_driver_operational_context` (pre-fetched at session open, so usually zero calls) ·
`list_active_shipments` · `get_latest_eta` · `get_current_appointment` · `report_delay_or_update_eta` ·
`find_feasible_slots` · `request_slot` · `confirm_held_slot` · `get_appointment_request_status` ·
`explain_slot_eligibility` · `cancel_appointment` · `escalate_exception`.

That is 12, and the honest reason it is not 9: `confirm_held_slot` and `explain_slot_eligibility` are new
and both are load-bearing. The remaining 11 of the 23 — profile reads, ETA history, facility details,
vehicle and carrier lookups, dock maintenance alerts, gate status, conversation memory — either fold into
the pre-fetched context block or are rare enough to justify a second-tier catalog loaded on demand.
`reschedule_appointment` collapses into cancel + request under D1, since a reschedule is now two interval
operations rather than one row update.

### 7.5.5 Ops console

§7.4 gives the escalation lifecycle and cascade rule, but — unlike planner, gate/yard, sequencer and
driver — never named the tools that back it. Found on a UI-UX recompare (2026-08-20): a coordinator's
own actions had no defined contract at all. These close that gap, under the same three principles §7.5
opens with (identity-derived scope, typed outcomes, snapshot/idempotency where a write is consequential).

| Tool | Arguments | Returns |
|---|---|---|
| `get_escalation_queue` | `facility_id?` (omitted = all facilities in scope), `owner?` (`mine`\|`unowned`\|`all`) | Rows ordered by time-to-SLA-breach ascending, unowned pinned above owned — each carrying reason, owner, stepper position, SLA remaining, and (for `CAPACITY_EVENT_CASCADE`) the affected-shipment set |
| `acknowledge_escalation` | `escalation_id`, `Idempotency-Key` | `ACKNOWLEDGED` (owner set to caller, stepper advances) · `ALREADY_ACTIONED` (another coordinator won the race — same transactional pattern as `confirm_request`'s race in §7.5.1, applied here to acknowledgement) |
| `reassign_escalation` | `escalation_id`, `new_owner_id` | `REASSIGNED` · `NOT_ACKNOWLEDGED` (nothing to reassign until someone has claimed it) |
| `take_over_thread` | `thread_id`, `escalation_id`, `Idempotency-Key` | `TAKEN_OVER` (sets `chat_threads.thread_status = 'ESCALATED'` if not already, disables assistant auto-reply on this thread only, and posts the driver-visible join notice) · `ALREADY_TAKEN_OVER` |
| `hand_back_thread` | `thread_id` | `HANDED_BACK` (re-enables assistant auto-reply, posts the driver-visible notice) · `NOT_IN_PROGRESS` (refuses on an unacknowledged escalation — nobody has taken responsibility for what happens if the driver replies immediately after) |
| `resolve_escalation` | `escalation_id`, `reason_code` (`ISSUE_FIXED`), `Idempotency-Key` | `RESOLVED` |
| `cancel_escalation` | `escalation_id`, `reason_code` (`SHIPMENT_CANCELLED`\|`DUPLICATE`\|`CREATED_IN_ERROR`), `Idempotency-Key` | `CANCELLED` |
| `request_sequencer_proposal` | `escalation_id`, `facility_id` | Delegates to §7.5.3's `propose_facility_schedule` with `trigger_reason = 'CAPACITY_INCIDENT'` and the `escalation_id` attached to the resulting `scheduling_run_id`, rather than a parallel tool — the incident and the run stay linkable. Returns the same shape §7.5.3 already defines. **Ops triages and requests; a planner still applies** (`apply_schedule_proposal`, §7.5.3) — this tool cannot itself apply a proposal, preserving D5 across the two-surface handoff |

**`reason_code` for resolve/cancel — `Source: assumption, untested`.** Unlike `reject_request`'s
`reason_code` (§7.5.1), no seeded case in this document grounds this exact value set; it is inferred
from what §7.4 already distinguishes (issue genuinely fixed vs. three different ways an escalation stops
applying) rather than drawn from an existing example. Revisit if real usage surfaces a reason these three
don't cover.

Co-pilot capabilities (summarise-thread, fetch-context, draft-reply-for-approval, §7.4) are intentionally
**not** in this table — they are LLM-assisted actions scoped to an active takeover, not new mutating
tools; drafting produces text a human still sends through the ordinary chat-send path, not a new capacity
or escalation-state effect.

### 7.5.6 Carrier portal

§2's persona table scopes this role to `shipments`, `drivers`, `vehicles` by `carrier_id` and lists no
write job — found with no backing tool anywhere in §7.5 on the same 2026-08-20 UI-UX recompare that found
§7.5.5 and §7.5.1's `block_dock`. **Read-only, every tool scope-derived from the caller's own `carrier_id`
(M15), never accepted as an argument** — the same principle §7.5 opens with, applied to a role with no
write surface at all rather than a partial one.

| Tool | Arguments | Returns |
|---|---|---|
| `get_fleet_overview` | *(none — carrier derived from identity)* | Active shipment count, open exception count, current on-time performance figure — the portal's own summary strip |
| `list_fleet_shipments` | `status_filter?` | This carrier's shipments across every facility they operate at (carriers are not facility-scoped, unlike every other role) — each row carrying promise state, dock/date, and an exception flag |
| `get_shipment_detail` | `shipment_id` | Full detail for one shipment — **validates the shipment belongs to the caller's own `carrier_id` server-side**, refusing (not merely hiding) a cross-carrier id rather than trusting the client not to pass one, per U28/M15 |
| `list_fleet_exceptions` | *(none)* | Open `driver_exceptions`/`escalation_queue` entries tied to this carrier's shipments — status only, never another carrier's queue position or why a contested interval was lost (U28) |
| `get_carrier_on_time_performance` | `window` (`30d` default) | This carrier's own on-time performance series for the sparkline (U33/U66) — **never a cross-carrier comparison, benchmark, or rank**, not even as an aggregate count that would let one be inferred (`auth-and-scoping.md`'s inference-risk rule) |

**No mutating tool exists here by design** — the persona table lists no write job for this role, and none
should be invented. A carrier manager who needs to act on an exception (contact a driver, contest a
rejection) does so through the conversation/control planes that already own that action, not through a new
capability this portal would otherwise be the first surface to introduce.

### 7.5.7 Admin console

§2's persona table scopes this role to `users`, `roles`, `user_scopes`, `facility_rules`,
`policy_versions`, `audit_logs` — found with no backing tool anywhere in §7.5, the fourth instance of this
project's gap class (after §7.5.5, §7.5.1's `block_dock`, §7.5.6). Four areas, one principle each already
established elsewhere in this document, applied here rather than invented fresh: **user/role changes are
scope-assignment writes (M15)**, **policy changes are versioned and simulated before publish (D7, U27)**,
**facility-rule changes go through the typed rule-type registry** (§0.9 issue 10's resolution — never
free-text rule matching), **every write here is itself an audited event** (M14) — this is the one console
whose own actions are the primary subject of the audit trail it also exposes.

| Tool | Arguments | Returns |
|---|---|---|
| `list_users` | `role_filter?`, `facility_filter?` | Users with role, scope, and active/inactive status |
| `invite_user` | `email`, `role`, `scope` (facility/carrier/driver id, matching `role`) | `INVITED` — role and scope set in the same call, never a two-step "create then scope" sequence (closes the exact gap window M15's foundational-architecture framing exists to prevent) |
| `update_user` | `user_id`, `role?`, `scope?` | `UPDATED` |
| `deactivate_user` / `reactivate_user` | `user_id` | `DEACTIVATED` / `REACTIVATED` — reversible, distinct from `remove_user` |
| `remove_user` | `user_id`, `Idempotency-Key` | `REMOVED` — permanent; High-tier destructive action (`components.md` §19), typed confirmation required |
| `list_facility_rules` | `facility_id?` | Rules with their typed `rule_type` (the registry §0.9 issue 10 resolves — `EARLY_LIMIT`, `DOCK_PIN`, `WEIGHT_LIMIT`, `NEW_START_CUTOFF`, etc., not free text), value, and `effective_from`/`effective_to` (now genuinely time-bounded, not bare dates) |
| `create_facility_rule` / `update_facility_rule` | `facility_id`, `rule_type`, `rule_value`, `effective_from`, `effective_to` | `CREATED`/`UPDATED` — `rule_type` is drawn from the registry enum, never accepted as a free string |
| `simulate_policy_weights` | `weights` (the Stage-2 coefficient set, `w_fairness` included), `window` | **Read-only** — replays the window's actual decisions against the proposed weights and returns aggregate flip count plus example before/after cases, never writes a `policy_versions` row |
| `publish_policy_version` | `weights`, `Idempotency-Key` | `PUBLISHED` — creates a new, immutable `policy_versions` row stamped onto every subsequent decision (D7); never mutates a prior version |
| `get_audit_log` | `actor?`, `event_type?`, `date_range?`, `resource?` | `audit_logs` entries — actor, action, timestamp, affected resource, and the `policy_version`/tool-call reference where relevant (M14's exact field set) |
| `export_audit_log` | `actor?`, `event_type?`, `date_range?` | CSV, same filters as the current view — never a silent full-table export ignoring whatever the admin was actually looking at |

**`simulate_policy_weights` is deliberately read-only and separate from `publish_policy_version`** — the
same select-then-press-button discipline `bulk_confirm` (§7.5.1) already established: a simulation informs,
a publish commits, and the two are never collapsed into one call that could accidentally publish while
only intending to preview.

### 7.5.8 Shared / cross-cutting tools — used by every role, owned by none

Found 2026-08-22 while checking the completed UI-UX mockup work (sign-in, role picker, password reset, the
user menu, the notifications panel, the search palette, the account/settings page) against this document's
own tool catalogs — **zero of the seven screens had a backing tool anywhere in §7.5.** Unlike §7.5.5,
§7.5.1's `block_dock`, §7.5.6, and §7.5.7 (each a gap inside *one* role's catalog), this is a fifth,
structurally different instance: the gap sits **between** the six role-scoped catalogs, in the shell every
role shares, so no single §7.5.x subsection was the natural place to notice it was missing.

**`search_records` deliberately does not own data.** Every other tool in §7.5 is scoped to one module's
tables. Search reads across several — shipments (Exception Intake), appointments (Allocation), drivers and
carriers (Identity & RBAC), facilities (Capacity & Rules Admin) — which would violate `SYSTEM_DESIGN.md`
§3's "no cross-module table access" rule if it queried any of those tables directly. It doesn't: it calls
each contributing module's own existing read method and composes the results at the API layer, the same
"routers stay thin, services hold the calls" discipline `AGENTS.md` already mandates elsewhere. This is
a composition capability, not a thirteenth module — nothing new is owned, nothing new needs its own tables.

| Tool | Arguments | Returns |
|---|---|---|
| `search_records` | `query`, `entity_types?` (defaults to all types the caller's role can see) | Results grouped by entity type, each composed from that entity's owning module's own search method — never a direct query against another module's tables. **Facility-scoped by default for facility-bound roles; no cross-facility toggle in v1** (deferred, `UI-UX/00-foundations/stitch-prompts-shared-shell.md` prompt 6) |
| `get_notifications` | `cursor?`, `unread_only?` | This user's notification feed, reverse-chronological — Module 10 (Notification/Outbox), a read extension of the outbox it already tracks delivery through |
| `mark_notifications_read` | `notification_ids[]` | `READ` — idempotent; marking an already-read notification read again is a no-op, not an error |
| `get_notification_preferences` / `update_notification_preferences` | *(none)* / `categories` (grouped, not per-event — matches the Linear-model decision locked this session, not GitHub's per-event granularity), `channels` (web push, SES email), `digest_mode` (email only) | Current preferences / `UPDATED` |
| `get_account_profile` | *(none — identity from the verified token, M15)* | Name, email/phone, role, scoped facilities — **read-only**, since Supabase Auth is the identity source of record; there is no `update_account_profile`, by design |
| `request_password_reset` | `email` | Identical response whether or not the email matched an account (`auth-and-scoping.md`'s enumeration-safety rule) — wraps Supabase Auth's `resetPasswordForEmail` directly. **Decided 2026-08-22: email-only for v1** — phone-registered accounts have no self-service reset path yet |
| `sign_out_everywhere` | *(none — acts on the caller's own identity)* | Revokes every refresh token for this user — Supabase Auth's `signOut({ scope: 'global' })`. **⚠️ `global` is Supabase's own *default* scope for a plain sign-out call** — the ordinary single-device "Sign out" action in the user menu must explicitly pass `{ scope: 'local' }`, or it silently becomes this tool instead. State this in the implementation, not just here, or the two buttons collapse into one by accident |

**Password reset is email-only for v1 — decided, not overlooked.** The sign-in field still accepts email
or phone (drivers know their phone number), but a phone-only account that forgets its password has no
self-service path right now. This is more defensible here than it would be for a desk role: `auth-and-scoping.md`
already establishes the driver session as long-lived with silent refresh, specifically because signing a
driver out mid-exception is a product failure — so a driver re-entering a password at all is already a rare
event, not a daily one. The gap is real but narrow. If it needs closing later, the fallback is an admin
resetting the account via the already-existing `update_user` tool (§7.5.7), not a new phone-OTP flow built
for a case that may not come up often enough to justify it.

**What `sign_out_everywhere` actually guarantees, stated honestly**: it revokes refresh tokens, preventing
any device from obtaining a *new* access token. It does **not** instantly invalidate an access token
already issued to another device — that token remains valid until its own short expiry, per Supabase Auth's
documented behaviour. The user-facing copy should say "signs out other devices" rather than imply an
instant kill switch, since the latter overstates what the mechanism does.

**Where notification state lives**: Postgres, not Redis — both `get_notification_preferences`' settings and
`get_notifications`'/`mark_notifications_read`'s read/unread markers are durable state a user expects to
survive well past 24 hours, which is exactly what disqualifies Upstash per this project's own rule
(*"Upstash Redis holds bounded, non-authoritative conversation/session state with a 24-hour TTL"*). This
isn't a new decision — it's the existing Postgres-vs-Redis rule applied to a case that's easy to
miscategorise as "just session state" because it's user-facing and low-stakes.

**Not a tool, by design**: the appearance/theme toggle. It is a client-only preference (localStorage or
equivalent) with no server state and no `user_id` binding requirement — inventing an endpoint for it would
be exactly the kind of scope creep `TECH_STACK.md`'s "5-person internal tool" calibration exists to catch.

**Search engine decision**: PostgreSQL full-text search (`tsvector`/`tsquery`) plus `pg_trgm` for fuzzy
matching — **not** a dedicated search engine (Elasticsearch/Meilisearch/Algolia). Verified against current
guidance: Postgres FTS alone is the recommended default under roughly 500K rows and is explicitly framed as
sufficient for internal applications where search is a secondary feature, not the product — both true here
at 600–1,000 shipments/week. A dedicated engine becomes justified past ~2M rows or when search relevance is
itself the product, neither of which describes this system. Revisit only if evidence says otherwise, not
on a hunch that Postgres "won't be enough."

---

## 8. Observability, and how the business trusts it

The brief's closing challenge is *"explain not only what the system says, but how the business can
trust the allocation."* Three layers:

1. **Traces** (LangSmith / OTel): every turn — prompt, tool calls, latency, cost, tool errors.
2. **Decision receipts** (`allocation_decisions`, `scheduling_runs`): every promise is reconstructable
   — inputs, policy version, candidates, why the winner won.
3. **KPI mart**, mapped directly to §13.1:

| Measure | Definition |
|---|---|
| Time to usable outcome | first `chat_messages.message_ts` → appointment reaching CONFIRMED |
| Automation coverage | share of exceptions resolved without `escalation_queue` entry |
| **Conflicting/duplicate allocations** | **must be 0** — the headline correctness metric |
| Options later found infeasible | SHOWN options that failed revalidation at commit |
| No-feasible-slot escalations handled correctly | escalations with an ops resolution inside SLA |
| Avg driver wait after rescheduling | `dock_in_ts − gate_in_ts` from `facility_checkins` |
| Dock utilisation | booked dock-minutes ÷ available dock-minutes |
| Priority-policy violations | lower-priority load granted over blocked higher-priority one |
| Driver clarification turns | agent clarification messages per resolved exception |

---

## 9. Roadmap

**Phase 0 — Foundation.** Postgres migration of the schema (timestamptz, interval-based dock capacity,
partial unique indexes preserved), volume generator on top of the seeded edge cases, RBAC + scoping,
envelope/audit/api logging.

**Phase 1 — Single-driver correctness.** Chat intake → thread/exception → ETA declaration with
confidence → Stage 1+2 engine → SHOWN options with `REC-` tokens → HELD → PENDING_CONFIRMATION.
Planner confirm/reject. *Acceptance: brief §7.1 end-to-end, including a clarification turn.*

**Phase 2 — Concurrency and scarcity.** Holds with TTL, idempotency, the GiST exclusion constraint, conflict
refresh, escalation queue, ops takeover console, outbox notifications.
*Acceptance: §11.2 stress set — 10 drivers / 3–4 slots, two drivers picking within seconds, mid-conversation
capacity reduction, cancellation freeing a slot, duplicate messages, ambiguous shipment, no-feasible-slot.*

**Phase 3 — Facility truth.** Gate/yard kiosk writing check-ins, live queue board, unload overrun
detection, no-show automation against RULE002/RULE006.

**Phase 4 — Facility sequencer.** Rolling-horizon re-sequencing over early/late/waiting/incoming
trucks with fixed in-progress work and a stability objective. *Acceptance: the §7.3 four-truck /
two-dock scenario produces a defensible sequence with a written explanation.*

**Phase 5 — Scale-out.** Multi-facility, carrier portal, analytics, policy admin UI.

**Explicitly out of scope** (§12.3): national network optimisation, carrier selection and rate
negotiation, shipment creation and driver/vehicle assignment (TMS-owned — §1), autonomous driver-safety
decisions, customs/hazmat/legal compliance, commercial penalty approval. Say so in the deck — scope
discipline reads as seniority.

---

## 9.1 Data generator

**This section was written against the classroom seed file. Audited against the live Supabase project on
2026-08-19, most of it already exists.** What follows is reframed accordingly: what the live database
already gets right, what §9.1 originally specified, and the four gaps that remain (D14/D15).

### Three layers, never mixed

| Layer | Content | Mutability |
|---|---|---|
| **A — Seed** | The shipped rows, verbatim: SHP1001–1021, DRV001–015, THR001–012, APT1001–1020, DEVT001–003, OM001–005, RULE001–006 | **Ids and relative timings are immutable and CI-asserted byte-identical. The absolute base date is a single parameter** (D14) — see "rebasing Layer A" below. This is a deliberate refinement: the original "byte-identical, full stop" rule cannot survive D14's date shift, but the thing that rule actually protects — that SHP1015 is still a reefer pinned to D5 by RULE003, still blocked by a DEVT002-shaped outage, still escalates for the same reason — survives untouched. |
| **B — Background** | Generated volume to D8 scale across a **seven-day window** (see the table below) | Regenerated freely from a seed value. **Already built and populated in the live project** (below). |
| **C — Contention** | Scripted pressure scenarios (below) | Parameterised, deterministic |

The separation is the point. If the generator can touch Layer A, a regression in the generator
silently invalidates every graded edge case — and you would not notice, because the tests would still
pass against the corrupted fixtures. Load A last, and assert it.

### What the live database already gets right

Audited 2026-08-19: 6 facilities · 25 docks · 106 drivers · 105 vehicles · 671 shipments · 3,574
appointment slots · 1,557 appointments · 807 ETA updates · 405 check-ins · 264 exceptions · 1,542 chat
messages — all within or close to the §11.1 targets below, and **Layer A survives verbatim** (21/12/10/20
seeded rows, unmodified). Whoever built this generator already respected the layer separation above; it
was an earlier draft of this document, not the database, that assumed the work was unstarted.

### Layer B volumes — the brief's own numbers (§11.1), against what is live

| Entity | Target (§11.1) | Live | |
|---|---|---:|---|
| Facilities | 6 | 6 | ✅ |
| Docks | 24–32 | 25 | ✅ |
| Drivers | 80–120 | 106 | ✅ |
| Vehicles | 90–140 | 105 | ✅ |
| Shipments | 600–1,000 | 671 | ✅ |
| Appointment slots | 2,000–3,000 | 3,574 | over target — fine, see the note on grid size below |
| Appointments | 900–1,500 | 1,557 | over target |
| ETA updates | 800–1,500 | 807 | ✅ |
| Facility check-ins | 400–700 | 405 | ✅ |
| Exceptions | 250–400 | 264 | ✅ |
| Chat messages | 1,500–3,000 | 1,542 | ✅ |

**One structural difference worth naming, not fixing:** the live grid runs mostly on **30-minute** slots
(3,468 of 3,574) rather than the classroom seed's 60-minute grid. That is closer to D11's 15-minute start
granularity than the original grid ever was, and under D1 the slot grid is only a publishing layer — the
booking authority is `dock_occupancy`'s true intervals. Leave it as generated.

### The four gaps that remain (D14/D15)

The live database is not simply "done" — four things §9.1 requires are still missing, and none of them
are volume:

1. **Layer A and Layer B occupy different dates and never coexist.** Layer A sits on 2026-08-04 (2
   facilities, 9 docks); Layer B on 2026-08-10→16 (6 facilities, 23 docks). You cannot demonstrate
   SHP1015's reefer escalation *alongside* realistic multi-facility load, because on the only date SHP1015
   exists, four of the six facilities do not. **Fixed by D14** — rebase Layer A onto the Layer B window.
2. **Capacity incidents exist only at Jaipur.** 3 `dock_status_events` rows, all from the classroom seed,
   against 25 docks. The DEVT001 cascade scenario (§7.4, "one incident, not N escalations") has nothing
   to exercise it anywhere else.
3. **No facility rule has intraday effectivity.** 14 rules live, **zero** with `effective_to` set — the
   same gap §6.2 #10 found in the schema is reproduced in the data. §11.3 explicitly requires this
   imperfection and nothing currently produces it.
4. **Location-spelling and wording imperfections are thin.** §11.3 also asks for inconsistent free-text
   location names and different wordings for the same exception reason; worth an explicit pass once 1–3
   are done, since it is the cheapest of the four to add.

**Deliberately not a gap:** the 116 dock-weight violations and 85 true-interval overlaps already present
in the live data (§6.2 #7, #1) are **kept**, not cleaned, per D15 — they become the D12 backfill worklist
and prove the reassignment/resolution paths actually work against real rows rather than synthetic ones.

### Rebasing Layer A (D14) — what moves and what doesn't

Per the Layer A mutability rule above: shipment ids, thread ids, exception ids and every *relative*
timing (an ETA update 45 minutes after gate-in stays 45 minutes after gate-in) are unchanged. Only the
absolute base date shifts, from 2026-08-04 to **2026-08-13**. Concretely, every Layer A timestamp is
offset by the same delta (`+9 days`), so `SHP1015`'s declared ETA moves from `2026-08-04T18:30` to
`2026-08-13T18:30`, RULE003/DEVT002 keep pinning and blocking D5 in exactly the same relative window, and
the CI assertion becomes "ids and offsets match the seed" rather than "timestamps match the seed
literally."

### The contention recipe — engineering scarcity, not volume

From the §0 arithmetic: contention comes from *clustering*, not daily totals. So construct it directly —
against the rebased **2026-08-13** snapshot (D14), so the contention scenario sits on the same date as
everything else being demonstrated, not on an isolated day nothing else touches.

Jaipur standard docks D1–D4, evening block **17:00–21:00** (RULE005 forbids new starts after 21:00, so
the block closes itself naturally). That is 4 docks × 240 min = **960 dock-minutes**. A typical 60-minute
unload plus D10's 15-minute changeover consumes 75 → roughly **12 placeable intervals** in the block.

To reproduce §11.2's *"at least 10 drivers request alternatives for the same facility and evening
window while only 3–4 compatible slots exist"*: commit **9** of those intervals in advance, leaving 3
open, then fire **10 exceptions** whose declared ETAs land between 17:00 and 19:00. The scarcity is
then a property of the data, not a staged demo — which is exactly what makes the demonstration credible.

Layer C also scripts: a mid-conversation capacity reduction, a cancellation that frees an interval
while a driver deliberates, two drivers selecting within the same second, and a CRITICAL load entering
the queue after lower-priority requests.

### Generator invariants (assert these, or the baseline is already broken)

- Every generated appointment satisfies Stage 1 **at generation time** — otherwise the fixture starts
  in a state the engine would reject. **This is a going-forward invariant, not a retroactive one:** the
  live data already contains 116 weight violations and 85 overlaps from before this rule was written down,
  and D15 keeps those on purpose as the migration worklist. The invariant governs anything the generator
  produces *from now on* — it does not mean go back and silently fix the existing rows.
- No dock overlap (do not rely on the exclusion constraint to reject; the generator should never emit it).
- Weight ≤ dock maximum · temperature-controlled only on `supports_refrigerated` · >25,000 kg on HEAVY (RULE004).
- `eta_updates` monotonic in `created_at` but **not** in `declared_eta` — corrections move both ways
  (SHP1006 goes 10:50 → 11:20; a driver who makes up time moves earlier).
- Priority mix drawn from the seed's own proportions (of 21: LOW 4, NORMAL 9, HIGH 6, CRITICAL 2) —
  roughly 20/43/28/9%. Do not generate a fleet that is half CRITICAL.
- Unload durations 45–90 min, correlated with weight and product class, not uniform random.

### Required imperfections (§11.3 — the data must be realistically dirty)

Missing delay durations · free-text location names with inconsistent spelling (*Neemrana / Nimrana*) ·
stale latest-ETA timestamps and several corrections in one thread · cancelled appointments still
visible in history · **rules effective for only part of the day** · different wordings for the same
exception reason. A generator that emits clean data produces an agent that has never met a real driver.

Live status (2026-08-19 audit): missing delay durations, stale/corrected ETA threads and cancelled
appointments in history are present (they arrive naturally from the seeded Layer A cases and the volume
generator's ETA-correction pass). **Intraday rule effectivity is not** — see gap 3 above — and
location-spelling variety is thin — gap 4. These two are what remains to add.

### Deterministic clock — easy to forget, fatal to omit

**The snapshot moves to 2026-08-13, Asia/Kolkata (D14),** from the originally stated 2026-08-04. The
reason is direct: 08-04 has only 2 facilities and 9 docks live, so no test run on that date can exercise
the multi-facility load §11.1 asks for. 08-13 sits midweek inside the generated Layer B window (435
slots, 23 docks live on that day), with three days of real history behind it — feeding
`appointment_history`, reschedule and on-time-performance queries — and three days of forward capacity
ahead, which is exactly what Stage 0's next-day search horizon needs to have something to find.

Every test must inject `now` rather than read the wall clock, or the entire suite starts failing the day
after it is written — and the failures will look like scheduling bugs. One injected clock, threaded
through the engine, the TTL sweepers and the sequencer.

## 9.2 Stress tests — the seeded cases as named, replayable tests

Each of the database guide's **29** cases (§6 of that guide) becomes a test with an asserted outcome.
The load-bearing ones:

| Test | Fixture | Must produce |
|---|---|---|
| `reefer_no_feasible_slot` | SHP1015 · RULE003 · DEVT002 | Zero options · `NO_FEASIBLE_SLOT` escalation · no booking attempt |
| `duplicate_retry` | THR001 / THR009, same `dedupe_key` | Exactly 1 exception, 1 hold attempt, 1 notification |
| `ambiguous_shipment` | DRV004 / THR010 (`shipment_id` NULL) | Clarification with human descriptors · no read that assumes a shipment |
| `low_confidence_eta` | SHP1013 · ETA008 (`LOW`) | No silent commit · risk-framed choice offered |
| `dock_breakdown_cascade` | DEVT001, D3 down 09:15–13:00 | **One** capacity incident + one sequencer proposal, not N escalations |
| `early_arrival_no_priority` | SHP1003, gate-in 08:20 for 09:00 | Early truck does not displace scheduled work · policy explained (MSG013) |
| `no_show_grace` | SHP1018 / APT1018 · RULE002 | `NO_SHOW` only after slot start + 30 min |
| `cancellation_frees_capacity` | SHP1008 / APT1008 | Freed interval appears in the very next option set |
| `heavy_vehicle_eligibility` | SHP1016, 31,000 kg | Only D6 offered — D1/D3 cap at 20,000 kg, D2/D4 at 25,000, D5 at 22,000; D6 is 35,000 |
| `weight_limit_violation` | SHP1005 → D3, SHP1014 → D1 (§6.2 #7) | Both flagged `REQUIRES_DOCK_REASSIGNMENT` by the backfill; neither is offerable to a new booking |
| `next_day_offer_accepted` | Any shipment whose horizon exhausts today | `NO_SAME_DAY_SLOT` (not an escalation) + a dated next-day option set |
| `ask_only_no_exception` | THR011 / DRV001 | Thread + recommendation created; **zero** `driver_exceptions` rows, no dedupe key, no SLA clock |
| `unroutable_notification` | CON005 (NULL email, GGN night shift) | `NOTIFICATION_UNROUTABLE` raised before any send is attempted |
| `eta_correction_sequence` | SHP1006 / ETA005 → ETA006 (10:50 → 11:20) | Latest declared ETA wins; both rows retained; no mutation of history |
| `appointment_history_chain` | APT1012A / APT1016A (`is_current=0`, `replaced_appointment_id`) | Superseded appointments stay visible; released `dock_occupancy` intervals return to the offer pool |
| `unload_overrun` | SHP1002 (70 min) · DEVT003 | Downstream trucks re-sequenced · churn counted and priced |
| `failed_notification` | **OM004** (`FAILED`) | Never treated as confirmation · escalation raised |
| `priority_late_entry` | SHP1014 CRITICAL, queued after NORMALs | Ranks above earlier requests · not buried by FIFO ordering |
| `cancelled_shipment_query` | THR012 / SHP1019 | Refuses to schedule · routes to dispatch (MSG020) |

### Four concurrency races worth naming individually

1. **`same_interval_race`** — 50 simultaneous requests on one interval → exactly 1 `HELD`, 49
   `SLOT_CONFLICT_REFRESH_REQUIRED`, zero 5xx.
2. **`hold_expiry_vs_confirm`** — the 90-second hold lapses in the same millisecond the driver
   confirms. Must resolve to exactly one outcome; never both a lapse notice and a pending appointment.
3. **`pending_expiry_vs_planner_confirm`** — the D9 sweeper fires as the planner clicks Confirm. The
   nastiest race in the design, because both actors believe they acted. Exactly one wins, and the
   audit log must show which and why.
4. **`ordinal_staleness`** — driver replies "2" against a `recommendation_id` that has since been
   re-ranked → rejected and re-presented. Never applied to the new list.

### Determinism assertion

Same snapshot + same `policy_version` → byte-identical ranking and byte-identical sequencer proposal,
run twice. Any drift means randomness leaked into an engine that promised none.

---

## 9.3 Migrating the live database (roadmap step 5)

The audit in §6.2 #5 and §9.1 found a live, populated Supabase project rather than an empty one. This is
the concrete sequence for turning it into what D1–D16 describe — written now, executed at step 5 of the
roadmap (design docs first: UI/UX, tech stack, deployment; then apply to the existing project).

1. **Backup first** (D16) — a Supabase dashboard snapshot or `pg_dump` of `kujffzgqjmqphkmrbawy`. This is
   the only safety net, since the migration runs directly on production rather than on a branch.
2. **Reconcile migration drift.** `supabase/migrations/20260817040000_escalation_resolution_note.sql`
   exists on disk but was not in the applied list as of the 2026-08-19 audit (5 applied, 6 files on disk).
   Resolve before adding a new migration on top.
3. `CREATE EXTENSION IF NOT EXISTS btree_gist;` — absent today (§0, D1 preconditions).
4. **Convert `text` → `timestamptz`** across `appointment_slots`, `appointments`, `shipments`,
   `eta_updates`, `facility_checkins`, `dock_status_events`. The existing values are ISO-8601 with a
   `+05:30` offset and parse directly; this is a type change, not a reformat.
5. **Create `dock_occupancy`** with the D1 exclusion constraint; backfill one row per active appointment
   (`PENDING_CONFIRMATION`/`CONFIRMED`/`IN_PROGRESS`) with `window = [slot_start_ts, slot_start_ts +
   expected_unload_min + 15 minutes)`.
6. **Route backfill conflicts to the D12 worklist**, not into silent fixes: the 85 true-interval overlaps
   land as `REQUIRES_TIME_RESOLUTION`; the 116 dock-weight violations land as `REQUIRES_DOCK_REASSIGNMENT`
   (D15). Both counts are as measured on 2026-08-19 and will need re-measuring at execution time.
7. **Rebase Layer A** onto the 2026-08-13 snapshot (D14) — shift every Layer A timestamp by the same
   delta, re-run the id/offset assertion described in §9.1's "rebasing Layer A" note.
8. **Add the remaining §11.3 imperfections** — capacity incidents beyond Jaipur, intraday facility rules,
   location-spelling variety (§9.1, "the four gaps that remain," items 2–4).

**Steps 3 and 4 are not optional cleanup — they are load-bearing for D1.** Attempting step 5 without them
fails on the first `CREATE TABLE dock_occupancy` (no `btree_gist`) or the first insert into a `tstzrange`
column built on `text` data. Writing that down here is the point of doing this audit before, not during,
the migration.

---

## 10. Verification — proving the system does not double-book

This is §12.1 Q13 and the thing a reviewer will actually push on.

1. **Concurrency harness.** Fire N=50 simultaneous `request_slot` calls at one interval from distinct
   sessions. Assert: exactly 1 → **`HELD`** (the D2 outcome — `PENDING_CONFIRMATION` only follows a
   `confirm_held_slot` inside the TTL); 49 → `SLOT_CONFLICT_REFRESH_REQUIRED` with fresh options; zero
   5xx; zero orphaned holds after TTL.
2. **Invariant queries, run continuously in CI.**
   - **No two `dock_occupancy` rows for one dock overlap** in a capacity-consuming state. This is the
     headline invariant; the GiST constraint should make it unfalsifiable, and the query proves it.
   - No shipment has >1 current active appointment.
   - No confirmed appointment overlaps a `dock_status_events` outage window.
   - No appointment starts after `LAST_NEW_START_TIME` without a recorded approval — **at facilities that
     define the rule**; FAC-GGN-01 does not, and an absent rule is unrestricted (§5 Stage 1).
   - Every reefer load sits on a `supports_refrigerated` dock; every load above a dock's
     `max_vehicle_weight_kg` is rejected — which, run against the shipped seed, must return exactly the
     two known violations of §6.2 #7 and nothing else.
3. **Idempotency replay.** Replay the seeded duplicate (`THR001`/`THR009`, same `dedupe_key`) →
   exactly one exception, one booking attempt, one notification.
4. **Scenario replay suite.** Each of the 29 seeded cases in the database guide §6 becomes a named
   test with an expected outcome — including the ones that must escalate (SHP1015 reefer, OM004
   failed email, contradictory warehouse reply). Coverage is asserted mechanically: a case with no
   named test fails the suite, so the mapping cannot silently rot.
5. **Determinism proof.** Same snapshot + same policy version → byte-identical ranking, twice.
   Tie-break by `shipment_id + slot_id`, no randomness anywhere in the engine.
6. **Chaos-lite.** Kill Redis mid-conversation; the next turn must still answer correctly from
   Postgres. Freshness comes from the database, never from cache.

---

## Appendix A — Latency architecture and region strategy *(provisional)*

> **Not binding.** D4 defers the tech stack and deployment, so everything below assumes a stack that has
> not been chosen. It is preserved as worked-through reasoning to draw on once that decision is made —
> read it as "here is how we would think about latency", not "here is what we are building on".


### First: the latency is not where you think it is

A driver turn decomposes roughly like this:

```
client → API        auth      Redis load     LLM call(s)      tool → Postgres      LLM final     stream out
 10–30 ms          ~1 ms       2–5 ms      ← DOMINANT →         5–50 ms each      ← DOMINANT →
```

**One tool hop costs two LLM inferences** (the call that decides to use the tool, and the call that
writes the answer). A three-hop turn costs four. So the ordering of levers is:

1. **Remove a tool hop** — saves a full inference plus a full network round trip.
2. **Cut time-to-first-token** — caching, smaller tool surface, lower effort, streaming.
3. **Co-locate the chatty tier** — DB and Redis next to compute.
4. **Region choice for the model hop** — real, but the smallest of the four.

Geography matters most because it is *multiplied by the number of sequential hops*. Mumbai→`us-east-1`
is roughly 200–250 ms round trip; four sequential LLM calls to a US region is ~1 s of pure network
before a single token is generated. The same four calls to a Mumbai-resident endpoint cost ~40–120 ms
in total. That is the whole argument.

### The co-location rule

> **Compute, Postgres and Redis go in one region. Only the model may be remote.**

Because tools make *many* round trips to the database (a feasibility query, a driver-context read, an
audit write) while the LLM is *one* round trip per loop iteration. Never split the chatty tier.

### For Maharashtra: `ap-south-1`

| Component | Choice | Note |
|---|---|---|
| Compute (FastAPI) | **`ap-south-1`** (Mumbai) | Physically in Maharashtra; ~5–15 ms from Mumbai/Pune |
| Supabase Postgres | **`ap-south-1`** | **Region is fixed at project creation** — changing it later is a full migration. Verify before you create the project. |
| Upstash Redis | **`ap-south-1`** primary | If using a Global database, ensure the *primary* is here — writes go to the primary, and every turn writes |
| Frontend (Vercel) | `bom1` for functions | Static assets are CDN-global regardless |
| Fallbacks if a service is absent in Mumbai | `ap-south-2` (Hyderabad), then `ap-southeast-1` (Singapore, ~50–70 ms) | Never fall back to a US region for the data tier |

### The AgentCore topology decision — the largest single risk

You said the loop is yours (LangChain `bind_tools` + bounded manual loop, no agent executor). Good —
that keeps the choice open. Two topologies:

- **(A) Loop runs inside AgentCore.** Every tool call crosses from AgentCore's region to your database.
  A 3-hop turn becomes 6+ cross-region round trips. If AgentCore is not in `ap-south-1`, this is
  seconds of avoidable latency.
- **(B) Loop runs in your FastAPI in `ap-south-1`, next to Postgres and Redis.** AgentCore is used for
  identity, memory, gateway and observability; Bedrock is called for inference. **Only the LLM hop is
  remote.** ✅ Recommend this.

The principle, stated so it survives a region change: **co-locate with the data, not with the user.**
Driver→API is one hop; tool→DB is many. If you ever must choose, the data wins.

**Verify before committing** (region availability shifts, and I will not guess): whether Bedrock
AgentCore is offered in `ap-south-1`; which Claude models are enabled for your account in `ap-south-1`;
and whether Claude Platform on AWS is available there.

### Bedrock vs Claude Platform on AWS — a real fork

These are different products and the difference is material for latency work:

| | Amazon Bedrock | Claude Platform on AWS |
|---|---|---|
| Operated by | AWS (partner) | **Anthropic**, same-day API parity |
| Model IDs | `anthropic.`-prefixed — `anthropic.claude-opus-5` | Bare — `claude-opus-5` |
| Client (Python) | `AnthropicBedrockMantle(aws_region="ap-south-1")` | `AnthropicAWS()` — needs `AWS_REGION` + `ANTHROPIC_AWS_WORKSPACE_ID` |
| Auth | AWS IAM / SigV4 | AWS IAM / SigV4, Marketplace billing |
| Prompt caching | ✅ **manual breakpoints only** | ✅ including automatic |
| Streaming, tool use | ✅ | ✅ |
| Fast mode (≈2.5× output tok/s) | ❌ | ❌ |

**Fast mode — the fact worth knowing before you commit.** Up to 2.5× higher output tokens/second on
Claude Opus 5 / Opus 4.8, but it is **first-party Claude API only** — not on Bedrock, and not on Claude
Platform on AWS. If raw generation speed is the binding constraint, that is an argument for the
first-party API; if AWS-native IAM and AgentCore integration matter more, you are trading it away
knowingly. Also absent on Bedrock: automatic prompt caching, `inference_geo`, Batches, and Files API.

### Model-side levers, in order of payoff

1. **Stream the final response.** TTFT is what a driver at a roadside actually experiences. Note that
   on Opus 5 the thinking `display` defaults to `"omitted"`, so a streaming UI shows a long pause
   before text appears — set `display: "summarized"` or render a typing indicator.
2. **Prompt-cache the stable prefix — manually, on Bedrock.** Render order is `tools` → `system` →
   `messages`, and caching is a *prefix match*: any byte change invalidates everything after it. Your
   tool definitions plus the frozen system prompt are a large, stable prefix — exactly the right cache
   candidate. Place the breakpoint *after* tools+system and *before* volatile per-turn context.
   Verify with `usage.cache_read_input_tokens`; if it is zero across repeated turns, something volatile
   (a timestamp, an unsorted `json.dumps`, a varying tool list) leaked into the prefix.
3. **Shrink the tool surface.** 23 tool schemas are input tokens on *every* call, and they sit in the
   cacheable prefix — but they also degrade selection accuracy, which causes extra hops. Role-scope
   hard: a Driver allowlist of ~8–10 tools.
4. **Lower `effort` for routine turns.** Most driver messages ("what's my slot?", "confirm") do not
   need deep reasoning. `output_config: {effort: "low"|"medium"}` is a large latency lever; reserve
   `high` for genuinely ambiguous exception handling.
5. **Return all parallel tool results in a single user message.** Splitting `tool_result` blocks across
   multiple messages silently teaches the model to stop calling tools in parallel — which converts
   parallel work into sequential hops. A common and expensive mistake.

### The biggest application-level win: delete the first tool call

Most driver turns open with a context read (`get_driver_operational_context`). **Pre-fetch it when the
session opens and inject it into the prompt** — that removes an entire LLM round trip from the common
path, worth more than any region tuning.

Caveat that follows directly from the caching rule: volatile driver context must sit **after** the
cache breakpoint, or it invalidates the cached tools+system prefix every turn. Order is:

```
[ tools ][ frozen system prompt ]  ←── cache_control breakpoint here
[ volatile driver/shipment context ][ conversation history ][ user message ]
```

### Redis and Postgres specifics

- **Use the native Redis protocol over a persistent connection**, not Upstash's REST/HTTP API, from
  long-lived FastAPI workers. Per-call TLS setup on the HTTP path costs tens of milliseconds on every
  turn — twice, since you read at turn start and write at turn end.
- **Batch the tool's reads.** One query returning driver + shipment + appointment + latest ETA beats
  four sequential round trips, even at 5 ms each, because they are serial inside the tool.
- **Budget `find_feasible_slots` at <50 ms.** The GiST index backing the D1 exclusion constraint serves
  the overlap query directly — this should never be the bottleneck.
- **Connection pooling:** long-lived containers should hold a SQLAlchemy pool on a direct connection.
  If you route through Supavisor in transaction mode, disable prepared statements.

### LangSmith — the classic footgun

LangSmith is hosted outside India. **If tracing flushes in the request path, you have added a
cross-region round trip to every single turn.** Trace on a background queue, fire-and-forget, bounded,
dropping rather than blocking when full. Never await a flush before responding to the driver. Sample
in production if volume grows; trace everything in dev.

### What to measure (and the SLO)

TTFT p50/p95 · **tool-loop hop count distribution** (the real latency driver) · per-tool DB latency ·
LLM latency split into network vs inference · cache hit rate · Redis RTT.

Target, consistent with the existing NFR: **TTFT p95 < 1.2 s, full single-hop turn p95 < 2.5 s.**
Track hop count as a first-class metric — a rise in average hops per turn will show up as a latency
regression that no amount of infrastructure tuning will fix.


---

## Note on scope of this document

This is a design/architecture deliverable, not a code change. No application code has been modified.

**Revision, 2026-08-19.** The document was reviewed line by line against its four sources — the FDE
challenge brief, the Scheduling Algorithm report, the 23-tool catalog and the shipped classroom database
(schema plus every seed row). That pass produced three kinds of change, all folded in above:

- **Retrofit contradictions removed.** §4, §5 Stage 3, §6.1 and §10 were written before D1/D2 and still
  specified both a `slot_holds` table and `dock_occupancy`, both row-locking and the exclusion constraint,
  and two different winners for the same 50-way race. The original latency/region material moved to
  **Appendix A**, marked provisional, so it no longer contradicts D4's deferral of the stack.
- **Six new data findings** (§6.2 #7–#12), verified against seed rows rather than inferred — most
  materially, two seeded appointments that exceed their dock's weight limit, and the absence of any
  length/height column behind a Stage 1 invariant that requires them.
- **Three gaps against the brief closed:** the multi-day search horizon and the next-day path (Stage 0),
  which §8's "check tomorrow morning" and Fallback message type had no answer for; the role-scoped tool
  catalogs for planner, gate and sequencer (§7.5), none of which had any tools despite D6 making the
  planner the throughput-critical actor; and the conversation gaps — comparison read from `score_terms`,
  the browse-only thread, `explain_slot_eligibility`.

**Revision, 2026-08-19 (second pass).** The document was reconciled against the **live Supabase project**
(`setuhaul` / `kujffzgqjmqphkmrbawy`), audited read-only. Two sections were factually wrong about it: §6.2
#5 claimed the dataset was under brief scale, but the live project already meets §11.1's volumes with
Layer A intact; §9.1 described a generator as future work that had, in large part, already been built and
run. Both are corrected in place, D13–D16 record the migration decisions taken, and a new §9.3 lays out
the concrete migration sequence for roadmap step 5 — including two preconditions (`btree_gist`,
`timestamptz`) that do not currently hold and would otherwise fail D1 on first attempt. No migration was
executed this turn; the audit and this document update are the only changes.

Known open items, deliberately not resolved here: whether `shipments.latest_eta_ts` is a fixture or an
accident (§6.2 #12), and the choice of stack, which stays parked under D4.

The next step is either (a) turning this into a presentable artifact (diagrams + deck-ready sections), or
(b) generating the concrete downstream specs — target DDL, tool contracts, the 29-case test matrix — which
this document is now consistent enough to support.
