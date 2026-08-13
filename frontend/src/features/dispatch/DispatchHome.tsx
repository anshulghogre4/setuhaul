import { useEffect, useRef, useState, type FormEvent } from 'react'
import { apiGet, apiPost, formatUserFriendlyError } from '../../core/http/api'
import { ProtectedLayout } from '../../layouts/ProtectedLayout'

type DriverItem = {
  driver_id: string
  driver_name: string
  home_base_city: string
  driver_status: string
}

type FacilityItem = {
  facility_id: string
  facility_name: string
  city: string
  state: string
}

type DispatchResult = {
  shipment_id: string
  order_reference: string
  driver_id: string
  driver_name: string
  facility_id: string
  facility_name: string
  planned_eta: string
  priority_code: string
  appointment?: Record<string, unknown> | null
  booking_result?: Record<string, unknown> | null
}

function BoundedLOVSelect({
  label,
  options,
  value,
  onChange,
  disabled,
}: {
  label: string
  options: Array<{ id: string; label: string }>
  value: string
  onChange: (val: string) => void
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [search, setSearch] = useState('')
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    if (open) {
      document.addEventListener('mousedown', handleClickOutside)
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [open])

  const selectedOpt = options.find((o) => o.id === value)
  const filtered = options.filter(
    (o) =>
      o.label.toLowerCase().includes(search.toLowerCase()) ||
      o.id.toLowerCase().includes(search.toLowerCase())
  )

  const fieldStyle: React.CSSProperties = {
    width: '100%',
    minWidth: 0,
    height: '44px',
    padding: '0 14px',
    boxSizing: 'border-box',
    background: 'var(--panel-high)',
    color: 'var(--text)',
    border: '1px solid var(--outline)',
    borderRadius: '8px',
    fontSize: '0.9rem',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    cursor: disabled ? 'not-allowed' : 'pointer',
    userSelect: 'none',
  }

  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: '0.85rem',
    marginBottom: '6px',
    color: 'var(--muted)',
    fontWeight: 500,
  }

  return (
    <div style={{ position: 'relative', minWidth: 0, width: '100%' }} ref={containerRef}>
      <label style={labelStyle}>{label}</label>
      <div style={fieldStyle} onClick={() => !disabled && setOpen(!open)}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', paddingRight: '8px', minWidth: 0, flex: 1 }}>
          {selectedOpt ? selectedOpt.label : 'Select an option…'}
        </span>
        <span style={{ fontSize: '0.7rem', opacity: 0.6, flexShrink: 0 }}>{open ? '▲' : '▼'}</span>
      </div>

      {open ? (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            zIndex: 9999,
            background: '#161f33',
            border: '1px solid var(--outline)',
            borderRadius: '8px',
            boxShadow: '0 12px 32px rgba(0,0,0,0.6)',
            maxHeight: '210px',
            overflow: 'hidden',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <input
            type="text"
            placeholder="Type to filter options…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              width: '100%',
              padding: '10px 12px',
              boxSizing: 'border-box',
              background: '#0d1527',
              border: 'none',
              borderBottom: '1px solid var(--outline)',
              color: '#fff',
              fontSize: '0.85rem',
              outline: 'none',
            }}
            autoFocus
          />
          <div style={{ overflowY: 'auto', flex: 1, maxHeight: '160px' }}>
            {filtered.length > 0 ? (
              filtered.map((opt) => (
                <div
                  key={opt.id}
                  onClick={() => {
                    onChange(opt.id)
                    setOpen(false)
                    setSearch('')
                  }}
                  style={{
                    padding: '10px 14px',
                    cursor: 'pointer',
                    fontSize: '0.85rem',
                    background: opt.id === value ? 'rgba(56, 189, 248, 0.2)' : 'transparent',
                    color: opt.id === value ? 'var(--accent)' : 'var(--text)',
                    borderBottom: '1px solid rgba(255,255,255,0.03)',
                  }}
                >
                  {opt.label}
                </div>
              ))
            ) : (
              <div style={{ padding: '12px', fontSize: '0.85rem', color: 'var(--muted)', textAlign: 'center' }}>
                No matching options
              </div>
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}

export function DispatchHome() {
  return (
    <ProtectedLayout portal="ops" title="Dispatch & Load Assignment">
      {() => <DispatchBody />}
    </ProtectedLayout>
  )
}

function DispatchBody() {
  const [drivers, setDrivers] = useState<DriverItem[]>([])
  const [facilities, setFacilities] = useState<FacilityItem[]>([])
  const [loadingLists, setLoadingLists] = useState(true)
  const [listError, setListError] = useState<string | null>(null)

  // Form State
  const [selectedDriver, setSelectedDriver] = useState('')
  const [selectedFacility, setSelectedFacility] = useState('')
  const [orderRef, setOrderRef] = useState('')
  const [productCategory, setProductCategory] = useState('GENERAL_LOAD')
  const [loadWeightKg, setLoadWeightKg] = useState('12000')
  const [requiredDockType, setRequiredDockType] = useState('ANY')
  const [priorityCode, setPriorityCode] = useState('HIGH')
  const [plannedEta, setPlannedEta] = useState('2026-08-16T18:40')
  const [unloadMin, setUnloadMin] = useState('30')

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [result, setResult] = useState<DispatchResult | null>(null)

  useEffect(() => {
    async function loadDropdowns() {
      setLoadingLists(true)
      try {
        const [dRes, fRes] = await Promise.all([
          apiGet<{ drivers: DriverItem[] }>('/api/v1/dispatch/drivers'),
          apiGet<{ facilities: FacilityItem[] }>('/api/v1/dispatch/facilities'),
        ])
        setDrivers(dRes.data.drivers || [])
        setFacilities(fRes.data.facilities || [])
        if (dRes.data.drivers.length > 0) {
          setSelectedDriver(dRes.data.drivers[0].driver_id)
        }
        if (fRes.data.facilities.length > 0) {
          setSelectedFacility(fRes.data.facilities[0].facility_id)
        }
      } catch (err) {
        setListError(formatUserFriendlyError(err))
      } finally {
        setLoadingLists(false)
      }
    }
    void loadDropdowns()
  }, [])

  async function onSubmitDispatch(e: FormEvent) {
    e.preventDefault()
    if (!selectedDriver || !selectedFacility || !plannedEta) {
      setSubmitError('Please select a driver, destination facility, and planned ETA.')
      return
    }
    setSubmitting(true)
    setSubmitError(null)
    setResult(null)

    let etaIso = plannedEta
    if (!etaIso.includes('Z') && !etaIso.includes('+')) {
      etaIso = `${plannedEta}:00+05:30`
    }

    try {
      const res = await apiPost<DispatchResult>('/api/v1/dispatch/shipments', {
        driver_id: selectedDriver,
        destination_facility_id: selectedFacility,
        order_reference: orderRef.trim() || undefined,
        product_category: productCategory,
        load_weight_kg: Number(loadWeightKg) || 12000,
        required_dock_type: requiredDockType,
        priority_code: priorityCode,
        original_eta_ts: etaIso,
        expected_unload_min: Number(unloadMin) || 30,
      })
      setResult(res.data)
    } catch (err) {
      setSubmitError(formatUserFriendlyError(err))
    } finally {
      setSubmitting(false)
    }
  }

  const fieldStyle: React.CSSProperties = {
    width: '100%',
    height: '44px',
    padding: '0 14px',
    boxSizing: 'border-box',
    background: 'var(--panel-high)',
    color: 'var(--text)',
    border: '1px solid var(--outline)',
    borderRadius: '8px',
    fontSize: '0.9rem',
    fontFamily: 'inherit',
    outline: 'none',
  }

  const labelStyle: React.CSSProperties = {
    display: 'block',
    fontSize: '0.85rem',
    marginBottom: '6px',
    color: 'var(--muted)',
    fontWeight: 500,
  }

  const driverOptions = drivers.map((d) => ({
    id: d.driver_id,
    label: `${d.driver_name} (${d.driver_id}) — ${d.home_base_city}`,
  }))

  const facilityOptions = facilities.map((f) => ({
    id: f.facility_id,
    label: `${f.facility_name} (${f.facility_id}) — ${f.city}`,
  }))

  const priorityOptions = [
    { id: 'CRITICAL', label: 'CRITICAL (+4000 pts)' },
    { id: 'HIGH', label: 'HIGH (+3000 pts)' },
    { id: 'NORMAL', label: 'NORMAL (+2000 pts)' },
    { id: 'LOW', label: 'LOW (+1000 pts)' },
  ]

  const categoryOptions = [
    { id: 'GENERAL_LOAD', label: 'GENERAL_LOAD' },
    { id: 'PERISHABLE_FOOD', label: 'PERISHABLE_FOOD (Reefer)' },
    { id: 'ELECTRONICS', label: 'ELECTRONICS' },
    { id: 'HAZMAT', label: 'HAZMAT' },
  ]

  const dockOptions = [
    { id: 'ANY', label: 'ANY Compatible Dock' },
    { id: 'STANDARD_FLATBED', label: 'STANDARD_FLATBED' },
    { id: 'COLD_STORAGE', label: 'COLD_STORAGE' },
    { id: 'HEAVY_DUTY', label: 'HEAVY_DUTY' },
  ]

  return (
    <div style={{ padding: '20px', maxWidth: '1100px', margin: '0 auto' }}>
      <header style={{ marginBottom: '24px' }}>
        <p className="eyebrow">Dispatch Console</p>
        <h1 style={{ margin: 0, fontSize: '1.6rem' }}>Assign Shipment &amp; Pre-Book Appointment</h1>
        <p className="muted" style={{ marginTop: '6px' }}>
          Assign cargo shipments to drivers. The engine automatically finds the best dock slot and pre-marks an initial appointment.
        </p>
      </header>

      {listError ? <div className="form-error">Error loading data: {listError}</div> : null}

      <div style={{ display: 'grid', gridTemplateColumns: result ? '1.1fr 0.9fr' : '1fr', gap: '24px', alignItems: 'start' }}>
        <form className="context-card" onSubmit={onSubmitDispatch} style={{ padding: '24px', borderRadius: '12px' }}>
          <h2>Shipment Assignment Details</h2>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '18px', marginTop: '18px' }}>
            <BoundedLOVSelect
              label="Select Driver"
              options={driverOptions}
              value={selectedDriver}
              onChange={setSelectedDriver}
              disabled={loadingLists || submitting}
            />

            <BoundedLOVSelect
              label="Destination Facility"
              options={facilityOptions}
              value={selectedFacility}
              onChange={setSelectedFacility}
              disabled={loadingLists || submitting}
            />

            <div>
              <label style={labelStyle}>Order Reference (Optional)</label>
              <input
                type="text"
                value={orderRef}
                onChange={(e) => setOrderRef(e.target.value)}
                placeholder="e.g. ORD-2026-DISP-01"
                disabled={submitting}
                style={fieldStyle}
              />
            </div>

            <BoundedLOVSelect
              label="Priority Code"
              options={priorityOptions}
              value={priorityCode}
              onChange={setPriorityCode}
              disabled={submitting}
            />

            <BoundedLOVSelect
              label="Cargo Category"
              options={categoryOptions}
              value={productCategory}
              onChange={setProductCategory}
              disabled={submitting}
            />

            <BoundedLOVSelect
              label="Required Dock Type"
              options={dockOptions}
              value={requiredDockType}
              onChange={setRequiredDockType}
              disabled={submitting}
            />

            <div>
              <label style={labelStyle}>Load Weight (kg)</label>
              <input
                type="number"
                value={loadWeightKg}
                onChange={(e) => setLoadWeightKg(e.target.value)}
                disabled={submitting}
                style={fieldStyle}
              />
            </div>

            <div>
              <label style={labelStyle}>Planned Arrival ETA</label>
              <input
                type="datetime-local"
                value={plannedEta}
                onChange={(e) => setPlannedEta(e.target.value)}
                disabled={submitting}
                style={fieldStyle}
              />
            </div>

            <div>
              <label style={labelStyle}>Expected Unload Duration (Mins)</label>
              <input
                type="number"
                value={unloadMin}
                onChange={(e) => setUnloadMin(e.target.value)}
                disabled={submitting}
                style={fieldStyle}
              />
            </div>
          </div>

          {submitError ? <div className="form-error" style={{ marginTop: '16px' }}>{submitError}</div> : null}

          <button
            type="submit"
            className="primary-btn"
            disabled={submitting || loadingLists}
            style={{ marginTop: '24px', width: '100%', height: '46px', fontSize: '0.95rem' }}
          >
            {submitting ? 'Creating Shipment & Pre-Booking Appointment…' : 'Assign Shipment & Pre-Book Appointment'}
          </button>
        </form>

        {result ? (
          <article
            className="context-card identity-card"
            style={{
              padding: '24px',
              borderRadius: '12px',
              maxHeight: '520px',
              overflowY: 'auto',
              border: '1px solid var(--outline)',
              boxSizing: 'border-box',
            }}
          >
            <span className="live-dot" style={{ float: 'right' }} />
            <h2 style={{ marginTop: 0, color: 'var(--accent)', fontSize: '1.2rem' }}>✅ Shipment &amp; Appointment Created</h2>

            <div className="data-grid" style={{ marginTop: '18px' }}>
              <div className="data-field tone-good">
                <span>Shipment ID</span>
                <strong>{result.shipment_id}</strong>
              </div>
              <div className="data-field">
                <span>Order Reference</span>
                <strong>{result.order_reference}</strong>
              </div>
              <div className="data-field tone-good">
                <span>Assigned Driver</span>
                <strong>{result.driver_name} ({result.driver_id})</strong>
              </div>
              <div className="data-field">
                <span>Destination</span>
                <strong>{result.facility_name} ({result.facility_id})</strong>
              </div>
              <div className="data-field tone-warn">
                <span>Priority</span>
                <strong>{result.priority_code}</strong>
              </div>
              <div className="data-field">
                <span>Planned ETA</span>
                <strong>{result.planned_eta}</strong>
              </div>
            </div>

            <h3 style={{ marginTop: '24px', fontSize: '1rem', borderTop: '1px solid var(--outline)', paddingTop: '16px' }}>
              📅 Pre-Marked Appointment Status
            </h3>

            {result.appointment ? (
              <div className="data-grid">
                <div className="data-field tone-good">
                  <span>Appointment ID</span>
                  <strong>{String(result.appointment.appointment_id || '—')}</strong>
                </div>
                <div className="data-field">
                  <span>Status</span>
                  <strong>{String(result.appointment.status || result.appointment.appointment_status || 'PENDING_CONFIRMATION')}</strong>
                </div>
                <div className="data-field">
                  <span>Slot ID</span>
                  <strong>{String(result.appointment.slot_id || '—')}</strong>
                </div>
                <div className="data-field">
                  <span>Dock</span>
                  <strong>{String(result.appointment.dock_id || 'Assigned')}</strong>
                </div>
              </div>
            ) : (
              <p className="state">No initial slot available for selected ETA; shipment created in-transit.</p>
            )}
          </article>
        ) : null}
      </div>
    </div>
  )
}
