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
 * **`HELD` is designed but not servable** — see `flags.ts` / issue #53. It stays in the union
 * because the chip, the countdown and the option card all have a specified `HELD` treatment
 * that is built and unit-renderable; what is gated is any code path that could *put* a real
 * appointment into it.
 */
export type PromiseState = 'SHOWN' | 'HELD' | 'PENDING_CONFIRMATION' | 'CONFIRMED'

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

/** The eight option-card treatments (`01-driver-chat/components.md` section 2). */
export type OptionCardState =
  | 'default'
  | 'pressed'
  | 'committing'
  /** Behind `heldStateEnabled` — issue #53. */
  | 'held'
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
