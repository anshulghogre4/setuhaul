import type { ReactNode } from 'react'
import { TooltipProvider } from '@/shared/ui/tooltip'

import { AuthProvider } from '@/core/auth/auth-provider'
import { CountdownProvider } from '@/shared/lib/countdown'
import { ThemeContext, useThemeState } from '@/shared/lib/theme'
import { Toaster } from '@/shared/ui/sonner'

/**
 * App-wide providers.  Deliberately four, not a stack of ten.
 *
 * `ThemeProvider` does NOT apply the theme class on mount -- the inline script in
 * index.html already did that, before first paint.  This provider only owns the *state* and
 * subsequent changes.  If you ever find yourself adding a `useEffect(() => applyTheme(...))`
 * here on mount, that is the white-flash bug coming back.
 *
 * `AuthProvider` is **outermost of the four and inside `<BrowserRouter>`** (see `main.tsx`), and
 * both halves of that placement matter:
 *   - outermost, because the route guards, the shell and every surface read identity from it, and
 *     a second instance would mean two independent session subscriptions racing each other;
 *   - inside the router, because sign-out and the central 401 handler must resolve through router
 *     navigation rather than a full page reload -- `auth-and-scoping.md` requires in-flight work to
 *     survive a session expiry.
 */
export function AppProviders({ children }: { children: ReactNode }) {
  const theme = useThemeState()

  return (
    <AuthProvider>
      <ThemeContext value={theme}>
        <CountdownProvider>
          <TooltipProvider delayDuration={200}>
            {children}
            <Toaster />
          </TooltipProvider>
        </CountdownProvider>
      </ThemeContext>
    </AuthProvider>
  )
}
