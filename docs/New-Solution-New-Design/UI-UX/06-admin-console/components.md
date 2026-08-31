# Admin console — components

> Surface-specific only. Shared components (form controls, data table conventions, unavailability
> taxonomy, the 3-tier destructive-action model) are specified once in `../00-foundations/components.md`
> and cross-referenced, not restated.

## 1. User row + invite/edit form

### Anatomy
Table row: name, email, role, scope (facility/carrier/driver names, comma-joined), status, overflow menu
(⋯) with Deactivate/Reactivate/Remove. Form: email, role select, scope select (shape depends on role).

### States
Row: active · inactive (dimmed status text, not the whole row — the row itself stays fully legible, only
the status column signals it) · pending invitation (distinct badge, Resend/Revoke instead of the overflow
menu). Form: idle → validating (email format, scope required for the selected role) → submitting →
success (returns to the list, new/updated row flashes once per the motion-budget rule) → error (named
cause — e.g. "This email already has an account").

### Rules
- **Scope field type follows role, not a generic multi-select for everything.** Ops/planner/gate roles
  pick one or more facilities; carrier-manager picks exactly one carrier; admin roles need no scope at all
  (scope-derived-from-identity, M15, doesn't apply to the role that assigns scope to everyone else). The
  form's scope control swaps shape when the role selection changes, rather than presenting an always-generic
  picker the admin has to interpret correctly for each role.
- **Remove requires typed confirmation** (`components.md` §19, High tier) — the admin types the user's
  email before the button enables. Deactivate/Reactivate do not — Moderate tier, immediate, reversible.
- **A deactivated user's existing sessions are not this component's concern** — session invalidation is a
  backend/security mechanism, not a UI state; this component only reflects and sets the account's active
  flag.

---

## 2. Facility rule row + editor

### Anatomy
Table row: facility, `rule_type` (from the registry, `iconography.md`-paired if a suitable icon exists),
value (type-specific rendering — a weight limit shows `kg`, a cutoff shows a 24-hour time), effective
window. Editor: facility select, rule-type select, **type-specific value fields that change per selected
type**, effective-from/to (date + optional time-of-day range).

### Rules
- **The value field set is entirely driven by `rule_type`** — this is the component-level enforcement of
  the typed-registry decision (§0.9 issue 10): there is no free-text "value" field that could hold anything.
  A `LAST_NEW_START_TIME` rule's editor shows one time field; a `CHECKIN_EARLY_LIMIT_MIN` or
  `NO_SHOW_GRACE_MIN` rule's editor shows one numeric minutes field; a `HEAVY_DOCK_REQUIRED_KG` rule's
  shows one kg threshold; a `REEFER_DOCK_REQUIRED` rule's is a single boolean. The component simply doesn't
  render fields that don't apply to the selected type.

  > **Registry corrected 2026-08-29 (A-G2, issue #70)** — see `screens.md` §3 for the full five-value table
  > and its provenance. Two consequences land specifically on *this* component, and they are why Screen 6
  > stays blocked after the correction rather than being unblocked by it:
  >
  > - **The `DOCK_PIN` example above was this rule's whole demonstration, and `DOCK_PIN` does not exist.**
  >   It was the only registry entry needing *two* value fields (dock picker + cargo-type picker) — the
  >   case that makes "the field set is driven by the type" visibly worth building rather than a one-field
  >   substitution. Every live type takes exactly one value. The rule below is unchanged and still correct;
  >   it has simply lost its most persuasive example, and no live analog replaces it.
  > - **Three of the five live types have no designed field set anywhere.** `NO_SHOW_GRACE_MIN` and
  >   `REEFER_DOCK_REQUIRED` appear in no artboard at all; `HEAVY_DOCK_REQUIRED_KG`'s is only inferable
  >   from the stale `WEIGHT_LIMIT` frame. Shipping a generic free-text value field for them instead would
  >   violate the one rule this section states outright, so the editor waits on design, not on backend.
- **Effective window defaults to "Always"** (no time bound) and only exposes the from/to fields when the
  admin explicitly narrows it — most rules genuinely are always-on, and forcing every rule creation through
  a time-bound picker would make the common case slower for no benefit.

  > **Corrected 2026-08-29 (A-G3, issue #71).** This bullet previously offered "intraday
  > from/to-time-of-day fields" implying a *recurring* daily window. The engine supports a single
  > **absolute** window only (hour-precise, so "from 2026-08-10 18:00 until 2026-08-11 06:00" works);
  > it has no day-of-week or repeat concept, and a recurring pattern saved into the column would be
  > enforced as **always on**, not as written. So this control is a from/to *datetime* pair, not a
  > weekday-plus-hours picker. See `screens.md` §3 for the reasoning and the owner fork.
- **Editing a rule with active dependent appointments requires the High-tier confirmation** — same pattern
  as user removal, since narrowing a rule (e.g. tightening `LAST_NEW_START_TIME`) could retroactively make
  an already-confirmed appointment non-compliant. The confirmation names what's affected, mirroring
  `03-planner-dock-board/`'s block-dock form's own "shows what it's about to strand before committing"
  discipline.

  > **Backed by a real read as of 2026-08-29 (A-G6, issue #74).** `GET /api/v1/admin/facility-rules/
  > {rule_id}/impact` takes `update_facility_rule`'s own arguments (omitted meaning unchanged) and returns
  > the affected set *before* the edit commits. Three details this component should render as given rather
  > than reinterpret:
  >
  > - It separates **`affected_count`** (appointments this edit would *newly* break) from
  >   **`already_non_compliant_count`** (ones the current rule forbids anyway). Only the first is a
  >   consequence of pressing Save; conflating them overstates the edit.
  > - **`evaluable: false`** is a real answer, not an error. Two of the five live rule types
  >   (`CHECKIN_EARLY_LIMIT_MIN`, `NO_SHOW_GRACE_MIN`) are not enforced by the feasibility engine at all,
  >   so no appointment *can* be made retroactively non-compliant by editing them. Render the returned
  >   `note`, not a bare "0 affected", which would read as "checked, nothing found".
  > - Each affected row carries the **engine's own violation message** as `reason`, so the dialog cannot
  >   describe the breach differently from the check that will actually reject future bookings.

---

## 3. Policy weight editor

### Anatomy
Read-only current-version header (version number, publish date, publisher) · numeric fields for each
Stage-2 coefficient (`w_lateness`, `w_wait`, `w_slack`, `P_dock`, `P_churn`) · the fixed priority-tier
values (CRITICAL/HIGH/NORMAL/LOW = 4000/3000/2000/1000 — shown, not editable, since these are the priority
*tiers themselves*, not tuning coefficients) · the fairness-term box (§4 below) · Simulate action.

### Rules
- **Every numeric field uses `--font-data` with `tabular-nums`** (`typography.md`) — these are precise
  values every future decision gets stamped with; they read as data, not prose.
- **No field commits on its own** — nothing here writes to `policy_versions` until Publish (§5 below) is
  pressed after a fresh simulation. The whole editor is staging area, not a live-saving form.
- **Changing any field after running a simulation marks the simulation result stale** (a visible banner:
  "Weights changed since this simulation — re-run before publishing") rather than silently allowing Publish
  against an outdated preview.

---

## 4. Fairness-term box (Danger-zone treatment)

### Anatomy
Visually separated card (border colour + icon distinct from the routine weight fields above it) · current
state ("Currently disabled (0)") · a one-line rationale referencing the carrier-concentration canary
(§8's KPI, cross-referenced not restated) · an Enable/Disable action gated by typed confirmation.

### Rules
- **This is the one weight field with its own confirmation gate**, deliberately inconsistent with every
  other field in §3's editor — the inconsistency *is* the point, matching the Admin Panel checklist's
  Danger Zone pattern: visual separation is what signals "this one is different," not a note buried in
  copy an admin could skim past.
- **Still goes through the same simulate-before-publish flow as any other weight change** — special
  friction on the *toggle*, not a bypass of the ordinary review discipline everything else in this editor
  already has.
- **Copy states the actual business stakes**, not just "advanced setting" — SetuHaul's own spec language
  ("if the data turns ugly") is the honest register to write this in, not a generic warning template.

---

## 5. Simulation result panel

### Anatomy
Headline stat ("N of M decisions would flip") · an expandable list of individual before/after cases, each
showing the shipment pair and which promise flips which way · Discard / Publish actions.

### States
Running (skeleton, since a 30-day replay is not instant) → **result** (as above) → **stale** (a weight
changed since this ran — banner, Publish disabled until re-run) → **published** (confirmation, returns to
the read-only current-version header with the new version number).

### Rules
- **Aggregate count is the headline; individual cases are secondary detail**, per the locked decision — an
  admin scans the number first, drills into cases only if the scale warrants a closer look.
- **Publish creates a new, immutable version — never edits the version just simulated against** (D7). The
  simulation's own "current policy" comparison point is whatever was live when Simulate was pressed; if
  another admin publishes a version in the meantime, Publish here returns a named conflict (see
  `edge-cases.md`) rather than silently publishing on top of a policy that's no longer current.

---

## 6. Audit log row

### Anatomy
Timestamp (`tabular-nums`) · actor (name + stable id, per the checklist's own reasoning) · event type
(a controlled vocabulary label, not free text — mirrors every other typed-enum discipline in this product)
· affected resource, as a plain reference (not a live link into another screen — `screens.md` §5's "no
drill-down" rule).

### Rules
- **System-generated events render actor as `(system)`**, in `text-tertiary`, never blank — a blank actor
  field reads as a data-quality problem; `(system)` reads as a fact.
- **Every write this console itself performs appears here** — a policy publish, a user removal, a rule
  edit are each their own audit entries, generated by the same M14 mechanism as any other tool call in the
  product. This component doesn't special-case admin's own actions; it's the same audit pipeline reused.
