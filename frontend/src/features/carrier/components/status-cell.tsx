import { TriangleAlert } from 'lucide-react'

import { PromiseChip } from '@/features/driver/components/promise-chip'
import { promiseCell } from '../lib/promise'
import type { LivePromiseState } from '../lib/types'

/**
 * The shipments table's status cell — `stitch-prompts.md` §3, `05-carrier-portal/components.md`
 * §2, `edge-cases.md` #3.
 *
 * A promise chip and an exception marker can appear **together** on one row: a shipment that is
 * `PENDING_CONFIRMATION` *and* has an open escalation is normal, not a bug, and neither section
 * de-duplicates against the other. Where no slot has ever been offered the chip is absent and
 * the marker stands alone.
 *
 * ## The exception marker's shape is load-bearing
 *
 * **No border, no fill** — amber text and a 14px `alert-triangle`, nothing more. An amber
 * *bordered pill* is visually a `HELD` promise chip, and confusing "this shipment has an open
 * exception" with "a dock slot is held for 90 seconds" is precisely the misread the four-state
 * chip system exists to prevent (`stitch-prompts.md` §1 and §3 both exclude it by name). Do not
 * give this a border to "tidy it up".
 *
 * ## Why the chip is imported from `features/driver/`
 *
 * `05-carrier-portal/components.md` §2 is explicit: **"Uses the shared promise-state chip
 * verbatim — no carrier-specific restyling. Consistency here matters more than differentiation:
 * a carrier reading a `PENDING_CONFIRMATION` chip should recognise it instantly from the exact
 * same visual language a planner uses."** The component E5.1 built is that chip — fully
 * prop-driven, and with no `expiresAt` passed it renders its static, non-counting branch, which
 * is exactly this surface's read-only consumption. Re-implementing the single most important
 * component in the product for one surface would be the worse defect by a wide margin.
 *
 * Its *home* is wrong, though: it belongs in `shared/ui/`, not inside one surface's folder. That
 * move is a shared-infrastructure change and is reported to the coordinator rather than made
 * here, since `shared/**` is being read by concurrent builds.
 *
 * **One recorded deviation that comes with the reuse**: the shared chip renders its label at
 * `text-body` (14px), from the owner's 2026-08-27 Fork B decision; `stitch-prompts.md` §1
 * specifies 12px for this surface's chips. The 14px is the later, owner-made decision applied to
 * the shared component, and honouring the prompt's 12px here would mean forking the chip, which
 * §2 forbids. Flagged for the owner, not silently resolved.
 */
export function StatusCell({
  promiseState,
  hasOpenException,
  shownHeldEnabled,
}: {
  promiseState: LivePromiseState | null
  hasOpenException: boolean
  shownHeldEnabled: boolean
}) {
  const cell = promiseCell(promiseState, shownHeldEnabled)

  return (
    <span className="flex flex-nowrap items-center gap-2">
      {cell.kind === 'chip' ? <PromiseChip state={cell.state} className="shrink-0" /> : null}
      {cell.kind === 'plain' ? (
        <span className="text-body text-muted-foreground">{cell.label}</span>
      ) : null}
      {cell.kind === 'none' && !hasOpenException ? (
        <>
          {/* An explicit dash, never a blank: `0`, `—` and absent are three different facts and
              must not look alike (`stitch-prompts.md` §6). The spoken form is what carries the
              meaning for AT, since a bare dash announces as nothing useful. */}
          <span aria-hidden="true" className="text-body text-muted-foreground">
            —
          </span>
          <span className="sr-only">{cell.spoken}</span>
        </>
      ) : null}

      {/* `text-label` carries 0.04em tracking from the type scale; this marker is sentence-case
          running text, not a label, so the tracking is reset rather than inherited. */}
      {hasOpenException ? (
        <span className="inline-flex shrink-0 items-center gap-1 text-label font-semibold tracking-normal whitespace-nowrap text-warning-fg">
          <TriangleAlert className="size-3.5" aria-hidden="true" strokeWidth={2} />
          Exception open
        </span>
      ) : null}
    </span>
  )
}
