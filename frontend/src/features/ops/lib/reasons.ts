import {
  AlertTriangle,
  CalendarX,
  CircleHelp,
  GitCompare,
  MailWarning,
  MailX,
  Network,
  ShieldAlert,
  TimerOff,
  type LucideIcon,
} from 'lucide-react'

import type { EscalationReason } from './types'

/** `iconography.md` "Escalation reason" table -- rendered inside the stepper's cause line and
 *  the queue row (`components.md` section 16 / this surface's `components.md` section 1). Text
 *  label + icon, never icon alone (U30). */
export const REASON_META: Record<EscalationReason, { label: string; icon: LucideIcon }> = {
  NO_FEASIBLE_SLOT: { label: 'No feasible slot', icon: CalendarX },
  PENDING_EXPIRED_UNACTIONED: { label: 'Pending expired, unactioned', icon: TimerOff },
  AMBIGUOUS_SHIPMENT: { label: 'Ambiguous shipment', icon: CircleHelp },
  LOW_CONFIDENCE_ETA: { label: 'Low-confidence ETA', icon: AlertTriangle },
  WAREHOUSE_REPLY_CONFLICT: { label: 'Warehouse reply conflict', icon: GitCompare },
  NOTIFICATION_FAILED: { label: 'Notification failed', icon: MailWarning },
  NOTIFICATION_UNROUTABLE: { label: 'Notification unroutable', icon: MailX },
  SAFETY_OR_REGULATED: { label: 'Safety / regulated', icon: ShieldAlert },
  CAPACITY_EVENT_CASCADE: { label: 'Capacity incident', icon: Network },
}

/** SS7.4's "SLA posture" vocabulary the mockup renders ("12m (soft posture)") has no backend
 *  field -- `screens.md` section 2 / implementation-spec section 2.3. Not surfaced here as a
 *  distinct label; `sla.ts`'s ok/warning/breach posture (computed from `sla_remaining_min`) is
 *  the only posture concept this build renders, and it is named as the substitute, not silently
 *  treated as the same thing. */
export const REASON_ORDER: EscalationReason[] = Object.keys(REASON_META) as EscalationReason[]
