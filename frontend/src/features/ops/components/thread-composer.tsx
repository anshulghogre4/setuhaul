import { forwardRef, useId, useState } from 'react'
import { Send } from 'lucide-react'

import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/utils'

/**
 * The coordinator's composer -- `screens.md` sections 3/3b, `flows-and-states.md` Flow 2,
 * `stitch-prompts.md` prompt 8.
 *
 * ## Two states of one pane, never two panes
 *
 * Flow 2's "States" section names three, which are two renderings: **composer disabled**
 * (pre-takeover and again post-hand-back -- the same read-only shape both times, with the
 * transcript now carrying the completed human exchange) and **composer enabled** (post-takeover,
 * pre-hand-back). The element is never unmounted between them, so a screen reader's position and
 * the pane's scroll offset survive the transition.
 *
 * ## Read-only, not Disabled and not Inactive -- Flow 2 says so explicitly
 *
 * > "this is genuinely Read-only, not Inactive, since there's nothing to explain by activating it;
 * > taking over is the explicit unlock"
 *
 * `00-foundations/components.md` section 18's Read-only row demands **zero interactive
 * affordance** -- no hover state, no focus ring, no accent colour, no cursor change -- because "a
 * read-only view that looks clickable and does nothing reads as broken, not as scoped". Hence
 * `readOnly` **and** `tabIndex={-1}` on the pre-takeover textarea: out of the tab order, no focus
 * ring, no hover. The visible label still explains the state, so nothing is hidden from a screen
 * reader browsing the pane -- it simply is not a stop for someone tabbing to the next action.
 *
 * It is still a real `<textarea>` rather than a `<div>`, which is `implementation-spec.md` section
 * 6 **Fork B**'s recommendation (a): "the composer is a `<textarea>` with `readonly`
 * pre-takeover". The mockup's empty unlabelled `<div>` had nothing to carry the state at all.
 */

/** `thread_message_service.MAX_MESSAGE_LENGTH`. Enforced here so an over-long message is caught
 *  before it costs a round trip, and again server-side (422 `MESSAGE_TOO_LONG`) because a
 *  client-side limit is a courtesy, not a control. */
const MAX_MESSAGE_LENGTH = 4000

/** Show the counter only when it starts to matter, rather than permanently occupying a line in a
 *  `compact`-density pane that is already fighting for room. */
const COUNTER_VISIBLE_FROM = MAX_MESSAGE_LENGTH - 500

export type ThreadComposerProps = {
  /** True once `take_over_thread` has succeeded on this thread. The ONLY thing that unlocks it. */
  active: boolean
  /** Blocks Send while a post is in flight, so a double-press cannot start a second attempt with
   *  a second key. (A retry of a *failed* attempt reuses the first key -- see `ops-console.tsx`.) */
  busy?: boolean
  onSend: (text: string) => void
}

export const ThreadComposer = forwardRef<HTMLTextAreaElement, ThreadComposerProps>(
  function ThreadComposer({ active, busy, onSend }, ref) {
    const [value, setValue] = useState('')
    // Issue #91: these were the literals "ops-composer" / "ops-composer-hint". Seven composers
    // render in the states gallery, so seven <label for> pointed at one textarea and seven
    // `aria-describedby` at one hint -- a real AT defect, not just a duplicate-id warning.
    // See the React-19 id-format note in `owner-control.tsx`.
    const composerId = useId()
    const hintId = useId()

    const trimmed = value.trim()
    const tooLong = value.length > MAX_MESSAGE_LENGTH
    const canSend = active && !busy && trimmed.length > 0 && !tooLong

    function submit() {
      if (!canSend) return
      onSend(trimmed)
      setValue('')
    }

    return (
      <section
        className="flex flex-col gap-1.5"
        aria-label={active ? 'Reply to the driver' : 'Thread composer, read-only'}
      >
        <label htmlFor={composerId} className="text-label tracking-wide text-muted-foreground uppercase">
          {active ? 'Reply as Operations' : 'Composer — read-only until you take over'}
        </label>

        <div className="flex items-end gap-2">
          <textarea
            id={composerId}
            ref={ref}
            rows={2}
            value={active ? value : ''}
            readOnly={!active}
            // Out of the tab order while read-only: components.md section 18's Read-only row
            // requires zero interactive affordance, and a focusable empty box between the
            // transcript and the terminal actions is exactly the dead stop that rule exists to
            // prevent.
            tabIndex={active ? 0 : -1}
            aria-describedby={hintId}
            placeholder={
              active
                ? 'Write to the driver. They see this in their own conversation.'
                : 'Take over the thread to reply.'
            }
            className={cn(
              'min-h-16 flex-1 resize-y rounded-md border px-3 py-2 text-body',
              active
                ? 'border-input bg-background focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2'
                : // No hover, no focus ring, no accent, default cursor: it was never a control.
                  'cursor-default border-dashed border-border bg-sunken text-muted-foreground',
              tooLong && 'border-destructive',
            )}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (!active) return
              // Escape exits the composer without sending -- accessibility.md's keyboard table
              // lists this as a product-wide rule, and it is the escape hatch for a coordinator
              // who started typing into the wrong thread.
              if (e.key === 'Escape') {
                e.currentTarget.blur()
                return
              }
              // Enter sends, Shift+Enter newlines. `isComposing` guards an IME: a Devanagari or
              // Hinglish transliteration keyboard uses Enter to commit a candidate, and sending on
              // that keystroke would post a half-typed sentence to a driver. Same guard, same
              // reason, as the driver composer.
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                submit()
              }
            }}
          />

          {/* Rendered only under takeover. Scope-denied and prerequisite-unmet cases are carried
              by the takeover control itself; a Send button with nowhere to send is exactly the
              dead control this build exists to remove. */}
          {active ? (
            <Button
              variant="constructive"
              onClick={submit}
              disabled={!canSend}
              aria-label="Send message to driver"
            >
              <Send aria-hidden="true" />
              Send
            </Button>
          ) : null}
        </div>

        <p id={hintId} className="flex items-center justify-between gap-2 text-micro text-muted-foreground">
          <span>
            {active
              ? 'Enter sends · Shift+Enter for a new line · Escape leaves the composer'
              : 'The driver still sees the assistant answering this thread.'}
          </span>
          {active && value.length >= COUNTER_VISIBLE_FROM ? (
            <span
              className={cn('font-data tabular-nums', tooLong && 'font-semibold text-destructive')}
            >
              {value.length} / {MAX_MESSAGE_LENGTH}
            </span>
          ) : null}
        </p>

        {tooLong ? (
          <p role="alert" className="text-supporting text-destructive">
            This message is too long to send. Trim it to {MAX_MESSAGE_LENGTH} characters or fewer.
          </p>
        ) : null}
      </section>
    )
  },
)
