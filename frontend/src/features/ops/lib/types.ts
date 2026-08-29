/**
 * Ops exception console -- types.
 *
 * Every field here is copied from a verified backend response, not invented. Source for each
 * block is named at the point it is used; the two authoritative reads are
 * `backend/app/services/escalation_service.py::get_exception_queue` (the queue item shape) and
 * the six mutation functions in the same file (the action-result `code` unions).
 */

export type EscalationStatus = 'OPEN' | 'ACKNOWLEDGED' | 'IN_PROGRESS' | 'RESOLVED' | 'CANCELLED'

/** SS7.4's nine canonical reasons -- `escalation_service.py` `ESCALATION_TYPES`. */
export type EscalationReason =
  | 'NO_FEASIBLE_SLOT'
  | 'PENDING_EXPIRED_UNACTIONED'
  | 'AMBIGUOUS_SHIPMENT'
  | 'LOW_CONFIDENCE_ETA'
  | 'WAREHOUSE_REPLY_CONFLICT'
  | 'NOTIFICATION_FAILED'
  | 'NOTIFICATION_UNROUTABLE'
  | 'SAFETY_OR_REGULATED'
  | 'CAPACITY_EVENT_CASCADE'

export type SeverityCode = 'HIGH' | 'MEDIUM' | 'LOW'

/** `payload.affected_appointments[]` -- `planner_service.py::_open_capacity_cascade`, the exact
 *  five fields it writes. **No `priority_code`** -- `_affected_appointments` (same file) reads
 *  it off `shipments.priority_code` but `_open_capacity_cascade` does not carry it into the
 *  stored payload, so the queue-row API genuinely cannot return a priority for these rows today.
 *  `components.md` section 17 and `screens.md` section 5 both show one on the affected-shipment
 *  list; rendering it would be inventing a fact this response does not have. See
 *  `capacity-incident-row.tsx`'s comment at the point this is rendered. */
export type AffectedAppointment = {
  appointment_id: string
  shipment_id: string
  appointment_status: string
  window_start: string
  window_end: string
}

/** One row of `GET /api/v1/operations/escalation-queue`'s `items[]`. */
export type EscalationQueueItem = {
  escalation_id: string
  shipment_id: string
  facility_id: string
  driver_id: string | null
  escalation_type: EscalationReason
  escalation_status: EscalationStatus
  severity_code: SeverityCode
  policy_version: string | null
  recommendation_id: string | null
  payload: Record<string, unknown>
  created_at: string
  updated_at: string
  owner_user_id: string | null
  owner_name: string | null
  /** `STEPPER_POSITIONS` -- 0..3. RESOLVED and CANCELLED both map to 3 (both terminal). */
  stepper_position: 0 | 1 | 2 | 3
  /** Minutes remaining against `SLA_BUDGET_MIN`'s per-severity budget -- negative once breached.
   *  `Source: assumption, untested` (escalation_service.py:29-35) -- no documented SLA policy
   *  grounds these budgets; carried forward with the same flag rather than laundered into a fact. */
  sla_remaining_min: number
  /** Populated only for `CAPACITY_EVENT_CASCADE` rows; `null` otherwise. */
  affected_shipments: AffectedAppointment[] | null
}

export type EscalationQueueResponse = {
  as_of: string
  source: string
  facility_id: string | null
  owner: 'mine' | 'unowned' | 'all'
  items: EscalationQueueItem[]
}

export type OwnerFilter = 'mine' | 'unowned' | 'all'

/** SLA posture -- `color.md` "Escalation severity". Computed client-side from
 *  `sla_remaining_min` + `severity_code` (see `lib/sla.ts`), not returned by the API. */
export type SlaPosture = 'ok' | 'warning' | 'breach'

export type AcknowledgeResult = {
  code: 'ACKNOWLEDGED' | 'ALREADY_ACTIONED'
  escalation_id: string
  shipment_id?: string
  escalation_status?: EscalationStatus
  owner_user_id?: string | null
}

export type ReassignResult = {
  code: 'REASSIGNED' | 'NOT_ACKNOWLEDGED'
  escalation_id: string
  shipment_id?: string
  escalation_status?: EscalationStatus
  owner_user_id?: string | null
}

export type ResolveCancelResult = {
  code: 'RESOLVED' | 'CANCELLED'
  escalation_id: string
  shipment_id?: string
  escalation_type?: string
  escalation_status?: EscalationStatus
  resolution_note?: string | null
}

export type TakeOverResult = {
  code: 'TAKEN_OVER' | 'ALREADY_TAKEN_OVER'
  thread_id: string
  escalation_id: string
  thread_status: 'ESCALATED'
}

export type HandBackResult = {
  code: 'HANDED_BACK' | 'NOT_IN_PROGRESS'
  thread_id: string
  escalation_id?: string
  thread_status: 'OPEN' | 'ESCALATED'
}

/** Flow 6 -- resolve_escalation / cancel_escalation's `reason_code`
 *  (`Source: assumption, untested`, escalation_service.py RESOLVE/CANCEL_REASON_CODES). */
export const RESOLVE_REASON_CODES = ['ISSUE_FIXED'] as const
export const CANCEL_REASON_CODES = ['SHIPMENT_CANCELLED', 'DUPLICATE', 'CREATED_IN_ERROR'] as const
export type ResolveReasonCode = (typeof RESOLVE_REASON_CODES)[number]
export type CancelReasonCode = (typeof CANCEL_REASON_CODES)[number]
