import { Button } from '@/shared/ui/button'
import { copy } from '../lib/copy'
import { OptionCard } from './option-card'
import type { DriverOption, OptionSet } from '../lib/types'

/**
 * A whole `find_feasible_slots` result, rendered as a tool-call part — never as text the model
 * composed (U48, `00-foundations/ai-chat-primitives.md`).
 *
 * ## Branch on `outcome`, never on `escalation === null`
 *
 * `backend/app/scheduling/feasibility.py` says so inline and it is a real trap:
 * `NO_SAME_DAY_SLOT` returns **options AND no escalation**. Three outcomes, three screens:
 *
 * | `outcome`           | Screen | What renders |
 * |---------------------|--------|--------------|
 * | `FEASIBLE`          | 4      | Cards for today. |
 * | `NO_SAME_DAY_SLOT`  | 19     | Tomorrow's cards — **the date is load-bearing** — plus an offered escalation route. **Not a failure treatment.** |
 * | `NO_FEASIBLE_SLOT`  | 20     | Reference + promise of contact. **No cards, no retry** — offering a retry that will fail identically is worse than not offering one. |
 *
 * The `NO_SAME_DAY_SLOT` escalation is **offered, not withheld** until the driver thinks to ask.
 * That single button is the difference between an exception that resolves and one that becomes a
 * phone call.
 *
 * ## Superseded sets
 *
 * When a newer set arrives the older one greys as a whole and becomes non-interactive
 * (`01-driver-chat/components.md` section 2). Handled at the set level, not by mutating each
 * card, because "superseded" is a fact about the set.
 */

export type OptionSetPartProps = {
  set: OptionSet
  /** Facility display name for the lead sentence. Server-sourced; the lead is omitted rather
   *  than guessed if absent. */
  facilityName?: string
  /** The specific blocking reason, from the server's own `rejected_reasons` — never
   *  "no availability" (`edge-cases.md` sections 5 and 6). */
  blockingReason?: string
  onSelect?: (option: DriverOption) => void
  onEscalate?: () => void
}

export function OptionSetPart({
  set,
  facilityName,
  blockingReason,
  onSelect,
  onEscalate,
}: OptionSetPartProps) {
  if (set.outcome === 'NO_FEASIBLE_SLOT') {
    return (
      <div className="mt-2">
        <p className="text-body-lg">
          {facilityName && blockingReason && set.escalationReference
            ? copy.noFeasibleSlot(facilityName, blockingReason, set.escalationReference)
            : /* No fabricated substitute. If the server did not supply a reason or a reference,
                 the honest render is the reference alone -- an escalation without a reference is
                 what edge-cases.md section 6 says "feels like being dropped", so the reference is
                 the one thing that must always show. */
              (set.escalationReference ?? '')}
        </p>
        <PolicyStamp version={set.policyVersion} />
      </div>
    )
  }

  const superseded = set.setState === 'superseded'

  return (
    <div className="mt-2">
      {set.outcome === 'NO_SAME_DAY_SLOT' ? (
        <p className="text-body-lg">
          {facilityName && blockingReason
            ? copy.noSameDaySlot(facilityName, blockingReason)
            : 'The earliest I can offer is tomorrow.'}
        </p>
      ) : facilityName ? (
        <p className="text-body-lg">{copy.shownLead(set.options.length, facilityName)}</p>
      ) : null}

      {/* "Nothing is held yet" is MANDATORY and appears BEFORE the options, not after -- a
          driver who taps without reading must still not have been misled by what they skimmed
          (voice-and-tone.md, the SHOWN template). */}
      <p className="mt-1 text-body text-muted-foreground">{copy.shownNothingHeld}</p>

      {/* A plain list, not a listbox: these are eight-state action targets, not a single-select
          control, and a listbox content model would owe every card an option role plus managed
          active-descendant focus. `role="group"` with a label is what the cards actually are. */}
      <div
        role="group"
        aria-label="Available slots"
        className="mt-3"
        aria-disabled={superseded || undefined}
      >
        {set.options.map((option) => (
          <OptionCard
            key={option.slotId}
            option={option}
            state={superseded ? 'superseded' : (set.perOption?.[option.slotId] ?? 'default')}
            onSelect={onSelect}
          />
        ))}
      </div>

      {set.outcome === 'FEASIBLE' && !superseded ? (
        <p className="mt-2 text-body text-muted-foreground">{copy.shownTapHint}</p>
      ) : null}

      {set.outcome === 'NO_SAME_DAY_SLOT' ? (
        <>
          <p className="mt-2 text-body">{copy.noSameDayEscalationOffer}</p>
          <div className="mt-3">
            <Button variant="cautionary" onClick={onEscalate}>
              {copy.getHelpAction}
            </Button>
          </div>
        </>
      ) : null}

      <PolicyStamp version={set.policyVersion} />
    </div>
  )
}

/**
 * `00-foundations/components.md` section 4: **always stamp the policy version.** "Which policy
 * produced this promise?" must be answerable later (section 5).
 *
 * 14px, not `text-micro`'s 11px — the driver surface's floor applies to the receipt stamp as
 * much as to anything else (F1).
 */
function PolicyStamp({ version }: { version: string }) {
  if (!version) return null
  return (
    <p className="mt-2 font-mono text-body text-subtle-foreground">Policy {version}</p>
  )
}
