import type { AffectedAppointment, EscalationQueueItem } from '../lib/types'

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
