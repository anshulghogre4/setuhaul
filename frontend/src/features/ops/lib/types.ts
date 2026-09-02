/**
 * Ops exception console -- types.
 *
 * Every field here is copied from a verified backend response, not invented. Source for each
 * block is named at the point it is used; the two authoritative reads are
 * `backend/app/services/escalation_service.py::get_exception_queue` (the queue item shape) and
 * the mutation functions in the same file plus
 * `backend/app/services/thread_message_service.py` (the action-result `code` unions).
 */

export type EscalationStatus = 'OPEN' | 'ACKNOWLEDGED' | 'IN_PROGRESS' | 'RESOLVED' | 'CANCELLED'

/** `chat_threads.thread_status`'s CHECK constraint --
 *  `supabase/migrations/20260805201923_setuhaul_baseline.sql:161-162`. Copied in full rather than
 *  narrowed to the two values this surface acts on, so an unexpected one renders as itself
 *  instead of falling through a `never`. */
export type ThreadStatus =
  | 'OPEN'
  | 'WAITING_FOR_DRIVER'
  | 'WAITING_FOR_WAREHOUSE'
  | 'RESOLVED'
  | 'ESCALATED'
  | 'CLOSED'

/** `chat_messages.sender_type`'s CHECK constraint (same baseline migration, lines 269-270).
 *  U47's three visual tiers are DRIVER / AGENT / (OPERATIONS|WAREHOUSE); SYSTEM renders as a
 *  centred divider rather than a bubble -- see `thread-transcript.tsx`. */
export type ChatSenderType = 'DRIVER' | 'AGENT' | 'OPERATIONS' | 'WAREHOUSE' | 'SYSTEM'

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
  /** E5.2, issues #55/#58: the shipment's most recently opened chat thread, added to the queue
   *  read via `LEFT JOIN LATERAL` (`escalation_service.py::get_exception_queue`). **`null` is a
   *  real, expected value** -- a `NOTIFICATION_FAILED` escalation may legitimately have no thread
   *  at all -- and both `take_over_thread` and `post_operations_message` need this id, so a null
   *  here is what makes takeover genuinely unavailable rather than merely unwired. */
  thread_id: string | null
  thread_status: ThreadStatus | null
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

/**
 * `POST /operations/escalations/{id}/start` -- `escalation_service.py::start_escalation_work`
 * (issue #56). The write that makes `escalation_status = 'IN_PROGRESS'` reachable at all, and
 * therefore the recovery path for a hand-back the backend now refuses (see `HandBackResult`).
 *
 * All five outcomes are HTTP **200** typed results, not exceptions -- so the console branches on
 * `code` rather than parsing an error string out of a thrown `Error`.
 */
export type StartWorkResult = {
  code: 'IN_PROGRESS' | 'ALREADY_IN_PROGRESS' | 'NOT_ACKNOWLEDGED' | 'NOT_OWNER' | 'ALREADY_ACTIONED'
  escalation_id: string
  shipment_id?: string
  escalation_status?: EscalationStatus
  owner_user_id?: string | null
  stepper_position?: 0 | 1 | 2 | 3
  idempotent_replay?: boolean
}

/**
 * `POST /operations/threads/{id}/take-over` -- `escalation_service.py::take_over_thread`.
 *
 * **`NOT_ACKNOWLEDGED` is new in E5.2 (issue #56)** and it fixes this console's action order: the
 * endpoint now refuses a takeover whose escalation is not `ACKNOWLEDGED`/`IN_PROGRESS` **and
 * owned** -- exactly the order `flows-and-states.md` Flow 1 already prescribes (step 3
 * acknowledge, step 4 take over). `delivered`/`delivery_reason` say whether the driver-visible
 * join divider actually reached the driver's live feed; see `lib/delivery.ts`.
 */
export type TakeOverResult = {
  code: 'TAKEN_OVER' | 'ALREADY_TAKEN_OVER' | 'NOT_ACKNOWLEDGED'
  thread_id: string
  escalation_id: string
  thread_status?: ThreadStatus
  escalation_status?: EscalationStatus | null
  owner_user_id?: string | null
  stepper_position?: 0 | 1 | 2 | 3 | null
  delivered?: boolean
  delivery_reason?: string | null
  idempotent_replay?: boolean
}

/**
 * `POST /operations/threads/{id}/hand-back` -- `escalation_service.py::hand_back_thread`.
 *
 * **`NOT_IN_PROGRESS` has two distinct causes and the console must tell them apart**, because one
 * is a no-op and the other is recoverable in a single call:
 *
 *  - `thread_status !== 'ESCALATED'` -- already handed back. Nothing to do but refresh.
 *  - `thread_status === 'ESCALATED'` -- still taken over, but no `IN_PROGRESS` escalation backs
 *    it. This is the live-data case `hand_back_thread`'s own docstring calls out: a thread taken
 *    over *before* issue #56 tightened the guard sits on an `ACKNOWLEDGED` escalation. Recovery is
 *    `start_escalation_work` then retry -- see `takeover-control.tsx`.
 */
export type HandBackResult = {
  code: 'HANDED_BACK' | 'NOT_IN_PROGRESS'
  thread_id: string
  escalation_id?: string
  thread_status: ThreadStatus
  delivered?: boolean
  delivery_reason?: string | null
}

/** One row of `GET /operations/threads/{id}/messages` -- `chat_threads.list_thread_messages`'s
 *  exact SELECT list. `sender_name` is a `LEFT JOIN` on `users.full_name` and is genuinely `null`
 *  for a DRIVER/AGENT row whose `sender_reference` is not a `users.user_id`. */
export type ThreadMessage = {
  chat_message_id: string
  thread_id: string
  sender_type: ChatSenderType
  sender_reference: string | null
  message_text: string
  message_ts: string
  sender_name: string | null
}

export type ThreadMessagesResponse = {
  as_of: string
  source: string
  thread_id: string
  thread_status: ThreadStatus
  shipment_id: string | null
  driver_id: string | null
  facility_id: string | null
  messages: ThreadMessage[]
  freshness: string
}

/**
 * `POST /operations/threads/{id}/messages` -- `thread_message_service.py::post_operations_message`
 * (issue #55). The coordinator reply path; the one thing the composer exists to do.
 *
 * **`delivered` and `delivery_reason` are not optional decoration.** Postgres `chat_messages` is
 * the write of record and Redis is a projection of it; when the projection fails the row is still
 * durable but **will never reach the driver's feed, even after Redis recovers, because nothing
 * back-fills it** (that module's own docstring states this as a known residual). Rendering
 * `POSTED` as an unqualified success would tell a coordinator their message reached a driver when
 * it did not.
 */
export type PostMessageResult = {
  code: 'POSTED' | 'NOT_TAKEN_OVER'
  thread_id: string
  chat_message_id?: string
  sender_type?: ChatSenderType
  sender_name?: string | null
  message_text?: string
  message_ts?: string
  thread_status?: ThreadStatus
  delivered: boolean
  delivery_reason: string | null
  idempotent_replay?: boolean
}

/* ---------------------------------------------------------------------------------------------
 * Escalate (the detail pane's overflow entry) -- `POST /api/v1/operations/escalate`
 * -------------------------------------------------------------------------------------------- */

/**
 * `escalate_exception`'s `confirmed=false` branch (`escalation_service.py:128-141`).
 *
 * The service returns this **before** it touches the database at all -- it is a preview, not a
 * refusal, and the `note` it carries is the server's own wording for what confirming would do.
 * Rendering that string rather than a locally-written one is the point: the sentence a coordinator
 * agrees to is the sentence the service authored for this exact call.
 */
export type EscalatePreview = {
  status: 'CONFIRMATION_REQUIRED'
  code: 'CONFIRMATION_REQUIRED'
  shipment_id: string
  escalation_type: string
  reason: string | null
  requires_confirmation: true
  note: string
}

/**
 * `escalate_exception`'s `confirmed=true` branch -- the `escalation_queue` row it INSERTed or, on
 * a `(shipment, day, type)` dedupe hit against a non-terminal row, the existing row with a
 * refreshed payload (`escalation_service.py:175-219`, issue #96's partial-index predicate).
 *
 * There is no `code` field on this branch, which is how a caller tells the two apart.
 */
export type EscalateCreated = {
  escalation_id: string
  shipment_id: string
  facility_id: string
  driver_id: string | null
  escalation_type: string
  escalation_status: EscalationStatus
  severity_code: string
  policy_version: string | null
  recommendation_id: string | null
  payload: Record<string, unknown>
  dedupe_key: string
  created_at: string
  updated_at: string
}

export type EscalateResult = EscalatePreview | EscalateCreated

export function isEscalatePreview(result: EscalateResult): result is EscalatePreview {
  return (result as EscalatePreview).code === 'CONFIRMATION_REQUIRED'
}

/** `EscalateExceptionCommand.severity_code` -- a free `str(max_length=30)` server-side, but
 *  `SLA_BUDGET_MIN` only has budgets for these three, and anything else silently falls to
 *  `DEFAULT_SLA_BUDGET_MIN`. Offering the three that have a real budget is the honest set. */
export const ESCALATE_SEVERITY_CODES = ['HIGH', 'MEDIUM', 'LOW'] as const

/** Flow 6 -- resolve_escalation / cancel_escalation's `reason_code`
 *  (`Source: assumption, untested`, escalation_service.py RESOLVE/CANCEL_REASON_CODES). */
export const RESOLVE_REASON_CODES = ['ISSUE_FIXED'] as const
export const CANCEL_REASON_CODES = ['SHIPMENT_CANCELLED', 'DUPLICATE', 'CREATED_IN_ERROR'] as const
export type ResolveReasonCode = (typeof RESOLVE_REASON_CODES)[number]
export type CancelReasonCode = (typeof CANCEL_REASON_CODES)[number]

// ---------------------------------------------------------------------------------------------
// Co-pilot resolution suggestion (issue #57)
// ---------------------------------------------------------------------------------------------

/**
 * `GET /api/v1/operations/escalations/{id}/suggestion` --
 * `backend/app/services/ops_copilot.py::build_suggestion`.
 *
 * **Scope, decided by the owner 2026-08-31 and narrower than the design docs describe.** The
 * co-pilot suggests *which resolution action to take and why*. It does not summarise the thread
 * and it does not draft the coordinator's reply -- so `components.md` section 3's three
 * capabilities and `REQUIREMENTS.md`'s `FR-OPS-003` are not what this contract serves. Nothing in
 * this response ever carries driver-facing text; the only free-form strings are `rationale` and
 * the evidence labels, both of which are about the escalation, never addressed to the driver.
 */
export type SuggestionActionStatus = 'recommended' | 'available' | 'suppressed' | 'unavailable'

/** One §7.5.5 tool name, plus the two E5.2 added (`start_escalation_work` #56,
 *  `post_operations_message` #55). Spelled exactly as the backend spells them. */
export type SuggestionActionName =
  | 'acknowledge_escalation'
  | 'start_escalation_work'
  | 'reassign_escalation'
  | 'take_over_thread'
  | 'post_operations_message'
  | 'hand_back_thread'
  | 'resolve_escalation'
  | 'cancel_escalation'
  | 'request_sequencer_proposal'

export type SuggestionAction = {
  action: SuggestionActionName
  label: string
  status: SuggestionActionStatus
  /** Why it is not available/recommended -- `NOT_OWNER`, `NO_THREAD`, `NOT_IMPLEMENTED`,
   *  `SAFETY_HUMAN_ONLY`, `ALREADY_TERMINAL`, and the rest of `_classify_actions`'s set. */
  reason_code: string | null
  /** Only ever `{ reason_code }`, and only ever a value `resolve_escalation` /
   *  `cancel_escalation` actually accept. **Never a facility, carrier or driver id** -- asserted
   *  server-side by `test_no_action_argument_ever_carries_a_scope_id`. */
  arguments: { reason_code: string } | null
}

/** One fact the recommendation rests on, and the column it was read from. `source` is the whole
 *  point: it is what makes "never invent operational data" checkable by reading the panel. */
export type SuggestionEvidence = {
  code: string
  label: string
  source: string
}

/* ==============================================================================================
 * `request_sequencer_proposal` -- SS7.5.5's delegate to SS7.5.3 (issues #54/#49, FR-OPS-004)
 *
 * RECONCILED 2026-09-02 against the shipped route. SS7.5.5 says the delegate returns *"the same
 * shape SS7.5.3 already defines"*, and it genuinely does: `routers/operations.py`'s handler is typed
 * `-> SchedulingRunResult`, the identical Pydantic model `POST /scheduling/proposals` and
 * `GET /scheduling/runs/{id}` both return.
 *
 * **This surface deliberately types only the subset it renders.** SS5.1's diff itself belongs to the
 * planner (U93), and ops can never act on a row of it -- so the placement arrays are typed as
 * opaque counts rather than mirrored from `features/planner/lib/types.ts`. Copying the full shape
 * here would create a second definition of a contract this surface cannot use, and importing the
 * planner's would couple two surfaces that are deliberately independent.
 * ============================================================================================ */

/** SS5.1's own run scope, as the server reports it. */
export type SequencerHorizon = {
  start_ts: string
  end_ts: string
  end_reason: string
}

/**
 * The subset of `sequencer.ObjectiveValues` the handoff line names.
 *
 * `churn_count` is the one SS5.1 puts in words in its sample effect line ("promises moved 1"), and
 * the one the admin console's `P_churn` field would price. Every term is a real number on the wire
 * even when zero -- the server reports them all so that "contributed nothing" and "not measured"
 * stay distinguishable -- so these are not nullable.
 */
export type SequencerObjective = {
  churn_count: number
  promises_moved: number
  waiting_minutes_delta: number
  total_cost: number
}

/**
 * What `request_sequencer_proposal` returns -- `sequencer.SchedulingRunResult`.
 *
 * `RUN_ALREADY_ACTIVE` is SS5.1's debounce rule expressed as a return value ("at most one active run
 * per facility, serialised"), and `03-planner-dock-board/edge-cases.md` section 4 requires it be
 * rendered as *an expected, recoverable condition, not a failure*. The shipped route agrees and
 * returns **200 with a typed body in both outcomes** rather than a 409 -- so this is branched on
 * `code`, exactly like `acknowledge_escalation`'s `ALREADY_ACTIONED`.
 *
 * `counts` is the server's own per-category map, preferred over array lengths (which may be
 * truncated on a large facility). The placement arrays are omitted from this type entirely: ops
 * renders totals and a handoff, never a row.
 */
export type SequencerProposalResult = {
  as_of: string
  code: 'PROPOSED' | 'RUN_ALREADY_ACTIVE'
  scheduling_run_id: string
  facility_id: string
  facility_name: string | null
  /** Always `CAPACITY_INCIDENT` from this route -- the delegate pins it, so no client chooses it. */
  trigger_reason: string
  /** SS7.5.5: *"the `escalation_id` attached to the resulting `scheduling_run_id` ... the incident
   *  and the run stay linkable."* A real FK on `scheduling_runs`, echoed back so the handoff line
   *  can prove the linkage rather than assume it. */
  escalation_id: string | null
  status: string
  policy_version: string
  snapshot_hash: string
  horizon: SequencerHorizon
  counts: Record<string, number>
  objective: SequencerObjective
  explanation: string
  /** `RUN_ALREADY_ACTIVE` only -- which run is in the way. */
  active_run: Record<string, unknown> | null
}

export type ResolutionSuggestion = {
  as_of: string
  source: string
  /** `"deterministic:v1"` today. If this ever becomes LLM-backed the shape does not change, so
   *  this field is the only way a client can tell -- render it, do not drop it. */
  generator: string
  escalation_id: string
  escalation_type: EscalationReason
  escalation_status: EscalationStatus
  stepper_position: 0 | 1 | 2 | 3
  /** `null` is a first-class, expected outcome, not an error: six of the nine §7.4 reasons have
   *  no ops tool that fixes them, so the honest answer is the evidence with no recommendation. */
  recommended_action: SuggestionActionName | null
  rationale: string | null
  confidence: 'high' | 'medium' | null
  abstain_reason: { code: string; label: string } | null
  evidence: SuggestionEvidence[]
  actions: SuggestionAction[]
  payload_reason: string | null
}
