# Spacing and layout

> Structure follows Checklist Design's *Spacing / Grid* checklist. Decisions follow `../README.md` U8, U20, U39, U43.

## Base unit

**4px.** Every spacing, sizing and radius value is a multiple. Nothing is arbitrary.

```
space-0    0px      space-4    16px     space-10   40px
space-1    4px      space-5    20px     space-12   48px
space-2    8px      space-6    24px     space-16   64px
space-3    12px     space-8    32px     space-20   80px
```

`space-2` (8px) and `space-4` (16px) do most of the work. `space-6` (24px) separates sections. Values
above `space-8` are rare outside empty states and login.

---

## Density scale — one system, three calibrations

U8: the same components at three densities rather than three design languages. Density changes **padding
and row height only** — never type size, never border width, never icon size.

| | `compact` | `comfortable` | `spacious` |
|---|---|---|---|
| **Used by** | Planner, ops console | Carrier, admin, driver chat | Gate kiosk |
| **Row height** | 36px | 44px | 64px |
| **Cell padding (y/x)** | 8px / 12px | 12px / 16px | 20px / 24px |
| **Card padding** | 12px | 16px | 24px |
| **Stack gap** | 8px | 12px | 16px |
| **Min tap target** | 32px¹ | 44px | 56px |
| **Button height** | 32px | 40px² | 56px |

¹ **The one exception to the 44px rule, and it is deliberate.** `compact` is desktop-and-pointer only,
where 32px is comfortable for a mouse. It is never used on a touch surface. Every touch context —
driver, gate, and any tablet use of the consoles — runs `comfortable` or `spacious`, where the 44×44px
target holds without exception.

² **The 40px button and the 44px floor are both correct, and they are not in conflict — resolved
2026-09-01, issue #91.** This table used to assert `comfortable` button height 40px and `comfortable`
minimum tap target 44px with no explanation of how a 40px button meets a 44px floor. It could not,
and the code faithfully implemented both numbers, which is why every audit of admin, carrier and
driver kept reporting the same "×40" miss. Neither number moves. **The floor is met by an invisible
hit region, not by a taller button.**

WCAG defines a target as the "**region of the display that will accept a pointer action**, such as
the interactive area of a user interface component"
([Understanding SC 2.5.5](https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html)) —
the pointer-reachable region, not the visible rendering. So a transparent `::after` centred on a
control, sized `max(100%, var(--tap))`, makes the *target* meet the density's own floor while the
drawn box stays exactly as this table specifies. That is the shipped mechanism: the `tap-floor`
utility in `frontend/src/styles/theme.css`, applied to `shared/ui/button.tsx` (all four size
variants), the shell's top-bar and rail controls, and the ops console's `text-micro` text buttons.
It follows `--tap` rather than a literal 44, so it is 32px on the compact consoles (footnote 1's
deliberate exception is preserved, not overridden), 44 on comfortable, 56 on the kiosk; and
`max(100%, …)` means it can only grow a control, never crop one that already exceeds its floor.

The pattern was already proven here before it was generalised: the settings Appearance switch
(`features/settings/settings-page.tsx`) expands a 36×20 visible track to a 44×60 region the same
way. **Verify it with `elementFromPoint` and a real click landing outside the visible box** —
`getBoundingClientRect` returns the drawn rectangle and structurally cannot see this. Measured
2026-09-01 (Playwright 1.62.1, Chromium): comfortable `Button` 103.8×40 drawn → **103.8×45** target;
rail item 40×40 → **46×45**; top-bar help 32×32 → **45×45**; global search 420×40 → **421×45**; ops
`text-micro` buttons 42.6×**14.3** → 43.6×**33.3** against their compact 32px floor. Each was
confirmed by a real mouse click landing below the visible bottom edge and activating the control,
and the compact rail item — already 40px against a 32px floor — correctly did **not** expand.

One honest limit: the top bar's notification bell sits 4px from the help control, so their expanded
regions overlap and the later one wins the shared band. The bell's own reachable region is therefore
**39×45**, not 44×45. Both still own their own centres, both are far above SC 2.5.8's 24×24 AA floor,
and both are larger than the 32×32 they were. Closing that last 5px would mean widening the gap,
i.e. a visual change, which this fix was scoped to avoid.

**Be precise about what the standard actually requires.** WCAG 2.2 **SC 2.5.8 Target Size (Minimum) is
24×24px and is Level AA**. The **44×44px** figure used here is **SC 2.5.5 Target Size (Enhanced), which is
Level AAA**. We exceed AA on the field surfaces deliberately — gloved hands on a tablet and one-handed use
at a roadside justify it — but it is a self-imposed bar, not a conformance requirement. It is recorded
this way so that a later "we only need AA" review does not shrink the kiosk to 24px believing it still
meets our stated standard. `compact`'s 32px still clears the actual AA minimum comfortably.

### Auth and full-page states — the group the table above missed (added 2026-08-26)

The three densities are assigned to *operational surfaces*. **Sign-in, the role picker, both password-reset
screens, and the five states that replace a whole content region (404, error boundary, maintenance,
out-of-scope, idle warning) belong to none of them** — they render before a surface is chosen, or instead of
one. Found during the M5/E5.0 pass, where the shared-shell mockup had settled on 44px controls without a
density row to justify them.

**Resolution: this group runs `comfortable`, with one stated override — controls are 44px, not 40px.**

| | Value | Why it differs |
|---|---|---|
| Input height | 44px | — |
| **Button height** | **44px** (not `comfortable`'s 40px) | These screens are the *driver's* entry point as well as a desk user's. A driver signs in one-handed at a roadside, so the field 44×44 bar applies to the door even though it does not apply to the planner console behind it. |
| Everything else | Per `comfortable` | Card padding 16px, stack gap 12px, min tap target 44px |

`Source: assumption, untested.` The 44px figure is `spacing-and-layout.md`'s own field bar applied to a
new context, not a measured result — it is recorded as an assumption so a later review can challenge it
without having to reverse-engineer where it came from.

**Density is a surface-level setting, not a user preference toggle** in v1. A planner cannot switch their
queue to spacious. If that becomes a request, it is a preference on top of the surface default, not a
replacement for it.

---

## Radius

```
radius-sm    4px     Chips, badges, small inputs
radius-md    6px     Buttons, inputs, table row hover
radius-lg    8px     Cards, panels, option cards
radius-xl    12px    Modals, drawers
radius-full  9999px  Avatars, count badges, toggle switches
```

Restrained on purpose. Heavy rounding reads as consumer software and costs perceived precision, which is
the wrong signal for a system making capacity commitments. Nothing in the operational surfaces exceeds
`radius-lg`.

**Toggle switches added to `radius-full` 2026-08-22** — found missing during the mockup gate pass
(`components.md` §12's toggle control is pill-shaped by convention, and had no permitted radius to reach
for). A switch is a binary physical-analogue control, the same category as an avatar or a count badge
in the sense that a fully-rounded shape is the control's identity rather than a decoration — it does not
open the door `radius-lg`'s restraint exists to hold shut for cards, panels, or option cards.

---

## App shell (U39, U43)

```
┌──┬──────────────────────────────────────────────────────────────┐
│  │  TOP BAR                                              56px   │
│  ├──────────────────────────────────────────────────────────────┤
│IR│                                                              │
│56│  CONTENT                                                     │
│px│                                                              │
│  │                                                              │
│  ├──────────────────────────────────────────────────────────────┤
│  │  STATUS BAR                                           28px   │
└──┴──────────────────────────────────────────────────────────────┘
   ▲
   └─ 4px facility accent stripe on the rail's outer edge (U40)
```

The stripe's colour comes from `color.md`'s **Facility accent** section (U59) — six hues drawn from
outside the four semantic colours, safe to use here precisely because this stripe and the facility
switcher swatch are the *only* two places that palette is permitted to appear.

| Region | Size | Contents |
|---|---|---|
| **Icon rail** | 56px fixed, expands to 240px overlay on hover/focus | Role-scoped destinations, icon + tooltip — **enumerated in `iconography.md` §Rail destinations** (added 2026-08-26; derived from `SOLUTION_DESIGN.md` §2 × §7.5.*, per U101). Active item marked by a 2px inner accent bar, not a fill — it must clear the 4px facility stripe. **A rail destination is a *surface*, and this product has one surface per role** (criterion in `components.md` §7), so all five internal roles have exactly one destination; the driver has no rail at all. |
| **Top bar** | 56px | Facility switcher (left) · global search (centre) · notifications, help, user menu (right) |
| **Status bar** | 28px | Connection state · last sync · active facility · pending count · policy version |
| **Content** | fills | Per-surface |

The rail **expands as an overlay**, not by pushing content. A planner hovering the rail must not cause the
queue to reflow — reflow under the cursor is the same class of error as U19's re-sorting under the click.

### Content padding

| Density | Padding |
|---|---|
| `compact` | 16px |
| `comfortable` | 24px |
| `spacious` | 32px |

---

## Grid

**12 columns, 16px gutters** for content areas that need one — carrier portal, admin console, empty
states. Operational surfaces (planner queue, dock board, gate kiosk) are **not** grid-driven; their layout
is dictated by data, and forcing a 12-column grid onto a Gantt chart produces worse results than laying it
out directly.

State plainly which surfaces use the grid rather than claiming a universal system that half the product
ignores.

---

## Breakpoints (U20)

Shared token scale; each surface declares the range it actually supports.

```
bp-sm    640px
bp-md    768px
bp-lg    1024px
bp-xl    1280px
bp-2xl   1536px
```

| Surface | Supported range | Primary target | Below range |
|---|---|---|---|
| **Driver chat** | 320–768px | 390×844 phone | Scales up to 768px, capped content width 640px |
| **Gate kiosk** | 1024–1366px, landscape locked | 1280×800 tablet | Not supported — shows an orientation prompt |
| **Planner / ops** | 1280px+ | 1600×900 | 1024–1280px degrades to a reduced column set; below 1024px shows "use a larger screen" |
| **Carrier portal** | 768px+ | 1280×800 | Responsive down to 768px |
| **Admin console** | 1024px+ | 1440×900 | Below 1024px, tables scroll horizontally |

**The planner console honestly does not work on a phone.** Seven fields, keyboard operation and a 30-second
decision budget do not survive 390px. Rather than shipping a degraded version that invites confirming
decisions with insufficient information, it states the requirement. A planner who needs to triage from a
phone is a real need — and the right answer is a purpose-built mobile triage view later, not a squeezed
table now.

---

## Table layout rules

The planner queue is the hardest layout in the product (§7.3). Rules that make it work:

- **Sticky header**, always. A planner 30 rows deep must still know which column is which.
- **Fixed first column** (shipment identity) when horizontal scrolling occurs, so a scrolled row never
  becomes anonymous.
- **Column widths are fixed, not auto.** Auto-width causes reflow as data changes, and reflow under a live
  queue is the U19 problem again.
- **Text truncates with ellipsis; the displacement warning never truncates.** If it does not fit, the
  column grows. §7.3 calls it the single most important field, so it does not get to be the one that is cut.
- **Row expansion pushes rows down** (U44), never overlays them.

---

## Z-index scale

```
z-base          0     Content
z-sticky       100    Sticky table headers
z-shell        200    Icon rail, top bar, status bar
z-rail-expand  300    Expanded rail overlay
z-dropdown     400    Menus, comboboxes, facility switcher
z-drawer       500    Side drawers
z-modal        600    Modal dialogs
z-toast        700    Toasts — above modals, so an undo is never hidden
z-tooltip      800    Tooltips
```

**Toasts sit above modals deliberately.** The undo toast (U41) must be reachable even if something else
has opened, since undo is time-boxed and a hidden undo is no undo.

---

## Safe areas and field conditions

- Driver PWA respects `env(safe-area-inset-*)`; the composer sits above the home indicator.
- Gate kiosk assumes no notch but does assume a case — 24px minimum edge padding so a bezel or grip
  does not obscure a control.
- **Nothing interactive within 16px of a viewport edge** on touch surfaces. Edge-adjacent targets are hard
  to hit accurately with gloves and easy to trigger accidentally with a palm.
