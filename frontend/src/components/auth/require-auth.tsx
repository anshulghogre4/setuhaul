import type { ReactNode } from 'react'
import { Navigate, useLocation } from 'react-router-dom'

import { AuthShell, Wordmark } from '@/features/auth/auth-shell'
import { Alert } from '@/shared/ui/alert'
import { Button } from '@/shared/ui/button'
import { useAuth } from '@/core/auth/auth-context'
import { canAccess, homePathFor } from '@/core/auth/surface-access'

/**
 * The route guard. Wraps every surface route in `App.tsx`.
 *
 * ## This is presentation-layer honesty. The server remains the authority.
 *
 * Nothing here grants access to anything. Every read and every write still goes through
 * `core/http/api.ts`, which attaches the caller's own Supabase token, and the backend re-derives
 * scope from that token on every request (M15; `require_roles` at `backend/app/core/deps.py:276`).
 * Deleting this component would expose no data — it would only let the app render a console whose
 * every request 403s, which is a worse experience and a worse signal than a redirect.
 *
 * What it *does* buy is the thing that was actually broken: before this existed, `/planner` and
 * every other surface rendered for an anonymous visitor with a fixture identity in the shell.
 *
 * ## Two redirects, and why they differ
 *
 *  - **No session -> `/signin`, carrying the attempted location** in router state, so a driver who
 *    followed a push notification to `/driver/t/THREAD` lands back on that exact thread after
 *    signing in rather than on a generic home.
 *  - **Signed in, wrong role -> that role's OWN home**, never a 403 page. A dead end telling
 *    someone they may not be here is useless when the app already knows exactly where they should
 *    be; `auth-and-scoping.md`'s Role-landing table is that answer, via `landingPathFor`.
 */
export function RequireAuth({ children }: { children: ReactNode }) {
  const { status, identity, error, retry, signOutLocal } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    /**
     * Deliberately a sentence rather than a skeleton of the surface behind it. A skeleton would
     * imply the surface is coming, and at this point the app does not yet know whether this
     * visitor is allowed on it at all — `components.md` section 13's skeleton rule is about
     * content whose shape is already known.
     */
    return (
      <AuthShell>
        <Wordmark />
        <p className="mt-10 text-body text-muted-foreground" role="status">
          Checking your session…
        </p>
      </AuthShell>
    )
  }

  if (status === 'error') {
    /**
     * **The state that must never be a fixture fallback.** The session is valid but the identity
     * read failed, so the app knows *someone* is signed in and does not know *who*. Rendering a
     * placeholder planner here is exactly the defect this whole change removes, so the honest
     * options are: try again, or sign out.
     */
    return (
      <AuthShell>
        <Wordmark />
        <Alert variant="danger" className="mt-10">
          {error ?? 'Could not load your account.'}
        </Alert>
        <div className="mt-6 flex gap-3">
          <Button variant="constructive" onClick={retry}>
            Try again
          </Button>
          <Button variant="neutral" onClick={() => void signOutLocal()}>
            Sign out
          </Button>
        </div>
      </AuthShell>
    )
  }

  if (status === 'anonymous' || identity === null) {
    return <Navigate to="/signin" state={{ from: location }} replace />
  }

  if (!canAccess(identity.activeRole, location.pathname)) {
    const home = homePathFor(identity.activeRole)
    // Guard against a mapping that would bounce someone forever: if a role's own home is a surface
    // it cannot access, render the refusal rather than loop. Cannot happen with the current tables
    // (both derive from the same server gates), and this asserts that rather than assuming it.
    if (!canAccess(identity.activeRole, home)) {
      return (
        <AuthShell>
          <Wordmark />
          <Alert variant="danger" className="mt-10">
            Your role ({identity.activeRoleLabel}) has no surface in this application.
          </Alert>
          <div className="mt-6">
            <Button variant="neutral" onClick={() => void signOutLocal()}>
              Sign out
            </Button>
          </div>
        </AuthShell>
      )
    }
    return <Navigate to={home} replace />
  }

  return <>{children}</>
}
