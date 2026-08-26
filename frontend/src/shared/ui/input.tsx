import * as React from 'react'

import { cn } from '@/shared/lib/utils'

/**
 * Re-authored from shadcn's default.
 *
 * Changes and why: 44px height (the auth density's tap target, and the field bar across the
 * product) instead of 36px; `border-input` = border-default rather than a shadow; the
 * two-ring focus treatment every other control gets rather than shadcn's 3px ring/50 glow --
 * elevation-and-depth.md is explicit that a glow vanishes against a selected row, and
 * planners operate by keyboard.  Hover uses `border-strong`, which existed all along; the
 * mockup had hardcoded neutral-400, which was too bright on a dark ground.
 */
function Input({ className, type, ...props }: React.ComponentProps<'input'>) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        'h-11 w-full min-w-0 rounded-md border border-input bg-card px-3',
        'text-body text-foreground placeholder:text-subtle-foreground',
        'transition-colors duration-(--d-fast) ease-(--e-out) hover:border-strong',
        'outline-none focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2',
        'disabled:cursor-not-allowed disabled:bg-disabled disabled:text-disabled-foreground',
        'aria-invalid:border-danger-border',
        className,
      )}
      {...props}
    />
  )
}

export { Input }
