# Carrier portal — edge cases

## 1 · A shipment link/bookmark points outside the carrier's own scope

A stale bookmark, a shared link, or a shipment reassigned to a different carrier upstream (TMS territory,
out of SetuHaul's control per §1's boundary). `get_shipment_detail` refuses server-side (§7.5.6) rather
than the client filtering after receiving data it shouldn't have.

- Renders the standard scope-failure treatment (`auth-and-scoping.md`'s "Scope failures" section) — "This
  shipment isn't in your fleet." / [ Back to dashboard ] — never a blank page, never a generic 404 that
  leaves the carrier wondering if the shipment simply doesn't exist elsewhere.
- **Never confirms or denies whether the shipment exists at all outside their scope** — the same
  inference-risk discipline (`auth-and-scoping.md`) that governs every other cross-scope boundary in the
  product. The message is about the carrier's own access, not a statement about the shipment's existence.

## 2 · A shipment's promise state changes while its detail screen is open

A planner confirms, rejects, or the driver's hold lapses while a carrier is looking at Shipment detail.
Unlike every operational console surface, **this does not need a live update** — Flow 5's "no
live-updating regions" decision applies here directly. The carrier sees the state as of their last load;
returning to the dashboard and re-opening the shipment shows the current state. This is a deliberate,
stated trade-off (simplicity over freshness for a non-time-pressured read-only viewer), not an oversight.

## 3 · A shipment appears in both the shipment list and the exceptions list

Normal, not a bug — a shipment with `PENDING_CONFIRMATION` and an open `NO_FEASIBLE_SLOT` escalation
appears once in Your Shipments (with its exception flag, `components.md` §2) and once in Open Exceptions
(`components.md` §3). No de-duplication logic needed — the two sections answer different questions ("what
is my fleet doing" vs. "what needs attention"), and a shipment can legitimately answer both.

## 4 · `get_fleet_overview`'s figures are stale relative to the shipment list

The overview strip and the shipment list are three independent calls (Flow 1) that can resolve at slightly
different times, or against slightly different snapshot moments if one is retried. This is acceptable and
not treated as an inconsistency to reconcile — the "last updated" timestamp (`screens.md` §1) is the
carrier's own signal for how fresh the page is as a whole, not a per-section guarantee. A console surface
under decision pressure (ops, planner) would need tighter consistency; a scoped read-only dashboard does
not.

## 5 · Carrier has zero shipments ever (new carrier, or fully inactive)

Distinguished from "no active shipments right now" (Flow 6's empty state) per U74's first-run-vs-caught-up
principle — a carrier with genuinely no history reads "No shipments on record yet — new deliveries will
appear here automatically," rather than the caught-up phrasing, since the two situations imply different
things about whether anything is wrong.

## 6 · A driver name or shipment identifier is unusually long

`data-formatting.md`'s truncation rules apply verbatim — carrier/driver names end-truncate (identity at
the start), shipment IDs mid-truncate (distinguishing suffix preserved), every truncated value carries a
focus-reachable tooltip with the full string. No surface-specific deviation; restated here only because
this surface's shipment table is the densest text-per-row layout it has.
