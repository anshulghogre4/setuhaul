import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { apiGet, type MeProfile } from '../core/http/api'
import {
  getSession,
  portalLogin,
  roleToPortal,
  signOut,
  type Portal,
} from '../core/auth/supabase'

type Props = {
  portal: Portal
  title: string
  children: (profile: MeProfile, refresh: () => Promise<void>) => ReactNode
}

export function ProtectedLayout({ portal, title, children }: Props) {
  const navigate = useNavigate()
  const [profile, setProfile] = useState<MeProfile | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const session = await getSession()
      if (!session) {
        setProfile(null)
        return
      }
      const me = await apiGet<MeProfile>('/api/v1/auth/me')
      const actual = roleToPortal(me.data.role_name)
      if (actual !== portal) {
        setError(`Wrong portal for role ${me.data.role_name}.`)
        setProfile(null)
        return
      }
      setProfile(me.data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load profile')
      setProfile(null)
    } finally {
      setLoading(false)
    }
  }, [portal])

  useEffect(() => {
    void load()
  }, [load])

  if (!loading && !profile && !error) {
    return <Navigate to={portalLogin[portal]} replace />
  }

  async function onLogout() {
    await signOut()
    navigate(portalLogin[portal], { replace: true })
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">SetuHaul AI</p>
          <h1>{title}</h1>
        </div>
        <div className="topbar-actions">
          {profile ? (
            <details className="profile-menu">
              <summary aria-label={`Profile menu for ${profile.full_name}`}>
                {profile.full_name}
              </summary>
              <div className="profile-panel">
                <p>
                  <strong>{profile.role_name}</strong>
                </p>
                <p>{profile.email}</p>
                <p>User {profile.user_id}</p>
                {profile.facility_id ? <p>Facility {profile.facility_id}</p> : null}
                {profile.driver_id ? <p>Driver {profile.driver_id}</p> : null}
                <p className="scope">{profile.scope.type}</p>
                <button type="button" onClick={() => void onLogout()}>
                  Log out
                </button>
              </div>
            </details>
          ) : null}
        </div>
      </header>
      <main>
        <div className="sr-live" aria-live="polite" aria-atomic="true">
          {loading ? <p className="state">Loading…</p> : null}
          {error ? (
            <p className="form-error" role="alert">
              {error}
            </p>
          ) : null}
        </div>
        {profile ? children(profile, load) : null}
      </main>
    </div>
  )
}
