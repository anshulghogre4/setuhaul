import { CircleCheck, OctagonAlert, TriangleAlert } from 'lucide-react'
import { useEffect, useId, useState } from 'react'

import { formatNumber } from '../lib/policy'
import type { PolicyPublishResult, PolicySimulation } from '../lib/types'
import { Button } from '@/shared/ui/button'
import { Skeleton } from '@/shared/ui/skeleton'

/**
 * Screen 10 — the simulation panel's four states (`components.md` §5, `mockup.html` §10.A–10.D),
 * plus a fifth the mockup flags as missing: the concurrent-publish refusal (`edge-cases.md` #3).
 *
 * All five are presentational. The tab owns the state machine; this file owns how each state
 * reads, so the gallery can render every one of them without a backend.
 */

/**
 * 10.A — running.
 *
 * A skeleton that matches the final layout, not a centred spinner: "a spinner followed by content
 * is a layout jump, and a jump under a cursor is a mis-click" (`mockup.html` §10.A). The status
 * line changes at roughly ten seconds, because a spinner looks identical at 2 seconds and at 40 —
 * also the mockup's own copy, implemented rather than left as a note.
 */
export function SimulationRunning() {
  const [longRunning, setLongRunning] = useState(false)
  const statusId = useId()

  useEffect(() => {
    const timer = window.setTimeout(() => setLongRunning(true), 10_000)
    return () => window.clearTimeout(timer)
  }, [])

  return (
    <div
      aria-busy="true"
      aria-labelledby={statusId}
      className="mt-6 rounded-md border border-border bg-card p-4"
    >
      <Skeleton className="h-5 w-[62%]" />
      <Skeleton className="mt-3 h-3 w-[80%]" />
      <Skeleton className="mt-2 h-3 w-[74%]" />
      <Skeleton className="mt-2 h-3 w-[78%]" />
      <p id={statusId} role="status" className="mt-4 text-supporting text-muted-foreground">
        {longRunning ? 'Still working — replaying the last 30 days' : 'Replaying the last 30 days…'}
      </p>
    </div>
  )
}

/**
 * 10.B / 10.C — result, and the same result gone stale.
 *
 * **The aggregate count is the headline and the first thing announced** (`components.md` §5,
 * `accessibility.md`): `role="status"` + `aria-live="polite"` + `aria-atomic` on the count line,
 * so a screen-reader user hears "12 of 340 decisions would flip" before any individual case —
 * matching how it is visually prioritised.
 *
 * ## Two honest divergences from the artboard, both contract-shaped
 *
 * 1. **The caption does not say "vs. current policy v3".** `simulate_policy_weights` compares the
 *    proposed weights against `constraints.json`'s live weights (`live = load_scheduling_constraints()`),
 *    **not** against the active `policy_versions` row. When those two diverge — which
 *    `engine_matches_active_version` exists to surface — the mockup's caption would name the wrong
 *    comparison point.
 * 2. **A case is one shipment and two slots, not a head-to-head pair of shipments.**
 *    `example_flips` returns `{shipment_id, live_top_slot, proposed_top_slot}`; the mockup's
 *    "SHP1014 vs SHP1009 — SHP1014 loses to SHP1009" implies two shipments contesting one slot,
 *    which is not what the tool computes. `implementation-spec.md` §3's Screen 10 caveat (b)
 *    predicted exactly this. The real shape is rendered; the copy is not.
 *
 * That is also why cases are a flat list rather than `mockup.html`'s `<details>` expanders: the
 * expander promises "both shipments' score terms … from the stored decision receipt", and no such
 * receipt is returned by (or exists anywhere behind) this tool. An expander that opens onto
 * nothing is worse than a line that says everything it has.
 */
export function SimulationResult({
  simulation,
  stale,
  publishing,
  onDiscard,
  onPublish,
}: {
  simulation: PolicySimulation
  /** A weight changed since this ran (`components.md` §3/§5, `flows-and-states.md` Flow 6). */
  stale: boolean
  publishing: boolean
  onDiscard: () => void
  onPublish: () => void
}) {
  const whyId = useId()
  const vacuous = simulation.candidates_evaluated === 0
  const canPublish = !stale && !vacuous && !publishing

  /**
   * Three separate refusals, deliberately not collapsed into one message — an admin needs to know
   * which one they are looking at, because the fix differs for each.
   *
   * The **vacuous** case is a strengthening of U27's gate that the design files do not name, and it
   * is stated rather than slipped in: `_replayable_candidates` only matches appointments that are
   * `is_current = 1` AND still `PENDING_CONFIRMATION`/`CONFIRMED`/`IN_PROGRESS`, whose slot starts
   * inside the window. A purely historical window can therefore legitimately match nothing, and a
   * "0 of 0 would flip" result is not evidence about the change — it is the absence of evidence.
   * Letting it satisfy the simulate-before-publish gate would make that gate vacuous, which is the
   * one thing U27 exists to prevent.
   */
  const whyNotPublish = publishing
    ? 'Publishing…'
    : stale
      ? 'Re-run the simulation against the current weights'
      : 'This simulation compared no decisions, so it is not evidence about the change'

  return (
    <div
      className={
        stale
          ? 'mt-6 rounded-md border border-border bg-card p-4 opacity-70'
          : 'mt-6 rounded-md border border-border bg-card p-4'
      }
    >
      {stale ? (
        <p
          role="status"
          className="mb-3 flex items-start gap-2 rounded-md border border-warning-border bg-warning-bg px-3 py-2 text-supporting text-warning-fg"
        >
          <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
          <span>Weights changed since this simulation — re-run before publishing.</span>
        </p>
      ) : null}

      <p className="text-supporting text-muted-foreground">
        Simulation: proposed weights vs. the weights the ranking engine is currently running.
      </p>

      <p
        role="status"
        aria-live="polite"
        aria-atomic="true"
        className="mt-2 text-h3 text-foreground"
      >
        <span className="font-data" data-numeric>
          {formatNumber(simulation.flip_count)}
        </span>{' '}
        of{' '}
        <span className="font-data" data-numeric>
          {formatNumber(simulation.candidates_evaluated)}
        </span>{' '}
        decisions in the last 30 days would flip
      </p>

      {vacuous ? (
        <p className="mt-2 text-supporting text-muted-foreground">
          No appointments in this window matched. This simulator re-scores appointments that are
          still active and whose slot starts inside the window, so a purely historical window can
          legitimately have none — which means this run says nothing about the change either way.
        </p>
      ) : simulation.example_flips.length === 0 ? (
        <p className="mt-2 text-supporting text-muted-foreground">
          No decision changes under these weights.
        </p>
      ) : (
        <ul className="mt-3 flex flex-col gap-2">
          {simulation.example_flips.map((flip) => (
            // Keyed on the whole flip, not the shipment id alone: one appointment per shipment is
            // what `_replayable_candidates` selects today, but a duplicate key would be a silent
            // React warning rather than a visible defect if that ever stops holding.
            <li
              key={`${flip.shipment_id}-${flip.live_top_slot}-${flip.proposed_top_slot}`}
              className="text-supporting text-foreground"
            >
              <span className="font-data">{flip.shipment_id}</span> — top slot changes from{' '}
              <span className="font-data">{flip.live_top_slot || '(none)'}</span> to{' '}
              <span className="font-data">{flip.proposed_top_slot || '(none)'}</span>
            </li>
          ))}
          {simulation.flip_count > simulation.example_flips.length ? (
            <li className="text-supporting text-muted-foreground">
              …{' '}
              <span className="font-data" data-numeric>
                {formatNumber(simulation.flip_count - simulation.example_flips.length)}
              </span>{' '}
              more — the tool returns at most ten examples.
            </li>
          ) : null}
        </ul>
      )}

      {/* The service's own statement of what it approximates, rendered verbatim. It is the honest
          part of this tool and paraphrasing it would be the dishonest part. */}
      <p className="mt-3 text-supporting text-muted-foreground">{simulation.note}</p>

      {/* `fairness_term_evaluated: false` is a real answer, not a skip — both sides ran at
          w_fairness = 0, so the term was arithmetically absent. Stated so the Danger Zone never
          has to be inferred from a flip count. */}
      <p className="mt-1 text-supporting text-muted-foreground">
        Fairness term{' '}
        {simulation.fairness_term_evaluated
          ? 'participated in this run'
          : 'did not participate: both sides ran at w_fairness = 0'}
        .
      </p>

      {/* U79 — safer action first in DOM order; §19's 16px minimum between a neutral and a
          committing control comes from the gap. */}
      <div className="mt-4 flex flex-wrap items-center gap-4">
        <Button variant="neutral" onClick={onDiscard}>
          Discard
        </Button>
        <Button
          variant="constructive"
          aria-disabled={!canPublish}
          tabIndex={0}
          title={canPublish ? undefined : whyNotPublish}
          aria-describedby={canPublish ? undefined : whyId}
          className={canPublish ? undefined : 'opacity-50'}
          onClick={() => {
            if (!canPublish) return
            onPublish()
          }}
        >
          {publishing ? 'Publishing…' : 'Publish new version'}
        </Button>
        {canPublish ? null : (
          <span id={whyId} className="sr-only">
            {whyNotPublish}
          </span>
        )}
      </div>
      {canPublish ? null : (
        <p className="mt-2 text-supporting text-muted-foreground">{whyNotPublish}.</p>
      )}
    </div>
  )
}

/**
 * 10.D — published.
 *
 * `role="alert"`: `accessibility.md` puts a *successful* high-consequence commit in the assertive
 * tier, "since a policy publish or a user removal is exactly the kind of change an admin needs
 * confirmed happened, not just assumed from a toast that could be missed." Green as a banner, never
 * as a status chip — in this product a green chip means a confirmed dock promise and the two must
 * not be confusable.
 *
 * **The mockup's own success copy is not used, because it is not true of the shipped backend.**
 * §10.D says "Published as v4. Every decision from now on is scored against this version." But
 * `publish_policy_version` deliberately does not rewrite `scheduling/constraints.json`, so
 * decisions from now on are scored against whatever that file says — which is exactly what
 * `engine_matches_active_version` reports, and why the header above will now show a divergence if
 * the weights changed. Shipping the mockup's sentence would have made this tab lie in its single
 * most consequential moment.
 */
export function SimulationPublished({ result }: { result: PolicyPublishResult }) {
  return (
    <div
      role="alert"
      className="mt-6 flex items-start gap-3 rounded-md border border-success-border bg-success-bg px-4 py-3 text-body text-success-fg"
    >
      <CircleCheck className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div className="flex flex-col gap-1">
        <p>
          Published as <span className="font-data">{result.policy_version_id}</span>
          {result.superseded_version_id ? (
            <>
              , superseding <span className="font-data">{result.superseded_version_id}</span>
            </>
          ) : null}
          .
          {result.idempotent_replay ? ' This was a replay of an earlier identical publish.' : ''}
        </p>
        <p className="text-supporting">
          This is now the version of record. It does not change what the ranking engine is running —
          publishing writes a <span className="font-data">policy_versions</span> row and does not
          rewrite <span className="font-data">scheduling/constraints.json</span>. The header above
          now shows whether the two agree.
        </p>
      </div>
    </div>
  )
}

/**
 * `edge-cases.md` #3 — someone else published first. **The state `mockup.html` §10.D flags as
 * having no copy template; this is that template.**
 *
 * The rule this follows is the product-wide one §7.5.1 states for `confirm_request`'s
 * `ALREADY_ACTIONED`: name the winning transition rather than report a generic failure, because
 * "the difference between 'your click failed' and 'someone else published first' is the difference
 * between retrying blind and re-simulating against what is actually current."
 *
 * Both server strings are rendered verbatim — `message` names the winning version id, `detail`
 * carries `current_version_id=` and `published_by=`. They are **not** parsed apart into fields: the
 * authoritative re-read of the winner is the refetched header above this banner (which
 * `edge-cases.md` #3 requires anyway — "A's editor re-fetches the now-current version as its new
 * baseline"), so string-scraping a formatted detail line would add a brittle dependency for
 * information already obtained properly.
 */
export function PublishConflict({
  message,
  detail,
  onDismiss,
}: {
  message: string
  detail: string
  onDismiss: () => void
}) {
  return (
    <div
      role="alert"
      className="mt-6 flex items-start gap-3 rounded-md border border-danger-border bg-danger-bg px-4 py-3 text-body text-danger-fg"
    >
      <OctagonAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div className="flex flex-col gap-2">
        <p>
          <strong className="font-semibold">Nothing has been published.</strong> {message}
        </p>
        <p className="font-data text-supporting">{detail}</p>
        <p className="text-supporting">
          The current version above has been re-read, and your simulation was discarded — it
          compared against a baseline that is no longer current. Simulate again before publishing.
        </p>
        <Button variant="neutral" className="self-start" onClick={onDismiss}>
          Dismiss
        </Button>
      </div>
    </div>
  )
}
