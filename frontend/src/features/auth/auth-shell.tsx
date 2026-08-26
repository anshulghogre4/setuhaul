import type { ReactNode } from 'react'

import { cn } from '@/shared/lib/utils'

/**
 * The 400px card chassis shared by sign-in, the role picker and both reset screens.
 *
 * Visual continuity is the point, not an accident: the role picker is the SECOND BEAT of one
 * flow, and a drifting chassis reads as a different product mid-flow.  Same width, same
 * 32px padding, same field height, same button on every screen that uses this.
 *
 * `data-density="auth"` -- these screens belong to none of the operational surfaces'
 * densities.  The auth row is `comfortable` with 44px controls, because this is the
 * DRIVER's door as well as a desk user's, so the field 44x44 bar applies to the door even
 * though it does not apply to the planner console behind it.  (spacing-and-layout.md, added
 * 2026-08-26; the 44px is tagged `Source: assumption, untested`.)
 *
 * Login is one of only two places in the product where spacing above 32px is permitted, so
 * the 40px gap under the wordmark is deliberate, not drift.
 */
export function AuthShell({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      data-density="auth"
      className="flex min-h-dvh items-center justify-center bg-background px-6 py-10"
    >
      <main
        className={cn(
          'w-full max-w-100 rounded-lg border border-border bg-card p-8 shadow-raised',
          className,
        )}
      >
        {children}
      </main>
    </div>
  )
}

/** No illustration, no split-screen hero, no "or continue with" divider. */
export function Wordmark() {
  return (
    <div>
      <div className="text-display" translate="no">
        SetuHaul
      </div>
      <div className="mt-1 text-body text-muted-foreground">Dock Command</div>
    </div>
  )
}
