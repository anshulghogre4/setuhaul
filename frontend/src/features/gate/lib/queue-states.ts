import {
  BellRing,
  Check,
  DoorClosed,
  DoorOpen,
  Truck,
  type LucideIcon,
} from 'lucide-react'

import type { GateTruckMatch, NextAction } from './types'

/**
 * `screens.md` section 3's state -> action table, split along the line the backend draws.
 *
 * **The server decides WHICH action; this file decides how the state and the verb LOOK.** That
 * split is not a style choice -- `gate_yard_reads.derive_next_action`'s own docstring requires it:
 * "a kiosk that derived its own next action would be a second copy of `QUEUE_TRANSITIONS` free to
 * drift from the one the writes actually enforce... The kiosk may still render its own label; this
 * only says which action is the one valid one." Section 7.5.2 says the same thing more bluntly: the
 * state machine is enforced server-side, not by the kiosk.
 *
 * So `actionFor` is a pure rendering map over the server's `next_action`, and `stateViewFor` is a
 * pure rendering map over `queue_state`. Neither infers policy.
 */
export type GateAction =
  | { tool: 'gate_in' }
  | { tool: 'queue_state'; target: 'CALLED_TO_DOCK' }
  | { tool: 'dock_in' }
  | { tool: 'unload'; phase: 'START' | 'END' }
  | { tool: 'gate_out' }

/**
 * The imperative verb and the endpoint for the server's chosen action.
 *
 * Labels are exact, from `components.md` section 4: "Gate in," "Call to dock," "Dock in," "Start
 * unload," "End unload," "Gate out." Never a generic "Next" or "Continue" -- the specific verb is
 * itself the officer's confirmation that they are about to do the right thing.
 *
 * "Call to dock" maps to `update_queue_state` targeting `CALLED_TO_DOCK`, not to a tool of its own
 * (`flows-and-states.md` Flow 4). That is the only place a target state is chosen client-side, and
 * it is safe because the server's own `CALL_TO_DOCK` enum value has exactly one meaning; the
 * transition is still validated against `QUEUE_TRANSITIONS` on arrival.
 */
export function actionFor(
  next: NextAction | null,
): { label: string; action: GateAction } | null {
  switch (next) {
    case 'GATE_IN':
      return { label: 'Gate in', action: { tool: 'gate_in' } }
    case 'CALL_TO_DOCK':
      return { label: 'Call to dock', action: { tool: 'queue_state', target: 'CALLED_TO_DOCK' } }
    case 'DOCK_IN':
      return { label: 'Dock in', action: { tool: 'dock_in' } }
    case 'START_UNLOAD':
      return { label: 'Start unload', action: { tool: 'unload', phase: 'START' } }
    case 'END_UNLOAD':
      return { label: 'End unload', action: { tool: 'unload', phase: 'END' } }
    case 'GATE_OUT':
      return { label: 'Gate out', action: { tool: 'gate_out' } }
    case null:
      // edge-cases.md #6 / screen 12: the truck's cycle is over. No button renders at all -- not a
      // greyed one, because this is not a temporarily-unavailable action.
      return null
  }
}

export type StateView = {
  /** `null` for `NOT_QUEUED`: `iconography.md`'s Queue state table makes absence the signal, and
   *  `mockup.html` screen 6 renders no state row at all -- not an empty one. */
  icon: LucideIcon | null
  /** `null` alongside a `null` icon, for the same reason: the whole row is omitted. */
  label: string | null
}

/**
 * The state row that renders **above** the button.
 *
 * `screens.md` section 3's Rules: "an officer glancing at the screen mid-task needs to confirm 'yes,
 * this is where this truck actually is' before pressing anything, especially after being interrupted
 * by another truck." The state is never implied by the button's label alone.
 *
 * **Queue state is not colour-coded** -- every icon here is drawn in `text-foreground`, the same
 * colour as its label. Hue is rationed to promise state and danger, and a queue state carries its
 * meaning in the glyph shape and the words, which is also what keeps it legible on a washed-out
 * screen. `WAITING_DOCK_UNAVAILABLE` differs from an ordinary wait by its glyph, never by colour.
 */
export function stateViewFor(truck: GateTruckMatch): StateView {
  // Terminal is checked first: `record_gate_out` leaves `queue_state` at COMPLETED, so the state
  // column alone cannot distinguish "unloaded, still on site" from "gone". Same ordering
  // `derive_next_action` uses, and for the same reason.
  if (truck.gate_out_ts !== null) return { icon: Check, label: 'Completed' }

  switch (truck.queue_state) {
    case 'NOT_QUEUED':
      return { icon: null, label: null }
    case 'WAITING_EARLY':
      return { icon: DoorOpen, label: 'Waiting (early)' }
    case 'WAITING_LATE':
      return { icon: DoorOpen, label: 'Waiting (late)' }
    case 'WAITING_DOCK_UNAVAILABLE':
      return { icon: DoorClosed, label: 'Waiting — dock unavailable' }
    case 'CALLED_TO_DOCK':
      return { icon: BellRing, label: 'Called to dock' }
    case 'IN_DOCK':
      return { icon: Truck, label: 'In dock' }
    case 'COMPLETED':
      // Deliberately not green and not in a filled badge: green in this product means a confirmed
      // capacity promise, and this is a yard queue state (mockup.html screen 11).
      return { icon: Check, label: 'Completed' }
    default:
      // `queue_state` is `str` server-side, not an enum, so an unrecognised value is possible
      // rather than impossible. Rendering no state row is the honest fallback -- inventing a label
      // for a state this build does not know would be worse than omitting one.
      return { icon: null, label: null }
  }
}
