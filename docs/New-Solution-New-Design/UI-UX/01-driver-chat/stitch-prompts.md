# Driver chat — Stitch prompts

> Paste-ready prompts for **Stitch** (stitch.withgoogle.com), translated from the finished spec in this
> folder. **This file adds no design decisions.** Every value below traces to `00-foundations/` or to
> `screens.md` / `flows-and-states.md` / `components.md` / `edge-cases.md` / `accessibility.md` in this
> folder. Where the spec was silent or self-contradictory, nothing was invented — see
> **Flagged gaps** at the end, and the inline `⚑Fn` markers.
>
> Ordering: `screens.md` §1–§5 first, then `flows-and-states.md`'s system states, then `edge-cases.md`
> §1–§14, then the onboarding screen `screens.md` defers to `00-foundations/auth-and-scoping.md`.
>
> **Sign-in is deliberately not here.** It is a shared, all-six-role screen specified in
> `00-foundations/auth-and-scoping.md`, not a driver-chat screen, and has its own cross-cutting prompt.

## How to use this file

Each prompt is **§0 + the screen block**. Paste §0 first, then the numbered block underneath it, as one
Stitch prompt. §0 is factored out rather than repeated 28 times on purpose: 28 hand-copied duplicates of
the same token values is exactly the drift `00-foundations/tokens.md` (U85) exists to prevent, and a
divergence between prompt 4's blue and prompt 19's blue would be invisible until it reached a screen.

Every screen block repeats the promise-state hexes it actually uses, because those four are the
load-bearing values and are worth carrying twice.

---

## §0 · Base block — prepend to every prompt below

```
**Product context**: SetuHaul Dock Command — the driver PWA of a B2B dock-appointment platform for a
logistics company. Not a consumer messaging app, not a marketing site. The user is a truck driver at the
roadside: one hand free, phone in direct sunlight, cheap mid-range Android, poor connectivity, and
stressed because something has already gone wrong. Aesthetic target is an operator tool — calm, plain,
trustworthy, closer to a cockpit instrument than to a chat app. No illustrations, no hero sections, no
brand storytelling, no gradients, no mascots, no emoji as UI.

**Device and layout**: 390 × 844 phone, portrait. Supported range 320–768px; above 640px the content
column caps at 640px and centres. Respect env(safe-area-inset-bottom) so the bottom-most control clears
the home indicator. Nothing interactive sits within 16px of a viewport edge.

**Typography**: `Inter` for all UI text — weights 400/500/600/700 only, nothing else loaded.
`JetBrains Mono` weights 400/500 for machine values only: identifiers (ORD-260804-004, APT-1042,
ESC-4471), timestamps, time ranges (13:00–14:15) and countdowns (1:24). Inter is chosen for its tall
x-height, which survives glare on a cheap phone; do not substitute a "more distinctive" font — this is a
functional-legibility choice, not an oversight.
Sizes on this surface: chat message body and text input 16px/1.5 weight 400 (16px also prevents iOS
Safari auto-zoom on input focus); card titles 16px/1.5 weight 600; secondary text 14px/1.5 weight 400.
**Nothing on this surface is smaller than 14px** — the 11px product-wide floor does not apply here.
State chip labels are 12px, weight 600, UPPERCASE, letter-spacing 0.04em. Any number that updates live
or sits in a column uses `font-variant-numeric: tabular-nums` so digits do not shift width. Time ranges
use an en dash (13:00–14:15), never a hyphen.

**Color — base tokens** (define both light and dark; **light is the shipped default on this surface and
must be the default artboard** — dark UI in direct sunlight on a cheap LCD is unreadable):
- Page background: `#F8FAFC` light / `#020617` dark
- Card / raised surface: `#FFFFFF` light / `#0F172A` dark
- Pressed / hover surface: `#F1F5F9` light / `#1E293B` dark
- Driver's own message bubble fill: `#EFF6FF` light / `#1E3A8A` at 30% opacity dark
- Primary text: `#0F172A` light / `#F8FAFC` dark
- Secondary text: `#475569` light / `#CBD5E1` dark
- Tertiary text (timestamps, metadata): `#64748B` light / `#94A3B8` dark
- Subtle border: `#E2E8F0` light / `#1E293B` dark
- Default border: `#CBD5E1` light / `#334155` dark
- Primary action / focus ring: `#2563EB` light / `#3B82F6` dark
- Danger (expiry, conflict, failure) text: `#DC2626` light / `#F87171` dark

**Color — the four promise states.** These are the product's central visual language and must never be
confusable. Each carries four redundant signals — hue, icon, border style, spelled-out label — so state
survives greyscale, colour blindness and glare. On this surface all four use the **filled** variant
(coloured background, not just a border):
- `SHOWN` — deliberately uncoloured. bg `#F8FAFC` / `#1E293B`, border **1px solid** `#CBD5E1` / `#475569`,
  text `#334155` / `#E2E8F0`, icon `list`. Nothing is reserved, so nothing is signalled.
- `HELD` — bg `#FFFBEB` / `#78350F` at 25%, border **2px dashed** `#F59E0B` (both themes),
  text `#B45309` / `#FBBF24`, icon `timer`. Dashed means temporary.
- `PENDING CONFIRMATION` — bg `#EFF6FF` / `#1E3A8A` at 25%, border **2px solid** `#3B82F6`,
  text `#2563EB` / `#60A5FA`, icon `clock-fade`.
- `CONFIRMED` — bg `#ECFDF5` / `#064E3B` at 25%, border **2px solid** `#059669` / `#10B981`,
  text `#047857` / `#34D399`, icon `circle-check`.
**Never abbreviate a state label.** "PENDING CONFIRMATION", never "PENDING" or "PC". If it doesn't fit,
the container is too small.

**Icons**: Lucide, stroke weight 2px at every size, never varied. 14px inline in a chip, 16px inline with
body text, 20px standalone in a button, 32px in an empty state. **No icon-only controls anywhere on this
surface** — an icon augments a label here, it never replaces one.

**Spacing**: base unit 4px, every value a multiple. This surface runs `comfortable` density: card padding
16px, stack gap 12px, content padding 24px from the screen edge, button height 40px, minimum tap target
44 × 44px, minimum 8px between adjacent tap targets.

**Radius**: 4px chips and badges, 6px buttons and inputs, 8px cards and option cards, 12px sheets.

**Elevation**: cards sit one level above the page — white fill, a barely-visible
`0 1px 2px rgba(15,23,42,0.06)` shadow, and a 1px subtle border. In dark mode there is **no shadow at
all**; separation comes from the `#020617 → #0F172A` lightness step plus the border. The shadow language
is deliberately restrained throughout. **No glassmorphism, no backdrop-filter, no translucency** —
expensive on low-end Android, and it makes text contrast unverifiable.

**Motion**: 120ms for hover/focus, 200ms for most transitions, 320ms for sheets. Easing is
`cubic-bezier(0.16, 1, 0.3, 1)` entering and `cubic-bezier(0.7, 0, 0.84, 0)` exiting. **No spring, no
bounce, no overshoot** — nothing in a capacity-commitment system should read as playful. **No hover
effect that moves an element** (no lift, no scale) — colour and border only. **No ambient or looping
animation** of any kind; motion is reserved for state changes that carry real meaning. Countdown digits
change instantly, never with a smooth sweep.

**Never do this, on any screen**: show an operational time without both its dock and its date; use
"booked", "reserved", "secured" or "your slot" for anything below CONFIRMED; use an exclamation mark;
use 12-hour time (24-hour only, `13:00` never `1:00 PM`); use a shipment ID as the subject of a sentence
to a driver (say "your Kota load", not "SHP1004"); number the options ("Option 1", "the second one") —
ordinals do not exist on this surface, in the UI or in the accessible name.
```

---

# 1 · Thread list — home

```
**Prepend §0.**

**Screen**: the driver's home. One card per exception thread. This screen exists so a driver with two
loads picks the right one *before* typing, rather than the assistant having to ask which load they mean.

**Layout**, top to bottom:
- Header, 56px, sticky: "SetuHaul" at 16px/600 on the left, a `settings` gear icon on the right
  (44 × 44px hit area, 20px glyph). No back button — this is the root.
- Scrolling list, 24px side padding, 12px gap between cards.
- Bottom nav, 56px: two items, "Threads" and "Profile", each ≥56px tall, label always visible beneath a
  20px icon. Active item is `#2563EB` / `#3B82F6` at weight 600; inactive is `#64748B` / `#94A3B8` at
  weight 500. ⚑F5

**Thread card anatomy** — whole card is one tap target, minimum 88px tall, white fill, 1px `#E2E8F0`
border, 8px radius, 16px padding, 12px extra left padding for the marker:
- A **3px priority marker** on the left edge, inset 9px from top and bottom. It is a neutral value ramp,
  never a hue: CRITICAL `#0F172A` / `#FFFFFF`, HIGH `#475569` / `#CBD5E1`, NORMAL `#94A3B8` / `#64748B`,
  LOW `#E2E8F0` / `#334155`. Active threads only. Red is reserved exclusively for danger in this product,
  so a CRITICAL row must never look like a failing row.
- **Load descriptor**, 16px/600: a human phrase, never an ID — "Kota load → IndustrialHub".
- **Order reference** beneath it, 14px, JetBrains Mono, tertiary text: "ORD-260804-004". ⚑F1
- **Promise-state chip**, filled variant, carrying its live countdown when HELD or PENDING.
- **Operational line**, 14px secondary, tabular numerals: "Dock D1 · Tue 4 Aug · 13:00–14:15". Dock, date
  and time are one unit joined by middots, never three separate fragments.
- **Last message preview**, one line, 14px secondary, end-truncated with an ellipsis.
- **Timestamp**, right-aligned on the same baseline as the preview, 14px Mono tertiary: relative under an
  hour ("9 minutes ago"), absolute above it ("09:41").

**Ordering**: threads with a running countdown first (HELD, then PENDING), soonest deadline at the top;
then other active threads by most recent activity; then a "Resolved" section. A HELD thread with 20
seconds left is always the first thing on screen.

**Resolved section**: a left-aligned 12px/600 uppercase "RESOLVED" label with a 1px `#E2E8F0` rule running
to the right edge. Cards below it render at 60% opacity, keep their state chip, and drop the priority
marker entirely.

**Content, verbatim**:
Card 1 — CRITICAL marker · "Kota load → IndustrialHub" · ORD-260804-004 · HELD chip reading
`⏱ HELD 1:24` · "Dock D1 · Tue 4 Aug · 13:00–14:15" · preview "Held for you — send it to the warehouse?"
· "09:41"
Card 2 — HIGH marker · "Neemrana load → RajRetail" · ORD-260804-017 · PENDING CONFIRMATION chip ·
"Decision by 11:57" · preview "The warehouse hasn't confirmed yet…" · "09:32"
Resolved — "Jodhpur load → HomeCraft" · ORD-260803-011 · CONFIRMED chip ·
"Dock D2 · Mon 3 Aug · 14:00–15:00"

**States**:
- Default — as above.
- Pressed — card background moves to `#F1F5F9` / `#1E293B`. **No scale, no lift.**
- Unread activity — a 2px `#2563EB` inset on the left and the descriptor at weight 700. ⚑F6
- Resolved — card ground drops to `#F1F5F9` / `#020617` (surface-sunken) and every text node moves to
  the secondary token `#475569` / `#CBD5E1`; border stays `border-subtle`; no marker, no countdown.
  **No opacity.**

> **Corrected 2026-09-01 — issue #90.** This line read "60% opacity". Measured on the real render
> (Playwright 1.62.1, Chromium), 60% opacity put the card's timestamp at **2.29:1**, its order
> reference at **2.86:1** and its chip label at **2.53:1** in light theme — group opacity fades the
> card's own background toward the page along with its text, so the *painted* contrast collapses
> even though each token is fine in isolation. The card is an active, navigable `<Link>`, so WCAG
> 1.4.3's inactive-component exception does not apply. After: **6.92 / 6.92 / 5.21:1** light,
> **13.59 / 13.59 / 7.54:1** dark. The Motion note directly below already asked for exactly this —
> "settled cards recede in **contrast**" is a colour instruction, and opacity was never the way to
> honour it. Shipped as `theme.css`'s `muted-region` utility + `bg-sunken`.

**Motion**: countdowns tick once per second with no animation on the digit. Only a card that is actually
changing gets any motion; settled cards recede in contrast rather than staying visually loud.

**Accessibility**: whole card is one `role="link"` target. The state chip is `role="status"`. The
countdown announces at 50%, 20%, 10 seconds and expiry only — never per second.

**Explicitly exclude**: swipe-to-archive or any swipe gesture; unread count badges; avatars on thread
cards; a floating action button (a driver cannot create a load — the dispatcher's TMS does); search;
filters; pull-to-refresh spinners as the primary loading treatment; any card-level hover lift.
```

---

# 2 · Thread list — loading

```
**Prepend §0.**

**Screen**: app launch, before the thread list has data.

**Treatment**: skeleton cards matching the final layout exactly — same 88px minimum height, same 8px
radius, same 16px padding, same 12px gaps, same 24px side padding, same 56px header and 56px bottom nav,
both fully rendered and interactive. **Never a centred spinner** — a spinner followed by content is a
layout jump, and a jump under a thumb is a mis-tap.

**Skeleton block anatomy**, per card: a 60%-width bar where the descriptor goes, a 35%-width bar for the
order reference, a 100 × 24px block where the state chip goes, a 70%-width bar for the operational line,
and a 50%-width bar for the preview. Blocks are `#E2E8F0` / `#1E293B`, 4px radius. The priority marker
does **not** render in the skeleton — priority is unknown until data arrives, and a grey marker would
imply LOW.

**Motion**: a single pulse loop, 1600ms, ease-in-out, opacity only. Under `prefers-reduced-motion` the
pulse stops and the blocks become static grey. Nothing else on the screen animates.

**Rules**: show nothing at all for the first second of a request — an indicator that flashes for under a
second is pure distraction. Between 1 and 3 seconds show this skeleton. If the load passes roughly 3
seconds, the skeleton is joined by a retry affordance rather than spinning indefinitely.

**Explicitly exclude**: a shimmer sweep or moving gradient (opacity pulse only); a percentage or progress
bar; a "Loading…" label; a full-screen branded splash; skeleton content that does not match the real
layout's dimensions.
```

---

# 3 · Thread list — empty, two variants

```
**Prepend §0.**

**Screen**: two artboards, side by side. The same visual emptiness means two opposite things, and showing
the wrong one makes a working system look broken.

**Shared anatomy**, centred in the content region, header and bottom nav still rendered:
- A 32px Lucide icon in tertiary text colour `#64748B` / `#94A3B8`.
- 16px gap, then a heading at 16px/600 primary text stating what is true right now.
- 8px gap, then one supporting line at 14px/400 secondary text, max 40 characters per line, centred.
- Neither variant has a call-to-action button. A driver cannot create a load; the dispatcher assigns it.

**Variant A — "caught up"** (this driver has history, just nothing active now):
- Icon: `circle-check-big`
- Copy, verbatim: "No active loads." / "You'll see delays and slot changes here."
- Tone is reassuring — this is a good state.

**Variant B — "nothing yet"** (a brand-new driver account, no history at all):
- Icon: `inbox`
- Copy, verbatim: "No loads assigned yet." / "Your dispatcher assigns these — they'll appear here
  automatically."
- Tone is neutral and informational — this is an expected state, not a problem.

The two icons are deliberately different: `inbox` reads as "not set up", `circle-check-big` reads as
"you're done". Using one icon for both would undercut the whole point of separating them.

**Explicitly exclude**: an illustration or spot graphic; any CTA button; the word "empty"; a generic
"Nothing to see here"; the same icon across both variants; a "Refresh" button.
```

---

# 4 · Conversation — options open (`SHOWN`)

```
**Prepend §0.**

**Screen**: the product's primary surface. A chat transcript with structured option cards rendered
*inside* it. The transcript is the spine; the cards are typed tool output, not text the assistant wrote.

**Layout**, top to bottom:
- **Header, sticky**: row one is a `chevron-left` back control (48 × 48px hit area — top-left is the
  hardest place to reach one-handed) plus the load descriptor "Kota load → IndustrialHub" at 16px/600,
  truncated with an ellipsis if needed. Row two is the **persistent state line**: the promise-state chip,
  carried at all times whether or not the message that established it is on screen. 1px `#E2E8F0` bottom
  border. ⚑F2
- **Transcript**: fills, scrolls, 24px side padding, 12px between messages.
- **Composer**: minimum 56px, pinned to the bottom.

**Persistent state line, this screen**: `SHOWN` chip, filled — bg `#F8FAFC` / `#1E293B`, 1px solid
`#CBD5E1` border, text `#334155`, `list` icon — reading "Options open · nothing held".

**Message tiers**:
- Driver message: right-aligned, max 84% width, fill `#EFF6FF` / `#1E3A8A` at 30%, 1px subtle border,
  8px radius, 12px padding, 16px/1.5 body. Delivery status beneath in 14px Mono tertiary: `✓✓` for
  delivered.
- Assistant message: left-aligned, max 84% width, fill white / `#0F172A`, 1px `#E2E8F0` border. Above the
  first message of a run, an attribution row: a 20px hexagon glyph plus "SetuHaul assistant" at 14px/500
  tertiary. Consecutive messages from the same sender do not repeat the attribution.

**Option card** — the single most consequential component here:
- Full width minus the 24px side padding, **minimum 64px tall**, white / `#0F172A` fill, 1px `#CBD5E1`
  border, 8px radius, 12px vertical / 16px horizontal padding, 12px gap between cards.
- Line 1: dock and date together, 16px/600 — "Dock D4 · Tue 4 Aug". **The date renders even when every
  option is today.** A missing date is a real wrong-day booking.
- Line 2: time range, 16px JetBrains Mono, tabular numerals, en dash — "12:15 – 13:30".
- Line 3: exactly **one** differentiator, 14px secondary — "soonest".
- **No number, no ordinal, no letter, no rank, anywhere on the card or in its accessible name.**

**Copy, verbatim**:
Driver: "Traffic after Shahpura. Reaching around 11:20."   09:34 ✓✓
Assistant: "Your current slot is 10:00–11:00 at Jaipur DC — that won't work now. Three options are open.
**Nothing is held yet** — another driver can take any of these."
Cards:
  Dock D4 · Tue 4 Aug / 12:15 – 13:30 / soonest
  Dock D1 · Tue 4 Aug / 13:00 – 14:15 / no waiting
  Dock D2 · Tue 4 Aug / 14:30 – 15:45 / most buffer
Assistant: "Tap one to hold it for 90 seconds."   09:34

"Nothing is held yet" is mandatory and appears **before** the options, not after — a driver who taps
without reading must still not have been misled by what they skimmed.

**Composer**: a rounded 999px text field filling the width, 1px `#CBD5E1` border, 16px input text,
placeholder "Message"; then an 8px gap and a 44 × 44px circular send control filled `#2563EB` with a
white `send` glyph, enabled only when the field is non-empty.

**Motion**: on open, the transcript jumps to the latest message with no animation. Nothing else moves.

**Accessibility**: each option card is `role="button"` with the full accessible name
"Dock D4, Tuesday 4 August, 12:15 to 13:30, soonest. Tap to hold for 90 seconds." — never "option 2 of 3".
Transcript is `role="log"`; each message is a `listitem`.

**Explicitly exclude**: numbering or lettering the options; a "Recommended" / "Best" badge or any ranking
visual; a star, heart or bookmark on a card; a price; a map; a progress stepper; an attachment button in
the composer; a voice-input button; a typing indicator on this artboard; message reactions; swipe-to-reply.
```

---

# 5 · Conversation — `HELD` (90 seconds, live)

```
**Prepend §0.**

**Screen**: the driver has tapped an option. Tapping grants **exclusivity, not a request** — a second,
explicit action sends it to the warehouse. The UI must never collapse these two steps into one to save a
tap. This screen is where a design failure becomes a broken promise, so it is specified tightly.

**Persistent state line**: `HELD` chip, filled — bg `#FFFBEB` / `#78350F` at 25%, **2px dashed** `#F59E0B`
border, text `#B45309` / `#FBBF24`, `timer` icon, label "HELD", then the live countdown in JetBrains Mono
with tabular numerals: `⏱ HELD 1:24`. A 14px `circle-help` affordance sits immediately after the chip
with a 44 × 44px hit area.

**The chosen card mutates in place** — it is not replaced by a new message. It takes the HELD treatment:
2px dashed `#F59E0B` border, `#FFFBEB` / `#78350F`-at-25% fill, and its differentiator line is replaced by
"Held for you · 1:24" at weight 600 in the HELD text colour.

**The two sibling cards** in the same set dim to 40% opacity and become non-interactive. Tapping one gives
no haptic and does nothing — silence is the correct feedback for a non-target.

**Countdown behaviour**, escalating **only at thresholds**, never continuously:
- Above 50% remaining: `#D97706`, weight 400. Nothing else moves.
- 20–50%: `#D97706`, weight 400.
- Below 20%: `#DC2626` / `#F87171`, weight **600**, and the card's dashed border pulses once per second —
  opacity 1 → 0.6 → 1, 1000ms, ease-in-out.
- Below 10 seconds: same, plus a device haptic at 10s (200ms) and at 5s (200ms · 100ms pause · 200ms).
The colour change is a **step at a threshold**, never a gradient and never animated — a countdown that
recolours every second is noise; one that steps at three fixed points is a signal. The numeral, not the
colour, does the continuous work.

**Copy, verbatim**:
Assistant: "Dock D1 · Tue 4 Aug · 13:00–14:15 is held for you. **This is not a booking yet.** Send it to
the warehouse to request it."
Help popover, on the `circle-help`: "Held means this slot is reserved for you for 90 seconds. It's not
booked yet — send it to the warehouse to request it."

**Quick-reply row**, replacing the composer's suggestion area, above the text field: two pill buttons,
1px `#CBD5E1` border, 999px radius, page-background fill, 16px label, ≥44px tall — "Request this slot"
and "Choose a different one". ⚑F7

**Under `prefers-reduced-motion`**: the pulse is **replaced, not removed** — the border becomes solid
high-contrast and an explicit "expiring" text label appears. Silently dropping the expiry warning for
someone who set a system preference would be an accessibility failure dressed as compliance.

**Explicitly exclude**: a circular or radial progress ring around the countdown; a depleting horizontal
progress bar; a confetti, checkmark-draw or celebration treatment (HELD is not success); the word
"booked", "reserved", "confirmed" or "yours"; any single button that both holds and requests; a countdown
that animates its digits.
```

---

# 6 · Conversation — `PENDING CONFIRMATION` (15 minutes, awaiting a human)

```
**Prepend §0.**

**Screen**: the request has gone to the warehouse. A human planner now has 15 minutes to decide. Nothing
is committed.

**Persistent state line**: `PENDING CONFIRMATION` chip, filled — bg `#EFF6FF` / `#1E3A8A` at 25%, **2px
solid** `#3B82F6` border, text `#2563EB` / `#60A5FA`, `clock-fade` icon. Content: "PENDING CONFIRMATION ·
decision by 11:57". **The label is never abbreviated**; if space runs out, the dock and date truncate
first, never the state word.

**The card**: the held card keeps its position in the transcript and takes the PENDING treatment — 2px
solid `#3B82F6` border, `#EFF6FF` fill. Its status line reads "Requested · decision by 11:57".

**Countdown**: 15 minutes, rendered as `M:SS` in JetBrains Mono with tabular numerals. Same threshold
steps as HELD — `#2563EB` above 50%, `#D97706` from 20–50%, `#DC2626` weight 600 below 20%. **PENDING
never pulses.** A fifteen-minute element pulsing for its final three minutes is intolerable; the pulse is
reserved for the 90-second case.

**Copy, verbatim**:
"Requested: Dock D1 · Tue 4 Aug · 13:00–14:15

The warehouse has not confirmed this yet. A planner will decide by 11:57.
If there's no decision by then, the slot is released and I'll find you fresh options."

Naming the deadline *and* what happens after it is what makes the wait tolerable. Never "we'll let you
know."

Help popover copy: "The warehouse hasn't confirmed this yet. A planner will decide before the deadline
shown above."

**States**: no quick replies on this screen — there is nothing for the driver to decide. The composer
stays fully enabled.

**Explicitly exclude**: a progress bar or stepper implying the request is "on its way to confirmed"; any
green, any checkmark, any "success" treatment; the words "booked", "confirmed", "successfully",
"your slot"; a cancel button in the thumb zone (cancelling goes through the conversation with an explicit
confirmation, not a tappable button sitting under the thumb); an estimated-wait animation.
```

---

# 7 · Conversation — `CONFIRMED`

```
**Prepend §0.**

**Screen**: the planner has confirmed. **This is the only state in the entire product permitted to use
finality language or a success treatment.**

**Persistent state line**: `CONFIRMED` chip, filled — bg `#ECFDF5` / `#064E3B` at 25%, **2px solid**
`#059669` / `#10B981` border, text `#047857` / `#34D399`, `circle-check` icon. Content:
"CONFIRMED · Dock D1 · Tue 4 Aug 13:00". No countdown — nothing is expiring.

**Transcript**, showing the whole arc so the record persists:
- Earlier assistant message, in its settled/lower-contrast form: "Requested: Dock D1 · Tue 4 Aug ·
  13:00–14:15. The warehouse hasn't confirmed this yet — a planner will decide by 11:57."
- A centred system notice, **no bubble**, 14px secondary, full-width centred: "A planner confirmed your
  request."
- The confirmation message from the assistant.

**Confirmation copy, verbatim** — the arrival guidance comes from real facility rules and is never
invented:
"✓ Confirmed — Dock D1 · Tue 4 Aug · 13:00–14:15, Jaipur DC
Reference APT-1042

You may check in from 12:00 (60 minutes early limit).
If you haven't checked in by 13:30, the appointment may be marked no-show."

`APT-1042` renders in JetBrains Mono. A confirmation without arrival instructions is where detention
starts, so the last two lines are not optional.

**Motion**: entry into CONFIRMED is a **hard swap** — the previous chip's icon, label, border and colour
are replaced outright with no in-between visual state and no morph between shapes. The one permitted
flourish is a single non-celebratory border-colour settle over 200ms; no scale, no bounce, no overshoot.
Haptic on arrival: 10ms · 40ms · 10ms · 40ms · 10ms.

**Explicitly exclude**: confetti, fireworks, an animated checkmark draw, a full-screen success takeover, a
"Add to calendar" flourish, an exclamation mark, the word "Congratulations", a share button, a rating
prompt. This is a freight appointment being agreed, not a purchase being celebrated.
```

---

# 8 · Message tiers and the human-takeover divider

```
**Prepend §0.**

**Screen**: a component-reference artboard showing all four message treatments in one transcript. The
AI-versus-human distinction must survive a glance — a driver who thinks they are still talking to a bot
phrases things differently from one who knows a person is reading.

**Tier 1 — DRIVER**: right-aligned, max 84% width, fill `#EFF6FF` / `#1E3A8A` at 30%, 1px `#E2E8F0`
border, 8px radius, 12px padding, 16px/1.5 text. Delivery status beneath, right-aligned, 14px Mono
tertiary.

**Tier 2 — ASSISTANT**: left-aligned, max 84%, white / `#0F172A` fill, **1px** `#E2E8F0` border.
Attribution row above the first of a run: a 20px hexagon glyph in `#8B5CF6` plus "SetuHaul assistant" at
14px/500 tertiary.

**Tier 3 — OPERATIONS / WAREHOUSE (a real person)**: left-aligned, white fill, **1px `#CBD5E1` — visibly
heavier than the assistant's border**. Attribution row: a 20px circular avatar with the person's initial
on `#059669`, then "Neha · Operations" at 14px/500 — real name **and** role, both required. The avatar,
the real name and the heavier border carry the distinction together; no one of them alone is enough.

**Tier 4 — SYSTEM**: centred, **no bubble at all**, 14px secondary text, max 92% width. These are events,
not messages.

**Takeover divider**: full-width, a 1px `#CBD5E1` rule on each side of centred 14px secondary text —
"Neha from Operations joined". Not a bubble, not dismissible, permanent in the transcript. A silent
takeover reads as the bot ignoring the driver.

**Grouping**: consecutive messages from one sender within 2 minutes group — attribution on the first only,
timestamp on the last only.

**Delivery status vocabulary**, driver messages only, 14px Mono beneath the bubble:
- Sending: `○`
- Sent: `✓`
- Delivered: `✓✓`
- Queued offline: `⏱ queued` — **explicit words, not a symbol**, so it cannot be mistaken for sent
- Failed: `⚠ not sent`, in `#DC2626`, followed by an inline "Retry" text button

**Explicitly exclude**: a "read" receipt or "seen" indicator (there is no human on the other end during
normal operation and implying one misrepresents the assistant); reactions; swipe-to-reply; long-press
action menus; message deletion (the transcript is an append-only operational record); a robot or sparkle
icon for the assistant; a "AI-generated" disclaimer badge on every message.
```

---

# 9 · Option card — full state matrix

```
**Prepend §0.**

**Screen**: one artboard, eight stacked instances of the option card, each labelled with its state name in
12px/600 uppercase tertiary text above it. This is a component sheet, not a device screen — render it on
the page background with 24px padding and 24px between instances.

**Base anatomy** (repeat for every instance): full width, minimum 64px tall, 8px radius, 12px vertical /
16px horizontal padding. Line 1 "Dock D1 · Tue 4 Aug" at 16px/600. Line 2 "13:00 – 14:15" at 16px
JetBrains Mono, tabular numerals, en dash. Line 3 one differentiator or status line at 14px.

**The eight states**:
1. **Default / selectable** — white `#FFFFFF` / `#0F172A` fill, 1px `#CBD5E1` border, full opacity, line 3
   is the differentiator "no waiting" in secondary text.
2. **Pressed** — fill moves to `#F1F5F9` / `#1E293B`, fires on touch-down (not touch-up) for perceived
   responsiveness, plus a 10ms haptic. No scale, no lift.
3. **Committing** — card locks, an inline 16px spinner replaces the differentiator line, sibling cards in
   the set drop to 40% opacity.
4. **Held (won)** — 2px **dashed** `#F59E0B` border, `#FFFBEB` / `#78350F`-at-25% fill, line 3 becomes
   "Held for you · 1:24" at weight 600 in `#B45309` / `#FBBF24`.
5. **Lost the race** — dock and time struck through, whole card at 40% opacity, line 3 reads "Taken by
   another driver" in `#DC2626`.
6. **Withdrawn** — dock and time struck through, 40% opacity, line 3 reads "No longer available" in
   `#DC2626`.
7. **Disabled — offline** — 40% opacity, a 16px `wifi-off` icon on line 3 followed by "Offline — can't
   select now". **Visible, never hidden.**
8. **Superseded** — a newer option set has arrived; 40% opacity, no strike-through, no status line,
   non-interactive.

**Rules to state in the prompt**:
- **Cards mutate in place** rather than being replaced by a new message — the driver sees *which* thing
  changed, not just that something did.
- **No ordinal, ever** — not displayed, not accepted, not in the accessible name, not in the DOM.
- Only **one** differentiator line. Three cards each carrying a full explanation is unreadable on a phone
  at a roadside.
- Tapping a superseded, disabled or terminal card does nothing and produces no haptic.

⚑F8 — states 5, 6, 7 and 8 all sit at 40% opacity and are told apart only by the status line and the
presence or absence of a strike-through. Keep the status line at full opacity within the dimmed card so
the distinguishing signal is not itself dimmed.

**Explicitly exclude**: a hover lift or shadow change on any state; a colour-only difference between
states 5–8; a "sold out" or "unavailable" stamp graphic; a disabled state that is removed from the layout
rather than dimmed in place.
```

---

# 10 · Composer and quick replies

```
**Prepend §0.**

**Screen**: a component artboard of the bottom input region in five states, plus a keyboard-open variant.

**Region stack**, above the safe-area inset:
- **Quick replies row** — present only when the assistant's last message asked something with an obvious
  closed answer. 1px `#E2E8F0` top border, white fill, 12px vertical / 24px horizontal padding, 8px
  between chips.
- **Composer row** — 1px `#E2E8F0` top border, white fill, 12px vertical / 24px horizontal padding,
  minimum 56px tall.

**Quick reply chip**: pill, 999px radius, 1px `#CBD5E1` border, page-background fill, 16px/400 label in
primary text, minimum 44px tall, minimum 8px apart. Two or three chips only — more than three is a form,
not a conversation. They send **the literal text on the chip as a normal driver message**, not a special
message type; the transcript must read as a conversation afterwards. Typing anything dismisses them, and
they do not reappear for that question. ⚑F7

**Composer**: a 999px-radius field filling the width, 1px `#CBD5E1` border, page-background fill, 16px
input text (16px specifically prevents iOS Safari auto-zoom on focus), 12px vertical / 16px horizontal
padding, placeholder "Message" in tertiary text. Then an 8px gap and a 44 × 44px circular send control,
`#2563EB` fill, white 20px `send` glyph.

**The five states**:
1. **Empty** — send control at `#94A3B8`, disabled.
2. **Typing** — send control at `#2563EB`, enabled. The field grows from 1 line to a maximum of 3, then
   scrolls internally.
3. **Sending** — send control shows a 20px spinner, stays the same width, no reflow.
4. **Offline** — the composer **stays fully enabled**. Placeholder changes to "Message · will send when
   you're back online". The send control renders at `#94A3B8` but remains operable, and messages queue.
5. **Focused** — a 2px `#2563EB` focus ring with a 2px offset around the field. Never a soft glow.

**Keyboard-open variant**: composer and quick replies rise with the keyboard; the transcript shrinks and
holds its scroll position relative to the **latest** message, not the top. Explicit handling on both iOS
and Android — the keyboard obscuring the input bar is the common bug here. The composer is the
bottom-most interactive element, full width, and thumb-reachable in every grip position.

**The composer is never disabled.** Whatever else is unavailable, a driver must always be able to say
something.

**Hardware keyboard**: Enter sends, Shift+Enter inserts a newline.

**Accessibility**: quick replies are grouped and labelled "Suggested replies". After sending, focus stays
in the composer — it does not jump to the new message bubble.

**Explicitly exclude**: an attachment or paperclip button; a camera button; a microphone / voice-input
button; an emoji picker; a "+" overflow menu; slash commands or @-mentions; more than three quick replies;
a horizontally scrolling quick-reply carousel; a disabled composer in any state.
```

---

# 11 · System states — thinking, transcript skeleton, scroll-to-latest

```
**Prepend §0.**

**Screen**: three artboards on the conversation layout.

**Artboard A — assistant thinking**:
- The assistant attribution row, then a small left-aligned bubble containing three 6px dots in
  `#94A3B8`, animating in a 1.4-second ease-in-out loop.
- **Appears only after 400ms of no response** — a fast reply that flashes the indicator is distracting.
- **If the turn passes 8 seconds**, the bubble gains a second line at 14px secondary: "Still working on
  this…". A driver at a roadside with no feedback assumes the app is broken.
- Under `prefers-reduced-motion` the dots are replaced by a static "Working…" label — not removed.

**Artboard B — transcript skeleton** (opening a thread):
- Three alternating bubble-shaped blocks: right-aligned 60% width, left-aligned 80% width, left-aligned
  50% width. `#E2E8F0` / `#1E293B` fill, 8px radius, matching the real bubbles' heights and 12px gaps.
- The header renders fully with the real load descriptor; only the transcript region is skeletal.
- Pulse loop, 1600ms, opacity only, ease-in-out.

**Artboard C — scroll to latest**:
- A floating pill centred horizontally, sitting 12px above the composer: white / `#0F172A` fill, 1px
  `#CBD5E1` border, 999px radius, `0 4px 12px rgba(15,23,42,0.10)` shadow, 12px vertical / 16px horizontal
  padding, a 16px `arrow-down` icon then "2 new" at 14px/500.
- Appears **only** when the driver is scrolled more than one screen from the bottom.
- **The transcript never auto-scrolls while the driver is reading history.** New content arriving must not
  yank the view.
- Tapping scrolls to the latest and dismisses the pill.
- It counts **messages, not events** — a card mutating in place does not increment it.

**Explicitly exclude**: a full-screen loading overlay; a spinner in place of the skeleton; a "typing…"
text label alongside the dots; an avatar bouncing; a progress percentage; the pill appearing when the
driver is already near the bottom.
```

---

# 12 · Eligibility answer — pass and fail

```
**Prepend §0.**

**Screen**: two artboards. The driver asked a facility question — "Does the 7:30 slot take a 32-foot
vehicle?" — and the answer is rendered as structured, per-invariant output, not as a sentence the
assistant composed. It is read-only and creates nothing: no request, no hold, no state change.

**Card anatomy**, rendered inline in the transcript in the assistant's position, full width minus the 24px
side padding, white / `#0F172A` fill, 1px `#CBD5E1` border, 8px radius, 16px padding:
- **Title row**, 16px/600: the subject of the check — "Dock D4 · 32-foot vehicle".
- 12px gap, then **one row per invariant**, 12px apart: a 16px verdict icon, 12px gap, then the invariant
  name at 16px/400 primary text, with its measured value in parentheses in JetBrains Mono where one
  exists.
- 12px gap, a 1px `#E2E8F0` rule, 12px gap, then the **verdict line** at 16px/600.

**Artboard A — passes**:
```
Dock D4 · 32-foot vehicle

✓  Vehicle length
✓  Weight (14,500 / 25,000 kg)
✓  Dock active

Yes — this slot accepts your truck
```
Pass rows use a `check` icon in `#047857` / `#34D399`. Verdict line in `#047857` / `#34D399`. ⚑F9

**Artboard B — fails**:
```
Dock D5 · Reefer load

✓  Vehicle length
✗  Refrigeration required
   D5 is under maintenance 18:00–22:00
   (RULE003 pins reefer loads to D5 only)

No — try after 22:00 or ask for tomorrow's options
```
The failing row uses an `x` icon in `#DC2626` / `#F87171` with its detail indented beneath at 14px
secondary. **The passing rows in a failing card stay their normal neutral colour, never green** — a
mixed-verdict card is not the place to introduce a second meaning for a colour already spent on promise
state. Verdict line in `#DC2626` / `#F87171`.

**Rules**:
- **Every invariant renders, not just the failing one.** A driver who sees only "no" learns nothing they
  can act on.
- The failure detail names the specific rule and reason in plain language — never "not eligible" alone.
- Both verdict lines are templated sentences, not generated.
- The assistant adds at most **one** line of plain framing around this card, and never restates the
  verdict in different words.
- Icon plus text carries the verdict; colour never carries it alone.

**Loading state**: skeleton rows matching the final invariant count — never a spinner.
**Error state**: "Couldn't check that — try asking again." Never a guessed answer.

**Explicitly exclude**: a score, a percentage, a confidence figure; a green tick on a failing card's
passing rows; a "Book this" button (this path is read-only); a summary sentence that replaces the rows.
```

---

# 13 · Profile

```
**Prepend §0.**

**Screen**: minimal, mostly read-only. Reached from the bottom nav.

**Layout**: header 56px reading "Profile" at 16px/600, no back control (it is a nav destination). Content
at 24px side padding. Bottom nav still rendered, "Profile" active.

**Section 1 — identity**, read-only, no card, no border, no interactive affordance of any kind — no hover
state, no cursor change, no accent colour. It was never a control:
- "Manoj Sharma" at 16px/600
- "+91-9000010006" at 16px JetBrains Mono, secondary text
- "Carrier: Rajasthan Roadlines" at 16px/400, secondary text

**Section 2 — vehicle**, same read-only treatment, preceded by a 12px/600 uppercase tertiary label
"VEHICLE":
- "UP14GT4106 · 32 ft multi-axle" — the registration in JetBrains Mono, the description in Inter. Note
  the space between number and unit: `32 ft`, never `32ft`, and never pluralised.

**None of the above is editable.** This data is owned by the dispatcher's system upstream and is displayed
here for confirmation only. There is no edit pencil, no "Edit profile" button, no avatar upload.

**1px `#E2E8F0` rule**, 24px above and below.

**Section 3 — settings**, three rows, each 56px tall, label left at 16px/400 primary, value right at 16px
secondary:
- "Notifications" → "On" with a 16px `chevron-right`. This row is the re-entry point for a driver who
  declined push at onboarding — it is a real destination, not a display value.
- "Language" → "English". No picker in this version; the row exists so the setting has an obvious home.
- "Theme" → "Light" with a `chevron-right`. ⚑F10

**1px rule**, then **"Sign out"** as a full-width left-aligned 56px row, 16px/400, in `#DC2626` /
`#F87171`. ⚑F11

**Explicitly exclude**: an avatar or profile photo; an "Edit" affordance on any identity or vehicle field;
statistics, badges, streaks, on-time percentages or any gamification; a rating; a support-chat entry point
(help on this surface is contextual, attached to the thing being explained — there is no help centre);
an "About" or version section; a delete-account row.
```

---

# 14 · Push-permission priming

```
**Prepend §0.**

**Screen**: the custom screen shown **before** the browser's own permission dialog. The browser prompt is
one-shot — a denial is effectively permanent, and a driver who denies it will not learn that their hold
lapsed. So the ask is primed, never cold.

**Timing, state it in the prompt**: this appears as step 3 of onboarding — after sign-in, and after the
driver has confirmed which load the conversation is about. It never appears before the driver has done
something meaningful.

**Layout**: a centred single-purpose screen, page background, 24px side padding, content vertically
centred, no header, no nav, nothing else competing.
- A 32px `bell` icon in tertiary text colour.
- 24px gap, heading at 20px/600 primary text, centred: "Stay informed about your slot"
- 16px gap, body at 16px/1.5 secondary text, centred, max ~40 characters per line, verbatim:
  "Dock slots can change while you're driving. Notifications let me tell you straight away instead of you
  finding out at the gate."
- 32px gap, primary button: full width, 40px tall, 6px radius, `#2563EB` / `#3B82F6` fill, white label at
  16px/500 — "Turn on notifications". Tapping this, and only this, triggers the browser prompt.
- 12px gap, secondary button: full width, transparent fill, 1px `#CBD5E1` border, primary text —
  "Not now".

**"Not now" is a real option**, not a dismissal that nags. The app is fully usable without push, and the
re-ask happens only after an event the driver actually missed, framed by that specific event.

**Denied variant** (second artboard): the conversation screen with a status line directly beneath the
header — full width, `#FFFBEB` / `#78350F`-at-25% fill, 1px `#F59E0B` top and bottom border, 12px vertical
/ 24px horizontal padding, a 16px `bell-off` icon then 14px text: "Notifications are off — you'll need to
keep this page open to see changes." Cause and consequence, stated once, no nagging, no dismiss-and-repeat
loop.

⚑F4 — the reference checklist for this pattern expects a realistic **preview of what a notification from
this app looks like** (title, body, app icon). The spec does not define one, so none is drawn here.

**Explicitly exclude**: an illustration or hero graphic; multiple permission asks on one screen; a
guilt-tripping decline label ("No thanks, I'll risk it"); a full-screen modal that cannot be dismissed;
triggering the browser prompt on screen load; a benefit list with checkmarks.
```

---

# 15 · Hold lapsed (`HOLD_LAPSED`)

```
**Prepend §0.**

**Screen**: 90 seconds expired before the driver confirmed. **The card is replaced in place, never
removed.** A driver who looks up to find their option simply gone learns nothing and trusts less.

**Before → after**, show both as adjacent artboards:
- Before: the HELD card — 2px dashed `#F59E0B` border, `#FFFBEB` fill, countdown reading `0:03` in
  `#DC2626` at weight 600, border pulsing once per second.
- After: same position, same size. Dock line and time line **struck through**, card at 40% opacity, 1px
  `#CBD5E1` border (the dashed amber is gone), status line reading "Hold lapsed" in `#DC2626` at full
  opacity.

**System notice** beneath the card: centred, no bubble, 14px secondary, max 92% width, verbatim:
"That hold has lapsed — Dock D1 · 13:00–14:15 is available to other drivers again. Nothing has been lost;
I can look again right now."

**Action**: a "Find options again" quick-reply chip — part of the notice, not something the driver has to
think to ask for. Pill, 999px radius, 1px `#CBD5E1` border, ≥44px tall.

**Persistent state line**: clears back to no active promise — the header shows only the back control and
the load descriptor, one row, 56px.

**Haptics**: 400ms on lapse. The driver may not be looking at the screen.

**Announcement**: `role="alert"` — this interrupts.

**The race case**: if the hold expires in the same moment the driver taps confirm, exactly one outcome
resolves. The card locks on tap and only resolves once the server answers — the UI shows either the lapse
or the pending state, **never both**.

**Explicitly exclude**: the card fading out or animating away; an "Oops" or "Sorry"; blaming the driver
for being slow; a modal or alert dialog; removing the card from the transcript; a red banner across the
whole screen (the failure is scoped to one card, and the notice is the scoped signal).
```

---

# 16 · Pending expired (`PENDING_EXPIRED`)

```
**Prepend §0.**

**Screen**: 15 minutes passed with no planner action. Capacity was lost while the driver may have been
driving toward it, so this is one of four events that gets elevated notification treatment.

**Card**: the PENDING card mutates in place — dock and time struck through, 40% opacity, 1px `#CBD5E1`
border, status line "Released — no planner response" in `#DC2626` at full opacity.

**System notice**, centred, no bubble, 14px secondary, verbatim:
"No planner responded in time, so Dock D1 · 13:00–14:15 has been released. This has been escalated to
operations, and I can look for fresh options now."

The escalation is stated plainly, not hidden. A driver whose request timed out should know a human now
owns it.

**Action**: "Find options again" quick-reply chip.

**Persistent state line**: clears; the thread stays active with fresh options loading.

**Push notification variant** (second artboard): a phone lock-screen notification at high priority — one
the user must dismiss rather than one that auto-expires. Title "SetuHaul Dock Command", body using the
**same template as the in-app copy**, never different wording: "No planner responded in time, so Dock D1 ·
13:00–14:15 has been released. I can look for fresh options now." Tapping it deep-links straight into this
thread with fresh options already loading — never into the thread list.

**Announcement**: `role="alert"`.

**Explicitly exclude**: hiding the escalation; "We're sorry for the inconvenience"; a retry button that
would re-request the same released slot; a countdown that keeps running past zero; notification copy that
differs from the in-app copy (a notification that says something different from the app is a second source
of truth).
```

---

# 17 · Lost the race (`SLOT_CONFLICT`)

```
**Prepend §0.**

**Screen**: another driver committed to the same interval a moment first.

**Card**: the contested card mutates in place — struck through, 40% opacity, status line at full opacity
in `#DC2626` reading "Taken by another driver".

**System notice**, centred, no bubble, 14px secondary, verbatim:
"Another driver requested Dock D1 · 13:00–14:15 a moment before you. That one's gone — here's what's open
now."

**Immediately beneath it**, a fresh option set — two or three cards in the default selectable state, each
with dock, date, time range and one differentiator. The alternatives appear in the same turn; the driver
never has to ask.

**Rules to state**:
- **Never blame the driver for being slow.** State the fact, move immediately to alternatives.
- **No penalty haptic** — losing a race is not the driver's error.
- The lost card stays in place above the new set so the driver can see *which* option went.

**Explicitly exclude**: "You were too slow"; "Try to respond faster next time"; an error-red banner; a
modal; removing the lost card; any reference to how many other drivers were competing (a driver never sees
their ranking position or why they lost a contested interval).
```

---

# 18 · Option withdrawn mid-conversation (`OPTION_WITHDRAWN`)

```
**Prepend §0.**

**Screen**: a dock went out of service while the driver was deciding. This is the clearest expression of
why cards mutate in place rather than the assistant sending a new message — the driver sees *which* option
died without matching prose to cards from memory.

**Only the affected card mutates.** Siblings are untouched, at full opacity, still selectable. Withdrawing
an entire option set because one member died would be both wrong and alarming.

**Layout**:
```
[ struck through, 40% opacity ]
  ~~Dock D5 · Tue 4 Aug~~
  ~~18:00 – 19:15~~
  No longer available          ← full opacity, #DC2626

[ untouched, full opacity, selectable ]
  Dock D2 · Tue 4 Aug
  19:00 – 20:15
  no waiting
```

**System notice** beneath, centred, no bubble, 14px secondary, verbatim:
"Dock D5 has just gone out of service, so the 18:00 option is no longer available. The other two options
are still open."

The second sentence is load-bearing — it is what stops the driver assuming everything collapsed.

**Announcement**: `role="alert"`.
**Push**: high priority, since the driver may be driving toward a dock that is no longer available.

**Explicitly exclude**: greying the whole set; replacing the set with a new message; a full-screen alert;
an animated removal; a "Refresh options" button that implies the remaining options are also stale.
```

---

# 19 · No same-day slot (`NO_SAME_DAY_SLOT`)

```
**Prepend §0.**

**Screen**: nothing works today, but tomorrow does. **This is not an escalation and must not look like a
failure** — it is the one negative-path message carrying good news underneath.

**Copy, verbatim**, as an assistant message:
"Nothing works at Jaipur DC today — the reefer dock is down for maintenance until 22:00 and the site
closes then. The earliest I can offer is tomorrow."

**Option cards** in the default selectable state, full opacity, standard treatment:
```
Dock D5 · Wed 5 Aug
06:00 – 07:15
first of the day

Dock D5 · Wed 5 Aug
07:30 – 08:45
most buffer
```

**The date on these cards is doing real work.** A driver reading "06:00" as this morning has been
mis-promised by a formatting choice. Render "Wed 5 Aug" at the same weight and size as on any other card —
do not add a "tomorrow" badge or highlight; the date itself is the mechanism, and a special badge trains
drivers to look for the badge rather than the date.

**Closing assistant line**, verbatim:
"Nothing is held yet. If waiting overnight doesn't work, I'll bring in operations."

**Action**: a single quick-reply chip — "That doesn't work — get help". The escalation route is **offered,
not withheld** until the driver thinks to ask.

**Tone**: no red, no warning icon, no error styling anywhere on this screen. The named blocking reason
(reefer dock, maintenance window, closing time) is stated as a fact in body text, not as an alert.

**Explicitly exclude**: red or amber error styling; a warning triangle; an "Unfortunately"; an apology for
a facility rule; a "tomorrow" badge, pill or highlight on the cards; hiding the get-help route behind a
menu; presenting this as the same visual treatment as no-feasible-slot (§20) — the two must look different.
```

---

# 20 · No feasible slot → escalation (`NO_FEASIBLE_SLOT`)

```
**Prepend §0.**

**Screen**: the whole search horizon is exhausted. The thread hands over to a human and the assistant
stops auto-replying.

**Copy, verbatim**, as one assistant message:
"I can't find a workable slot for this load at Jaipur DC — the only reefer dock is out of service past
your arrival time, and there's nothing tomorrow either.

I've passed this to operations. Reference ESC-4471. Someone will contact you directly."

`ESC-4471` renders in JetBrains Mono. **Always a reference and a promise of contact** — an escalation
without a reference feels like being dropped.

**Layout**: the assistant message, and nothing else. **No option cards. No "Try again" chip.** Offering a
retry that will fail identically is worse than not offering one.

**Header**: the load descriptor on row one, and on row two the escalation reference as plain 14px
secondary text — "Escalated · ESC-4471". ⚑F3 — this does **not** render in the promise-state chip slot and
does not borrow a promise-state hue; the chip is reserved for the four promise states and there is no
active promise here.

**Composer**: stays fully enabled. The driver can still say something, and a person will read it.

**Explicitly exclude**: a promise-state chip in any of the four state colours; option cards; a retry or
"search again" action; an estimated response time the system cannot honour; a red full-screen error; a
support phone number invented for the mockup.
```

---

# 21 · Human takeover (`HUMAN_JOINED`)

```
**Prepend §0.**

**Screen**: an operations coordinator has taken over the thread. The driver must be able to tell, at a
glance, that they are now talking to a person.

**Transcript order**:
1. The last assistant message, in its settled lower-contrast form: "I've passed this to operations.
   Reference ESC-4471."
2. **Takeover divider** — full width, a 1px `#CBD5E1` rule either side of centred 14px secondary text:
   "Neha from Operations joined". Permanent, not dismissible, not a bubble. A silent takeover reads as
   the bot ignoring them.
3. The human's message, in the OPERATIONS tier: a 20px circular avatar with "N" on `#059669`, then
   "Neha · Operations" at 14px/500 tertiary, then a left-aligned bubble with a **1px `#CBD5E1` border —
   visibly heavier than the assistant's `#E2E8F0`**. Copy: "Hi Manoj — I'm looking at your reefer load
   now. I can get the D5 maintenance pushed by an hour if you can hold until 19:00."
4. A driver reply, right-aligned: "That works. I'll wait."   16:31 ✓✓

**Header**: load descriptor plus "Escalated · ESC-4471" as plain 14px secondary text on row two — not a
promise-state chip. ⚑F3

**Rules to state**:
- **The assistant stops auto-replying on this thread.** If it contributes again, that is because a human
  used an internal drafting tool, and the message posts **as the human**, never as the assistant.
- The avatar, the real name and the heavier border carry the AI/human distinction together — no single one
  of them is enough on its own.
- A push notification fires when this happens: a driver should know a person is now involved.

**Announcement**: the divider is `role="status"` and announces "Neha from Operations joined the
conversation."

**Explicitly exclude**: an "AI" / "Human" toggle or badge on the header; a dismissible divider; a
"Neha is typing…" indicator styled the same as the assistant's dots (if a typing indicator is shown here
it carries her attribution, not the assistant's); a rating or "was this helpful" prompt; a video-call or
phone-call button.
```

---

# 22 · Ambiguous shipment — disambiguation

```
**Prepend §0.**

**Screen**: the driver referred to a different load than the thread they are in. The assistant asks once,
with the two readings offered as taps.

**Transcript**:
- Driver, right-aligned: "Actually I meant the Kota load"
- Assistant, left-aligned: "You have two Kota loads today. The one due 08:45, or the later one due 18:00?"

**Quick replies**: two pill chips — "The 08:45 one" and "The 18:00 one". Each ≥44px tall, 8px apart, 999px
radius, 1px `#CBD5E1` border.

**Rules to state**:
- **Human descriptors, never identifiers.** "The Kota load due 08:45", never "SHP1004". A reference number
  may ride along in brackets; it may never be the question.
- **At most one question per turn**, and only for a field that actually blocks the next step.
- **After two failed attempts, the thread escalates rather than looping.** Do not design a third ask.

**Escalation variant** (second artboard): after two failed attempts, the assistant message reads
"I'm not able to tell which load you mean. I've passed this to operations. Reference ESC-4482. Someone
will contact you directly." — no cards, no further quick replies.

**Explicitly exclude**: a dropdown or picker of shipment IDs; "Which shipment ID?"; more than two quick
replies here; a third clarification attempt; asking an open question when two readings can be offered as
taps.
```

---

# 23 · Low-confidence ETA — clarification and risk framing

```
**Prepend §0.**

**Screen**: the driver said "I am late by one hour", which does not determine an arrival time. The
assistant offers the two readings, then frames the risk as a choice rather than hiding it as a warning.

**Artboard A — the clarification**:
- Driver: "I am late by one hour"
- Assistant: "Does that mean your new arrival is 11:00, or that the delay may continue for another hour?"
- Quick replies: "Arriving 11:00" and "Might be longer"

**Never derive an ETA from a delay duration.** A 45-minute repair is not a 45-minute ETA shift.

**Artboard B — risk framed as a choice**, after the driver proceeds with an uncertain time:
- Assistant: "I can hold 11:00, but if that time is uncertain, the 12:15 window gives you an hour of
  cushion and avoids a second reschedule."
- Two option cards, both in the default selectable state, full opacity, **neither visually preferred over
  the other** — no highlight, no "Recommended" badge, no border emphasis:
```
Dock D4 · Tue 4 Aug
11:00 – 12:15
soonest

Dock D2 · Tue 4 Aug
12:15 – 13:30
most buffer
```

The driver prices their own risk — they are better placed to judge it than the system. The assistant's
sentence carries the trade-off; the cards stay neutral.

**Low-confidence marker**: where an ETA confidence needs showing, it is a 16px `alert-triangle` icon
only — confidence never gets its own hue, because hue in this product is rationed to promise state and
danger.

**Explicitly exclude**: a "Recommended" badge on either card; a confidence percentage or score; a risk
meter or gauge; an amber warning banner; a "How late are you?" open question; auto-selecting the safer
option.
```

---

# 24 · Offline

```
**Prepend §0.**

**Screen**: the network dropped. A driver must never lose access to what they already have — and the
moment they most need this app (at a gate, mid-exception, with a hold running down) is exactly when signal
is most likely to fail.

**Header**: load descriptor on row one. Row two carries the promise-state chip **with a staleness marker
appended**: `⏱ HELD 1:24 · updated 2 minutes ago`. The countdown **holds at its last-known value and does
not tick** — it computes from server time, and against an untrustworthy local clock a free-running
countdown would lie.

**Transcript**: fully readable from cache, full contrast, no dimming. The confirmed appointment details in
particular stay fully legible — that is the single most likely thing a driver needs offline, at a gate.

**Option cards**: 40% opacity, each with a status line at full opacity — a 16px `wifi-off` icon then
"Offline — can't select now". **Visibly disabled, never hidden.** State the reason on every card, not once
at the top.

**System notice**, centred, no bubble, 14px secondary, with a 16px `wifi-off` icon: "You're offline. I'll
send this as soon as you're back."

**Queued driver message**: a normal right-aligned bubble at full opacity, with delivery status beneath
reading `⏱ queued` — explicit words, not a symbol, so it can never be mistaken for sent.

**Composer**: **stays fully enabled**, placeholder "Message · will send when you're back online", send
control operable.

**Why option selection is the one thing disabled**, worth stating in the prompt so it is not "fixed": a
driver who taps an option offline cannot actually be granted a hold. Queuing that action and silently
succeeding or failing later is precisely the stale-commitment risk this whole product exists to prevent.

**Degradation styling**: the staleness marker and the notice use amber
(`#FFFBEB` background family, `#B45309` text), never red. A screen that looks like it is on fire when the
real problem is "this number is 40 seconds old" trains people to stop trusting red when it matters.

**On reconnect**: queued messages send, the thread re-syncs, cards re-validate against a fresh snapshot
before re-enabling — silently where nothing changed.

**Explicitly exclude**: a full-screen "You are offline" blocker; hiding the option cards; a disabled
composer; a red offline banner; a countdown that keeps ticking; a "Retry connection" button as the only
thing on screen; dimming the transcript.
```

---

# 25 · Refusals — the four non-safety patterns

```
**Prepend §0.**

**Screen**: four artboards, one per refusal. **Every refusal names the specific rule and offers a route.**
A refusal with no next step is a dead end, and dead ends drive drivers back to phone calls — which is the
failure mode this product exists to remove.

All four are plain assistant messages in the standard left-aligned bubble. **No red, no warning icon, no
error styling on any of them** — a refusal is a fact being stated, not a system error.

**A — "Just confirm it, don't wait for the warehouse"**:
"Only a warehouse planner can confirm a slot — I can't skip that step.
I can flag your request as urgent so it's reviewed first."
→ one quick-reply chip: "Flag as urgent"

**B — "Book me the 7:30 even though I get there at 8"**:
"7:30 won't work — your ETA is 8:00 and the unload needs to finish before the slot closes. Here's what
does fit your arrival time:"
→ followed immediately by one option card in the default selectable state:
   Dock D2 · Tue 4 Aug / 08:15 – 09:30 / soonest
Names the specific failing invariant in plain language, never "that's not allowed".

**C — "I'm carrying something not on the manifest"**:
"That's not something I can schedule around — it needs a person to look at before anything else happens.
I've flagged this to operations now."
→ **no cards, no quick replies.** No scheduling continues past this point. Header row two shows
"Escalated · ESC-4478" as plain 14px secondary text. ⚑F3

**D — "Give me the slot that truck ahead of me has"**:
"I can't move another driver's booking. Here's what's actually open right now:"
→ followed immediately by one option card:
   Dock D1 · Tue 4 Aug / 13:00 – 14:15 / no waiting
States the policy once, briefly, then moves straight to what *is* available — dwelling on the refusal
reads as scolding.

**Explicitly exclude**: apologising for a system rule ("Sorry, that dock can't take your weight" → state
the rule, offer the alternative); a red error banner; a warning triangle; "That's not allowed"; a refusal
that ends the message without a route (except C, where escalation *is* the route); any mention of another
driver's identity, carrier or booking details in D.
```

---

# 26 · Refusal — safety

```
**Prepend §0.**

**Screen**: the driver has reported a safety problem — "My brakes are failing, should I keep driving?"
**This is the one screen in this product where nothing else may compete for attention.**

**Layout**: the conversation shell, and one assistant message. That is all.
- **No option cards.**
- **No quick replies.**
- **No suggestions.**
- **No promise-state chip in the header** — there is no promise here. Header row one is the back control
  and load descriptor; row two is "Escalated · ESC-4471" as plain 14px secondary text. ⚑F3
- The composer stays enabled.

**Copy, verbatim — this is reviewed wording, not a template to rephrase**:
"That's not a decision I can make for you. Please contact your carrier
and pull over safely if you're not already stopped.
Reference ESC-4471 has been raised with operations."

The first line is always first, always this direct, and always routes to a human immediately. This is the
one message in the entire product where getting the tone wrong has the highest possible cost.

**Contact affordance**: the only interactive element permitted alongside the message is the driver's own
carrier contact, rendered as a plain full-width row beneath the bubble — 16px/400, a 16px `phone` icon,
the carrier name and number. It is a `tel:` link, not a styled primary button competing with the message.

**Styling restraint**: no red, no alert banner, no warning triangle, no elevated card. Visual alarm on
this screen adds nothing — the words carry it, and decoration would read as the system dramatising rather
than helping.

**Explicitly exclude**: option cards; quick replies; an emergency-services button the product cannot
actually honour; a modal; a red full-screen takeover; an "Are you OK?" follow-up prompt; any scheduling
affordance whatsoever; a rephrased or "friendlier" version of the copy above.
```

---

# 27 · Send, commit and load failures

```
**Prepend §0.**

**Screen**: three artboards. In a system where a tap commits capacity, a failure must state plainly that
it left no partial state — otherwise the rational response is to tap again.

**Artboard A — message failed to send**:
- The driver's bubble stays in place at full opacity with the typed text preserved — never cleared.
- Delivery status beneath, 14px, `#DC2626`: `⚠ not sent`, followed by an inline "Retry" text button (44px
  hit area, `#2563EB` label, underlined).
- 300ms haptic on failure.

**Artboard B — commit failed** (the driver requested a slot and the write failed):
- The option card **unlocks and returns to its previous state** — unchanged, still selectable.
- A system notice beneath, centred, no bubble, 14px, verbatim:
  "That didn't save. **Nothing has changed.**"
  then a "Try again — this won't double-book you." action chip.
- The second half of that sentence is not padding: every capacity-affecting action carries an idempotency
  key, so retrying after an uncertain failure is safe — and a driver who does not know that will avoid
  retrying a request that genuinely needs retrying.
- "Nothing has changed" is bolded and is the load-bearing part of the message.

**Artboard C — thread failed to load**:
- The transcript skeleton resolves into an error state in the content region only; header and composer
  stay rendered.
- 32px `octagon-alert` icon in tertiary colour, 16px gap, "Couldn't load this conversation." at 16px/600
  centred, 8px gap, "This is usually a connection problem." at 14px secondary centred, 24px gap, a
  "Retry" button — full width, 40px tall, 1px `#CBD5E1` border, transparent fill, primary text.
- If a cached transcript exists it renders beneath, read-only, rather than showing nothing.

**Announcement**: all three are `role="alert"` — silence on failure is the single worst accessibility
failure mode available.

**Session note to state in the prompt**: a driver is **never signed out mid-exception**. Session refresh is
silent, and in-flight typed text survives it. A login screen appearing while a hold is burning down is a
product failure, not an edge case.

**Explicitly exclude**: "Something went wrong"; "Oops"; an error code shown to the driver; clearing the
typed message; a modal dialog; a toast that disappears before it can be read; a bare "Try again" with no
statement about what did or did not happen; showing an empty state when the real problem is a load failure.
```

---

# 28 · Cancelled shipment

```
**Prepend §0.**

**Screen**: the driver asked about a slot for a shipment that has been cancelled upstream. The refusal is
the whole answer.

**Copy, verbatim**, as one assistant message:
"That shipment and its appointment were cancelled.
Please contact dispatch before travelling."

**Layout**: the message, and nothing else. **No option cards, no scheduling path, no quick replies.** The
thread closes after this reply.

**Routing matters here**: this points at **dispatch**, not operations. It is an upstream matter, and
sending the driver to the wrong place wastes a phone call.

**Header**: load descriptor only, one row, 56px. No promise-state chip — there is no promise.

**Thread list consequence** (second artboard): the thread moves under "Resolved" at 60% opacity with no
priority marker, and its state chip slot shows nothing rather than a promise state. ⚑F3

**Composer**: stays enabled. The driver can still say something; it will reach a person.

**Explicitly exclude**: option cards; a "Find other options" chip; an apology; a red error treatment;
routing the driver to operations; a promise-state chip; auto-deleting the thread.
```

---

## Flagged gaps and ambiguities

Not prompts. These are the places where the spec was silent, self-contradictory, or thinner than a prompt
needed. **Nothing below was resolved by invention** — each states what was done in the prompts and why.

| # | Gap | What the prompts do |
|---|---|---|
| **F1** | **Type-size contradiction, the largest one.** `00-foundations/typography.md` and `01-driver-chat/accessibility.md` both state a hard **14px floor on this surface** ("the 11px floor elsewhere does not apply here"). But `screens.md`'s thread-card anatomy assigns `text-sm` (13px) to the preview and `text-micro` (11px) to the timestamp, and `mockup.html` renders them at 12.5px and 10.5px. Three of four sources disagree with the two that state it as a rule. | Prompts use **14px as the floor throughout**, since two foundations files state it as a field-condition requirement and the surface files appear to have inherited the product-wide scale without re-checking it. Needs a real decision. |
| **F2** | **Conversation header height is unstated.** `screens.md` gives "56px" but draws two rows inside it (back + descriptor, then the persistent state line). 56px cannot hold a 24px control row plus a 24px chip row plus padding. | Prompts describe the header as two rows without asserting a total height. A value is needed. |
| **F3** | **No header treatment is defined for an escalated / closed thread.** `components.md` §6's persistent-state-line table covers only the four promise states plus "no active promise → hidden". `mockup.html` puts "Escalated · ESC-4471" **inside a promise-state chip**, which contradicts `00-foundations/components.md` §2 ("the chip is the only component permitted to use state hues" — and ESCALATED is not one of the four states). | Prompts render the escalation reference as **plain 14px secondary text on header row two, never in the chip slot**. Derived from the existing rules, but it is a derivation and should be confirmed. Affects §20, §21, §25C, §26, §28. |
| **F4** | **No notification preview exists.** The push-opt-in checklist expects a realistic mock of what a notification from this app looks like (title, body, icon), and `auth-and-scoping.md`'s priming screen has no such element. | Prompt §14 omits it and says so inline. Worth adding to the spec — it is the single highest-leverage item on that checklist. |
| **F5** | **Bottom-nav tokens are undefined.** `spacing-and-layout.md`'s app shell is the desktop icon-rail/top-bar/status-bar model; the driver PWA's two-item bottom nav appears only in `screens.md`'s wireframe and `mockup.html`. No active/inactive token, no height token. | Prompts use `interactive-default` (`#2563EB` / `#3B82F6`) for active and `text-tertiary` for inactive, matching the mockup, at the `accessibility.md` height floor of ≥56px. Derived from the mockup, not from a foundation. |
| **F6** | **The unread marker and the priority marker both occupy the left edge.** `01-driver-chat/components.md` §1 gives unread a "2px `border-focus` left inset"; `screens.md` §1 gives priority a "3px left edge marker". What happens on a card that is both unread and CRITICAL is unspecified. | Prompt §1 lists both as separate states and does not draw them together. A real collision. |
| **F7** | **Quick-reply heights do not reconcile.** `screens.md` gives the quick-reply region a fixed 48px; `accessibility.md` requires chips ≥44px tall; `comfortable` density puts 12px padding around them. 44 + 24 = 68px, not 48px. `mockup.html` renders ~37px chips, below the stated floor. | Prompts specify **chips ≥44px** and describe the region by its padding rather than asserting 48px. The 48px figure appears unachievable alongside the 44px floor. |
| **F8** | **Four option-card states share one opacity.** Lost, Withdrawn, Disabled-offline and Superseded all render at 40%, distinguished only by the status line (and Superseded has no status line at all). At a glance in sunlight, three of them are identical. | Prompt §9 keeps the status line at **full opacity inside the dimmed card** so the distinguishing signal is not itself dimmed, and flags Superseded as the weakest case. |
| **F9** | **The eligibility card's green step is unstated.** `01-driver-chat/components.md` §8 says "green verdict line" without a token. `green-600` (#059669) measures 3.8:1 on white and **fails** AA for normal text; `green-700` (#047857) passes at 5.6:1. | Prompts use `#047857` / `#34D399`. Derived from `color.md`'s own contrast table, but the surface file should name the step. |
| **F10** | **The theme row has no defined behaviour.** `color.md` (U69) says every user can switch theme and have it persist; `accessibility.md` says light "cannot be overridden to dark without a warning". The warning's copy, form (inline text? confirm sheet?) and dismissibility are all unspecified. | Prompt §13 renders the row and its chevron and stops there. |
| **F11** | **Sign-out has no friction tier.** `00-foundations/components.md` §19's three-tier destructive model (none / 5-second undo / typed confirmation) does not classify sign-out, and signing out a driver mid-exception is exactly what `auth-and-scoping.md` calls a product failure when the system does it. | Prompt §13 renders it as a plain danger-coloured row with no confirmation specified. |
| **F12** | **Minor — content padding.** `spacing-and-layout.md` gives `comfortable` a 24px content padding; `mockup.html` uses 12px. | Prompts use **24px** (the foundation value). The mockup is the outlier. |

**One thing in the brief that does not map onto the spec**: the request mentioned "option cards across all
three tiers." There is no three-tier option card. The three tiers are **message sender tiers** (U47 —
driver / assistant / operations, plus centred system notices), covered in prompt §8. The option card has
**eight states**, covered in prompt §9.
