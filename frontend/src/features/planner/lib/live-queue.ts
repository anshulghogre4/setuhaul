import type { PlannerQueue, PlannerQueueRow } from './types'

/**
 * U19's frozen sort, as a pure function -- issue #59.
 *
 * ## The rule this file exists to keep
 *
 * `00-foundations/motion.md` states it as three lines and every one of them is load-bearing:
 *
 * ```
 * Idle, nothing focused → New rows insert with a single arrival flash.
 * Row focused           → Order is PINNED. New arrivals accumulate behind a
 *                         "N new · press <key>" affordance. Nothing above the
 *                         focused row moves. Ever.
 * User triggers re-sort → List re-renders instantly at the new order, focus follows
 *                         the same row by id, and that row flashes once.
 * ```
 *
 * (`FR-X-012`, `REQUIREMENTS.md`: *"never move the target under the click"*.)
 *
 * ## The one genuinely hard case: a row that vanishes while the sort is frozen
 *
 * `accessibility-behaviour.md`'s matrix says a row the user is **not** focused on disappearing is
 * **silent** -- but "silent" is about *announcement*, and removing it would still shift every row
 * below it, which `motion.md` forbids in the same breath ("nothing above the focused row moves.
 * Ever"). Both can hold at once only one way, and this is it: **while frozen, no row is ever
 * removed.** A row the server no longer returns is marked `vanished` **in place** -- the same
 * treatment `02-ops-exception-console/edge-cases.md` section 2 already requires for its own race
 * ("the row updates in place ... never removed and re-inserted") -- and it leaves on the next
 * re-sort, which is a moment the planner chose.
 *
 * The announcement politeness for that mark is decided by the caller, not here, because it turns
 * on which row has focus: `assertive` if it is the focused row (the matrix's `ALREADY_ACTIONED`
 * row -- "a user about to act on a row that just changed underneath them must be interrupted"),
 * silent otherwise.
 *
 * ## Field updates while frozen are allowed; order changes are not
 *
 * A frozen row still refreshes its own contents (TTL deadline, ETA, displacement, and critically
 * `snapshot_hash`). Freezing the *data* as well as the order would be worse than useless: a
 * planner would then confirm against a hash the server has already moved past, turning a rare
 * `SNAPSHOT_STALE` into the normal outcome. Freezing is about **position**, never about facts.
 */

export type LiveQueueState = {
  /** Exactly what is rendered, in exactly the order it is rendered. */
  rows: PlannerQueueRow[]
  /** Rows the server has sent that are not in `rows` yet, in server order. */
  staged: PlannerQueueRow[]
  /** Appointment ids in `rows` the server no longer returns. */
  vanished: Set<string>
  /**
   * Ids that arrived since the planner last saw the list settle. Drives `motion.md`'s single 200ms
   * arrival flash and, under `prefers-reduced-motion`, the persistent "New" badge that replaces it
   * (`styles/theme.css`). **Not cleared on a timer**, deliberately: the CSS animation plays once
   * regardless, and the badge is required to persist -- one lifetime serving both renderings is
   * what keeps the reduced-motion path honest instead of silently deleting the signal.
   */
  flash: Set<string>
  /** The payload whose ORDER is currently rendered. The toolbar's counts come from here, so the
   *  header never claims a total the visible list does not correspond to. */
  applied: PlannerQueue | null
  /** The most recent payload seen, applied or not, so a re-sort needs no second fetch. */
  latest: PlannerQueue | null
}

export function emptyLiveQueueState(): LiveQueueState {
  return { rows: [], staged: [], vanished: new Set(), flash: new Set(), applied: null, latest: null }
}

/** The first load, and any explicit Refresh: server order wins outright, nothing is staged. */
export function adoptQueue(payload: PlannerQueue): LiveQueueState {
  return {
    rows: payload.items,
    staged: [],
    vanished: new Set(),
    flash: new Set(),
    applied: payload,
    latest: payload,
  }
}

/**
 * Fold a poll response into the current state.
 *
 * `frozen` is the caller's answer to "is a planner mid-decision right now" -- a row has DOM focus,
 * a selection exists, a dialog is open, or a write is in flight. It is deliberately broader than
 * "a row has focus": every one of those states is a decision in progress, and re-ordering under
 * any of them causes the same wrong click.
 */
export function mergeQueue(
  state: LiveQueueState,
  payload: PlannerQueue,
  frozen: boolean,
): LiveQueueState {
  const incoming = new Map(payload.items.map((r) => [r.appointment_id, r]))

  if (!frozen) {
    // Nothing is being decided: adopt server order wholesale and flash only what is genuinely new,
    // so a settled row does not re-highlight on every poll (`stitch-prompts.md` section 4:
    // "settled rows recede in contrast ... they do not re-highlight when the list re-renders").
    const known = new Set(state.rows.map((r) => r.appointment_id))
    const flash = new Set(
      payload.items.filter((r) => !known.has(r.appointment_id)).map((r) => r.appointment_id),
    )
    return {
      rows: payload.items,
      staged: [],
      vanished: new Set(),
      flash,
      applied: payload,
      latest: payload,
    }
  }

  // Frozen: keep this exact order and this exact membership. Refresh each row's own fields in
  // place; mark the ones the server dropped; stage the arrivals behind the pill.
  const rows = state.rows.map((row) => incoming.get(row.appointment_id) ?? row)
  const present = new Set(state.rows.map((r) => r.appointment_id))
  const vanished = new Set(
    state.rows.map((r) => r.appointment_id).filter((id) => !incoming.has(id)),
  )
  const staged = payload.items.filter((r) => !present.has(r.appointment_id))

  // `flash` is carried forward untouched: a row that arrived before this poll is still new to the
  // planner, and clearing it here would delete the reduced-motion badge on the next 15s tick.
  return { rows, staged, vanished, flash: state.flash, applied: state.applied, latest: payload }
}

/**
 * Apply what the pill has been holding -- the `press <key>` half of the affordance.
 *
 * Server order wins from here; the previously-vanished rows leave; the staged rows join. The
 * flash set is every row the planner has not already seen in place, which is what makes the new
 * order legible rather than merely correct.
 */
export function applyResort(state: LiveQueueState): LiveQueueState {
  if (!state.latest) return { ...state, staged: [], vanished: new Set() }
  const seen = new Set(state.rows.filter((r) => !state.vanished.has(r.appointment_id)).map((r) => r.appointment_id))
  const flash = new Set(
    state.latest.items.filter((r) => !seen.has(r.appointment_id)).map((r) => r.appointment_id),
  )
  return {
    rows: state.latest.items,
    staged: [],
    vanished: new Set(),
    flash,
    applied: state.latest,
    latest: state.latest,
  }
}

/**
 * Drop rows locally after this planner's OWN write succeeded, preserving everything else. Used
 * instead of a full re-adopt so a confirm does not also silently apply a pending re-sort.
 *
 * **It must also strip the ids out of the cached payloads, and that is not tidiness.** `applied`
 * and `latest` are what `applyResort` rebuilds the list from; leaving a just-confirmed row in them
 * means the next press of the re-sort key resurrects a row the planner already actioned, offering
 * Confirm on an appointment that is no longer pending. Found by tracing confirm -> press S rather
 * than by reading either function alone.
 */
export function removeRowsFromState(
  state: LiveQueueState,
  appointmentIds: readonly string[],
): LiveQueueState {
  const drop = new Set(appointmentIds)
  const strip = (payload: PlannerQueue | null) =>
    payload === null
      ? null
      : { ...payload, items: payload.items.filter((r) => !drop.has(r.appointment_id)) }

  return {
    ...state,
    rows: state.rows.filter((r) => !drop.has(r.appointment_id)),
    staged: state.staged.filter((r) => !drop.has(r.appointment_id)),
    vanished: new Set([...state.vanished].filter((id) => !drop.has(id))),
    applied: strip(state.applied),
    latest: strip(state.latest),
  }
}

export function removeRowFromState(state: LiveQueueState, appointmentId: string): LiveQueueState {
  return removeRowsFromState(state, [appointmentId])
}

/**
 * Where focus goes after a re-sort, per `accessibility-behaviour.md`'s focus contract.
 *
 * "Focus follows the same row by id" while that row still exists; when it does not, focus goes to
 * **an adjacent row at the same position, never the top of the list** -- "a planner working row 20
 * of 35 who loses focus to row 1 has effectively lost their place in the spike".
 */
export function focusTargetAfterResort(
  previousRows: PlannerQueueRow[],
  nextRows: PlannerQueueRow[],
  focusedId: string | null,
): string | null {
  if (focusedId === null) return null
  if (nextRows.some((r) => r.appointment_id === focusedId)) return focusedId
  if (nextRows.length === 0) return null
  const previousIndex = previousRows.findIndex((r) => r.appointment_id === focusedId)
  if (previousIndex < 0) return null
  return nextRows[Math.min(previousIndex, nextRows.length - 1)].appointment_id
}
