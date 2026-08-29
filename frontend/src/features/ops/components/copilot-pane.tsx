import { useState } from 'react'
import { Bot } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { copilotActiveEnabled } from '../lib/flags'

/**
 * `screens.md` section 4, `components.md` (this folder) section 3, U57.
 *
 * **Inactive state (prompt 11) ships unconditionally.** `components.md` foundations section 18's
 * Inactive contract: fully focusable, explains itself on activation -- not plain, inert prose.
 * That is **Fork B**, applied directly here (implementation-spec.md section 6): the pane is a
 * real `<button>`, not a `<div>` of centred text, precisely because a keyboard-first coordinator
 * (this surface's entire ergonomic profile, per `accessibility.md`) cannot reach plain prose.
 *
 * **Active state (prompts 12/13) is behind `copilotActiveEnabled` (issue #57, G4 / Fork A).** No
 * endpoint, request shape or error taxonomy exists anywhere in `backend/app/` for summarise /
 * fetch-context / draft-reply -- building the two-gate draft-reply flow against nothing would
 * mean faking an LLM response, which this build's brief explicitly forbids.
 */
export function CopilotPane({ takeoverActive }: { takeoverActive: boolean }) {
  const [explaining, setExplaining] = useState(false)

  if (!takeoverActive || !copilotActiveEnabled) {
    return (
      <div className="flex h-full flex-col gap-3 p-4">
        <h2 className="text-label tracking-wide text-muted-foreground uppercase">Co-pilot</h2>
        <button
          type="button"
          onClick={() => setExplaining((v) => !v)}
          aria-expanded={explaining}
          className="flex flex-col items-center gap-3 rounded-md border border-dashed border-border p-4 text-center text-body text-muted-foreground hover:bg-hover focus-visible:outline-2 focus-visible:outline-ring"
        >
          <Bot className="size-6" aria-hidden="true" />
          <span>
            {takeoverActive
              ? 'Co-pilot capabilities aren’t wired up yet.'
              : 'Available once you take over a thread.'}
          </span>
          {explaining ? (
            <span className="text-supporting">
              {takeoverActive
                ? 'Summarise / fetch context / draft-reply have no backend contract yet (issue #57). Not offered as a fake response.'
                : 'Summarise thread, fetch context, and draft replies for your approval.'}
            </span>
          ) : null}
        </button>
      </div>
    )
  }

  // Unreachable while copilotActiveEnabled is false -- kept so the flag flip is a one-line
  // change, not a rewrite, the moment issue #57 lands with a real contract.
  return (
    <div className="flex h-full flex-col gap-2 p-4">
      <h2 className="text-label tracking-wide text-muted-foreground uppercase">Co-pilot</h2>
      <Button variant="neutral">Summarise thread</Button>
      <Button variant="neutral">Fetch context</Button>
    </div>
  )
}
