import type {
  DriverMessage,
  DriverOption,
  DriverThread,
  EligibilityAnswer,
  OptionSet,
} from '../lib/types'

/**
 * Render fixtures for `/driver/_states`. **Gallery-only — nothing in the shipped surface imports
 * this file** (the same discipline E5.0's `features/gallery/fixtures.ts` keeps).
 *
 * Values are the seeded cast from `SOLUTION_DESIGN.md` section 9.2 and the mockup's own
 * artboards, so a plate matches the reference board rather than showing invented data. Times are
 * fixed rather than relative so two runs of the gallery are comparable.
 *
 * `expiresAt` values are computed at module load, once, relative to now — a hold has to actually
 * be running for the countdown bands, the pulse and the expiry replacement to be observable,
 * which is what makes R2/R3/R4/R5 regression-testable rather than assertions in a document.
 */

const now = Date.now()
const iso = (offsetMs: number) => new Date(now + offsetMs).toISOString()

/** 46 seconds into a 90-second hold: past the 50% band, before the 20% one. */
export const HELD_MID = iso(44_000)
/** 9 seconds left: the `<10s` band, weight 600, pulsing, haptics fired. */
export const HELD_FINAL = iso(9_000)
/** Already gone: the expiry state must REPLACE the numeric in place, not remove it (R3). */
export const HELD_EXPIRED = iso(-1_000)
/** 12 minutes into a 15-minute pending window. */
export const PENDING_LIVE = iso(720_000)

/**
 * Ungated band probes.
 *
 * R2 / R3 / R4 are the three defects that **only appear when the component actually runs**, and
 * the spec is explicit that they are regression tests rather than one-off fixes. But every `HELD`
 * plate is behind `heldStateEnabled` (issue #53), so with the flag off there would be nothing
 * left to observe them on.
 *
 * `PENDING_CONFIRMATION` carries a mandatory countdown too, and `components.md` section 3's band
 * table applies to it identically — the **only** HELD-specific row is the border pulse. So these
 * four probes give a real, ungated way to watch the 20–50% band fire, the `<20%` weight change,
 * and the expiry state **replace** the numeric in place, using the same
 * `usePromiseCountdown` the HELD path uses.
 *
 * Offsets are against a 15-minute (900 s) total.
 */
export const PENDING_TOTAL_MS = 900_000
/** 70% — rest band, the state's own text colour. */
export const BAND_REST = iso(630_000)
/** 40% — the amber `--color-urgent-mid` band (R2: never fired in the mockup). */
export const BAND_MID = iso(360_000)
/** 15% — red, weight 600. */
export const BAND_URGENT = iso(135_000)
/** 8 s — the final band. Short on purpose so a live watch reaches expiry inside ten seconds. */
export const BAND_FINAL = iso(8_000)
/** Already past. R3: the component must be REPLACED in place by the expiry state, never removed
 *  and never restarted (the mockup looped back to max). */
export const BAND_EXPIRED = iso(-2_000)

export const OPTIONS: DriverOption[] = [
  {
    slotId: 'SLOT-D4-1215',
    dockId: '11111111-1111-1111-1111-111111111111',
    dockCode: 'D4',
    slotLocalDate: '2026-08-04',
    feasibleStartTs: '2026-08-04T06:45:00+00:00',
    feasibleEndTs: '2026-08-04T08:00:00+00:00',
    // The three labels are the CLOSED server vocabulary from
    // feasibility.assign_differentiators -- not strings this file chose.
    differentiator: 'soonest',
    recommendationId: 'REC-GALLERY-1',
    optionStatus: 'DISPLAYED_NOT_RESERVED',
  },
  {
    slotId: 'SLOT-D1-1300',
    dockId: '22222222-2222-2222-2222-222222222222',
    dockCode: 'D1',
    slotLocalDate: '2026-08-04',
    feasibleStartTs: '2026-08-04T07:30:00+00:00',
    feasibleEndTs: '2026-08-04T08:45:00+00:00',
    differentiator: 'no waiting',
    recommendationId: 'REC-GALLERY-1',
    optionStatus: 'DISPLAYED_NOT_RESERVED',
  },
  {
    slotId: 'SLOT-D2-1430',
    dockId: '33333333-3333-3333-3333-333333333333',
    dockCode: 'D2',
    slotLocalDate: '2026-08-04',
    feasibleStartTs: '2026-08-04T09:00:00+00:00',
    feasibleEndTs: '2026-08-04T10:15:00+00:00',
    // Empty string on purpose: this is the U81 case the option card must render as an OMITTED
    // line, not as a blank row. `assign_differentiators` genuinely leaves options unlabelled
    // when no label in the vocabulary is true of them.
    differentiator: '',
    recommendationId: 'REC-GALLERY-1',
    optionStatus: 'DISPLAYED_NOT_RESERVED',
  },
]

export const FEASIBLE_SET: OptionSet = {
  recommendationId: 'REC-GALLERY-1',
  outcome: 'FEASIBLE',
  options: OPTIONS,
  escalationReference: null,
  policyVersion: 'sprint3_constraints_v1',
  setState: 'active',
}

/** Screen 19. **The date is load-bearing** — these are tomorrow's slots and a driver reading
 *  "06:00" as this morning has been mis-promised by formatting. */
export const TOMORROW_SET: OptionSet = {
  ...FEASIBLE_SET,
  outcome: 'NO_SAME_DAY_SLOT',
  options: OPTIONS.slice(0, 2).map((o) => ({ ...o, slotLocalDate: '2026-08-05' })),
}

/** Screen 20. No cards, no retry — a reference and a promise of contact. */
export const ESCALATED_SET: OptionSet = {
  recommendationId: 'REC-GALLERY-2',
  outcome: 'NO_FEASIBLE_SLOT',
  options: [],
  escalationReference: 'ESC-4471',
  policyVersion: 'sprint3_constraints_v1',
  setState: 'active',
}

export const ELIGIBILITY_PASS: EligibilityAnswer = {
  slotId: 'SLOT-D4-1215',
  dockCode: 'D4',
  subject: '32-foot vehicle',
  eligible: true,
  rows: [
    { constraintId: 'dock_vehicle_compatibility', label: 'Vehicle fits the dock', passed: true },
    { constraintId: 'slot_capacity_available', label: 'Slot has capacity', passed: true },
    { constraintId: 'dock_operational', label: 'Dock active', passed: true },
    { constraintId: 'arrival_before_slot_end', label: 'Arrival fits the slot', passed: true },
  ],
  verdict: 'Yes — this slot accepts your truck',
}

export const ELIGIBILITY_FAIL: EligibilityAnswer = {
  slotId: 'SLOT-D5-1800',
  dockCode: 'D5',
  subject: 'Reefer load',
  eligible: false,
  rows: [
    { constraintId: 'dock_vehicle_compatibility', label: 'Vehicle fits the dock', passed: true },
    {
      constraintId: 'dock_operational',
      label: 'Dock active',
      passed: false,
      detail: 'D5 is under maintenance 18:00–22:00 (RULE003 pins reefer loads to D5 only)',
    },
    { constraintId: 'arrival_before_slot_end', label: 'Arrival fits the slot', passed: true },
  ],
  verdict: 'No — this slot will not work for this load',
}

export const THREADS: DriverThread[] = [
  {
    threadId: 'THR-KOTA',
    shipmentId: 'SHP1004',
    descriptor: 'Kota load → IndustrialHub',
    orderReference: 'ORD-260804-004',
    priority: 'CRITICAL',
    promiseState: 'PENDING_CONFIRMATION',
    expiresAt: PENDING_LIVE,
    ttlMs: 900_000,
    operationalLine: 'Dock D1 · Tue 4 Aug · 13:00 – 14:15',
    lastMessagePreview: 'The warehouse hasn’t decided yet…',
    lastActivityAt: iso(-9 * 60_000),
    resolved: false,
    unread: true,
  },
  {
    threadId: 'THR-NEEMRANA',
    shipmentId: 'SHP1017',
    descriptor: 'Neemrana load → RajRetail',
    orderReference: 'ORD-260804-017',
    priority: 'HIGH',
    promiseState: 'SHOWN',
    operationalLine: null,
    lastMessagePreview: 'Three options are open right now…',
    lastActivityAt: iso(-26 * 60_000),
    resolved: false,
    unread: false,
  },
  {
    threadId: 'THR-JODHPUR',
    shipmentId: 'SHP1002',
    descriptor: 'Jodhpur load → HomeCraft',
    orderReference: 'ORD-260803-002',
    priority: 'NORMAL',
    promiseState: 'CONFIRMED',
    operationalLine: 'Dock D3 · Mon 3 Aug · 09:00 – 10:15',
    lastMessagePreview: null,
    lastActivityAt: iso(-26 * 60 * 60_000),
    resolved: true,
    unread: false,
  },
]

const at = (offsetMinutes: number) => iso(offsetMinutes * 60_000)

export const TRANSCRIPT: DriverMessage[] = [
  {
    id: 'm1',
    tier: 'DRIVER',
    createdAt: at(-14),
    parts: [{ kind: 'text', text: 'Traffic after Shahpura. Reaching around 11:20.' }],
    delivery: 'delivered',
  },
  {
    id: 'm2',
    tier: 'AGENT',
    createdAt: at(-13),
    parts: [
      {
        kind: 'text',
        text: 'Your current slot is 10:00–11:00 at Jaipur DC. Three options are open right now. Nothing is held yet.',
      },
      { kind: 'optionSet', optionSet: FEASIBLE_SET },
    ],
  },
]

/** Screen 8's third tier plus the permanent takeover divider. */
export const TAKEOVER_TRANSCRIPT: DriverMessage[] = [
  ...TRANSCRIPT,
  {
    id: 'm3',
    tier: 'SYSTEM',
    createdAt: at(-4),
    parts: [],
    notice: { variant: 'takeover', code: 'HUMAN_JOINED', body: 'Neha from Operations has joined' },
  },
  {
    id: 'm4',
    tier: 'OPERATIONS',
    createdAt: at(-3),
    parts: [{ kind: 'text', text: 'Hi — I’m looking at your reefer load now.' }],
    author: { name: 'Neha', role: 'Operations', initials: 'N' },
  },
]
