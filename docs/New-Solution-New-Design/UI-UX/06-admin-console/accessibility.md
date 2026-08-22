# Admin console — accessibility

> Desk-based, Windows-primary, `comfortable` density — the same general profile as carrier portal and
> driver chat, not a hostile physical context. Cross-references `../00-foundations/accessibility-behaviour.md`
> rather than restating. The one thing this surface adds that no other does: **the highest-consequence
> destructive actions in the whole product** (remove user, publish a policy affecting every future ranking
> decision, enable the fairness term) live here, so focus/confirmation discipline matters more than on any
> read-only or routine-action surface.

## The actual usage context

Office desk use, low time pressure relative to ops/planner — an admin task is deliberate, not reactive.
This affects the accessibility priorities: correctness and confirmability of a rare, high-stakes action
matter more here than speed, which is the opposite emphasis from the planner console's 30-second budget.

---

## High-tier confirmation and keyboard/AT reachability

- **Typed confirmation (Remove user, Danger-zone fairness toggle, destructive rule edits) must be fully
  operable by keyboard and correctly announced** — this is the one place in the product where getting the
  confirmation UX wrong has the highest cost, since these are exactly the actions U41's "no confirmation
  modal" philosophy deliberately does *not* apply to. The typed-text field receives focus automatically
  when the confirmation surface opens (`components.md` foundations §10's modal rule: first interactive
  element, never the destructive button itself).
- **The confirm button stays genuinely disabled (not just visually muted) until the typed value matches** —
  a screen-reader user must be told the button is unavailable and why ("Type the user's email to confirm"),
  not discover it only by a failed activation attempt.
- **Announcement is `assertive` on both open and on successful commit** — matching
  `accessibility-behaviour.md`'s "unsuccessful actions" tier extended here to *successful* high-consequence
  ones too, since a policy publish or a user removal is exactly the kind of change an admin needs
  confirmed happened, not just assumed from a toast that could be missed.

---

## Policy editor specifics

- **Every numeric weight field has a visible label and unit**, never a bare number — `tabular-nums`
  (`typography.md`) keeps columns of coefficients aligned for a sighted user scanning them, and a screen
  reader announces the label + unit together ("Lateness weight, per minute, 4") rather than a bare "4" with
  no context.
- **The simulation result's aggregate count is the first thing announced** when the result renders
  (`polite`, matching the general pattern for a completed async result) — "12 of 340 decisions would flip"
  before any individual case detail, so a screen-reader user gets the headline first, consistent with how
  it's visually prioritised (`components.md` §5).
- **Stale-simulation state is announced, not just visually banner'd** — a screen-reader user who tabs
  straight to Publish after changing a field must still learn it's disabled and why.

---

## Facility rule editor specifics

- **The type-specific field set change (`components.md` §2) is itself an announced event** — selecting a
  new `rule_type` and having the form's fields change under a screen-reader user without any signal would
  be genuinely disorienting; announce "Fields updated for [rule type]" `polite`, matching the general
  content-added pattern.

---

## Audit log specifics

- **Table follows the same keyboard/roving-tabindex model as every other dense table in the product**
  (`components.md` foundations §19) — `j`/`k`/arrows move focus, though this surface has no single-key
  action bindings (`C`/`R`/`O`/`H`/`E` are planner-specific, U46), since nothing on an audit-log row is
  actionable beyond reading it.
- **Export's disabled-when-empty state carries a reason** (`edge-cases.md` #5), same Inactive/Disabled
  discipline as everywhere else in the product.

---

## AT testing matrix

Per `accessibility-behaviour.md`'s product-wide table: **NVDA + Chrome, NVDA + Firefox** — same desktop
pairing as planner/ops. Test specifically: the typed-confirmation flow end-to-end with a screen reader
active (focus lands correctly, the disabled state announces, successful commit is assertively confirmed) —
this is the surface's one genuinely novel interaction pattern relative to everything built so far, and the
one most worth a dedicated AT pass before implementation.
