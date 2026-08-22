# Gate/yard kiosk — accessibility

> The most physically hostile context in the product — outdoors, gloves, direct sunlight, one-handed
> operation, unreliable connectivity. `spacing-and-layout.md`'s `spacious` density (64px rows, 56×56px
> minimum tap target) exists primarily for this surface. Cross-references
> `../00-foundations/accessibility-behaviour.md` rather than restating.
>
> **Two things checked and found unavailable this session, stated plainly rather than silently skipped**:
> no `checklist-design` checklist matches this surface's shape (nothing in the 122-item index covers a
> single-purpose field kiosk); `ui-ux-pro-max` — cited in the existing decisions log (U37) as governing
> this surface's touch-target/contrast rules specifically — is not present in the current session's skill
> list. Neither absence is treated as "therefore skip the concern" — the rules below are derived directly
> from the foundations that do exist (`color.md`'s field-condition contrast section, `spacing-and-layout.md`'s
> density table) instead.

## The actual usage context

Outdoor, any time of day including direct midday sun. Officers wear work gloves, operate the device
one-handed (the other hand often occupied — a clipboard, a truck door, waving a driver forward). Yard
tablets move between varying light conditions across a single shift; gate-booth kiosks may sit behind
glass with its own glare characteristics. Connectivity is facility Wi-Fi or cellular at the edge of
coverage, not a controlled office network.

---

## Touch targets

- **56×56px minimum on every interactive element** — `spacing-and-layout.md`'s `spacious` density value,
  the largest in the system, used because this is the one surface where the standard 44px AAA overlay
  itself isn't generous enough given gloves specifically (driver/PWA's 44px target assumes a bare
  fingertip; a gloved fingertip's effective contact area is measurably larger).
- **The one-dominant-button pattern (U110) is itself an accessibility decision, not just an interaction
  one** — a single 56px+ full-width target is unambiguously reachable one-handed; a row of smaller buttons
  would fail both the size requirement and the one-handed-reach requirement simultaneously.
- **Spacing between any two adjacent interactive elements is generous enough that a gloved mis-tap lands on
  nothing, not on the wrong control** — most screens on this surface have exactly one primary target
  precisely to make this a non-issue by construction.

---

## Contrast under glare

- **`color.md`'s field-condition contrast section** (already computed for driver/PWA) applies identically
  here — sunlight-tested contrast ratios, not just the AA baseline. This surface shares the exact
  usage-context justification driver chat has for exceeding AA.
- **Colour is never the sole carrier of meaning** (product-wide rule, doubly load-bearing here): every
  `queue_state` icon (`iconography.md`) pairs with a text label; the `DOCK_MISMATCH`/overrun
  `feedback-warning` banners (`components.md` §5) carry their meaning in the headline text, not the tint
  alone — a washed-out screen under direct sun must still be legible from text and icon shape.
- **Outcome banners use large, high-contrast headline text** (`typography.md`'s upper scale steps, not the
  dense `text-sm`/`text-label` values used on desk-based consoles) — this surface's type scale skews larger
  throughout, consistent with `spacious` density's own logic.

---

## One-handed / gloved operation

- **No drag, no swipe, no multi-touch gesture anywhere on this surface** — every interaction is a single
  tap on a large target, consistent with U25's product-wide "no free dragging" rule applied at its most
  literal here.
- **Text entry is minimized to exactly one field** (search, `components.md` §2) — every other interaction
  on the surface is tap-only. The shift-identity name field (§1) is the only other text input, entered once
  per shift, not per truck.
- **No hover-dependent affordance anywhere** — a touch device has no hover state, and this surface's
  earlier-established rule (mirroring the ops/planner correction) applies equally here even though it was
  never at risk on a touch-first surface: nothing here should have relied on hover in the first place.

---

## Offline / low-connectivity behaviour

Cross-references `edge-cases.md` #7 for the mechanics (Inactive primary action, idempotent retry copy).
Stated here as the accessibility-relevant framing: a gate officer who can't tell *why* the button won't
respond is functionally locked out just as much as one who can't read the screen — the Inactive state's
mandatory reason text (`components.md` foundations §18) is not optional politeness here, it's the
difference between a usable degraded state and a dead one.

---

## AT testing matrix

Per `accessibility-behaviour.md`'s product-wide table: **not a primary AT target** — device-bound,
single-purpose, shared-kiosk hardware, matching the existing entry already written there for this surface.
**Must not actively break if a device-level screen reader is enabled** — a real possibility on a shared
tablet outside this product's control, restated here as a live requirement rather than a hypothetical:
every outcome banner and state label must remain readable by a generic screen reader even though none of
this surface's design was built around one, since "not the primary target" is not the same as "assumed
never present."
