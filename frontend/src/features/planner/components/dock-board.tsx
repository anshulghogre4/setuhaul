import { Truck } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { RegionError } from '@/components/states/region-states'
import { formatUserFriendlyError } from '@/core/http/api'
import { useCountdownClock } from '@/shared/lib/countdown'
import { Button } from '@/shared/ui/button'
import { cn } from '@/shared/lib/utils'
import { counterOffer, endDockBlock, fetchDockBoard, fetchFeasibleSlots } from '../lib/api'
import { classifyRefusal, withNothingChanged } from '../lib/refusals'
import type { RejectReasonCode } from '../lib/reasons'
import { BoardPickerBanner } from './board-picker'
import {
  LEGEND_STATES,
  barTreatment,
  groupByDock,
  hourTicks,
  placeOnTrack,
} from '../lib/board'
import { formatDate, formatTime } from '../lib/format'
import { BoardSkeleton } from './board-skeleton'
import type {
  BoardBar,
  BoardBlock,
  BoardDock,
  DockBoard as DockBoardPayload,
  FeasibleSlotOption,
  PlannerQueueRow,
} from '../lib/types'

/**
 * The Board tab at rest -- `03-planner-dock-board/screens.md` section 3, `stitch-prompts.md`
 * section 8, states 2 and 22.
 *
 * One horizontal lane per dock, time along the x-axis, one bar per live `dock_occupancy` claim.
 * Every bar's treatment comes from `lib/board.ts`'s single mapping table (components.md section 3's
 * own rule); there is no per-state branch in this file.
 *
 * ## The three rules from the prompt that are code here rather than review notes
 *
 * 1. **Nothing on this board is draggable.** No drag-to-reschedule, no resize handles, no
 *    range-select. Bars are focusable elements with tooltips; every action happens through an
 *    explicit control. A drag affordance on a capacity board is a mis-book waiting for a slip.
 * 2. **The now-line is server time**, reconciled through `CountdownProvider`'s measured offset --
 *    never bare `Date.now()`. A planner whose laptop clock is three minutes fast would otherwise
 *    see the line, and therefore every "is this already running" judgement, three minutes wrong.
 * 3. **A terminal state renders as open space, never a ghost bar.** Enforced by the mapping table
 *    returning `null`, not by a filter here.
 *
 * ## The board owns its fetch
 *
 * Same reason `QueueTab` does, and it is the trap E5.3's own flag audit named: a component that
 * renders an empty/at-rest state without having asked the server tells a planner the board is clear
 * when it has simply never looked. The empty caption below is reachable only after a successful read
 * that genuinely returned nothing.
 *
 * ## What is deliberately NOT here
 *
 * The counter-offer picker's interactive mode (states 3, 24, 25 -- eligible lanes highlighted,
 * ineligible dimmed) is not built. It needs per-shipment eligibility over these lanes, which is a
 * different read from this one, and `plannerCounterOfferEnabled`'s interim dialog remains the entry
 * point until it exists. Stated here rather than hinted at by absence.
 */

/** Lane geometry. 32px lanes and a 56px label column, from `stitch-prompts.md` section 8. */
const LANE_H = 'h-8'
const LABEL_W = 'w-14'
/** Kept in sync with `LABEL_W` (`w-14` = 3.5rem = 56px). The now-line's offset has to be expressed
 *  in the same units as the label column it starts after, so the number appears twice by necessity
 *  and is named once here rather than inlined. */
const LABEL_WIDTH_PX = 56

export function DockBoardPanel({
  facilityId,
  /**
   * Bumped by `PlannerConsole` after a successful `block_dock` (issue #100).
   *
   * Flow 7 step 4 requires the board's outage layer to update "immediately" once the form closes,
   * and it did not: the panel owned its fetch and nothing told it a block had been created, so the
   * new hatch (and, since #100, the new Active-blocks row) only appeared on the next tab switch or
   * reload. That made the end-block control unreachable for the block a planner had just made,
   * which is precisely the case it exists for.
   */
  externalReloadToken = 0,
  picking = null,
  onPickerCancel = () => {},
  onPickerDone = () => {},
}: {
  facilityId: string | null
  externalReloadToken?: number
  /** U103: the queue row a planner pressed Counter-offer on, or `null` at rest. Owned by
   *  `PlannerConsole` because entering the picker also switches tab, which is the console's job. */
  picking?: PlannerQueueRow | null
  onPickerCancel?: () => void
  onPickerDone?: (outcome: { ok: boolean; message: string }) => void
}) {
  const [board, setBoard] = useState<DockBoardPayload | null>(null)
  const [failed, setFailed] = useState(false)
  const [reloadToken, setReloadToken] = useState(0)
  const { now, offsetMs, setServerTime } = useCountdownClock()

  // --- counter-offer picker (U103, `screens.md` section 4) -------------------------------------
  const [options, setOptions] = useState<FeasibleSlotOption[] | null>(null)
  const [optionsToken, setOptionsToken] = useState(0)
  const [chosen, setChosen] = useState<FeasibleSlotOption | null>(null)
  const [reason, setReason] = useState<RejectReasonCode | null>(null)
  const [note, setNote] = useState('')
  const [sending, setSending] = useState(false)
  const [pickerError, setPickerError] = useState<string | null>(null)

  /** One key per *press*, reused across a retry of that press -- U70, and the same mechanism
   *  `queue-tab.tsx` uses. Keyed by appointment AND slot, so picking a different interval after a
   *  refusal is a genuinely new decision with its own key rather than a replay of the first. */
  const keys = useRef<Map<string, string>>(new Map())
  const keyFor = useCallback((slot: string) => {
    const existing = keys.current.get(slot)
    if (existing) return existing
    const next = crypto.randomUUID()
    keys.current.set(slot, next)
    return next
  }, [])

  const pickingShipment = picking?.shipment_id ?? null

  useEffect(() => {
    // Entering the picker (or re-fetching after INTERVAL_UNAVAILABLE) reloads Stage 1's answer.
    // Leaving it drops everything: a half-chosen interval surviving into the next request would be
    // the worst possible carry-over on this surface.
    setChosen(null)
    setReason(null)
    setNote('')
    setPickerError(null)
    if (!pickingShipment) {
      setOptions(null)
      return
    }
    let ignore = false
    setOptions(null)
    fetchFeasibleSlots(pickingShipment)
      .then((res) => {
        if (!ignore) setOptions(res.options)
      })
      .catch((err: unknown) => {
        if (ignore) return
        setOptions([])
        setPickerError(
          `Couldn't load feasible intervals. ${err instanceof Error ? err.message : ''}`.trim(),
        )
      })
    return () => {
      ignore = true
    }
  }, [pickingShipment, optionsToken])

  useEffect(() => {
    let ignore = false
    setFailed(false)
    fetchDockBoard(facilityId)
      .then((data) => {
        if (ignore) return
        setBoard(data)
        // Same reconciliation the queue does: the now-line and any hold countdown on this board are
        // only as honest as the offset between this browser's clock and the server's.
        setServerTime(data.as_of)
      })
      .catch(() => {
        if (!ignore) setFailed(true)
      })
    return () => {
      ignore = true
    }
  }, [facilityId, reloadToken, externalReloadToken, setServerTime])

  const retry = useCallback(() => setReloadToken((n) => n + 1), [])

  /**
   * `screens.md` section 4's commit step.
   *
   * > *"Clicking an open interval **revalidates through Stage 1 before offering** — a planner
   * > cannot hand out an infeasible slot by hand. A refusal (`INTERVAL_UNAVAILABLE`) re-renders the
   * > board with that interval now shown occupied, never a dead click."*
   *
   * The revalidation is genuinely server-side: `counter_offer` resolves `(dock_id, start_ts)` to a
   * real `appointment_slots` row and runs `explain_slot_eligibility` before reserving. What the
   * board contributes is that the planner can only ever *click* an interval Stage 1 already
   * returned, so the refusal is a rare race rather than the normal outcome -- the exact property
   * `lib/api.ts::fetchFeasibleSlots` says a typed-timestamp form would have destroyed.
   */
  const sendCounterOffer = useCallback(async () => {
    if (!picking || !chosen || reason === null || sending) return
    const slot = `counter:${picking.appointment_id}:${chosen.slot_id}`
    setSending(true)
    setPickerError(null)
    try {
      await counterOffer({
        shipmentId: picking.shipment_id,
        appointmentId: picking.appointment_id,
        dockId: chosen.dock_id,
        startTs: chosen.slot_start_ts,
        reasonCode: reason,
        // Round-tripped verbatim from the queue row. Never recomputed here -- `lib/api.ts`'s
        // snapshot rule applies to this call site exactly as it does to the dialog's.
        snapshotHash: picking.snapshot_hash,
        note: note.trim() === '' ? null : note.trim(),
        idempotencyKey: keyFor(slot),
      })
      keys.current.delete(slot)
      onPickerDone({
        ok: true,
        message: `Counter-offered ${picking.shipment_id} · ${chosen.dock_code}. Awaiting the driver.`,
      })
    } catch (err) {
      const refusal = classifyRefusal(err)
      // A refusal is a decided outcome, not a transport hiccup: the key must not be reused,
      // because a retry would be a genuinely new decision against re-read data.
      keys.current.delete(slot)
      if (refusal.kind === 'INTERVAL_UNAVAILABLE') {
        // Section 4's own answer: stay in the picker, drop the choice, and re-read BOTH the
        // feasible set and the board so the interval that was taken renders occupied.
        setChosen(null)
        setPickerError(`${refusal.message} Pick another interval.`)
        setOptionsToken((n) => n + 1)
        retry()
      } else {
        // Everything else (ALREADY_ACTIONED, SNAPSHOT_STALE, DISPLACEMENT_DETECTED) closes the
        // picker and reports on the row, where the planner can see it in the queue's own context
        // -- the same split `counter-offer-dialog.tsx` documents for the interim form.
        onPickerDone({ ok: false, message: withNothingChanged(refusal.message) })
      }
    } finally {
      setSending(false)
    }
  }, [picking, chosen, reason, note, sending, keyFor, onPickerDone, retry])

  if (failed) {
    // State 23. Scoped to this region -- the Queue tab stays usable, per the prompt's own error
    // variant ("never a whole-app error screen").
    return <RegionError regionName="dock board" onRetry={retry} />
  }
  if (board === null) return <BoardSkeleton />

  return (
    <>
      {picking ? (
        <BoardPickerBanner
          row={picking}
          chosen={chosen}
          reason={reason}
          note={note}
          optionCount={options?.length ?? 0}
          outOfHorizonCount={countOutOfHorizon(options, board)}
          loading={options === null}
          busy={sending}
          error={pickerError}
          onReasonChange={setReason}
          onNoteChange={setNote}
          onClearChoice={() => setChosen(null)}
          onCancel={onPickerCancel}
          onSubmit={() => void sendCounterOffer()}
        />
      ) : null}

      <Board
        board={board}
        nowMs={now + offsetMs}
        pickable={picking ? (options ?? []) : null}
        chosenSlotId={chosen?.slot_id ?? null}
        onPickInterval={(option) => {
          setPickerError(null)
          setChosen(option)
        }}
      />

      {/* Flow 8's second stated entry point. Rendered here rather than inside `Board` so
          `BoardPlate` (the `/planner/_states` gallery) keeps rendering the board and nothing that
          writes -- a gallery artboard with a live `end_dock_block` button would be a fixture page
          that can change production capacity. `retry` is the same reload token the fetch above
          uses, so ending a block re-reads the board rather than mutating a local copy of it.

          Hidden while picking: `screens.md` section 4's board carries exactly one action, and
          leaving a capacity-mutating control live underneath the picker invites a planner to block
          the very dock they are mid-way through offering. */}
      {picking ? null : <ActiveBlocks board={board} onEnded={retry} />}
    </>
  )
}

/**
 * How many of Stage 1's feasible intervals cannot be drawn on this board.
 *
 * The board's horizon is server-computed as "four hours, or until closing time, whichever comes
 * sooner", while `find_feasible_slots` searches its own, longer horizon -- so a genuinely feasible
 * interval can simply be off the right-hand edge, or on a dock outside this facility's board.
 * `placeOnTrack` already returns `null` for the first case (that is how a bar outside the horizon
 * is correctly not drawn); this counts the same condition so the banner can *say* the number
 * rather than the planner discovering that four of six options never appeared.
 */
function countOutOfHorizon(
  options: FeasibleSlotOption[] | null,
  board: DockBoardPayload,
): number {
  if (options === null) return 0
  const startMs = Date.parse(board.horizon_start)
  const endMs = Date.parse(board.horizon_end)
  const dockIds = new Set(board.docks.map((d) => d.dock_id))
  return options.filter(
    (o) =>
      !dockIds.has(o.dock_id) ||
      placeOnTrack(o.slot_start_ts, o.slot_end_ts, startMs, endMs) === null,
  ).length
}

/**
 * **Flow 8 — End a dock block** (`flows-and-states.md`: *"From the outage-window marker (§4) or a
 * small 'Active blocks' list on the Board tab — `end_dock_block(dock_status_event_id)`"*).
 * Issue #100.
 *
 * `endDockBlock()` shipped with the block-dock group and had **zero call sites**: a planner who
 * blocked a dock for a spill and cleared it early had no way back, so the block ran its course or
 * someone ran SQL. This is that missing control.
 *
 * ## The list, not the marker — and why
 *
 * The design offers both. The list is chosen because the marker cannot carry the affordance at a
 * usable size: a marker's width IS its duration, so the 20-minute outage a planner most often
 * clears early draws ~8px on a four-hour axis (`placeOnTrack`), which is under every touch and
 * pointer floor this product holds itself to and would need a popover to hang a button off. A
 * list row is a stable target with room for the dock, the dated window and the reason.
 *
 * ⚠ **The list is NOT "every block".** `board.blocks` is horizon-filtered server-side —
 * `planner_service._board_blocks` selects only events overlapping `[horizon_start, horizon_end)`,
 * deliberately, so that the hatch appears exactly when Stage 1 would refuse the interval. So a
 * block scheduled entirely beyond the board's horizon (tonight, tomorrow) cannot be ended from
 * this surface, and neither can a marker-based control end it — the row simply is not in the
 * payload. Ending those still needs a read this surface does not have (`dock_status_events` has no
 * "list active blocks" tool in §7.5.1). Stated here rather than discovered later.
 *
 * ## Friction: an in-place confirm, not a modal and not a bare click
 *
 * `00-foundations/components.md` §19 tiers this as **Moderate** — the same tier `components.md` §6
 * assigns to *creating* a block, on the reasoning that it is reversible. Moderate's stated
 * treatment is "acts immediately, 5-second undo, no modal", and the undo half genuinely does not
 * apply here: U41's undo window exists to hold back a **driver notification** until it closes
 * (`shared/lib/undo.ts`), and ending a block notifies nobody — there is nothing to defer, so an
 * "Undo" would have to re-block, which creates a *different* `dock_status_events` row and is a new
 * decision rather than a reversal. So the friction is an in-place two-step, the same shape the
 * shell's own "Sign out everywhere" uses: no modal (U41), safer action first in DOM order (U79).
 */
function ActiveBlocks({
  board,
  onEnded,
}: {
  board: DockBoardPayload
  onEnded: () => void
}) {
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [endingId, setEndingId] = useState<string | null>(null)

  const dockCodeById = useMemo(
    () => new Map(board.docks.map((d) => [d.dock_id, d.dock_code])),
    [board.docks],
  )

  if (board.blocks.length === 0) return null

  async function end(block: BoardBlock) {
    if (endingId !== null) return
    setEndingId(block.dock_event_id)
    try {
      const result = await endDockBlock(block.dock_event_id)
      setConfirmingId(null)
      if (result.code === 'NOT_BLOCKED') {
        // Flow 8: "`NOT_BLOCKED` (already ended elsewhere) refreshes the board silently,
        // consistent with U19's rule that a background change to something the planner wasn't
        // focused on does not interrupt them." So no toast -- the board re-read is the whole
        // response, and the marker disappearing IS the answer.
        onEnded()
        return
      }
      toast.success(
        `${dockCodeById.get(block.dock_id) ?? block.dock_id} is bookable again from now.`,
      )
      onEnded()
    } catch (err) {
      // The mandatory phrase for a failed write (`stitch-prompts.md` §12) -- the block is still in
      // place, and a planner who walks away believing the dock is free would send a truck to it.
      toast.error(`${formatUserFriendlyError(err)} Nothing has changed — the dock is still blocked.`)
    } finally {
      setEndingId(null)
    }
  }

  return (
    <section aria-labelledby="active-blocks-heading" className="mt-4 flex flex-col gap-2">
      <h3 id="active-blocks-heading" className="text-supporting font-semibold text-foreground">
        Active blocks
      </h3>
      <ul role="list" className="flex flex-col gap-1">
        {board.blocks.map((block) => {
          const dockCode = dockCodeById.get(block.dock_id) ?? block.dock_id
          const window = block.event_end_ts
            ? `${formatDate(block.event_start_ts)} · ${formatTime(block.event_start_ts)}–${formatTime(block.event_end_ts)}`
            : `${formatDate(block.event_start_ts)} · from ${formatTime(block.event_start_ts)}, no end set`
          const confirming = confirmingId === block.dock_event_id
          const busy = endingId === block.dock_event_id

          return (
            <li
              key={block.dock_event_id}
              className="rounded-md border border-border bg-card px-3 py-2"
            >
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span className="font-mono text-supporting text-foreground">{dockCode}</span>
                <span className="text-supporting text-muted-foreground" translate="no">
                  {window}
                </span>
                <span className="min-w-0 flex-1 truncate text-supporting text-muted-foreground">
                  {block.reason ?? block.event_type}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-expanded={confirming}
                  // Names the dock in the accessible name: three rows all reading "End block"
                  // would give a screen-reader user three identical controls with no way to tell
                  // which dock each one frees.
                  aria-label={`End the block on ${dockCode}`}
                  onClick={() => setConfirmingId(confirming ? null : block.dock_event_id)}
                >
                  End block
                </Button>
              </div>

              {confirming ? (
                <div className="mt-2 border-t border-border pt-2">
                  <p className="mb-2 text-supporting text-muted-foreground">
                    {dockCode} becomes bookable again from now. Appointments already stranded by
                    this block are not restored — the escalation it opened stays open.
                  </p>
                  {/* U79: the safer action FIRST in DOM order, so a keyboard user who overshoots
                      lands on the harmless one. */}
                  <div className="flex items-center gap-2">
                    <Button variant="neutral" size="sm" onClick={() => setConfirmingId(null)}>
                      Keep it blocked
                    </Button>
                    <Button
                      variant="cautionary"
                      size="sm"
                      aria-disabled={busy}
                      onClick={() => {
                        if (busy) return
                        void end(block)
                      }}
                    >
                      {busy ? 'Ending…' : 'End block'}
                    </Button>
                  </div>
                </div>
              ) : null}
            </li>
          )
        })}
      </ul>
    </section>
  )
}

/**
 * The board rendered from a payload the caller already has, with **no fetch**.
 *
 * Exists for `/planner/_states`: the gallery's whole purpose is that "it type-checks" is not "it has
 * been seen rendering", which only holds if the plate mounts the *same* component the route does.
 * A second board built for the gallery would certify markup the live surface never uses.
 *
 * The now-line still comes from the shared clock, so on a fixture whose horizon is in the past the
 * line is correctly absent rather than pinned to an edge.
 */
export function BoardPlate({
  board,
  pickable = null,
  chosenSlotId = null,
  onPickInterval,
}: {
  board: DockBoardPayload
  /** Lets the gallery mount the picker's own rendering (states 3/24/25) through the SAME `Board`
   *  the live route uses. Still writes nothing: the plate supplies a no-op `onPickInterval`, and
   *  the counter-offer call lives in `DockBoardPanel`, which the gallery never mounts. */
  pickable?: FeasibleSlotOption[] | null
  chosenSlotId?: string | null
  onPickInterval?: (option: FeasibleSlotOption) => void
}) {
  const { now, offsetMs } = useCountdownClock()
  return (
    <Board
      board={board}
      nowMs={now + offsetMs}
      pickable={pickable}
      chosenSlotId={chosenSlotId}
      onPickInterval={onPickInterval}
    />
  )
}

function Board({
  board,
  nowMs,
  pickable = null,
  chosenSlotId = null,
  onPickInterval,
}: {
  board: DockBoardPayload
  nowMs: number
  /** `null` = at rest. A non-null array (even empty) means the counter-offer picker is active, and
   *  is what switches every lane into eligible/ineligible rendering. */
  pickable?: FeasibleSlotOption[] | null
  chosenSlotId?: string | null
  onPickInterval?: (option: FeasibleSlotOption) => void
}) {
  const horizonStartMs = useMemo(() => Date.parse(board.horizon_start), [board.horizon_start])
  const horizonEndMs = useMemo(() => Date.parse(board.horizon_end), [board.horizon_end])

  const barsByDock = useMemo(() => groupByDock(board.bars), [board.bars])
  const blocksByDock = useMemo(() => groupByDock(board.blocks), [board.blocks])
  const ticks = useMemo(
    () => hourTicks(horizonStartMs, horizonEndMs),
    [horizonStartMs, horizonEndMs],
  )

  const nowPlacement =
    nowMs >= horizonStartMs && nowMs <= horizonEndMs
      ? ((nowMs - horizonStartMs) / (horizonEndMs - horizonStartMs)) * 100
      : null

  const facility = board.facility_name ?? board.facility_id

  return (
    <div className="flex flex-col gap-3">
      {/* The board's own DATE, always. A board of times with no date is the wrong-day hazard this
          product designs against, and it is the one thing `stitch-prompts.md` section 8 puts in
          the header by name. */}
      <p className="text-supporting text-muted-foreground">
        {facility} · {formatDate(board.horizon_start)} · {formatTime(board.horizon_start)}–
        {formatTime(board.horizon_end)}{' '}
        <span className="text-subtle-foreground">
          {board.horizon_end_reason === 'FACILITY_CLOSE'
            ? '(to closing time)'
            : '(next four hours)'}
        </span>
      </p>

      <div className="flex flex-col">
        {/* Axis. `aria-hidden` because every tick's information is already in each bar's own
            accessible name as a dated interval -- a screen-reader user should not have to
            reconstruct a time from a pixel offset. */}
        <div aria-hidden="true" className="flex items-end">
          <div className={cn(LABEL_W, 'shrink-0')} />
          <div className="relative h-5 flex-1">
            {ticks.map((t) => (
              <span
                key={t}
                className="absolute font-mono text-micro text-subtle-foreground"
                style={{
                  left: `${((t - horizonStartMs) / (horizonEndMs - horizonStartMs)) * 100}%`,
                  transform: 'translateX(-50%)',
                }}
              >
                {formatTime(new Date(t).toISOString())}
              </span>
            ))}
          </div>
        </div>

        {/* `role="list"` of lanes: the board is a set of docks, and a screen reader walking it
            should hear that structure rather than a table it cannot navigate cell-wise. */}
        <div
          role="list"
          aria-label={`Dock occupancy at ${facility}`}
          className={cn(
            'relative flex flex-col',
            // Fork F's component-scoped token (U85, tokens.md's component tier). See `board.ts`
            // for the measurement and why this is not a change to `color.md`. Dark deliberately
            // falls through to the foundations token, which already clears 3:1 there.
            '[--dock-bar-held-border:var(--amber-700)]',
            'dark:[--dock-bar-held-border:var(--color-state-held-border)]',
          )}
        >
          {board.docks.map((dock) => (
            <Lane
              key={dock.dock_id}
              dock={dock}
              bars={barsByDock.get(dock.dock_id) ?? []}
              blocks={blocksByDock.get(dock.dock_id) ?? []}
              horizonStartMs={horizonStartMs}
              horizonEndMs={horizonEndMs}
              ticks={ticks}
              picking={pickable !== null}
              // Eligibility is Stage 1's own answer, projected onto this lane -- never recomputed
              // client-side from dock_type/weight, which would be a second implementation of a
              // constraint the engine already owns.
              laneOptions={pickable?.filter((o) => o.dock_id === dock.dock_id) ?? []}
              chosenSlotId={chosenSlotId}
              onPickInterval={onPickInterval}
            />
          ))}

          {/* The now-line spans the whole lane stack. Static: `stitch-prompts.md` section 8
              excludes a pulsing now-line explicitly, along with every other ambient movement. */}
          {nowPlacement !== null && board.docks.length > 0 ? (
            <span
              aria-hidden="true"
              className="pointer-events-none absolute inset-y-0 w-0.5 bg-foreground"
              style={{ left: `calc(${LABEL_WIDTH_PX}px + (100% - ${LABEL_WIDTH_PX}px) * ${nowPlacement / 100})` }}
            />
          ) : null}
        </div>

        {board.docks.length === 0 ? (
          <p className="py-6 text-supporting text-muted-foreground">
            No docks are configured at {facility}.
          </p>
        ) : null}
      </div>

      {/* The empty variant renders the LANES and then says this, rather than replacing the board
          with a blank panel -- `stitch-prompts.md` section 8's own wording. */}
      {board.docks.length > 0 && board.bars.length === 0 ? (
        <p className="text-supporting text-muted-foreground">
          {board.horizon_end_reason === 'FACILITY_CLOSE'
            ? `No appointments before closing time at ${facility}.`
            : `No appointments in the next four hours at ${facility}.`}
        </p>
      ) : null}

      <Legend holdsEnabled={board.holds_enabled} hasBlocks={board.blocks.length > 0} />
    </div>
  )
}

function Lane({
  dock,
  bars,
  blocks,
  horizonStartMs,
  horizonEndMs,
  ticks,
  picking = false,
  laneOptions = [],
  chosenSlotId = null,
  onPickInterval,
}: {
  dock: BoardDock
  bars: BoardBar[]
  blocks: BoardBlock[]
  horizonStartMs: number
  horizonEndMs: number
  ticks: number[]
  picking?: boolean
  laneOptions?: FeasibleSlotOption[]
  chosenSlotId?: string | null
  onPickInterval?: (option: FeasibleSlotOption) => void
}) {
  /**
   * `screens.md` section 4: *"Ineligible docks dim and become unclickable (`components.md` §18's
   * **Disabled**, not Inactive — this is a temporary, prerequisite-driven unavailability specific
   * to *this* shipment, not a permission or scope question)."*
   *
   * Disabled is the right tier and it is why there is nothing to activate here: an Inactive control
   * explains itself on press, but "this dock cannot take this shipment" has no further explanation
   * this client possesses (no read returns per-dock constraint failures), so a press that said
   * nothing new would be worse than a lane that is plainly out of play. The `title` carries the one
   * true sentence, and the lane keeps its label and its bars so the planner can still *read* it.
   */
  const ineligible = picking && laneOptions.length === 0

  return (
    <div
      role="listitem"
      className="flex items-center border-b border-border"
      data-ineligible={ineligible ? 'true' : undefined}
    >
      <span
        className={cn(
          LABEL_W,
          'shrink-0 truncate py-1 pr-2 font-mono text-supporting',
          // Issue #90's ruling: dim with the muted/disabled TOKENS, never an opacity multiplier --
          // opacity on a lane would drag its bars' contrast below the floor they were measured at.
          ineligible ? 'text-disabled-foreground' : 'text-muted-foreground',
        )}
      >
        {dock.dock_code}
      </span>
      <div
        className={cn('relative flex-1 rounded-sm', LANE_H, ineligible ? 'bg-disabled' : 'bg-hover')}
        aria-disabled={ineligible || undefined}
        title={ineligible ? `${dock.dock_code}: no feasible interval for this shipment` : undefined}
      >
        {/* One 1px hour tick, and nothing else -- every other gridline decoration is excluded. */}
        {ticks.map((t) => (
          <span
            key={t}
            aria-hidden="true"
            className="absolute inset-y-0 w-px bg-border"
            style={{ left: `${((t - horizonStartMs) / (horizonEndMs - horizonStartMs)) * 100}%` }}
          />
        ))}

        {/* Outage windows render UNDER the bars deliberately. The block-dock form is what stops a
            dock being blocked and booked over the same instant (components.md section 4), so an
            overlap on screen is a data anomaly and the booking is the fact a planner must not lose
            sight of. */}
        {blocks.map((block) => (
          <BlockMarker
            key={block.dock_event_id}
            block={block}
            horizonStartMs={horizonStartMs}
            horizonEndMs={horizonEndMs}
          />
        ))}

        {bars.map((bar) => (
          <Bar
            key={bar.occupancy_id}
            bar={bar}
            dock={dock}
            horizonStartMs={horizonStartMs}
            horizonEndMs={horizonEndMs}
          />
        ))}

        {/* Drawn LAST so a pickable interval sits above the occupancy bars it is offered against --
            the one case on this board where something must be on top of a booking, because it is
            the thing the planner is being asked to click. */}
        {laneOptions.map((option) => (
          <PickableInterval
            key={option.slot_id}
            option={option}
            dock={dock}
            chosen={chosenSlotId === option.slot_id}
            horizonStartMs={horizonStartMs}
            horizonEndMs={horizonEndMs}
            onPick={() => onPickInterval?.(option)}
          />
        ))}
      </div>
    </div>
  )
}

/**
 * One clickable open interval in the counter-offer picker (`screens.md` section 4's
 * *"▒ click here ▒"*).
 *
 * A real `<button>`, so it is keyboard-reachable and gets focus-visible for free -- the same
 * reasoning `Bar` gives for being a button that does nothing. Unlike `Bar`, this one does act, and
 * it is the **only** interactive element the board ever adds. Nothing here is draggable and no
 * range-select exists: U25's rule survives the picker intact, which is exactly why the design
 * specifies "click an open interval" rather than "drag out a window".
 *
 * The accessible name carries dock, dated interval and the differentiator, because a screen-reader
 * user cannot see which lane the button sits in.
 */
function PickableInterval({
  option,
  dock,
  chosen,
  horizonStartMs,
  horizonEndMs,
  onPick,
}: {
  option: FeasibleSlotOption
  dock: BoardDock
  chosen: boolean
  horizonStartMs: number
  horizonEndMs: number
  onPick: () => void
}) {
  const place = placeOnTrack(
    option.slot_start_ts,
    option.slot_end_ts,
    horizonStartMs,
    horizonEndMs,
  )
  // Outside the drawn horizon. Not an error -- the banner counts these and says so.
  if (place === null) return null

  const label = `Offer ${dock.dock_code} · ${formatDate(option.slot_start_ts)} · ${formatTime(
    option.slot_start_ts,
  )}–${formatTime(option.slot_end_ts)}${option.differentiator ? ` · ${option.differentiator}` : ''}`

  return (
    <button
      type="button"
      onClick={onPick}
      aria-pressed={chosen}
      title={label}
      aria-label={label}
      className={cn(
        'absolute inset-y-0.5 flex items-center justify-center overflow-hidden rounded-sm',
        'border-2 border-dashed text-micro font-semibold whitespace-nowrap',
        'focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-1',
        // Deliberately NOT a promise-state token: this is an offer being considered, not a claim
        // on the dock, and reusing a state colour would say the slot is already held. The primary
        // ring is the product's "you may act here" signal everywhere else too.
        chosen
          ? 'border-solid border-primary bg-primary text-primary-foreground'
          : 'border-primary bg-card text-primary hover:bg-hover',
      )}
      style={{ left: `${place.leftPct}%`, width: `${place.widthPct}%` }}
    >
      <span aria-hidden="true" className="truncate px-1">
        {chosen ? '✓ ' : ''}
        {formatTime(option.slot_start_ts)}
      </span>
    </button>
  )
}

function Bar({
  bar,
  dock,
  horizonStartMs,
  horizonEndMs,
}: {
  bar: BoardBar
  dock: BoardDock
  horizonStartMs: number
  horizonEndMs: number
}) {
  const treatment = barTreatment(bar.state)
  const place = placeOnTrack(bar.window_start, bar.window_end, horizonStartMs, horizonEndMs)
  // Two independent reasons to draw nothing, and both are correct answers rather than failures:
  // a terminal state occupies no capacity, and an interval outside the horizon is not on this board.
  if (treatment === null || place === null) return null

  const interval = `${formatDate(bar.window_start)} · ${formatTime(bar.window_start)}–${formatTime(bar.window_end)}`
  const identity = bar.order_reference ?? bar.shipment_id ?? bar.occupancy_id
  // Colour is never the only carrier: the state word is in the tooltip and in the accessible name
  // alongside the identity and the dated interval (`stitch-prompts.md` section 8's legend rule).
  const description = `${treatment.label} · ${identity} · Dock ${dock.dock_code} · ${interval}${
    bar.hold_expires_at ? ` · hold expires ${formatTime(bar.hold_expires_at)}` : ''
  }`

  return (
    <button
      type="button"
      // A real button, so it is keyboard-reachable and gets focus-visible for free. It performs no
      // action on activation by design -- the board is read-and-act-via-affordances, and every
      // action lives in an explicit control elsewhere. `title` carries the same string the
      // accessible name does, so the two cannot drift.
      title={description}
      aria-label={description}
      className={cn(
        'absolute inset-y-0.5 flex items-center gap-1 overflow-hidden rounded-sm px-1',
        'text-micro font-medium whitespace-nowrap',
        'focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-1',
        treatment.className,
      )}
      style={{ left: `${place.leftPct}%`, width: `${place.widthPct}%` }}
    >
      {treatment.icon === 'truck' ? (
        <Truck size={12} strokeWidth={2} aria-hidden="true" className="shrink-0" />
      ) : null}
      <span aria-hidden="true" className="truncate font-mono">
        {identity}
      </span>
    </button>
  )
}

function BlockMarker({
  block,
  horizonStartMs,
  horizonEndMs,
}: {
  block: BoardBlock
  horizonStartMs: number
  horizonEndMs: number
}) {
  const place = placeOnTrack(
    block.event_start_ts,
    block.event_end_ts,
    horizonStartMs,
    horizonEndMs,
  )
  if (place === null) return null

  const reason = block.reason ? `blocked — ${block.reason}` : `blocked — ${block.event_type}`
  const ends = block.event_end_ts
    ? `${formatTime(block.event_start_ts)}–${formatTime(block.event_end_ts)}`
    : `from ${formatTime(block.event_start_ts)}, no end set`
  const description = `${reason} · ${ends}`

  return (
    <span
      // A 45-degree hatch, no elevation, no promise-state colour: an unavailability and a booking
      // are different facts and must never share an encoding. Elevation here would imply something
      // is booked in the window (components.md section 4).
      title={description}
      aria-label={description}
      role="img"
      // `border-subtle-foreground`, NOT `border-border`. Measured in a real render (2026-08-31):
      // the design's own `#CBD5E1` (= `--color-input`) sits at **1.13:1** against this board's
      // `surface-hover` track, far under WCAG 1.4.11's 3:1 for a UI component boundary -- and it is
      // the same 1.36 the E5.3 fix pass already caught and raised to 4.34 for this exact marker
      // (`implementation-spec.md` section 5.2's bar table). `neutral-500` is the value that produces
      // that 4.34, so this uses the corrected token rather than the prompt's original hex. Same
      // token for the hatch stripe, because a hatch nobody can see is not an encoding.
      className="absolute inset-y-0 overflow-hidden rounded-sm border border-subtle-foreground px-1 text-micro text-muted-foreground"
      style={{
        left: `${place.leftPct}%`,
        width: `${place.widthPct}%`,
        backgroundImage:
          'repeating-linear-gradient(45deg, var(--color-subtle-foreground) 0 2px, transparent 2px 6px)',
      }}
    >
      <span aria-hidden="true" className="truncate">
        {reason}
      </span>
    </span>
  )
}

/**
 * One legend row. Each swatch carries its own **border style**, not just its fill -- that is what
 * makes dashed-means-temporary legible in the legend as well as on the bar.
 *
 * The HELD entry is omitted when `holds_enabled` is false: on a deploy where the D2 path is off, no
 * `dock_occupancy` row can be in that state, so a HELD swatch would be a legend entry for something
 * this board can never show. Omitted rather than greyed, per `components.md` section 18.
 */
function Legend({ holdsEnabled, hasBlocks }: { holdsEnabled: boolean; hasBlocks: boolean }) {
  const states = holdsEnabled ? LEGEND_STATES : LEGEND_STATES.filter((s) => s !== 'HELD')
  return (
    <ul
      role="list"
      className={cn(
        'flex flex-wrap items-center gap-4 text-micro text-muted-foreground',
        // Same component-scoped Fork F token as the board, so the legend's HELD swatch and the bar
        // it stands for cannot render different borders.
        '[--dock-bar-held-border:var(--amber-700)]',
        'dark:[--dock-bar-held-border:var(--color-state-held-border)]',
      )}
    >
      {states.map((state) => {
        const treatment = barTreatment(state)
        if (!treatment) return null
        return (
          <li key={state} className="flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className={cn('inline-block size-2 rounded-[2px]', treatment.className)}
            />
            {treatment.label}
          </li>
        )
      })}
      {hasBlocks ? (
        <li className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className="inline-block size-2 rounded-[2px] border border-subtle-foreground"
            style={{
              backgroundImage:
                'repeating-linear-gradient(45deg, var(--color-subtle-foreground) 0 1px, transparent 1px 3px)',
            }}
          />
          Blocked
        </li>
      ) : null}
    </ul>
  )
}
