import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import {
  acknowledgeEscalation,
  cancelEscalation,
  fetchEscalationQueue,
  resolveEscalation,
} from './lib/api'
import type { CancelReasonCode, EscalationQueueItem, ResolveReasonCode } from './lib/types'
import { CopilotPane } from './components/copilot-pane'
import { DetailPane } from './components/detail-pane'
import { QueuePane } from './components/queue-pane'

type LoadState = 'loading' | 'error' | 'ready'

/**
 * `screens.md` section 1, U89. The three-pane shell -- queue always visible, detail populated on
 * row selection, co-pilot populated only under takeover.
 *
 * **Real data.** This mounts against `GET /api/v1/operations/escalation-queue` and the six
 * mutation endpoints M3/E3.2 shipped (`lib/api.ts`) -- the same pattern E5.1's driver chat used
 * against `/api/v1/chat/stream`, not a fixture. `gallery/` is the separate, fixture-only
 * verification path for `/ops/_states`.
 *
 * `data-density="compact"` is set by the shell already (`identity.ts`'s `densityFor('ops')`) --
 * not repeated here.
 */
export function OpsConsole() {
  const [state, setState] = useState<LoadState>('loading')
  const [items, setItems] = useState<EscalationQueueItem[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [alreadyActioned, setAlreadyActioned] = useState<{
    id: string
    winningOwnerName: string | null
  } | null>(null)

  const queueRef = useRef<HTMLDivElement | null>(null)
  const detailRef = useRef<HTMLDivElement | null>(null)
  const copilotRef = useRef<HTMLDivElement | null>(null)

  const load = useCallback(async () => {
    setState('loading')
    try {
      const res = await fetchEscalationQueue({ owner: 'all' })
      setItems(res.items)
      setState('ready')
    } catch {
      setState('error')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  // Cmd/Ctrl+1/2/3 -- accessibility.md's "Three-pane keyboard model". Jump focus directly to
  // queue / detail / co-pilot. Registered at the console root, same pattern as AppShell's
  // Cmd/Ctrl+K palette binding.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!(e.metaKey || e.ctrlKey)) return
      if (e.key === '1') {
        e.preventDefault()
        queueRef.current?.focus()
      } else if (e.key === '2') {
        e.preventDefault()
        detailRef.current?.focus()
      } else if (e.key === '3') {
        e.preventDefault()
        copilotRef.current?.focus()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const selected = items.find((i) => i.escalation_id === selectedId) ?? null

  function handleSelect(item: EscalationQueueItem) {
    setSelectedId(item.escalation_id)
    setAlreadyActioned(null)
    // accessibility.md's "Focus management": selecting a row focuses the detail pane's own
    // primary heading, not the pane's outer wrapper (see detail-pane.tsx's `#ops-detail-heading`).
    requestAnimationFrame(() => document.getElementById('ops-detail-heading')?.focus())
  }

  async function handleAcknowledge() {
    if (!selected) return
    setBusy(true)
    try {
      const res = await acknowledgeEscalation(selected.escalation_id)
      if (res.code === 'ALREADY_ACTIONED') {
        // edge-cases.md section 2 -- the nastiest race. Row updates in place, never removed and
        // re-inserted. `assertive` only when this exact row is focused; it is, since the
        // coordinator just tried to act on it.
        setAlreadyActioned({ id: selected.escalation_id, winningOwnerName: null })
      } else {
        toast.success(`Acknowledged ${selected.escalation_id}.`)
        await load()
      }
    } catch {
      // components.md foundations section 13: "That didn't save. Nothing has changed."
      toast.error("That didn't save. Nothing has changed.")
    } finally {
      setBusy(false)
    }
  }

  async function handleResolve(reasonCode: ResolveReasonCode) {
    if (!selected) return
    setBusy(true)
    try {
      await resolveEscalation(selected.escalation_id, reasonCode)
      toast.success(`Resolved ${selected.escalation_id}.`)
      await load()
    } catch {
      toast.error("That didn't save. Nothing has changed.")
    } finally {
      setBusy(false)
    }
  }

  async function handleCancel(reasonCode: CancelReasonCode) {
    if (!selected) return
    setBusy(true)
    try {
      await cancelEscalation(selected.escalation_id, reasonCode)
      toast.success(`Cancelled ${selected.escalation_id}.`)
      await load()
    } catch {
      toast.error("That didn't save. Nothing has changed.")
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid h-full min-h-0 grid-cols-[340px_1fr_320px] gap-0">
      <div ref={queueRef} tabIndex={-1} className="min-h-0 outline-none">
        <QueuePane
          state={state}
          items={items}
          selectedId={selectedId}
          onSelect={handleSelect}
          onRetry={load}
        />
      </div>

      <div
        ref={detailRef}
        tabIndex={-1}
        role="region"
        aria-label="Escalation detail"
        className="min-h-0 overflow-auto border-r border-border outline-none"
      >
        <DetailPane
          item={selected}
          onAcknowledge={handleAcknowledge}
          onResolve={handleResolve}
          onCancel={handleCancel}
          busy={busy}
          alreadyActioned={
            alreadyActioned && selected?.escalation_id === alreadyActioned.id
              ? { winningOwnerName: alreadyActioned.winningOwnerName }
              : null
          }
        />
      </div>

      <div ref={copilotRef} tabIndex={-1} role="region" aria-label="Co-pilot" className="min-h-0 outline-none">
        <CopilotPane takeoverActive={false} />
      </div>
    </div>
  )
}
