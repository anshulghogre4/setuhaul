/**
 * Driver-surface copy, externalised as keys (U31).
 *
 * `01-driver-chat/accessibility.md` ("Language and i18n readiness"):
 *   > All copy externalised as keys — **especially the state templates**, which are the most
 *   > painful to extract retroactively.
 *   > The highest-value future translation is the four state templates and the eight
 *   > negative-path messages. Those carry the promises.
 *
 * So this file is not a tidiness exercise; it is the thing that makes Hindi a translation job
 * rather than a rewrite. It is deliberately a flat object of functions/strings rather than an
 * i18n library: adding `i18next` for one locale would be infrastructure with no second locale
 * to justify it, and the shape here (keys in, string out) is what an i18n backend consumes when
 * one arrives.
 *
 * **Every string below is copied verbatim from `00-foundations/voice-and-tone.md`.** Where a
 * template interpolates, the parameter names match the fields the server actually returns. Two
 * of the refusals (safety, off-manifest cargo) are marked as reviewed wording in that file —
 * treat them as legal text, not copy to riff on.
 *
 * Mechanics the whole file obeys (`voice-and-tone.md` "Mechanics"): second person for the
 * driver, first person for the assistant, **never "we"**, 24-hour time, dates as `Tue 4 Aug`,
 * sentence case except the uppercase state chips, and never a shipment ID as the subject of a
 * sentence.
 */

export const copy = {
  /* ---- the four state templates -------------------------------------------------------- */

  /** "Nothing is held yet" is **mandatory and appears before the options, not after** — a
   *  driver who taps without reading must still not have been misled by what they skimmed. */
  shownLead: (count: number, facilityName: string) =>
    `${count === 1 ? 'One option is' : `${count} options are`} open right now at ${facilityName}.`,
  shownNothingHeld: 'Nothing is held yet — another driver can take any of these.',
  shownTapHint: 'Tap one to hold it for 90 seconds.',

  /** HELD — behind `heldStateEnabled` (#53). Kept here so the flag flip is a one-line change
   *  and not a copywriting exercise. */
  heldLead: (operationalLine: string) => `${operationalLine} is held for you.`,
  heldNotABooking: 'This is not a booking yet. Send it to the warehouse to request it.',
  heldRequestAction: 'Request this slot',
  heldChooseAnother: 'Choose a different one',

  pendingLead: (operationalLine: string) => `Requested: ${operationalLine}`,
  pendingDeadline: (decisionBy: string) =>
    `The warehouse has not confirmed this yet. A planner will decide by ${decisionBy}.`,
  pendingAfterDeadline:
    "If there's no decision by then, the slot is released and I'll find you fresh options.",

  /** The only sentence in the product permitted to say "confirmed". */
  confirmedLead: (operationalLine: string, facilityName: string) =>
    `Confirmed — ${operationalLine}, ${facilityName}`,
  confirmedReference: (reference: string) => `Reference ${reference}`,
  /** Arrival guidance comes from RULE001 (60-min early limit) and RULE002 (30-min no-show
   *  grace) — **real rules, never invented**. The caller passes the values the server gave it;
   *  this template never supplies a default, because a default here is a fabricated rule. */
  confirmedArrival: (checkInFrom: string, earlyLimitMin: number) =>
    `You may check in from ${checkInFrom} (${earlyLimitMin} minutes early limit).`,
  confirmedNoShow: (noShowAfter: string) =>
    `If you haven't checked in by ${noShowAfter}, the appointment may be marked no-show.`,

  /* ---- the eight negative paths -------------------------------------------------------- */

  holdLapsed: (operationalLine: string) =>
    `That hold has lapsed — ${operationalLine} is available to other drivers again. Nothing has been lost; I can look again right now.`,
  pendingExpired: (operationalLine: string) =>
    `No planner responded in time, so ${operationalLine} has been released. This has been escalated to operations, and I can look for fresh options now.`,
  /** **Never blames the driver for being slow.** State the fact, move to alternatives. */
  slotConflict: (operationalLine: string) =>
    `Another driver requested ${operationalLine} a moment before you. That one's gone — here's what's open now.`,
  optionWithdrawn: (dockCode: string, startTime: string, remainingCount: number) =>
    `Dock ${dockCode} has just gone out of service, so the ${startTime} option is no longer available. ${
      remainingCount === 1 ? 'The other option is' : `The other ${remainingCount} options are`
    } still open.`,
  noSameDaySlot: (facilityName: string, blockingReason: string) =>
    `Nothing works at ${facilityName} today — ${blockingReason}. The earliest I can offer is tomorrow.`,
  noSameDayEscalationOffer:
    "Nothing is held yet. If waiting overnight doesn't work, I'll bring in operations.",
  noFeasibleSlot: (facilityName: string, blockingReason: string, reference: string) =>
    `I can't find a workable slot for this load at ${facilityName} — ${blockingReason}. I've passed this to operations. Reference ${reference}. Someone will contact you directly.`,
  humanJoined: (name: string, team: string) => `${name} from ${team} has joined`,
  connectionLost: "You're offline. I'll send this as soon as you're back.",

  /* ---- refusals (U61) ------------------------------------------------------------------ */

  refuseJustConfirm:
    "Only a warehouse planner can confirm a slot — I can't skip that step. I can flag your request as urgent so it's reviewed first.",
  refuseFlagUrgentAction: 'Flag as urgent',
  refuseInfeasibleTime: (requested: string, etaTime: string) =>
    `${requested} won't work — your ETA is ${etaTime} and the unload needs to finish before the slot closes. Here's what does fit your arrival time:`,
  /** Reviewed wording. Do not edit without the owner. */
  refuseOffManifest:
    "That's not something I can schedule around — it needs a person to look at before anything else happens. I've flagged this to operations now.",
  /** Reviewed wording, and the highest-cost message in the product to get wrong. Always the
   *  first line, always this direct, always routes to a human immediately. */
  refuseSafety: (reference: string) =>
    `That's not a decision I can make for you. Please contact your carrier and pull over safely if you're not already stopped. Reference ${reference} has been raised with operations.`,
  refuseOtherDriversSlot: "I can't move another driver's booking. Here's what's actually open right now:",
  cancelledShipment:
    'That shipment and its appointment were cancelled. Please contact dispatch before travelling.',

  /* ---- clarification ------------------------------------------------------------------- */

  clarifyLowConfidenceEta: (arrivalTime: string) =>
    `Does that mean arriving at ${arrivalTime}, or another hour from where you are now?`,
  clarifyRiskAsChoice: (heldTime: string, cushionTime: string) =>
    `I can hold ${heldTime}, but if that time is uncertain, the ${cushionTime} window gives you an hour of cushion and avoids a second reschedule.`,
  /** Human descriptors, never IDs. */
  clarifyAmbiguousShipment: (descriptor: string, firstDue: string, secondDue: string) =>
    `You have two ${descriptor}s today. The one due ${firstDue}, or the later one due ${secondDue}?`,

  /* ---- empty, loading, error (U32) ----------------------------------------------------- */

  /** Two distinct empty states, and the distinction is a **server-side history check, never
   *  `count === 0`** (U74). Using one icon and one sentence for both would undercut the point. */
  emptyCaughtUpTitle: 'No active loads',
  emptyCaughtUpBody: "You'll see delays and slot changes here.",
  emptyNothingYetTitle: 'No loads assigned yet',
  /** Points at the TMS boundary without using the word "TMS" — a driver knows "dispatcher". */
  emptyNothingYetBody: "Your dispatcher assigns these — they'll appear here automatically.",

  threadLoadFailedTitle: "Couldn't load this conversation",
  threadLoadFailedBody: 'This is usually a connection problem.',
  retryAction: 'Retry',
  findOptionsAgainAction: 'Find options again',
  getHelpAction: "That doesn't work — get help",

  /** The clause is load-bearing, not padding. In a system where a tap commits capacity, a
   *  driver must know a failure left no partial state — otherwise the rational response is to
   *  tap again, which is what idempotency (U70) exists to survive. */
  commitFailed: "That didn't save. Nothing has changed.",
  messageNotSent: 'not sent',
  messageQueued: 'queued',

  eligibilityToolFailed: "Couldn't check that — try asking again.",

  /* ---- composer ----------------------------------------------------------------------- */

  /**
   * The only quick replies the client supplies, and they are supplied because
   * `confirmation_required` is the one branch where the two readings genuinely are closed and
   * generic ("do it" / "don't"). **Everything else is server-supplied or absent.**
   *
   * ⚠ Recorded gap: `done.data.confirmation` is the raw tool result
   * (`run_assistant.py` — a `CONFIRMATION_REQUIRED` / `PERSISTED` dict) and carries **no
   * suggested-reply strings at all**, so the question-specific pairs `voice-and-tone.md`'s
   * clarification table specifies ("Arriving 11:00" / "Might be longer", "Leave the gate" /
   * "Unloading starts") have no source. The component is built and wired; the feed is honestly
   * empty for those cases rather than filled with strings the assistant never offered. Filed as
   * a follow-up, not invented here — a quick reply sends its literal text as a driver message,
   * so a made-up chip puts words in the driver's mouth.
   */
  quickReplyConfirm: 'Yes, go ahead',
  quickReplyDecline: "No, don't",

  composerPlaceholder: 'Message',
  composerPlaceholderOffline: "Message · will send when you're back online",
  composerSendLabel: 'Send message',

  /* ---- system / connection ------------------------------------------------------------ */

  offlineCardReason: "Offline — can't select now",
  staleness: (minutes: number) => `updated ${minutes}m ago`,
  thinkingStillWorking: 'Still working on this…',
  thinkingReducedMotion: 'Working…',
  scrollToLatest: (newCount: number) => `${newCount} new`,

  /* ---- push (screens 14A / 14B) ------------------------------------------------------- */

  pushPrimingTitle: 'Get told when your slot changes',
  pushPrimingBody:
    "A planner can confirm, reject or release your slot while you're driving. Turn on notifications and I'll tell you the moment it happens — you won't need to keep this page open.",
  pushPrimingEnable: 'Turn on notifications',
  pushPrimingNotNow: 'Not now',
  /** The consequence is stated **once**, plainly, and then not nagged. Re-ask only after a
   *  genuinely missed event (`edge-cases.md` section 14). */
  pushDeniedStatus:
    "Notifications are off — you'll need to keep this page open to see changes.",
  pushDeniedReentry: 'You can turn them on from Profile at any time.',

  /* ---- state line (`01-driver-chat/components.md` section 6) --------------------------- */

  stateLineShown: 'Options open · nothing held',
  stateLineHeld: 'HELD',
  /** **Never abbreviated.** If it does not fit, the container is too small
   *  (`00-foundations/components.md` section 2). */
  stateLinePending: (decisionBy: string) => `PENDING · decision by ${decisionBy}`,
  stateLineConfirmed: (operationalLine: string) => `CONFIRMED · ${operationalLine}`,

  /* ---- contextual help on state (U73 — the driver's entire help surface) --------------- */

  helpShown:
    "These are open right now but not reserved. Another driver can take any of them until you hold one.",
  helpHeld:
    "Held means this slot is reserved for you for 90 seconds. It's not booked yet — send it to the warehouse to request it.",
  helpPending:
    "You've asked for this slot. A warehouse planner has to agree before it's yours; if nobody decides in time it's released and I'll look again.",
  helpConfirmed: 'This is agreed. Arrive in the window shown and check in at the gate.',

  /* ---- navigation --------------------------------------------------------------------- */

  navThreads: 'Threads',
  navProfile: 'Profile',
  backToThreads: 'Back to loads',
  resolvedDivider: 'Resolved',
  signOut: 'Sign out',
} as const
