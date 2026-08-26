import type { ReactNode } from 'react'
import { TooltipProvider } from '@/shared/ui/tooltip'

import { CountdownProvider } from '@/shared/lib/countdown'
import { ThemeContext, useThemeState } from '@/shared/lib/theme'
import { Toaster } from '@/shared/ui/sonner'

/**
 * App-wide providers.  Deliberately three, not a stack of ten.
 *
 * `ThemeProvider` does NOT apply the theme class on mount -- the inline script in
 * index.html already did that, before first paint.  This provider only owns the *state* and
 * subsequent changes.  If you ever find yourself adding a `useEffect(() => applyTheme(...))`
 * here on mount, that is the white-flash bug coming back.
 */
export function AppProviders({ children }: { children: ReactNode }) {
  const theme = useThemeState()

  return (
    <ThemeContext value={theme}>
      <CountdownProvider>
        <TooltipProvider delayDuration={200}>
          {children}
          <Toaster />
        </TooltipProvider>
      </CountdownProvider>
    </ThemeContext>
  )
}
