import { InactiveNote, NotYetAvailable } from './primitives'
import { adminFairnessTermEnabled, adminPolicyEditorEnabled } from '../lib/flags'

/**
 * Screens 8, 9 and 10 — the Policy tab. **All three render honest stubs.**
 *
 * This is a **stronger block than `implementation-spec.md` §3's own table**, which marks Screen 8
 * and Screen 10 🟡 (buildable in reduced form) and only Screen 9 🔴. Stated as a disagreement
 * rather than quietly applied, with the evidence that changed the call:
 *
 * **The gap the spec did not catch (new this build): there is no read endpoint for the active
 * policy version or the live score weights anywhere in the API.** `backend/app/api/v1/routers/
 * admin.py` exposes exactly two policy routes — `POST /policy/simulate` and `POST /policy/publish`
 * — and grepping the whole of `app/api/` for `policy_version` / `score_weights` / `ranking_policy`
 * turns up nothing else. `simulate_policy_weights` loads `constraints.json` **server-side**
 * (`admin_governance_service.py:251`) and never returns the live weights it compared against.
 *
 * Two design requirements are unsatisfiable as a direct result:
 *   - `components.md` §3 requires a read-only current-version header (version, publish date,
 *     publisher). `policy_versions` has no read route.
 *   - `screens.md` §4 requires "the current policy is always visible above the editor so an admin
 *     can see what they're changing *from*."
 *
 * And the four routine weight fields would have to be seeded from somewhere. Hardcoding
 * `4 / -6 / 1 / -25` into this file — which is what makes those numbers byte-match
 * `constraints.json` in the mockup — duplicates server configuration into a client that cannot
 * detect drift, and `AGENTS.md`'s "never invent … operational data" applies squarely to a value
 * every future ranking decision is stamped with. Publishing weights an admin never saw the
 * current values for is exactly the failure U27's simulate-before-publish gate exists to prevent.
 *
 * **Screen 9 (the fairness Danger Zone) is separately and independently blocked** on A-G1 /
 * issue #69: `w_fairness` and `P_churn` are real §D7/§5 formula terms that do not exist in
 * `feasibility.py::_rank_slot`, in `constraints.json`'s four-key `score_weights`, or in
 * `admin_governance_service.py::_score`'s verbatim copy of that formula. `SimulatePolicyBody.
 * weights` is an untyped `dict[str, Any]`, so a `w_fairness` an admin typed would be **silently
 * ignored** and still return a real-looking `flip_count` — worse than a rejection, and the
 * specific reason the Danger Zone is not rendered as a real-looking control.
 *
 * Nothing here is a fake editor, a fake version header or a fake simulation. `AGENTS.md`: "Never
 * invent shipment, ETA, dock, appointment, capacity, or operational data."
 */
export function PolicyTab() {
  if (adminPolicyEditorEnabled) {
    // Unreachable until a policy read endpoint exists. Left as the documented shape this branch
    // takes rather than a half-built editor nobody can currently exercise.
    return (
      <NotYetAvailable
        title="Policy editor placeholder."
        body="adminPolicyEditorEnabled was flipped before the editor was built. Build the weight editor, simulate and publish flows here."
      />
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <NotYetAvailable
        title="The policy weight editor isn’t available yet."
        body="Nothing in the API reads the active policy version or the live score weights — /policy/simulate and /policy/publish are the only two policy routes, and simulate reads constraints.json server-side without returning it. An editor that can’t show what you’re changing from can’t satisfy the simulate-before-publish gate it exists for."
      />

      <div className="mx-auto flex max-w-[70ch] flex-col gap-3">
        <InactiveNote>
          <strong className="font-semibold">Weight editor and simulation.</strong> Blocked on a
          missing read endpoint for the active policy version (a new finding from this build — no
          issue number yet). Publish and simulate both exist and work; the baseline they would be
          compared against is not fetchable.
        </InactiveNote>

        {adminFairnessTermEnabled ? null : (
          <InactiveNote>
            <strong className="font-semibold">Fairness term (w_fairness) Danger Zone.</strong>{' '}
            Blocked on issue #69. <code>w_fairness</code> and <code>P_churn</code> are real
            SOLUTION_DESIGN §D7/§5 formula terms that do not exist in the shipped ranking formula.
            A value entered for either is accepted by the API and silently contributes nothing, so
            the typed-confirmation gate would be confirming something fictional.{' '}
            <code>P_churn</code> additionally depends on the Sequencer (issue #49), unbuilt.
          </InactiveNote>
        )}

        <InactiveNote>
          <strong className="font-semibold">Concurrent-publish conflict.</strong> Issue #75 —{' '}
          <code>publish_policy_version</code> takes no expected-current-version argument and
          unconditionally supersedes whatever is active, so two admins racing both succeed
          silently. <code>edge-cases.md</code> #3 specifies a named refusal; no copy template for
          it exists either (<code>mockup.html</code> §10.D flags this itself).
        </InactiveNote>
      </div>
    </div>
  )
}
