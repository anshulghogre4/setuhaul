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

type EscalationItem = {
  escalation_id: string
  shipment_id: string
  driver_id: string | null
  escalation_type: string
  escalation_status: string
  severity_code: string
  created_at: string
}

function prettyStatus(status: string) {
  return status
    .toLowerCase()
    .split('_')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function formatTimestamp(value: string | null | undefined) {
  if (!value) return 'Pending'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZoneName: 'short',
  }).format(date)
}

/** Shared Operator + Admin dashboard. Scope comes from verified profile, not the URL. */
export function OpsHome() {
  return (
    <ProtectedLayout portal="ops" title="Operations dashboard">
      {(profile) => (
        <OpsBody
          facilityId={profile.facility_id}
          global={
            profile.role_name === 'ADMIN' ||
            profile.role_name === 'TRANSPORT_MANAGER' ||
            profile.role_name === 'REGIONAL_OPERATIONS_HEAD' ||
            profile.scope.type === 'global' ||
            profile.scope.type === 'global_read_only'
          }
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
  const [escalations, setEscalations] = useState<EscalationItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [asOf, setAsOf] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    const q = !global && facilityId ? `?facility_id=${encodeURIComponent(facilityId)}` : ''
    try {
      const [sum, exc, queue] = await Promise.all([
        apiGet<Summary>(`/api/v1/operations/dashboard-summary${q}`),
        apiGet<{ as_of: string; items: ExceptionItem[] }>(`/api/v1/operations/exceptions${q}`),
        apiGet<{ as_of: string; items: EscalationItem[] }>(`/api/v1/operations/escalation-queue${q}`),
      ])
      setSummary(sum.data)
      setExceptions(exc.data.items || [])
      setEscalations(queue.data.items || [])
      setAsOf(queue.data.as_of || exc.data.as_of || sum.data.as_of)
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
        <p className="state">Loading operations summary...</p>
      </div>
    )
  }

  const statusEntries = Object.entries(summary.shipments_by_status)
  const totalShipments = statusEntries.reduce((sum, [, n]) => sum + n, 0)
  const maxStatusCount = Math.max(...statusEntries.map(([, n]) => n), 1)
  const scopeLabel = global ? 'Network read model' : facilityId || 'Facility scope'
  const freshest = asOf || summary.as_of
  const recentForDemo = exceptions.filter(
    (e) => e.shipment_id === 'SHP1017' || e.driver_id === 'DRV001',
  )

  return (
    <section className="ops-dashboard" aria-label="Operations dashboard">
      <div className="ops-hero">
        <div>
          <p className="eyebrow">{global ? 'Global read-only' : 'Facility operations'}</p>
          <h2>{global ? 'Network overview' : 'Facility overview'}</h2>
          <div className="ops-meta-row" aria-label="Dashboard scope">
            <span>{formatTimestamp(freshest)}</span>
            <span>{roleName.replaceAll('_', ' ')}</span>
            <span>{summary.scope.type.replaceAll('_', ' ')}</span>
            {summary.scope.facility_id ? <span>{summary.scope.facility_id}</span> : null}
          </div>
        </div>
        <div className="ops-hero-actions">
          {summary.scope.read_only ? <span className="chip primary">Read only</span> : null}
          <button type="button" onClick={() => void load()} aria-label="Refresh operations data">
            Refresh
          </button>
        </div>
      </div>

      <div className="ops-metrics">
        <article className="metric-card accent-blue">
          <p className="metric-label">Shipments in scope</p>
          <p className="metric-value">{totalShipments}</p>
          <p className="metric-note">{scopeLabel}</p>
        </article>
        <article className="metric-card accent-warn">
          <p className="metric-label">Open exceptions</p>
          <p className="metric-value">{summary.open_exceptions}</p>
          <p className="metric-note">Requires coordinator attention</p>
        </article>
        <article className="metric-card accent-green">
          <p className="metric-label">Status buckets</p>
          <p className="metric-value">{statusEntries.length}</p>
          <p className="metric-note">Authorized aggregate only</p>
        </article>
      </div>

      <div className="ops-content-grid">
        <article className="ops-status-panel status-distribution">
          <div className="card-heading">
            <div>
              <h2>Shipment status</h2>
              <p className="muted">Authorized aggregate for the current scope.</p>
            </div>
            <span className="chip secondary">{statusEntries.length} buckets</span>
          </div>
          {statusEntries.length === 0 ? (
            <p className="state">No shipment status rows in current scope</p>
          ) : (
            <ul className="status-list">
              {statusEntries.map(([status, count]) => (
                <li key={status}>
                  <span>{prettyStatus(status)}</span>
                  <div className="status-measure">
                    <span className="status-bar">
                      <span style={{ width: `${Math.max((count / maxStatusCount) * 100, 8)}%` }} />
                    </span>
                    <strong>{count}</strong>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </article>

        <article className="ops-status-panel exception-panel">
          <div className="card-heading">
            <div>
              <h2>Latest exceptions</h2>
              <p className="muted">Refresh after a driver ETA write to reconcile state.</p>
            </div>
            <span className="chip secondary">{exceptions.length} rows</span>
          </div>
          {exceptions.length === 0 ? (
            <div className="empty-state">
              <strong>Clear in this scope</strong>
              <span>No open exception rows are visible for {scopeLabel}.</span>
            </div>
          ) : (
            <ul className="exception-list">
              {(recentForDemo.length ? recentForDemo : exceptions.slice(0, 8)).map((e) => (
                <li key={e.exception_id}>
                  <div>
                    <strong>{e.shipment_id || 'Unassigned shipment'}</strong>
                    <span>
                      {prettyStatus(e.exception_type)} - {prettyStatus(e.exception_status)}
                    </span>
                    <small>{e.description}</small>
                  </div>
                  <div className="exception-meta">
                    <span>{e.driver_id}</span>
                    {e.declared_eta_ts ? <span>ETA {formatTimestamp(e.declared_eta_ts)}</span> : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </article>
      </div>

      <article className="ops-status-panel exception-panel">
        <div className="card-heading">
          <div>
            <h2>Escalation queue</h2>
            <p className="muted">Open human-takeover items for the authorized facility scope.</p>
          </div>
          <span className="chip secondary">{escalations.length} open</span>
        </div>
        {escalations.length === 0 ? (
          <div className="empty-state">
            <strong>No active escalations</strong>
            <span>New no-slot and exception handoffs will appear here.</span>
          </div>
        ) : (
          <ul className="exception-list">
            {escalations.slice(0, 8).map((item) => (
              <li key={item.escalation_id}>
                <div>
                  <strong>{item.shipment_id}</strong>
                  <span>{prettyStatus(item.escalation_type)} · {prettyStatus(item.escalation_status)}</span>
                  <small>Opened {formatTimestamp(item.created_at)}</small>
                </div>
                <div className="exception-meta">
                  <span>{item.severity_code}</span>
                  {item.driver_id ? <span>{item.driver_id}</span> : null}
                </div>
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
