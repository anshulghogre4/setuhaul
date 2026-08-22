# Carrier portal — screens

> Surface: desktop-primary, scoped read-only. Density `comfortable` (`spacing-and-layout.md`'s table lists
> "Carrier, admin, driver chat" together). Light theme default, dark at parity (U69). Foundations:
> `../00-foundations/`.
>
> Structure derived from Checklist Design's *Analytics* checklist (Web app) — the closest match found,
> read directly before drafting (per the standing rule) — see *Checklist coverage* at the end for what
> applies and what's deliberately excluded.

## The surface in one line

One sectioned dashboard, cross-facility, entirely read-only. `SOLUTION_DESIGN.md` §2's persona table lists
no write job for this role, and §7.5.6 (added this checkpoint — the third missing tool catalog found this
project) backs every read with a `carrier_id`-scoped tool. §18's unavailability taxonomy already calls this
"substantially a Read-only surface" — every rule below follows from taking that literally.

---

## Screen map

```
Sign in ──▶ Dashboard (single page, sectioned)
              │
              └──▶ Shipment detail (opens from any shipment row, read-only)
```

No tabs, no facility switcher (carriers are not facility-scoped — a fleet spans whatever facilities it
delivers to, shown together always), no settings beyond account basics (out of this file's scope, covered
once in `auth-and-scoping.md`).

---

## 1 · Dashboard

```
┌──┬──────────────────────────────────────────────────────────────────────────────────┐
│▌ │ Rajasthan Roadlines                                    🔔  ?  ⚙︎ AB              │  56px top bar
├──┼───────────────────────────────────────────────────────────────────────────────────┤
│▤ │  ┌──────────────┬──────────────┬──────────────────────────┐                       │
│  │  │ 18 active     │ 3 open       │ On-time: 91%  ▲2%         │  ← stat tiles (U66)   │
│👤│  │ shipments     │ exceptions   │ ╱╲╱▔╲╱╲╱▔  (30d)          │                       │
│  │  └──────────────┴──────────────┴──────────────────────────┘                       │
│  │  Last updated 2 min ago   ↻ Refresh                                                │
│  │                                                                                     │
│  │  YOUR SHIPMENTS                        [ Filter: all statuses ▾ ]                  │
│  │ ┌────────┬──────────┬──────────────────┬────────────────┬─────────┐               │
│  │ │Shipment│Driver    │Facility · Dock    │Status           │         │               │
│  │ ├────────┼──────────┼──────────────────┼────────────────┼─────────┤               │
│  │ │SHP1015 │Ravi K.   │Jaipur · D5        │◷ PENDING        │    ›    │               │
│  │ │SHP1009 │Amit S.   │Gurugram · D2      │✓ CONFIRMED      │    ›    │               │
│  │ │SHP1013 │Neha P.   │Kota · —           │⚠ Exception open │    ›    │               │
│  │ └────────┴──────────┴──────────────────┴────────────────┴─────────┘               │
│  │                                                                                     │
│  │  OPEN EXCEPTIONS                                                                    │
│  │ ┌──────────────────────────────────────────────────────────────────┐               │
│  │ │ SHP1013 · Neha P. · No feasible slot — escalated 09:12            │  ›            │
│  │ └──────────────────────────────────────────────────────────────────┘               │
└──┴──────────────────────────────────────────────────────────────────────────────────┘
```

### Sections

| Section | Content | Rule |
|---|---|---|
| Header strip | Carrier's own name (not a facility, since none is selected — this *is* the account context) | Replaces the facility-switcher slot every other console surface has in this position |
| Stat tiles (U66) | Active shipment count · open exception count · 30-day on-time % with delta and sparkline | One `get_fleet_overview` call. The on-time tile's delta compares this 30-day window against the prior 30-day window — the checklist's *Period comparison* item, applied narrowly to the one metric that earns it |
| Last updated | Timestamp **+ an explicit refresh control** (`↻ Refresh`), not a live-updating region | This is a scoped read surface, not an operational console under time pressure — a manual refresh model is honest about data freshness without implying real-time urgency this role doesn't need. The control itself was missing from an earlier pass (caught in a `checklist-design` audit against the Analytics checklist's "last updated indicator" item) — re-fetches all three sections per Flow 5, same mechanism a page reload would trigger |
| Your shipments | `list_fleet_shipments`, filterable by status | Every row opens Shipment detail (§2) |
| Open exceptions | `list_fleet_exceptions` | Status only — never the full escalation detail an ops coordinator sees (owner, SLA clock, co-pilot); a carrier sees *that* something is being worked, not the internal mechanics of who's working it |

### Rules
- **No facility filter, no facility switcher** — a carrier's fleet is shown whole, always, across every
  facility it touches. Facility appears as a column value per row, never a scope-narrowing control.
- **Every row and every control here is Read-only or a genuine navigation link — never a styled-but-inert
  control** (`components.md` §18's Read-only state: "no hover state, no accent colour, no cursor change on
  anything the carrier cannot act on"). The `›` chevron on each row is the one exception — it's real
  navigation to Shipment detail, not an action on the row's data.
- **No cross-carrier framing anywhere on this page** — no "you rank 2nd of 4," no facility-wide average to
  compare against, not even a bare count of other carriers' shipments at a shared facility (U28,
  `auth-and-scoping.md`'s inference-risk rule).

---

## 2 · Shipment detail

```
┌────────────────────────────────────┐
│ ← Dashboard                         │
│                                     │
│ SHP1015 · Ravi K.                   │
│                                     │
│ ◷ PENDING CONFIRMATION               │
│ Decision by 11:57                   │
│                                     │
│ Jaipur · D5 · Tue 20 Aug · 13:00    │
│                                     │
│ ── History ─────────────────────── │
│ 09:41  Reported delay               │
│ 09:52  Option offered               │
│ 09:53  Held, then requested         │
└────────────────────────────────────┘
```

### Rules
- **Read-only in full** — no Confirm/Reject/Counter-offer affordances render here even though the
  promise-state chip is the same component a planner sees; this is the chip's read-only consumption, not a
  new interactive context for it.
- **`get_shipment_detail` validates the shipment belongs to this carrier server-side** (§7.5.6) — the UI
  never needs its own guard against a stale/shared link reaching a shipment outside scope, since the tool
  itself refuses rather than the client filtering after the fact.
- History is a plain timeline of the shipment's own recorded events — never another party's internal
  notes (a planner's rejection note, an ops coordinator's internal-only remark) which are explicitly
  never-shown fields elsewhere in the spec (`components.md` §11's "internal note the driver never sees,"
  same boundary applies to the carrier).

---

## Checklist coverage (U34)

Checklist Design's *Analytics* (Web app) items: **Headline metrics** (present, the stat-tile strip) ·
**Charts with labels and axes** (present but deliberately minimal — one sparkline, per U33's product-wide
charting policy, not a chart library) · **Period comparison** (present, narrowly — only the on-time tile's
delta, not applied to every metric) · **Segment breakdown** (present, narrowly — the shipment status
filter, not a full slice-by-any-dimension control this light a surface doesn't need) · **Last updated
indicator** (present) · **Loading and empty states** (present, `components.md` §13). **Date range
selector** is explicitly **Not needed here** — the 30-day window is fixed by decision, not user-configurable;
a picker would imply a flexibility this surface deliberately doesn't offer, consistent with U33's
minimal-charting stance for the one chart this surface has.
