/**
 * Shift-identity session (U111, `components.md` section 1, Flow 0).
 *
 * **Local device state, not a server write** -- `edge-cases.md` #7 is explicit that this must
 * stay usable through a connectivity drop, and G2 (issue #68) confirms no write tool anywhere
 * accepts an officer name server-side, so there is nothing to persist remotely even if we
 * wanted to. `sessionStorage`, not `localStorage`: a shift ends when the browser tab/kiosk
 * session ends, matching "ended... session name cleared" (`components.md` section 1) without
 * needing an explicit end-shift tap to survive an accidental reload.
 *
 * The officer name captured here is genuinely displayed on every subsequent screen (the shift
 * bar) but is never sent to the backend -- G2 (issue #68) is a real, unfixed gap this build does
 * not attempt to close; every write this session makes is attributed server-side only to
 * `ctx.user_id`, the shared kiosk device's own Supabase Auth session.
 */

export type ShiftSession = {
  officerName: string
}

const STORAGE_KEY = 'setuhaul.gate.shift.v1'

export function loadShiftSession(): ShiftSession | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<ShiftSession>
    if (typeof parsed.officerName !== 'string' || parsed.officerName.trim() === '') return null
    return { officerName: parsed.officerName }
  } catch {
    return null
  }
}

export function startShift(officerName: string): ShiftSession {
  const session: ShiftSession = { officerName: officerName.trim() }
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(session))
  return session
}

export function endShift(): void {
  sessionStorage.removeItem(STORAGE_KEY)
}
