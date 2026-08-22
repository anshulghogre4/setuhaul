# Planner dock board — accessibility

> Cross-references `../00-foundations/accessibility-behaviour.md` for the product-wide announcement
> politeness matrix and focus-management contract. This file covers what's specific to *this* surface —
> and this is the one surface in the product where full keyboard operation is not a nice-to-have, it's the
> entire premise of clearing a 20–35-request spike in 30 minutes.

## The actual usage context

Desk-based, Windows desktop, keyboard-first — same physical profile as `02-ops-exception-console/`, but
under real time pressure where `02-ops-exception-console/` has dwell time. `spacing-and-layout.md`'s
`compact` density and the Windows-focused `forced-colors` case (U87) both apply here for the same reason.

---

## Keyboard model

The product-wide map (`components.md` foundations §19) is written *for* this surface first — this is where
`C`/`R`/`O`/`H`/`E` actually live (U46). Restated with this surface's own additions:

| Key | Action | Scope |
|---|---|---|
| `j`/`k`/`↓`/`↑` | Move focus one row | Queue tab |
| `C`/`R`/`O`/`H`/`E` | Confirm/Reject/Counter-offer/Hold/Escalate on the focused row | Queue tab only — **not offered on the Board tab**, since a board has no single "focused row" the way a table does |
| `Tab`/`Shift+Tab` | Move between the queue's own controls (Select-all-eligible, then rows) | Queue tab |
| `Cmd/Ctrl+1` / `+2` | Switch Queue / Board tab | Global to this surface |
| `Escape` | Cancel a counter-offer pick, close the block-dock form, exit the proposal-diff overlay without applying | Global |
| `Enter` (on an eligible board interval, once reached by `Tab`) | Selects that interval for counter-offer — the board's clickable intervals are real keyboard-focusable elements, not mouse-only targets, per U25's "act via affordances" applying equally to keyboard and pointer | Board tab, picker mode |

**Single-key actions never fire while focus is inside a text input** (block-dock reason field, reject-flow
note, search) — the product-wide rule, restated because this surface's whole design leans on it working
correctly.

---

## The Gantt board's own accessibility posture

The one genuinely open item on this surface: `../00-foundations/README.md`'s U52 already flags that Kibo
UI Gantt's zoom presets and virtualisation are unverified from its docs. **Its accessible-rendering
posture (screen-reader traversal of a dense visual timeline, keyboard reachability of every interval) is
equally unverified and must be checked before implementation, not assumed.**

- **The board is not this surface's only interaction surface for its own data** — every action reachable
  by clicking a board interval (counter-offer, review a bar's detail) has a keyboard path stated above, so
  even if the rendered Gantt itself has AT gaps, no *action* is mouse-only.
- **Bars are not the sole carrier of state information** — every bar's tooltip/focus content includes the
  shipment id and state in text, so a screen-reader user reaching a bar (however that traversal works)
  gets the same fact a sighted user gets from colour + icon.
- Outage windows (§4, `components.md`) carry their reason in the same focus-reachable text, not only the
  hatched visual pattern.

---

## Forced-colors mode (U87)

Same Windows-desktop case that motivated the decision. Two things specific to this surface:

- **The board's task-bar colouring depends on the promise-state tokens, which already have the
  `CanvasText` border fallback** (`elevation-and-depth.md`, `color.md`) — bars stay distinguishable by
  border under forced-colors, same dividend `02-ops-exception-console/` gets for free.
- **The outage-window hatch pattern must not rely on colour alone either** — it already carries a text
  label (reason) per `components.md` §4, which is what survives forced-colors when the hatch fill itself
  might not render distinctly.

---

## Focus management specific to this surface

| Event | Focus goes to |
|---|---|
| Confirming/rejecting a row | The next row at the same position (general "content removed" rule, `accessibility-behaviour.md`) — never the top of the queue, matching the same rule already stated for `02-ops-exception-console/` |
| Counter-offer switches to the Board tab | The context banner's Cancel control, so a keyboard user immediately has the exit path before anything else |
| Returning from a successful counter-offer | The Queue tab's now-updated row |
| Block-dock form opens | The Dock select field (first interactive element, never a destructive button — the product-wide modal rule) |
| Proposal diff overlay opens | The overlay's own heading, matching the route-change focus/announcement pairing rule |

---

## AT testing matrix

Per `accessibility-behaviour.md`'s product-wide table: **NVDA + Chrome, NVDA + Firefox** — same pairing as
ops and admin. Test specifically:
- Every single-key action (`C`/`R`/`O`/`H`/`E`) fires correctly with NVDA's own browse-mode active, since
  single-letter shortcuts are exactly the kind of binding that can collide with a screen reader's own
  navigation keys.
- The Gantt board's actual screen-reader traversal path, once Kibo Gantt's real behaviour is known — this
  is the one item on this surface genuinely blocked on implementation-time verification, stated plainly
  rather than assumed clean.
