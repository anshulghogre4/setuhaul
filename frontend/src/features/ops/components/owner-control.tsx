import { Button } from '@/shared/ui/button'

/**
 * `components.md` (this folder) section 2, U92. "Unowned -> [ Acknowledge ]". Acknowledge names
 * the actor and advances the stepper to ACKNOWLEDGED in one action -- no separate assignment step.
 *
 * ## Reassign moved out of this component (2026-09-01)
 *
 * Section 2's anatomy draws the owned state as `[ Reassign ▾ ]` here, but `screens.md` section 3
 * and `stitch-prompts.md` prompt 7 both put Reassign in the detail pane's overflow `[ ⋯ ]` "once
 * acknowledged ... deliberately not primary buttons". Those are the same action in two places, and
 * the overflow is the more specific instruction (it names the exact control and gives the reason),
 * so it won. See `overflow-menu.tsx`, which now carries the Inactive explanation this file used to.
 *
 * The owner's *name* is not lost by that move: the full-variant stepper renders it directly above
 * (`escalation-stepper.tsx`, `components.md` section 16), in the one `feedback-warning` token
 * section 2 requires for "Unowned". So an owned escalation renders no control here at all rather
 * than a second copy of a fact already on screen.
 */
export function OwnerControl({
  ownerName,
  onAcknowledge,
  busy,
}: {
  ownerName: string | null
  onAcknowledge: () => void
  busy?: boolean
}) {
  if (ownerName !== null) return null

  return (
    <Button variant="constructive" onClick={onAcknowledge} disabled={busy}>
      Acknowledge
    </Button>
  )
}
