# Stitch prompts — shared shell, auth and account surfaces

> Generation prompts only. **This file is not a spec** — it does not define or amend any decision. Every
> value below is copied from an existing foundations file (`color.md`, `typography.md`,
> `spacing-and-layout.md`, `elevation-and-depth.md`, `motion.md`, `iconography.md`, `voice-and-tone.md`,
> `accessibility-behaviour.md`, `components.md` §7/§10/§13/§15/§18/§19, `auth-and-scoping.md`) or is
> flagged inline as a judgement call. Where a value has no foundation source, it says so — that is a gap to
> close in the real spec, not a new decision made here.
>
> Target tool: **Stitch** (`stitch.withgoogle.com`). Each block is self-contained and meant to be
> copy-pasted alone, which is why the product/typography/colour preamble repeats.

## Prompt inventory and why the count is 8, not 9

| # | Prompt | Covers decision |
|---|---|---|
| 1 | Sign-in (with show/hide password) | 1, 4 |
| 2 | Role picker | 2 |
| 3 | Password reset — both screens | 3 |
| 4 | User menu popover | 5 |
| 5 | Notifications panel popover | 6 |
| 6 | Search palette modal | 7 |
| 7 | Help — top-bar contact link | 8 |
| 8 | Account / Settings page — all five sections | 9 |

**Decision 4 is an exclusion rule, not a screen.** "No Remember me, no SSO, no Sign up" describes what
must be absent from sign-in, so it lives in prompt 1's exclude list rather than getting a prompt that
would have nothing to render.

**Decision 3 is one prompt with two artboards.** The two reset screens share a single card chassis and
sit in one continuous flow with no shell chrome between them; splitting them risks Stitch drifting the
card's padding, width and field treatment between two generations that must look identical.

**Decision 9 is one prompt for all five sections.** It is one continuous scrolling route in the content
region, not five screens — sectioning it into five prompts would produce five headers and no page.

---

## 1 · Sign-in (with show/hide password toggle)

Reproduces the approved reference block verbatim, with **one addition**: the show/hide password toggle
(locked decision 1), which the reference predates.

---
**Copy-paste into Stitch — SetuHaul Dock Command · Sign-in (comprehensive)**

**Product context**: SetuHaul Dock Command is a B2B internal operations tool for a logistics company — not a consumer app, no marketing site, no brand storytelling. One shared login serves six roles across 6 facilities. Treat this as an "operator tool" aesthetic: calm, dense-capable, trustworthy — closer to a cockpit instrument than a SaaS landing page.

**Typography**: `Inter` for all UI text — weights 400/500/600/700 only, no others loaded. Chosen specifically for legibility at 12–14px (this product has dense queues elsewhere), tall x-height that survives glare on a driver's phone. Do not substitute a "more distinctive" font — this is a deliberate, locked choice for functional legibility, not an oversight to fix.

**Color** (must define both a light and dark variant):
- Primary action: `#2563EB` (`interactive-default` / blue-600) light, `#3B82F6` (blue-500) dark
- Page/card background: `#FFFFFF` (`surface-raised` / neutral-0) light, `neutral-900` dark
- Primary text: `neutral-900` light, `neutral-50` dark
- Error state: text `#B91C1C` (red-700) on background `#FEF2F2` (red-50) with border `#DC2626` (red-600), in dark mode text `red-400` on `red-900 @ 25% opacity`

**Spacing**: base unit 4px. Standard field/section gaps use 8px and 16px; 24px separates the form from secondary links. Values above 32px are rare outside empty states and login — so a generously padded login/settings card is correct here.

**Elevation**: cards sit at elevation tier 1 ("Raised") — `neutral-0` fill, a barely-visible `0 1px 2px rgba(15,23,42,0.06)` shadow, subtle border. Popovers/dropdowns (user menu, notifications) sit at tier 3 ("Floating") — `shadow-md`, `0 4px 12px rgba(15,23,42,0.10)`. Modals (search palette) sit at tier 4 ("Overlay") — `shadow-lg`, `0 12px 32px rgba(15,23,42,0.14)`.

**Radius**: 8px on cards (`radius-lg`), 12px on modals (`radius-xl`), 6px on inputs/buttons/popovers (`radius-md`).

**Motion**: transitions use 200ms (`duration-base`) with ease-out (`cubic-bezier(0.16, 1, 0.3, 1)`) — quick and settled, never bouncy, never a spring/elastic overshoot. No looping/ambient animation anywhere.

**Layout**: single centred card, no split-screen hero panel, no illustration, no marketing copy. Card max width 400px, 32px internal padding.

**Fields**: labels always visible, never placeholder-as-label; error text sits below the field with an alert icon, never colour alone; validate on blur not keystroke.

**Screen contents, in order**: wordmark "SetuHaul" with "Dock Command" beneath it · field "Email or phone" (one field, not two tabs — drivers know their phone number, office staff know their email) · field "Password" with a show/hide toggle · primary full-width button "Sign in" · text link "Forgotten your password?".

**Show/hide password toggle**: a 20px icon-only button sitting inside the password field's right edge, vertically centred, with 8px inset from the field border. Lucide `eye` when the password is masked, `eye-off` when revealed. It is a toggle button, not a checkbox — `aria-pressed` reflects state and its accessible name changes between "Show password" and "Hide password". It never sits outside the field as a separate labelled control, and it never covers typed characters: the field's text padding-right reserves 40px for it. Default state is masked. Focus ring on the toggle is the same 2px solid ring with 2px offset as every other control — not a subtler treatment because it is small.

**Explicitly exclude**: no "Remember me" checkbox, no SSO/social login buttons, no "Sign up" or "Create account" link, no "or continue with" divider, no marketing footer, no illustration, no background photograph or gradient mesh, no animated background.

**Error variant**: a message reading "Those details don't match" — deliberately identical wording whether the email or the password was wrong.

**Rate-limited variant**: "Too many attempts. Try again in 5 minutes." — a cause and a next action, never a silent failure.
---

---

## 2 · Role picker

Interstitial between password submit and landing surface. **Rendered only for accounts holding more than
one role** — a single-role account never sees this screen and goes straight to its landing surface.

---
**Copy-paste into Stitch — SetuHaul Dock Command · Role picker (interstitial)**

**Product context**: SetuHaul Dock Command is a B2B internal operations tool for a logistics company — not a consumer app, no marketing, no brand storytelling. "Operator tool" aesthetic: calm, trustworthy, closer to a cockpit instrument than a SaaS product tour. This screen appears once, between password submit and the landing surface, and only for the small number of accounts that hold more than one role. It is a fork in a flow, not a destination — it should feel like one step of signing in, not a new place.

**Typography**: `Inter` only — weights 400/500/600/700. Do not substitute a more distinctive font. Role names render at 14px weight 600 (`text-body` at emphasis weight); facility names at 13px weight 400 in secondary text colour (`text-sm`).

**Color** (define light and dark):
- Card background `#FFFFFF` (neutral-0) light, `neutral-900` dark
- Primary text `neutral-900` light, `neutral-50` dark
- Secondary text `#475569` (neutral-600) light, `#CBD5E1` (neutral-300) dark
- Row hover background `#F1F5F9` (neutral-100) light, `#1E293B` (neutral-800) dark
- Row separators 1px `#E2E8F0` (border-subtle) light, `#1E293B` dark
- Focus ring `#2563EB` (blue-600) light, `#60A5FA` (blue-400) dark

**Layout**: the same single centred card as the sign-in screen — same 400px max width, same 8px radius, same tier-1 elevation (`0 1px 2px rgba(15,23,42,0.06)` + subtle border), same 32px padding. Visual continuity with sign-in is the point: this must read as the second beat of one flow.

**Contents**: a short heading "Choose how to sign in" · one line of secondary text "You have more than one role. This decides what you see." · a plain vertical list of role + facility pairs, each a full-width row.

**Row anatomy**: role name on the first line, facility on the second, left-aligned, 12px vertical / 16px horizontal padding, 1px separator between rows, 44px minimum height. Examples to render: "Warehouse Planner — Jaipur DC", "Operations Manager — All facilities", "Gate Officer — Gurugram Cross-Dock". Render role and facility as two lines within the row, not as one run-on string.

**Interaction**: the entire row is the target. Tapping/clicking one proceeds immediately to that role's landing surface — no selected state, no radio button, no "Continue" button to press afterwards. Hover changes background colour only; it must not lift, scale, or shift the row. Keyboard: arrow keys move between rows, Enter activates.

**Explicitly exclude**: no icons of any kind on the rows (no shield, no truck, no building, no avatar) · no colour swatches or coloured accents beside facility names (facility accent colour is reserved elsewhere in this product and must not appear here) · no branding chrome — no wordmark, no logo, no product name banner · no radio buttons or checkboxes · no "Continue"/"Next" button · no "Remember my choice" option · no role descriptions or explanatory blurbs per row · no illustrations · no card-grid or tile layout — this is a plain list.

**Empty/edge**: never render this screen with one row. If an account resolves to a single role it must be skipped entirely.
---

---

## 3 · Password reset — request form and new-password form

One prompt, two artboards. **Screen A** is reached from sign-in's "Forgotten your password?"; **screen B**
is reached from an out-of-app email link and is a cold entry into the product — the user arrives with no
session and no context.

Screen B's **invalid/expired-link state is an addition beyond the locked decision**, included because a
reset link that has been used or has aged out is the most likely real outcome after the happy path and the
screen cannot exist without an answer for it. Flagged in the report.

---
**Copy-paste into Stitch — SetuHaul Dock Command · Password reset (two screens)**

**Product context**: SetuHaul Dock Command is a B2B internal operations tool for a logistics company. Invite-only accounts, one password-based identity provider, six roles across 6 facilities. "Operator tool" aesthetic: calm, factual, trustworthy — never reassuring-in-a-consumer-way, never celebratory. Generate two artboards that share one identical card chassis.

**Typography**: `Inter` only — 400/500/600/700. Body 14px/1.5. Headings 20px weight 600. Do not substitute a more distinctive font.

**Color** (define light and dark):
- Card background `#FFFFFF` (neutral-0) light, `neutral-900` dark
- Primary action `#2563EB` (blue-600) light, `#3B82F6` (blue-500) dark
- Primary text `neutral-900` light, `neutral-50` dark; secondary text `#475569` light, `#CBD5E1` dark
- Error: text `#B91C1C` (red-700) on `#FEF2F2` (red-50) with `#DC2626` border; dark mode `red-400` text on `red-900 @ 25%`
- Informational (not success): text `#1D4ED8` (blue-700) on `#EFF6FF` (blue-50) with `#3B82F6` border; dark mode `blue-400` on `blue-900 @ 25%`

**Shared chassis**: single centred card, 400px max width, 32px padding, 8px radius, tier-1 elevation (`0 1px 2px rgba(15,23,42,0.06)`, subtle 1px border). Identical on both artboards — same width, same padding, same field height, same button. No hero panel, no illustration, no split screen.

**Motion**: 200ms ease-out `cubic-bezier(0.16, 1, 0.3, 1)` on state changes. No entrance animation on the card, no ambient/looping motion.

**Fields**: labels always visible above the field, never placeholder-as-label. Error text below the field with a small alert icon — never colour alone. Validate on blur, not on keystroke.

**ARTBOARD A — Request a reset**
- Heading "Reset your password"
- One line: "Enter the email or phone number you sign in with."
- One field, labelled "Email or phone" (single field — do not split into tabs or two inputs)
- Primary full-width button "Send reset link"
- Secondary text link "Back to sign in"
- **Submitted state (render as a variant)**: the form is replaced in place by an informational panel — not a green success panel — reading "If that email or phone matches an account, a reset link is on its way. The link works once and expires in 30 minutes." Use the informational blue treatment above, not a success/green treatment. This wording must be identical whether or not an account exists; the screen must never confirm that an account was found.
- **Rate-limited variant**: "Too many attempts. Try again in 5 minutes."

**ARTBOARD B — Set a new password**
- Heading "Set a new password"
- Field "New password" with a show/hide toggle (Lucide `eye` / `eye-off`, icon-only button inset 8px inside the field's right edge, 20px, `aria-pressed`, accessible name toggles between "Show password" and "Hide password", field reserves 40px right padding for it)
- Field "Confirm new password" with its own independent show/hide toggle
- Requirements list beneath the first field, rendered as static helper text at 13px secondary colour — each requirement gets a state marker (a check when met, a neutral dot when not), never colour as the only signal
- Primary full-width button "Set password and sign in"
- **Mismatch error variant**: below the confirm field — "Those two passwords don't match."
- **Invalid or expired link variant (render as a separate state of this artboard)**: the form is not rendered at all. In its place, inside the same card: a 32px `link-2-off` icon in tertiary text colour, the line "This reset link has expired or has already been used.", one line of secondary text "Links work once and last 30 minutes.", and a single button "Request a new link" returning to artboard A. Do not render a disabled form behind it.

**Explicitly exclude, both artboards**: no password strength meter with a coloured bar (requirements list only) · no "Remember me" · no SSO/social buttons · no "Sign up" link · no security questions · no CAPTCHA widget mockup · no illustration, mascot, or background image · no confetti, checkmark animation, or celebratory treatment on success · no marketing footer · no support-chat bubble.
---

---

## 4 · User menu popover

Opens from the top bar's right-hand user-menu slot. Uses the existing popover primitive — not a drawer, not
a modal, not a new overlay type.

---
**Copy-paste into Stitch — SetuHaul Dock Command · User menu popover**

**Product context**: SetuHaul Dock Command is a B2B internal operations tool for a logistics company. This is the account menu in the top bar of the internal desktop shell (planner, operations, gate, carrier, admin). It is deliberately minimal — a five-person internal tool, not a SaaS account centre. "Operator tool" aesthetic: calm, terse, no delight.

**Trigger and placement**: a 32px circular avatar showing the user's initials, sitting at the far right of a 56px-tall top bar. Clicking it opens a popover anchored to the trigger's bottom-right, 8px below the top bar, 280px wide, auto height.

**Typography**: `Inter` only — 400/500/600/700. Menu item labels 14px weight 400. The identity header's name is 14px weight 600; the role line beneath it is 13px weight 400 in secondary colour. Do not substitute a more distinctive font.

**Color** (define light and dark):
- Popover surface `#FFFFFF` (neutral-0) light, `#1E293B` (neutral-800) dark
- Border 1px `#E2E8F0` light, `#334155` dark
- Primary text `neutral-900` light, `neutral-50` dark; secondary text `#475569` light, `#CBD5E1` dark
- Item hover background `#F1F5F9` light, `#1E293B`-on-`#0F172A` step dark
- Separators 1px `#E2E8F0` light, `#1E293B` dark
- Destructive text `#B91C1C` (red-700) light, `#F87171` (red-400) dark — used only on the two sign-out items
- Focus ring 2px `#2563EB` light / `#60A5FA` dark with 2px offset

**Elevation**: tier 3 "Floating" — light: `neutral-0` fill + `0 4px 12px rgba(15,23,42,0.10)` + 1px subtle border. Dark: `neutral-800` fill + `0 4px 12px rgba(0,0,0,0.40)` + 1px border. Radius 6px. No blur, no translucency, no glassmorphism anywhere — the surface is opaque.

**Motion**: the popover appears and disappears **instantly**, with no fade, scale, or slide entrance. Hover and focus background changes are 120ms ease-out `cubic-bezier(0.16, 1, 0.3, 1)`. No ambient motion.

**Contents, top to bottom**:
1. **Identity header** — non-interactive block, 12px/16px padding: full name on line one, current role and its scope on line two, e.g. "Warehouse Planner — Jaipur DC". This block has zero interactive affordance: no hover state, no cursor change, no focus ring.
2. Separator
3. **"Switch role"** — a menu item that opens a submenu listing the account's other role + facility pairs. **Render this item only when the account holds more than one role**; for a single-role account it is absent from the markup entirely, not greyed out.
4. **Appearance** — an inline three-way segmented control labelled "Appearance", with segments "Light", "Dark", "System". Not a submenu, not a switch — the current selection is visible without opening anything. Light is the default. The selected segment is marked by both a filled background and a weight change, never colour alone.
5. Separator
6. **"Settings"** — navigates to the account settings page.
7. Separator
8. **"Sign out"** — destructive text colour, acts immediately.
9. **"Sign out everywhere"** — destructive text colour. Activating it does not act immediately: the item expands in place into a two-line confirmation inside the same popover — "This signs you out on every device you're signed in on." with a single "Sign out everywhere" button beneath. No modal, no separate dialog.

**Item anatomy**: full-width rows, 44px minimum height, 10px vertical / 16px horizontal padding, label left-aligned. Hover changes background colour only — never lift, scale, or shift.

**Behaviour**: `Escape` closes the popover and returns focus to the avatar trigger. Arrow keys move between items. The popover is not modal — it does not trap the page or dim anything behind it, and there is no scrim.

**Explicitly exclude**: no leading icons on menu items (this shell has no menu-icon vocabulary and must not invent one) · no profile photo and no photo upload · no email address in the identity header (the role and its scope are what change what a click means; the email does not) · no active-sessions or device list · no "Manage account" external link · no billing, plan, usage, or upgrade item · no keyboard-shortcut hints beside items · no "What's new" / changelog / product-tour item · no theme preview thumbnails · no coloured facility swatch beside the role's facility name · no badge or count on the avatar.
---

---

## 5 · Notifications panel popover

Opens from the top bar's bell icon. Feed only — its preferences live in the settings page (prompt 8) and
are reached from there, not from inside this panel.

---
**Copy-paste into Stitch — SetuHaul Dock Command · Notifications panel**

**Product context**: SetuHaul Dock Command is a B2B internal operations tool for a logistics company — dock appointments, driver exceptions, escalations. This panel is the notification feed in the top bar of the internal desktop shell. Its job is: what happened, when, and take me to it. Nothing else. "Operator tool" aesthetic — terse, factual, no celebration, no emoji.

**Trigger and placement**: a 24px Lucide `bell` icon button at the right of a 56px-tall top bar, with an accessible name "Notifications". When unread items exist it carries a small count badge — a pill with the number, positioned top-right of the icon, in `#2563EB` (blue-600) with white text; the count is also spoken in the button's accessible name ("Notifications, 3 unread") so the badge is never the only carrier of that fact. Clicking opens a popover anchored bottom-right of the trigger, 8px below the top bar, **400px wide**, max height 480px with the item list scrolling inside.

**Typography**: `Inter` only — 400/500/600/700. Item title 14px; unread titles weight 600, read titles weight 400. Item body 13px weight 400 secondary colour, capped at two lines with ellipsis. Timestamps 11px weight 500 in tertiary colour. Any shipment, appointment or escalation identifier inside an item renders in `JetBrains Mono` — machine-generated values should look machine-generated. Do not substitute either font.

**Color** (define light and dark):
- Popover surface `#FFFFFF` light, `#1E293B` (neutral-800) dark
- Border 1px `#E2E8F0` light, `#334155` dark
- Primary text `neutral-900` light, `neutral-50` dark; secondary `#475569` / `#CBD5E1`; tertiary `#64748B` / `#94A3B8`
- Unread dot `#2563EB` (blue-600) light, `#60A5FA` (blue-400) dark
- Item hover background `#F1F5F9` light, one step lighter than the popover surface in dark
- Focus ring 2px `#2563EB` / `#60A5FA` with 2px offset

**Elevation**: tier 3 "Floating" — `0 4px 12px rgba(15,23,42,0.10)` light, `0 4px 12px rgba(0,0,0,0.40)` dark, 1px border, 6px radius, fully opaque. No blur, no translucency.

**Motion**: the popover appears and disappears instantly — no fade, scale or slide. Hover/focus transitions 120ms ease-out. A newly arrived item while the panel is open gets a single one-off background flash, 200ms ease-out — **only that item animates; every other row stays completely still and does not re-highlight or re-draw.** No pulsing, no looping, no ambient motion, no animated badge.

**Header**: 12px/16px padding, "Notifications" at 16px weight 600 on the left, a text button "Mark all read" on the right at 13px. "Mark all read" is present only when unread items exist. No filter chips, no tabs, no settings gear.

**Item anatomy** (reverse-chronological, newest first, 12px/16px padding, 1px separator between items, entire item is one link target):
```
● Escalation raised · ESC-4471            2m
  No feasible slot for the Kota load at Jaipur DC.

  Slot confirmed · APT-1042               18m
  Dock D1 · Tue 4 Aug · 13:00–14:15, Jaipur DC.

  Policy published · v12                   1h
  Fairness weights changed by A. Rao.
```
- **Unread is carried by three channels, never colour alone**: a 6px filled dot in the left gutter, the title at weight 600, and the item's `aria-label` beginning with "Unread". Read items have no dot and a weight-400 title.
- **Every operational time in an item carries its dock and its date** — "Dock D1 · Tue 4 Aug · 13:00–14:15", never a bare "13:00". This is a hard rule in this product: option sets span days and a bare time is a wrong-day booking. Times are 24-hour, always. Dates are "Tue 4 Aug" with the weekday included.
- Timestamps are relative and right-aligned on the title's line ("2m", "18m", "1h", "Tue").
- Each item navigates to its source record. **There are no per-item buttons** — no Confirm, no Reject, no Dismiss, no Snooze, no overflow "…" menu, no hover-revealed actions.

**Empty states — two distinct ones, both required**:
- *Caught up* (an account with history, nothing unread or recent): a 32px Lucide `circle-check-big` icon in tertiary colour, "You're all caught up.", one line "New notifications appear here automatically." No button.
- *Nothing yet* (a newly provisioned account): a 32px Lucide `inbox` icon in tertiary colour, "No notifications yet.", one line "You'll see escalations, appointment changes and policy updates here." No button.

**Loading state**: three skeleton rows shaped exactly like real items (dot, title bar, body bar, timestamp bar) — never a centred spinner.

**Behaviour**: `Escape` closes and returns focus to the bell. Arrow keys move between items. Not modal — no scrim, nothing behind it is dimmed or blocked.

**Explicitly exclude**: no tabs or segmented filter ("All / Unread / Mentions") · no category filter chips · no per-item action buttons of any kind · no swipe-to-dismiss · no per-item overflow menu · no "Load more" pagination button (the list scrolls) · no settings gear or "Notification preferences" link inside the panel · no grouping headers by date ("Today", "Yesterday") · no avatars or sender photos · no promise-state chips inside items (a notification is a historical event; a live state chip here could contradict the record it links to) · no emoji · no sound · no animated bell.
---

---

## 6 · Search palette modal

Cmd/Ctrl+K, and the top bar's centre search field. Uses the existing modal primitive at its 640px width.

---
**Copy-paste into Stitch — SetuHaul Dock Command · Search palette**

**Product context**: SetuHaul Dock Command is a B2B internal operations tool for a logistics company — shipments, dock appointments, drivers, carriers, facilities. This is the global search, opened either by clicking the top bar's centre search field or by pressing Cmd/Ctrl+K. Users are under time pressure at a desk; the palette exists to get them to one record in a few keystrokes. "Operator tool" aesthetic: dense, fast, no ornament.

**Overlay**: a modal centred horizontally, offset from the top of the viewport (roughly 15% down, not vertically centred — it should sit where the eye already is). **640px wide.** Behind it, a flat scrim `rgba(15,23,42,0.5)` in light mode and `rgba(0,0,0,0.65)` in dark. **The scrim is a flat dim — no blur, no backdrop-filter, no frosted glass anywhere in this product.**

**Elevation and shape**: tier 4 "Overlay" — light: `#FFFFFF` fill with `0 12px 32px rgba(15,23,42,0.14)`. Dark: `#1E293B` (neutral-800) fill with `0 12px 32px rgba(0,0,0,0.55)` and a 1px `#334155` border. Radius 12px. Fully opaque.

**Typography**: `Inter` only — 400/500/600/700. Query input 16px weight 400. Group headers 12px weight 600 uppercase with 0.04em letterspacing, in tertiary colour. Result primary line 14px weight 500; result secondary line 13px weight 400 in secondary colour. **All identifiers, times and dates render in `JetBrains Mono`** — `SHP1015`, `APT-1042`, `DOCK-JAI-D4`, `13:00–14:15`. Do not substitute either font.

**Color** (define light and dark):
- Surface `#FFFFFF` light, `#1E293B` dark
- Primary text `neutral-900` / `neutral-50`; secondary `#475569` / `#CBD5E1`; tertiary `#64748B` / `#94A3B8`
- Highlighted (keyboard-focused) result row background `#EFF6FF` (blue-50) light, `blue-900 @ 30%` dark, plus a 2px left edge in `#2563EB` / `#60A5FA` — the highlight is never carried by background colour alone
- Separators 1px `#E2E8F0` / `#334155`
- Focus ring 2px `#2563EB` / `#60A5FA` with 2px offset

**Motion**: the modal enters at 320ms ease-out `cubic-bezier(0.16, 1, 0.3, 1)` and exits at the same duration. Results update **instantly** as the query changes — no crossfade, no staggered row animation, no skeleton flicker for sub-second responses. No ambient motion.

**Anatomy, top to bottom**:
1. **Query row** — a 24px Lucide `search` icon at the left, then a borderless full-width input with the placeholder "Search shipments, appointments, drivers, carriers, facilities", then a small `Esc` key hint at the right. 56px tall, 16px horizontal padding. The input has no visible border or fill of its own; the modal's edge is the field's edge.
2. **Scope line** — a single 12px line directly beneath the query row, in tertiary colour, reading "Jaipur DC only". This is not a filter control and cannot be changed here; it states the scope so a user never wonders why a Gurugram shipment is missing.
3. Separator
4. **Results region** — max height 400px, scrolls internally. Results are grouped, group order fixed: **Shipments · Appointments · Drivers · Carriers · Facilities.** Each group has an uppercase header row and its results beneath. A group with no matches is absent entirely — never rendered as an empty header.

**Result row anatomy** (44px, 10px/16px padding, whole row is the target):
```
SHIPMENTS
  SHP1015   Kota load · Reefer · due Tue 4 Aug 08:45
  SHP1004   Jaipur load · Standard · due Tue 4 Aug 18:00

APPOINTMENTS
  APT-1042  Dock D1 · Tue 4 Aug · 13:00–14:15 · Jaipur DC
```
- The identifier is the first element of every row, in mono.
- **Every appointment result carries its dock, its date and its time, in that order** — never a bare time. This is a hard product rule: a missing date is a real wrong-day booking.
- Times are 24-hour. Dates are "Tue 4 Aug", weekday included. Time ranges use an en dash, not a hyphen.
- Matched substrings within a result are marked with weight 600, not with a coloured background highlight.
- No trailing action buttons, no chevrons, no per-row menus.

**Empty-query state (also the state on first open)**: the results region shows a group headed "RECENT" listing the last few searches, each row being the previous query string with a small Lucide `clock` icon. No "trending", no "suggested for you", no promoted records.

**No-results state**: a 32px Lucide `search-x` icon in tertiary colour, centred, with "No shipment matches 'RJ14'." beneath it (echo the actual query in quotes), then one line of secondary text with a concrete suggestion — "Try a shipment number, a dock code, or a driver's name. Search covers Jaipur DC only." and a single text button "Clear search".

**Loading state**: only if a query takes longer than one second — four skeleton rows shaped like result rows. Under one second, show nothing at all rather than a flash of loading.

**Keyboard**: `Cmd/Ctrl+K` opens; `Escape` closes and returns focus to the element that opened it; `↑`/`↓` move the highlight across groups (skipping headers); `Enter` opens the highlighted result. Typing never moves focus out of the input — the highlight moves, focus does not.

**Explicitly exclude**: no filter UI of any kind — no facility switcher, no date range, no type toggles, no advanced-search link · no cross-facility toggle · no result-count display ("42 results") anywhere, per group or total · no pagination or "see all results" footer link · no tabs · no AI-answer or summary block above the results · no recent-items carousel with thumbnails · no keyboard-shortcut cheat-sheet footer · no blur/frosted-glass on the scrim or the modal · no illustration in the no-results state beyond the single icon.
---

---

## 7 · Help — top-bar contact link

Deliberately the thinnest surface in this set. It exists to **protect** an existing decision: this product
has no FAQ or article library, because help arrives at the point of confusion instead. The top-bar icon is
a contact route, and nothing more.

---
**Copy-paste into Stitch — SetuHaul Dock Command · Top-bar help affordance**

**Product context**: SetuHaul Dock Command is a B2B internal operations tool for a logistics company. **This product has no help center, no documentation site, no article library, and no FAQ** — contextual explanations are attached to the specific things that confuse people, inline, elsewhere in the app. The top bar's help icon is therefore a single contact route and carries no content of its own. Do not design a help center. Do not design a knowledge-base search. Do not design an article list.

**What to render**: a 24px Lucide `circle-help` icon button in the top bar's right-hand cluster, between the notifications bell and the user-menu avatar, in a 56px-tall top bar. Accessible name "Contact support". On hover and keyboard focus it shows a small tooltip reading "Contact support".

**Behaviour**: activating it goes straight to the contact route — it does not open a menu, a popover, a panel, or a modal. There is no intermediate step and no choice to make.

**Typography**: `Inter` only, 400/500/600/700. Tooltip text 12px weight 500. Do not substitute a more distinctive font.

**Color** (light and dark): icon in `#475569` (neutral-600) light / `#CBD5E1` (neutral-300) dark at rest; `neutral-900` / `neutral-50` on hover. Hover background `#F1F5F9` light / `#1E293B` dark on a 6px-radius 32px square. Tooltip surface `#0F172A` with `neutral-50` text in light mode, `#E2E8F0` with `neutral-900` text in dark mode. Focus ring 2px `#2563EB` / `#60A5FA` with 2px offset.

**Motion**: hover and focus transitions 120ms ease-out `cubic-bezier(0.16, 1, 0.3, 1)`. Tooltip appears instantly. No ambient motion.

**Explicitly exclude**: no help center, knowledge base, or documentation page · no article list, category grid, or popular-topics section · no search field for help content · no dropdown menu of help options · no chat widget, chat bubble, or live-chat launcher · no "Getting started" or product tour · no video embeds · no feedback/NPS survey prompt · no changelog or "What's new" · no bot avatar · no notification badge on the icon.
---

---

## 8 · Account / Settings page

One route, one continuous scroll, five sections in a fixed order. Renders inside the app shell's content
region — the icon rail, top bar and status bar stay mounted and are not part of this generation.

Applies to the five internal roles (planner, operations, gate officer, carrier manager, admin). **The
driver's existing Profile screen is a separate surface and is untouched.**

---
**Copy-paste into Stitch — SetuHaul Dock Command · Account settings page**

**Product context**: SetuHaul Dock Command is a B2B internal operations tool for a logistics company, used by roughly five internal people across six facilities plus carrier partners. This is the account settings route for internal staff. It is deliberately small: identity is managed by an external auth provider and account lifecycle is managed by an admin elsewhere, so almost nothing here is editable. "Operator tool" aesthetic — calm, factual, dense-capable, zero ornament. Do not pad it out into a SaaS account centre.

**Frame**: this page renders inside an existing app shell that is NOT part of this generation — assume a 56px icon rail on the left, a 56px top bar above, and a 28px status bar below, and design only the content region between them. Content region padding 24px. The page content sits in a **single column, max width 720px, left-aligned within the region** — not centred, not a two-column form, not a card grid.

**Typography**: `Inter` only — weights 400/500/600/700. Page title 24px weight 600. Section headings 16px weight 600. Field labels 13px weight 500 in secondary colour. Values 14px weight 400. Helper text 13px weight 400 in tertiary colour. Any identifier renders in `JetBrains Mono`. Do not substitute either font.

**Color** (define light and dark):
- Page background `#F8FAFC` (neutral-50) light, `#020617` (neutral-950) dark
- Section card background `#FFFFFF` light, `#0F172A` (neutral-900) dark
- Primary text `neutral-900` / `neutral-50`; secondary `#475569` / `#CBD5E1`; tertiary `#64748B` / `#94A3B8`
- Border `#E2E8F0` / `#1E293B`
- Toggle on-state `#2563EB` (blue-600) light, `#3B82F6` dark; off-state `#CBD5E1` / `#334155`
- Focus ring 2px `#2563EB` / `#60A5FA` with 2px offset

**Density**: `comfortable` — 44px row height, 12px vertical / 16px horizontal cell padding, 16px card padding, 12px stack gap, 40px button height, 44px minimum tap target.

**Elevation and shape**: each section is a tier-1 "Raised" card — light: `#FFFFFF` fill, `0 1px 2px rgba(15,23,42,0.06)` shadow, 1px subtle border. Dark: `neutral-900` fill, **no shadow at all**, 1px border — depth in dark mode comes from the lightness step, not from shadow. Radius 8px. 24px vertical gap between sections.

**Motion**: 200ms ease-out `cubic-bezier(0.16, 1, 0.3, 1)` on toggles and state changes; 120ms on hover and focus. No entrance animation on sections, no scroll-triggered reveals, no parallax, no ambient motion.

**Page header**: title "Settings", no subtitle, no breadcrumb, no tabs.

**SECTION 1 — Personal info (read-only)**
Three label/value pairs stacked: Name, Email, Role. Beneath them one line of tertiary helper text: "These come from your SetuHaul account. Ask an admin to change them."
**Read-only means zero interactive affordance**: no input borders, no field boxes, no hover state, no focus ring, no cursor change, no "Edit" pencil, no disabled-looking greyed inputs. Render as plain labelled text.

**SECTION 2 — Notification preferences**
A small table of **categories**, not individual events. Rows: "Exception raised", "Escalation triggered", "Appointment changed", "Policy changed". Two toggle columns: **Web push** and **Email**. Column headers 12px weight 600 uppercase, tertiary colour. Each row is the category name on the left with its two toggles right-aligned under their columns; each toggle has its own accessible name combining category and channel ("Email — Escalation triggered").
Above the table, a single **"Mute everything"** toggle in its own row with a 1px separator beneath it. When it is on, the category rows below render dimmed with their toggles disabled, and one line of helper text appears: "All notifications are off. Turn this off to use the settings below."
Toggles carry state through position AND a text label ("On"/"Off") beside each — never colour alone.

**SECTION 3 — Email digest**
A two-option radio group labelled "Email delivery": "As it happens" and "Once daily digest". One line of tertiary helper text beneath: "Applies to email only. Web push is always sent as it happens." When "Mute everything" or the Email column is entirely off, this section is dimmed with the reason stated inline rather than silently doing nothing.

**SECTION 4 — Appearance**
A three-way segmented control labelled "Theme": "Light", "Dark", "System". Light is the default. The selected segment is marked by a filled background AND a weight change, never colour alone. One line of tertiary helper text: "This is saved to your account and follows you between devices."

**SECTION 5 — Your access (read-only)**
Two read-only blocks: **Role** (e.g. "Warehouse Planner") and **Facilities** (a plain vertical list of facility names, e.g. "Jaipur DC", "Gurugram Cross-Dock"). Beneath them one line of tertiary helper text: "Access is set by an admin. If this looks wrong, contact them."
Same read-only treatment as Section 1 — plain text, no chips, no boxes, no hover, no cursor change, no remove/× affordance beside a facility, and **no coloured swatch or accent beside any facility name** (facility colour is reserved for the shell's rail stripe and facility switcher and must not appear here).

**Saving**: preference changes save immediately on toggle. There is no "Save changes" button and no sticky save bar. A save failure surfaces as an inline message on the affected row reading "That didn't save — nothing has changed. [Try again]" — never a silent revert.

**Explicitly exclude — all of these were evaluated and rejected for this product**: no profile photo or avatar upload · no cover image · no "Edit profile" affordance of any kind · no password-change form (password changes go through the reset flow) · no MFA / two-factor / authenticator section · no security or login-history section · no active-sessions or device list · no linked/connected accounts · no API keys or tokens · no webhooks · no billing, plan, invoices, usage, or upgrade prompts · no team-members or invite-user section · no danger zone, no "Delete account", no "Deactivate account" · no data-export or download-my-data button · no language or timezone picker (times are always shown in the facility's local zone, by design) · no per-event notification list (categories only) · no SMS or WhatsApp notification channel · no Slack/Teams integration toggles · no marketing-email or newsletter opt-in · no left-hand settings sub-navigation or tab strip (this is one scrolling page) · no illustrations, no empty-state art, no gradient headers.
---
