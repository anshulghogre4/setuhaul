import { cn } from '@/shared/lib/utils'
import { formatSlaRemaining, slaPosture } from '../lib/sla'
import type { EscalationStatus, SeverityCode } from '../lib/types'

/**
 * `00-foundations/components.md` section 16 (U60). Neutral filled/outline dots -- no hue.
 * Deliberately does not reuse the priority value-ramp or the promise-state chip's colours:
 * lifecycle position, urgency and promise state are three different facts.
 *
 * `CANCELLED` renders as a fifth, greyed terminal label replacing the stepper (never a
 * partially-filled trail, which would misleadingly suggest work in progress).
 *
 * **Position 2 (IN_PROGRESS) is real in this rendering logic but currently unreachable with live
 * data** -- issue #56 (G3): nothing in `escalation_service.py` ever writes
 * `escalation_status = 'IN_PROGRESS'`. This component still draws it correctly for whatever
 * `stepper_position` the API returns; it is not hidden or special-cased, because the gap is a
 * backend-completeness issue, not a reason to misrender the four positions the design specifies.
 */
const STEPS: { status: EscalationStatus; label: string }[] = [
  { status: 'OPEN', label: 'Open' },
  { status: 'ACKNOWLEDGED', label: 'Ack' },
  { status: 'IN_PROGRESS', label: 'In prog' },
  { status: 'RESOLVED', label: 'Resolved' },
]

export function EscalationStepper({
  status,
  position,
  severityCode,
  slaRemainingMin,
  owner,
  variant = 'compact',
}: {
  status: EscalationStatus
  position: 0 | 1 | 2 | 3
  severityCode: SeverityCode
  slaRemainingMin: number
  /** `null` = Unowned, rendered in `feedback-warning` colour per components.md section 2. */
  owner: string | null
  /** compact: steps + SLA clock only (queue row). full: adds owner + cause (detail pane). */
  variant?: 'compact' | 'full'
}) {
  const posture = slaPosture(severityCode, slaRemainingMin)
  const cancelled = status === 'CANCELLED'

  return (
    <div className="flex flex-col gap-1">
      {cancelled ? (
        <span className="text-body font-medium text-muted-foreground">Cancelled</span>
      ) : (
        <div className="flex items-center gap-1" role="img" aria-label={`Stage: ${STEPS[position]?.label ?? 'Open'}`}>
          {STEPS.map((step, i) => (
            <span key={step.status} className="flex items-center gap-1">
              <span
                aria-hidden="true"
                className={cn(
                  'size-2 rounded-full border-2 border-muted-foreground',
                  i <= position && 'bg-muted-foreground',
                )}
              />
              {i < STEPS.length - 1 ? (
                <span aria-hidden="true" className="h-px w-3 bg-border" />
              ) : null}
            </span>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
        {variant === 'full' && !cancelled ? (
          <span className="text-micro tracking-wide text-muted-foreground uppercase">
            {STEPS.map((s) => s.label).join('  ·  ')}
          </span>
        ) : null}
        {variant === 'full' ? (
          <span
            className={cn(
              'text-body font-medium',
              owner === null && 'text-warning-fg',
            )}
          >
            {owner ?? 'Unowned'}
          </span>
        ) : null}
        {!cancelled ? (
          <span
            className={cn(
              'font-data text-body tabular-nums',
              posture === 'ok' && 'text-muted-foreground',
              posture === 'warning' && 'text-sla-warning',
              posture === 'breach' && 'text-sla-breach font-semibold',
            )}
          >
            {formatSlaRemaining(slaRemainingMin)}
          </span>
        ) : null}
      </div>
    </div>
  )
}
