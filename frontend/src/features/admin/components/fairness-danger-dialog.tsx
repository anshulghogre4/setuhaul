import { TriangleAlert } from 'lucide-react'
import { useEffect, useId, useState } from 'react'

import { Button } from '@/shared/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'
import { FAIRNESS_KEY } from '../lib/policy'

/**
 * Screen 9 — the fairness-term Danger-Zone typed confirmation.
 *
 * `06-admin-console/stitch-prompts.md` §9 · `screens.md` §4 · `components.md` §4 ·
 * `flows-and-states.md` Flow 7 · `edge-cases.md` #6 · `SOLUTION_DESIGN.md` §D7 / §5 Stage 2.
 * **FR-ADM-007.**
 *
 * ## What this dialog does, and the far longer list of what it does not
 *
 * Flow 7 step 2, quoted because it is the whole contract: *"On confirming, `w_fairness` becomes an
 * editable field in the ordinary weight editor (§3) rather than immediately publishing anything —
 * enabling the *term* and *publishing a policy that uses a non-zero value* remain two separate
 * steps, both still gated by Flow 6's simulate-before-publish discipline."*
 *
 * So this dialog **writes nothing, calls nothing, and publishes nothing**. It flips one piece of
 * client state. The prompt's exclusion list is implemented literally: no publish action, no numeric
 * input for the fairness value (that lives in the ordinary editor afterwards), no "learn more"
 * link, no generic "Are you sure?", no illustration beyond the single 20px icon.
 *
 * ## Amber, not red, and that distinction is load-bearing
 *
 * The prompt calls it out explicitly: *"this dialog is AMBER, not red. Red in this product means
 * danger — expiry, conflict, an action that ends something for another person. Enabling a policy
 * term is a risk decision, not a destruction."* Hence `warning-*` tokens throughout and the
 * `cautionary` button variant — which `shared/ui/button.tsx` already documents as "escalates or
 * hands off", exactly the semantics wanted, rather than `destructive`.
 *
 * ## Why the confirm button is genuinely disabled here, unlike most of this codebase
 *
 * This surface's house style is Inactive-not-Disabled (`components.md` foundations §18) — a control
 * that explains itself on activation. **This one is the deliberate exception**, because the prompt
 * says so (*"genuinely disabled until the typed value matches ... with the reason in a tooltip"*)
 * and because the reason is already on screen one line above it as the field's own label. A control
 * whose explanation is the label directly above it has nothing to add on activation.
 *
 * ## Disabling again is NOT gated, deliberately
 *
 * Flow 7 step 3: *"Disabling it (setting back to 0) is the ordinary weight-field path, not a second
 * Danger-zone gate — the friction is specifically on *turning it on* ... returning to the safe
 * default doesn't need the same ceremony."* So there is no counterpart dialog anywhere in this
 * folder, and that absence is the design rather than an omission.
 */
export function FairnessDangerDialog({
  open,
  onOpenChange,
  onEnable,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Makes `w_fairness` editable in the ordinary weight editor. Publishes nothing. */
  onEnable: () => void
}) {
  const [typed, setTyped] = useState('')
  const fieldId = useId()
  const whyId = useId()

  // Cleared on every open rather than on close: a dialog reopened with the phrase still in the box
  // would present an already-armed confirm button to someone who has not read the stakes panel
  // this time round.
  useEffect(() => {
    if (open) setTyped('')
  }, [open])

  // Exact-match, case-sensitive, trimmed only at the ends. A case-insensitive compare would make
  // "enable fairness" pass, which defeats the point of a typed confirmation: the friction IS the
  // deliberate act of reproducing the phrase.
  const matches = typed.trim() === CONFIRM_PHRASE

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[30rem]">
        <DialogHeader>
          <DialogTitle>Enable the fairness term</DialogTitle>
        </DialogHeader>

        {/* The stakes panel. `components.md` §4: "Copy states the actual business stakes, not just
            'advanced setting'." Verbatim from prompt 9 — this is the one place in the product where
            the exact sentences were specified and there is no reason to paraphrase them. */}
        <div className="flex items-start gap-3 rounded-md border border-warning-border bg-warning-bg px-4 py-3 text-warning-fg">
          <TriangleAlert className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
          <p className="text-supporting">
            This changes how every future ranking decision balances urgency against carrier
            concentration. Watch the carrier-concentration canary after publishing — if the data
            turns ugly, set the weight back to 0.
          </p>
        </div>

        <div className="flex flex-col gap-2 text-body text-muted-foreground">
          <p>
            Enabling makes <span className="font-data">{FAIRNESS_KEY}</span> editable in the weight
            editor. It does not publish anything. Any non-zero value still has to be simulated and
            published like every other weight.
          </p>
          {/* Beyond the artboard, and deliberately: §D7 says the term ships at 0 and the mitigation
              in v1 is "visibility, not mechanism". An admin about to enable it should be told what
              the number will actually do, since the editor row afterwards shows only a coefficient.
              Sourced from feasibility.py's own shipped behaviour, not invented. */}
          <p>
            The term multiplies how many other active appointments the same carrier already holds at
            this facility on the candidate slot&rsquo;s own local date, so a negative weight pushes a
            carrier that already holds today&rsquo;s capacity toward later intervals.
          </p>
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor={fieldId}>
            Type <span className="font-data">{CONFIRM_PHRASE}</span> to confirm
          </Label>
          <Input
            id={fieldId}
            value={typed}
            onChange={(event) => setTyped(event.currentTarget.value)}
            // Prompt 9: the field "receives focus automatically on open — never a submit or
            // destructive button". Radix focuses the first focusable child of the content by
            // default, which would be the close button, so this is set explicitly.
            autoFocus
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            spellCheck={false}
            className="font-data"
            aria-describedby={matches ? undefined : whyId}
          />
        </div>

        <DialogFooter>
          {/* Prompt 9: Cancel is "first in reading and tab order". U79's safer-action-first rule,
              and the same ordering every other confirmation on this surface uses. */}
          <Button variant="neutral" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="cautionary"
            disabled={!matches}
            title={matches ? undefined : `Type ${CONFIRM_PHRASE} to confirm`}
            onClick={() => {
              if (!matches) return
              onEnable()
              onOpenChange(false)
            }}
          >
            Enable fairness term
          </Button>
        </DialogFooter>
        {matches ? null : (
          <span id={whyId} className="sr-only">
            Type {CONFIRM_PHRASE} to confirm.
          </span>
        )}
      </DialogContent>
    </Dialog>
  )
}

/** Prompt 9's exact phrase. Exported so the sweep asserts against the same constant the dialog
 *  compares to, rather than a string literal copied into a test that could drift from it. */
export const CONFIRM_PHRASE = 'ENABLE FAIRNESS'
