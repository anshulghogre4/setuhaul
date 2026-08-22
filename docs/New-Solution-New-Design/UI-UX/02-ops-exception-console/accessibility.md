# Ops exception console — accessibility

> Cross-references `../00-foundations/accessibility-behaviour.md` for the product-wide announcement
> politeness matrix and focus-management contract — this file covers only what's specific to *this*
> surface's physical and interaction context. It does not restate the matrix; it adds rows where this
> surface has events the matrix doesn't already cover, and states the keyboard model for its unique
> three-pane layout.

## The actual usage context

Desk-based, Windows desktop, keyboard-driven, long dwell per item — the opposite ergonomic profile from
`01-driver-chat/`'s roadside phone use. A coordinator may spend minutes on a single hard escalation, then
work a queue of a dozen more across a shift. This is `spacing-and-layout.md`'s desktop-primary breakpoint
and `00-foundations/color.md` §*Forced-colors mode* (U87)'s primary case — Windows High Contrast is a real,
not theoretical, condition on this surface.

---

## Three-pane keyboard model

Extends the product-wide keyboard map (`components.md` foundations §19) with this surface's pane-traversal
layer, since no other surface has three simultaneously-live regions to move between.

| Key | Action |
|---|---|
| `Cmd/Ctrl+1` / `+2` / `+3` | Jump focus directly to queue pane / detail pane / co-pilot pane |
| `Tab` / `Shift+Tab` | Moves within the currently-focused pane's own interactive elements, in the pane's DOM order — never jumps panes on its own |
| `j` / `k` / `↓` / `↑` | Move focus one row, inside the queue pane only (per the product-wide map) |
| `Enter` | On a queue row: opens it in the detail pane (does **not** trigger takeover — a separate, deliberate act per U94) |
| `C` / `R` / `O` / `H` / `E` | **Not offered on this surface.** Those single-key actions are the planner's five affordances (§7.3) and do not exist here — an ops coordinator's actions (Acknowledge, Take over, Resolve, Cancel) are deliberately not bound to the same letters to avoid a coordinator who also works the planner console developing a muscle-memory collision |
| `Escape` | Collapses an expanded incident row, or exits the composer without sending (product-wide rule) |

**Safer-action-first DOM order** (`components.md` foundations §1, U79) applies to the detail pane's action
row: Resolve/Cancel/Reassign precede any takeover-adjacent action in tab order where both are present,
consistent with the product-wide rule that destructive-adjacent controls should not be the first stop for
a keyboard user tabbing through quickly.

---

## Focus management specific to this surface

The general contract lives in `accessibility-behaviour.md`; these are this surface's own applications of
it, not new rules.

| Event | Focus goes to |
|---|---|
| Selecting a queue row | The detail pane's primary heading (matches the general "content added" rule's route-change variant — this is effectively a view change even though the URL doesn't move) |
| Taking over a thread | The composer, since that's the newly-available interactive surface the coordinator almost certainly wants next |
| Hand-back completes | The detail pane's stepper/status area — not the composer, since it just became non-interactive again |
| A co-pilot draft is Approved | The composer, at the end of the inserted text — the coordinator's very next likely action is editing or sending it |
| An escalation is Resolved or Cancelled | The next escalation in the queue at the same position (the general "content removed" rule, `accessibility-behaviour.md`) — never the top of the queue, so a coordinator working down a list doesn't lose their place |

---

## Announcement additions to the politeness matrix

Everything else this surface does is already covered by the existing matrix (route changes, write
failures, toast content). Two events are specific enough to this surface to need their own row:

| Region | Politeness | What's announced |
|---|---|---|
| Co-pilot action completes (summarise / fetch-context / draft) | `polite` | "Summary ready" / "Context loaded" / "Draft ready" — the result itself is read on request (screen reader navigates into the panel), not pushed in full |
| Takeover / hand-back divider posts | `assertive` | "You joined the thread" / "You handed the thread back" — mirrors the existing "unsuccessful actions" tier's urgency, because a coordinator who doesn't register they've taken over may not realise the composer just became live |

---

## Forced-colors mode (U87)

This surface is the case that motivated the decision in `color.md`/`elevation-and-depth.md` — Windows
desktop, box-shadow-based elevation model, three visually stacked panes.

- The three panes' separation currently relies on elevation (`elevation-and-depth.md`'s layer model) —
  under `forced-colors: active`, box-shadow is stripped, so pane boundaries fall back to the `CanvasText`
  border already specified there. Verify visually that queue/detail/co-pilot remain distinguishable as
  regions by border alone, not by the elevation shadow.
- The escalation-sla-breach red and escalation-sla-warning amber (`color.md`) both survive forced-colors
  mode for free, per the product-wide rule that danger colour is never the sole carrier of meaning — the
  SLA line's *text* ("4:12 to breach") carries the fact independent of colour.
- Facility accent (rail stripe) is decorative-only under U91's neutral-by-default posture on this surface
  in the common "All facilities" case — nothing operationally depends on the stripe rendering, so its loss
  under forced-colors is a non-issue here specifically (unlike a surface that leaned on it more).

---

## AT testing matrix

Per `accessibility-behaviour.md`'s product-wide table: **NVDA + Chrome, NVDA + Firefox** — same pairing as
planner and admin, Windows desktop. Test specifically:
- Pane-jump shortcuts (`Cmd/Ctrl+1/2/3`) don't collide with NVDA's own browse-mode key bindings.
- The co-pilot's Inactive-state explanation is reachable and announced before a screen-reader user tries to
  interact with a control that only explains itself on activation (`components.md` foundations §18's
  Inactive contract).
- The takeover divider's `assertive` announcement doesn't double-fire when both the divider element and the
  composer's enabled-state change land in the same render pass.
