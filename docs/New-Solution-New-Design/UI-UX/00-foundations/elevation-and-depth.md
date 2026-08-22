# Elevation and depth

> Decisions follow `../README.md` U7 (light/dark parity), U8 (density), U39 (shell).

## The principle

**Light mode conveys depth with shadow. Dark mode conveys it with lightness.** These are not the same
system with different values — shadow is nearly invisible on a dark ground, and a design that relies on it
produces a flat, undifferentiated dark theme where every panel merges.

So each theme gets its own mechanism, expressed through the same tokens.

---

## The layer model

Five levels. Nothing in this product needs more.

| Level | Purpose | Light | Dark |
|---|---|---|---|
| **0 — Base** | App background | `neutral-50`, no shadow | `neutral-950`, no shadow |
| **1 — Raised** | Cards, panels, table container | `neutral-0` + `shadow-sm` + `border-subtle` | `neutral-900`, no shadow, `border-subtle` |
| **2 — Shell** | Icon rail, top bar, status bar | `neutral-0` + `border-default` on the content-facing edge | `neutral-900` + `border-default` |
| **3 — Floating** | Dropdowns, popovers, expanded rail, tooltips | `neutral-0` + `shadow-md` + `border-subtle` | `neutral-800` + `shadow-md` + `border-default` |
| **4 — Overlay** | Modals, drawers | `neutral-0` + `shadow-lg` | `neutral-800` + `shadow-lg` + `border-default` |

Note dark mode's raised level (1) uses **no shadow at all** — separation comes entirely from the
`neutral-950 → neutral-900` lightness step plus a subtle border. Adding shadow there produces muddy
edges, not depth.

---

## Shadow tokens

```
                LIGHT                                          DARK
shadow-sm       0 1px 2px rgba(15,23,42,0.06)                  none
shadow-md       0 4px 12px rgba(15,23,42,0.10)                 0 4px 12px rgba(0,0,0,0.40)
shadow-lg       0 12px 32px rgba(15,23,42,0.14)                0 12px 32px rgba(0,0,0,0.55)
shadow-focus    0 0 0 2px var(--surface-base),
                0 0 0 4px var(--border-focus)                  same
```

Shadows are **cool-tinted** in light mode (`15,23,42` is `neutral-900`), not neutral black. A pure-black
shadow against a slate-tinted surface reads as dirty; matching the shadow to the neutral ramp keeps it
clean.

Dark mode shadows are pure black at high opacity, since the ground is already dark and any tint is lost.

### The focus ring is two rings

`shadow-focus` renders a 2px ring in the surface colour, then a 2px ring in the focus colour. The inner
ring creates separation so the focus indicator stays visible even when the focused element sits directly
against another coloured element — a table row against a selected row, for instance. Planners navigate the
queue entirely by keyboard (U46), so focus must never be ambiguous.

---

## Borders

Borders do more work here than shadow, especially in dark mode.

```
border-hairline   1px    Table row separators, subtle divisions
border-default    1px    Cards, inputs, panels
border-emphasis   2px    Promise-state chips, focused elements, selected rows
border-marker     3px    Priority left-edge marker (color.md)
border-accent     4px    Facility accent stripe (U40)
```

**2px is reserved for meaning, not decoration.** If something has a 2px border it is either focused,
selected, or carrying promise state. This keeps border weight readable as a signal.

### Promise-state borders carry permanence

From `color.md`, restated because it is an elevation concern too:

| State | Border |
|---|---|
| `SHOWN` | 1px solid neutral — no elevation, nothing reserved |
| `HELD` | **2px dashed** — temporary |
| `PENDING_CONFIRMATION` | 2px solid |
| `CONFIRMED` | 2px solid |

Dashed vs solid survives greyscale, colour blindness and glare. It is the encoding that does not depend on
the display.

### Forced-colors fallback (U87)

`forced-colors: active` (Windows High Contrast) strips every `box-shadow` in the system, which means
**Level 1's entire light-theme elevation model — the only thing separating a raised card from the base
behind it — disappears** under this mode, on the two surfaces (planner, admin) most likely to run on
Windows desktops.

**The fix is `border: 1px solid CanvasText` as a `forced-colors` media-query fallback on every Level 1+
surface**, using the CSS forced-colors system colour keyword rather than any of our own tokens (our tokens
are exactly what the OS is overriding). This restores *separation* — a raised panel has a visible edge —
even though it can no longer restore relative *depth*, since forced-colors mode has no shadow-based
"higher/lower" concept to offer. That's an acceptable loss: knowing where a panel ends and the next begins
is what a planner actually needs to operate the console; which one is notionally "above" the other is not.

The dock board's sequencer-proposal offset (below) is the one place this matters beyond simple panel
separation — under forced-colors it degrades to the border-only outline it already uses for `dashed`, so
the proposal-vs-current distinction survives on border style alone, exactly as it does for colour-blind
users.

---

## No glassmorphism

Blur and translucency are excluded from this system. Three reasons:

1. **`backdrop-filter` is expensive** on the low-end Android the driver surface targets.
2. **Translucent surfaces destroy contrast guarantees.** Text on a blurred background has a contrast ratio
   that depends on what happens to be behind it — unverifiable, and unacceptable when the text says
   whether a slot is confirmed.
3. It reads as consumer-premium, which is the wrong signal for capacity commitments.

Modal scrims are a flat `rgba(15,23,42,0.5)` in light and `rgba(0,0,0,0.65)` in dark — dimming, not
blurring.

---

## Depth in the dock board

The Gantt is the one place where depth encodes data rather than hierarchy:

| Element | Treatment |
|---|---|
| Dock lane background | Level 0 |
| Occupancy interval (`CONFIRMED`) | Level 1, solid border, full opacity |
| Occupancy interval (`PENDING`) | Level 1, solid border, 85% opacity |
| Hold (`HELD`) | Level 1, **dashed** border, 70% opacity |
| Dock outage window | **No elevation** — a diagonal hatch pattern directly on the lane |
| Sequencer proposal (unapplied) | Level 3, dashed, offset 2px above the current interval |

Outages use pattern rather than elevation because they are an *absence* of capacity — raising them would
imply something is booked there. A hatch says "this space is unavailable" without implying occupancy.

The sequencer proposal floating at Level 3 above the current state is the visual expression of D5: it
proposes, a planner applies. It is literally not yet part of the schedule, and it should look that way.
