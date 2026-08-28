import { EligibilityAnswerPart } from './eligibility-answer'
import { OptionSetPart } from './option-set'
import type { DriverMessage, DriverOption } from '../lib/types'

/**
 * The structured half of a message: option sets, eligibility answers, receipts.
 *
 * **Extracted so the product transcript and the verification gallery cannot diverge.** They did:
 * the first render of `/driver/_states` showed screen 4 ("Conversation — SHOWN") with its two
 * bubbles and **no option cards at all**, because the gallery's row wrapper passed no children
 * while `Transcript` mapped the parts itself. A gallery that silently omits the most consequential
 * component on the surface is worse than no gallery — it certifies something it never rendered.
 * One renderer, two callers.
 *
 * The `switch` is exhaustive on `part.kind`, so a new part type is a compile error rather than a
 * silently missing card.
 *
 * Text parts are handled by the bubble itself (`message.tsx`) and skipped here: they are prose,
 * and mixing the two would put the U48 seam in two places.
 */
export function MessageParts({
  message,
  facilityName,
  onSelectOption,
  onEscalate,
}: {
  message: DriverMessage
  facilityName?: string
  onSelectOption?: (option: DriverOption) => void
  onEscalate?: () => void
}) {
  return (
    <>
      {message.parts.map((part, i) => {
        switch (part.kind) {
          case 'optionSet':
            return (
              <OptionSetPart
                key={i}
                set={part.optionSet}
                facilityName={facilityName}
                onSelect={onSelectOption}
                onEscalate={onEscalate}
              />
            )
          case 'eligibility':
            return <EligibilityAnswerPart key={i} answer={part.answer} />
          case 'receipt':
            return (
              <p key={i} className="mt-2 font-mono text-body text-subtle-foreground">
                {part.lines.join(' · ')} · Policy {part.policyVersion}
              </p>
            )
          case 'text':
            return null
        }
      })}
    </>
  )
}
