/**
 * Admin-surface feature flags.
 *
 * Named for the DEPENDENCY, not the feature — the convention E5.1/E5.2/E5.3 established
 * (`features/driver/lib/flags.ts`, `features/ops/lib/flags.ts`, `features/planner/lib/flags.ts`)
 * so that reading a flag name tells you what removes it, not merely what it hides. Grouped by the
 * SCREEN BLOCK each gap gates, per `06-admin-console/implementation-spec.md` §3's own table,
 * rather than one flag per issue number.
 *
 * All seven default OFF. Each names the issue(s) that gate it and the exit criterion.
 *
 * **What is NOT behind a flag, deliberately:**
 *
 *  - **Screen 5 (Facility Rules list).** `implementation-spec.md` §3 marks it 🟡 on A-G2 (#70),
 *    but the weakening is that the design docs name a stale registry, not that the read fails.
 *    Per this build's brief and the spec's own Fork A recommendation (§6), the list is built
 *    against the **live, shipped** five-value registry (`lib/rule-types.ts`). Nothing to gate.
 *  - **A-G7 / issue #75 (no version-conflict detection on `publish_policy_version`).** There is
 *    no rendered element to gate: the Policy tab is already behind
 *    `adminPolicyEditorEnabled`, and `mockup.html` §10.D flags in its own note that no copy
 *    template for the conflict state exists to render either. Recorded here rather than given a
 *    flag with nothing behind it.
 *  - **The Audit tab's free-text search box.** Not built at all, no flag — `get_audit_log` has no
 *    search parameter, and `flows-and-states.md` Flow 8 explicitly forbids client-side filtering
 *    of an already-fetched audit page ("the log can be arbitrarily large"). Both paths are closed,
 *    so there is nothing to gate. See `components/audit-tab.tsx`'s own comment; reported as a
 *    new finding rather than papered over.
 */

/**
 * Gates the multi-facility half of the Users tab and the invite/edit form — the Scope column
 * rendering more than one facility, and the chip multi-select with "+ Add facility".
 *
 * **Default OFF. Single-facility rendering is NOT behind this flag** and ships today: this gap
 * *weakens* Screens 2 and 3 rather than blocking them (`implementation-spec.md` §3: 🟡, §5.1 G4).
 *
 * Why (A-G4, issue #72): `user_scopes` is a real table built for exactly this
 * (`20260823090000_e23_identity_model.sql`) and `account_service.get_account_profile` already
 * reads `scoped_facility_ids` from it — but `admin_user_service.py`'s `list_users` reads only the
 * single `users.facility_id` column (line 168), and `invite_user`/`update_user` take
 * `scope: str | None`, a bare single value that `_validate_scope` requires exactly one of
 * (lines 134-142). `screens.md`'s own first example row ("Neha B. · Ops · Jaipur, Gurugram")
 * cannot be produced by the shipped tool.
 *
 * **Exit criterion:** issue #72 closed, then flip to `true`.
 */
export const adminMultiFacilityScopeEnabled = false

/**
 * Gates the Users tab's pending-invitation row — the "◔ Invited, awaiting acceptance" badge and
 * its Resend / Revoke actions (`mockup.html` §2.1's fourth row).
 *
 * **Default OFF.** Active and Inactive rows ship unconditionally.
 *
 * Why (A-G5, issue #73): `invite_user` sets `is_active = 1` at creation
 * (`admin_user_service.py:220`) — there is no distinct "invited, not yet accepted" state in the
 * schema or the response, and no `resend_invite`/`revoke_invite` endpoint exists at all.
 * `last_login_ts IS NULL` is the only available proxy and it conflates "genuinely pending" with
 * "account exists, this person simply hasn't signed in yet" — a different fact, and rendering a
 * badge off it would be inventing a state the system does not track.
 *
 * **Exit criterion:** issue #73 closed (a real invite lifecycle plus the two tools), then flip.
 */
export const adminPendingInvitesEnabled = false

/**
 * Gates one sentence in the Remove-user confirmation: "This user owns N active escalations — they
 * will show as unowned once removed."
 *
 * **Default OFF, and Screen 4 ships regardless** — this is a single-field enrichment, not a
 * blocker (`implementation-spec.md` §3 marks Screen 4 🟢, §5.1 G8: "Ship the dialog without that
 * specific sentence").
 *
 * Why (A-G8, issue #76): `remove_user`'s only read is `SELECT user_id, auth_user_id FROM
 * public.users WHERE user_id = :uid` (`admin_user_service.py:365-369`). No join to
 * `escalation_queue`, no count of any kind, and no other endpoint returns one either. The other
 * two consequence lines the dialog shows ARE true of the shipped tool and are rendered
 * unconditionally.
 *
 * **Exit criterion:** issue #76 closed, then flip to `true`.
 */
export const adminRemovalImpactEnabled = false

/**
 * Gates Screen 6 entirely — the facility-rule editor (Add rule / Edit rule), including the
 * type-specific value-field mechanism and the effective-window sub-flow.
 *
 * **Default OFF. This is a hard block (🔴), not a weakening.**
 *
 * Why (A-G2, issue #70): `components.md` §2's signature feature — "the value field set is
 * entirely driven by `rule_type`... there is no free-text 'value' field that could hold
 * anything" — is designed around `DOCK_PIN` / `EARLY_LIMIT` / `WEIGHT_LIMIT` /
 * `NEW_START_CUTOFF`, and the live `CHECK` constraint accepts none of those four
 * (`20260825213000_e34_policy_versions_and_rule_registry.sql:19-24`). The **list** is built
 * against the live registry per this build's brief; the **editor** cannot be, because three of
 * the five live types (`HEAVY_DOCK_REQUIRED_KG`, `REEFER_DOCK_REQUIRED`, `NO_SHOW_GRACE_MIN`)
 * have no field set designed anywhere — `implementation-spec.md` §6 Fork A option 1 says so in
 * as many words ("no existing artboard models these three"). Building one here would be
 * inventing design, and shipping a generic free-text value field instead would violate the one
 * rule §2 states outright.
 *
 * Why also #71 (A-G3): the editor's effective-window control offers a day-of-week + hour-range
 * recurring pattern. `feasibility.py::active_facility_rules` (lines 218-246) evaluates
 * `effective_from`/`effective_to` as a plain absolute instant range; nothing downstream parses a
 * weekly pattern out of the `TEXT` column. A saved "Weekdays only, 18:00–23:59" would be stored
 * and silently never enforced.
 *
 * **Exit criterion:** issue #70 closed (registry reconciled and the three uncovered types
 * designed) AND issue #71 closed (engine support), then flip to `true`.
 */
export const adminRuleEditorEnabled = false

/**
 * Gates Screen 7 — the dependent-appointment confirmation that names how many already-`CONFIRMED`
 * appointments a tightened rule would affect, before the edit commits.
 *
 * **Default OFF. Hard block (🔴).** Doubly gated in practice, since `adminRuleEditorEnabled` is
 * the only entry point to it.
 *
 * Why (A-G6, issue #74): `update_facility_rule` (`admin_governance_service.py:138-167`) is a bare
 * `UPDATE ... COALESCE`. No query anywhere in the backend counts or names the appointments a rule
 * edit would affect. This is the same shape as planner's `get_dock_block_impact` — a real,
 * narrowly-scoped read this surface needs and does not have — which is exactly why the gap is
 * gated rather than approximated client-side: `edge-cases.md` #4's whole point is naming the
 * count *before* the write, and a guessed count is worse than none.
 *
 * **Exit criterion:** issue #74 closed, then flip to `true`.
 */
export const adminRuleImpactEnabled = false

/**
 * Gates the whole Policy tab's weight editor, the simulate action, and Publish (Screens 8 and 10).
 *
 * **Default OFF — and this is a STRONGER block than `implementation-spec.md` §3's own table,
 * which marks Screens 8 and 10 🟡.** Stated as a disagreement with the spec, not slipped in:
 *
 * The gap the spec did not catch is that **there is no read endpoint for the active policy
 * version or the live score weights anywhere in the API.** `backend/app/api/v1/routers/admin.py`
 * exposes exactly two policy routes — `POST /policy/simulate` and `POST /policy/publish` — and
 * grepping `app/api/` for `policy_version` / `score_weights` / `ranking_policy` returns nothing
 * else. `simulate_policy_weights` loads `constraints.json` **server-side**
 * (`admin_governance_service.py:251`) and never returns the live weights it compared against.
 *
 * Consequences, both of which the design forbids working around:
 *   - `components.md` §3 requires a "read-only current-version header (version number, publish
 *     date, publisher)" and `screens.md` §4 requires "the current policy is always visible above
 *     the editor so an admin can see what they're changing *from*." Neither is fetchable.
 *   - The four routine weight fields would have to be seeded from somewhere. Hardcoding
 *     `4 / -6 / 1 / -25` into the frontend duplicates server configuration into a client that
 *     cannot detect drift, and `AGENTS.md`'s "never invent … operational data" applies squarely
 *     to a value every future ranking decision is stamped with.
 *
 * Publishing weights an admin never actually saw the current values for is precisely the failure
 * U27's simulate-before-publish gate exists to prevent, so the tab renders an honest stub rather
 * than a working-looking editor over an unknown baseline.
 *
 * Also gated by issue #69 for the fairness half — see `adminFairnessTermEnabled`.
 *
 * **Exit criterion:** a `GET /api/v1/admin/policy` (active version + live weights) exists —
 * filed as a new finding this build, no issue number yet — then flip to `true`.
 */
export const adminPolicyEditorEnabled = false

/**
 * Gates the fairness-term Danger Zone (Screen 9 entirely, plus the fairness box and the Churn
 * (`P_churn`) field inside Screen 8, plus any fairness-carrying simulation on Screen 10).
 *
 * **Default OFF. Hard block (🔴) on the surface's own flagship feature.**
 *
 * Why (A-G1, issue #69): `w_fairness` and `P_churn` are real `SOLUTION_DESIGN.md` §D7/§5 formula
 * terms and neither exists in the live ranking engine. `constraints.json`'s `score_weights` has
 * four keys only, and `feasibility.py::_rank_slot`'s formula — which
 * `admin_governance_service.py::_score` copies verbatim — has no fairness or churn term.
 * `SimulatePolicyBody.weights` is an untyped `dict[str, Any]` (`admin.py:93`), so sending
 * `w_fairness` produces **no error at all**: it is silently ignored, and an admin would get a
 * real-looking `flip_count` back with the field having contributed nothing. That is worse than a
 * rejection, and it is the specific reason this is a flag rather than a "just leave the field in,
 * it's harmless" call.
 *
 * `P_churn`'s own definition depends on the Sequencer (§7.5.3, issue #49), which is entirely
 * unbuilt — the third surface in a row to hit that root cause, after ops and planner.
 *
 * **Exit criterion:** issue #69 closed (at minimum `w_fairness` as a real formula term; `P_churn`
 * additionally depends on #49), then flip to `true`.
 */
export const adminFairnessTermEnabled = false
