# Carrier portal — Stitch prompts

> Paste-ready prompts for [Stitch](https://stitch.withgoogle.com). One block per screen/state, in
> `screens.md` order. **These are a translation of the finished spec, not new design.** Every value below
> traces to `../00-foundations/` or to this folder's own files; nothing here is invented. If a value in a
> prompt disagrees with a foundations file, the foundations file wins and the prompt is the bug.
>
> **Sign-in is not in this file** — it is a shared surface specified once in
> `../00-foundations/auth-and-scoping.md` and already has its own prompt.
>
> Density is `comfortable` throughout, confirmed against `spacing-and-layout.md`'s density table
> ("Carrier, admin, driver chat"): 44px rows · 12/16px cell padding · 16px card padding · 12px stack gap ·
> 44px minimum tap target · 40px button height · 24px content padding.
>
> **The one constraint every prompt restates:** `auth-and-scoping.md`'s inference-risk rule. A carrier sees
> its own numbers and nothing that implies anyone else's — no benchmark, no ranking, no aggregate, **not
> even a count** from which another carrier's volume could be inferred (U28, M15). This is the single
> easiest thing for a generative tool to add "helpfully," so it is excluded explicitly, every time.

**Contents**

1. [Dashboard — default loaded state](#1--dashboard--default-loaded-state)
2. [Fleet overview strip — three stat tiles and the on-time sparkline](#2--fleet-overview-strip--three-stat-tiles-and-the-on-time-sparkline)
3. [Your shipments — table, status filter, filtered-empty](#3--your-shipments--table-status-filter-filtered-empty)
4. [Open exceptions — summary rows](#4--open-exceptions--summary-rows)
5. [Dashboard — loading (per-section skeletons)](#5--dashboard--loading-per-section-skeletons)
6. [Dashboard — empty states (caught-up vs nothing-yet)](#6--dashboard--empty-states-caught-up-vs-nothing-yet)
7. [Dashboard — load failure and degradation](#7--dashboard--load-failure-and-degradation)
8. [Shipment detail — read-only](#8--shipment-detail--read-only)
9. [Shipment detail — out-of-scope refusal](#9--shipment-detail--out-of-scope-refusal)

---

## 1 · Dashboard — default loaded state

*`screens.md` §1. The whole surface: one sectioned page, cross-facility, entirely read-only.*

---
**Copy-paste into Stitch — SetuHaul Dock Command · Carrier Portal Dashboard (comprehensive)**

**Product context**: SetuHaul Dock Command is a B2B internal operations tool for a logistics company — not
a consumer app, no marketing site, no brand storytelling. This screen is the **carrier portal**: a haulage
company's dispatcher or fleet manager checking on their own trucks across every warehouse they deliver to.
It is **entirely read-only** — there is no action on this page that changes anything in the system. Treat
it as an "operator tool" aesthetic: calm, dense-capable, trustworthy — closer to a cockpit instrument than
a SaaS dashboard.

**Typography**: `Inter` for all UI text — weights 400/500/600/700 only, no others loaded. `JetBrains Mono`
weights 400/500 for machine-generated values only: shipment IDs, dock codes, times, dates. Inter is chosen
for legibility at 12–14px; do not substitute a "more distinctive" font, this is a locked functional choice.
Exact scale:
- Page/section headings: 12px / line-height 1.33 / weight 700 / letter-spacing 0.04em / UPPERCASE
- Body and all table cells: 14px / 1.5 / 400
- Stat tile value: 16px / 1.5 / 600, `JetBrains Mono`
- Secondary text: 13px / 1.4 / 400
- Timestamps and metadata: 11px / 1.3 / 500 — **11px is a hard floor, nothing smaller**
- Column headers: 12px / 1.33 / 600 / 0.04em / UPPERCASE
- `font-variant-numeric: tabular-nums` on every number in a column

**Color** (define both a light and a dark variant):
- Page background: `#F8FAFC` light, `#020617` dark
- Card/table/top-bar background: `#FFFFFF` light, `#0F172A` dark
- Row hover background: `#F1F5F9` light, `#1E293B` dark
- Primary text: `#0F172A` light, `#F8FAFC` dark
- Secondary text: `#475569` light, `#CBD5E1` dark
- Tertiary text (labels, timestamps): `#64748B` light, `#94A3B8` dark
- Hairline borders: `#E2E8F0` light, `#1E293B` dark
- Control borders: `#CBD5E1` light, `#334155` dark
- The only interactive accent on the page: `#2563EB` light, `#3B82F6` dark

**Status chips — four states, and they must never be confusable.** Each carries four redundant channels
(hue, icon, border style, uppercase label). Never abbreviate a label; if it does not fit, the container is
too small. 12px / 600 / 0.04em / UPPERCASE, 2px 4px padding, 4px radius, 14px Lucide icon:
- `SHOWN` — icon `list`, **1px solid** `#CBD5E1`, bg `#F8FAFC`, text `#334155` (dark: border `#475569`, bg `#1E293B`, text `#E2E8F0`). Deliberately uncoloured — nothing is reserved.
- `HELD` — icon `timer`, **2px dashed** `#F59E0B`, bg `#FFFBEB`, text `#B45309` (dark: bg `#78350F` at 25% opacity, text `#FBBF24`). Dashed = temporary.
- `PENDING CONFIRMATION` — icon `clock-fade`, **2px solid** `#3B82F6`, bg `#EFF6FF`, text `#2563EB` (dark: bg `#1E3A8A` at 25%, text `#60A5FA`)
- `CONFIRMED` — icon `circle-check`, **2px solid** `#059669`, bg `#ECFDF5`, text `#047857` (dark: border `#10B981`, bg `#064E3B` at 25%, text `#34D399`)

**Layout** — 12-column grid, 16px gutters, target viewport 1280×800, responsive down to 768px:
- **Top bar, 56px tall**, background `#FFFFFF`, 1px bottom border `#E2E8F0`, 20px horizontal padding.
  Left: the carrier's own company name, 16px / 700 (`Rajasthan Roadlines`) — this is the account context,
  and it occupies the slot where other SetuHaul consoles put a facility switcher. Right, 16px apart:
  `bell` (notifications), `circle-help` (help), then a 32px circular avatar, `#2563EB` fill, white
  initials at 12px / 700.
- **Icon rail, 56px fixed width**, full height, background `#FFFFFF`, 1px right border `#E2E8F0`, 16px top
  padding, 20px gap. Exactly two 24px Lucide destinations: `layout-dashboard` (active, `#2563EB`) and
  `circle-user`. The active item is marked by a 2px inner accent bar, **never a background fill**. The
  rail's outer edge is a plain 1px border — no coloured stripe, because a carrier is not scoped to any one
  facility.
- **Content region**, 24px padding, sections stacked with 20px between them.

**Section order and content**:
1. **Three stat tiles** in a row, 16px gap, equal width. Card: `#FFFFFF`, 1px `#E2E8F0`, 6px radius, 16px
   padding. Each has an uppercase 12px tertiary label above a 16px mono value. Tile 1 "Active shipments /
   18". Tile 2 "Open exceptions / 3". Tile 3 "On-time (30d) / 91%" plus a small `▲2%` delta in `#047857`
   and a 24px-tall inline sparkline.
2. **A single line beneath the tiles**, 11px `#64748B`: `Last updated 2 minutes ago` followed by a
   `↻ Refresh` text button in `#2563EB` / 600. This is a **manual** refresh model — there is no live
   updating anywhere on this page and no auto-refresh.
3. **`YOUR SHIPMENTS`** section heading (12px / 700 / uppercase / `#64748B`) with a `Filter: all statuses ▾`
   control right-aligned on the same line. Beneath it a table: columns *Shipment · Driver · Facility · Dock
   · Status · (chevron)*. Rows are 44px tall, 12px vertical / 16px horizontal cell padding, 1px `#E2E8F0`
   separators, sticky header. Shipment IDs, dock codes and facility names in `JetBrains Mono`. Every row
   ends with a right-aligned `chevron-right` in `#64748B`.
   - `SHP1015 · Ravi K. · Jaipur · D5 · [PENDING CONFIRMATION chip]`
   - `SHP1009 · Amit S. · Gurugram · D2 · [CONFIRMED chip]`
   - `SHP1013 · Neha P. · Kota · — · [alert-triangle 14px] Exception open` in `#B45309` / 12px / 600, with
     **no border and no filled background** (see exclusions)
4. **`OPEN EXCEPTIONS`** section heading, then one full-width row per exception: 1px `#E2E8F0` border, 6px
   radius, 12px/16px padding, 14px text, trailing `chevron-right`.
   `SHP1013 · Neha P. · No feasible slot — escalated 09:12`

**Interaction — this is where read-only is enforced visually.** Only three things on this page are
interactive: a shipment row, an exception row, and the filter control. Those three get a hover background
(`#F1F5F9`, 120ms), a pointer cursor, and a focus ring. **Everything else — every value, every label, every
number — has zero interactive affordance: no hover state, no accent colour, no cursor change.** A read-only
value that looks clickable and does nothing reads as broken, not as scoped.

**Focus ring**: 2px solid `#2563EB` with a 2px offset in the surface colour (a two-ring treatment), never a
soft glow.

**Elevation**: cards and the table sit at elevation tier 1 ("Raised") — `#FFFFFF` fill, a barely-visible
`0 1px 2px rgba(15,23,42,0.06)` shadow, 1px subtle border. In dark mode there is **no shadow at all**;
separation comes from the `#020617 → #0F172A` lightness step plus the border. The shadow language is
deliberately restrained throughout this product.

**Radius**: 8px on large cards, 6px on table containers/inputs/buttons/exception rows, 4px on chips.

**Spacing**: base unit 4px, every value a multiple. 8px and 16px do most of the work; 20–24px separates
sections.

**Motion**: transitions use 120ms for hover/focus and 200ms for anything larger, both with ease-out
`cubic-bezier(0.16, 1, 0.3, 1)`. Never bouncy, never a spring or elastic overshoot. **No looping or
ambient animation anywhere.** No hover effect that moves an element — colour and border only, never a lift
or a scale.

**Explicitly exclude**:
- **Any comparative or cross-carrier framing whatsoever.** No leaderboard, no "you're #2 of 4", no
  "industry average", no "compared to other carriers at this facility", no percentile, no rank badge, no
  benchmark line on the sparkline — **and not even a count** of anything that isn't this carrier's own
  (e.g. never "3 carriers are booked at Jaipur today"). Aggregates leak individual facts; this is a hard
  product rule, not a preference.
- **No facility switcher, no facility filter, no facility tabs.** A carrier's fleet spans whatever
  warehouses it delivers to and is always shown whole. Facility is a value in a row, never a scope control.
- **No coloured facility accent** anywhere — no per-facility dot, badge, chip or row tint.
- **No action buttons of any kind**: no Confirm, Reject, Reschedule, Cancel, Counter-offer, Book, Contact
  driver, Export, or bulk-select checkboxes. Nothing on this page mutates anything.
- **The exception marker must not be a bordered or filled chip.** An amber pill with a border is visually a
  `HELD` promise chip, and confusing "this shipment has an open exception" with "a dock slot is held for
  90 seconds" is exactly the misread the four-state chip system exists to prevent.
- No live-updating counters, no "3 new" badges, no websocket/real-time indicator, no auto-refresh spinner.
- No tabs, no sidebar filters panel, no date-range picker (the 30-day window is fixed by decision).
- No illustrations, no marketing copy, no hero section, no gradients, no glassmorphism, no blur, no
  translucency, no drop-shadow larger than the token above.
- No emoji. Icons are Lucide, 2px stroke, at 14 / 16 / 20 / 24px only.

**Dark mode is a designed parity variant, not an automatic inversion** — light is the shipped default.
---

---

## 2 · Fleet overview strip — three stat tiles and the on-time sparkline

*`components.md` (surface) §1, `../00-foundations/components.md` §14 (stat tile, U66), U115 (30-day
window). The sparkline's own form and colour follow the `dataviz` skill, which §14 explicitly defers to.*

---
**Copy-paste into Stitch — SetuHaul Dock Command · Carrier fleet overview strip (component detail)**

**What to generate**: a single horizontal strip of **three stat tiles**, rendered on the carrier
dashboard's content background at 1120px content width. Not a full page — this is a component sheet for
one section, shown in light and dark.

**Product context**: B2B logistics operations tool, read-only carrier view. Every number shown is this
carrier's own. Operator-tool aesthetic — calm, precise, instrument-like.

**Typography**: `Inter` 400/500/600/700; `JetBrains Mono` 400/500 for the values.
- Tile label: 12px / 1.33 / 600 / letter-spacing 0.04em / UPPERCASE / `#64748B`
- Tile value: 16px / 1.5 / 600, `JetBrains Mono`, `font-variant-numeric: tabular-nums`, `#0F172A`
- Delta: 12px / 600, sits inline after the label
- No other type sizes in this component.

**Color**:
- Tile surface `#FFFFFF` light / `#0F172A` dark; 1px border `#E2E8F0` light / `#1E293B` dark
- Label `#64748B` light / `#94A3B8` dark; value `#0F172A` light / `#F8FAFC` dark
- Positive delta `#047857` light / `#34D399` dark; negative delta `#B91C1C` light / `#F87171` dark
- **The delta colours the arrow glyph and its number only — it never tints the tile, its border, or its
  background.** A tile that turns green is a tile shouting; the arrow is sufficient.

**Layout**: three equal-width tiles, CSS grid, 16px gap. Tile padding 16px (the `comfortable` density
value). Label on the first line, value on the second, 4px between them.

**Tile 1** — label `ACTIVE SHIPMENTS`, value `18`. No delta, no sparkline.
**Tile 2** — label `OPEN EXCEPTIONS`, value `3`. No delta, no sparkline.
**Tile 3** — label `ON-TIME (30D)` followed by a `▲ 2%` delta; value `91%`; then the sparkline.

Tiles 1 and 2 deliberately have no trend line: they are point-in-time facts with no meaningful shape at a
glance, and forcing a sparkline onto every tile is decoration, not information.

**The sparkline, specified exactly**:
- **Form**: a single-series line, 30 daily points (the rolling 30-day window), left-to-right, most recent
  at the right edge. No second series, ever.
- **Stroke**: 2px, round join and round cap, colour `#64748B` light / `#94A3B8` dark — the same tertiary
  ink as the label. Contrast against the tile surface is 4.8:1 light and 6.7:1 dark, so it clears the 3:1
  requirement for a non-text UI mark comfortably.
- **Why not a coloured line**: hue in this product is rationed to two jobs — promise state and danger. A
  green trend line 40px above a green `CONFIRMED` chip invites a misread, and status colours are reserved.
  The line carries *shape*; the headline `91%` carries the value.
- **End marker**: one filled dot at the final point, radius 4px (8px diameter), same colour as the stroke,
  with a 2px ring in the tile's own surface colour so it stays legible where it sits on the line. This is
  the only labelled/emphasised point. Give it `#0F172A` light / `#F8FAFC` dark fill — emphasis by
  lightness value, not by hue.
- **Optional area wash**: if a fill is used, it is the stroke colour at **10% opacity** only — a wash,
  never a saturated block.
- **Size**: fills the tile's content box, minimum 96px wide, **24px tall**, 8px above it. Draw it at its
  rendered pixel size — do **not** stretch an SVG viewBox non-uniformly, because that makes a "2px" stroke
  render thicker in one axis than the other.

**Motion**: none. The sparkline does not draw in, the number does not count up, nothing pulses.
On **manual refresh**, do not flash a skeleton over an already-rendered tile — hold the previous render at
`opacity: 0.6` while the new data loads (and only once the request has been in flight for 1 second; under
1 second show nothing at all). The `refresh-cw` icon is the only icon in this product permitted to spin.

**Elevation**: tier 1 — `0 1px 2px rgba(15,23,42,0.06)` in light, no shadow in dark.
**Radius**: 6px. **Spacing**: 4px base unit.

**Explicitly exclude**:
- **No comparison of any kind against another carrier.** No benchmark line, no shaded "industry range"
  band, no "vs. average", no percentile marker, no rank, no target line sourced from anyone else's
  performance. The delta compares this carrier's current 30 days against **its own** prior 30 days, and
  that is the only comparison permitted on this surface.
- No axis, no gridlines, no tick labels, no legend (a single series needs none — the tile label names it),
  no value labels on individual points, no tooltip that is the only way to read a number.
- No second sparkline in any tile, and never two series in one sparkline.
- No dual-axis anything. No bar chart, donut, pie, gauge, radial progress or speedometer — this is a stat
  tile, and the number is the chart.
- No coloured tile backgrounds, no coloured left borders, no "traffic light" tile states.
- No dashed lines (dashing in this product means "temporary/held" and must not appear in a chart).
- No 4th tile, no "view full analytics" link, no drill-down — full KPI analytics does not exist here.
---

---

## 3 · Your shipments — table, status filter, filtered-empty

*`screens.md` §1, `components.md` (surface) §2, `flows-and-states.md` Flow 2 and Flow 6,
`edge-cases.md` #3 and #6.*

---
**Copy-paste into Stitch — SetuHaul Dock Command · Carrier shipments table (component detail, 3 states)**

**What to generate**: the "Your shipments" section of a read-only carrier dashboard, at 1120px content
width, in **three states** side by side or stacked: (a) default, (b) filter control open, (c) filtered with
no matches. Light and dark variants of each.

**Product context**: B2B logistics operations tool. A haulage dispatcher scanning their own trucks across
several warehouses. Read-only: a row can be *opened* for detail, never *acted on*.

**Typography**: `Inter` 400/500/600/700, `JetBrains Mono` 400/500.
- Section heading `YOUR SHIPMENTS`: 12px / 1.33 / 700 / 0.04em / UPPERCASE / `#64748B`
- Column headers: 12px / 1.33 / 600 / 0.04em / UPPERCASE / `#64748B`
- Cells: 14px / 1.5 / 400. Shipment ID at weight **600** (it is the row's primary identifier); everything
  else 400.
- Shipment IDs, facility names and dock codes in `JetBrains Mono`; driver names in `Inter`.
- Hierarchy inside a row comes from **weight, colour, and font family only — never size.** Every cell is
  14px.

**Color**: surface `#FFFFFF` / `#0F172A`; row separators 1px `#E2E8F0` / `#1E293B`; primary text `#0F172A`
/ `#F8FAFC`; secondary `#475569` / `#CBD5E1`; header/label ink `#64748B` / `#94A3B8`; row hover background
`#F1F5F9` / `#1E293B`; focus ring `#2563EB` / `#60A5FA`.

**Rows**: 44px tall, 12px vertical / 16px horizontal cell padding, sticky header, **fixed column widths
(never auto-width)**. Columns: *Shipment · Driver · Facility · Dock · Status · chevron*.

**Status cell** — a single flex row, 8px gap, containing:
- the promise-state chip (see the four-state spec in prompt 1), **and**
- where the shipment also has an open exception, a marker: 14px Lucide `alert-triangle` + the words
  `Exception open`, 12px / 600, `#B45309` light / `#FBBF24` dark, **with no border and no background fill**.
Both can appear together on the same row — a shipment that is `PENDING CONFIRMATION` *and* has an open
exception is normal, not a bug. Where no dock time has ever been offered, the dock cell reads `—` and the
exception marker stands alone with no chip.

**Truncation** (long values are expected here — this is the densest text-per-row layout on the surface):
- Driver and facility names **end-truncate** — identity is at the start: `Rajasthan Roadlines Priv…`
- Shipment IDs and references **mid-truncate** — the distinguishing suffix must survive:
  `SH-2026-0819-00…17`, never `SH-2026-08…`
- An ellipsis stands for 3 or more removed characters; at least 4 characters always remain.
- Every truncated value carries a native `title` tooltip with the full string, reachable on **focus**, not
  hover-only.
- **Never truncate**: the section heading, a promise-state chip's label, or any error message.

**State (a) — default**: 3 rows, "Filter: all statuses ▾" control right-aligned on the heading line, 12px
text, 1px `#CBD5E1` border, 4px radius, 4px/12px padding.

**State (b) — filter open**: a popover beneath the control, `#FFFFFF` / `#1E293B`, 1px `#E2E8F0` border,
6px radius, `0 4px 12px rgba(15,23,42,0.10)` shadow, 6 single-select options at 40px each:
`All statuses` · `Shown` · `Held` · `Pending confirmation` · `Confirmed` · `Has open exception`.
Selecting one filters the table only — **the three stat tiles above do not change**, because they describe
the whole fleet regardless of what the list is currently filtered to. Focus stays on the filter control
after selection; it does not jump into the results.

**State (c) — filtered, no matches**: the table body is replaced by a centred block, 48px vertical padding:
a 32px Lucide `search-x` in `#64748B`, then `No shipments match this filter.` at 14px `#0F172A`, then a
single `Clear filter` button — 40px tall, transparent background, 1px `#CBD5E1` border, 6px radius, 14px
text `#0F172A`. The section heading and the filter control both stay visible.

**Interaction**: the whole row is one navigation target that opens a read-only detail screen. Hover:
background `#F1F5F9`, 120ms ease-out `cubic-bezier(0.16, 1, 0.3, 1)`, no lift and no scale. Focus: 2px
`#2563EB` ring with a 2px surface-coloured offset ring. Keyboard operation is plain `Tab` / `Shift+Tab` /
`Enter` — there are no single-key shortcuts on this surface.

**Radius** 6px on the table container and popover, 4px on chips. **Spacing** 4px base unit.
**Elevation**: table at tier 1 (`0 1px 2px rgba(15,23,42,0.06)`, no shadow in dark); popover at tier 3
(`0 4px 12px rgba(15,23,42,0.10)`).

**Explicitly exclude**:
- **No cross-carrier framing.** No column, tooltip, or footer showing anyone else's shipments, no "12
  other trucks at this facility today", no facility utilisation figure, no queue-position-among-carriers,
  no aggregate that another carrier's volume could be read out of.
- **No row-level actions.** No checkbox column, no bulk-select bar, no overflow "⋯" menu, no inline
  Reschedule / Cancel / Contact / Message driver, no swipe actions, no drag to reorder.
- **No sortable column headers.** Sort is fixed at most-recently-updated first; a clickable header would
  promise an interaction this surface does not have.
- **No live updates**: no arriving rows, no "new" badges, no flashing, no row-count that ticks.
- No pagination controls if the list is short; no infinite-scroll spinner.
- No coloured row backgrounds, no priority stripes, no facility colour-coding, no zebra striping.
- The exception marker is **not** a bordered amber pill — that shape is reserved for the `HELD` promise
  chip and must not be imitated.
- No emoji; Lucide icons only, 2px stroke.
---

---

## 4 · Open exceptions — summary rows

*`screens.md` §1, `components.md` (surface) §3. The boundary this prompt protects: a carrier sees **that**
something is being handled, never the internal apparatus handling it.*

---
**Copy-paste into Stitch — SetuHaul Dock Command · Carrier open-exceptions section (component detail)**

**What to generate**: the "Open exceptions" section of a read-only carrier dashboard, at 1120px content
width, showing two rows plus the caught-up empty variant. Light and dark.

**Product context**: B2B logistics operations tool. An exception is a delivery problem that a human
operations coordinator inside the warehouse company is already working on. The carrier is being kept
informed — they are not being asked to do anything, and they are not shown how the work is being done.

**Typography**: `Inter` 400/500/600/700, `JetBrains Mono` 400/500.
- Section heading `OPEN EXCEPTIONS`: 12px / 1.33 / 700 / 0.04em / UPPERCASE / `#64748B`
- Row text: 14px / 1.5 / 400, `#0F172A` light / `#F8FAFC` dark
- Shipment ID: `JetBrains Mono`, weight 600
- Timestamp: `JetBrains Mono`, 14px, inline in the sentence

**Row anatomy** — a single line, read left to right, middot-separated:
`SHP1013 · Neha P. · No feasible slot — escalated 09:12` with a trailing right-aligned `chevron-right`
(16px, `#64748B`). A 16px Lucide reason icon leads the row: `calendar-x` for "no feasible slot",
`timer-off` for an expired pending decision, `shield-alert` for a safety review, `network` for a
dock/facility capacity incident.

**Layout**: full-width row, 1px `#E2E8F0` / `#1E293B` border, 6px radius, 12px vertical / 16px horizontal
padding, minimum 44px tall, 12px between rows.

**Colour**: the row is **neutral** — the reason icon and text use ordinary primary/secondary ink, not a
danger colour. A carrier's open exception is a status, not an alarm, and reserving red for genuine danger
is what keeps red meaningful elsewhere in the product.

**Copy — use these exact strings, do not rewrite them.** Each is a plain-language status clause, never
internal jargon:
- `No feasible slot — escalated 09:12`
- `No planner decision in time — released and escalated 11:57`
- `Awaiting operations review — raised 08:20`

**Empty variant** (no open exceptions): centred block, 48px vertical padding — a 32px Lucide
`circle-check-big` in `#64748B`, then `No open exceptions.` at 14px `#0F172A`. No button, no call to
action. This is the good state and should read as reassuring, not as a blank.

**Interaction**: the whole row is one navigation target and opens the **same** read-only shipment detail
screen a shipment row opens — there is exactly one detail destination on this surface, reached two ways.
Hover `#F1F5F9` at 120ms ease-out; 2px `#2563EB` focus ring with a 2px offset; no lift, no scale.

**Elevation** tier 1, `0 1px 2px rgba(15,23,42,0.06)` light / no shadow dark. **Radius** 6px.
**Spacing** 4px base unit. **Motion** 120ms hover/focus, ease-out `cubic-bezier(0.16, 1, 0.3, 1)`, nothing
ambient, nothing looping.

**Explicitly exclude** — this list is the point of the component:
- **No internal escalation mechanics.** No owner name or avatar, no "assigned to", no SLA countdown or
  "8m remaining", no progress stepper (`OPEN → ACKNOWLEDGED → IN PROGRESS → RESOLVED`), no priority label,
  no internal notes, no activity feed of who did what. The carrier learns *that* it is being handled.
- **No cross-carrier framing.** No "3 carriers affected", no facility-wide incident count, no comparison of
  this carrier's exception rate to anyone else's, no aggregate of any kind.
- **No actions**: no Escalate, Chase, Nudge, Message operations, Add comment, Resolve, Dismiss, or Snooze.
- No red/amber alarm treatment on the row, no pulsing, no badge counter, no unread dot.
- No grouping into an accordion, no "show 4 more", no severity sort control.
- No emoji; Lucide icons only, 2px stroke, 16px in-row.
---

---

## 5 · Dashboard — loading (per-section skeletons)

*`flows-and-states.md` Flow 1. Four calls, four sections resolving independently — never one page-level
spinner.*

---
**Copy-paste into Stitch — SetuHaul Dock Command · Carrier dashboard loading state**

**What to generate**: the carrier dashboard mid-load, with each section in its own skeleton state, at
1280×800. Light and dark. Show a second frame where the stat tiles have resolved but the table has not —
that partial state is the point of this design, not an edge case.

**Product context**: B2B logistics operations tool, read-only carrier dashboard. Four independent data
calls populate this page, and **each section renders the moment its own data arrives.** A carrier with a
fast overview query and a slow fleet query sees the tiles resolve immediately rather than waiting on the
slowest section.

**Typography / colour / spacing / radius**: identical to the loaded dashboard (prompt 1) — `Inter`
400/500/600/700, `JetBrains Mono` 400/500, 4px base unit, 6–8px radii, `#F8FAFC` page / `#FFFFFF` cards
light, `#020617` page / `#0F172A` cards dark.

**The shell never shows a loading state.** The top bar, the icon rail, the carrier's own name, the section
headings and the column headers all render immediately and stay put. Only the data regions are skeletons —
what is loading is data, not the application.

**Skeleton treatment**:
- Blocks are `#E2E8F0` light / `#1E293B` dark, at the **exact dimensions of the real content they replace**
  — 44px skeleton rows for 44px table rows, tile-sized blocks for tiles, 6px radius matching the container.
  A skeleton must never cause a layout jump when it resolves.
- Pulse: opacity oscillating on a 1600ms loop, `cubic-bezier(0.65, 0, 0.35, 1)`. This is the **only**
  looping animation permitted anywhere in this product.
- Under `prefers-reduced-motion: reduce` the shimmer becomes a **static** grey block — same colour, no
  pulse.
- **No centred spinner anywhere.** A spinner followed by content is a layout jump.

**Per-section skeleton shapes**:
- Stat tiles: three tile-shaped blocks, 16px gap. Within each, a 90×12px label block and a 48×16px value
  block. The on-time tile's sparkline slot stays **empty** while loading — it is secondary content and does
  not get its own skeleton.
- "Last updated" line: a 160×11px block.
- Shipments table: the section heading and the uppercase column headers render as real text; below them 5
  skeleton rows at 44px each, each containing block widths that match the real columns (72 / 88 / 140 /
  120 / 130px).
- Open exceptions: 2 skeleton rows at 44px, full width.

**Latency behaviour** — this governs whether anything appears at all:
- Under 1 second in flight: **show nothing.** No skeleton, no spinner. An indicator that flashes for under
  a second is pure distraction.
- 1–3 seconds: the skeletons above.
- Past roughly 3 seconds: the skeleton is joined by a `Retry` affordance rather than pulsing indefinitely.

**Explicitly exclude**:
- No full-page loading overlay, no progress bar across the top, no percentage, no "Loading your fleet…"
  copy, no branded splash, no animated logo.
- No unmounting or greying of the top bar or icon rail.
- No shimmer gradient sweeping across blocks — plain opacity pulse only.
- No skeleton for the sparkline.
- **No comparative or cross-carrier framing** in any placeholder or copy — a skeleton must not hint at
  content this surface would never show.
---

---

## 6 · Dashboard — empty states (caught-up vs nothing-yet)

*`flows-and-states.md` Flow 6, `edge-cases.md` #5, `../00-foundations/components.md` §13 (U74). Same
visual emptiness, two opposite meanings — showing the wrong one makes a working system look broken.*

---
**Copy-paste into Stitch — SetuHaul Dock Command · Carrier dashboard empty states (2 distinct kinds)**

**What to generate**: two separate frames of the same carrier dashboard, at 1280×800, light and dark.
They must be visually and verbally distinguishable at a glance — that distinction is the entire brief.

**Product context**: B2B logistics operations tool, read-only carrier dashboard. An empty screen here means
one of two completely different things, and conflating them is a correctness bug, not a copy nit:
- **Caught up** — an established carrier with a real delivery history that happens to have nothing running
  right now. A good state. Reassuring tone.
- **Nothing yet** — a brand-new carrier account with no history at all. An expected state. Neutral,
  informational tone. Never reassuring, because there is nothing yet to be reassured about.

**Frame A — "Caught up"** (established carrier, currently at zero):
- The three stat tiles **still render**, with real zeroes: `ACTIVE SHIPMENTS / 0`, `OPEN EXCEPTIONS / 0`,
  `ON-TIME (30D) / 94%` with its sparkline intact. **A genuine zero renders as `0`, never as a blank or a
  dash** — a blank cell and a real zero must never look the same.
- Shipments section: centred block, 48px vertical padding — 32px Lucide `circle-check-big` in `#64748B`,
  then `No active shipments right now.` at 14px `#0F172A`. **No button.**
- Exceptions section: same treatment, copy `No open exceptions.`
- The `Last updated 2 minutes ago ↻ Refresh` line stays exactly as it is in the loaded state.

**Frame B — "Nothing yet"** (new carrier, no history at all):
- Stat tiles render with `0`, `0`, and the on-time tile shows `—` with **no sparkline and no delta** —
  there is no history to compute a percentage from, and an unknown must render as an explicit `—`, never
  as `0%` and never as a blank.
- Shipments section: centred block — 32px Lucide `inbox` in `#64748B`, then
  `No shipments on record yet` at 16px / 600 `#0F172A`, then on a second line at 13px `#475569`:
  `New deliveries will appear here automatically once they're scheduled.` **No button** — there is no setup
  step a carrier user can take.
- Exceptions section: hidden entirely for this state, or the same `inbox` treatment with
  `Nothing here yet.` — pick one and apply it consistently.

**The two icons must differ**: `circle-check-big` reads "you're done"; `inbox` reads "not started". Using
one icon for both would undercut the whole distinction.

**Typography**: `Inter` 400/500/600/700. Empty-state heading 16px / 1.5 / 600; supporting line 13px / 1.4 /
400 `#475569` / `#CBD5E1`. Icons 32px, `#64748B` / `#94A3B8`, Lucide, 2px stroke.

**Colour / spacing / radius / elevation**: unchanged from the loaded dashboard — `#F8FAFC` page,
`#FFFFFF` cards, 1px `#E2E8F0` borders, 6–8px radii, `0 1px 2px rgba(15,23,42,0.06)` shadow in light and
none in dark, 4px base unit, 24px content padding.

**Motion**: none. Empty states do not animate in.

**Explicitly exclude**:
- **No comparative or cross-carrier framing** — never "quieter than other carriers this week", never a
  facility-wide activity figure to fill the space, never an aggregate of any kind. An empty screen is the
  most tempting place to add "helpful context", and it is exactly where this rule matters most.
- No illustration, no mascot, no spot art, no confetti, no celebratory language, no exclamation marks.
- No "Book a slot" / "Create shipment" / "Add a driver" / "Invite a colleague" call to action — this
  surface is read-only and a carrier cannot create anything here.
- No upsell, no onboarding checklist, no product tour, no "Get started in 3 steps".
- No dashes or blanks where a real zero exists, and no zeros where a value is genuinely unknown — those are
  three different states (`0`, `—`, and absent) and must look different.
- No emoji.
---

---

## 7 · Dashboard — load failure and degradation

*`../00-foundations/components.md` §13, `auth-and-scoping.md`'s degradation policy (U84),
`edge-cases.md` #4. Primary content fails loudly and stays reachable; secondary content simply disappears.*

---
**Copy-paste into Stitch — SetuHaul Dock Command · Carrier dashboard failure and degraded states**

**What to generate**: the carrier dashboard in three failure variants at 1280×800, light and dark:
(a) the shipments table failed to load, (b) the on-time trend data failed to load, (c) the whole page's
data is stale after a failed refresh.

**Product context**: B2B logistics operations tool, read-only carrier dashboard. Regions of this page fail
differently on purpose, according to whether the screen is still usable without them:
- **Primary** — the shipments table and the exceptions list. Without these the screen cannot do its job, so
  a failure is stated plainly with a route out.
- **Secondary** — the on-time sparkline. It enriches the page but nothing depends on it, so on failure it
  **simply is not there**: no error, no placeholder, no retry button competing for attention with the
  content that actually matters.

**Variant (a) — shipments table failed**:
The section heading and filter control stay. The table body is replaced by a centred block, 48px vertical
padding: 32px Lucide `octagon-alert` in `#64748B`, then at 14px `#0F172A`:
`Couldn't load your shipments — usually a connection problem.`
then a `Try again` button: 40px tall, transparent, 1px `#CBD5E1` border, 6px radius, 14px `#0F172A` text.
The stat tiles and the exceptions section above and below are **unaffected and fully rendered** — each
section has its own error boundary, and one failing region must not take the others down.

**Variant (b) — trend data failed**:
The on-time tile renders normally with its label, its `91%` value and its delta. **The sparkline is simply
absent.** No empty box, no dashed placeholder, no "chart unavailable", no retry icon, no reduced-opacity
ghost. The tile shrinks to the height of the other two. Nothing on the page mentions the failure.

**Variant (c) — refresh failed, data is stale**:
A single page-level notice above the stat tiles, full content width, 12px/16px padding, 6px radius:
background `#FFFBEB` light / `#78350F` at 25% dark, 1px border `#F59E0B`, text `#B45309` light / `#FBBF24`
dark, with a 16px Lucide `alert-triangle`. Copy:
`This page couldn't refresh. You're seeing data from 09:41.` followed by a `Try again` text button.
The stale sections below stay fully rendered and legible — **do not** grey them out, do not overlay them,
do not blur them. **One notice, not five** — a page reporting a separate warning per region has stopped
being informative.

**Colour discipline**: a degradation notice uses **warning** tokens (`#FFFBEB` / `#F59E0B` / `#B45309`),
never danger red. A page that looks like it is on fire when the real problem is "these numbers are 40
seconds old" trains people to stop trusting red when it actually matters.

**Typography**: `Inter` 400/500/600/700. Error headline 14px / 1.5 / 400; notice text 14px; button label
14px. Icons Lucide, 2px stroke, 16px inline and 32px for the section-level error.

**Spacing / radius / elevation / motion**: unchanged from the loaded dashboard — 4px base unit, 6px radius
on the notice and buttons, tier-1 elevation on cards, 200ms ease-out `cubic-bezier(0.16, 1, 0.3, 1)` on
the notice appearing, nothing looping.

**Explicitly exclude**:
- **No comparative or cross-carrier framing** in any error, notice, or fallback copy.
- No full-page error screen for a single failed section — errors are scoped per region.
- No raw error codes, stack traces, request IDs or HTTP status numbers shown to the user.
- No "something went wrong" with no cause and no next step. Every state here names a cause and an action.
- **No retry button, error text, placeholder box or ghosted chart for the sparkline** — secondary content
  disappears silently, and giving it an error state would put it in competition with the fleet list.
- No red on a staleness warning. No toast for a stale-data condition (it is a persistent condition, not an
  event). No modal blocking the page.
- No auto-retry loop with a visible countdown.
---

---

## 8 · Shipment detail — read-only

*`screens.md` §2, `components.md` (surface) §4, `edge-cases.md` #2. The same promise-state chip a planner
sees, in its read-only consumption — with no affordance rendered beside it.*

---
**Copy-paste into Stitch — SetuHaul Dock Command · Carrier shipment detail (read-only, 4 state variants)**

**What to generate**: a single read-only shipment detail screen, 640px content column on a 1280px page, in
**four variants** — one per promise state. Light and dark.

**Product context**: B2B logistics operations tool. A carrier's dispatcher has opened one of their own
trucks to see where its warehouse slot stands. They cannot change anything from here; only a warehouse
planner can. The screen exists to answer "what is true right now, and what happens next".

**Typography**: `Inter` 400/500/600/700, `JetBrains Mono` 400/500.
- Identity line (`SHP1015 · Ravi K.`): 20px / 1.4 / 600, ID in `JetBrains Mono`
- State chip label: 12px / 1.33 / 600 / 0.04em / UPPERCASE
- Deadline line: 13px / 1.4 / 400 `#475569`
- The dock-and-time line: 14px, `JetBrains Mono`, `#475569`
- `HISTORY` heading: 12px / 700 / 0.04em / UPPERCASE / `#64748B`
- History rows: 13px / 1.4; the time in `JetBrains Mono` in a fixed 56px left column, `#64748B`

**Layout**: a back affordance at the top (`← Dashboard`, 14px `#64748B`, 16px Lucide `arrow-left`), then a
single card — `#FFFFFF` / `#0F172A`, 1px `#E2E8F0` / `#1E293B`, 8px radius, 20px padding,
`0 1px 2px rgba(15,23,42,0.06)` shadow in light and none in dark. Inside, in order:
identity line → promise-state chip → deadline line (only where one exists) → dock/date/time line →
`HISTORY` heading → history rows separated by 1px `#E2E8F0` hairlines, 8px vertical padding each.

**The dock-and-time line — this format is mandatory, not stylistic**:
`Jaipur · D5 · Tue 20 Aug · 13:00–14:15`
- **An operational time never appears without its dock and its date.** Option sets in this product can span
  two days, and a bare time is a wrong-day arrival waiting to happen.
- 24-hour clock always (`13:00`, never `1:00 PM`). Dates as `Tue 20 Aug`, weekday included.
- Time ranges use an **en dash** (`13:00–14:15`), never a hyphen.
- Middot separators with a space either side; they group the four facts as one unit.
- Times are always the **facility's** local time, never converted to the viewer's timezone.

**The four variants** (chip specs as in prompt 1 — four redundant channels, never abbreviate a label):
- **`SHOWN`** — `list` icon, 1px solid `#CBD5E1`, bg `#F8FAFC`, text `#334155`. No deadline line. Supporting
  line at 13px `#475569`: `Nothing is held yet.`
- **`HELD`** — `timer` icon, **2px dashed** `#F59E0B`, bg `#FFFBEB`, text `#B45309`. Countdown beside the
  label in `JetBrains Mono` with `tabular-nums` so digits do not shift width: `1:24`. Supporting line:
  `Held for the driver until 11:42:30. This is not a booking yet.`
- **`PENDING CONFIRMATION`** — `clock-fade` icon, 2px solid `#3B82F6`, bg `#EFF6FF`, text `#2563EB`.
  Deadline line: `Decision by 11:57.` Supporting line: `The warehouse hasn't confirmed this yet.`
- **`CONFIRMED`** — `circle-check` icon, 2px solid `#059669`, bg `#ECFDF5`, text `#047857`. Adds a
  reference line: `Reference APT-1042` in `JetBrains Mono`. **Only this state may use finality language.**

**History**: a plain chronological list of the shipment's own recorded events, oldest first, time then
event:
```
09:41   Reported delay
09:52   Option offered
09:53   Held, then requested
11:12   Confirmed by warehouse
```

**Motion**: none on this screen. No countdown animation beyond the digit itself changing, and the digit
change is instant — a tick must read as a discrete step, never a smooth sweep. Nothing pulses, nothing
loops, nothing fades in.

**Read-only enforcement**: nothing on this screen has a hover state, a pointer cursor, or an accent colour
except the single `← Dashboard` back link. The chip is a status display here, not a control.

**Spacing** 4px base unit, 12px between stacked elements, 16px card padding at this density.
**Radius** 8px card, 4px chip.

**Explicitly exclude**:
- **No planner affordances.** No Confirm, Reject, Counter-offer, Hold-for-information, Escalate,
  Reschedule, Cancel, or Approve — not even greyed out. This screen reuses the planner's chip component,
  not the planner's context.
- **No internal notes from anyone else.** A planner's rejection note and an operations coordinator's
  internal remark are never-shown fields; only outcomes and driver-visible messages appear in the history.
- **No cross-carrier framing.** Never "you were 2nd in the queue for this dock", never "3 trucks competed
  for this slot", never a facility utilisation figure, never any explanation of *why* a contested interval
  went elsewhere — that reveals another carrier's operations.
- **No `CONFIRMED`-style success treatment on `HELD` or `PENDING`.** No green, no checkmark, no "booked",
  "reserved", "secured", "your slot", or "successfully" anywhere below `CONFIRMED`. A `HELD` state that
  reads as booked is a broken promise.
- No map, no live truck tracking, no ETA-vs-actual chart, no driver photo, no chat transcript, no call or
  message button, no document upload, no proof-of-delivery panel.
- No countdown ring, radial timer, progress bar or animated clock — the countdown is a mono numeral.
- No exclamation marks, no celebratory copy, no emoji.
---

---

## 9 · Shipment detail — out-of-scope refusal

*`edge-cases.md` #1, `flows-and-states.md` Flow 3 step 3, `auth-and-scoping.md`'s scope-failure section.
The message is about the viewer's access, never about the shipment's existence.*

---
**Copy-paste into Stitch — SetuHaul Dock Command · Carrier shipment detail, out-of-scope**

**What to generate**: the full-content-region state shown when a carrier opens a shipment link that is not
part of their own fleet — a stale bookmark, a forwarded link, or a load reassigned to a different carrier
upstream. 1280×800, light and dark. The top bar and icon rail stay; only the content region is replaced.

**Product context**: B2B logistics operations tool. The server refused this request; the client never
received the shipment's data at all. The screen's entire job is to say what happened and offer a route
back, **without disclosing whether that shipment exists anywhere else in the system.**

**Layout**: centred block in the content region, roughly 400px wide, vertically centred with 64px of
breathing room:
- 32px Lucide `shield-off` icon in `#64748B` / `#94A3B8`
- 24px gap
- Headline: `This shipment isn't in your fleet` — 16px / 1.5 / 600, `#0F172A` / `#F8FAFC`
- 8px gap
- Supporting line: `Check the link, or go back to your dashboard.` — 13px / 1.4 / 400, `#475569` /
  `#CBD5E1`
- 24px gap
- One button, `Back to dashboard`: 40px tall, transparent background, 1px `#CBD5E1` / `#334155` border, 6px
  radius, 14px `#0F172A` / `#F8FAFC` label, minimum 80px wide. Focus ring 2px `#2563EB` with a 2px
  surface-coloured offset ring.

**Copy is exact and must not be rewritten.** In particular: it says the shipment *isn't in your fleet* — it
does **not** say the shipment does not exist, was not found, was deleted, or belongs to someone else. That
wording covers both the "genuinely does not exist" and the "exists but is out of scope" cases with the same
sentence, deliberately, so the screen cannot be used to probe for which shipments are real.

**Typography**: `Inter` 400/500/600/700 only. No mono on this screen — **do not echo the requested shipment
ID back to the user**; repeating it invites the reading that the system looked it up and found something.

**Colour / spacing / radius / elevation**: `#F8FAFC` page / `#020617` dark; the block sits directly on the
page background with **no card and no shadow** — this is a full-region state, not a component in a
container. 4px base unit. 6px button radius.

**Motion**: none. The state appears instantly on navigation; route transitions in this product are not
animated.

**Announcement**: this is an unsuccessful action and a route change — the headline is the focus target on
arrival and is announced assertively to assistive technology.

**Explicitly exclude**:
- **Never confirm or deny the shipment's existence.** No "not found", no "404", no "this belongs to another
  carrier", no "contact the owner", no "request access", no shipment ID echoed back.
- **No cross-carrier framing of any kind** — nothing that names, counts, or implies another carrier.
- No generic 404 illustration, no "lost in space" art, no large `404` numeral, no mascot.
- No bare error code, no HTTP status, no raw API message, no support ticket form.
- No search box offering to look the shipment up another way — that is the same disclosure through a
  different door.
- No "sign in with a different account" prompt.
- No emoji, no exclamation marks.
---

---

## Notes on values these prompts had to pin down

Recorded here rather than inside a prompt block, because they are **flags for the spec owner**, not
instructions for Stitch. Each is a place where the surface spec did not fully determine a value the prompts
needed.

| # | Gap | What the prompts do, and why |
|---|---|---|
| 1 | **Sparkline stroke colour.** `mockup.html` strokes it `--green-600` (`#059669`). No foundations file authorises this: `color.md`'s hue budget rations hue to promise state and danger, `components.md` §14 explicitly defers the sparkline's colour to the `dataviz` skill, and `dataviz` reserves status colours and calls for a de-emphasis hue. A green trend line also sits ~40px above green `CONFIRMED` chips on the same screen. | Prompts 1 and 2 specify `text-tertiary` (`#64748B` light, `#94A3B8` dark) — an existing functional token, 4.8:1 / 6.7:1 against its surface, spends no hue. **Treat the mockup's green as the bug.** |
| 2 | **`tabular-nums` on the stat-tile value.** `typography.md` mandates tabular figures on "all metric displays" and `components.md` §14 repeats it; `dataviz` argues the opposite for large standalone values (`121` looks loose). | Prompts follow the project foundation (tabular), since it is locked and explicit. Flagged because the two sources genuinely disagree. |
| 3 | **The exception marker's shape.** `components.md` (surface) §2 says the exception flag is "a status-line addition to the row", and `edge-cases.md` #3 says a chip and a flag can co-occur — but `mockup.html` shows the flag *replacing* the chip, and no file states how both fit in a 44px row. | Prompts 1 and 3 render both inline in one status cell, 8px apart, with the marker as **unbordered, unfilled** amber text + `alert-triangle`. The no-border rule is load-bearing: an amber bordered pill is visually a `HELD` chip. |
| 4 | **Rail-edge facility accent.** `spacing-and-layout.md` puts a 4px facility-accent stripe on the rail for every console; the carrier has no facility scope at all, and neither `screens.md` nor `mockup.html` shows one. U91 covers the ops console's "All facilities" case but not this one. | Prompts specify a plain 1px border, no coloured stripe. Reasonable, but not a decision any file actually records. |
| 5 | **Status bar.** `spacing-and-layout.md`'s app shell has a 28px status bar carrying connection state, active facility, pending count and policy version — three of which are meaningless or leaky for a carrier. `screens.md`'s wireframe and `mockup.html` both omit it. | Prompts omit it. Worth an explicit decision, since "the shell has a status bar" is otherwise product-wide. |
| 6 | **Top-bar composition.** Foundations specify facility switcher · global search · notifications, help, user menu. This surface has no facility switcher (correct, U113) — but `mockup.html` also drops global search and adds a settings gear that the foundations list does not include. | Prompts use the carrier name, then `bell` + `circle-help` + avatar; no search, no gear. The gear appears to be mockup drift. |
| 7 | **Icon-rail destination icons.** U101 requires rail destinations be grounded in what the role actually has. `mockup.html` shows two glyphs (`▤`, `👤`) but `iconography.md` has no rail-destination entries. | Prompts name `layout-dashboard` and `circle-user`. The *count* (two) is grounded; the specific Lucide names are not. |
| 8 | **Refresh behaviour on re-fetch.** `flows-and-states.md` Flow 5 specifies a manual refresh but not what the sections look like while it runs; Flow 1's skeletons are written for first load. | Prompts 2 and 5 hold the previous render at `opacity: 0.6` (a `dataviz` rule — never skeleton-flash a re-fetch) and apply `motion.md`'s U84 latency bands, so nothing shows under 1s. |
| 9 | **Session expiry.** `auth-and-scoping.md` gives the carrier a 30-minute idle timeout, but no file in this folder describes the warning or expiry screen for this surface. | Not prompted. Out of scope for these nine; raise separately if a carrier-specific treatment is wanted rather than the shared one. |
