import { useId, useState } from 'react'
import { Link } from 'react-router-dom'

import { AuthShell, Wordmark } from '@/features/auth/auth-shell'
import { Alert } from '@/shared/ui/alert'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'
import { PasswordField } from '@/shared/ui/password-field'

/** The four sign-in states (artboards 1-4). */
export type SignInState = 'at-rest' | 'error' | 'rate-limited'

/**
 * Artboards 1-4.  One shared sign-in for all six roles; the role decides the landing
 * surface, never a separate login page.
 *
 * Three rules that are correctness, not styling:
 *
 *  - **One field, "Email or phone", not two tabs.**  Drivers know their phone number, office
 *    staff know their email.  Disambiguate server-side rather than making the user choose.
 *
 *  - **The error is identical whichever half was wrong.**  "Those details don't match" for
 *    both wrong-user and wrong-password, and neither field is singled out -- singling one
 *    out IS the disclosure.  Anti-enumeration, deliberately.
 *
 *  - **"Forgotten your password?" stays live when rate-limited.**  A locked-out user still
 *    has a route forward.  The Sign in button is the one legitimate use of Disabled:
 *    temporary, self-resolving, and paired with the reason directly above it.
 *
 * Explicitly absent, and it must stay absent: Remember me, SSO, social buttons, "Sign up",
 * an "or continue with" divider, a marketing footer, any illustration.  Accounts are
 * invite-only.
 */
export function SignIn({
  state = 'at-rest',
  onSubmit,
  initialIdentifier = '',
  errorMessage,
  pending = false,
}: {
  state?: SignInState
  onSubmit?: (identifier: string, password: string) => void
  initialIdentifier?: string
  /**
   * Overrides the default "Those details don't match." copy while `state === 'error'`.
   *
   * Added when the screen was wired to the real `signInWithPassword` (2026-09-01). The
   * anti-enumeration rule above is about **credential** failures and stays the default: a wrong
   * email and a wrong password both render the same sentence, from this component, with no field
   * marked. But a transport failure or an unconfigured client is not a credential failure at all,
   * and telling a driver at a roadside "those details don't match" when the request never left the
   * phone is a lie that costs them their password attempts. So the caller may substitute a
   * sentence for the non-credential cases only -- `App.tsx`'s `SignInRoute` is the only caller and
   * branches on `AuthError.code`, never on a message string
   * (`supabase.com/docs/guides/auth/debugging/error-codes`: *"Always use `error.code` and
   * `error.name` to identify errors, not string matching on error messages."*).
   */
  errorMessage?: string
  /**
   * The request is in flight. `components.md` section 1's Loading row: **label unchanged**, width
   * frozen, `aria-busy="true"`. The spinner half of that row is not rendered because it specifies
   * *"spinner replaces the leading icon"* and this button has no leading icon -- adding one just
   * for the loading state would change the button's at-rest layout, which the row explicitly
   * guards against. Reported as a partial implementation rather than silently reinterpreted.
   */
  pending?: boolean
}) {
  const identifierId = useId()
  const [identifier, setIdentifier] = useState(initialIdentifier)
  const [password, setPassword] = useState('')

  const rateLimited = state === 'rate-limited'

  return (
    <AuthShell>
      <Wordmark />
      <form
        className="mt-10"
        onSubmit={(e) => {
          e.preventDefault()
          onSubmit?.(identifier, password)
        }}
      >
        <div>
          <Label
            htmlFor={identifierId}
            className="mb-2 block text-supporting font-medium text-muted-foreground"
          >
            Email or phone
          </Label>
          <Input
            id={identifierId}
            name="identifier"
            type="text"
            autoComplete="username"
            inputMode="email"
            spellCheck={false}
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
            // Neither field carries aria-invalid on a credential failure: marking one would
            // tell an attacker which half was wrong.
          />
        </div>

        <div className="mt-4">
          <PasswordField
            label="Password"
            name="password"
            autoComplete="current-password"
            value={password}
            onChange={setPassword}
          />
        </div>

        {state === 'error' ? (
          <Alert variant="danger" className="mt-4" data-testid="signin-error">
            {errorMessage ?? <>Those details don&rsquo;t match.</>}
          </Alert>
        ) : null}

        {rateLimited ? (
          <Alert variant="danger" className="mt-4">
            Too many attempts. Try again in 5 minutes.
          </Alert>
        ) : null}

        <div className="mt-6">
          <Button
            type="submit"
            variant="constructive"
            full
            disabled={rateLimited || pending}
            aria-busy={pending || undefined}
            title={rateLimited ? 'Locked for 5 minutes after too many attempts' : undefined}
          >
            Sign in
          </Button>
        </div>

        <div className="mt-6">
          <Link
            to="/reset"
            className="text-body text-link underline underline-offset-2 hover:text-primary-hover"
          >
            Forgotten your password?
          </Link>
        </div>
      </form>
    </AuthShell>
  )
}
