import type { LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'

import { cn } from '@/shared/lib/utils'

/**
 * components.md section 13.  Every state names a cause and a next action (U32).
 *
 * Icon is 32px in `text-tertiary`; the title states what is true right now; the body
 * explains why, if useful; actions come last.
 *
 * Actions are rendered in the order given, and call sites are expected to pass the SAFER
 * action first (U79) -- "Report this" before "Try again", never the reverse -- so a fast
 * keyboard user who overshoots lands on the harmless one.
 */
export function EmptyState({
  icon: Icon,
  title,
  body,
  actions,
  className,
}: {
  icon: LucideIcon
  title: ReactNode
  body?: ReactNode
  actions?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center px-6 py-10 text-center',
        className,
      )}
    >
      <Icon className="size-8 text-subtle-foreground" aria-hidden="true" />
      <p className="mt-4 text-h3 text-balance">{title}</p>
      {body ? <p className="mt-2 max-w-[44ch] text-body text-muted-foreground">{body}</p> : null}
      {actions ? <div className="mt-6 flex flex-wrap justify-center gap-4">{actions}</div> : null}
    </div>
  )
}
