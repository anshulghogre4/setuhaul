import { CircleCheck, TriangleAlert } from 'lucide-react'

import { formatAuditTimestamp } from '../lib/audit'
import { formatNumber, publisherLabel } from '../lib/policy'
import type { ActivePolicyResponse, PolicyWeights } from '../lib/types'

/**
 * `components.md` §3's read-only current-version header — "version number, publish date,
 * publisher" — plus the one thing the design files could not have specified, because the backend
 * behaviour it describes was written after them: **`engine_matches_active_version`**.
 *
 * ## Why this component renders two facts and not one
 *
 * `publish_policy_version` writes an immutable `policy_versions` row and **deliberately does not
 * rewrite `backend/app/scheduling/constraints.json`**, which is the file `feasibility.py::_rank_slot`
 * actually reads. Its own docstring states why: "that file is the live ranking engine's actual
 * input and changing it is a deploy-time decision, not a runtime admin write." So there are two
 * separate truths — *the version of record* and *the weights currently scoring every decision* —
 * and they can legitimately differ.
 *
 * `get_active_policy_version` returns both, plus its own comparison of them, precisely so this UI
 * does not have to imply the published version is live. Flattening the two into one line
 * ("Current policy: POLV-… ") would be the single most misleading thing this tab could do: an
 * admin would read a version they published as the one in force, and it might not be. So when the
 * server says they diverge, the divergence is named key by key, from the two dicts the server
 * supplied — never inferred, never smoothed over.
 *
 * ## Version "number"
 *
 * `screens.md` §4 and `mockup.html` §8 show "v3". **There is no version number in the schema** —
 * `policy_versions.policy_version_id` is a `POLV-` text id and there is no ordinal column
 * (`20260825213000_e34_policy_versions_and_rule_registry.sql`). The real id is rendered rather
 * than a fabricated sequence; a made-up "v4" would be exactly the invented operational data this
 * surface refused to ship for.
 *
 * Publish date carries a time as well as a date, unlike the mockup's bare `2026-08-11` — the
 * concurrent-publish race (`edge-cases.md` #3) is decided on ordering, so "which of these two came
 * first" has to be answerable from the header.
 */
export function PolicyVersionHeader({
  policy,
  publisherNames,
}: {
  policy: ActivePolicyResponse
  /** `user_id` -> display name, from `list_users`. A missing entry renders the raw id. */
  publisherNames: Record<string, string>
}) {
  const active = policy.active_version

  return (
    <div className="flex flex-col gap-3">
      {active === null ? (
        <p className="text-body text-muted-foreground">
          <strong className="font-semibold text-foreground">
            No policy version has been published yet.
          </strong>{' '}
          The ranking engine is running the weights below straight from{' '}
          <code className="font-data">scheduling/constraints.json</code>. Publishing here records
          the first version of record.
        </p>
      ) : (
        <p className="text-body text-muted-foreground">
          Current policy:{' '}
          <span className="font-data text-foreground" data-numeric>
            {active.policy_version_id}
          </span>{' '}
          · published{' '}
          <span className="font-data" data-numeric>
            {formatAuditTimestamp(active.published_at)}
          </span>{' '}
          · {publisherLabel(active, publisherNames)}
        </p>
      )}

      {active === null ? null : policy.engine_matches_active_version ? (
        <EngineMatches />
      ) : (
        <EngineDiverged published={active.weights} live={policy.live_weights} note={policy.note} />
      )}
    </div>
  )
}

/**
 * The reassuring case, stated rather than left implicit.
 *
 * `role="status"` and not `role="alert"`: nothing is wrong, and `accessibility-behaviour.md`
 * reserves the assertive tier for unsuccessful or high-consequence outcomes.
 */
function EngineMatches() {
  return (
    <p
      role="status"
      className="flex items-start gap-2 rounded-md border border-success-border bg-success-bg px-3 py-2 text-supporting text-success-fg"
    >
      <CircleCheck className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <span>
        The ranking engine is running these exact weights. The published version and{' '}
        <code className="font-data">constraints.json</code> agree.
      </span>
    </p>
  )
}

/**
 * The case the whole field exists for.
 *
 * Every differing key is named with both values, computed from the two dicts the server sent — no
 * client-side judgement about which is "right", because neither is: the published row is the
 * decision of record and the file is what is executing, and reconciling them is a deploy, not a
 * click. The copy says exactly that instead of offering an action this console cannot perform.
 */
function EngineDiverged({
  published,
  live,
  note,
}: {
  published: PolicyWeights
  live: PolicyWeights
  note: string
}) {
  const keys = [...new Set([...Object.keys(published), ...Object.keys(live)])]
    .filter((key) => published[key] !== live[key])
    .sort((a, b) => a.localeCompare(b))

  return (
    <div
      role="status"
      className="flex items-start gap-2 rounded-md border border-warning-border bg-warning-bg px-3 py-2 text-supporting text-warning-fg"
    >
      <TriangleAlert className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
      <div className="flex flex-col gap-2">
        <p>
          <strong className="font-semibold">
            The ranking engine is not running the active version.
          </strong>{' '}
          {note}
        </p>
        {keys.length === 0 ? null : (
          <ul className="flex flex-col gap-1">
            {keys.map((key) => (
              <li key={key} className="font-data" data-numeric>
                {key}: published {describe(published[key])} · engine {describe(live[key])}
              </li>
            ))}
          </ul>
        )}
        <p>
          The fields below are seeded from what the engine is actually running, because that is what
          a simulation compares against.
        </p>
      </div>
    </div>
  )
}

/** A key absent from one side is a real difference and must not read as a zero. */
function describe(value: number | undefined): string {
  return value === undefined ? '(not set)' : formatNumber(value)
}
