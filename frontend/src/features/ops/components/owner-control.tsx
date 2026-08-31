import { useId, useState } from 'react'

import { Button } from '@/shared/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/shared/ui/dropdown-menu'
import { cn } from '@/shared/lib/utils'

/**
 * `components.md` (this folder) section 2, U92. "Unowned -> [ Acknowledge ]" before,
 * "Name -> [ Reassign v ] " after. Acknowledge names the actor and advances the stepper to
 * ACKNOWLEDGED in one action -- no separate assignment step.
 *
 * Reassign's coordinator list is meant to be scoped to the caller's own facility/team
 * (`auth-and-scoping.md`). There is no `list_coordinators`-shaped read in section 7.5.5's catalog
 * and none was found in `backend/app/`, so the combobox is deliberately not built against a live
 * list here -- offering a free-text `new_owner_id` field would let a coordinator type an
 * arbitrary user id, which is exactly the kind of client-trusted identifier M15 forbids. Reassign
 * is therefore Inactive (not Hidden -- the action is real and will work the moment a scoped
 * coordinator list exists), with an inline explanation, rather than a fake dropdown of one name.
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
  const [explain, setExplain] = useState(false)
  // Issue #91: this was the literal string "reassign-explain", which collides the moment two
  // OwnerControls render on one page -- the states gallery renders six, so six elements shared
  // one id and every `aria-describedby` pointed at the first. `useId` is per-instance.
  // React 19.2.8 emits `_r_<n>_` (verified in the installed react-dom, and live in the rendered
  // DOM as `radix-_r_0_`) -- underscores, not the 19.0 `:r0:` colons and not 19.1's `«r0»`, so
  // these ids are valid CSS selectors and safe for querySelector/getElementById.
  const explainId = useId()

  if (ownerName === null) {
    return (
      <Button variant="constructive" onClick={onAcknowledge} disabled={busy}>
        Acknowledge
      </Button>
    )
  }

  return (
    <div className="flex flex-col gap-1">
      <DropdownMenu open={explain} onOpenChange={setExplain}>
        <DropdownMenuTrigger asChild>
          <Button
            variant="neutral"
            aria-describedby={explainId}
            onClick={() => setExplain(true)}
          >
            Reassign
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" className="max-w-72">
          <DropdownMenuItem disabled className={cn('whitespace-normal text-body')}>
            Reassigning needs a facility-scoped coordinator list, which has no backend read yet
            (no tool in section 7.5.5 returns one). Not offered as a free-text id, since that would
            let this screen trust a client-supplied user id.
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <span id={explainId} className="sr-only">
        Reassign is not available: no coordinator list endpoint exists yet.
      </span>
    </div>
  )
}
