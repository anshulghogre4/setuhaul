# Planner dock board — Stitch prompts

> Paste-ready prompts for Stitch (stitch.withgoogle.com), one per screen/state, in `screens.md` order
> followed by the flow- and edge-case-specific states. Every value below is traceable to
> `../00-foundations/` or to this surface's own four spec files — nothing here is a new decision.
>
> Each prompt is **self-contained** (Stitch does not carry context between generations), so the token
> block repeats. Copy everything between the `---` rules.
>
> Surface constants used by every prompt: density `compact` (`spacing-and-layout.md`), light default with
> dark at parity (U69), desktop 1280px+ (below 1024px is out of support), keyboard-first.

---

## 1 · Console shell (screens.md §1)

---
**Copy-paste into Stitch — SetuHaul Dock Command · Planner console shell**

**Product context**: SetuHaul Dock Command is a B2B internal operations tool for a logistics company — not
a consumer app, no marketing site, no brand storytelling. This is the **planner console shell**: the
chrome that wraps a warehouse coordinator's whole working day. Five coordinators clear 20–35 dock-time
requests in 30 minutes on this surface. Treat it as an "operator tool" aesthetic: calm, dense-capable,
trustworthy — closer to a cockpit instrument than a SaaS dashboard.

**Typography**: `Inter` for all UI text — weights 400/500/600/700 only. `JetBrains Mono` 400/500 for
machine values only (facility codes, times, counts, policy version). Inter is chosen for legibility at
12–14px and a tall x-height; do not substitute a "more distinctive" font. Sizes: body 14px/1.5/400;
secondary 13px/1.4/400; uppercase labels 12px/1.33/600 with 0.04em tracking; metadata 11px/1.3/500
(**hard floor — nothing smaller**). All numerals `font-variant-numeric: tabular-nums`.

**Layout — fixed three-region shell, no variation**:
```
┌──┬──────────────────────────────────────────────────────────┐
│▌ │ TOP BAR                                            56px   │
│  ├──────────────────────────────────────────────────────────┤
│IR│ CONTENT (fills)                                           │
│56│                                                           │
│  ├──────────────────────────────────────────────────────────┤
│  │ STATUS BAR                                         28px   │
└──┴──────────────────────────────────────────────────────────┘
 ▲ 4px facility accent stripe on the rail's OUTER edge
```
- **Icon rail**: 56px fixed. Exactly **two destinations** — this console (active) and Profile. Lucide
  icons at 24px, stroke 2px, never varied. Active item marked by a **2px inner accent bar, not a
  background fill**. Rail expands to 240px **as an overlay on hover/focus — it never pushes the content
  region** (reflow under a planner's cursor causes a wrong click). 120ms ease-out.
- **Top bar** 56px: facility switcher (left) · two tabs `Queue` | `Board` (left of centre) · global search
  (centre, flexible) · notification bell, help, user avatar (right, 20px icons, 16px gaps).
- **Facility switcher**: a combobox that **always shows the facility name in text** ("Jaipur"), never an
  icon alone, preceded by an 8px round accent swatch. This is a **single-facility** switcher — there is no
  "All facilities" option on this surface.
- **Tabs**: 13px/600, 8px 12px padding, 6px radius. Active tab = background `#EFF6FF`, text `#2563EB`.
  Inactive = text `#64748B`, transparent. No underline indicator, no pill outline.
- **Status bar** 28px: `wifi` icon + "Online · synced 3 s ago" · "Jaipur" · "24 pending" · "Policy v3",
  11px, `#64748B`, separated by 16px. Connection state always carries **icon + text, never a coloured dot
  alone**.

**Color — light**: page `#F8FAFC`; shell surfaces (rail, top bar, status bar) `#FFFFFF` with a 1px
`#CBD5E1` border on the content-facing edge; text primary `#0F172A`, secondary `#475569`, tertiary
`#64748B`; borders subtle `#E2E8F0`, default `#CBD5E1`; focus `#2563EB`; search field background
`#F1F5F9`.
**Color — dark (full parity, not an afterthought)**: page `#020617`; shell surfaces `#0F172A` with border
`#334155`; text primary `#F8FAFC`, secondary `#CBD5E1`, tertiary `#94A3B8`; borders subtle `#1E293B`,
default `#334155`; focus `#60A5FA`.

**Facility accent**: violet `#8B5CF6` (light) / `#A78BFA` (dark) for the example facility. It renders in
**exactly two places — the 4px rail-edge stripe and the switcher's swatch — and nowhere else, ever.** Not
on a tab, not on a row, not on a badge. Accent is assigned by facility creation order, not by name.

**Spacing**: 4px base unit. Compact density throughout — content padding 16px, stack gap 8px, cell padding
8px vertical / 12px horizontal, button height 32px, minimum pointer target 32px (this is a
desktop-and-pointer-only surface; the 44px touch rule does not apply here).

**Elevation**: shell regions are Level 2 — flat fill plus a 1px border on the content-facing edge, **no
shadow**. Only floating layers (dropdowns, the expanded rail) get `0 4px 12px rgba(15,23,42,0.10)`. This
product's shadow language is deliberately restrained.

**Radius**: 6px on buttons, inputs, tabs and the switcher; 8px on cards/panels; nothing exceeds 8px in
operational chrome.

**Motion**: 120ms for rail expand and hover, 200ms `cubic-bezier(0.16, 1, 0.3, 1)` for panels. Route
changes are **instant, not animated** — a planner switching tabs is working, not enjoying a journey. No
looping or ambient animation anywhere. No spring, no bounce, no overshoot. No hover lift or scale on any
element — hover changes background and border colour only.

**Focus**: 2px solid ring with a 2px offset, drawn as two rings (inner ring in the surface colour, outer
in `#2563EB`) so focus stays visible against a coloured row. Never a soft glow.

**Explicitly exclude**: no labelled/expanded sidebar by default; no "All facilities" scope option; no
breadcrumbs; no hero band or page-title banner in the shell; no logo lockup, wordmark art or brand
gradient; no glassmorphism, backdrop blur or translucent bars; no drop shadow under the top bar; no
notification-count pulse or badge animation; no theme toggle in the top bar; no mobile hamburger, bottom
navigation or responsive collapse (this surface does not support phones); no avatar photos — initials
only; no emoji anywhere.

**Error variant — offline**: status bar switches to the `wifi-off` icon plus the text "Offline · last
synced 09:41", coloured `#B91C1C` on `#FEF2F2` (dark: `#F87171` on `#7F1D1D` at 25% opacity) with a 1px
`#DC2626` border. Icon and text both change — colour is never the only signal.
---

---

## 2 · Queue tab — at rest, the 30-second row (screens.md §2)

---
**Copy-paste into Stitch — SetuHaul Dock Command · Planner queue (the 30-second row)**

**Product context**: B2B internal logistics operations tool. This is **the throughput-critical screen in
the entire product**: a warehouse coordinator has a **30-second decision budget per row**, must read seven
fields without opening anything, and must clear a spike of 20–35 requests in 30 minutes. Density and
keyboard operation matter more than elegance. No consumer polish, no marketing surface.

**Typography**: `Inter` 400/500/600/700 for UI; `JetBrains Mono` 400/500 for all machine values —
shipment IDs, dock codes, dated time ranges, countdowns, clock limits. Body/table cells 14px/1.5/400;
supporting text 13px/1.4; column headers 12px/1.33/600 uppercase, 0.04em tracking, colour `#64748B`;
metadata 11px/1.3/500 (hard floor). Every numeral uses `font-variant-numeric: tabular-nums` so a ticking
countdown never shifts column width. Time ranges use an **en dash** (`13:00–14:15`), never a hyphen.
24-hour clock everywhere — never AM/PM.

**Layout — one table, full width, no side panel**:
```
[24 pending · 6 bulk-eligible]  [Select all eligible (6)]   Filter: CRITICAL · 6 shown
┌─┬───────────────┬───────────────────────────┬──────────────┬────────────────┬─────┬───────┬──────┬──────────┐
│☐│Driver·Carrier │Requested interval          │Receipt       │Displacement    │ETA  │Limit  │TTL   │Actions   │
├─┼───────────────┼───────────────────────────┼──────────────┼────────────────┼─────┼───────┼──────┼──────────┤
│▌│Ravi K.        │D1 · Tue 4 Aug · 13:00–14:15│CRITICAL ·    │conflicts with  │ —   │13:30  │ 2:14 │✓ ↻ ✕ ⏸ ↗ │
│ │Rajasthan Road…│                            │70 min late · │none            │     │       │      │          │
│ │               │                            │exact dock ·  │                │     │       │      │          │
│ │               │                            │0 min wait    │                │     │       │      │          │
└─┴───────────────┴───────────────────────────┴──────────────┴────────────────┴─────┴───────┴──────┴──────────┘
```
- **Sticky header**, always — a planner 30 rows deep must still know which column is which.
- **Column widths are fixed pixel values, never `auto` or `fr`.** A row that reflows mid-read is an
  operational cost, not a polish concern.
- **First column stays fixed when the table scrolls horizontally**, so a scrolled row never becomes
  anonymous.
- **Row height 36px**, cell padding 8px/12px, rows separated by a 1px `#E2E8F0` hairline. No card
  treatment, no gaps between rows, no zebra striping.
- **Selection column**: a checkbox plus a **3px left-edge priority marker** on the row itself.
- **Actions column**: the five affordances as compact 24px ghost icon buttons at the row's trailing edge,
  **always visible in every row's default state — never revealed on hover.** Lucide icons: `check`
  (Confirm), `repeat` (Counter-offer), `x` (Reject), `pause` (Hold for information), `arrow-up-right`
  (Escalate). Each has an `aria-label` and a tooltip. Reject and Confirm are separated by at least 16px
  and sit in different visual groups.

**The seven fields, and how each renders**:
1. **Driver · carrier** — two lines, driver 14px/500 `#0F172A`, carrier 11px `#64748B`. Carrier names
   **end-truncate** ("Rajasthan Roadlines Priv…") with a focus-reachable `title` tooltip carrying the full
   string; at least 4 characters always remain.
2. **Requested interval** — mono, **always dock + weekday + date + time range**: `D1 · Tue 4 Aug ·
   13:00–14:15`. A time without its dock and date is a wrong-day booking waiting to happen; never render
   one.
3. **Condensed decision receipt** — middot-separated fragments, never a sentence: `CRITICAL · 70 min late
   · exact dock · 0 min wait`, 11px `#475569`. A genuine zero renders as `0 min wait`; a missing term
   renders as a visible gap, never as a fabricated `0`.
4. **Displacement check** — the single most important field. `conflicts with none` in 11px `#64748B`, or a
   full sentence in `#B91C1C` weight 600 when there is harm: `Confirming this delays SHP1009 to 19:45.`
   **This cell never truncates and never ellipsises — if it does not fit, the column grows.**
5. **ETA confidence** — `LOW` renders as an inline warning flag: text `#B45309` on `#FFFBEB`, 1px
   `#F59E0B` border, 4px radius, 1px 6px padding, with a 14px `alert-triangle` icon. MEDIUM/HIGH render as
   plain text. Not-yet-declared renders as an explicit `—`, never as an empty cell.
6. **Driver's own limit** — mono clock value (`13:30`), the latest arrival the driver said they can make.
7. **TTL remaining** — mono countdown `M:SS`, tabular. Colour by threshold, stepping **only at the
   threshold, never as a gradient**: above 50% remaining `#2563EB`; 20–50% `#D97706`; below 20% `#DC2626`
   **and weight 600**; expired `#64748B` on `#F1F5F9`, struck through.

**Priority — value ramp, never a hue**: 3px left edge marker. CRITICAL `#0F172A`, HIGH `#475569`, NORMAL
`#94A3B8`, LOW `#E2E8F0` (dark mode inverts wholesale: `#FFFFFF` / `#CBD5E1` / `#64748B` / `#334155`).
Priority is never a coloured badge, never a red/orange/yellow chip. Red in this product means danger only.

**Color — light**: page `#F8FAFC`; table container `#FFFFFF` with 1px `#E2E8F0` border and
`0 1px 2px rgba(15,23,42,0.06)`; header row background `#FFFFFF`; hover row `#F1F5F9`; selected row
`#EFF6FF`; text primary `#0F172A`, secondary `#475569`, tertiary `#64748B`.
**Color — dark**: page `#020617`; table container `#0F172A`, 1px `#1E293B` border, **no shadow**
(separation comes from the lightness step); hover `#1E293B`; selected `#1E3A8A` at 30%; text `#F8FAFC` /
`#CBD5E1` / `#94A3B8`.

**Toolbar above the table**: "24 pending · 6 bulk-eligible" as plain 12px `#64748B` text, a single
`Select all eligible (6)` button (background `#2563EB`, white text, 32px high, 6px radius), and the active
filter stated as **text, not chips**: "Filter: CRITICAL · 6 shown". Filtering narrows membership only; it
never changes the sort.

**Sort**: fixed composite urgency computed server-side (TTL · priority · physically waiting at the gate) —
**column headers are not sortable and show no sort arrows.** The header displays the pin state when sort
is frozen. When a row has keyboard focus, the order is pinned and new arrivals accumulate behind a
"3 new · press R to re-sort" affordance in the header; nothing above the focused row ever moves.

**Motion**: only the row that just changed animates — a single 200ms `cubic-bezier(0.16, 1, 0.3, 1)`
arrival flash. **Settled rows recede in contrast rather than staying visually loud**; they do not
re-highlight when the list re-renders. Re-sorting is **instant, never animated**. Countdown digits change
at 0ms — discrete ticks, never a smooth sweep. Hover transitions 120ms, colour and border only.

**Keyboard (the primary interaction model, not an add-on)**: roving tabindex; `j`/`k`/`↓`/`↑` move focus
one row; `Space` selects; `Enter` expands; `C`/`R`/`O`/`H`/`E` act on the focused row with no modifier.
Single-key actions never fire while focus is in a text input. Focus ring is the two-ring 2px treatment,
never a glow.

**Explicitly exclude**: no pagination (this queue is capped at 15–35 rows by design); no sortable column
headers or sort arrows; no hover-revealed row actions; no row cards, gaps, shadows or rounded row
containers; no zebra striping; no avatars or driver photos; no coloured priority badges; no progress
rings or gauges; no "urgent!" banners or exclamation marks; no emoji; no drag handles or row reordering;
no expanding overlay/modal on row click (detail expands inline, pushing rows down); no infinite-scroll
spinner; no marketing empty-state illustration; no hover lift, scale or shadow growth.

**Error variant — a failed write on a row**: an error toast at bottom-left that **persists until
dismissed** (info/success toasts auto-dismiss at 4s; errors never do), `role="alert"`, text `#B91C1C` on
`#FEF2F2` with a 1px `#DC2626` border: "That didn't save. **Nothing has changed.**" plus a `[ Try again ]`
button. The words "nothing has changed" are mandatory — in a system where a click commits capacity, a user
must know a failure left no partial state.
---

---

## 3 · Queue row — state variants (components.md §1)

---
**Copy-paste into Stitch — SetuHaul Dock Command · Planner queue row states**

**Product context**: B2B logistics operations tool. This is a **variant sheet for a single table row** in
a dense planner queue (36px row height, compact density, desktop only). The same row must be legible in
six different states while a planner scans at speed under a 30-second-per-row decision budget. Show all
six stacked vertically in one artboard, each labelled.

**Typography**: `Inter` 400/500/600/700; `JetBrains Mono` 400/500 for IDs, dated time ranges and
countdowns, with `tabular-nums`. Cells 14px/1.5/400; supporting 11px/1.3/500. Nothing below 11px.

**The six states**:

1. **Default** — background `#FFFFFF` (dark `#0F172A`), 1px `#E2E8F0` bottom hairline, text `#0F172A`.
2. **Hover** — background `#F1F5F9` (dark `#1E293B`), 120ms `cubic-bezier(0.16, 1, 0.3, 1)`. **Background
   and border only — no lift, no scale, no shadow.**
3. **Focused (keyboard)** — background `#EFF6FF` (dark `#1E3A8A` at 30%) plus the two-ring focus
   indicator: 2px ring in the surface colour then 2px `#2563EB` (dark `#60A5FA`). Below the row, a 11px
   hint line: `[C] Confirm · [R] Reject · [O] Counter-offer · [H] Hold · [E] Escalate`. While this row has
   focus, the queue's sort is pinned — nothing above it moves.
4. **Selected (part of a bulk batch)** — checkbox checked, background `#EFF6FF`, plus a 2px left inner
   border in `#2563EB`. Selection and focus are visually distinct states and may co-occur.
5. **Stale — another actor already actioned this row** — the row **updates in place; it must not
   disappear and reappear.** The interval and receipt cells strike through in `#64748B`, and an inline
   line in `#B91C1C` on `#FEF2F2` with a 1px `#DC2626` border names what actually happened:
   "Expired at 13:04 — the deadline passed before this was confirmed." The five action buttons switch to
   **Inactive, not Disabled**: full contrast, still keyboard-focusable, and activating one opens the
   explanation rather than doing nothing. A dead grey rectangle gives no feedback at all.
6. **Displacement-flagged — a confirm was refused because a conflict appeared** — a 3px `#DC2626` left
   edge in addition to the priority marker, and the displacement cell re-renders in `#B91C1C` weight 600
   with the newly-named conflict as a full sentence: "Confirming this delays SHP1009 to 19:45." **Never
   truncated.** The row stays in place with its data refreshed; the planner re-reads and decides again.

**Plus one countdown sub-state — paused (hold for information)**: the TTL cell swaps the `timer` icon for
`pause`, and the **numeric value freezes and hides entirely** — replaced by the text
`⏸ paused · waiting on driver` in `#64748B` (dark `#94A3B8`), **deliberately off the amber→red urgency
scale** so a paused row never reads as a healthy long-TTL row. A frozen number would invite the misread
that time is still passing. The Hold button becomes Disabled with the tooltip "Hold has already been used
for this request" — one hold per request, prevented before the call rather than after a rejection.

**Color reference**: text primary `#0F172A` / dark `#F8FAFC`; secondary `#475569` / `#CBD5E1`; tertiary
`#64748B` / `#94A3B8`; borders `#E2E8F0` subtle, `#CBD5E1` default; danger text `#B91C1C` / `#F87171` on
`#FEF2F2` / `#7F1D1D` at 25%, border `#DC2626`; warning text `#B45309` / `#FBBF24` on `#FFFBEB` /
`#78350F` at 25%, border `#F59E0B`.

**Priority markers (never a hue)**: 3px left edge — CRITICAL `#0F172A`, HIGH `#475569`, NORMAL `#94A3B8`,
LOW `#E2E8F0`; dark mode inverts to `#FFFFFF` / `#CBD5E1` / `#64748B` / `#334155`.

**Motion**: only a row that has just changed animates — one 200ms ease-out flash, once. Settled rows do
not re-animate on re-render. Under `prefers-reduced-motion`, the arrival flash is **replaced** by a
persistent "new" badge on the row, not silently dropped.

**Explicitly exclude**: no row-level drop shadows or elevation changes between states; no scale, lift or
translate on hover or focus; no colour-only state signalling (every state above carries an icon, a border
change or text as well); no coloured left-edge bars for priority; no strikethrough without an accompanying
explanation line; no toast substituting for the in-row state change; no fade-out-then-remove on stale
rows; no spinner replacing the row while it refreshes; no emoji; no red used for anything except danger.

**Error variant**: for state 5, if the winning transition is unknown to the client, still never render a
bare "Error" — render "This request was actioned elsewhere. Refreshing this row." with a `[ Refresh row ]`
action. Every failure names a cause and a next action.
---

---

## 4 · Queue tab — bulk confirm (flows-and-states.md Flow 6)

---
**Copy-paste into Stitch — SetuHaul Dock Command · Planner queue bulk confirm**

**Product context**: B2B logistics operations tool, planner console. During a spike a coordinator must
clear 20–35 dock-time requests in 30 minutes. Bulk confirm is the deliberate fast path: one click selects
exactly the batch that is safe to confirm without individual review. It is **queue-only — no board
interaction, no preview step**, because a preview would reintroduce the friction it exists to remove.

**Typography**: `Inter` 400/500/600/700; `JetBrains Mono` for IDs, dated intervals and counts, with
`tabular-nums`. Table cells 14px; toolbar text 12px; tooltip text 13px.

**Layout — three pieces on the existing queue table**:
1. **Toolbar (above the table)**: `[ Select all eligible (12) ]` as the single primary button — background
   `#2563EB`, white text, 32px high, 6px radius, 12px horizontal padding — with plain text beside it:
   "35 pending · 12 bulk-eligible". **This button, not manual multi-select, is the primary entry point.**
2. **Ineligible rows stay visible in place**, never hidden, never moved to a separate list — they are
   often the rows that most need individual attention. Their checkbox is **Disabled**: `#E2E8F0` fill,
   `#94A3B8` mark, `cursor: not-allowed`, with the **specific failing predicate as its tooltip**, e.g.
   "ETA confidence is LOW — needs individual review", "An escalation is already open on this request",
   "Would displace SHP1009". Never a bare greyed-out control with no explanation.
3. **Contextual action bar**, appearing only when at least one row is selected — it must not reserve
   vertical space when nothing is selected. Height 40px, background `#EFF6FF` (dark `#1E3A8A` at 30%),
   1px `#3B82F6` border, 6px radius, containing "12 selected", a `[ Confirm 12 ]` constructive button and
   a `[ Clear selection ]` ghost button.

**Selection model**: click a checkbox to select; `Shift`-click extends a range from the last-clicked row;
the header checkbox selects/deselects **currently filtered rows only**, never the full unfiltered set
silently. A planner may deselect an eligible row, but may **never** select an ineligible one — the
checkbox is disabled, not merely unchecked. The eligible count recomputes live as requests arrive, but
freezes while a row has focus so the batch cannot silently grow or shrink between the two clicks.

**Color — light**: selected row `#EFF6FF`, selection border `#2563EB`; disabled checkbox `#E2E8F0` fill
with `#94A3B8` mark and `#94A3B8` label text; primary button `#2563EB` / white, hover `#1D4ED8`, pressed
`#1E40AF`. **Dark**: selected `#1E3A8A` at 30%, primary `#3B82F6` with `#020617` text, disabled `#1E293B`
fill with `#475569` mark.

**Spacing**: compact — 36px rows, 8px/12px cell padding, 8px between toolbar elements, 16px between the
action bar's own button group and its count text.

**Idempotency, stated explicitly**: the `Confirm 12` button carries an idempotency key. The loading state
prevents an accidental second click, but it does not cover a client timeout on a request that already
succeeded server-side — the retry must be safe by construction.

**Loading state**: the button's leading icon is replaced by a spinner, the label is unchanged, and **the
button width is frozen** so nothing reflows. `aria-busy="true"`. Nothing appears at all for the first
second of the request — an indicator that flashes for under a second is pure distraction.

**Result — a partial-outcome summary toast, bottom-left, never a silent partial success**: "5 confirmed,
1 skipped — SHP1013 no longer eligible." The skipped row **stays visible in the queue** for individual
review; it is not removed. Success toasts sit for 4 seconds; the undo toast (below) runs 5 seconds with a
linear depleting bar.

**Undo, not a confirmation modal**: there is **no "Are you sure?" dialog** for confirm. The database write
happens immediately; the **driver notification is queued and only dispatched when the 5-second window
closes**. Undo cancels the queued notification silently — the driver never learns it nearly happened. The
toast sits above modals in the stacking order, and `Cmd/Ctrl+Z` triggers the same undo regardless of where
focus is, so the window is reachable without racing a countdown to a specific pixel.

**Motion**: toast enters 200ms `cubic-bezier(0.16, 1, 0.3, 1)`, exits 120ms `cubic-bezier(0.7, 0, 0.84, 0)`.
The undo bar depletes over exactly 5000ms, **linear** — it represents literal elapsed time. Nothing else
on screen animates while the batch resolves; settled rows stay static.

**Explicitly exclude**: no confirmation modal; no "Are you sure you want to confirm 12 requests?" step; no
board preview before bulk confirm; no progress percentage or step counter for the batch; no confetti,
checkmark burst, or celebratory success animation; no hiding or collapsing of ineligible rows; no bare
disabled checkboxes without a tooltip reason; no "select all" that silently crosses the active filter; no
row-count badge animation; no emoji.

**Error variant — the whole batch fails**: persistent error toast (`role="alert"`), `#B91C1C` on `#FEF2F2`
with a 1px `#DC2626` border: "That didn't save. **Nothing has changed.**" plus `[ Try again ]`. Selection
is preserved so the planner does not have to rebuild the batch.
---

---

## 5 · Reject flow (flows-and-states.md Flow 3, components.md §11)

---
**Copy-paste into Stitch — SetuHaul Dock Command · Reject request dialog**

**Product context**: B2B logistics operations tool. A warehouse planner is declining a driver's requested
dock slot. The rejection reason is **sent to the driver verbatim**, so the person sending it must read the
exact words first. Structure: category → internal detail → **preview** → send. The preview step is not
optional — nobody sends copy they have not read.

**Typography**: `Inter` 400/500/600/700. Dialog title 20px/1.4/600; radio labels 14px/1.5/400; section
labels 12px/1.33/600 uppercase 0.04em `#64748B`; the preview text 14px/1.5/400; helper text 13px/1.4.
`JetBrains Mono` for the shipment ID in the title.

**Layout — a 640px modal, single decision, nothing else on screen competing**:
```
┌────────────────────────────────────────────────┐
│ Reject request · SHP1014                       │  20px/600
│                                                │
│ REASON                                         │  12px label
│  ○ Capacity            ○ Rule violation        │
│  ● Priority conflict                           │
│  ○ Safety review       ○ Data conflict         │
│                                                │
│ INTERNAL NOTE (never shown to the driver)      │
│  ┌──────────────────────────────────────────┐  │
│  └──────────────────────────────────────────┘  │
│                                                │
│ ── THE DRIVER WILL RECEIVE ─────────────────── │
│  "A higher-priority load needed that dock      │
│   time. Here are the next available options."  │
│                                                │
│         [ Cancel ]      [ Send rejection ]     │
└────────────────────────────────────────────────┘
```

**The five reasons and their exact driver-facing sentences — never rewritten, never generated**:
- `CAPACITY` → "The warehouse couldn't fit this slot alongside the trucks already scheduled."
- `RULE_VIOLATION` → "That slot isn't allowed for your load at this facility."
- `PRIORITY_CONFLICT` → "A higher-priority load needed that dock time."
- `SAFETY` → "Operations needs to review this before scheduling."
- `DATA_CONFLICT` → "Some details don't match our records — operations is checking."

The preview block updates the instant a radio changes. It is visually quoted — background `#F8FAFC` (dark
`#020617`), 1px `#E2E8F0` border, 8px radius, 12px padding, with the section rule above it labelled "THE
DRIVER WILL RECEIVE". **A rejection is never the last message in a thread** — the preview always ends by
pointing at alternatives or an escalation route.

**Fields**: labels are always visible above their control — never placeholder-as-label, which disappears
exactly when a stressed user needs it. The internal note is a textarea with the visible label "Internal
note (never shown to the driver)". Validation runs **on blur, not on keystroke**. Error text sits below
the field with a 14px `circle-alert` icon and `aria-describedby`, never colour alone.

**Buttons**: `[ Send rejection ]` is `destructive` — background `#DC2626`, white text, 32px high, 6px
radius, minimum 80px wide (dark: `#EF4444` with `#020617` text). `[ Cancel ]` is `neutral` — transparent
with a 1px `#CBD5E1` border and `#0F172A` text. **They sit at least 16px apart in different visual
groups**, and Cancel comes **first in DOM order** so keyboard traversal reaches the safer action first.
The send button carries an idempotency key.

**Color — light**: modal surface `#FFFFFF` with `0 12px 32px rgba(15,23,42,0.14)`; scrim a flat
`rgba(15,23,42,0.5)` — **dimming, never blurring**. Text `#0F172A` / `#475569` / `#64748B`; borders
`#E2E8F0` and `#CBD5E1`; focus `#2563EB`. **Dark**: surface `#1E293B` with `0 12px 32px rgba(0,0,0,0.55)`
and a 1px `#334155` border; scrim `rgba(0,0,0,0.65)`; focus `#60A5FA`.

**Radius**: 12px on the modal, 6px on inputs and buttons, 8px on the preview block.

**Motion**: modal enters at 320ms `cubic-bezier(0.16, 1, 0.3, 1)`; under `prefers-reduced-motion` it
appears instantly. No spring, no bounce, no scale-from-zero.

**Focus and dismissal**: focus traps inside the dialog and lands on the **first radio, never on the send
button**; `Escape` dismisses; focus returns to the element that opened it. Scroll is locked behind it.

**Explicitly exclude**: no free-text reason field replacing the controlled vocabulary; no "Other" radio;
no sending without the preview rendered; no apology copy ("Sorry, we couldn't…"); no exclamation marks; no
emoji or icon decoration on the reason radios; no red banner or warning triangle at the top of the dialog
(the destructive button is signal enough); no glassmorphism or blurred scrim; no illustration; no
multi-step wizard with a progress indicator — this is one screen.

**Error variant — the send fails**: the dialog **stays open**, the button returns from its loading state,
and an inline message appears above the button group: `#B91C1C` on `#FEF2F2`, 1px `#DC2626` border, with a
14px `circle-alert` icon — "That didn't send. **Nothing has changed** — the request is still pending."
plus `[ Try again ]`. Field values are preserved.
---

---

## 6 · Hold for information (flows-and-states.md Flow 4)

---
**Copy-paste into Stitch — SetuHaul Dock Command · Hold for information**

**Product context**: B2B logistics operations tool. A planner cannot decide on a dock-time request until
the driver answers a question, so they pause the request's decision clock **once** and send that question.
This is the only affordance in the queue that stops a countdown, and it is one-shot per request.

**Typography**: `Inter` 400/500/600/700; `JetBrains Mono` for the shipment ID and the dated interval.
Dialog title 20px/1.4/600; field label 12px/1.33/600 uppercase `#64748B`; textarea text 14px/1.5;
character/helper text 11px/1.3/500.

**Layout — a 480px modal**:
```
┌──────────────────────────────────────────┐
│ Hold for information · SHP1014           │
│ D1 · Tue 4 Aug · 13:00–14:15             │  mono, 13px, #475569
│                                          │
│ QUESTION FOR THE DRIVER  (required)       │
│ ┌──────────────────────────────────────┐ │
│ │ What time do you expect to reach the │ │
│ │ gate?                                │ │
│ └──────────────────────────────────────┘ │
│ The decision clock pauses until they      │
│ reply. You can only do this once.         │
│                                          │
│      [ Cancel ]     [ Send and pause ]   │
└──────────────────────────────────────────┘
```

**Rules that must be visible in the design**:
- The question field is **required** — marked on the label, not by the absence of "optional". `[ Send and
  pause ]` stays disabled until it has content, with the tooltip "Enter a question first".
- The helper line "You can only do this once." is mandatory copy — the one-shot rule must be stated before
  the action, not discovered after it.
- Validation on blur, never on keystroke.

**The resulting row state (show as a second artboard)**: the queue row's TTL cell swaps `timer` for
`pause`, the numeric countdown **freezes and hides**, and the cell reads `⏸ paused · waiting on driver` in
`#64748B` (dark `#94A3B8`) — **deliberately not on the amber→red urgency scale**, because paused time is
not elapsing and must not compete with rows genuinely running out. The Hold icon button becomes Disabled
with the tooltip "Hold has already been used for this request".

**Resume (show as a third artboard)**: when the driver replies, the countdown **reappears** at 200ms
`cubic-bezier(0.16, 1, 0.3, 1)` with its remaining time recalculated from the new deadline, and the row
gets one arrival flash so a planner who looked away does not miss that the clock is running again. This is
a visible transition, never a silent swap.

**Color — light**: modal `#FFFFFF`, `0 12px 32px rgba(15,23,42,0.14)`, scrim flat `rgba(15,23,42,0.5)`,
no blur; `[ Send and pause ]` is `neutral` intent — transparent with a 1px `#CBD5E1` border and `#0F172A`
text, **not** a blue primary, because pausing commits nothing; `[ Cancel ]` same treatment, placed first
in DOM order. **Dark**: modal `#1E293B` + 1px `#334155`, scrim `rgba(0,0,0,0.65)`, text `#F8FAFC`.

**Spacing**: 12px card padding, 8px stack gap, 32px button height, 16px between the two buttons, 12px
radius on the modal, 6px on the textarea and buttons.

**Explicitly exclude**: no "Are you sure?" second step; no suggested-question chips or AI-drafted question
text on this surface; no timer visual inside the dialog; no celebratory confirmation; no second Hold
offered anywhere once used; no frozen numeric countdown left on screen (it must hide, not sit still); no
emoji; no illustration.

**Error variant**: the dialog stays open, the button leaves its loading state, and an inline message in
`#B91C1C` on `#FEF2F2` with a 1px `#DC2626` border reads "That didn't send. **Nothing has changed** — the
clock is still running." plus `[ Try again ]`. If the request was already held by someone else, the copy
instead reads "This request has already been held once. The clock cannot be paused again." and the primary
button becomes Inactive — full contrast, still focusable, explaining itself on activation.
---

---

## 7 · Action feedback — undo, toasts and confirm refusals (flows-and-states.md Flow 1, edge-cases #1–#3)

---
**Copy-paste into Stitch — SetuHaul Dock Command · Planner action feedback**

**Product context**: B2B logistics operations tool. A planner confirming a dock slot commits real
warehouse capacity. There are **no confirmation modals** for routine confirm/reject — instead the write
happens immediately and the **driver notification is held for 5 seconds**, during which the action can be
undone. This artboard set covers the four things a planner sees after acting.

**Typography**: `Inter` 400/500/600/700; `JetBrains Mono` for IDs, dock codes and dated times, with
`tabular-nums`. Toast title 14px/1.5/500; toast supporting 13px/1.4; button 13px/600.

**1 · Undo toast (bottom-left, the default success path)**
```
┌────────────────────────────────────────────┐
│ Confirmed SHP1014 · Dock D1 · Tue 4 Aug ·  │
│ 13:00–14:15                                │
│ ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░       [ Undo ]      │
└────────────────────────────────────────────┘
```
- Surface `#FFFFFF` with `0 4px 12px rgba(15,23,42,0.10)` and a 1px `#E2E8F0` border, 8px radius, 12px
  padding, 360px wide. Dark: `#1E293B`, 1px `#334155`, `0 4px 12px rgba(0,0,0,0.40)`.
- The depleting bar runs **exactly 5000ms, linear** — it represents literal elapsed time, so it must not
  ease. Bar fill `#2563EB` on a `#E2E8F0` track, 4px high, 4px radius.
- The operational time **always carries its dock and its date**. Never "Confirmed SHP1014 · 13:00".
- Maximum 3 toasts stack; older ones collapse to "+2 more". Toasts sit **above modals** in the stacking
  order — a time-boxed undo that can be hidden is no undo.
- `Cmd/Ctrl+Z` performs the same undo for the same window regardless of where focus sits.
- `role="status"`. Success/info toasts auto-dismiss at 4s; **error toasts persist until dismissed.**

**2 · `ALREADY_ACTIONED` — the row was actioned elsewhere while the planner was looking at it**
The row **updates in place — it does not vanish and reappear**, so the planner keeps their position in the
queue. The winning transition is **named**, never a bare error: "Expired at 13:04 — the deadline passed
before this was confirmed." rendered in `#B91C1C` on `#FEF2F2`, 1px `#DC2626` border, 6px radius, with a
14px `circle-alert` icon. If the planner was focused on that exact row, this is announced assertively; if
they were not, the row updates silently.

**3 · `SNAPSHOT_STALE` — the view was older than the server, but there is no real conflict**
The row re-renders with fresh data and a neutral inline note in `#475569`: "This row was updated — read it
again before deciding." **No automatic retry** against stale data. This costs one extra glance, never a
false confirm. Treatment is deliberately *quieter* than case 2 — it is not a conflict.

**4 · `DISPLACEMENT_DETECTED` — a conflict appeared since render**
The confirm is refused outright. The displacement cell re-renders in `#B91C1C` weight 600 with the newly
named conflict as a **full sentence, never truncated**: "Confirming this delays SHP1009 to 19:45." The
row gains a 3px `#DC2626` left edge alongside its priority marker. Displacement warnings are the one place
in this product where full sentences replace terse fragments — they describe harm to a third party and
must not be skimmed.

**Color reference**: danger text `#B91C1C` (dark `#F87171`) on `#FEF2F2` (dark `#7F1D1D` at 25%), border
`#DC2626`; success text `#047857` (dark `#34D399`) on `#ECFDF5` (dark `#064E3B` at 25%), border `#059669`;
info text `#1D4ED8` (dark `#60A5FA`) on `#EFF6FF`, border `#3B82F6`; neutral text `#475569` / `#CBD5E1`.

**Motion**: toast enters 200ms `cubic-bezier(0.16, 1, 0.3, 1)`, exits 120ms `cubic-bezier(0.7, 0, 0.84, 0)`.
Under `prefers-reduced-motion` toasts appear and disappear instantly but stay on screen the same length of
time. The row's in-place update is a single 200ms flash on that row only — no other row re-animates.

**Explicitly exclude**: no confirmation modal before confirm or reject; no checkmark animation, confetti,
or celebratory success state (this system does not celebrate a capacity commitment); no exclamation marks;
no "Success!" as toast copy; no auto-dismissing error toasts; no toast that carries the only copy of an
important fact — a toast is a confirmation, not a record; no full-screen success overlay; no sound; no
emoji; no toast stacking beyond 3; no fade-out-and-remove of a row that was actioned elsewhere.

**Error variant — the undo itself fails**: a persistent error toast (`role="alert"`) reading "Couldn't
undo — the notification has already gone out. You can reject and re-offer instead." plus a
`[ Open the request ]` action. After the window closes, reversal is still possible but becomes a **new**
action with its own notification; the interface says so rather than implying the undo is still live.
---

---

## 8 · Board tab — at rest (screens.md §3)

---
**Copy-paste into Stitch — SetuHaul Dock Command · Dock board (Gantt) at rest**

**Product context**: B2B logistics operations tool. This is a **per-facility, per-day dock occupancy
board**: one horizontal lane per loading dock, time along the x-axis, each bar an appointment occupying
that dock. A planner opens it for occupancy context, to pick a counter-offer slot, to block a dock, or to
review a proposed re-sequence. Desktop only, compact density, keyboard reachable. Operator-tool
aesthetic — an instrument panel, not an analytics dashboard.

**Typography**: `Inter` 400/500/600/700 for labels and buttons; `JetBrains Mono` 400/500 for the time
axis, dock codes and shipment IDs, `tabular-nums`. Axis labels 11px/1.3/500 `#64748B`; dock row labels
12px/500 mono; bar labels 11px/500; buttons 13px/600. Nothing below 11px. 24-hour clock throughout.

**Layout**:
```
Jaipur · Board · Tue 4 Aug        [ Block a dock ]   [ Review proposal (0) ]
        09:00     10:00     11:00     12:00 │now 13:00     14:00     15:00
 D1  ███████░░░░░░░████████░░░░░░░░░░░░░░░░░│░░░▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░
 D2  ░░░░████████░░░░░░░░░░░░░░░░░░░░░░░░░░░│░░░░░░░░████████░░░░░░░░░░░░
 D3  ░░░░░░░░░░░░╌╌╌╌╌╌╌╌░░░░░░░░░░░░░░░░░░░│░░░░░░░░░░░░░░░░░░░░░░░░░░░░
 D5  ▨▨▨▨▨▨ blocked — DEVT002 outage ▨▨▨▨▨▨▨│▨▨▨▨▨▨▨▨▨▨▨▨▨▨▨▨▨▨▨▨▨▨▨▨▨▨▨
 ███ CONFIRMED   ▓▓▓ PENDING   ╌╌╌ HELD (dashed)   ▨▨▨ blocked
```
- **Dock lane height 32px**, 1px `#E2E8F0` separator between lanes, lane track background `#F1F5F9` (dark
  `#1E293B`) with 4px radius. Dock label column 56px, fixed.
- **Time axis**: the facility's rolling operating horizon — **four hours, or until closing time, whichever
  comes sooner**. This is a bounded horizon, **not a free-zoom timeline**: there are no zoom controls, no
  "day/week/month" toggle, no pinch-zoom.
- **"Now" indicator**: a 2px vertical line spanning the full lane stack with a small `now` label above it,
  computed from **server time reconciled against a measured client-clock offset** — never raw client
  `Date.now()`.
- **Header** carries the facility name **and the board's date** — a board of times with no date is exactly
  the wrong-day hazard this product designs against.

**Task bars reuse the promise-state chip's exact tokens — there is no separate Gantt palette**:
| State | Fill | Border | Opacity |
|---|---|---|---|
| `CONFIRMED` | `#ECFDF5` | 2px **solid** `#059669` | 100% |
| `PENDING_CONFIRMATION` | `#EFF6FF` | 2px **solid** `#3B82F6` | 85% |
| `HELD` | `#FFFBEB` | 2px **dashed** `#F59E0B` | 70% |
| `IN_PROGRESS` | `#ECFDF5` | 2px solid `#059669` | 100%, **plus a 14px `truck` icon inside the bar** |
| `COMPLETED` / `CANCELLED` / `EXPIRED` / `NO_SHOW` / `REJECTED` | **no bar at all — render open lane space** | | |

Dark mode: confirmed `#064E3B` at 25% with `#10B981` border; pending `#1E3A8A` at 25% with `#3B82F6`;
held `#78350F` at 25% with `#F59E0B`.

**Two rules that matter more than they look**:
- **Dashed vs solid carries permanence independently of colour** — a dashed bar says "temporary" in
  greyscale, under glare, and for a colour-blind user. Do not normalise all bars to one border style.
- **A terminal state renders as nothing, not as a ghost bar.** The board is forward-looking; that interval
  no longer occupies capacity, so it is open space. Never a faded placeholder bar.

**Outage windows** (a dock taken out of service) are **visually and semantically distinct from every
booking bar**: a 45° diagonal hatch in `#CBD5E1` on `#F1F5F9` with a 1px `#CBD5E1` border, **no elevation,
no promise-state colour**, carrying its reason as visible text inside the marker — "blocked — DEVT002
outage". An unavailability and a booking are different facts and must never share an encoding. Raising an
outage with elevation would imply something is booked there.

**Toolbar**: `[ Block a dock ]` as a `neutral` button (transparent, 1px `#CBD5E1` border, `#0F172A` text,
32px high, 6px radius). `[ Review proposal (0) ]` sits right-aligned and is **Inactive when the count is
zero — full contrast, still keyboard-focusable, and activating it explains why rather than doing nothing.**
Inactive is not the same as disabled and must not look faded.

**Legend**: a single 11px row beneath the board — an 8px swatch per state carrying its exact border style,
plus the label. Colour is never the only carrier: every bar also has its state in its focus-reachable
tooltip text alongside the shipment ID, carrier and dated interval.

**Interaction — read and act via affordances only**: **nothing on this board is draggable.** No
drag-to-reschedule, no drag-to-resize, no drag handles on bar edges, no drag-to-select a range. Bars are
keyboard-focusable elements with tooltips; actions happen through explicit buttons and clicks.

**Motion**: **only a bar that just changed state animates** — one 200ms `cubic-bezier(0.16, 1, 0.3, 1)`
flash. Settled bars stay completely static regardless of how long they have been visible. No draw-in
animation when the board loads, no shimmer on the lanes, no pulsing "now" line, no ambient movement of any
kind.

**Explicitly exclude**: no dependency arrows or link lines between bars; no drag-to-reschedule or resize
handles; no zoom controls, day/week/month switcher, or timeline scrubber; no minimap; no avatars on bars;
no gradients, glass or blur on bars; no rounded pill bars (4px radius maximum); no drop shadows on bars;
no colour-coding by carrier, priority or lateness — bar hue means promise state and nothing else; no
percentage-complete fills inside bars; no chart gridline decoration beyond a 1px hour tick; no "today"
badge in place of a real date; no ghost bars for completed or cancelled appointments; no emoji.

**Empty variant**: a facility with no occupancy in the horizon renders **the lanes, still labelled and
still showing the now-line** — never a blank panel — with one line of 13px `#64748B` text below: "No
appointments in the next four hours at Jaipur."

**Error variant**: if the board's data fails to load, the region shows its own scoped error state (the
queue tab must remain usable): `octagon-alert` at 32px `#64748B`, "Couldn't load the dock board — usually a
connection problem." and `[ Retry ]`. Scoped per region, never a whole-app error screen.
---

---

## 9 · Board tab — counter-offer picker active (screens.md §4)

---
**Copy-paste into Stitch — SetuHaul Dock Command · Counter-offer slot picker**

**Product context**: B2B logistics operations tool. A planner has decided a driver's requested dock time
will not work and is picking a replacement slot **by clicking an open interval on the dock board**. The
click is the affordance — there is no dragging anywhere in this interaction. The picked interval is
re-validated against the feasibility engine before anything is offered to the driver, so a planner cannot
hand out an infeasible slot by hand.

**Typography**: `Inter` 400/500/600/700; `JetBrains Mono` for shipment IDs, dock codes, the time axis and
dated intervals. Banner text 13px/1.4/600; axis 11px/1.3/500; bar labels 11px/500.

**Layout — the board from prompt 8, plus a persistent context banner pinned above it**:
```
┌────────────────────────────────────────────────────────────────────┐
│ Picking a new slot for SHP1014 (Ravi K. · Rajasthan Roadlines)      │
│ — click an open interval on an eligible dock.        [ Cancel ]     │
└────────────────────────────────────────────────────────────────────┘
        09:00     10:00     11:00     12:00 │now 13:00     14:00
 D1  ███████░░░░░░░████████░░░░░░[ click here ]░░░░░░░░░░░░░░░░░░░
 D2  ░░░░████████░░░░░░░░░░░░░░░░░░░░░░░░░░░│░░░░░░░░████████░░░░
 D5  ░░░ heavy-load dock — not eligible for this shipment ░░░  (dimmed)
```
- **The banner is persistent and never scrolls away** — a planner must never forget which request they are
  picking for. Background `#FFFBEB`, 1px `#F59E0B` border, text `#B45309`, 6px radius, 8px/12px padding
  (dark: `#78350F` at 25%, border `#F59E0B`, text `#FBBF24`).
- **Cancel is always reachable and always returns to the board at rest with zero side effects.** No
  partial counter-offer state exists. Cancel is a `neutral` button — transparent, 1px `#CBD5E1`, `#0F172A`
  text, 32px high.
- **Keyboard focus lands on Cancel the moment the picker opens**, so a keyboard user has the exit path
  before anything else.

**Three interval treatments, all non-draggable**:
1. **Open and eligible** — the lane's open space becomes a real, focusable, clickable target. On hover or
   keyboard focus it shows a 2px `#2563EB` outline with a 1px offset and the label "Pick 13:30–14:45" in
   11px. `Enter` selects it. Never a drag-to-define range.
2. **Occupied** — existing bars render exactly as in the board at rest (promise-state tokens, dashed for
   `HELD`) and are not clickable targets in this mode.
3. **Ineligible dock** — the entire lane dims to 35% opacity and becomes unclickable, with an inline
   reason in the lane: "Heavy-load dock — not eligible for this shipment." This is **Disabled** (a
   temporary, prerequisite-driven unavailability specific to *this* shipment), not a permission state, and
   eligibility is recomputed per shipment — a different request would dim a different set of docks.

**Revalidating state**: on click, that single interval shows a brief inline loading treatment — the real
interval rendered invisible so it holds its exact dimensions, with a pulsing block drawn over it at the
lane's own muted token. **Nothing appears at all for the first second** of the request. No page-level
spinner, no board-wide skeleton, no blocking overlay.

**Refusal state (`INTERVAL_UNAVAILABLE`)** — the click was valid but the capacity went in the meantime:
**the board re-renders with that interval now shown as occupied**, the banner stays exactly where it is,
and a 13px line appears inside the banner: "That interval was taken a moment ago. Pick another." **Never a
dead click, never a silent no-op, never a modal.**

**Success**: the surface returns to the Queue tab with the row updated to show the new proposed interval
and a distinct "awaiting driver" micro-state — the row does not simply vanish, because the planner's work
on it is not finished until the driver responds.

**Color reference — light**: pick outline `#2563EB`; banner `#FFFBEB` / `#F59E0B` / `#B45309`; lane track
`#F1F5F9`; dimmed lane at 35% opacity; text `#0F172A` / `#475569` / `#64748B`. **Dark**: pick outline
`#60A5FA`; banner `#78350F` at 25% / `#F59E0B` / `#FBBF24`; lane track `#1E293B`.

**Motion**: 120ms `cubic-bezier(0.16, 1, 0.3, 1)` on hover/focus outline. The board itself does not
animate on entering picker mode — the banner appears, the ineligible lanes dim, nothing slides or
re-lays-out. Only the interval that changed state animates.

**Explicitly exclude**: no drag-to-select a time range; no resize handles on the proposed interval; no
"snap to grid" ghost that follows the cursor; no modal confirmation after the click; no full-board overlay
or scrim during picking; no tooltip-only explanation of why a dock is ineligible (the reason renders in
the lane as text); no hiding of ineligible docks (they dim in place so the planner sees the whole
facility); no automatic re-pick or "best slot" suggestion button; no emoji.

**Error variant — the underlying request expires mid-pick**: the banner **updates in place** rather than
letting a click fail against a row that no longer exists. It switches to danger tone — `#B91C1C` on
`#FEF2F2`, 1px `#DC2626`, 14px `circle-alert` — reading "This request expired while you were picking a
slot." with a single `[ Back to queue ]` action. The picker session ends and the queue row shows its
expired state.
---

---

## 10 · Block-dock form (screens.md §5)

---
**Copy-paste into Stitch — SetuHaul Dock Command · Block a dock**

**Product context**: B2B logistics operations tool. A planner is taking a loading dock out of service for
a window of time — a leveller failure, maintenance, an outage. This is **a form opened from a toolbar
button, not a drag-to-select gesture on the board**: nothing on this product's dock board is draggable.
Blocking a dock can strand appointments that are already confirmed on it, so the form must show exactly
what it will strand **before** the planner commits, not after.

**Typography**: `Inter` 400/500/600/700; `JetBrains Mono` 400/500 with `tabular-nums` for the time inputs,
dock codes and shipment IDs. Dialog title 20px/1.4/600; field labels 12px/1.33/600 uppercase `#64748B`;
input text 14px/1.5; warning text 13px/1.4; helper 11px/1.3.

**Layout — a 480px modal**:
```
┌──────────────────────────────────────────┐
│ Block a dock                             │
│                                          │
│ DOCK          [ D5 (Reefer)          ▾ ] │
│ FROM          [ 18:00 ]                  │
│ TO            [ 22:00 ]                  │
│ REASON        [ Leveller failure       ] │
│                                          │
│ ⚠ 2 confirmed appointments fall inside   │
│   this window — SHP1005, SHP1013.        │
│   Blocking will escalate both as a       │
│   capacity incident.                     │
│                                          │
│      [ Cancel ]        [ Block dock ]    │
└──────────────────────────────────────────┘
```

**Fields**: labels **always visible above the control**, never placeholder-as-label. The dock select is a
combobox showing the dock code plus its type ("D5 (Reefer)") with the matching 14px Lucide icon — `box`
for standard, `snowflake` for reefer, `weight` for heavy. **Time inputs are 24-hour, always**, mono, with
`tabular-nums` — never a 12-hour AM/PM picker. Reason is free text (there is no controlled vocabulary for
this one, because unlike a rejection reason it is never shown to a driver). Validation runs **on blur, not
on keystroke**; errors sit below their field with a 14px `circle-alert` icon and `aria-describedby`, never
colour alone.

**The affected-appointment warning is the point of this form**:
- It fetches **live as the dock and time fields complete** — it is not deferred to submission. A planner
  deciding *whether* to block needs the consequence visible before committing.
- It **names the shipments by ID**, never just a count.
- Treatment: `#B45309` text on `#FFFBEB`, 1px `#F59E0B` border, 8px radius, 12px padding, 16px
  `alert-triangle` icon (dark: `#FBBF24` on `#78350F` at 25%).
- When there are none, the same block renders a plain neutral line instead: "No confirmed appointments in
  this window." — **the empty case is stated, never left blank**, so a planner can tell "checked, none"
  apart from "not checked yet".
- **`[ Block dock ]` stays disabled until the warning has been shown at least once against current data**,
  with the tooltip "Checking which appointments this affects…". A planner must never submit against a
  stale, not-yet-computed affected set.

**Buttons**: `[ Block dock ]` is `cautionary`, not destructive — background `#FFFBEB`, 1px `#F59E0B`
border, `#B45309` text, 32px high, 6px radius, minimum 80px wide (dark: `#78350F` at 25%, border
`#F59E0B`, text `#FBBF24`). `[ Cancel ]` is `neutral` and comes **first in DOM order**. They sit 16px
apart. The submit carries an idempotency key. **There is deliberately no typed-confirmation gate here** —
blocking is reversible, and the named-appointment warning already supplies the friction.

**Color — light**: modal `#FFFFFF` with `0 12px 32px rgba(15,23,42,0.14)`, scrim flat `rgba(15,23,42,0.5)`
with **no blur**; inputs `#FFFFFF` with 1px `#CBD5E1`, focus ring 2px `#2563EB` with 2px offset; text
`#0F172A` / `#475569` / `#64748B`. **Dark**: modal `#1E293B` + 1px `#334155`, scrim `rgba(0,0,0,0.65)`,
inputs `#0F172A` with 1px `#334155`, focus `#60A5FA`.

**Focus**: opens with focus on the **Dock select — the first interactive element, never the submit
button**; `Escape` closes; focus returns to the `[ Block a dock ]` toolbar button on close.

**Motion**: modal enters 320ms `cubic-bezier(0.16, 1, 0.3, 1)`, instant under `prefers-reduced-motion`. The
warning block appearing/updating is a 200ms ease-out swap, not a slide or an expand-height animation.

**Explicitly exclude**: no drag-to-select the window on the board; no calendar/date-range picker widget
with a mini month grid (this is a single operating day, two time fields); no 12-hour clock or AM/PM
toggle; no typed-confirmation "type D5 to confirm" gate; no destructive red submit button; no dismissible
or collapsible affected-appointment warning; no bare count without shipment IDs; no blank space where "no
appointments affected" should be stated; no illustration; no emoji; no multi-step wizard.

**Error variant — `ALREADY_BLOCKED`**: the form **stays open** and **names the conflicting block** rather
than failing vaguely — `#B91C1C` on `#FEF2F2`, 1px `#DC2626`, 14px `circle-alert`: "D5 is already blocked
18:00–20:00 for 'Reefer compressor fault'. Adjust your window, or end that block first." Field values are
preserved so the planner can adjust rather than re-enter.
---

---

## 11 · Sequencer proposal — diff overlay (screens.md §6)

---
**Copy-paste into Stitch — SetuHaul Dock Command · Schedule proposal review**

**Product context**: B2B logistics operations tool. An automated sequencer has produced a **proposed**
re-arrangement of a facility's dock schedule — usually because a capacity incident stranded several
appointments. The planner reviews it as a **before/after diff drawn on the dock board itself** and either
applies it whole or leaves it. It proposes; a human applies. The proposal is **not part of the schedule
yet, and must look that way.**

**Typography**: `Inter` 400/500/600/700; `JetBrains Mono` 400/500 for the run ID, shipment IDs, the time
axis and dated intervals, `tabular-nums`. Overlay heading 20px/1.4/600; run metadata 11px/1.3/500 mono
`#64748B`; summary line 13px/1.4/500; bar labels 11px/500.

**Layout — a full-width overlay above the board region**:
```
┌───────────────────────────────────────────────────────────────────────┐
│ Proposal · RUN-8f2a · requested from Ops (capacity incident)  [ Apply ]│
│ Tue 4 Aug · Jaipur                                                     │
│        09:00     10:00     11:00     12:00 │now 13:00     14:00        │
│ D1  ███████░░░░░░░████████░░░░░░░░░░░░░░░░░│░░░▓▓▓▓▓▓░░░░░░░░░░░░░░░░  │
│ D3  ░░░░░░░░░░░░████████░░[MOVED ⇢]┌╌╌╌╌┐░░│░░░░░░░░░░░░░░░░░░░░░░░░  │
│ D4  ░░░░░░░░░░[NEW]┌╌╌╌╌┐░░░░░░░░░░░░░░░░░░│░░░░░░░░░░░░░░░░░░░░░░░░  │
│                                                                        │
│ 4 shipments: 1 unchanged · 2 moved · 1 newly placed · 0 unplaceable    │
└───────────────────────────────────────────────────────────────────────┘
```

**The diff vocabulary is fixed — use these four words, no synonyms**: **unchanged · moved · newly placed ·
unplaceable**. Not "rescheduled", not "added", not "failed".

**How the delta renders — outline treatment, never a new colour**:
- The **current schedule** stays drawn in its normal promise-state bars, at reduced contrast.
- The **proposed** bars are drawn as **floating outlines offset 2px above** their current position — 2px
  **dashed** border in the same promise-state hue the bar already carries, transparent fill, plus a small
  11px uppercase badge label (`MOVED`, `NEW`) at the bar's leading edge. Under `prefers-reduced-motion`,
  forced-colors mode, or greyscale this still reads, because the distinction is **border style plus a text
  badge**, not hue.
- **No fifth semantic colour is introduced.** The palette stays exactly where it is: green `#059669`
  confirmed, blue `#3B82F6` pending, amber `#F59E0B` held, red `#DC2626` danger only.
- Elevation: the proposal layer floats at `0 4px 12px rgba(15,23,42,0.10)` above the current schedule —
  the literal visual expression of "not committed yet".

**Unplaceable shipments list separately below the board**, never as a zero-width or ghost bar pretending
to be a placement: a plain list, `#B45309` on `#FFFBEB` with a 1px `#F59E0B` border and a 16px
`calendar-x` icon — "Couldn't place: SHP1017 (CRITICAL, reefer required)". A gap is a gap.

**Apply is all-or-nothing**: one `[ Apply ]` button, `constructive` — `#2563EB` background, white text,
32px high, 6px radius, idempotency-keyed. **There is no per-shipment checkbox, no "apply these three"
partial selection** — the underlying operation does not support it, and the interface does not offer a
control that does not exist.

**Header metadata is mandatory**: the run ID (mono), the origin — either "requested from Ops (capacity
incident)" or "requested by you" — and the board's date. A proposal with no traceable origin is not
reviewable.

**States**:
- **Loading** — the board's lanes render at their real dimensions with a pulsing block drawn over them, in
  the surface's own muted token; never a centred spinner, which causes a layout jump.
- **Reviewing** — as drawn above.
- **Applying** — the Apply button's icon becomes a spinner, its label unchanged and its **width frozen**,
  `aria-busy="true"`. Past 3 seconds it becomes determinate; past 10 seconds it adds a plain "Still
  working on this…" line.
- **Applied** — the overlay closes and the board shows the new committed schedule. No celebratory state.

**Color — light**: overlay surface `#FFFFFF`, 1px `#E2E8F0`, `0 12px 32px rgba(15,23,42,0.14)`; text
`#0F172A` / `#475569` / `#64748B`. **Dark**: `#1E293B`, 1px `#334155`, `0 12px 32px rgba(0,0,0,0.55)`.

**Motion**: the overlay opens at 320ms `cubic-bezier(0.16, 1, 0.3, 1)`; the diff bars do **not** animate
into position — no morphing from the current bar to the proposed one, no travelling ghost. `Escape` exits
without applying.

**Explicitly exclude**: no partial-apply checkboxes or per-shipment approve/reject; no drag adjustment of
proposed bars; no animated transition showing bars sliding to their new positions; no new hue for
"proposed" (outline and badge only); no zero-width or ghosted bar for an unplaceable shipment; no
confidence score, star rating or "optimality" gauge for the proposal; no auto-apply or countdown to
auto-apply; no chart of before/after utilisation; no confetti or success overlay after applying; no emoji.

**Error variants — both refusals are named outcomes, never a bare failure**:
- **Snapshot drift** (the world moved since the proposal was computed): `#B91C1C` on `#FEF2F2`, 1px
  `#DC2626` — "The schedule changed after this proposal was calculated, so it can no longer be applied
  safely." with a single `[ Request a fresh proposal ]` action. **Never a blind retry of the stale
  proposal.**
- **Partially infeasible** (one constraint invalidates the whole batch): same treatment — "This proposal
  can't be applied — SHP1017 no longer fits any dock in the window, and the proposal only applies as a
  whole." No "apply what's still valid" fallback is offered, because none exists.
- **A run is already in progress for this facility**: an inline, non-blocking state on the request action —
  `#1D4ED8` on `#EFF6FF`, 1px `#3B82F6` — "A re-sequence is already running — you'll be notified when it's
  ready." This is an expected condition, not a failure, and must not read like one.
---

---

## 12 · Empty, loading and failure states (components.md §13, edge cases)

---
**Copy-paste into Stitch — SetuHaul Dock Command · Planner console empty, loading and failure states**

**Product context**: B2B logistics operations tool, planner console. This artboard set covers every state
where the console has **no data, incomplete data, or broken data**. In a system where one click commits
warehouse capacity, each of these must **name a cause and a next action** — no bare spinners, no
"something went wrong", no decorative empty-state illustrations.

**Typography**: `Inter` 400/500/600/700. Empty-state heading 16px/1.5/600 `#0F172A`; supporting line
14px/1.5/400 `#475569`; action button 13px/600. `JetBrains Mono` only where a value appears.

**Shared anatomy for every empty/error state** — centred in the content region, nothing else:
```
        [ Lucide icon, 32px, #64748B ]

           What is true right now
      One line explaining why, if useful

            [ The next action ]
```
Icon 32px, 16px below it the heading, 8px below that the supporting line, 24px below that the action.
Maximum text width ~60 characters.

**The eight states**:

1. **Queue empty — caught up.** Icon `circle-check-big`. "No pending requests." / "New ones appear here
   automatically." **No call to action** — this is a good state. Tone reassuring.
2. **Queue empty — nothing yet (a newly provisioned facility).** Icon `inbox`. "This facility has no
   requests yet." / "Once shipments start arriving, they'll show up here." Tone neutral and
   informational. **These two must never share an icon or copy** — the same visual emptiness means two
   opposite things, and showing the wrong one makes a working system look broken.
3. **Search returned nothing.** Icon `search-x`. "No shipment matches 'RJ14'." with `[ Clear search ]`.
4. **Queue skeleton (loading).** **Not a centred spinner.** Render the real table rows invisible so they
   hold their exact 36px height and column widths, then draw a pulsing block over each at `#F1F5F9` (dark
   `#1E293B`), 1600ms `cubic-bezier(0.65, 0, 0.35, 1)` loop. The shell — rail, top bar, status bar —
   **never unmounts**; only the content region loads. Under `prefers-reduced-motion` the shimmer becomes a
   static grey block.
5. **Board skeleton (loading).** Same technique but shaped like **lanes, not rows** — the dock label
   column and lane tracks at their real dimensions with the pulse over them. Each destination gets a
   skeleton matching its own final layout; never one generic loader for both tabs.
6. **Load failed.** Icon `octagon-alert`. "Couldn't load the queue — usually a connection problem." with
   `[ Retry ]`. **Scoped to the region**: the queue and the dock board have separate error boundaries, so
   a board failure must not take down a queue a planner is mid-decision on.
7. **404 / out of scope.** Icon `map-pin-off`. "That shipment doesn't exist, or isn't somewhere you have
   access to see." with `[ Back to your queue ]`. **The same message deliberately covers both cases** — a
   different message for "exists but not yours" would leak that it exists.
8. **Below minimum width (under 1024px).** Not a squeezed table: a plain full-region message — "The
   planner console needs a screen at least 1024px wide." / "Seven fields and a 30-second decision don't
   survive a phone screen." No responsive fallback layout, no horizontal-scroll mini table.

**Plus one system state — maintenance.** Icon `wrench`. "SetuHaul Dock Command is being updated." /
"Expect this to take about 15 minutes." / "Anything you were doing has been saved — just come back and
pick up where you left off." Always states an estimated duration; a maintenance page that does not say how
long reads as indefinite.

**Color — light**: icon and supporting text `#64748B`; heading `#0F172A`; page `#F8FAFC`; the action
button is `neutral` — transparent, 1px `#CBD5E1`, `#0F172A` text, 32px high, 6px radius. Error states
use `#B91C1C` text on `#FEF2F2` with a 1px `#DC2626` border **only for the inline message block**, never
as a full-page red wash. **Dark**: icon/supporting `#94A3B8`; heading `#F8FAFC`; page `#020617`; error
`#F87171` on `#7F1D1D` at 25%.

**Copy rules that are non-negotiable**: on any failed **write**, the words "**Nothing has changed.**" are
mandatory — a user must know a failure left no partial state. Never "Oops", never "Something went wrong",
never an apology for a system rule, never an exclamation mark.

**Explicitly exclude**: no illustrations, spot art, mascots or 3D graphics; no centred spinners anywhere;
no global top-of-page progress bar (a skeleton that appears immediately is sufficient signal); no
full-page red or amber background washes; no "Oops!" or "Uh oh!" copy; no exclamation marks; no emoji; no
"Contact support" as the only action; no whole-app error screen replacing the shell; no animated
loading mascot or bouncing dots; no auto-retry countdown that reloads without the user asking; no
responsive phone layout for a surface that does not support phones.

**Motion**: skeleton shimmer is the only looping animation permitted anywhere in this product, and only
while data is genuinely in flight. **Nothing appears at all for the first second** of any request — an
indicator that flashes for under a second is pure distraction. Between 1 and 3 seconds, the skeleton or
button spinner. Past 3 seconds, a determinate indicator where progress can be expressed. Past 10 seconds,
an explicit "Still working on this…" line.
---
