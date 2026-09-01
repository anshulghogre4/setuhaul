import { memo } from 'react'
import { ArrowUpRight, Check, CircleAlert, Pause, Repeat, TriangleAlert, X } from 'lucide-react'

import { useCountdown } from '@/shared/lib/countdown'
import { cn } from '@/shared/lib/utils'
import {
  TTL_BAND_CLASS,
  describeDisplacement,
  formatInterval,
  formatLimit,
  priorityMarkerClass,
  ttlBand,
} from '../lib/format'
import { plannerConfirmEnabled, plannerCounterOfferEnabled, plannerHoldEnabled } from '../lib/flags'
import type { PlannerRefusal } from '../lib/refusals'
import type { BulkConfirmOutcome, PlannerQueueRow } from '../lib/types'
import { describePredicates } from '../lib/reasons'

/**
 * The 30-second row (`components.md` section 1, `screens.md` section 2, `SOLUTION_DESIGN.md`
 * section 7.3). Nine columns for section 7.3's seven fields plus selection and actions.
 *
 * Three rules from the design are load-bearing here and are implemented rather than hoped for:
 *
 *  1. **The displacement cell never truncates** (`components.md` section 1) -- it wraps, and it is
 *     the one place a full sentence replaces terse fragments, because it describes harm to a third
 *     party. Every other cell may ellipsise; this one may not.
 *  2. **The five affordances render always-visible, never hover-revealed** -- a hover-only reveal
 *     costs a discovery step the 30-second budget cannot spare, and gives the keyboard path
 *     (`C`/`R`/`O`/`H`/`E`) nothing.
 *  3. **Safer-action-first DOM order (U79)** -- Reject is emitted *before* Confirm in source
 *     order regardless of visual placement, matching `components.md` section 2 and the mockup's
 *     own `.actgrp.destr` / `.actgrp.primary` split.
 *
 * A refusal renders **in place and keeps the row's position** (`mockup.html` State 8's note:
 * *"nothing fades out and nothing is removed under the planner's cursor"*).
 */

const ROW_ACTION_TITLE = {
  confirm:
    'Confirm is not available yet — see features/planner/lib/flags.ts (plannerConfirmEnabled).',
  hold: 'Hold for information is switched off in this build — see features/planner/lib/flags.ts (plannerHoldEnabled).',
  /** The one-shot cap, stated as the fact it is rather than as a failure. `edge-cases.md` #6. */
  holdUsed:
    'Already held once — a request’s D9 deadline can only be extended a single time, and this one’s extension has been used.',
  escalate:
    'Escalate is not available yet — section 7.5.1’s escalate_request(appointment_id, reason) does not exist. The shipped POST /operations/escalate needs an escalation_type from a fixed vocabulary that has no value for “a planner needs help deciding this request”, and it would not remove the row from this queue the way Flow 5 requires.',
  counterOffer:
    'Counter-offer is not available yet — see features/planner/lib/flags.ts (plannerCounterOfferEnabled).',
}

export type QueueRowProps = {
  row: PlannerQueueRow
  /** From `PlannerQueue.ttl_minutes` -- the D9 total the countdown bands are a fraction of.
   *  Passed down rather than re-declared, so the row cannot disagree with the server's clock. */
  ttlTotalMs: number
  focused: boolean
  selected: boolean
  busy: boolean
  /** Null when this row is not part of the client-visible ineligible set; a sentence naming the
   *  failing predicate otherwise. Advisory only -- the server re-checks all five at press time. */
  selectionCaveat: string | null
  refusal: PlannerRefusal | null
  outcome: BulkConfirmOutcome | null
  /** Arrived since the planner last let the list settle. Drives `motion.md`'s single 200ms arrival
   *  flash and, under `prefers-reduced-motion`, the persistent "New" badge that replaces it. */
  arrived?: boolean
  /**
   * The server stopped returning this row while the sort was frozen -- confirmed, rejected or
   * expired by somebody else. `edge-cases.md` #1 and `02-ops-exception-console/edge-cases.md`
   * section 2 both require the row to update **in place** rather than be removed and re-inserted;
   * it leaves on the next re-sort, which is a moment the planner chose.
   *
   * `announce` is the politeness decision and it belongs to the caller, because it turns on which
   * row has focus (`accessibility-behaviour.md`'s matrix): `assertive` for the focused row, silent
   * for every other one.
   */
  vanished?: { announce: boolean } | null
  onFocusRow: () => void
  onToggleSelect: () => void
  onConfirm: () => void
  onReject: () => void
  onCounterOffer: () => void
  /** Flow 4. Optional so the gallery's `RowPlate` can mount a row with no write path at all. */
  onHold?: () => void
}

export const QueueRow = memo(function QueueRow({
  row,
  ttlTotalMs,
  focused,
  selected,
  busy,
  selectionCaveat,
  refusal,
  outcome,
  arrived = false,
  vanished = null,
  onFocusRow,
  onToggleSelect,
  onConfirm,
  onReject,
  onCounterOffer,
  onHold = () => {},
}: QueueRowProps) {
  // One shared 1 Hz tick for every row (`shared/lib/countdown.tsx`) -- 35 pending rows must not
  // run 35 timers, and the reading is computed from *server* time via the measured offset the
  // queue's own `as_of` feeds in. Offline it holds at last-known rather than free-running.
  const countdown = useCountdown(row.ttl.deadline_ts, ttlTotalMs)
  const band = ttlBand(countdown.remainingMs, ttlTotalMs)
  const limit = row.latest_acceptable_ts ? formatLimit(row.latest_acceptable_ts) : null
  const etaLow = (row.eta.confidence ?? '').toUpperCase() === 'LOW'

  // A refused or already-actioned row cannot be acted on again from here. Everything else stays
  // live: `SNAPSHOT_STALE` explicitly leaves the row actionable after a re-read (edge-cases #2 --
  // "costs one extra glance, not a false confirm").
  const terminal =
    refusal?.kind === 'ALREADY_ACTIONED' || outcome?.code === 'ALREADY_ACTIONED' || vanished !== null
  const struck = terminal || countdown.expired

  return (
    <>
      <tr
        // The roving-focus handler in `queue-tab.tsx` finds a row by this attribute, so it lives
        // on the element that actually takes focus rather than on a wrapper.
        data-appointment={row.appointment_id}
        tabIndex={focused ? 0 : -1}
        onFocus={onFocusRow}
        data-focused={focused || undefined}
        data-selected={selected || undefined}
        aria-selected={selected}
        className={cn(
          'border-b border-border align-top outline-none',
          selected && 'bg-selected',
          focused && 'ring-2 ring-ring ring-inset',
          terminal && 'opacity-80',
          // One 200ms play, never looping, and only on a row that is genuinely new -- a settled row
          // must not re-highlight when the list re-renders (`stitch-prompts.md` section 4).
          arrived && 'animate-row-flash',
        )}
      >
        {/* Selection + the priority marker as the row's left edge (screens.md section 2). The
            marker is a value ramp, never a hue (U10). */}
        <td className="relative py-1.5 pr-1 pl-3">
          <span
            aria-hidden="true"
            className={cn(
              'absolute inset-y-0 left-0 w-1',
              priorityMarkerClass(row.receipt.priority_code),
            )}
          />
          <label
            className="flex size-8 cursor-pointer items-center justify-center"
            title={selectionCaveat ?? undefined}
          >
            <input
              type="checkbox"
              checked={selected}
              disabled={terminal || busy}
              onChange={onToggleSelect}
              // R21: 21 of 30 checkboxes in the mockup had no accessible name, on the surface
              // whose throughput feature *is* selection. Named from the shipment and the driver.
              aria-label={`Select ${row.shipment_id}${row.driver_name ? ` — ${row.driver_name}` : ''}`}
              className="size-4 accent-primary"
            />
          </label>
        </td>

        <td className="px-2 py-1.5 text-supporting">
          <span className="block truncate text-foreground">
            {row.driver_name ?? row.driver_id ?? '—'}
            {/* The reduced-motion REPLACEMENT for the arrival flash, not an addition to it:
                `styles/theme.css` hides `.row-arrival-badge` by default and reveals it only under
                `prefers-reduced-motion: reduce`. Real markup rather than CSS `content`, so a screen
                reader can reach it and it carries no untranslatable literal in a stylesheet. */}
            {arrived ? (
              <span className="row-arrival-badge ml-1 rounded bg-info-bg px-1 text-micro font-semibold text-info-fg">
                New
              </span>
            ) : null}
          </span>
          <span className="block truncate text-muted-foreground" title={row.carrier_name ?? undefined}>
            {row.carrier_name ?? '—'}
          </span>
        </td>

        <td className="px-2 py-1.5">
          <span
            translate="no"
            data-numeric
            className={cn('font-mono text-supporting tabular-nums', struck && 'line-through')}
          >
            {formatInterval(row)}
          </span>
          {/* `interval_source` is surfaced, not hidden: "appointment_slot_derived" means this row
              holds no dock_occupancy claim and the window was recomputed, which is a materially
              weaker fact than D1's own authority answering. */}
          {row.interval_source !== 'dock_occupancy' ? (
            <span
              className="block text-micro text-subtle-foreground"
              title="This appointment holds no dock_occupancy claim; the interval was derived from its slot."
            >
              derived interval
            </span>
          ) : null}
        </td>

        <td className={cn('px-2 py-1.5 text-supporting', struck && 'line-through')}>
          {row.receipt.text}
        </td>

        {/* Section 7.3's single most important field. Never truncated -- no `truncate`, no
            `line-clamp`, wraps instead. When a confirm was refused for displacement the SERVER's
            conflict set replaces the row's own, because the two are not the same set. */}
        <td className="px-2 py-1.5 text-supporting">
          {refusal?.kind === 'DISPLACEMENT_DETECTED' ? (
            <span className="flex items-start gap-1.5 text-danger-fg" role="alert">
              <CircleAlert className="mt-px size-3.5 shrink-0" aria-hidden="true" />
              <span>{refusal.message}</span>
            </span>
          ) : row.displacement.status === 'CONFLICT' ? (
            <span className="flex items-start gap-1.5 text-warning-fg">
              <TriangleAlert className="mt-px size-3.5 shrink-0" aria-hidden="true" />
              <span>{describeDisplacement(row)}</span>
            </span>
          ) : (
            <span className="text-muted-foreground">conflicts with none</span>
          )}
        </td>

        {/* ETA confidence: LOW is a rendered WARNING, not a value (components.md section 1 --
            "the rule 'do not confirm without asking' needs to be visible at a glance"). */}
        <td className="px-2 py-1.5 text-supporting">
          {etaLow ? (
            <span className="inline-flex items-center gap-1 text-warning-fg">
              <TriangleAlert className="size-3.5 shrink-0" aria-hidden="true" />
              LOW
            </span>
          ) : (
            <span className="text-muted-foreground">{row.eta.confidence ?? '—'}</span>
          )}
        </td>

        <td className="px-2 py-1.5">
          {limit ? (
            <span
              data-numeric
              title={limit.title}
              className={cn(
                'font-mono text-supporting tabular-nums',
                // The driver's own limit as a RULE, not just a column (screens.md section 2):
                // confirming past it creates a new exception, so a breach is coloured.
                row.latest_acceptable_breached ? 'text-danger-fg font-semibold' : 'text-foreground',
              )}
            >
              {limit.text}
            </span>
          ) : (
            // Three-valued: no limit on file is not the same as "we could not check".
            <span className="text-subtle-foreground" title="No latest-acceptable time on file.">
              —
            </span>
          )}
        </td>

        <td className="px-2 py-1.5">
          {/**
           * Issue #64's held treatment, and the one place this surface knowingly departs from
           * `00-foundations/components.md` §3 (U67). Read the reason before "fixing" it.
           *
           * **U67 specifies a PAUSE**: pause icon, colour off the amber->red urgency scale, and the
           * numeric value *"freezes and hides -- replaced by the reason text, not a static 04:12.
           * A frozen number invites the misread that time is still passing normally."* Resume is a
           * visible transition when the driver answers.
           *
           * **The shipped tool is not a pause.** `hold_for_information` (#64) writes
           * `appointments.expires_at = now + N minutes` -- ONE bounded extension, server-chosen --
           * and `ttl.deadline_ts` becomes that value. Time keeps elapsing. Nothing resumes,
           * because nothing stopped, and no server path recalculates the deadline when the driver
           * answers.
           *
           * So this takes U67's visual language, which serves its stated purpose (a held row must
           * be unmistakable from a healthy long-TTL row), and **keeps the number**, which U67 says
           * to hide. Hiding it here would invert U67's own reasoning: the misread it protects
           * against is "time is still passing normally" when it is not, and on this mechanism time
           * genuinely IS still passing. A planner told "paused · waiting on driver" would look away
           * from a request that expires in twelve minutes.
           *
           * Flagged for the owner rather than decided as settled -- either (a) accept extension
           * semantics and correct U67's copy and this column's spec, or (b) build a real
           * pause/resume server-side, at which point the number should hide exactly as written.
           */}
          <span
            data-numeric
            data-held={row.ttl.hold_used ? 'true' : undefined}
            className={cn(
              'font-mono text-supporting tabular-nums',
              // Held wins over the urgency band deliberately: U67's rule that a held row must not
              // "visually compete with rows that are genuinely running out".
              row.ttl.hold_used ? 'text-muted-foreground' : TTL_BAND_CLASS[band],
            )}
            title={
              row.ttl.hold_used
                ? 'Held for information — this request’s one deadline extension has been used. The clock is still running against the extended deadline.'
                : countdown.live
                  ? undefined
                  : 'Offline — this countdown is holding at its last known value rather than ticking.'
            }
          >
            {row.ttl.hold_used ? (
              <span className="inline-flex items-center gap-1">
                <Pause aria-hidden="true" className="size-3" />
                {/* "held", not "paused": the word has to match the mechanism. */}
                held · {countdown.expired ? '0:00' : countdown.label}
              </span>
            ) : countdown.expired ? (
              '0:00'
            ) : (
              countdown.label
            )}
          </span>
        </td>

        {/* U79: the destructive group is FIRST in DOM order, whatever the visual arrangement. */}
        <td className="px-2 py-1.5">
          <div className="flex items-center gap-3">
            <div className="flex items-center">
              <RowAction
                icon={X}
                label={`Reject ${row.shipment_id}`}
                tone="destructive"
                disabled={terminal || busy}
                onClick={onReject}
              />
            </div>
            <div className="flex items-center gap-0.5">
              <RowAction
                icon={Check}
                label={`Confirm ${row.shipment_id}`}
                tone="constructive"
                // Inactive rather than absent if the flag is ever turned back off: a Confirm
                // button that silently does nothing is worse than one that says why it cannot.
                inactive={!plannerConfirmEnabled}
                inactiveTitle={ROW_ACTION_TITLE.confirm}
                disabled={terminal || busy}
                onClick={onConfirm}
              />
              <RowAction
                icon={Repeat}
                label={`Counter-offer ${row.shipment_id}`}
                inactive={!plannerCounterOfferEnabled}
                inactiveTitle={ROW_ACTION_TITLE.counterOffer}
                disabled={terminal || busy}
                onClick={onCounterOffer}
              />
              {/* One-shot, prevented rather than handled: `edge-cases.md` #6 is explicit that a
                  second hold must be impossible to attempt, not merely refused afterwards. The
                  gate is the row's own `ttl.hold_used`, which is the same fact the server checks
                  (`appointments.expires_at IS NOT NULL`). */}
              <RowAction
                icon={Pause}
                label={`Hold ${row.shipment_id} for information`}
                inactive={!plannerHoldEnabled || row.ttl.hold_used}
                inactiveTitle={
                  plannerHoldEnabled ? ROW_ACTION_TITLE.holdUsed : ROW_ACTION_TITLE.hold
                }
                disabled={terminal || busy}
                onClick={onHold}
              />
              <RowAction
                icon={ArrowUpRight}
                label={`Escalate ${row.shipment_id}`}
                inactive
                inactiveTitle={ROW_ACTION_TITLE.escalate}
                onClick={() => {}}
              />
            </div>
          </div>
        </td>
      </tr>

      {/* The refusal and the bulk outcome render as their own full-width row so the nine columns
          above keep their fixed widths -- `components.md` section 1's hard rule that a reflow
          during a read is an operational cost on this screen specifically. */}
      {vanished ? (
        <tr className="border-b border-border">
          <td colSpan={9} className="px-3 pb-2">
            {/* `role="alert"` (assertive) ONLY when this is the row the planner is focused on --
                `accessibility-behaviour.md` gives that exact case its own row and calls it the
                nastiest race in the product. Every other row's disappearance is silent by the same
                matrix, so it renders with no live region at all rather than a quieter one. */}
            <span
              role={vanished.announce ? 'alert' : undefined}
              className="flex items-start gap-1.5 text-supporting text-warning-fg"
            >
              <TriangleAlert className="mt-px size-3.5 shrink-0" aria-hidden="true" />
              <span>
                This request was actioned elsewhere and is no longer pending. It stays in place
                until you re-sort, so nothing moves under you.
              </span>
            </span>
          </td>
        </tr>
      ) : null}

      {refusal && refusal.kind !== 'DISPLACEMENT_DETECTED' ? (
        <tr className="border-b border-border">
          <td colSpan={9} className="px-3 pb-2">
            <RowMessage refusal={refusal} />
          </td>
        </tr>
      ) : null}

      {outcome && outcome.code !== 'CONFIRMED' ? (
        <tr className="border-b border-border">
          <td colSpan={9} className="px-3 pb-2">
            <span
              role="status"
              className="flex items-start gap-1.5 text-supporting text-warning-fg"
            >
              <TriangleAlert className="mt-px size-3.5 shrink-0" aria-hidden="true" />
              <span>
                Skipped in the batch ({outcome.code.toLowerCase().replace(/_/g, ' ')})
                {outcome.failed_predicates.length > 0
                  ? ` — ${describePredicates(outcome.failed_predicates)}`
                  : outcome.detail
                    ? ` — ${outcome.detail}`
                    : ''}
                . It stays here for individual review.
              </span>
            </span>
          </td>
        </tr>
      ) : null}
    </>
  )
})

/**
 * Three refusals, three deliberately different volumes (`mockup.html` State 8's note).
 *
 * `ALREADY_ACTIONED` is the assertive case -- section 9.2 #3's nastiest race, where both actors
 * believe they acted, and `edge-cases.md` #1 requires the loser to be told **what won**, which is
 * carried in the server's own message rather than reconstructed here. `SNAPSHOT_STALE` is
 * deliberately quiet and neutral-toned: it is not a conflict, so it must not look like one.
 */
function RowMessage({ refusal }: { refusal: PlannerRefusal }) {
  if (refusal.kind === 'ALREADY_ACTIONED') {
    return (
      <span role="alert" className="flex items-start gap-1.5 text-supporting text-danger-fg">
        <CircleAlert className="mt-px size-3.5 shrink-0" aria-hidden="true" />
        <span>{refusal.message}</span>
      </span>
    )
  }
  if (refusal.kind === 'SNAPSHOT_STALE') {
    return (
      <span role="status" className="block text-supporting text-muted-foreground">
        This row was updated — read it again before deciding.
        {refusal.drift ? (
          <span className="ml-1 text-subtle-foreground">
            Now {refusal.drift.current.appointment_status.toLowerCase().replace(/_/g, ' ')} on{' '}
            <span translate="no">{refusal.drift.current.dock_id}</span>.
          </span>
        ) : null}
      </span>
    )
  }
  return (
    <span role="alert" className="flex items-start gap-1.5 text-supporting text-danger-fg">
      <CircleAlert className="mt-px size-3.5 shrink-0" aria-hidden="true" />
      <span>{refusal.message}</span>
    </span>
  )
}

/**
 * One affordance button. 32px effective target -- `spacing-and-layout.md`'s `compact` floor, the
 * deliberate desktop-and-pointer exception to the 44px rule, and comfortably over WCAG 2.2
 * SC 2.5.8's 24x24 AA floor. (Section 2.2: 151 of 304 targets in the mockup sat under this.)
 *
 * `inactive` is `components.md` section 18's **Inactive**, not Disabled: the control stays
 * focusable and explains itself, because a planner needs to tell "this action does not apply"
 * from "this action does not exist yet". `disabled` is the ordinary Disabled tier, used only for
 * a row that is genuinely finished or a press already in flight.
 */
function RowAction({
  icon: Icon,
  label,
  tone,
  disabled,
  inactive,
  inactiveTitle,
  onClick,
}: {
  icon: typeof Check
  label: string
  tone?: 'constructive' | 'destructive'
  disabled?: boolean
  inactive?: boolean
  inactiveTitle?: string
  onClick: () => void
}) {
  const unavailable = Boolean(inactive)
  return (
    <button
      type="button"
      // Inactive is aria-disabled (focusable, announces its reason); Disabled is the real
      // attribute. Never both, and never `disabled` for an unbuilt backend -- that would hide the
      // explanation behind a control a keyboard user cannot reach.
      aria-disabled={unavailable || disabled || undefined}
      disabled={!unavailable && disabled}
      title={unavailable ? inactiveTitle : label}
      aria-label={unavailable ? `${label} — unavailable, activate for an explanation` : label}
      onClick={() => {
        if (unavailable || disabled) return
        onClick()
      }}
      className={cn(
        'inline-flex size-8 shrink-0 items-center justify-center rounded-md border border-transparent outline-none',
        'focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2',
        unavailable
          ? 'cursor-default text-subtle-foreground'
          : disabled
            ? 'cursor-not-allowed text-disabled-foreground'
            : tone === 'destructive'
              ? 'text-danger-fg hover:bg-hover'
              : tone === 'constructive'
                ? 'text-success-fg hover:bg-hover'
                : 'text-muted-foreground hover:bg-hover hover:text-foreground',
      )}
    >
      <Icon className="size-4" aria-hidden="true" />
    </button>
  )
}
