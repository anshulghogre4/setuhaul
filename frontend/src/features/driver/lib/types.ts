/**
 * Driver-surface domain types.
 *
 * **Every field here is read off a live server shape, not invented.** Where the server has no
 * field for something the design asks for, the type says so in a comment rather than adding an
 * optimistic property that nothing can ever fill (`00-foundations/data-formatting.md`'s
 * blank-vs-zero rule, U81: a gap is a real answer, a fabricated value is not).
 *
 * Sources, verified 2026-08-27:
 *   - `FeasibleSlotOption` / `FeasibleSlotsResult` — `backend/app/scheduling/feasibility.py`
 *   - `SlotEligibilityResult`                     — same file
 *   - SSE frames + `done.data`                    — `backend/app/assistant/run_assistant.py`,
 *                                                   `backend/app/api/v1/routers/chat.py`
 *   - `/api/v1/driver/context`                    — `backend/app/services/driver_reads.py`
 */

/* ------------------------------------------------------------------------------------------
   Promise state
   ------------------------------------------------------------------------------------------ */

/**
 * The four designed promise states (`00-foundations/components.md` section 2).
 *
 * **`HELD` is servable since 2026-08-31** (issues #53/#83/#86): a hold is a `dock_occupancy` row
 * with a NULL `appointment_id`, and `holds.live_hold_for_shipment` is what makes it readable. It
 * arrives on `/driver/context` as `promise_state: 'HELD'` with `promise_state_source:
 * 'dock_occupancy_hold'`, and from `request_slot`'s HELD outcome inside a turn.
 *
 * `SHOWN` remains a **client-side** state and always was: it is what an option set on screen means,
 * and `find_feasible_slots` reserves nothing and writes no row. Nothing on the wire can say it.
 */
export type PromiseState = 'SHOWN' | 'HELD' | 'PENDING_CONFIRMATION' | 'CONFIRMED'

/**
 * A live D2 hold, as every driver-facing read reports it.
 *
 * One shape for three producers, which is the point: `holds.live_hold_for_shipment` (behind
 * `/driver/context`'s `current_hold` and `get_appointment_request_status`'s `hold`) and
 * `request_slot`'s HELD outcome all name the same fields, so `mappers.ts` has one function rather
 * than three near-copies that could drift about which field the countdown reads.
 *
 * **`expiresAt` is the server's own `expires_at` and is the countdown's only legitimate source.**
 * A client that computed `now + 90s` on receipt would be asserting a deadline the server never
 * gave, and would drift by exactly the round-trip time — in the wrong direction, since it would
 * show time the driver does not have.
 */
export type DriverHold = {
  holdId: string
  shipmentId: string
  slotId: string | null
  dockCode: string | null
  /** ISO, server-stamped. */
  expiresAt: string
  /**
   * The server's own remaining-seconds reading at the moment it answered, computed against the
   * same `now` the row was filtered with (`holds.live_hold_for_shipment`). Carried but **not** used
   * to drive the countdown: the countdown runs off `expiresAt` reconciled through the shared
   * clock's measured offset, which stays correct as the seconds pass. This value is a receipt of
   * what the server believed at answer time, useful for a staleness check, and is deliberately not
   * a second source of truth to tick from (R4's lesson: one rule, no possible disagreement).
   */
  expiresInSeconds: number | null
  windowStart: string | null
  windowEnd: string | null
}

/** Priority ramp for the thread card's 3px left marker (`components.md` section 5, U10).
 *  Values are `shipments.priority_code` verbatim. */
export type PriorityCode = 'CRITICAL' | 'HIGH' | 'NORMAL' | 'LOW'

/* ------------------------------------------------------------------------------------------
   Option cards
   ------------------------------------------------------------------------------------------ */

/**
 * One option card's data, mapped 1:1 from `FeasibleSlotOption`.
 *
 * `dockCode` not `dockId`, and `slotLocalDate` **not** the date component of `slotStartTs`:
 * the ISO timestamps carry a UTC offset, so `2026-08-16T19:00+00:00` is 17 Aug in
 * `Asia/Kolkata`. The backend added `slot_local_date` for exactly this and says so inline.
 * Using the wrong one is a literal wrong-day booking.
 */
export type DriverOption = {
  slotId: string
  dockId: string
  dockCode: string
  /** Facility-local calendar date, `YYYY-MM-DD`. The load-bearing field on screen 19. */
  slotLocalDate: string
  feasibleStartTs: string
  feasibleEndTs: string
  /**
   * The server-computed comparative label — `soonest` / `no waiting` / `most buffer`, or `''`.
   *
   * E5.1 Fork A, landed in `feasibility.assign_differentiators`. **`''` means omit the line**,
   * not render an empty row: no label in the closed vocabulary was true of this option, and
   * inventing a fourth phrase is what U48 exists to prevent (the interface renders receipts,
   * it never reasons about ranking).
   */
  differentiator: string
  /** Carried, never displayed. U16: no ordinal reaches the DOM. */
  recommendationId: string
  /** Always `'DISPLAYED_NOT_RESERVED'` from `find_feasible_slots`. The server is explicit that
   *  display reserves nothing — this *is* `SHOWN`. */
  optionStatus: string
}

/**
 * The option-card treatments (`01-driver-chat/components.md` section 2).
 *
 * `lapsed` is **not** in that section's table and is added deliberately, from `stitch-prompts.md`
 * §15 (screen 15, `HOLD_LAPSED`), which specifies the treatment precisely: *"same position, same
 * size. Dock line and time line struck through, card at 40% opacity, 1px border (the dashed amber
 * is gone), status line reading 'Hold lapsed'."* That is the `lost`/`withdrawn` shape with its own
 * copy, and it needs its own value rather than reusing one of theirs because the status line is the
 * whole signal: "Taken by another driver" and "Hold lapsed" are different facts, and §15 is
 * explicit that the card must **never** be removed, because *"a driver who looks up to find their
 * option simply gone learns nothing and trusts less."*
 */
export type OptionCardState =
  | 'default'
  | 'pressed'
  | 'committing'
  /** Behind `heldStateEnabled` — issue #53. */
  | 'held'
  /** Screen 15. Behind `heldStateEnabled`, since only a held card can lapse. */
  | 'lapsed'
  | 'lost'
  | 'withdrawn'
  | 'offline'
  | 'superseded'

/** Stage 0's outcome split. **Branch on this, never on `escalation === null`** — the backend
 *  says so inline: `NO_SAME_DAY_SLOT` returns options *and* no escalation. */
export type SlotOutcome = 'FEASIBLE' | 'NO_SAME_DAY_SLOT' | 'NO_FEASIBLE_SLOT'

/** `find_feasible_slots`'s tool result, as the option-set card renders it. */
export type OptionSet = {
  recommendationId: string
  outcome: SlotOutcome
  options: DriverOption[]
  /** Screen 20's `ESC-…`. Present only on `NO_FEASIBLE_SLOT`. */
  escalationReference: string | null
  /** `components.md` section 4: always stamp the policy version on a receipt. */
  policyVersion: string
  /** Set-level state, so a superseded set greys as a whole (`components.md` section 2). */
  setState: 'active' | 'superseded'
  /** Per-slot overrides for U50's mutate-in-place: only the affected card changes. */
  perOption?: Partial<Record<string, OptionCardState>>
}

/* ------------------------------------------------------------------------------------------
   Eligibility (screens 12A / 12B)
   ------------------------------------------------------------------------------------------ */

export type EligibilityRow = {
  /** A `feasibility_hard_constraints[].id` from `backend/app/scheduling/constraints.json`. */
  constraintId: string
  label: string
  passed: boolean
  /** Only on a failing row: the server's own `message` / `explanation` lines. */
  detail?: string
}

export type EligibilityAnswer = {
  slotId: string
  dockCode: string
  /** Short subject line — "32-foot vehicle", "Reefer load". Server-sourced or omitted. */
  subject?: string
  eligible: boolean
  rows: EligibilityRow[]
  /** Templated, never model-composed (`components.md` section 8). */
  verdict: string
}

/* ------------------------------------------------------------------------------------------
   Transcript
   ------------------------------------------------------------------------------------------ */

/** U47's three tiers plus the centred system tier. Maps from `chat_messages.sender_type`. */
export type SenderTier = 'DRIVER' | 'AGENT' | 'OPERATIONS' | 'SYSTEM'

/** `01-driver-chat/components.md` section 4. `queued` is words, not a glyph, so it cannot be
 *  mistaken for sent. */
export type DeliveryStatus = 'sending' | 'sent' | 'delivered' | 'queued' | 'failed'

/** System-notice variants (`components.md` section 5). `takeover` draws the permanent divider;
 *  `event` pairs with a card mutating in place (U50); `connection` adds the `wifi-off` icon. */
export type SystemNoticeVariant = 'takeover' | 'event' | 'connection'

/**
 * The event vocabulary the negative-path screens render. Each maps to one screen in
 * `01-driver-chat/edge-cases.md`, and each maps to `voice-and-tone.md` copy via
 * `copy.ts` — never to a sentence assembled at the call site.
 */
export type DriverEventCode =
  | 'HOLD_LAPSED' /* screen 15 — behind heldStateEnabled (#53) */
  | 'PENDING_EXPIRED' /* screen 16A */
  | 'SLOT_CONFLICT' /* screen 17 */
  | 'OPTION_WITHDRAWN' /* screen 18 */
  | 'HUMAN_JOINED' /* screen 21 */
  | 'CONNECTION_LOST' /* screen 24 */
  | 'COMMIT_FAILED' /* screen 27B */

/** A message part. Text and structured parts are siblings, never one parsed out of the other
 *  (U48 — the whole reason `MessagePartPrimitive` is the binding target). */
export type DriverPart =
  | { kind: 'text'; text: string }
  | { kind: 'optionSet'; optionSet: OptionSet }
  | { kind: 'eligibility'; answer: EligibilityAnswer }
  | { kind: 'receipt'; policyVersion: string; lines: string[] }

export type DriverMessage = {
  id: string
  tier: SenderTier
  /** Wall-clock ISO. Rendered through `Intl` with `en-IN`, never a hand-built string. */
  createdAt: string
  parts: DriverPart[]
  /** Driver messages only. */
  delivery?: DeliveryStatus
  /** `OPERATIONS` / `WAREHOUSE` tier only — real name + role, never "Agent". */
  author?: { name: string; role: string; initials: string }
  /** `SYSTEM` tier only. */
  notice?: { variant: SystemNoticeVariant; code?: DriverEventCode; body: string }
  /** Set on a driver message that failed, so Retry can resend it byte-identically with the
   *  same `client_message_id` (U70 — this is what makes screen 27A safe). */
  clientMessageId?: string
}

/** `done.data.ux_state`, verbatim from `run_assistant.py`. **This is the branch key, not the
 *  prose.** */
export type UxState =
  | 'chat'
  | 'confirmation_required'
  | 'clarification_required'
  | 'capability_not_enabled'
  | 'persisted_success'

/* ------------------------------------------------------------------------------------------
   Thread list
   ------------------------------------------------------------------------------------------ */

export type DriverThread = {
  threadId: string
  shipmentId: string
  /**
   * Human descriptor — "Kota load → IndustrialHub". **Never the shipment ID**
   * (`voice-and-tone.md`).
   *
   * ⚠ `GET /api/v1/driver/context` does **not** return the two fields this is built from:
   * its `shipments[]` projection has no `origin_city` and no destination facility *name*
   * (only `destination_facility_id`). Verified against
   * `backend/app/repositories/drivers.py::load_driver_operational_snapshot`. See
   * `data.ts` for how that is handled honestly rather than papered over.
   */
  descriptor: string
  orderReference: string
  priority: PriorityCode | null
  /** `null` when the thread has no active promise — the state line hides entirely. */
  promiseState: PromiseState | null
  /** ISO. Present only for the two states that carry a countdown. */
  expiresAt?: string
  /** Total TTL in ms, for the countdown's threshold bands. 90_000 for HELD, 900_000 for
   *  PENDING_CONFIRMATION (D2 / D9). */
  ttlMs?: number
  /** Dock + dated range, always together, never a bare time (`voice-and-tone.md`). */
  operationalLine: string | null
  /** One truncated line. `null` when the server has no message to preview (see `data.ts`). */
  lastMessagePreview: string | null
  lastActivityAt: string
  resolved: boolean
  unread: boolean
}
