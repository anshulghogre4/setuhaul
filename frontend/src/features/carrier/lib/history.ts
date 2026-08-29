import type { ShipmentHistoryEntry } from './types'

/**
 * Shipment-detail history labels.
 *
 * ## The deviation this file records rather than hides
 *
 * `stitch-prompts.md` §8 shows four illustrative history rows — `Reported delay`,
 * `Option offered`, `Held, then requested`, `Confirmed by warehouse`. Only the last of those
 * corresponds to an event `list_shipment_history` actually emits. The live vocabulary is eight
 * `event_type` values, drawn from five tables, and "Option offered" is not among them at all
 * (nothing persists an offered option set). So the labels below are derived from the live event
 * vocabulary, keeping the one design string that does map (`Confirmed by warehouse`) verbatim.
 * Flagged as a deviation from the prompt's illustrative rows, not treated as matching them.
 *
 * ## What is deliberately NOT rendered
 *
 * Nothing free-text. `components.md` §4 draws the line ("History never surfaces another party's
 * internal-only content — a planner's rejection note, an operations coordinator's private
 * remark"), and the repository already holds it with a column allowlist:
 * `appointments.cancellation_reason`, `driver_exceptions.description`/`resolution_note`,
 * `eta_updates.note` and `escalation_queue.payload_json` are never selected. Only two coded
 * fields arrive here (`detail_code`, `reason_code`), and only the codes that mean something to a
 * carrier are surfaced as a qualifier below — never the raw code as-is.
 */

const LABEL: Record<ShipmentHistoryEntry['event_type'], string> = {
  ETA_UPDATE: 'ETA updated',
  APPOINTMENT_BOOKED: 'Slot requested',
  APPOINTMENT_CONFIRMED: 'Confirmed by warehouse',
  APPOINTMENT_CANCELLED: 'Appointment cancelled',
  EXCEPTION_REPORTED: 'Exception reported',
  GATE_IN: 'Arrived at gate',
  DOCK_IN: 'At the dock',
  GATE_OUT: 'Departed',
}

/** `NO_FEASIBLE_SLOT` -> `no feasible slot`. A coded vocabulary made readable, not a translation
 *  layer — if a code is added upstream it renders sensibly instead of disappearing. */
function humanise(code: string): string {
  return code.replace(/_/g, ' ').toLowerCase()
}

/**
 * Which coded qualifier, if any, belongs beside a given event.
 *
 * Deliberately narrow. `ETA_UPDATE.detail_code` is `source_type` (`DRIVER_CHAT`, …) — internal
 * plumbing, not an outcome, so it is dropped. `GATE_IN.detail_code` is `arrival_state`
 * (`EARLY / ON_TIME / LATE / NO_SHOW`), the same recorded fact the on-time tile is computed
 * from, so it is kept: it is this carrier's own outcome, stated plainly.
 */
function qualifier(entry: ShipmentHistoryEntry): string | null {
  switch (entry.event_type) {
    case 'ETA_UPDATE':
      return entry.reason_code ? humanise(entry.reason_code) : null
    case 'EXCEPTION_REPORTED':
      return entry.reason_code ? humanise(entry.reason_code) : null
    case 'GATE_IN':
      return entry.detail_code ? humanise(entry.detail_code) : null
    default:
      return null
  }
}

export function historyLabel(entry: ShipmentHistoryEntry): string {
  const base = LABEL[entry.event_type] ?? humanise(entry.event_type)
  const q = qualifier(entry)
  // En dash, matching every other qualified clause on this surface.
  return q ? `${base} – ${q}` : base
}
