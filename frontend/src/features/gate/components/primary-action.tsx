import { useEffect, useState } from 'react'
import { LoaderCircle, WifiOff } from 'lucide-react'

import { cn } from '@/shared/lib/utils'
import { TOUCH_CLASS } from '../lib/touch'

/**
 * The one-dominant-button next-action control (U110, `components.md` section 4), and the subject of
 * screen 13's state sheet -- the one screen on this surface that ships with no backend dependency
 * at all, because it depends on nothing beyond the design system.
 *
 * Four states, and the two that are easy to get wrong are the reason this is its own component:
 *
 * **Submitting: the label never leaves.** The spinner takes the *leading-icon* position and the
 * width is frozen; it does not replace the word. `components.md` section 13's rule that loading
 * never removes the action's own label is doubly load-bearing here -- a label-less spinner under
 * gloves invites a mis-tap on whatever renders next.
 *
 * **Inactive is not a faded Disabled control.** `components.md` foundations section 18 names this
 * surface specifically: outdoors, in sunlight, a faded grey rectangle is indistinguishable from a
 * rendering failure, and an officer who cannot tell *why* a button will not respond is locked out
 * just as thoroughly as one who cannot read the screen. So Inactive keeps full-contrast text,
 * stays focusable and stays tappable, and activating it surfaces the reason. It is a real
 * `<button>` with no `disabled` and no `aria-disabled` -- it genuinely is operable.
 *
 * **`inert` is the third tier and is deliberately distinct from both.** It is used only for the
 * shift-start button with an empty name field (screens 1a/2a), where `aria-disabled="true"` plus a
 * permanently-visible reason line is correct: nothing "changes while being looked at", so pressing
 * it would reveal nothing the helper text does not already say. That is `implementation-spec.md`
 * Fork B, taken as recommended -- (a) now, with (c) as the foundations fix -- and it is flagged in
 * the build report rather than treated as settled, because section 18's own wording is a blanket
 * rule that names this surface without carving out the static-prerequisite case.
 *
 * `type="button"` on all of them: nothing here is inside a `<form>` that should submit natively,
 * and a stray Enter-key submit on a gate write is exactly the accident U110's single-target design
 * exists to prevent.
 */
export type PrimaryActionState = 'default' | 'submitting' | 'inactive' | 'inert'

/**
 * U84's latency bands, as rendered behaviour rather than a comment.
 *
 * `mockup.html` screens 3 and 13 both state it: "Nothing appears at all for the first second of a
 * request... an indicator that flashes for under a second is pure distraction." So the button goes
 * unresponsive immediately (the tap is consumed the moment it lands) but the spinner only appears
 * once the request has actually been slow. `motion.md`'s 1-3s row names the button spinner as the
 * correct treatment for exactly this band.
 */
const SPINNER_DELAY_MS = 1000

export function PrimaryAction({
  label,
  state = 'default',
  reason,
  reasonId,
  onClick,
  className,
}: {
  label: string
  state?: PrimaryActionState
  /** Required by `components.md` section 1/18 for both `inactive` and `inert` -- a control that is
   *  not doing what it looks like it does must say why, always, not on demand. */
  reason?: string
  reasonId?: string
  onClick?: () => void
  className?: string
}) {
  const [showSpinner, setShowSpinner] = useState(false)

  useEffect(() => {
    if (state !== 'submitting') {
      setShowSpinner(false)
      return
    }
    const t = window.setTimeout(() => setShowSpinner(true), SPINNER_DELAY_MS)
    return () => window.clearTimeout(t)
  }, [state])

  const base = cn(
    'flex w-full min-h-(--btn-h) min-w-20 items-center justify-center gap-3 rounded-md px-6',
    'text-h2 font-bold',
    TOUCH_CLASS,
    'transition-colors duration-(--d-fast) ease-(--e-out)',
    'outline-none focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2',
  )

  if (state === 'inert') {
    return (
      <button
        type="button"
        aria-disabled="true"
        aria-describedby={reasonId}
        // Not the native `disabled` attribute: an `aria-disabled` control stays in the tab order,
        // so an officer tabbing through the shift-start card still reaches it and still hears the
        // reason via `aria-describedby`. `disabled` would remove it from the accessibility tree and
        // take the explanation with it.
        onClick={(e) => e.preventDefault()}
        className={cn(base, 'cursor-not-allowed bg-disabled text-disabled-foreground', className)}
      >
        {label}
      </button>
    )
  }

  if (state === 'inactive') {
    return (
      <div className="flex flex-col gap-4">
        <button
          type="button"
          onClick={onClick}
          className={cn(base, 'border border-input bg-card text-foreground hover:bg-hover', className)}
        >
          <WifiOff className="size-5" aria-hidden="true" />
          {label}
        </button>
        {reason ? (
          <p id={reasonId} className="text-body-lg text-foreground">
            {reason}
          </p>
        ) : null}
      </div>
    )
  }

  return (
    <button
      type="button"
      // Guarded on the handler, not on the `disabled` attribute: `components.md` section 4 keeps
      // the label AND the target stable through a submit, and disabling would move focus and change
      // the control's contrast at the exact moment the officer is looking at it.
      onClick={state === 'submitting' ? undefined : onClick}
      aria-busy={state === 'submitting' || undefined}
      className={cn(
        base,
        'bg-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-pressed',
        className,
      )}
    >
      {showSpinner ? (
        <LoaderCircle className="size-5 animate-spin motion-reduce:animate-none" aria-hidden="true" />
      ) : null}
      {label}
    </button>
  )
}
