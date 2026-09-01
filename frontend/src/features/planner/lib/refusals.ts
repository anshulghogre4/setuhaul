import { isApiError } from '@/core/http/api'
import type { QueueConflict } from './types'

/**
 * The refusal taxonomy, parsed once.
 *
 * `flows-and-states.md` Flow 1 steps 4-6 and `edge-cases.md` #1-#3 give three of these three
 * *different* treatments, three different volumes and two different announcement politeness
 * levels. That only works if the client can tell them apart structurally, which is what
 * `ApiError.code` (`core/http/errors.ts`) is for and what this module turns into something a
 * component can switch on without ever parsing an English sentence.
 *
 * **Every `message` below is the envelope's own `message`, never `detail`** -- `err.envelopeMessage`
 * rather than `err.message`. That distinction is load-bearing here and not stylistic: for the three
 * JSON refusals `detail` is a machine document, and for `INVALID_REASON_CODE` it is the
 * `"Supported: ..."` fragment, neither of which is the sentence a planner should read.
 *
 * **Nothing here recomputes a server fact.** `SNAPSHOT_STALE` carries `current_snapshot_hash` in
 * its own body (`snapshot.py::describe_snapshot_drift`), so recovery is a re-read of what the
 * server already sent, not a second round trip and never a locally-derived hash.
 *
 * **`DISPLACEMENT_DETECTED` used to be a superset of what the row displayed. Issue #88 closed
 * that** (2026-09-02). The write path counts `snapshot.py::displacement_conflicts`
 * (`conflicts + dock_blocks`); the queue row's `displacement` column used to come from
 * `planner_service._conflicts_for`, the overlapping-claim half only, so a planner could be refused
 * for a dock taken offline under them since render -- a reason their screen never showed. The row
 * now carries **both** legs, each tagged with a `conflict_type` (`INTERVAL_CONFLICT` |
 * `DOCK_BLOCKED`), so the two paths count the same set.
 *
 * The guarantee this file provides is unchanged and is now the *only* thing standing between the
 * two: the refusal renders **whatever the server actually returned**, never the row's idea of the
 * conflict set. That still matters, because a row rendered a minute ago is stale by definition --
 * what is gone is the structural asymmetry, not the race. `conflicts` here is the same
 * discriminated union the row uses (`lib/types.ts`), so a `DOCK_BLOCKED` entry cannot be read as a
 * displaced shipment on this path either. See `components/queue-row.tsx`'s refusal block.
 */

export type SnapshotStaleDrift = {
  reason_code: string
  algorithm: string
  expected_snapshot_hash: string
  current_snapshot_hash: string
  current: {
    appointment_status: string
    is_current: number | null
    dock_id: string
    interval_start: string
    interval_end: string
    interval_source: string
    conflict_appointment_ids: string[]
  }
}

export type PlannerRefusal =
  /** The nastiest race (section 9.2 #3): the sweeper or another planner got there first. The
   *  winning transition is named in `message`, which is why that field is carried, not dropped. */
  | { kind: 'ALREADY_ACTIONED'; message: string }
  /** No conflict -- the row is simply older than the server. Quiet treatment, no auto-retry.
   *  `currentSnapshotHash` lets the row recover without a second call. */
  | { kind: 'SNAPSHOT_STALE'; message: string; drift: SnapshotStaleDrift | null }
  /** A real conflict appeared. Refuses outright and names the harm; never truncated. */
  | { kind: 'DISPLACEMENT_DETECTED'; message: string; conflicts: QueueConflict[] }
  /** Counter-offer only: the picked interval is gone, or was never a real slot. */
  | { kind: 'INTERVAL_UNAVAILABLE'; message: string; failureCode: string | null }
  /** Reject / counter-offer: the reason code is outside the frozen five (issue #66's 422). */
  | { kind: 'INVALID_REASON_CODE'; message: string; supported: string | null }
  /**
   * Hold only (issue #64): this request's single D9 extension is already spent.
   *
   * **The UI is meant to make this unreachable**, by disabling Hold off the row's own
   * `ttl.hold_used` (`edge-cases.md` #6: "prevention over error handling ... there should be no
   * error to handle if the UI does its job"). It is classified anyway, because unreachable-from-
   * this-client is not unreachable: another planner can hold the same row between this row's
   * render and this planner's press. `currentDeadline` is the server's own extended deadline, so
   * the row can correct itself from the refusal without a second read.
   */
  | { kind: 'HOLD_ALREADY_USED'; message: string; currentDeadline: string | null }
  /** Anything else, including transport failure. Never silently swallowed. */
  | { kind: 'OTHER'; message: string; code: string }

export function classifyRefusal(err: unknown): PlannerRefusal {
  if (!isApiError(err)) {
    const message = err instanceof Error ? err.message : String(err)
    return { kind: 'OTHER', message, code: 'NETWORK' }
  }

  // Three refusals put a JSON document in `detail`; the rest put prose there. `ApiError` already
  // did that parse once when it was constructed, so this module no longer repeats it -- `data` is
  // the document or `null`, under exactly the object-not-array rule this file used to apply.
  const body = err.data

  switch (err.code) {
    case 'ALREADY_ACTIONED':
      return { kind: 'ALREADY_ACTIONED', message: err.envelopeMessage }

    case 'SNAPSHOT_STALE':
      return {
        kind: 'SNAPSHOT_STALE',
        message: err.envelopeMessage,
        drift: body as SnapshotStaleDrift | null,
      }

    case 'DISPLACEMENT_DETECTED':
      return {
        kind: 'DISPLACEMENT_DETECTED',
        message: err.envelopeMessage,
        conflicts: Array.isArray(body?.conflicts) ? (body.conflicts as QueueConflict[]) : [],
      }

    case 'HOLD_ALREADY_USED':
      return {
        kind: 'HOLD_ALREADY_USED',
        message: err.envelopeMessage,
        // `allocation.py` puts a JSON document in `detail` carrying `current_deadline`, spelled
        // with `.isoformat()` so it agrees with the success response's spelling of the same
        // instant (that file's own comment on why `str(datetime)` was not used).
        currentDeadline:
          typeof err.data?.current_deadline === 'string' ? err.data.current_deadline : null,
      }

    case 'INTERVAL_UNAVAILABLE':
      return {
        kind: 'INTERVAL_UNAVAILABLE',
        message: err.envelopeMessage,
        failureCode: typeof body?.failure_code === 'string' ? body.failure_code : null,
      }

    case 'INVALID_REASON_CODE':
      // `_assert_reason_code` puts "Supported: A, B, C." in `detail` as plain prose, not JSON.
      return {
        kind: 'INVALID_REASON_CODE',
        message: err.envelopeMessage,
        supported: err.detail || null,
      }

    default:
      return { kind: 'OTHER', message: err.envelopeMessage, code: err.code }
  }
}

/**
 * The mandatory failed-write phrase (`stitch-prompts.md` section 12, State 11's error toast:
 * *"the words 'nothing has changed' are mandatory -- in a system where a click commits capacity"*).
 *
 * Deliberately NOT appended to the three real refusals: `ALREADY_ACTIONED` means something
 * genuinely did change (someone else's write won), and `SNAPSHOT_STALE` / `DISPLACEMENT_DETECTED`
 * each already say precisely what happened. The phrase belongs on the failures that leave the
 * world untouched, where it is reassurance rather than a contradiction.
 */
export function withNothingChanged(message: string): string {
  return `${message} Nothing has changed.`
}
