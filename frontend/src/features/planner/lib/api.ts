import { apiGet, apiPost, isApiError } from '@/core/http/api'
import { plannerGet, plannerPost, plannerPostNoKey } from './http'
import type {
  ApplyProposalResult,
  AppointmentTransitionResult,
  BulkConfirmResult,
  CounterOfferResult,
  Dock,
  DockBlockImpact,
  DockBlockResult,
  DockBoard,
  FeasibleSlotsResult,
  HoldForInformationResult,
  PlannerQueue,
  SchedulingRun,
  SchedulingRunList,
  SchedulingRunSummary,
} from './types'
import type { RejectReasonCode } from './reasons'

/**
 * Real calls against the endpoints M3/E3.6 shipped (`backend/app/api/v1/routers/planner.py`) plus
 * the one existing ops-portal read the block-dock form's dock select borrows
 * (`backend/app/api/v1/routers/operations.py::dock_snapshot` -- `WAREHOUSE_PLANNER` is inside
 * `OPS_PORTAL_ROLES`, `core/deps.py:83-91`). No fixture data here -- this file is the one used by
 * the live `/planner` route; `gallery/fixtures.ts` is the separate, explicitly-fixture-only file
 * for `/planner/_states`.
 *
 * Every mutation the backend requires an `Idempotency-Key` for (`planner.py:40-46`,
 * `scheduling.py:330/377/412/439`, U70) gets one, the same mechanism `features/ops/lib/api.ts`
 * already uses. `end_dock_block` takes none -- `planner.py:141`'s own comment states the catalog
 * names none for it, and this file does not invent one.
 *
 * ## Two call styles in one file, on purpose
 *
 * The block-dock group keeps `core/http/api.ts`'s `apiGet`/`apiPost`: its one refusal
 * (`ALREADY_BLOCKED`) arrives as a **200 with a `code` field in the body**, not as an error, so
 * nothing is lost by a wrapper that flattens errors to a string. The six queue endpoints use
 * `lib/http.ts` instead, because their refusals arrive as 409/422 *errors* whose `code` and JSON
 * `detail` are the entire contract -- see that file's header for the full reasoning. Mixing the
 * two is deliberate rather than drift, and this paragraph is why.
 *
 * ## The snapshot rule, stated once and enforced by every signature below
 *
 * `snapshotHash` is always a **required, opaque, caller-supplied string**. It is never optional,
 * never defaulted, and never computed here. The queue read produces it (`planner_service.
 * _snapshot_hash`); confirm / counter-offer / bulk-confirm consume it under the row lock
 * (`allocation._snapshot_guard`). The only correct value is exactly what the row handed us --
 * a recomputed one would either be a lie about what the planner saw or an accidental match that
 * defeats the guard. `lib/batch-hash.ts` composes the *batch* token from those per-row tokens,
 * which is the one composition `snapshot.py::batch_snapshot_hash` explicitly designs for.
 */

export async function fetchDocksForFacility(facilityId: string): Promise<Dock[]> {
  const res = await apiGet<{ docks: Dock[] }>(
    `/api/v1/operations/dock-snapshot?facility_id=${encodeURIComponent(facilityId)}`,
  )
  return res.data.docks
}

/**
 * `GET /api/v1/planner/board` -- the Board tab's at-rest occupancy view.
 *
 * Same scope contract as `fetchPlannerQueue`: `facilityId` is a **narrowing request, never an
 * assertion** (M15/NFR-019), resolved server-side through `resolve_facility_scope`. It is sent for
 * the same reason -- an `ADMIN` holds global read scope and the route runs `require_facility=True`.
 *
 * No horizon argument is sent. The axis is *"four hours, or until closing time, whichever comes
 * sooner"* (`screens.md` section 3), and both bounds are server facts: the four hours is the
 * design's number and the close time needs the facility's own timezone. The response reports which
 * of the two applied, so the caption states the reason rather than the client guessing it.
 */
export function fetchDockBoard(facilityId?: string | null): Promise<DockBoard> {
  const params = new URLSearchParams()
  if (facilityId) params.set('facility_id', facilityId)
  const qs = params.toString()
  return plannerGet<DockBoard>(`/api/v1/planner/board${qs ? `?${qs}` : ''}`)
}

export async function fetchDockBlockImpact(
  dockId: string,
  windowStart: string,
  windowEnd: string,
): Promise<DockBlockImpact> {
  const params = new URLSearchParams({ window_start: windowStart, window_end: windowEnd })
  const res = await apiGet<DockBlockImpact>(
    `/api/v1/planner/docks/${encodeURIComponent(dockId)}/block-impact?${params.toString()}`,
  )
  return res.data
}

export async function blockDock(
  dockId: string,
  payload: { window_start: string; window_end: string; reason: string },
): Promise<DockBlockResult> {
  const res = await apiPost<DockBlockResult>(
    `/api/v1/planner/docks/${encodeURIComponent(dockId)}/block`,
    payload,
    { idempotencyKey: crypto.randomUUID() },
  )
  return res.data
}

export async function endDockBlock(dockStatusEventId: string): Promise<DockBlockResult> {
  const res = await apiPost<DockBlockResult>(
    `/api/v1/planner/dock-status-events/${encodeURIComponent(dockStatusEventId)}/end`,
    {},
  )
  return res.data
}

/* ==============================================================================================
 * The queue and its four write paths (issues #60, #61/#62, #63, #65, #66)
 * ============================================================================================ */

/**
 * `GET /api/v1/planner/queue` -- section 7.5.1 `get_planner_queue`, FR-PLN-010.
 *
 * `facilityId` is sent as a **narrowing request, never an assertion of scope** (M15/NFR-019). The
 * server runs it through `repositories.scope.resolve_facility_scope`, which lets a global-read
 * persona narrow and lets everyone else pass only their own facility -- a mismatch is a
 * server-side 403 `FORBIDDEN` (`scope.py:56-58`), not something this client can talk its way
 * past. It is sent at all because an `ADMIN` holds global read scope and the route runs with
 * `require_facility=True`, so a facility has to be named by someone; for a `WAREHOUSE_PLANNER` it
 * is redundant with the identity and the server ignores the difference.
 *
 * `horizonHours` is omitted rather than defaulted: the server treats absence as "no horizon
 * bound", and inventing a window here would silently hide pending requests a planner is
 * accountable for.
 */
export function fetchPlannerQueue(facilityId?: string | null): Promise<PlannerQueue> {
  const params = new URLSearchParams()
  if (facilityId) params.set('facility_id', facilityId)
  const qs = params.toString()
  return plannerGet<PlannerQueue>(`/api/v1/planner/queue${qs ? `?${qs}` : ''}`)
}

/**
 * `confirm_request` -- section 7.5.1, FR-PLN-001. Refuses with `ALREADY_ACTIONED` ->
 * `DISPLACEMENT_DETECTED` -> `SNAPSHOT_STALE`, in that order, all inside the row lock.
 *
 * `warehouse_confirmation_ref` is deliberately **not sent**. Issue #62 made it optional precisely
 * because the planner console has no source for one -- it is a WMS reference, an
 * inbound-integration field, and it appears in none of the 30 artboards. Omitting it leaves the
 * stored value untouched (`COALESCE(:ref, warehouse_confirmation_ref)`); sending a synthesised
 * one would stamp a fake warehouse acknowledgement onto the row.
 */
export function confirmRequest(args: {
  shipmentId: string
  appointmentId: string
  snapshotHash: string
  idempotencyKey: string
  note?: string | null
}): Promise<AppointmentTransitionResult> {
  return plannerPost<AppointmentTransitionResult>(
    `/api/v1/shipments/${encodeURIComponent(args.shipmentId)}/appointments/${encodeURIComponent(args.appointmentId)}/confirm`,
    { snapshot_hash: args.snapshotHash, note: args.note ?? null },
    args.idempotencyKey,
  )
}

/**
 * `reject_request` -- section 7.5.1, FR-PLN-003. Issue #66.
 *
 * The wire field is `reason_code`, **not** `rejection_reason`, and its value must be one of
 * `lib/reasons.ts`'s five. The body model is `extra="forbid"`, so the old name is not merely
 * ignored -- it is a 422. `note` is the planner's internal annotation and never reaches the
 * driver-facing column.
 *
 * Takes no `snapshot_hash`: section 7.5.1 does not give `reject_request` one, and neither does
 * the shipped command. It still races the D9 sweeper, which is why `ALREADY_ACTIONED` applies
 * here too.
 */
export function rejectRequest(args: {
  shipmentId: string
  appointmentId: string
  reasonCode: RejectReasonCode
  idempotencyKey: string
  note?: string | null
}): Promise<AppointmentTransitionResult> {
  return plannerPost<AppointmentTransitionResult>(
    `/api/v1/shipments/${encodeURIComponent(args.shipmentId)}/appointments/${encodeURIComponent(args.appointmentId)}/reject`,
    { reason_code: args.reasonCode, note: args.note ?? null },
    args.idempotencyKey,
  )
}

/**
 * `GET /shipments/{id}/slots/feasible` -- Stage 1, the same engine the driver's own option set
 * comes from.
 *
 * Borrowed by the counter-offer picker, and the borrowing is the honest part: section 7.5.1 gives
 * `counter_offer` a `(dock_id, start_ts)` pair because the Board tab's Gantt hands the planner a
 * point on a dock/time grid. That board is blocked on `dock_occupancy.state` (issue #53,
 * unapplied), so there is no grid to click. Rather than ask a planner to *type* a timestamp that
 * has to match an `appointment_slots` row exactly -- which would turn `INTERVAL_UNAVAILABLE` from
 * a rare race into the normal outcome -- the picker offers the intervals Stage 1 says are
 * genuinely feasible for **this shipment**, which is the same eligibility the board's
 * dimmed/undimmed lanes were going to express spatially.
 *
 * Reachable by a planner: the route takes any authenticated identity and
 * `feasibility._assert_scope` applies the read tier of `assert_shipment_visible`, so an operator
 * sees shipments in their own facility. Verified against the source, not assumed.
 */
export function fetchFeasibleSlots(shipmentId: string, limit = 10): Promise<FeasibleSlotsResult> {
  return plannerGet<FeasibleSlotsResult>(
    `/api/v1/shipments/${encodeURIComponent(shipmentId)}/slots/feasible?limit=${limit}`,
  )
}

/**
 * `counter_offer` -- section 7.5.1, FR-PLN-002. Issue #63.
 *
 * `(dock_id, start_ts)` rather than a `slot_id`, because that is the catalog's own argument shape.
 * The server resolves the pair to a real `appointment_slots` row and runs full Stage-1
 * revalidation through `explain_slot_eligibility` before reserving; an interval with no slot
 * behind it comes back as `INTERVAL_UNAVAILABLE` rather than an invented slot. The offered
 * interval is genuinely **reserved**, not merely shown -- see `counter_offer`'s own docstring on
 * why a shown-but-unreserved offer would be a mis-promise.
 */
export function counterOffer(args: {
  shipmentId: string
  appointmentId: string
  dockId: string
  startTs: string
  reasonCode: RejectReasonCode
  snapshotHash: string
  idempotencyKey: string
  note?: string | null
}): Promise<CounterOfferResult> {
  return plannerPost<CounterOfferResult>(
    `/api/v1/shipments/${encodeURIComponent(args.shipmentId)}/appointments/${encodeURIComponent(args.appointmentId)}/counter-offer`,
    {
      dock_id: args.dockId,
      start_ts: args.startTs,
      reason_code: args.reasonCode,
      snapshot_hash: args.snapshotHash,
      note: args.note ?? null,
    },
    args.idempotencyKey,
  )
}

/**
 * `hold_for_information` -- section 7.5.1, FR-PLN-004. Issue #64.
 *
 * **One argument, and the two that are absent are the contract.** The body carries `question` and
 * nothing else: no `snapshot_hash` (this consumes no capacity, so section 7.5's principle-3 guard
 * does not attach) and **no duration** -- a client cannot choose how much time the hold buys, which
 * is what stops it becoming the unbounded sit-on-capacity the catalog's own one-shot cap exists to
 * prevent. The extension is D9's own TTL, resolved server-side.
 *
 * One-shot by construction: a second call on the same appointment answers 409 `HOLD_ALREADY_USED`.
 * The UI's job is to make that 409 unreachable (`edge-cases.md` #6 -- prevention, not error
 * handling) by disabling the affordance off `ttl.hold_used`; the refusal is still classified and
 * rendered, because "unreachable" is a claim about this client and not about the other planner who
 * held the same row a second ago.
 */
export function holdForInformation(args: {
  shipmentId: string
  appointmentId: string
  question: string
  idempotencyKey: string
}): Promise<HoldForInformationResult> {
  return plannerPost<HoldForInformationResult>(
    `/api/v1/shipments/${encodeURIComponent(args.shipmentId)}/appointments/${encodeURIComponent(args.appointmentId)}/hold-for-information`,
    { question: args.question },
    args.idempotencyKey,
  )
}

/**
 * `bulk_confirm` -- section 7.5.1, FR-PLN-006. Issue #65.
 *
 * **Always resolves, never rejects, on a normal outcome.** The route returns 200 with a per-id
 * outcome list even when most ids were skipped: Flow 6 step 4 requires the skipped rows to be
 * *named* rather than the call to fail, and a batch where 5 of 6 were written is not an error.
 * The caller must render `outcomes`, not `code`.
 *
 * Not shipment-scoped, unlike every other write here -- a spike-clearing batch crosses shipments
 * by construction, and each id's facility scope is validated server-side per id from the verified
 * identity. There is no facility argument in this body for a client to supply (M15).
 */
export function bulkConfirm(args: {
  appointmentIds: string[]
  snapshotHash: string
  idempotencyKey: string
  note?: string | null
}): Promise<BulkConfirmResult> {
  return plannerPost<BulkConfirmResult>(
    '/api/v1/appointments/bulk-confirm',
    {
      appointment_ids: args.appointmentIds,
      snapshot_hash: args.snapshotHash,
      note: args.note ?? null,
    },
    args.idempotencyKey,
  )
}

/** `MAX_BULK_CONFIRM_IDS` -- `allocation.py:104`. A spike is 20-35 requests, so a cap a little
 *  above that refuses an obviously-wrong call without ever refusing a real one. Mirrored here so
 *  the UI can stop before the server has to. */
export const MAX_BULK_CONFIRM_IDS = 50

/* ==============================================================================================
 * The Sequencer -- SS7.5.3's three tools (issue #49, FR-PLN-009, FR-SYS-016)
 *
 * PATHS RECONCILED 2026-09-02 against `backend/app/api/v1/routers/scheduling.py` as landed. SS7.5.3
 * is a TOOL catalog, not a REST spec -- it names arguments and returns, never URLs -- so the routes
 * below are the backend's choice and this client was corrected to them, not the other way round.
 * The one path this client guessed correctly is the ops delegate, because SS7.5.5 pins it to the
 * escalation it is called on.
 * ============================================================================================ */

/**
 * `propose_facility_schedule` -- SS7.5.3. Flow 9's **self-triggered** origin.
 *
 * `POST /api/v1/scheduling/proposals`.
 *
 * ## Three arguments this client deliberately does not send, each for a different reason
 *
 * **`trigger_reason`** -- the route pins it to `PLANNER_REQUESTED` server-side and takes no such
 * body field. That is the correct division and it matches what this client wanted anyway: the other
 * admissible value, `CAPACITY_INCIDENT`, belongs to SS7.5.5's ops delegate and is set there from the
 * escalation it was called on. A planner client able to choose it could stamp an incident origin
 * onto a run no incident produced, which is exactly the linkage SS7.5.5 exists to keep honest.
 *
 * **`horizon_end`** -- the body accepts it; this client omits it. SS5.1 fixes the run scope at
 * *"4 hours or to `close_time`, whichever is sooner"*, and both bounds need the facility's own
 * timezone and closing time. Same reasoning `fetchDockBoard` gives for sending no horizon: a browser
 * deriving them from a local clock is the wrong-day hazard this product designs against. The
 * response reports which bound applied (`horizon.end_reason`).
 *
 * **`Idempotency-Key`** -- the route takes none, deliberately, and its docstring gives a better
 * reason than this client's original one: SS7.5 principle 3 attaches keys to calls that *consume
 * capacity*, and a proposal writes no `dock_occupancy` row, no appointment and no notification
 * (D5: *"Sequencer output is a reviewable artifact, never a silent write"*). The protection is
 * already given, and given better, by the partial unique index behind `RUN_ALREADY_ACTIVE` -- a
 * double-submit produces **one** run and a named refusal naming it, rather than two runs sharing a
 * key. The key was removed from this signature rather than sent and ignored.
 *
 * `facilityId` goes in the **body** (not a query string, which is what this client first guessed)
 * and remains a **narrowing request, never an assertion** (M15/NFR-019), identical to
 * `fetchPlannerQueue`/`fetchDockBoard`: it is sent because an `ADMIN` holds global read scope and
 * something has to name a facility, and a mismatch is a server-side 403.
 *
 * ## `RUN_ALREADY_ACTIVE` arrives as a 200, not an error
 *
 * The route returns *"200 with a typed body in both outcomes, matching `bulk_confirm`'s posture
 * rather than `request_slot`'s 409: `RUN_ALREADY_ACTIVE` is not an error, it is section 5.1's
 * debounce working, and the response carries the incumbent run the planner should look at
 * instead."* So there is no catch block here at all -- the caller branches on `code`, and
 * `active_run` names the incumbent.
 */
export function proposeFacilitySchedule(args: {
  facilityId?: string | null
}): Promise<SchedulingRun> {
  return plannerPostNoKey<SchedulingRun>('/api/v1/scheduling/proposals', {
    facility_id: args.facilityId ?? null,
  })
}

/**
 * `get_scheduling_run` -- SS7.5.3: *"the stored run: input snapshot, proposal, objective values,
 * explanation -- replayable a month later, which is what makes SS8's 'how the business can trust
 * the allocation' answerable."*
 *
 * `GET /api/v1/scheduling/runs/{scheduling_run_id}`.
 *
 * A plain read with no snapshot argument: reading a run never revalidates it. The staleness check
 * belongs to apply, and doing it here would make merely *opening* the overlay refuse a proposal the
 * planner has not yet decided about.
 *
 * **Returns the same `SchedulingRunResult` model `propose` does**, which is the backend's own
 * deliberate choice: *"a planner reviewing a proposal an hour after it was computed must see the
 * identical object the requester saw, or the review is of something else."*
 */
export function fetchSchedulingRun(schedulingRunId: string): Promise<SchedulingRun> {
  return plannerGet<SchedulingRun>(
    `/api/v1/scheduling/runs/${encodeURIComponent(schedulingRunId)}`,
  )
}

/**
 * The pending-run list behind `[ Review proposal (N) ]` (`screens.md` section 3).
 *
 * `GET /api/v1/scheduling/runs?facility_id=&status=PROPOSED&limit=`.
 *
 * ## The gap this function used to report is CLOSED (2026-09-02)
 *
 * It previously returned `null` for "this backend cannot answer", because SS7.5.3 defines propose /
 * apply / get-by-id and **no list**, while `screens.md` section 3 requires a count on the Board
 * toolbar and Flow 9 requires the button to go live for an **ops-handoff** run this surface never
 * observes. The endpoint now exists and names itself honestly as *"an addition to section 7.5.3's
 * catalog, not an implementation of it"*, citing both callers -- the same discipline
 * `planner.py::dock_block_impact` states for itself. The `null` degrade is therefore gone: an
 * unknown count was only ever the right answer while the server genuinely could not answer.
 *
 * ## Two properties worth keeping straight
 *
 * `facility_id` is a **narrowing request, never a scope assertion** (M15) -- it runs through
 * `resolve_facility_scope_with_user_scopes`. Unlike `/scheduling/proposals` no facility is
 * *required*, deliberately: *"is any facility waiting on a planner"* is a legitimate question for a
 * global-read tier, and this is a read.
 *
 * The response carries **summaries**, not whole runs (`runs`, not `items` -- checked against the
 * model rather than assumed): enough for a count and an id, so opening one still fetches the full
 * run by id. An unknown `status` is a 422 rather than a silently empty list, which is why nothing
 * here coerces the filter.
 */
export async function listPendingSchedulingRuns(
  facilityId?: string | null,
): Promise<SchedulingRunSummary[]> {
  const params = new URLSearchParams({ status: 'PROPOSED' })
  if (facilityId) params.set('facility_id', facilityId)
  const res = await plannerGet<SchedulingRunList>(`/api/v1/scheduling/runs?${params.toString()}`)
  return res.runs ?? []
}

/**
 * `apply_schedule_proposal` -- SS7.5.3, and the most constrained call on this surface.
 *
 * `POST /api/v1/scheduling/runs/{scheduling_run_id}/apply`.
 *
 * ## Three arguments, and the absent fourth is the contract
 *
 * `scheduling_run_id` (path), `snapshot_hash` (body), `Idempotency-Key` (header, **required** -- the
 * route 400s `IDEMPOTENCY_KEY_REQUIRED` without one, because this is the sequencer call that does
 * consume capacity). **There is deliberately no "apply these rows" argument** -- SS7.5.3 states it
 * outright, SS5.1 gives the reason (*"cherry-picking produces a schedule nobody validated"*), and
 * `components.md` section 7 turns it into a UI rule (*"the UI does not offer a control the tool
 * doesn't support"*). The backend enforces it too: `ApplyScheduleBody` is `extra="forbid"` with
 * `snapshot_hash` as its only field. This signature is where that rule lives on the client side --
 * there is no parameter a future checkbox could be wired into.
 *
 * `snapshotHash` is the value the **run** handed us, round-tripped verbatim and never recomputed --
 * the same discipline every other write on this surface follows (see this file's header).
 *
 * ## Five outcomes across two transports, all normalised to one result
 *
 * 200 carries `APPLIED`, `ALREADY_APPLIED` and `RUN_NOT_ACTIVE` -- none of which is a failure, so
 * they arrive as ordinary results. 409 carries `SNAPSHOT_DRIFT` and `PARTIALLY_INFEASIBLE`, the two
 * refusals Flow 9 steps 4-5 give distinct screens; they are folded back into a result here so the
 * overlay branches on one `code` rather than on a status.
 *
 * ## The 409 payload gap is CLOSED (2026-09-02), and the fix landed where it belonged
 *
 * This client previously reported that the route put the typed `ApplyResult` in the envelope's
 * `data` while `core/http/errors.ts` builds `ApiError` from `errors[0]` only -- so `infeasible[]`
 * and `drift`, the recovery data Flow 9 renders from, never reached the client. The route now
 * `json.dumps`-es the whole `ApplyResult` into `errors[0].detail`, which is exactly what
 * `allocation.py`'s own `_snapshot_stale_error` / `_displacement_error` /
 * `_interval_unavailable_error` already did and precisely why `ApiError.data` exists. So the
 * parsed document below is the real payload, not a reconstruction -- **fixed on the backend in one
 * line rather than worked around per-surface, and without touching a shared error type every
 * surface depends on.**
 */
export async function applyScheduleProposal(args: {
  schedulingRunId: string
  snapshotHash: string
  idempotencyKey: string
}): Promise<ApplyProposalResult> {
  const path = `/api/v1/scheduling/runs/${encodeURIComponent(args.schedulingRunId)}/apply`
  try {
    return await plannerPost<ApplyProposalResult>(
      path,
      { snapshot_hash: args.snapshotHash },
      args.idempotencyKey,
    )
  } catch (error) {
    if (
      isApiError(error) &&
      (error.code === 'SNAPSHOT_DRIFT' || error.code === 'PARTIALLY_INFEASIBLE')
    ) {
      // `error.data` IS the server's own `ApplyResult`, parsed from the JSON document it put in
      // `detail`. Spread rather than field-picked, so a term the server adds later reaches the
      // overlay instead of being silently dropped by a hand-written mapping.
      const doc = (error.data ?? {}) as Partial<ApplyProposalResult>
      return {
        as_of: doc.as_of ?? new Date().toISOString(),
        scheduling_run_id: args.schedulingRunId,
        status: 'PROPOSED',
        notification_batch_id: null,
        notifications_enqueued: 0,
        moved: 0,
        newly_placed: 0,
        unchanged: 0,
        drift: null,
        infeasible: [],
        idempotency_key: args.idempotencyKey,
        idempotent_replay: false,
        ...doc,
        // Last word to the envelope's own code: `detail` and `errors[0].code` cannot be allowed to
        // disagree about which refusal this is, and the code is what the overlay switches on.
        code: error.code,
      }
    }
    throw error
  }
}
