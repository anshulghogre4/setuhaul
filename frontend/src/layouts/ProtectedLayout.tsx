import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
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

function ProfileMenu({ profile, onLogout }: { profile: MeProfile; onLogout: () => void }) {
  const detailsRef = useRef<HTMLDetailsElement>(null)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (detailsRef.current && detailsRef.current.open && !detailsRef.current.contains(event.target as Node)) {
        detailsRef.current.open = false
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  return (
    <details className="profile-menu" ref={detailsRef}>
      <summary aria-label={`Profile menu for ${profile.full_name}`}>
        {profile.full_name}
      </summary>
      <div className="profile-panel">
        <p className="profile-role">
          <strong>{profile.role_name.replaceAll('_', ' ')}</strong>
        </p>
        <p>{profile.email}</p>
        <p>User ID : {profile.user_id}</p>
        {profile.facility_id ? <p>Facility {profile.facility_id}</p> : null}
        {profile.driver_id ? <p>Driver {profile.driver_id}</p> : null}
        <button type="button" className="secondary-btn logout-btn" onClick={onLogout}>
          Log out
        </button>
      </div>
    </details>
  )
}

export function ProtectedLayout({ portal, title, children }: Props) {
  const navigate = useNavigate()
  const location = useLocation()
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
        setLoading(false)
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
      setError(err instanceof Error ? err.message : 'Auth verification failed')
      setProfile(null)
    } finally {
      setLoading(false)
    }
  }, [navigate, portal])

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
          {profile ? <ProfileMenu profile={profile} onLogout={() => void onLogout()} /> : null}
        </div>
      </header>
      {portal === 'ops' ? (
        <nav
          style={{
            display: 'flex',
            gap: '8px',
            padding: '12px 24px 0 24px',
            borderBottom: '1px solid var(--outline)',
            background: 'rgba(15, 23, 42, 0.6)',
          }}
        >
          <Link
            to="/ops"
            style={{
              padding: '8px 18px',
              borderRadius: '8px 8px 0 0',
              background: location.pathname === '/ops' ? 'var(--panel-high)' : 'transparent',
              color: location.pathname === '/ops' ? 'var(--accent)' : 'var(--muted)',
              fontWeight: 600,
              fontSize: '0.9rem',
              textDecoration: 'none',
              borderBottom: location.pathname === '/ops' ? '2px solid var(--accent)' : '2px solid transparent',
              transition: 'all 0.15s ease',
            }}
          >
            Dock Command
          </Link>
        </nav>
      ) : null}
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
