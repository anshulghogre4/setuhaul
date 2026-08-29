import { calendarDay, clockRange, clockTime, dwellText } from '../lib/format'
import { stateViewFor } from '../lib/queue-states'
import type { GateTruckMatch } from '../lib/types'

/**
 * The truck-identity card (`components.md` section 3) -- identity, current state, appointment.
 *
 * **The state row renders above the button, not just implied by the button's own label.**
 * `screens.md` section 3's Rules: "an officer glancing at the screen mid-task needs to confirm
 * 'yes, this is where this truck actually is' before pressing anything, especially after being
 * interrupted by another truck." That sentence is why this component and the action button are
 * inseparable, and it is the whole reason a blind action with no identity card was not shipped --
 * see `lib/flags.ts`.
 *
 * `NOT_QUEUED` renders **no state row at all** -- not an empty one, not "Not queued". Absence is
 * the signal (`iconography.md`'s Queue state table, and `mockup.html` screen 6).
 *
 * **Queue state is not colour-coded.** The icon is drawn in `text-foreground`, the same colour as
 * its label: hue is rationed to promise state and danger, and a queue state carries its meaning in
 * the glyph shape and the words -- which is also what keeps it legible on a washed-out screen. The
 * `COMPLETED` check in particular is deliberately not green and not in a filled badge, because
 * green in this product means a confirmed capacity promise and this is a yard queue state.
 *
 * The appointment line never truncates and always carries its dock **and** its date. If it does
 * not fit, the container is wrong -- `whitespace-nowrap` is here to make that failure visible
 * rather than silently ellipsise a date an officer is about to act on.
 */
export function TruckIdentityCard({ truck }: { truck: GateTruckMatch }) {
  const view = stateViewFor(truck)
  const Icon = view.icon

  return (
    <div className="flex flex-col gap-4 rounded-md bg-hover p-6">
      <p className="text-h2">
        <span className="font-mono tabular-nums" translate="no">
          {truck.shipment_id}
        </span>{' '}
        · {truck.driver_name}
      </p>
      {/* End-truncation if it overflows (`data-formatting.md`) -- identity carries at the START of
          a carrier name, so a mid-truncation would remove the distinguishing part. Never the
          shipment-id treatment, which has a distinguishing suffix. */}
      <p className="truncate text-body-lg">{truck.carrier_name}</p>

      {Icon && view.label ? (
        <p className="flex items-center gap-2 text-h2">
          <Icon className="size-6 text-foreground" aria-hidden="true" />
          {view.label}
        </p>
      ) : null}

      {/* screens.md section 3 splits IN_DOCK on this, and screen 10b renders the fact. "Unload
          started 14:12" is a RECORDED FACT, not a live counter -- nothing on this card ticks. */}
      {truck.unload_start_ts && truck.queue_state === 'IN_DOCK' ? (
        <p className="text-body-lg">
          Unload started{' '}
          <span className="font-mono tabular-nums" translate="no">
            {clockTime(truck.unload_start_ts)}
          </span>
        </p>
      ) : null}

      {truck.appointment_dock_code && truck.slot_start_ts && truck.slot_end_ts ? (
        <p className="border-t border-input pt-4 text-body-lg whitespace-nowrap">
          Appointment:{' '}
          <span className="font-mono tabular-nums" translate="no">
            {truck.appointment_dock_code} · {calendarDay(truck.slot_start_ts)} ·{' '}
            {clockRange(truck.slot_start_ts, truck.slot_end_ts)}
          </span>
        </p>
      ) : null}

      {/* edge-cases.md #6 / screen 12: the terminal fact, stated plainly. Rendered inside the card
          rather than as a banner, because nothing just happened -- this is the record of an event
          from earlier, which is exactly why there is no button on this screen. */}
      {truck.gate_out_ts ? (
        <p className="border-t border-input pt-4 text-body-lg">
          Gate-out recorded{' '}
          <span className="font-mono tabular-nums" translate="no">
            {clockTime(truck.gate_out_ts)}
          </span>
          {truck.dwell_min !== null ? (
            <>
              {' '}
              · dwell{' '}
              <span className="font-mono tabular-nums" translate="no">
                {dwellText(truck.dwell_min)}
              </span>
            </>
          ) : null}
        </p>
      ) : null}
    </div>
  )
}

/**
 * The held-open space where a button would have sat on a terminal record (screen 12).
 *
 * **Not a greyed control and not a closed-up card.** Foundations `components.md` section 18:
 * Disabled means *temporarily* unavailable pending a prerequisite; this truck's cycle is over and
 * there is no next action, so absence is the correct treatment. The gap is held rather than closed
 * so the card does not appear to be a different component from the one the officer saw a moment
 * ago -- and under direct sunlight a greyed control is indistinguishable from a rendering failure
 * anyway.
 */
export function ButtonVoid() {
  return <div className="h-(--btn-h)" aria-hidden="true" />
}
