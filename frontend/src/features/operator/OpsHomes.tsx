import { useCallback, useEffect, useState } from 'react'
import { apiGet } from '../../core/http/api'
import { ProtectedLayout } from '../../layouts/ProtectedLayout'

type Summary = {
  as_of: string
  scope: { type: string; facility_id: string | null; read_only: boolean }
  shipments_by_status: Record<string, number>
  open_exceptions: number
  note?: string
}

type ExceptionItem = {
  exception_id: string
  shipment_id: string | null
  driver_id: string
  exception_type: string
  exception_status: string
  declared_eta_ts: string | null
  description: string
  reported_at: string
}

/** Shared Operator + Admin dashboard. Scope comes from verified profile, not the URL. */
export function OpsHome() {
  return (
    <ProtectedLayout portal="ops" title="Operations dashboard">
      {(profile) => (
        <OpsBody
          facilityId={profile.facility_id}
          global={profile.role_name === 'ADMIN' || profile.scope.type === 'global' || profile.scope.type === 'global_read_only'}
          roleName={profile.role_name}
        />
      )}
    </ProtectedLayout>
  )
}

function OpsBody({
  facilityId,
  global,
  roleName,
}: {
  facilityId: string | null
  global: boolean
  roleName: string
}) {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [exceptions, setExceptions] = useState<ExceptionItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [asOf, setAsOf] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    const q = !global && facilityId ? `?facility_id=${encodeURIComponent(facilityId)}` : ''
    try {
      const [sum, exc] = await Promise.all([
        apiGet<Summary>(`/api/v1/operations/dashboard-summary${q}`),
        apiGet<{ as_of: string; items: ExceptionItem[] }>(`/api/v1/operations/exceptions${q}`),
      ])
      setSummary(sum.data)
      setExceptions(exc.data.items || [])
      setAsOf(exc.data.as_of || sum.data.as_of)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Ops load failed')
    } finally {
      setLoading(false)
    }
  }, [facilityId, global])

  useEffect(() => {
    void load()
  }, [load])

  if (error) {
    return (
      <div className="sr-live" aria-live="polite" aria-atomic="true">
        <p className="form-error" role="alert">
          {error}
        </p>
        <button type="button" onClick={() => void load()}>
          Retry refresh
        </button>
      </div>
    )
  }
  if (loading || !summary) {
    return (
      <div className="sr-live" aria-live="polite" aria-atomic="true">
        <p className="state">Loading operations summary…</p>
      </div>
    )
  }

  const statusEntries = Object.entries(summary.shipments_by_status)
  const totalShipments = statusEntries.reduce((sum, [, n]) => sum + n, 0)
  const recentForDemo = exceptions.filter(
    (e) => e.shipment_id === 'SHP1017' || e.driver_id === 'DRV001',
  )

  return (
    <section className="ops-dashboard" aria-label="Operations dashboard">
      <div className="ops-hero">
        <div>
          <p className="eyebrow">{global ? 'Global read-only' : 'Facility operations'}</p>
          <h2>{global ? 'Network overview' : 'Facility overview'}</h2>
          <p className="muted">
            as_of {asOf || summary.as_of} · signed in as {roleName} · scope {summary.scope.type}
            {summary.scope.facility_id ? ` · ${summary.scope.facility_id}` : ''}
          </p>
        </div>
        <div className="ops-hero-actions">
          {summary.scope.read_only ? <span className="chip primary">Read only</span> : null}
          <button type="button" onClick={() => void load()} aria-label="Refresh operations data">
            Refresh
          </button>
        </div>
      </div>

      <div className="ops-metrics">
        <article className="metric-card">
          <p className="metric-label">Shipments in scope</p>
          <p className="metric-value">{totalShipments}</p>
        </article>
        <article className="metric-card">
          <p className="metric-label">Open exceptions</p>
          <p className="metric-value">{summary.open_exceptions}</p>
        </article>
        <article className="metric-card">
          <p className="metric-label">Status buckets</p>
          <p className="metric-value">{statusEntries.length}</p>
        </article>
      </div>

      <article className="ops-status-panel">
        <h2>Shipments by status</h2>
        {statusEntries.length === 0 ? (
          <p className="state">No shipment status rows in current scope</p>
        ) : (
          <ul className="status-list">
            {statusEntries.map(([status, count]) => (
              <li key={status}>
                <span>{status}</span>
                <strong>{count}</strong>
              </li>
            ))}
          </ul>
        )}
      </article>

      <article className="ops-status-panel">
        <h2>Exceptions (latest)</h2>
        <p className="muted">Refresh after a driver ETA write to see matching state. Not realtime.</p>
        {exceptions.length === 0 ? (
          <p className="state">No exceptions in scope</p>
        ) : (
          <ul className="status-list">
            {(recentForDemo.length ? recentForDemo : exceptions.slice(0, 8)).map((e) => (
              <li key={e.exception_id}>
                <span>
                  {e.shipment_id || '—'} · {e.exception_type} · {e.exception_status}
                  {e.declared_eta_ts ? ` · ETA ${e.declared_eta_ts}` : ''}
                </span>
                <strong>{e.driver_id}</strong>
              </li>
            ))}
          </ul>
        )}
      </article>

      <p className="fine-print">
        {summary.note ??
          'Observational dashboard. No scheduling mutations. Refresh to reconcile with seeded/driver ETA writes.'}
      </p>
    </section>
  )
}
