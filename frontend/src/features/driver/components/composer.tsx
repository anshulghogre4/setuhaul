import { Send } from 'lucide-react'
import { useRef, useState } from 'react'

import { cn } from '@/shared/lib/utils'
import { copy } from '../lib/copy'

/**
 * The composer plus contextual quick replies (`01-driver-chat/components.md` section 3, U49).
 *
 * ## The composer is never disabled. Not once, not offline, not mid-turn.
 *
 * *"Whatever else is unavailable, a driver must always be able to say something — that message
 * queueing safely is the whole point of `CONNECTION_LOST`."* Offline it stays fully enabled and
 * the **placeholder** changes; the send button stays live and the message queues. This is why
 * this component takes an `offline` prop and **no `disabled` prop**: there is no caller-supplied
 * way to switch it off, by construction.
 *
 * ## Quick replies (U49)
 *
 * - Shown **only** when the assistant's last message asked something with an obvious closed
 *   answer. The caller decides that from `done.data.ux_state`
 *   (`clarification_required` / `confirmation_required`), never from parsing the prose.
 * - **2–3 only.** More than 3 is a form, not a conversation, and horizontal scroll on a phone
 *   hides options.
 * - **They send the literal chip text as a normal driver message** — not a special type. The
 *   transcript has to read as a conversation afterwards.
 * - **Typing anything dismisses them**, and they do not reappear for that question. Handled here
 *   (`dismissed` state) rather than by the caller, because "the driver started typing" is a fact
 *   only this component sees.
 *
 * ## Sizes that are requirements, not choices
 *
 * - Input at **16px** (`text-body-lg`): prevents iOS Safari auto-zoom on focus, and is the
 *   driver body size anyway, so it costs nothing.
 * - Send at **44×44**. The audit measured 38×38 on 4 of 34 frames.
 * - Quick-reply chips at **≥44px tall**. The audit measured 34px on 4 of 15. F7's own reading is
 *   upheld here: the **chip** carries the floor and the region is described by its padding,
 *   because 44px plus `comfortable`'s padding cannot fit inside a 48px region.
 * - `env(safe-area-inset-bottom)` so the composer clears the home indicator — on **every**
 *   conversation screen, not just the keyboard-open artboard (the mockup had one occurrence).
 */

export type ComposerProps = {
  offline?: boolean
  /** 2–3 literal strings. More than 3 is sliced with a dev warning rather than silently
   *  scrolled: the design's reason for the cap is that scroll HIDES options. */
  quickReplies?: string[]
  onSend: (text: string) => void
}

export function Composer({ offline = false, quickReplies = [], onSend }: ComposerProps) {
  const [value, setValue] = useState('')
  const [dismissed, setDismissed] = useState(false)
  const textarea = useRef<HTMLTextAreaElement>(null)

  const replies = quickReplies.slice(0, 3)
  if (import.meta.env.DEV && quickReplies.length > 3) {
    console.warn('[driver] more than 3 quick replies supplied; extra ones are dropped, not scrolled')
  }

  const submit = (text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    onSend(trimmed)
    setValue('')
    setDismissed(false)
    if (textarea.current) textarea.current.style.height = 'auto'
  }

  return (
    <div
      className="border-t border-border bg-card"
      // The safe-area inset lives on the wrapper so both the quick replies and the input clear
      // the home indicator, not just the bottom-most element.
      style={{ paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      {replies.length > 0 && !dismissed ? (
        <div
          // Grouped and labelled "Suggested replies" (accessibility.md, "Screen reader").
          role="group"
          aria-label="Suggested replies"
          className="flex flex-wrap gap-2 px-4 pt-3"
        >
          {replies.map((reply) => (
            <button
              key={reply}
              type="button"
              onClick={() => submit(reply)}
              className={cn(
                'min-h-11 rounded-full border border-input bg-card px-4 text-body',
                'hover:bg-hover active:bg-hover',
                'focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2',
              )}
            >
              {reply}
            </button>
          ))}
        </div>
      ) : null}

      <form
        className="flex items-end gap-2 p-3"
        onSubmit={(e) => {
          e.preventDefault()
          submit(value)
        }}
      >
        <textarea
          ref={textarea}
          value={value}
          rows={1}
          // text-body-lg is 16px. Do NOT shrink this: below 16px iOS Safari zooms the viewport
          // on focus and the driver has to pinch back out one-handed.
          className={cn(
            'max-h-24 min-h-11 flex-1 resize-none rounded-md border border-input bg-background',
            'px-3 py-2.5 text-body-lg',
            'focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2',
          )}
          placeholder={offline ? copy.composerPlaceholderOffline : copy.composerPlaceholder}
          onChange={(e) => {
            setValue(e.target.value)
            // Typing dismisses the quick replies for THIS question and they do not come back.
            if (e.target.value.length > 0 && !dismissed) setDismissed(true)
            // Grows to 3 lines then scrolls internally (max-h-24 is 96px ~= 3 lines at 16/1.5).
            const el = e.target
            el.style.height = 'auto'
            el.style.height = `${Math.min(el.scrollHeight, 96)}px`
          }}
          onKeyDown={(e) => {
            // Hardware keyboard: Enter sends, Shift+Enter newlines. `isComposing` guards an IME
            // -- a Devanagari or Hinglish transliteration keyboard uses Enter to commit a
            // candidate, and sending on that keystroke would fire a half-typed message.
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              submit(value)
            }
          }}
        />
        <button
          type="submit"
          aria-label={copy.composerSendLabel}
          // Enabled only when non-empty (components.md section 3). NOT disabled when offline --
          // that is the one thing this component must never do.
          disabled={value.trim().length === 0}
          className={cn(
            'grid size-11 shrink-0 place-items-center rounded-md',
            'bg-primary text-primary-foreground',
            'disabled:bg-disabled disabled:text-disabled-foreground',
            'focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2',
          )}
        >
          <Send size={18} strokeWidth={2} aria-hidden="true" />
        </button>
      </form>
    </div>
  )
}
