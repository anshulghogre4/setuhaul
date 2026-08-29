/**
 * Which of U108's two physical device contexts this browser is.
 *
 * `screens.md`'s header splits the surface into a mounted **gate booth** (1280x800, landscape,
 * gate-in/gate-out only) and a handheld **yard tablet** (800x1280, portrait, the five in-between
 * states). The shift bar names it on every screen from 3 onward ("Gate booth - Jaipur - Shift:
 * Ramesh K." vs "Yard tablet - ...").
 *
 * **Source: inferred, not in a design file.** Nothing in `04-gate-yard-kiosk/` or in `backend/`
 * says how a device declares which one it is -- `screens.md` section 1 only says the *facility* is
 * "fixed to the device's own assignment", and there is no device-registration concept anywhere in
 * the product. Orientation is the one signal actually available to a browser, and it happens to be
 * a true discriminator here because both devices are orientation-locked in the design (the booth
 * kiosk is mounted and never rotated; the yard tablet is a portrait handheld). Flagged in the build
 * report rather than presented as a spec value.
 *
 * Deliberately **not** a width breakpoint: `spacing-and-layout.md`'s breakpoint table is itself
 * unresolved for this surface (`implementation-spec.md` Fork C -- it has one "Gate kiosk,
 * 1024-1366px, landscape locked" row and no row at all for an 800px-wide portrait tablet, which
 * taken literally would show an orientation prompt and break the entire yard half). Reading
 * orientation instead avoids inheriting a contradiction that is still open.
 */
export type DeviceContext = 'gate-booth' | 'yard-tablet'

const PORTRAIT = '(orientation: portrait)'

export function currentDeviceContext(): DeviceContext {
  // SSR-safe guard: this app is client-rendered, but `matchMedia` is also absent in a plain jsdom
  // environment, and defaulting to the booth would silently mis-label the yard half.
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return 'gate-booth'
  return window.matchMedia(PORTRAIT).matches ? 'yard-tablet' : 'gate-booth'
}

export function deviceLabel(device: DeviceContext): string {
  return device === 'yard-tablet' ? 'Yard tablet' : 'Gate booth'
}

/**
 * Subscribe to orientation changes. A mounted booth kiosk never fires this; a yard tablet that is
 * physically rotated mid-shift does, and the shift bar has to stop claiming the wrong device.
 * `MediaQueryList.addEventListener('change')` rather than the deprecated `addListener` -- the
 * latter is still present in browsers but is marked deprecated in the current DOM types and
 * `tsconfig`'s `lib` would flag it.
 */
export function watchDeviceContext(onChange: (device: DeviceContext) => void): () => void {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return () => {}
  const mql = window.matchMedia(PORTRAIT)
  const handler = () => onChange(mql.matches ? 'yard-tablet' : 'gate-booth')
  mql.addEventListener('change', handler)
  return () => mql.removeEventListener('change', handler)
}
