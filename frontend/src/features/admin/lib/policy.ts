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
 * `P_churn` -- a live `score_weights` key since 2026-09-02 (issues #49/#69).
 *
 * It used to be in `admin_governance_service.BLOCKED_WEIGHT_KEYS`, refused with a 422 because the
 * sequencer that produces the count did not exist. The sequencer shipped, `constraints.json` now
 * carries `P_churn: 30` (§5.1's own recommended ≈30 weighted-minute-equivalents per moved promise),
 * and `BLOCKED_WEIGHT_KEYS` is empty.
 *
 * **It is a sequencer-objective weight, not a Stage-2 ranking coefficient**, which is why the
 * simulator reports `churn_term_evaluated: false` by design: §5 Stage 2's per-driver formula does
 * not contain `P_churn` at all, and §5.1's sequencer objective does. The field is editable and
 * publishable because the sequencer genuinely reads it
 * (`sequencer.py:1222`: `churn=int(weights.get(WEIGHT_CHURN, 30))`) and prices it into every run's
 * `objective.churn_cost`.
 */
export const CHURN_KEY = 'P_churn'

/**
 * The churn coefficient as a weight field.
 *
 * Like `FAIRNESS_WEIGHT_FIELD`, **deliberately not in `ROUTINE_WEIGHT_FIELDS`** -- but for the
 * opposite reason. Fairness is separated because it carries a Danger-Zone gate; churn is separated
 * because it is the one editable weight on this tab that **no simulation can preview**. Bundling it
 * with the four Stage-2 coefficients would let it inherit copy ("compare against the last 30 days")
 * that is untrue of it.
 */
export const CHURN_WEIGHT_FIELD: WeightField = {
  key: CHURN_KEY,
  label: 'Churn',
  symbol: 'P_churn',
}

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

/**
 * The fairness coefficient, as a weight field — but **deliberately not a member of
 * `ROUTINE_WEIGHT_FIELDS`**.
 *
 * `components.md` §4: *"This is the one weight field with its own confirmation gate, deliberately
 * inconsistent with every other field in §3's editor — the inconsistency *is* the point."* Keeping
 * it out of the routine array is what makes that structural rather than a rendering condition: no
 * loop over the routine fields can accidentally start editing it, and `buildProposedWeights` has to
 * be handed the unlock explicitly before it will read a draft for it.
 *
 * It is the same wire key the engine reads (`feasibility.WEIGHT_FAIRNESS` /
 * `admin_governance_service.WEIGHT_FAIRNESS`), and the symbol matches §5 Stage 2's formula.
 */
export const FAIRNESS_WEIGHT_FIELD: WeightField = {
  key: FAIRNESS_KEY,
  label: 'Fairness',
  symbol: 'w_fairness',
}

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
  // The fairness unit is not in `mockup.html` §8 -- the artboard never renders this field as an
  // input, because when it was drawn the term did not exist. Taken from what the engine actually
  // multiplies (`feasibility.py`: `w_fairness * carrier_concentration`) rather than left blank:
  // §8's own rule is "every field has a visible label AND a visible unit -- never a bare number",
  // and this is the field where a bare number would be least interpretable.
  if (field.key === FAIRNESS_KEY) return 'per other appointment this carrier holds that day'
  // SS5.1's own unit, verbatim from `mockup.html` section 8's fifth row.
  if (field.key === CHURN_KEY) return 'weighted-min-equivalent per moved promise'
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
 * `w_fairness` round-trips **unchanged** unless the Danger-Zone gate has been passed in this
 * session (`fairnessUnlocked`). That is Flow 7 step 2 expressed as a data rule rather than a
 * rendering one: until the gate is passed there is no draft for it to read, so the console
 * structurally cannot edit the field even if a form somewhere rendered it.
 *
 * Once unlocked, the fairness value re-enters the **ordinary** discipline with no exemption --
 * `edge-cases.md` #6: *"there is no separate bypass for the fairness field; it re-enters the
 * ordinary weight-editor discipline the instant the Danger-zone gate has been passed."* Because it
 * lands in the same returned object the staleness comparison runs over, changing it after a
 * simulation marks that simulation stale automatically, exactly like any other weight.
 *
 * **`P_churn` is never added here under any condition.** It is not a live key, the API refuses it
 * with a 422 naming its own reason, and starting from `live` is what makes sending it structurally
 * impossible rather than merely unlikely.
 */
export function buildProposedWeights(
  live: PolicyWeights,
  drafts: Record<string, string>,
  fairnessUnlocked = false,
  churnEnabled = false,
): PolicyWeights | null {
  const proposed: PolicyWeights = { ...live }
  const fields = editableFields(live, fairnessUnlocked, churnEnabled)
  for (const field of fields) {
    // A key the engine does not currently define is not invented into existence: if
    // constraints.json ever drops one, the field is not rendered and nothing is sent for it.
    // This is also the guard that keeps a fairness draft from creating the key on a deploy whose
    // engine predates #69 -- which would be the 422 this whole file is built to avoid.
    if (!(field.key in live)) continue
    const parsed = parseWeightInput(drafts[field.key] ?? '')
    if (parsed === null) return null
    proposed[field.key] = parsed
  }
  return proposed
}

/**
 * The fields the server actually defines, in display order.
 *
 * The fairness row is appended only once the Danger-Zone gate has been passed, which is Flow 7
 * step 2's *"`w_fairness` becomes an editable field in the ordinary weight editor"* -- literally
 * the ordinary editor, so it inherits every rule the other rows already follow rather than getting
 * a bespoke input of its own.
 */
export function editableFields(
  live: PolicyWeights,
  fairnessUnlocked = false,
  churnEnabled = false,
): WeightField[] {
  const fields = [...ROUTINE_WEIGHT_FIELDS]
  // Churn sits with the routine coefficients (it is `mockup.html` section 8's fifth row) but is
  // gated on its own flag, because its dependency is the sequencer rather than the Danger Zone.
  if (churnEnabled) fields.push(CHURN_WEIGHT_FIELD)
  if (fairnessUnlocked) fields.push(FAIRNESS_WEIGHT_FIELD)
  // A key the engine does not define is never invented into existence -- if constraints.json drops
  // one, the field is not rendered and nothing is sent for it.
  return fields.filter((field) => field.key in live)
}

/**
 * Live keys this console shows but does not edit — everything that is not one of the four.
 *
 * Rendered read-only rather than hidden: `screens.md` §4's rule is that an admin can see what
 * they are changing *from*, and a key that silently participates in every score while being
 * invisible in the editor is the same class of problem the whole tab exists to prevent.
 */
export function passthroughKeys(live: PolicyWeights, editable: WeightField[] = []): string[] {
  const shown = new Set([...ROUTINE_KEYS, ...editable.map((f) => f.key)])
  return Object.keys(live)
    .filter((key) => !shown.has(key))
    .sort((a, b) => a.localeCompare(b))
}

/**
 * Seeds the editor's text state from the live weights. Strings, because a half-typed "-" is a
 * legal intermediate state a numeric state value cannot hold.
 */
export function draftsFrom(live: PolicyWeights): Record<string, string> {
  const drafts: Record<string, string> = {}
  // The fairness draft is seeded unconditionally, unlike the field's EDITABILITY. Seeding it costs
  // nothing (an unlocked field would otherwise open empty, reading as a cleared value rather than
  // the engine's current 0) and it cannot leak into a payload: `buildProposedWeights` only reads a
  // draft for a field it was told is unlocked, and every key it does not read is round-tripped from
  // `live` regardless.
  for (const field of [...ROUTINE_WEIGHT_FIELDS, CHURN_WEIGHT_FIELD, FAIRNESS_WEIGHT_FIELD]) {
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
