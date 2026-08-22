# Admin console — Stitch prompts

> Paste-ready prompts for **stitch.withgoogle.com**, translated from this folder's finished spec
> (`screens.md`, `components.md`, `flows-and-states.md`, `edge-cases.md`, `accessibility.md`, `mockup.html`)
> and `../00-foundations/`. **No new design decisions are made here** — every value below traces to a
> foundations file. Where the spec was genuinely silent, the prompt says so inline rather than inventing.
>
> **One prompt per block, in `screens.md`'s own order.** Each block is deliberately self-contained
> (tokens repeated in full) because Stitch sessions do not share context — paste one block, get one screen.
>
> Surface facts that apply to every block: desktop, **`comfortable` density**
> (`spacing-and-layout.md`'s density table lists "Carrier, admin, driver chat" together — confirmed),
> supported range **1024px+, primary target 1440×900**, light theme default with dark at full parity (U69).

---

## 1 · Console shell (four-tab frame)

```text
Design a desktop application shell for an internal admin console.

PRODUCT CONTEXT
SetuHaul Dock Command is a B2B internal operations tool for a logistics company — not a consumer app, no
marketing site, no brand storytelling. This is the admin console: six internal roles across 6 warehouse
facilities are managed from here. Treat this as an "operator tool" aesthetic: calm, dense-capable,
trustworthy — closer to a cockpit instrument than a SaaS landing page. The person using it is at an office
desk, working deliberately, not under time pressure.

LAYOUT
Three regions only:
- Left icon rail: 56px fixed width, full height, background #FFFFFF, 1px right border #E2E8F0. Exactly TWO
  destinations, stacked from the top with a 20px gap and 16px top padding: a console icon (Lucide
  `layout-dashboard`) and a profile icon (Lucide `user`). Active item is marked by a 2px inner accent bar
  in #2563EB, NOT a background fill. Icons are 24px, 2px stroke, colour #64748B; the active one is #2563EB.
- Top bar: 56px tall, background #FFFFFF, 1px bottom border #E2E8F0, 20px horizontal padding. Left: the
  wordmark "Admin" at 16px/700. Then a 20px gap, then four tabs. Right-aligned group with 16px gaps:
  a notifications bell (Lucide `bell`, 20px), a help icon (Lucide `circle-help`, 20px), a settings gear
  (Lucide `settings`, 20px), and a 32px circular avatar filled #2563EB with white initials "AB" at 12px/700.
- Content region: fills the remaining space, background #F8FAFC, 24px padding on all sides.

TABS
Four tabs, in this order: Users · Facility Rules · Policy · Audit. "Users" is active by default.
- Each tab: 8px vertical / 12px horizontal padding, 13px, weight 600, 4px corner radius.
- Inactive: colour #64748B, transparent background.
- Active: colour #2563EB with a #F1F5F9 filled background. Two channels (colour + fill) carry the active
  state — do not rely on colour alone.
- NO badge, count, or dot on any tab. This surface has no "pending work" framing; every tab is a management
  area, not a queue to clear.

TYPOGRAPHY
`Inter` for all UI text — load weights 400/500/600/700 only, nothing else. Chosen specifically for
legibility at 12–14px. Do not substitute a "more distinctive" font — this is a deliberate, locked choice for
functional legibility, not an oversight to fix. `JetBrains Mono` 400/500 for machine-generated values only
(IDs, timestamps, policy numbers).
Scale: 24px/1.33/600 page title · 20px/1.4/600 section heading · 16px/1.5/600 card title ·
14px/1.5/400 body and all table cells (default) · 13px/1.4/400 secondary text ·
12px/1.33/600/0.04em uppercase column headers and chip labels · 11px/1.3/500 metadata (hard floor —
nothing smaller anywhere).

COLOR — light theme (default) then dark
- Page background #F8FAFC light / #020617 dark
- Raised surfaces (cards, panels, table containers) #FFFFFF light / #0F172A dark
- Shell surfaces (rail, top bar) #FFFFFF light / #0F172A dark
- Primary text #0F172A light / #F8FAFC dark
- Secondary text #475569 light / #CBD5E1 dark
- Tertiary text #64748B light / #94A3B8 dark
- Subtle border #E2E8F0 light / #1E293B dark
- Default border #CBD5E1 light / #334155 dark
- Primary action / active state #2563EB light / #3B82F6 dark
Dark mode raises a surface by LIGHTENING it (#020617 base → #0F172A raised), never by adding shadow —
shadow is nearly invisible on dark ground.

SPACING
Base unit 4px; every value is a multiple. 8px and 16px do most of the work; 24px separates sections.
This surface runs `comfortable` density: 44px table rows, 12px vertical / 16px horizontal cell padding,
16px card padding, 12px stack gap, 40px button height, 44px minimum interactive target, 24px content
padding.

ELEVATION AND RADIUS
Shell (rail, top bar) uses a border on its content-facing edge, not a shadow. Cards and panels sit at
elevation tier 1 "Raised": #FFFFFF fill + `0 1px 2px rgba(15,23,42,0.06)` + 1px #E2E8F0 border (dark: #0F172A
fill, no shadow, 1px #1E293B border). Shadows are cool-tinted (`15,23,42` is the neutral-900 value), never
pure black — a black shadow on a slate-tinted surface reads as dirty. Radius: 8px cards, 6px buttons and
inputs, 4px chips and tabs. Nothing exceeds 12px anywhere in this product.

MOTION
Transitions use 200ms with ease-out `cubic-bezier(0.16, 1, 0.3, 1)` — quick and settled, never bouncy.
Route/tab switching is INSTANT with no transition animation. No looping or ambient animation anywhere.
No hover effect that moves an element — colour and border changes only, never lift or scale.

FOCUS
Focus ring is two rings: 2px in the surface colour then 2px in #2563EB (dark: #60A5FA), i.e.
`0 0 0 2px <surface>, 0 0 0 4px #2563EB`. Never a soft glow — a glow disappears against a coloured row.

EXPLICITLY EXCLUDE
- No facility switcher in the top bar. Admin actions span facilities by nature — a user's scope and a
  rule's facility are set per-action, not by a global view filter.
- No facility accent colour stripe on the rail edge (the rest of this product has one; this surface has no
  single active facility to colour it by).
- No global search field in the top bar — each tab carries its own search instead.
- No hero section, banner, marketing copy, tagline, or illustration of any kind.
- No gradients, no glassmorphism, no backdrop blur, no translucency.
- No sidebar navigation beyond the 56px icon rail; no breadcrumb bar.
- No emoji, no exclamation marks, no celebratory or congratulatory treatment anywhere.
- No badge counts or notification dots on the four tabs.
- No dark-only design — produce both themes.
```

---

## 2 · Users tab — list, filters, pending invitations, row menu

```text
Design the Users tab of an internal admin console: a dense user-management table.

PRODUCT CONTEXT
SetuHaul Dock Command, a B2B internal logistics operations tool. This tab is where an administrator sees
every internal user, their role, and which facilities or carrier they are scoped to. Operator-tool
aesthetic: calm, dense-capable, trustworthy. Not a consumer app.

LAYOUT
Inside the app shell (56px left icon rail, 56px top bar with four tabs where "Users" is active), the
content region has 24px padding and contains:

1. A toolbar row, 16px below the top bar, 8px gaps between items:
   [ Filter: role ▾ ]  [ Filter: facility ▾ ]  [ 🔍 Search ————— flexes to fill ]  [ Invite user ]
   - Filter pills: 8px/12px padding, 1px #CBD5E1 border, 4px radius, 12px text, colour #64748B.
   - Search field: flexes to fill remaining width, background #F1F5F9, 4px radius, 8px/12px padding,
     13px text, Lucide `search` icon 16px inline.
   - "Invite user" button: primary/constructive — background #2563EB, white text, 13px/600,
     8px vertical / 16px horizontal padding, 40px height, 6px radius, minimum width 80px.

2. A table, full width, 1px #E2E8F0 row separators, no vertical rules, no zebra striping.
   Columns, left-aligned, fixed widths (never auto — auto-width reflows as data changes):
   Name | Email | Role | Scope | Status | (overflow menu, right-aligned, ~48px)
   - Header row: 12px/600 uppercase, 0.04em letter-spacing, colour #64748B, 12px/16px padding,
     1px #E2E8F0 bottom border. Header is STICKY on scroll.
   - Body rows: 44px tall, 12px vertical / 16px horizontal cell padding, 14px/400 text.
   - Email and any identifier render in `JetBrains Mono` 400 with tabular figures.
   - Row hover: background #F1F5F9 (dark #1E293B). No lift, no scale, no shadow change.

ROWS TO SHOW (use exactly these)
| Neha B.    | neha.bansal@setuhaul.example    | Ops       | Jaipur, Gurugram | Active   | ⋯ |
| Ramesh K.  | ramesh.kumar@setuhaul.example   | Gate/Yard | Jaipur           | Active   | ⋯ |
| Priya S.   | priya.sharma@setuhaul.example   | Gate/Yard | Jaipur           | Inactive | ⋯ |
| —          | amit.d@setuhaul.example         | Ops       | Gurugram         | Invited, awaiting acceptance | Resend  Revoke |

STATUS COLUMN
- "Active": colour #047857 (dark #34D399), weight 600.
- "Inactive": colour #64748B (dark #94A3B8), weight 400. Dim ONLY the status cell — the rest of the row
  stays at full legibility. A whole dimmed row reads as a rendering failure.
- "Invited, awaiting acceptance": a distinct badge — 12px/600, 4px radius, 2px/8px padding, text #B45309 on
  #FFFBEB with a 1px #F59E0B border (dark: #FBBF24 text on #78350F at 25% opacity, border #F59E0B), with
  Lucide `clock-fade` at 14px inline. A pending invitation is not an account state, so it must not look like
  one.
- A pending-invitation row shows the Name cell as an em dash "—" (not yet known), never blank. In this
  product a genuine zero, a not-yet-known value, and a scope-hidden value are three different things and
  must never share a visual treatment.
- The pending row replaces the overflow menu with two inline text buttons: "Resend" and "Revoke", 13px/600,
  transparent background, colour #475569, 8px gap.

ROW OVERFLOW MENU (draw one open, on the "Priya S." row)
Trigger: Lucide `ellipsis`, 20px, colour #64748B, with an accessible label — never a bare icon.
Open menu is a floating panel at elevation tier 3: #FFFFFF fill, `0 4px 12px rgba(15,23,42,0.10)` shadow,
1px #E2E8F0 border, 6px radius, 4px internal padding (dark: #1E293B fill, `0 4px 12px rgba(0,0,0,0.40)`,
1px #334155 border). Items, 36px tall each, 8px/12px padding, 13px:
  Edit
  Reactivate            ← reads "Deactivate" on an active user
  ────────────────────  ← 1px #E2E8F0 divider
  Remove                ← colour #B91C1C (dark #F87171)
"Remove" is separated by the divider because it is the one genuinely hard-to-reverse action here; the other
two are immediate and reversible.

TYPOGRAPHY
`Inter` 400/500/600/700 only — chosen for legibility at 12–14px, a locked choice, not to be substituted.
`JetBrains Mono` 400/500 for emails, IDs and timestamps, so machine-generated values look machine-generated
and align character-for-character down a column.
14px/1.5/400 body and table cells · 13px/1.4/400 secondary · 12px/1.33/600/0.04em uppercase column headers ·
11px/1.3/500 metadata floor.
Hierarchy inside a row comes from weight, colour and font family — NEVER from size. Every cell is 14px.

COLOR (light / dark)
Page #F8FAFC / #020617 · table container #FFFFFF / #0F172A · primary text #0F172A / #F8FAFC ·
secondary #475569 / #CBD5E1 · tertiary #64748B / #94A3B8 · subtle border #E2E8F0 / #1E293B ·
default border #CBD5E1 / #334155 · primary action #2563EB / #3B82F6 · row hover #F1F5F9 / #1E293B ·
destructive text #B91C1C / #F87171.

SPACING — `comfortable` density
4px base unit. 44px row height, 12px/16px cell padding, 16px card padding, 12px stack gap, 40px button
height, 44px minimum interactive target, 24px content padding, 16px toolbar-to-table gap.

RADIUS AND ELEVATION
8px table container, 6px buttons and inputs, 4px filter pills and badges. Table container at tier 1:
#FFFFFF + `0 1px 2px rgba(15,23,42,0.06)` + 1px #E2E8F0 border.

MOTION
200ms ease-out `cubic-bezier(0.16, 1, 0.3, 1)` for hover and menu open; 120ms for focus. Only a row that
has actually just changed animates — settled rows recede in contrast rather than staying visually loud.
No ambient or looping animation.

STATES TO RENDER
Default table · row hover · one row keyboard-focused (2px #FFFFFF ring + 2px #2563EB ring) · overflow menu
open · the pending-invitation row.

EXPLICITLY EXCLUDE
- No bulk-invite action, no CSV user import.
- No "last active" / activity column — not in this product's data model.
- No user avatars or profile photos in the table.
- No zebra striping, no vertical column rules, no coloured row backgrounds.
- No checkbox column or bulk-select bar — nothing on this tab is a batch operation.
- No pagination controls in the design (assume a scrolling table with a sticky header).
- No status shown as a coloured dot alone — status is always a word.
- No icon-only buttons without an accessible label.
- No hero, banner, marketing copy, illustration, gradient, blur or translucency.
```

---

## 3 · Invite / edit user modal (role + scope, one flow)

```text
Design a modal dialog for inviting or editing an internal user in a B2B logistics admin console.

PRODUCT CONTEXT
SetuHaul Dock Command. An administrator invites a colleague and sets BOTH their role and their access scope
in one submission — never "create the account now, assign scope later". A user who exists with a role but no
scope is a security hole, however brief. The same modal handles editing, pre-filled, with different copy.

LAYOUT
Centred modal over a dimmed page. 640px wide, 12px corner radius, elevation tier 4 "Overlay": #FFFFFF fill
with `0 12px 32px rgba(15,23,42,0.14)` (dark: #1E293B fill, `0 12px 32px rgba(0,0,0,0.55)`, 1px #334155
border). Scrim is a FLAT `rgba(15,23,42,0.5)` light / `rgba(0,0,0,0.65)` dark — dimming, never blurring.
This product's shadow language is deliberately restrained; nothing floats without reason.

Internal padding 24px. Structure top to bottom, 16px between blocks:
1. Title "Invite user" at 20px/1.4/600 (edit variant: "Edit user"). No subtitle, no descriptive paragraph.
2. Field: Email — text input.
3. Field: Role — select.
4. Field: Scope — control whose SHAPE depends on the selected role (below).
5. Footer, right-aligned, 8px gap: [ Cancel ] [ Send invite ]  (edit variant: [ Cancel ] [ Save changes ]).

THE SCOPE FIELD — the point of this screen
The scope control changes shape when the Role selection changes, rather than presenting one generic picker
the admin has to interpret correctly per role:
- Ops coordinator / Planner / Gate–Yard officer → multi-select of facilities, rendered as removable chips
  inside the field plus a "+ Add facility" affordance. Chips: 4px radius, #F1F5F9 background, 13px text,
  a Lucide `x` at 14px to remove.
- Carrier manager → a single-carrier select. Exactly one value, no multi-select affordance.
- Administrator → NO scope field at all. It is absent from the layout, not shown disabled — the row that
  assigns scope to everyone else does not itself carry one.
Draw the "Ops coordinator" case as the primary frame, with the field showing two chips: "Jaipur" and
"Gurugram".

FIELDS
- Labels are ALWAYS visible above the field, 13px/500, colour #475569. Never placeholder-as-label — it
  disappears exactly when a stressed user needs it.
- Inputs: 40px height, 1px #CBD5E1 border, 6px radius, 8px/12px padding, 14px text, background #FFFFFF.
- Focus: 2px #FFFFFF ring then 2px #2563EB ring, border becomes #2563EB.
- Required fields are marked on the label, not by the absence of an "optional" note.
- Validate on BLUR, not on keystroke.
- Error text sits BELOW the field with a Lucide `circle-alert` icon at 14px — never colour alone. Error
  colour #B91C1C on #FEF2F2 with a 1px #DC2626 field border (dark: #F87171 text, #7F1D1D at 25% background,
  #EF4444 border).

BUTTONS
- "Send invite" / "Save changes": constructive — #2563EB background, white text, 13px/600, 40px height,
  6px radius, 8px/16px padding, minimum width 80px. Exactly one primary button per view.
- "Cancel": neutral — transparent background, 1px #CBD5E1 border, text #0F172A, same metrics.
- The safer action ("Cancel") comes FIRST in reading and tab order.
- Loading: a spinner replaces the leading icon, the label stays unchanged, and the button width is FROZEN
  so nothing reflows.

TYPOGRAPHY
`Inter` 400/500/600/700 only — a locked legibility choice at 12–14px, not to be substituted.
20px/1.4/600 modal title · 14px/1.5/400 field values · 13px/1.4/500 labels · 13px/1.4/400 error text.
Sentence case everywhere.

COLOR (light / dark)
Modal surface #FFFFFF / #1E293B · primary text #0F172A / #F8FAFC · label text #475569 / #CBD5E1 ·
input border #CBD5E1 / #334155 · focus #2563EB / #60A5FA · primary action #2563EB / #3B82F6 ·
error text #B91C1C / #F87171 on #FEF2F2 / #7F1D1D-at-25% with #DC2626 / #EF4444 border.

SPACING
4px base. 24px modal padding, 16px between field blocks, 8px between a label and its field, 8px between
footer buttons, 24px above the footer.

MOTION
Modal enters at 320ms with ease-out `cubic-bezier(0.16, 1, 0.3, 1)` — a large surface, too fast is jarring.
No spring, no bounce, no overshoot. No looping animation.

FOCUS BEHAVIOUR
Focus lands on the first interactive element (the Email field) when the modal opens — never on a submit or
destructive button. Escape dismisses. Focus returns to the trigger on close.

STATES TO RENDER
Empty/idle · Role = Ops coordinator with two facility chips in Scope · Role = Carrier manager showing the
single-carrier variant · error state on Email reading exactly: "This email already has an account."

EXPLICITLY EXCLUDE
- No multi-step wizard, no progress stepper — role and scope are ONE submission.
- No "invite by link" / "copy invite link" alternative.
- No optional message-to-invitee field, no personal note textarea.
- No permissions matrix or checkbox grid — role is a single select.
- No avatar upload.
- No backdrop blur (flat scrim only), no gradient, no illustration, no marketing copy.
- No exclamation marks, no "Success!" language.
```

---

## 4 · Remove user — typed confirmation dialog

```text
Design a high-consequence typed-confirmation dialog for removing a user from a B2B logistics admin console.

PRODUCT CONTEXT
SetuHaul Dock Command. Removing a user is the one genuinely hard-to-reverse action on the Users tab — the
account does not come back and does not reappear in search. Everywhere else in this product, destructive
actions use a 5-second undo instead of a confirmation modal; this one is a deliberate exception. The dialog
must state exactly what will be lost, including consequences the admin would otherwise discover later.

LAYOUT
Centred modal, 480px wide, 12px corner radius, elevation tier 4 "Overlay": #FFFFFF fill with
`0 12px 32px rgba(15,23,42,0.14)` (dark: #1E293B fill, `0 12px 32px rgba(0,0,0,0.55)`, 1px #334155 border).
Flat scrim `rgba(15,23,42,0.5)` light / `rgba(0,0,0,0.65)` dark — dimming, never blurring.
24px internal padding. Top to bottom, 16px between blocks:

1. Title: "Remove Priya Sharma" — 20px/1.4/600, primary text colour. Not red; the title states the action,
   the button carries the consequence.
2. Consequence block — a visually separated panel, 16px padding, 6px radius, background #FEF2F2, 1px
   #DC2626 border, with a Lucide `alert-triangle` at 20px in #B91C1C. Body text 14px/1.5, colour #B91C1C
   (dark: #F87171 text, #7F1D1D at 25% background, #EF4444 border). Exact copy, as three short lines:
       This account will be removed permanently and will not appear in user search again.
       This user owns 2 active escalations — they will show as unowned once removed.
       Their past actions stay attributable in the Audit tab.
3. Typed-confirmation field:
   - Visible label above the input: "Type priya.sharma@setuhaul.example to confirm"
   - Input: 40px height, 1px #CBD5E1 border, 6px radius, 14px `JetBrains Mono` 400 with tabular figures.
   - This field receives focus automatically when the dialog opens — never the destructive button.
4. Footer, right-aligned, 8px gap, with at least 16px separating the two buttons:
   [ Cancel ]  [ Remove user ]

BUTTONS
- "Cancel": neutral — transparent, 1px #CBD5E1 border, text #0F172A, 40px height, 6px radius, min width
  80px. FIRST in reading and tab order, because it is the safer action.
- "Remove user": destructive — #DC2626 background, white text, 13px/600, 40px height, 6px radius
  (dark: #EF4444 background, #020617 text).
- The destructive button is GENUINELY DISABLED, not merely muted, until the typed value matches exactly:
  background #E2E8F0, text #94A3B8, `cursor: not-allowed` (dark: #1E293B background, #475569 text). While
  disabled it carries a tooltip and an accessible description reading:
  "Type the user's email to confirm" — a disabled control with no stated reason is a dead end.

TYPOGRAPHY
`Inter` 400/500/600/700 only — a locked legibility choice, not to be substituted. `JetBrains Mono` 400 for
the typed email in both the instruction label and the input.
20px/1.4/600 title · 14px/1.5/400 body · 13px/1.4/500 field label · 13px/1.4/600 button labels.
Sentence case. No exclamation marks. Do not apologise for the system rule — state it and offer the exit.

COLOR (light / dark)
Modal surface #FFFFFF / #1E293B · primary text #0F172A / #F8FAFC · secondary #475569 / #CBD5E1 ·
danger text #B91C1C / #F87171 · danger background #FEF2F2 / #7F1D1D at 25% · danger border #DC2626 /
#EF4444 · destructive button #DC2626 / #EF4444 · disabled #E2E8F0 + #94A3B8 / #1E293B + #475569.

SPACING
4px base. 24px modal padding, 16px between blocks, 16px inside the consequence panel, 8px label-to-input,
16px minimum between Cancel and Remove so they cannot be mis-clicked for one another.

RADIUS AND ELEVATION
12px modal, 6px consequence panel and inputs and buttons. Modal at tier 4 as specified above; nothing else
in the dialog carries a shadow.

MOTION
Modal enters at 320ms ease-out `cubic-bezier(0.16, 1, 0.3, 1)`. The disabled→enabled transition on the
destructive button is a 120ms colour change, no movement. No spring, no bounce, no pulsing, no looping
animation.

STATES TO RENDER
Open with the field empty and the destructive button disabled · field filled with a matching value and the
button enabled · a mismatch typed, showing the button still disabled.

EXPLICITLY EXCLUDE
- No "type DELETE in capitals" pattern — the value typed is the user's own email, which forces the admin to
  read who they are removing.
- No checkbox-instead-of-typing shortcut.
- No countdown timer or forced delay before the button enables.
- No undo affordance here — undo is this product's pattern for moderate actions, not for this one.
- No "are you sure?" phrasing, no generic warning template, no apology.
- No red page background, no full-bleed red header, no skull/trash illustration.
- No emoji, no exclamation marks, no blur, no gradient.
```

---

## 5 · Facility Rules tab — rule list

```text
Design the Facility Rules tab of an internal B2B logistics admin console: a table of typed operational
rules per warehouse facility.

PRODUCT CONTEXT
SetuHaul Dock Command. Each rule constrains how dock appointments can be scheduled at one facility — an
early-arrival limit, a dock pinned to refrigerated cargo, a cut-off after which no new unload may start.
Rule types come from a fixed registry; there is no free-text rule anywhere. Operator-tool aesthetic: calm,
dense-capable, trustworthy.

LAYOUT
Inside the app shell (56px left icon rail, 56px top bar with four tabs where "Facility Rules" is active),
the content region has 24px padding:

1. Toolbar, 8px gaps, 16px above the table:
   [ Filter: facility ▾ ] ————————————————————— [ + Add rule ]
   - Filter pill: 8px/12px padding, 1px #CBD5E1 border, 4px radius, 12px text, colour #64748B.
   - "+ Add rule": constructive — #2563EB background, white text, 13px/600, 40px height, 6px radius,
     8px/16px padding, with a Lucide `plus` at 16px.

2. Table, full width, 1px #E2E8F0 row separators, no zebra striping, no vertical rules.
   Columns, fixed widths, left-aligned:
   Facility | Rule type | Value | Effective | (overflow menu, right-aligned)
   - Header: 12px/600 uppercase, 0.04em tracking, colour #64748B, 12px/16px padding, sticky on scroll.
   - Rows: 44px tall, 12px/16px cell padding, 14px/400.
   - "Rule type" renders as an uppercase enum token in `JetBrains Mono` 500 at 13px, colour #0F172A —
     these are registry values, not prose, and should look like it.
   - "Value" renders type-specifically with its unit, space between number and unit: "60 min", "21:00",
     "18,500 kg". Never pluralise a unit symbol. Weight is always kg.
   - Times are 24-hour, always. Ranges use an en dash: "18:00–23:59", never a hyphen.

ROWS TO SHOW (use exactly these)
| Jaipur   | EARLY_LIMIT       | 60 min      | Always                     | ⋯ |
| Jaipur   | DOCK_PIN          | Reefer → D5 | Always                     | ⋯ |
| Jaipur   | NEW_START_CUTOFF  | 21:00       | Weekdays only, 18:00–23:59 | ⋯ |
| Gurugram | WEIGHT_LIMIT      | 18,500 kg   | Always                     | ⋯ |

Where a rule type has a matching icon, pair it inline at 16px before the value: `snowflake` for
refrigerated cargo, `weight` for a weight limit, `box` for standard. Lucide, 2px stroke at every size.

DIGIT FORMATTING
Numbers use `en-IN` locale grouping — 18,500 is correct here, but any larger figure groups as 1,00,000
(lakh), not 100,000. Never hand-build digit grouping. Every number in a column uses tabular figures so the
column aligns.

TYPOGRAPHY
`Inter` 400/500/600/700 only — a locked choice for legibility at 12–14px, not to be substituted.
`JetBrains Mono` 400/500 for rule-type enums, numeric values, times and dock codes.
14px/1.5/400 cells · 13px/1.4/400 secondary · 12px/1.33/600/0.04em uppercase headers · 11px floor.
Hierarchy inside a row comes from weight, colour and font family — never from size.

COLOR (light / dark)
Page #F8FAFC / #020617 · table container #FFFFFF / #0F172A · primary text #0F172A / #F8FAFC ·
secondary #475569 / #CBD5E1 · tertiary #64748B / #94A3B8 · subtle border #E2E8F0 / #1E293B ·
primary action #2563EB / #3B82F6 · row hover #F1F5F9 / #1E293B.
Rule rows carry NO status colour. A rule is not a state — colour in this product is rationed to promise
state and danger, and spending it here would dilute both.

SPACING — `comfortable` density
4px base. 44px rows, 12px/16px cell padding, 40px button height, 24px content padding, 16px toolbar-to-table
gap, 44px minimum interactive target.

RADIUS AND ELEVATION
8px table container at tier 1: #FFFFFF + `0 1px 2px rgba(15,23,42,0.06)` + 1px #E2E8F0 border
(dark: #0F172A, no shadow, 1px #1E293B border). 6px buttons, 4px filter pills.

MOTION
200ms ease-out `cubic-bezier(0.16, 1, 0.3, 1)` on hover, 120ms on focus. No row-reorder animation, no
ambient motion, no hover lift or scale.

STATES TO RENDER
Default table · row hover · one row keyboard-focused with the two-ring focus indicator (2px #FFFFFF then
2px #2563EB).

EXPLICITLY EXCLUDE
- No free-text rule column and no free-text search over rule bodies — rule type is a fixed enum.
- No enable/disable toggle switch per row — effectivity is expressed by the Effective window, not a switch.
- No priority, severity, or status colour-coding on rules.
- No drag-to-reorder handles — rule order is not a user-editable property.
- No "simulate" affordance on this tab. Facility rule changes take effect immediately on save; only policy
  weights are simulated before publishing.
- No checkbox column or bulk-edit bar.
- No zebra striping, no vertical rules, no coloured row backgrounds.
- No hero, banner, illustration, gradient, blur or marketing copy.
```

---

## 6 · Facility rule editor — type-driven fields

```text
Design a form panel for creating or editing one facility rule in a B2B logistics admin console. The
distinctive property: the value fields RENDER PER SELECTED RULE TYPE — there is no generic "value" field.

PRODUCT CONTEXT
SetuHaul Dock Command. Rule types come from a fixed registry. Choosing DOCK_PIN asks for a dock and a cargo
type; choosing EARLY_LIMIT asks for one number of minutes; choosing NEW_START_CUTOFF asks for a time. The
form simply does not render fields that do not apply to the selected type. This is the interface expression
of a backend decision to stop string-matching rule text.

LAYOUT
Centred modal, 640px wide, 12px radius, elevation tier 4 "Overlay": #FFFFFF fill,
`0 12px 32px rgba(15,23,42,0.14)`, (dark: #1E293B fill, `0 12px 32px rgba(0,0,0,0.55)`, 1px #334155 border).
Flat scrim `rgba(15,23,42,0.5)` light / `rgba(0,0,0,0.65)` dark. No blur.
24px padding. Top to bottom, 16px between blocks:

1. Title "Add rule" at 20px/1.4/600 (edit variant: "Edit rule").
2. Facility — select.
3. Rule type — select, showing registry values in `JetBrains Mono` 500: EARLY_LIMIT · DOCK_PIN ·
   WEIGHT_LIMIT · NEW_START_CUTOFF.
4. TYPE-SPECIFIC VALUE BLOCK — a visually grouped region with a 1px #E2E8F0 top border and 16px top padding,
   so it reads as "fields that belong to the choice above". Draw the DOCK_PIN case as the primary frame:
       Dock        [ D5 ▾ ]
       Cargo type  [ Reefer ▾ ]   ← with a Lucide `snowflake` at 16px inline in the option
   Also draw the EARLY_LIMIT variant as a second frame: a single numeric field
       Early arrival limit  [ 60 ] minutes
   with the number in `JetBrains Mono` 400, tabular figures, right-aligned in an 80px-wide input, and the
   unit "minutes" as a 12px #64748B suffix outside the input.
5. Effective window:
   - Defaults to a single value reading "Always" — most rules genuinely are always-on, and forcing every
     rule through a time-bound picker would slow the common case for no benefit.
   - A "Narrow to specific days and hours" disclosure expands to: day-of-week checkboxes (Mon–Sun) plus a
     from/to time-of-day pair in 24-hour format, en dash between them ("18:00–23:59").
6. Footer, right-aligned, 8px gap: [ Cancel ] [ Save rule ]. "Cancel" is first in reading and tab order.

FIELDS
- Labels always visible above the field, 13px/500, colour #475569. Never placeholder-as-label.
- Inputs 40px tall, 1px #CBD5E1 border, 6px radius, 8px/12px padding, 14px.
- Numeric inputs use `JetBrains Mono` with tabular figures, right-aligned.
- Time inputs are 24-hour, always.
- Validate on blur, not keystroke. Error text below the field with a Lucide `circle-alert` at 14px, colour
  #B91C1C on a #FEF2F2 field background with a 1px #DC2626 border — never colour alone.
- Focus: 2px surface ring then 2px #2563EB ring; border becomes #2563EB.

BUTTONS
- "Save rule": constructive — #2563EB background, white text, 13px/600, 40px height, 6px radius,
  min width 80px.
- "Cancel": neutral — transparent, 1px #CBD5E1 border, text #0F172A.
- Loading: spinner replaces the leading icon, label unchanged, width frozen.

TYPOGRAPHY
`Inter` 400/500/600/700 only — a locked legibility choice, not to be substituted. `JetBrains Mono` 400/500
for enum values, numbers, times and dock codes.
20px/1.4/600 title · 14px/1.5/400 values · 13px/1.4/500 labels · 12px/1.33/600/0.04em group label ·
11px floor.

COLOR (light / dark)
Modal surface #FFFFFF / #1E293B · primary text #0F172A / #F8FAFC · label #475569 / #CBD5E1 ·
tertiary #64748B / #94A3B8 · border #CBD5E1 / #334155 · group divider #E2E8F0 / #1E293B ·
focus and primary action #2563EB / #3B82F6 · error #B91C1C / #F87171 on #FEF2F2 / #7F1D1D-at-25%.

SPACING
4px base. 24px modal padding, 16px between blocks, 8px label-to-input, 12px between fields inside the
type-specific group, 24px above the footer.

MOTION
Modal enters at 320ms ease-out `cubic-bezier(0.16, 1, 0.3, 1)`. When the rule-type selection changes and the
value fields swap, the new field group appears at 200ms ease-out — a single, once-only transition, no
staggering, no looping. No spring, no bounce.

STATES TO RENDER
DOCK_PIN selected (dock + cargo type fields) · EARLY_LIMIT selected (one numeric minutes field) ·
Effective window collapsed at "Always" · Effective window expanded showing day checkboxes and a 24-hour
from/to range.

EXPLICITLY EXCLUDE
- No generic free-text "value" field — ever. The registry drives the fields.
- No JSON / code editor / expression builder.
- No fields for rule types other than the one selected, disabled or otherwise — they simply do not render.
- No "simulate this rule" action; rule changes apply immediately on save.
- No priority or severity selector on a rule.
- No calendar month-grid picker for the effective window — it is a day-of-week + time-of-day narrowing,
  not a date range browser.
- No 12-hour times, no AM/PM anywhere.
- No blur, gradient, illustration or marketing copy.
```

---

## 7 · Facility rule edit — dependent-appointment confirmation

```text
Design a typed-confirmation dialog for a facility rule edit that affects appointments already confirmed.

PRODUCT CONTEXT
SetuHaul Dock Command, a B2B logistics dock-scheduling tool. Tightening a rule — moving a "no new unload
starts after" cut-off from 21:00 to 20:00 — can make an already-confirmed 20:30 appointment retroactively
non-compliant. The system deliberately does NOT auto-cancel or auto-flag those appointments; it names the
count before the edit commits and lets the admin decide. The dialog's whole job is to show what it is about
to strand, before committing.

LAYOUT
Centred modal, 480px wide, 12px radius, elevation tier 4 "Overlay": #FFFFFF fill,
`0 12px 32px rgba(15,23,42,0.14)` (dark: #1E293B fill, `0 12px 32px rgba(0,0,0,0.55)`, 1px #334155 border).
Flat scrim `rgba(15,23,42,0.5)` light / `rgba(0,0,0,0.65)` dark — no blur.
24px padding. Top to bottom, 16px between blocks:

1. Title: "Tighten NEW_START_CUTOFF at Jaipur" — 20px/1.4/600, with "NEW_START_CUTOFF" in `JetBrains Mono`
   500 at the same size.
2. Change summary — a two-line before/after, 14px, in `JetBrains Mono` for the values:
       Current   21:00
       New       20:00
   Right-aligned values in a 2-column layout with tabular figures so the digits line up.
3. Consequence panel — visually separated: 16px padding, 6px radius, background #FEF2F2, 1px #DC2626 border,
   Lucide `alert-triangle` at 20px in #B91C1C (dark: #F87171 text, #7F1D1D at 25% background, #EF4444
   border). Exact copy:
       3 already-confirmed appointments start after 20:00 and will no longer comply with this rule.
       They will not be cancelled or rescheduled automatically. This rule governs future scheduling only.
   Below that copy, a compact read-only list of the three affected appointments, 13px, one per line, each
   as: reference in `JetBrains Mono`, then dock, then date, then time — e.g.
       APT-1042 · Dock D4 · Tue 4 Aug · 20:30–21:45
   Every operational time carries its dock AND its date. A time without a date is a wrong-day booking
   waiting to happen. 24-hour clock, en dash for the range, weekday included in the date.
4. Typed-confirmation field:
   - Label: "Type NEW_START_CUTOFF to confirm"
   - Input 40px, 1px #CBD5E1 border, 6px radius, 14px `JetBrains Mono` 400.
   - Receives focus automatically on open — never the destructive button.
5. Footer, right-aligned, 8px gap, 16px minimum between the two buttons:
   [ Cancel ]  [ Apply rule change ]

BUTTONS
- "Cancel": neutral — transparent, 1px #CBD5E1 border, text #0F172A, 40px height, 6px radius. First in
  reading and tab order.
- "Apply rule change": destructive — #DC2626 background, white text, 13px/600, 40px height, 6px radius
  (dark: #EF4444 background, #020617 text). Genuinely disabled — background #E2E8F0, text #94A3B8,
  `cursor: not-allowed` — until the typed value matches, with the reason stated in a tooltip:
  "Type the rule type to confirm".

TYPOGRAPHY
`Inter` 400/500/600/700 only — locked legibility choice, not to be substituted. `JetBrains Mono` 400/500 for
the rule-type enum, times, dates, references and dock codes.
20px/1.4/600 title · 14px/1.5/400 body · 13px/1.4/400 affected-appointment lines · 13px/1.4/500 field label.
Sentence case, terse and factual — this is an internal surface, no reassurance, no apology.

COLOR (light / dark)
Modal #FFFFFF / #1E293B · primary text #0F172A / #F8FAFC · secondary #475569 / #CBD5E1 ·
danger text #B91C1C / #F87171 · danger background #FEF2F2 / #7F1D1D at 25% · danger border #DC2626 /
#EF4444 · destructive button #DC2626 / #EF4444 · disabled #E2E8F0 + #94A3B8 / #1E293B + #475569.

SPACING
4px base. 24px modal padding, 16px between blocks, 16px inside the consequence panel, 8px between affected-
appointment lines, 16px minimum between Cancel and the destructive button.

MOTION
Modal enters at 320ms ease-out `cubic-bezier(0.16, 1, 0.3, 1)`. Disabled→enabled on the destructive button
is a 120ms colour change, no movement. No pulsing, no looping, no bounce.

STATES TO RENDER
Open with the field empty and the button disabled · field matching and the button enabled.

EXPLICITLY EXCLUDE
- No "cancel the affected appointments too" checkbox or bulk action — this dialog does not reach into
  appointments at all.
- No auto-escalation offer, no "notify the affected drivers" toggle.
- No red page background or full-bleed red header — the panel carries the danger colour, the page does not.
- No countdown or forced delay.
- No generic "Are you sure? This cannot be undone." copy — say the actual number and the actual consequence.
- No emoji, exclamation marks, blur, gradient or illustration.
```

---

## 8 · Policy tab — weight editor and fairness Danger Zone

```text
Design the Policy tab of a B2B logistics admin console: a numeric coefficient editor for the ranking policy
that every future scheduling decision is scored against.

PRODUCT CONTEXT
SetuHaul Dock Command. These weights decide which driver gets which dock slot when several compete. Getting
them wrong is expensive at scale, so nothing here saves on its own — the whole editor is a staging area,
and values only reach the system through a separate simulate-then-publish flow. One field, the fairness
term, is singled out as a business-risk decision rather than routine tuning and gets its own gated
treatment. Operator-tool aesthetic: precise, quiet, instrument-like.

LAYOUT
Inside the app shell (56px left icon rail, 56px top bar with four tabs where "Policy" is active), the
content region has 24px padding and a single column capped at roughly 800px:

1. Current-version header — read-only, 13px, colour #64748B, with a 1px #E2E8F0 bottom border and 12px
   bottom padding, 20px below it:
       Current policy: v3 · published 2026-08-11 · Anshul G.
   The version number and date render in `JetBrains Mono` 400. This stays visible above the editor so the
   admin can always see what they are changing FROM.

2. Priority tiers — read-only, presented as a labelled row, not inputs. Zero interactive affordance: no
   hover state, no focus ring, no cursor change, no accent colour. These are the priority tiers themselves,
   not tuning coefficients.
       Priority weights    CRITICAL 4000   HIGH 3000   NORMAL 2000   LOW 1000
   Values in `JetBrains Mono` 500, tabular figures.

3. Editable weight rows — five of them, each a horizontal row with 8px vertical padding, 12px gaps:
       [ label, 220px wide, 14px/600 ]  [ input, 80px wide ]  [ unit suffix, 12px #64748B ]
   Exactly these five, in this order and with these values and units:
       Lateness (w_lateness)      [   4 ]  /min, cap 720
       Wait (w_wait)              [  -6 ]  /min
       Slack (w_slack)            [   1 ]  /min, cap 120
       Dock mismatch (P_dock)     [ -25 ]
       Churn (P_churn)            [  30 ]  weighted-min-equivalent per moved promise
   Inputs: 36px tall, 80px wide, 1px #CBD5E1 border, 4px radius, 8px horizontal padding, RIGHT-ALIGNED text
   in `JetBrains Mono` 400 with tabular figures. Every field has a visible label AND a visible unit — never
   a bare number.

4. Fairness term — a DANGER ZONE panel, visually separated from the routine fields above it by 16px margin
   and a distinct border colour. 16px padding, 6px radius, background #FFFBEB, 1px #F59E0B border
   (dark: #FBBF24 text, #78350F at 25% background, #F59E0B border). Lucide `alert-triangle` at 20px in
   #B45309. Exact copy:
       Heading, 13px/700, colour #B45309:
         Fairness term (w_fairness) — currently disabled (0)
       Body, 13px/1.5, colour #475569:
         Enabling this is a business-risk decision, not routine tuning — see the carrier-concentration
         canary.
       Then a neutral button: [ Enable fairness term ] — transparent background, 1px #CBD5E1 border,
       text #0F172A, 40px height, 6px radius.
   The visual separation IS the signal that this field is different. A note buried in copy would be skimmed
   past.

5. Primary action, 24px below the danger panel, left-aligned:
       [ Simulate against last 30 days ] — constructive: #2563EB background, white text, 13px/600,
       40px height, 6px radius, 8px/16px padding.

TYPOGRAPHY
`Inter` 400/500/600/700 only — a locked choice for legibility at 12–14px, not to be substituted.
`JetBrains Mono` 400/500 for EVERY numeric policy value, with tabular figures — these are precise values
that every future decision gets stamped with; they must read as data, not prose.
14px/1.5/600 field labels · 14px/1.5/400 body · 13px/1.4/400 secondary and unit suffixes ·
13px/1.4/700 danger-panel heading · 12px/1.33/600/0.04em any uppercase label · 11px floor.

COLOR (light / dark)
Page #F8FAFC / #020617 · panel surface #FFFFFF / #0F172A · primary text #0F172A / #F8FAFC ·
secondary #475569 / #CBD5E1 · tertiary #64748B / #94A3B8 · input border #CBD5E1 / #334155 ·
divider #E2E8F0 / #1E293B · primary action #2563EB / #3B82F6 ·
danger-zone background #FFFBEB / #78350F at 25% · danger-zone text #B45309 / #FBBF24 ·
danger-zone border #F59E0B / #F59E0B.

SPACING — `comfortable` density
4px base. 24px content padding, 20px below the version header, 8px vertical padding per weight row, 12px
between a label, its input and its unit, 16px above the danger panel, 16px inside it, 24px above the
Simulate button.

RADIUS AND ELEVATION
8px on any card, 6px on the danger panel and buttons, 4px on the small numeric inputs. Panels sit at tier 1
"Raised": #FFFFFF + `0 1px 2px rgba(15,23,42,0.06)` + 1px #E2E8F0 border. Restrained shadow language —
nothing floats without reason.

MOTION
200ms ease-out `cubic-bezier(0.16, 1, 0.3, 1)` on hover and focus transitions; 120ms on focus rings.
No number count-up animation — these are values, not scores. No ambient or looping animation. No hover lift
or scale.

FOCUS AND ACCESSIBILITY
Focus ring is 2px surface then 2px #2563EB. Every numeric field's label and unit are announced together
("Lateness weight, per minute, 4"), never a bare number.

STATES TO RENDER
Default editor · one numeric field focused · the fairness danger panel in its disabled/default state.

EXPLICITLY EXCLUDE
- No sliders, dials, gauges or steppers for the weights. These are exact numeric values typed by an admin,
  and a slider implies a smooth tolerance that does not exist.
- No "Save" or "Apply" button on the editor, and no autosave indicator. Nothing here commits without going
  through simulate-then-publish.
- No charts, graphs or visualisations of weight impact on this tab.
- No preset/template picker ("balanced", "aggressive").
- No reset-to-defaults button.
- No toggle switch for the fairness term — it is a gated action button, not a switch a cursor can slip onto.
- No editable inputs on the priority tiers row.
- No hero, banner, illustration, gradient, blur, emoji or exclamation marks.
```

---

## 9 · Enable fairness term — Danger Zone typed confirmation

```text
Design a typed-confirmation dialog for enabling a business-risk policy term in a B2B logistics admin
console.

PRODUCT CONTEXT
SetuHaul Dock Command. The fairness term redistributes dock-slot ranking away from pure urgency and toward
carrier balance. Every other coefficient in the same editor is routine tuning; this one is singled out as a
business decision with a real downside. Enabling the TERM and publishing a policy that uses a non-zero value
remain two separate steps — this dialog does the first only. It publishes nothing.

LAYOUT
Centred modal, 480px wide, 12px radius, elevation tier 4 "Overlay": #FFFFFF fill,
`0 12px 32px rgba(15,23,42,0.14)` (dark: #1E293B fill, `0 12px 32px rgba(0,0,0,0.55)`, 1px #334155 border).
Flat scrim `rgba(15,23,42,0.5)` light / `rgba(0,0,0,0.65)` dark. No blur.
24px padding. Top to bottom, 16px between blocks:

1. Title: "Enable the fairness term" — 20px/1.4/600.
2. Stakes panel — visually separated: 16px padding, 6px radius, background #FFFBEB, 1px #F59E0B border,
   Lucide `alert-triangle` at 20px in #B45309 (dark: #FBBF24 text, #78350F at 25% background, #F59E0B
   border). Copy, 13px/1.5, stating the actual business stakes rather than a generic warning:
       This changes how every future ranking decision balances urgency against carrier concentration.
       Watch the carrier-concentration canary after publishing — if the data turns ugly, set the weight
       back to 0.
3. What this does and does not do — plain body text, 14px/1.5, colour #475569:
       Enabling makes w_fairness editable in the weight editor. It does not publish anything.
       Any non-zero value still has to be simulated and published like every other weight.
4. Typed-confirmation field:
   - Label: "Type ENABLE FAIRNESS to confirm"
   - Input 40px tall, 1px #CBD5E1 border, 6px radius, 14px `JetBrains Mono` 400.
   - Receives focus automatically on open — never a submit or destructive button.
5. Footer, right-aligned, 8px gap, 16px minimum between the buttons:
   [ Cancel ]  [ Enable fairness term ]

BUTTONS
- "Cancel": neutral — transparent, 1px #CBD5E1 border, text #0F172A, 40px height, 6px radius. First in
  reading and tab order.
- "Enable fairness term": cautionary rather than destructive, because this escalates risk rather than
  ending something for someone else — background #FFFBEB, 1px #F59E0B border, text #B45309, 13px/600,
  40px height, 6px radius (dark: #78350F at 25% background, #F59E0B border, #FBBF24 text).
- Genuinely disabled until the typed value matches: background #E2E8F0, text #94A3B8,
  `cursor: not-allowed`, with the reason in a tooltip: "Type ENABLE FAIRNESS to confirm".

TYPOGRAPHY
`Inter` 400/500/600/700 only — locked legibility choice, not to be substituted. `JetBrains Mono` 400 for the
confirmation phrase and for `w_fairness`.
20px/1.4/600 title · 14px/1.5/400 body · 13px/1.5/400 stakes copy · 13px/1.4/500 field label.
Sentence case. No exclamation marks. Terse and factual — internal surface, no reassurance.

COLOR (light / dark)
Modal #FFFFFF / #1E293B · primary text #0F172A / #F8FAFC · secondary #475569 / #CBD5E1 ·
warning text #B45309 / #FBBF24 · warning background #FFFBEB / #78350F at 25% ·
warning border #F59E0B / #F59E0B · disabled #E2E8F0 + #94A3B8 / #1E293B + #475569.
Note the deliberate distinction: this dialog is AMBER, not red. Red in this product means danger — expiry,
conflict, an action that ends something for another person. Enabling a policy term is a risk decision, not
a destruction.

SPACING
4px base. 24px modal padding, 16px between blocks, 16px inside the stakes panel, 8px label-to-input,
16px minimum between Cancel and the confirm button.

MOTION
Modal enters at 320ms ease-out `cubic-bezier(0.16, 1, 0.3, 1)`. Disabled→enabled is a 120ms colour change,
no movement. No pulsing, no looping, no bounce, no overshoot.

STATES TO RENDER
Open with the field empty and the button disabled · field matching and the button enabled.

EXPLICITLY EXCLUDE
- No publish action in this dialog — it enables a field, nothing else.
- No slider or numeric input for the fairness value here; the value is set afterwards, in the ordinary
  weight editor.
- No "learn more" link to documentation, no help-centre article — the stakes are stated inline.
- No red treatment (this is amber), no skull/warning-triangle illustration beyond the single 20px icon.
- No generic "Are you sure?" copy, no apology.
- No emoji, exclamation marks, blur, gradient or marketing copy.
```

---

## 10 · Policy simulation — running, result, stale, published

```text
Design the simulation result panel for a policy weight change in a B2B logistics admin console, in four
states.

PRODUCT CONTEXT
SetuHaul Dock Command. Before publishing new ranking weights, an admin replays them against the last 30 days
of real scheduling decisions. The simulation is READ-ONLY — it writes nothing. Publishing creates a new
immutable policy version rather than editing the current one. The headline an admin needs first is the SCALE
of the change, not a single plausible example. Operator-tool aesthetic: precise, quiet, instrument-like.

LAYOUT — the panel sits directly below the weight editor, full column width (capped ~800px), 16px below the
Simulate button. Background #F1F5F9 (dark #1E293B), 6px radius, 20px padding.

STATE A — RUNNING
A 30-day replay is not instant, so this state matters. Show a skeleton that matches the final layout, never
a centred spinner (a spinner followed by content is a layout jump, and a jump under a cursor is a mis-click):
- One wide skeleton block where the headline will be, roughly 20px tall.
- Three narrower skeleton lines where the cases will be, roughly 13px tall, 8px apart.
- Skeleton blocks are #E2E8F0 (dark #334155) with a 1600ms ease-in-out pulse. Under reduced-motion the pulse
  becomes a static grey block.
- Below the skeleton, a single line of status text, 13px, colour #64748B: "Replaying the last 30 days…"
- If the run passes about 10 seconds, that line becomes "Still working — replaying the last 30 days" rather
  than a spinner that looks identical at 2 seconds and 40 seconds.

STATE B — RESULT (the primary frame)
       Simulation: proposed weights vs. current policy v3        ← 13px, colour #64748B
       12 of 340 decisions in the last 30 days would flip        ← 20px/700, primary text, the HEADLINE
       ────────────────────────────────────────────────────────  ← 1px #E2E8F0 divider
       ▶ SHP1014 vs SHP1009 — under these weights, SHP1014 loses to SHP1009
       ▶ SHP1002 vs SHP1021 — under these weights, SHP1002 wins (was: loses)
       ... 10 more
       [ Discard ]                                  [ Publish as v4 ]
- The aggregate count is the headline at 20px/700; individual cases are secondary at 13px, colour #475569,
  each an expandable row with a Lucide `chevron-right` at 14px, 6px vertical padding, separated by 1px
  #E2E8F0 top borders. Shipment IDs render in `JetBrains Mono` 500.
- Numbers use tabular figures and `en-IN` grouping (340 here; a larger figure would group as 1,00,000, not
  100,000 — never hand-build grouping).
- Buttons, 24px below the case list, 8px gap:
  "Discard" — neutral: transparent, 1px #CBD5E1 border, text #0F172A, 40px height, 6px radius. First in
  reading and tab order.
  "Publish as v4" — constructive: #2563EB background, white text, 13px/600, 40px height, 6px radius,
  minimum width 80px.

STATE C — STALE
A weight field changed after this simulation ran, so the preview no longer matches the fields. Show the
whole result block at reduced emphasis (body text drops to #64748B) with a banner ABOVE the headline:
- Banner: full panel width, 12px/16px padding, 6px radius, background #FFFBEB, 1px #F59E0B border, Lucide
  `alert-triangle` at 16px in #B45309, text 13px in #B45309 (dark: #FBBF24 on #78350F at 25%, border
  #F59E0B). Exact copy:
      Weights changed since this simulation — re-run before publishing.
- "Publish as v4" is genuinely disabled: background #E2E8F0, text #94A3B8, `cursor: not-allowed`, with the
  reason in a tooltip: "Re-run the simulation against the current weights".
- "Simulate against last 30 days" above the panel returns to its default enabled appearance.

STATE D — PUBLISHED
The panel is replaced by a confirmation block and the version header above the editor updates:
- Confirmation, 12px/16px padding, 6px radius, background #ECFDF5, 1px #059669 border, Lucide `circle-check`
  at 16px in #047857, text 13px in #047857 (dark: #34D399 on #064E3B at 25%, border #10B981). Exact copy:
      Published as v4. Every decision from now on is scored against this version.
- The header above the editor now reads, in `JetBrains Mono` for the version and date:
      Current policy: v4 · published 2026-08-21 · Anshul G.
- No confetti, no celebratory treatment. A capacity system does not celebrate.

TYPOGRAPHY
`Inter` 400/500/600/700 only — a locked legibility choice at 12–14px, not to be substituted.
`JetBrains Mono` 400/500 with tabular figures for shipment IDs, version numbers, dates and every count.
20px/1.25/700 headline · 14px/1.5/400 body · 13px/1.4/400 case rows and status text · 12px/1.33/600/0.04em
any uppercase label.

COLOR (light / dark)
Panel #F1F5F9 / #1E293B · page #F8FAFC / #020617 · primary text #0F172A / #F8FAFC ·
secondary #475569 / #CBD5E1 · tertiary #64748B / #94A3B8 · divider #E2E8F0 / #1E293B ·
primary action #2563EB / #3B82F6 · disabled #E2E8F0 + #94A3B8 / #1E293B + #475569 ·
warning #B45309 on #FFFBEB with #F59E0B border / #FBBF24 on #78350F-at-25% with #F59E0B border ·
success #047857 on #ECFDF5 with #059669 border / #34D399 on #064E3B-at-25% with #10B981 border.
Note: the green here is FEEDBACK about an action succeeding, rendered as a banner. It is never rendered as a
status chip — in this product a green chip means a confirmed dock promise, and the two must not be
confusable. Position disambiguates what colour cannot.

SPACING
4px base. 20px panel padding, 12px below the headline, 6px vertical per case row, 24px above the buttons,
8px between buttons, 16px between the panel and the editor above it.

MOTION
The result panel appears at 200ms ease-out `cubic-bezier(0.16, 1, 0.3, 1)` once. Skeleton pulse is a
1600ms ease-in-out loop and is the ONLY looping motion permitted here. No number count-up — the "12 of 340"
figure appears at its final value. No chart draw-in. No spring, no bounce.

STATES TO RENDER
All four: A running (skeleton) · B result · C stale (banner + disabled publish) · D published (success
banner + updated version header).

EXPLICITLY EXCLUDE
- No charts, bar graphs, before/after visualisations or diff heatmaps.
- No progress percentage or determinate progress bar unless the run genuinely reports progress; the default
  is the skeleton.
- No centred spinner at any point.
- No confetti, celebration, success illustration or "Success!" copy.
- No "publish anyway" override on the stale state — re-running is the only path.
- No inline editing of weights inside the result panel.
- No emoji, exclamation marks, blur, gradient or marketing copy.
```

---

## 11 · Audit tab — filtered event log with export

```text
Design the Audit tab of a B2B logistics admin console: a chronological record of significant actions,
recent-first.

PRODUCT CONTEXT
SetuHaul Dock Command. An admin investigating something starts at "what just happened" and works backwards,
so recent-first is the default and not a sort the user has to choose. This console's own writes — policy
publishes, user removals, rule edits — are the primary subject of the log it displays. System-generated
events appear too, attributed to "(system)", never to a blank actor.

LAYOUT
Inside the app shell (56px left icon rail, 56px top bar with four tabs where "Audit" is active), the content
region has 24px padding:

1. Toolbar, 8px gaps, 16px above the table:
   [ Date range: last 7 days ▾ ] [ Actor ▾ ] [ Event type ▾ ] [ 🔍 search ——— flexes ] [ Export ]
   - Filter pills: 8px/12px padding, 1px #CBD5E1 border, 4px radius, 12px text, colour #64748B, with a
     Lucide `chevron-down` at 14px.
   - Search field flexes to fill: background #F1F5F9, 4px radius, 8px/12px padding, 13px, Lucide `search`
     16px inline.
   - "Export": neutral button — transparent, 1px #CBD5E1 border, text #0F172A, 13px/600, 40px height,
     6px radius, with a Lucide `download` at 16px. Export always respects the CURRENT filter set — never a
     silent full-table dump.

2. Table, full width, 1px #E2E8F0 row separators, no zebra striping, no vertical rules.
   Columns, fixed widths, left-aligned:
   Time | Actor | Event | Resource
   - Header: 12px/600 uppercase, 0.04em tracking, colour #64748B, 12px/16px padding, sticky on scroll.
   - Rows: 44px tall, 12px/16px cell padding, 14px/400.
   - Time and Resource render in `JetBrains Mono` 400 with tabular figures.
   - Recent-first, always. Do not show a sort control on the Time column suggesting otherwise.

ROWS TO SHOW (use exactly these)
| 14:02 today | Anshul G. | Policy published | policy_versions v4                  |
| 13:40 today | Neha B.   | User removed     | priya.sharma@… (Gate/Yard, Jaipur)  |
| 11:15 today | (system)  | Rule updated     | Jaipur · NEW_START_CUTOFF           |
| 09:52 today | Anshul G. | Rule created     | Gurugram · WEIGHT_LIMIT             |

ACTOR COLUMN
- Human actors: name at 14px/400 primary text, with a stable identifier available on the row (a `title`
  tooltip carrying the user id). A display name can change; the logged reference does not, so a renamed
  user's historical actions stay attributable.
- System actors: the literal string "(system)" in colour #64748B (dark #94A3B8), never a blank cell. A blank
  actor reads as a data-quality problem; "(system)" reads as a fact.

EVENT COLUMN
A controlled-vocabulary label in sentence case — "Policy published", "User removed", "Rule updated" — never
free text and never a raw enum. No severity colour, no coloured badge: colour in this product is rationed to
promise state and danger, and an audit event is neither.

RESOURCE COLUMN
Plain reference text, NOT a link. Clicking a resource does not navigate anywhere — the tab that owns that
resource already is its detail view, and duplicating it here would be two places maintaining one fact.
Render with no interactive affordance at all: no hover state, no underline, no cursor change, no accent
colour. A read-only value that looks clickable and does nothing reads as broken.

TRUNCATION
Long values truncate with an ellipsis and carry a native tooltip with the full string, reachable on FOCUS,
not hover-only. An ellipsis stands for three or more removed characters, and at least four characters always
remain.

TIME AND DATE FORMAT
24-hour clock, always — "14:02", never "2:02 PM". Relative day labels for the current day ("14:02 today");
anything 24 hours or older shows an absolute facility-local date with the weekday included, e.g.
"Tue 4 Aug · 14:02". Ranges use an en dash.

TYPOGRAPHY
`Inter` 400/500/600/700 only — a locked legibility choice at 12–14px, not to be substituted.
`JetBrains Mono` 400/500 for timestamps, resource references and enum values, so machine-generated values
look machine-generated and align down a column.
14px/1.5/400 cells · 13px/1.4/400 secondary · 12px/1.33/600/0.04em uppercase headers · 11px floor.

COLOR (light / dark)
Page #F8FAFC / #020617 · table container #FFFFFF / #0F172A · primary text #0F172A / #F8FAFC ·
secondary #475569 / #CBD5E1 · tertiary #64748B / #94A3B8 · subtle border #E2E8F0 / #1E293B ·
default border #CBD5E1 / #334155 · row hover #F1F5F9 / #1E293B.

SPACING — `comfortable` density
4px base. 44px rows, 12px/16px cell padding, 40px button height, 24px content padding, 16px toolbar-to-table
gap, 8px between toolbar items.

RADIUS AND ELEVATION
8px table container at tier 1: #FFFFFF + `0 1px 2px rgba(15,23,42,0.06)` + 1px #E2E8F0 border
(dark: #0F172A, no shadow, 1px #1E293B border). 6px buttons, 4px filter pills.

MOTION
200ms ease-out `cubic-bezier(0.16, 1, 0.3, 1)` on hover, 120ms on focus. Filtering re-renders the table
instantly with no transition. No ambient or looping motion.

FOCUS BEHAVIOUR
Keyboard focus moves row to row with a two-ring indicator (2px surface then 2px #2563EB). When a filter
changes, focus STAYS on the filter control — results update beneath it; focus does not jump into the result
set.

STATES TO RENDER
Default table · a filter dropdown open · one row keyboard-focused · Export in its hover state.

EXPLICITLY EXCLUDE
- No links from a log row to the affected resource, and no drill-down detail drawer.
- No severity levels, no colour-coded event badges, no icons per event type.
- No user avatars in the Actor column.
- No checkbox column, no bulk actions, no row-level menu — nothing on an audit row is actionable beyond
  reading it.
- No single-key keyboard shortcuts on rows (those exist elsewhere in this product; there is nothing to act
  on here).
- No infinite-scroll spinner at the bottom; use a plain "load more" or a scrolling table with a sticky
  header.
- No zebra striping, no vertical rules, no coloured row backgrounds.
- No hero, banner, illustration, gradient, blur or marketing copy.
```

---

## 12 · Empty, loading and error states (console-wide)

```text
Design the empty, loading and error states for a B2B logistics admin console. Every one names a cause and a
next action — no bare spinners, no "something went wrong".

PRODUCT CONTEXT
SetuHaul Dock Command. This is an internal operations tool where a click can commit warehouse capacity, so
a user must always be able to tell a working-but-empty system from a broken one, and must always know
whether a failed action left partial state behind. Operator-tool aesthetic: calm, factual, no reassurance
theatre.

SHARED ANATOMY — every empty/error state uses this vertical stack, centred in the content region:
       [ Lucide icon, 32px, 2px stroke, colour #64748B ]
       ↓ 16px
       [ Headline — what is true right now, 16px/1.5/600, colour #0F172A ]
       ↓ 8px
       [ One line explaining why, 14px/1.5/400, colour #475569, max ~75 characters ]
       ↓ 24px
       [ The next action — a button, or nothing at all if none is needed ]
No illustration, no spot art, no mascot. The icon is the only graphic.

RENDER THESE SEVEN FRAMES

A · Users list, nothing yet (a newly provisioned deployment)
   Icon `inbox`. Neutral, informational — this is an expected state, not a problem.
       No users have been invited yet.
       Once you invite someone, they will show up here.
       [ Invite user ]  ← constructive: #2563EB, white text, 40px height, 6px radius

B · Search returned nothing
   Icon `search-x`.
       No user matches "rj14".
       Try a different name, email, or role.
       [ Clear search ]  ← neutral: transparent, 1px #CBD5E1 border, text #0F172A

C · Audit log, filter matches nothing
   Icon `search-x`.
       No events match this filter.
       Widen the date range, or clear the actor and event-type filters.
       [ Clear filters ]  ← neutral
   In this state the Export button in the toolbar is genuinely DISABLED — background #E2E8F0, text #94A3B8,
   `cursor: not-allowed` — with the reason in a tooltip: "There is nothing to export with this filter".
   An admin must never receive a file and be left guessing whether it is empty because nothing happened or
   because something went wrong.

D · Table loading
   NOT a centred spinner. Draw skeleton rows matching the final table layout exactly: the same 44px row
   height, the same fixed column widths, with a #E2E8F0 (dark #334155) block in each cell at roughly the
   width of the real value. Skeleton blocks pulse at 1600ms ease-in-out; under reduced-motion the pulse
   becomes a static grey block. The app shell (rail, top bar, tabs) stays fully rendered — only the content
   region loads. No global progress bar.

E · Load failed
   Icon `octagon-alert`.
       Couldn't load the user list — usually a connection problem.
       [ Try again ]  ← neutral
   This is scoped to the content region, not the whole app: the rail, top bar and tabs remain usable.

F · Write failed
   A banner across the top of the content region rather than a full-region state, because the table beneath
   is still valid: full width, 12px/16px padding, 6px radius, background #FEF2F2, 1px #DC2626 border,
   Lucide `circle-alert` at 16px in #B91C1C, text 13px in #B91C1C (dark: #F87171 on #7F1D1D at 25%, border
   #EF4444). Exact copy, with the second sentence in weight 600:
       That didn't save. Nothing has changed.
       [ Try again ]  ← inline text button inside the banner
   "Nothing has changed" is essential and not optional phrasing: in a system where a click commits capacity,
   a user must know a failure left no partial state.

G · Maintenance (full page)
   Icon `wrench`, 32px.
       SetuHaul Dock Command is being updated.
       Expect this to take about 15 minutes.
       Anything you were doing has been saved — just come back and pick up where you left off.
   No action button. Always states an estimated duration — a maintenance page that doesn't say how long
   reads as indefinite, which is worse than the wait.

TYPOGRAPHY
`Inter` 400/500/600/700 only — a locked legibility choice at 12–14px, not to be substituted.
16px/1.5/600 headline · 14px/1.5/400 explanatory line · 13px/1.4/600 button labels · 13px/1.4/400 banner
text. Sentence case throughout. No exclamation marks. Never apologise for a system rule — state it and offer
the exit.

COLOR (light / dark)
Page #F8FAFC / #020617 · content surface #FFFFFF / #0F172A · headline #0F172A / #F8FAFC ·
explanatory text #475569 / #CBD5E1 · icon #64748B / #94A3B8 · skeleton block #E2E8F0 / #334155 ·
primary action #2563EB / #3B82F6 · neutral button border #CBD5E1 / #334155 ·
danger text #B91C1C / #F87171 on #FEF2F2 / #7F1D1D-at-25% with #DC2626 / #EF4444 border ·
disabled #E2E8F0 + #94A3B8 / #1E293B + #475569.
Colour never carries meaning alone: every error state pairs its colour with an icon AND explicit words.

SPACING
4px base. 16px icon-to-headline, 8px headline-to-explanation, 24px explanation-to-action, 24px content
padding. Empty-state stacks are the one place in this product where vertical space above 32px is acceptable
— centre the stack in the content region.

MOTION
Skeleton pulse 1600ms ease-in-out loop — the only looping motion here, and it becomes static under
`prefers-reduced-motion`. Everything else appears instantly; empty and error states do not animate in.
No spring, no bounce, no ambient motion.

EXPLICITLY EXCLUDE
- No centred spinners anywhere — skeletons matching the final layout instead.
- No global top-of-page progress bar.
- No illustrations, spot art, characters, mascots or 3D graphics.
- No "Oops!", "Uh oh", "Something went wrong", or any exclamation mark.
- No emoji.
- No identical treatment for "nothing yet" and "no results" — they use different icons (`inbox` vs
  `search-x`) and different copy, on purpose.
- No error state that hides the app shell — the rail, top bar and tabs stay rendered and usable.
- No blur, gradient or marketing copy.
```

---

## Spec gaps flagged, not filled

Things the prompts above deliberately did **not** invent. Each is a real under-specification in this
surface's spec or a divergence between two of its files.

| # | Gap | Where it bites | What the prompts did |
|---|---|---|---|
| 1 | **No tab component exists in `../00-foundations/components.md`.** The admin console is the only four-tab surface in the product, and the shared inventory has no Tabs entry — no height, no active-indicator rule, no keyboard model. | Prompt 1 | Derived active-tab styling from `mockup.html` (colour `#2563EB` + `#F1F5F9` fill, 4px radius, 8px/12px padding). Colour + fill is two channels, so the "never colour alone" rule holds without inventing an underline. Worth adding a real Tabs entry to the foundations. |
| 2 | **The shell's 28px status bar is specified in `spacing-and-layout.md` but absent from this surface's `screens.md` and `mockup.html`.** Its contents (connection · last sync · active facility · pending count · **policy version**) are arguably more relevant here than anywhere — policy version is this surface's own subject. | Prompt 1 | Followed the surface's own files: no status bar. Flagged rather than added. |
| 3 | **The 4px facility-accent rail stripe has no defined value for a surface with no active facility.** `screens.md` removes the facility switcher ("admin actions span facilities by nature"); the stripe's colour is per-facility. | Prompt 1 | Excluded the stripe explicitly. The alternative — a neutral or a seventh hue — would be a new decision. |
| 4 | **Global search is in the shell spec's top bar but absent from this surface's mockup**, which gives each tab its own search instead. | Prompt 1 | Followed the mockup; excluded the top-bar search and said so. |
| 5 | **`iconography.md` has no entry for an overflow menu, a settings gear, or a Danger-Zone warning.** The mockup uses `⋯` and `⚙︎` glyphs. | Prompts 1, 2, 4, 7, 8, 9 | Used Lucide's literal names (`ellipsis`, `settings`) per the file's own "name an icon by what it literally is" rule, and reused the existing `alert-triangle` entry for danger panels rather than adding a glyph. Three small additions the inventory should absorb. |
| 6 | **Email truncation has no stated rule.** `data-formatting.md` says mid-truncate identifiers, end-truncate free text; an email is neither cleanly. The mockup's `neha@...` end-truncates. | Prompts 2, 11 | Showed full emails at the 1440px target width (the column fits), and specified end-truncation with a focus-reachable tooltip only where narrower. Did not promote either to a rule. |
| 7 | **The fairness box's cross-reference points to two different places.** `screens.md` says the carrier-concentration canary is "on this tab"; `mockup.html` says "on the Audit tab"; `components.md` cross-references it without naming a location. No canary is actually designed on any of the four tabs. | Prompt 8 | Used `screens.md`'s copy minus the location pointer. The canary itself appears to be an undesigned surface element — the bigger of the two issues. |
| 8 | **No copy exists for the concurrent-publish conflict** (`edge-cases.md` #3 specifies the behaviour — named refusal, re-fetch B's version as the new baseline, mark A's simulation stale — but no string). | Prompt 10 | Rendered only the stale state, whose copy *is* specified ("Weights changed since this simulation — re-run before publishing"). Did not compose a conflict string. Needs a template. |
| 9 | **Deactivate's undo behaviour is ambiguous.** `screens.md` calls Deactivate "Moderate — immediate, reversible via Reactivate, no typed confirmation"; `components.md` §19's Moderate tier is "acts immediately, **5-second undo**, no modal". Those are two different affordances. | Prompt 2 | Rendered neither an undo toast nor a confirmation for Deactivate. Needs one call. |
| 10 | **Admin-specific empty/error copy is not written anywhere.** `components.md` §13 supplies the *pattern* and planner-queue examples ("Couldn't load the queue…"). | Prompt 12 | Composed admin-context copy strictly from the pattern (name a cause, name a next action, "Nothing has changed" verbatim on a failed write) and marked it as composed here rather than quoted. |
| 11 | **`mockup.html` uses 20px content padding**; `spacing-and-layout.md`'s density table specifies **24px** for `comfortable`. | Every prompt | Used 24px — a mockup value with no foundation source is a mockup bug, not a decision. Also noted: the mockup's frame shadow (`0 8px 24px rgba(0,0,0,.10)`) is not a `shadow-*` token; it appears to be board presentation, not UI. |
| 12 | **`SOLUTION_DESIGN.md` §7.5.7's `reason_code` enum for Resolve/Cancel is tagged `Source: assumption, untested`** in the existing spec. | — | No prompt renders it; nothing in these twelve screens depends on it. Noted so it is not treated as settled if a later screen does. |
