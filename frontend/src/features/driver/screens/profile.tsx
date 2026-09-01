import { Bell, BellOff, ChevronLeft, TriangleAlert } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { useAuth } from '@/core/auth/auth-context'
import { useTheme } from '@/shared/lib/theme'
import { Button } from '@/shared/ui/button'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogTitle,
} from '@/shared/ui/dialog'
import { copy } from '../lib/copy'
import { fetchDriverContext, type DriverContext } from '../lib/data'

/**
 * Screen 13 — Profile. Minimal, and **everything is read-only except notification settings**.
 *
 * ## What the server actually has, and what it does not — flagged, not filled in
 *
 * `screens.md` section 5 draws four identity facts:
 *
 * ```
 *   Manoj Sharma                 ← /driver/context -> driver.driver_name        ✓ exists
 *   +91-9000010006               ← /driver/context -> driver.phone             ✓ exists
 *   Carrier: Rajasthan Roadlines ← ✗ NOT RETURNED by any driver-scoped endpoint
 *   UP14GT4106 · 32ft multi-axle ← ✗ NOT RETURNED by any driver-scoped endpoint
 * ```
 *
 * `implementation-spec.md` section 0.1 asked for exactly this to be confirmed before building
 * the screen. Confirmed, against source: `load_driver_operational_snapshot` selects
 * `(driver_id, driver_name, phone, licence_number, home_base_city, driver_status)` from
 * `public.drivers` — **no carrier, no vehicle** — and `GET /auth/me` returns
 * `(user_id, email, full_name, role_id, role_name, driver_id, facility_id, permissions, scope)`,
 * also neither. `shipments.carrier_id` / `shipments.vehicle_id` exist in the table but are not in
 * `/driver/context`'s projection, and neither is `carriers.carrier_name` or any `vehicles` row.
 *
 * So carrier and vehicle **render as absent** rather than as a placeholder or an invented value.
 * That is TMS-owned data (section 1) that the driver read does not expose yet, and a Profile
 * screen showing "Vehicle: —" would be inventing a fact the driver does not have. Filed as a
 * follow-up (extend `/driver/context` with carrier name + vehicle registration/type, or add
 * them to `/auth/me`); not built here, because it is a backend contract change outside issue
 * #36's `area:frontend` scope.
 *
 * ## F10 — the theme row, and the warning that is a requirement
 *
 * `01-driver-chat/accessibility.md`: *"Light theme is the default and **cannot be overridden to
 * dark without a warning**"* — because dark UI in direct sunlight on a cheap LCD is genuinely
 * unreadable. F10 recorded that the copy, form and dismissibility were all unspecified. Built
 * here as a **confirm dialog on the light -> dark transition only** (never on dark -> light),
 * naming the actual consequence. Marked as F10's answer for the owner rather than as settled
 * design.
 *
 * ## F11 — sign-out friction
 *
 * `00-foundations/components.md` section 19's three-tier friction model has no tier assigned to
 * sign-out, and *"signing a driver out mid-exception is what `auth-and-scoping.md` calls a
 * product failure."* Built as a **confirm dialog whose safer action is first in DOM order**
 * (U79) and which names what the driver loses. Also flagged as F11's answer, not settled.
 *
 * Sign-out goes through `useAuth().signOutLocal()`, which wraps the shared single-device
 * `signOut()` in `core/auth/supabase.ts` — fixed during E3.5 to pass `scope: 'local'` explicitly,
 * because Supabase's bare `signOut()` defaults to `scope: 'global'` and was silently revoking
 * every other device's session. Do not "simplify" it back to the bare call.
 *
 * Routed through the provider rather than calling `signOut()` directly (2026-09-01) so the React
 * state clears in the same tick as the revocation; `RequireAuth` then redirects to `/signin` on
 * the next render. A direct call worked only because the `SIGNED_OUT` event eventually arrived.
 */
export function DriverProfile() {
  const { signOutLocal } = useAuth()
  const [ctx, setCtx] = useState<DriverContext | null>(null)
  const { choice, setChoice, resolved } = useTheme()
  const [darkWarning, setDarkWarning] = useState(false)
  const [signOutConfirm, setSignOutConfirm] = useState(false)
  const [pushPermission, setPushPermission] = useState<NotificationPermission | 'unsupported'>(
    'default',
  )

  useEffect(() => {
    void fetchDriverContext().then(setCtx).catch(() => setCtx(null))
    setPushPermission(
      typeof Notification === 'undefined' ? 'unsupported' : Notification.permission,
    )
  }, [])

  const driver = ctx?.driver

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex min-h-12 shrink-0 items-center gap-1 border-b border-border bg-card px-2">
        <Link
          to="/driver"
          aria-label={copy.backToThreads}
          className="grid size-12 shrink-0 place-items-center rounded-md focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
        >
          <ChevronLeft size={24} strokeWidth={2} aria-hidden="true" />
        </Link>
        <h1 className="text-body-lg font-semibold">{copy.navProfile}</h1>
      </header>

      {/* `<main>`, not a `<div>` -- see the note in `thread-list.tsx`. Measured 2026-08-31:
          the driver surface had no main landmark on any screen. */}
      <main className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-(--content-p)">
        {/* Read-only identity. No edit affordance anywhere -- this is TMS-owned and displayed
            for confirmation only. */}
        <section aria-labelledby="identity-heading">
          <h2 id="identity-heading" className="sr-only">
            Your details
          </h2>
          <p className="text-h2">{driver?.driver_name ?? ctx?.profile?.full_name ?? ''}</p>
          {driver?.phone ? (
            <p className="mt-1 font-mono text-body-lg text-muted-foreground">{driver.phone}</p>
          ) : null}
          {driver?.home_base_city ? (
            <p className="mt-1 text-body text-muted-foreground">
              Home base: {driver.home_base_city}
            </p>
          ) : null}
          {/* Carrier and Vehicle rows are deliberately absent -- see the header note. When the
              server read gains them, they go here, in this order (screens.md section 5). */}
        </section>

        <hr className="my-6 border-border" />

        <section aria-labelledby="settings-heading" className="space-y-1">
          <h2 id="settings-heading" className="sr-only">
            Settings
          </h2>

          {/* Notifications: the re-entry point for a driver who denied push at onboarding
              (auth-and-scoping.md). Shows the CURRENT permission plainly, and the consequence
              once, not as a nag. */}
          <div className="flex min-h-11 items-center justify-between gap-3">
            <span className="flex items-center gap-2 text-body-lg">
              {pushPermission === 'granted' ? (
                <Bell size={18} strokeWidth={2} aria-hidden="true" />
              ) : (
                <BellOff size={18} strokeWidth={2} aria-hidden="true" />
              )}
              Notifications
            </span>
            {pushPermission === 'granted' ? (
              <span className="text-body text-muted-foreground">On</span>
            ) : pushPermission === 'unsupported' ? (
              <span className="text-body text-muted-foreground">Not available</span>
            ) : (
              <Button
                variant="neutral"
                size="sm"
                onClick={() => {
                  void Notification.requestPermission().then(setPushPermission)
                }}
              >
                {copy.pushPrimingEnable}
              </Button>
            )}
          </div>
          {pushPermission === 'denied' ? (
            <p className="text-body text-muted-foreground">{copy.pushDeniedStatus}</p>
          ) : null}

          {/* Language: English with **no picker** in v1 (U31) -- present so the setting has an
              obvious future home, and deliberately not a disabled dropdown, which would imply a
              choice exists. */}
          <div className="flex min-h-11 items-center justify-between gap-3">
            <span className="text-body-lg">Language</span>
            <span className="text-body text-muted-foreground">English</span>
          </div>

          <div className="flex min-h-11 items-center justify-between gap-3">
            <span className="text-body-lg">Theme</span>
            <Button
              variant="neutral"
              size="sm"
              onClick={() => {
                // The warning fires ONLY on light -> dark. Going back to light needs no warning:
                // light is the safe direction on this surface.
                if (resolved === 'light') setDarkWarning(true)
                else setChoice('light')
              }}
            >
              {choice === 'system' ? `System (${resolved})` : resolved === 'dark' ? 'Dark' : 'Light'}
            </Button>
          </div>
        </section>

        <hr className="my-6 border-border" />

        <Button variant="destructive" onClick={() => setSignOutConfirm(true)}>
          {copy.signOut}
        </Button>
      </main>

      {/* F10's answer. Names the real consequence rather than asking "are you sure". */}
      <Dialog open={darkWarning} onOpenChange={setDarkWarning}>
        <DialogContent>
          <DialogTitle className="flex items-center gap-2">
            <TriangleAlert size={18} strokeWidth={2} aria-hidden="true" />
            Dark mode is hard to read in sunlight
          </DialogTitle>
          <DialogDescription>
            This app is built for light theme because a dark screen in direct sun on most phones
            is unreadable. You can switch back at any time.
          </DialogDescription>
          <DialogFooter>
            {/* Safer action FIRST in DOM order (U79), so a fast keyboard user who overshoots
                lands on the harmless one. */}
            <DialogClose asChild>
              <Button variant="neutral">Keep light</Button>
            </DialogClose>
            <Button
              variant="cautionary"
              onClick={() => {
                setChoice('dark')
                setDarkWarning(false)
              }}
            >
              Switch to dark
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* F11's answer. */}
      <Dialog open={signOutConfirm} onOpenChange={setSignOutConfirm}>
        <DialogContent>
          <DialogTitle>Sign out?</DialogTitle>
          <DialogDescription>
            You will need your password to get back in, and you will not see slot changes for your
            loads until you do.
          </DialogDescription>
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="neutral">Stay signed in</Button>
            </DialogClose>
            <Button variant="destructive" onClick={() => void signOutLocal()}>
              {copy.signOut}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
