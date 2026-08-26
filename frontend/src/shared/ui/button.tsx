import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { Slot } from 'radix-ui'

import { cn } from '@/shared/lib/utils'

/**
 * components.md section 1 (U12): variants are named by CONSEQUENCE, not appearance.
 *
 * shadcn ships `default | secondary | destructive | outline | ghost | link`, named by how
 * they look.  Re-theming those would have kept the appearance names and lost U12 -- the
 * whole point of which is that a new button must declare what it DOES, which matters in a
 * product where confirming can silently harm a third party.  So the variant map is
 * rewritten rather than re-themed.  `cautionary` has no shadcn equivalent at all.
 *
 * Three rules from section 1 that live in review notes elsewhere and have to live in code here:
 *   - One `constructive` per view.
 *   - `destructive` never adjacent to `constructive` -- min 16px and a different visual group.
 *   - Safer action FIRST in DOM order (U79), whatever the visual position.  Call sites own
 *     that one; it is asserted in the states gallery rather than enforceable here.
 */
const buttonVariants = cva(
  [
    'inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap',
    'rounded-md border border-transparent text-body font-medium',
    // min-width 80px so short labels ("OK") do not produce tiny targets (section 1)
    'min-w-20',
    // No lift, no scale on hover -- motion.md.  Only colour transitions.
    'transition-colors duration-(--d-fast) ease-(--e-out)',
    'outline-none focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2',
    'disabled:cursor-not-allowed disabled:bg-disabled disabled:text-disabled-foreground disabled:border-transparent',
    "[&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  ],
  {
    variants: {
      variant: {
        /** Commits something good -- Confirm, Request slot, Save. */
        constructive: 'bg-primary text-primary-foreground hover:bg-primary-hover active:bg-primary-pressed',
        /** Non-committal -- Counter-offer, Hold, Cancel, Close. */
        neutral: 'bg-transparent border-input text-foreground hover:bg-hover',
        /** Escalates or hands off -- Escalate, Get help.  No shadcn equivalent. */
        cautionary: 'bg-warning-bg border-warning-border text-warning-fg hover:brightness-95 dark:hover:brightness-125',
        /** Ends something for someone else -- Reject, Cancel appointment. */
        destructive:
          'bg-destructive text-destructive-foreground hover:brightness-110 active:brightness-95',
        /** Tertiary, in-row -- expand, overflow menu. */
        ghost: 'bg-transparent text-muted-foreground hover:bg-hover hover:text-foreground min-w-0',
      },
      size: {
        /** Height follows density: --btn-h is 32 / 40 / 44 / 56 by data-density. */
        default: 'h-(--btn-h) px-4',
        sm: 'h-10 px-4',
        icon: 'size-8 min-w-0 p-0',
        'icon-lg': 'size-10 min-w-0 p-0',
      },
      full: { true: 'w-full', false: '' },
    },
    defaultVariants: { variant: 'neutral', size: 'default', full: false },
  },
)

export type ButtonIntent = NonNullable<VariantProps<typeof buttonVariants>['variant']>

function Button({
  className,
  variant,
  size,
  full,
  asChild = false,
  ...props
}: React.ComponentProps<'button'> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : 'button'

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, full, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
