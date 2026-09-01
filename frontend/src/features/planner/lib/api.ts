import { apiGet, apiPost } from '@/core/http/api'
import { plannerGet, plannerPost } from './http'
import type {
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
