# Planner dock board — components

> Surface-specific components only. Shared components (countdown, decision receipt, priority marker, data
> table conventions, toast, undo affordance, form controls, unavailability taxonomy, queue conventions) are
> specified once in `../00-foundations/components.md` and cross-referenced, not restated. The 7-field row
> itself is the full instantiation of foundations §6, which explicitly deferred it here.

## 1. The 30-second row (§7.3, full spec)

### Anatomy
See `screens.md` §2 for the rendered layout. Seven fixed-width columns: selection+priority, identity,
interval, condensed receipt, displacement, ETA confidence, driver's limit, TTL.

### States
Default · hover · focused (roving tabindex, single-key actions active) · selected (part of a bulk batch)
· **stale** (`ALREADY_ACTIONED` — see `edge-cases.md` #1) · **displacement-flagged** (the row's own
`DISPLACEMENT_DETECTED` outcome on a failed confirm attempt).

### Rules
- **Column widths are fixed pixel values, never `auto` or `fr`** — re-derived here as a hard rule because
  this is the one screen in the product where a layout shift during a read is a real operational cost
  (§7.3's 30-second budget), not just a polish concern elsewhere.
- **The displacement-check column never truncates**, even under the ellipsis rule every other cell follows
  (`data-formatting.md`) — §7.3 calls it "the single most important field," and a truncated warning is a
  warning that failed at its one job.
- **`LOW` ETA confidence renders as a warning-toned inline flag inside its cell**, not just plain text —
  the rule "do not confirm without asking" needs to be visible at a glance, not inferable from a value.
- **The five affordance buttons render always-visible, never hover-revealed** (caught in a `checklist-design`
  audit against the Data Table checklist, whose default pattern is hover-reveal row actions). A hover-only
  reveal costs a mouse user a discovery step this surface's 30-second budget cannot spare, and provides
  nothing for the keyboard path (`C`/`R`/`O`/`H`/`E`) that's the primary interaction model anyway. Rendered
  as compact icon buttons at the row's trailing edge, present in every row's default state.
- **Empty state, named explicitly**: "No pending requests for [facility]." / "New ones appear here
  automatically." — the same anatomy as every other surface's empty state (`components.md` foundations
  §13), stated concretely here rather than left as a bare cross-reference.

---

## 2. Five affordance buttons (§7.3)

| Button | Icon (`iconography.md`) | Variant (`components.md` §1) | Key |
|---|---|---|---|
| Confirm | `check` | `constructive` | `C` |
| Counter-offer | `repeat` | `neutral` | `O` |
| Reject | `x` | `destructive` | `R` |
| Hold for information | `pause` | `neutral` | `H` |
| Escalate | `arrow-up-right` | `cautionary` | `E` |

### Rules
- **Safer-action-first DOM order** (U79) — Reject sits before Confirm in source order regardless of visual
  left-to-right placement, so keyboard tab traversal reaches the non-destructive action first.
- **Counter-offer switches the surface to the Board tab** (U103) — it is the one affordance that isn't a
  same-tab action; state this explicitly so it isn't mistaken for a bug.
- **Escalate hands the row to `02-ops-exception-console/`** — calls `escalate_request` (§7.5.1), and the
  row's terminal state here is "gone from this queue, now an escalation elsewhere," not a local state
  change. This is the other half of that surface's Flow 1.
- Every button here is idempotency-keyed (U70) — stated once, applies to all five plus bulk confirm.

---

## 3. Gantt board — dock row and task bar

### `dock_occupancy.state` → chip token mapping

The board reuses the promise-state chip's exact tokens (`color.md`) rather than an invented Gantt palette.
Grounded directly in D1's schema (`SOLUTION_DESIGN.md`, `CREATE TABLE dock_occupancy`), which has nine
possible `state` values — more than the four-state chip vocabulary, resolved as follows:

| `dock_occupancy.state` | Bar treatment |
|---|---|
| `HELD` | `state-held-*` tokens, **2px dashed border** (the chip's own dashed-means-temporary rule) |
| `PENDING_CONFIRMATION` | `state-pending-*` tokens, 2px solid |
| `CONFIRMED` | `state-confirmed-*` tokens, 2px solid |
| `IN_PROGRESS` | `state-confirmed-*` tokens **+ a small `truck-loading` icon** (`iconography.md`) inside the bar — still fundamentally the committed/confirmed category (a driver physically at the dock), distinguished by icon rather than a new hue, keeping the hue budget exactly where U10/U59/U85 already fixed it |
| `COMPLETED` / `CANCELLED` / `EXPIRED` / `NO_SHOW` / `REJECTED` | **No bar at all.** The board's horizon is forward-looking (§5.1's rolling 4 hours); a terminal state means that interval no longer occupies capacity, so it renders as open space, not a ghost bar. A history view is future scope, not v1. |

### Rules
- **One shared render pass, not per-row logic invented ad hoc** — every dock row runs the same state→token
  function; a new `dock_occupancy` state added later gets a mapping-table row, not a bespoke branch.
- **Motion-budget rule applies** (U76, `motion.md`): only a bar that just changed state animates; settled
  bars stay static regardless of how long they've been visible.
- Bars carry a `title`/focus-reachable tooltip with the shipment id, carrier, and interval — the board is a
  spatial overview, not a replacement for the queue's own identity columns.

---

## 4. Outage-window marker (`dock_status_events`)

### Anatomy
A hatched fill, visually and semantically distinct from every `dock_occupancy` bar treatment above — never
a promise-state token, never the same visual family as a booking.

### Rules
- **Rendered from `dock_status_events`, D1's declared single authority for availability** — never
  reconciled against `appointment_slots.slot_status='BLOCKED'` for display purposes; `SOLUTION_DESIGN.md`
  §0.9 point 9 already resolves that the two disagree today and `dock_status_events` wins.
- Carries the block's reason as its tooltip/label — "blocked — DEVT002 outage," not just a hatch pattern
  with no explanation.
- **A dock cannot be both blocked and show a booking bar over the same instant** — the block-dock form
  (§5) is exactly what prevents this at the point of creation, by surfacing the conflicting appointments
  before the block commits.

---

## 5. Counter-offer board-picker

### States
Idle (board at rest) → **picking** (context banner shown, eligible docks highlighted, ineligible dimmed
per `components.md` §18's Disabled — `screens.md` §4) → **revalidating** (brief loading state on click, per
`components.md` §13's skeleton technique scaled down for a single interval) → **confirmed** (returns to
Queue tab, row updated) or **refused** (`INTERVAL_UNAVAILABLE` — board re-renders that interval occupied,
banner stays, planner picks again) or **cancelled** (banner dismissed, no action taken).

### Rules
- **Eligibility is computed per shipment, not global** — a heavy-load shipment dims every dock lacking
  `HEAVY_DOCK_REQUIRED_KG` clearance; a different shipment's picker session would dim a different set.
- The banner's Cancel is always reachable and always returns to the board at rest with no side effect —
  a planner must never feel committed just by entering picker mode.

---

## 6. Block-dock form

### Anatomy
Dock select · start time · end time · reason (free text — no controlled vocabulary defined for this in
`SOLUTION_DESIGN.md`, unlike `reject_request`'s enum, since this reason is never rendered to a driver the
way a rejection reason is) · a mandatory affected-appointment warning block · Cancel/Block dock actions.

### States
Idle → **checking** (as dock/time fields complete, the affected-appointment set is fetched and rendered
live — not deferred to submission) → **ready** (warning shown if any appointments are affected, or a plain
"no confirmed appointments in this window" line if none) → **submitting** → **blocked** (form closes,
board's outage-window layer updates) or **error** (`ALREADY_BLOCKED` — an overlapping block already
exists; form stays open, names the conflict).

### Rules
- **The affected-appointment warning is not dismissible without acknowledgement** — `[ Block dock ]` stays
  disabled until the warning (if any) has been shown at least once with current data, preventing a planner
  from submitting against a stale, not-yet-computed affected set.
- **High-tier friction is deliberately not applied here** (`components.md` §19's 3-tier destructive model)
  — blocking a dock is Moderate, not High: it's reversible via `end_dock_block`, and the warning already
  provides the friction a typed-confirmation gate would add with less redundant clicking. High tier is
  reserved for genuinely hard-to-reverse admin actions (§6 of `06-admin-console/`, not yet written).

---

## 7. Sequencer proposal diff overlay

### Anatomy
Run id + origin (self-triggered / "requested from Ops (Capacity incident)") · the board re-rendered with
current-schedule bars beneath and proposal-delta bars overlaid, outlined not re-hued · a summary line
(unchanged/moved/newly placed/unplaceable counts) · an unplaceable-shipments list below the board when
non-empty · Apply.

### States
Loading (fetching the run) → **reviewing** → **applying** (Apply pressed, all-or-nothing per
`apply_schedule_proposal`) → **applied** (overlay closes, board reflects the new committed schedule,
originating capacity incident/escalation — if any — is left for `02-ops-exception-console/` to mark
resolved, per that surface's Flow 4 step 6) or **refused** (`SNAPSHOT_DRIFT` → re-run required,
`PARTIALLY_INFEASIBLE` → refuses entirely, both rendered as named outcomes, never a silent failure).

### Rules
- **Delta bars are an outline treatment on the existing hue-budget colours, never a new colour** — "moved"
  and "newly placed" are distinguished by border style and a small badge label, not by inventing a fifth
  semantic hue.
- **No partial-apply affordance** — matches `apply_schedule_proposal`'s own contract exactly; the UI does
  not offer a control the tool doesn't support.
