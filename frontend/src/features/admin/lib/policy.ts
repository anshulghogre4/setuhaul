import type { ActivePolicy, PolicyWeights } from './types'

/**
 * The Policy tab's weight vocabulary and the pure helpers around it (Screens 8 and 10).
 *
 * **Nothing in this file hardcodes a weight VALUE.** That is the whole reason it exists in this
 * shape: E5.6 deliberately refused to build this tab because seeding `4 / -6 / 1 / -25` into the
 * client would have duplicated server configuration into a place that cannot detect drift from it
 * (`components/policy-tab.tsx`'s original header, and `AGENTS.md`'s "never invent … operational
 * data"). What is hardcoded here is only COPY — the label and unit strings, verbatim from
 * `mockup.html` §8 — and the *key names* the ranking engine reads. Every number comes from
 * `GET /api/v1/admin/policy/active`.
 *
 * The four keys below are the routine coefficients `admin_governance_service._score` actually
 * multiplies (verified against `backend/app/scheduling/constraints.json`'s `score_weights` and
 * `feasibility.py::_rank_slot`, read 2026-08-31). They are NOT the whole of `score_weights`:
 * `lateness_cap_minutes`, `fit_slack_cap_minutes` and `w_fairness` are also live keys, are also
 * read by `_score`, and are deliberately not editable here — see `buildProposedWeights`.
 */

/** `admin_governance_service.WEIGHT_FAIRNESS` / `feasibility.WEIGHT_FAIRNESS`. */
export const FAIRNESS_KEY = 'w_fairness'

/**
 * `P_churn` is NOT a live key and is never sent.
 *
 * It is in `admin_governance_service.BLOCKED_WEIGHT_KEYS`, which returns a **422**
 * (`UNKNOWN_WEIGHT_KEYS`) carrying its own reason: the term counts promises the facility
 * sequencer moved, and the sequencer (§7.5.3, issue #49) is entirely unbuilt. Named here so the
 * Danger Zone can state that fact rather than rendering a field with nowhere to go.
 */
export const CHURN_KEY = 'P_churn'

/**
 * The two cap keys `_score` reads out of the same `weights` dict (`admin_governance_service.py`'s
 * `_score`: `weights.get("lateness_cap_minutes", 720)`). Displayed inside a unit string, never
 * edited — `screens.md` §4's editor lists them as part of the unit ("per minute, cap 720"), not as
 * fields of their own.
 */
const LATENESS_CAP_KEY = 'lateness_cap_minutes'
const FIT_SLACK_CAP_KEY = 'fit_slack_cap_minutes'

export type WeightField = {
  /** The wire key sent to `/policy/simulate` and `/policy/publish`. */
  key: string
  /** `mockup.html` §8's label, verbatim. */
  label: string
  /** `SOLUTION_DESIGN.md` §5's formula symbol for the same coefficient, as the mockup shows it. */
  symbol: string
}

/**
 * The four routine weights this console edits, in `mockup.html` §8's own order.
 *
 * Order is copy, not data — it is the reading order an admin was designed to scan, so it is fixed
 * here rather than taken from the server's key iteration order (a JSON object's key order carries
 * no meaning).
 */
export const ROUTINE_WEIGHT_FIELDS: WeightField[] = [
  { key: 'lateness_per_minute', label: 'Lateness', symbol: 'w_lateness' },
  { key: 'wait_after_eta_per_minute', label: 'Wait', symbol: 'w_wait' },
  { key: 'fit_slack_per_minute', label: 'Slack', symbol: 'w_slack' },
  { key: 'compatible_but_not_exact_dock_penalty', label: 'Dock mismatch', symbol: 'P_dock' },
]

const ROUTINE_KEYS = new Set(ROUTINE_WEIGHT_FIELDS.map((field) => field.key))

/** `mockup.html` §10.B: "Counts use tabular figures and en-IN grouping." */
const NUMBER_FORMAT = new Intl.NumberFormat('en-IN')

export function formatNumber(value: number): string {
  return NUMBER_FORMAT.format(value)
}

function capUnit(base: string, cap: number | undefined): string {
  return typeof cap === 'number' ? `${base}, cap ${formatNumber(cap)}` : base
}

/**
 * The unit string for a field, with any cap read from the LIVE weights rather than written down.
 *
 * `mockup.html` §8 renders "per minute, cap 720" and "per minute, cap 120". Those two numbers are
 * `lateness_cap_minutes` and `fit_slack_cap_minutes` in `constraints.json` — real server config,
 * so they are interpolated, and the ", cap N" clause is dropped entirely if the engine stops
 * sending the key rather than falling back to a remembered number.
 */
export function unitFor(field: WeightField, live: PolicyWeights): string {
  if (field.key === 'lateness_per_minute') return capUnit('per minute', live[LATENESS_CAP_KEY])
  if (field.key === 'fit_slack_per_minute') return capUnit('per minute', live[FIT_SLACK_CAP_KEY])
  if (field.key === 'wait_after_eta_per_minute') return 'per minute'
  return 'flat penalty, unitless'
}

/**
 * Accepts a signed decimal and nothing else. `null` means "not a number the API can take".
 *
 * Two of the four coefficients are negative by design (`w_wait`, `P_dock`), so a `min={0}` guard
 * would be wrong; and `Number('')` is `0`, which would silently turn a cleared field into a
 * genuinely published zero. Both are why this is explicit rather than a bare `Number()`.
 */
export function parseWeightInput(raw: string): number | null {
  const trimmed = raw.trim()
  if (trimmed === '' || !/^-?\d+(\.\d+)?$/.test(trimmed)) return null
  const value = Number(trimmed)
  return Number.isFinite(value) ? value : null
}

/**
 * The payload for `/policy/simulate` and `/policy/publish`: **the server's own live key set, with
 * only the four routine keys overridden.**
 *
 * This is the load-bearing decision in this file, and it closes three separate hazards at once:
 *
 *  1. **Unknown keys are a 422, not a silent drop** (issue #69, `_validate_weight_keys`). A client
 *     that invented a key name would fail the whole request. Starting from `live` — which
 *     `get_active_policy_version` reads out of the same `constraints.json` that
 *     `allowed_weight_keys()` derives its allowlist from — makes an unknown key structurally
 *     impossible to send.
 *  2. **Dropping a live key is just as wrong as adding one.** `_score` reads
 *     `lateness_cap_minutes` / `fit_slack_cap_minutes` / `w_fairness` out of the *proposed*
 *     weights too, falling back to its own literal defaults when absent. Sending only four keys
 *     would silently simulate against those defaults instead of the caps actually configured, and
 *     would publish a `policy_versions` row missing them.
 *  3. **`engine_matches_active_version` stays meaningful.** That flag is a strict dict equality
 *     between the active row's `weights` and `constraints.json`'s `score_weights`
 *     (`admin_governance_service.get_active_policy_version`). Publishing a subset of keys would
 *     make it permanently `false` even for an unchanged republish, turning a real divergence
 *     signal into noise.
 *
 * `w_fairness` therefore round-trips **unchanged** while issue #69's Danger Zone is gated off: the
 * console neither edits it nor drops it.
 */
export function buildProposedWeights(
  live: PolicyWeights,
  drafts: Record<string, string>,
): PolicyWeights | null {
  const proposed: PolicyWeights = { ...live }
  for (const field of ROUTINE_WEIGHT_FIELDS) {
    // A routine key the engine does not currently define is not invented into existence: if
    // constraints.json ever drops one, the field is not rendered and nothing is sent for it.
    if (!(field.key in live)) continue
    const parsed = parseWeightInput(drafts[field.key] ?? '')
    if (parsed === null) return null
    proposed[field.key] = parsed
  }
  return proposed
}

/** The routine fields the server actually defines, in display order. */
export function editableFields(live: PolicyWeights): WeightField[] {
  return ROUTINE_WEIGHT_FIELDS.filter((field) => field.key in live)
}

/**
 * Live keys this console shows but does not edit — everything that is not one of the four.
 *
 * Rendered read-only rather than hidden: `screens.md` §4's rule is that an admin can see what
 * they are changing *from*, and a key that silently participates in every score while being
 * invisible in the editor is the same class of problem the whole tab exists to prevent.
 */
export function passthroughKeys(live: PolicyWeights): string[] {
  return Object.keys(live)
    .filter((key) => !ROUTINE_KEYS.has(key))
    .sort((a, b) => a.localeCompare(b))
}

/**
 * Seeds the editor's text state from the live weights. Strings, because a half-typed "-" is a
 * legal intermediate state a numeric state value cannot hold.
 */
export function draftsFrom(live: PolicyWeights): Record<string, string> {
  const drafts: Record<string, string> = {}
  for (const field of ROUTINE_WEIGHT_FIELDS) {
    if (field.key in live) drafts[field.key] = String(live[field.key])
  }
  return drafts
}

/**
 * Value equality over the exact key set, used for the staleness rule.
 *
 * `components.md` §3/§5 and `flows-and-states.md` Flow 6: "changing any field after running a
 * simulation marks the simulation result stale". Comparing the *submitted* weights object against
 * the *current* one is what makes that true by construction, rather than by remembering to reset a
 * flag inside every change handler.
 */
export function weightsEqual(a: PolicyWeights | null, b: PolicyWeights | null): boolean {
  if (a === null || b === null) return a === b
  const aKeys = Object.keys(a)
  const bKeys = Object.keys(b)
  if (aKeys.length !== bKeys.length) return false
  return aKeys.every((key) => key in b && a[key] === b[key])
}

/**
 * The publisher's display name, or the raw id.
 *
 * `components.md` §3 asks the current-version header for a publisher; the row carries only
 * `published_by_user_id`. Resolving it through `list_users` is the same derivation the Audit tab
 * already does for its Actor column — and falling back to the raw id rather than to "Unknown"
 * keeps the header attributable when a publisher has since been removed from the user list, which
 * is exactly `screens.md` §5's stated reason for logging a stable id beside a display name.
 */
export function publisherLabel(active: ActivePolicy, names: Record<string, string>): string {
  return names[active.published_by_user_id] ?? active.published_by_user_id
}
