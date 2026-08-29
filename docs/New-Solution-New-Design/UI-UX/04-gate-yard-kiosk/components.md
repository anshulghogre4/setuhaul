# Gate/yard kiosk — components

> Surface-specific only. Shared components (form controls, empty/loading/error anatomy, unavailability
> taxonomy) are specified once in `../00-foundations/components.md` and cross-referenced, not restated.

## 1. Shift-identity capture (U111)

### Anatomy
Officer-name text field · fixed facility label (not a switcher) · Start shift button.

### States
Idle → filled → **active shift** (name stamped in session, persists until explicitly ended) → **ended**
(returns here, session name cleared).

### Rules
- **One capture per shift, not per action** — the defining property of this component. Every event this
  session writes (`record_gate_in`, `update_queue_state`, etc.) carries this officer's identity as an
  attribute of the write, not as a re-asked credential.
- No password/credential here beyond the name — this is a shared-device attribution mechanism, not an
  authentication boundary. Actual device-level access control (who can physically use the kiosk at all) is
  a facility/IT concern outside this file's scope, same boundary `auth-and-scoping.md` already draws
  between "who can act" and "what they can see once they can."
- Ending a shift is a low-emphasis control (text link, not a button at the 56px primary scale) — it's a
  rare action relative to searching trucks, and shouldn't compete visually with the actions an officer
  performs dozens of times a shift.

---

## 2. Search input (U109)

### Anatomy
Single large text field, numeric-friendly keyboard, Search button.

### States
Idle → typing → searching (brief, per `components.md` §13's skeleton technique scaled to a single result)
→ **found** (routes to §3 below) → **not found** (named cause + retry, `components.md` §13) → **multiple
matches** (disambiguation list).

### Rules
- **Matches on either `shipment_id` or a plate number** — an officer may have either on hand first
  depending on what's physically visible on the truck versus what's on paperwork; the search does not
  require knowing which field to search, it tries both.
- Text size and input height both meet the 56×56px minimum target and the `spacious` density's larger type
  scale — this field is used far more than any other single control on the surface.

---

## 3. Truck-identity card

### Anatomy
```
SHP1015 · Ravi K.
Rajasthan Roadlines

🚪 Waiting (late)

Appointment: D5 · 18:00–19:00
```

### Rules
- **Renders the current `queue_state` with its icon from `iconography.md`'s Queue state table** — never a
  bare label. `NOT_QUEUED` renders with no icon (absence is the signal, per that table's own note).
- **Appointment interval always carries its dock and date** — the product-wide rule, restated because a
  gate officer confirming a truck's dock assignment is exactly the moment a missing date or dock would
  cause a real misdirection.
- Carrier name uses `data-formatting.md`'s end-truncation rule if it overflows (identity carries at the
  start) — never mid-truncated, since carrier names aren't identifiers with a distinguishing suffix the way
  shipment IDs are.

---

## 4. The one-dominant-button next-action control (U110)

### Anatomy
A single full-width button, minimum 56px height, label matching the current state's one valid action
(`screens.md` §3's mapping table).

### States
Default (enabled, labelled) → pressed → **submitting** (label stays, a spinner does not replace it —
`components.md` §13's rule that loading never removes the action's own label, doubly important here since
a label-less spinner under gloves invites a mis-tap on whatever renders next) → **outcome** (routes to an
outcome screen, §5 below).

### Rules
- **There is never a second button at this decision point.** Not a "Cancel," not an "Are you sure" — U41's
  no-confirmation-modal philosophy taken to its logical extreme for a surface where every action is a
  factual record of something that just physically happened (a truck arrived, unloading started), not a
  reversible commitment the way confirming a driver's appointment is. If an officer taps the wrong truck's
  button, `edge-cases.md` covers correction, but the button itself never second-guesses the officer.
- **Label is the imperative verb matching the state table exactly** — "Gate in," "Call to dock," "Dock in,"
  "Start unload," "End unload," "Gate out." Never a generic "Next" or "Continue," since the specific verb
  is itself confirmation the officer is about to do the right thing.
- Retry-safe against a double-tap (U70's underlying concern), but not uniformly by an idempotency key.
  **Corrected 2026-08-29, M5/E5.4:** only `record_gate_in` actually carries an `Idempotency-Key` header
  server-side (`gate.py:78-83, 93-96`). The other four (`update_queue_state`, `record_dock_in`,
  `record_unload_start_end`, `record_gate_out`) achieve the same double-tap safety through their own
  state-machine guards instead — a retry either lands on a transition already made (returns the same
  restated fact, e.g. `ALREADY_GATED_OUT`) or fails a precondition that's already satisfied. The end
  result — retry-safe — is real and verified for all five; the mechanism is not one thing.

---

## 5. Outcome banners

### Anatomy
Icon + headline + one supporting fact (timestamp, dock, dwell time) + a single "Search next truck" action.

### Variants

| Outcome | Tone | Anatomy detail |
|---|---|---|
| Success (`GATE_IN_RECORDED`, `QUEUE_UPDATED`, `DOCK_IN_RECORDED`, `RECORDED`, `COMPLETED`) | `feedback-success` | States the recorded fact plainly — timestamp, and on gate-out, dwell time (`gate_out − gate_in`) |
| `DOCK_MISMATCH` | `feedback-warning`, **not** danger | Names both the confirmed and actual dock; states plainly this is recorded as a deviation, not rejected |
| Unload-end **overrun** | `feedback-warning` | States the overrun delta against `expected_unload_min` as a fact ("22 min over expected") — the officer isn't asked to do anything about it; it feeds the DEVT003-style re-sequence and churn pricing downstream, not an action here |
| `ALREADY_CHECKED_IN`, `NO_ACTIVE_APPOINTMENT`, `DOCK_OCCUPIED`, `INVALID_TRANSITION` | `feedback-danger`/`feedback-warning` per severity — see `edge-cases.md` | Named cause, and where a next action exists (e.g. re-search), it's offered directly |

### Rules
- **Every outcome is named, never a generic "Done" or "Error."** This is the single most important
  discipline on this surface — an officer standing at a gate with a truck behind them needs to know exactly
  what the system just recorded, especially for the non-obvious ones like `DOCK_MISMATCH` and the unload
  overrun, which are facts about the world, not results of the officer having done something wrong.
- **`DOCK_MISMATCH` and overrun banners are explicitly not framed as officer error** — both are facts about
  the truck/dock, not about the action just taken. Danger-toned framing here would train officers to see
  honest deviation-recording as a mistake to avoid, which risks under-reporting real deviations.
