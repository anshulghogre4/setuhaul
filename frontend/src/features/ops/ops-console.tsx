import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { formatUserFriendlyError } from '@/core/http/api'
import { useLivePoll } from '@/shared/lib/live-poll'
import {
  acknowledgeEscalation,
  cancelEscalation,
  fetchEscalationQueue,
  fetchMe,
  fetchThreadMessages,
  handBackThread,
  postOperationsMessage,
  resolveEscalation,
  startEscalationWork,
  takeOverThread,
} from './lib/api'
import type {
  CancelReasonCode,
  EscalationQueueItem,
  EscalationQueueResponse,
  ResolveReasonCode,
  ThreadMessage,
} from './lib/types'
import { opsLiveUpdatesEnabled } from './lib/flags'
import {
  adoptOpsQueue,
  applyOpsResort,
  changeKey,
  describeDisappearance,
  describeEscalationChange,
  emptyOpsLiveState,
  mergeOpsQueue,
  type EscalationChange,
  type OpsLiveState,
} from './lib/live-queue'
import { CopilotPane } from './components/copilot-pane'
import { DetailPane } from './components/detail-pane'
import { QueuePane } from './components/queue-pane'
import type { PendingMessage } from './components/thread-transcript'
import type { TakeoverNotice } from './components/takeover-control'

type LoadState = 'loading' | 'error' | 'ready'

/**
 * `screens.md` section 1, U89. The three-pane shell -- queue always visible, detail populated on
 * row selection, co-pilot populated only under takeover.
 *
 * **Real data.** This mounts against `GET /api/v1/operations/escalation-queue` and the ops
 * mutation endpoints (`lib/api.ts`) -- not a fixture. `gallery/` is the separate, fixture-only
 * verification path for `/ops/_states`.
 *
 * `data-density="compact"` is set by the shell already (`identity.ts`'s `densityFor('ops')`) --
 * not repeated here.
 *
 * ## Idempotency-key lifetime lives here, deliberately
 *
 * `implementation-spec.md` section 3D: the key must be "reused verbatim on retry". A key generated
 * inside the API function is a *new* key on every retry, which defeats the header entirely -- so
 * `keyFor`/`clearKey` below own it: one key per attempt, reused across retries of that attempt,
 * dropped on success so the next deliberate action gets a fresh one. That last part matters as
 * much as the first: `take_over_thread` stores its response against the key, so a permanently
 * stable key would make a second, genuine takeover after a hand-back replay the first response and
 * silently never touch the thread.
 */
export function OpsConsole() {
  const [state, setState] = useState<LoadState>('loading')
  const [live, setLive] = useState<OpsLiveState>(emptyOpsLiveState)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  /** True while the queue pane holds DOM focus. U19's freeze applies to focus, not selection --
   *  see `lib/live-queue.ts`'s header for why a selected-but-unfocused row must not pin the sort
   *  for the minutes a coordinator spends reading it. */
  const [queueFocusWithin, setQueueFocusWithin] = useState(false)
  /** `edge-cases.md` sections 2 and 9 -- what a poll observed changing on the selected escalation
   *  since the coordinator opened it. Cleared on selection change and on the coordinator's own
   *  successful write, never on a timer: a fact that scrolls away unread is not surfaced. */
  const [liveChange, setLiveChange] = useState<EscalationChange | null>(null)
  /** The last change the coordinator explicitly dismissed. A disappearance stays true on every
   *  later poll, so without this a dismissed notice would reappear on the next tick, forever. */
  const dismissedChangeRef = useRef<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [currentUserId, setCurrentUserId] = useState<string | null>(null)
  const [alreadyActioned, setAlreadyActioned] = useState<{
    id: string
    winningOwnerName: string | null
  } | null>(null)

  // --- thread state, keyed to the selected escalation's thread ---
  const [threadState, setThreadState] = useState<'loading' | 'error' | 'ready' | 'none'>('none')
  const [messages, setMessages] = useState<ThreadMessage[]>([])
  const [pending, setPending] = useState<PendingMessage[]>([])
  /** `chat_message_id` -> `delivery_reason`, for messages this session posted that did not reach
   *  the driver's live feed. Session-scoped on purpose: the API has no per-message delivery
   *  column to read this back from on reload, and inventing one would be worse than saying so. */
  const [undelivered, setUndelivered] = useState<Record<string, string | null>>({})
  const [takeoverNotice, setTakeoverNotice] = useState<TakeoverNotice | null>(null)

  const queueRef = useRef<HTMLDivElement | null>(null)
  const detailRef = useRef<HTMLDivElement | null>(null)
  const copilotRef = useRef<HTMLDivElement | null>(null)
  const composerRef = useRef<HTMLTextAreaElement | null>(null)
  const stepperRef = useRef<HTMLDivElement | null>(null)

  /** Issue #91. Owned here rather than in `DetailPane`, because this component is the one that
   *  looks the heading up to move focus after a row selection -- see `handleSelect`. */
  const detailHeadingId = useId()

  const idempotencyKeys = useRef<Map<string, string>>(new Map())
  const keyFor = useCallback((action: string) => {
    const existing = idempotencyKeys.current.get(action)
    if (existing) return existing
    const fresh = crypto.randomUUID()
    idempotencyKeys.current.set(action, fresh)
    return fresh
  }, [])
  const clearKey = useCallback((action: string) => {
    idempotencyKeys.current.delete(action)
  }, [])

  /**
   * The authoritative read: mount, Retry, and after every one of this coordinator's own writes.
   * Adopts server order outright -- each of those is a moment the coordinator asked for the list to
   * be current, so nothing is staged behind a pill.
   */
  const load = useCallback(async () => {
    setState('loading')
    try {
      const res = await fetchEscalationQueue({ owner: 'all' })
      setLive(adoptOpsQueue(res))
      setLiveChange(null)
      setState('ready')
    } catch {
      setState('error')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const items = live.items

  // The signed-in coordinator. Needed for the queue's "Owner: mine" filter (previously
  // approximated as "owned by anyone", which is a different question) and to tell "You" apart
  // from another coordinator in the transcript. A failure here is not fatal: both features
  // degrade to their pre-identity behaviour rather than blocking the console.
  useEffect(() => {
    let cancelled = false
    void fetchMe()
      .then((me) => {
        if (!cancelled) setCurrentUserId(me.user_id)
      })
      .catch(() => {
        /* non-fatal, see above */
      })
    return () => {
      cancelled = true
    }
  }, [])

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
  const selectedThreadId = selected?.thread_id ?? null

  /* ------------------------------------------------------------------------------------------
   * Live updates (issue #59). Polling, per the owner's decision -- see `lib/flags.ts`.
   * ---------------------------------------------------------------------------------------- */

  // Read at RESPONSE time rather than request time, so a coordinator who starts a takeover during
  // the round trip still gets the paused/frozen treatment the tick was not aware of when it left.
  const pollContextRef = useRef({ frozen: false, selectedId, currentUserId, selected })
  pollContextRef.current = {
    frozen: queueFocusWithin || busy,
    selectedId,
    currentUserId,
    selected,
  }

  // The LATEST payload, not the applied one: the status bar reports ambient server truth while the
  // visible order may be pinned, and that field is `silent` in `accessibility-behaviour.md`'s
  // matrix, so a moving number interrupts nobody.
  const pendingCount = useMemo(
    () => (live.latest ? live.latest.items.length : null),
    [live.latest],
  )

  useLivePoll<EscalationQueueResponse>({
    enabled: opsLiveUpdatesEnabled,
    // Constraint 3 of #59: a refresh landing under a coordinator mid-takeover must not discard
    // their state. `busy` covers every mutation this console can have in flight; the tick is
    // skipped and re-armed rather than counted as a failure.
    paused: busy,
    pendingCount,
    fetcher: () => fetchEscalationQueue({ owner: 'all' }),
    onData: (res) => {
      const ctx = pollContextRef.current
      setLive((prev) => mergeOpsQueue(prev, res, { frozen: ctx.frozen, keepId: ctx.selectedId }))

      // edge-cases.md sections 2 and 9. Computed against the item the coordinator currently has
      // open, because that is the only row for which "acted on underneath them" is meaningful.
      if (ctx.selectedId === null || ctx.selected === null) return
      const after = res.items.find((i) => i.escalation_id === ctx.selectedId)
      const change = after
        ? describeEscalationChange(ctx.selected, after, ctx.currentUserId)
        : describeDisappearance(ctx.selected)
      if (!change) return
      const key = changeKey(change)
      if (dismissedChangeRef.current === key) return
      // Keep the existing object when the fact has not changed: a new object every 15 seconds would
      // re-render the notice, and a live region that re-renders is a live region that can
      // re-announce.
      setLiveChange((prev) => (prev !== null && changeKey(prev) === key ? prev : change))
    },
    // A poll failure does not blank the console. The rows on screen are still the last thing the
    // server actually said; "we could not reach the server" belongs in the status bar's connection
    // row (`auth-and-scoping.md`'s degradation policy), not in place of a coordinator's queue.
    onError: () => {},
  })

  /** Named in section 2's own words: "the loser's UI receives ALREADY_ACTIONED with the winning
   *  owner named". Read off the merged row rather than reconstructed, so it is whatever the server
   *  actually says. */
  const raceOwnerName = selected?.owner_name ?? null

  /** The "press S" half of prompt 3's affordance. Applies the held order, and keeps the selected
   *  escalation on screen even if the server has stopped returning it. */
  const applyArrivals = useCallback(() => {
    setLive((prev) => applyOpsResort(prev, selectedId))
  }, [selectedId])

  const loadThread = useCallback(async (threadId: string | null) => {
    if (!threadId) {
      setThreadState('none')
      setMessages([])
      return
    }
    setThreadState('loading')
    try {
      const res = await fetchThreadMessages(threadId)
      setMessages(res.messages)
      setThreadState('ready')
    } catch {
      setThreadState('error')
    }
  }, [])

  // Reload the transcript whenever the selected escalation's thread changes. Pending sends and
  // the undelivered map are cleared with it -- both are about one thread, and carrying them
  // across would attribute one thread's failed message to another.
  useEffect(() => {
    setPending([])
    setUndelivered({})
    setTakeoverNotice(null)
    void loadThread(selectedThreadId)
  }, [selectedThreadId, loadThread])

  // A change notice belongs to ONE escalation. Carrying it across a selection change would report
  // one row's race against another row's detail.
  useEffect(() => {
    setLiveChange(null)
    dismissedChangeRef.current = null
  }, [selectedId])

  function handleSelect(item: EscalationQueueItem) {
    setSelectedId(item.escalation_id)
    setAlreadyActioned(null)
    // accessibility.md's "Focus management": selecting a row focuses the detail pane's own
    // primary heading, not the pane's outer wrapper.
    //
    // Issue #91: the id used to be the hardcoded string "ops-detail-heading", which the states
    // gallery duplicated nine times. The console now MINTS the id (`useId`, below) and hands it
    // to its one DetailPane, so this lookup is unambiguous by construction rather than by
    // nobody having rendered a second console yet. React 19.2.8's `_r_<n>_` ids are valid CSS
    // selectors, so `getElementById` (and `querySelector`) are both safe with them.
    requestAnimationFrame(() => document.getElementById(detailHeadingId)?.focus())
  }

  async function handleAcknowledge() {
    if (!selected) return
    const action = `ack:${selected.escalation_id}`
    setBusy(true)
    try {
      const res = await acknowledgeEscalation(selected.escalation_id, keyFor(action))
      clearKey(action)
      if (res.code === 'ALREADY_ACTIONED') {
        // edge-cases.md section 2 -- the nastiest race. Row updates in place, never removed and
        // re-inserted. `assertive` only when this exact row is focused; it is, since the
        // coordinator just tried to act on it.
        setAlreadyActioned({ id: selected.escalation_id, winningOwnerName: null })
      } else {
        toast.success(`Acknowledged ${selected.escalation_id}.`)
      }
      await load()
    } catch {
      // components.md foundations section 13: "That didn't save. Nothing has changed."
      // The key is deliberately NOT cleared here, so a retry reuses it.
      toast.error("That didn't save. Nothing has changed.")
    } finally {
      setBusy(false)
    }
  }

  async function handleResolve(reasonCode: ResolveReasonCode) {
    if (!selected) return
    const action = `resolve:${selected.escalation_id}`
    setBusy(true)
    try {
      await resolveEscalation(selected.escalation_id, reasonCode, keyFor(action))
      clearKey(action)
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
    const action = `cancel:${selected.escalation_id}`
    setBusy(true)
    try {
      await cancelEscalation(selected.escalation_id, reasonCode, keyFor(action))
      clearKey(action)
      toast.success(`Cancelled ${selected.escalation_id}.`)
      await load()
    } catch {
      toast.error("That didn't save. Nothing has changed.")
    } finally {
      setBusy(false)
    }
  }

  /**
   * Flow 2 step 1-4. The backend refuses `NOT_ACKNOWLEDGED` on an unowned or unacknowledged
   * escalation and advances `ACKNOWLEDGED -> IN_PROGRESS` in the same transaction, so a success
   * here moves the stepper too -- hence the queue reload.
   */
  async function handleTakeOver() {
    if (!selected?.thread_id) return
    const threadId = selected.thread_id
    const action = `takeover:${selected.escalation_id}:${threadId}`
    setBusy(true)
    setTakeoverNotice(null)
    try {
      const res = await takeOverThread(threadId, selected.escalation_id, keyFor(action))

      if (res.code === 'NOT_ACKNOWLEDGED') {
        // A refusal is a completed request, not a failed one -- the key has been consumed against
        // this request hash, so drop it rather than replaying the refusal on the next press.
        clearKey(action)
        setTakeoverNotice({ kind: 'not-acknowledged' })
        await load()
        return
      }

      clearKey(action)

      if (res.code === 'ALREADY_TAKEN_OVER') {
        setTakeoverNotice({ kind: 'already-taken-over' })
      } else if (res.delivered === false) {
        // #58's residual, surfaced rather than swallowed: the divider row is durable but the
        // driver's live feed never got it, and nothing back-fills. A silent takeover reads to a
        // driver as the assistant ignoring them (SS7.4), so the coordinator has to be told.
        setTakeoverNotice({
          kind: 'divider-undelivered',
          reason: res.delivery_reason ?? null,
          event: 'joined',
        })
      } else {
        // accessibility.md's announcement table: takeover announces assertively, because a
        // coordinator who does not register they have taken over may not realise the composer
        // just became live.
        toast.success('You joined the thread. The assistant is no longer answering it.')
      }

      await load()
      await loadThread(threadId)
      // accessibility.md's focus table: "Taking over a thread -> the composer, since that's the
      // newly-available interactive surface the coordinator almost certainly wants next."
      requestAnimationFrame(() => composerRef.current?.focus())
    } catch (err) {
      setTakeoverNotice({ kind: 'failed', message: formatUserFriendlyError(err) })
    } finally {
      setBusy(false)
    }
  }

  /**
   * Flow 2 step 5. `hand_back_thread` now requires `IN_PROGRESS` (tightened once issue #56 made
   * the value writable), so this has a refusal path that is genuinely recoverable -- see
   * `handleRecoverHandBack`.
   */
  async function handleHandBack() {
    if (!selected?.thread_id) return
    const threadId = selected.thread_id
    setBusy(true)
    setTakeoverNotice(null)
    try {
      const res = await handBackThread(threadId)

      if (res.code === 'NOT_IN_PROGRESS') {
        // The two causes are distinguishable from `thread_status` alone: still ESCALATED means
        // the thread is taken over but no IN_PROGRESS escalation backs it (the pre-#56 live-data
        // case, recoverable); anything else means it was already handed back.
        setTakeoverNotice(
          res.thread_status === 'ESCALATED'
            ? { kind: 'handback-needs-start' }
            : { kind: 'handback-noop' },
        )
      } else if (res.delivered === false) {
        setTakeoverNotice({
          kind: 'divider-undelivered',
          reason: res.delivery_reason ?? null,
          event: 'handed-back',
        })
      } else {
        toast.success('Handed back. The assistant is answering this thread again.')
      }

      await load()
      await loadThread(threadId)
      // accessibility.md's focus table: hand-back sends focus to the stepper/status area, NOT the
      // composer, since the composer just became non-interactive again.
      requestAnimationFrame(() => stepperRef.current?.focus())
    } catch (err) {
      setTakeoverNotice({ kind: 'failed', message: formatUserFriendlyError(err) })
    } finally {
      setBusy(false)
    }
  }

  /**
   * The recovery path for `handback-needs-start`: mark the escalation `IN_PROGRESS`, then retry
   * the hand-back. Two calls, one press, and every refusal in between is reported rather than
   * retried blindly -- `start_escalation_work` can itself refuse with `NOT_OWNER`, and looping
   * past that would leave a coordinator pressing a button that can never work.
   */
  async function handleRecoverHandBack() {
    if (!selected?.thread_id) return
    const threadId = selected.thread_id
    const action = `start:${selected.escalation_id}`
    setBusy(true)
    try {
      const started = await startEscalationWork(selected.escalation_id, keyFor(action))
      clearKey(action)

      if (started.code === 'NOT_OWNER') {
        setTakeoverNotice({ kind: 'not-owner', ownerName: selected.owner_name })
        await load()
        return
      }
      if (started.code === 'NOT_ACKNOWLEDGED') {
        setTakeoverNotice({ kind: 'not-acknowledged' })
        await load()
        return
      }

      const res = await handBackThread(threadId)
      if (res.code === 'NOT_IN_PROGRESS') {
        setTakeoverNotice(
          res.thread_status === 'ESCALATED'
            ? { kind: 'handback-needs-start' }
            : { kind: 'handback-noop' },
        )
      } else if (res.delivered === false) {
        setTakeoverNotice({
          kind: 'divider-undelivered',
          reason: res.delivery_reason ?? null,
          event: 'handed-back',
        })
      } else {
        setTakeoverNotice(null)
        toast.success('Handed back. The assistant is answering this thread again.')
      }

      await load()
      await loadThread(threadId)
      requestAnimationFrame(() => stepperRef.current?.focus())
    } catch (err) {
      setTakeoverNotice({ kind: 'failed', message: formatUserFriendlyError(err) })
    } finally {
      setBusy(false)
    }
  }

  /**
   * Post as `OPERATIONS`. The one thing the composer exists to do (issue #55).
   *
   * `key` is both the `Idempotency-Key` and the `client_message_id`, generated once per message
   * and held on the pending record so a retry re-sends the *same* key -- the backend then returns
   * the original row instead of posting a second copy of a sentence nobody can unsend.
   */
  const sendWithKey = useCallback(
    async (key: string, text: string) => {
      if (!selectedThreadId) return
      const threadId = selectedThreadId
      setBusy(true)
      setPending((prev) =>
        prev.some((p) => p.key === key)
          ? prev.map((p) => (p.key === key ? { ...p, state: 'sending' } : p))
          : [...prev, { key, text, state: 'sending' }],
      )
      try {
        const res = await postOperationsMessage(threadId, text, key)

        if (res.code === 'NOT_TAKEN_OVER') {
          // Nothing was written. This is a refusal, not an undelivered message, so it must NOT
          // reuse the undelivered-divider copy -- that would tell a coordinator their message is
          // saved but unseen, when no message exists at all. Keep the text in the pending list as
          // failed so it is not lost, and name the actual cause.
          setPending((prev) => prev.map((p) => (p.key === key ? { ...p, state: 'failed' } : p)))
          setTakeoverNotice({ kind: 'post-refused' })
          await load()
          return
        }

        setPending((prev) => prev.filter((p) => p.key !== key))

        const postedId = res.chat_message_id

        if (res.idempotent_replay) {
          // A replay is NOT an undelivered message, and conflating the two would be dishonest in
          // the opposite direction to the bug this build exists to fix.
          // `post_operations_message` stores its idempotency record *before* the projection runs
          // and comments that `false` is "the honest value for it" there -- because a replay
          // delivers nothing new. So `delivered: false` on a replay means "this retry sent
          // nothing", not "the driver never saw it": the original attempt's real delivery
          // outcome was reported at the time and is not stored anywhere to read back.
          // Telling the coordinator their message never arrived, on the strength of that, could
          // send them chasing a driver who already has it.
          toast.success('Already posted — your retry did not send a second copy.')
        } else if (res.delivered === false && postedId) {
          // The write landed and is permanent; the driver's live feed did not get it and never
          // will. Recorded against the message id so the marker stays attached to that message in
          // the transcript, not to a toast that disappears in five seconds.
          setUndelivered((prev) => ({ ...prev, [postedId]: res.delivery_reason }))
        }

        await loadThread(threadId)
      } catch (err) {
        setPending((prev) => prev.map((p) => (p.key === key ? { ...p, state: 'failed' } : p)))
        toast.error(formatUserFriendlyError(err))
      } finally {
        setBusy(false)
      }
    },
    [selectedThreadId, load, loadThread],
  )

  function handleSendMessage(text: string) {
    void sendWithKey(crypto.randomUUID(), text)
  }

  function handleRetryPending(key: string) {
    const entry = pending.find((p) => p.key === key)
    if (entry) void sendWithKey(entry.key, entry.text)
  }

  function handleDiscardPending(key: string) {
    setPending((prev) => prev.filter((p) => p.key !== key))
  }

  return (
    <div className="grid h-full min-h-0 grid-cols-[340px_1fr_320px] gap-0">
      <div
        ref={queueRef}
        tabIndex={-1}
        className="min-h-0 outline-none"
        // U19's freeze tracks DOM focus, not selection. `relatedTarget` is where focus is going, so
        // arrowing between two rows never registers as leaving the pane -- without that check the
        // sort would unfreeze for one render on every `j`/`k`.
        onFocus={() => setQueueFocusWithin(true)}
        onBlur={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setQueueFocusWithin(false)
        }}
      >
        <QueuePane
          state={state}
          items={items}
          selectedId={selectedId}
          currentUserId={currentUserId}
          onSelect={handleSelect}
          onRetry={load}
          newCount={live.staged.length}
          onApplyArrivals={applyArrivals}
          sortPinned={queueFocusWithin}
          goneIds={live.gone}
          raceOn={
            liveChange?.race
              ? { escalationId: liveChange.escalationId, ownerName: raceOwnerName }
              : null
          }
          // `accessibility-behaviour.md`: assertive ONLY for the row this coordinator is focused
          // on. The queue pane holding focus is what makes "focused on that exact row" true here;
          // a race on a row they are merely reading in the detail pane is reported inline there
          // instead, which is the section 9 treatment.
          announceRace={queueFocusWithin}
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
          headingId={detailHeadingId}
          item={selected}
          liveChange={liveChange}
          onDismissLiveChange={() => {
            if (liveChange) dismissedChangeRef.current = changeKey(liveChange)
            setLiveChange(null)
          }}
          onAcknowledge={handleAcknowledge}
          onResolve={handleResolve}
          onCancel={handleCancel}
          busy={busy}
          alreadyActioned={
            alreadyActioned && selected?.escalation_id === alreadyActioned.id
              ? { winningOwnerName: alreadyActioned.winningOwnerName }
              : null
          }
          threadState={threadState}
          messages={messages}
          pending={pending}
          undelivered={undelivered}
          currentUserId={currentUserId}
          takeoverNotice={takeoverNotice}
          onReloadThread={() => void loadThread(selectedThreadId)}
          onSendMessage={handleSendMessage}
          onRetryPending={handleRetryPending}
          onDiscardPending={handleDiscardPending}
          onTakeOver={handleTakeOver}
          onHandBack={handleHandBack}
          onRecoverHandBack={handleRecoverHandBack}
          onDismissTakeoverNotice={() => setTakeoverNotice(null)}
          composerRef={composerRef}
          stepperRef={stepperRef}
        />
      </div>

      <div ref={copilotRef} tabIndex={-1} role="region" aria-label="Co-pilot" className="min-h-0 outline-none">
        {/* Issue #57. The co-pilot is now scoped to one thing -- suggesting a resolution action
            with its reasoning -- and it needs the *escalation*, not the takeover state, because
            `take_over_thread` is itself one of the actions it can recommend (Flow 1 step 4).
            `escalation_status` is passed as a cache key so acknowledging or taking over
            re-derives the suggestion instead of leaving a card recommending the step just taken.
            The pane owns its own fetch on purpose: a co-pilot failure must not touch this
            console's load path (`edge-cases.md` #5, U84). */}
        <CopilotPane
          escalationId={selected?.escalation_id ?? null}
          escalationStatus={selected?.escalation_status ?? null}
        />
      </div>
    </div>
  )
}
