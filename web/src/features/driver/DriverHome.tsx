import { useEffect, useState, type FormEvent } from 'react'
import { apiGet } from '../../core/http/api'
import { ProtectedLayout } from '../../layouts/ProtectedLayout'

type DriverContext = {
  as_of: string
  driver: { driver_id: string; driver_name: string; driver_status: string }
  primary_shipment: Record<string, unknown> | null
  current_appointment: Record<string, unknown> | null
  facility: Record<string, unknown> | null
  latest_eta: Record<string, unknown> | null
}

export function DriverHome() {
  return (
    <ProtectedLayout portal="driver" title="Driver assistant">
      {(profile) => (
        <DriverBody
          userId={profile.user_id}
          driverName={profile.full_name}
          driverId={profile.driver_id}
        />
      )}
    </ProtectedLayout>
  )
}

function DriverBody({
  userId,
  driverName,
  driverId,
}: {
  userId: string
  driverName: string
  driverId: string | null
}) {
  const [ctx, setCtx] = useState<DriverContext | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [draft, setDraft] = useState('')
  const [composerNote, setComposerNote] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    void apiGet<DriverContext>('/api/v1/driver/context')
      .then((res) => {
        setCtx(res.data)
        setError(null)
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [userId])

  function onComposerSubmit(e: FormEvent) {
    e.preventDefault()
    if (!draft.trim()) return
    setComposerNote(
      'Chat is a Sprint 1 shell only. Sprint 2 wires ChatOpenAI.bind_tools + a manual invoke loop.',
    )
    setDraft('')
  }

  const displayName = ctx?.driver.driver_name ?? driverName
  const status = ctx?.driver.driver_status ?? 'Context pending'
  const facilityLabel =
    typeof ctx?.facility?.facility_name === 'string'
      ? ctx.facility.facility_name
      : typeof ctx?.facility?.facility_id === 'string'
        ? ctx.facility.facility_id
        : 'Facility context'

  return (
    <div className="driver-workspace">
      <section className="chat-shell" aria-label="Driver AI assistant skeleton">
        <div className="chat-history">
          <div className="chat-day">Today</div>
          <div className="chat-row ai">
            <div className="chat-meta">
              <span className="chat-avatar" aria-hidden="true">
                AI
              </span>
              <span>SetuHaul AI</span>
            </div>
            <div className="chat-bubble ai-bubble">
              <p>
                Hello {displayName}. This is your driver assistant shell for the Sprint 1 POC. Live
                shipment, appointment, and ETA context appears beside this panel when available.
              </p>
              <p className="muted">
                Agent replies arrive in Sprint 2. No invented operational advice is shown here.
              </p>
            </div>
          </div>
          <div className="chat-row user">
            <div className="chat-meta">
              <span>You</span>
            </div>
            <div className="chat-bubble glass-bubble">
              <p>Show my current shipment and appointment status.</p>
            </div>
          </div>
          <div className="chat-row ai">
            <div className="chat-meta">
              <span className="chat-avatar" aria-hidden="true">
                AI
              </span>
              <span>SetuHaul AI</span>
            </div>
            <div className="chat-bubble ai-bubble">
              <p>
                Observational context loads from the API. Use the cards on the right — chat tools are
                not connected yet.
              </p>
            </div>
          </div>
        </div>

        <form className="chat-composer" onSubmit={onComposerSubmit}>
          <div className="composer-chips">
            <span className="chip secondary">{status}</span>
            <span className="chip primary">{facilityLabel}</span>
            {driverId ? <span className="chip primary">{driverId}</span> : null}
          </div>
          <div className="composer-row">
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ask SetuHaul about routes, cargo, or facility access…"
              aria-label="Message SetuHaul AI"
            />
            <button type="submit" aria-label="Send message (shell only)">
              Send
            </button>
          </div>
          {composerNote ? (
            <p className="fine-print" role="status">
              {composerNote}
            </p>
          ) : (
            <p className="fine-print">
              Composer is a Stitch-inspired shell. Sprint 2 connects ChatOpenAI + bind_tools.
            </p>
          )}
        </form>
      </section>

      <aside className="context-rail" aria-label="Driver operational context">
        <div className="sr-live" aria-live="polite" aria-atomic="true">
          {loading ? <p className="state">Loading driver context…</p> : null}
          {error ? (
            <p className="form-error" role="alert">
              Context API: {error}
            </p>
          ) : null}
        </div>
        {ctx ? (
          <>
            <article>
              <h2>Operational context</h2>
              <p className="muted">as_of {ctx.as_of}</p>
              <p>
                {ctx.driver.driver_name} · {ctx.driver.driver_id} · {ctx.driver.driver_status}
              </p>
            </article>
            <article>
              <h2>Primary shipment</h2>
              {ctx.primary_shipment ? (
                <pre>{JSON.stringify(ctx.primary_shipment, null, 2)}</pre>
              ) : (
                <p className="state">No active shipment</p>
              )}
            </article>
            <article>
              <h2>Current appointment</h2>
              {ctx.current_appointment ? (
                <pre>{JSON.stringify(ctx.current_appointment, null, 2)}</pre>
              ) : (
                <p className="state">No current appointment</p>
              )}
            </article>
            <article>
              <h2>Facility</h2>
              {ctx.facility ? (
                <pre>{JSON.stringify(ctx.facility, null, 2)}</pre>
              ) : (
                <p className="state">No facility context</p>
              )}
            </article>
          </>
        ) : !loading ? (
          <article>
            <h2>Operational context</h2>
            <p className="state">Unavailable until the context endpoint recovers.</p>
          </article>
        ) : null}
      </aside>
    </div>
  )
}
