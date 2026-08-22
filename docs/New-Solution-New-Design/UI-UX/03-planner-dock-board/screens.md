# Planner dock board — screens

> Surface: desktop, Windows-primary, keyboard-first, **the throughput-critical surface in the product**
> (§7.3 — 5 coordinators clearing 20–35 requests in 30 minutes, 30 seconds/row, under a 15-minute D9
> deadline). Density `compact` (`spacing-and-layout.md` lists "Planner, ops console" together). Light
> theme default, dark at parity (U69). Desktop-only. Foundations: `../00-foundations/`.
>
> Structure derived from Checklist Design's *Data Table* and *Timeline/Gantt View* (Web app) checklists,
> read directly before drafting this file, not audited afterward (per the standing process rule) — see
> *Checklist coverage* at the end.

## The surface in one line

Two tabs: the §7.3 pending-request **Queue** (default) and the **Board** — a per-facility dock/time Gantt
(§2's persona table: "Dock board, Gantt, per facility, per day"). Queue is where a planner spends their
30 seconds; Board is where they get occupancy context, pick a counter-offer slot, block a dock, or review
a sequencer proposal. Never a permanent split (U102) — the queue's 7-field row needs the full width U39
was written to protect.

---

## Screen map

```
Sign in ──▶ Console (two tabs)
              │
              ├── Queue tab   (default, always the throughput home)
              └── Board tab   (occupancy, counter-offer picker, block-dock form, proposal diff)
```

Selecting **Counter-offer** on a queue row switches to Board automatically, pinned to that request
(U103). Everything else about tab-switching is a plain, explicit click — the surface never silently
changes tabs on its own.

---

## 1 · Console shell

```
┌──┬──────────────────────────────────────────────────────────────────────────────────┐
│▌ │ [Jaipur ▾]   [ Queue ]  Board          🔍 Search        🔔  ?  ⚙︎ AB              │  56px top bar
├──┼───────────────────────────────────────────────────────────────────────────────────┤
│▤ │  QUEUE (24 pending · 6 bulk-eligible)                                             │
│  │  [ Select all eligible (6) ]                                                       │
│⏱ │ ┌────────┬──────────────┬────────────────────┬─────────┬─────┬───────┬──────┬───┐ │
│  │ │Sel     │Driver·Carrier│Interval             │Receipt  │Displ│ETA    │Limit │TTL│ │
│  │ ├────────┼──────────────┼────────────────────┼─────────┼─────┼───────┼──────┼───┤ │
│  │ │☑ ▌     │Ravi · RajR.  │D1 · 13:00–14:15     │CRIT·70m │none │—      │13:30 │2:1│ │
│  │ │☑       │Amit · Kota T.│D2 · 14:00–14:45     │HIGH·20m │none │—      │15:00 │6:4│ │
│  │ │☐       │Neha · GGN L. │D3 · 15:00–16:00     │NORM·0m  │SHP-x│LOW    │16:00 │9:0│ │
│  │ └────────┴──────────────┴────────────────────┴─────────┴─────┴───────┴──────┴───┘ │
│  │  focused row: [C]onfirm [R]eject c[O]unter [H]old [E]scalate                       │
├──┴───────────────────────────────────────────────────────────────────────────────────┤
│ ● Online · synced 3s ago     Jaipur     24 pending     Policy v3                      │  28px status bar
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### Shell anatomy

| Element | Rule |
|---|---|
| Icon rail | 56px, per `components.md` §7 — same minimal two-destination model as `02-ops-exception-console/` (U101): this console + Profile |
| Top bar | **Single-facility switcher** (not "All facilities" — §7.3's load arithmetic and D5's sequencer are explicitly per-facility; unlike ops, there is no cross-facility triage job here) · the two tabs · search · notifications/help/user |
| Status bar | Per `components.md` §7 — connection, last sync, **active facility (always one, never "All")**, pending count, policy version |

---

## 2 · Queue tab (the 30-second row, §7.3)

```
┌────────┬──────────────┬─────────────────────┬──────────┬──────┬────────┬───────┬─────┐
│ ☐      │ Ravi K.      │ D1 · 13:00–14:15    │ CRITICAL │ none │  —     │ 13:30 │ 2:14│
│ ▌       │ Rajasthan R. │                     │ 70m late │      │        │       │     │
│        │              │                     │ exact dk │      │        │       │     │
│        │              │                     │ 0m wait  │      │        │       │     │
├────────┼──────────────┼─────────────────────┼──────────┼──────┼────────┼───────┼─────┤
│ ☑      │ Amit S.      │ D2 · 14:00–14:45    │ HIGH     │ none │  —     │ 15:00 │ 6:42│
│        │ Kota Transp. │                     │ 20m late │      │        │       │     │
├────────┼──────────────┼─────────────────────┼──────────┼──────┼────────┼───────┼─────┤
│ ☐      │ Neha P.      │ D3 · 15:00–16:00    │ NORMAL   │ SHP- │  LOW   │ 16:00 │ 9:05│
│        │ GGN Logist.  │                     │ 0m wait  │ 1013 │        │       │     │
└────────┴──────────────┴─────────────────────┴──────────┴──────┴────────┴───────┴─────┘
```

### The seven fields (§7.3's own list, cross-referenced to their components)

| Column | Renders |
|---|---|
| Selection | Checkbox (`components.md` §19's selection model) + priority marker (§5) as the row's left edge |
| Driver · shipment · carrier | Identity, one line each |
| Requested interval | Dock + dated time range — **always dated**, per the multi-day-horizon rule already governing every other surface |
| Condensed receipt | `components.md` §4's condensed variant — never a sentence |
| Displacement check | "conflicts with none" / "would delay SHP-xxxx" — §7.3 calls this **the single most important field**; never truncated (`data-formatting.md`'s general rule, restated in `components.md` §6 for this exact case) |
| ETA confidence | `LOW` in `feedback-warning` tone — **do not confirm** without asking first (this is a rendered warning, not just a value) |
| Driver's own limit | `latest_acceptable_ts` — confirming past it creates a new exception, stated as a rule not just a column |
| TTL remaining | Countdown (`components.md` §3), colour-coded by the same thresholds as everywhere else |

### Rules
- **Sort is the composite urgency** (TTL remaining · priority · physically-waiting at the gate,
  `facility_checkins.queue_state`), never plain FIFO — §7.3's own SHP1014 example (CRITICAL, arrived late,
  must not be buried). Frozen while a row has focus (U19).
- **Column widths are fixed, never auto** (`components.md` §6) — a 30-second decision cannot tolerate the
  row reflowing under the planner's eyes mid-read.
- **Filter by priority or ETA confidence, narrowing membership only, never changing sort** (caught missing
  in a `checklist-design` audit — added, unlike ops's cross-facility filter set, because a spike is exactly
  when a planner wants to isolate "CRITICAL only" or "LOW confidence only" for a focused pass). Small
  surface: no filter chips needed at this scale (15–35 rows) the way ops's cross-facility view needed them
  — the active filter is visible directly in the toolbar text ("Filter: CRITICAL · 6 shown").
- **Single-key actions on the focused row**: `C`/`R`/`O`/`H`/`E` (U46), never active while focus is in a
  text input.
- **"Select all eligible (N)" is the primary bulk entry point** (U63/§6) — manual multi-select stays
  available for anything outside the five safe-batch predicates, but ineligible rows show a disabled
  checkbox with the specific failing predicate as its tooltip, never a bare disabled control.

---

## 3 · Board tab — at rest

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│ Jaipur · Board                          [ Block a dock ]   [ Review proposal (0) ]  │
│                                                                                      │
│         09:00      10:00      11:00      12:00 │now  13:00      14:00      15:00    │
│ D1  ████░░░░░░░░████████░░░░░░░░░░░░░░░░░│    │▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │
│ D2  ░░░░████████░░░░░░░░░░░░░░░░░░░░░░░░░│    │░░░░░░░░████████░░░░░░░░░░░░░░░░░░  │
│ D3  ░░░░░░░░░░░░████████░░░░░░░░░░░░░░░░░│    │░░░░░░░░░░░░░░░░░░░░████████░░░░░░  │
│ D4  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│    │░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │
│ D5  ▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒│    │▒ blocked — DEVT002 outage ▒▒▒▒▒▒  │
│ D6  ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░│    │░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │
│                                            │now                                     │
└────────────────────────────────────────────────────────────────────────────────────┘
  ████ CONFIRMED   ▓▓▓▓ HELD/PENDING (dashed border, per chip rules)   ▒▒▒ blocked (dock_status_events)
```

### Anatomy, grounded in the actual schema

| Element | Source | Rendering |
|---|---|---|
| Rows | `docks` for this facility | One row per dock — **row grouping is inherent**, not a separate control (checklist item, already satisfied by the domain) |
| Time axis | The sequencer's own rolling horizon: **4 hours or to `close_time`, whichever is sooner** (§5.1) | Not a generic "zoom to any range" axis — Kibo Gantt's zoom presets are one of U52's still-unverified items; this surface does not depend on them |
| **"Now" indicator** | Client clock reconciled against server offset, same discipline as the countdown component (`components.md` §3: "server time is authoritative") | Vertical line, labelled `now` |
| Task bars | `dock_occupancy` rows, `window` (tstzrange) for position, **`state` column for colour** | See the state→token mapping table in `components.md` §3 — reuses the promise-state chip's exact tokens, no invented palette |
| Outage windows | `dock_status_events` — D1's declared single authority for availability | Distinct hatched fill, **never rendered with a promise-state token** — a booking and an unavailability are different facts and must not share an encoding |

### Rules
- **No drag-to-reschedule, no dependency lines** (checklist items explicitly out of scope) — U25 rules out
  free dragging, and nothing in `SOLUTION_DESIGN.md` models inter-shipment dependencies the way a
  project-management Gantt would. Stated here so a future reader knows these were considered, not missed.
- **Read + act via affordances only** (U25): clicking an open interval on an eligible dock is the
  counter-offer picker (U103, §4 below); clicking `[ Block a dock ]` opens the form (U107, §5 below).
  Nothing on the board is draggable.
- The `[ Review proposal (N) ]` button is Inactive (`components.md` §18) with `(0)` when no sequencer run
  is pending, and becomes the entry point to §6's diff overlay the moment one exists — self-triggered or
  handed off from `02-ops-exception-console/`'s Flow 4.

---

## 4 · Board tab — counter-offer picker active (U103)

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│  Picking a new slot for SHP1014 (Ravi K. · Rajasthan Roadlines) — click an open      │
│  interval on an eligible dock.                                    [ Cancel ]         │
│                                                                                      │
│         09:00      10:00      11:00      12:00 │now  13:00      14:00      15:00    │
│ D1  ████░░░░░░░░████████░░░░░░░░░░░░░░░░░│    │▓▓▓▓▓▓░░ ▒ click here ▒░░░░░░░░░░  │
│ D2  ░░░░████████░░░░░░░░░░░░░░░░░░░░░░░░░│    │░░░░░░░░████████░░░░░░░░░░░░░░░░░░  │
│ D5  ▓heavy-only, SHP1014 ineligible — dimmed, not clickable▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓  │
└────────────────────────────────────────────────────────────────────────────────────┘
```

### Rules
- **A persistent context banner names the shipment and offers Cancel** — a planner must never forget which
  request they're picking a slot for, and must always have a clean way out without committing anything.
- **Ineligible docks dim and become unclickable** (`components.md` §18's Disabled, not Inactive — this is a
  temporary, prerequisite-driven unavailability specific to *this* shipment, not a permission or scope
  question) — a heavy-dock-only shipment cannot be counter-offered into D1–D4.
- Clicking an open interval **revalidates through Stage 1 before offering** (`components.md` §11, already
  stated for the reject flow's sibling) — a planner cannot hand out an infeasible slot by hand. A refusal
  (`INTERVAL_UNAVAILABLE`) re-renders the board with that interval now shown occupied, never a dead click.
- On success, the surface returns to the Queue tab with the row updated to reflect the new proposed
  interval and the driver's new option set sent — matching `counter_offer`'s actual return shape
  (`SOLUTION_DESIGN.md` §7.5.1).

---

## 5 · Block-dock form (U106/U107)

```
┌──────────────────────────────────────┐
│ Block a dock                         │
│                                       │
│ Dock          [ D5 (Reefer) ▾ ]      │
│ From          [ 18:00 ]              │
│ To            [ 22:00 ]              │
│ Reason        [ Leveller failure ]   │
│                                       │
│ ⚠ 2 confirmed appointments fall       │
│   inside this window — SHP1005,      │
│   SHP1013. Blocking will escalate     │
│   both as a capacity incident.        │
│                                       │
│         [ Cancel ]   [ Block dock ]  │
└──────────────────────────────────────┘
```

### Rules
- **Form, not a board gesture** (U107) — opened from the `[ Block a dock ]` toolbar action, never a
  click-and-drag range-select, which would sit on the same line U25 already draws against dragging.
- **The affected-appointment warning is mandatory, not optional**, and names the shipments by id — a
  planner commits a block knowing exactly what it strands, never discovering the cascade after the fact.
  This is the honest interface version of the seeded DEVT001/SHP1005 case.
- Submitting calls `block_dock` (`SOLUTION_DESIGN.md` §7.5.1); the response's affected-appointment set is
  what actually starts the `CAPACITY_EVENT_CASCADE` escalation (§7.4) on the ops side — this form does not
  create the escalation itself, the backend does, consistent with every other surface never inventing an
  effect the tool contract doesn't already produce.
- 24-hour time inputs, `tabular-nums` (`components.md` foundations §12).

---

## 6 · Sequencer proposal — diff overlay (U104)

```
┌────────────────────────────────────────────────────────────────────────────────────┐
│  Proposal · scheduling_run_id RUN-8f2a · requested from Ops (Capacity incident)      │
│                                                                            [ Apply ] │
│         09:00      10:00      11:00      12:00 │now  13:00      14:00      15:00    │
│ D1  ████░░░░░░░░████████░░░░░░░░░░░░░░░░░│    │▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │
│ D3  ░░░░░░░░░░░░████████░░░░[MOVED→]████░│    │░░░░░░░░░░░░░░░░░░░░████████░░░░░░  │
│ D4  ░░░░░░░░░░░░░░░░░░[NEW]████░░░░░░░░░░│    │░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░  │
│                                                                                      │
│  4 shipments: 1 unchanged · 2 moved · 1 newly placed · 0 unplaceable                │
└────────────────────────────────────────────────────────────────────────────────────┘
```

### Rules
- **§5.1's own diff vocabulary, verbatim** — unchanged / moved / newly placed / unplaceable. No synonyms
  invented for the UI.
- **Moved and newly-placed bars render distinctly from the current-schedule bars beneath them** (an
  outline or ghost treatment, not a new hue — the hue budget stays exactly where U10/U59/U85 already fixed
  it).
- **Unplaceable shipments list separately below the board**, since they have no interval to show — a gap
  is a gap, never a zero-width bar pretending to be a real placement (`data-formatting.md`'s absence rule).
- **Apply calls `apply_schedule_proposal`** (§7.5.3) — all-or-nothing, exactly as the tool contract states;
  there is no "apply these three" partial-selection affordance here either, matching the tool's own
  deliberate omission of that argument.
- **Reachable from two origins**: self-triggered (a planner requests a re-sequence directly — out of this
  file's detailed scope, since §7.3 frames re-sequencing as available but doesn't specify a planner-side
  trigger UI beyond "review proposal") and handed off from `02-ops-exception-console/`'s Flow 4 (a capacity
  incident ops triaged). Both land on this same overlay — one screen, not two.

---

## Checklist coverage (U34)

**Data Table** items: sortable columns (deliberately fixed algorithmic sort, not user-toggleable — Not
needed here, same reasoning `02-ops-exception-console/` used for its own queue and for the same D9/urgency
correctness reason) · row selection and bulk actions (present, §6/§19/U63) · search and filter (present,
top bar) · pagination (Not needed here — §7.3's own load arithmetic caps this at 15–35 rows) · frozen
columns (present — first column fixed on horizontal scroll, `components.md` §6) · empty/loading (present,
§13). **Timeline/Gantt View** items: time axis (present, horizon-bound not free-zoom) · task bars (present,
schema-grounded state colouring) · today indicator (present, server-reconciled) · milestones (present, as
outage windows) · row grouping (inherent, docks) · dependencies and drag-to-reschedule (explicitly Not
needed here, reasoned above, not silently dropped).
