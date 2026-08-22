# Carrier portal — accessibility

> The least physically demanding surface in the product — desktop-primary, `comfortable` density, no time
> pressure, no gloves/glare context. Cross-references `../00-foundations/accessibility-behaviour.md` rather
> than restating. Fewer surface-specific rules than any other file in this set, which is itself a fact
> about this surface's simplicity, not a shortcut taken.

## The actual usage context

Office or desk use, ordinary desktop/laptop conditions — a carrier's dispatcher or fleet manager checking
status, not an operator under a decision clock. `spacing-and-layout.md`'s `comfortable` density is the
same value driver-chat and admin console use.

---

## Read-only surface, read-only implications

- **`components.md` §18's Read-only contract governs almost the entire surface**: no hover state, no
  accent colour, no cursor change on anything the carrier cannot act on. The one true interactive class is
  navigation (shipment rows, the exception rows, the filter control) — and only those get focus rings,
  hover states, and cursor changes. A screen-reader or keyboard user should never encounter a control that
  announces itself as interactive but does nothing.
- **The single-key action map does not apply here** (`components.md` foundations §19) — this surface has
  no dense queue under a decision budget, so no product-wide keyboard shortcuts are bound. Standard
  `Tab`/`Shift+Tab`/`Enter` navigation through rows and controls is sufficient and expected.

---

## Focus management

| Event | Focus goes to |
|---|---|
| Opening Shipment detail | The screen's own heading (route-change rule, `accessibility-behaviour.md`) |
| Returning to the dashboard | The shipment row that was open — not the top of the list, matching the same "don't lose your place" principle every other surface's queue already follows |
| Filtering the shipment list | Stays on the filter control — results update without moving focus, the product-wide rule |

---

## Announcements

Nothing on this surface has a live-updating region (Flow 5's own decision) — the announcement politeness
matrix's entries for live regions largely don't apply here. The two that do, unchanged from the product-wide
table: **route changes** (assertive, on the new view's heading) and **unsuccessful actions** (a failed
`get_shipment_detail` call, assertive) — both already covered generically in
`accessibility-behaviour.md`, restated here only to confirm they weren't overlooked for a surface that
otherwise has so little dynamic behaviour to announce.

---

## Contrast and type

Standard AA baseline — this surface has no field-condition justification for the AAA overlays driver/gate
carry, and none is claimed. `color.md`'s ordinary computed contrast tables apply as-is. Promise-state chips
render with their full four-channel redundancy (hue, icon, border style, text) exactly as everywhere else
— consistency with the rest of the product matters more here than any surface-specific adjustment would.

---

## AT testing matrix

Per `accessibility-behaviour.md`'s product-wide table: not explicitly listed there for this surface (only
planner/ops/admin, carrier-portal, and driver/gate are named) — inherited as the same desktop pairing
planner/ops/admin use, **NVDA + Chrome, NVDA + Firefox**, since this is a desktop-primary business
surface with the same general assistive-technology profile.
