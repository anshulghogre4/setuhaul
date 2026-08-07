import { useEffect, useState } from 'react'
import { apiGet } from '../../core/http/api'
import { ProtectedLayout } from '../../layouts/ProtectedLayout'

type Summary = {
  as_of: string
  scope: { type: string; facility_id: string | null; read_only: boolean }
  shipments_by_status: Record<string, number>
  open_exceptions: number
  note?: string
}

/** Shared Operator + Admin dashboard. Scope comes from verified profile, not the URL. */
export function OpsHome() {
  return (
    <ProtectedLayout portal="ops" title="Operations dashboard">
      {(profile) => (
        <OpsBody
          facilityId={profile.facility_id}
          global={profile.role_name === 'ADMIN' || profile.scope.type === 'global'}
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
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const q = !global && facilityId ? `?facility_id=${encodeURIComponent(facilityId)}` : ''
    void apiGet<Summary>(`/api/v1/operations/dashboard-summary${q}`)
      .then((res) => {
        setSummary(res.data)
        setError(null)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [facilityId, global])

  if (error) {
    return (
      <div className="sr-live" aria-live="polite" aria-atomic="true">
        <p className="form-error" role="alert">
          {error}
        </p>
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

  return (
    <section className="ops-dashboard" aria-label="Operations dashboard skeleton">
      <div className="ops-hero">
        <div>
          <p className="eyebrow">{global ? 'Global read-only' : 'Facility operations'}</p>
          <h2>{global ? 'Network overview' : 'Facility overview'}</h2>
          <p className="muted">
            as_of {summary.as_of} · signed in as {roleName} · scope {summary.scope.type}
            {summary.scope.facility_id ? ` · ${summary.scope.facility_id}` : ''}
          </p>
        </div>
        {summary.scope.read_only ? <span className="chip primary">Read only</span> : null}
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

      <p className="fine-print">
        {summary.note ??
          'Sprint 1 observational dashboard skeleton. Chat / write tools arrive in Sprint 2.'}
      </p>
    </section>
  )
}
