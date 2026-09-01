/**
 * Planner dock board -- types.
 *
 * Every field here is copied from a verified backend response, not invented. Source for each
 * block is named at the point it is used; the two authoritative reads for the block-dock group
 * (the only group with a complete backend this pass -- `implementation-spec.md` section 0.1) are
 * `backend/app/services/planner_service.py` (`DockBlockResult` / `DockBlockImpact`) and
 * `backend/app/services/operations_reads.py::get_dock_snapshot` (the dock list -- section 7.5.1
 * names no dock-listing tool of its own, so the facility's existing `dock-snapshot` read, already
 * reachable by `WAREHOUSE_PLANNER` via `OPS_PORTAL_ROLES`, supplies the block-dock form's dock
 * select. Flagged as an addition, same discipline `get_dock_block_impact`'s own docstring uses).
 */

/** `docks` row shape -- `repositories/facilities.py::list_docks`, via `GET /operations/dock-snapshot`. */
export type DockType = 'STANDARD' | 'REEFER' | 'HEAVY'
export type DockStatus = 'ACTIVE' | 'MAINTENANCE' | 'OUT_OF_SERVICE' | 'INACTIVE'

export type Dock = {
  dock_id: string
  facility_id: string
  dock_code: string
  dock_type: DockType
  supports_refrigerated: boolean
  max_vehicle_weight_kg: number | null
  dock_status: DockStatus
}

/** One row of `block_dock`/`get_dock_block_impact`'s `affected_appointments[]`
 *  (`planner_service.py::_affected_appointments`). */
export type AffectedAppointment = {
  occupancy_id: number
  appointment_id: string
  dock_id: string
  window_start: string
  window_end: string
  appointment_status: string
  shipment_id: string
  driver_id: string | null
  priority_code: string | null
  load_weight_kg: number | null
}

/** `dock_status_events` row shape, as returned inside `conflicting_event` (`ALREADY_BLOCKED`). */
export type ConflictingEvent = {
  dock_event_id: string
  dock_id: string
  event_type: string
  event_start_ts: string
  event_end_ts: string | null
  reason: string | null
}

/** `GET /planner/docks/{dock_id}/block-impact` -- `planner_service.py::DockBlockImpact`. */
export type DockBlockImpact = {
  as_of: string
  source: string
  freshness: string
  dock_id: string
  facility_id: string
  window_start: string
  window_end: string
  affected_appointments: AffectedAppointment[]
  affected_count: number
  conflicting_event: ConflictingEvent | null
}

/** `POST /planner/docks/{dock_id}/block` and `.../dock-status-events/{id}/end` --
 *  `planner_service.py::DockBlockResult`. */
export type DockBlockResult = {
  as_of: string
  source: string
  freshness: string
  code: 'BLOCKED' | 'ALREADY_BLOCKED' | 'UNBLOCKED' | 'NOT_BLOCKED'
  dock_id: string
  facility_id: string
  dock_status_event_id: string | null
  window_start: string | null
  window_end: string | null
  reason: string | null
  affected_appointments: AffectedAppointment[]
  affected_count: number
  escalation_id: string | null
  conflicting_event: ConflictingEvent | null
  idempotency_key: string | null
  idempotent_replay: boolean
}

/* ==============================================================================================
 * get_planner_queue -- issue #60, `SOLUTION_DESIGN.md` section 7.3 / section 7.5.1, FR-PLN-010.
 *
 * Every type below is copied field-for-field from the Pydantic models in
 * `backend/app/services/planner_service.py` (`PlannerQueueRow` and its six sub-models,
 * `PlannerQueue`, `PlannerQueueSnapshotInfo`), read 2026-08-29. Each of those models is
 * `extra="forbid"`, so this is the whole surface -- nothing inferred, nothing padded out with
 * fields the server does not send.
 * ============================================================================================ */

/** Section 7.3's condensed receipt -- "the score terms in words" (`QueueReceipt`). */
export type QueueReceipt = {
  priority_code: string
  lateness_minutes: number | null
  wait_after_eta_minutes: number | null
  /** "exact" | "compatible" | null -- mirrors `_rank_slot`'s `exact_dock_type_match`. */
  dock_match: string | null
  /** Pre-joined server-side with " . ". Rendered verbatim; never re-composed on this side. */
  text: string
}

/**
 * One overlapping live claim (`planner_service._conflicts_for`). Since issue #84 a claim can be a
 * D2 hold rather than an appointment, which is why `appointment_id` is nullable and `claim_id` --
 * not `appointment_id` -- is the identity that goes into the snapshot digest.
 */
export type QueueIntervalConflict = {
  conflict_type: 'INTERVAL_CONFLICT'
  claim_id: string
  claim_source: string
  appointment_id: string | null
  shipment_id: string
  order_reference: string | null
  appointment_status: string
  hold_expires_at: string | null
  window_start: string
  window_end: string
}

/**
 * The second leg of the displacement column, added by issue #88:
 * `snapshot.py::load_dock_block_conflicts` -- a `dock_status_events` outage overlapping this
 * interval.
 *
 * **It carries no shipment, and that is the whole point.** Nobody is displaced; the dock is simply
 * gone. The exact field set is the one the SQL builds
 * (`scheduling/snapshot.py:323-327`): `conflict_type`, `dock_event_id`, `dock_id`, `event_type`,
 * `reason` -- no `window_start`/`window_end`, no `claim_id`, no `shipment_id`. Typing those absent
 * fields as optional-anything would have let `describeDisplacement` keep reading `shipment_id` off
 * this leg, which is exactly the bug the discriminator exists to make impossible.
 */
export type QueueDockBlockedConflict = {
  conflict_type: 'DOCK_BLOCKED'
  dock_event_id: string
  dock_id: string
  event_type: string
  reason: string | null
}

export type QueueConflict = QueueIntervalConflict | QueueDockBlockedConflict

/**
 * The one place that reads the discriminator.
 *
 * **An absent `conflict_type` is treated as `INTERVAL_CONFLICT`**, deliberately: that is the only
 * shape this field had before #88, so a response from an older deploy degrades to the previous
 * (correct-for-it) rendering rather than to `undefined`. Narrowing on the *presence* of
 * `DOCK_BLOCKED` rather than on the absence of the other value is what makes that true.
 */
export function isDockBlockedConflict(
  conflict: QueueConflict,
): conflict is QueueDockBlockedConflict {
  return conflict.conflict_type === 'DOCK_BLOCKED'
}

/** Section 7.3's "single most important field": would confirming this hurt a third party? */
export type QueueDisplacement = {
  status: 'NONE' | 'CONFLICT'
  conflicts: QueueConflict[]
}

export type QueueEta = {
  effective_eta_ts: string | null
  /** LOW renders as a warning-toned flag, not plain text (`components.md` section 1). */
  confidence: string | null
  source: string | null
}

/** The D9 clock, derived server-side from `booked_at + DEFAULT_PENDING_TTL_MINUTES`, never stored. */
export type QueueTtl = {
  deadline_ts: string
  remaining_seconds: number
  expired: boolean
  /**
   * Issue #64: true once `hold_for_information` has spent this request's one extension
   * (`planner_service.py:237-248` -- it is `appointments.expires_at IS NOT NULL`, not a separate
   * counter). When true, `deadline_ts` **is** the extended deadline.
   *
   * Two consequences, both rendered: the Hold affordance goes Disabled (the one-shot cap, prevented
   * before the call rather than handled after a 409 -- `edge-cases.md` #6), and the countdown takes
   * its held treatment. See `queue-row.tsx` for the one place the design and the shipped mechanism
   * genuinely disagree, and what this build does about it.
   */
  hold_used: boolean
}

export type QueueGateState = {
  queue_state: string | null
  queue_position: number | null
  gate_in_ts: string | null
  physically_waiting: boolean
}

/** The composite-urgency sort, returned per row so the order is inspectable rather than magic. */
export type QueueUrgency = {
  score: number
  priority_score: number
  ttl_pressure: number
  waiting_bonus: number
}

export type PlannerQueueRow = {
  appointment_id: string
  shipment_id: string
  slot_id: string
  appointment_status: string
  booking_source: string
  booked_at: string
  order_reference: string | null

  driver_id: string | null
  driver_name: string | null
  carrier_id: string | null
  carrier_name: string | null

  facility_id: string
  dock_id: string
  dock_code: string | null
  dock_type: string | null
  interval_start: string
  interval_end: string
  /** "dock_occupancy" when D1's authority answered, "appointment_slot_derived" when this
   *  appointment holds no claim and the window had to be recomputed. Surfaced rather than
   *  hidden: the two are different facts about how load-bearing the interval is. */
  interval_source: string

  receipt: QueueReceipt
  displacement: QueueDisplacement
  eta: QueueEta
  latest_acceptable_ts: string | null
  latest_acceptable_exception_id: string | null
  /** Deliberately three-valued. `null` is "no limit on file, or one that could not be parsed" --
   *  "we checked and it is fine" and "we could not check" are different facts, the same
   *  distinction State 17 protects for the block-dock preview. */
  latest_acceptable_breached: boolean | null
  ttl: QueueTtl
  gate: QueueGateState
  urgency: QueueUrgency
  /** Section 7.5 principle 3. Round-tripped verbatim into confirm / counter-offer / bulk-confirm.
   *  Never recomputed on this side -- see `lib/api.ts`'s header. */
  snapshot_hash: string
}

export type PlannerQueueSnapshotInfo = {
  algorithm: string
  /** Stale as of 2026-08-29: the payload still reports `false` while `_snapshot_guard` genuinely
   *  enforces the hash on confirm / counter-offer / bulk-confirm (issue #62 landed after that
   *  note was written). This client therefore never branches on it -- it always sends the hash. */
  enforced: boolean
  note: string
}

export type PlannerQueue = {
  as_of: string
  source: string
  freshness: string
  scope: { facility_id?: string; read_only?: boolean }
  policy_version: string
  ttl_minutes: number
  horizon_hours: number | null
  limit: number
  /** True means "there may be more pending requests than this page shows". The toolbar must not
   *  render a total from `count` alone when it is set -- the server's own comment says so. */
  limit_reached: boolean
  ordering: {
    rule?: string
    terms?: string[]
    weights?: Record<string, unknown>
    tiebreaker?: string
  }
  snapshot: PlannerQueueSnapshotInfo
  count: number
  items: PlannerQueueRow[]
}

/* ==============================================================================================
 * Stage-1 feasible options -- `backend/app/scheduling/feasibility.py`
 *
 * Deliberately a SUBSET of `FeasibleSlotOption`: only the fields the counter-offer picker
 * actually renders or sends. The full model carries ranking internals (`ranking_factors`,
 * `checked_constraints`, `rank_score`) that belong to the engine's own explanation path, not to
 * this dialog, and typing fields nobody reads invites someone to start reading them.
 * ============================================================================================ */

export type FeasibleSlotOption = {
  slot_id: string
  facility_id: string
  dock_id: string
  dock_code: string
  dock_type: string
  slot_start_ts: string
  slot_end_ts: string
  /** The facility-LOCAL calendar date. Not derivable from `slot_start_ts` by the client: a
   *  19:00+00:00 slot is the next day in Asia/Kolkata, and the server says so explicitly for
   *  exactly that reason. Any date shown to a human must come from here. */
  slot_local_date: string
  is_same_day: boolean
  /** E5.1 Fork A's comparative label, or "" when no label in the closed vocabulary is true of
   *  this option. Empty is a real answer -- the line is omitted, never filled with a fourth
   *  invented phrase. */
  differentiator?: string
  ranking_explanation: string[]
}

export type FeasibleSlotsResult = {
  as_of: string
  policy_version: string
  recommendation_id: string
  shipment_id: string
  facility_id: string
  /** FEASIBLE / NO_SAME_DAY_SLOT / NO_FEASIBLE_SLOT -- callers must branch on this rather than on
   *  `options.length`, because NO_SAME_DAY_SLOT returns options AND is not a plain success. */
  outcome: string
  options: FeasibleSlotOption[]
}

/* ==============================================================================================
 * Write results -- `backend/app/scheduling/allocation.py`
 * ============================================================================================ */

/**
 * `AppointmentTransitionResult` -- confirm (`APPOINTMENT_CONFIRMED`) and reject
 * (`APPOINTMENT_REJECTED`). `snapshot_hash` is the token for this row's NEXT write: present on
 * confirm, `null` on reject, because section 7.5.1's `reject_request` takes no snapshot argument.
 */
export type AppointmentTransitionResult = {
  as_of: string
  source: string
  freshness: string
  status: string
  code: string
  shipment_id: string
  appointment_id: string
  appointment: Record<string, unknown> | null
  idempotency_key: string
  idempotent_replay: boolean
  appointment_writes: number
  snapshot_hash: string | null
}

/** One entry of `counter_offer`'s `offered_options` -- the single interval the planner picked,
 *  returned as a list because section 7.5.1 says "the new option set". */
export type CounterOfferedOption = {
  slot_id: string
  facility_id: string
  dock_id: string
  dock_code: string
  dock_type: string
  slot_start_ts: string
  slot_end_ts: string
  occupancy_window?: string
  checked_constraints?: unknown
  explanation?: unknown
}

export type CounterOfferResult = {
  as_of: string
  source: string
  freshness: string
  code: string
  shipment_id: string
  appointment_id: string
  reason_code: string
  offered_options: CounterOfferedOption[]
  appointment: Record<string, unknown> | null
  idempotency_key: string
  idempotent_replay: boolean
  appointment_writes: number
  snapshot_hash: string | null
}

/**
 * `hold_for_information` -- section 7.5.1, FR-PLN-004, issue #64.
 * `allocation.py::HoldForInformationResult`, `extra="forbid"`, copied field for field.
 *
 * `previous_deadline` is carried so the row can say what the hold actually *bought* rather than
 * only what the new deadline is, and `hold_used` is returned explicitly (always `true` on success)
 * so a client never has to infer "spent" from the presence of `new_deadline`.
 */
export type HoldForInformationResult = {
  as_of: string
  source: string
  freshness: string
  status: string
  code: string
  shipment_id: string
  appointment_id: string
  question: string
  new_deadline: string
  previous_deadline: string
  extension_minutes: number
  hold_used: boolean
  appointment: Record<string, unknown> | null
  idempotency_key: string
  idempotent_replay: boolean
  appointment_writes: number
}

/**
 * Per-id outcome. `code` is one of CONFIRMED | ALREADY_ACTIONED | DISPLACEMENT_DETECTED |
 * NOT_ELIGIBLE | NOT_FOUND | OUT_OF_SCOPE -- read off `allocation.bulk_confirm`'s own branches,
 * not from prose. Deliberately `string` rather than a union: an outcome code added server-side
 * should render as itself, not be silently dropped by an exhaustive switch on this side.
 */
export type BulkConfirmOutcome = {
  appointment_id: string
  shipment_id: string | null
  code: string
  detail: string | null
  /** Which of section 7.3's five safe-batch predicates this id failed. Named, never counted. */
  failed_predicates: string[]
  conflicts: QueueConflict[]
  snapshot_hash: string | null
}

export type BulkConfirmResult = {
  as_of: string
  source: string
  freshness: string
  code: string
  requested: number
  confirmed: number
  skipped: number
  /** False means the board moved between selection and press. It REPORTS; it does not refuse --
   *  `bulk_confirm`'s own documented behaviour, and the reason this UI renders per-id outcomes
   *  rather than one batch verdict. */
  snapshot_hash_matched: boolean
  expected_snapshot_hash: string
  current_snapshot_hash: string
  outcomes: BulkConfirmOutcome[]
  idempotency_key: string
  idempotent_replay: boolean
  appointment_writes: number
}

/* ==============================================================================================
 * The Board tab's at-rest occupancy view -- `GET /api/v1/planner/board`
 * (`planner_service.py::DockBoard`, added for E5.3's third `dockBoardEnabled` gate).
 * ============================================================================================ */

/**
 * Every `dock_occupancy.state` the board can be handed.
 *
 * Nine values, exactly as `components.md` section 3's mapping table enumerates them -- **not the
 * four the promise chip renders**. The extra five are terminal and map to "no bar"; keeping them
 * in the union rather than filtering them out of the type is what makes that a *mapping-table row*
 * instead of a silent gap, which is the rule that table states about itself.
 */
export type DockOccupancyState =
  | 'HELD'
  | 'PENDING_CONFIRMATION'
  | 'CONFIRMED'
  | 'IN_PROGRESS'
  | 'COMPLETED'
  | 'CANCELLED'
  | 'EXPIRED'
  | 'NO_SHOW'
  | 'REJECTED'

/** Which table asserted this claim. Only a hold has an `expires_at`, and only a hold draws dashed. */
export type ClaimSource = 'appointments' | 'dock_occupancy_hold'

export type BoardDock = {
  dock_id: string
  dock_code: string
  dock_type: DockType | null
  dock_status: DockStatus | null
  supports_refrigerated: boolean | null
  max_vehicle_weight_kg: number | null
}

export type BoardBar = {
  occupancy_id: string
  dock_id: string
  /** Typed as the nine-value union but treated as an open string at the mapping site: an unknown
   *  state must render *nothing* rather than throw, which is why `board.ts` looks it up in a
   *  record rather than switching exhaustively. */
  state: DockOccupancyState
  claim_source: ClaimSource
  appointment_id: string | null
  shipment_id: string | null
  order_reference: string | null
  window_start: string
  window_end: string
  /** Present only on a `dock_occupancy_hold` bar (D2's 90-second TTL). */
  hold_expires_at: string | null
}

export type BoardBlock = {
  dock_event_id: string
  dock_id: string
  event_type: string
  event_start_ts: string
  /** `null` means open-ended -- the dock is out until someone ends the block. The client clamps
   *  it to the horizon for drawing; the server does not invent an end instant. */
  event_end_ts: string | null
  reason: string | null
}

export type DockBoard = {
  as_of: string
  source: string
  freshness: string
  facility_id: string
  facility_name: string | null
  timezone: string | null
  horizon_start: string
  horizon_end: string
  /** Which of the two bounds in "four hours, or until closing time, whichever comes sooner"
   *  actually applied. Rendered in the axis caption so the board says why it stops where it does. */
  horizon_end_reason: 'ROLLING_WINDOW' | 'FACILITY_CLOSE'
  docks: BoardDock[]
  bars: BoardBar[]
  blocks: BoardBlock[]
  /** `TWO_PHASE_HOLD_ENABLED`. False means a HELD bar cannot occur on this deploy, which is what
   *  lets the legend omit an entry nothing could ever fill rather than showing a dead swatch. */
  holds_enabled: boolean
}
