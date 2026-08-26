import * as React from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { CircleAlert, CircleCheckBig, Info } from 'lucide-react'

import { cn } from '@/shared/lib/utils'

/**
 * Re-authored from shadcn's two-variant alert.
 *
 * color.md's feedback tokens are a set of four (success / warning / danger / info) and they
 * are **never rendered in a promise-state slot** -- feedback is "an action succeeded or
 * failed", promise state is "where does this shipment stand".  Conflating them is the single
 * easiest way to make a CONFIRMED chip and a success toast look like the same fact.
 *
 * The `info` variant matters more than it looks: the password-reset "link sent" panel is
 * informational **blue, never green**.  Green in this product means CONFIRMED or "an action
 * succeeded", and an unread email is neither.
 *
 * Every variant carries an icon, because colour is never the only channel.
 */
const alertVariants = cva(
  'flex w-full items-start gap-2 rounded-md border p-3 text-supporting leading-[1.45] [&>svg]:mt-px [&>svg]:size-4 [&>svg]:shrink-0',
  {
    variants: {
      variant: {
        danger: 'bg-danger-bg border-danger-border text-danger-fg',
        warning: 'bg-warning-bg border-warning-border text-warning-fg',
        info: 'bg-info-bg border-info-border text-info-fg',
        success: 'bg-success-bg border-success-border text-success-fg',
      },
    },
    defaultVariants: { variant: 'info' },
  },
)

const ICON = {
  danger: CircleAlert,
  warning: CircleAlert,
  info: Info,
  success: CircleCheckBig,
} as const

export function Alert({
  className,
  variant = 'info',
  children,
  ...props
}: React.ComponentProps<'div'> & VariantProps<typeof alertVariants>) {
  const Icon = ICON[variant ?? 'info']
  return (
    <div
      data-slot="alert"
      // An unsuccessful action is ALWAYS announced assertively
      // (accessibility-behaviour.md); everything else is polite.  Silence on failure is the
      // single worst accessibility failure mode available.
      role={variant === 'danger' ? 'alert' : 'status'}
      className={cn(alertVariants({ variant }), className)}
      {...props}
    >
      <Icon aria-hidden="true" />
      <span>{children}</span>
    </div>
  )
}
