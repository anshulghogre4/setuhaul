import { useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { apiGet, apiPost } from '../../core/http/api'
import { ProtectedLayout } from '../../layouts/ProtectedLayout'
import './DriverLayout.css'

type DriverContext = {
  as_of: string
  driver: { driver_id: string; driver_name: string; driver_status: string }
  primary_shipment: Record<string, unknown> | null
  current_appointment: Record<string, unknown> | null
  facility: Record<string, unknown> | null
  latest_eta: Record<string, unknown> | null
}

type ChatMessage = {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
}

type ChatHistoryResponse = {
  thread_id: string | null
  session_id: string | null
  messages: Array<{ role: string; content: string; client_message_id?: string | null }>
  memory_degraded?: boolean
  degraded?: boolean
  degrade_reason?: string | null
  ttl_seconds?: number
  non_authoritative?: boolean
  code?: string
}

type ChatResponse = {
  thread_id: string
  session_id: string
  response: string
  tool_calls: Array<{
    name: string
    args: Record<string, unknown>
    result?: unknown
    result_preview?: string
  }>
  memory_degraded: boolean
  memory_degrade_reason: string | null
  ux_state: string
  confirmation?: {
    shipment_id?: string
    declared_eta_ts?: string
    display_eta?: string
    code?: string
  } | null
}

function renderFormattedText(content: string) {
  if (!content) return null
  const lines = content.split('\n')
  return lines.map((line, lineIdx) => {
    if (!line.trim()) {
      return <div key={lineIdx} className="chat-spacer" />
    }

    const parts: React.ReactNode[] = []
    let lastIndex = 0
    const regex = /(\*\*(.*?)\*\*|`(.*?)`)/g
    let match: RegExpExecArray | null

    while ((match = regex.exec(line)) !== null) {
      if (match.index > lastIndex) {
        parts.push(line.slice(lastIndex, match.index))
      }

      if (match[2] !== undefined) {
        parts.push(<strong key={`${lineIdx}-${match.index}`}>{match[2]}</strong>)
      } else if (match[3] !== undefined) {
        parts.push(
          <code key={`${lineIdx}-${match.index}`} className="chat-inline-code">
            {match[3]}
          </code>
        )
      }

      lastIndex = regex.lastIndex
    }

    if (lastIndex < line.length) {
      parts.push(line.slice(lastIndex))
    }

    return (
      <p key={lineIdx} className="chat-line">
        {parts}
      </p>
    )
  })
}

type EtaWriteResult = {
  status: string
  display_eta?: string
  shipment?: Record<string, unknown>
  eta_update?: Record<string, unknown>
  exception?: Record<string, unknown>
  declared_eta_ts?: string
  requires_confirmation?: boolean
}

function valueText(value: unknown, fallback = 'Unknown') {
  if (value === null || value === undefined || value === '') return fallback
  return String(value)
}

function formatHumanDateTime(value: unknown, fallback = '—'): string {
  if (value === null || value === undefined || value === '') return fallback
  const raw = String(value).trim()
  try {
    const date = new Date(raw)
    if (isNaN(date.getTime())) return raw
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    }).format(date)
  } catch {
    return raw
  }
}

function hasEtaChanged(original: unknown, latest: unknown): boolean {
  if (!latest || !original) return false
  const origStr = String(original).trim()
  const latStr = String(latest).trim()
  if (!origStr || !latStr || origStr === latStr) return false
  const origTime = new Date(origStr).getTime()
  const latTime = new Date(latStr).getTime()
  if (!isNaN(origTime) && !isNaN(latTime)) {
    return origTime !== latTime
  }
  return origStr !== latStr
}

function getField(record: Record<string, unknown> | null | undefined, keys: string[]) {
  if (!record) return null
  for (const key of keys) {
    if (record[key] !== null && record[key] !== undefined && record[key] !== '') return record[key]
  }
  return null
}

function getDriverConversationIds(userId: string): { sessionId: string; threadId: string | null } {
  const key = `setuhaul:driver-conversation:${userId}`
  const legacySessionKey = `setuhaul:driver-session:${userId}`
  try {
    const raw = window.localStorage.getItem(key)
    if (raw) {
      const parsed = JSON.parse(raw) as { sessionId?: string; threadId?: string | null }
      if (parsed.sessionId) {
        return {
          sessionId: parsed.sessionId,
          threadId: parsed.threadId || null,
        }
      }
    }
  } catch {
    // ignore corrupt local state
  }
  const legacy = window.sessionStorage.getItem(legacySessionKey)
  const sessionId = legacy || `web-${crypto.randomUUID()}`
  window.localStorage.setItem(key, JSON.stringify({ sessionId, threadId: null }))
  window.sessionStorage.setItem(legacySessionKey, sessionId)
  return { sessionId, threadId: null }
}

function saveDriverConversationIds(
  userId: string,
  sessionId: string,
  threadId: string | null,
) {
  const key = `setuhaul:driver-conversation:${userId}`
  window.localStorage.setItem(key, JSON.stringify({ sessionId, threadId }))
  window.sessionStorage.setItem(`setuhaul:driver-session:${userId}`, sessionId)
}

function DataField({
  label,
  value,
  tone,
}: {
  label: string
  value: unknown
  tone?: 'good' | 'warn' | 'neutral'
}) {
  return (
    <div className={`data-field ${tone ? `tone-${tone}` : ''}`}>
      <span>{label}</span>
      <strong>{valueText(value)}</strong>
    </div>
  )
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
  const statusId = useId()
  const [ctx, setCtx] = useState<DriverContext | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [draft, setDraft] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const initialIds = getDriverConversationIds(userId)
  const [threadId, setThreadId] = useState<string | null>(initialIds.threadId)
  const [sessionId, setSessionId] = useState(initialIds.sessionId)
  const [sending, setSending] = useState(false)
  const [uxState, setUxState] = useState<string>('ready')
  const [pendingConfirm, setPendingConfirm] = useState<ChatResponse['confirmation']>(null)
  const [memoryNote, setMemoryNote] = useState<string | null>(null)
  const [lastTools, setLastTools] = useState<string[]>([])
  const [historyLoading, setHistoryLoading] = useState(true)
  const chatHistoryRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (chatHistoryRef.current) {
      chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight
    }
  }, [messages, sending])

  async function refreshContext() {
    setLoading(true)
    try {
      const res = await apiGet<DriverContext>('/api/v1/driver/context')
      setCtx(res.data)
      setError(null)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Context failed')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refreshContext()

    async function restoreChatHistoryOnMount() {
      setHistoryLoading(true)
      const saved = getDriverConversationIds(userId)
      try {
        // Prefer server active pointer so re-login restores last Redis thread (24h).
        let restored = (await apiGet<ChatHistoryResponse>('/api/v1/chat/history')).data
        if (!restored.messages?.length && (saved.threadId || saved.sessionId)) {
          const params = new URLSearchParams()
          if (saved.sessionId) params.set('session_id', saved.sessionId)
          if (saved.threadId) params.set('thread_id', saved.threadId)
          restored = (
            await apiGet<ChatHistoryResponse>(`/api/v1/chat/history?${params.toString()}`)
          ).data
        }
        if (restored.session_id) setSessionId(restored.session_id)
        if (restored.thread_id) setThreadId(restored.thread_id)
        if (restored.session_id || restored.thread_id) {
          saveDriverConversationIds(
            userId,
            restored.session_id || saved.sessionId,
            restored.thread_id || null,
          )
        }
        if (restored.messages?.length) {
          setMessages(
            restored.messages
              .filter((m) => m.role === 'user' || m.role === 'assistant')
              .map((m, index) => ({
                id: m.client_message_id || `restored-${index}`,
                role: m.role as 'user' | 'assistant',
                content: m.content,
              })),
          )
          setMemoryNote(
            restored.degraded
              ? `Conversation memory degraded (${restored.degrade_reason || 'unknown'}).`
              : `Restored last ${restored.messages.length} Redis chat turns (24h TTL, non-authoritative).`,
          )
        }
      } catch (err) {
        setMemoryNote(
          err instanceof Error
            ? `Could not restore chat history: ${err.message}`
            : 'Could not restore chat history.',
        )
      } finally {
        setHistoryLoading(false)
      }
    }

    void restoreChatHistoryOnMount()
  }, [userId])

  async function sendChat(text: string) {
    const trimmed = text.trim()
    if (!trimmed || sending) return
    setSending(true)
    setUxState('write_in_progress')
    const clientMessageId = crypto.randomUUID()
    setMessages((prev) => [...prev, { id: clientMessageId, role: 'user', content: trimmed }])
    setDraft('')
    try {
      const res = await apiPost<ChatResponse>('/api/v1/chat', {
        message: trimmed,
        thread_id: threadId,
        session_id: sessionId,
        client_message_id: clientMessageId,
      })
      setThreadId(res.data.thread_id)
      setSessionId(res.data.session_id)
      saveDriverConversationIds(userId, res.data.session_id, res.data.thread_id)
      setUxState(res.data.ux_state || 'answered')
      setPendingConfirm(res.data.confirmation ?? null)
      const tools = res.data.tool_calls || []
      setLastTools(
        tools.map((t) => {
          const code =
            t.result && typeof t.result === 'object' && t.result !== null && 'code' in t.result
              ? String((t.result as { code?: unknown }).code || '')
              : ''
          return code ? `${t.name}:${code}` : t.name
        }),
      )
      // Demo/debug: full tool args + results for the driver console.
      console.groupCollapsed(
        `[SetuHaul] chat tools (${tools.length}) · thread ${res.data.thread_id} · ux ${res.data.ux_state}`,
      )
      console.log('user_message', trimmed)
      console.log('assistant_response', res.data.response)
      for (const tool of tools) {
        console.log(tool.name, {
          args: tool.args,
          result: tool.result ?? null,
          result_preview: tool.result_preview ?? null,
        })
      }
      console.groupEnd()
      if (res.data.memory_degraded) {
        setMemoryNote(
          `Conversation memory degraded (${res.data.memory_degrade_reason || 'unknown'}). REST still works.`,
        )
      } else {
        setMemoryNote(null)
      }
      setMessages((prev) => [
        ...prev,
        {
          id: `${clientMessageId}-asst`,
          role: 'assistant',
          content: res.data.response,
        },
      ])
      if (res.data.ux_state === 'persisted_success') {
        await refreshContext()
      }
    } catch (err) {
      setUxState('error')
      setMessages((prev) => [
        ...prev,
        {
          id: `${clientMessageId}-err`,
          role: 'system',
          content: err instanceof Error ? err.message : 'Chat failed',
        },
      ])
    } finally {
      setSending(false)
    }
  }

  function onComposerSubmit(e: FormEvent) {
    e.preventDefault()
    void sendChat(draft)
  }

  async function confirmEtaWrite() {
    if (!pendingConfirm?.shipment_id || !pendingConfirm.declared_eta_ts) return
    setSending(true)
    setUxState('write_in_progress')
    const key = crypto.randomUUID()
    try {
      const res = await apiPost<EtaWriteResult>(
        `/api/v1/shipments/${pendingConfirm.shipment_id}/eta-updates`,
        {
          declared_eta_ts: pendingConfirm.declared_eta_ts,
          confirmation_eta_ts: pendingConfirm.declared_eta_ts,
          confirmed: true,
          confidence_code: 'HIGH',
          delay_reason_code: 'TRAFFIC',
          note: 'Driver confirmed via chat confirmation UX',
          thread_id: threadId,
          client_message_id: key,
        },
        { idempotencyKey: key },
      )
      if (res.data.status === 'PERSISTED') {
        setUxState('persisted_success')
        setPendingConfirm(null)
        setMessages((prev) => [
          ...prev,
          {
            id: `eta-${key}`,
            role: 'assistant',
            content: `ETA persisted: ${res.data.display_eta || pendingConfirm.display_eta}. Ops can refresh to see the matching exception/ETA.`,
          },
        ])
        await refreshContext()
      } else {
        setUxState('confirmation_required')
        setMessages((prev) => [
          ...prev,
          {
            id: `eta-pending-${key}`,
            role: 'system',
            content: 'Still awaiting confirmation of the exact ETA.',
          },
        ])
      }
    } catch (err) {
      setUxState('retry_safe_unknown')
      setMessages((prev) => [
        ...prev,
        {
          id: `eta-err-${key}`,
          role: 'system',
          content:
            (err instanceof Error ? err.message : 'ETA write failed') +
            ' — if the network dropped after commit, retry with the same Idempotency-Key is safe.',
        },
      ])
    } finally {
      setSending(false)
    }
  }

  const displayName = driverName || ctx?.driver.driver_name || 'Driver'
  const status = ctx?.driver.driver_status ?? 'Context pending'
  const facilityLabel =
    typeof ctx?.facility?.facility_name === 'string'
      ? ctx.facility.facility_name
      : typeof ctx?.facility?.facility_id === 'string'
        ? ctx.facility.facility_id
        : 'Facility context'
  const shipmentId =
    typeof ctx?.primary_shipment?.shipment_id === 'string'
      ? ctx.primary_shipment.shipment_id
      : null

  return (
    <div className="driver-workspace">
      <section className="chat-shell" aria-label="Driver AI assistant">
        <div className="chat-panel-header">
          <div>
            <p className="eyebrow">Driver Console</p>
            <h2>{displayName}</h2>
          </div>
          <div className="header-pills">
            <span className="chip secondary">{status}</span>
            <span className="chip primary">{shipmentId || 'Shipment pending'}</span>
          </div>
        </div>
        <div className="chat-history" ref={chatHistoryRef}>
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
                Hello {displayName}. Ask about your shipment, appointment, facility, or report a
                revised ETA. I only use verified database facts.
              </p>
            </div>
          </div>
          {messages.map((m) => (
            <div key={m.id} className={`chat-row ${m.role === 'user' ? 'user' : 'ai'}`}>
              <div className="chat-meta">
                {m.role !== 'user' ? (
                  <span className="chat-avatar" aria-hidden="true">
                    AI
                  </span>
                ) : null}
                <span>{m.role === 'user' ? 'You' : m.role === 'system' ? 'System' : 'SetuHaul AI'}</span>
              </div>
              <div className={`chat-bubble ${m.role === 'user' ? 'glass-bubble' : 'ai-bubble'}`}>
                {renderFormattedText(m.content)}
              </div>
            </div>
          ))}
          {sending ? (
            <div className="chat-row ai typing-row" aria-live="polite">
              <div className="chat-meta">
                <span className="chat-avatar" aria-hidden="true">
                  AI
                </span>
                <span>SetuHaul AI</span>
              </div>
              <div className="chat-bubble ai-bubble typing-bubble">
                <div className="typing-dots" aria-label="Thinking">
                  <span className="dot dot-1" />
                  <span className="dot dot-2" />
                  <span className="dot dot-3" />
                </div>
                <span className="typing-text">Thinking &amp; verifying database facts…</span>
              </div>
            </div>
          ) : null}
        </div>

        <div className="composer-chips" style={{ padding: '0 16px' }}>
          <span className="chip secondary">{status}</span>
          <span className="chip primary">{facilityLabel}</span>
          {driverId ? <span className="chip primary">{driverId}</span> : null}
          <span className="chip secondary" id={statusId}>
            UX: {uxState}
          </span>
        </div>

        <div className="quick-actions" aria-label="Quick actions">
          <button
            type="button"
            className="chip-btn"
            disabled={sending}
            onClick={() => void sendChat('Show my current shipment and appointment status.')}
          >
            View appointment
          </button>
          <button
            type="button"
            className="chip-btn"
            disabled={sending}
            onClick={() => void sendChat('What are my facility details?')}
          >
            Facility details
          </button>
          <button
            type="button"
            className="chip-btn"
            disabled={sending}
            onClick={() =>
              void sendChat(
                shipmentId
                  ? `I need to update the ETA for ${shipmentId}. I will be late due to traffic.`
                  : 'I need to update my ETA. I will be late.',
              )
            }
          >
            Update ETA
          </button>
        </div>

        {pendingConfirm?.display_eta ? (
          <div className="confirm-banner" role="region" aria-label="ETA confirmation">
            <p>
              Confirm exact ETA: <strong>{pendingConfirm.display_eta}</strong>
            </p>
            <div className="confirm-actions">
              <button type="button" disabled={sending} onClick={() => void confirmEtaWrite()}>
                Confirm &amp; write ETA
              </button>
              <button
                type="button"
                className="secondary-btn"
                disabled={sending}
                onClick={() => {
                  setPendingConfirm(null)
                  setUxState('ready')
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        ) : null}

        <form className="chat-composer" onSubmit={onComposerSubmit}>
          <div className="composer-row">
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ask SetuHaul about routes, cargo, or facility access…"
              aria-label="Message SetuHaul AI"
              disabled={sending}
            />
            <button type="submit" aria-label="Send message" disabled={sending || !draft.trim()}>
              {sending ? '…' : 'Send'}
            </button>
          </div>
          <p className="fine-print" role="status" aria-live="polite">
            {historyLoading
              ? 'Restoring chat history…'
              : memoryNote
                ? memoryNote
                : lastTools.length
                  ? `Last tools: ${lastTools.join(', ')}`
                  : 'Live ChatOpenAI.bind_tools + manual invoke loop. Writes require explicit ETA confirmation.'}
          </p>
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
            <article className="context-card identity-card">
              <div className="card-heading">
                <div>
                  <p className="eyebrow">Active context</p>
                  <h2>{displayName}</h2>
                </div>
                <span className="live-dot" aria-hidden="true" />
              </div>
              <div className="data-grid">
                <DataField label="Driver" value={ctx.driver.driver_id} tone="good" />
                <DataField label="Status" value={ctx.driver.driver_status} />
                <DataField label="Shipment" value={shipmentId} tone="neutral" />
                <DataField label="Facility" value={facilityLabel} />
              </div>
              <button type="button" className="secondary-btn" onClick={() => void refreshContext()}>
                Refresh context
              </button>
            </article>
            <article className="context-card">
              <h2>Primary shipment</h2>
              {ctx.primary_shipment ? (
                <div className="data-grid">
                  <DataField
                    label="Shipment ID"
                    value={getField(ctx.primary_shipment, ['shipment_id'])}
                    tone="good"
                  />
                  <DataField
                    label="Status"
                    value={getField(ctx.primary_shipment, [
                      'current_status',
                      'status',
                      'shipment_status',
                    ])}
                  />
                  <DataField
                    label="Priority"
                    value={getField(ctx.primary_shipment, ['priority_code', 'priority'])}
                    tone="warn"
                  />
                  <DataField
                    label="Product"
                    value={getField(ctx.primary_shipment, [
                      'product_category',
                      'product_class',
                    ])}
                  />
                  <DataField
                    label="Planned ETA"
                    value={formatHumanDateTime(
                      getField(ctx.primary_shipment, ['original_eta_ts', 'planned_eta'])
                    )}
                  />
                  {hasEtaChanged(
                    ctx.primary_shipment.original_eta_ts,
                    ctx.primary_shipment.latest_eta_ts
                  ) ? (
                    <DataField
                      label="Updated ETA"
                      value={formatHumanDateTime(ctx.primary_shipment.latest_eta_ts)}
                      tone="good"
                    />
                  ) : null}
                  <DataField
                    label="Unload minutes"
                    value={getField(ctx.primary_shipment, [
                      'expected_unload_min',
                      'expected_unload_minutes',
                    ])}
                  />
                </div>
              ) : (
                <p className="state">No active shipment</p>
              )}
            </article>
            <article className="context-card">
              <h2>Current appointment</h2>
              {ctx.current_appointment ? (
                <div className="data-grid">
                  <DataField
                    label="Appointment"
                    value={getField(ctx.current_appointment, ['appointment_id'])}
                    tone="good"
                  />
                  <DataField
                    label="Status"
                    value={getField(ctx.current_appointment, ['status', 'appointment_status'])}
                  />
                  <DataField label="Dock" value={getField(ctx.current_appointment, ['dock_id', 'dock_name'])} />
                  <DataField label="Slot" value={getField(ctx.current_appointment, ['slot_id'])} />
                  <DataField
                    label="Start"
                    value={formatHumanDateTime(
                      getField(ctx.current_appointment, [
                        'slot_start_ts',
                        'start_time',
                      ])
                    )}
                  />
                  <DataField
                    label="End"
                    value={formatHumanDateTime(
                      getField(ctx.current_appointment, ['slot_end_ts', 'end_time'])
                    )}
                  />
                </div>
              ) : (
                <p className="state">No current appointment</p>
              )}
            </article>
            <article className="context-card">
              <h2>Facility</h2>
              {ctx.facility ? (
                <div className="data-grid">
                  <DataField
                    label="Facility"
                    value={getField(ctx.facility, ['facility_name', 'name', 'facility_id'])}
                    tone="good"
                  />
                  <DataField label="City" value={getField(ctx.facility, ['city'])} />
                  <DataField label="Timezone" value={getField(ctx.facility, ['timezone'])} />
                  <DataField label="Open" value={getField(ctx.facility, ['open_time'])} />
                  <DataField label="Close" value={getField(ctx.facility, ['close_time'])} />
                </div>
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
