# Planner dock board — flows and states

## Flow 1 · Confirm

1. Planner reads the 30-second row, decides.
2. `C` or click Confirm → `confirm_request(appointment_id, snapshot_hash, Idempotency-Key)`.
3. **Success** → row disappears from the queue, U41's undo affordance appears (5s, driver notification
   queued not yet sent), toast bottom-left.
4. **`ALREADY_ACTIONED`** → see `edge-cases.md` #1, the nastiest race in the product.
5. **`SNAPSHOT_STALE`** → row re-renders with current data; planner re-reads before deciding again — never
   a silent retry with old context.
6. **`DISPLACEMENT_DETECTED`** → a conflict appeared since render. Row flags as displacement-flagged
   (`components.md` §1), refuses the confirm, re-renders the displacement column with the new conflict
   named. The planner sees exactly what changed, not just "try again."

## Flow 2 · Counter-offer (the one affordance that leaves the tab, U103)

```
Queue row, press O ──▶ Board tab opens, banner pinned to this shipment (screens.md §4)
                              │
                    click an open interval on an eligible dock
                              │
                    revalidate through Stage 1
                        │              │
                    feasible      infeasible
                        │              │
              COUNTER_OFFERED    INTERVAL_UNAVAILABLE
              new option set          │
              sent to driver    board re-renders that
                    │            interval occupied,
              return to Queue    banner stays, pick again
              tab, row updated
```

- **Cancel** at any point returns to the Queue tab with zero side effects — no partial counter-offer state
  exists.
- The Queue-tab row, once a counter-offer succeeds, shows the *new* proposed interval and a distinct
  "awaiting driver" micro-state until the driver responds — it does not simply vanish, since the planner's
  work on this row isn't actually done yet.

## Flow 3 · Reject + reason

Uses `components.md` foundations §11 verbatim — category → detail → preview → send. `reject_request`'s
`reason_code` enum (`CAPACITY`/`RULE_VIOLATION`/`PRIORITY_CONFLICT`/`SAFETY`/`DATA_CONFLICT`) is rendered
to the driver, so the preview step is not optional here any more than it is anywhere else it's used.

## Flow 4 · Hold for information

1. `H` or click Hold → mandatory question field → `hold_for_information(appointment_id, question,
   Idempotency-Key)`.
2. Row's countdown transitions to the Paused state (`components.md` §3) — icon swap, value freezes and
   hides, reason shown ("paused · waiting on driver").
3. **One-shot**: a second Hold attempt on the same row returns `HOLD_ALREADY_USED`; the Hold action itself
   becomes Disabled with a tooltip stating it's already been used (`components.md` §1's rule).
4. Driver answers (in `01-driver-chat/`) → countdown resumes with the visible arrival-flash transition
   already specified for resume (`components.md` §3).

## Flow 5 · Escalate

`E` or click Escalate → `escalate_request(appointment_id, reason, owner?)` → row leaves this queue,
`ESCALATED` + a queue-item id + thread attached. **This is the entry point to `02-ops-exception-console/`'s
own Flow 1** (Triage an escalation) — this file's responsibility ends at the handoff; ops's files own
everything from acknowledgment onward.

## Flow 6 · Bulk confirm

1. `[ Select all eligible (N) ]` — one click selects exactly the safe batch (`components.md` §6/U63).
   Manual deselection of an eligible row remains available; selecting an ineligible row does not (its
   checkbox is Disabled, not merely unchecked).
2. Confirm the batch → `bulk_confirm(appointment_ids[], snapshot_hash, Idempotency-Key)`.
3. **Server re-evaluates all five predicates at press time** — the per-id outcome list may differ from
   what was selected if a row's eligibility changed between selection and the click (the eligible count
   itself is frozen-while-focused per U19, but a genuine state change still wins over a stale client view).
4. Per-id outcomes render as a brief summary toast ("5 confirmed, 1 skipped — SHP1013 no longer eligible")
   — never a silent partial success. A skipped row stays in the queue, visibly, for individual review.
5. **No board interaction anywhere in this flow** (U105) — bulk confirm stays the fast, queue-only path
   §7.3 designed it to be.

## Flow 7 · Block a dock (U106/U107)

1. Board tab → `[ Block a dock ]` → form opens (`screens.md` §5, `components.md` §6).
2. As dock + time range fields complete, the affected-appointment set fetches live — this is not deferred
   to submission, since a planner deciding *whether* to block needs the consequence visible before
   committing, not after.
3. Submit → `block_dock(dock_id, window, reason, Idempotency-Key)`.
4. **`BLOCKED`** → form closes, board's outage-window layer (`components.md` §4) updates immediately. **If
   the response's affected-appointment set is non-empty, this is exactly how a `CAPACITY_EVENT_CASCADE`
   escalation begins** (§7.4) — the escalation itself is created server-side, not by this UI, and surfaces
   next in `02-ops-exception-console/`'s queue as a single capacity-incident row (U65), not N separate
   escalations, regardless of how many appointments this block stranded.
5. **`ALREADY_BLOCKED`** → form stays open, names the conflicting existing block (dock, window, reason) so
   the planner can adjust their own window rather than guessing why it failed.

## Flow 8 · End a dock block

From the outage-window marker (§4, `components.md`) or a small "Active blocks" list on the Board tab —
`end_dock_block(dock_status_event_id)` → `UNBLOCKED`, the hatched marker is removed, the freed interval
becomes bookable again through the ordinary feasibility engine (no special re-opening step — Stage 1
already reads `dock_status_events` live). `NOT_BLOCKED` (already ended elsewhere) refreshes the board
silently, consistent with U19's rule that a background change to something the planner wasn't focused on
does not interrupt them.

## Flow 9 · Review and apply a sequencer proposal (U104)

Two origins, one screen (`screens.md` §6, `components.md` §7):

**Self-triggered**: a planner requests a re-sequence directly. §7.3 frames re-sequencing as available to
the planner but doesn't specify a dedicated trigger UI beyond "review proposal" — treated here as a small
"Request re-sequence" action on the Board tab that calls `propose_facility_schedule` with
`trigger_reason='PLANNER_REQUESTED'`.

**Ops handoff**: `02-ops-exception-console/`'s Flow 4 requests a proposal on a capacity incident's behalf.
The `[ Review proposal (N) ]` button (`screens.md` §3) goes from Inactive-with-`(0)` to active the moment
either origin produces a `scheduling_run_id`.

1. Open the review → diff overlay renders (`components.md` §7): current schedule beneath, proposal delta
   outlined on top, unchanged/moved/newly-placed/unplaceable counts.
2. **Apply** → `apply_schedule_proposal(scheduling_run_id, snapshot_hash, Idempotency-Key)` — all-or-nothing.
3. **`APPLIED`** → board reflects the new committed schedule; every affected driver's notification is
   included in the tool's own notification-batch id, not composed separately by this UI. If this run
   originated from an ops capacity incident, that incident's resolution (marking the escalation `RESOLVED`)
   is `02-ops-exception-console/`'s own step, not this surface's — the handoff completes here, the
   escalation lifecycle closes there.
4. **`SNAPSHOT_DRIFT`** → re-run required; overlay states this plainly and offers "Request a fresh
   proposal" rather than a bare error.
5. **`PARTIALLY_INFEASIBLE`** → refuses entirely, per the tool's own all-or-nothing contract; the overlay
   explains which constraint made the whole proposal invalid, not just that it failed.
