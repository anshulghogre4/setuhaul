/**
 * Server shape -> view type. **The only file allowed to know the wire format.**
 *
 * Everything here is a rename or a null-check. There is deliberately no ranking, no
 * comparison, no verdict derivation: U48 (the interface renders receipts, it never reasons) is
 * enforced by keeping this file boring. If a function here starts sorting options or choosing a
 * label, that is the architectural property leaking.
 */

import type {
  DriverOption,
  EligibilityAnswer,
  EligibilityRow,
  OptionSet,
  SlotOutcome,
} from './types'

/* ------------------------------------------------------------------------------------------
   find_feasible_slots
   ------------------------------------------------------------------------------------------ */

type RawOption = {
  slot_id: string
  dock_id: string
  dock_code: string
  slot_local_date?: string
  feasible_start_ts: string
  feasible_end_ts: string
  differentiator?: string
  option_status?: string
}

type RawSlotsResult = {
  recommendation_id: string
  outcome?: string
  options?: RawOption[]
  escalation?: { escalation_id?: string; reference?: string } | null
  policy_version?: string
}

const OUTCOMES: ReadonlySet<string> = new Set(['FEASIBLE', 'NO_SAME_DAY_SLOT', 'NO_FEASIBLE_SLOT'])

export function toOptionSet(raw: RawSlotsResult): OptionSet {
  return {
    recommendationId: raw.recommendation_id,
    // Unknown outcome falls back to NO_FEASIBLE_SLOT, the SAFEST branch: it shows no cards and
    // no retry. Defaulting to FEASIBLE would render selectable cards for a result the client
    // did not understand, which is the one direction that can mis-promise capacity.
    outcome: (OUTCOMES.has(raw.outcome ?? '') ? raw.outcome : 'NO_FEASIBLE_SLOT') as SlotOutcome,
    options: (raw.options ?? []).map((o) => toOption(o, raw.recommendation_id)),
    escalationReference: raw.escalation?.escalation_id ?? raw.escalation?.reference ?? null,
    policyVersion: raw.policy_version ?? '',
    setState: 'active',
  }
}

function toOption(o: RawOption, recommendationId: string): DriverOption {
  return {
    slotId: o.slot_id,
    dockId: o.dock_id,
    dockCode: o.dock_code,
    // `slot_local_date` and NOT the date component of `feasible_start_ts`. The backend added
    // this field for exactly this reason and says so inline: the ISO timestamps carry a UTC
    // offset, so 2026-08-16T19:00+00:00 is 17 Aug in Asia/Kolkata. Using the wrong one is a
    // literal wrong-day booking. An empty string renders no date rather than a wrong one.
    slotLocalDate: o.slot_local_date ?? '',
    feasibleStartTs: o.feasible_start_ts,
    feasibleEndTs: o.feasible_end_ts,
    // E5.1 Fork A. Empty string is a REAL answer meaning "omit the line" (U81), so it is not
    // coerced to a placeholder and not filled from ranking_factors.
    differentiator: o.differentiator ?? '',
    recommendationId,
    optionStatus: o.option_status ?? 'DISPLAYED_NOT_RESERVED',
  }
}

/* ------------------------------------------------------------------------------------------
   explain_slot_eligibility
   ------------------------------------------------------------------------------------------ */

/**
 * ⚠ **This is the one place the client carries a copy of a server vocabulary, and it is a
 * flagged gap, not a design choice.**
 *
 * `SlotEligibilityResult` (`backend/app/scheduling/feasibility.py`) returns
 * `{ eligible, checked_constraints: string[], failure_code, message, explanation }` — that is
 * the list of invariant **ids** that were checked plus **one** failure code. It does *not*
 * return per-invariant rows. But `01-driver-chat/components.md` section 8 requires *"every
 * invariant renders, not just the failing one"*, with a `check`/`x` per row.
 *
 * So the client has to (a) label each id and (b) know which id the returned `failure_code`
 * belongs to. Both tables below are copied verbatim from
 * `backend/app/scheduling/constraints.json`'s `feasibility_hard_constraints[]`, which carries
 * an explicit 1:1 `id` -> `failure_code` pair for all ten.
 *
 * **Why this is acceptable for now:** it is a static vocabulary, not a decision — the server
 * still says whether the slot is eligible and which code failed; the client only pairs a code
 * to a row so the right row gets the ✗. Nothing here computes a verdict.
 *
 * **Why it should not stay:** renaming a `failure_code` server-side silently degrades this to
 * "all rows pass but the verdict says no". The clean fix is Fork-A-shaped —
 * `SlotEligibilityResult` gains `invariants: [{ id, label, passed, detail }]` — and is filed as
 * a follow-up rather than done here, because it is a backend contract change outside issue
 * #36's `area:frontend` scope. An unknown `failure_code` is handled explicitly below rather
 * than silently dropped.
 */
const CONSTRAINT_LABEL: Record<string, string> = {
  arrival_before_slot_end: 'Arrival fits the slot',
  facility_operating_hours: 'Facility open',
  dock_operational: 'Dock active',
  dock_vehicle_compatibility: 'Vehicle fits the dock',
  shipment_handling_compatibility: 'Load type supported',
  slot_capacity_available: 'Slot has capacity',
  latest_eta_only: 'Using your latest ETA',
  no_conflicting_active_appointment: 'No conflicting booking',
  facility_rule_compliance: 'Facility rules',
  driver_acceptable_window: 'Inside your stated window',
}

const FAILURE_CODE_TO_CONSTRAINT: Record<string, string> = {
  ETA_AFTER_SLOT_WINDOW: 'arrival_before_slot_end',
  FACILITY_CLOSED: 'facility_operating_hours',
  DOCK_UNAVAILABLE: 'dock_operational',
  DOCK_INCOMPATIBLE_VEHICLE: 'dock_vehicle_compatibility',
  DOCK_INCOMPATIBLE_LOAD: 'shipment_handling_compatibility',
  SLOT_CAPACITY_UNAVAILABLE: 'slot_capacity_available',
  STALE_ETA: 'latest_eta_only',
  ACTIVE_APPOINTMENT_EXISTS: 'no_conflicting_active_appointment',
  FACILITY_RULE_VIOLATION: 'facility_rule_compliance',
  DRIVER_WINDOW_VIOLATION: 'driver_acceptable_window',
}

type RawEligibility = {
  slot_id: string
  eligible: boolean
  checked_constraints?: string[]
  failure_code?: string | null
  message?: string | null
  explanation?: string[]
}

export function toEligibilityAnswer(
  raw: RawEligibility,
  dockCode: string,
  subject?: string,
): EligibilityAnswer {
  const failingId = raw.failure_code ? FAILURE_CODE_TO_CONSTRAINT[raw.failure_code] : undefined
  const detail = raw.message ?? raw.explanation?.[0] ?? undefined

  const rows: EligibilityRow[] = (raw.checked_constraints ?? []).map((id) => ({
    constraintId: id,
    // An id with no label renders the raw id rather than being hidden: a checked invariant the
    // client does not recognise is still a checked invariant, and dropping it would silently
    // shorten a list the design says must be complete.
    label: CONSTRAINT_LABEL[id] ?? id,
    passed: id !== failingId,
    detail: id === failingId ? detail : undefined,
  }))

  // The server said it failed but the code did not map to any checked id -- a genuine contract
  // drift. Surface it as its own failing row rather than rendering an all-green card under a
  // "No" verdict, which would be the worst possible outcome of the gap flagged above.
  if (!raw.eligible && raw.failure_code && !failingId) {
    rows.push({
      constraintId: raw.failure_code,
      label: raw.failure_code.replace(/_/g, ' ').toLowerCase(),
      passed: false,
      detail,
    })
  }

  return {
    slotId: raw.slot_id,
    dockCode,
    subject,
    eligible: raw.eligible,
    rows,
    // Templated, not generated (components.md section 8). Two sentences, chosen by the boolean
    // the server returned -- nothing here composes prose from the rows.
    verdict: raw.eligible
      ? 'Yes — this slot accepts your truck'
      : 'No — this slot will not work for this load',
  }
}
