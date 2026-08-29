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

import type { FleetExceptionItem } from './types'

/**
 * The exception summary row's icon and its plain-language status clause.
 *
 * ## Two rules this file is the enforcement point for
 *
 * 1. **Status only** (`05-carrier-portal/components.md` §3, §7.5.6). No owner, no "assigned
 *    to", no SLA countdown, no `OPEN → ACKNOWLEDGED → RESOLVED` stepper, no priority, no
 *    internal note. The carrier learns *that* something is being handled, never how. The
 *    backend already enforces this by column allowlist (`repositories/carrier.py`'s
 *    `_OPEN_EXCEPTION_ITEMS_SQL` selects no such field) — this file must not reintroduce the
 *    apparatus by deriving it from what *is* returned.
 * 2. **Use the three exact strings, do not rewrite them** (`stitch-prompts.md` §4). They are
 *    the only three authorised clauses on this surface, and the mapping below is a mapping onto
 *    them, never a fourth phrasing invented for a reason code the design did not enumerate.
 *
 * ## Why so many reason codes map onto one clause
 *
 * `escalation_queue_escalation_type_check` (migration `20260823100000_e24_...`) admits eleven
 * values and `driver_exceptions_exception_type_check` (baseline, line 249) admits seven — 18
 * codes against the design's three sentences. Two of the three name a specific cause
 * (`NO_FEASIBLE_SLOT`, `PENDING_EXPIRED_UNACTIONED`); the third, "Awaiting operations review",
 * is the generic "a human has this" clause and is accurate for every remaining code. Inventing
 * fifteen new sentences would be inventing product copy; collapsing them onto the authorised
 * generic one is not.
 *
 * The **icon** still varies, because `iconography.md`'s Escalation reason table assigns one per
 * code and `stitch-prompts.md` §4 names four of them by hand (`calendar-x`, `timer-off`,
 * `shield-alert`, `network`). So the row keeps a distinguishing glyph without the copy claiming
 * a distinction the design never wrote. Icon is never the only channel (U30) — the shipment id,
 * driver and clause carry the row on their own.
 */

/** `iconography.md` §"Escalation reason", verbatim. Nine codes, nine glyphs. */
const ESCALATION_ICON: Record<string, LucideIcon> = {
  NO_FEASIBLE_SLOT: CalendarX,
  PENDING_EXPIRED_UNACTIONED: TimerOff,
  AMBIGUOUS_SHIPMENT: CircleHelp,
  LOW_CONFIDENCE_ETA: AlertTriangle,
  WAREHOUSE_REPLY_CONFLICT: GitCompare,
  NOTIFICATION_FAILED: MailWarning,
  NOTIFICATION_UNROUTABLE: MailX,
  SAFETY_OR_REGULATED: ShieldAlert,
  CAPACITY_EVENT_CASCADE: Network,
  // The two D12/D9 worklist categories the same migration keeps. `iconography.md`'s table does
  // not name them (it covers §7.4's eight/nine reasons); both are dock/time resolution work, so
  // they take the capacity glyph rather than a new one invented here.
  REQUIRES_TIME_RESOLUTION: TimerOff,
  REQUIRES_DOCK_REASSIGNMENT: Network,
}

/** `driver_exceptions.exception_type` — a driver-reported problem, not an escalation reason, so
 *  `iconography.md`'s escalation table does not cover it. All seven are "a human is reviewing
 *  this" from the carrier's side, and all seven take the generic clause. */
const DRIVER_EXCEPTION_ICON: Record<string, LucideIcon> = {
  DELAY: AlertTriangle,
  BREAKDOWN: AlertTriangle,
  TRAFFIC: AlertTriangle,
  WEATHER: AlertTriangle,
  EARLY_ARRIVAL: AlertTriangle,
  DOCK_UNAVAILABLE: Network,
  UNKNOWN: CircleHelp,
}

export type ExceptionPresentation = {
  icon: LucideIcon
  /** The part before the timestamp. One of exactly three authorised strings. */
  clause: string
  /** The verb the timestamp attaches to, also from the authorised strings. */
  timePrefix: string
}

export function presentException(item: FleetExceptionItem): ExceptionPresentation {
  const code = item.reason_code

  if (item.source === 'ESCALATION') {
    if (code === 'NO_FEASIBLE_SLOT') {
      return { icon: CalendarX, clause: 'No feasible slot', timePrefix: 'escalated' }
    }
    if (code === 'PENDING_EXPIRED_UNACTIONED') {
      return {
        icon: TimerOff,
        clause: 'No planner decision in time',
        timePrefix: 'released and escalated',
      }
    }
    return {
      icon: ESCALATION_ICON[code] ?? CircleHelp,
      clause: 'Awaiting operations review',
      timePrefix: 'raised',
    }
  }

  return {
    icon: DRIVER_EXCEPTION_ICON[code] ?? CircleHelp,
    clause: 'Awaiting operations review',
    timePrefix: 'raised',
  }
}
