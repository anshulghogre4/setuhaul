import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { toast } from 'sonner'
import { useRegisterSW } from 'virtual:pwa-register/react'

import { BottomNav } from './components/bottom-nav'

/**
 * The driver route root.
 *
 * ## No `<AppShell>`, and that is not an omission
 *
 * `core/auth/identity.ts` already encodes the driver's shell exclusions as code:
 * `DRIVER -> rail: null`, `landingPathFor -> '/driver'`, `hasFacilityScope(DRIVER) -> false`,
 * `idlePolicyFor(DRIVER) -> null`. `AppShell` exists to render a 56px icon rail, a facility
 * switcher and an idle-timeout warning — three things this surface deliberately does not have.
 * Mounting it here would render chrome for a role the shell's own configuration says has none.
 * The PWA runs 320–768px and a rail expanding to a 240px overlay is not viable on a 390px phone.
 *
 * The driver also has **no idle timeout at all** — `idlePolicyFor` returns `null` because
 * *"drivers must never be signed out mid-exception"* — so there is no `<IdleWarning>` here
 * either.
 *
 * ## Density, set ONCE
 *
 * `data-density="comfortable"` at the route root, giving `--tap: 44px` and `--content-p: 24px`.
 * Never per component, never a user preference (`spacing-and-layout.md`'s density rule, U8).
 * F12 is resolved in favour of the foundation here: content padding is 24px, not the mockup's
 * 12px.
 *
 * ## PWA registration
 *
 * `vite-plugin-pwa` was configured in E5.0 (manifest + workbox in `vite.config.ts`,
 * `theme_color: #F8FAFC` = surface-base) but nothing registered the service worker. Registered
 * here rather than in `providers.tsx` on purpose: a service worker's scope is its whole origin,
 * and the desk surfaces (planner, ops, admin) should **not** get offline caching of a live
 * capacity console. Registering from the driver route means the SW exists for the surface that
 * is specified as an installable PWA and for nobody else.
 *
 * `registerType: 'prompt'` (E5.0's choice) is why this uses `onNeedRefresh` rather than
 * auto-reloading: a silent reload can land mid-exception, and `auth-and-scoping.md` is explicit
 * that a driver must never lose in-flight work. The prompt is a toast with an explicit action.
 *
 * API verified against the installed `vite-plugin-pwa@1.3.0`'s own generated client
 * (`dist/client/build/react.js`) rather than from memory: `useRegisterSW` returns
 * `{ needRefresh: [bool, setter], offlineReady: [bool, setter], updateServiceWorker }`. The
 * `virtual:pwa-register/react` types are already wired — `tsconfig.app.json` carries
 * `"types": ["vite/client", "vite-plugin-pwa/react"]`.
 *
 * ⚠ One dependency note: that generated client does `await import("workbox-window")`.
 * `workbox-window` is present in `node_modules` **transitively** via `vite-plugin-pwa`, not as a
 * declared devDependency, which the plugin's own docs say it should be. Left undeclared here
 * because adding it to `package.json` without regenerating `package-lock.json` would break
 * `npm ci`; recorded as a follow-up so it is a known state rather than a surprise.
 */
export function DriverShell() {
  const {
    needRefresh: [needRefresh, setNeedRefresh],
    updateServiceWorker,
  } = useRegisterSW({
    onRegisterError(error) {
      // Never surfaced to the driver: a failed SW registration degrades the app to a plain web
      // page, which still works. Logging it is for us, not for them.
      console.warn('[driver] service worker registration failed', error)
    },
  })

  useEffect(() => {
    if (!needRefresh) return
    toast('A new version is ready', {
      description: 'Reload when you are not mid-conversation.',
      duration: Infinity,
      action: {
        label: 'Reload',
        onClick: () => void updateServiceWorker(true),
      },
      onDismiss: () => setNeedRefresh(false),
    })
  }, [needRefresh, setNeedRefresh, updateServiceWorker])

  return (
    // dvh, not vh: on mobile Safari `100vh` includes the retracted URL bar, so the composer sits
    // below the fold until the driver scrolls -- and the composer is the one element that must
    // always be thumb-reachable.
    <div
      data-density="comfortable"
      data-surface="driver"
      className="flex h-dvh min-h-0 flex-col bg-background text-foreground"
    >
      <Outlet />
      <BottomNav />
    </div>
  )
}
