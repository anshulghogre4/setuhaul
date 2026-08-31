import type { EscalationQueueItem, EscalationQueueResponse } from './types'

/**
 * The ops console's half of issue #59 -- the merge, and the change detection the two announcement
 * behaviours in `edge-cases.md` depend on.
 *
 * ## Why the queue freezes here too
 *
 * `edge-cases.md` section 1: "the row does **not** re-sort out of the coordinator's current view if
 * they have it focused (U19) -- a breach happening under someone's eyes must not also relocate the
 * thing they're looking at." U95's sort is server-side (unowned above owned, then time-to-breach
 * ascending) and this file never re-implements it; freezing is about *when* a new server order is
 * adopted, never about computing one.
 *
 * **Focus freezes the order; selection does not.** A coordinator dwells on one escalation for
 * minutes (`accessibility.md`: "long dwell per item"), so freezing for the whole time a row is
 * *selected* would make the live count useless -- it would never be applied. Freezing while the
 * queue pane actually holds focus is the behaviour U19 describes and the one that prevents the
 * harm: a wrong click on a row that moved.
 *
 * ## The selected row is never dropped by a poll
 *
 * Independent of freezing. If the server stops returning the escalation currently open in the
 * detail pane, the item is **kept in place and marked gone** rather than removed -- otherwise the
 * detail pane, the transcript and any half-written reply vanish underneath a coordinator because
 * somebody else resolved the item. `edge-cases.md` section 9 is explicit that the console must not
 * close an escalation the coordinator has not actioned, and that applies to the *view* as much as
 * to the record.
 */

export type OpsLiveState = {
  /** Rendered, in rendered order. */
  items: EscalationQueueItem[]
  /** Arrivals held behind the frozen sort -- the "N new" count. */
  staged: EscalationQueueItem[]
  /** Ids still rendered that the server no longer returns. */
  gone: Set<string>
  /** The response whose ORDER is currently rendered. */
  applied: EscalationQueueResponse | null
  /** The newest response seen, applied or not, so a re-sort needs no second fetch. */
  latest: EscalationQueueResponse | null
}

export function emptyOpsLiveState(): OpsLiveState {
  return { items: [], staged: [], gone: new Set(), applied: null, latest: null }
}

export function adoptOpsQueue(payload: EscalationQueueResponse): OpsLiveState {
  return { items: payload.items, staged: [], gone: new Set(), applied: payload, latest: payload }
}

export function mergeOpsQueue(
  state: OpsLiveState,
  payload: EscalationQueueResponse,
  opts: { frozen: boolean; keepId: string | null },
): OpsLiveState {
  const incoming = new Map(payload.items.map((i) => [i.escalation_id, i]))

  if (!opts.frozen) {
    const gone = new Set<string>()
    let items = payload.items
    // The selected row survives even when the server drops it -- see the header.
    if (opts.keepId !== null && !incoming.has(opts.keepId)) {
      const kept = state.items.find((i) => i.escalation_id === opts.keepId)
      if (kept) {
        const at = Math.min(
          state.items.findIndex((i) => i.escalation_id === opts.keepId),
          payload.items.length,
        )
        items = [...payload.items.slice(0, at), kept, ...payload.items.slice(at)]
        gone.add(opts.keepId)
      }
    }
    return { items, staged: [], gone, applied: payload, latest: payload }
  }

  // Frozen: this order, this membership. Fields refresh in place; arrivals wait behind the pill.
  const items = state.items.map((item) => incoming.get(item.escalation_id) ?? item)
  const present = new Set(state.items.map((i) => i.escalation_id))
  const gone = new Set(
    state.items.map((i) => i.escalation_id).filter((id) => !incoming.has(id)),
  )
  const staged = payload.items.filter((i) => !present.has(i.escalation_id))

  return { items, staged, gone, applied: state.applied, latest: payload }
}

export function applyOpsResort(state: OpsLiveState, keepId: string | null): OpsLiveState {
  if (!state.latest) return { ...state, staged: [], gone: new Set() }
  return mergeOpsQueue(
    { ...state, applied: state.latest },
    state.latest,
    { frozen: false, keepId },
  )
}

/* ==============================================================================================
 * Change detection -- `edge-cases.md` sections 2 and 9
 * ============================================================================================ */

export type EscalationChange = {
  escalationId: string
  /** One sentence per fact that changed, ready to render inline in the detail pane. */
  facts: string[]
  /**
   * True when the change is somebody else claiming or acting on this escalation -- section 2's
   * race. The caller pairs this with "is the coordinator focused on this exact row" to decide
   * `assertive` vs silent; this flag alone is not the politeness decision.
   */
  race: boolean
  /** `updated_at` from the server, so the notice can name a time rather than invent one. */
  atIso: string
}

/**
 * What changed about ONE escalation between two polls.
 *
 * ## What this can and cannot see, stated plainly
 *
 * `edge-cases.md` section 9's own example sentence is *"SHP1015 was confirmed by another planner at
 * 09:58"* -- a fact about the **shipment**, not about the escalation.
 * `escalation_service.py::get_exception_queue` returns no shipment or appointment status
 * (its SELECT carries the escalation, its owner, its SLA and a `LEFT JOIN LATERAL` for the thread),
 * so that exact sentence cannot be produced from this read without a server-side change. It is not
 * approximated and it is not faked.
 *
 * What the read genuinely supports is every escalation-level fact below, which is all of section 2
 * and the part of section 9 that concerns the escalation's own lifecycle. The shipment-level half
 * of section 9 is a real remaining gap and is reported as one rather than papered over.
 */
export function describeEscalationChange(
  before: EscalationQueueItem,
  after: EscalationQueueItem,
  currentUserId: string | null,
): EscalationChange | null {
  const facts: string[] = []
  let race = false

  const byMe = (userId: string | null) => userId !== null && userId === currentUserId

  if (before.owner_user_id !== after.owner_user_id) {
    if (after.owner_user_id === null) {
      facts.push('Ownership was released — this escalation is unowned again.')
      race = true
    } else if (!byMe(after.owner_user_id)) {
      // Section 2's exact case: two coordinators acknowledged, one committed, and this client is
      // the loser. The winning owner is NAMED, which the section requires.
      facts.push(
        before.owner_user_id === null
          ? `${after.owner_name ?? 'Another coordinator'} acknowledged this escalation.`
          : `This escalation was reassigned to ${after.owner_name ?? 'another coordinator'}.`,
      )
      race = true
    }
  }

  if (before.escalation_status !== after.escalation_status) {
    facts.push(`Status changed to ${after.escalation_status.toLowerCase().replace(/_/g, ' ')}.`)
    if (after.escalation_status === 'RESOLVED' || after.escalation_status === 'CANCELLED') {
      race = true
    }
  }

  if (before.thread_status !== after.thread_status) {
    if (after.thread_status === 'ESCALATED') {
      facts.push('Someone took over this thread — the assistant is no longer answering it.')
      race = true
    } else if (before.thread_status === 'ESCALATED') {
      facts.push('This thread was handed back to the assistant.')
    }
  }

  if (facts.length === 0) return null
  return { escalationId: after.escalation_id, facts, race, atIso: after.updated_at }
}

/** The section 9 case the queue read *can* answer: the escalation stopped being returned at all
 *  while the coordinator had it open. Kept separate from `describeEscalationChange` because there
 *  is no "after" item to diff against. */
export function describeDisappearance(item: EscalationQueueItem): EscalationChange {
  return {
    escalationId: item.escalation_id,
    facts: [
      'This escalation is no longer in the open queue — it was resolved or cancelled elsewhere. Nothing you have typed has been sent.',
    ],
    race: true,
    atIso: item.updated_at,
  }
}

/**
 * A stable identity for one observed change, so the console can tell "the same fact, still true on
 * the next poll" from "a new fact".
 *
 * Needed for a concrete bug rather than for tidiness: a disappearance stays true on every
 * subsequent poll (the item never comes back), so without this a coordinator who dismisses the
 * notice would have it re-raised 15 seconds later, forever.
 */
export function changeKey(change: EscalationChange): string {
  return `${change.escalationId}|${change.atIso}|${change.facts.join('|')}`
}
