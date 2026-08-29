import { useEffect, useId, useState } from 'react'
import { TriangleAlert } from 'lucide-react'

import { OutcomeBlock, OutcomeFact } from './outcome-block'
import { PrimaryAction } from './primary-action'
import { ButtonVoid, TruckIdentityCard } from './truck-identity-card'
import {
  recordDockIn,
  recordGateIn,
  recordGateOut,
  recordUnloadStartEnd,
  updateQueueState,
} from '../lib/api'
import { haptic } from '../lib/haptics'
import { actionFor, type GateAction } from '../lib/queue-states'
import type { GateEventResult, GateTruckMatch } from '../lib/types'

/**
 * Flow 2: the truck-identity card plus the one valid action, and the code that actually performs
 * the write. **This is real backend wiring, not a stub** -- every branch below calls a live,
 * shipped `/api/v1/gate/*` endpoint (E3.6/#30) with the arguments its router expects.
 *
 * The `GateTruckMatch` it takes comes from Flow 1’s search (`GET /api/v1/gate/trucks`, issue #67).
 * Which of the five writes is the one valid action is **not decided here**: it is read off the
 * server’s `next_action` via `actionFor`, so this component cannot drift from the state machine the
 * writes actually enforce.
 *
 * ## Three behaviours here that are requirements, not implementation detail
 *
 * **Offline: the button goes Inactive, it does not accept a hopeful tap.** `edge-cases.md` #7
 * classifies the one-dominant-button action as *primary* under `auth-and-scoping.md`'s degradation
 * policy: "if connectivity can't be confirmed, the button goes Inactive with a reason rather than
 * accepting a tap that might silently fail. A gate/yard write is exactly the kind of fact that must
 * not be lost or duplicated by a hopeful offline submission." `navigator.onLine` is the only signal
 * a browser has, and it is a weak one -- it reports link-layer connectivity, not reachability -- so
 * the reason copy is deliberately "Can't confirm this will save", not "You are offline". The
 * distinction is the honest one: the kiosk genuinely does not know.
 *
 * **A failed write says nothing has changed, and says the retry is safe.** Both halves of that copy
 * are load-bearing (`mockup.html` screen 13's own note): in a system where a tap commits capacity,
 * an officer must know a failure left no partial state. "This won't record it twice" is true for
 * all five tools -- but by two different mechanisms, not one, which is why no `Idempotency-Key` is
 * fabricated for the four that do not take one (see `lib/api.ts`).
 *
 * **A fresh idempotency key per submit attempt, not per truck.** `record_gate_in`'s replay is keyed
 * on `(key, user_id, route, request_hash)`; reusing one key across a retry after a *network* error
 * is exactly the case it exists for, so the key is generated once when the action is armed and
 * reused for every retry of that same action -- not regenerated on each tap, which would defeat it.
 */
export function TruckAction({
  truck,
  onOutcome,
}: {
  truck: GateTruckMatch
  /**
   * Called with the tool's own typed result. The parent routes it to `OutcomeScreen` -- and owns
   * the `INVALID_TRANSITION` re-fetch, because `edge-cases.md` #3's resolution is to re-render
   * Flow 2 with the truck's *real* state, which needs the search tool (#67) this component
   * deliberately knows nothing about. Handling it here would put a second, hidden dependency on
   * #67 inside a component that otherwise has none.
   */
  onOutcome: (result: GateEventResult) => void
}) {
  const next = actionFor(truck.next_action)
  const [submitting, setSubmitting] = useState(false)
  const [failed, setFailed] = useState(false)
  const [online, setOnline] = useState(() => navigator.onLine)
  const reasonId = useId()

  // A yard tablet at the edge of facility Wi-Fi crosses this line repeatedly across a shift, so the
  // button has to follow it live rather than sample once on mount.
  useEffect(() => {
    const up = () => setOnline(true)
    const down = () => setOnline(false)
    window.addEventListener('online', up)
    window.addEventListener('offline', down)
    return () => {
      window.removeEventListener('online', up)
      window.removeEventListener('offline', down)
    }
  }, [])

  // Armed once per truck+action, so a retry after a transport failure replays the same key rather
  // than presenting the server with a new one. `crypto.randomUUID` is Baseline and is already the
  // key source elsewhere in this codebase.
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID())
  useEffect(() => {
    setIdempotencyKey(crypto.randomUUID())
    setFailed(false)
  }, [truck.shipment_id, truck.next_action])

  async function run(action: GateAction) {
    setSubmitting(true)
    setFailed(false)
    try {
      const result = await dispatch(action, truck, idempotencyKey)
      // Recorded vs rejected, per the mockup's own non-visual notes. DOCK_MISMATCH counts as
      // recorded -- a deviation was written -- which is exactly why screen 17's note says the
      // rejection pattern does not fire there.
      haptic(REJECTED_CODES.has(result.code) ? 'rejected' : 'recorded')
      onOutcome(result)
    } catch {
      // A transport/5xx failure, not a named outcome. `apiPost` throws for those and returns the
      // envelope for every code the tools actually produce, including INVALID_TRANSITION -- which
      // is a 200 with a code, not a rejection, and therefore never lands here.
      haptic('rejected')
      setFailed(true)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <TruckIdentityCard truck={truck} />

      {failed ? (
        <OutcomeBlock
          tone="warning"
          live="alert"
          icon={TriangleAlert}
          headline="That didn’t record — nothing has changed."
          align="inline"
        >
          <OutcomeFact>Try again — this won’t record it twice.</OutcomeFact>
        </OutcomeBlock>
      ) : null}

      {next === null ? (
        // edge-cases.md #6 / screen 12: past gate-out there is no action at all, so the space where
        // a button would have sat is held open rather than filled with a greyed control.
        <ButtonVoid />
      ) : !online ? (
        <PrimaryAction
          label={next.label}
          state="inactive"
          reason="Can’t confirm this will save — check connection"
          reasonId={reasonId}
          // Activating it surfaces the explanation rather than doing nothing (components.md
          // foundations section 18). The reason line is already permanently visible, so the tap
          // re-checks connectivity instead of only re-stating it -- which is the more useful
          // answer to "why won't this work" when the link has since come back.
          onClick={() => setOnline(navigator.onLine)}
        />
      ) : (
        <PrimaryAction
          label={next.label}
          state={submitting ? 'submitting' : 'default'}
          onClick={() => void run(next.action)}
        />
      )}

    </div>
  )
}

/** The codes where the officer's intended action did not happen. Drives the 300ms haptic and
 *  nothing else -- tone and politeness are decided per-screen in `outcome-screen.tsx`. */
const REJECTED_CODES = new Set<string>([
  'NO_ACTIVE_APPOINTMENT',
  'DOCK_OCCUPIED',
  'INVALID_TRANSITION',
])

/**
 * `GateAction` -> the live endpoint. Exhaustive over the union, so a new action added to
 * `screens.md` section 3's table fails the build here rather than silently doing nothing.
 */
async function dispatch(
  action: GateAction,
  truck: GateTruckMatch,
  idempotencyKey: string,
): Promise<GateEventResult> {
  switch (action.tool) {
    case 'gate_in':
      return recordGateIn(truck.shipment_id, idempotencyKey)
    case 'queue_state':
      return updateQueueState(truck.shipment_id, action.target)
    case 'dock_in': {
      // flows-and-states.md Flow 5: the dock submitted is the truck's CONFIRMED APPOINTMENT'S dock,
      // read off the card the officer is looking at. There is no dock selector, no bay grid and no
      // editable dock field anywhere on this surface.
      const dockId = truck.appointment_dock_id
      if (!dockId) {
        // Unreachable through the state table -- a truck cannot be CALLED_TO_DOCK without an
        // appointment -- but thrown rather than defaulted, because a fabricated dock id would write
        // a real arrival against the wrong bay.
        throw new Error('No confirmed dock on this appointment.')
      }
      return recordDockIn(truck.shipment_id, dockId)
    }
    case 'unload':
      return recordUnloadStartEnd(truck.shipment_id, action.phase)
    case 'gate_out':
      return recordGateOut(truck.shipment_id)
  }
}
