# FDE presentation Q&A prep — §11.2 stress scenarios & §12.1 judge questions

Source: `docs/SetuHaul_FDE_Challenge.pdf` §11.2 and §12.1.
Companion docs: [PRESENTATION_CHECKLIST.md](PRESENTATION_CHECKLIST.md) (live script) ·
[DEMO_MANUAL_RUNBOOK.md](DEMO_MANUAL_RUNBOOK.md) (phase-by-phase script referenced throughout) ·
[DEMO_DAY_READINESS.md](DEMO_DAY_READINESS.md) (SHOW/ANSWER/PARTIAL/NOT YET scoreboard).

Use this file to answer judge questions directly, with a code reference and the exact runbook
phase to point to (or run) if asked to prove it live. `file:line` references are correct as of
2026-08-17; re-check line numbers if the referenced file has changed since.

---

## §12.1 — Questions judges must be able to answer

### 1. What information must be collected before useful options can be shown?
Shipment compatibility requirements (dock type, refrigeration, weight), the shipment's latest
declared ETA, current active appointment state, and live facility/dock/slot availability — all
re-read fresh inside `find_feasible_slots` (`backend/app/scheduling/feasibility.py:321`), never
inferred from chat text. **Show:** Runbook Phase B2.

### 2. How is a conversation connected to the correct driver, shipment and appointment?
Server-side only: JWT → `ExecutionContext.driver_id` (`backend/app/core/execution_context.py:29`),
set from the verified `auth_user_id → users` mapping, never from client input.
`assert_driver_self()` / `can_read_facility()` (same file, lines 57–65) gate every tool call. The
shipment is locked explicitly in chat, not inferred — every phase opens with `"I need help with
shipment <ID>."` A cross-driver shipment id fails closed (403), verified in the Sprint 1 exit-gate
evidence. **Show:** Runbook Phase A1, B1, C1/C2, D1, H1.

### 3. How is revised arrival time determined and uncertainty communicated?
`report_delay_or_update_eta` requires an explicit ISO-8601 timestamp with a timezone offset before
any write (ADR 008); a bare delay/repair statement is rejected and re-asked. Uncertainty is a
first-class `confidence_code` field (default `MEDIUM`) stored alongside `declared_eta_ts`
(`backend/app/services/eta_service.py:31,347`). **Show:** Runbook Phase A3–A6 (repair-duration
rejected → explicit ETA → confirm preview → write).

### 4. What makes a slot feasible for a specific shipment?
Six hard constraints checked per candidate in `evaluate_candidate_slot`
(`backend/app/scheduling/feasibility.py:204-276`): slot status `OPEN`, no conflicting active
appointment/dock event, dock `ACTIVE`, dock-type match, refrigeration compatibility, vehicle
weight vs. dock max, and the shipment fitting the slot's time window. Any failure returns a typed
reason code, not a silent drop.

### 5. What does "available" mean while another driver is considering the same slot?
Every returned option carries `option_status = "DISPLAYED_NOT_RESERVED"` (`feasibility.py:35`) —
showing it creates zero database rows and zero hold. Only `request_slot` creates a real claim.
**Show:** Runbook Phase B (pass criterion: "options not reserved").

### 6. At what point does an option become a hold, request, reservation or confirmed booking?
There is no informal "hold" state — `PENDING_CONFIRMATION` (written by `request_slot`,
`backend/app/scheduling/allocation.py:972-1050`) *is* the atomic durable claim. It only becomes
`CONFIRMED` through the ops/admin-only warehouse-confirm transition; `CANCELLED` / `REJECTED` /
`EXPIRED` are separate idempotent transitions. **Show:** Runbook Phase B5 ("has the warehouse
confirmed?" → pending ≠ confirmed) and Phase F4 (Ops Confirm button).

### 7. How are simultaneous requests ordered when capacity is insufficient?
Two mechanisms — worth distinguishing explicitly if asked: the **ranking policy**
(`rank_score` / `ranking_factors`, `backend/app/scheduling/constraints.json`) decides which slots
each individual driver is *shown* and in what order. When two drivers land on the *same* slot,
there is no fairness queue — it's optimistic concurrency: whichever `request_slot` transaction
commits first under the row lock wins, with the Postgres unique partial index as final arbiter.
The loser gets `SLOT_CONFLICT_REFRESH_REQUIRED` (`allocation.py:428`) with fresh options, not
silence. **Show:** Runbook Phase C.

### 8. Optional scheduling extension: facility-wide recalculation, fixed work, optimization objective?
**NOT YET / deferred by design** — documented rather than skipped silently. The master plan's
deferred-scope note: start with a rule-based facility-snapshot tool (dock occupancy + open slots +
pending appointments for one facility/day), with an optional OR-Tools optimizer later behind the
same typed-tool boundary — the agent would never free-text SQL and optimizer output would never be
labeled a confirmed booking. Answer honestly as designed-but-not-built if asked; do not claim it.

### 9. How are stale options, cancellations, duplicate messages and retries handled?
Four separate mechanisms:
- **Stale** — `REC-` recommendation fingerprint + a Redis stale-marker set after any ETA commit →
  `SLOT_OPTIONS_STALE` (`allocation.py:453`) on the next request/reschedule.
- **Cancellation** — `cancel_appointment` writes `CANCELLED` / `is_current=0`, releasing the slot
  for the very next search.
- **Duplicate messages** — `client_message_id` dedupe in `ConversationMemory` (Redis).
- **Retries** — REST mutation routes require an `Idempotency-Key`, backed by
  `idempotency_requests`.

**Show:** Runbook Phase E (stale + cancel live); duplicate-message replay is in Runbook "Optional
extras" (needs a manual API replay since the UI mints a fresh id per send).

### 10. What happens when there is no feasible slot?
Zero options returned, zero invented capacity, and a durable `escalation_queue` row created via
`escalate_exception` (gated behind a two-step confirm to prevent LLM misfires — see the 08:10 IST
fix in `wiki/handoff.md`). **Show:** Runbook Phase D (`SHP-D16-NOSLOT`).

### 11. What is explained when the preferred slot is not granted?
Two layers: displayed options carry a human-readable ranking explanation built from
`ranking_factors` — priority, lateness, wait-after-ETA, fit slack, dock match
(`feasibility.py:169-180`); and on an actual conflict, the response is explicit
`SLOT_CONFLICT_REFRESH_REQUIRED` with fresh alternatives, never a silent substitution. **Show:**
Runbook Phase C (the losing driver's reply) and Phase B (ranking factors on the initial list).

### 12. Which decisions require human approval or takeover?
Warehouse `CONFIRMED` is ops/admin-only and unreachable from Driver chat; `REJECTED` / `EXPIRED`
are also ops/admin REST-only; any no-feasible-slot or explicit escalate case routes to
`escalation_queue` + the Ops dashboard. This is invariant #5 in the master plan: "the LLM never
decides feasibility, priority, availability, or booking success." **Show:** Runbook Phase F (Ops
confirm button + escalation list).

### 13. How will the team prove that the system did not double-book capacity?
Two Postgres unique partial indexes are the actual last line of defense:
`ux_active_appointment_per_slot` and `ux_current_active_appointment_per_shipment`
(`supabase/migrations/20260805201923_setuhaul_baseline.sql:428,432`), with dedicated DB tests in
`supabase/tests/database/appointment_constraints.sql`. Live proof stacks on top:
`backend/tests/integration/test_live_scheduling_concurrency.py` (2-client same-slot) and
`test_live_demo_day_load.py` (10×4 live load — 4 winners / 6 conflicts / **zero** double-books).
**Show:** Runbook Phase C (manual 2-browser race) and Phase G (manual sample);
`loadtests/locust_slot_contention.py` prints `PASS_zero_double_books` for the load-test angle if
asked.

**Summary:** 11 of 13 map to a live-demoable runbook phase. Only #8 (facility-wide OR-Tools) is
honestly "designed but not built" — say so. Pre-empt #7 with the ranking-vs-concurrency
distinction so it doesn't sound like a fairness queue that doesn't exist.

---

## §11.2 — Required stress scenarios

Legend: **SHOW** (fully live-demoable) · **PARTIAL** (mechanism real/tested, not staged as a live
beat) · **NOT YET** (not built or not wired for live demo).

### 1. At least 10 drivers request alternatives for the same facility/evening window, only 3–4 compatible slots exist
**SHOW.** Cast: `SHP-D16-CONTEND-01..10` competing for evening `STANDARD` slots (incl.
`D16-SLT-RACE`) in `supabase/demo/fixtures/stress_scenarios.json`. Automated proof:
`backend/tests/integration/test_live_demo_day_load.py::test_live_ten_driver_scarce_evening_load_has_no_double_books`
— live 10×4 run, 4 winners / 6 conflicts / zero double-books. **Runbook Phase G** (manual 2-driver
sample, G1–G4); the full 10×4 is the pytest, not re-run live in the room.

### 2. Simultaneously: one truck early+waiting, one late+waiting, one currently unloading, one declared a later ETA but hasn't arrived
**SHOW as data, not as a scripted live beat.** Cast: `SHP-D16-EARLY` / `SHP-D16-LATE` /
`SHP-D16-UNDOCK` / `SHP-D16-FUTURE`. The protection is real —
`evaluate_candidate_slot` (`backend/app/scheduling/feasibility.py:210-226`) rejects any candidate
with an `active_appointment_id` or `active_dock_event_id`, so an in-progress/committed truck can't
be double-claimed underneath. Runbook only lists this under "Optional extras → Early/late snapshot
data" (Ops/API observation), not a walked chat scenario. **If asked:** narrate from that snapshot
rather than a live 4-truck script.

### 3. Two drivers select the same option within a few seconds
**SHOW.** **Runbook Phase C** (C1–C5): Ravi (`SHP-D16-RACE-A`) and Amit (`SHP-D16-RACE-B`) both
request `D16-SLT-RACE` near-simultaneously — one `PENDING_CONFIRMATION`, one conflict refresh.
Also proved by `backend/tests/integration/test_live_scheduling_concurrency.py` (live two-session
same-slot contention).

### 4. A facility reduces capacity after options have already been discussed
**NOT YET as a live beat** — the weakest of the eleven. No runbook step has Ops close a dock
mid-conversation. The safety net exists structurally: `request_slot` / `reschedule_appointment`
re-check `dock_status == ACTIVE` and `slot_status == OPEN` transactionally at claim time
(`feasibility.py:222-226`, revalidated again inside `backend/app/scheduling/allocation.py`), so a
capacity cut between search and claim fails safe as a conflict/stale refresh, never a silent
confirm. `wiki/current-state.md` calls this "dock-close mid-conversation path thin." **If asked:**
explain the transactional revalidation; there is no Ops "close this dock" control wired into the
UI to trigger it on demand.

### 5. A cancellation creates a new slot during an active conversation
**SHOW.** **Runbook Phase E** (E5 cancel → E6 re-search shows the freed slot back in results).

### 6. A driver sends duplicate messages because of weak connectivity
**SHOW.** Dedupe is keyed on `client_message_id` in `ConversationMemory` (Redis), and `request_slot`
chat mutations reuse the same idempotency key so a replay doesn't double-write. **Runbook "Optional
extras": "Duplicate message: replay same `client_message_id` via API."** Not a default-path phase
step since the UI mints a fresh id per send — needs a manual API replay to show.

### 7. A driver has more than one shipment record, requiring disambiguation
**SHOW.** **Runbook Phase A** (A2 — Ravi's three actives) and **Phase D** (Vikas:
`SHP-D16-NOSLOT` vs `SHP-D16-MULTI-B`, D1/D4 prove the assistant doesn't blend them).

### 8. A stated 90-minute repair delay does not equal a 90-minute ETA shift
**SHOW.** Literally scripted: **Runbook Phase A3–A5** — `"Repair will take 90 minutes."` must be
rejected as an ETA and the assistant must ask for an explicit timestamp+timezone before any write.

### 9. One shipment has higher priority but enters the queue later
**PARTIAL.** The mechanism is real: `priority_scores` is a first-class ranking weight in
`backend/app/scheduling/constraints.json:110-116`, exercised by
`backend/tests/unit/test_scheduling_feasibility.py` (`priority_code="HIGH"` cases). But no cast
scenario or runbook phase stages "a HIGH-priority shipment arrives after a NORMAL one and still
outranks it" as a live story beat — it's unit-verified, not demo-dramatized. **Caveat if pressed:**
`find_feasible_slots` caps candidates at `LIMIT 200` before the global rank sort
(`feasibility.py:417`, also flagged in `wiki/current-state.md`), so at very large scarce-capacity
volumes a late-arriving high-priority option could theoretically be truncated before ranking — not
an issue at demo cast size, don't overclaim correctness at scale.

### 10. One request has no feasible same-day slot
**SHOW.** **Runbook Phase D** (D2: `SHP-D16-NOSLOT` → zero options + escalation language, zero
invented slots; D3 optional explicit escalate).

### 11. A warehouse reply conflicts with the stored schedule
**NOT YET.** No tool/route models an inbound warehouse reply being checked against the stored
schedule. `escalate_exception` / `escalation_queue` covers generic human-takeover, but not this
specific conflict-detection flow. The runbook says so directly under "Out of scope — do not
claim": *"Warehouse-reply conflict automation (lightweight escalate path exists; not a full
warehouse messaging channel)."* **Do not attempt to demo this one** — answer verbally: "escalation
queue is the human-takeover mechanism; a dedicated warehouse-reply-conflict channel is out of
scope for this build."

**Summary:** 7 of 11 are fully scripted, live-demoable phases (1, 3, 5, 6, 7, 8, 10). Scenarios 2
and 9 have real backing (data/mechanism + tests) but no dedicated live script step — answer from
evidence, don't improvise acting them out. Scenario 4 is structurally safe but has no trigger UI to
demo it. Scenario 11 is honestly out of scope — say so rather than improvising.

---

## Do not claim (cross-reference)

- Displayed options are reserved / a confirmed booking
- Facility-wide OR-Tools / national optimization / live GPS / maps
- A fairness queue orders simultaneous requests on the same slot (it's optimistic concurrency + a
  unique index, not a queue)
- A full warehouse-reply-conflict messaging channel
- Sprint 4 hosting exit gate as complete
- Password rotation / session revocation
- Locust Suite B as run (it has not been)

Success line (PDF §13.1): exception → feasible, current plan, **zero conflict for another driver**.
