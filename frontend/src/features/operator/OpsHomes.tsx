import { useCallback, useEffect, useState } from 'react'
import { apiGet, apiPost } from '../../core/http/api'
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
  payload?: Record<string, any>
}

type PendingConfirmationItem = {
  appointment_id: string
  shipment_id: string
  driver_id: string | null
  order_reference: string | null
  facility_id: string
  dock_id: string | null
  slot_start_ts: string | null
  slot_end_ts: string | null
  booked_at: string | null
}

function extractEscalationReason(item: EscalationItem): string {
  const p = item.payload || {}
  if (p.reason) return String(p.reason)
  if (p.note) return String(p.note)
  if (p.message) return String(p.message)
  if (p.rejected_reasons && Array.isArray(p.rejected_reasons) && p.rejected_reasons.length > 0) {
    const first = p.rejected_reasons[0]
    return typeof first === 'object'
      ? `${first.failure_code || 'SLOT_REJECTED'}: ${first.message || 'No dock available'}`
      : String(first)
  }
  if (item.escalation_type === 'NO_FEASIBLE_SLOT') {
    return 'No same-day dock slot available matching shipment requirements and driver ETA.'
  }
  if (item.escalation_type === 'DRIVER_BREAKDOWN') {
    return 'Driver reported vehicle breakdown or emergency incident on route.'
  }
  return 'Requires manual operational review and decision.'
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
  const [pendingConfirmations, setPendingConfirmations] = useState<PendingConfirmationItem[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [asOf, setAsOf] = useState<string | null>(null)

  // Decision Modal State
  const [selectedEscalation, setSelectedEscalation] = useState<EscalationItem | null>(null)
  const [decisionNote, setDecisionNote] = useState('')
  const [submittingDecision, setSubmittingDecision] = useState(false)
  const [confirmingAppointmentId, setConfirmingAppointmentId] = useState<string | null>(null)

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
      setAsOf(sum.data.as_of)
      setError(null)
      // Pending confirmations require an explicit facility scope (own facility for
      // an Operator, or a chosen one for global/Admin) — skip the call rather than
      // let the backend 403 when a global user hasn't picked a facility yet.
      if (facilityId || !global) {
        const pending = await apiGet<{ as_of: string; items: PendingConfirmationItem[] }>(
          `/api/v1/operations/pending-confirmations${q}`,
        )
        setPendingConfirmations(pending.data.items || [])
      } else {
        setPendingConfirmations([])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load dashboard data')
    } finally {
      setLoading(false)
    }
  }, [facilityId, global])

  async function handleConfirmAppointment(item: PendingConfirmationItem) {
    setConfirmingAppointmentId(item.appointment_id)
    try {
      await apiPost(
        `/api/v1/shipments/${item.shipment_id}/appointments/${item.appointment_id}/confirm`,
        { warehouse_confirmation_ref: `WH-OPS-${item.appointment_id}` },
        { idempotencyKey: `confirm-${item.appointment_id}-${Date.now()}` },
      )
      void load()
    } catch (err) {
      alert('Failed to confirm appointment: ' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setConfirmingAppointmentId(null)
    }
  }

  useEffect(() => {
    void load()
  }, [load])

  async function handleTakeDecision(escalationId: string, status: string) {
    setSubmittingDecision(true)
    try {
      await apiPost(`/api/v1/operations/escalations/${escalationId}/resolve`, {
        resolution_note: decisionNote || 'Resolved by Operations user',
        status: status,
      })
      setSelectedEscalation(null)
      setDecisionNote('')
      void load()
    } catch (err) {
      alert('Failed to resolve escalation: ' + (err instanceof Error ? err.message : String(err)))
    } finally {
      setSubmittingDecision(false)
    }
  }

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
            <h2>Pending confirmations</h2>
          </div>
          <span className="chip secondary">{pendingConfirmations.length} awaiting</span>
        </div>
        {global && !facilityId ? (
          <div className="empty-state">
            <strong>Pick a facility</strong>
            <span>Global scope needs a specific facility to list pending confirmations for.</span>
          </div>
        ) : pendingConfirmations.length === 0 ? (
          <div className="empty-state">
            <strong>Nothing waiting</strong>
            <span>New driver-booked appointments needing warehouse confirmation appear here.</span>
          </div>
        ) : (
          <ul className="exception-list">
            {pendingConfirmations.slice(0, 8).map((item) => (
              <li
                key={item.appointment_id}
                style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '14px' }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', width: '100%' }}>
                  <div>
                    <strong>{item.shipment_id}</strong>
                    <span style={{ marginLeft: '10px' }}>{item.dock_id || 'Dock TBD'}</span>
                    <small style={{ display: 'block', marginTop: '2px' }}>
                      Slot {formatTimestamp(item.slot_start_ts)} - {formatTimestamp(item.slot_end_ts)}
                    </small>
                  </div>
                  <div className="exception-meta" style={{ textAlign: 'right' }}>
                    {item.driver_id ? <span>{item.driver_id}</span> : null}
                    <span>Booked {formatTimestamp(item.booked_at)}</span>
                  </div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '4px' }}>
                  <button
                    type="button"
                    style={{
                      fontSize: '0.8rem',
                      padding: '6px 14px',
                      background: 'var(--accent)',
                      color: '#000',
                      border: 'none',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontWeight: 600,
                    }}
                    onClick={() => void handleConfirmAppointment(item)}
                    disabled={confirmingAppointmentId === item.appointment_id}
                  >
                    {confirmingAppointmentId === item.appointment_id ? 'Confirming…' : 'Confirm'}
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </article>

      <article className="ops-status-panel exception-panel">
        <div className="card-heading">
          <div>
            <h2>Escalation queue</h2>
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
            {escalations.slice(0, 8).map((item) => {
              const reasonText = extractEscalationReason(item)
              return (
                <li key={item.escalation_id} style={{ display: 'flex', flexDirection: 'column', gap: '8px', padding: '14px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', width: '100%' }}>
                    <div>
                      <strong>{item.shipment_id}</strong>
                      <span style={{ marginLeft: '10px' }}>
                        {prettyStatus(item.escalation_type)} · {prettyStatus(item.escalation_status)}
                      </span>
                      <small style={{ display: 'block', marginTop: '2px' }}>Opened {formatTimestamp(item.created_at)}</small>
                    </div>
                    <div className="exception-meta" style={{ textAlign: 'right' }}>
                      <span className="chip secondary">{item.severity_code}</span>
                      {item.driver_id ? <span style={{ marginLeft: '6px' }}>{item.driver_id}</span> : null}
                    </div>
                  </div>

                  <div
                    style={{
                      background: 'rgba(239, 68, 68, 0.1)',
                      borderLeft: '3px solid var(--accent)',
                      padding: '8px 12px',
                      borderRadius: '4px',
                      fontSize: '0.82rem',
                      color: 'var(--text)',
                      marginTop: '4px',
                    }}
                  >
                    <strong>Why Escalated:</strong> {reasonText}
                  </div>

                  <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '4px' }}>
                    <button
                      type="button"
                      style={{
                        fontSize: '0.8rem',
                        padding: '6px 14px',
                        background: 'var(--accent)',
                        color: '#000',
                        border: 'none',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontWeight: 600,
                      }}
                      onClick={() => {
                        setSelectedEscalation(item)
                        setDecisionNote('')
                      }}
                    >
                      Inspect &amp; Take Decision
                    </button>
                  </div>
                </li>
              )
            })}
          </ul>
        )}
      </article>

      {/* Decision Modal */}
      {selectedEscalation ? (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 9999,
            background: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '20px',
          }}
        >
          <div
            className="context-card"
            style={{
              maxWidth: '560px',
              width: '100%',
              background: '#161f33',
              border: '1px solid var(--outline)',
              borderRadius: '14px',
              padding: '24px',
              boxShadow: '0 20px 50px rgba(0,0,0,0.8)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
              <h2 style={{ margin: 0, fontSize: '1.2rem' }}>⚡ Escalation Decision</h2>
              <button
                type="button"
                style={{ background: 'none', border: 'none', color: 'var(--muted)', fontSize: '1.2rem', cursor: 'pointer' }}
                onClick={() => setSelectedEscalation(null)}
              >
                ✕
              </button>
            </div>

            <div className="data-grid" style={{ gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '16px' }}>
              <div className="data-field">
                <span>Shipment ID</span>
                <strong>{selectedEscalation.shipment_id}</strong>
              </div>
              <div className="data-field">
                <span>Escalation Type</span>
                <strong>{selectedEscalation.escalation_type}</strong>
              </div>
              <div className="data-field">
                <span>Driver</span>
                <strong>{selectedEscalation.driver_id || 'Unassigned'}</strong>
              </div>
              <div className="data-field">
                <span>Severity</span>
                <strong>{selectedEscalation.severity_code}</strong>
              </div>
            </div>

            <div
              style={{
                background: 'rgba(239, 68, 68, 0.12)',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                borderRadius: '8px',
                padding: '14px',
                marginBottom: '18px',
              }}
            >
              <p style={{ margin: '0 0 6px 0', fontSize: '0.85rem', fontWeight: 600, color: 'var(--accent)' }}>
                Why this requires Ops intervention:
              </p>
              <p style={{ margin: 0, fontSize: '0.9rem', lineHeight: 1.4 }}>
                {extractEscalationReason(selectedEscalation)}
              </p>
            </div>

            <div style={{ marginBottom: '20px' }}>
              <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '6px', color: 'var(--muted)', fontWeight: 500 }}>
                Operations Resolution Note
              </label>
              <input
                type="text"
                value={decisionNote}
                onChange={(e) => setDecisionNote(e.target.value)}
                placeholder="e.g. Approved manual dock override; notified gate team."
                style={{
                  width: '100%',
                  height: '44px',
                  padding: '0 14px',
                  background: 'var(--panel-high)',
                  color: 'var(--text)',
                  border: '1px solid var(--outline)',
                  borderRadius: '8px',
                  fontSize: '0.9rem',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
              <button
                type="button"
                className="secondary-btn"
                onClick={() => setSelectedEscalation(null)}
                disabled={submittingDecision}
              >
                Cancel
              </button>
              <button
                type="button"
                style={{
                  padding: '10px 18px',
                  background: 'var(--accent)',
                  color: '#000',
                  border: 'none',
                  borderRadius: '8px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
                onClick={() => void handleTakeDecision(selectedEscalation.escalation_id, 'RESOLVED')}
                disabled={submittingDecision}
              >
                {submittingDecision ? 'Saving…' : 'Mark Resolved'}
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </section>
  )
}
