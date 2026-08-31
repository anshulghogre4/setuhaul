import { useCallback, useEffect, useMemo, useState } from 'react'

import { PolicyVersionHeader } from './policy-version-header'
import { PolicyWeightEditor } from './policy-weight-editor'
import {
  PublishConflict,
  SimulationPublished,
  SimulationResult,
  SimulationRunning,
} from './policy-simulation-panel'
import { LoadFailed, NotYetAvailable, TableCard, TableSkeleton, WriteFailedBanner } from './primitives'
import {
  getActivePolicy,
  listUsers,
  publishPolicyVersion,
  simulatePolicyWeights,
} from '../lib/api'
import { adminPolicyEditorEnabled } from '../lib/flags'
import { buildProposedWeights, draftsFrom, parseWeightInput, weightsEqual } from '../lib/policy'
import type {
  ActivePolicyResponse,
  PolicyPublishResult,
  PolicySimulation,
  PolicyWeights,
} from '../lib/types'
import { formatUserFriendlyError, isApiError } from '@/core/http/api'

type LoadState = 'loading' | 'ready' | 'failed'

type SimState =
  | { kind: 'idle' }
  | { kind: 'running' }
  /** `weights` is exactly what was sent, which is what makes the staleness check truthful. */
  | { kind: 'result'; result: PolicySimulation; weights: PolicyWeights }

type PublishState =
  | { kind: 'idle' }
  | { kind: 'busy' }
  | { kind: 'done'; result: PolicyPublishResult }
  /** `edge-cases.md` #3 — someone else published first, or a baseline was required and absent. */
  | { kind: 'conflict'; message: string; detail: string }
  | { kind: 'failed'; message: string }

/** 30 days back from now, the interval the Simulate button's own label names. */
const SIMULATION_WINDOW_DAYS = 30

/**
 * Screens 8 and 10 — the Policy tab, **built** (2026-08-31).
 *
 * ## Why this stopped being a stub
 *
 * E5.6 shipped this tab as a hard stub and said so explicitly, disagreeing with its own readiness
 * spec's 🟡: no endpoint read the active policy version or the live score weights, so seeding the
 * four weight fields would have meant hardcoding `4 / -6 / 1 / -25` into a client that could not
 * detect drift from server config, and the current-version header `components.md` §3 requires had
 * nothing to render. Publishing weights an admin never saw the baseline for is exactly what U27's
 * simulate-before-publish gate exists to prevent. That reasoning was correct and is not being
 * walked back — **the gap it named is closed**:
 *
 *  - `GET /api/v1/admin/policy/active` now returns the active `policy_versions` row,
 *    `constraints.json`'s live `score_weights`, the live priority tiers, and
 *    `engine_matches_active_version`.
 *  - `POST /api/v1/admin/policy/publish` now takes `based_on_version_id`, **required whenever an
 *    active version exists**, so `edge-cases.md` #3's named refusal is expressible for the first
 *    time.
 *
 * ## The invariants this component keeps
 *
 * 1. **Nothing renders until the server has answered.** No weight field, no version header and no
 *    Simulate button exists in the `loading` or `failed` states. It is structurally impossible for
 *    this tab to show a made-up coefficient, which is the property E5.6 refused to ship without.
 * 2. **Publish requires a fresh simulation against the current field values** (`screens.md` §4,
 *    `components.md` §5). Staleness is derived by comparing the weights actually submitted against
 *    the weights currently in the form — not tracked by a flag some future change could forget to
 *    set.
 * 3. **The baseline is always sent when one exists.** `publish_policy_version`'s own docstring:
 *    "an optional guard is not a guard."
 * 4. **A conflict discards the simulation and re-reads the baseline**, per `edge-cases.md` #3: "A's
 *    editor re-fetches the now-current version (B's) as its new baseline and marks A's own
 *    simulation stale… A cannot publish blind on top of a policy they never actually compared
 *    against."
 *
 * Still gated on issue #69: the fairness Danger Zone (Screen 9) and the `P_churn` field — see
 * `policy-weight-editor.tsx`. This build does not flip that flag; another agent owns it.
 */
export function PolicyTab() {
  if (!adminPolicyEditorEnabled) {
    return (
      <div className="flex flex-col gap-6">
        <NotYetAvailable
          title="The policy weight editor is switched off."
          body="adminPolicyEditorEnabled is false. The editor itself is built and wired to GET /admin/policy/active, POST /admin/policy/simulate and POST /admin/policy/publish — this branch exists so the tab can be switched off without deleting it."
        />
      </div>
    )
  }
  return <PolicyEditor />
}

function PolicyEditor() {
  const [load, setLoad] = useState<LoadState>('loading')
  const [policy, setPolicy] = useState<ActivePolicyResponse | null>(null)
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [sim, setSim] = useState<SimState>({ kind: 'idle' })
  const [publish, setPublish] = useState<PublishState>({ kind: 'idle' })
  const [simError, setSimError] = useState<string | null>(null)
  const [publisherNames, setPublisherNames] = useState<Record<string, string>>({})

  /**
   * The `Idempotency-Key` for the current publish INTENT, held across retries.
   *
   * Minting a fresh key inside each call would defeat the header entirely: a publish whose response
   * was lost in flight and then retried would write a second immutable `policy_versions` row rather
   * than replaying the first. Held here, a retry of the same attempt replays — and
   * `SimulationPublished` renders the server's own `idempotent_replay` flag when it does, so a
   * replay is visible rather than indistinguishable from a fresh publish.
   *
   * It is cleared whenever the intent changes (edit, discard, new simulation, success, conflict),
   * because `lookup_idempotency` hashes `{weights, based_on_version_id}` and refuses a reused key
   * against a changed payload with `IDEMPOTENCY_PAYLOAD_MISMATCH` (409).
   */
  const [publishKey, setPublishKey] = useState<string | null>(null)

  /**
   * `reseedDrafts` is false on a post-publish or post-conflict refetch: the admin's typed values
   * are theirs, and silently resetting a form under someone because a background read completed
   * would lose work. It is true only on first load, where there is nothing to lose.
   */
  const refresh = useCallback(async (reseedDrafts: boolean) => {
    const result = await getActivePolicy()
    setPolicy(result)
    if (reseedDrafts) setDrafts(draftsFrom(result.live_weights))
    return result
  }, [])

  useEffect(() => {
    let cancelled = false
    void (async () => {
      setLoad('loading')
      try {
        const result = await getActivePolicy()
        if (cancelled) return
        setPolicy(result)
        setDrafts(draftsFrom(result.live_weights))
        setLoad('ready')
      } catch {
        if (!cancelled) setLoad('failed')
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  /**
   * `published_by_user_id` -> display name, for `components.md` §3's publisher.
   *
   * The same derivation the Audit tab already makes for its Actor column, and it degrades the same
   * way: a failure leaves the header showing the raw user id, which is still attributable, rather
   * than blocking the tab on a secondary read.
   */
  useEffect(() => {
    let cancelled = false
    void (async () => {
      try {
        const result = await listUsers()
        if (cancelled) return
        const names: Record<string, string> = {}
        for (const user of result.items) names[user.user_id] = user.full_name ?? user.email
        setPublisherNames(names)
      } catch {
        if (!cancelled) setPublisherNames({})
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const invalidKeys = useMemo(() => {
    const invalid = new Set<string>()
    for (const [key, raw] of Object.entries(drafts)) {
      if (parseWeightInput(raw) === null) invalid.add(key)
    }
    return invalid
  }, [drafts])

  /** The exact payload a simulate or publish would send right now, or null if a field is unusable. */
  const proposed = useMemo(
    () => (policy === null ? null : buildProposedWeights(policy.live_weights, drafts)),
    [policy, drafts],
  )

  /**
   * `components.md` §3: "changing any field after running a simulation marks the simulation result
   * stale". Derived, never stored — a value comparison against what was actually submitted cannot
   * drift out of sync with the form the way a manually-reset boolean could. An unparseable field
   * also counts as stale, because there is no payload to compare and there is certainly no fresh
   * simulation of one.
   */
  const stale = sim.kind === 'result' && !weightsEqual(sim.weights, proposed)

  function onChange(key: string, value: string) {
    setDrafts((current) => ({ ...current, [key]: value }))
    // A field edit invalidates a completed publish message: it is no longer describing what is on
    // screen. The conflict banner is left alone deliberately -- it names a fact about another
    // admin's action, which editing a field here does not undo.
    setPublish((current) => (current.kind === 'done' ? { kind: 'idle' } : current))
    // The payload has changed, so the key must too, or the server refuses it as a reused key
    // against a different payload.
    setPublishKey(null)
  }

  async function onSimulate() {
    if (policy === null || proposed === null) return
    setSimError(null)
    setPublish({ kind: 'idle' })
    setPublishKey(null)
    setSim({ kind: 'running' })
    const windowEnd = new Date()
    const windowStart = new Date(windowEnd)
    windowStart.setDate(windowStart.getDate() - SIMULATION_WINDOW_DAYS)
    try {
      const result = await simulatePolicyWeights({ weights: proposed, windowStart, windowEnd })
      setSim({ kind: 'result', result, weights: proposed })
    } catch (error) {
      setSim({ kind: 'idle' })
      setSimError(formatUserFriendlyError(error))
    }
  }

  /** Flow 6's diagram: Discard returns the editor to the baseline, it does not merely hide the panel. */
  function onDiscard() {
    if (policy !== null) setDrafts(draftsFrom(policy.live_weights))
    setSim({ kind: 'idle' })
    setSimError(null)
    setPublish({ kind: 'idle' })
    setPublishKey(null)
  }

  async function onPublish() {
    if (policy === null || sim.kind !== 'result' || stale) return
    // Reused on a retry of this same attempt, minted once per intent. See `publishKey`.
    const key = publishKey ?? crypto.randomUUID()
    setPublishKey(key)
    setPublish({ kind: 'busy' })
    try {
      const result = await publishPolicyVersion({
        idempotencyKey: key,
        // The weights that were SIMULATED, not the current form state. They are equal here by the
        // staleness check above; sending the simulated object makes "you publish what you previewed"
        // true by construction rather than by that check continuing to hold.
        weights: sim.weights,
        basedOnVersionId: policy.active_version?.policy_version_id ?? null,
      })
      setPublish({ kind: 'done', result })
      setSim({ kind: 'idle' })
      setPublishKey(null)
      // The header must show the new version and re-evaluate engine_matches_active_version, and
      // the next publish needs the new baseline. A failure here leaves a stale header, so it
      // downgrades the whole tab to the load-failed state rather than being swallowed: publishing
      // against a baseline this client can no longer confirm is the situation the guard exists for.
      try {
        await refresh(false)
      } catch {
        setLoad('failed')
      }
    } catch (error) {
      // `isApiError` narrows to the shared code-bearing error; a transport failure is not one and
      // so can never be mistaken for the server's baseline refusal.
      if (isApiError(error) && isBaselineRefusal(error.code)) {
        // edge-cases.md #3: re-read the now-current version as the new baseline, and discard the
        // simulation -- it compared against a baseline that is no longer current.
        setSim({ kind: 'idle' })
        // The baseline is about to change, which changes the payload hash, so the key must not be
        // carried into the next attempt.
        setPublishKey(null)
        // `envelopeMessage`, not `message`: for BASE_VERSION_REQUIRED the envelope's `detail` is
        // the machine fragment `based_on_version_id=<uuid>`, which is what `detail` below carries,
        // while the sentence an admin should read is the envelope's own `message`.
        setPublish({ kind: 'conflict', message: error.envelopeMessage, detail: error.detail })
        try {
          await refresh(false)
        } catch {
          setLoad('failed')
        }
        return
      }
      setPublish({
        kind: 'failed',
        message: isApiError(error)
          ? `${error.envelopeMessage} (${error.code})`
          : formatUserFriendlyError(error),
      })
    }
  }

  if (load === 'loading') {
    return (
      <TableCard>
        <TableSkeleton columns={3} rows={5} />
      </TableCard>
    )
  }
  if (load === 'failed' || policy === null) {
    return (
      <LoadFailed
        what="the active policy"
        onRetry={() => {
          setLoad('loading')
          void refresh(true)
            .then(() => setLoad('ready'))
            .catch(() => setLoad('failed'))
        }}
      />
    )
  }

  return (
    <div className="flex max-w-[80ch] flex-col gap-6">
      {publish.kind === 'failed' ? (
        <WriteFailedBanner detail={publish.message} onRetry={() => void onPublish()} />
      ) : null}
      {simError === null ? null : <WriteFailedBanner detail={simError} onRetry={() => void onSimulate()} />}

      <PolicyVersionHeader policy={policy} publisherNames={publisherNames} />

      <PolicyWeightEditor
        live={policy.live_weights}
        priorityScores={policy.live_priority_scores}
        drafts={drafts}
        invalidKeys={invalidKeys}
        onChange={onChange}
        onSimulate={() => void onSimulate()}
        simulating={sim.kind === 'running'}
        windowLabel={`the last ${SIMULATION_WINDOW_DAYS} days`}
      />

      {sim.kind === 'running' ? <SimulationRunning /> : null}
      {sim.kind === 'result' ? (
        <SimulationResult
          simulation={sim.result}
          stale={stale}
          publishing={publish.kind === 'busy'}
          onDiscard={onDiscard}
          onPublish={() => void onPublish()}
        />
      ) : null}
      {publish.kind === 'done' ? <SimulationPublished result={publish.result} /> : null}
      {publish.kind === 'conflict' ? (
        <PublishConflict
          message={publish.message}
          detail={publish.detail}
          onDismiss={() => setPublish({ kind: 'idle' })}
        />
      ) : null}
    </div>
  )
}

/**
 * The two refusals that mean "your baseline is not the current one", both of which take
 * `edge-cases.md` #3's handling.
 *
 * `ALREADY_ACTIONED` (409) is the documented race: someone published between this admin's
 * simulation and their Publish. `BASE_VERSION_REQUIRED` (422) is the same situation seen from the
 * other side — this client loaded when nothing was active, so it sent no baseline, and something
 * has been published since. Both are resolved by re-reading and re-simulating, so both get the
 * same screen, with the server's own message distinguishing them.
 */
function isBaselineRefusal(code: string): boolean {
  return code === 'ALREADY_ACTIONED' || code === 'BASE_VERSION_REQUIRED'
}
