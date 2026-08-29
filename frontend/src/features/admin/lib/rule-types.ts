/**
 * The facility-rule type registry — **the five values the live `CHECK` constraint actually
 * accepts**, not `SOLUTION_DESIGN.md` §7.5.7's four illustrative names that
 * `06-admin-console/`'s own design files inherited.
 *
 * Source of truth, in order:
 *   1. `supabase/migrations/20260825213000_e34_policy_versions_and_rule_registry.sql:19-24` —
 *      `facility_rules_rule_type_check`.
 *   2. `backend/app/services/admin_governance_service.py:47-49` — `RULE_TYPES`, the same five,
 *      with its own docstring stating the substitution was deliberate.
 *
 * This is A-G2 / issue #70, and following the live registry here is the spec's own recommendation
 * (`implementation-spec.md` §6 Fork A option 1: "E3.4 shipped against `facility_rules_rule_type_
 * check`'s live values with a stated, deliberate reason; reopening the constraint contradicts that
 * reasoning"). The consequence is that this surface's own `screens.md`/`components.md`/`mockup.html`
 * show `EARLY_LIMIT` / `DOCK_PIN` / `WEIGHT_LIMIT` / `NEW_START_CUTOFF` and the built table shows
 * five different strings. That divergence is intentional and is what #70 exists to reconcile on
 * the DESIGN side.
 *
 * Rough correspondence, recorded so a future reader doesn't re-derive it:
 *   `CHECKIN_EARLY_LIMIT_MIN` ≈ `EARLY_LIMIT`
 *   `LAST_NEW_START_TIME`     ≈ `NEW_START_CUTOFF`
 *   `HEAVY_DOCK_REQUIRED_KG`  ≈ `WEIGHT_LIMIT`
 *   `DOCK_PIN`                — no live analog at all
 *   `NO_SHOW_GRACE_MIN`, `REEFER_DOCK_REQUIRED` — no mockup representation at all
 */

export const RULE_TYPES = [
  'HEAVY_DOCK_REQUIRED_KG',
  'LAST_NEW_START_TIME',
  'CHECKIN_EARLY_LIMIT_MIN',
  'NO_SHOW_GRACE_MIN',
  'REEFER_DOCK_REQUIRED',
] as const

export type RuleType = (typeof RULE_TYPES)[number]

/**
 * How each type's `rule_value` reads with its unit.
 *
 * `data-formatting.md` via `mockup.html` §5: "values carry their unit with a space and never a
 * pluralised symbol (`60 min`, `18,500 kg`); times are 24-hour". Only types whose unit is
 * *derivable from the type name itself* get one — `_KG`, `_MIN`, `_TIME`. `REEFER_DOCK_REQUIRED`'s
 * value is a dock reference, which carries no unit, so it renders bare rather than being decorated.
 */
const UNIT_BY_TYPE: Partial<Record<RuleType, string>> = {
  HEAVY_DOCK_REQUIRED_KG: 'kg',
  CHECKIN_EARLY_LIMIT_MIN: 'min',
  NO_SHOW_GRACE_MIN: 'min',
}

export function isKnownRuleType(value: string): value is RuleType {
  return (RULE_TYPES as readonly string[]).includes(value)
}

/**
 * Renders a rule's value with its unit.
 *
 * A numeric value gets thousands separators (`18,500 kg`); a non-numeric one is passed through
 * untouched, because `rule_value` is an unstructured `TEXT` column
 * (`20260805201923_setuhaul_baseline.sql:85`) and could legitimately hold a dock code. Never
 * reformats what it cannot parse.
 */
export function formatRuleValue(ruleType: string, ruleValue: string): string {
  const unit = isKnownRuleType(ruleType) ? UNIT_BY_TYPE[ruleType] : undefined
  const asNumber = Number(ruleValue)
  const body =
    ruleValue.trim() !== '' && Number.isFinite(asNumber)
      ? asNumber.toLocaleString('en-IN')
      : ruleValue
  return unit ? `${body} ${unit}` : body
}

/**
 * The "Effective" column.
 *
 * Renders "Always" when both bounds are null — `components.md` §2: "effective window defaults to
 * 'Always' (no time bound)" — and otherwise the literal absolute range with an en dash.
 *
 * **Never renders a recurring weekly pattern** (the design's "Weekdays only, 18:00–23:59"):
 * `feasibility.py::active_facility_rules` evaluates these two columns as a plain absolute instant
 * range and nothing downstream parses a weekly window out of them (issue #71 / A-G3). Showing one
 * would claim an enforcement the engine does not perform.
 */
export function formatEffectiveWindow(from: string | null, to: string | null): string {
  if (!from && !to) return 'Always'
  if (from && !to) return `From ${from}`
  if (!from && to) return `Until ${to}`
  return `${from} – ${to}`
}
