import { createContext, use, useCallback, useEffect, useMemo, useState } from 'react'

export type ThemeChoice = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

export const THEME_STORAGE_KEY = 'setuhaul.theme'

/**
 * Theme is the ONE preference in this product that is not durable server state.
 *
 * SOLUTION_DESIGN.md section 7.5.8 is explicit that the appearance toggle is deliberately
 * not a tool: client-only, no endpoint, no `user_id` binding.  Notification preferences by
 * contrast ARE Postgres-backed.  The asymmetry is intentional, and noted here because it
 * otherwise reads as an oversight to whoever touches this next -- do not "fix" it by adding
 * a field to update_notification_preferences.
 *
 * U69: light is the shipped default for EVERY role.  `prefers-color-scheme` is consulted
 * ONLY when the user has explicitly chosen "System" -- never as a fallback default.  A CSS
 * media query would silently hand a dark-configured Windows planner a dark UI, which is the
 * exact "two internal screens disagree by accident" outcome U69 rejected.
 */
export function readStoredTheme(): ThemeChoice {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY)
    if (raw === 'light' || raw === 'dark' || raw === 'system') return raw
  } catch {
    /* private mode / storage disabled -- fall through to the locked default */
  }
  return 'light'
}

export function resolveTheme(choice: ThemeChoice): ResolvedTheme {
  if (choice === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return choice
}

export function applyTheme(resolved: ResolvedTheme) {
  document.documentElement.classList.toggle('dark', resolved === 'dark')
}

type ThemeContextValue = {
  choice: ThemeChoice
  resolved: ResolvedTheme
  setChoice: (next: ThemeChoice) => void
}

export const ThemeContext = createContext<ThemeContextValue | null>(null)

export function useTheme(): ThemeContextValue {
  const ctx = use(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>')
  return ctx
}

export function useThemeState(): ThemeContextValue {
  const [choice, setChoiceState] = useState<ThemeChoice>(() => readStoredTheme())
  const [resolved, setResolved] = useState<ResolvedTheme>(() => resolveTheme(readStoredTheme()))

  const setChoice = useCallback((next: ThemeChoice) => {
    setChoiceState(next)
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next)
    } catch {
      /* storage disabled: the choice still applies for this session */
    }
    const r = resolveTheme(next)
    setResolved(r)
    applyTheme(r)
  }, [])

  // Only "System" listens to the OS.  A mid-session OS switch should be honoured for a user
  // who asked for that, and ignored for a user who picked an explicit theme.
  useEffect(() => {
    if (choice !== 'system') return
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => {
      const r: ResolvedTheme = mq.matches ? 'dark' : 'light'
      setResolved(r)
      applyTheme(r)
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [choice])

  return useMemo(() => ({ choice, resolved, setChoice }), [choice, resolved, setChoice])
}
