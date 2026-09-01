import { Ellipsis } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/shared/ui/dropdown-menu'

/**
 * The detail pane's overflow `[ ⋯ ]` (`screens.md` section 3, `stitch-prompts.md` prompt 7:
 * *"a ghost icon button (Lucide `ellipsis` 20px, `text-secondary`) holding Escalate, Reassign and
 * Cancel. These are deliberately not primary buttons — Acknowledge and Take over are the two
 * decisions this pane foregrounds."*).
 *
 * ## Rendered only once acknowledged, per the same sentence
 *
 * `screens.md` section 3 says these actions live here **"once acknowledged"**, so the trigger does
 * not render on an unowned escalation. That is not a cosmetic rule: `reassign_escalation` refuses
 * `NOT_ACKNOWLEDGED` server-side, and offering Escalate before anyone has claimed the case invites
 * a second case being opened on work nobody has looked at yet.
 *
 * ## Cancel is NOT duplicated here, and that is a flagged design fork rather than an omission
 *
 * The same file contradicts itself: section 3's prose puts Cancel in this menu, while sections 3
 * and 3b both **draw** it as a visible button (`[ Take over thread ] [ Cancel ]`, then
 * `[ Resolve ] [ Cancel ]`) in the pane's own action group. Both halves cannot ship. Putting it in
 * both places would give one irreversible terminal action two entry points, which
 * `00-foundations/components.md` section 19's destructive-action tiering argues against directly;
 * moving it here would delete the drawn group that `flows-and-states.md` Flow 6 depends on for the
 * Resolve/Cancel pairing ("two different terminal states ... not interchangeable done buttons"),
 * which only reads as a pair while the two sit together.
 *
 * **This build keeps the drawn group and leaves Cancel out of the menu**, and the menu says so
 * rather than staying silent about it. Flagged for the owner: either correct section 3's prose to
 * "Escalate and Reassign", or redraw 3/3b with Cancel removed from the action group.
 */
export function DetailOverflowMenu({
  onEscalate,
  reassignBlockedReason,
  busy,
}: {
  onEscalate: () => void
  /**
   * Why Reassign cannot be offered, or `null` if it can.
   *
   * Still non-null today: section 7.5.5 names no tool that returns a facility-scoped coordinator
   * list, and a free-text `new_owner_id` field would let this screen hand the server a user id it
   * chose -- exactly the client-supplied scope identifier M15 forbids. The item renders and
   * explains itself rather than disappearing (`components.md` foundations section 18's Inactive
   * contract), which is where this copy came from when it moved out of `owner-control.tsx`.
   */
  reassignBlockedReason: string | null
  busy?: boolean
}) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          // Named, not "…": the trigger's accessible name has to say what it opens, and the glyph
          // is `aria-hidden` below.
          aria-label="More actions"
          disabled={busy}
        >
          <Ellipsis aria-hidden="true" className="size-5" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="max-w-80">
        <DropdownMenuItem onSelect={onEscalate}>Escalate…</DropdownMenuItem>

        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-micro font-normal text-subtle-foreground">
          Reassign
        </DropdownMenuLabel>
        {reassignBlockedReason === null ? (
          <DropdownMenuItem disabled>Reassign is available</DropdownMenuItem>
        ) : (
          <DropdownMenuItem disabled className="whitespace-normal text-body">
            {reassignBlockedReason}
          </DropdownMenuItem>
        )}

        <DropdownMenuSeparator />
        <DropdownMenuLabel className="max-w-80 text-micro font-normal whitespace-normal text-subtle-foreground">
          Cancel stays with Resolve in the action group below — see this component&apos;s note on
          the design&apos;s own contradiction.
        </DropdownMenuLabel>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

/** The one sentence stating why Reassign is unavailable, kept next to the menu that renders it so
 *  the detail pane and any future call site cannot drift into two different explanations. */
export const REASSIGN_BLOCKED_REASON =
  'Reassigning needs a facility-scoped coordinator list, which has no backend read yet (no tool in §7.5.5 returns one). Not offered as a free-text id, since that would let this screen trust a client-supplied user id.'
