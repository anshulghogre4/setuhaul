import { CircleAlert, CircleCheckBig, Info, OctagonAlert } from 'lucide-react'
import { Toaster as Sonner, type ToasterProps } from 'sonner'

import { useTheme } from '@/shared/lib/theme'

/**
 * Rewritten from the shadcn-generated file, which shipped two things that were wrong here:
 *
 *  1. It imported `useTheme` from `next-themes`, a package this project does not have and
 *     will not add -- theme is client-only localStorage (implementation-spec 4.5), resolved
 *     by our own provider.
 *  2. It set `--normal-bg: var(--popover)`.  Our variables are `--color-popover`; the bare
 *     `--popover` does not exist, so every toast would have rendered with no background at
 *     all.  This is the tier rule earning its keep -- the fault is invisible in the markup.
 *
 * components.md section 8: bottom-LEFT, max 3 stacked.  `z-toast` (700) must sit above
 * `z-modal` (600) -- U41's time-boxed undo that can be hidden behind a dialog is no undo,
 * and Radix/sonner both default to z-50, where DOM order alone decides the winner.
 */
export function Toaster(props: ToasterProps) {
  const { resolved } = useTheme()

  return (
    <Sonner
      theme={resolved}
      position="bottom-left"
      visibleToasts={3}
      className="toaster group z-toast"
      style={
        {
          zIndex: 700,
          '--normal-bg': 'var(--color-popover)',
          '--normal-text': 'var(--color-foreground)',
          '--normal-border': 'var(--color-floating-border)',
          '--border-radius': 'var(--radius)',
        } as React.CSSProperties
      }
      icons={{
        success: <CircleCheckBig className="size-4" />,
        info: <Info className="size-4" />,
        warning: <CircleAlert className="size-4" />,
        error: <OctagonAlert className="size-4" />,
      }}
      {...props}
    />
  )
}
