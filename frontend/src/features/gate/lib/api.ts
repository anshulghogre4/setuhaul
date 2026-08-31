import { apiGet, apiPost } from '@/core/http/api'
import type { GateEventResult, GateTruckSearchResult } from './types'

/**
 * Real calls against `backend/app/api/v1/routers/gate.py` (E3.6/#30, closed) -- section 7.5.2's
 * five write tools. All five were re-read off the shipped router and service this pass rather than
 * trusted from `implementation-spec.md` section 0.1, and all five are complete and correct.
 *
 * Every one of these is called for real by `components/truck-action.tsx`. Nothing here is a stub, a
 * mock or a fixture. They are unreachable from `/gate` only because `gateSearchEnabled` is still
 * off -- see `flags.ts`, which records both why it was off when this surface was built and the
 * `GET /api/v1/gate/trucks` route that landed concurrently and is the reason it can now be flipped.
 *
 * **`Idempotency-Key` only on `record_gate_in`.** The catalog names one for exactly this tool and
 * the router 400s (`IDEMPOTENCY_KEY_REQUIRED`) without it (`gate.py:78-83, 96`). The other four are
 * retry-safe by their own state-machine guards instead -- verified individually, not assumed:
 * `update_queue_state` re-targets a state already reached and gets `INVALID_TRANSITION`;
 * `record_dock_in` fails its `current != 'CALLED_TO_DOCK'` guard; `record_unload_start_end` guards
 * on its own already-set timestamp column in both phases; `record_gate_out` hits the explicit
 * `ALREADY_GATED_OUT` branch. No key is invented for them here, since sending one would be
 * silently ignored and would imply a replay guarantee the server does not give
 * (`implementation-spec.md` G3 / Fork G; `components.md` section 4 was corrected 2026-08-29 to say
 * the same thing).
 *
 * Every one of the four non-idempotent tools can also return `INVALID_TRANSITION` in place of its
 * success code -- a 200 envelope, not a rejection -- which is screen 22 and is handled by
 * `outcome-screen.tsx`, not by an error path.
 *
 * ## `officerName` -- U111's shift label, now actually transmitted (issue #68)
 *
 * Every write takes it, because `components.md` section 1 says every event this session writes
 * carries the officer's identity "as an attribute of the write". Until 2026-08-31 it carried
 * nothing: the name was captured at shift start, rendered in the shift bar, and sent nowhere.
 *
 * Three properties of how it travels, each deliberate:
 *
 *   **It is a body field, not a header.** A header would put it beside `Authorization` and
 *   `Idempotency-Key`, where a later reader could take it for part of the request's identity or its
 *   replay key. It is neither -- it is an unverified label being recorded. (It also could not have
 *   been a header without editing `core/http/api.ts`, whose `apiPost` exposes only
 *   `idempotencyKey`; but the body is the right answer independently of that.)
 *
 *   **The parameter is required and nullable, not optional.** `string | null`, never omitted -- so
 *   TypeScript makes every call site state what it knows, and "no shift is active" is an explicit
 *   `null` rather than a forgotten argument that looks identical.
 *
 *   **`null` is a legitimate value and the server records it as one.** A kiosk mid-shift-change
 *   still writes the event, attributed to nobody. The server never substitutes the device account's
 *   name as a stand-in -- see `gate_yard_service.OFFICER_ATTRIBUTION_KEY`.
 *
 * The server normalises (trim, collapse whitespace, sanitise control characters, truncate) and
 * echoes the stored value back on `GateEventResult.officer_name`. It never *rejects* over the
 * label: a bad name would otherwise fail every write of the whole shift, not one.
 */

/**
 * Flow 1's search -- `GET /api/v1/gate/trucks` (`gate.py::search_trucks`, issue #67 / GY-G1).
 *
 * Written against the **real shipped route**, not against a guess. An earlier draft of this file
 * targeted `/api/v1/gate/search?q=` with a `{ matches }` body, invented before the endpoint existed;
 * that was wrong on the path, the parameter name and the response shape, and is exactly the reason
 * this was re-checked against source rather than left as designed.
 *
 * **No facility argument, and that is the point (M15/NFR-019).** The device's facility is fixed
 * (`screens.md` section 1) and is already on the caller's verified identity -- the service derives it
 * through `resolve_facility_scope` and never reads one from the request. A `facility_id` query
 * parameter here would be exactly the client-supplied-scope shape M15 exists to forbid, on the one
 * surface where the client is a shared device sitting in a yard.
 *
 * **This is also the refresh endpoint.** `edge-cases.md` #3 requires the kiosk to re-fetch a truck's
 * current state after an `INVALID_TRANSITION` rather than retry the rejected transition; re-searching
 * that shipment id returns exactly that one truck, which is why no separate per-shipment route
 * exists and why nothing here needs one.
 *
 * `QUERY_TOO_SHORT` (422) is a real rejection for a query under two characters, so it arrives as a
 * throw rather than a `NO_MATCH` body -- the caller guards on length before calling.
 */
export async function searchTrucks(query: string): Promise<GateTruckSearchResult> {
  const res = await apiGet<GateTruckSearchResult>(
    `/api/v1/gate/trucks?query=${encodeURIComponent(query)}`,
  )
  return res.data
}

/** `gate_yard_reads.MIN_QUERY_LENGTH`, mirrored so the kiosk can avoid a round trip that can only
 *  return 422. Kept next to the call it guards rather than in a constants file, because it is only
 *  correct as long as it matches that module. */
export const MIN_QUERY_LENGTH = 2

export async function recordGateIn(
  shipmentId: string,
  idempotencyKey: string,
  officerName: string | null,
): Promise<GateEventResult> {
  const res = await apiPost<GateEventResult>(
    `/api/v1/gate/shipments/${encodeURIComponent(shipmentId)}/gate-in`,
    { officer_name: officerName },
    { idempotencyKey },
  )
  return res.data
}

/** Flow 4. "Call to dock" is this tool targeting `CALLED_TO_DOCK`, not an action of its own
 *  (`flows-and-states.md` Flow 4). `queue_position` is omitted: nothing on this surface assigns
 *  one, and `screens.md` section 3 never shows a position. */
export async function updateQueueState(
  shipmentId: string,
  queueState: string,
  officerName: string | null,
): Promise<GateEventResult> {
  const res = await apiPost<GateEventResult>(
    `/api/v1/gate/shipments/${encodeURIComponent(shipmentId)}/queue-state`,
    { queue_state: queueState, queue_position: null, officer_name: officerName },
  )
  return res.data
}

/** Flow 5. `dockId` is the **appointment's** dock, read off the identity card -- the officer never
 *  picks one (`screens.md` section 3: "No dock selector"). See `truck-action.tsx` for the real
 *  consequence of that rule against this tool's actual mismatch check. */
export async function recordDockIn(
  shipmentId: string,
  dockId: string,
  officerName: string | null,
): Promise<GateEventResult> {
  const res = await apiPost<GateEventResult>(
    `/api/v1/gate/shipments/${encodeURIComponent(shipmentId)}/dock-in`,
    { dock_id: dockId, officer_name: officerName },
  )
  return res.data
}

/** Flow 6. `END` additionally returns the signed `overrun_min` against `expected_unload_min`.
 *
 *  START and END are separately attributed on purpose -- an unload can straddle a shift change, so
 *  each phase records whoever was actually on shift for it rather than copying one onto the other. */
export async function recordUnloadStartEnd(
  shipmentId: string,
  phase: 'START' | 'END',
  officerName: string | null,
): Promise<GateEventResult> {
  const res = await apiPost<GateEventResult>(
    `/api/v1/gate/shipments/${encodeURIComponent(shipmentId)}/unload`,
    { phase, officer_name: officerName },
  )
  return res.data
}

/** Flow 7. Terminal for a truck. Returns `COMPLETED` + `dwell_min`, or `ALREADY_GATED_OUT`. */
export async function recordGateOut(
  shipmentId: string,
  officerName: string | null,
): Promise<GateEventResult> {
  const res = await apiPost<GateEventResult>(
    `/api/v1/gate/shipments/${encodeURIComponent(shipmentId)}/gate-out`,
    { officer_name: officerName },
  )
  return res.data
}
