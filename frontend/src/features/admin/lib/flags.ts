/**
 * Admin-surface feature flags.
 *
 * Named for the DEPENDENCY, not the feature — the convention E5.1/E5.2/E5.3 established
 * (`features/driver/lib/flags.ts`, `features/ops/lib/flags.ts`, `features/planner/lib/flags.ts`)
 * so that reading a flag name tells you what removes it, not merely what it hides. Grouped by the
 * SCREEN BLOCK each gap gates, per `06-admin-console/implementation-spec.md` §3's own table,
 * rather than one flag per issue number.
 *
 * Each names the issue(s) that gate it and the exit criterion.
 *
 * **Re-audited 2026-08-29 (M5 flag-flip audit), again 2026-08-31, and again later the same day.**
 * Four of the seven are now ON: `adminRemovalImpactEnabled`, `adminPolicyEditorEnabled`, and — with
 * `GET /admin/facilities` (#78) landing — `adminMultiFacilityScopeEnabled` and
 * `adminPendingInvitesEnabled`. Every flag below was re-checked against the live router and service
 * source, not against its issue's state — the issues are mostly still OPEN, because this repo
 * closes on owner review, so OPEN carries no information about whether the code exists.
 *
 * **#78's own flag does not exist, deliberately.** The facilities read is not an optional feature
 * to gate: without it two other flags cannot flip, and the thing it replaces (an option list
 * derived from already-loaded rows) is not a fallback worth keeping — it was wrong in exactly the
 * case the endpoint exists to serve. So it was wired unconditionally and the workaround deleted.
 *
 * **Four flags' stated reasons had gone stale by 2026-08-31 and are corrected in place** — the
 * corrections matter more than the flips, because a stale reason is how a wrong flip happens:
 *  - `adminPolicyEditorEnabled`: its blocker (no read for the active version or live weights) is
 *    gone, and the editor is now built. Flipped.
 *  - `adminRuleEditorEnabled`: #70/#71 are resolved; the blocker is now **missing design**, not a
 *    backend gap. Its "stored and silently never enforced" claim was also **backwards** — see
 *    that block. Still OFF.
 *  - `adminRuleImpactEnabled`: the endpoint now exists; the blocker is that its only entry point
 *    (Screen 6) does not. Still OFF.
 *  - `adminFairnessTermEnabled`: **its stated reason is stale and is deliberately left untouched
 *    here** — `w_fairness` *is* now a live `score_weights` key and unknown keys are *no longer*
 *    silently dropped (they are a 422). A concurrent agent owns that flag and the work behind it
 *    (#69); rewriting its comment mid-flight would clobber theirs. Flagged, not edited.
 *
 * **What is NOT behind a flag, deliberately:**
 *
 *  - **Screen 5 (Facility Rules list).** `implementation-spec.md` §3 marks it 🟡 on A-G2 (#70),
 *    but the weakening is that the design docs name a stale registry, not that the read fails.
 *    Per this build's brief and the spec's own Fork A recommendation (§6), the list is built
 *    against the **live, shipped** five-value registry (`lib/rule-types.ts`). Nothing to gate.
 *  - **A-G7 / issue #75 (version-conflict detection on `publish_policy_version`).** Nothing to
 *    gate: the backend guard exists (`based_on_version_id`, `BASE_VERSION_REQUIRED` 422,
 *    `ALREADY_ACTIONED` 409) and Screen 10 now renders both refusals unconditionally
 *    (`components/policy-simulation-panel.tsx`'s `PublishConflict`) — a conflict is not an
 *    optional feature to flag off. **The copy template `mockup.html` §10.D flagged as missing was
 *    written by this build**, following §7.5.1's "name the winning transition" rule rather than
 *    inventing a register. #75's own implementation also corrected this gap's premise: the
 *    truly-simultaneous race never silently succeeded, it died on `idx_policy_versions_one_active`
 *    as a raw 500; the **sequential** case (A simulates, B publishes, A publishes) is the one that
 *    silently overwrote. Both are handled.
 *  - **The Audit tab's free-text search box.** Not built at all, no flag — `get_audit_log` has no
 *    search parameter, and `flows-and-states.md` Flow 8 explicitly forbids client-side filtering
 *    of an already-fetched audit page ("the log can be arbitrarily large"). Both paths are closed,
 *    so there is nothing to gate. See `components/audit-tab.tsx`'s own comment; reported as a
 *    new finding rather than papered over.
 */

/**
 * Gates the multi-facility half of the Users tab and the invite/edit form — the Scope column
 * rendering more than one facility, and the facility multi-select.
 *
 * **ON since 2026-08-31, as ONE flag — the split the 2026-08-29 audit recommended was NOT taken,
 * because the reason for splitting it went away.** That audit's own words: "the read half is now
 * real ... the write half has an unresolved blocker of its own: issue #78, still OPEN with no
 * implementation". #78 landed in this same change (`GET /api/v1/admin/facilities`), so both halves
 * are servable at the same moment and a split would have created two flags that could only ever be
 * flipped together.
 *
 * ## What was verified before flipping, on both halves
 *
 * **Read half**, against `admin_user_service.list_users`:
 *  - `scoped_facility_ids` is returned per row via `COALESCE(array_agg(us.scope_value ORDER BY
 *    us.scope_value), ARRAY[]::text[])` over `user_scopes`, with a documented fallback to the
 *    primary `users.facility_id` mirror for a row predating E2.3's backfill — so a single-facility
 *    user never renders an empty Scope cell.
 *  - `facility_filter` matches on **either** side of that mirror, so a user whose primary facility
 *    is Jaipur but who also holds Gurugram appears under a Gurugram filter.
 *  - Wired here: `AdminUser.scoped_facility_ids` is typed, and `users-table.tsx`'s `ScopeCell`
 *    comma-joins the server's array through the facility directory's `nameOf`.
 *
 * **Write half**, against the same file plus `routers/admin.py`:
 *  - `InviteUserBody.scope` / `UpdateUserBody.scope` are `str | list[str] | None` on the wire.
 *    The form sends an **array**; `normalize_scope` treats a one-element array and a bare string
 *    identically, so there is no second encoding to keep straight.
 *  - `_validate_scope` checks a whole multi-select in one `= ANY(:ids)` round trip and names every
 *    missing id at once; it refuses `SCOPE_NOT_MULTI_VALUED` (422) for DRIVER/CARRIER rather than
 *    silently truncating to the first entry. Those two roles render Inactive here anyway — no
 *    endpoint lists carriers or drivers — so the refusal is a backstop, not the UI's guard.
 *  - `_write_user_scopes` deletes all three managed scope types before inserting, so a role change
 *    cannot leave a stale row behind, and it carries `ON CONFLICT ... DO NOTHING` against
 *    `UNIQUE (user_id, scope_type, scope_value)`. The form de-duplicates too, so neither side
 *    depends on the other to be correct.
 *  - `update_user` applies a **scope-only** edit by re-reading the role from the database. The
 *    edit form still submits both, since its role select is pre-filled and may have been changed.
 *
 * **The option list is what made the write half real.** A multi-select over the previous
 * derived-from-loaded-rows list would have been a worse control than the single `<select>` it
 * replaced — that was the audit's exact objection, and #78 is what answers it.
 *
 * **NOT verified: a live HTTP round trip.** No running backend and no authenticated admin session
 * were available. Stated plainly, the same way `adminRemovalImpactEnabled` and
 * `adminPolicyEditorEnabled` record their own boundaries. The failure modes are bounded on the
 * server: an unknown facility is `INVALID_SCOPE` (422) naming the id, an empty selection cannot be
 * submitted (the button stays `aria-disabled` with its reason), and every scope write is validated
 * server-side before any row is touched.
 *
 * **One deliberate divergence from the artboard, flagged rather than silent:** the multi-select is
 * a native checkbox group in a `<fieldset>`, not `screens.md`'s `[ Jaipur ▾ ] [ + add ]` chip row.
 * Reasoning in `components/invite-user-dialog.tsx`'s header. Owner call if the chips are wanted.
 *
 * **Delete criterion:** once #72 is closed and reviewed, delete this flag and the two branches that
 * read it (`ScopeCell`'s array branch, the dialog's checkbox-vs-select branch).
 */
export const adminMultiFacilityScopeEnabled = true

/**
 * Gates the Users tab's pending-invitation row — the "Invited, awaiting acceptance" badge and its
 * Resend / Revoke actions (`mockup.html` §2.1's fourth row, `screens.md` §2).
 *
 * **ON since 2026-08-31.** Active and Inactive rows ship unconditionally as before.
 *
 * ## The wrong flip this flag existed to prevent, and how it is now structurally impossible
 *
 * The previous comment's warning was the important part and it is preserved here: `last_login_ts`
 * is **read** in two places and **written nowhere in the application** — only `seed.sql` sets it —
 * so `user.last_login_ts === null`, which is what this row used to gate on, would have labelled
 * essentially the entire user list "Invited" the moment the flag flipped.
 *
 * That predicate is gone. The badge now gates on **`lifecycle_state === 'INVITED'`**, derived
 * server-side by `admin_user_service.derive_lifecycle_state` from three real stamps
 * (`invited_at` / `invite_accepted_at` / `removed_at`, migration
 * `20260831132101_users_invite_lifecycle.sql`). `lib/types.ts::lifecycleStateOf` is the only place
 * a missing field falls back, and it falls back to `ACTIVE`/`DEACTIVATED` — **never** to `INVITED`,
 * so even a pre-migration backend cannot reproduce the old failure.
 *
 * ## What was verified before flipping
 *
 *  - **The fork #73 named was decided in favour of local columns**, and the migration's own header
 *    records why: option (b) — joining GoTrue's admin user list inside `list_users` — would put a
 *    synchronous external call on this tab's main read, and would report a *removed* user's status
 *    as unknown rather than removed, since `remove_user` deletes the Auth identity outright.
 *  - **The accept stamp has a writer that cannot be forgotten**, which is the whole reason this is
 *    not a repeat of `last_login_ts`: `core/deps.py::get_execution_context` writes
 *    `invite_accepted_at` on the first authenticated request an invited user ever makes. A request
 *    either resolved an `ExecutionContext` or was never authenticated.
 *  - **Both tools exist and are role-gated**: `POST /users/{id}/resend-invite` and
 *    `POST /users/{id}/revoke-invite`, both `AdminCtx`, the second requiring an `Idempotency-Key`.
 *    Neither accepts an email — the address is read from the stored row (M15).
 *  - **The refusals are rendered by code, not by message**: `AUTH_EMAIL_RATE_LIMITED` (429),
 *    `NOT_PENDING_INVITE` (409) and `USER_REMOVED` (409) each get their own copy through
 *    `hasApiErrorCode` in `users-tab.tsx::describeWriteFailure`.
 *  - Backend: the 12 lifecycle/resend/revoke tests in `tests/unit/test_e34_admin_console.py` pass.
 *
 * ## What this actually looks like in production right now
 *
 * **No Invited rows at all.** The migration is applied but deliberately unbackfilled — every
 * existing user has `invited_at IS NULL`, which `derive_lifecycle_state` correctly reports as
 * `ACTIVE`, because those accounts were seeded rather than invited through this console. So the
 * flip's visible effect today is *nothing changes*, and that is the correct rendering, not a
 * failure to load. The first Invited row appears the first time an admin actually invites someone.
 *
 * **NOT verified: a live HTTP round trip, and no rendered Invited row against real data** (there
 * are none to render). The gallery plate at `/admin/_states` covers the populated case against a
 * fixture whose three lifecycle stamps are shaped exactly as the service returns them.
 *
 * **Delete criterion:** once #73 is closed and reviewed, delete this flag and the `invited` guard
 * in `users-table.tsx` — but keep `lifecycleStateOf`, which is not a flag concern.
 */
export const adminPendingInvitesEnabled = true

/**
 * Gates one sentence in the Remove-user confirmation: "This user owns N active escalations — they
 * will show as unowned once removed."
 *
 * **ON since 2026-08-29.** Flipped in the M5 flag-flip audit, and wired in the same change —
 * `remove-user-dialog.tsx` now fetches the count instead of rendering the sentence blind.
 *
 * **What was verified before flipping**, not merely that #76 has an implementation comment:
 *  - `GET /api/v1/admin/users/{user_id}/removal-impact` is registered
 *    (`backend/app/api/v1/routers/admin.py:180`) and carries `AdminCtx` — the same
 *    `require_roles`-derived dependency every other read this surface already calls uses, so it is
 *    reachable by exactly the sessions that reach the Users tab.
 *  - `admin_user_service.get_user_removal_impact` (line 552) returns `active_escalation_count` as a
 *    `CAST(count(*) OVER () AS integer)` evaluated **before** its own `LIMIT 50`, so the headline
 *    number stays true when the sample list is truncated. The client reads that field and never
 *    `active_escalations.length`.
 *  - "Owns" is `escalation_queue.owner_user_id` with `escalation_status <> ALL(terminal)`, which is
 *    the same ownership concept `edge-cases.md` #1 means. An `OPEN` escalation has no owner, so it
 *    correctly contributes nothing.
 *  - 404 on an unknown user, 403 when `ctx.is_admin` is false — both already handled by the
 *    dialog's swallow-and-omit path.
 *
 * **Not verified: a live round trip.** No authenticated admin session was available in this pass,
 * and #76's own implementation note says the new SQL has not been executed against a live
 * PostgreSQL either. The failure mode is deliberately the pre-flip behaviour rather than a broken
 * screen — a throw leaves `impactCount` at `null`, the sentence is omitted, and the removal still
 * proceeds, because this read is advisory and `remove_user` recounts inside its own transaction.
 *
 * **Delete criterion:** once #76 is closed and reviewed, delete this flag and the two conditions
 * in `remove-user-dialog.tsx` that read it (the fetch guard and the render guard).
 */
export const adminRemovalImpactEnabled = true

/**
 * Gates Screen 6 entirely — the facility-rule editor (Add rule / Edit rule), including the
 * type-specific value-field mechanism and the effective-window sub-flow.
 *
 * **Default OFF. This is a hard block (🔴), not a weakening.**
 *
 * **The blocker changed on 2026-08-31 and is no longer a backend one.** #70 and #71 are both
 * resolved — #70 reconciled the design docs to the live five-value registry, and #71 resolved to a
 * doc correction (recurring intraday effectivity is deliberately unbuilt, not pending). **What
 * remains missing is DESIGN**, and it is not a small remainder:
 *
 *  - Three of the five live types (`HEAVY_DOCK_REQUIRED_KG`, `REEFER_DOCK_REQUIRED`,
 *    `NO_SHOW_GRACE_MIN`) have no field set designed anywhere — `implementation-spec.md` §6 Fork A
 *    option 1 says so in as many words ("no existing artboard models these three").
 *  - `DOCK_PIN`, which has **no live analog at all**, was the only two-field type in the design —
 *    i.e. it was the entire demonstration of `components.md` §2's type-driven field mechanism. The
 *    pattern the editor was designed around does not exist in the shipped registry.
 *
 * Building either here would be inventing design, and shipping a generic free-text value field
 * instead would violate the one rule §2 states outright ("there is no free-text 'value' field that
 * could hold anything"). The **list** is built against the live registry per E5.6's brief; the
 * **editor** stays off.
 *
 * **Corrected 2026-08-31 — this comment previously stated the opposite of the real behaviour, in
 * the dangerous direction.** It said a recurrence string saved into `effective_from`/`effective_to`
 * would be "stored and silently never enforced". It is the reverse: `feasibility.py::parse_rule_boundary`
 * returns `None` — meaning **no bound on that side** — both for an empty value *and* for a
 * non-empty value that no accepted shape parses (its own docstring says so, and there is now a
 * characterisation test pinning it). So a saved "Weekdays only, 18:00–23:59" makes the rule apply
 * **always**, not never. "Never enforced" reads as *worst case, the rule does nothing*; the truth
 * is *worst case, the rule blocks everything* — an over-applying rule rejects intervals the
 * facility would actually accept. Anyone reasoning from the old wording would have misjudged the
 * risk in the safe-sounding direction.
 *
 * **Exit criterion:** field sets designed for the three uncovered live types, and a decision on
 * what replaces `DOCK_PIN` as §2's worked example. Not an issue-close; a design deliverable.
 */
export const adminRuleEditorEnabled = false

/**
 * Gates Screen 7 — the dependent-appointment confirmation that names how many already-`CONFIRMED`
 * appointments a tightened rule would affect, before the edit commits.
 *
 * **Default OFF — but the reason changed on 2026-08-31. The backend gap is closed; the entry
 * point is what is missing.**
 *
 * `GET /api/v1/admin/facility-rules/{rule_id}/impact` now exists
 * (`admin_governance_service.get_facility_rule_impact`, A-G6 / issue #74), built to
 * `get_dock_block_impact`'s shape and evaluating through `feasibility.py`'s own
 * `active_facility_rules`/`check_facility_rules` rather than re-implementing rule semantics — so
 * the preview and the enforcing engine cannot disagree.
 *
 * **It stays off because Screen 7 has no way in.** This flag gates the confirmation that names
 * what a rule edit would break *before it commits*; the only thing that can raise that
 * confirmation is Screen 6's rule editor, which is `adminRuleEditorEnabled` and is blocked on
 * missing design (above). A confirmation dialog for an edit that cannot be started is not a
 * screen, and flipping this today would reveal nothing.
 *
 * **When it is wired, it needs FOUR states, not a count** — verified by reading the service's own
 * return envelope, because a bare "N affected" would misrepresent three of them:
 *  1. `affected_count` — appointments this *edit* newly breaks. The number `edge-cases.md` #4 means.
 *  2. `already_non_compliant_count` — appointments the rule *already* excludes, independent of the
 *     edit. Folding these into (1) would blame the admin's change for pre-existing state.
 *  3. `evaluable: false` — the rule type is one the feasibility engine deliberately never enforces
 *     (`CHECKIN_EARLY_LIMIT_MIN` is a gate-arrival rule; `NO_SHOW_GRACE_MIN` needs an injected
 *     clock that does not exist). **This is a real answer, not an error and not a zero**: nothing
 *     can be broken retroactively by editing a rule nothing checks at offer time.
 *  4. `active_flag = 0` — the rule is inactive, so the engine never loads it and the edit affects
 *     nothing until it is reactivated. Also a real answer.
 *  Plus `truncated` / `scanned_count`: the scan is bounded at 500 rows and says so rather than
 *  quietly under-reporting.
 *
 * **Exit criterion:** `adminRuleEditorEnabled` is unblocked AND all four states above are rendered
 * distinctly. Do not flip on the count alone.
 */
export const adminRuleImpactEnabled = false

/**
 * Gates the whole Policy tab's weight editor, the simulate action, and Publish (Screens 8 and 10).
 *
 * **ON since 2026-08-31. Screens 8 and 10 are built** (`components/policy-tab.tsx`,
 * `policy-version-header.tsx`, `policy-weight-editor.tsx`, `policy-simulation-panel.tsx`).
 *
 * ## What was verified before flipping, and what was not
 *
 * Verified, mechanically rather than by reading source alone — this flag's whole history is a
 * warning about trusting a comment:
 *  - **The request contract, against the running app's own OpenAPI schema** (generated from
 *    `create_app()`): `GET /api/v1/admin/policy/active` exists; `POST /policy/simulate` declares
 *    exactly `weights` / `window_start` / `window_end`, all required, `additionalProperties: false`;
 *    `POST /policy/publish` declares `weights` (required) + `based_on_version_id` (optional) and an
 *    `Idempotency-Key` header parameter. The client sends exactly those and nothing else.
 *  - **The response contract, against the backend's own passing tests** — 13 policy tests in
 *    `tests/unit/test_e34_admin_console.py` pin every field this client reads:
 *    `active_version.policy_version_id`, `live_weights`, `engine_matches_active_version` (all three
 *    of its cases, including "never published"), `superseded_version_id`, and the
 *    `BASE_VERSION_REQUIRED` / `ALREADY_ACTIONED` codes. Re-run here: 13 passed.
 *  - **The error envelope**: `core/errors.py` + `core/envelope.py` put the code in
 *    `errors[0].code`. The shared `apiPost` used to discard it, which is why this surface carried a
 *    local `AdminApiError`; since 2026-08-31 it throws `ApiError` (`core/http/errors.ts`) carrying
 *    `code`/`detail`/`status`, and the local duplicate is gone. `policy-tab.tsx` branches on
 *    `isApiError(e) && e.code`, which is the same discrimination, centrally provided.
 *  - `tsc -b`, `oxlint`, `vite build` clean.
 *
 * **NOT verified: a live HTTP round trip.** No running backend and no authenticated admin session
 * were available in this environment. Stated plainly rather than implied, the same way
 * `adminRemovalImpactEnabled` records its own boundary.
 *
 * The flip is defensible despite that gap because **no failure mode of this client produces a
 * wrong write**: every guard is server-side (idempotency key, required baseline, weight-key
 * allowlist), the editor renders no field until `GET /policy/active` has answered — so it cannot
 * display an invented coefficient — and a broken read degrades to `LoadFailed`, a broken simulate
 * or publish to a named banner. The `false` branch is kept so the tab can be switched off without
 * deleting it.
 *
 * ## The history this replaces
 *
 * This flag was originally set stronger than `implementation-spec.md` §3's own 🟡 marks, on the
 * grounds that **no read endpoint existed for the active policy version or the live score
 * weights.** That gap was filed as #77 and has since been closed in substance by #75's own pass:
 *
 *  - **`GET /api/v1/admin/policy/active` now exists** (`routers/admin.py:258` →
 *    `admin_governance_service.get_active_policy_version`). Verified by reading the router, not
 *    from the issue text. It returns the active `policy_versions` row, `constraints.json`'s live
 *    score weights, and an `engine_matches_active_version` flag — that last field specifically
 *    because `publish_policy_version` deliberately does **not** rewrite the file the ranking engine
 *    reads, so an admin could otherwise be shown an "active" version the engine is not using.
 *  - So `components.md` §3's read-only current-version header and `screens.md` §4's "always visible
 *    above the editor" are both now fetchable, and the four weight fields can be seeded from the
 *    server instead of hardcoded. The `AGENTS.md` "never invent operational data" objection that
 *    made this a hard stub no longer applies.
 *  - #75 also added the version-conflict guard `edge-cases.md` #3 requires: `based_on_version_id`
 *    is **required whenever an active version exists** (`BASE_VERSION_REQUIRED`, 422), and a stale
 *    baseline returns `ALREADY_ACTIONED` (409) naming the winning version id and its publisher.
 *    The editor must send it — an optional guard is not a guard.
 *
 * Screens 8/10 are built for the **four routine weights only**. The fairness half is still gated
 * by `adminFairnessTermEnabled` (#69), which this build does not touch — the Danger Zone renders
 * Inactive with its reason, and `w_fairness` is round-tripped unchanged rather than edited or
 * dropped. `P_churn` is not offered at all: the API refuses the key with a 422.
 *
 * **Delete criterion:** once #77 is closed and reviewed, delete this flag and the `false` branch in
 * `components/policy-tab.tsx` that reads it.
 */
export const adminPolicyEditorEnabled = true

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
