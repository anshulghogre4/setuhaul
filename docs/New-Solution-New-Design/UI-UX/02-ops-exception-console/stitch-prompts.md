# Ops exception console — Stitch prompts

> Paste-ready generation prompts for **stitch.withgoogle.com**, translated from this surface's finished
> spec. Not a spec — every value below traces to `../00-foundations/` or to this folder's
> `screens.md` / `flows-and-states.md` / `components.md` / `edge-cases.md` / `mockup.html`.
> **A value in a prompt with no foundation source is a bug in the prompt, not a new decision.**
>
> Order matches `screens.md`, then `flows-and-states.md`, then `edge-cases.md`.

## How to use these

1. **Paste Prompt 0 first, in every new Stitch session.** It carries the palette, type, density and
   exclusions that all sixteen screen prompts assume.
2. **Then paste one screen prompt.** Each repeats the handful of values it actually needs, so a single
   paste still produces something close to correct if Prompt 0 has scrolled out of context.
3. Stitch generates one screen per prompt. Do not merge two prompts hoping for two artboards.

Density is **`compact`** throughout (`spacing-and-layout.md`'s density table lists "Planner, ops console"
together) — desktop-and-pointer only, minimum 1280px, never a touch target on this surface.

---

## Prompt 0 · Shared foundation block

Paste this above every prompt below.

---
**Product and aesthetic context**

SetuHaul Dock Command is a B2B internal logistics operations tool. This is the **ops exception console** —
a cross-facility triage desk where a coordinator works escalations and capacity incidents, and takes over
driver conversations when the assistant can't resolve them. Desktop only, Windows-primary, keyboard-driven,
long dwell per item. Treat this as an **operator instrument**: calm, dense, trustworthy. Not a SaaS
dashboard, not a marketing page, no brand storytelling, no illustrations, no hero.

**Typography**

`Inter` for all UI text — weights 400/500/600/700 only, nothing else loaded. `JetBrains Mono` weights
400/500 for machine-generated values only: identifiers (ESC-104, SHP1015, DOCK-JAI-D3), timestamps, time
ranges, countdowns. Mono is mandatory there because fixed advance width stops a ticking countdown from
shifting layout and lets a column of IDs align character-for-character. Do not substitute a "more
distinctive" typeface — Inter is locked for legibility at 12–14px.

Type scale (1.2 modular, snapped to a 4px baseline):

| Token | Size / line-height / weight / tracking | Used for |
|---|---|---|
| `text-h2` | 20px / 1.4 / 600 / −0.01em | Modal title |
| `text-h3` | 16px / 1.5 / 600 / 0 | Detail-pane heading |
| `text-body` | 14px / 1.5 / 400 / 0 | Default — all UI text |
| `text-sm` | 13px / 1.4 / 400 / 0 | Secondary/supporting text |
| `text-label` | 12px / 1.33 / 600 / 0.04em, uppercase | Pane headers, enum labels, chips |
| `text-micro` | 11px / 1.3 / 500 / 0.02em | Timestamps, metadata. **Hard floor — nothing smaller.** |

Any number in a column or updating live gets `font-variant-numeric: tabular-nums`.
Body is 14px, not 16px — a deliberate density decision for dense queue work.

**Color — define both a light and a dark variant, at full parity**

Light is the shipped default for every role.

| Token | Light | Dark |
|---|---|---|
| `surface-base` (app background) | `#F8FAFC` | `#020617` |
| `surface-raised` (panes, cards, bars) | `#FFFFFF` | `#0F172A` |
| `surface-hover` | `#F1F5F9` | `#1E293B` |
| `surface-selected` (selected queue row) | `#EFF6FF` | `#1E3A8A` at 30% |
| `text-primary` | `#0F172A` | `#F8FAFC` |
| `text-secondary` | `#475569` | `#CBD5E1` |
| `text-tertiary` | `#64748B` | `#94A3B8` |
| `border-subtle` | `#E2E8F0` | `#1E293B` |
| `border-default` | `#CBD5E1` | `#334155` |
| `border-focus` | `#2563EB` | `#60A5FA` |
| `interactive-default` (primary action) | `#2563EB` | `#3B82F6` |
| `interactive-hover` | `#1D4ED8` | `#60A5FA` |
| `escalation-sla-ok` | `#475569` (no colour — normal) | `#CBD5E1` |
| `escalation-sla-warning` (<25% window left) | `#D97706` | `#FBBF24` |
| `escalation-sla-breach` (SLA missed) | `#DC2626` | `#F87171` |
| `feedback-warning-text` ("Unowned") | `#B45309` | `#FBBF24` |
| `feedback-info-text` (takeover divider) | `#1D4ED8` | `#60A5FA` |
| `feedback-danger-bg / -text / -border` | `#FEF2F2` / `#B91C1C` / `#DC2626` | `#7F1D1D` @25% / `#F87171` / `#EF4444` |

Priority left-edge markers are a **neutral value ramp, never a hue** — CRITICAL `#0F172A`, HIGH `#475569`,
NORMAL `#94A3B8`, LOW `#E2E8F0` in light; inverted wholesale in dark (`#FFFFFF` / `#CBD5E1` / `#64748B` /
`#334155`). Red in this product means danger only, never priority.

**Spacing, density, radius**

Base unit 4px; every spacing and radius value is a multiple. `compact` density means: **row height 36px,
cell padding 8px vertical / 12px horizontal, card padding 12px, stack gap 8px, button height 32px, content
padding 16px.** Radius: 4px chips/badges, 6px buttons/inputs/row hover, 8px cards/panels, 12px modals only.
Nothing rounder — heavy rounding reads as consumer software and costs perceived precision, which is wrong
for a system making capacity commitments.

**Elevation**

Light mode conveys depth with shadow, dark mode with lightness — not the same values twice.
`shadow-sm: 0 1px 2px rgba(15,23,42,0.06)` (raised panels, light only — dark uses no shadow at level 1,
separation comes from the `#020617 → #0F172A` step plus a subtle border).
`shadow-md: 0 4px 12px rgba(15,23,42,0.10)` light / `0 4px 12px rgba(0,0,0,0.40)` dark — dropdowns, popovers.
`shadow-lg: 0 12px 32px rgba(15,23,42,0.14)` light / `0 12px 32px rgba(0,0,0,0.55)` dark — modals.
Focus ring is **two rings, always**: `0 0 0 2px <surface colour>, 0 0 0 4px #2563EB` — 2px solid with 2px
offset, never a soft glow. Shadows are cool-tinted (`15,23,42` is the neutral-900 slate), never pure black.
Border weights: 1px hairline separators, 1px default panels, 2px reserved for meaning only (focused,
selected), 3px priority marker, 4px facility accent stripe.

**Motion**

`duration-instant 0ms` · `duration-fast 120ms` (hover, focus) · `duration-base 200ms` (panels, expansion,
toasts) · `duration-slow 320ms` (modal/drawer). Easing: entering `cubic-bezier(0.16, 1, 0.3, 1)`, exiting
`cubic-bezier(0.7, 0, 0.84, 0)`. **No spring, no bounce, no overshoot** — nothing in a capacity-commitment
system should read as playful. No looping or ambient animation of any kind. Animate `transform` and
`opacity` only, never `width`/`height`/`top`/`left`. Hover changes colour and border only — never a lift or
a scale.

**Motion-budget rule — state this in every live-updating region:** only the row currently changing
animates. Rows that have already settled recede in contrast toward `text-secondary` / `border-subtle`
rather than staying visually loud. Twenty rows all holding full visual weight is the same as none of them
holding it.

**Icons**

Lucide, **stroke weight 2px at every size, never varied**. Sizes: 14px inline in a chip or metadata line,
16px inline with body text, 20px standalone in a button, 24px in the top bar and icon rail, 32px in empty
and error states. Every icon is paired with visible text or an `aria-label`; icon colour never carries
meaning on its own.

**Copy register — internal, not driver-facing**

Terse and factual. No reassurance, no exclamation marks, no "successfully". 24-hour time always (`13:00`,
never `1:00 PM`). Dates as `Tue 4 Aug` with the weekday. En dash for time ranges (`09:15–13:00`), never a
hyphen. Middot separators group facts as one unit (`SHP1015 · Jaipur`). Sentence case everywhere except
uppercase enum labels. Never truncate a heading, a state label, an error message, or an SLA line.

**Explicitly exclude, everywhere in this surface**

- No hero section, no landing-page structure, no marketing copy, no testimonials, no illustration or spot
  art, no decorative photography.
- **No glassmorphism, no backdrop blur, no translucent panels** — text contrast must be verifiable, and it
  isn't when the background depends on what's behind it. Modal scrims are flat `rgba(15,23,42,0.5)` light /
  `rgba(0,0,0,0.65)` dark: dimming, not blurring.
- No gradient fills on surfaces, buttons or bars. (Aesthetic call for this system, stated plainly as one.)
- No emoji as interface icons — Lucide only.
- No ambient/looping animation, no parallax, no scroll-triggered reveals, no animated page transitions.
- No colour as the sole carrier of meaning, anywhere.
- No promise-state chips (`SHOWN` / `HELD` / `PENDING CONFIRMATION` / `CONFIRMED`) in this console's queue,
  shell or incident rows — those belong to the driver and planner surfaces. This surface renders
  escalations and incidents, not promises.
- The facility accent hue renders in **exactly two places** — the 4px rail-edge stripe and the swatch in
  the facility switcher. Never on a chip, a card, a row or any content surface.
---

---

## Prompt 1 · Console shell — three panes, queue at rest, nothing selected

`screens.md` §1. The default view a coordinator lands on.

---
**Screen**: SetuHaul Dock Command — ops exception console, default state. Desktop, minimum width 1280px,
designed for 1600×900. Light theme primary; also produce the dark variant.

**Layout** — one screen, no scrolling chrome, four fixed regions and three persistent panes:

```
┌──┬──────────────────────────────────────────────────────────────────────┐
│▌ │ [🏢 All facilities ▾]   🔍 Search shipment, driver, carrier…  🔔 ? ⚙ AB│ 56px
├──┼──────────────┬────────────────────────────────┬────────────────────────┤
│⚑ │ ESCALATIONS(7)│  Select an escalation to see   │  CO-PILOT              │
│👤│ [Filter ▾][⚙] │  its detail and thread.        │                        │
│  │ ─────────────│                                 │  Available once you    │
│  │ ▌ESC-104     │                                 │  take over a thread.   │
│  │  rows…       │                                 │                        │
├──┴──────────────┴────────────────────────────────┴────────────────────────┤
│ ● Online · synced 4s ago   All facilities   7 pending   Policy v3          │ 28px
└──────────────────────────────────────────────────────────────────────────┘
```

- **Icon rail**: 56px fixed, `surface-raised`. Exactly **two destinations** — Escalations (Lucide `flag`,
  active) and Profile (Lucide `user`). Nothing else; this role has no second home screen. Active item is
  marked by a **2px inner accent bar** in `#2563EB`, never a background fill. Icons 24px. The rail expands
  to 240px **as an overlay on hover/focus, never by pushing content** — reflow under the cursor causes
  mis-clicks. On the rail's outer edge, a **4px vertical stripe**; because scope is "All facilities" it
  renders **neutral** `#CBD5E1` light / `#334155` dark, not a facility hue.
- **Top bar**: 56px, `surface-raised`, 1px `border-subtle` on the content-facing edge, 16px horizontal
  padding, 16px gap. Left: facility switcher — a combobox that **always shows the facility name as text**,
  never an icon alone, default "All facilities", 32px tall, 6px radius, 1px `border-default`, label 14px/600.
  Centre: search field, flex-fill, `surface-hover` fill, 6px radius, 8px/12px padding, placeholder
  "Search shipment, driver, carrier…" at 13px `text-tertiary`, Lucide `search` 16px. Right: Lucide `bell`,
  `circle-help`, `settings` at 24px `text-tertiary`, then a 24px circular avatar, `#2563EB` fill, white
  initials at 11px/700.
- **Queue pane**: fixed **340px**, 1px `border-subtle` on its right edge. Header row: "ESCALATIONS" in
  `text-label` 12px/600/uppercase/0.04em `text-tertiary`, with the count "(7)" beside it; 12px/14px padding;
  1px bottom border. Below the header, a filter control and a settings icon button.
- **Detail pane**: flexible, takes the remaining width. Empty here — centred, 13px `text-tertiary`, 24px
  padding: **"Select an escalation to see its detail and thread."** No icon, no illustration, no call to
  action. Nothing has failed; the coordinator simply hasn't picked a row.
- **Co-pilot pane**: fixed **320px**. Present but inert — see Prompt 11 for its exact inactive content.
  **Never hidden**, so a coordinator always knows the capability exists.
- **Status bar**: 28px, `surface-raised`, 1px top border, 11px `text-micro` `text-tertiary`, 12px padding,
  16px gaps. Four groups: connection state (Lucide `wifi` 14px + the words "Online · synced 4s ago" —
  **icon and text, never a coloured dot alone**), active scope "All facilities", "7 pending", "Policy v3".

**Queue rows** — four items, `compact` density, 8px/12px padding, 1px `border-subtle` separators, 3px
transparent left edge reserved for the priority marker:

1. `ESC-104` · Unowned · NO_FEASIBLE_SLOT · SHP1015 · Jaipur · timer 4:12 to breach *(SLA amber)*
2. `ESC-102` · Neha B. · NOTIFICATION_FAILED · SHP1009 · Gurugram · timer 22m to breach
3. `ESC-099` · Neha B. · AMBIGUOUS_SHIPMENT · DRV004 · Kota · timer 12m (soft)
4. A **capacity-incident row**, visually distinct from the three above (Prompt 14 specifies it fully):
   collapsed, Lucide `network` 16px, "Capacity incident", "DOCK-JAI-D3 · 4 shipments · 09:15–13:00", and a
   small outline button "Review incident".

Row typography: ID in JetBrains Mono 14px/600 `text-primary`; owner right-aligned 11px — **"Unowned"
renders in `#B45309` at weight 600**, a named owner in `text-tertiary` at 400; reason enum in `text-label`
12px uppercase `text-secondary` with its Lucide reason icon at 14px (`calendar-x`, `mail-warning`,
`circle-help` respectively — **icon plus text label, never icon alone**); shipment · facility on one 13px
`text-secondary` line with facility as **plain text, no accent colour and no coloured dot**; SLA line in
JetBrains Mono 13px tabular with a Lucide `timer` 14px, coloured `escalation-sla-ok` / `-warning` /
`-breach`. **The SLA line is the only element in the row eligible for danger colour.**

**States to show**: default; hover (row background lifts to `surface-hover`, **no lift, no scale, 120ms**);
keyboard focus (the two-ring focus treatment, clearly visible against both a plain and a selected row).

**Explicitly exclude on this screen**: no sortable column headers (sort is fixed policy — time-to-SLA
ascending with unowned rows pinned above owned ones, not a user choice); no checkbox column and no bulk
action bar (every escalation needs individual judgment); no pagination and no rows-per-page control; no
export button; no column-visibility or reorder control; no per-row hover action icons; no breadcrumb; no
tabs; no secondary navigation of any kind — selecting a queue row is the only navigation this surface has.
---

---

## Prompt 2 · Queue pane — filtered, with active filter chips

`screens.md` §2. Same shell as Prompt 1; only the queue pane changes.

---
**Screen**: the ops console's 340px queue pane with two filters applied. Render the full three-pane shell
around it exactly as in the default state; only the queue pane differs.

**Filter control**: below the "ESCALATIONS (5)" header, a row containing a filter button labelled
"Filter: reason" with a Lucide `chevron-down` 16px, 32px tall, 6px radius, 1px `border-default`, and a
small ghost icon button (Lucide `settings-2` 16px, `text-secondary`).

**Active filter chips — the load-bearing part of this screen.** Directly beneath the filter control,
a wrapping row of dismissible chips, 8px gap:

```
[ Reason: NOTIFICATION_FAILED  ✕ ]   [ Owner: mine  ✕ ]
```

Each chip: `surface-hover` fill, 1px `border-default`, 4px radius, 4px/8px padding, label 12px
`text-primary` with the facet name in `text-secondary`, and a Lucide `x` at 14px as the dismiss control.
**These chips are mandatory whenever any filter is active** — without them, a coordinator reading "(5)"
has no way to tell whether that count is the whole queue or an already-narrowed view.

**Count behaviour**: the header count reflects the **filtered** set. Filtering changes membership only —
it never changes sort order.

**Focus behaviour to depict**: after applying a filter, focus stays on the filter control; it does not
jump into the result set.

**Rows**: two escalation rows matching the filter, plus a "Clear all" text button at the end of the chip
row in `#2563EB` at 12px.

**Empty-under-filter variant**: if the filter set matches nothing, the pane shows the empty-search
treatment — Lucide `search-x` 32px `text-tertiary`, "No escalations match these filters." and a
`[ Clear filters ]` outline button. Do **not** reuse the caught-up copy here; a filtered-to-zero queue and
a genuinely empty queue are different facts.

**Explicitly exclude**: no filter sidebar or drawer — the control is a popover; no saved-filter/segment
management; no "advanced search" builder; no chip colour-coding by facet.
---

---

## Prompt 3 · Queue pane — live arrivals held behind the frozen sort

`components.md` §19 / `motion.md`'s frozen-sort rule. The hardest live-update state on this surface.

---
**Screen**: the ops console queue pane while a coordinator has a row focused and new escalations have
arrived behind the frozen sort.

**The situation to depict**: a coordinator's keyboard focus is on the third row. New escalations have
arrived that would sort above it. **Nothing above the focused row may move.** Instead, arrivals accumulate
behind an affordance in the queue header.

**The affordance**: in the queue pane header, right-aligned beside "ESCALATIONS (9)", a compact pill:

```
[ 2 new · press S ]
<!-- Corrected 2026-09-01 (owner-ratified, #59 fork): re-sort/refresh is bound to S product-wide;
     R is Reject on the planner tab and the two surfaces share one RESORT_KEY constant. -->
```

`feedback-info-bg` `#EFF6FF` light / `#1E3A8A` at 25% dark, 1px `#3B82F6` border, 4px radius, 4px/8px
padding, 12px/600 label in `#1D4ED8` light / `#60A5FA` dark. Count in tabular numerals. It is a real
button as well as a keyboard hint.

**Focused row**: the third row carries the two-ring focus indicator — `0 0 0 2px #FFFFFF, 0 0 0 4px
#2563EB`. The inner ring in the surface colour is what keeps focus legible when a focused row sits
directly against a selected one.

**Motion-budget rule, applied literally here**: the arrival does **not** animate anywhere in the visible
list, because nothing has been inserted yet. The rows already on screen do not re-highlight, re-flash or
re-draw. Rows that settled earlier sit at reduced contrast — metadata in `text-secondary`, separators in
`border-subtle` — so the focused row and the "2 new" pill are the only two things with visual weight.

**On re-sort (describe, do not animate)**: the list re-renders **instantly**, not with an animated
reorder — several hundred milliseconds of a visibly wrong order is exactly the window where a keypress
does the wrong thing. Focus follows the same row by id, and that row flashes **once** at 200ms ease-out.

**Reduced-motion variant**: the arrival flash is replaced by a persistent "new" badge on the row until
acknowledged — the information survives, the movement doesn't.

**Explicitly exclude**: no animated list reordering; no rows sliding into position; no auto-scroll; no
"live" pulsing dot on the header; no toast for arrivals (the count pill is the whole signal).
---

---

## Prompt 4 · Queue pane — loading

`flows-and-states.md` Flow 1, loading. `components.md` (foundations) §13.

---
**Screen**: the ops console with its queue pane loading and the shell already rendered.

**The rule this screen exists to enforce**: the app shell — icon rail, top bar, status bar — **never
unmounts**. Only the queue pane's content region shows a loading state. Never a centred spinner over the
pane, which would hide the queue-depth count a coordinator relies on and cause a layout jump when content
arrives.

**Skeleton rows**: six placeholder rows at exactly the final row height (36px content per line, `compact`
8px/12px padding, 1px `border-subtle` separators) — the skeleton has the same shape as the real row
because it *is* the real row, rendered invisible with a pulsing block drawn over it. Each skeleton row
shows four stacked bars matching the real anatomy: a short bar where the mono ID sits, a shorter one
right-aligned for the owner, a medium bar for the reason enum, a longer bar for shipment · facility, and a
short one for the SLA line.

**Skeleton fill**: `#F1F5F9` light / `#1E293B` dark, matching the surface's own muted token, inheriting
the row's radius. A single shimmer loop at **1600ms, ease-in-out** — this is the one looping animation
permitted anywhere in this product, because it is what distinguishes "loading" from "empty". Under
`prefers-reduced-motion` it becomes a **static grey block**, not a removed element.

**Header during loading**: "ESCALATIONS" renders, but the count is **absent**, not "(0)" — a zero count
during load is a fabricated fact. Render a short skeleton bar where the count will be.

**Latency behaviour to note in the design**: nothing appears at all for the first second — an indicator
that flashes for under a second is pure distraction. The skeleton appears in the 1–3 second band. Past
roughly 3 seconds the skeleton is joined by a retry affordance rather than shimmering indefinitely.

**Detail and co-pilot panes** during queue load: detail shows its ordinary "Select an escalation…" empty
copy; the co-pilot shows its ordinary inactive copy. Neither shows a skeleton — they aren't loading.

**Explicitly exclude**: no centred spinner; no global top progress bar; no percentage; no "Loading…" text
label; no dimming of the shell; no blocking overlay.
---

---

## Prompt 5 · Queue pane — load failed

`flows-and-states.md` Flow 1, error. Copy is verbatim; do not rewrite it.

---
**Screen**: the ops console with the escalation queue failing to load. Shell fully rendered and
interactive; only the queue pane's content region shows the error.

**Anatomy**, centred in the 340px queue pane, 24px padding, 8px stack gap:

```
        [ Lucide cloud-alert, 32px, text-tertiary ]

     Couldn't load escalations — usually a
     connection problem.

              [ Retry ]
```

- Icon 32px, `text-tertiary` — **not red.** Nothing is in danger; a fetch failed.
- Message at 14px `text-primary`, centred, max ~40 characters per line. **Exact copy, unchanged:**
  "Couldn't load escalations — usually a connection problem."
- `[ Retry ]` as a neutral outline button: transparent fill, 1px `border-default`, `text-primary` label
  14px/600, 32px tall, 6px radius, minimum width 80px.

**Status bar during this state**: connection group switches to Lucide `wifi-off` plus the word "Offline",
or `cloud-alert` plus "Sync failed" — icon and text together, never a red dot alone. The pending count
renders as **"—", not "0"** — unknown and zero must never look the same.

**Error boundary variant (separate, more severe)**: if the pane crashed rather than failed to fetch, use
Lucide `octagon-alert` 32px with "Something broke loading this. The rest of the app is unaffected." and two
buttons, `[ Try again ]` and `[ Report this ]`. **Boundaries are scoped per pane, never whole-app** — a
crash in the co-pilot must not take the queue down with it. Show the other two panes still fully rendered
and usable behind it.

**Announcement**: this is an unsuccessful action and interrupts — `role="alert"`, assertive. Silence on
failure is the worst available accessibility outcome.

**Explicitly exclude**: no red-tinted pane background; no full-screen error page (this is a regional
failure); no stack trace or error code shown to the coordinator (a trace id rides along with
"Report this", invisibly); no auto-retry countdown; no apologetic copy ("Oops", "Sorry about that").
---

---

## Prompt 6 · Queue pane — empty: caught up, and nothing yet

`screens.md` §6, U74. Two different facts that must not share one treatment.

---
**Screen**: the ops console queue pane with zero escalations. Produce **two variants side by side** —
they look similar and mean opposite things, which is exactly why they get different icons and copy.

**Variant A — caught up** (a facility with history, currently at zero):

```
        [ Lucide circle-check-big, 32px, text-tertiary ]

              No open escalations.
        New ones appear here automatically.
```

Headline 14px `text-primary`; supporting line 13px `text-secondary`. **No button, no call to action** —
there is nothing for the coordinator to do, and offering an action would imply otherwise. Tone is
reassuring: this is a good state.

**Variant B — nothing yet** (a newly provisioned facility, no history at all):

```
        [ Lucide inbox, 32px, text-tertiary ]

     No escalations recorded for this facility yet.
     Once shipments start arriving, they'll show up here.
```

Tone is neutral and informational — an expected state, not a good one and not a problem.

**Why two**: an empty queue on day one and a fully caught-up queue on a busy day are different facts a
coordinator needs told apart, and showing the wrong one makes a working system look broken. The
distinguishing signal is whether the underlying facility has any prior record at all — a server-side data
check, not "count is zero".

**Header**: "ESCALATIONS (0)" — here a genuine, known zero renders as `0`, unlike the load-failure state
where it renders "—".

**Shell around it**: unchanged. Detail pane keeps its "Select an escalation to see its detail and thread."
copy; co-pilot keeps its inactive copy; status bar reads "0 pending".

**Explicitly exclude**: no illustration or spot art; no celebratory graphic, confetti or "You're all
caught up!" with an exclamation mark — a capacity system does not celebrate; no onboarding checklist; no
"Create escalation" button (escalations are raised by the engine, never by a coordinator).
---

---

## Prompt 7 · Detail pane — escalation selected, before takeover

`screens.md` §3. The read-only-thread mode. Selecting a row is never destructive or committing.

---
**Screen**: the ops console with `ESC-104` selected in the queue and its detail rendered in the centre
pane. Queue and co-pilot panes remain fully visible — this is a persistent three-pane layout, **not** an
overlay, drawer or modal.

**Selected queue row**: `surface-selected` fill `#EFF6FF` light / `#1E3A8A` at 30% dark, with a 3px left
edge in `#2563EB`. All other rows unchanged and still readable.

**Detail pane content**, 16px content padding, sections separated by 24px:

```
ESC-104 · NO_FEASIBLE_SLOT

●───●───○───○                    Unowned          ⏱ 4:12 to breach
OPEN  ACK  IN PROG  RESOLVED

[ Acknowledge ]                                              [ ⋯ ]

── REASON ────────────────────────────────────────────────────────
Reefer SHP1015 pinned to D5 (RULE003); D5 down 18:00–22:00
(DEVT002). No feasible slot in the search horizon.

── SHIPMENT ──────────────────────────────────────────────────────
SHP1015 · Jaipur · Reefer · Priority CRITICAL

── THREAD (read-only until takeover) ─────────────────────────────
Driver    Still waiting on a dock, what's happening?      09:41

[ composer — disabled, with a label explaining why ]

[ Take over thread ]
```

- **Title**: `ESC-104` in JetBrains Mono 16px/600, then a middot, then the reason enum `NO_FEASIBLE_SLOT`
  in `text-label` 12px uppercase with its Lucide `calendar-x` 16px icon.
- **Escalation stepper** (full variant — owner and cause visible): four dots joined by 1px 20px connector
  lines. **Dots are neutral, never hued** — filled `#475569` for passed/current, outline `#94A3B8` for not
  yet reached. Step names beneath in `text-micro` 11px `text-tertiary`. Lifecycle position and trouble are
  different questions; colouring the steps would blur both.
- **Owner**: "Unowned" in `#B45309` light / `#FBBF24` dark at weight 600 — the same token in every location
  it appears, so a coordinator scanning for unowned work has one colour to look for.
- **SLA clock**: the **only** danger-coloured element in this pane. `⏱ 4:12 to breach`, Lucide `timer`
  14px, JetBrains Mono 13px tabular, `#D97706` at this level. Its text carries the fact independent of
  colour.
- **`[ Acknowledge ]`**: the single primary action, `#2563EB` fill, white 14px/600 label, 32px tall, 6px
  radius. This one click both claims ownership and advances the stepper — there is no separate assignment
  step. Only one primary action exists in this view.
- **Overflow `[ ⋯ ]`**: a ghost icon button (Lucide `ellipsis` 20px, `text-secondary`) holding Escalate,
  Reassign and Cancel. These are deliberately not primary buttons — Acknowledge and Take over are the two
  decisions this pane foregrounds.
- **Section labels**: `text-label` 12px/600/uppercase/0.04em `text-tertiary`, with a 1px `border-subtle`
  rule running to the pane edge.
- **Reason body**: 14px `text-secondary`, line-height 1.5, rule codes (`RULE003`, `DEVT002`) in JetBrains
  Mono. Times in 24-hour with an en dash: `18:00–22:00`.
- **Thread**: sender name in `text-micro` 11px/600 `text-tertiary` above the message; message body 14px
  `text-primary`; timestamp right-aligned 11px `text-tertiary`. Relative bands for recent messages
  ("Just now", "N minutes ago"), absolute past 24 hours.
- **Composer, disabled**: full-width field, `surface-hover` fill, 1px `border-default`, 6px radius, with a
  visible label stating **why** it's inert — this is genuinely read-only, and taking over is the explicit
  unlock. It must not read as broken.
- **`[ Take over thread ]`**: a neutral outline button beneath the composer, not a primary fill —
  Acknowledge is the primary here.

**Reason-specific variant to include**: for `NOTIFICATION_FAILED`, the Reason section names the failed
channel and offers a `[ Retry send ]` action inline. For `NOTIFICATION_UNROUTABLE` (Lucide `mail-x`, a
deliberately different icon) that retry action **does not exist** — retrying against a missing recipient is
pointless and offering it would mislead the coordinator about what the fix is.

**Explicitly exclude**: no modal or drawer — the detail is a persistent pane; no promise-state chip; no
Confirm/Reject buttons (those are the planner's affordances, not ops'); no "mark as read"; no comment or
internal-notes thread beyond what's specified; no avatar images in the thread (sender name only).
---

---

## Prompt 8 · Detail pane — under takeover

`screens.md` §3b, `flows-and-states.md` Flow 2. A human is now in the driver's conversation.

---
**Screen**: the same detail pane as Prompt 7, after **Take over thread** was pressed. Queue and co-pilot
panes still visible; the co-pilot is now active (Prompt 12).

**What changed, exactly**:

```
ESC-104 · NO_FEASIBLE_SLOT                              [ Hand back ]

●───●───●───○              You (Anshul G.)      ⏱ 4:12 to breach
OPEN  ACK  IN PROG  RESOLVED

── THREAD ────────────────────────────────────────────────────────
Driver     Still waiting on a dock, what's happening?      09:41

─────────────  You joined the thread  ─────────────

[ composer: free text, interactive                       ] [ Send ]

[ Resolve ]  [ Cancel ]
```

- **Stepper**: third dot now filled — `IN_PROGRESS`. Owner reads "You (Anshul G.)" in `text-primary`, no
  longer the warning colour.
- **Takeover divider**: a horizontal rule with centred text "You joined the thread", 12px/600 in
  `#1D4ED8` light / `#60A5FA` dark, with the rules either side in the same hue at 40% opacity, 12px margin
  above and below. **A divider, not a message bubble — it is an event, not a message.** The equivalent
  divider is visible to the driver in their own conversation at the same moment; a silent takeover reads
  as the bot ignoring them.
- **Composer, now interactive**: `surface-raised` fill, 1px `border-default`, 6px radius, 8px padding,
  multi-line capable, 14px `text-primary`. `[ Send ]` sits beside it as the primary action — `#2563EB`
  fill, white 14px/600, 32px tall.
- **Terminal actions**: `[ Resolve ]` and `[ Cancel ]` as neutral outline buttons in a group **separated
  from Send by at least 16px and visually grouped apart from it**. These are two different terminal states
  with two different consequences, not interchangeable "done" buttons. Both open the reason picker in
  Prompt 15 — neither commits directly.
- **`[ Hand back ]`**: top-right of the pane, neutral outline, 32px. Available only from `IN_PROGRESS`
  onward. Posts a symmetric driver-visible divider and restores the assistant's auto-reply.

**Focus behaviour to depict**: on taking over, focus moves to the composer — the newly available surface
the coordinator almost certainly wants next. On hand-back completing, focus moves to the stepper/status
area, **not** the composer, since it just became non-interactive again.

**Announcement**: the takeover divider announces assertively — "You joined the thread" — because a
coordinator who doesn't register they've taken over may not realise the composer just became live.

**Time and value formatting inside the composer**: any time typed or inserted renders 24-hour; any figure
uses tabular numerals.

**Explicitly exclude**: no attachment/paperclip control, no emoji picker, no reactions, no message
editing or deletion, no read receipts on outbound messages (whether delivery state surfaces here is not
specified — do not invent an indicator), no typing indicator, no @-mentions or slash commands, no
"Approve and send" combined action anywhere.
---

---

## Prompt 9 · Detail pane — `WAREHOUSE_REPLY_CONFLICT`, side-by-side, no auto-reconcile

`edge-cases.md` #10. The interface must not make automatic reconciliation *look* available.

---
**Screen**: the ops console detail pane showing an escalation whose reason is `WAREHOUSE_REPLY_CONFLICT` —
a warehouse reply contradicts the stored schedule.

**Title**: `ESC-097 · WAREHOUSE_REPLY_CONFLICT` with Lucide `git-compare` 16px.

**The Reason section renders two accounts side by side, both read-only**, in a two-column layout with a
16px gap and a 1px `border-subtle` divider between:

```
── CONFLICT ──────────────────────────────────────────────────────
 STORED SCHEDULE                │  WAREHOUSE REPLY
 Dock D2 · Tue 4 Aug            │  Dock D4 · Tue 4 Aug
 13:00–14:15                    │  15:30–16:45
 Source: appointment APT-1042   │  Received 09:31
```

- Both columns use identical treatment — **neither is styled as correct or preferred.** Same background
  (`surface-raised`), same border, same type weights. Values in JetBrains Mono 14px, labels in `text-label`
  12px uppercase `text-tertiary`.
- Both are **Read-only in the strict sense**: zero interactive affordance — no hover state, no focus ring,
  no accent colour, no cursor change. They were never controls. A read-only view that looks clickable and
  does nothing reads as broken, not as scoped.
- Every operational time carries its **dock and its date**. Never a bare time.

**What must not exist on this screen**: there is **no "Accept warehouse's version", no "Keep our version",
no "Reconcile", no merge control, no radio pair choosing between the two columns, and no primary button
adjacent to either column.** Reconciling two conflicting accounts of a schedule is a judgment call that
must not be automated even partially — a wrong auto-merge is indistinguishable from a correct one until
it's too late. This exclusion is the entire point of the screen; a generated design that "helpfully" adds a
choose-one control has failed it.

**The only path forward**: the ordinary `[ Acknowledge ]` → `[ Take over thread ]` → manual resolution
flow, identical to every other reason. Render those two buttons exactly as in Prompt 7, with no
reason-specific shortcut beside them.

**SLA posture**: Immediate — the SLA line renders in `escalation-sla-warning` `#D97706` or `-breach`
`#DC2626` as appropriate, in JetBrains Mono tabular.

**Explicitly exclude**: no diff highlighting that implies one side is "wrong" (no red/green diff colouring
across the two columns — red means danger in this system, and neither column is dangerous); no swap
animation; no "recommended" badge; no confidence score.
---

---

## Prompt 10 · Detail pane — the row was acted on elsewhere (`ALREADY_ACTIONED`)

`edge-cases.md` #2 and #9. The nastiest race in the product, on the ops side.

---
**Screen**: the ops console at the moment a coordinator's focused escalation changes underneath them —
another coordinator acknowledged the same escalation, or a planner confirmed the shipment it refers to.

**Two variants to produce.**

**Variant A — lost the acknowledge race.** The coordinator pressed Acknowledge; another coordinator's
click committed first.

- The queue row **updates in place** to show the winning owner. It is **never removed and re-inserted**,
  which would read as a new escalation rather than the same one someone else claimed.
- The detail pane's owner field switches from "Unowned" (`#B45309`) to the winning owner's name in
  `text-primary`.
- The `[ Acknowledge ]` button is replaced by an **Inactive** control, not a Disabled one: it keeps normal
  contrast, stays fully focusable and operable, and on activation explains what happened —
  "Neha B. acknowledged this first." A dead grey rectangle gives no feedback at all.
- An inline notice above the action row, `feedback-warning` toned: `feedback-warning-bg` `#FFFBEB` light /
  `#78350F` at 25% dark, 1px `#F59E0B` left border at 3px, text `#B45309` light / `#FBBF24` dark, 14px,
  with a Lucide `circle-alert` 16px. **Inline, not a modal.**

**Variant B — the underlying shipment changed.** A planner confirmed, rejected, or cancelled `SHP1015`
while the coordinator was working the escalation.

- The escalation does **not** auto-resolve or auto-cancel. The stepper stays exactly where it was.
- The detail pane surfaces the new fact inline as soon as it's known, in the Shipment section:
  "SHP1015 was confirmed by another planner at 09:58" — 14px, `feedback-info` toned, mono for the ID and
  the 24-hour time.
- The coordinator is left to Resolve or Cancel deliberately, with the new fact as visible context.

**Announcement, both variants**: `assertive` — this is the one case that must interrupt rather than
politely queue, because a user about to act on a row that just changed underneath them needs interrupting.
If the coordinator is **not** focused on that row, the same change is **silent** and updates in place with
no announcement at all.

**Focus**: stays on that row's now-changed content. Never silently moved — the coordinator needs to see
what happened to the exact thing they were about to act on.

**Explicitly exclude**: no modal interruption; no toast as the only carrier of this fact (a toast is a
confirmation, not a record); no removal of the row from the queue; no full-pane reload; no undo affordance
(nothing of the coordinator's was committed to undo).
---

---

## Prompt 11 · Co-pilot pane — inactive

`screens.md` §4, `components.md` §3. **Inactive**, deliberately not Disabled and not Hidden.

---
**Screen**: the ops console's 320px right-hand co-pilot pane while no takeover is active — the state it
sits in most of the time.

**Content**, 24px vertical / 12px horizontal padding, centred, 8px stack gap:

```
CO-PILOT

  Available once you take over a thread.

  Summarise, fetch context, and draft
  replies for your approval.
```

- Pane header "CO-PILOT" in `text-label` 12px/600/uppercase/0.04em `text-tertiary`, 12px/14px padding,
  1px `border-subtle` bottom rule — identical treatment to the queue pane's header, so the three panes read
  as one system.
- Body copy 13px `text-tertiary`, line-height 1.6, centred, max ~28 characters per line.

**The critical distinction to honour**: this is the **Inactive** state, not Disabled and not Hidden.

- It **meets normal contrast** — deliberately not faded like a disabled control.
- It stays **keyboard-reachable** and explains itself rather than presenting a dead control.
- It is **never removed from the layout.** A coordinator should never wonder whether the co-pilot exists.
  Hiding it would also make the three-pane layout jump between two-pane and three-pane, which is worse than
  a quiet pane.

**Variant — a capacity incident is selected**: same treatment, second line replaced with "Not applicable to
a capacity incident — there is no single driver thread to take over."

**Explicitly exclude**: no greyed-out ghost buttons for Summarise / Fetch context / Draft a reply (do not
render the active controls in a disabled style — the pane explains itself in words instead); no lock icon;
no "Upgrade" or feature-gating language; no collapsing the pane to a thin strip; no chat input field.
---

---

## Prompt 12 · Co-pilot pane — active, with a draft awaiting approval

`screens.md` §4, `components.md` §3–§4, `flows-and-states.md` Flow 3. Built on an assistant sidebar
primitive, styled entirely through our tokens.

---
**Screen**: the ops console's co-pilot pane while a takeover is active on the focused escalation. The
detail pane beside it is in the takeover state (Prompt 8).

**Layout**, 12px pane padding, 8px stack gap:

```
CO-PILOT

[ Summarise thread          ]
[ Fetch context             ]

── DRAFT REPLY ──────────────
[ Draft a reply             ]

┌────────────────────────────┐
│ "Your reefer's slot at D5  │
│  reopens after 22:00. I    │
│  can offer you 22:15."     │
│                            │
│ [ Discard ]  [ Approve → ] │
└────────────────────────────┘
```

- **Three action buttons**, full pane width, left-aligned labels, 14px/600 `text-primary`, 32px tall, 1px
  `border-default`, 6px radius, `surface-raised` fill. Only three — this is not a general chat feature.
- **Section label** "DRAFT REPLY" in `text-label` 12px uppercase `text-tertiary` with a 1px rule.
- **Draft-reply card**: `surface-hover` fill `#F1F5F9` light / `#1E293B` dark, 1px `border-default`, 6px
  radius, 12px padding, body 14px `text-primary` line-height 1.5. Two actions at the card's foot, equal
  width, 8px gap: `[ Discard ]` neutral outline, `[ Approve → ]` primary `#2563EB` fill with white label.

**The two-gate rule, which the design must not shortcut**: `Approve` moves the exact text into the
**thread composer**, editable and unsent. It does **not** send. Sending is the ordinary composer Send in
the detail pane. The coordinator reads the same string twice — once in this card, once in the composer.
**There is no "Approve and send" combined action, and it must not be invented.** Show the approved text
sitting in the detail pane's composer, with `[ Send ]` still unpressed.

**Loading state per action**: the pressed button shows a spinner **in place of its leading icon, with its
own label unchanged and its width frozen** — loading never removes the action's own label, and never
reflows the pane. Nothing appears for the first second; the spinner belongs to the 1–3 second band.

**Result rendering**: Summarise and Fetch context render their results **inline in this pane,
non-editable** — 2–4 condensed lines for a summary; shipment / appointment / ETA history for context.
These are context, not messages: they never enter the thread transcript and never get a Send action.
**Only a drafted reply can cross into the composer.**

**After Discard**: the card is removed and **nothing is left behind** — no trace in the thread, no text in
the composer, no confirmation prompt. Nothing was ever shown to the driver, so there is nothing to lose.

**Explicitly exclude**: no free-text chat input in this pane (it is three fixed capabilities, not a
chatbot); no message history or conversation view; no regenerate/retry-variant control; no thumbs
up/down feedback; no model name, token count or latency readout; no streaming text animation; no
auto-population of the composer without an explicit Approve click; no auto-send under any condition.
---

---

## Prompt 13 · Co-pilot pane — stale draft, suppressed draft, and per-action errors

`edge-cases.md` #4, #5, #11; `components.md` §3's suppression rule. Three failure-adjacent states.

---
**Screen**: three variants of the co-pilot pane, each showing a different way the co-pilot degrades. All
three keep the console fully operable — the co-pilot is secondary and **never blocks the primary path**.

**Variant A — stale draft.** The thread advanced (the driver replied, or another coordinator changed the
shipment) while the draft was generating or sitting unapproved.

- The draft-reply card renders with a visible **stale marker** above the draft text: Lucide
  `alert-triangle` 14px plus "Thread updated since this was drafted", 12px in `#B45309` light / `#FBBF24`
  dark, on `feedback-warning-bg` `#FFFBEB` / `#78350F` at 25%, 4px radius, 4px/8px padding.
- Both `[ Discard ]` and `[ Approve → ]` **stay enabled** — the coordinator, not the system, decides
  whether the draft is still good advice. On Approve, the same marker carries into the composer as a
  reminder before Send.

**Variant B — `SAFETY_OR_REGULATED` suppression.** The focused escalation's reason is
`SAFETY_OR_REGULATED` (Lucide `shield-alert`).

- `[ Draft a reply ]` renders **Inactive immediately** on selecting the escalation — not after an attempt
  fails, so no generation cycle is wasted on a reply that was never going to be offered. Inactive means
  normal contrast, fully focusable, and it explains itself on activation:
  **"Not offered on safety-related escalations — write this reply yourself."**
- **`[ Summarise thread ]` and `[ Fetch context ]` remain fully available and normally styled** — gathering
  context carries none of the liability a drafted message does.
- This suppression is reason-specific, not takeover-wide. Do not grey the whole pane.

**Variant C — per-action error.** Each action degrades independently and visibly.

- Failed Summarise: inline message below that button — "Couldn't summarise — the thread is still readable
  above." 13px, `feedback-danger-text` `#B91C1C` light / `#F87171` dark, with Lucide `circle-alert` 14px.
- Failed Draft: "Couldn't draft a reply — write one directly in the composer."
- Failed Fetch context: degrades to "Context unavailable."
- **The other two buttons stay enabled**, and the detail pane's composer stays fully interactive behind
  the failure. Co-pilot failure never disables manual reply.

**Copy is verbatim in all three variants.** Do not rewrite it, soften it, or add an apology.

**Explicitly exclude**: no whole-pane error state; no retry-all button; no modal; no red pane background;
no disabling of the detail pane's composer for any of these; no hiding of the suppressed Draft button
(Hidden is reserved for scope denial, and this is not a scope decision).
---

---

## Prompt 14 · Capacity incident — collapsed row, expanded, and handed off

`screens.md` §5, `components.md` (foundations) §17, `flows-and-states.md` Flow 4. One incident, never
N escalations.

---
**Screen**: the ops console showing a capacity incident in the queue pane and its detail in the centre
pane. Produce three states.

**State 1 — collapsed row in the 340px queue pane**, visually distinct from an escalation row:

```
▶ [network] Capacity incident
  DOCK-JAI-D3 · 4 shipments · 09:15–13:00
  [ Review incident ]
```

Lucide `chevron-right` 16px as the disclosure, Lucide `network` 16px as the incident icon, title 14px/600
`text-primary`, sub-line 13px `text-secondary` with the dock code and time range in JetBrains Mono and an
en dash. **The affected count is part of the row's primary text, not a badge easy to miss.** A small
outline button "Review incident", 12px/600, 4px radius. **One row per incident, always, regardless of how
many shipments it affects** — this rule is the component's whole reason for existing.

**State 2 — expanded**, in the detail pane:

```
[network] Capacity incident · DOCK-JAI-D3

── WINDOW ────────────────────────────────
09:15–13:00

── AFFECTED SHIPMENTS (4) ────────────────
▌ SHP1005 · CRITICAL · Jaipur
▌ SHP1009 · HIGH     · Jaipur
▌ SHP1013 · NORMAL   · Jaipur
▌ SHP1014 · CRITICAL · Jaipur

[ Request sequencer proposal ]
```

- IDs in JetBrains Mono 14px. Each row carries its **3px neutral priority marker** on the left edge —
  CRITICAL `#0F172A`, HIGH `#475569`, NORMAL `#94A3B8` in light — always alongside the written priority
  word, since the bar alone is not sufficient signal.
- **Every shipment row here is strictly Read-only**: no hover state, no focus ring, no accent colour, no
  cursor change, and **no per-shipment action of any kind** — no confirm, reject, counter-offer or
  reschedule, even though these rows are queue-row-shaped. Acting happens only through the single button
  below.
- `[ Request sequencer proposal ]` is the **only action this surface has on an incident**, rendered as the
  one primary button in the pane: `#2563EB` fill, white 14px/600, 32px tall. It does not apply any capacity
  change; it asks the sequencer to compute one.

**State 3 — handed off**, after the proposal was requested:

```
[network] Capacity incident · DOCK-JAI-D3 · 09:15–13:00

Proposal requested · routed to Planner queue
4 shipments awaiting a planner's review

[ View in planner queue ↗ ]
```

- The handoff line renders `feedback-info` toned — `#EFF6FF` background light / `#1E3A8A` at 25% dark, 1px
  `#3B82F6`, text `#1D4ED8` / `#60A5FA`, 14px, 12px padding, 6px radius.
- **The incident row persists in the ops queue in this state** — it does not disappear once handed off,
  since the coordinator who triaged it may still need to track it to resolution. It also **never collapses
  back into individual rows on its own.**
- `[ View in planner queue ↗ ]` renders **only if the viewer is scoped to the planner console**. If they
  are not, the button is **absent from the layout entirely** — scope denial is always Hidden, never a
  greyed-out control that reveals a destination exists.
- The affected count is **not frozen** at request time — it reflects the current true set, so it may read
  5 later even though 4 was requested.

**Co-pilot pane in all three states**: inactive, with the incident-specific line from Prompt 11.

**Explicitly exclude**: no per-shipment checkboxes; no bulk action bar; no drag-to-reorder of affected
shipments; no timeline or Gantt visualisation here (the board belongs to the planner surface); no
"Dismiss incident" or "Ignore" action; no second "Request proposal" click offered once one is outstanding.
---

---

## Prompt 15 · Resolve / Cancel — reason picker before committing

`flows-and-states.md` Flow 6, structured on the foundations' category → detail → consequence pattern.
**Read the note under "Known gaps" before building this one** — one part of it is inference, and labelled.

---
**Screen**: the reason picker a coordinator must complete before an escalation closes. Two variants,
Resolve and Cancel — **two different terminal states with two different meanings, not interchangeable
"done" buttons.** Conflating them is the likeliest real mistake a coordinator makes under time pressure.

**Container**: the smallest modal size, **480px wide**, `surface-raised` fill, 12px radius, `shadow-lg`
(`0 12px 32px rgba(15,23,42,0.14)` light / `0 12px 32px rgba(0,0,0,0.55)` dark), 24px padding. Scrim behind
is flat `rgba(15,23,42,0.5)` light / `rgba(0,0,0,0.65)` dark — **dimming, never blurring.** Escape
dismisses; focus is trapped, restored to the trigger on close, and lands initially on the **first
interactive element, never on the committing button.**

**Cancel variant** (three reasons — the one that genuinely needs a choice):

```
┌────────────────────────────────────────────────┐
│ Cancel escalation · ESC-104                    │
│                                                │
│ REASON                                         │
│  ○ Shipment cancelled                          │
│  ○ Duplicate of another open escalation        │
│  ○ Created in error                            │
│                                                │
│ INTERNAL NOTE (never shown to the driver)      │
│  ┌──────────────────────────────────────────┐  │
│  └──────────────────────────────────────────┘  │
│                                                │
│ ── WHAT HAPPENS NEXT ────────────────────────  │
│  No message is sent to the driver. The         │
│  escalation closes with this reason on its     │
│  audit trail.                                  │
│                                                │
│         [ Cancel ]     [ Cancel escalation ]   │
└────────────────────────────────────────────────┘
```

- Title `text-h2` 20px/600, escalation ID in JetBrains Mono.
- Section labels `text-label` 12px/600/uppercase/0.04em `text-tertiary`.
- **Radio group, one column**, labels 14px `text-primary`, 32px minimum row, radios always visibly
  labelled. The three options map to the reason codes `SHIPMENT_CANCELLED`, `DUPLICATE`,
  `CREATED_IN_ERROR`. Required — the commit button stays Disabled (with a tooltip stating why) until a
  reason is chosen. A bare Cancel with no reason leaves no audit trail for why an SLA-tracked item closed.
- **Internal note**: label always visible, never placeholder-as-label; textarea 1px `border-default`, 6px
  radius, 14px; the "(never shown to the driver)" qualifier is part of the label, not a tooltip.
- **"What happens next"** replaces the driver-message preview used in the planner's reject flow, because
  neither Resolve nor Cancel sends the driver anything. It states the internal consequence instead. Do not
  render invented driver-facing copy in this slot.
- **Buttons**: `[ Cancel ]` (dismiss) neutral outline; `[ Cancel escalation ]` as the committing action.
  They sit **at least 16px apart** and the safer action comes **first in source order**, so a keyboard user
  tabbing quickly reaches the dismissal before the commit, whatever the visual order.

**Resolve variant**: identical structure, one reason only — "Issue fixed" (`ISSUE_FIXED`) — pre-selected,
with the same required internal note field, and a "What happens next" block reading: "Resolve does not send
a separate message. If a takeover occurred, the driver has already been told the outcome in the thread."
Commit button reads `[ Resolve escalation ]`.

**Validation**: on blur, never on keystroke. Error text sits **below** the field with a Lucide
`circle-alert` 14px, in `#B91C1C` light / `#F87171` dark — never colour alone.

**Focus after committing**: the next escalation in the queue **at the same position** — never the top of
the queue, so a coordinator working down a list doesn't lose their place.

**Explicitly exclude**: no "are you sure?" second confirmation on top of this (the reason picker *is* the
friction); no free-text-only reason field replacing the controlled vocabulary; no dropdown for three
options (a radio group shows all three at once); no destructive red fill on the Resolve variant's commit
button (resolving is not destructive); no driver-message preview text invented for a message that is never
sent.
---

---

## Prompt 16 · Toast and failed write

`components.md` (foundations) §8, §9, §13. The feedback layer that sits above everything else.

---
**Screen**: the ops console with system feedback rendered over it. Produce three toast types plus one
inline failure.

**Toast placement**: **bottom-left**, 16px from both edges, maximum **3 stacked** with 8px gaps; older ones
collapse to a "+2 more" summary. Toasts sit **above modals in stacking order** — a time-boxed undo that can
be hidden is no undo. Each toast: `surface-raised` fill, 1px `border-subtle`, 8px radius, `shadow-md`,
12px padding, max width 360px, body 14px `text-primary`.

**Type 1 — undo**, 5 seconds with a visible depleting bar:

```
┌──────────────────────────────────────────┐
│ Resolved ESC-104 · issue fixed           │
│ ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░       [ Undo ]       │
└──────────────────────────────────────────┘
```

The bar depletes **linearly over exactly 5000ms** — linear because it represents literal elapsed time, not
an eased transition. Bar height 3px, fill `#2563EB`, track `#E2E8F0`. `[ Undo ]` is a text button in
`#2563EB` 14px/600. The same 5-second window is **also reachable by `Cmd/Ctrl+Z` regardless of where focus
is** — a toast a sighted user can click in 5 seconds is functionally unreachable for a screen-reader user
who must first hear it announced and then navigate to it.

**Type 2 — success**, 4 seconds, dismissible, `role="status"`, announced politely. A success does not need
to interrupt.

**Type 3 — error**, **persists until dismissed**, `role="alert"`, announced assertively. Lucide
`circle-alert` 16px in `#DC2626` light / `#F87171` dark, with an explicit dismiss `x`.

**Toasts never carry the only copy of important information** — a toast is a confirmation, not a record.
Whatever it says must also be true and visible somewhere in the console.

**Inline failed write** (not a toast — this belongs next to the thing that failed):

```
[ Lucide circle-alert 16px ]  That didn't save. Nothing has changed.
                              [ Try again ]
```

`feedback-danger-bg` `#FEF2F2` light / `#7F1D1D` at 25% dark, 3px left border `#DC2626`, text `#B91C1C` /
`#F87171`, 14px, 12px padding, 6px radius. **"Nothing has changed" is mandatory and verbatim** — in a
system where a click commits capacity, a coordinator must know a failure left no partial state.

**Non-blocking warning variant** (hand-back on a thread whose shipment changed): same inline anatomy,
`feedback-warning` tones — `#FFFBEB` / `#78350F` at 25%, 3px `#F59E0B` left border, text `#B45309` /
`#FBBF24` — reading "This thread's shipment has changed since takeover — the assistant may not have
current context." The coordinator can proceed anyway, **but not silently**. This is an inline notice, not
a modal.

**Motion**: toast enters at 200ms ease-out, exits at 120ms ease-in. Under `prefers-reduced-motion` both
become instant, with the same time on screen.

**Explicitly exclude**: no top-centre or top-right toast placement; no toast stack taller than three; no
sound; no auto-dismissing error toasts; no progress spinner inside a toast; no toast for routine row
arrivals.
---

---

## Known gaps carried into these prompts

Flagged rather than invented. Each is a place the surface spec doesn't reach as far as a generation prompt
needs, and where a prompt above states an inference explicitly instead of quietly filling it.

| # | Gap | What the prompts do |
|---|---|---|
| 1 | **The Resolve/Cancel reason picker's container is never specified** as modal, popover or inline. `flows-and-states.md` Flow 6 requires a reason before committing; the foundations' §11 reject flow (the nearest precedent) is a modal, but U41 bans confirmation modals for routine actions. | Prompt 15 uses the 480px modal, on the reading that a reason picker is data collection, not a confirmation gate. Stated as an inference in the prompt. |
| 2 | **The third block of that picker has nothing to preview.** §11's DfE structure ends in a driver-message preview, but Flow 6 says Resolve sends no separate message and Cancel never notifies the driver. | Prompt 15 renders "What happens next" — an internal consequence statement — and explicitly forbids inventing driver-facing copy for a message that is never sent. |
| 3 | **Whether Resolve/Cancel gets the 5-second undo is unstated.** U41's mechanism delays a *driver notification*, and neither of these sends one, so the mechanism's rationale doesn't apply; §19 still tiers "Cancel appointment" as Moderate. | Prompt 16 shows the undo toast using the shared §9 anatomy, without asserting it fires for these two actions. |
| 4 | **Per-line type tokens for the escalation queue row aren't assigned anywhere.** `components.md` (this folder) §1 gives the anatomy in words ("text label + icon", "plain text"); `mockup.html` gives px values at the board's reduced scale. | Prompts 1–2 map each line onto `typography.md`'s scale (mono 14px/600 ID, `text-label` reason, `text-sm` shipment line, mono 13px SLA), preserving the mockup's hierarchy rather than its literal px. |
| 5 | **Three icons have no source.** `iconography.md` covers escalation reasons, dock types, queue states, planner affordances, system/connection and app-level states — but not the icon rail's Escalations destination, the Profile destination, or the facility switcher. `mockup.html` uses emoji placeholders. | Prompts 1 and 14 name Lucide `flag`, `user` and `building-2`, marked here as chosen, not sourced. |
| 6 | **The top bar's global search has no specified behaviour on this surface** — no results view, no scoping rule, no empty/no-match state. | No prompt was written for it. The field renders as chrome only; do not generate a results screen from these prompts. |
| 7 | **No export affordance is specified anywhere for ops**, and §7.5.5's tool catalog gives no export tool. | Excluded explicitly in Prompt 1 rather than left ambiguous. |
| 8 | **Send-key behaviour in the takeover composer is unspecified** (Enter to send vs. Shift+Enter for newline), and **no outbound delivery/read indicator is specified** — which is notable given `NOTIFICATION_FAILED` and `NOTIFICATION_UNROUTABLE` are both first-class escalation reasons on this very surface. | Prompt 8 excludes a delivery indicator explicitly and says not to invent one. |
</content>
</invoke>
