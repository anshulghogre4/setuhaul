import type {
  AffectedAppointment,
  EscalationQueueItem,
  ResolutionSuggestion,
  ThreadMessage,
} from '../lib/types'

/**
 * Fixtures for `/ops/_states` ONLY -- never imported by the live `/ops` route (`ops-console.tsx`
 * calls `lib/api.ts` against the real backend). Values are copied from `screens.md`'s own
 * rendered examples (ESC-104/102/099, DOCK-JAI-D3) rather than invented, same discipline as
 * `features/gallery/fixtures.ts`'s header comment for the shared shell.
 */

const NOW = Date.now()
const isoMinAgo = (min: number) => new Date(NOW - min * 60_000).toISOString()

export const ESCALATION_UNOWNED_BREACHING: EscalationQueueItem = {
  escalation_id: 'ESC-104',
  shipment_id: 'SHP1015',
  facility_id: 'FAC-JAI-01',
  driver_id: 'DRV010',
  escalation_type: 'NO_FEASIBLE_SLOT',
  escalation_status: 'OPEN',
  severity_code: 'HIGH',
  policy_version: 'v3',
  recommendation_id: null,
  payload: { reason: 'Reefer SHP1015 pinned to D5 (RULE003); D5 down 18:00-22:00 (DEVT002). No feasible slot in the search horizon.' },
  created_at: isoMinAgo(116),
  updated_at: isoMinAgo(116),
  owner_user_id: null,
  owner_name: null,
  stepper_position: 0,
  sla_remaining_min: 4.2,
  affected_shipments: null,
  // E5.2/#55: the queue read now carries the shipment's most recent thread. This row is
  // unacknowledged, so `take_over_thread` would refuse it with NOT_ACKNOWLEDGED -- which is
  // exactly what plate 7a demonstrates.
  thread_id: 'THR-1015',
  thread_status: 'OPEN',
}

export const ESCALATION_OWNED_NOTIFICATION_FAILED: EscalationQueueItem = {
  ...ESCALATION_UNOWNED_BREACHING,
  escalation_id: 'ESC-102',
  shipment_id: 'SHP1009',
  facility_id: 'FAC-GGN-01',
  escalation_type: 'NOTIFICATION_FAILED',
  escalation_status: 'ACKNOWLEDGED',
  severity_code: 'MEDIUM',
  owner_user_id: 'USR-DEMO-OPS',
  owner_name: 'Neha B.',
  stepper_position: 1,
  sla_remaining_min: 22,
  payload: { reason: 'Delivery-confirmation SMS failed in flight.' },
  // A NOTIFICATION_FAILED escalation legitimately has no chat thread -- `LEFT JOIN LATERAL`
  // returns NULL. The takeover control must say so rather than offering a dead button.
  thread_id: null,
  thread_status: null,
}

export const ESCALATION_AMBIGUOUS_SOFT: EscalationQueueItem = {
  ...ESCALATION_UNOWNED_BREACHING,
  escalation_id: 'ESC-099',
  shipment_id: 'DRV004',
  facility_id: 'FAC-JAI-01',
  escalation_type: 'AMBIGUOUS_SHIPMENT',
  escalation_status: 'ACKNOWLEDGED',
  severity_code: 'LOW',
  owner_user_id: 'USR-DEMO-OPS',
  owner_name: 'Neha B.',
  stepper_position: 1,
  sla_remaining_min: 12,
  thread_id: 'THR-0994',
  thread_status: 'OPEN',
}

export const ESCALATION_UNROUTABLE: EscalationQueueItem = {
  ...ESCALATION_UNOWNED_BREACHING,
  escalation_id: 'ESC-108',
  escalation_type: 'NOTIFICATION_UNROUTABLE',
  payload: { reason: 'No valid phone or email on file for this driver.' },
}

export const ESCALATION_WAREHOUSE_CONFLICT: EscalationQueueItem = {
  ...ESCALATION_UNOWNED_BREACHING,
  escalation_id: 'ESC-111',
  escalation_type: 'WAREHOUSE_REPLY_CONFLICT',
  payload: {
    reason: "Warehouse reply names a different dock than the stored appointment.",
    stored: { dock_id: 'D5', window: '18:00-22:00' },
    reply: { dock_id: 'D7', window: '18:00-20:00' },
  },
}

export const ESCALATION_RESOLVED: EscalationQueueItem = {
  ...ESCALATION_UNOWNED_BREACHING,
  escalation_id: 'ESC-090',
  escalation_status: 'RESOLVED',
  stepper_position: 3,
  owner_user_id: 'USR-DEMO-OPS',
  owner_name: 'Neha B.',
}

const AFFECTED: AffectedAppointment[] = [
  { appointment_id: 'APT1005', shipment_id: 'SHP1005', appointment_status: 'CONFIRMED', window_start: isoMinAgo(60), window_end: isoMinAgo(-60) },
  { appointment_id: 'APT1009', shipment_id: 'SHP1009', appointment_status: 'PENDING_CONFIRMATION', window_start: isoMinAgo(30), window_end: isoMinAgo(-30) },
  { appointment_id: 'APT1013', shipment_id: 'SHP1013', appointment_status: 'CONFIRMED', window_start: isoMinAgo(10), window_end: isoMinAgo(-90) },
  { appointment_id: 'APT1014', shipment_id: 'SHP1014', appointment_status: 'CONFIRMED', window_start: isoMinAgo(5), window_end: isoMinAgo(-100) },
]

export const ESCALATION_CAPACITY_INCIDENT: EscalationQueueItem = {
  ...ESCALATION_UNOWNED_BREACHING,
  escalation_id: 'ESC-120',
  escalation_type: 'CAPACITY_EVENT_CASCADE',
  severity_code: 'HIGH',
  payload: { dock_id: 'DOCK-JAI-D3', reason: 'Dock block overlaps live appointments.', affected_count: AFFECTED.length },
  affected_shipments: AFFECTED,
}

export const QUEUE_FIXTURE: EscalationQueueItem[] = [
  ESCALATION_UNOWNED_BREACHING,
  ESCALATION_OWNED_NOTIFICATION_FAILED,
  ESCALATION_AMBIGUOUS_SOFT,
  ESCALATION_CAPACITY_INCIDENT,
]

/** Acknowledged, owned, and the thread is already `ESCALATED` -- prompt 8's state. This is the one
 *  fixture where the composer is live and `[ Hand back ]` replaces `[ Take over thread ]`. */
export const ESCALATION_UNDER_TAKEOVER: EscalationQueueItem = {
  ...ESCALATION_AMBIGUOUS_SOFT,
  escalation_id: 'ESC-104',
  shipment_id: 'SHP1015',
  escalation_status: 'IN_PROGRESS',
  stepper_position: 2,
  owner_name: 'You (Anshul G.)',
  owner_user_id: 'USR-DEMO-OPS',
  thread_id: 'THR-1015',
  thread_status: 'ESCALATED',
}

/** `screens.md` section 3's own transcript, plus the takeover divider prompt 8 specifies and one
 *  `OPERATIONS` reply -- Fork G's "the thread never renders an AGENT or OPERATIONS message" gap,
 *  which the board could not show and this gallery now can. */
export const THREAD_FIXTURE: ThreadMessage[] = [
  {
    chat_message_id: 'MSG-001',
    thread_id: 'THR-1015',
    sender_type: 'DRIVER',
    sender_reference: 'DRV010',
    sender_name: 'Ravi K.',
    message_text: 'Still waiting on a dock, what is happening?',
    message_ts: isoMinAgo(46),
  },
  {
    chat_message_id: 'MSG-002',
    thread_id: 'THR-1015',
    sender_type: 'AGENT',
    sender_reference: null,
    sender_name: null,
    message_text:
      'I could not find a feasible slot in the search horizon. I have passed this to operations.',
    message_ts: isoMinAgo(45),
  },
  {
    chat_message_id: 'MSG-003',
    thread_id: 'THR-1015',
    sender_type: 'SYSTEM',
    sender_reference: 'USR-DEMO-OPS',
    sender_name: 'Anshul G.',
    message_text: 'Anshul G. from Operations has joined this conversation.',
    message_ts: isoMinAgo(8),
  },
  {
    chat_message_id: 'MSG-004',
    thread_id: 'THR-1015',
    sender_type: 'OPERATIONS',
    sender_reference: 'USR-DEMO-OPS',
    sender_name: 'Anshul G.',
    message_text: "D5 reopens after 22:00. I can hold 22:15 for you -- does that work?",
    message_ts: isoMinAgo(6),
  },
]

// ---------------------------------------------------------------------------------------------
// Co-pilot suggestions (issue #57), prompts 12 and 13
// ---------------------------------------------------------------------------------------------

/**
 * Copied from the shapes `backend/app/services/ops_copilot.py::build_suggestion` actually
 * produces -- the `AMBIGUOUS_SHIPMENT` branch and the `CAPACITY_EVENT_CASCADE` abstention -- not
 * composed by hand to look good on the board. Two states, because they are the two the feature
 * exists to distinguish: a confident recommendation, and an honest refusal to make one.
 */
export const SUGGESTION_RECOMMENDED: ResolutionSuggestion = {
  as_of: new Date(NOW).toISOString(),
  source: 'postgresql',
  generator: 'deterministic:v1',
  escalation_id: 'ESC-102',
  escalation_type: 'AMBIGUOUS_SHIPMENT',
  escalation_status: 'ACKNOWLEDGED',
  stepper_position: 1,
  recommended_action: 'take_over_thread',
  rationale:
    'The assistant could not tell which shipment the driver means. Flow 1 names taking over the ' +
    'thread as this reason’s resolution — a person asks, the assistant stops guessing.',
  confidence: 'high',
  abstain_reason: null,
  evidence: [
    { code: 'OWNED', label: 'Owned by Anshul G.', source: 'escalation_queue.owner_user_id' },
    {
      code: 'NO_CURRENT_APPOINTMENT',
      label: 'The shipment holds no live appointment.',
      source: 'appointments (is_current = 1)',
    },
    {
      code: 'DRIVER_SPOKE_LAST',
      label: 'The driver wrote last, 40 minutes ago, and nobody has answered.',
      source: 'chat_messages.sender_type / message_ts',
    },
  ],
  actions: [
    { action: 'acknowledge_escalation', label: 'Acknowledge', status: 'unavailable', reason_code: 'ALREADY_ACKNOWLEDGED', arguments: null },
    { action: 'start_escalation_work', label: 'Mark in progress', status: 'available', reason_code: null, arguments: null },
    { action: 'reassign_escalation', label: 'Reassign', status: 'available', reason_code: null, arguments: null },
    { action: 'take_over_thread', label: 'Take over thread', status: 'recommended', reason_code: null, arguments: null },
    { action: 'post_operations_message', label: 'Reply in the thread', status: 'unavailable', reason_code: 'NOT_TAKEN_OVER', arguments: null },
    { action: 'hand_back_thread', label: 'Hand back', status: 'unavailable', reason_code: 'NOT_TAKEN_OVER', arguments: null },
    { action: 'resolve_escalation', label: 'Resolve', status: 'available', reason_code: null, arguments: { reason_code: 'ISSUE_FIXED' } },
    { action: 'cancel_escalation', label: 'Cancel', status: 'available', reason_code: null, arguments: null },
    { action: 'request_sequencer_proposal', label: 'Request sequencer proposal', status: 'unavailable', reason_code: 'NOT_IMPLEMENTED', arguments: null },
  ],
  payload_reason: null,
}

/** The abstention state, which is the designed outcome for six of §7.4’s nine reasons --
 *  here the capacity cascade, whose correct action is a sequencer proposal that is not built. */
export const SUGGESTION_ABSTAINED: ResolutionSuggestion = {
  ...SUGGESTION_RECOMMENDED,
  escalation_id: 'ESC-099',
  escalation_type: 'CAPACITY_EVENT_CASCADE',
  recommended_action: null,
  rationale: null,
  confidence: null,
  abstain_reason: {
    code: 'SEQUENCER_UNBUILT',
    label:
      'The right move is a sequencer proposal, and the sequencer is not built yet (issues #54, ' +
      '#49). No other ops action fixes a capacity cascade.',
  },
  evidence: [
    { code: 'OWNED', label: 'Owned by Anshul G.', source: 'escalation_queue.owner_user_id' },
    {
      code: 'AFFECTED_SHIPMENTS',
      label: '4 appointments were stranded by the block on DOCK-JAI-D3.',
      source: 'escalation_queue.payload_json.affected_count',
    },
    {
      code: 'SLA_BREACHED',
      label: 'Past its SLA budget by 35 minutes.',
      source:
        'derived from escalation_queue.created_at + SLA_BUDGET_MIN (Source: assumption, untested)',
    },
  ],
  actions: SUGGESTION_RECOMMENDED.actions.map((a) =>
    a.status === 'recommended' ? { ...a, status: 'available' as const } : a,
  ),
}

/**
 * **A live reason `REASON_META` has no entry for.** Not hypothetical: as of 2026-08-31 the live
 * `escalation_queue` holds 151 open rows carrying `REQUIRES_DOCK_REASSIGNMENT` or
 * `REQUIRES_TIME_RESOLUTION` across all six facilities, and exactly one carrying a §7.4 reason.
 * Those two are D12's backfill worklist types -- real, system-generated, and deliberately absent
 * from §7.4's nine (`escalation_service.py`'s `ESCALATION_TYPES` comment says so outright).
 *
 * The cast is the point: the backend genuinely returns a value outside `EscalationReason`, so the
 * fixture has to reproduce that rather than pretend the union is exhaustive.
 */
export const ESCALATION_UNMAPPED_REASON: EscalationQueueItem = {
  ...ESCALATION_UNOWNED_BREACHING,
  escalation_id: 'ESC-D1BF-TIME-APT1014A',
  escalation_type: 'REQUIRES_TIME_RESOLUTION' as EscalationQueueItem['escalation_type'],
}
