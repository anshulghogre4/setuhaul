import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiGet, type MeProfile } from '../../core/http/api'
import {
  portalHome,
  roleToPortal,
  signIn,
  type Portal,
} from '../../core/auth/supabase'

type Props = {
  portal: Portal
  title: string
  subtitle: string
}

export function LoginForm({ portal, title, subtitle }: Props) {
  const navigate = useNavigate()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const { error: authError } = await signIn(email.trim(), password)
      if (authError) {
        setError(authError.message)
        return
      }
      const me = await apiGet<MeProfile>('/api/v1/auth/me')
      const actual = roleToPortal(me.data.role_name)
      if (!actual) {
        setError('This account role is not enabled for the POC portals.')
        return
      }
      if (actual !== portal) {
        setError(`This account belongs to the ${actual} portal. Redirecting…`)
        navigate(portalHome[actual], { replace: true })
        return
      }
      navigate(portalHome[portal], { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="login-shell">
      <div className="login-panel">
        <p className="eyebrow">SetuHaul AI</p>
        <h1>{title}</h1>
        <p className="lede">{subtitle}</p>
        <form
          onSubmit={onSubmit}
          className="login-form"
          noValidate
          aria-busy={busy}
          aria-describedby={error ? 'login-status' : undefined}
        >
          <label htmlFor={`${portal}-email`}>
            Work email
            <input
              id={`${portal}-email`}
              type="email"
              name="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label htmlFor={`${portal}-password`}>
            Password
            <input
              id={`${portal}-password`}
              type="password"
              name="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <div id="login-status" className="sr-live" aria-live="polite" aria-atomic="true">
            {busy ? <p className="state">Signing in…</p> : null}
            {error ? (
              <p className="form-error" role="alert">
                {error}
              </p>
            ) : null}
          </div>
          <button type="submit" disabled={busy}>
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        <p className="fine-print">
          Role is decided by the verified backend profile, never by this URL.
        </p>
      </div>
    </div>
  )
}
