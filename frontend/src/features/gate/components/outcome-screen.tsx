import { CalendarX, Check, CircleAlert, DoorClosed, RefreshCw, TriangleAlert } from 'lucide-react'

import { OutcomeBlock, OutcomeFact, OutcomePair } from './outcome-block'
import { PrimaryAction } from './primary-action'
import { clockRange, clockTime, dwellText, minutesText } from '../lib/format'
import type { GateEventResult, GateTruckMatch } from '../lib/types'

/**
 * Screens 14-22: every `GateEventResult` code rendered as its own named outcome.
 *
 * **Every outcome is named, never a generic "Done" or "Error"** -- `components.md` section 5 calls
 * this "the single most important discipline on this surface": an officer standing at a gate with a
 * truck behind them needs to know exactly what the system just recorded. There is deliberately no
 * fallback "something happened" branch; the switch is exhaustive over the codes the five shipped
 * tools can actually return, read off `gate_yard_service.py` rather than off the design docs.
 *
 * **Tone and politeness are set independently** (see `outcome-block.tsx`). The full table, and the
 * two places it is not obvious:
 *   `DOCK_MISMATCH` is `warning` + `status` -- **not an error, and not assertive**: section 7.5.2's
 *     own wording is "allowed, but recorded as a deviation", the officer recorded what actually
 *     happened, and danger framing here would train officers to under-report honest deviations.
 *   `DOCK_OCCUPIED` and `INVALID_TRANSITION` are informational in tone (no red, no X, nobody
 *     blamed) but `alert` in politeness, because both are unsuccessful actions and
 *     `INVALID_TRANSITION` is about to re-render the card underneath the officer.
 *
 * **No undo, anywhere.** Every outcome here is a factual record of something that physically
 * happened, not a reversible commitment -- `components.md` section 4 argues explicitly against both
 * a confirmation step and an undo, and this surface has no modals at all.
 */
export function OutcomeScreen({
  result,
  truck,
  onNext,
}: {
  result: GateEventResult
  /** The card the action was taken from -- the only source of a human-readable dock code, and of
   *  the driver/carrier names the two blocking outcomes name. See `dockCode` below. */
  truck: GateTruckMatch
  /** `null` for `INVALID_TRANSITION`, which has no button at all: the screen resolves on its own
   *  by re-fetching (`edge-cases.md` #3). The parent owns that re-fetch. */
  onNext: (() => void) | null
}) {
  const content = outcomeContent(result, truck)

  return (
    <div className="flex flex-col gap-4">
      {content.body}
      {content.nextLabel && onNext ? (
        <PrimaryAction label={content.nextLabel} onClick={onNext} />
      ) : null}
    </div>
  )
}

/**
 * `GateEventResult` returns dock **ids** (`D16-DOCK-JAI-D5`), every outcome screen renders dock
 * **codes** (`D5`), and nothing in the response carries the code.
 *
 * Resolved without inventing anything: the only dock this kiosk ever submits is the one already on
 * the truck-identity card (`flows-and-states.md` Flow 5 -- "the officer does not choose a dock"),
 * so its code is known locally. An id that does *not* match the card's is one the server chose,
 * has no code available anywhere in the response, and falls back to the raw id rather than to a
 * guess -- visibly wrong instead of quietly wrong.
 *
 * That fallback is reachable in exactly one situation, and it is worth naming because it is also
 * the only situation in which `DOCK_MISMATCH` can fire at all under this UI contract: the
 * appointment's dock changed server-side between the card rendering and the tap landing. Raised in
 * the build report -- the design's own narrative for `DOCK_MISMATCH` ("if the truck physically
 * arrived somewhere else") cannot be produced by a kiosk that submits the appointment's own dock,
 * because `record_dock_in` computes the mismatch by comparing the submitted id against the
 * appointment's id (`gate_yard_service.py:667-669`), and those are the same value by construction.
 */
function dockCode(dockId: string | null, truck: GateTruckMatch): string {
  if (!dockId) return ''
  if (truck.appointment_dock_id === dockId && truck.appointment_dock_code)
    return truck.appointment_dock_code
  return dockId
}

/** `EARLY` / `ON_TIME` / `LATE` in sentence case. The raw enum has no business on screen
 *  (`voice-and-tone.md`: uppercase is for text-label state chips, and this is a 16px/400 fact
 *  line). The enum value in the payload is untouched; only its rendering changes. */
function arrivalText(arrivalState: string | null): string {
  switch (arrivalState) {
    case 'EARLY':
      return 'Early'
    case 'ON_TIME':
      return 'On time'
    case 'LATE':
      return 'Late'
    default:
      return ''
  }
}

function Mono({ children }: { children: React.ReactNode }) {
  return (
    <span className="font-mono tabular-nums" translate="no">
      {children}
    </span>
  )
}

function outcomeContent(
  r: GateEventResult,
  truck: GateTruckMatch,
): { body: React.ReactNode; nextLabel: string | null } {
  const id = r.shipment_id

  switch (r.code) {
    // ---- screen 14 -----------------------------------------------------------------------
    case 'GATE_IN_RECORDED': {
      // The computed arrival_state is surfaced rather than buried: an EARLY truck may still have
      // to wait regardless of how quickly it was checked in (flows-and-states.md Flow 3).
      const arrival = arrivalText(r.arrival_state)
      return {
        body: (
          <OutcomeBlock tone="success" live="status" icon={Check} headline="Gate-in recorded">
            <OutcomeFact>
              <Mono>{id}</Mono> · <Mono>{clockTime(r.gate_in_ts)}</Mono>
              {arrival ? ` · ${arrival}` : ''}
            </OutcomeFact>
          </OutcomeBlock>
        ),
        nextLabel: 'Search next truck',
      }
    }

    // ---- screen 15a ----------------------------------------------------------------------
    case 'QUEUE_UPDATED':
      return {
        body: (
          <OutcomeBlock tone="success" live="status" icon={Check} headline="Called to dock">
            <OutcomeFact mono>
              {id} · {truck.appointment_dock_code ?? ''} · {clockTime(r.as_of)}
            </OutcomeFact>
          </OutcomeBlock>
        ),
        nextLabel: 'Search next truck',
      }

    // ---- screen 15b ----------------------------------------------------------------------
    case 'DOCK_IN_RECORDED':
      return {
        body: (
          <OutcomeBlock tone="success" live="status" icon={Check} headline="Dock-in recorded">
            <OutcomeFact mono>
              {id} · {dockCode(r.actual_dock_id, truck)} · {clockTime(r.as_of)}
            </OutcomeFact>
          </OutcomeBlock>
        ),
        nextLabel: 'Search next truck',
      }

    // ---- screens 15c and 18 --------------------------------------------------------------
    case 'RECORDED': {
      if (r.phase === 'START') {
        return {
          body: (
            <OutcomeBlock tone="success" live="status" icon={Check} headline="Unload started">
              <OutcomeFact mono>
                {id} · {truck.appointment_dock_code ?? ''} · {clockTime(r.unload_start_ts)}
              </OutcomeFact>
            </OutcomeBlock>
          ),
          nextLabel: 'Search next truck',
        }
      }

      const overrun = r.overrun_min ?? 0
      const dock = truck.appointment_dock_code ?? ''
      const window =
        r.unload_start_ts && r.unload_end_ts ? clockRange(r.unload_start_ts, r.unload_end_ts) : ''

      // screen 18. Warning tone, no red -- the officer is not asked to explain, justify or fix it;
      // the delta feeds re-sequencing and churn pricing downstream. `overrun_min` is signed, not
      // clamped, so an unload that finished EARLY is a negative value and belongs in the
      // brief-success family, not here.
      if (overrun > 0) {
        return {
          body: (
            <OutcomeBlock
              tone="warning"
              live="status"
              icon={TriangleAlert}
              headline={`Unload ended · ${minutesText(overrun)} over expected`}
            >
              <OutcomeFact mono>
                {id} · {dock} · {window}
              </OutcomeFact>
              <OutcomeFact>
                Expected <Mono>{minutesText(r.expected_unload_min ?? 0)}</Mono> · actual{' '}
                <Mono>{minutesText(r.actual_unload_min ?? 0)}</Mono>
              </OutcomeFact>
            </OutcomeBlock>
          ),
          nextLabel: 'Search next truck',
        }
      }

      // An on-time or early unload END has no artboard of its own -- screen 15's family header
      // says "unload recorded" and covers both phases, but only the START variant is drawn.
      // Copy inferred from that family's own pattern (specific past-tense verb, mono fact line),
      // flagged in the build report rather than presented as specified.
      return {
        body: (
          <OutcomeBlock tone="success" live="status" icon={Check} headline="Unload ended">
            <OutcomeFact mono>
              {id} · {dock} · {window}
            </OutcomeFact>
          </OutcomeBlock>
        ),
        nextLabel: 'Search next truck',
      }
    }

    // ---- screen 16 -----------------------------------------------------------------------
    case 'COMPLETED':
      // Dwell is a measured fact, not an assessment: no judgement, no coloured delta, no benchmark,
      // no gauge. This surface records; other surfaces evaluate.
      return {
        body: (
          <OutcomeBlock tone="success" live="status" icon={Check} headline="Gate-out recorded">
            <OutcomeFact mono>
              {id} · {clockTime(r.gate_out_ts)} · dwell {dwellText(r.dwell_min ?? 0)}
            </OutcomeFact>
          </OutcomeBlock>
        ),
        nextLabel: 'Search next truck',
      }

    // ---- screen 17 -----------------------------------------------------------------------
    case 'DOCK_MISMATCH':
      return {
        body: (
          <OutcomeBlock tone="warning" live="status" icon={TriangleAlert} headline="Different dock">
            <OutcomePair label="Confirmed dock:" value={dockCode(r.expected_dock_id, truck)} />
            <OutcomePair label="Actual dock:" value={dockCode(r.actual_dock_id, truck)} />
            <OutcomeFact>Recorded as a deviation — not an error.</OutcomeFact>
          </OutcomeBlock>
        ),
        nextLabel: 'Search next truck',
      }

    // ---- screen 19 -----------------------------------------------------------------------
    case 'ALREADY_CHECKED_IN':
      // Informational: not green (nothing new was recorded) and not red (nothing went wrong). From
      // the officer's position the truck genuinely IS gated in, whoever recorded it -- so no
      // "Error", no "Duplicate", no "You already did this", and no force-anyway override.
      return {
        body: (
          <OutcomeBlock
            tone="info"
            live="status"
            icon={CircleAlert}
            headline={<>Already gated in at <Mono>{clockTime(r.gate_in_ts)}</Mono></>}
          >
            <OutcomeFact>
              <Mono>{id}</Mono> · {truck.driver_name}
            </OutcomeFact>
            <OutcomeFact>Nothing new was recorded. This truck is already checked in.</OutcomeFact>
          </OutcomeBlock>
        ),
        nextLabel: 'Search next truck',
      }

    // ---- screen 20 -----------------------------------------------------------------------
    case 'NO_ACTIVE_APPOINTMENT':
      // Danger tone, because this genuinely blocks the truck -- and the kiosk cannot resolve it: no
      // "create appointment", no override, no escalation, no click-to-call. The button label
      // differs from the success family on purpose: "Search next truck" would imply this truck is
      // dealt with, and it is not.
      return {
        body: (
          <OutcomeBlock tone="danger" live="alert" icon={CalendarX} headline="No active appointment">
            <OutcomeFact>
              <Mono>{id}</Mono> · {truck.driver_name} · {truck.carrier_name}
            </OutcomeFact>
            <OutcomeFact>
              Nothing was recorded. This can’t be fixed from the gate — contact the facility office.
            </OutcomeFact>
          </OutcomeBlock>
        ),
        nextLabel: 'Back to search',
      }

    // ---- screen 21 -----------------------------------------------------------------------
    case 'DOCK_OCCUPIED': {
      // Same `door-closed` glyph as the WAITING_DOCK_UNAVAILABLE state (screen 8), deliberately, so
      // the officer connects this outcome to the state the truck is about to sit in.
      //
      // The copy says dock-in was NOT recorded but does not say "nothing was recorded" -- that
      // would be false against the shipped backend, which UPDATEs queue_state to
      // WAITING_DOCK_UNAVAILABLE, writes a DOCK_IN_REFUSED audit row and commits
      // (`gate_yard_service.py:638-663`). The truck's state genuinely changes, and the state table
      // depends on it: "Call to dock" is only offered again because the truck is back in a
      // WAITING_* state.
      const dock = dockCode(r.expected_dock_id, truck)
      return {
        body: (
          <OutcomeBlock
            tone="warning"
            live="alert"
            icon={DoorClosed}
            headline={<><Mono>{dock}</Mono> is occupied</>}
          >
            <OutcomeFact>
              <Mono>{id}</Mono> · {truck.driver_name}
            </OutcomeFact>
            <OutcomeFact>
              Dock-in was not recorded. This truck is back in the yard queue — call it again when{' '}
              {dock} clears.
            </OutcomeFact>
          </OutcomeBlock>
        ),
        nextLabel: 'Back to search',
      }
    }

    // ---- screen 22a ----------------------------------------------------------------------
    case 'INVALID_TRANSITION':
      // No button: the screen resolves on its own. The info block is NOT kept as a persistent
      // banner -- the re-rendered card IS the resolution (screen 22b). `refresh-cw` is the one icon
      // in the system permitted to spin (`iconography.md`), and under prefers-reduced-motion it
      // becomes a static icon plus the same headline: the information is not lost, only the
      // movement.
      return {
        body: (
          <OutcomeBlock
            tone="info"
            live="alert"
            icon={RefreshCw}
            headline="This truck’s status changed — refreshing"
          >
            <OutcomeFact>Nothing was recorded.</OutcomeFact>
          </OutcomeBlock>
        ),
        nextLabel: null,
      }

    // ---- no artboard: a real code the design files never name --------------------------------
    case 'ALREADY_GATED_OUT':
      // `gate_yard_service.py:829`, matching `edge-cases.md` #6's narrative exactly, but never
      // named as a CODE in `screens.md`, `edge-cases.md`, `components.md` or
      // `stitch-prompts.md`'s outcome-tone table -- every other outcome code in the catalog is.
      // Reachable here only as a race (another device gated the same truck out between this card
      // rendering and the tap landing), so it is rendered in the same informational register as
      // ALREADY_CHECKED_IN, its closest specified sibling, rather than invented as a new tone.
      // Raised in the build report as a one-line documentation addition.
      return {
        body: (
          <OutcomeBlock
            tone="info"
            live="alert"
            icon={CircleAlert}
            headline={<>Already gated out at <Mono>{clockTime(r.gate_out_ts)}</Mono></>}
          >
            <OutcomeFact>
              <Mono>{id}</Mono> · {truck.driver_name}
            </OutcomeFact>
            <OutcomeFact>
              Nothing new was recorded. This truck has already left
              {r.dwell_min !== null ? <> · dwell <Mono>{dwellText(r.dwell_min)}</Mono></> : null}.
            </OutcomeFact>
          </OutcomeBlock>
        ),
        nextLabel: 'Search next truck',
      }
  }
}
