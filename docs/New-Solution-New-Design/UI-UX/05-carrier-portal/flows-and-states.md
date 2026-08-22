# Carrier portal — flows and states

## Flow 1 · Load the dashboard

1. Sign-in (`auth-and-scoping.md`, not repeated here) routes directly to the dashboard — no facility or
   role landing choice, since this role has exactly one destination.
2. Four calls fire on load: `get_fleet_overview` (the headline counts + current on-time %),
   `get_carrier_on_time_performance(window='30d')` (the sparkline's trend series specifically — a separate
   call from the overview's single current figure), `list_fleet_shipments`, `list_fleet_exceptions`. Each
   section renders independently as its own data arrives — the shipments table is not blocked waiting on
   the overview strip, and vice versa. The on-time stat tile itself waits on both of its two calls before
   rendering the sparkline (the headline % can render from `get_fleet_overview` alone in the meantime).
3. **Skeleton loading per section** (`components.md` §13), not one page-level spinner — a carrier with a
   fast connection to `get_fleet_overview` but a slower fleet-list query should see the stat tiles resolve
   immediately rather than waiting on the slowest section.

## Flow 2 · Browse and filter shipments

1. Default view: all statuses, most-recently-updated first.
2. Filter dropdown narrows by promise state (`SHOWN`/`HELD`/`PENDING_CONFIRMATION`/`CONFIRMED`) or "has
   open exception" — membership only, never re-fetches the on-time/exception-count tiles, which reflect
   the whole fleet regardless of the shipment list's current filter.
3. No sort control beyond the default — this is a light, mostly-glanced-at surface; a full sortable-column
   data table (`checklist-design`'s Data Table checklist items) would be over-building for a read-only list
   this size.

## Flow 3 · Open a shipment's detail

1. Tap any shipment row (`components.md` §2) → `get_shipment_detail(shipment_id)`.
2. **Success** → renders `screens.md` §2's read-only detail.
3. **Refused** (a stale link or bookmark pointing at a shipment outside this carrier's own `carrier_id`) →
   see `edge-cases.md` #1 — never a silent redirect or an empty page, since either would leave the carrier
   guessing whether the shipment simply doesn't exist or whether they're being denied something.
4. Back returns to the dashboard with the shipment list's scroll position and filter preserved — a carrier
   checking on several shipments in sequence shouldn't lose their place each time.

## Flow 4 · Open an exception's shipment

Same mechanism as Flow 3 — the exception summary row (`components.md` §3) routes to the same Shipment
detail screen, not a separate exception-detail view. There is exactly one detail destination on this
surface, reached two ways.

## Flow 5 · Data refresh

- **No live-updating regions** — this is a deliberate departure from every operational console surface
  (ops, planner, gate), all of which have some real-time element. A scoped-read dashboard for a role with
  no time-pressured decision to make doesn't need one; `screens.md` §1 already states the "last updated"
  timestamp replaces a live-sync indicator here.
- A manual refresh (browser reload, or a small refresh control beside the "last updated" timestamp)
  re-fetches all three sections. There is no partial/background refresh model to specify — the surface is
  simple enough that a full reload is the honest, sufficient mechanism.

## Flow 6 · Empty states

| Situation | Copy | Next action |
|---|---|---|
| No active shipments | "No active shipments right now." | None — this is a genuine "nothing right now," not "nothing yet" (U74), since a carrier with an established fleet legitimately has slow periods |
| No open exceptions | "No open exceptions." | None — the caught-up state, same anatomy as every other surface's empty-queue treatment |
| Filtered shipment list, no matches | "No shipments match this filter." | [ Clear filter ] |
