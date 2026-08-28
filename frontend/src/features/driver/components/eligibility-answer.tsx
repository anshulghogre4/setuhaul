import { Check, X } from 'lucide-react'

import { Skeleton } from '@/shared/ui/skeleton'
import { cn } from '@/shared/lib/utils'
import { copy } from '../lib/copy'
import type { EligibilityAnswer } from '../lib/types'

/**
 * Screens 12A / 12B — the eligibility answer (`01-driver-chat/components.md` section 8,
 * `flows-and-states.md` Flow 6, `FR-DRV-006`).
 *
 * Structurally distinct from the shared decision receipt: that renders *why an option ranked
 * where it did*; this renders *whether one specific thing is allowed*. Binary per invariant,
 * not scored.
 *
 * ## Two rules that are the whole point
 *
 * - **Every invariant renders, not only the failing one.** A driver who sees only "no" learns
 *   nothing they can act on; seeing which specific thing failed is what turns a refusal into a
 *   route.
 * - **Passing rows stay neutral, never green** (F9). A mixed-verdict card is not the place to
 *   introduce a second meaning for a colour already spent on promise state. Only the *verdict*
 *   line and the failing row carry colour, and the failing row's red uses `--color-danger-fg`.
 *   Where a green is needed it is `--color-success-fg` (green-700, 5.6:1) — **not** green-600,
 *   which F9 measured at 3.8:1 and fails AA.
 * - **`check`/`x` icon plus colour, never colour alone** (`iconography.md`).
 *
 * ## Read-only
 *
 * No exception row, no thread-state change, no dedupe key — the same browse-only category as the
 * Flow 2 option-preview path. Nothing in this component takes an action callback, deliberately.
 */

export function EligibilityAnswerPart({ answer }: { answer: EligibilityAnswer }) {
  return (
    <div className="mt-2 rounded-lg border border-input bg-card p-4">
      <p className="text-body-lg font-semibold">
        Dock {answer.dockCode}
        {answer.subject ? ` · ${answer.subject}` : ''}
      </p>

      {/* A definition-free list: each row is one invariant and its verdict. `role="list"` is
          explicit because the rows are <div>s carrying an icon plus text, and the
          web-design-guidelines pass flagged exactly this shape (a log with no list items) as
          the recurring mistake. */}
      <div role="list" className="mt-3 space-y-2">
        {answer.rows.map((row) => (
          <div key={row.constraintId} role="listitem" className="flex gap-2">
            {row.passed ? (
              <Check
                size={16}
                strokeWidth={2}
                aria-hidden="true"
                className="mt-0.5 shrink-0 text-success-fg"
              />
            ) : (
              <X
                size={16}
                strokeWidth={2}
                aria-hidden="true"
                className="mt-0.5 shrink-0 text-danger-fg"
              />
            )}
            <div className="min-w-0">
              {/* Passing rows are `text-foreground`, NOT green. Only the failing row is
                  coloured. */}
              <p className={cn('text-body', !row.passed && 'text-danger-fg')}>
                {row.label}
                {/* Spoken verdict, so a screen-reader user does not depend on the icon's
                    accessible name (it has none -- it is aria-hidden, per iconography.md's
                    decorative-glyph rule). */}
                <span className="sr-only">{row.passed ? ' — passes' : ' — fails'}</span>
              </p>
              {/* The specific rule id and reason in plain language, never "not eligible" alone
                  (voice-and-tone.md: a refusal without a route is a dead end). Server-sourced. */}
              {row.detail ? (
                <p className="mt-0.5 text-body text-muted-foreground">{row.detail}</p>
              ) : null}
            </div>
          </div>
        ))}
      </div>

      {/* Templated verdict, matching the discipline applied to the four state messages -- this
          is a sentence that declares a fact, not conversational glue. */}
      <p
        className={cn(
          'mt-3 border-t border-border pt-3 text-body-lg font-semibold',
          answer.eligible ? 'text-success-fg' : 'text-danger-fg',
        )}
      >
        {answer.verdict}
      </p>
    </div>
  )
}

/** Loading: **skeleton rows matching the final invariant count, never a spinner**
 *  (`components.md` section 13). Ten is the real count — `constraints.json` carries ten
 *  `feasibility_hard_constraints`, so the skeleton is the true shape rather than a guess. */
export function EligibilityAnswerSkeleton({ rows = 10 }: { rows?: number }) {
  return (
    <div className="mt-2 rounded-lg border border-input bg-card p-4">
      <Skeleton className="h-5 w-40" />
      <div className="mt-3 space-y-2">
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} className="h-5 w-full" />
        ))}
      </div>
      <Skeleton className="mt-3 h-6 w-2/3" />
    </div>
  )
}

/** Tool call failed. **Never a guessed answer** (`voice-and-tone.md`'s empty/error rule). */
export function EligibilityAnswerError() {
  return (
    <p className="mt-2 text-body text-danger-fg" role="status">
      {copy.eligibilityToolFailed}
    </p>
  )
}
