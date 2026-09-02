import { useState } from 'react'
import { ChevronDown, ChevronRight, Info, Network, SquareArrowOutUpRight } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Button } from '@/shared/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/ui/popover'
import { requestSequencerProposal } from '../lib/api'
import { sequencerProposalEnabled } from '../lib/flags'
import type { AffectedAppointment, SequencerProposalResult } from '../lib/types'
import { formatUserFriendlyError } from '@/core/http/api'
import { useAuth } from '@/core/auth/auth-context'
import { railDestinationFor } from '@/core/auth/identity'

/**
 * `00-foundations/components.md` section 17 (U65) + `screens.md` section 5. One row per incident,
 * always -- the affected-count is part of the collapsed row's primary text.
 *
 * ## The three states `stitch-prompts.md` prompt 14 specifies, and which of them is gated
 *
 * State 1 (collapsed row) and State 2 (expanded, read-only affected list) ship unconditionally and
 * always have. **State 3 -- the post-request handoff -- plus the "Request sequencer proposal"
 * action that reaches it are behind `sequencerProposalEnabled` (issues #54/#49).** That split is
 * unchanged from this component's first version; what changed is that the flag's `true` branch is
 * now a real call rather than a documented shape.
 *
 * ## Flow 4's division of responsibility is structural here, not just copy
 *
 * `flows-and-states.md` Flow 4 step 3: *"the coordinator's only action on the incident itself.
 * This does not apply any capacity change; it asks the sequencer (D5) to compute one."* And SS7.5.5:
 * *"Ops triages and requests; a planner still applies ... this tool cannot itself apply a
 * proposal."* So there is **no Apply, no diff table and no per-shipment control anywhere in this
 * file** -- the whole of SS5.1's diff is rendered on `03-planner-dock-board/`. The handoff line
 * names the counts the run returned and stops there.
 *
 * **No priority marker on the affected shipments.** `components.md` section 17 and `screens.md`
 * section 5 both show one; `payload.affected_appointments` (the only source, written by
 * `planner_service.py::_open_capacity_cascade`) does not carry `priority_code` even though the
 * query one function below it (`_affected_appointments`) reads it off `shipments` -- it is simply
 * never copied into the stored payload. Rendering a guessed priority here would be inventing data
 * this response does not have.
 */
export function CapacityIncidentRow({
  rowId: incidentEscalationId,
  dockLabel,
  affected,
  scopeDenied,
  viewerHasPlannerScope,
}: {
  /** The incident's own `escalation_id` -- lets the queue pane's roving-tabindex treat this row
   *  the same as an ordinary escalation row (Fork D item 3: one row, always). */
  rowId: string
  dockLabel: string
  affected: AffectedAppointment[]
  /** True when the incident belongs to a facility outside the caller's scope (U83: Hidden, not
   *  Disabled -- but this component still needs an honest state to demonstrate that rule). */
  scopeDenied?: boolean
  /**
   * Whether this viewer's own grants include the planner surface.
   *
   * Prompt 14 State 3: *"`[ View in planner queue ↗ ]` renders **only if the viewer is scoped to
   * the planner console**. If they are not, the button is **absent from the layout entirely** --
   * scope denial is always Hidden, never a greyed-out control that reveals a destination exists."*
   *
   * **Omit it and the row derives the answer itself** from the signed-in identity's own grants,
   * which is the correct behaviour on the live route -- a coordinator whose account holds only
   * `OPERATIONS_EXECUTIVE` genuinely has no planner surface. The prop exists so `/ops/_states` can
   * render both branches side by side; it is never how the live console decides. Either way this is
   * presentation only: `/planner`'s own reads are role-gated server-side (`require_roles`), so
   * showing the link to someone who should not have it would be a cosmetic bug, not a hole.
   */
  viewerHasPlannerScope?: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  /** Nullable rather than `useIdentity()`: the gallery mounts this component outside a
   *  `<RequireAuth>` boundary, and `useIdentity` throws there by design. */
  const { identity } = useAuth()
  const derivedPlannerScope =
    identity?.grants.some((g) => railDestinationFor(g.role)?.surface === 'planner') ?? false
  const showPlannerLink = viewerHasPlannerScope ?? derivedPlannerScope
  /**
   * The outcome of this coordinator's own request, held for the life of the row.
   *
   * Not derived from the escalation row: nothing in `get_exception_queue`'s response says whether a
   * proposal has been requested (there is no `scheduling_run_id` on an escalation row, and SS7.5.3
   * defines no read keyed by escalation). So a reload returns this row to State 2 -- stated in the
   * handoff copy rather than hidden, and reported as a contract gap rather than papered over with a
   * client-side cache that would survive a reload and lie after a server-side change.
   */
  const [outcome, setOutcome] = useState<SequencerProposalResult | null>(null)
  const [busy, setBusy] = useState(false)
  const [failure, setFailure] = useState<string | null>(null)
  const panelId = `incident-panel-${incidentEscalationId}`

  if (scopeDenied) {
    return null // U83: scope-denied is Hidden, never rendered greyed-out.
  }

  async function onRequest() {
    setBusy(true)
    setFailure(null)
    try {
      // No Idempotency-Key: the route takes none. A double-press is made safe by
      // `scheduling_runs`' partial unique index instead -- it yields ONE run plus a named
      // RUN_ALREADY_ACTIVE, which is exactly the state rendered below. See `lib/api.ts`.
      setOutcome(await requestSequencerProposal(incidentEscalationId))
    } catch (error) {
      setFailure(formatUserFriendlyError(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="border-b border-border">
      <button
        type="button"
        role="option"
        aria-selected={false}
        data-row-id={incidentEscalationId}
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start gap-2 px-4 py-3 text-left hover:bg-hover focus-visible:outline-2 focus-visible:outline-ring focus-visible:-outline-offset-2"
      >
        {expanded ? (
          <ChevronDown className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        ) : (
          <ChevronRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        )}
        <Network className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="text-body font-medium">Capacity incident · {dockLabel}</span>
          <span className="text-supporting text-muted-foreground" aria-live="polite">
            {affected.length} shipment{affected.length === 1 ? '' : 's'} affected
          </span>
        </span>
      </button>

      {expanded ? (
        <div id={panelId} className="flex flex-col gap-2 px-4 pb-3 pl-10">
          <ul className="flex flex-col gap-1">
            {affected.map((a) => (
              <li
                key={a.appointment_id}
                className="font-data flex items-center justify-between gap-2 rounded-md bg-sunken px-2 py-1.5 text-supporting tabular-nums"
              >
                <span>{a.shipment_id}</span>
                <span className="text-muted-foreground">{a.appointment_status}</span>
              </li>
            ))}
          </ul>

          {!sequencerProposalEnabled ? (
            // Inactive, not Disabled (components.md foundations section 18): fully focusable,
            // explains itself on activation rather than doing nothing.
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="neutral" size="sm">
                  Request sequencer proposal
                </Button>
              </PopoverTrigger>
              <PopoverContent role="dialog" aria-label="Why this isn't available">
                Not available yet. This delegates to section 7.5.3's Sequencer engine, which is
                entirely unbuilt (issue #49) — tracked for this console specifically as issue #54.
              </PopoverContent>
            </Popover>
          ) : outcome === null ? (
            <>
              <Button
                variant="constructive"
                size="sm"
                className="self-start"
                aria-disabled={busy}
                aria-busy={busy}
                onClick={() => {
                  if (busy) return
                  void onRequest()
                }}
              >
                {busy ? 'Requesting…' : 'Request sequencer proposal'}
              </Button>
              {failure === null ? null : (
                // A failed request is a failure, and it keeps the button so the same press can be
                // retried with the same key. Deliberately not the RUN_ALREADY_ACTIVE treatment
                // below -- that one is an expected condition and must not read like this one.
                <p
                  role="alert"
                  className="rounded-md border border-danger-border bg-danger-bg px-3 py-2 text-supporting text-danger-fg"
                >
                  {failure}
                </p>
              )}
            </>
          ) : outcome.code === 'RUN_ALREADY_ACTIVE' ? (
            <RunAlreadyActive runId={outcome.scheduling_run_id} />
          ) : (
            <HandedOff
              outcome={outcome}
              affectedCount={affected.length}
              viewerHasPlannerScope={showPlannerLink}
            />
          )}
        </div>
      ) : null}
    </div>
  )
}

/**
 * SS5.1's debounce rule, seen from the console: *"allow at most one active run per facility
 * (serialised)."*
 *
 * `03-planner-dock-board/edge-cases.md` section 4 is explicit that this *"shows an inline state
 * ... rather than a bare rejection, since this is an expected, recoverable condition, not a
 * failure"*, and `stitch-prompts.md` (planner) section 11's error-variant list gives it the info
 * tone (`#1D4ED8` on `#EFF6FF`) rather than the danger tone the two apply-refusals get. Hence
 * `feedback-info` tokens and `role="status"`, not `role="alert"`.
 *
 * **No retry button.** Retrying is precisely what the debounce exists to prevent, and a second
 * press would return this same message -- an affordance whose only outcome is its own explanation.
 */
function RunAlreadyActive({ runId }: { runId: string | null }) {
  return (
    <p
      role="status"
      className="flex items-start gap-2 rounded-md border border-info-border bg-info-bg px-3 py-2 text-supporting text-info-fg"
    >
      <Info className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>
        A re-sequence is already running for this facility — you&rsquo;ll be notified when it&rsquo;s
        ready.
        {runId ? (
          <>
            {' '}
            Run <span className="font-data">{runId}</span>.
          </>
        ) : null}
      </span>
    </p>
  )
}

/**
 * Prompt 14 State 3 -- the handoff, and the one screen in this console that exists purely to say
 * *who owns this now*.
 *
 * Three of its rules are load-bearing and each is implemented rather than approximated:
 *
 *  1. **The count is not frozen at request time** (prompt 14: *"it reflects the current true set, so
 *     it may read 5 later even though 4 was requested"*). So the sentence counts `affected.length`
 *     -- the live payload the queue read just returned -- and the run's own `unchanged + moved +
 *     newly_placed + unplaceable` is shown separately as *what the run saw*, which is a different
 *     and equally real fact. Collapsing the two would make one of them a lie the moment they differ.
 *  2. **The incident row persists and never collapses back into individual rows** -- structural
 *     here: this component still renders the same single row, and the parent's queue read is
 *     untouched by a proposal request.
 *  3. **`[ View in planner queue ↗ ]` is Hidden, not disabled, for a viewer without planner scope.**
 *
 * The run id renders because SS7.5.5's whole reason for making this a delegate rather than a
 * parallel tool is that *"the incident and the run stay linkable"* -- a handoff that does not name
 * the run it handed off is not traceable, which is the same standard `stitch-prompts.md` (planner)
 * section 11 sets for the overlay header.
 */
function HandedOff({
  outcome,
  affectedCount,
  viewerHasPlannerScope,
}: {
  outcome: SequencerProposalResult
  affectedCount: number
  viewerHasPlannerScope: boolean
}) {
  // The server's own per-category map. Ops renders the TOTAL and the four counts and stops there:
  // SS5.1's diff rows belong to the planner (U93), and this surface can never act on one.
  const c = outcome.counts
  const placed =
    (c.unchanged ?? 0) + (c.moved ?? 0) + (c.newly_placed ?? 0) + (c.unplaceable ?? 0)

  return (
    <div
      role="status"
      className="flex flex-col gap-2 rounded-md border border-info-border bg-info-bg px-3 py-2 text-supporting text-info-fg"
    >
      <p>
        Proposal requested · routed to Planner queue
        {outcome.scheduling_run_id ? (
          <>
            {' '}
            · run <span className="font-data">{outcome.scheduling_run_id}</span>
          </>
        ) : null}
      </p>
      <p>
        {affectedCount} shipment{affectedCount === 1 ? '' : 's'} awaiting a planner&rsquo;s review.
      </p>
      {placed === 0 ? null : (
        <p>
          The run covered {placed} appointment{placed === 1 ? '' : 's'}: {c.unchanged ?? 0} unchanged
          · {c.moved ?? 0} moved · {c.newly_placed ?? 0} newly placed · {c.unplaceable ?? 0}{' '}
          unplaceable. Promises moved: {outcome.objective.promises_moved}, of which{' '}
          {outcome.objective.churn_count} had already been communicated to a driver.
        </p>
      )}
      {/* Stated rather than discovered: nothing in the escalation read carries a scheduling_run_id,
          so this state cannot be reconstructed after a reload. */}
      <p className="text-subtle-foreground">
        This handoff note is local to this session — the escalation read carries no run id, so
        reloading returns the row to its pre-request view. The run itself is unaffected.
      </p>
      {viewerHasPlannerScope ? (
        <Button variant="neutral" size="sm" className="self-start" asChild>
          {/* SPA navigation, not a full reload: the planner console is a route in this same app,
              and a hard `<a>` would drop the session's in-memory state for no gain. The ↗ glyph
              the artboard draws is carried by the icon rather than a literal character, so a
              screen reader reads the label and not an arrow. */}
          <Link to="/planner">
            View in planner queue
            <SquareArrowOutUpRight className="ml-1 size-3.5" aria-hidden="true" />
          </Link>
        </Button>
      ) : null}
    </div>
  )
}
