# Carrier portal — components

> Surface-specific only. Shared components (stat tile, promise-state chip, data table conventions,
> unavailability taxonomy) are specified once in `../00-foundations/components.md` and cross-referenced,
> not restated.

## 1. Fleet overview strip

### Anatomy
Three stat tiles (`components.md` foundations §14) in a row: active shipments, open exceptions, on-time
performance.

### States
Loading (skeleton, matching final tile dimensions) → loaded → **stale** (see `edge-cases.md` #4).

### Rules
- **The on-time tile is the only one with a delta and a sparkline** — active-shipment and exception counts
  are point-in-time facts with no meaningful trend to show at a glance; forcing a sparkline onto every tile
  would be decoration, not information, exactly the distinction `dataviz`'s own discipline argues for.
- **On-time delta compares the current 30-day window against the prior 30-day window** — up/down arrow +
  percentage point change, `feedback-success`/`feedback-danger` tone on the arrow only, never recolouring
  the whole tile (the same restraint `components.md` §14 already specifies for stat tiles generally).
- Sparkline follows `dataviz`'s form guidance: a thin area/line fill, faint baseline, no axis labels or
  gridlines at this scale — it exists to show shape (trending up/down/flat), not to be read as precise data
  points; `get_shipment_detail`-level precision belongs in the number, not the line.

---

## 2. Fleet shipment row

### Anatomy
```
SHP1015    Ravi K.    Jaipur · D5    ◷ PENDING CONFIRMATION    ›
```

### Rules
- **Uses the shared promise-state chip verbatim** (`components.md` §2) — no carrier-specific restyling.
  Consistency here matters more than differentiation: a carrier reading a `PENDING_CONFIRMATION` chip
  should recognise it instantly from the exact same visual language a planner uses.
- **Facility · dock renders as plain text**, no facility-accent colour (same reasoning as U91's ops-console
  rule — this surface's rows span many facilities at once, and the accent's two safe render locations
  don't include a cross-facility list row here either).
- **The whole row is a single navigation target to Shipment detail** — not a row of individually-styled
  cells with one hidden action; per `components.md` §18's Read-only guidance, nothing about the row implies
  it can be acted on, only opened for more detail.
- **Exception flag** (⚠) renders when `list_fleet_exceptions` has an open entry for this shipment — a
  status-line addition to the row, not a separate lookup the carrier has to perform manually by cross-
  referencing two lists.

---

## 3. Exception summary row

### Anatomy
```
SHP1013 · Neha P. · No feasible slot — escalated 09:12                    ›
```

### Rules
- **Status only** — reason (`iconography.md`'s Escalation reason table, same icons) + a plain-language
  status clause, timestamp. **Never** the internal escalation mechanics an ops coordinator's console shows
  — no owner name, no SLA clock, no stepper. A carrier needs to know *that* something is being handled, not
  the internal apparatus handling it.
- Tapping opens the same Shipment detail (`screens.md` §2), not a separate escalation-detail view — this
  surface has exactly one detail destination, keeping the read-only promise simple and singular.

---

## 4. Shipment detail (read-only consumption)

### Anatomy
Identity line · promise-state chip (full context: dock, dated interval, TTL if still live) · a plain
chronological history list.

### Rules
- **Every component here is the same shared component used elsewhere, in its read-only form** — the chip,
  the countdown (if a hold/pending is still live and TTL-bearing), the history entries. This file adds no
  new visual language, only the rule that no affordance renders alongside them.
- **History never surfaces another party's internal-only content** — a planner's rejection note, an ops
  coordinator's private remark, are both explicitly not-shown fields (`components.md` foundations §11's
  reject-flow already draws this line for the driver; it applies identically here). Only outcomes and
  driver-visible messages appear.
