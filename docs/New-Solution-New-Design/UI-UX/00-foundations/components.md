# Component inventory

> Shared components used by two or more surfaces. Surface-specific components live in each surface's
> `components.md`. Specs are implementation-agnostic (U22); shadcn/ui + Radix is what they bind to (U51).
>
> Every component lists **anatomy**, **variants**, and **states** — default, hover, focus, active,
> disabled, loading, error, empty, as applicable.

---

## 1. Button

Intent-based variants (U12) — named by **consequence**, not appearance. This forces every new button to
declare what it does, which is the right discipline when confirming can silently harm a third party.

| Variant | Use for | Light | Dark |
|---|---|---|---|
| `constructive` | Commits something good — Confirm, Request slot, Save | bg `blue-600`, text white | bg `blue-500`, text `neutral-950` |
| `neutral` | Non-committal — Counter-offer, Hold, Cancel, Close | bg transparent, border `border-default`, text `text-primary` | same |
| `cautionary` | Escalates or hands off — Escalate, Get help | bg `amber-50`, border `amber-500`, text `amber-700` | bg `amber-900`/25%, border `amber-500`, text `amber-400` |
| `destructive` | Ends something for someone else — Reject, Cancel appointment | bg `red-600`, text white | bg `red-500`, text `neutral-950` |
| `ghost` | Tertiary, in-row — expand, overflow menu | transparent, text `text-secondary` | same |

### Anatomy
```
┌─────────────────────────────┐
│ [icon] Label        [badge] │   height per density (32/40/56)
└─────────────────────────────┘
  ↑ 8px    ↑ 6px gap    ↑ 8px
```

### States
| State | Treatment |
|---|---|
| Default | Per variant above |
| Hover | Background one step darker (light) / lighter (dark). **No lift, no scale** (`motion.md`). |
| Focus | `shadow-focus` two-ring. Visible on keyboard focus always; on click, only if keyboard-initiated. |
| Active | Background two steps darker/lighter, no transform |
| Disabled | `interactive-disabled-bg` + `interactive-disabled-text`, `cursor: not-allowed`. **Always paired with a tooltip explaining why** — a disabled control with no explanation is a dead end (U32). |
| Loading | Spinner replaces the leading icon, label unchanged, width **frozen** to prevent reflow, `aria-busy="true"` |

### Rules
- **One `constructive` per view.** If two things compete for primary, the hierarchy is wrong.
- **`destructive` never sits adjacent to `constructive`.** Minimum 16px and a different visual group —
  Confirm and Reject must not be mis-clicked for one another under time pressure.
- Icon-only buttons require `aria-label` and a tooltip. Never in the driver surface.
- Minimum width 80px so short labels ("OK") do not produce tiny targets.
- **Every `constructive` and `destructive` button that affects capacity carries an idempotency key (U70,
  M9).** The loading/disabled state prevents an *accidental* second click, but it does not cover a client
  timeout on a request that actually succeeded server-side — the retry that follows must be safe by
  construction, not by the user refraining from clicking twice. `neutral` and `cautionary` actions that
  don't mutate capacity (Counter-offer's *proposal*, Hold, Escalate's initial flag) don't strictly need
  one, but including it uniformly on every mutating call is simpler than reasoning about which subset is
  exempt — and cheap.
- **Safer-action-first DOM order (U79).** When a `destructive` and a `constructive` (or `cautionary`)
  button appear together — Reject beside Confirm, Cancel beside Save — the less harmful action is placed
  **first in source order**, regardless of visual left-to-right position. Keyboard tab traversal then
  reaches the safer action first no matter how the row is laid out. Free correctness for the planner
  console's Confirm/Reject pair specifically — a planner tabbing quickly through a 35-request spike lands
  on Reject before Confirm if they overshoot, never the reverse.

---

## 2. Promise-state chip

**The most important component in the product.** Four redundant encodings (U14).

### Anatomy
```
┌──────────────────────────┐
│ ◷  HELD          1:24    │   ← icon · label · optional countdown
└──────────────────────────┘
  border varies by state
```

| State | Icon | Label | Border | Countdown |
|---|---|---|---|---|
| `SHOWN` | `list` | SHOWN | 1px solid neutral | none |
| `HELD` | `timer` | HELD | **2px dashed amber** | yes, mandatory |
| `PENDING_CONFIRMATION` | `clock-fade` | PENDING CONFIRMATION | 2px solid blue | yes, mandatory |
| `CONFIRMED` | `circle-check` | CONFIRMED | 2px solid green | none |

### Variants
- **`outline`** (default) — for dense contexts: table rows, dock board bars
- **`filled`** — coloured background. **Mandatory on driver and gate surfaces** so state survives glare.

### Rules
- **Never abbreviate the label.** `PENDING CONFIRMATION`, not `PENDING` or `PC`. If it does not fit, the
  container is too small.
- **Never render feedback colours in the state slot** — a green banner means an action succeeded; a green
  chip means CONFIRMED. Position disambiguates what colour cannot (`color.md`).
- Always `role="status"` so assistive tech announces transitions.
- The chip is **the only component permitted to use state hues**. Nothing else may borrow them.
- **Transitions between states are hard-swaps, not a morph (U75).** When a promise moves from `HELD` to
  `PENDING_CONFIRMATION` to `CONFIRMED`, the chip does not animate one shape into another — the old chip's
  icon, label, border and colour are replaced outright, at `duration-instant` (`motion.md`), with no
  in-between visual state. This was a genuine fork: a single element that visually morphs between states
  gives better continuity (the eye never has to re-acquire it), but U14's own principle is that these four
  states must **never be confusable** — and a morph risks exactly that, since a driver catching the chip
  mid-transition could plausibly read `HELD` as "on its way to being `CONFIRMED`" rather than as a
  distinct, still-revocable state. Distinctness wins over continuity here. **The one exception:** entry
  into `CONFIRMED` may carry a single non-celebratory mark (a brief border-colour settle, not a scale or
  bounce) — the one moment in the lifecycle where "this just became permanent" is worth a beat of
  acknowledgement, still within the no-spring, no-overshoot rules of `motion.md`.

---

## 3. Countdown

A bespoke primitive — no library does this (research, 2026-08-19). It drives consequential actions, so it
is specified and tested like logic, not styling.

### Anatomy
```
⏱ 1:24        or        ⏱ 14:32 remaining
```

### Behaviour
| Remaining | Colour | Weight | Extra |
|---|---|---|---|
| > 50% | state hue | 400 | — |
| 20–50% | `amber-600` | 400 | — |
| < 20% | `red-600` | **600** | `HELD` only: border pulses 1/sec |
| < 10s | `red-600` | 600 | Haptic at 10s and 5s (driver) |
| 0 | `neutral-500` | 400 | Component is **replaced in place** by the expiry state |
| **paused** | `neutral-500` | 400 | See below — a distinct state, not a colour on the existing scale |

### Paused (U67)

§7.3's "hold for information" affordance pauses the D9 clock once. This must be **unmistakable from a
healthy long-TTL row** — a planner scanning the queue reads a calm neutral countdown as "plenty of time,"
and a paused request left in that state by mistake would be treated as fine when it is actually blocked
on the driver.

```
⏸ paused · waiting on driver
```

- Icon switches from `timer`/`clock-fade` to `pause` (`iconography.md`).
- Numeric value **freezes and hides** — replaced by the reason text, not a static `04:12`. A frozen number
  invites the misread that time is still passing normally.
- Colour is `neutral-500`/`neutral-400`, deliberately *not* on the amber→red urgency scale, since paused
  time is not elapsing and should not visually compete with rows that are genuinely running out.
- **One-shot.** A second `hold_for_information` call on the same request is not offered — `components.md`
  §11's reject-flow discipline applies equally here: the affordance that triggers pause is disabled with a
  tooltip stating it has already been used, once used.
- **Resume is a visible transition**, not a silent swap: the countdown reappears at `duration-base` with
  its remaining time recalculated from the new deadline, and the row gets one `motion.md` arrival-style
  flash so a planner who looked away doesn't miss that the clock is running again.

### Implementation requirements
- **One shared 1 Hz interval for the whole app**, not one timer per instance. A queue with 35 pending rows
  must not run 35 timers.
- Always `--font-data` with `tabular-nums` so digits do not shift width.
- `aria-live="polite"`, but **throttled to announce at 50%, 20%, 10s and expiry only**. A per-second live
  region is unusable with a screen reader.
- Never animate the digit change (`motion.md`) — ticks must read as discrete.
- **Server time is authoritative.** Compute from a server-provided `expires_at` with a measured clock
  offset, never from client `Date.now()` alone. A driver with a wrong device clock must not see a wrong
  hold duration.
- On expiry, **do not remove the component** — replace it with the expiry state so the record persists.

---

## 4. Decision receipt

Renders `score_terms` (§7.2b). **The interface displays this; it never computes or re-ranks it.**

### Variants

**`condensed`** — one line, for queue rows and option cards:
```
CRITICAL · 70 min late · exact dock · 0 min wait
```
Middot-separated fragments, ordered by decision weight. Never a sentence — a planner reads this in under
two seconds.

**`full`** — expanded row or detail view:
```
┌────────────────────────────────────────────┐
│ Why this slot ranked first                 │
│                                            │
│ Priority          CRITICAL         +4000   │
│ Lateness          70 min            +280   │
│ Driver wait       0 min                0   │
│ Slack buffer      25 min             +25   │
│ Dock match        exact                0   │
│                              ─────────────  │
│ Total                              +4305   │
│                                            │
│ Policy v3 · computed 09:52:14              │
└────────────────────────────────────────────┘
```

### Rules
- Values are `--font-data`, right-aligned, `tabular-nums`.
- **Always stamp the policy version.** "Which policy produced this promise?" must be answerable later (§5).
- The driver-facing explanation is *generated from* this data, never invented — the assistant narrates the
  receipt (§7.2b).
- If `score_terms` is missing a field, **render a gap, not a zero**. A fabricated 0 is a wrong explanation.

---

## 5. Priority marker

3px left edge bar, neutral value ramp (U10, `color.md`). Never a hue.

```
┃ SHP1014  ...    ← CRITICAL, near-black
┃ SHP1009  ...    ← HIGH
┃ SHP1002  ...    ← NORMAL
┃ SHP1003  ...    ← LOW, near-invisible
```

Always accompanied by a text label in the row or its tooltip — the bar alone is not sufficient signal
(U30).

---

## 6. Data table

The planner queue is the hardest layout in the product. Full spec in `03-planner-dock-board/`; shared
behaviour here.

### Required behaviour
| Concern | Rule |
|---|---|
| Header | Sticky, `text-label` uppercase, `text-tertiary` |
| First column | Fixed when horizontally scrolled — a scrolled row must never become anonymous |
| Column widths | **Fixed, never auto.** Auto-width reflows as data changes, which is the U19 problem. |
| Truncation | Ellipsis, except the displacement warning, which never truncates (§7.3 calls it the most important field) |
| Row height | Per density (`spacing-and-layout.md`) |
| Selection | Checkbox column, shift-click ranges, header select-all scoped to *filtered* rows only |
| Sort | Frozen while a row has focus (U19). Header shows the pin state explicitly. |
| Keyboard | Roving tabindex; `j`/`k`/arrows move, `Enter` expands, `Space` selects, single keys act (U46) |
| Empty | Named cause + next action (U32) |
| Loading | Skeleton rows matching final layout — never a centred spinner, which causes a layout jump |

### Live updates (U19)
```
No focus      → new rows insert in correct order, single arrival flash
Row focused   → order PINNED; arrivals accumulate behind "3 new · press R"
Re-sort       → instant re-render, focus follows the same row by id, that row flashes once
```

### Bulk-eligible selection (U63)

§7.3's bulk confirm re-evaluates five safe-batch predicates server-side (zero displacement · exact dock
match · ETA confidence ≠ LOW · inside operating hours and before `LAST_NEW_START_TIME` · no open
escalation). The table surfaces this without hiding or side-panelling the rows that fail it — those are
often the ones that most need individual attention during a spike.

```
[ Select all eligible (12) ]                    35 pending · 12 bulk-eligible

☑ SHP1014  CRITICAL  ...
☑ SHP1009  HIGH      ...
☐ SHP1013  NORMAL    ...   ← checkbox disabled, greyed
                              tooltip: "ETA confidence is LOW — needs individual review"
☑ SHP1002  NORMAL    ...
```

- **The button is the primary interaction**, not manual multi-select — one click selects exactly the safe
  batch and states the count. This is what makes bulk confirm actually fast rather than merely possible.
- **Ineligible rows stay visible in place**, checkbox disabled, with the specific failing predicate as the
  disabled control's tooltip — a planner learns the rule from the row itself rather than a separate legend.
- Manual selection remains available on top of the auto-selected batch — a planner may deselect an
  eligible row they want to review individually, but may **never** select an ineligible one; the checkbox
  is disabled, not merely unchecked.
- The eligible count **recomputes live** as new requests arrive, following the same frozen-while-focused
  rule as row order (U19) — the batch a planner is about to confirm must not silently grow or shrink
  between their click on "Select all eligible" and their click on Confirm.

---

## 7. App shell

### Icon rail (U39)
- 56px fixed; expands to 240px **as an overlay** on hover/focus — never pushes content, since reflow under
  the cursor is the U19 failure again.
- Active item: 2px inner accent bar, not a background fill.
- Destinations filtered by role (U29). A carrier user has no ops destination in the DOM at all, not merely
  hidden.
- 4px facility accent stripe on the outer edge (U40).
- Keyboard: `Tab` reaches the rail, arrows move within, `Cmd/Ctrl+B` toggles pinned-expanded.

### Top bar
56px. Facility switcher (left) · global search (centre) · notifications, help, user menu (right).

### Facility switcher (U40)
- Combobox showing current facility name always — never an icon alone.
- Search-filterable; 6 facilities now, designed for more.
- Changing facility **clears row focus and any pending selection**, so a stale selection cannot be acted
  on in a new context.

### Status bar (U43)
28px. Connection state · last sync · active facility · pending count · policy version.
Connection state carries an icon and text, never a coloured dot alone.

---

## 8. Toast (U45)

Bottom-left, max 3 stacked, older collapse to "+2 more".

| Type | Duration | Dismissible |
|---|---|---|
| `undo` | 5s with a visible depleting bar | Acting dismisses |
| `info` | 4s | Yes |
| `success` | 4s | Yes |
| `error` | **Persists** until dismissed | Yes |

- `z-toast` sits **above modals** — a time-boxed undo that can be hidden is no undo.
- `role="status"` for info/success, `role="alert"` for errors.
- Never carries the only copy of important information; a toast is a confirmation, not a record.

---

## 9. Undo affordance (U41)

Replaces confirmation modals for Confirm and Reject.

```
┌──────────────────────────────────────────┐
│ Confirmed SHP1014 · Dock D1 13:00        │
│ ▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░  [ Undo ]            │
└──────────────────────────────────────────┘
```

**The mechanism matters:** the database write happens immediately, but **the driver notification is queued
and only dispatched when the window closes**. The irreversible act is the message to a person, not the
row update — so that is what is delayed.

- 5 seconds, linear depleting bar.
- Undo restores the prior state and **cancels the queued notification silently** — the driver never learns
  it nearly happened.
- Multiple undos stack independently; each has its own window.
- After the window closes, reversal is still possible but becomes a *new* action with its own notification.

---

## 10. Modal, drawer, popover

Used sparingly. Per U41 there are **no confirmation modals** for the planner's routine actions.

| Component | Use for | Width |
|---|---|---|
| `modal` | Blocking, single-decision — policy publish, destructive admin actions | 480 / 640 / 800px |
| `drawer` | Contextual detail alongside the list — driver conversation thread | 400px right |
| `popover` | Small transient — filters, column visibility, date picker | auto |

Required (Radix supplies these): focus trap, focus restore on close, `Escape` dismisses, `aria-modal`,
scroll lock, initial focus on the first interactive element — never on a destructive button.

Modal scrim is flat `rgba(15,23,42,0.5)` light / `rgba(0,0,0,0.65)` dark. **No blur** — see
`elevation-and-depth.md`.

---

## 11. Reject flow (U42, U55)

Follows the UK DfE "reasons for rejection" structure — category → detail → preview.

```
┌────────────────────────────────────────────────┐
│ Reject request · SHP1014                       │
│                                                │
│ Reason                                         │
│  ○ Capacity        ○ Rule violation            │
│  ● Priority conflict                           │
│  ○ Safety review   ○ Data conflict             │
│                                                │
│ Internal note (never shown to the driver)      │
│  ┌──────────────────────────────────────────┐  │
│  └──────────────────────────────────────────┘  │
│                                                │
│ ── The driver will receive ──────────────────  │
│  "A higher-priority load needed that dock      │
│   time. Here are the next available options."  │
│                                                │
│         [ Cancel ]    [ Send rejection ]       │
└────────────────────────────────────────────────┘
```

**The preview is not optional.** Nobody sends copy they have not read — that is the entire point of a
controlled vocabulary (§7.3). Per the DfE lesson (U55), each reason is worded to tell the recipient what
happens next, not merely what was wrong.

A rejection is **never the last message in a thread** — alternatives or an escalation route always follow.

---

## 12. Form controls

Standard set: text input, textarea, select, combobox, checkbox, radio, toggle, date/time picker,
**segmented control**.

### Shared rules
- **Labels are always visible.** Never placeholder-as-label — it disappears exactly when a stressed user
  needs it.
- Error text sits **below** the field, with `aria-describedby` and a `circle-alert` icon. Never colour alone.
- Required fields marked on the label, not by absence of "optional".
- **Validate on blur, not on keystroke.** Validating mid-typing tells someone their half-entered ETA is
  wrong.
- **Time inputs use 24-hour, always** (`voice-and-tone.md`).
- Numeric inputs use `--font-data` with `tabular-nums`.

### Segmented control

**Added 2026-08-22** — found missing during the mockup gate pass: two screens (the driver/gate device-view
switch and the admin policy-tier filter) needed one, built ad hoc from existing tokens, with no entry in
this file to check against or reuse from next time.

**When to use it, and when not to**: a segmented control is for switching between **2–4 mutually exclusive
views of the same data**, all valid at once, selection visible at a glance — not for a form field's value
(that's `radio`, which supports more options and a per-option help text row) and not for navigation between
different destinations (that's tabs, `components.md` §7's top bar / rail pattern).

**Anatomy**: a single-row, one-piece container — `surface-base` fill, `border-subtle` 1px border,
`radius-md` (6px). Segments sit inside with no gap and no individual border; the selected segment gets a
`surface-raised` fill radius-inset by 2px from the container so its corners never collide with the
container's own radius, `text-primary` at weight 600. Unselected segments are `text-secondary` at weight
500, transparent fill.

**States**:
| State | Treatment |
|---|---|
| Selected | `surface-raised` fill, `text-primary`, weight 600 — the visual "chip" that reads as one physical position |
| Unselected | Transparent, `text-secondary`, weight 500 |
| Hover (unselected) | `surface-hover` fill — background only, no scale, no lift |
| Focus | `shadow-focus` two-ring on the segment, not the container |
| Disabled | `interactive-disabled-text`, whole segment non-interactive, paired with a tooltip stating why (U32) |

**Interaction and ARIA**: `role="radiogroup"` on the container, `role="radio"` + `aria-checked` on each
segment, roving `tabindex` (selected segment is `0`, the rest `-1`) so arrow keys move the selection the
way a native radio group does. Never a bare set of `<button>`s with a shared visual style and no group
semantics — a sighted user reads the selected fill as a state; a screen-reader user needs the same fact
asserted, not implied.

---

## 13. Empty, loading and error states (U32)

Every one names a cause and a next action.

### Anatomy
```
        [ icon, 32px, text-tertiary ]

           What is true right now
      One line explaining why, if useful

            [ The next action ]
```

| Situation | Copy | Action |
|---|---|---|
| Empty queue (caught up) | "No pending requests." | "New ones appear here automatically." |
| Empty queue (unprovisioned) | "This facility has no requests yet." | See *First-run vs. caught-up*, below |
| Empty search | "No shipment matches 'RJ14'." | [ Clear search ] |
| Load failed | "Couldn't load the queue — usually a connection problem." | [ Retry ] |
| Write failed | "That didn't save. **Nothing has changed.**" | [ Try again ] |
| No permission | "This facility isn't in your access scope." | [ Switch facility ] |

**"Nothing has changed" on a failed write is essential.** In a system where a click commits capacity, a
user must know a failure left no partial state.

### First-run vs. caught-up (U74)

The same visual emptiness means two opposite things, and showing the wrong one makes a working system
look broken:

| | **Caught up** | **Nothing yet** |
|---|---|---|
| **When** | A facility/carrier with history, currently at zero | A newly provisioned facility, a brand-new carrier account, a role with no data yet |
| **Icon** | `circle-check-big` (`iconography.md`) | `inbox` |
| **Copy** | "No pending requests. New ones appear here automatically." | "This facility has no requests yet. Once shipments start arriving, they'll show up here." |
| **Tone** | Reassuring — this is a good state | Neutral/informational — this is an expected state, not a problem |
| **Action** | None needed — no CTA | Admin-scoped: link to facility setup, if the viewer has permission |

**Distinguishing signal**: caught-up is any surface where the underlying entity (facility, carrier,
shipment set) has **prior history** — at least one past record, even if none are currently active.
Nothing-yet is the absence of history entirely. This is a data check, not a guess, and it must be made
server-side and passed to the client rather than inferred from "count is zero" alone.

### Route loading (U71)

The app shell (rail, top bar, status bar) **never unmounts** on navigation — only the content region shows
a loading state, and `motion.md` already makes the route *transition* itself instant. What loads is data,
not the shell.

- **Per-destination skeleton**, matching that destination's final layout — the planner queue skeleton
  looks like rows, the dock board skeleton looks like lanes, never a generic centred spinner.
- No global progress bar. A skeleton that appears immediately is sufficient signal; a progress bar adds a
  second loading indicator for the same event without adding information.
- If a route's data load exceeds ~3s, the skeleton is joined by the standard load-failed pattern's retry
  affordance rather than spinning indefinitely.

### Full-page states (U72)

Three additions, distinct from the inline empty/error states above because they replace the entire
content region, not a component within it.

**404 — resource not found**
```
        [ map-pin-off, 32px ]

    That shipment doesn't exist, or isn't
    somewhere you have access to see.

         [ Back to your queue ]
```
Deliberately **the same message** whether the resource genuinely doesn't exist or exists outside the
viewer's scope — see `auth-and-scoping.md`'s scope-failure section for why conflating these two cases is
correct, not vague.

**Error boundary — unexpected failure**
```
        [ octagon-alert, 32px ]

    Something broke loading this. The rest
    of the app is unaffected.

    [ Try again ]    [ Report this ]
```
**Scoped per region, never whole-app.** The dock board, the queue, and the co-pilot sidebar each have
their own boundary — a crash in one must not take the others down, since a planner mid-decision on the
queue should not lose that queue because the dock board threw. "Report this" attaches the region name and
a trace id, never a full stack trace to the end user.

**Maintenance**
```
        [ wrench, 32px ]

    SetuHaul Dock Command is being updated.
    Expect this to take about 15 minutes.

    Anything you were doing has been saved —
    just come back and pick up where you left off.
```
Not hypothetical: `SOLUTION_DESIGN.md` §9.3's live-database migration (the `text`→`timestamptz`
conversion, the `dock_occupancy` backfill) is a planned event this page announces. Always states an
estimated duration and reassures about saved state — a maintenance page that doesn't say how long reads as
indefinite, which is worse than the wait itself.

Loading uses **skeletons matching the final layout**, never centred spinners — a spinner followed by
content is a layout jump, and a jump under a cursor is a mis-click.

**Implementation technique (U78):** render the real content **invisible** (`visibility: hidden`, not
`display: none`) so it holds its true layout dimensions, then overlay a pulsing block at
`absolute inset-0 rounded-[inherit] animate-pulse` using the surface's own muted token. This needs no
`ResizeObserver`, no manual height measurement, and automatically inherits whatever token the surface is
already using — a skeleton row is exactly the shape of the real row because it *is* the real row, just
invisible with a pulse drawn over it.

---

## 14. Stat tile (U66)

One component for every "a label, a number, maybe a trend" need in the product — the status bar's pending
count, the planner's queue-depth metric, the carrier's on-time sparkline. Built once so three surfaces
don't each invent a slightly different way to show a number.

### Anatomy
```
┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ Pending           │   │ Queue depth       │   │ On-time          │
│ 14                │   │ 8    ▁▂▃▅▃▂▁      │   │ 94%  ▲2%          │
└──────────────────┘   └──────────────────┘   └──────────────────┘
   label + value          + inline sparkline      + delta
```

| Slot | Required? | Notes |
|---|---|---|
| Label | Always | `text-label`, `text-tertiary` |
| Value | Always | `text-h3`, `--font-data`, `tabular-nums` |
| Delta | Optional | Small, coloured only via `feedback-*` tokens (`color.md`) — never promise-state hues |
| Sparkline | Optional | Load the `dataviz` skill when specifying the sparkline's own form and colour — this component only reserves the slot |

### Rules
- **The delta is feedback, not state** — it uses `feedback-success`/`feedback-danger` per `color.md`'s
  existing collision rule, never a promise-state hue, and never appears in a promise-state chip's position.
- No stat tile in this product renders more than one sparkline. If a metric needs comparison across
  several series, that is a chart, not a stat tile, and is out of scope per U33's "charting is minimal."
- Density-aware (`spacing-and-layout.md`) — the status-bar instance is `compact` and shows label+value
  only, no sparkline; the carrier portal instance runs `comfortable` and can show all three slots.

---

## 15. Contextual help affordance (U73)

No FAQ surface exists in this product (U73) — help arrives at the point of confusion instead.

### Anatomy
```
PENDING CONFIRMATION ⓘ
                      └─ on hover/focus/tap:
                         ┌─────────────────────────────────┐
                         │ The warehouse hasn't confirmed   │
                         │ this yet. A planner will decide  │
                         │ before the deadline shown above. │
                         └─────────────────────────────────┘
```

- A small `circle-help` (`iconography.md`) affordance, `icon-xs`, placed immediately after the element it
  explains — never floating separately.
- **Content is state-specific, drawn from the same copy source as `voice-and-tone.md`'s state templates.**
  This is not a generic tooltip system; it explains *this* promise state, *this* ambiguous field — never a
  paragraph of general product help.
- Two hosts in this product: the promise-state chip (driver-facing, plain language) and ambiguous planner
  fields like the displacement check or a truncated receipt term (internal-facing, terse).
- Popover pattern from `components.md` §10 — `Escape` dismisses, never modal, never blocks interaction with
  anything else on the page.
- **Never the only place a fact is stated.** The help affordance clarifies; it does not carry information
  that exists nowhere else, since a driver who doesn't discover it must not be missing something essential.

---

## 16. Escalation stepper (U60)

§7.4's lifecycle — `OPEN → ACKNOWLEDGED → IN_PROGRESS → RESOLVED`, plus `CANCELLED` — rendered as a
compact horizontal stepper, deliberately separate from the SLA clock beside it.

### Anatomy
```
●───●───○───○     Owner: Neha Bansal          ⏱ 8m remaining
OPEN  ACK  IN PROG  RESOLVED
```

| Element | Encoding |
|---|---|
| Steps | Neutral filled/outline dots — **no hue**. Filled = passed or current, outline = not yet reached. |
| Owner | Avatar + name, or "Unowned" in `feedback-warning` colour — an escalation with no owner is a correctness gap the design should make visible, per `SOLUTION_DESIGN.md` §7.4 ("An escalation with no owner is just a list") |
| SLA clock | The **only** danger-coloured element here — `escalation-sla-ok`/`-warning`/`-breach` (`color.md`) |
| Cause | One line beneath, using the matching icon from `iconography.md`'s Escalation reason table |

### Rules
- **Deliberately does not reuse the priority value-ramp or the promise-state chip's colours.** Lifecycle
  position, urgency, and promise state are three different facts about three different things, and this
  product's whole colour discipline rests on never letting one encoding answer a question it wasn't
  designed for.
- `CANCELLED` renders as a fifth, greyed terminal state replacing the stepper entirely — a cancelled
  escalation never shows a partially-filled progress trail, which would misleadingly suggest work in
  progress.
- Compact variant (queue row) shows steps + SLA clock only; full variant (detail view) adds owner and cause.

---

## 17. Capacity-incident row (U65)

§7.4's cascade rule — "one incident, not N escalations" — encoded as an interface property: a single
dock/facility event affecting several shipments **cannot be presented as several identical rows**, because
the UI never renders it that way.

### Anatomy
```
▶ 🔌 Capacity incident · DOCK-JAI-D3 breakdown · 09:15–13:00
   4 shipments affected                                    [ Review incident ]

   (expanded)
   ▼ 🔌 Capacity incident · DOCK-JAI-D3 breakdown · 09:15–13:00
      SHP1005  CRITICAL  ...
      SHP1009  HIGH      ...
      SHP1013  NORMAL    ...
      SHP1014  CRITICAL  ...
                                                             [ Review incident ]
```

### Rules
- **One row per incident, always**, regardless of how many shipments it affects. The affected-count is
  part of the collapsed row's primary text, not a badge easy to miss.
- Expanding reveals the individual shipments **read-only** — they carry their usual priority marker and
  identity, but no individual affordances (§16's five actions). Acting happens through **"Review
  incident,"** which routes to the sequencer's proposal for that incident (§5.1, `SOLUTION_DESIGN.md`),
  never through confirming/rejecting shipments one at a time out of an incident.
- Icon is `network` (`iconography.md`, shared with `CAPACITY_EVENT_CASCADE`'s escalation-reason icon,
  deliberately — it is the same underlying fact viewed from two surfaces).
- **The row never collapses on its own** once created — it persists until the incident is resolved via the
  sequencer flow, so a planner cannot lose track of an active incident by it silently reverting to
  individual rows.

---

## 18. Unavailability taxonomy (U83)

Four distinct reasons a control can be unavailable, not one "disabled" state. Cross-referenced from
`auth-and-scoping.md`'s scope-failure and inference-risk rules, since the choice between two of these four
is a data-leak decision, not a styling one.

| | Meaning | Screen reader | Visual | Explains itself |
|---|---|---|---|---|
| **Disabled** | Temporarily unavailable pending a prerequisite | Not exposed as interactive | `interactive-disabled-*` tokens (`color.md`), reduced contrast | Tooltip on hover/focus (Button §1) |
| **Inactive** | Looks unavailable, but stays keyboard-reachable | **Fully focusable and operable** | Meets normal contrast — deliberately does *not* look as faded as Disabled | Activating it opens an explanation (dialog, inline message), rather than doing nothing |
| **Read-only** | Content matters more than interaction | Reads as plain content | **Zero interactive affordance** — no hover state, no focus ring, no accent colour, no cursor change | N/A — it was never a control |
| **Hidden** | Outside the viewer's permission scope | Absent from the DOM entirely | Nothing renders | N/A — nothing to explain |

### Rules

- **Scope-denied is always Hidden, never Disabled.** A greyed-out "Reassign to Facility B" button tells a
  carrier or a facility-scoped user that Facility B *exists* and that reassignment is a thing the product
  can do — exactly the kind of structural leak `auth-and-scoping.md`'s inference-risk rule already forbids
  for data, now stated for controls. If a user cannot act on something because of *scope*, it does not
  render. If they cannot act because of a *temporary product state* (still loading, prerequisite not met
  yet), it renders Disabled with an explanation.
- **Use Inactive, not Disabled, for anything a driver or planner needs to understand *why* is unavailable
  right now.** The clearest case in this product: a `HELD` option card whose hold has lapsed, or a request
  a planner is looking at that another planner just confirmed. A dead, unfocusable grey rectangle gives no
  feedback at all — the control must stay reachable and, on activation, say what happened and what to do
  next (the same `voice-and-tone.md` negative-path templates already written for these events). This
  matters most on the **gate kiosk**: outdoors, low contrast, in sunlight, a Disabled control is
  indistinguishable from a rendering failure, while Inactive's full-contrast requirement survives glare.
- **The carrier portal is substantially a Read-only surface.** Every field there must carry zero
  interactive affordance — Carbon's rule, adopted verbatim: no hover state, no accent colour, no cursor
  change on anything the carrier cannot act on. A read-only view that *looks* clickable and does nothing
  reads as broken, not as scoped.
- **Disabled is reserved for genuinely temporary, self-resolving states** — a form mid-validation, an
  action waiting on another async step to complete — and is always paired with the reason (Button §1's
  existing rule), never a bare greyed-out control.

---

## 19. Shared queue interaction conventions (U86)

Cross-cutting rules for the queue component `02-ops-exception-console/` and `03-planner-dock-board/` share
(U23), specified here ahead of either surface being written so both inherit the same model rather than
converging on it independently.

### Selection and bulk actions

- **Checkbox column, standard multi-select**: click a row's checkbox to select; shift-click extends a
  range from the last-clicked row; header checkbox selects/deselects all **currently filtered** rows, never
  the full unfiltered set silently.
- **The bulk-eligible pattern (U63) is the primary bulk-select entry point** — "Select all eligible (12)"
  — with manual multi-select available as a secondary path for anything outside the five safe-batch
  predicates.
- Selecting any row surfaces a **contextual action bar**, not a permanently-reserved toolbar row — it
  should not cost vertical space when nothing is selected, which matters on a screen already fighting for
  room under the 7-field-row budget.

### Destructive-action tiering

Not every destructive action deserves the same friction. Three tiers, distinguished by how expensive a
mistake is:

| Tier | Example | Friction |
|---|---|---|
| **Low** | Dismissing a read notification, clearing a filter | None — acts immediately, no confirmation |
| **Moderate** | Reject (§11), Cancel appointment | U41's pattern — acts immediately, 5-second undo, no modal |
| **High** | Admin deleting a dock with future appointments still booked against it, removing a user | **Requires typed confirmation** — the admin types the resource's name or code before the action commits |

This is a necessary correction to reading U41 ("no confirmation modals") as a blanket product-wide rule —
it resolves exactly the Confirm/Reject pair at Moderate tier. A High-tier action in the admin console (§6
of `06-admin-console/`, once written) is a different risk profile and gets Carbon's typed-confirmation
pattern, not an undo toast that would let a genuinely destructive schema-adjacent change slip through on
a misclick.

### Product-wide keyboard map

One vocabulary across every surface with a queue or a dense table, so ops, planner and admin do not
diverge and so the ops co-pilot's composer (`ai-chat-primitives.md`, U57) has an unambiguous boundary for
where its own keystroke capture starts:

| Key | Action | Scope |
|---|---|---|
| `j` / `k` or `↓` / `↑` | Move focus one row | Any dense table |
| `Enter` | Expand/collapse the focused row | Any dense table |
| `Space` | Toggle selection on the focused row | Any dense table |
| `Shift+↓` / `Shift+↑` | Extend selection | Any dense table |
| `C` / `R` / `O` / `H` / `E` | Confirm / Reject / Counter-offer / Hold / Escalate on the focused row | Planner queue only (U46) |
| `Cmd/Ctrl+B` | Toggle the icon rail's pinned-expanded state | Global (`spacing-and-layout.md` §*App shell*) |
| `Escape` | Collapse an expanded row, close a drawer/modal, or exit the co-pilot's composer without sending | Global |

**Single-key actions never fire while focus is inside a text input** (Composer, note fields, search) —
this is what makes `C`/`R`/`O`/`H`/`E` safe to leave unmodified rather than requiring `Cmd/Ctrl+`.
