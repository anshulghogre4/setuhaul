# Gate/yard kiosk — screens

> Surface: **two device contexts (U108)** — a mounted gate-booth kiosk (landscape, gate-in/gate-out only)
> and a handheld yard tablet (portrait, call-to-dock → dock-in → unload start/end). Density `spacious`
> (`spacing-and-layout.md`: 64px row height, 20/24 cell padding, 24px card padding, 16px stack gap, **56×56px
> minimum tap target** — the one deliberate exception beyond the 44px AAA overlay used elsewhere, per U30).
> Light theme only in practice (outdoor glare; dark theme exists for parity but is not the expected
> real-world state). Foundations: `../00-foundations/`.
>
> **No `checklist-design` checklist matches this surface's shape** — checked the full 122-checklist index;
> nothing covers a single-purpose, one-truck-at-a-time field kiosk. Structure is derived directly from U26
> ("search-then-act, one truck at a time — only currently-valid actions are offered") and the
> `facility_checkins.queue_state` state machine (`iconography.md`'s Queue state table) instead.

## The surface in one line

Search a truck, see its current state, do the one thing that's valid right now. Six §7.5.2 tools, one
state machine, two physical device contexts sharing the same interaction model (U108).

---

## Screen map

```
Shift start (once, U111) ──▶ Search ──▶ Truck found ──▶ [ one dominant button ] ──▶ outcome
                                 ▲                                                       │
                                 └───────────────────────────────────────────────────────┘
```

No other navigation exists. There is no list, no dashboard, no settings beyond shift start — the entire
surface is this loop, repeated once per truck. This is the literal interpretation of U26, not a
simplification of something bigger.

---

## 1 · Shift start (U111, both device contexts)

```
┌────────────────────────────────────┐
│                                     │
│         SetuHaul · Gate/Yard        │
│                                     │
│    Officer name                     │
│    ┌─────────────────────────────┐ │
│    │                             │ │
│    └─────────────────────────────┘ │
│                                     │
│    Facility: Jaipur (fixed)         │
│                                     │
│    ┌─────────────────────────────┐ │
│    │        Start shift          │ │  ← 56px min height
│    └─────────────────────────────┘ │
└────────────────────────────────────┘
```

- **Once per shift, not per truck** (U111) — a name entered here is stamped on every event this session
  writes; the officer is never asked to re-authenticate for an individual action.
- Facility is fixed to the device's own assignment, not chosen — a gate-booth kiosk or yard tablet is
  physically installed at one facility and has no reason to offer a switcher (unlike every desktop
  console surface, which does).
- Ending a shift (a small, low-emphasis control, not a primary action) returns here and clears the
  session-level officer name — the next person to use the device must set their own.

---

## 2 · Search (U109)

```
┌────────────────────────────────────┐
│  ← Shift: Ramesh K.                 │
│                                     │
│    Shipment ID or plate number      │
│    ┌─────────────────────────────┐ │
│    │  SHP1015                    │ │  ← large input, 24px text
│    └─────────────────────────────┘ │
│                                     │
│    ┌─────────────────────────────┐ │
│    │           Search             │ │
│    └─────────────────────────────┘ │
└────────────────────────────────────┘
```

- **Typed entry only** (U109) — shipment ID or plate number, no scan/camera path. A large single input,
  numeric-friendly keyboard by default (`shipments.shipment_id` and plate numbers are both short
  alphanumeric strings).
- **Not found**: named cause + next action (`components.md` §13) — "No shipment matches that ID or plate."
  / [ Try again ]. Never a bare "not found."
- **Multiple matches** (a plate shared across trips, unlikely but not impossible): a short disambiguation
  list, each row tappable at the 56px minimum target — never a dropdown menu, which is a poor fit for
  gloves.

---

## 3 · Truck found — current state + one dominant action (U110)

```
┌────────────────────────────────────┐
│  ← Search                           │
│                                     │
│  SHP1015 · Ravi K.                  │
│  Rajasthan Roadlines                │
│                                     │
│  🚪 Waiting (late)                   │  ← queue_state icon + label
│                                     │
│  Appointment: D5 · 18:00–19:00      │
│                                     │
│  ┌─────────────────────────────┐   │
│  │                             │   │
│  │      Call to dock            │   │  ← ONE button, full width, 56px+
│  │                             │   │
│  └─────────────────────────────┘   │
└────────────────────────────────────┘
```

### The state → action mapping (the entire logic of this surface)

| Current `queue_state` | Icon (`iconography.md`) | The one button offered |
|---|---|---|
| `NOT_QUEUED` (no check-in yet) | *(none)* | **Gate in** |
| `WAITING_EARLY` / `WAITING_LATE` | `door-open` | **Call to dock** |
| `WAITING_DOCK_UNAVAILABLE` | `door-closed` | **Call to dock** (retried — the officer isn't blocked from trying again; the tool itself is what decides whether the dock is actually free now) |
| `CALLED_TO_DOCK` | `bell-ring` | **Dock in** |
| `IN_DOCK`, no unload recorded | `truck` | **Start unload** |
| `IN_DOCK`, unload started | `truck` | **End unload** |
| `COMPLETED` | `check` | **Gate out** |
| Gated out already | *(terminal)* | *(no button — see edge-cases.md)* |

### Rules
- **Exactly one button, always** (U110) — never a menu, never two options to weigh. This is the literal
  reading of U26 taken as far as it goes: an officer under gloves, glare, and a moving queue of trucks
  should never have to *choose* which action is correct — the state already determines it.
- **The current state renders above the button, not just implied by the button's own label** — an officer
  glancing at the screen mid-task needs to confirm "yes, this is where this truck actually is" before
  pressing anything, especially after being interrupted by another truck.
- **Appointment interval (dock, dated time range) always shown when one exists** — the same "never show a
  time without its dock and date" rule as every other surface, doubly important here since a gate officer
  is the one who'd otherwise be checking a mismatch that no other surface can see in real time.
- On **gate-booth** devices, the button set is naturally limited to Gate in / Gate out (the states in
  between never surface on that device in practice, since a truck in the yard isn't at the gate) — this
  isn't a separate rule, it falls out of U108 + the state table above automatically.

---

## 4 · Outcome screens

Every tool call resolves to a named outcome, rendered honestly rather than as a generic success/fail:

```
┌────────────────────────────────────┐         ┌────────────────────────────────────┐
│                                     │         │                                     │
│         ✓ Gate-in recorded          │         │      ⚠ Different dock              │
│                                     │         │                                     │
│  SHP1015 · 18:04                    │         │  Confirmed dock: D5                 │
│                                     │         │  Actual dock: D3                    │
│  ┌─────────────────────────────┐   │         │                                     │
│  │      Search next truck       │   │         │  Recorded as a deviation.           │
│  └─────────────────────────────┘   │         │                                     │
└────────────────────────────────────┘         │  ┌─────────────────────────────┐   │
                                                 │  │      Continue                │   │
                                                 │  └─────────────────────────────┘   │
                                                 └────────────────────────────────────┘
```

- **Success outcomes** show the recorded fact (timestamp, dock, dwell time on gate-out) and one button:
  **Search next truck** — returning to §2, never lingering on a success screen.
- **`DOCK_MISMATCH`** (right) is **not an error** — §7.5.2 states it's "allowed, but recorded as a
  deviation." Rendered in `feedback-warning` tone, not `feedback-danger` — an officer who correctly
  recorded what actually happened must not be made to feel they did something wrong.
- Every other named outcome (`ALREADY_CHECKED_IN`, `NO_ACTIVE_APPOINTMENT`, `DOCK_OCCUPIED`,
  `INVALID_TRANSITION`) gets its own honest, specific screen — see `components.md` for the outcome-banner
  component and `edge-cases.md` for what each one means operationally.

---

## Checklist coverage

No matching `checklist-design` checklist exists for this surface's shape (stated in the file header). This
section is retained per the project's own convention of naming what was and wasn't checked, rather than
silently omitted: once something is built, this surface is the right candidate for a `critique`-mode pass
(general design feedback, not a checklist), and — separately — for `web-design-guidelines`, which applies
here more than on any other surface given the physical operating conditions.
