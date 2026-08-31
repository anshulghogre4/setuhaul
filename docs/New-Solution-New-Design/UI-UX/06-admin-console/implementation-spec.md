# Implementation spec — admin console (E5.6)

> **M5 / E5.6 (issue #41).** The buildable translation of `06-admin-console/`'s locked design, on top of
> the design system E5.0 shipped and the tool catalog M3 actually closed. **This file defines no new design
> decisions.** Every value is copied from a foundations file, a surface file, `mockup.html`, or verified
> source in `backend/` / `supabase/`, with its source named. Where a value has no source, or two sources
> disagree, it is in §6 as a decision the owner has to make — not resolved here.
>
> **Read for this pass, and only these:** all six `06-admin-console/` files (`screens.md`,
> `flows-and-states.md`, `edge-cases.md`, `components.md`, `accessibility.md`, `stitch-prompts.md` — the
> last skimmed for artboard structure, not read line-by-line) plus `mockup.html`; `00-foundations/` —
> `color.md`, `typography.md`, `spacing-and-layout.md`, `accessibility-behaviour.md`; `SOLUTION_DESIGN.md`
> §D7, §5, §7.5.7; `02-ops-exception-console/implementation-spec.md` and
> `03-planner-dock-board/implementation-spec.md` (as templates and as the source of the shared-token fixes
> this surface has to check for); and the live `backend/app/api/v1/routers/admin.py`,
> `backend/app/services/admin_user_service.py`, `backend/app/services/admin_governance_service.py`,
> `backend/app/services/account_service.py`, `backend/app/scheduling/feasibility.py`,
> `backend/app/scheduling/constraints.json`, `supabase/migrations/20260805201923_setuhaul_baseline.sql`,
> `supabase/migrations/20260823090000_e23_identity_model.sql`,
> `supabase/migrations/20260825213000_e34_policy_versions_and_rule_registry.sql`.
>
> **Continuation note:** a prior pass on this exact issue was cut off mid-work by an account-wide Opus
> spend limit (its last line named "R2 contrast, R6/R7 hit areas, R12 overscroll, hero type tokens" as
> still-pending). This session is Sonnet specifically to avoid that limit. **Every one of those four named
> items was checked by measurement, not trusted from the comment**: R2 (contrast) and R12 (overscroll) had
> genuinely already been applied and re-verify clean; **R7 (search-box hit area) was genuinely already
> applied and correct; R6 (`.b-link` hit area) had *not* actually been fully applied despite its own inline
> comment claiming "grown to 44×44... the same technique `.chipx` already uses"** — measured at 18.6×44,
> not 44×44, and fixed properly this pass (§5.3, R20). "Hero type tokens" turned out not to correspond to
> anything in this file (no `hero` class or token exists anywhere in `typography.md` or the mockup) and is
> recorded as a stale/unfindable reference, not chased further.
>
> **Status: 4 of 12 screens build clean today, 5 are partially blocked, 3 are hard-blocked.** This is the
> *least* backend-blocked of the four surfaces audited so far in raw screen count (planner 10/30, ops 9/16,
> driver 24/28) — Users, Remove-user, Audit, and the empty/loading/error states are all fully and correctly
> backed. **But the surface's own flagship, most-emphasized feature — the fairness-term Danger Zone this
> project's own README names by title — has zero backend representation**, and a second severe gap
> (`facility_rules.rule_type`) blocks the Facility Rules tab's entire type-specific editor. Eight backend
> gaps found (§5.1), one of them (G1) the third surface in a row to hit the same root cause both
> `02-ops-exception-console/` and `03-planner-dock-board/` already found (the unbuilt Sequencer, issue #49).
> Twenty-seven rendering/ARIA defects found by measurement in a continuation pass over the prior session's
> partial work — three were structural HTML corruption (duplicated/garbled attribute strings, one live
> region announced twice), not just styling — **all twenty-seven fixed and re-measured.**

**Owner decisions still open: four (§6).**

---

## 0 · Starting point — what exists, verified not assumed

### 0.1 What M3 (E3.4, issue #28) actually shipped for this surface

E5.6's issue lists M3 as a blocker and M3 is closed. Checked tool-by-tool against `SOLUTION_DESIGN.md`
§7.5.7, read off source — not taken from the milestone's closed state.

| §7.5.7 tool | Shipped? | Source |
|---|---|---|
| `list_users` | ✅ Shipped | `admin_user_service.py:150` → `GET /api/v1/admin/users` |
| `invite_user` | 🟡 Shipped, narrower than designed | `admin_user_service.py:183` — single-facility scope only (§5.1 G4) |
| `update_user` | 🟡 Same narrowing | `admin_user_service.py:267` |
| `deactivate_user` / `reactivate_user` | ✅ Shipped, exactly as designed | `admin_user_service.py:332`/`337` — reversible, Moderate tier, role/scope untouched |
| `remove_user` | 🟡 Shipped, one enrichment missing | `admin_user_service.py:342` — High-tier, typed-confirmation-ready, idempotent, deletes the real Supabase Auth identity; the confirmation dialog's "owns N active escalations" count (`edge-cases.md` #1) has no backing query (§5.1 G8) |
| `list_facility_rules` | ✅ Shipped | `admin_governance_service.py:68` |
| `create_facility_rule` / `update_facility_rule` | 🔴 Shipped against a different registry | `admin_governance_service.py:104`/`138` — `rule_type` enum is real and enforced, but not the one this surface's own design files specify (§5.1 G2) |
| `simulate_policy_weights` | 🟡 Shipped, honest, narrower than the mockup implies | `admin_governance_service.py:242` — read-only, self-documents its own approximation; silently ignores `w_fairness`/`P_churn` if sent (§5.1 G1) |
| `publish_policy_version` | 🟡 Shipped, one guarantee missing | `admin_governance_service.py:305` — immutable versioning, idempotent; no version-conflict detection (§5.1 G7) |
| `get_audit_log` | ✅ Shipped | `admin_governance_service.py:373` |
| `export_audit_log` | ✅ Shipped, filter-respecting | `admin_governance_service.py:400` |

**11 of 11 tools exist as callable endpoints — a materially better starting point than planner's 2.5 of 9
or ops's 7 of 8.** The gap on this surface is not missing tools; it is tools that exist but were built
against a different data contract than this surface's own design files describe, in three separate,
independently-confirmed ways (§5.1).

Also verified alongside, and this part is genuinely good:

| Fact | Source |
|---|---|
| The admin router is role-gated to `ADMIN` only — deliberately narrower than `OPS_PORTAL_ROLES`, matching §7.5.7's persona scoping exactly | `admin.py:3-7` |
| `remove_user`/`invite_user` are the only writes in the whole backend that create/delete a real Supabase Auth login identity, and correctly use the service-role key, not the anon key E3.5's self-service tools use | `admin_user_service.py:8-12` |
| `remove_user` deactivates rather than hard-deletes the local `users` row — `audit_logs`/`escalation_queue.resolved_by_user_id` FKs reference it | `admin_user_service.py:346-351` |
| Every write on this console is idempotent where §19's High tier requires it (`remove_user`, `publish_policy_version`) via the shared `lookup_idempotency`/`store_idempotency` mechanism | `admin_user_service.py:355-363`, `admin_governance_service.py:316-324` |
| Every write on this console lands in `audit_logs` through the same M14 mechanism every other tool uses — no separate, weaker audit path for admin's own actions (`flows-and-states.md` Flow 9) | Confirmed in `invite_user`/`remove_user`; `create_facility_rule`/`publish_policy_version` write their own domain rows which the Audit tab reads back |
| `export_audit_log` genuinely respects the caller's current filter set, never a silent full dump | `admin_governance_service.py:400-430` |

### 0.2 The frontend after E5.0–E5.5

| Fact | Consequence for E5.6 |
|---|---|
| `theme.css` carries every token this surface references — no new colour needed | Confirmed: every fix in §5.3 below reuses an existing functional token (`text-secondary`, `blue-400`, `status-active`), never a new one |
| `identity.ts` gives admin `density: comfortable`, no facility scope, a rail | `data-density="comfortable"` at the route root; two-destination rail (this console + account), matching `accessibility.md`'s "office desk, low time pressure" framing |
| **Rail-Profile duplication, settled project-wide 2026-08-29** — the rail's second item duplicated the top-bar account control; already dropped from ops's and planner's mockups (their own Fork E/Fork H) | Applied directly here per the owner's explicit direction mid-pass, not re-raised as a new fork — all 20 frames now single-destination rail. See the mockup's own header comment at the first `<nav class="rail2">` occurrence. |
| Issue **#52 is OPEN** — `/auth/me` returns one `role_name`, not `grants[]` | Does not affect this surface directly (admin is a single fixed role, not multi-role); noted for completeness only |

---

## 1 · The console shell — four tabs, one workspace

`screens.md` §1. Four tabs (U102-style pattern, matching ops/planner's own tab-not-route reasoning),
never a permanent split — this is the broadest single surface in the product but still one workspace.

```
┌──┬──────────────────────────────────────────────────────────────────────────────────┐
│▌ │ Admin   [ Users ] Facility Rules  Policy  Audit        🔔  ?  ⚙︎  AB              │  56px top bar
├──┼───────────────────────────────────────────────────────────────────────────────────┤
│56│ role="main"                                                                        │
│  │   Users tab           → list + invite/edit/remove flows                            │
│  │   Facility Rules tab  → registry table + rule editor                                │
│  │   Policy tab          → weight editor, fairness Danger Zone, simulate → publish     │
│  │   Audit tab           → filtered log, export                                        │
└──┴──────────────────────────────────────────────────────────────────────────────────┘
```

Rail: 56px, **one destination — this console** (Profile now lives only in the top-bar account button,
per the cross-surface fix above). `screens.md` §1's own stated reason still holds: "no facility switcher,
since admin actions span facilities by nature."

Density: `spacing-and-layout.md`'s table gives admin `comfortable` alongside carrier portal and driver
chat — 44px rows, 40px controls, 24px content padding, all confirmed against the rendered mockup (§2
below), not just the CSS declaring them.

---

## 2 · Density and measurement baseline

This is a dense, four-tab, 20-artboard surface. The brief asked for the same rigor given to narrower
surfaces, on the stated basis that "contrast/tap-target/ARIA regressions hide easiest in dense UI." Method:
headless Chromium (Playwright 1.62.1) over `file://`, computed styles and `getBoundingClientRect` across
all 20 frames, contrast computed from **rendered** `rgb()` values against each element's effective
background (walking the ancestor chain), full ARIA census over the live DOM, three colour-scheme
conditions (light default, OS dark preference emulated, opt-in `data-theme="dark"`), and a dedicated
tab-strip/tabpanel wiring check (below) — not just a duplicate-`id` scan, since two of this pass's defects
were *consistent* ids that pointed to the *wrong* element rather than colliding with another one.

| | Before this pass | After |
|---|---|---|
| Duplicate `id` attributes | 0 (none had *collided*) | 0 |
| Tab strips whose `aria-controls`/tabpanel `id`/`aria-labelledby` were internally mismatched | **4** (3 different artboards, one compounding into a second) | **0** — verified by walking every `.frame`, not just scanning `id` uniqueness |
| `role="tabpanel"` present | 18 / 20 | **20 / 20** |
| Duplicated live-region announcement (`aria-live` fires twice for one event) | 1 | 0 |
| `role="main"` | 0 / 20 | **20 / 20** |
| Contrast failures, light | **14** (7 unique color/bg pairs) | **0 real** (6 retracted — disabled-button text, exempt per WCAG 1.4.3, see §5.3) |
| Contrast failures, dark | **28** (10 unique pairs — 2 genuinely new to dark: a tab-selected state and a hardcoded-not-tokenized status colour) | **0 real** (6 retracted, same disabled-button class) |
| Targets < 24×24 (WCAG 2.2 SC 2.5.8 AA floor), raw element box | 31 | 27 raw, **0 real** (all 27 are false positives from measuring the element instead of its effective hit area — verified individually, see §5.3) |
| `@media (prefers-color-scheme: dark)` rules | 0 (already clean before this pass) | 0 |
| `--surface-base` under emulated OS dark preference (should stay light; U69) | `#F8FAFC` (already correct) | `#F8FAFC` |
| Text under 11px floor | 0 | 0 |
| `overscroll-behavior: contain` on `.modal`/`.menu` | 15/15, 2/2 (already correct — a prior-pass fix, re-verified not re-applied) | 15/15, 2/2 |
| Rail Profile duplication | 20 instances | **0** — cross-surface fix applied |

**No regressions**: re-ran the full suite after every fix, not just once at the end (caught the `tp4`
duplicate-id collision my own §12.C fix introduced against a *third*, previously-undiscovered instance of
the same corruption class at §12.B — see §5.3's R23 note).

---

## 3 · The 12 screens → build readiness

Twelve numbered artboard groups in `mockup.html` (`1 · Console shell` through `12 · Empty, loading and
error states`), matching issue #41's own "12 screens" count and `stitch-prompts.md`'s ordering.

**Legend:** 🟢 buildable today · 🟡 buildable, partially blocked · 🔴 blocked by a §5.1 gap.

| # | Screen | Gap | Build |
|---|---|---|:--:|
| 1 | Console shell | — | 🟢 |
| 2 | Users tab | G4, G5 | 🟡 |
| 3 | Invite / edit user modal | G4 | 🟡 |
| 4 | Remove user — typed confirmation | G8 | 🟢 |
| 5 | Facility Rules tab | G2 | 🟡 |
| 6 | Facility rule editor | **G2 — hard**, G3 | 🔴 |
| 7 | Dependent-appointment confirmation | **G6 — hard** | 🔴 |
| 8 | Policy tab — weight editor + fairness Danger Zone | **G1 (fairness half) — hard** | 🟡 |
| 9 | Enable fairness term — Danger Zone confirmation | **G1 — hard** | 🔴 |
| 10 | Policy simulation — four states | G1 (partial), content-shape note | 🟡 |
| 11 | Audit tab | — | 🟢 |
| 12 | Empty, loading and error states | — | 🟢 |

**Tally: 🟢 4 · 🟡 5 · 🔴 3.**

### Screen 1 — Console shell 🟢
No backend dependency. Tabs, rail, top-bar icons, status all render from static shell state. Fully fixed
this pass (landmarks, tab wiring, rail).

### Screen 2 — Users tab 🟡
`list_users` returns real rows (name/email/role/facility_id/is_active/last_login_ts) and search/filter
are genuinely queryable. **Two things in the mockup's own first example row can't be produced**:
- **Multi-facility scope display** ("Neha B. · Ops · Jaipur, Gurugram") — `list_users` reads only the
  single `users.facility_id` column, never `user_scopes` (G4). The column would show at most one facility.
- **The "◔ Invited" pending-invitation row with Resend/Revoke** — no distinguishable pending state and no
  resend/revoke tool exist (G5). Build the Active/Inactive rows; the Invited row has nothing to render from.

### Screen 3 — Invite / edit user modal 🟡
Single-flow invite/edit (role + scope in one submission) is real and matches `flows-and-states.md` Flow 1
closely — but the mockup's own scope control ("`[ Jaipur ▾ ] [ + add ]`", implying multiple facility
chips for an ops-scoped role) has no API to submit more than one facility (G4). Build a single-facility
picker; the `+ add` affordance has nowhere to send its second value.

### Screen 4 — Remove user, typed confirmation 🟢
The mechanism is fully real: typed-email confirmation, `Idempotency-Key`, real Supabase Auth deletion,
local deactivation preserving audit FK integrity, audit-logged. **One enrichment is unbacked** (G8): the
confirmation copy naming "This user owns 2 active escalations" has no query behind the number. Ship the
dialog without that specific sentence, or wire a new count — either way this doesn't block the core flow.

### Screen 5 — Facility Rules tab (list) 🟡
`list_facility_rules` is a plain, correct read — the table itself renders. **The `rule_type` values it
returns will never match this surface's own copy, icons, or filter labels** (G2) — the list is readable
but every value in the "Rule type" column will be an unfamiliar string.

### Screen 6 — Facility rule editor 🔴
Hard-blocked on two compounding gaps. **G2**: `components.md` §2's entire type-specific-field-set
mechanism — the tab's signature feature — is built around `DOCK_PIN`/`EARLY_LIMIT`/`WEIGHT_LIMIT`/
`NEW_START_CUTOFF`, none of which the live `CHECK` constraint accepts. **G3**: the day-of-week + hour-range
"intraday effectivity" UI (checkboxes for Mon–Sun, two time pickers) has no engine support — the live
ranking code only evaluates a single absolute `effective_from`/`effective_to` instant range, never a
recurring weekly pattern. Neither gap is a styling problem; both need real design-vs-schema reconciliation
before this screen is buildable as drawn.

### Screen 7 — Dependent-appointment confirmation 🔴
Hard-blocked on G6: no tool anywhere computes which appointments a rule edit would affect. The screen's
whole reason to exist — naming the count before the edit commits, per `edge-cases.md` #4 and
`components.md` §2's High-tier pattern — has nothing to query.

### Screen 8 — Policy tab (weight editor + fairness box) 🟡
Four of the five stage-2 coefficients are fully real, and their *shown values match the live constraints
file exactly* (`4`, `-6`, `1`, `-25` — a genuinely good sign this part of the surface was built against
real data). **The fifth field (Churn/`P_churn`) and the entire fairness Danger-Zone box are inert** (G1) —
editable in the UI, silently ignored by the scoring formula underneath.

### Screen 9 — Enable fairness term, Danger-Zone confirmation 🔴
Hard-blocked on G1. This is the surface's single most-emphasized requirement (`screens.md` calls it
"locked this checkpoint," `components.md` §4 gives it its own anatomy section, this project's own README
names it "Danger-zone fairness-term gate" as one of E5.6's headline deliverables) — and `w_fairness` does
not exist as a term in the shipped `_score()` formula at all. The typed-confirmation mechanism itself is
buildable (it's the same pattern as Screen 4/`remove_user`'s); what it would be confirming is fictional.

### Screen 10 — Policy simulation, four states 🟡
`simulate_policy_weights` is real, read-only, and honestly self-documents its own approximation
(`admin_governance_service.py`'s module docstring is a model of the "Source: assumption" discipline this
project asks for elsewhere) — the loading/result/stale/error states are all buildable. Two caveats, not
blockers: **(a)** any `w_fairness`/`P_churn` value an admin enters is silently no-op'd by the same formula
gap as Screen 8/9 — a simulation "using" fairness would report identical flip counts regardless of the
value; **(b)** a content-shape mismatch — the mockup's copy ("SHP1014 vs SHP1009 — under these weights,
SHP1014 loses to SHP1009") implies a head-to-head comparison between two shipments contesting one slot,
but the tool actually compares one shipment's own current appointment against alternative slots at the
same facility. The aggregate "N of M would flip" headline is accurate either way; the per-case narrative
copy needs rewording to match what the tool actually returns, or the tool needs to return the head-to-head
shape the copy implies.

### Screen 11 — Audit tab 🟢
Fully real: filtered, recent-first, actor-id-carrying, system-attributed, export respects the active
filter set. The strongest area of the whole surface, matching `screens.md`'s own "full coverage, no gaps
found" self-assessment (independently confirmed, not just trusted — see §5.4's checklist audit).

### Screen 12 — Empty, loading and error states 🟢
No backend dependency — these are frontend-owned rendering states (skeleton rows, named empty states,
`role="alert"` failures). All render correctly after this pass's landmark/tabpanel fixes.

---

## 4 · What E5.6 adds to the design system

**Nothing new.** Every fix in §5.3 reuses an existing functional token
(`--text-secondary`, `--blue-400`, `--status-active`, `--border-focus`) or an existing structural pattern
already established elsewhere in this file (`.chipx::after`'s inset-overlay technique, extended to
`.b-link::after`; `role="main"` placement matching the same landmark discipline planner's R14 established).
One correction is owed **to** the design system rather than added by it: `--status-active` was defined with
both a light and dark value in `theme.css`'s token block from the start, but `.status-active` (the older,
Part-A-only usage) never referenced the token — it hardcoded `--green-700` directly, silently defeating the
dark override. Fixed to read the token like every other consumer of it (`.st-on`) already did.

---

## 5 · Readiness call

**Verdict: 4 of 12 screens build clean today. 5 are partially blocked (buildable in reduced form). 3 are
hard-blocked on backend gaps that are not UI decisions.** Twenty-seven rendering/ARIA defects found by
measurement, **all twenty-seven fixed and re-measured**, including three genuine structural corruptions
(not styling) inherited from the prior session's interrupted pass. Eight backend gaps found and escalated
rather than designed over.

### 5.1 Eight escalated gaps

> **Status as of 2026-08-29 — work has landed for seven of the eight; every issue is still OPEN in the
> tracker.** That distinction is deliberate and is this project's standing rule: an issue closes on
> verified evidence and owner review, not on an agent believing it finished. "Addressed" below means code
> or docs are on disk and tested; it does not mean closed. **The gap write-ups are left unedited** — they
> are the evidence the issues were filed on, and rewriting them would destroy the record of what was
> actually found. Each addressed gap carries a resolution note immediately after it.
>
> | Gap | Issue | Tracker | Work landed |
> |---|---|---|---|
> | G1 `w_fairness` / `P_churn` | #69 | OPEN | **Partly.** `w_fairness` built as a real, defaulted-off term; unknown weight keys now refused by name. `P_churn` remains genuinely blocked on the sequencer (#49) — refused rather than ignored. |
> | G2 `rule_type` registry | #70 | OPEN | **Docs reconciled** to the live five-value registry. `DOCK_PIN`'s missing analog and the two unmocked types are stated, not resolved. `mockup.html` untouched (out of scope). |
> | G3 intraday effectivity | #71 | OPEN | **Claim corrected; feature deliberately not built.** See the note under G3. |
> | G6 rule-edit impact | #74 | OPEN | **Built** — `GET /admin/facility-rules/{rule_id}/impact`. |
> | G4 multi-facility scope | #72 | OPEN | Addressed in an earlier 2026-08-29 pass. |
> | G5 pending invitations | #73 | OPEN | Not started. |
> | G7 publish version conflict | #75 | OPEN | Addressed in an earlier 2026-08-29 pass. |
> | G8 removal-impact count | #76 | OPEN | Addressed in an earlier 2026-08-29 pass. |
>
> **Screen 6 stays blocked even though both of its gating issues are closed**, and that is the one
> non-obvious outcome here. #70 removed the *wrong-names* half of the block; #71's resolution was to
> correct the claim rather than build recurrence. What remains is missing **design**, not missing backend:
> three of the five live rule types have no artboard field set, and the `DOCK_PIN` two-field pattern the
> editor was designed around has no live analog. `adminRuleEditorEnabled` should therefore stay off
> pending a design decision, while `adminRuleImpactEnabled` (#74) and `adminFairnessTermEnabled` (#69,
> `w_fairness` half only) are now genuinely unblocked.

Found the standing rule's way: cross-checked this surface's own design files (`screens.md`,
`components.md`, `edge-cases.md`, `flows-and-states.md`) against the actual shipped tool bodies and schema,
not against the tool *names* alone (all 11 names exist — the mismatch is one layer deeper, in argument
shapes, enum contents, and formula terms).

**G1 · 🔴 `w_fairness` and `P_churn` are real `SOLUTION_DESIGN.md` §D7/§5 formula terms — genuinely
absent from the live ranking engine, not an admin-console invention.** §D7 states the formula "*defines* a
per-carrier displacement penalty term with weight `w_fairness = 0`" (i.e. present, defaulted off — not
absent); §5's formula spells out `P_churn · |{ j : promise communicated ∧ |start_j − promised_j| > 15 min
}|`. Neither term appears in `constraints.json`'s `score_weights` (four keys only:
`lateness_per_minute`/`wait_after_eta_per_minute`/`fit_slack_per_minute`/
`compatible_but_not_exact_dock_penalty`) or in `feasibility.py::_rank_slot`'s formula, and
`simulate_policy_weights`'s own `_score()` copy inherits the identical gap by design (it's a direct copy of
the live formula, per its own module docstring). `SimulatePolicyBody.weights` is an untyped `dict[str,
Any]`, so passing `w_fairness`/`P_churn` produces no error — it is silently ignored, which is worse than a
rejection: an admin could reasonably believe they simulated a policy that uses fairness and get a real
`flip_count` back, with the field having contributed nothing. **This is the third surface in a row to hit
the identical root cause** `02-ops-exception-console/implementation-spec.md` (G9/#49) and
`03-planner-dock-board/implementation-spec.md` (G9/#49) already found: `P_churn`'s own definition (a count
of promises the Sequencer moved) depends on §7.5.3's re-sequencing machinery, which is entirely unbuilt.
`w_fairness` has no such excuse — it needs only a formula term and a schema column, not the Sequencer — but
it was never added either. **Gates Screens 8 (Churn field), 9 (the whole Danger Zone), and half of
Screen 10.**

> **Resolved in part, 2026-08-29 (issue #69).** `w_fairness` is now a real key in `constraints.json`
> shipping at `0`, evaluated by `_rank_slot` and by `admin_governance_service._score` (the copy the parity
> test pins). It multiplies **`carrier_concentration`** — the number of *other* active appointments this
> shipment's carrier already holds at the facility **on the candidate interval's facility-local date**.
> Keying on the local date rather than on the carrier alone is load-bearing: Stage 2 ranks one shipment's
> own candidates against each other, so a per-carrier constant could never reorder anything and would have
> been a term in name only. **No schema column was needed** — `shipments.carrier_id` already exists, so
> this gap's own "needs a schema column" framing turned out to overstate it. The concentration read is
> issued **only when the weight is non-zero**, so the shipped policy adds no round trip to
> `find_feasible_slots`' existing four. Byte-identity at `w_fairness = 0` is proved by recomputing the
> pre-change formula literally, across several concentration values, not by inspection.
>
> **The silent-ignore is fixed, which was the sharper half of this gap.** `simulate_policy_weights` and
> `publish_policy_version` now refuse any weight key the ranking engine does not read, with the allowlist
> derived at runtime from `constraints.json`'s own `score_weights` so it cannot drift from the engine.
> `P_churn` is refused **by name, with its reason stated** ("the sequencer is not built, so there is
> nothing to count") rather than lumped in as an unknown key. **`P_churn` itself remains blocked on #49
> and nothing here changes that** — Screen 8's Churn field still has no implementable backing, only an
> honest refusal to render against.

**G2 · 🔴 `facility_rules.rule_type`'s live registry does not match this surface's own design files, and
the mismatch traces to a known, previously-flagged, never-reconciled deviation.** `SOLUTION_DESIGN.md`
§7.5.7 itself states the registry as `EARLY_LIMIT`, `DOCK_PIN`, `WEIGHT_LIMIT`, `NEW_START_CUTOFF` — this
surface's `screens.md`, `components.md`, `edge-cases.md`, and `mockup.html` all correctly inherit those
exact names from the spec. **The live migration's `CHECK` constraint enforces a completely different
five-value set**: `HEAVY_DOCK_REQUIRED_KG`, `LAST_NEW_START_TIME`, `CHECKIN_EARLY_LIMIT_MIN`,
`NO_SHOW_GRACE_MIN`, `REEFER_DOCK_REQUIRED`
(`supabase/migrations/20260825213000_e34_policy_versions_and_rule_registry.sql:19-24`). This is not new —
`admin_governance_service.py`'s own module docstring already says so ("the five real rule_type values
seeded in facility_rules, not SS7.5.7's illustrative and unmatched example names"), and `wiki/log.md`'s
2026-08-25 16:07 entry for E3.4 independently confirms the implementer knew and made the substitution
deliberately. **What never happened is this surface's own design files getting updated to match** — the
UI-UX pass for `06-admin-console/` came after E3.4 shipped (per this project's own roadmap) but inherited
`SOLUTION_DESIGN.md`'s stale names rather than the actually-shipped registry, the same "spec drift the
downstream consumer never re-checked" shape as planner's `dock_occupancy.state` gap. Rough correspondence
exists for three of five real types (`CHECKIN_EARLY_LIMIT_MIN`≈`EARLY_LIMIT`,
`LAST_NEW_START_TIME`≈`NEW_START_CUTOFF`, `HEAVY_DOCK_REQUIRED_KG`≈`WEIGHT_LIMIT`, all renamed only); the
mockup's flagship `DOCK_PIN` two-field pattern (dock + cargo-type pairing) has no live analog at all, and
two real types (`NO_SHOW_GRACE_MIN`, `REEFER_DOCK_REQUIRED`) have zero mockup representation. **Gates
Screen 6 entirely, weakens Screen 5.**

> **Resolved as a documentation correction, 2026-08-29 (issue #70). The live registry wins.** E5.6's
> frontend already builds against it (`features/admin/lib/rule-types.ts`), so making the docs the party
> that moves is the only option that leaves one truth rather than two. Reconciled: `SOLUTION_DESIGN.md`
> §7.5.7 (now carrying the full five-value table with each type's value shape and whether the feasibility
> engine enforces it), `screens.md` §3, `components.md` §2, `edge-cases.md` #4 and #7,
> `flows-and-states.md` Flow 5.
>
> **Two things this correction deliberately does not fix**, restated here because renaming everything else
> makes them easy to lose: `DOCK_PIN` has **no live analog** — and it was the *only* registry entry
> requiring two value fields, i.e. the whole demonstration of `components.md` §2's type-driven field
> mechanism; `REEFER_DOCK_REQUIRED` carries RULE003's intent as a boolean, which is narrower, not
> equivalent. And `NO_SHOW_GRACE_MIN`/`REEFER_DOCK_REQUIRED` still have **zero artboard representation**,
> with `HEAVY_DOCK_REQUIRED_KG`'s field set only inferable from the stale `WEIGHT_LIMIT` frame. **Screen 6
> therefore stays gated after this closes, on missing design rather than on backend** — a generic
> free-text value field would violate the one rule §2 states outright. Screen 5 (the list) is unweakened
> and ships.
>
> **`mockup.html` was NOT edited** — this pass owned the folder's `.md` files only. It still renders the
> four stale names, and that divergence is now the one remaining instance of this gap. Flagged for the
> owner rather than left silent.

**G3 · 🔴 "Intraday effectivity" (day-of-week + hour-of-day recurring window) has no engine support.**
`screens.md` §3 states this "genuinely support[s] intraday effectivity... closing the exact gap the spec
named as unimplementable." Checked directly against the engine that would enforce it:
`feasibility.py::active_facility_rules` (lines 218-246) filters rules against a single instant `at` using
only `effective_from`/`effective_to` as a **plain absolute start/end range** (`if start is not None and at
< start: continue` / `if end is not None and at >= end: continue`) — there is no day-of-week or recurring
weekly-window concept anywhere in the evaluation. The column type itself (`TEXT`, unstructured, per the
baseline migration) can store whatever string the UI serializes, but nothing downstream parses a "Weekdays
only, 18:00–23:59" pattern out of it. The claim in `screens.md` is not true against the shipped engine.
**Gates Screen 6's effective-window sub-flow.**

> **Resolved 2026-08-29 (issue #71) by correcting the claim, not by building the feature. Stated plainly:
> recurring intraday effectivity is UNBUILT.** Not partially built, not built-but-rough — there is no
> day-of-week concept anywhere in the enforcing engine and none was added.
>
> **Why this fork went that way.** A correct recurring window wants real columns (`days_of_week`,
> `start_time_local`, `end_time_local`) and therefore a migration. The alternative — encoding recurrence
> into the existing unstructured `TEXT` column — would add a **third** undiscoverable shape to a column
> already carrying two (a bare date from the original seed, an offset-bearing ISO timestamp from the demo
> overlay), invisible to SQL and unenforceable by any constraint, and would put its parser inside
> `active_facility_rules` — which `evaluate_candidate_slot` calls **once per candidate interval, up to 500
> per search**, on the D1 booking hot path. No live rule uses recurrence, and D15's "intraday facility
> rules" means the *absolute* intraday windows that already work. Building unstructured recurrence into
> the ranking hot path to satisfy one mockup cell, at five-concurrent-user scale, is the wrong trade.
>
> **What was clarified rather than changed.** The absolute half of the claim was always true and is now
> stated precisely and pinned by test: an offset-bearing boundary really is hour-precise, so a rule *can*
> apply to part of one specific day. And a genuine hazard the original gap write-up did not reach was
> found and pinned: because an unparseable boundary yields *no bound on that side*, a recurrence string
> saved into that column today would make the rule apply **always**, not never — the opposite of the
> "stored and silently never enforced" the flag comment assumed. Behaviour deliberately left unchanged
> (over-applying rejects an interval; under-applying lets the system promise one the facility forbids, the
> worse failure for this product), but no longer undocumented.
>
> **Owner fork left open:** if recurring windows are actually wanted, they are a scoped schema change plus
> a hot-path parser, filed separately — not a doc fix and not a follow-on to this issue.

**G4 · 🟡 Multi-facility scope exists in the schema and is read elsewhere, but not by this surface's own
tools.** `user_scopes` (`supabase/migrations/20260823090000_e23_identity_model.sql`) is a real child table
built explicitly for this — its own migration comment names "a future multi-facility FACILITY_MANAGER" as
the exact scenario — and `account_service.get_account_profile` (E3.5) already reads `scoped_facility_ids`
from it correctly. **`admin_user_service.py`'s `list_users`/`invite_user`/`update_user` never read or write
`user_scopes` for facility-scoped roles** — only `list_users` reads the single `users.facility_id` column,
and `invite_user`/`update_user`'s `scope: str | None` parameter is a bare string, `_validate_scope`
requiring (not permitting) exactly one facility value. `screens.md`'s own first example row ("Neha B. ·
Ops · Jaipur, Gurugram") cannot be produced by `list_users` as shipped. Narrower blast radius than G1/G2 —
most users have one facility, and the single-facility path works correctly — but the specific claim
`flows-and-states.md` Flow 1 makes ("facility multi-select for ops/planner/gate") is false against the
admin console's own tools today. **Weakens Screens 2 and 3.**

**G5 · 🟡 No pending-invitation state or resend/revoke tools.** `invite_user` sets `is_active = 1`
immediately at creation (`admin_user_service.py:220`) — there is no distinct "invited, not yet accepted"
state anywhere in the schema or the response, and no `resend_invite`/`revoke_invite` endpoint exists at
all. `last_login_ts IS NULL` is the only available proxy, and it conflates "genuinely pending" with
"account exists, user simply hasn't logged in yet" — not the same fact. **Weakens Screen 2's pending row.**

**G6 · 🔴 No dependent-appointment-impact tool for facility rule edits.** `update_facility_rule`
(`admin_governance_service.py:138-167`) is a bare `UPDATE` with a `COALESCE` — no query anywhere counts or
names which appointments a tightened rule would affect. `edge-cases.md` #4 depends on this ("Tightening
`NEW_START_CUTOFF` from 21:00 to 20:00 could make an already-`CONFIRMED` appointment at 20:30 retroactively
non-compliant... the count of affected appointments before the edit commits") and it names the exact
scenario the mockup's own Screen 7 renders. This is the same shape as planner's `get_dock_block_impact` —
a real, buildable, narrowly-scoped read this surface needs and doesn't have. **Gates Screen 7 entirely.**

> **Resolved 2026-08-29 (issue #74).** `GET /api/v1/admin/facility-rules/{rule_id}/impact` —
> `admin_governance_service.get_facility_rule_impact`. Built to the same shape as
> `get_dock_block_impact`/`get_user_removal_impact` rather than a second shape for the same problem, and
> flagged in its own docstring as an **addition to §7.5.7's catalog**, not an implementation of it.
>
> Four decisions worth knowing before rendering Screen 7:
> - **It evaluates by calling the engine, not by re-implementing it.** `active_facility_rules` decides
>   *when* the proposed rule is in force; `check_facility_rules` decides *what* it forbids. A locally
>   rewritten "is 20:30 after 20:00" check would be correct until someone changed the engine's
>   strict-vs-inclusive boundary and not the copy — and each affected row carries the engine's own message
>   as `reason`, so the dialog cannot describe the breach differently from the check that will reject
>   future bookings.
> - **Two counts, not one.** `affected_count` is what this edit would *newly* break;
>   `already_non_compliant_count` is what the current rule forbids anyway. Only the first is a consequence
>   of pressing Save.
> - **`evaluable: false` is a real answer.** `CHECKIN_EARLY_LIMIT_MIN` and `NO_SHOW_GRACE_MIN` are not
>   enforced by the feasibility engine at all, so editing them cannot make anything retroactively
>   non-compliant. Render the returned `note`; a bare "0 affected" would read as "checked, nothing found".
> - **No wall-clock filter.** The scan is bounded by the proposed rule's own effectivity window. This
>   engine has no injected clock (§9.1), so a `now()` bound would return a confident "0 affected" against
>   any dataset whose snapshot clock differs from the wall clock — and a dialog that always says zero is
>   worse than one that says nothing.
>
> Pure read; `update_facility_rule` is unchanged, so `edge-cases.md` #4's "does not mutate or escalate"
> guarantee is structural rather than merely intended. **Screen 7 is unblocked**
> (`adminRuleImpactEnabled`), though its only entry point is Screen 6's editor, which stays gated on the
> G2 design gap above.

**G7 · 🟡 No version-conflict detection on `publish_policy_version`.** `edge-cases.md` #3 states: "if
another admin publishes a version between this admin's simulation and their own Publish attempt, the tool
refuses with a named conflict... same shape as `confirm_request`'s `ALREADY_ACTIONED`." Checked
`publish_policy_version` (`admin_governance_service.py:305-345`): it takes only `weights` and an
`Idempotency-Key`, unconditionally clears whatever row is currently active and inserts the new one — no
`based_on_version_id`/expected-current-version parameter exists to detect the race at all. Two admins
racing to publish will both succeed, the second silently superseding the first with no refusal, contrary
to the documented behaviour. Same class of gap as planner's G2 (`snapshot_hash` doesn't exist for
`confirm_request`) — a described optimistic-concurrency guarantee the shipped tool doesn't implement.

**G8 · 🟡 `remove_user`'s confirmation dialog cites an escalation count with no query behind it.**
`edge-cases.md` #1 locks specific copy: "This user owns 2 active escalations — they will show as unowned
once removed." `remove_user`'s only read (`admin_user_service.py:365-369`) is `SELECT user_id,
auth_user_id FROM public.users WHERE user_id = :uid` — no join to `escalation_queue`, no count of any
kind. The removal mechanism itself is otherwise fully correct (§0.1); this is a narrow, single-field
enrichment gap, not a blocker to the flow.

### 5.2 The shared-token reconciliation

The brief asked whether this surface inherits E5.1's/E5.2's/E5.3's shared-token corrections — and per
planner's own §5.2, whether `color.md`'s 2026-08-29 correction (`state-shown-border`, `state-held-border`,
the escalation-SLA pair) had propagated here.

**Not applicable in the direct sense**: this surface renders no promise-state chip and no SLA-urgency
colour anywhere — Users/Facility Rules/Policy/Audit have no dock-time-interval or escalation-countdown
concept, so the corrected tokens have nothing to bind to here. Confirmed by grep: zero occurrences of
`state-shown`/`state-held`/`state-pending`/`state-confirmed`/`sla-warning`/`sla-breach` anywhere in this
file. **This is the one surface of the four audited so far where the question is genuinely moot, not
merely unchecked.**

### 5.3 Twenty-seven defects — measured, not inspected · **ALL FIXED 2026-08-29**

Scoreboard in §2; every fix carries a dated inline comment in `mockup.html` at the site it changes.

**Three structural corruptions, found before any styling pass, inherited from the interrupted prior
session:**

**R25 · A live-region announcement was duplicated verbatim.** Two identical
`<p class="vh" role="status" aria-live="polite">Fields updated for DOCK_PIN</p>` lines in the rule editor —
a screen-reader user hears the same announcement twice for one field-set change. One copy removed.

**R26 / R27 · Two tabpanel `id`/`aria-labelledby` pairs were garbled into a single malformed attribute
string** — `id="tp5" role="tabpanel" aria-labelledby="t5-users" tabindex="0">id="tp6" role="tabpanel"
aria-labelledby="t6-users" tabindex="0">` (and the same shape for `tp1`/`tp2`). Read as HTML this renders
the *first* `id`/`aria-labelledby` pair (the browser stops at the first `>`), silently pointing every
affected tabpanel at the wrong tab. Found by grep (`id="tp[0-9]*" role="tabpanel"[^>]*>id=`), not by any
visual symptom — this is exactly the kind of defect that hides in dense, repetitive markup and would have
shipped invisibly. Both resolved to the half matching their own artboard's real tab strip.

**R23 · A second, distinct class of the same mismatch — consistent, non-colliding, but wrong.** Re-running
the tabpanel-wiring check after R26/R27 (not just a duplicate-`id` scan) found **three more artboards**
whose tab strip's `aria-controls` pointed at an `id` that either belonged to a *different* artboard
entirely (§12.C's tab strip was `t4-*`/`tp4`, selected tab "Audit," but its content `<div>` carried
`id="tp3" aria-labelledby="t3-users"` — someone else's ids, wrong tab too) or was simply absent (§12.D and
§12.F's tab strips referenced `tp3`/`tp1` that no element in their own artboard defined at all — `role=
"tabpanel"` was 0% present on either div). **Fixing §12.C's mismatch by giving it `id="tp4"` collided with
a pre-existing, previously-undiscovered fourth instance**: §12.B's own tab strip is `t5-*`/`tp5`, but its
content `<div>` already (wrongly) carried `id="tp4" aria-labelledby="t4-audit"` — the exact ids §12.C
needed. Assigning `tp4` to §12.C without knowing this produced a genuine duplicate, caught immediately by
re-running the duplicate-`id` check after the fix rather than trusting it clean, and fixed by correcting
§12.B to its own `tp5`/`t5-users`. All four now resolve to their own
artboard's actual tab strip, verified by a dedicated per-frame wiring check (not just uniqueness) that
confirms `tabs' aria-controls === panel.id` and `panel.aria-labelledby === selected-tab.id` across all 20
frames with zero mismatches.

**R21 · `role="main"` was absent from all 20 frames**, though all 20 correctly had a `<nav>`. A
keyboard/AT user had no way to skip straight to content. `.main2`/`.main` is already `role="tabpanel"` (a
widget role — can't also carry `role="main"`), so the landmark goes on the containing `.body` element
instead; nav nested inside main is valid ARIA where semantically justified, and it avoids restructuring 20
artboards' worth of markup to insert a new wrapping element. Verified: 20/20 after.

**R17 · `.status-active` (Part A) hardcoded `--green-700` instead of referencing `--status-active`**, so
`:root[data-theme="dark"]`'s correct override (`--status-active: var(--green-400)`) never took effect —
measured **3.68:1** under dark (need 4.5). `.st-on`, the Part-B equivalent, already referenced the token
correctly; this was the one holdout.

**R18 · Four functional-token usages of `text-tertiary` measured 4.34:1 against `surface-hover`/
`surface-raised`** (need 4.5 for 13px/400 text) — `.verhdr` (the policy-version header), `.sim .cap`
(simulation caption), `.moreline`, `.hint` (the fairness-simulation explainer copy, "never composed prose"
receipt text — this one carries real semantic weight per `edge-cases.md`, not just decoration). Same defect
class as E5.2's R5 and E5.3's R5–R8: the token is correctly named and correctly themed, it is simply one
step too light for this specific background pairing. All four raised to `text-secondary` (7.24:1).

**R22 · A fifth instance of the same defect hid behind higher CSS specificity.** `.sim.is-stale .cap`
(the "simulation is stale, re-run before publishing" state) re-broke `.cap` back to `text-tertiary` via a
more specific selector — R18's fix never reached it, because `.sim.is-stale .cap`'s specificity beats
`.sim .cap`'s. Split the rule: `.cap` (13px/400, needs 4.5:1) gets `text-secondary`; `.head` (20px/700,
already clears the 3:1 large-text threshold at `text-tertiary`) and `.caselist` (carries no text of its
own) are left as-is, rather than over-darkening text that already passes.

**R19 · `.tab2[aria-selected="true"]` had no dark-mode override at all.** `background: surface-hover;
color: blue-600` — under `data-theme="dark"`, `surface-hover` darkens but `blue-600` does not lighten to
compensate, measuring **2.83:1** (need 4.5). `--blue-400` is the token already used for this exact
light-on-dark-surface situation (`--border-focus`, two lines below in the same token block) — added
`:root[data-theme="dark"] .tab2[aria-selected="true"]{color:var(--blue-400);}`, matching the `.menu`/
`.modal` dark-border-override pattern already established in this same file.

**R20 / R6-correction · `.b-link`'s hit-area fix from the prior session only extended one dimension.**
The prior pass's own comment claimed "grown to 44×44... the same technique `.chipx` already uses" — that
claim was checked by measuring `.chipx::after` directly (`inset:-12px`, extending all four sides to a true
44×44) against `.b-link::after` (`left:0; right:0; top:50%; height:44px`) — the latter extends height only;
`left:0;right:0` matches the link's own text width exactly. "Resend"/"Revoke" measured **18.6×44** and
**18.5×44** post-prior-fix — WCAG 2.2 SC 2.5.8 requires both dimensions ≥24px, and the *comment* describing
a fix that wasn't actually applied is precisely the failure mode this project's "re-verify by measurement,
don't trust the comment" instruction exists to catch. Fixed to `left:-6px; right:-6px`, giving Resend/Revoke
an effective ~30.5×44 hit area; "Try again" (already 54px wide) unaffected.

**R24 (web-design-guidelines gate) · `.srch input{outline:none}` had no focus replacement anywhere.**
Flagged by a fresh `web-design-guidelines` pass (Vercel's Web Interface Guidelines, fetched live — "never
`outline-none` without replacement"). Unlike every other focusable control in this file, no artboard
demonstrates a focused search box, and — because this is real CSS rather than a manually-applied
per-artboard demo class — `:focus-within` genuinely activates on a live render, unlike `.is-kbfocus` which
only exists as a static class. Added `.srch:focus-within` using the same ring token (`--border-focus`)
every other focused control in the file already uses.

**Nineteen tap-target readings retracted as false positives, not real defects** — the largest single
category, and worth recording precisely because it's exactly the "measure the effective area, not the
element's own box" lesson planner's R16 already learned:
- **19 `<input type="search">` elements measured 18–19px tall** — each is nested inside `<label
  class="srch">`, a 40px-tall, `cursor:text` label (already fixed for exactly this in a prior pass, R7) —
  the whole 40px row forwards click focus to the input natively; measuring the bare `<input>` understates
  its real hit area.
- **5 `.b-link` elements (post-R20-fix) still measure 18.x px wide in a naive box-model read** — but their
  `::after` overlay is now 30.5–66px wide × 44px tall, verified by directly querying the pseudo-element's
  computed box (`getComputedStyle(el, '::after')`), not just the element's own `getBoundingClientRect()`.
- **3 `.chipx` "remove chip" buttons measured 20×20px** — `.chipx::after{inset:-12px}` was already correct
  before this pass; effective area is 44×44, confirmed the same way.
- **7 native `<input type="checkbox">` elements measured 18×18px** — each is wrapped in a `<label>` with no
  padding constraint, and the *label's* own bounding box (which natively forwards the click) measures
  44–59px tall × 46–190px wide, confirmed by measuring the ancestor `<label>` directly rather than the
  checkbox alone.
- **3 disabled-button text-contrast readings (`.b-des`/`.b-cau`/`.b-con`) at 2.08:1 light / 1.93:1 dark** —
  `color.md` states explicitly that "low contrast against `interactive-disabled-bg` is the correct
  appearance for a disabled control," and both `02-ops-exception-console/implementation-spec.md` and
  `03-planner-dock-board/implementation-spec.md` already independently confirmed this class is "explicitly
  exempt from WCAG 1.4.3's contrast minimum." Retracted on the same standing, not re-litigated.

**Two `table-layout: auto` instances checked and confirmed correct, not fixed** — two small, static,
2-row key/value tables (the "Tighten NEW_START_CUTOFF" Current/New comparison, Screen 7) have no column-
width-during-load concern the way planner's live-scanning queue table does (`components.md` §1's "never
`auto`" rule is specific to that surface's own reflow-during-read cost, restated nowhere in this surface's
own `components.md`); forcing `fixed` without a `colgroup` on a header-less 2-column table would be a
speculative regression, not a fix. Left as-is, recorded as checked rather than silently skipped.

### 5.4 Checklist audit — User Management and Audit Log (Web app), independently re-run

`screens.md`'s own "Checklist coverage" section claims full coverage on both. Independently re-audited via
the `checklist-design` skill (not cited from memory) against both checklists' full item lists —
confirms the self-assessment on every item, with one nuance the self-assessment couldn't have known:
**"Pending invitation status" reads 🟢 against the checklist** (the mockup genuinely shows an Invited row
with Resend/Revoke, which is what the checklist item asks for) **but is backend-unbuildable as drawn**
(G5) — the checklist audits presence in the design, not backend feasibility, so both things are true at
once and belong in different sections of this document, not blended into one verdict. No other item on
either checklist came back weaker than `screens.md` already claimed.

### 5.5 What's genuinely good here

Worth stating plainly, matching the practice in the other three specs: **Users, Remove-user, and Audit are
the strongest three screens of any surface audited in this phase.** `list_users`/`deactivate_user`/
`reactivate_user`/`get_audit_log`/`export_audit_log` all match their design files closely, with correct
idempotency, correct role-gating, correct real-Auth-identity handling on the one action in this whole
backend that needs it, and an audit trail that genuinely covers this console's own actions (not a weaker,
separate path). `simulate_policy_weights`'s module docstring is a model of this project's own "Source:
assumption, untested" honesty discipline — it states plainly what it approximates and why, rather than
presenting a proxy as more than it is. The four real Stage-2 weight values in the mockup (`4`, `-6`, `1`,
`-25`) are byte-exact matches to `constraints.json` — someone built that part of this surface against real
data, not an illustrative guess.

---

## 6 · Owner decisions (four forks)

> **Forks A and B were resolved by the owner and implemented 2026-08-29 (issues #70 and #69). The options
> below are left as written** — they are the reasoning the decision was made against. Outcomes:
>
> - **Fork A → option (1), as recommended, with one deviation and one correction to its premise.** The
>   design files were reconciled to the live five types. **Deviation:** the type-specific field sets for
>   the three uncovered types were *not* redesigned — that is design work this pass had no mandate to
>   invent, so it is called out explicitly instead and Screen 6 stays gated on it. **Premise correction:**
>   "this surface hasn't been built into `frontend/` yet" was true when written and is no longer — E5.6
>   shipped `features/admin/`, already built against the live registry, which independently reinforces (1)
>   rather than weakening it. `mockup.html` was out of this pass's scope (`.md` files only) and still
>   carries the stale names.
> - **Fork B → option (1) for `w_fairness`, option (2)-in-substance for `P_churn`.** `w_fairness` is
>   built, defaulted off, and genuinely evaluated. Its "schema default of 0" turned out to need no schema
>   change at all — it lives in `constraints.json` alongside the other coefficients, and
>   `shipments.carrier_id` already existed. `P_churn` stays gated on #49, but option (3) was **rejected**:
>   a permanently-Inactive field is a weaker guarantee than a server that refuses the key by name, which
>   is what was built instead.
>
> **Fork C** (multi-facility scope, G4/#72) had its backend work land in an earlier 2026-08-29 pass;
> the fork text below is left as written and the issue is still OPEN. **Fork D** (pending-invitation
> lifecycle, G5/#73) is untouched and genuinely open.

**Fork A — `facility_rules.rule_type` reconciliation (G2).** Three options, not silently picked:
1. Update `06-admin-console/`'s design files (`screens.md`, `components.md`, `edge-cases.md`,
   `mockup.html`) to the five real shipped types, redesigning the type-specific field sets around what
   `HEAVY_DOCK_REQUIRED_KG`/`REEFER_DOCK_REQUIRED`/`NO_SHOW_GRACE_MIN` actually need (no existing artboard
   models these three).
2. Add a migration extending the `CHECK` constraint to also accept the four originally-designed types,
   treating E3.4's substitution as the thing to walk back.
3. Do both partially — keep the three renamed correspondences, formally retire `DOCK_PIN` (there's no real
   analog), and design fresh for the two uncovered real types.
Recommendation: (1). E3.4 shipped against `facility_rules_rule_type_check`'s live values with a stated,
deliberate reason (`admin_governance_service.py`'s own docstring); reopening the constraint contradicts
that reasoning without a new one, and this surface hasn't been built into `frontend/` yet, so there's no
shipped UI cost to changing the design side.

**Fork B — `w_fairness`/`P_churn` sequencing (G1).** This can't be resolved by this UI-UX pass alone —
implementing the formula terms is a `backend/app/scheduling/` change, and `P_churn`'s real value depends on
the Sequencer (#49). Options: (1) implement `w_fairness` alone now (it needs no Sequencer — just a
per-carrier displacement term and a schema default of 0, per §D7's own description) and gate `P_churn`
behind #49 the same way ops/planner already gate their own Sequencer-dependent states; (2) gate the whole
Danger Zone behind a new issue, matching the `sequencerProposalEnabled`-style flag pattern E5.2 already
established; (3) leave both fields in the mockup as visually present but permanently Inactive with an
inline explanation, never wired to a real flag, since neither term may ship before this surface does.
Recommendation: (1) for `w_fairness` specifically — it's cheap, self-contained, and directly named by
§D7 as the accepted-but-deferred trade-off; (2) for `P_churn`, filed as a dependency on #49 rather than
duplicating a new issue for the same root cause a third time.

**Fork C — Multi-facility admin scope (G4).** Extend `invite_user`/`update_user`/`list_users` to read/
write `user_scopes` for facility-scoped roles (mirroring what `get_account_profile` already does on the
read side), or keep the single-facility model and correct `flows-and-states.md`/`screens.md`'s claims to
match. Recommendation: extend the tools — the schema and a working reader already exist (E2.3/E3.5), so
this is a narrower lift than G1/G2, and the single-facility limitation would otherwise surface as a real
operational gap the moment an ops coordinator genuinely needs two facilities, which `screens.md`'s own
example row treats as the normal case, not an edge case.

**Fork D — Pending-invitation lifecycle (G5).** Add `invited_at`/`accepted_at` (or a `status` enum) plus
`resend_invite`/`revoke_invite` tools, or drop the pending-row treatment from the Users tab design and show
every invited user as an ordinary Active row from the moment of invite (arguably accurate — Supabase Auth's
own invite flow, `admin_user_service._create_auth_user`, already treats acceptance as implicit). Neither
option was picked here since it changes what the Users tab promises to show, not just how it's built.
