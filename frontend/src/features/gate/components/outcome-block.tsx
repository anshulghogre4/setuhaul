import type { LucideIcon } from 'lucide-react'

import { cn } from '@/shared/lib/utils'

export type OutcomeTone = 'success' | 'warning' | 'danger' | 'info'

const TONE: Record<OutcomeTone, { block: string; ink: string }> = {
  success: { block: 'bg-success-bg border-success-border', ink: 'text-success-fg' },
  warning: { block: 'bg-warning-bg border-warning-border', ink: 'text-warning-fg' },
  danger: { block: 'bg-danger-bg border-danger-border', ink: 'text-danger-fg' },
  info: { block: 'bg-info-bg border-info-border', ink: 'text-info-fg' },
}

/**
 * The outcome banner (`components.md` section 5), used by every screen from 14 to 22.
 *
 * **Tone and politeness are separate channels, and conflating them is the mistake this component
 * exists to prevent.** The prior mockup pass's R2 fix is the worked example: `DOCK_OCCUPIED` and
 * `INVALID_TRANSITION` are informational in *tone* (no red, no X, nobody blamed) but
 * `accessibility-behaviour.md`'s politeness matrix puts every unsuccessful action at `assertive`
 * without qualification -- and `INVALID_TRANSITION` is about to re-render the card underneath the
 * officer, which is exactly the interrupt case. So `tone` and `live` are independent props here,
 * and callers set both deliberately (see `outcome-screen.tsx`'s table).
 *
 * `role="status"` / `role="alert"` rather than a bare `aria-live` attribute: the roles already
 * imply polite/assertive live-region behaviour, and adding `aria-live` on top would be redundant.
 * The mockup's raw `aria-live` count is 0 by design, not by omission.
 *
 * Colour is never the sole carrier of meaning here -- the icon shape and the headline text both
 * carry it, which is what keeps the block legible on a sun-washed screen.
 */
export function OutcomeBlock({
  tone,
  live,
  icon: Icon,
  headline,
  children,
  align = 'center',
}: {
  tone: OutcomeTone
  live: 'status' | 'alert'
  icon: LucideIcon
  /** May contain a mono span -- `ALREADY_CHECKED_IN`'s headline embeds a timestamp, and
   *  `DOCK_OCCUPIED`'s embeds a dock code. */
  headline: React.ReactNode
  children?: React.ReactNode
  /** `inline` is the under-the-field message on the no-match search screen (screen 4): icon to
   *  the left of the headline, not above it, and the block sits below the field it refers to. */
  align?: 'center' | 'inline'
}) {
  const t = TONE[tone]

  if (align === 'inline') {
    return (
      <div role={live} className={cn('flex flex-row items-start gap-3 rounded-md border p-6', t.block)}>
        <Icon className={cn('mt-0.5 size-5 shrink-0', t.ink)} aria-hidden="true" />
        <div className="flex flex-col gap-1">
          <p className={cn('text-h2 font-bold text-balance', t.ink)}>{headline}</p>
          {children}
        </div>
      </div>
    )
  }

  return (
    <div
      role={live}
      className={cn('flex flex-col items-center gap-4 rounded-md border p-6 text-center', t.block)}
    >
      <Icon className={cn('size-8', t.ink)} aria-hidden="true" />
      <p className={cn('text-h2 font-bold text-balance', t.ink)}>{headline}</p>
      {children}
    </div>
  )
}

/** A supporting fact line inside a block. `text-foreground`, not the tone ink: `color.md`'s
 *  field-condition rule puts all operational text at `text-primary` on this surface, and only the
 *  headline and icon take the tone colour. */
export function OutcomeFact({
  children,
  mono,
}: {
  children: React.ReactNode
  mono?: boolean
}) {
  return (
    <p
      className={cn('text-body-lg text-foreground', mono && 'font-mono tabular-nums')}
      translate={mono ? 'no' : undefined}
    >
      {children}
    </p>
  )
}

/** The label/value pair `DOCK_MISMATCH` uses for its two docks (`mockup.html` `.pair`). */
export function OutcomePair({ label, value }: { label: string; value: string }) {
  return (
    <p className="flex w-full justify-between gap-6 text-body-lg text-foreground">
      <span>{label}</span>
      <span className="font-mono tabular-nums" translate="no">
        {value}
      </span>
    </p>
  )
}
