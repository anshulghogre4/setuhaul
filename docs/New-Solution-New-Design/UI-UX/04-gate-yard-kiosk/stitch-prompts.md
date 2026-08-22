# Gate/yard kiosk — Stitch prompts

> Paste-ready prompts for **Stitch** (stitch.withgoogle.com). This file is a **translation of the finished
> spec**, not a place where new design decisions get made. Every value below traces to
> `screens.md`, `components.md`, `flows-and-states.md`, `edge-cases.md`, `accessibility.md` in this folder,
> or to `../00-foundations/`. Where a value required a judgement call because the spec was silent or
> self-contradictory, it is listed in **§ Values that required a judgement call** at the end of this file —
> not silently absorbed into a prompt.
>
> **Order matches `screens.md`**: shift start → search → truck found (one action per `queue_state`) →
> outcome screens. Both device contexts (U108) are covered: mounted **gate-booth kiosk** (landscape) and
> handheld **yard tablet** (portrait).
>
> **22 prompts.** Each block is self-contained — paste one block, get one screen. The repetition between
> blocks is deliberate; Stitch does not carry a design system between prompts.

## Why this surface looks different from every other SetuHaul surface

Stated once here so each prompt can assert the numbers without re-arguing them:

**`spacious` density — the only surface in the product that uses it** (`../00-foundations/spacing-and-layout.md`,
density table). Row height 64px, cell padding 20/24px, card padding 24px, stack gap 16px, **minimum tap
target 56×56px**, button height 56px, content padding 32px. Every other surface runs `compact` (planner,
ops — 32px targets, pointer-only) or `comfortable` (driver, carrier, admin — 44px targets).

The reason is physical, not aesthetic, and it is load-bearing:

- **Gloves.** `accessibility.md` (this folder): a gloved fingertip's effective contact area is measurably
  larger than a bare one, so the 44px AAA target used on the driver PWA — which assumes a bare fingertip —
  is not generous enough here. 56px is the response to gloves specifically.
- **Outdoors, direct sun.** `color.md`'s *Field-condition contrast* section: light theme only, body text
  never uses `text-secondary` for anything operational, state never carried by colour alone.
- **No fine-motor precision available.** One-handed, the other hand occupied (clipboard, truck door, waving
  a driver forward). Hence U110's one-dominant-button pattern — a single full-width 56px+ target is
  unambiguously reachable one-handed, and generous spacing between any two interactive elements means a
  gloved mis-tap lands on nothing rather than on the wrong control.
- **Standards note, per U30**: WCAG 2.2 SC 2.5.8 Target Size (Minimum) is **24×24px at AA**. The 44px figure
  used elsewhere is SC 2.5.5 (Enhanced), **AAA**. 56px exceeds both, deliberately and self-imposed. This is
  recorded so a later "we only need AA" review cannot shrink the kiosk to 24px believing it still conforms.

**Light theme only.** Both themes are specified at full parity product-wide (U7), and light is the global
default (U69) — but `screens.md`'s header states dark is not the expected real-world state on this surface,
and `color.md` requires dark to carry an explicit "hard to read outdoors" warning on the two field surfaces.
So the prompts below ask for light only. Do not ask Stitch for a dark variant here; a dark artboard would be
a rendering of a state we tell officers not to use.

**No app shell.** `screens.md`: "No other navigation exists. There is no list, no dashboard, no settings
beyond shift start." No icon rail, no top bar, no status bar, no facility switcher — and therefore **no
facility accent colour anywhere** (U59/U40 confine that palette to the rail-edge stripe and the switcher
swatch, neither of which exists on this device).

## Skills actually run for this file

- **`checklist-design`** — invoked; read `references/index.md` (122 checklists, v3.2.0). Confirms
  `screens.md`'s existing claim: **no whole-screen checklist matches a single-purpose field kiosk.** Two
  component-level checklists do partially apply and were read and used: **Banner** (design system) and
  **Searchbar** (design system). Two items from them changed prompt content and are marked inline:
  Banner's *Dismissable* item, and Searchbar's *Previous searches / autocomplete* item.
- **`web-design-guidelines`** — invoked; guidelines fetched. Nothing in it conflicts with the foundations
  (visible focus via `:focus-visible`, labels on every control, `prefers-reduced-motion` honoured, animate
  `transform`/`opacity` only). Its rules are folded into the prompts rather than listed separately.
- **`dataviz`** — **does not apply.** No chart, sparkline, stat tile or metric visual exists on this surface.
- **`design` (canvas)** — not run here. This file's deliverable is text prompts; the "not sloppy" bar's
  canvas-draft step belongs to the cross-cutting screens batch, not to a spec-to-prompt translation.

---

## 1 · Shift start — gate-booth kiosk (landscape)

`screens.md` §1 · `components.md` §1 · Flow 0 · U111. Once per shift, not per truck. Facility is fixed to
the device, never a switcher.

```
Copy-paste into Stitch — SetuHaul Dock Command · Gate-booth kiosk · Shift start (landscape)

Product context: SetuHaul Dock Command is a B2B internal logistics operations tool. This screen runs on a
wall-mounted tablet inside a gate booth at a distribution centre. The user is a gate officer, outdoors or
behind glare-prone glass, wearing work gloves, operating one-handed. Not a consumer app: no marketing, no
onboarding carousel, no illustration, no brand storytelling. Treat this as an instrument panel, not a SaaS
product page.

Frame: 1280 x 800, landscape, fixed. This is a mounted device — it is never rotated and never resized.

What this screen is: a shared-device shift sign-on. The officer types their name once at the start of a
shift; that name is stamped on every event the device records until the shift ends. It is an attribution
mechanism, not authentication — there is no password, no email, no "forgot password", no "create account",
no SSO buttons.

Typography: Inter only, weights 400/500/600/700, no other weights loaded. JetBrains Mono 400/500 for
machine-generated values only (none on this screen). Inter is a locked functional choice — tall x-height
that survives glare. Do not substitute a more distinctive display font.
- Product line: 20px / line-height 1.4 / weight 600 / letter-spacing -0.01em
- Screen title: 24px / 1.33 / 600 / -0.01em
- Field label: 16px / 1.5 / 600
- Field input text: 20px / 1.4 / 400
- Facility line: 16px / 1.5 / 400
- Primary button label: 20px / 1.4 / 700
- Absolute floor: no text below 14px anywhere on this screen. 11px and 13px steps that exist elsewhere in
  this design system are forbidden on this surface (outdoor legibility).

Color, light theme only (this device is used in direct sunlight; do not produce a dark variant):
- Page background: #F8FAFC
- Card surface: #FFFFFF with 1px border #E2E8F0 and shadow 0 1px 2px rgba(15,23,42,0.06)
- Primary text: #0F172A (17.9:1 on white)
- Secondary text: #475569 — used only for the facility hint, never for anything operational
- Input border: #CBD5E1, 1px; input background #FFFFFF; input text #0F172A
- Primary button: background #2563EB, label #FFFFFF, no border, no gradient. Hover #1D4ED8, pressed #1E40AF
- Focus ring: two rings — inner 2px #F8FAFC, outer 2px #2563EB, 2px offset. Never a soft glow.

Spacing: 4px base unit, spacious tier. Card padding 24px. Vertical gap between stacked elements 16px.
Content padding 32px from the card edge. Minimum 24px padding from the device edge (the tablet sits in a
protective case that eats the bezel). Nothing interactive within 16px of the viewport edge.

Touch targets: the text input and the button are both minimum 56px tall and full card width. 56px, not
44px, because the user is wearing work gloves.

Radius: 8px on the card, 6px on the input and the button. Restrained on purpose — heavy rounding reads as
consumer software, which is the wrong signal for a system that commits dock capacity.

Layout: one centred card, roughly 560px wide, vertically centred in the 1280x800 frame. Inside it, top to
bottom: small product line "SetuHaul · Gate/Yard"; screen title "Start shift"; a labelled text field;
a fixed facility line; the primary button. Generous whitespace around the card — the landscape frame does
not need to be filled.

Exact copy, use verbatim:
- Product line: "SetuHaul · Gate/Yard"
- Title: "Start shift"
- Field label (always visible above the field, never a placeholder standing in for a label): "Officer name"
- Field placeholder: leave empty
- Facility line: "Facility: Jaipur (fixed)" — plain text, not a control, no chevron, no dropdown arrow
- Button: "Start shift"

States to show as separate artboards:
1. Empty — field empty, button present but not yet actionable, styled #E2E8F0 background with #94A3B8
   label, and a short line under the field reading "Enter your name to start" (a disabled control with no
   explanation is a dead end).
2. Filled — field contains "Ramesh K.", button fully blue and active.
3. Focused — field with the two-ring focus indicator described above.

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1) on state changes; 120ms on focus. No bounce, no
spring, no scale, no lift on hover. No looping or ambient animation of any kind. Honour
prefers-reduced-motion by making transitions instant.

Explicitly exclude: password field, email field, SSO or social sign-in buttons, "remember me", "forgot
password", "create account", terms/privacy fine print, a facility dropdown or switcher of any kind, a
company logo lockup larger than the one text line, background photography, gradients, glassmorphism or
backdrop blur, illustration, emoji, a bottom tab bar, a side navigation rail, a top app bar, any dark-mode
artboard, any facility accent colour.
```

*Non-visual behaviour to annotate, not render: this screen is local device state, not a server write — it
must remain usable during a connectivity drop (`edge-cases.md` #7).*

---

## 2 · Shift start — yard tablet (portrait)

Same component, same copy, different physical device (U108 — the split is layout, not a different tool
contract).

```
Copy-paste into Stitch — SetuHaul Dock Command · Yard tablet · Shift start (portrait)

Product context: SetuHaul Dock Command is a B2B internal logistics operations tool. This screen runs on a
handheld tablet carried by a yard marshal across an outdoor truck yard — direct sun, work gloves,
one-handed operation with the other hand occupied. Not a consumer app: no marketing, no onboarding, no
illustration, no brand storytelling.

Frame: 800 x 1280, portrait, handheld.

What this screen is: a shared-device shift sign-on. The marshal types their name once per shift; it is
stamped on every event the device records until the shift ends. Attribution, not authentication — no
password, no email, no account creation.

Typography: Inter only, 400/500/600/700. Sizes: product line 20/1.4/600; title 24/1.33/600/-0.01em; field
label 16/1.5/600; input text 20/1.4/400; facility line 16/1.5/400; button label 20/1.4/700. No text below
14px anywhere.

Color, light theme only (outdoor use — do not produce a dark variant): page #F8FAFC; card #FFFFFF, 1px
#E2E8F0 border, shadow 0 1px 2px rgba(15,23,42,0.06); primary text #0F172A; secondary text #475569; input
border #CBD5E1; primary button #2563EB with #FFFFFF label, hover #1D4ED8, pressed #1E40AF; focus ring two
rings — inner 2px #F8FAFC, outer 2px #2563EB at 2px offset.

Spacing: 4px base, spacious tier. Card padding 24px, stack gap 16px, 24px minimum device-edge padding,
nothing interactive within 16px of the viewport edge.

Touch targets: input and button both minimum 56px tall, full width. 56px because of gloves.

Radius: card 8px, input and button 6px.

Layout, portrait-specific: the card spans the full content width (edge padding aside) rather than sitting
as a narrow centred box, and it sits in the UPPER-MIDDLE of the frame — roughly 25% down — not vertically
centred. Reason: this is a handheld device gripped at the bottom; the primary button should fall in the
comfortable thumb arc, not at the extreme bottom edge and not near the top where a one-handed grip cannot
reach. Leave the bottom third empty rather than stretching content into it.

Exact copy, verbatim: product line "SetuHaul · Gate/Yard"; title "Start shift"; visible field label
"Officer name"; facility line "Facility: Jaipur (fixed)" as plain text with no chevron; button "Start
shift".

States as separate artboards: empty (button #E2E8F0 with #94A3B8 label, plus the line "Enter your name to
start"), filled with "Priya S.", and focused with the two-ring focus indicator.

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1); 120ms for focus. No bounce, no spring, no hover
lift, no ambient loops. Instant under prefers-reduced-motion.

Explicitly exclude: password/email/SSO, "remember me", "forgot password", terms fine print, a facility
switcher, background imagery, gradients, glassmorphism or blur, illustration, emoji, bottom tab bar, side
rail, top app bar, any dark artboard, any facility accent colour, any pull-to-refresh or swipe affordance.
```

---

## 3 · Search — idle and in-flight (gate-booth kiosk, landscape)

`screens.md` §2 · `components.md` §2 · Flow 1 · U109 (typed entry only — no scan/camera path was invented
because nothing in the schema establishes a scannable code exists).

```
Copy-paste into Stitch — SetuHaul Dock Command · Gate-booth kiosk · Search a truck (landscape)

Product context: B2B internal logistics operations tool, mounted gate-booth tablet, gate officer in gloves
in direct sunlight. This is the screen the officer returns to dozens of times per shift — it is the loop
the whole surface is built around. Not a consumer app.

Frame: 1280 x 800, landscape, fixed.

What this screen is: a single-field search for one truck, by shipment ID or vehicle plate number. The
officer may have either one to hand depending on whether they are reading paperwork or reading the truck;
one field accepts both.

Typography: Inter 400/500/600/700 for UI; JetBrains Mono 400/500 for the typed value, because a shipment ID
is a machine-generated identifier and should look like one — mono also keeps character alignment readable
under glare.
- Shift bar text: 16px / 1.5 / 500
- Screen title: 24px / 1.33 / 600 / -0.01em
- Field label: 16px / 1.5 / 600
- Field input text: 24px JetBrains Mono / 1.4 / 400, letter-spacing 0.01em
- Button label: 20px / 1.4 / 700
- No text below 14px anywhere.

Color, light theme only: page #F8FAFC; card #FFFFFF, 1px #E2E8F0, shadow 0 1px 2px rgba(15,23,42,0.06);
primary text #0F172A; shift-bar text #475569; input border #CBD5E1, focus border #2563EB; primary button
#2563EB with #FFFFFF label, hover #1D4ED8, pressed #1E40AF; focus ring inner 2px #F8FAFC + outer 2px
#2563EB at 2px offset.

Spacing: 4px base, spacious tier. Content padding 32px. Card padding 24px. Stack gap 16px. 24px minimum
device-edge padding. Nothing interactive within 16px of the viewport edge.

Touch targets: the input, the Search button and the "End shift" control are each minimum 56px tall.
The "End shift" control sits at least 32px away from any other interactive element so a gloved mis-tap
cannot reach it.

Radius: card 8px, input 6px, button 6px.

Layout: a thin shift bar across the top of the content area (not a coloured app bar — plain text on the
page background, separated by a 1px #E2E8F0 rule) reading device, facility and officer on the left, and a
low-emphasis "End shift" text control on the right. Below it, a centred card about 720px wide with: the
title, the labelled input, and a full-width primary button. Nothing else on screen.

Exact copy, verbatim:
- Shift bar left: "Gate booth · Jaipur · Shift: Ramesh K."
- Shift bar right: "End shift" — text-style control, 16px / 600 / #475569, underlined on focus, no button
  chrome. It is rare relative to searching and must not compete with the primary action.
- Title: "Search"
- Visible field label: "Shipment ID or plate number"
- Field value in the filled artboard: "SHP1015"
- Button: "Search"

States as separate artboards:
1. Idle — field empty, button active.
2. Typed — field contains "SHP1015" in mono, field border #2563EB, focus ring visible.
3. In-flight — button label stays "Search" with a small spinner replacing the leading icon position; the
   button width is frozen so nothing reflows. The label is never removed and never replaced by a spinner
   alone: a label-less control under gloves invites a mis-tap on whatever renders next. Show nothing at all
   for the first second of a request — an indicator that flashes for under a second is pure distraction.

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1); 120ms on focus. Spinner is the only moving element
and only while in flight. No ambient loops, no bounce, no hover lift. Instant under prefers-reduced-motion.

Explicitly exclude: a QR/barcode scan button, a camera icon, an NFC affordance (typed entry only is a
deliberate decision — no scannable code is established to exist); autocomplete dropdowns, type-ahead
suggestions, and a "recent searches" list (this is a shared device — surfacing the previous officer's
lookups across a shift boundary leaks operational context to the wrong person, and nothing in the spec
establishes a suggestion source); voice input; filters; a results table; a truck list or dashboard; a
sidebar or icon rail; a top app bar with tabs; breadcrumbs; a bottom navigation bar; gradients;
glassmorphism or blur; illustration; emoji; any dark-mode artboard; any facility accent colour.
```

---

## 4 · Search — no match (yard tablet, portrait)

`screens.md` §2 · Flow 1.3 · `components.md` foundations §13 — named cause plus next action, never a bare
"not found". The field keeps focus so the officer can retype immediately.

```
Copy-paste into Stitch — SetuHaul Dock Command · Yard tablet · Search returned no match (portrait)

Product context: B2B internal logistics operations tool, handheld tablet, yard marshal in gloves outdoors.
The officer has typed a shipment ID or plate and nothing matched. This is a routine mistype, not a system
failure — the screen must read that way.

Frame: 800 x 1280, portrait.

Typography: Inter 400/500/600/700; JetBrains Mono 400/500 for the searched value echoed back.
- Shift bar 16/1.5/500; title 24/1.33/600; field label 16/1.5/600; input text 24px mono; message headline
  20/1.4/600; message body 16/1.5/400; button label 20/1.4/700. No text below 14px.

Color, light theme only: page #F8FAFC; card #FFFFFF, 1px #E2E8F0, shadow 0 1px 2px rgba(15,23,42,0.06);
primary text #0F172A; the no-match message block uses background #FEF2F2, 1px border #DC2626, text
#B91C1C — do not use #DC2626 for the message text itself, it only clears AA at 4.8:1 against white and this
block sits on a tinted ground; #B91C1C is the specified text step. Input border returns to #CBD5E1 with the
value still present. Primary button #2563EB / #FFFFFF.

Spacing: 4px base, spacious. Card padding 24px, stack gap 16px, 24px device-edge padding.

Touch targets: input and button minimum 56px tall, full width.

Radius: card 8px, message block 6px, input and button 6px.

Layout: shift bar at top; card in the upper-middle of the frame containing, top to bottom: title, labelled
input still holding the failed value, the message block, then the button. The message block sits BELOW the
field it refers to, with a 20px alert icon (a triangle with an exclamation, 2px stroke, single colour, no
fill) to the left of the headline — the meaning must survive a washed-out screen, so it is carried by the
icon shape and the words, never by the tint alone.

Exact copy, verbatim:
- Shift bar: "Yard tablet · Jaipur · Shift: Priya S."   /   right: "End shift"
- Title: "Search"
- Field label: "Shipment ID or plate number"
- Field value: "SHP1O15"  (note: the letter O in place of a zero — this is the realistic mistype and makes
  the mono typeface earn its place)
- Message headline: "No shipment matches that ID or plate."
- Message body: "Check the number and try again."
- Button: "Try again"

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1). The message block appears in place; nothing shifts
above it. No shake, no flash, no bounce — a failed search is not an alarm. Instant under
prefers-reduced-motion.

Explicitly exclude: a "contact support" link, a help-centre link, a "search by driver name" suggestion
(the search matches shipment ID and plate only), scan/camera/voice affordances, autocomplete or recent
searches, an error illustration or mascot, a full-screen error page (this is an inline state on the search
screen — the field and its value stay on screen), a dismiss X on the message block (warning and error
messages are not dismissible), a toast, a modal, a sidebar, a top app bar, gradients, blur, emoji, any
dark-mode artboard.
```

---

## 5 · Search — multiple matches (yard tablet, portrait)

`screens.md` §2 · Flow 1.4. A plate shared across trips is unlikely but possible. Explicitly **a list of
rows, not a dropdown menu** — a dropdown is a poor fit for gloves.

```
Copy-paste into Stitch — SetuHaul Dock Command · Yard tablet · Multiple matches (portrait)

Product context: B2B internal logistics operations tool, handheld tablet, yard marshal in gloves outdoors.
The typed plate matched more than one active trip. The officer must pick the right one before any action is
offered.

Frame: 800 x 1280, portrait.

Typography: Inter 400/500/600/700 for labels and names; JetBrains Mono 400/500 for shipment IDs, dates and
times.
- Shift bar 16/1.5/500; title 24/1.33/600; helper line 16/1.5/400; row primary line 20/1.4/600; row
  secondary line 16/1.5/400. No text below 14px.

Color, light theme only: page #F8FAFC; card #FFFFFF, 1px #E2E8F0, shadow 0 1px 2px rgba(15,23,42,0.06);
row separators 1px #E2E8F0; primary text #0F172A; secondary text #475569; pressed row background #F1F5F9;
focus ring inner 2px #FFFFFF + outer 2px #2563EB at 2px offset.

Spacing: 4px base, spacious tier. Card padding 24px. Row height 64px minimum — taller if the two-line row
content needs it, never shorter. Cell padding 20px vertical / 24px horizontal. 16px gap between rows is not
needed (rows are separated by rules) but each row's full 64px+ height is the tap target.

Touch targets: every row is a single tap target of at least 64px height and full card width. Gloved
accuracy comes from the row being large and the whole row being tappable — not from a small chevron.

Radius: card 8px. Rows are not individually rounded.

Layout: shift bar; title; a one-line helper; then a vertical list of 2–3 rows inside one card. Each row is
two lines: line 1 is the shipment ID in mono plus the driver name; line 2 is the carrier plus the
appointment, in secondary text. A right-pointing chevron (2px stroke) sits at the right edge of each row as
a direction cue only — it is never the tap target.

Exact copy, verbatim:
- Shift bar: "Yard tablet · Jaipur · Shift: Priya S."   /   right: "End shift"
- Title: "2 trucks match RJ14 GH 2211"
- Helper: "Pick the right one."
- Row 1 line 1: "SHP1015 · Ravi K."
- Row 1 line 2: "Rajasthan Roadlines · D5 · Tue 4 Aug · 18:00–19:00"
- Row 2 line 1: "SHP1021 · Ravi K."
- Row 2 line 2: "Rajasthan Roadlines · D2 · Wed 5 Aug · 06:00–07:15"
Use an en dash in time ranges, never a hyphen. Use 24-hour time, never AM/PM. Dates always carry the
weekday. Never show a time without its dock and its date — a bare time here is a wrong-day booking.

States as separate artboards: default list; one row in pressed state (#F1F5F9 background); one row focused
(two-ring focus indicator drawn inside the row, not clipped by it).

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1) on press feedback. No row hover lift, no scale, no
staggered list entrance animation. Instant under prefers-reduced-motion.

Explicitly exclude: a dropdown/select menu of any kind (a native picker is unusable with gloves), radio
buttons plus a separate Continue button (the row itself is the action), checkboxes or multi-select, swipe
actions, drag to reorder, avatars or driver photos, a "sort by" control, pagination, an overflow "..." menu,
a sidebar, a top app bar, gradients, blur, emoji, any dark-mode artboard.
```

---

## 6 · Truck found — `NOT_QUEUED` → Gate in (gate-booth kiosk, landscape)

`screens.md` §3 (state → action table) · `components.md` §3, §4 · Flow 3 · U110. `NOT_QUEUED` renders
**with no state icon** — absence is the signal (`../00-foundations/iconography.md`, Queue state table).

```
Copy-paste into Stitch — SetuHaul Dock Command · Gate-booth kiosk · Truck found, gate in (landscape)

Product context: B2B internal logistics operations tool, mounted gate-booth tablet, gate officer in gloves,
truck idling at the barrier behind them. The officer searched a shipment; this screen shows who the truck
is, where it currently stands, and offers exactly ONE action — the only action that is valid right now.

Frame: 1280 x 800, landscape, fixed.

The single most important structural rule: there is exactly one button on this screen. Not a menu, not two
options to weigh, not a Cancel beside it. The truck's current state already determines which action is
correct, so the officer is never asked to choose. Do not add a secondary button "for balance".

Typography: Inter 400/500/600/700 for names and labels; JetBrains Mono 400/500 for the shipment ID, the
dock code, the date and the time range.
- Shift bar 16/1.5/500
- Identity line (shipment ID + driver name) 20/1.4/600
- Carrier line 16/1.5/400
- State label 20/1.4/600
- Appointment line 16/1.5/400, mono for the dock/date/time portion
- Button label 20/1.4/700
- No text below 14px anywhere.

Color, light theme only: page #F8FAFC; identity card background #F1F5F9 with no border (it is a grouped
block inside the white card, not a floating element); outer card #FFFFFF, 1px #E2E8F0, shadow 0 1px 2px
rgba(15,23,42,0.06); primary text #0F172A; carrier and appointment text #475569; a 1px #CBD5E1 rule above
the appointment line; primary button #2563EB with #FFFFFF label, hover #1D4ED8, pressed #1E40AF; focus ring
inner 2px #FFFFFF + outer 2px #2563EB at 2px offset.

Spacing: 4px base, spacious tier. Outer card padding 24px; identity block padding 24px; 16px gap between
the identity block and the button; 16px between lines inside the identity block; 32px content padding;
24px device-edge padding.

Touch targets: the primary button is full card width and minimum 56px tall — this is the target the officer
hits dozens of times a shift with gloves on. The back control and "End shift" are at least 32px away from
it and from each other.

Radius: outer card 8px, identity block 6px, button 6px.

Layout: shift bar at top with a back control on the left; one centred card about 720px wide. Inside, top to
bottom: identity block, then the button. In this state the truck has not checked in yet, so NO state icon
and NO state row is rendered — its absence is the signal that nothing has happened to this truck yet. The
appointment line still renders, separated by a 1px rule.

Exact copy, verbatim:
- Shift bar left: "← Search"   ·   "Gate booth · Jaipur · Shift: Ramesh K."   /   right: "End shift"
- Identity line: "SHP1015 · Ravi K."   (shipment ID in mono, driver name in Inter)
- Carrier line: "Rajasthan Roadlines"
- State row: none in this state
- Appointment line: "Appointment: D5 · Tue 4 Aug · 18:00–19:00"
- Button: "Gate in"
The button label is always the specific imperative verb for the valid action — never "Next", never
"Continue", never "Submit". The verb is itself the officer's confirmation that they are about to do the
right thing.
The appointment line must never truncate and must always carry its dock AND its date. If it does not fit,
the container is wrong.

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1) on the card entering; 120ms on focus. No hover lift,
no scale, no ambient motion. Instant under prefers-reduced-motion.

Explicitly exclude: a second button of any kind, a Cancel, an "Are you sure" step, an overflow menu, a
dock-selection dropdown (the dock comes from the confirmed appointment, the officer never picks one), an
editable field on this screen, a map, a driver photo or avatar, a phone/call button, a notes field, a
timeline or history strip, a progress stepper, a sidebar, a top app bar with tabs, a bottom tab bar,
gradients, blur, emoji, any dark-mode artboard, any facility accent colour.
```

---

## 7 · Truck found — `WAITING_EARLY` / `WAITING_LATE` → Call to dock (yard tablet, portrait)

`screens.md` §3 · icon `door-open` (Lucide) per `../00-foundations/iconography.md`. Most frequent action on
the surface (Flow 4 — `update_queue_state` targeting `CALLED_TO_DOCK`).

```
Copy-paste into Stitch — SetuHaul Dock Command · Yard tablet · Truck waiting, call to dock (portrait)

Product context: B2B internal logistics operations tool, handheld tablet, yard marshal walking an outdoor
truck yard in gloves and sun. The truck is checked in and waiting in the yard; the one valid action is to
call it forward to its dock.

Frame: 800 x 1280, portrait.

One button only. The truck's current state determines the action; the marshal never chooses between
options. Do not add a secondary button.

Typography: Inter 400/500/600/700; JetBrains Mono 400/500 for shipment ID, dock code, date and time range.
Shift bar 16/1.5/500; identity line 20/1.4/600; carrier 16/1.5/400; state label 20/1.4/600; appointment
16/1.5/400; button label 20/1.4/700. No text below 14px.

Color, light theme only: page #F8FAFC; outer card #FFFFFF with 1px #E2E8F0 and shadow 0 1px 2px
rgba(15,23,42,0.06); identity block #F1F5F9; primary text #0F172A; carrier and appointment #475569; 1px
#CBD5E1 rule above the appointment line; primary button #2563EB / #FFFFFF label, hover #1D4ED8, pressed
#1E40AF; focus ring inner 2px #FFFFFF + outer 2px #2563EB.

State row: a Lucide "door-open" icon at 24px, 2px stroke, drawn in #0F172A — the same colour as its label.
The state is NOT colour-coded. Colour in this product is rationed to promise state and danger only; a queue
state carries its meaning in the icon shape and the words, which is also what keeps it legible on a
washed-out screen in direct sun.

Spacing: 4px base, spacious. Card padding 24px; identity block padding 24px; 16px gap between blocks and
between lines; 8px gap between the state icon and its label; 24px device-edge padding.

Touch targets: the primary button is full width and minimum 56px tall, positioned in the lower-middle of
the portrait frame so it falls in a one-handed thumb arc — not flush to the bottom edge. Keep at least 16px
of dead space below it.

Radius: card 8px, identity block 6px, button 6px.

Layout: shift bar with a back control; one full-width card; inside it the identity block (identity line,
carrier, state row, rule, appointment line) then the button. Nothing else.

Exact copy, verbatim:
- Shift bar: "← Search"  ·  "Yard tablet · Jaipur · Shift: Priya S."   /   right: "End shift"
- Identity line: "SHP1015 · Ravi K."
- Carrier: "Rajasthan Roadlines"
- State row: door-open icon + "Waiting (late)"
- Appointment: "Appointment: D5 · Tue 4 Aug · 18:00–19:00"
- Button: "Call to dock"

Second artboard, early variant: identical layout, state row reads "Waiting (early)" with the same
door-open icon. Same single button, same label.

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1); 120ms focus. No hover lift, no pulse, no ambient
motion. Instant under prefers-reduced-motion.

Explicitly exclude: a second button, Cancel, an "Are you sure" step, a dock picker, a queue-position
stepper or +/- control, a drag handle, a map of the yard, a driver photo, a call/phone button, a notes
field, a progress bar or stepper across the top, a coloured status pill using red/amber/green for the queue
state, a sidebar, top app bar, bottom tab bar, gradients, blur, emoji, any dark-mode artboard.
```

---

## 8 · Truck found — `WAITING_DOCK_UNAVAILABLE` → Call to dock, retried (yard tablet, portrait)

`screens.md` §3 · icon `door-closed`. The officer is **not blocked from trying again** — the tool decides
whether the dock is actually free now, not the kiosk.

```
Copy-paste into Stitch — SetuHaul Dock Command · Yard tablet · Waiting, dock unavailable (portrait)

Product context: B2B internal logistics operations tool, handheld tablet, yard marshal in gloves outdoors.
This truck was called before and the dock was not free. The action offered is the same one, retried — the
kiosk does not block the attempt, because only the server knows whether the dock has since cleared.

Frame: 800 x 1280, portrait.

One button only. Same label as the un-blocked waiting state — do not rename it "Retry" or "Try again", and
do not disable it. Disabling it here would tell the marshal something the kiosk does not actually know.

Typography: Inter 400/500/600/700; JetBrains Mono 400/500 for ID, dock, date, time. Shift bar 16/1.5/500;
identity line 20/1.4/600; carrier 16/1.5/400; state label 20/1.4/600; appointment 16/1.5/400; button label
20/1.4/700. No text below 14px.

Color, light theme only: page #F8FAFC; card #FFFFFF, 1px #E2E8F0, shadow 0 1px 2px rgba(15,23,42,0.06);
identity block #F1F5F9; primary text #0F172A; secondary #475569; primary button #2563EB / #FFFFFF; focus
ring inner 2px #FFFFFF + outer 2px #2563EB.

State row: Lucide "door-closed" at 24px, 2px stroke, in #0F172A — deliberately a DIFFERENT GLYPH from the
open-door used for ordinary waiting, not a different colour. The distinction has to survive a sun-washed
screen and a colour-blind reader, so it is carried by the drawing, not the tint.

Spacing, targets, radius: identical to the ordinary waiting screen — card padding 24px, stack gap 16px,
full-width button minimum 56px tall in the lower-middle thumb arc, card radius 8px, block 6px, button 6px,
24px device-edge padding.

Exact copy, verbatim:
- Shift bar: "← Search"  ·  "Yard tablet · Jaipur · Shift: Priya S."   /   right: "End shift"
- Identity line: "SHP1009 · Amit S."
- Carrier: "Kota Transport"
- State row: door-closed icon + "Waiting — dock unavailable"
- Appointment: "Appointment: D2 · Tue 4 Aug · 14:00–14:45"
- Button: "Call to dock"

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1). No pulse, no attention-seeking animation on the state
row — this is a fact, not an alarm. Instant under prefers-reduced-motion.

Explicitly exclude: a disabled or greyed button, a countdown or timer, a "dock will be free at…" estimate
(the kiosk does not have that data), a red banner (this is not an error state), an auto-refresh spinner, a
second button, a dock picker, a sidebar, top app bar, bottom tab bar, gradients, blur, emoji, any dark-mode
artboard.
```

---

## 9 · Truck found — `CALLED_TO_DOCK` → Dock in (yard tablet, portrait)

`screens.md` §3 · icon `bell-ring` · Flow 5. The `dock_id` submitted is the **confirmed appointment's**
dock — the officer never picks one from a list.

```
Copy-paste into Stitch — SetuHaul Dock Command · Yard tablet · Called to dock, dock in (portrait)

Product context: B2B internal logistics operations tool, handheld tablet, yard marshal in gloves outdoors.
This truck has been called forward. The one valid action is to record that it has arrived at its dock.

Frame: 800 x 1280, portrait.

One button only.

Critical content rule: the dock shown in the appointment line is the dock the action submits. The officer
does NOT choose a dock. If the truck physically pulled into a different bay, that mismatch is something the
server reports back afterwards — it is never something the officer selects up front. Do not render a dock
selector, a bay grid, or an editable dock field anywhere on this screen.

Typography: Inter 400/500/600/700; JetBrains Mono 400/500 for ID, dock code, date, time. Shift bar
16/1.5/500; identity 20/1.4/600; carrier 16/1.5/400; state label 20/1.4/600; appointment 16/1.5/400; button
20/1.4/700. No text below 14px.

Color, light theme only: page #F8FAFC; card #FFFFFF, 1px #E2E8F0, shadow 0 1px 2px rgba(15,23,42,0.06);
identity block #F1F5F9; primary text #0F172A; secondary #475569; 1px #CBD5E1 rule above the appointment
line; button #2563EB / #FFFFFF, hover #1D4ED8, pressed #1E40AF; focus ring inner 2px #FFFFFF + outer 2px
#2563EB.

State row: Lucide "bell-ring" at 24px, 2px stroke, #0F172A. No colour coding, no badge, no dot.

Spacing: 4px base, spacious. Card padding 24px, identity block 24px, 16px stack gap, 24px device-edge
padding.

Touch target: full-width button, minimum 56px tall, lower-middle thumb arc, 16px clear below it.

Radius: card 8px, block 6px, button 6px.

Exact copy, verbatim:
- Shift bar: "← Search"  ·  "Yard tablet · Jaipur · Shift: Priya S."   /   right: "End shift"
- Identity line: "SHP1009 · Amit S."
- Carrier: "Kota Transport"
- State row: bell-ring icon + "Called to dock"
- Appointment: "Appointment: D2 · Tue 4 Aug · 14:00–14:45"
- Button: "Dock in"

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1); 120ms focus. No bell animation, no ring/pulse effect
on the icon. Instant under prefers-reduced-motion.

Explicitly exclude: a dock selector or bay picker of any kind, a map or yard diagram, a photo-capture step,
a signature pad, a second button, a Cancel, an "Are you sure" confirmation, a timer, a sidebar, top app bar,
bottom tab bar, gradients, blur, emoji, any dark-mode artboard.
```

---

## 10 · Truck found — `IN_DOCK` → Start unload / End unload (yard tablet, portrait)

`screens.md` §3 · icon `truck` for both · Flow 6. Two artboards, same state icon, different verb — the
distinction is whether an unload start has already been recorded.

```
Copy-paste into Stitch — SetuHaul Dock Command · Yard tablet · In dock, unload start and end (portrait)

Product context: B2B internal logistics operations tool, handheld tablet, yard marshal in gloves outdoors
at a dock face. The truck is in its dock. The one valid action is either to record that unloading has
started, or — if it already has — that it has finished.

Frame: 800 x 1280, portrait. Produce TWO artboards.

One button per artboard. The two states are never shown together and there is never a choice between them.

Typography: Inter 400/500/600/700; JetBrains Mono 400/500 for ID, dock, date, time and the elapsed figure.
Shift bar 16/1.5/500; identity 20/1.4/600; carrier 16/1.5/400; state label 20/1.4/600; appointment and
supporting line 16/1.5/400; button 20/1.4/700. No text below 14px.

Color, light theme only: page #F8FAFC; card #FFFFFF, 1px #E2E8F0, shadow 0 1px 2px rgba(15,23,42,0.06);
identity block #F1F5F9; primary text #0F172A; secondary #475569; 1px #CBD5E1 rule above the appointment
line; button #2563EB / #FFFFFF; focus ring inner 2px #FFFFFF + outer 2px #2563EB.

State row: Lucide "truck" at 24px, 2px stroke, #0F172A, on both artboards.

Spacing / targets / radius: card padding 24px, block padding 24px, 16px stack gap, 24px device-edge
padding; full-width button minimum 56px tall in the lower-middle thumb arc; card 8px, block 6px, button
6px.

Artboard A — unload not yet started:
- Identity line: "SHP1009 · Amit S."
- Carrier: "Kota Transport"
- State row: truck icon + "In dock"
- Appointment: "Appointment: D2 · Tue 4 Aug · 14:00–14:45"
- Button: "Start unload"

Artboard B — unload in progress:
- Same identity, carrier, state row and appointment line
- One additional supporting line directly under the state row, in #475569: "Unload started 14:12"
  (mono for the time). This is a recorded fact, not a live counter.
- Button: "End unload"

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1); 120ms focus. Nothing on this screen ticks, counts, or
animates — the "unload started" line is a static recorded timestamp, not a running clock. Instant under
prefers-reduced-motion.

Explicitly exclude: a live elapsed-time counter or stopwatch, a progress bar for the unload, a percentage,
a pause button, a photo or damage-report step, a quantity or pallet-count field, a second button, a Cancel,
a sidebar, top app bar, bottom tab bar, gradients, blur, emoji, any dark-mode artboard.
```

---

## 11 · Truck found — `COMPLETED` → Gate out (gate-booth kiosk, landscape)

`screens.md` §3 · icon `check` · Flow 7. Terminal action for a truck; the outcome carries dwell time.

```
Copy-paste into Stitch — SetuHaul Dock Command · Gate-booth kiosk · Completed, gate out (landscape)

Product context: B2B internal logistics operations tool, mounted gate-booth tablet, gate officer in gloves.
The truck has finished unloading and is at the barrier to leave. The one valid action is to record its
departure.

Frame: 1280 x 800, landscape, fixed.

One button only.

Typography: Inter 400/500/600/700; JetBrains Mono 400/500 for ID, dock, date, time. Shift bar 16/1.5/500;
identity 20/1.4/600; carrier 16/1.5/400; state label 20/1.4/600; appointment 16/1.5/400; button 20/1.4/700.
No text below 14px.

Color, light theme only: page #F8FAFC; card #FFFFFF, 1px #E2E8F0, shadow 0 1px 2px rgba(15,23,42,0.06);
identity block #F1F5F9; primary text #0F172A; secondary #475569; button #2563EB / #FFFFFF; focus ring inner
2px #FFFFFF + outer 2px #2563EB.

State row: Lucide "check" at 24px, 2px stroke, #0F172A. Important: this check is NOT green and is NOT
inside a filled circle or badge. Green in this product means a confirmed capacity promise, and this row is
a yard queue state, not a promise. Rendering it green would borrow a meaning that belongs to a different
component.

Spacing / targets / radius: content padding 32px, card padding 24px, block padding 24px, 16px stack gap,
24px device-edge padding; full-width button minimum 56px tall; card 8px, block 6px, button 6px. Card about
720px wide, centred.

Exact copy, verbatim:
- Shift bar: "← Search"  ·  "Gate booth · Jaipur · Shift: Ramesh K."   /   right: "End shift"
- Identity line: "SHP1015 · Ravi K."
- Carrier: "Rajasthan Roadlines"
- State row: check icon + "Completed"
- Appointment: "Appointment: D5 · Tue 4 Aug · 18:00–19:00"
- Button: "Gate out"

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1); 120ms focus. No celebratory animation, no confetti,
no checkmark draw-in. A capacity system does not celebrate. Instant under prefers-reduced-motion.

Explicitly exclude: green styling on the check icon or the state row, a success banner (this screen is a
pending action, not an outcome), a signature capture, a paperwork checklist, a rating prompt, a second
button, a sidebar, top app bar, bottom tab bar, gradients, blur, emoji, any dark-mode artboard.
```

---

## 12 · Truck found — terminal, no action available

`edge-cases.md` #6. The card still renders so the officer can confirm what happened, but **no button
renders at all** — not a greyed one. There is genuinely no action here, not a temporarily unavailable one
(`../00-foundations/components.md` §18: Disabled means *temporarily* unavailable; absence means there is
nothing).

```
Copy-paste into Stitch — SetuHaul Dock Command · Gate-booth kiosk · Truck already gated out (landscape)

Product context: B2B internal logistics operations tool, mounted gate-booth tablet, gate officer in gloves.
The officer searched a truck that has already completed its whole cycle and left. Nothing remains to be
done to it. This is a routine repeat lookup, not an error.

Frame: 1280 x 800, landscape, fixed.

The defining rule of this screen: there is NO button. Not a greyed-out button, not a disabled one, not a
button with a tooltip. A greyed control would say "this action exists but is unavailable right now", which
is false — the truck's cycle is over and there is no next action at all. Under direct sunlight a greyed
control is also indistinguishable from a rendering failure. Render the record, and nothing else.

Typography: Inter 400/500/600/700; JetBrains Mono 400/500 for ID, dock, date, times and the dwell figure.
Shift bar 16/1.5/500; identity 20/1.4/600; carrier 16/1.5/400; state label 20/1.4/600; terminal fact line
16/1.5/400; back control 16/1.5/600. No text below 14px.

Color, light theme only: page #F8FAFC; card #FFFFFF, 1px #E2E8F0, shadow 0 1px 2px rgba(15,23,42,0.06);
identity block #F1F5F9; primary text #0F172A; secondary #475569; 1px #CBD5E1 rule above the terminal fact
line. No accent colour anywhere on this screen — nothing here is actionable, so nothing gets the
interactive blue.

Spacing / radius: content padding 32px, card padding 24px, block padding 24px, 16px stack gap, 24px
device-edge padding; card 8px, block 6px. Card about 720px wide, centred. Where the button would have sat,
leave the space empty — do not restretch the card to close the gap, and do not fill it with a message
block.

Touch target: the only interactive element on screen is the "← Search" control in the shift bar, and it is
minimum 56px tall.

Exact copy, verbatim:
- Shift bar: "← Search"  ·  "Gate booth · Jaipur · Shift: Ramesh K."   /   right: "End shift"
- Identity line: "SHP1015 · Ravi K."
- Carrier: "Rajasthan Roadlines"
- State row: Lucide "check" icon, 24px, 2px stroke, #0F172A + "Completed"
- Appointment: "Appointment: D5 · Tue 4 Aug · 18:00–19:00"
- Terminal fact line: "Gate-out recorded 19:14 · dwell 1h 22m"

Motion: none beyond a 200ms ease-out card entrance. Nothing on this screen changes. Instant under
prefers-reduced-motion.

Explicitly exclude: a disabled or greyed button, a "no actions available" empty-state illustration, a
history timeline of the truck's events, a re-open or correct-this-record affordance (corrections are not a
kiosk capability), a print or export control, a toast, a modal, a sidebar, top app bar, bottom tab bar,
gradients, blur, emoji, any dark-mode artboard.
```

---

## 13 · Primary action — state sheet (default / pressed / submitting / inactive-offline)

`components.md` §4 (this folder) · `../00-foundations/components.md` §1, §18 · `edge-cases.md` #7 · U70,
U84. The submitting state is the one most likely to be got wrong: the label never leaves.

```
Copy-paste into Stitch — SetuHaul Dock Command · Gate/yard kiosk · Primary action button, all states

Product context: B2B internal logistics operations tool used outdoors on tablets by officers wearing work
gloves. This is a component state sheet, not a screen: one full-width primary button rendered in four
states, laid out vertically with a short caption above each.

Frame: 800 x 1280, portrait. Each button spans the full content width (roughly 720px inside 24px edge
padding + 16px inner margin), minimum 56px tall.

Typography: Inter 400/500/600/700. Button label 20px / 1.4 / 700. State caption above each button 16px /
1.5 / 600 in #475569. Inactive-state reason text 16px / 1.5 / 400. No text below 14px.

The four states, top to bottom, each captioned:

1. "Default" — background #2563EB, label #FFFFFF, no border, no gradient, no shadow, radius 6px, height
   56px, label "Gate in".

2. "Pressed" — background #1E40AF, label #FFFFFF, same size exactly. No scale-down, no shrink, no shadow
   change, no ripple. The colour step is the entire press feedback; a transform on a 56px target under a
   gloved finger just makes the target feel unstable.

3. "Submitting" — background stays #2563EB, label stays "Gate in" and does NOT disappear, and a 20px
   spinner sits to the LEFT of the label in the leading-icon position. The button width is frozen so
   nothing reflows. This is the rule that matters most here: a spinner must never replace the label,
   because a label-less control under gloves invites a mis-tap on whatever renders next. Show nothing at
   all for the first second of a request — an indicator that flashes for under a second is pure
   distraction — then this state.

4. "Inactive — connection unconfirmed" — background #FFFFFF, 1px border #CBD5E1, label #0F172A at FULL
   contrast (deliberately NOT faded like a normal disabled control), a Lucide "wifi-off" icon 20px 2px
   stroke to the left of the label, and a reason line directly beneath the button in #0F172A reading:
   "Can't confirm this will save — check connection". The control stays focusable and tappable; tapping it
   surfaces the explanation rather than doing nothing. Reason: on a sun-washed outdoor screen a faded,
   unfocusable grey rectangle is indistinguishable from a rendering failure, and an officer who cannot tell
   WHY a button won't respond is locked out just as thoroughly as one who cannot read the screen.

Also render, below state 4, the retry message block that follows a failed write: background #FFFBEB, 1px
border #F59E0B, text #B45309, radius 6px, padding 20px, containing the line "That didn't record — nothing
has changed." and beneath it "Try again — this won't record it twice." The second sentence is required
copy, not reassurance filler: every action on this surface carries an idempotency key, so retrying is
genuinely safe and the officer is told so.

Focus state, shown once on the default button: two rings — inner 2px #F8FAFC, outer 2px #2563EB, 2px
offset. Never a soft glow.

Motion: colour transitions 120ms ease-out cubic-bezier(0.16, 1, 0.3, 1). The spinner is the only looping
element and only while a request is in flight. No ripple, no bounce, no scale, no shadow animation. Under
prefers-reduced-motion the spinner becomes a static indeterminate bar.

Explicitly exclude: a faded low-contrast disabled variant (this surface uses the full-contrast inactive
treatment instead), a ripple or material-style ink effect, a hover lift or scale, a shadow that grows on
press, an icon-only variant (icon-only controls are forbidden here), a pill/fully-rounded shape, a gradient
fill, a destructive red variant (no action on this surface is destructive), any dark-mode artboard.
```

---

## 14 · Outcome — Gate-in recorded (success)

`screens.md` §4 · `components.md` §5 · Flow 3. The computed `arrival_state` (EARLY / ON_TIME / LATE) is
surfaced, not buried — an early truck may still have to wait.

```
Copy-paste into Stitch — SetuHaul Dock Command · Gate-booth kiosk · Gate-in recorded (landscape)

Product context: B2B internal logistics operations tool, mounted gate-booth tablet, gate officer in gloves
with another truck already waiting behind. This screen states exactly what was just recorded, then gets out
of the way. The officer reads it in about two seconds and moves on.

Frame: 1280 x 800, landscape, fixed.

Typography: Inter 400/500/600/700; JetBrains Mono 400/500 for the identifier, timestamp and arrival state.
Headline 20px / 1.4 / 700; fact line 16px / 1.5 / 400 in mono; button label 20px / 1.4 / 700. No text below
14px.

Color, light theme only:
- Page #F8FAFC; outer card #FFFFFF, 1px #E2E8F0, shadow 0 1px 2px rgba(15,23,42,0.06)
- Success block: background #ECFDF5, 1px border #059669, headline text #047857, radius 6px, padding 24px
- Do NOT use #059669 for the headline text — it measures 3.8:1 on white and fails normal-text contrast.
  #047857 is the specified text step at 5.6:1. The 600 step is border/UI only.
- Fact line text #475569
- Button #2563EB with #FFFFFF label

Icon: a Lucide "check" at 32px, 2px stroke, in #047857, centred above the headline. Not inside a filled
circle, not animated, no draw-in.

Spacing: 4px base, spacious. Content padding 32px; success block padding 24px; 16px between the block and
the button; 24px device-edge padding.

Touch target: one full-width button, minimum 56px tall.

Radius: card 8px, success block 6px, button 6px.

Layout: shift bar at top; one centred card about 720px wide containing the success block (icon, headline,
fact line, centred) and then the button beneath it. Nothing else on screen.

Exact copy, verbatim:
- Shift bar: "Gate booth · Jaipur · Shift: Ramesh K."   /   right: "End shift"
- Headline: "Gate-in recorded"
- Fact line: "SHP1015 · 18:04 · ON_TIME"
- Button: "Search next truck"
Do not write "Success", "Done", "Successfully recorded" or "Great!". Every outcome on this surface names
the specific thing that was recorded. A bare "Done" tells an officer nothing about what is now true.
No exclamation marks anywhere.

Motion: the card enters at 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1). No checkmark animation, no
confetti, no scale-in, no celebratory motion of any kind. Instant under prefers-reduced-motion.

Explicitly exclude: confetti or celebration graphics, an animated tick, a share/print control, a "view
details" link, an undo affordance (this is a factual record of something that physically happened, not a
reversible commitment), a rating or feedback prompt, a dismiss X on the block, an auto-dismissing toast
instead of this screen, a sidebar, top app bar, bottom tab bar, gradients, blur, emoji, any dark-mode
artboard.
```

*Non-visual behaviour to annotate: 15ms haptic pulse on a recorded gate event; the headline is announced
politely to assistive tech (successful writes are polite, failures are assertive).*

---

## 15 · Outcome — brief success family (queue updated / dock-in / unload recorded)

`components.md` §5 · Flows 4, 5, 6. The most frequent outcomes on the surface; they state the fact and stay
out of the way.

```
Copy-paste into Stitch — SetuHaul Dock Command · Yard tablet · Brief success outcomes (portrait)

Product context: B2B internal logistics operations tool, handheld tablet, yard marshal in gloves outdoors
moving to the next truck immediately. These are the highest-frequency outcomes on the surface — they must
be readable at a glance and must not linger or demand interaction.

Frame: 800 x 1280, portrait. Produce THREE artboards, identical in layout, differing only in the headline
and fact line.

Typography: Inter 400/500/600/700; JetBrains Mono 400/500 for identifiers, dock codes and timestamps.
Headline 20/1.4/700; fact line 16/1.5/400 mono; button 20/1.4/700. No text below 14px.

Color, light theme only: page #F8FAFC; card #FFFFFF, 1px #E2E8F0, shadow 0 1px 2px rgba(15,23,42,0.06);
success block background #ECFDF5, 1px border #059669, headline text #047857 (not #059669 — that step fails
normal-text contrast at 3.8:1), fact text #475569; button #2563EB / #FFFFFF.

Icon: Lucide "check", 32px, 2px stroke, #047857, centred above the headline, static.

Spacing / targets / radius: success block padding 24px, 16px gap to the button, card padding 24px, 24px
device-edge padding; full-width button minimum 56px tall in the lower-middle thumb arc; card 8px, block
6px, button 6px.

Layout: shift bar "Yard tablet · Jaipur · Shift: Priya S." with "End shift" at the right; one full-width
card holding the success block and, beneath it, the single button "Search next truck".

Artboard A — headline "Called to dock", fact line "SHP1009 · D2 · 14:06"
Artboard B — headline "Dock-in recorded", fact line "SHP1009 · D2 · 14:09"
Artboard C — headline "Unload started", fact line "SHP1009 · D2 · 14:12"
Button on all three: "Search next truck"

Every headline names the specific thing recorded. Never "Success", never "Done", never "Saved". 24-hour
time throughout, never AM/PM. Never a time without its dock.

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1) on entry. Nothing else moves. No auto-dismiss timer,
no progress ring counting down to the next screen — the officer decides when to move on, because they may
be interrupted mid-task by another truck. Instant under prefers-reduced-motion.

Explicitly exclude: an auto-advancing timer or countdown, a toast in place of the screen, confetti or
celebration, an undo control, a "view record" link, a share/print control, a dismiss X, a sidebar, top app
bar, bottom tab bar, gradients, blur, emoji, any dark-mode artboard.
```

---

## 16 · Outcome — Gate-out recorded, with dwell time (success)

`components.md` §5 · Flow 7. Dwell (`gate_out − gate_in`) is the raw material for the detention metric, so
it is surfaced rather than computed silently.

```
Copy-paste into Stitch — SetuHaul Dock Command · Gate-booth kiosk · Gate-out recorded (landscape)

Product context: B2B internal logistics operations tool, mounted gate-booth tablet, gate officer in gloves.
The truck has left. This is the terminal record for that truck's visit, and it carries one extra fact the
other success screens do not: how long the truck was on site.

Frame: 1280 x 800, landscape, fixed.

Typography: Inter 400/500/600/700; JetBrains Mono 400/500 for the identifier, timestamp and dwell figure.
Headline 20/1.4/700; fact line 16/1.5/400 mono; secondary dwell label 16/1.5/400; button 20/1.4/700. No
text below 14px.

Color, light theme only: page #F8FAFC; card #FFFFFF, 1px #E2E8F0, shadow 0 1px 2px rgba(15,23,42,0.06);
success block #ECFDF5 with 1px #059669 border and #047857 headline text (never #059669 for text — 3.8:1
fails); fact text #475569; button #2563EB / #FFFFFF.

Icon: Lucide "check", 32px, 2px stroke, #047857, centred, static.

Spacing / targets / radius: content padding 32px; success block padding 24px; 16px to the button; 24px
device-edge padding; full-width button minimum 56px tall; card 8px, block 6px, button 6px; card about 720px
wide, centred.

Exact copy, verbatim:
- Shift bar: "Gate booth · Jaipur · Shift: Ramesh K."   /   right: "End shift"
- Headline: "Gate-out recorded"
- Fact line: "SHP1015 · 19:14 · dwell 1h 22m"
- Button: "Search next truck"
The dwell figure is a measured fact, not an assessment. Do not add a judgement ("good", "over target",
a green or red arrow, a benchmark comparison) — this surface records; other surfaces evaluate.

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1). No number counting up, no animated dwell figure, no
celebration. Values are not scores. Instant under prefers-reduced-motion.

Explicitly exclude: a dwell-time gauge, chart, sparkline or benchmark bar; a coloured up/down delta on the
dwell figure; confetti; a "trip complete" summary card listing every event; a print/export control; an undo
affordance; a rating prompt; a sidebar, top app bar, bottom tab bar; gradients; blur; emoji; any dark-mode
artboard.
```

---

## 17 · Outcome — Different dock (`DOCK_MISMATCH`)

`screens.md` §4 · `components.md` §5 · Flow 5. **Not an error.** The tool contract says it is "allowed, but
recorded as a deviation." Danger framing here would train officers to under-report honest deviations.

```
Copy-paste into Stitch — SetuHaul Dock Command · Yard tablet · Different dock recorded (portrait)

Product context: B2B internal logistics operations tool, handheld tablet, yard marshal in gloves outdoors.
The truck pulled into a different dock from the one on its confirmed appointment. The system accepted it
and recorded it as a deviation. This is NOT a rejection and NOT the officer's mistake — they recorded what
actually happened, which is exactly what they should have done. The screen must read that way or officers
will learn to avoid recording real deviations.

Frame: 800 x 1280, portrait.

Typography: Inter 400/500/600/700; JetBrains Mono 400/500 for the two dock codes. Headline 20/1.4/700; the
two dock lines 16/1.5/400 with mono dock codes; the explanatory line 16/1.5/400; button 20/1.4/700. No text
below 14px.

Color, light theme only — warning, never danger:
- Page #F8FAFC; card #FFFFFF, 1px #E2E8F0, shadow 0 1px 2px rgba(15,23,42,0.06)
- Warning block: background #FFFBEB, 1px border #F59E0B, headline text #B45309, radius 6px, padding 24px
- Do NOT use #D97706 for the headline text — 3.2:1 on white, fails normal text. #B45309 is the specified
  text step at 5.1:1. The 500/600 amber steps are border and UI only.
- Do NOT use any red on this screen. Red means danger in this system — expiry, conflict, escalation — and
  nothing here has gone wrong.
- Supporting text #475569; button #2563EB / #FFFFFF

Icon: a Lucide "alert-triangle" at 32px, 2px stroke, #B45309, centred above the headline. The icon shape
and the words carry the meaning; the amber tint is a third channel, never the only one — a sun-washed
screen must still read correctly.

Spacing / targets / radius: warning block padding 24px, 16px internal stack gap, 16px gap to the button,
24px device-edge padding; full-width button minimum 56px tall; card 8px, block 6px, button 6px.

Layout: shift bar; one full-width card; inside it the warning block with icon and headline centred, then
the two dock lines as a left-aligned pair (label left, value right, with the mono values aligned), then the
explanatory line, then the button beneath the block.

Exact copy, verbatim:
- Shift bar: "Yard tablet · Jaipur · Shift: Priya S."   /   right: "End shift"
- Headline: "Different dock"
- Line 1: "Confirmed dock: D2"
- Line 2: "Actual dock: D4"
- Explanatory line: "Recorded as a deviation — not an error."
- Button: "Search next truck"
Do not add "Please correct this", "Are you sure?", "This may cause a delay", or any wording implying the
officer should have done something else.

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1) on entry. No shake, no pulse, no attention-grabbing
animation — this is a fact being filed, not an alarm. Instant under prefers-reduced-motion.

Explicitly exclude: any red colour, an error/X icon, a "report a problem" link, a correction or "change
dock" affordance, an undo control, a confirmation step, a dismiss X on the block (warning messages are not
dismissible), a toast in place of the screen, a sidebar, top app bar, bottom tab bar, gradients, blur,
emoji, any dark-mode artboard.
```

---

## 18 · Outcome — Unload overrun

`components.md` §5 · Flow 6. States the delta against `expected_unload_min` as a fact. The officer is not
asked to do anything about it — it feeds re-sequencing and churn pricing downstream.

```
Copy-paste into Stitch — SetuHaul Dock Command · Yard tablet · Unload ended, over expected (portrait)

Product context: B2B internal logistics operations tool, handheld tablet, yard marshal in gloves outdoors.
Unloading finished later than the expected duration for this load. The overrun is recorded as a fact and
feeds scheduling decisions elsewhere in the system. The officer is not being asked to explain it, justify
it, or fix it.

Frame: 800 x 1280, portrait.

Typography: Inter 400/500/600/700; JetBrains Mono 400/500 for the identifier, times and the overrun figure.
Headline 20/1.4/700; fact lines 16/1.5/400; button 20/1.4/700. No text below 14px.

Color, light theme only — warning, never danger: page #F8FAFC; card #FFFFFF, 1px #E2E8F0, shadow 0 1px 2px
rgba(15,23,42,0.06); warning block background #FFFBEB, 1px border #F59E0B, headline text #B45309 (never
#D97706 for text — 3.2:1 fails); supporting text #475569; button #2563EB / #FFFFFF. No red anywhere.

Icon: Lucide "alert-triangle", 32px, 2px stroke, #B45309, centred, static.

Spacing / targets / radius: block padding 24px, 16px internal gap, 16px to the button, 24px device-edge
padding; full-width button minimum 56px tall; card 8px, block 6px, button 6px.

Exact copy, verbatim:
- Shift bar: "Yard tablet · Jaipur · Shift: Priya S."   /   right: "End shift"
- Headline: "Unload ended · 22 min over expected"
- Fact line 1: "SHP1009 · D2 · 14:12–15:34"
- Fact line 2: "Expected 60 min · actual 82 min"
- Button: "Search next truck"
Use an en dash in the time range. 24-hour time only. A space between number and unit ("22 min"), never
"22min". Never pluralise a unit symbol.

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1). No animated counter, no bar filling past a marker.
Instant under prefers-reduced-motion.

Explicitly exclude: a required "reason for delay" field or dropdown, a comment box, an escalation button, a
red treatment, a progress or over-budget bar, a comparison chart, a target-vs-actual gauge, an apology or
blame in the copy, a dismiss X, a sidebar, top app bar, bottom tab bar, gradients, blur, emoji, any
dark-mode artboard.
```

---

## 19 · Outcome — Already gated in (`ALREADY_CHECKED_IN`)

`edge-cases.md` #1. States the existing check-in's timestamp rather than a bare rejection — from the
officer's position the truck genuinely is gated in, whoever recorded it.

```
Copy-paste into Stitch — SetuHaul Dock Command · Gate-booth kiosk · Already gated in (landscape)

Product context: B2B internal logistics operations tool, mounted gate-booth tablet, gate officer in gloves.
The officer tried to gate in a truck that already has a check-in for this visit — usually because a second
officer did it, or because they re-searched after not seeing the first outcome clearly. Nothing is broken.
The truck IS gated in; this attempt simply recorded nothing new.

Frame: 1280 x 800, landscape, fixed.

Typography: Inter 400/500/600/700; JetBrains Mono 400/500 for the identifier and timestamp. Headline
20/1.4/700; fact line 16/1.5/400; supporting line 16/1.5/400; button 20/1.4/700. No text below 14px.

Color, light theme only — informational, not danger and not success:
- Page #F8FAFC; card #FFFFFF, 1px #E2E8F0, shadow 0 1px 2px rgba(15,23,42,0.06)
- Info block: background #EFF6FF, 1px border #3B82F6, headline text #1D4ED8, radius 6px, padding 24px
- Supporting text #475569; button #2563EB / #FFFFFF
- Do not use green (nothing new was recorded) and do not use red (nothing went wrong).

Icon: Lucide "circle-alert" at 32px, 2px stroke, #1D4ED8, centred above the headline, static.

Spacing / targets / radius: content padding 32px; block padding 24px; 16px to the button; 24px device-edge
padding; full-width button minimum 56px tall; card 8px, block 6px, button 6px; card about 720px wide,
centred.

Exact copy, verbatim:
- Shift bar: "Gate booth · Jaipur · Shift: Ramesh K."   /   right: "End shift"
- Headline: "Already gated in at 17:52"
- Fact line: "SHP1015 · Ravi K."
- Supporting line: "Nothing new was recorded. This truck is already checked in."
- Button: "Search next truck"
Do not write "Error", "Duplicate", "Rejected", or "You already did this". The officer needs to know the
truck's actual state, not to be told off.

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1). No shake, no alert animation. Instant under
prefers-reduced-motion.

Explicitly exclude: red or amber treatment, an X or error icon, a "force gate-in anyway" override, a "who
recorded this" audit link, a correction affordance, a dismiss X, a modal, a sidebar, top app bar, bottom
tab bar, gradients, blur, emoji, any dark-mode artboard.
```

---

## 20 · Outcome — No active appointment (`NO_ACTIVE_APPOINTMENT`)

`edge-cases.md` #2. The kiosk **cannot resolve this** — it has no scheduling controls. The screen states
the fact and offers no false next step; the officer's real next move (calling the facility office, holding
the truck) is outside this surface.

```
Copy-paste into Stitch — SetuHaul Dock Command · Gate-booth kiosk · No active appointment (landscape)

Product context: B2B internal logistics operations tool, mounted gate-booth tablet, gate officer in gloves
with a truck at the barrier. This truck has no matching appointment — a walk-in, a cancelled booking the
driver didn't hear about, or a data problem upstream. The kiosk has no scheduling powers at all and must
not pretend otherwise. The officer's real next step happens off-screen (phone the facility office, hold the
truck in the yard).

Frame: 1280 x 800, landscape, fixed.

The honesty rule for this screen: offer no kiosk action that would imply the officer can fix this here.
There is no "create appointment", no "book a slot", no "override". The only control is the way back.

Typography: Inter 400/500/600/700; JetBrains Mono 400/500 for the identifier. Headline 20/1.4/700; fact
line 16/1.5/400; supporting line 16/1.5/400; button 20/1.4/700. No text below 14px.

Color, light theme only — danger tone, because this genuinely blocks the truck:
- Page #F8FAFC; card #FFFFFF, 1px #E2E8F0, shadow 0 1px 2px rgba(15,23,42,0.06)
- Danger block: background #FEF2F2, 1px border #DC2626, headline text #B91C1C, radius 6px, padding 24px
- Use #B91C1C for the headline text, not #DC2626 — the 600 step is the border/UI step here
- Supporting text #475569; button #2563EB / #FFFFFF

Icon: Lucide "calendar-x" at 32px, 2px stroke, #B91C1C, centred above the headline, static.

Spacing / targets / radius: content padding 32px; block padding 24px; 16px to the button; 24px device-edge
padding; full-width button minimum 56px tall; card 8px, block 6px, button 6px; card about 720px wide.

Exact copy, verbatim:
- Shift bar: "Gate booth · Jaipur · Shift: Ramesh K."   /   right: "End shift"
- Headline: "No active appointment"
- Fact line: "SHP1015 · Ravi K. · Rajasthan Roadlines"
- Supporting line: "Nothing was recorded. This can't be fixed from the gate — contact the facility office."
- Button: "Back to search"
Note the button label differs from the success screens: nothing was recorded, so "Search next truck" would
imply this truck is dealt with. It is not.

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1). No shake, no flashing, no alarm animation. Instant
under prefers-reduced-motion.

Explicitly exclude: a "create appointment" or "book a slot" action, an override or force-entry control, a
phone-number link or click-to-call (the phone is a physical one in the booth; nothing in this product
supplies a number), a driver-contact affordance, an escalation button, a support chat, a dismiss X, a
modal, a sidebar, top app bar, bottom tab bar, gradients, blur, emoji, any dark-mode artboard.
```

---

## 21 · Outcome — Dock occupied (`DOCK_OCCUPIED`)

`edge-cases.md` #4. A real operational conflict, not a UI bug. The officer's next kiosk action is naturally
"Call to dock" again once it clears — which the state table already offers without a special case.

```
Copy-paste into Stitch — SetuHaul Dock Command · Yard tablet · Dock occupied (portrait)

Product context: B2B internal logistics operations tool, handheld tablet, yard marshal in gloves outdoors.
Dock-in was attempted but another truck's interval is genuinely live on that dock right now. This is a real
yard conflict, not a system error and not the marshal's mistake. They cannot resolve it from this device —
the truck waits in the yard queue and gets called again when the dock clears.

Frame: 800 x 1280, portrait.

Typography: Inter 400/500/600/700; JetBrains Mono 400/500 for the identifier and dock code. Headline
20/1.4/700; fact line 16/1.5/400; supporting line 16/1.5/400; button 20/1.4/700. No text below 14px.

Color, light theme only — warning, not danger: page #F8FAFC; card #FFFFFF, 1px #E2E8F0, shadow 0 1px 2px
rgba(15,23,42,0.06); warning block background #FFFBEB, 1px border #F59E0B, headline text #B45309 (never
#D97706 for text — 3.2:1 fails normal-text contrast); supporting text #475569; button #2563EB / #FFFFFF.
No red: nothing has failed, a dock is simply busy.

Icon: Lucide "door-closed" at 32px, 2px stroke, #B45309, centred above the headline, static. Deliberately
the same glyph the waiting-dock-unavailable state uses, so the officer connects this outcome to the state
the truck is about to sit in.

Spacing / targets / radius: block padding 24px, 16px internal gap, 16px to the button, 24px device-edge
padding; full-width button minimum 56px tall in the lower-middle thumb arc; card 8px, block 6px, button
6px.

Exact copy, verbatim:
- Shift bar: "Yard tablet · Jaipur · Shift: Priya S."   /   right: "End shift"
- Headline: "D2 is occupied"
- Fact line: "SHP1009 · Amit S."
- Supporting line: "Nothing was recorded. Keep this truck in the yard and call it again when D2 clears."
- Button: "Back to search"

Motion: 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1). No auto-retry spinner, no countdown to a retry.
Instant under prefers-reduced-motion.

Explicitly exclude: an "assign a different dock" control (the kiosk has no scheduling powers), an
auto-retry or polling indicator, an estimated clear time (the kiosk does not have that data), a red
treatment, a queue-position display, an escalation button, a dismiss X, a modal, a sidebar, top app bar,
bottom tab bar, gradients, blur, emoji, any dark-mode artboard.
```

---

## 22 · Outcome — Status changed, refreshing (`INVALID_TRANSITION`)

`edge-cases.md` #3 and #5. Two devices acting on the same truck seconds apart is the realistic cause; the
server's state machine is the coordination mechanism. The screen re-fetches and re-renders the truck's real
current state — it never retries the rejected transition.

```
Copy-paste into Stitch — SetuHaul Dock Command · Yard tablet · Truck status changed (portrait)

Product context: B2B internal logistics operations tool, handheld tablet, yard marshal in gloves outdoors.
A gate-booth officer and this marshal both acted on the same truck within seconds. The server accepted the
first and rejected this one because the truck had already moved on. Nothing is broken and nobody did
anything wrong — the device's picture of the truck was a few seconds stale. The screen re-fetches and shows
the truck's real current state with its real current action.

Frame: 800 x 1280, portrait. Produce TWO artboards showing the sequence.

Typography: Inter 400/500/600/700; JetBrains Mono 400/500 for the identifier, dock, date and time.
Headline 20/1.4/700; supporting line 16/1.5/400; identity 20/1.4/600; state label 20/1.4/600; button
20/1.4/700. No text below 14px.

Color, light theme only — informational, not danger: page #F8FAFC; card #FFFFFF, 1px #E2E8F0, shadow 0 1px
2px rgba(15,23,42,0.06); info block background #EFF6FF, 1px border #3B82F6, headline text #1D4ED8;
supporting text #475569; identity block #F1F5F9; primary text #0F172A; button #2563EB / #FFFFFF.

Artboard A — refreshing:
- Info block, centred: Lucide "refresh-cw" icon at 32px, 2px stroke, #1D4ED8, rotating continuously while
  the re-fetch is in flight (this is the only icon in the whole system permitted to spin)
- Headline: "This truck's status changed — refreshing"
- Supporting line: "Nothing was recorded."
- No button on this artboard. The screen resolves on its own.

Artboard B — re-rendered with the truck's real state:
- The standard truck card: identity "SHP1009 · Amit S.", carrier "Kota Transport", state row with a Lucide
  "truck" icon 24px 2px stroke #0F172A + "In dock", appointment "Appointment: D2 · Tue 4 Aug · 14:00–14:45"
- One button, now showing the state's actual valid action: "Start unload"
- The info block from artboard A is gone — it is not kept as a persistent banner. The re-rendered card IS
  the resolution.

Spacing / targets / radius: block padding 24px, card padding 24px, identity block 24px, 16px stack gap,
24px device-edge padding; full-width button minimum 56px tall; card 8px, blocks 6px, button 6px.

Motion: the refresh icon rotates at a steady rate while in flight only — no easing, no pulsing, no
acceleration. Artboard B enters at 200ms ease-out cubic-bezier(0.16, 1, 0.3, 1). Under
prefers-reduced-motion the rotating icon is replaced by a static icon plus the same headline text; the
information must not be lost, only the movement.

Explicitly exclude: an error or X icon, red treatment, a "retry" button that would re-attempt the rejected
action, a "someone else acted" attribution line naming another officer, a conflict-resolution dialog, a
persistent banner carried into artboard B, a full-page error state, a toast, a modal, a sidebar, top app
bar, bottom tab bar, gradients, blur, emoji, any dark-mode artboard.
```

---

## Screens deliberately not given a prompt

**Flow 9 — End shift.** It has no screen of its own. The low-emphasis "End shift" control is specified
inline in every prompt that carries the shift bar (§3 onward), and activating it clears the session name
and returns to **Prompt 1 / 2** (shift start). There is no confirmation modal — ending a shift has no
destructive consequence, and this surface uses no confirmation modals at all. Generating a separate
artboard for it would invent a screen the spec does not have.

**A dark-theme artboard for any screen above.** Dark is fully specified at parity product-wide, but
`screens.md` states it is not the expected real-world state here, and `color.md` requires dark to carry a
"hard to read outdoors" warning on field surfaces. Asking Stitch for dark kiosk artboards would produce a
polished rendering of a configuration officers are told not to use.

**An orientation-blocked / rotate-your-device screen.** See the judgement-call list below — the foundations
breakpoint table calls for one, but U108's yard tablet is a portrait device, so the two cannot both be
true. Flagged rather than resolved here.

---

## Values that required a judgement call

Every one of these is a place where the spec was silent, partial, or self-contradictory. They are listed
rather than absorbed, so the owner can rule on them and the prompts can be corrected in one pass.

| # | Value used in the prompts | Why it needed a call |
|---|---|---|
| 1 | **Body/supporting text at 16px** rather than `text-body`'s 14px | `spacing-and-layout.md` says density changes padding and row height only, **never type size**; this folder's `accessibility.md` says this surface's "type scale skews larger throughout." Both cannot hold. Prompts use 16px for supporting text with 14px as an absolute floor, following the surface file, since the outdoor-legibility argument is the specific one. |
| 2 | **Label-style text at 14–16px, not `text-label`'s 12px** | `typography.md` defines `text-label` at 12px and `text-micro` at 11px, but its own accessibility section forbids anything below 14px on gate surfaces. The floor wins in the prompts. |
| 3 | **Yard tablet frame 800×1280 portrait** | `spacing-and-layout.md`'s breakpoint table says the gate kiosk is "1024–1366px, **landscape locked**… below range shows an orientation prompt." U108 then introduced a portrait handheld yard tablet. The table predates U108 and now contradicts it. 800×1280 is a standard 10" portrait tablet, chosen as a plausible value — **not a spec value**. |
| 4 | **Outcome-banner icons**: `check` (success), `alert-triangle` (warning), `circle-alert` (info), `calendar-x` (no appointment), `door-closed` (dock occupied), `refresh-cw` (refreshing) | `iconography.md` enumerates queue states, dock types, escalation reasons, planner affordances and app-level states — but **not outcome banners**. These are derived from the nearest existing entries. |
| 5 | **Tone assignments for the four named non-success outcomes** | `components.md` §5 says "`feedback-danger`/`feedback-warning` per severity — see `edge-cases.md`", and `edge-cases.md` never actually assigns them. Derived: `ALREADY_CHECKED_IN` → info (the truck genuinely is gated in), `INVALID_TRANSITION` → info (transient, self-healing), `DOCK_OCCUPIED` → warning (real conflict, has a natural next step), `NO_ACTIVE_APPOINTMENT` → danger (blocks the truck, unresolvable here). |
| 6 | **`queue_state` display labels** — "Waiting (early)", "Waiting — dock unavailable", "In dock", "Completed" | Only "Waiting (late)" (`screens.md`) and "Called to dock" (`mockup.html`) exist as written copy. The rest are derived from the enum names in the same style. |
| 7 | **The appointment line carries its date** — "Appointment: D5 · Tue 4 Aug · 18:00–19:00" | `screens.md`'s wireframe and `mockup.html` both render it **without a date** ("Appointment: D5 · 18:00–19:00"), while this folder's `components.md` §3 and the product-wide rule both require dock **and** date. The rule wins; the wireframe and mockup are the ones out of step. |
| 8 | **Dwell rendered as "1h 22m"** | Taken verbatim from `edge-cases.md` #6, but it conflicts with `data-formatting.md`'s "space between number and unit" and "prefer the full unit word" rules, and no grammar for absolute compound durations is defined (only countdowns and relative-time bands). Used as written; the format needs a ruling. |
| 9 | **"End shift" at 16px/600 in #475569, not `text-tertiary`** | `components.md` §1 calls it low-emphasis; `color.md`'s field-condition rule says body text on this surface uses `text-primary` only and reserves `text-secondary` for genuinely secondary content. De-emphasis is carried by type style, position and the absence of button chrome rather than by fading, because fading is what glare destroys first. |
| 10 | **Search field excludes autocomplete, suggestions and recent searches** | Checklist Design's *Searchbar* checklist lists both as items; neither has a spec source, and on a shared device a recent-search list carries the previous officer's lookups across a shift boundary. Excluded, with the reason stated in the prompt. |
| 11 | **Outcome blocks are not dismissible** | Checklist Design's *Banner* checklist says info/success banners suit dismissal. Here the banner **is** the screen and its single action ("Search next truck") is the dismissal, so a separate X would be a second competing target on a surface built around having exactly one. |

## Known mockup deviations (the mockup, not the foundations, is what is wrong)

`mockup.html` in this folder carries four values that do not match `00-foundations/`. The prompts above use
the **foundation** values, per the standing rule that a mockup value with no foundation source is a bug in
the mockup:

| Mockup value | Foundation value | File |
|---|---|---|
| `--feedback-warning-border: amber-600 (#D97706)` | `feedback-warning-border` light = **amber-500 `#F59E0B`** | `color.md` |
| `--feedback-danger-text: red-600 (#DC2626)` | `feedback-danger-text` light = **red-700 `#B91C1C`** | `color.md` |
| `--r-md: 8px; --r-lg: 12px` | `radius-md` = **6px**, `radius-lg` = **8px** (12px is `radius-xl`, modals/drawers only) | `spacing-and-layout.md` |
| Device tag at 11px, deviation note at 13px, body at 14px | **Nothing below 14px on gate surfaces** | `typography.md` |
