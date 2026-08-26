import { useId, useState } from 'react'
import { Link } from 'react-router-dom'
import { Check, Link2Off } from 'lucide-react'

import { AuthShell } from '@/features/auth/auth-shell'
import { Alert } from '@/shared/ui/alert'
import { Button } from '@/shared/ui/button'
import { EmptyState } from '@/shared/ui/empty-state'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'
import { PasswordField } from '@/shared/ui/password-field'

/** The five reset states (artboards 6-10). */
export type ResetState = 'request' | 'sent' | 'set-new' | 'mismatch' | 'expired'

function BackToSignIn() {
  return (
    <Link
      to="/signin"
      className="text-body text-link underline underline-offset-2 hover:text-primary-hover"
    >
      Back to sign in
    </Link>
  )
}

/**
 * Artboards 6-10.  Two screens sharing one card chassis: screen A is reached from sign-in,
 * screen B is a cold entry from an emailed link with no session and no context.
 *
 * **Email only, not sign-in's combined "Email or phone" field.**  Decided 2026-08-22 for
 * v1: a phone-registered account (the driver role) has no self-service reset here, which is
 * defensible because the driver session is already long-lived with silent refresh, so
 * re-entering a password at all is rare.  The fallback is an admin-assisted reset, not a new
 * phone-OTP flow.
 *
 * **"Link sent" is informational blue, never green.**  Nothing has succeeded yet -- green in
 * this product means CONFIRMED or "an action succeeded", and an unread email is neither.  No
 * checkmark animation, no confetti.
 *
 * **The wording is identical whether or not the account exists**, for the same reason sign-in
 * has one error string, and "expired" and "already used" share a string too: neither state
 * should teach an attacker anything about the account.
 */
export function PasswordReset({
  state = 'request',
  onRequest,
  onSetPassword,
  onRequestNewLink,
}: {
  state?: ResetState
  onRequest?: (email: string) => void
  onSetPassword?: (password: string) => void
  onRequestNewLink?: () => void
}) {
  const emailId = useId()
  const [email, setEmail] = useState('')

  // Artboard 10 -- the most likely real outcome after the happy path.  The form is NOT
  // rendered at all behind this: a disabled form under a message reads as a broken page
  // rather than an expired link.
  if (state === 'expired') {
    return (
      <AuthShell>
        <EmptyState
          className="px-0 py-2"
          icon={Link2Off}
          title="This reset link has expired or has already been used."
          body="Links work once and last 30 minutes."
          actions={
            <Button variant="constructive" onClick={onRequestNewLink}>
              Request a new link
            </Button>
          }
        />
      </AuthShell>
    )
  }

  // Artboards 8-9 -- set a new password, and the mismatch variant.
  if (state === 'set-new' || state === 'mismatch') {
    return (
      <AuthShell>
        <h1 className="text-h2">Set a new password</h1>
        <form
          className="mt-6"
          onSubmit={(e) => {
            e.preventDefault()
            onSetPassword?.('')
          }}
        >
          <PasswordField label="New password" name="newpw" autoComplete="new-password" />

          {/* Requirements carry a state marker per line -- a check when met, a neutral dot
              when not -- never colour as the only signal.  No coloured strength meter
              anywhere: the list says what to DO rather than scoring what was typed.
              ⚠ The two requirement strings are placeholders.  No foundations file states a
              password policy, so the wording is not spec-sourced; the component, its markers
              and its typography are. */}
          <ul className="mt-2 flex flex-col gap-1">
            <li className="flex items-center gap-2 text-supporting text-muted-foreground">
              <Check className="size-3.5" aria-hidden="true" />
              At least 12 characters
            </li>
            <li className="flex items-center gap-2 text-supporting text-subtle-foreground">
              <span
                className="mx-[5px] size-1.5 shrink-0 rounded-full bg-marker-unmet"
                aria-hidden="true"
              />
              Not a password you have used here before
            </li>
          </ul>

          <div className="mt-6">
            <PasswordField
              label="Confirm new password"
              name="confirmpw"
              autoComplete="new-password"
              invalid={state === 'mismatch'}
              // This one CAN name the field: which field is wrong is not a secret here,
              // unlike a credential failure at sign-in.
              error={state === 'mismatch' ? 'Those two passwords don’t match.' : undefined}
            />
          </div>

          <div className="mt-6">
            <Button type="submit" variant="constructive" full>
              Set password and sign in
            </Button>
          </div>
        </form>
      </AuthShell>
    )
  }

  // Artboard 7 -- the form is replaced in place.
  if (state === 'sent') {
    return (
      <AuthShell>
        <h1 className="text-h2">Reset your password</h1>
        <Alert variant="info" className="mt-4">
          If that email matches an account, a reset link is on its way. The link works once and
          expires in 30 minutes.
        </Alert>
        <div className="mt-6">
          <BackToSignIn />
        </div>
      </AuthShell>
    )
  }

  // Artboard 6 -- request a link.
  return (
    <AuthShell>
      <h1 className="text-h2">Reset your password</h1>
      <p className="mt-2 text-body text-muted-foreground">
        Enter the email address you sign in with.
      </p>
      <form
        className="mt-6"
        onSubmit={(e) => {
          e.preventDefault()
          onRequest?.(email)
        }}
      >
        <Label htmlFor={emailId} className="mb-2 block text-supporting font-medium text-muted-foreground">
          Email
        </Label>
        <Input
          id={emailId}
          name="email"
          type="email"
          autoComplete="username"
          inputMode="email"
          spellCheck={false}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
        />
        {/* Validation is on blur, not keystroke -- telling someone their half-typed address
            is wrong is noise, not help (components.md section 12). */}
        <div className="mt-6">
          <Button type="submit" variant="constructive" full>
            Send reset link
          </Button>
        </div>
        <div className="mt-6">
          <BackToSignIn />
        </div>
      </form>
    </AuthShell>
  )
}
