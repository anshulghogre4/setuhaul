# Iconography

> Structure follows Checklist Design's *Icon* checklist. Decisions follow `../README.md` U11, U57–U58.

## The rule

**Name an icon by what it literally is, not by the action it happens to represent here.** A `truck` icon
is `truck` — never `assign-driver` — so the same glyph stays usable the next time a truck-shaped meaning
is needed. This is the checklist's own tip, and it matters in a product with this many distinct icon-using
concepts: naming by action guarantees duplication the moment a second context needs the same picture.

**Icon-only controls are forbidden on the driver surface** (`components.md` §1) and require `aria-label`
everywhere else. An icon augments a label; it does not replace one in this product.

---

## Library and stroke weight

**Lucide** (U11), stroke weight **2px at every size, never varied.** Consistency of stroke is one of the
checklist's core items, and it is also what keeps an icon legible at the smallest size this system uses —
a variable-weight icon set (the `Phosphor` alternative considered during foundations) reads inconsistently
across a dense table where several icons sit in one row at once.

---

## Sizing scale

Tied to `typography.md`'s scale, not invented separately.

| Token | Size | Used for |
|---|---:|---|
| `icon-xs` | 14px | Inline with `text-sm` / `text-micro` — inside a chip, a table cell |
| `icon-sm` | 16px | Inline with `text-body` — the default for most in-row icons |
| `icon-md` | 20px | Standalone in a button, form field, or list item |
| `icon-lg` | 24px | Top bar, rail, section headers |
| `icon-xl` | 32px | Empty states, error pages (`components.md` §13, §14) |

**Responsiveness at size** (the checklist's first item): every icon in this inventory reads correctly down
to `icon-xs`. Where a Lucide icon's detail collapses below that — dense multi-stroke icons like
`layout-dashboard` — the simpler variant is chosen instead, even if the more detailed one is a marginally
better literal match. Legibility at the smallest size wins the tie.

---

## Per-domain inventory

### Promise state

Defined in `components.md` §2 — **cross-referenced here, not redefined.** These four are the only icons
permitted to sit inside a promise-state chip, and no other icon in this inventory may be reused there.

| State | Icon |
|---|---|
| `SHOWN` | `list` |
| `HELD` | `timer` |
| `PENDING_CONFIRMATION` | `clock-fade` |
| `CONFIRMED` | `circle-check` |

### Dock type

`shipments.required_dock_type` / `docks.dock_type` (§6, SOLUTION_DESIGN.md).

| Type | Icon | Note |
|---|---|---|
| `STANDARD` | `box` | The default — appears least often as an explicit icon, since it needs no distinguishing |
| `REEFER` | `snowflake` | Temperature-controlled; also used wherever `supports_refrigerated` is surfaced |
| `HEAVY` | `weight` | >25,000 kg dock requirement (RULE004) |

### Queue state

`facility_checkins.queue_state` — the gate/yard vocabulary.

| State | Icon |
|---|---|
| `NOT_QUEUED` | *(none — absence is the signal)* |
| `WAITING_EARLY` / `WAITING_LATE` | `door-open` |
| `WAITING_DOCK_UNAVAILABLE` | `door-closed` |
| `CALLED_TO_DOCK` | `bell-ring` |
| `IN_DOCK` | `truck` |
| `COMPLETED` | `check` |

**Deliberately distinct from the promise-state icons**, even where a naive reading might reuse `check` for
both `COMPLETED` and `CONFIRMED` — they never appear in the same component, but the inventory keeps them
conceptually separate so a future screen combining gate and promise data doesn't collide.

### Escalation reason

§7.4's eight reasons. Rendered inside the escalation stepper's cause line (`components.md` §16), never as
the stepper's step icons — the steps themselves (`OPEN → ACKNOWLEDGED → IN_PROGRESS → RESOLVED`) are
unlabelled dots, per U60.

| Reason | Icon |
|---|---|
| `NO_FEASIBLE_SLOT` | `calendar-x` |
| `PENDING_EXPIRED_UNACTIONED` | `timer-off` |
| `AMBIGUOUS_SHIPMENT` | `circle-help` |
| `LOW_CONFIDENCE_ETA` | `alert-triangle` — same glyph as the ETA-confidence icon in `color.md`, deliberately, since it is the same underlying fact |
| `WAREHOUSE_REPLY_CONFLICT` | `git-compare` |
| `NOTIFICATION_FAILED` | `mail-warning` |
| `NOTIFICATION_UNROUTABLE` | `mail-x` — distinct from `NOTIFICATION_FAILED`; a send that never had anywhere to go reads differently from one that failed in flight |
| `SAFETY_OR_REGULATED` | `shield-alert` |
| `CAPACITY_EVENT_CASCADE` | `network` — reused as the capacity-incident row's icon (`components.md` §17) |

### Planner affordances

§7.3's five, matching the intent-based button variants (`components.md` §1).

| Affordance | Icon | Variant |
|---|---|---|
| Confirm | `check` | `constructive` |
| Counter-offer | `repeat` | `neutral` |
| Reject | `x` | `destructive` |
| Hold for information | `pause` | `neutral` |
| Escalate | `arrow-up-right` | `cautionary` |

### Rail destinations (added 2026-08-26)

The sizing table above says `icon-lg` is for "Top bar, rail, section headers", but this inventory had **no
navigation domain at all** — found during the M5/E5.0 implementation pass, when the icon rail turned out to
have a prose spec, no rendering, and no icons. These are the six destinations the six roles actually get,
and the list is short because **U101 governs it**: a destination exists only where
`SOLUTION_DESIGN.md` §2 gives the role a job *and* §7.5.* gives it a tool. Nothing here was added to make a
rail look less empty.

**One destination per role — one surface per role.** The criterion is stated in `components.md` §7 (*What
is a rail destination, and what is a tab*); this table is its application.

| Destination | Role | Icon | Grounded in |
|---|---|---|---|
| **Exceptions** | Ops coordinator | `flag` | §2 "triage exceptions, resolve ambiguity, escalate"; §7.5.5 (8 tools) |
| **Dock Command** | Warehouse planner | `chart-gantt` | §2 "confirm/reject, block docks, re-sequence"; §7.5.1 (8 tools) + §7.5.3. Queue and Board are **tabs** |
| **Yard** | Gate / yard officer | `warehouse` | §2 "gate-in, yard queue, call-to-dock…"; §7.5.2 (5 tools). Two device contexts switch on a **segmented control** |
| **Fleet** | Carrier manager | `package` | §2 "own fleet's shipments, exceptions, on-time performance"; §7.5.6 (5 tools). All three are **sections of one dashboard** — `05-carrier-portal/screens.md`: *"one sectioned dashboard,"* *"no tabs"* |
| **Admin** | Administrator | `sliders-horizontal` | §2 "users, roles, facility_rules, policy weights, audit"; §7.5.7 (12 tools). Four **tabs** |

**Corrected 2026-08-26.** Carrier initially had three destinations (Shipments · Exceptions · Performance),
derived by counting §2's jobs and §7.5.6's tools. That contradicted the already-designed surface, which is a
single sectioned dashboard. **A job in §2 is not a destination and neither is a tool in §7.5.\*** — the
tool-catalog cross-check proves a job has backing, not that it has its own screen. `flag` is therefore
Ops-only; `chart-line` is no longer a rail icon at all (the on-time figure is a stat tile on the Fleet
dashboard).

**Two further consequences, each of which prevented an invented icon:**

- **The driver has no rail.** The PWA runs 320–768px and carries its own chrome; a 56px rail expanding to a
  240px overlay on a 390px phone is not a viable shell. The driver's Profile is a separate surface.
- **Settings is not a rail destination** — it is reached from the user menu, so no gear icon appears on the
  rail. This also avoids `settings` colliding with `sliders-horizontal`'s admin meaning.

⚠️ **Verify `chart-gantt` against the installed `lucide-react` version** — it was renamed in Lucide's
`chart-*` sweep (from `gantt-chart`), so the export name depends on the version pinned. The glyph is the
same either way; only the import breaks.

### System and connection

For the status bar (`spacing-and-layout.md`) and the offline states (`auth-and-scoping.md`).

| State | Icon |
|---|---|
| Online / synced | `wifi` |
| Offline | `wifi-off` |
| Syncing | `refresh-cw` (the only icon in this inventory that spins — see `motion.md`'s skeleton-shimmer treatment, same rule applies) |
| Sync failed | `cloud-alert` |

### Informational callout

**Added 2026-08-22** — found missing during the mockup gate pass: a "link sent" style panel had nothing
to reach for and borrowed `circle-alert`, which is reserved for errors elsewhere in this same inventory.
Distinct from `circle-help` (contextual, explains a specific ambiguous element per `components.md` §15) and
from `circle-alert` (something is wrong) — this is for a neutral fact worth surfacing, not a warning and
not an explanation.

| Context | Icon |
|---|---|
| Neutral informational notice (e.g. "a reset link has been sent") | `info` |

### App-level states

| Context | Icon |
|---|---|
| 404 | `map-pin-off` |
| Error boundary | `octagon-alert` |
| Maintenance | `wrench` |
| Empty — nothing yet (unprovisioned) | `inbox` |
| Empty — nothing right now (caught up) | `circle-check-big` |
| Empty — search returned nothing | `search-x` |
| Contextual help | `circle-help` |

**The two empty-state icons are deliberately different** (U74) — `inbox` reads as "not set up,"
`circle-check-big` reads as "you're done," and using the same icon for both would undercut the whole point
of distinguishing them in copy.

---

## Accessibility

- Every icon paired with visible text **or** `aria-label` — never bare, except inside a component that
  already names itself via `role` and a label (the promise-state chip, `role="status"`).
- Purely decorative icons (e.g. a `truck` illustrating a dock-type label that already says "Reefer") get
  `aria-hidden="true"` so assistive tech doesn't announce redundant content.
- Icon colour never carries meaning alone — every icon in this inventory that signals state is already
  paired with the label/border/colour redundancy `color.md` establishes for that state.
