import { apiGet, apiPost } from '@/core/http/api'

/**
 * The planner surface's two call adapters.
 *
 * ## This file used to hold its own fetch and its own `PlannerApiError`. It no longer does
 * ## (2026-08-31).
 *
 * The reason it did was real, and is now served centrally instead: `apiGet`/`apiPost` threw
 * `new Error(detail)` and **discarded the envelope's `errors[0].code`**, while this surface's
 * entire confirm path is a refusal taxonomy keyed on that code -- `ALREADY_ACTIONED` /
 * `SNAPSHOT_STALE` / `DISPLACEMENT_DETECTED` / `INTERVAL_UNAVAILABLE` / `INVALID_REASON_CODE` --
 * and `flows-and-states.md` Flow 1 gives each of the first three a *different* treatment and a
 * different announcement politeness. Worse, three of those five put a **JSON document** in
 * `detail` (`allocation.py::_snapshot_stale_error`, `_displacement_error`,
 * `_interval_unavailable_error` all `json.dumps(...)` into it), so flattening the envelope to one
 * string threw away `current_snapshot_hash` and the named conflict set -- the recovery data the
 * server deliberately sent.
 *
 * `core/http/errors.ts::ApiError` now carries `code`, the raw `detail`, the parsed document as
 * `data`, the envelope's own sentence as `envelopeMessage`, and the status. `lib/refusals.ts`
 * reads all of those. Nothing is lost by this file no longer having a fetch of its own.
 *
 * ## Why these two wrappers still exist rather than calling `apiGet`/`apiPost` inline
 *
 * They are not a duplicate transport -- they are a *signature*. `plannerPost` takes
 * `idempotencyKey` as a **required positional argument**, which is the discipline the six call
 * sites in `lib/api.ts` are written against, and they unwrap `.data` so those call sites read as
 * the tool's own return shape rather than as an envelope. Making the key optional here would let a
 * mutation the backend 400s without one (`scheduling.py:330, 377, 412, 439`) compile silently.
 */

export async function plannerGet<T>(path: string): Promise<T> {
  const res = await apiGet<T>(path)
  return res.data
}

/**
 * Every planner mutation the backend gates on `Idempotency-Key` gets one, generated per press with
 * `crypto.randomUUID()` -- U70, and enforced server-side with a 400 `IDEMPOTENCY_KEY_REQUIRED` on
 * all four routes.
 *
 * The key is an argument rather than generated in here on purpose: a retry of the *same* press must
 * reuse the *same* key (that is the whole point of the header), so the caller -- which knows
 * whether this is a retry or a new decision -- has to own it.
 */
export async function plannerPost<T>(
  path: string,
  payload: unknown,
  idempotencyKey: string,
): Promise<T> {
  const res = await apiPost<T>(path, payload, { idempotencyKey })
  return res.data
}

/**
 * A planner mutation the backend deliberately does NOT key.
 *
 * Exists so that "no key" is a **stated** decision at the call site rather than an omission that
 * looks like a mistake -- `plannerPost`'s required positional key is the discipline this surface is
 * written to, and quietly passing an unused string to satisfy it would hide the real contract.
 *
 * Only one caller today: `propose_facility_schedule` (`POST /scheduling/proposals`). Its route
 * docstring gives the reasoning, and it is stronger than a key would be: SS7.5 principle 3 attaches
 * idempotency to calls that *consume capacity*, and a proposal writes no `dock_occupancy` row, no
 * appointment and no notification (D5 -- *"Sequencer output is a reviewable artifact, never a silent
 * write"*). The double-submit protection comes instead from `scheduling_runs`' partial unique index
 * on `(facility_id) WHERE status = 'PROPOSED'`, which turns a second press into **one** run plus a
 * named `RUN_ALREADY_ACTIVE` refusal -- a stronger guarantee than two runs sharing a key.
 *
 * Do not reach for this to skip a key on a write that does consume capacity; `apply` keeps
 * `plannerPost` for exactly that reason and the backend 400s without the header.
 */
export async function plannerPostNoKey<T>(path: string, payload: unknown): Promise<T> {
  const res = await apiPost<T>(path, payload)
  return res.data
}
