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

/**
 * Reasons that exist in `escalation_queue` but are **not** among §7.4's nine.
 *
 * `REQUIRES_TIME_RESOLUTION` and `REQUIRES_DOCK_REASSIGNMENT` are D12's backfill worklist types --
 * `escalation_service.py`'s `ESCALATION_TYPES` comment names them and deliberately excludes them
 * from the enum a caller may pass, because they are system-generated during the E1.1 backfill.
 * `get_exception_queue` does not filter on type, so they reach this console.
 *
 * **This is not hypothetical and it was not a style concern.** Measured against the live database
 * on 2026-08-31: 151 of the 152 open `escalation_queue` rows carry one of these two, across all
 * six facilities; exactly one row carries a §7.4 reason. With `REASON_META` keyed only by the
 * nine, `REASON_META[item.escalation_type]` returned `undefined` and
 * `escalation-queue-row.tsx`'s `reason.icon` threw
 * `TypeError: Cannot read properties of undefined (reading 'icon')` on the first row it rendered
 * -- reproduced in Chromium, which rendered a blank page. On `/ops` the shell's
 * `RegionErrorBoundary` would catch it and replace the whole console content instead. Either way
 * the ops console was unusable against current live data.
 *
 * Found while verifying issue #57 against real rows. Fixed here rather than at the three call
 * sites so the lookup is total for everyone who indexes it, present and future -- the same
 * discipline `lib/types.ts` already applies to `ThreadStatus` ("copied in full... so an
 * unexpected one renders as itself instead of falling through a `never`").
 */
type BackfillReason = 'REQUIRES_TIME_RESOLUTION' | 'REQUIRES_DOCK_REASSIGNMENT'

/** `iconography.md` "Escalation reason" table -- rendered inside the stepper's cause line and
 *  the queue row (`components.md` section 16 / this surface's `components.md` section 1). Text
 *  label + icon, never icon alone (U30).
 *
 *  Keyed by §7.4's nine **plus** the two backfill reasons above, so indexing it with any value
 *  the API actually returns yields an entry rather than `undefined`. Call sites index it with an
 *  `EscalationReason`, a subset of these keys, so nothing at a call site had to change. */
export const REASON_META: Record<
  EscalationReason | BackfillReason,
  { label: string; icon: LucideIcon }
> = {
  NO_FEASIBLE_SLOT: { label: 'No feasible slot', icon: CalendarX },
  PENDING_EXPIRED_UNACTIONED: { label: 'Pending expired, unactioned', icon: TimerOff },
  AMBIGUOUS_SHIPMENT: { label: 'Ambiguous shipment', icon: CircleHelp },
  LOW_CONFIDENCE_ETA: { label: 'Low-confidence ETA', icon: AlertTriangle },
  WAREHOUSE_REPLY_CONFLICT: { label: 'Warehouse reply conflict', icon: GitCompare },
  NOTIFICATION_FAILED: { label: 'Notification failed', icon: MailWarning },
  NOTIFICATION_UNROUTABLE: { label: 'Notification unroutable', icon: MailX },
  SAFETY_OR_REGULATED: { label: 'Safety / regulated', icon: ShieldAlert },
  CAPACITY_EVENT_CASCADE: { label: 'Capacity incident', icon: Network },
  // Labelled from what the backfill actually means (`supabase/migrations/` E1.1 / D12), and
  // given the neutral `CircleHelp` rather than a severity-coloured icon: these are worklist
  // items, not §7.4 exceptions, and dressing them as the latter would overstate them.
  REQUIRES_TIME_RESOLUTION: { label: 'Needs a time resolved', icon: CircleHelp },
  REQUIRES_DOCK_REASSIGNMENT: { label: 'Needs a dock reassigned', icon: CircleHelp },
}

/** SS7.4's "SLA posture" vocabulary the mockup renders ("12m (soft posture)") has no backend
 *  field -- `screens.md` section 2 / implementation-spec section 2.3. Not surfaced here as a
 *  distinct label; `sla.ts`'s ok/warning/breach posture (computed from `sla_remaining_min`) is
 *  the only posture concept this build renders, and it is named as the substitute, not silently
 *  treated as the same thing. */
/** The reason **filter** stays §7.4's nine, deliberately -- it is no longer `Object.keys` now
 *  that the lookup above carries two extra keys. Offering "Needs a dock reassigned" as a filter
 *  would present a backfill worklist as a peer of the escalation vocabulary, which is a product
 *  claim this build has no grounds to make. The rows still render; they are just not a filter. */
export const REASON_ORDER: EscalationReason[] = [
  'NO_FEASIBLE_SLOT',
  'PENDING_EXPIRED_UNACTIONED',
  'AMBIGUOUS_SHIPMENT',
  'LOW_CONFIDENCE_ETA',
  'WAREHOUSE_REPLY_CONFLICT',
  'NOTIFICATION_FAILED',
  'NOTIFICATION_UNROUTABLE',
  'SAFETY_OR_REGULATED',
  'CAPACITY_EVENT_CASCADE',
]
