import { ShieldAlert } from 'lucide-react'
import { useId, useState } from 'react'

import { InactiveNote } from './primitives'
import { FairnessDangerDialog } from './fairness-danger-dialog'
import { adminChurnWeightEnabled, adminFairnessTermEnabled } from '../lib/flags'
import {
  CHURN_KEY,
  FAIRNESS_KEY,
  editableFields,
  formatNumber,
  passthroughKeys,
  unitFor,
} from '../lib/policy'
import type { PolicyWeights } from '../lib/types'
import { Button } from '@/shared/ui/button'
import { Input } from '@/shared/ui/input'

/**
 * Screen 8 — the policy weight editor (`screens.md` §4, `components.md` §3, `mockup.html` §8).
 *
 * **Nothing here commits on its own.** There is deliberately no Save, no Apply and no autosave
 * indicator: `components.md` §3's "the whole editor is staging area, not a live-saving form", and
 * values reach the system only through simulate-then-publish (U27). The only action on this
 * component is Simulate.
 *
 * **Every value shown is server data.** Priority tiers come from `live_priority_scores`, the four
 * coefficients and their caps from `live_weights` — both out of `GET /policy/active`. The four
 * numbers that made `mockup.html` byte-match `constraints.json` are not written down anywhere in
 * this build; if the engine's configuration changes, this editor changes with it, which is the
 * exact drift-detection property E5.6 hard-stubbed this screen to protect.
 *
 * Priority tiers are read-only with **zero interactive affordance** (`mockup.html` §8): they are
 * the priority tiers themselves, not tuning coefficients.
 */
export function PolicyWeightEditor({
  live,
  priorityScores,
  drafts,
  invalidKeys,
  onChange,
  onSimulate,
  simulating,
  windowLabel,
  fairnessUnlocked = false,
  onUnlockFairness,
}: {
  live: PolicyWeights
  priorityScores: Record<string, number>
  drafts: Record<string, string>
  /** Keys whose current text is not a number the API can take. */
  invalidKeys: Set<string>
  onChange: (key: string, value: string) => void
  onSimulate: () => void
  simulating: boolean
  /** The exact interval the Simulate button will send, spelled out for the admin. */
  windowLabel: string
  /** Whether Flow 7's Danger-Zone gate has been passed in this session. Owned by the tab, because
   *  it also decides what `buildProposedWeights` is allowed to read. */
  fairnessUnlocked?: boolean
  onUnlockFairness?: () => void
}) {
  const fields = editableFields(live, fairnessUnlocked, adminChurnWeightEnabled)
  // Any key that became an EDITED field must leave the read-only "also in this policy" list, or it
  // would render twice with two different affordances for the same key. Derived from `fields`
  // rather than from a hand-maintained exclusion list, so a future editable weight cannot be
  // forgotten here. `w_fairness` is excluded even while locked: the Danger Zone below states its
  // value, so listing it as a passthrough too would say the same number twice.
  const passthrough = passthroughKeys(live, fields).filter((key) => key !== FAIRNESS_KEY)
  const canSimulate = invalidKeys.size === 0 && !simulating
  const whyId = useId()
  const whyNotSimulate = simulating
    ? 'A simulation is already running'
    : 'Every weight must be a number before a simulation can run'

  return (
    <div className="flex flex-col gap-6">
      <section aria-labelledby={`${whyId}-tiers`} className="flex flex-col gap-2">
        <h3 id={`${whyId}-tiers`} className="text-label text-muted-foreground uppercase tracking-wide">
          Priority weights
        </h3>
        {/* Read-only by nature, so a definition list rather than a table of inputs. */}
        <dl className="flex flex-wrap gap-x-6 gap-y-2">
          {Object.entries(priorityScores)
            .sort((a, b) => b[1] - a[1])
            .map(([tier, score]) => (
              <div key={tier} className="flex items-baseline gap-2">
                <dt className="text-supporting text-muted-foreground">{tier}</dt>
                <dd className="font-data text-body text-foreground" data-numeric>
                  {formatNumber(score)}
                </dd>
              </div>
            ))}
        </dl>
      </section>

      <section className="flex flex-col gap-3">
        {fields.map((field) => (
          <WeightRow
            key={field.key}
            wireKey={field.key}
            label={field.label}
            symbol={field.symbol}
            unit={unitFor(field, live)}
            value={drafts[field.key] ?? ''}
            invalid={invalidKeys.has(field.key)}
            onChange={(value) => onChange(field.key, value)}
          />
        ))}
      </section>

      {passthrough.length === 0 ? null : (
        <section className="flex flex-col gap-2">
          {/*
            Live keys this console does not edit, shown rather than hidden.

            `screens.md` §4's rule is that an admin can see what they are changing FROM, and a key
            that silently participates in every score while being invisible in the editor is the
            same class of problem this whole tab exists to prevent. They are also sent back
            unchanged on simulate and publish (`lib/policy.ts::buildProposedWeights`), so showing
            them is also showing the payload.
          */}
          <h3 className="text-label text-muted-foreground uppercase tracking-wide">
            Also in this policy, not editable here
          </h3>
          <dl className="flex flex-wrap gap-x-6 gap-y-2">
            {passthrough.map((key) => (
              <div key={key} className="flex items-baseline gap-2">
                <dt className="font-data text-supporting text-muted-foreground">{key}</dt>
                <dd className="font-data text-body text-foreground" data-numeric>
                  {formatNumber(live[key])}
                </dd>
              </div>
            ))}
          </dl>
          <p className="text-supporting text-muted-foreground">
            These are read by the same scoring formula and are round-tripped unchanged when you
            simulate or publish — dropping them would silently score against the engine&rsquo;s
            built-in defaults instead of the configured values.
          </p>
        </section>
      )}

      <FairnessDangerZone
        live={live}
        unlocked={fairnessUnlocked}
        onUnlock={onUnlockFairness}
      />

      <div>
        <Button
          variant="constructive"
          aria-disabled={!canSimulate}
          tabIndex={0}
          title={canSimulate ? undefined : whyNotSimulate}
          aria-describedby={canSimulate ? undefined : whyId}
          className={canSimulate ? undefined : 'opacity-50'}
          onClick={() => {
            if (!canSimulate) return
            onSimulate()
          }}
        >
          Simulate against last 30 days
        </Button>
        {canSimulate ? null : (
          <span id={whyId} className="sr-only">
            {whyNotSimulate}
          </span>
        )}
        <p className="mt-2 text-supporting text-muted-foreground">
          Compares {windowLabel}. The simulation is read-only — it never writes a policy version.
        </p>
      </div>
    </div>
  )
}

/**
 * One coefficient row: visible label, editable value, visible unit.
 *
 * `accessibility.md`'s policy-editor rule — "a screen reader announces the label + unit together
 * ('Lateness weight, per minute, 4') rather than a bare '4' with no context" — is implemented with
 * `aria-describedby` pointing at the unit text, matching `mockup.html` §8's own
 * `aria-describedby="p8-late-u"` wiring rather than re-inventing it.
 *
 * `type="text"` with `inputMode="numeric"`, not `type="number"`: two of the four coefficients are
 * negative by design, spinner arrows on a policy weight are a mis-click waiting to happen, and a
 * `number` input reports an empty string for anything the browser considers invalid — which would
 * make a typo indistinguishable from a cleared field. Same choice the mockup made.
 *
 * The wire key is part of the described text on purpose. Every gap this surface has hit has been a
 * name mismatch between a design document and the shipped contract, so the key the value is
 * actually sent under is on screen next to it.
 */
function WeightRow({
  wireKey,
  label,
  symbol,
  unit,
  value,
  invalid,
  onChange,
}: {
  wireKey: string
  label: string
  symbol: string
  unit: string
  value: string
  invalid: boolean
  onChange: (value: string) => void
}) {
  const fieldId = useId()
  const unitId = `${fieldId}-unit`

  return (
    <div className="grid items-center gap-x-4 gap-y-1 sm:grid-cols-[minmax(0,16rem)_7rem_minmax(0,1fr)]">
      <label htmlFor={fieldId} className="text-body text-foreground">
        {label} (<span className="font-data">{symbol}</span>)
      </label>
      <Input
        id={fieldId}
        type="text"
        inputMode="numeric"
        autoComplete="off"
        spellCheck={false}
        value={value}
        aria-describedby={unitId}
        aria-invalid={invalid || undefined}
        className="font-data text-right"
        data-numeric
        onChange={(event) => onChange(event.currentTarget.value)}
      />
      <span id={unitId} className="text-supporting text-muted-foreground">
        {unit} · sent as <span className="font-data">{wireKey}</span>
        {invalid ? (
          <span className="block text-danger-fg">
            Enter a number — this value cannot be simulated or published.
          </span>
        ) : null}
      </span>
    </div>
  )
}

/**
 * `components.md` §4 / `screens.md` §4 / `mockup.html` §8's fourth block — the fairness-term Danger
 * Zone, and Screen 9's entry point. **FR-ADM-007.**
 *
 * ## The visual separation IS the signal, and it is not decoration
 *
 * `components.md` §4: *"This is the one weight field with its own confirmation gate, deliberately
 * inconsistent with every other field in §3's editor — the inconsistency *is* the point, matching
 * the Admin Panel checklist's Danger Zone pattern: visual separation is what signals 'this one is
 * different,' not a note buried in copy an admin could skim past."* Hence its own card, its own
 * border colour and its own icon.
 *
 * ## Live as of 2026-09-02 (issue #69), and why the previous objection is genuinely retired
 *
 * E5.6 refused to build this because *"what it would be confirming is fictional"* — `w_fairness`
 * was not a term in the shipped formula at all. It is now: a live `score_weights` key at `0`,
 * multiplied by a per-carrier concentration count in `feasibility.py::_rank_slot`, with the
 * simulator carrying the same term and reporting `fairness_term_evaluated`. Verified by reading
 * `constraints.json` and `feasibility.py:558-559` in this session, not from the issue's state — see
 * `lib/flags.ts::adminFairnessTermEnabled` for the full check.
 *
 * ## An enabled term is stated differently from a disabled one, and neither is hardcoded
 *
 * The value comes from `live_weights`, so *"Currently disabled (0)"* is a real reading of the
 * engine rather than the artboard's literal string. Once non-zero it says so, because an admin
 * arriving at a policy someone else already enabled must not be shown the default copy.
 *
 * ## A no-op button is not offered
 *
 * Once the gate has been passed the Enable action is **gone**, not disabled — there is nothing left
 * to enable, and Flow 7 step 3 puts disabling back on the ordinary weight-field path rather than a
 * second gate. What replaces it is a line saying the field is now editable above.
 */
function FairnessDangerZone({
  live,
  unlocked,
  onUnlock,
}: {
  live: PolicyWeights
  unlocked: boolean
  onUnlock?: () => void
}) {
  const whyId = useId()
  const [dialogOpen, setDialogOpen] = useState(false)
  const value = live[FAIRNESS_KEY]
  const known = typeof value === 'number'
  const enabled = known && value !== 0
  const why = 'Enabling the fairness term is gated on issue #69, which is still in progress.'

  return (
    <section
      aria-labelledby={`${whyId}-title`}
      className="flex items-start gap-3 rounded-md border border-warning-border bg-warning-bg px-4 py-3 text-warning-fg"
    >
      <ShieldAlert className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
      <div className="flex flex-col gap-2">
        <h3 id={`${whyId}-title`} className="text-body font-semibold">
          Fairness term (<span className="font-data">{FAIRNESS_KEY}</span>) —{' '}
          {known ? (
            <>
              currently {enabled ? 'enabled' : 'disabled'} (
              <span className="font-data" data-numeric>
                {formatNumber(value)}
              </span>
              )
            </>
          ) : (
            'not present in the engine'
          )}
        </h3>
        <p className="text-supporting">
          Enabling this is a business-risk decision, not routine tuning — see the
          carrier-concentration canary.
        </p>

        {!adminFairnessTermEnabled ? (
          <>
            <Button
              variant="cautionary"
              aria-disabled
              tabIndex={0}
              title={why}
              aria-describedby={whyId}
              className="mt-1 self-start opacity-50"
            >
              Enable fairness term
            </Button>
            <span id={whyId} className="sr-only">
              {why}
            </span>
            <InactiveNote>
              <strong className="font-semibold">Gated on issue #69.</strong> The term is real in the
              engine now — <code>{FAIRNESS_KEY}</code> is a live <code>score_weights</code> key and
              the ranking formula multiplies it by a per-carrier concentration count — but the
              Danger-Zone flow (<code>flows-and-states.md</code> Flow 7) is switched off here.
              Whatever value the engine holds is sent back unchanged when you simulate or publish
              from this tab; this console does not edit it.
            </InactiveNote>
          </>
        ) : unlocked ? (
          <p role="status" className="text-supporting">
            <strong className="font-semibold">Editable above.</strong> Setting it back to{' '}
            <span className="font-data">0</span> is an ordinary weight edit and needs no
            confirmation — the friction is on turning it on. Any non-zero value still has to be
            simulated and published like every other weight.
          </p>
        ) : (
          <>
            {/* `mockup.html` §8: "a neutral button ... it is a gated action button, not a switch a
                cursor can slip onto." A toggle is excluded by name in the prompt; this stays a
                button that opens a confirmation. */}
            <Button
              variant="neutral"
              className="mt-1 self-start"
              onClick={() => setDialogOpen(true)}
            >
              Enable fairness term
            </Button>
            <FairnessDangerDialog
              open={dialogOpen}
              onOpenChange={setDialogOpen}
              onEnable={() => onUnlock?.()}
            />
          </>
        )}

        <ChurnNote />
      </div>
    </section>
  )
}

/**
 * Why `mockup.html` §8's fifth weight row — Churn (`P_churn`) — is absent rather than inert.
 *
 * This note survives independently of the fairness gate, which is exactly why it was split out of
 * `FairnessDangerZone`'s `false` branch: the two used to share a flag and no longer do. `P_churn`'s
 * dependency is the **Sequencer (#49)**, not #69, and an admin looking for the field the artboard
 * draws needs the reason whether or not fairness is enabled.
 *
 * Re-verified against the backend in this session: `P_churn` is not a key in `constraints.json`'s
 * `score_weights`, and `admin_governance_service.BLOCKED_WEIGHT_KEYS` still refuses it by name with
 * a 422 `UNKNOWN_WEIGHT_KEYS`. A field whose value the API rejects on submit is worse than no
 * field — so nothing is rendered to type into, and this says why.
 */
function ChurnNote() {
  if (adminChurnWeightEnabled) return null
  return (
    <InactiveNote>
      <strong className="font-semibold">
        Churn (<code>{CHURN_KEY}</code>) is not offered as a field.
      </strong>{' '}
      It is not a weight this API accepts: the key is refused with a 422 naming its own reason —{' '}
      <code>{CHURN_KEY}</code> counts promises the facility sequencer moved, and the sequencer
      (issue #49) is not shipped as a ranking term. A field with nowhere to send its value is worse
      than no field, so <code>mockup.html</code> §8&rsquo;s Churn row is deliberately absent rather
      than rendered inert.
    </InactiveNote>
  )
}
