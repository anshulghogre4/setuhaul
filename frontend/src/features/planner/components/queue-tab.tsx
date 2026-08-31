import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { toast } from 'sonner'

import { RegionError } from '@/components/states/region-states'
import { useCountdownClock } from '@/shared/lib/countdown'
import { RESORT_KEY, RESORT_KEY_LABEL, useLivePoll } from '@/shared/lib/live-poll'
import { Alert } from '@/shared/ui/alert'
import { Button } from '@/shared/ui/button'
import {
  MAX_BULK_CONFIRM_IDS,
  bulkConfirm,
  confirmRequest,
  counterOffer,
  fetchPlannerQueue,
  rejectRequest,
} from '../lib/api'
import { batchHashAvailable, batchSnapshotHash } from '../lib/batch-hash'
import {
  plannerBulkConfirmEnabled,
  plannerConfirmEnabled,
  plannerCounterOfferEnabled,
  plannerLiveArrivalsEnabled,
} from '../lib/flags'
import {
  adoptQueue,
  applyResort,
  emptyLiveQueueState,
  focusTargetAfterResort,
  mergeQueue,
  removeRowFromState,
  removeRowsFromState,
  type LiveQueueState,
} from '../lib/live-queue'
import { classifyRefusal, withNothingChanged, type PlannerRefusal } from '../lib/refusals'
import type { RejectReasonCode } from '../lib/reasons'
import type {
  BulkConfirmOutcome,
  FeasibleSlotOption,
  PlannerQueue,
  PlannerQueueRow,
} from '../lib/types'
import { CounterOfferDialog } from './counter-offer-dialog'
import { QueueEmptyCaughtUp, QueueSearchEmpty, QueueSkeleton } from './queue-region-states'
import { QueueRow } from './queue-row'
import { RejectDialog } from './reject-dialog'

/**
 * The Queue tab -- section 7.3's throughput surface, wired to `GET /api/v1/planner/queue` and the
 * four write tools that start from one of its rows.
 *
 * ## Live arrivals (issue #59) -- a poll, held behind U19's frozen sort
 *
 * This file used to carry a paragraph headed "why there is no background poll", whose argument was
 * that a silent interval re-fetch would reorder rows under the cursor. **That argument was against
 * a naive poll, and it still stands** -- composite urgency is a function of the TTL, so the correct
 * order genuinely drifts every second. What changed is that the poll is no longer naive: the
 * transport (owner decision, #59) is polling, and every response goes through
 * `lib/live-queue.ts::mergeQueue`, which will not move a row while a planner is mid-decision.
 *
 * Concretely, and this is the whole of U19 / `FR-X-012` on this screen:
 *
 *  - **Nothing focused, nothing selected, no dialog, no write in flight** -> server order is
 *    adopted directly and genuinely-new rows flash once (`motion.md`).
 *  - **Otherwise the order is PINNED.** Arrivals accumulate behind the "N new . press S" pill;
 *    existing rows still refresh their own *fields* in place (including `snapshot_hash`, which
 *    must stay current or every confirm would refuse `SNAPSHOT_STALE`); a row the server has
 *    dropped is marked in place rather than removed, because removing it would move every row
 *    below it -- the same failure as re-sorting.
 *  - **A poll never lands on top of a write.** `paused` is passed while any confirm / reject /
 *    counter-offer / bulk-confirm is in flight, so the tick is skipped and re-armed rather than
 *    racing the write's own re-read.
 *
 * A poll failure does **not** replace the queue with an error region -- the rendered rows are still
 * the last thing the server actually said, and the honest place for "we could not reach the server"
 * is the status bar's connection row (`auth-and-scoping.md`'s degradation policy, and
 * `accessibility-behaviour.md`'s `polite` status-bar row). Only the *first* load can fail into
 * `RegionError`, because there is nothing to keep on screen in that case.
 *
 * ## The R-key collision -- decided here, flagged for the owner
 *
 * `accessibility.md`'s keyboard table binds `R` to **Reject** on the focused row. `stitch-prompts.md`
 * section 4 and State 9's pin line both write the affordance as "3 new . press R to re-sort". Both
 * are this surface's own design; they collide on the same tab, and making re-sort real is what
 * makes the collision live rather than theoretical.
 *
 * **This build keeps `R` = Reject and binds re-sort to `S`** (`RESORT_KEY`), for two reasons: the
 * AT matrix is the surface's own authority on keys and was written as a table of bindings rather
 * than as prose in a prompt; and losing Reject's single-key shortcut costs a planner one of five
 * per-row affordances in a 30-second decision, where losing R for re-sort costs a mnemonic on an
 * action that also has a real, clickable button. `S` is free on this surface (`C`/`R`/`O`/`H`/`E`,
 * `j`/`k`, `Cmd/Ctrl+1`/`+2`) and reads as "sort".
 *
 * **Owner call needed**, because the copy in two design files now disagrees with the product: either
 * (a) adopt `S` and correct "press R to re-sort" in `stitch-prompts.md` section 4 / State 9 and in
 * `02-ops-exception-console/stitch-prompts.md` prompt 3, or (b) move Reject to another key and give
 * `R` back to re-sort. Recommendation is (a).
 */

type PendingAction = { kind: 'confirm' | 'reject' | 'counter-offer'; appointmentId: string }

export function QueueTab({ facilityId }: { facilityId: string | null }) {
  const [live, setLive] = useState<LiveQueueState>(emptyLiveQueueState)
  const [loadFailed, setLoadFailed] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)
  const [search, setSearch] = useState('')
  /** True while any element inside the table has DOM focus. Tracked from `focusin`/`focusout`
   *  (React's bubbling `onFocus`/`onBlur`) rather than from `focusedId`, which is the roving-
   *  tabindex anchor and survives blur -- a planner who clicked one row once would otherwise
   *  freeze the sort for the rest of their shift. */
  const [rowFocusWithin, setRowFocusWithin] = useState(false)

  const [focusedId, setFocusedId] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const [refusals, setRefusals] = useState<Record<string, PlannerRefusal>>({})
  const [outcomes, setOutcomes] = useState<Record<string, BulkConfirmOutcome>>({})
  const [pending, setPending] = useState<PendingAction | null>(null)
  const [batchBusy, setBatchBusy] = useState(false)
  const [batchNotice, setBatchNotice] = useState<string | null>(null)

  const [rejectFor, setRejectFor] = useState<PlannerQueueRow | null>(null)
  const [rejectError, setRejectError] = useState<string | null>(null)
  const [counterFor, setCounterFor] = useState<PlannerQueueRow | null>(null)
  const [counterError, setCounterError] = useState<string | null>(null)
  const [counterRefresh, setCounterRefresh] = useState(0)

  const { setServerTime } = useCountdownClock()
  const tableRef = useRef<HTMLTableElement | null>(null)
  const regionRef = useRef<HTMLDivElement | null>(null)

  const rows = live.rows
  const queue = live.applied

  /**
   * One idempotency key per *press*, reused across a retry of that same press and discarded once
   * the press resolves. U70 and the four routes' own 400 `IDEMPOTENCY_KEY_REQUIRED`: the header
   * exists so a retry after a client-side timeout cannot double-write, which only works if a
   * retry sends the *same* key. Generating a fresh one inside the request helper would have
   * defeated the entire mechanism while looking correct.
   */
  const keys = useRef<Map<string, string>>(new Map())
  const keyFor = useCallback((slot: string) => {
    const existing = keys.current.get(slot)
    if (existing) return existing
    const next = crypto.randomUUID()
    keys.current.set(slot, next)
    return next
  }, [])

  useEffect(() => {
    let ignore = false
    setLoadFailed(false)
    fetchPlannerQueue(facilityId)
      .then((data) => {
        if (ignore) return
        // An explicit load (mount, facility change, Refresh) adopts server order outright. It is
        // the one moment the planner has asked for the list to move, so nothing is staged.
        setLive(adoptQueue(data))
        // The countdown clock reconciles against SERVER time using this offset. Without it every
        // TTL on screen is only as trustworthy as the planner's own laptop clock, and a clock
        // three minutes fast would show live requests as already expired.
        setServerTime(data.as_of)
      })
      .catch(() => {
        if (ignore) return
        setLoadFailed(true)
      })
    return () => {
      ignore = true
    }
  }, [facilityId, reloadToken, setServerTime])

  const reload = useCallback(() => {
    setRefusals({})
    setOutcomes({})
    setBatchNotice(null)
    setSelected(new Set())
    setReloadToken((n) => n + 1)
  }, [])

  /**
   * "Is a planner mid-decision right now." U19 says the sort freezes while a row has focus; this is
   * deliberately broader, because every state below is a decision in progress and re-ordering under
   * any of them produces the same wrong click:
   *
   *  - a row (or one of its controls) holds DOM focus;
   *  - a selection exists -- `components.md` section 6 requires the bulk-eligible batch not to grow
   *    or shrink between "Select all eligible" and Confirm;
   *  - the reject or counter-offer dialog is open;
   *  - a write is in flight.
   */
  const writeInFlight = pending !== null || batchBusy
  const frozen =
    rowFocusWithin || selected.size > 0 || writeInFlight || rejectFor !== null || counterFor !== null

  // Read at RESPONSE time, not request time: a planner who focuses a row during the round trip
  // must still get the frozen merge, not the one that was correct when the request left.
  const frozenRef = useRef(frozen)
  frozenRef.current = frozen

  useLivePoll<PlannerQueue>({
    enabled: plannerLiveArrivalsEnabled,
    paused: writeInFlight,
    // Feeds the shell status bar's pending count, and it comes from the LATEST payload rather
    // than the applied one: the status bar is ambient server truth, not a description of the
    // pinned view, and the pill is what explains the gap between the two. That field is `silent`
    // in `accessibility-behaviour.md`'s matrix, so a moving number interrupts nobody.
    pendingCount: live.latest?.count ?? null,
    fetcher: () => fetchPlannerQueue(facilityId),
    onData: (data) => {
      setServerTime(data.as_of)
      setLive((prev) => mergeQueue(prev, data, frozenRef.current))
      // A poll that succeeds after a failed first load is a recovery, not a surprise.
      setLoadFailed(false)
    },
    // A poll failure deliberately does NOT raise the region error: the rows on screen are still the
    // last thing the server actually said, and blanking them would destroy a planner's place in a
    // spike over one dropped request. The failure is reported in the status bar's connection row.
    onError: () => {},
  })

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (q === '') return rows
    return rows.filter(
      (r) =>
        r.shipment_id.toLowerCase().includes(q) ||
        (r.driver_name ?? '').toLowerCase().includes(q) ||
        (r.carrier_name ?? '').toLowerCase().includes(q) ||
        (r.order_reference ?? '').toLowerCase().includes(q),
    )
  }, [rows, search])

  const eligibility = useMemo(() => {
    const map = new Map<string, { eligible: boolean; caveat: string | null }>()
    for (const row of rows) map.set(row.appointment_id, clientVisibleEligibility(row))
    return map
  }, [rows])

  const eligibleIds = useMemo(
    () => visible.filter((r) => eligibility.get(r.appointment_id)?.eligible).map((r) => r.appointment_id),
    [visible, eligibility],
  )

  /**
   * Removes a row the way Flow 1 step 3 and `accessibility.md`'s focus table require: the row
   * leaves, and focus lands on the **next row at the same position**, never the top of the queue
   * -- a planner who confirms row 12 must not be thrown back to row 1.
   *
   * The successor is computed from `rows` here rather than inside the `setRows` updater on
   * purpose: an updater that calls another setter is impure, and React invokes updaters twice
   * under StrictMode. It happens to be idempotent in this case, which is exactly the kind of
   * accident that stops being true after the next edit.
   */
  const removeRow = useCallback(
    (appointmentId: string) => {
      const index = rows.findIndex((r) => r.appointment_id === appointmentId)
      const remaining = rows.filter((r) => r.appointment_id !== appointmentId)
      const successor = index < 0 ? undefined : remaining[Math.min(index, remaining.length - 1)]
      setFocusedId(successor ? successor.appointment_id : null)
      setLive((prev) => removeRowFromState(prev, appointmentId))
      setSelected((prev) => {
        const next = new Set(prev)
        next.delete(appointmentId)
        return next
      })
    },
    [rows],
  )

  const handleRefusal = useCallback((appointmentId: string, err: unknown): PlannerRefusal => {
    const refusal = classifyRefusal(err)
    setRefusals((prev) => ({ ...prev, [appointmentId]: refusal }))
    return refusal
  }, [])

  const doConfirm = useCallback(
    async (row: PlannerQueueRow) => {
      if (!plannerConfirmEnabled || pending) return
      const slot = `confirm:${row.appointment_id}`
      setPending({ kind: 'confirm', appointmentId: row.appointment_id })
      try {
        await confirmRequest({
          shipmentId: row.shipment_id,
          appointmentId: row.appointment_id,
          // Round-tripped verbatim. Never recomputed -- see lib/api.ts's header.
          snapshotHash: row.snapshot_hash,
          idempotencyKey: keyFor(slot),
        })
        keys.current.delete(slot)
        removeRow(row.appointment_id)
        // No Undo affordance. U41's 5-second undo depends on the driver notification being
        // QUEUED and dispatched only when the window closes, with undo cancelling it silently --
        // a server-side mechanism that does not exist. A button that "undid" a committed
        // confirm after the driver had already been told would be a lie, so it is omitted and
        // the gap is stated rather than mocked up.
        toast.success(`Confirmed ${row.shipment_id} · ${row.dock_code ?? row.dock_id}`)
      } catch (err) {
        const refusal = handleRefusal(row.appointment_id, err)
        // A refusal is a decided outcome, not a transport hiccup: the key must not be reused,
        // because a retry would be a genuinely new decision against re-read data.
        if (refusal.kind !== 'OTHER') keys.current.delete(slot)
        if (refusal.kind === 'OTHER') toast.error(withNothingChanged(refusal.message))
      } finally {
        setPending(null)
      }
    },
    [pending, keyFor, removeRow, handleRefusal],
  )

  const doReject = useCallback(
    async (row: PlannerQueueRow, reasonCode: RejectReasonCode, note: string | null) => {
      const slot = `reject:${row.appointment_id}`
      setPending({ kind: 'reject', appointmentId: row.appointment_id })
      setRejectError(null)
      try {
        await rejectRequest({
          shipmentId: row.shipment_id,
          appointmentId: row.appointment_id,
          reasonCode,
          note,
          idempotencyKey: keyFor(slot),
        })
        keys.current.delete(slot)
        setRejectFor(null)
        removeRow(row.appointment_id)
        toast.success(`Rejected ${row.shipment_id} — the driver has been given the reason.`)
      } catch (err) {
        const refusal = classifyRefusal(err)
        if (refusal.kind === 'ALREADY_ACTIONED') {
          // Not a failed send: somebody else's write won. Close and report on the row, where
          // edge-cases #1 wants the outcome shown in place.
          keys.current.delete(slot)
          setRefusals((prev) => ({ ...prev, [row.appointment_id]: refusal }))
          setRejectFor(null)
        } else if (refusal.kind === 'INVALID_REASON_CODE') {
          keys.current.delete(slot)
          setRejectError(
            `The server does not accept that reason code. ${refusal.supported ?? ''}`.trim(),
          )
        } else {
          // State 13: the dialog stays open and every value survives.
          setRejectError(withNothingChanged(refusal.message))
        }
      } finally {
        setPending(null)
      }
    },
    [keyFor, removeRow],
  )

  const doCounterOffer = useCallback(
    async (
      row: PlannerQueueRow,
      option: FeasibleSlotOption,
      reasonCode: RejectReasonCode,
      note: string | null,
    ) => {
      const slot = `counter:${row.appointment_id}:${option.slot_id}`
      setPending({ kind: 'counter-offer', appointmentId: row.appointment_id })
      setCounterError(null)
      try {
        const result = await counterOffer({
          shipmentId: row.shipment_id,
          appointmentId: row.appointment_id,
          dockId: option.dock_id,
          startTs: option.slot_start_ts,
          reasonCode,
          snapshotHash: row.snapshot_hash,
          note,
          idempotencyKey: keyFor(slot),
        })
        keys.current.delete(slot)
        setCounterFor(null)
        const offered = result.offered_options[0]
        toast.success(
          `Counter-offered ${row.shipment_id} · ${offered?.dock_code ?? option.dock_code}. Awaiting the driver.`,
        )
        // Flow 2: the row does NOT vanish -- the planner's work on it is not done until the
        // driver responds. Re-reading is how the moved interval and the fresh snapshot_hash get
        // onto the row; there is no local edit that could produce a correct hash.
        reload()
      } catch (err) {
        const refusal = classifyRefusal(err)
        keys.current.delete(slot)
        if (refusal.kind === 'INTERVAL_UNAVAILABLE') {
          setCounterError(`${refusal.message} Pick another interval.`)
          setCounterRefresh((n) => n + 1)
        } else {
          setCounterFor(null)
          setRefusals((prev) => ({ ...prev, [row.appointment_id]: refusal }))
        }
      } finally {
        setPending(null)
      }
    },
    [keyFor, reload],
  )

  const doBulkConfirm = useCallback(async () => {
    if (!plannerBulkConfirmEnabled || batchBusy) return
    const chosen = rows.filter((r) => selected.has(r.appointment_id))
    if (chosen.length === 0) return
    setBatchBusy(true)
    setBatchNotice(null)
    const slot = `bulk:${chosen.map((r) => r.appointment_id).sort().join(',')}`
    try {
      const rowHashes = Object.fromEntries(chosen.map((r) => [r.appointment_id, r.snapshot_hash]))
      const result = await bulkConfirm({
        appointmentIds: chosen.map((r) => r.appointment_id),
        snapshotHash: await batchSnapshotHash(rowHashes),
        idempotencyKey: keyFor(slot),
      })
      keys.current.delete(slot)

      // Per-id outcomes are the contract, not the batch code. A skipped row STAYS VISIBLE with
      // its own reason attached (edge-cases #7); only the confirmed ones leave.
      const nextOutcomes: Record<string, BulkConfirmOutcome> = {}
      const confirmedIds: string[] = []
      for (const outcome of result.outcomes) {
        if (outcome.code === 'CONFIRMED') confirmedIds.push(outcome.appointment_id)
        else nextOutcomes[outcome.appointment_id] = outcome
      }
      setOutcomes((prev) => ({ ...prev, ...nextOutcomes }))
      // Strips the confirmed ids from the cached payloads too, so a later re-sort cannot bring a
      // row this planner has already confirmed back into the queue. See `removeRowsFromState`.
      setLive((prev) => removeRowsFromState(prev, confirmedIds))
      setSelected(new Set())

      const skippedNames = result.outcomes
        .filter((o) => o.code !== 'CONFIRMED')
        .map((o) => o.shipment_id ?? o.appointment_id)
      toast.success(
        skippedNames.length === 0
          ? `${result.confirmed} confirmed.`
          : `${result.confirmed} confirmed, ${result.skipped} skipped — ${skippedNames.join(', ')}. They stay in the queue for individual review.`,
      )

      if (!result.snapshot_hash_matched) {
        // REPORTS, does not refuse -- `bulk_confirm`'s documented behaviour and an open owner
        // fork (#65). Said plainly rather than swallowed, because it means the board moved
        // between selection and press even where every id still succeeded.
        setBatchNotice(
          'Some rows changed between selecting them and pressing Confirm. The server re-checked every one at press time, so the outcomes above are against current data — not against what was on screen when you selected.',
        )
      }
    } catch (err) {
      const refusal = classifyRefusal(err)
      keys.current.delete(slot)
      toast.error(withNothingChanged(refusal.message))
    } finally {
      setBatchBusy(false)
    }
  }, [batchBusy, rows, selected, keyFor])

  const openCounterOffer = useCallback((row: PlannerQueueRow) => {
    if (!plannerCounterOfferEnabled) return
    setCounterError(null)
    setCounterFor(row)
  }, [])

  const newCount = live.staged.length

  /**
   * The "press S" half of the affordance, and the only thing in this file allowed to move a row.
   *
   * `motion.md`: "the list re-renders instantly at the new order, focus follows the same row by id,
   * and that row flashes once so the planner can find it again." All three happen here -- there is
   * deliberately no transition, because several hundred milliseconds during which the visible order
   * matches neither the old nor the new state is exactly the window in which a keypress does the
   * wrong thing.
   *
   * The next order and the focus target are computed OUTSIDE the `setLive` updater on purpose: an
   * updater that calls another setter is impure and React runs updaters twice under StrictMode.
   */
  const doResort = useCallback(() => {
    const next = applyResort(live)
    const target = focusTargetAfterResort(live.rows, next.rows, focusedId)
    setLive(next)
    setFocusedId(target)
    if (target !== null) {
      // After paint, or the row we want to focus may not exist in the DOM yet.
      requestAnimationFrame(() => {
        tableRef.current
          ?.querySelector<HTMLTableRowElement>(`tr[data-appointment="${target}"]`)
          ?.focus()
      })
    }
  }, [live, focusedId])

  /**
   * Single-key actions on the focused row (U46) -- `C`/`R`/`O`/`H`/`E`. **Never while focus is in
   * a text input**: the product-wide rule, restated by `accessibility.md` because this surface's
   * whole design leans on it working. Modifier chords are excluded too, so `Cmd/Ctrl+1`/`+2`
   * (tab switching, owned by the console) still reach their own handler.
   */
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.metaKey || e.ctrlKey || e.altKey) return
      const target = e.target as HTMLElement | null
      const tag = target?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || target?.isContentEditable) return

      // Re-sort is a surface-level affordance (the header pill), not a per-row action, so unlike
      // `C`/`R`/`O` it fires from anywhere in the Queue tab -- including before anything has been
      // focused at all, which is when a planner is most likely to be watching arrivals accumulate.
      // Scoped to the *visible* tab: the Board tab's panel carries `hidden`, so `offsetParent` is
      // null there and a planner looking at the board cannot silently re-sort a queue behind it.
      const region = regionRef.current
      if (
        e.key.toLowerCase() === RESORT_KEY &&
        region !== null &&
        region.offsetParent !== null &&
        (target === null || target === document.body || region.contains(target))
      ) {
        e.preventDefault()
        doResort()
        return
      }

      if (!tableRef.current?.contains(target ?? null)) return

      const index = visible.findIndex((r) => r.appointment_id === focusedId)
      const move = (delta: number) => {
        if (visible.length === 0) return
        const next = visible[Math.min(visible.length - 1, Math.max(0, (index < 0 ? 0 : index) + delta))]
        setFocusedId(next.appointment_id)
        const el = tableRef.current?.querySelector<HTMLTableRowElement>(
          `tr[data-appointment="${next.appointment_id}"]`,
        )
        el?.focus()
      }

      switch (e.key) {
        case 'j':
        case 'ArrowDown':
          e.preventDefault()
          move(1)
          return
        case 'k':
        case 'ArrowUp':
          e.preventDefault()
          move(-1)
          return
        default:
          break
      }

      const row = visible[index]
      if (!row) return
      switch (e.key.toLowerCase()) {
        case 'c':
          e.preventDefault()
          void doConfirm(row)
          break
        case 'r':
          e.preventDefault()
          setRejectError(null)
          setRejectFor(row)
          break
        case 'o':
          e.preventDefault()
          openCounterOffer(row)
          break
        // `h` (Hold) and `e` (Escalate) are deliberately unbound rather than bound to a no-op:
        // a key that visibly does nothing reads as a broken shortcut, where an unbound key reads
        // as a feature that is not here yet -- which is the truth (issues #64 and the missing
        // `escalate_request` shape).
        default:
          break
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [visible, focusedId, doConfirm, openCounterOffer, doResort])

  if (loadFailed) {
    return <RegionError regionName="queue" onRetry={reload} />
  }
  if (queue === null) {
    return <QueueSkeleton />
  }

  const ttlTotalMs = queue.ttl_minutes * 60_000
  const selectedCount = selected.size
  const bulkAvailable = plannerBulkConfirmEnabled && batchHashAvailable()

  return (
    <div ref={regionRef} className="flex min-h-0 flex-col gap-2">
      {/* Toolbar. The pending count comes from the server's own `count`, and `limit_reached`
          turns it into "at least N" rather than a total the payload cannot support. */}
      <div className="flex shrink-0 flex-wrap items-center gap-4 text-supporting">
        <span className="font-semibold">
          {queue.limit_reached ? `At least ${queue.count}` : queue.count} pending
        </span>
        {bulkAvailable && eligibleIds.length > 0 ? (
          <Button
            variant="constructive"
            onClick={() =>
              setSelected(new Set(eligibleIds.slice(0, MAX_BULK_CONFIRM_IDS)))
            }
          >
            Select all eligible ({eligibleIds.length})
          </Button>
        ) : null}
        <label className="flex items-center gap-2">
          <span className="text-subtle-foreground">Search</span>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Shipment, driver or carrier…"
            className="h-8 w-56 rounded-md border border-input bg-card px-2 text-supporting text-foreground outline-none focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
          />
        </label>
        {/* The sort must always be stated (`implementation-spec.md` section 5.3-R17 / State 1) and
            the pin state must be visible when it is on -- a planner has to be able to tell that the
            order they are looking at is held rather than current. */}
        <span className="text-subtle-foreground">
          {frozen ? 'Sort pinned' : 'Sort'} · composite urgency (TTL · priority · waiting at the
          gate)
        </span>

        {plannerLiveArrivalsEnabled && newCount > 0 ? (
          <button
            type="button"
            onClick={doResort}
            className="inline-flex items-center gap-1 rounded border border-info-border bg-info-bg px-2 py-0.5 text-supporting font-semibold tabular-nums text-info-fg focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
          >
            {newCount} new · press {RESORT_KEY_LABEL}
          </button>
        ) : null}

        {/* `accessibility-behaviour.md`'s matrix, "Planner queue — new row arrives": **polite, and
            the COUNT ONLY**. Announcing each arrival's content during a spike is the "distracting
            stream" case, and a spike is exactly when this fires most. Kept as its own region rather
            than wrapping the pill, so the words "press S" are not read out on every arrival, and
            rendered unconditionally so the live region exists in the DOM before its text changes. */}
        <span role="status" className="sr-only">
          {plannerLiveArrivalsEnabled && newCount > 0
            ? `${newCount} new request${newCount === 1 ? '' : 's'}`
            : ''}
        </span>

        <Button variant="neutral" className="ml-auto" onClick={reload}>
          <RefreshCw aria-hidden="true" />
          Refresh
        </Button>
      </div>

      {!plannerLiveArrivalsEnabled ? (
        <p className="shrink-0 text-micro text-subtle-foreground">
          New requests do not appear on their own — live arrivals are switched off. Refresh to
          re-read, which also re-sorts.
        </p>
      ) : null}

      {/* The contextual action bar exists only while something is selected and reserves no
          vertical space when nothing is (`components.md` foundations section 19). */}
      {selectedCount > 0 ? (
        <div className="flex shrink-0 items-center gap-4 rounded-md border border-info-border bg-info-bg px-3 py-2">
          <span className="text-supporting font-semibold">{selectedCount} selected</span>
          <div className="ml-auto flex items-center gap-3">
            <Button variant="ghost" onClick={() => setSelected(new Set())} disabled={batchBusy}>
              Clear selection
            </Button>
            <Button
              variant="constructive"
              aria-busy={batchBusy}
              aria-disabled={batchBusy}
              onClick={() => void doBulkConfirm()}
            >
              {`Confirm ${selectedCount}`}
            </Button>
          </div>
        </div>
      ) : null}

      {batchNotice ? <Alert variant="warning">{batchNotice}</Alert> : null}

      {rows.length === 0 ? (
        // Only the "caught up" empty state can be asserted from this payload. "This facility has
        // never had a request" is a genuinely different fact (U74) and `get_planner_queue`
        // returns no has-ever-had-requests signal, so that state is not guessed at from
        // `count === 0` -- it stays in the gallery, unreachable, until the read grows the flag
        // (`implementation-spec.md` section 6 Fork C).
        <QueueEmptyCaughtUp />
      ) : visible.length === 0 ? (
        <QueueSearchEmpty query={search} onClear={() => setSearch('')} />
      ) : (
        <div
          className="min-h-0 flex-1 overflow-auto"
          // `focusin`/`focusout` (React's bubbling onFocus/onBlur). `relatedTarget` is where focus
          // is GOING, so moving between two rows never registers as leaving the table -- without
          // that check the sort would unfreeze for one render on every `j`/`k` press.
          onFocus={() => setRowFocusWithin(true)}
          onBlur={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setRowFocusWithin(false)
          }}
        >
          <table
            ref={tableRef}
            className="w-full table-fixed border-collapse"
            aria-label="Pending appointment requests"
          >
            {/* Fixed pixel widths, never `auto` or `fr` -- `components.md` section 1's hard rule:
                a reflow during a read is an operational cost on this screen specifically. */}
            <colgroup>
              <col style={{ width: '48px' }} />
              <col style={{ width: '164px' }} />
              <col style={{ width: '210px' }} />
              <col style={{ width: '190px' }} />
              <col style={{ width: '250px' }} />
              <col style={{ width: '72px' }} />
              <col style={{ width: '80px' }} />
              <col style={{ width: '66px' }} />
              <col style={{ width: '160px' }} />
            </colgroup>
            <thead>
              <tr className="border-b border-border text-label text-subtle-foreground uppercase">
                <th scope="col" className="px-3 py-2 text-left">
                  <span className="sr-only">Select</span>
                </th>
                <th scope="col" className="px-2 py-2 text-left">Driver · carrier</th>
                <th scope="col" className="px-2 py-2 text-left">Requested interval</th>
                <th scope="col" className="px-2 py-2 text-left">Decision receipt</th>
                <th scope="col" className="px-2 py-2 text-left">Displacement</th>
                <th scope="col" className="px-2 py-2 text-left">ETA</th>
                <th scope="col" className="px-2 py-2 text-left">Driver’s limit</th>
                <th scope="col" className="px-2 py-2 text-left">TTL</th>
                <th scope="col" className="px-2 py-2 text-left">Actions</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((row) => (
                <QueueRow
                  key={row.appointment_id}
                  row={row}
                  ttlTotalMs={ttlTotalMs}
                  focused={focusedId === row.appointment_id}
                  selected={selected.has(row.appointment_id)}
                  busy={pending?.appointmentId === row.appointment_id || batchBusy}
                  selectionCaveat={eligibility.get(row.appointment_id)?.caveat ?? null}
                  refusal={refusals[row.appointment_id] ?? null}
                  outcome={outcomes[row.appointment_id] ?? null}
                  arrived={live.flash.has(row.appointment_id)}
                  // `accessibility-behaviour.md`'s matrix, both rows at once: a row acted on
                  // elsewhere is `assertive` **only** when it is the row this planner is focused
                  // on ("a user about to act on a row that just changed underneath them must be
                  // interrupted"); any other row changes silently, the frozen-sort principle
                  // extended to audio.
                  vanished={
                    live.vanished.has(row.appointment_id)
                      ? { announce: focusedId === row.appointment_id }
                      : null
                  }
                  onFocusRow={() => setFocusedId(row.appointment_id)}
                  onToggleSelect={() =>
                    setSelected((prev) => {
                      const next = new Set(prev)
                      if (next.has(row.appointment_id)) next.delete(row.appointment_id)
                      else if (next.size < MAX_BULK_CONFIRM_IDS) next.add(row.appointment_id)
                      return next
                    })
                  }
                  onConfirm={() => void doConfirm(row)}
                  onReject={() => {
                    setRejectError(null)
                    setRejectFor(row)
                  }}
                  onCounterOffer={() => openCounterOffer(row)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <RejectDialog
        row={rejectFor}
        open={rejectFor !== null}
        onOpenChange={(next) => !next && setRejectFor(null)}
        busy={pending?.kind === 'reject'}
        error={rejectError}
        onSubmit={(reasonCode, note) => {
          if (rejectFor) void doReject(rejectFor, reasonCode, note)
        }}
      />

      <CounterOfferDialog
        row={counterFor}
        open={counterFor !== null}
        onOpenChange={(next) => !next && setCounterFor(null)}
        busy={pending?.kind === 'counter-offer'}
        error={counterError}
        refreshToken={counterRefresh}
        onSubmit={(option, reasonCode, note) => {
          if (counterFor) void doCounterOffer(counterFor, option, reasonCode, note)
        }}
      />
    </div>
  )
}

/**
 * What this client can honestly say about bulk eligibility -- **three of section 7.3's five
 * safe-batch predicates, and it says which two it cannot see.**
 *
 * The server re-evaluates all five at press time (`allocation.evaluate_safe_batch_predicates`),
 * and that re-check is what keeps D6's human authority real rather than ceremonial. Nothing here
 * substitutes for it: this only decides which rows "Select all eligible (N)" pre-ticks, and every
 * one of them can still come back skipped with a named predicate, which the row then renders.
 *
 * Derivable from a queue row:
 *   - `ZERO_DISPLACEMENT`        -> `displacement.status === 'NONE'`
 *   - `EXACT_DOCK_MATCH`         -> `receipt.dock_match === 'exact'`
 *   - `ETA_CONFIDENCE_NOT_LOW`   -> `eta.confidence !== 'LOW'`
 *
 * NOT derivable, and deliberately not guessed at:
 *   - `INSIDE_HOURS_AND_BEFORE_LAST_NEW_START` -- needs the facility's operating window, which
 *     `get_planner_queue` does not return.
 *   - `NO_OPEN_ESCALATION` -- needs `escalation_queue`, which this read does not join.
 *
 * **Deviation from `screens.md` section 2, flagged not hidden.** The design says an ineligible
 * row shows a *disabled* checkbox carrying its failing predicate. With only 3 of 5 predicates
 * visible, disabling would block a planner from manually selecting a row that is genuinely
 * eligible on all five -- a false refusal, and the harmful direction of the two. So every row
 * stays selectable and the caveat rides as a tooltip instead. When the queue read grows the two
 * missing signals, this can become the disabled control the design asks for.
 */
function clientVisibleEligibility(row: PlannerQueueRow): {
  eligible: boolean
  caveat: string | null
} {
  const reasons: string[] = []
  if (row.displacement.status !== 'NONE') reasons.push('it would displace another booking')
  if (row.receipt.dock_match !== 'exact') reasons.push('the dock type is not an exact match')
  if ((row.eta.confidence ?? '').toUpperCase() === 'LOW') reasons.push('its ETA confidence is LOW')

  if (reasons.length === 0) {
    return {
      eligible: true,
      caveat: null,
    }
  }
  return {
    eligible: false,
    caveat: `Outside the safe batch on what this screen can see: ${reasons.join('; ')}. You can still select it — the server re-checks all five predicates when you press Confirm.`,
  }
}
