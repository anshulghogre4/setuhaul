# Gate/yard kiosk — flows and states

## Flow 0 · Shift start (U111)

1. Device wakes to the shift-start screen (`components.md` §1) — always the entry point, whether the
   device has never been used or the previous shift explicitly ended.
2. Officer enters their name, presses Start shift.
3. Session now carries this officer's identity for every subsequent write, until Flow 7 (end shift) or the
   device otherwise resets. No further identity prompts occur during the shift.

## Flow 1 · Search (U109)

1. From the search screen, officer types a shipment id or plate number, presses Search.
2. **Match** → routes to Flow 2 with the found truck's current `queue_state`.
3. **No match** → named cause + "Try again," per `components.md` §13's anatomy — the search field retains
   focus so the officer can immediately retype rather than re-tapping into the field.
4. **Multiple matches** → short disambiguation list; tapping a row routes to Flow 2 for that specific truck.

## Flow 2 · Truck found → the one action

1. Truck-identity card renders (`components.md` §3): identity, current state + icon, appointment interval
   if one exists.
2. The one-dominant-button control (`components.md` §4) renders the single valid action per
   `screens.md` §3's state→action table.
3. Officer presses the button → the corresponding §7.5.2 tool call fires (see Flows 3–7 below for the
   per-tool detail) → routes to Flow 8 (outcome).

## Flow 3 · Gate-in

`record_gate_in(shipment_id, ts, Idempotency-Key)`.

- **`GATE_IN_RECORDED`** → outcome banner states the computed `arrival_state` (EARLY/ON_TIME/LATE, derived
  server-side from the appointment and RULE001's 60-minute early limit) alongside the timestamp — this is
  a fact worth surfacing to the officer, not buried, since an EARLY truck may need to wait regardless of
  how quickly it was checked in.
- **`ALREADY_CHECKED_IN`** → see `edge-cases.md` #1.
- **`NO_ACTIVE_APPOINTMENT`** → see `edge-cases.md` #2.

## Flow 4 · Queue state update (yard queue + call-to-dock)

`update_queue_state(shipment_id, queue_state, queue_position?)`.

- Every non-gate-in, non-terminal transition in the state table goes through this one tool — "Call to
  dock" is `update_queue_state` targeting `CALLED_TO_DOCK`, not a separate action with its own tool.
- **`QUEUE_UPDATED`** → outcome banner, brief, since this is the most frequent action on the surface and
  shouldn't linger — "Search next truck" is immediately available.
- **`INVALID_TRANSITION`** → see `edge-cases.md` #3. Should be rare given U110's one-valid-action design,
  but the state machine is enforced server-side (§7.5.2's own text), not trusted to the kiosk alone.

## Flow 5 · Dock-in

`record_dock_in(shipment_id, dock_id, ts)`.

- The `dock_id` passed is the truck's **confirmed appointment's dock** — the officer does not choose a
  dock from a list; the kiosk reads it from the appointment already shown on the truck-identity card
  (`components.md` §3) and submits it as the truck's *arrival* dock. If the truck physically arrived
  somewhere else, that mismatch is what the tool call reveals, not something the officer selects up front.
- **`DOCK_IN_RECORDED`** → success outcome.
- **`DOCK_OCCUPIED`** → see `edge-cases.md` #4.
- **`DOCK_MISMATCH`** → success-adjacent outcome, `feedback-warning` tone, states both docks plainly
  (`components.md` §5) — this is §7.5.2's own "allowed, but recorded as a deviation" outcome, not a
  failure the officer needs to resolve.

## Flow 6 · Unload start / end

`record_unload_start_end(shipment_id, phase, ts)`.

- **Start** → `RECORDED`, brief outcome, "End unload" becomes the truck's next valid action.
- **End** → `RECORDED` + the overrun delta against `expected_unload_min`. If the delta is positive
  (overrun), the outcome banner states it plainly (`components.md` §5) — this is the DEVT003-style
  re-sequence trigger and the input to churn pricing (§5.1), a fact for the record, not a decision point
  for the officer.

## Flow 7 · Gate-out

`record_gate_out(shipment_id, ts)`.

- **`COMPLETED`** → outcome states dwell time (`gate_out − gate_in`), the raw material for the detention
  metric (§8's KPI mart). This is the surface's terminal action for a given truck — after this, searching
  the same shipment again returns a truck with no further valid action (`edge-cases.md` #6).

## Flow 8 · Outcome → next truck

Every outcome screen (`components.md` §5) offers exactly one path forward: **Search next truck**, returning
to Flow 1. There is no "view history," no list of trucks processed this shift — the surface's whole design
is this single repeating loop, matching the literal one-truck-at-a-time framing of U26.

## Flow 9 · End shift

From the low-emphasis "End shift" control (`components.md` §1): session's officer identity clears, device
returns to Flow 0. No confirmation modal (consistent with U41's philosophy) — ending a shift has no
destructive consequence; a new officer simply starts a new one immediately after if the device stays in use.
