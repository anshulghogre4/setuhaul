/**
 * Shift-identity session (U111, `components.md` section 1, Flow 0).
 *
 * **Starting a shift is local device state, not a server write** -- `edge-cases.md` #7 is explicit
 * that this must stay usable through a connectivity drop, so Flow 0 must not depend on the network.
 * `sessionStorage`, not `localStorage`: a shift ends when the browser tab/kiosk session ends,
 * matching "ended... session name cleared" (`components.md` section 1) without needing an explicit
 * end-shift tap to survive an accidental reload.
 *
 * **The name is now transmitted on every write (issue #68, closed 2026-08-31).** It used to be
 * captured here, rendered in the shift bar, and sent nowhere -- so every event any officer wrote on
 * this device was indistinguishable in the audit trail, which is precisely what U111 exists to
 * prevent. It now travels as an `officer_name` body field on all five `/api/v1/gate/*` writes
 * (`lib/api.ts`) and is recorded on each event's `audit_logs` row.
 *
 * **It is still not a credential, and this file is still not an auth boundary.** Nothing verifies
 * the name; anyone can type anything. Authorisation is the device's own `GATE_OFFICER` Supabase
 * session (issue #79), checked server-side against the verified token and unaffected by whatever is
 * stored here. Do not start gating UI on this value, and do not send it anywhere expecting it to
 * mean the user is who they say -- `components.md` section 1: "a shared-device attribution
 * mechanism, not an authentication boundary".
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
