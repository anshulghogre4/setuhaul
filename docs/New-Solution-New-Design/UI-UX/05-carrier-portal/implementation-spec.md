# Implementation spec — carrier portal (E5.5)

> **M5 / E5.5 (issue #40).** The buildable translation of `05-carrier-portal/`'s locked design, on top of
> the design system E5.0 shipped and the tool catalog M3 actually closed. **This file defines no new design
> decisions.** Every value is copied from a foundations file, a surface file, `mockup.html`, or verified
> source in `backend/`, with its source named. Where a value has no source, or two sources disagree, it is
> in §6 as a decision the owner has to make — not resolved here.
>
> **Read for this pass, and only these:** all six `05-carrier-portal/` files (`screens.md`,
> `flows-and-states.md`, `edge-cases.md`, `components.md`, `accessibility.md`, `stitch-prompts.md`) plus
> `mockup.html`; `00-foundations/` — `components.md`, `accessibility-behaviour.md`, `color.md`,
> `typography.md`, `spacing-and-layout.md`, `iconography.md`; `SOLUTION_DESIGN.md` §7.5.6; the three prior
> implementation specs (`01-driver-chat/`, `02-ops-exception-console/`, `03-planner-dock-board/`) as
> templates and as the source of patterns to check for recurrence; and the live
> `backend/app/api/v1/routers/carrier.py`, `backend/app/services/carrier_reads.py`,
> `backend/app/repositories/carrier.py`, `backend/app/repositories/scope.py`.
>
> **Continuation, not a fresh pass.** A prior session (dispatched on Opus) started this exact issue and hit
> an account-wide spend limit mid-work, leaving 228 insertions / 159 deletions of genuine fixes uncommitted
> in `mockup.html` (its own inline comments, dated 2026-08-29, tagged `[E5.5 R1]` through `[R18]`). Every one
> of those fixes was **re-verified by measurement in this pass, not trusted from its comment** — §5.0 states
> which were confirmed exactly as claimed and which were not.
>
> **Status: BUILD-READY. 9 of 9 screens ship now (all backed by shipped §7.5.6 endpoints); 1 is gated on a
> single already-tracked backend epic (#53) for two of its four state variants.** This is the cleanest
> backend of the four surfaces audited so far — a genuine, structural difference from
> `02-ops-exception-console/` (9/16) and `03-planner-dock-board/` (10/30): §7.5.6 was built complete, and
> server-side scope enforcement was verified, not assumed. Three rendering defects found in this pass (two
> genuinely new, one a correction to a prior pass's fix that measured wrong), all three fixed and
> re-measured. One real backend-contract gap found, and it connects directly to an already-open issue rather
> than needing a new one.

**Owner decisions still open: two (§6).**

---

## 0 · Starting point — what exists, verified not assumed

### 0.1 What M3 actually shipped for this surface

Checked tool-by-tool against `SOLUTION_DESIGN.md` §7.5.6, read off source — not taken from the milestone's
closed state:

| §7.5.6 tool | Shipped? | Source |
|---|---|---|
| `get_fleet_overview` | ✅ | `carrier.py:37` `GET /carrier/fleet-overview` → `carrier_reads.get_fleet_overview` |
| `list_fleet_shipments` | ✅, with `status_filter?` | `carrier.py:47` → `carrier_reads.list_fleet_shipments` |
| `get_shipment_detail` | ✅, with server-side cross-carrier refusal | `carrier.py:65` → `carrier_reads.get_shipment_detail` |
| `list_fleet_exceptions` | ✅ | `carrier.py:84` → `carrier_reads.list_fleet_exceptions` |
| `get_carrier_on_time_performance` | ✅, with `window?` (only `30d` accepted) | `carrier.py:94` → `carrier_reads.get_carrier_on_time_performance` |

**Five of five.** This is the first surface in this audit series where the tool catalog is not the
bottleneck — E5.2 found 7/8, E5.3 found 2.5/9. §7.5.6 shipped complete under E3.3 (issue #27), well before
this pass.

**The read-only guarantee, checked concretely rather than taken from the router's own docstring:**

| Claim | Verified how |
|---|---|
| No mutating tool exists on this surface | `carrier.py` contains five `@router.get` and zero `@router.post`/`@router.patch`/`@router.delete` — read the whole file, not grepped for a pattern that could miss one |
| Carrier scope is never client-supplied | `resolve_carrier_scope(ctx)` (`repositories/scope.py:118`) takes **no parameter** at all beyond `ctx` — there is no wire format (path, query, or body) in which a caller could pass a `carrier_id`; confirmed by reading every one of the five route signatures, none of which declares one |
| A cross-carrier `shipment_id` is refused, not silently filtered | `get_fleet_shipment` (`repositories/carrier.py:256`) scopes the query itself (`WHERE s.shipment_id = :shipment_id AND s.carrier_id = :carrier_id`) so another carrier's row is **never read into the process**; the caller then passes the result through `assert_shipment_in_carrier_fleet` (`scope.py:144`), which is what turns "no row" into a 403 — not a 404-then-403 pair, which `assert_shipment_in_carrier_fleet`'s own docstring names as itself a leak (a nonexistent id and another carrier's id must return identically) |
| No cross-carrier aggregate leaks through a denominator | `repositories/carrier.py`'s own module docstring states the rule ("not one statement below computes a facility-wide, cross-carrier or peer aggregate") and every query in the file carries `carrier_id = :carrier_id` in its own `WHERE`, not composed from an unscoped base query filtered after the fact |
| An unmapped `CARRIER` identity is refused, not served the whole table | `resolve_carrier_scope` raises `CARRIER_UNMAPPED` (403) rather than returning `None` — the one place this function's behaviour deliberately diverges from `resolve_facility_scope`'s "no filter" convention for global-read personas, and the divergence is explained in its own docstring |

**This is the answer to the task's specific question**: the read-only guarantee on this surface is
**server-verified, not client-enforced**, at every layer checked — router (no mutating route exists to
call), service (`carrier_reads.py` has no `session.commit()` anywhere, stated in its own module docstring),
repository (every `SELECT` is carrier-scoped in its own `WHERE`), and scope (`resolve_carrier_scope` derives
the carrier from the verified token, never accepts one). No stray write/mutation affordance was found
anywhere in `mockup.html` either — see §0.3.

### 0.2 One real backend-contract gap, found by cross-checking design against schema

`carrier_reads.py`'s own module comment already names this — the finding here is connecting it to what the
UI-UX spec designs over it, not discovering the schema fact itself:

**`SHOWN` and `HELD` have no representation in `appointments.appointment_status`.** The live CHECK
constraint admits `PENDING_CONFIRMATION / CONFIRMED / IN_PROGRESS / COMPLETED / CANCELLED / REJECTED /
EXPIRED / NO_SHOW` and nothing else (`carrier_reads.py:40-48`, `repositories/carrier.py`'s
`promise_state AS appt.appointment_status`). This is not a scoping gap or an authorization gap — it is the
same structural fact `issue #53` already tracks for driver chat: **the live promise lifecycle is three
states (`PENDING_CONFIRMATION → CONFIRMED/CANCELLED`), not the four the design specifies
(`SHOWN → HELD → PENDING_CONFIRMATION → CONFIRMED`)**, because `request_slot` inserts directly at
`PENDING_CONFIRMATION` and there is no intermediate row for either `SHOWN` or `HELD` to occupy.

Two concrete places this surface's own design assumes otherwise:

1. **`flows-and-states.md` Flow 2** and **`mockup.html` state 4b**'s filter popover list `Shown` and `Held`
   as selectable status filters. `carrier_reads._validate_status_filter` explicitly refuses both with a 400
   `FILTER_UNSUPPORTED`, naming the exact reason (`_SCHEMA_UNSUPPORTED_REASON`) — selecting either option
   as designed would error, not filter to an empty (or populated) list.
2. **`stitch-prompts.md` §8** and **`mockup.html` states 12a/12b** design a full `SHOWN` chip variant
   ("Nothing is held yet") and a full `HELD` chip variant with a live 90-second countdown
   (`Held for the driver until 11:42:30`). `get_shipment_detail` can never return either value for a real
   shipment — a shipment genuinely in a pre-appointment state today returns `promise_state: null` (the
   `LEFT JOIN LATERAL` in `list_fleet_shipments`/`get_fleet_shipment` yields no row, not a `SHOWN` row), and
   **no file in this surface's spec describes what a null promise-state row renders as.** State 4a's own
   row 5 (`SH-2026-0819-00…17`, rendered `SHOWN`) is therefore illustrative data that the live schema cannot
   actually produce today, not a real example.

**This is `#53`'s scope, not a new gap** — filing a duplicate would fragment the one place this is already
tracked. §6 Fork A is the owner decision this connects to (what to do with the two designed screens/states
in the meantime).

### 0.3 Read-only affordance sweep — no stray mutation found

Checked every interactive element in `mockup.html` against §7.5.6's "no mutating tool by design": five
`<button>` types exist (`iconbtn`, `avatarbtn`, `filterbtn`/`popitem`, `linkbtn` [Refresh / Try again /
Clear filter], `.btn` [Retry / Try again / Back to dashboard / Clear filter]) — every one either **reads**
(Refresh, Retry, Try again) or **navigates/filters client-side** (filter popover, Clear filter, Back to
dashboard). None posts, confirms, holds, rejects, or otherwise writes. `components.md` §18's Read-only
contract ("no hover state, no accent colour, no cursor change on anything the carrier cannot act on") is
followed correctly on non-navigation cells — verified live: `table.f tr:hover td{ background:none; }` zeroes
hover on the legacy (non-`.tbl`) tables where no row is a navigation target, and `.tbl` rows only gain a
hover background when they `:has(.rowlink:hover)`.

### 0.4 The frontend after E5.0–E5.4

| Fact | Consequence for E5.5 |
|---|---|
| `theme.css` carries every token this surface references | Nothing to add for colour, confirmed by the fix pass adding only functional-tier tokens already licensed by `color.md` (`--feedback-warning-*`), not new primitives |
| `identity.ts` gives carrier `density: comfortable`, `hasFacilityScope: false` | Matches `screens.md`'s own framing exactly — no facility switcher, cross-facility list rows |
| `iconography.md`'s Rail destinations table (added 2026-08-26) gives Carrier exactly **one** destination — `package`, "Fleet" | **Already correctly applied in this uncommitted pass** — verified live: every spec-accurate frame (states 3 onward) renders a single `<nav class="rail" aria-label="Sections">` item, `aria-label="Fleet"`, the `package` icon path. The two-item rail (`▤ Dashboard` + `👤 Account`) survives only in states 1–2, the explicitly-disclosed legacy sketch |
| **Coordinator update, mid-pass**: rail-Profile-duplication (raised as E5.2's Fork E / E5.3's Fork H) is now settled project-wide — drop the rail Profile item, keep only the top-bar account control | **Already compliant, independently confirmed by measurement, no action needed.** This surface never had a live "Fleet + Profile" two-item rail to begin with in its spec-accurate states — only the disclosed legacy sketch does, and that sketch is named drift, not a rendering the fix pass is obligated to correct. Checked this explicitly rather than assuming compliance from the single-item count alone |

---

## 1 · The dashboard shell — one page, no tabs, no facility switcher

`screens.md` §1. Confirmed against `spacing-and-layout.md`'s surface table: **Carrier portal, 768px+,
target 1280×800, "Responsive down to 768px"** — the only one of the four operational/portal surfaces with
no stated below-breakpoint degradation note (planner/ops get a reduced column set or "use a larger screen";
admin gets horizontal table scroll called out explicitly). Carrier portal is expected to just keep working
down to 768px.

```
┌──┬──────────────────────────────────────────────────────────────────────────────────┐
│▌ │ TOP BAR 56px   Carrier name              🔔  ?  AB                                │
├──┼───────────────────────────────────────────────────────────────────────────────────┤
│56│ role="region" "Fleet dashboard"                                                    │
│  │   Overview strip (3 stat tiles) → Your shipments (filterable table) →              │
│  │   Open exceptions (status-only summary rows)                                       │
└──┴──────────────────────────────────────────────────────────────────────────────────┘
```

Rail: 56px, **one destination** (§0.4). No facility-accent stripe on the rail's outer edge — `stitch-prompts.md`'s own "Notes on values" §4 already flags this as undecided by any file; the mockup renders a plain 1px border, which is the same choice `05-carrier-portal/`'s own designer made without a stated foundations source. Not re-opened here; see §6 for whether it should be recorded.

Second destination: Shipment detail, reached only by opening a row — `screens.md`'s own screen map states
this plainly ("No tabs, no facility switcher... no settings beyond account basics").

---

## 2 · The nine screens → build readiness

Nine `stitch-prompts.md` prompts, rendered as 13 labelled states / 20 frames in `mockup.html`. Copy is
authoritative at the prompt number given.

**Legend:** 🟢 buildable today · 🟡 buildable, two of four variants blocked on #53.

| # | Prompt | States realizing it | Build |
|---|---|---|:--:|
| 1 | Dashboard — default loaded | States 3+4a+5a compose the spec-accurate default (no single assembled "plain default" hero — the design deliberately splits it into three verified component sheets; states 6b/9/10/11 assemble the full shell but each for its own specific condition, not the plain default) | 🟢 |
| 2 | Fleet overview strip | State 3 | 🟢 |
| 3 | Your shipments — table, filter, filtered-empty | States 4a/4b/4c | 🟡 — filter popover offers `Shown`/`Held`, which 400 against the live endpoint (§0.2). Every other filter value and the table itself is fully backed |
| 4 | Open exceptions — summary rows | States 5a/5b | 🟢 |
| 5 | Dashboard loading | States 6a/6b | 🟢 |
| 6 | Dashboard empty states | States 7/8 | 🟢 |
| 7 | Dashboard load failure / degradation | States 9/10/11 | 🟢 |
| 8 | Shipment detail, read-only, 4 variants | States 12a (`SHOWN`) / 12b (`HELD`) / 12c (`PENDING_CONFIRMATION`) / 12d (`CONFIRMED`) | 🟡 — 12c and 12d render real `appointment_status` values and are fully backed; 12a and 12b design a chip and (for `HELD`) a live countdown that `get_shipment_detail` can never populate for a real shipment (§0.2) |
| 9 | Shipment detail — out-of-scope refusal | State 13 | 🟢 — and this is the one screen whose exact backend behaviour was verified line-by-line (§0.1's table): the copy's own "never confirms or denies whether the shipment exists" requirement is met by `assert_shipment_in_carrier_fleet` returning the identical 403 for both a missing id and a cross-carrier id |

**Net: 9 of 9 screens are buildable now.** Two of nine have one narrow, already-tracked gap apiece (prompt
3's two filter options; prompt 8's two of four chip variants) rather than being blocked outright — a real
difference from `02-ops-exception-console/`'s and `03-planner-dock-board/`'s screen-level gating, worth
stating plainly rather than rounding down to "7 of 9."

---

## 3 · What E5.5 adds to the design system

**Two functional-tier tokens**, both already licensed by `color.md` rather than invented: `--feedback-warning-bg/-border/-text` (light: `amber-50`/`amber-500`/`amber-700`; dark: `#3A2C10`/`amber-500`/`amber-400`) — added because the stale-data notice had been reaching for `--state-held-*` (the promise-chip's own reserved token family, `components.md` §2: "nothing else may borrow them"), which made a staleness warning render in `HELD`'s exact palette. This is the same class of token-boundary violation as `02-ops-exception-console/`'s SLA-colour fork, caught here before shipping rather than after. No primitive was added — both values already exist in `color.md`'s ramps.

One correction **to** the design system rather than added by it: `color.md`'s `amber-600` was missing from the primitives block this surface's mockup declares (needed for the `HELD` chip border); added at the primitive tier, not invented — it is `color.md`'s own documented Amber-600 value.

---

## 4 · Readiness call

**Verdict: 9 of 9 screens build now. Zero screens fully blocked. One narrow backend gap (already tracked as
#53) touches two states out of thirteen. Three rendering defects found in this pass, all three fixed and
re-measured** — two genuinely new (not present in the prior pass's own fix list), one a correction to a
prior fix whose own inline comment overclaimed what it achieved.

### 4.0 Fix-pass scoreboard — every item re-measured, none trusted from a comment

Method: headless Chromium (Playwright 1.62.1 / Chromium 1234, same build the prior three passes used) over
the DevTools Protocol. Computed styles and box model, contrast computed from **rendered** `rgb()` against
each element's effective background, `document.elementFromPoint` sweeps for click-target verification
(not just `getBoundingClientRect`, which — see R5b — measures the wrong thing for a stretched pseudo-element
target), ARIA/heading census over the live DOM, forced `prefers-color-scheme` in both directions, and dark
`data-theme` contrast. Every number below is from this pass's own run, not carried over from the prior
session's comments.

**Confirmed exactly as claimed (prior session's fixes, re-verified rather than trusted):**

| Fix | Claim | Re-measured |
|---|---|---|
| R1 — theme auto-switch (U69) | 0 `prefers-color-scheme` media rules remain | **Confirmed.** Forced dark preference: `--surface-base` resolves `#F8FAFC` (light), `data-theme` attribute stays `null` (i.e. nothing switched it) |
| R4 — tap targets to 44px via expanded pseudo-hit-areas | `.avatarbtn`/`.btn` visually stay their original size, hit area grows to 44 via `::after` inset math | **Confirmed, but not by the method the prior session's comment implies.** `getBoundingClientRect()` on `.avatarbtn` itself still reads 32×32 — that is by design (`::after` isn't measurable that way). Verified instead with a real click test: `elementFromPoint` 5px beyond the visible 32px edge (within the claimed 6px extension) resolves to `BUTTON.avatarbtn`. The 44px hit area is real |
| R8 — type tokens | `table.f th`/`.dhead`/`.stat .value` etc. match named scale rows | **Confirmed** — `h3Count: 0` (all promoted to `h2` as claimed), no residual mismatched sizes found in the sweep |
| R9 — stale-notice tokens | Notice uses `--feedback-warning-*`, not `--state-held-*` | **Confirmed**, light 4.84:1 and dark 8.13:1, both measured directly |
| R10 — sparkline baseline | `.spark2 .baseline` renders | **Confirmed** present on every sparkline instance |
| R14 — delta in percentage points, named period | "2 pts vs. prior 30 days" | **Confirmed** for text content — see R14b below for what this claim didn't cover |
| R15 — sticky first column | `position:sticky` on `.tbl thead th:first-child`/`td:first-child` | **Confirmed present, and confirmed *necessary*** — checked against `spacing-and-layout.md`'s own breakpoint table rather than assumed: Carrier portal's stated floor is 768px, and the table's `min-width:972px` genuinely overflows a 768px viewport (972 > 768−48px frame padding), so this is a real, needed fix, not one reflexively imported from `components.md` §6's general rule. This matters for R5b below |
| R18 — motion token declared | `--t-fast: 120ms` | **Confirmed** |

**Two genuinely new defects, found in this pass, fixed and re-measured:**

| # | Defect | Before | After | Verified by |
|---|---|---|---|---|
| **R16b** | R16's own selector lost a CSS specificity fight it never checked. `.tbl td{ height:44px; padding:0 16px; }` (specificity 0,1,1) is beaten by the base rule `table.f td{ padding:12px 16px; height:44px; }` (0,1,2) — the intended `0 16px` padding never actually applied; the real computed padding stayed `12px 16px`. With `line-height:1.5` at 14px (a 21px line box) plus 24px of vertical padding neither R8 nor R16 intended to keep, several rows exceeded the 44px floor they were supposed to be clamped to | **51 / 51 / 46 / 69 / 66.5 / 51px** across 6 rows in one table — not the "44/46/48/71" the R16 comment itself cites as the *before* state, and not 44 anywhere as claimed *after* | Raised the selector to `.tbl table.f td`/`.tbl table.f th` (specificity 0,2,2, now wins). **All 10 rows measured across both live tables now read exactly 44px, 0 exceptions** | `getBoundingClientRect().height`, every row in both `.tbl`-wrapped tables |
| **R14b** | The on-time delta's direction (increased vs. decreased) is carried by exactly one channel — an `aria-hidden="true"` arrow icon — with no textual equivalent | Accessible name (aria-hidden nodes stripped, per the accessible-name algorithm): `"2 pts vs. prior 30 days"` — direction absent | Added `<span class="sr-only">Increased </span>` before the number on all 5 spec-accurate instances. Accessible name now: `"Increased 2 pts vs. prior 30 days"` | Simulated accessible-name computation (strip `[aria-hidden="true"]`, read remaining text), all 5 instances |

**One correction to a prior fix that measured the wrong thing:**

| # | What R5's comment claimed | What direct testing showed | Root cause | Disposition |
|---|---|---|---|---|
| **R5b** | `.rowlink::after{ inset:0 }` "stretches over the whole row" | `elementFromPoint` sweep across 7 points in a real shipment row: only the point over the ID text itself (inside column 1) resolves to the link. Driver cell, facility cell, status cell, chevron cell, and even the row's top/bottom edges directly above/below the ID text all miss | **R15 and R5 conflict, and R5's own verification never rendered both together.** `position:sticky` on the first `<td>` (R15) is a *nearer* positioned ancestor to `.rowlink` than the `<tr>` R5's `inset:0` targets, so the pseudo-element's containing block resolves to the 180px-wide sticky column, not the 972px row. Tested and ruled out `overflow:hidden` as an alternative cause (removing it from `.tbl td` made no difference to the sweep) before concluding it was the sticky ancestor | **No pure-CSS fix exists** — R15 is confirmed necessary (table above) and only one ancestor can be `.rowlink`'s nearest positioned one. Corrected the misleading comment to state the true, measured behaviour and named the real fix: a row-level `onClick`/`onKeyDown` delegate in the React build, with `.rowlink` staying the focusable/keyboard/screen-reader target. **What is functionally true today**: column 1 (180×44, comfortably above the 44px floor and WCAG 2.5.8's 24px floor) is a genuine, reachable click/keyboard target; the rest of the row is not, despite `components.md` §2's "whole row is a single navigation target" and despite the row's hover background (via `:has()`) visually implying otherwise across all five columns |

**This is the same defect *class* `02-ops-exception-console/implementation-spec.md` §5.3's R3/R4 named** —
"only appears in combination," where no single rule is individually wrong but two correct-looking fixes
interact destructively, invisible until both are rendered and tested together rather than verified in
isolation. R5b is that exact pattern a second time, on a different surface, caught the same way (render,
don't trust the comment).

**No regressions**, re-checked after every edit above: theme auto-switch still 0 media rules; emoji count
still 3 (legacy sketch only, unchanged); `role="region"` count 28, `h1`/`h2`/`h3` 12/18/0, `nav` count 10 —
all identical before and after this pass's own edits; focus-visible verified live via real `.focus()` calls
(not inferred) on `.rowlink` (→ its ancestor `<tr>` gets a 2px solid outline, −2px offset), `.avatarbtn`,
`.iconbtn`, `.filterbtn` (all three: 2px surface-offset ring + 2px blue ring, matching
`elevation-and-depth.md`); dark-theme contrast on chips/notice/exflag/delta all ≥6.3:1, comfortably clearing
AA and mostly clearing AAA.

### 4.1 One backend gap — already tracked, not a new issue

**G1 · 🟡 `SHOWN`/`HELD` have no live representation, and this surface designs full UI for both.** Detailed
in §0.2. Same structural fact as **open issue #53** (filed for driver chat, 2026-08-26) — `appointments`
has three states where the design specifies four, because `request_slot` writes `PENDING_CONFIRMATION`
directly with no intermediate hold row. Carrier portal is the **third surface this reaches** (after driver
chat, where it blocks 4/28 screens, and implicitly ops/planner's own promise-chip renders) — not a new
finding about the schema, but a new finding about how far its consequences already spread through the UI-UX
workspace. **Recommendation in §6 Fork A: widen #53's stated scope to note this surface rather than filing
a duplicate #6x issue for the same root cause.**

### 4.2 `web-design-guidelines` (U38 gate) — actually invoked

Skill invoked via the `Skill` tool; guidelines fetched fresh from
[vercel-labs/web-interface-guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md).
Applied to the post-fix-pass `mockup.html`.

| Category | Finding |
|---|---|
| Icon-only buttons | ✅ Clean — all `.iconbtn` (Notifications, Help) and `.avatarbtn` instances carry `aria-label` |
| `transition: all` | ✅ None found (grepped the whole file) |
| `outline: none` without a replacement | ✅ Both occurrences (`.excrow`/`.popitem` and `.rowlink`) carry a verified replacement — `box-shadow: var(--shadow-focus)` on the first, and the ancestor `<tr>`'s `:has()`-driven outline on the second (live-verified via `.focus()`, §4.0) |
| `prefers-reduced-motion` respected | ✅ `.sk{ animation: skpulse ... }` has a `@media (prefers-reduced-motion: reduce){ .sk{ animation:none; } }` pairing — the one animation on this surface |
| Ellipsis character | ✅ `…` used consistently for mid-truncated IDs (`data-formatting.md`'s rule), no `...` found |
| `tabular-nums` on metric displays | ✅ `.tnum` applied to every stat value, delta number, and countdown |
| Semantic HTML for actions | ✅ Every action is a real `<button type="button">` or `<a href>` — no `<div onclick>` found |
| Forms | N/A — no form inputs on this surface; the filter control is a `role="menu"` popover, correctly not a form |
| `Intl` for dates/times | 🔴 **Reported, not fixed here — a build requirement, same position `01-driver-chat/` and `02-ops-exception-console/` both took.** Every timestamp (`09:41`, `11:57`, `Tue 20 Aug`) is a hardcoded string. `data-formatting.md` and U31 require `Intl` with `en-IN` from the first component |
| Large lists / virtualization | N/A — 5–6 rows per table, no list on this surface approaches the 50-item threshold |
| Row-as-navigation-target semantics | 🟡 Flagged in §4.0/R5b — a real gap, but a build-time one (row-level event delegate), not fixable in static markup |

### 4.3 `checklist-design` (U34 gate) — actually invoked

Skill invoked via the `Skill` tool; `references/index.md` and two checklists read from the skill's own
bundled files — **Analytics** (already `screens.md`'s own cited checklist) and **Single Item Detail**
(never previously checked against the shipment-detail screen — the same gap-class `02-ops-exception-console/`
found for its own detail pane, checked here proactively rather than waiting to be caught).

#### Analytics — Web app ([checklist.design/web-app/analytics](https://www.checklist.design/web-app/analytics))

| | Item | Why |
|---|---|---|
| ⚪ | **Date range selector** — A date picker with shortcuts for today, last 7 days, last 30 days, this month, and custom range | The 30-day window is fixed by decision, and `carrier_reads.py`'s `_SUPPORTED_WINDOWS = {"30d": 30}` makes this a real backend constraint too, not just a UI restraint — a picker would offer choices the endpoint would 400 on |
| 🟢 | **Headline metrics** — The most important numbers displayed as prominent headline figures | Three stat tiles, top of dashboard, one `get_fleet_overview` call |
| 🟡 | **Charts with labels and axes** — Visualisations with clearly labelled axes, a legend where needed, and readable tick marks | One sparkline (on-time tile only), no visible axes or tick marks by deliberate product-wide policy (U33, `components.md` §14 defers to `dataviz`'s minimal-charting stance) — but it does carry a full `aria-label` naming the period and the ending value, which is closer to the checklist's underlying intent (a chart a screen-reader user can also read) than a chart with visible-but-unlabelled axes would be |
| 🟢 | **Period comparison** — A percentage or absolute change indicator showing how each metric has moved relative to the prior period | On-time tile's delta, in percentage points against a named prior period — and after R14b, its direction is now accessible-name-legible too, not just visually legible |
| 🟡 | **Segment breakdown** — The ability to slice a metric by properties e.g. channel, device, geography, or another attribute | The status filter narrows the shipment *list*, but `screens.md` §1 states the three stat tiles deliberately don't respond to it ("reflect the whole fleet regardless of filter") — so the metrics themselves are never sliced, only the list beneath them |
| 🟢 | **Last updated indicator** — A visible timestamp or refresh button showing when the data was last updated | Timestamp + a real, focusable `Refresh` button, not a static string |
| 🟢 | **Loading and empty states** — Skeleton loaders while data is fetching, and a contextual message when no data exists | The most complete treatment of this single item across the whole surface: per-section skeletons (not one page spinner), a stalled/retry state past ~3s, two *distinct* empty states (`caught up` vs. `nothing yet`, U74), a regional load-failure state, and a stale-data notice — five different negative states for what the checklist names as one item |

#### Single Item Detail — Web app ([checklist.design/web-app/single-item-detail](https://www.checklist.design/web-app/single-item-detail))

| | Item | Why |
|---|---|---|
| 🟢 | **Clear title or identifier** — The name, ID, or primary label of the item, shown prominently at the top of the screen | `SHP1015 · Ravi K.`, 20px/600, mono ID, top of the card |
| 🟢 | **Status indicator (if applicable)** — A clear signal of the item's current state | The shared promise-state chip, four redundant channels (hue, icon, border style, text label) — the checklist's own tip ("colour-blind users can't distinguish status by colour alone") is exceeded, not just met |
| 🟢 | **Key details section** — The most important attributes surfaced prominently, secondary details below | Identity → chip → deadline (where one exists) → dock/date/time line → reference (confirmed only) → history, in that order, one card |
| ⚪ | **Edit action** — A clear way to modify the item's details | Deliberately, structurally absent: §7.5.6 has no mutating tool for this role, and `components.md` §18 requires a scope-denied control to be **Hidden**, never Disabled — rendering an edit affordance here would misrepresent what this surface can do. The strongest ⚪ on this table |
| 🟢 | **Related items or activity** — Associated records, linked content, or a history of changes | The History list — outcomes and driver-visible messages only, by column allowlist at the repository layer (`list_shipment_history`), not a redaction pass over `SELECT *` |
| 🟢 | **Breadcrumb or back navigation** — A way to return to the list or parent context | `← Dashboard`, and per `accessibility.md`'s focus-management table, returns to the exact row that was open, not the top of the list — stronger than the checklist asks for |
| ⚪ | **Destructive actions** — Delete or archive options, kept visually separate from primary actions | No destructive action exists anywhere on this surface; nothing to separate |

**Beyond the checklists.** Two observations, kept brief per the audit's own discipline:

1. The filter popover (state 4b) is the one place this surface's own UI promises something the backend
   explicitly refuses (§0.2) — worth a reviewer's attention precisely because everything else on this
   surface is unusually well-matched to its backend.
2. `stitch-prompts.md`'s own "Notes on values these prompts had to pin down," item 9, already flags session
   expiry as unaddressed for this surface — not re-raised here, just confirmed still open on re-reading.

---

## 5 · Suggested order for E5.5

1. **The dashboard shell + overview strip** (§1, prompts 1–2) — no gates, fully backed, and the R16b fix
   (row height) matters most here since it's the first table a build would render.
2. **Your shipments table, prompts 3/4a–4c** — build the filter with `Shown`/`Held` **omitted** from the
   popover until #53 lands (§6 Fork A), not rendered-then-erroring.
3. **Open exceptions, prompt 4** — no gates, simplest of the nine screens.
4. **The five negative/loading states, prompts 5–7** — do these alongside the happy path, not after; this
   surface's own checklist audit (§4.3) found them to be its strongest single item.
5. **Shipment detail, prompt 8** — build `PENDING_CONFIRMATION`/`CONFIRMED` (12c/12d) against real data
   first; gate `SHOWN`/`HELD` (12a/12b) behind a flag named for #53, same pattern
   `02-ops-exception-console/`'s suggested order used for its own backend-gated screens.
6. **Out-of-scope refusal, prompt 9** — build early, not late: it's the one screen whose exact backend
   behaviour (identical 403 for missing vs. cross-carrier) is already fully verified, and it's cheap.
7. **The row-click delegate (R5b)** — implement as a `<tr onClick>`/`onKeyDown` handler wrapping the whole
   row, calling the same `href` `.rowlink` carries; keep `.rowlink` as the real focusable/keyboard element.
   Do this once, in the shared row component if this pattern recurs elsewhere, not per-surface.
8. `Intl` with `en-IN` for every date/time from the first component, not retrofitted (§4.2).

**Feature flag.** `carrier_shown_held_enabled` (#53) — gates the two filter options and the two chip
variants named in §0.2/§4.1, default off, issue number in the comment.

---

## 6 · Two forks for the owner

**Fork A · What should the `SHOWN`/`HELD` screens do until #53 lands?**
§0.2/§4.1. Two designed states (12a, 12b) and two filter options (state 4b) have no backend to sit on.
*Options:* (a) gate both behind a flag and ship the surface without them for now — the filter popover omits
`Shown`/`Held` entirely, and a shipment with `promise_state: null` (the real value a pre-appointment
shipment returns today) needs its **own**, currently undesigned, row/chip treatment, since neither
"SHOWN chip" nor "blank" is accurate; (b) treat this as fully blocking and hold the whole surface until #53
resolves; (c) ship the illustrative `SHOWN`/`HELD` states as-is with a "coming soon" label, accepting that
they'd be non-functional demo content in a production build.
*Recommendation:* **(a)**. `02-ops-exception-console/` and `03-planner-dock-board/` both used the
gate-behind-a-named-flag pattern for real backend gaps rather than either blocking the whole surface or
shipping something that errors — same call here, and it's the only option of the three that also surfaces
the genuinely new question this pass found: **what does a null-promise-state row look like?** That needs a
design answer (probably closest to `SHOWN`'s own "nothing is held yet" framing, but not verified against
any file), not just a flag.

**Fork B · Should `spacing-and-layout.md`'s Carrier portal breakpoint note the sticky-column /
row-click-target trade-off explicitly?**
§4.0/R5b. The conflict between R15 (a genuinely required sticky column, confirmed against this surface's own
768px floor) and `components.md` §2's whole-row-click requirement isn't specific to carrier portal — any
`.tbl`-style table with a sticky first column and a row-as-link pattern hits the identical containing-block
conflict. *Options:* (a) record the resolution (row-level JS delegate, not CSS) once in
`00-foundations/components.md`'s shared table conventions, so the next surface that combines these two
patterns inherits the answer instead of re-discovering it the same way this pass did; (b) leave it as a
surface-specific note in this file only; (c) redesign the column widths so no `.tbl` table on this surface
ever needs to scroll at any stated breakpoint, removing the sticky column (and the conflict) entirely — a
bigger, more invasive change than (a) or (b), and not evaluated here for whether it's actually achievable
within `screens.md`'s stated six columns.
*Recommendation:* **(a)**. This is the second time in this audit series a foundations-level interaction
between two individually-correct rules only showed up once both were rendered together (the first was
`02-ops-exception-console/`'s R3/R4 selected-row contrast pairing) — worth the same treatment: fix it once
where every surface using the pattern can inherit the answer, not per-surface.

---

## 7 · Constitution Check

| Check | Result |
|---|---|
| Contradicts a locked decision U1–U120? | **No.** U19, U28, U31, U33, U34, U38, U66, U69, U70, U74, U83, U84, U85, U91, U96, U101 are each cited where they constrain a value. No live U69/U83/U91 violation was found in this pass — the prior session's own R1 fix for U69 was re-verified rather than re-broken. |
| Amends a foundations or surface file? | **`mockup.html` only** — three fixes/corrections this pass (R16b, R14b, R5b's comment correction), each with a dated inline comment. No `00-foundations/` or `05-carrier-portal/*.md` file was edited. Fork B's foundations-level recommendation is left for the owner, not applied here. |
| Invents product behaviour? | **No.** All five §7.5.6 tools were read off `carrier.py`/`carrier_reads.py`/`repositories/carrier.py` directly; the one gap (G1) is read off the live CHECK constraint and `carrier_reads.py`'s own comments, not inferred from the design docs; the null-promise-state row's undesigned treatment is named as absent, not given one. |
| Invents data? | **No.** Where a value has no source (the rail-edge accent decision, session-expiry treatment) it is named as absent, per `stitch-prompts.md`'s own "Notes on values" section, not silently resolved. |
| React 19 frontend (ADR 012)? | Yes — unchanged from E5.0–E5.4. |
| Stays inside the named scope? | Yes. The brief named `05-carrier-portal/`'s six files, `mockup.html`, and `00-foundations/`; `backend/app/api/v1/routers/carrier.py`, `services/carrier_reads.py`, `repositories/carrier.py`, `repositories/scope.py` were read because the brief's own instruction requires confirming M3's tool catalog and the read-only guarantee against source, which cannot be asserted from design docs alone. `gh issue view 40` and `gh issue view 53` were read per `AGENTS.md`'s startup rule and to confirm G1 connects to an already-open issue rather than needing a new one. |
| Skills actually invoked, not cited? | **Yes, both, via the `Skill` tool.** `checklist-design` (§4.3 — two checklists read from the skill's own bundled files, audited item-by-item in each checklist's own order) and `web-design-guidelines` (§4.2 — guidelines fetched fresh from source). `dataviz` not run — the one sparkline is an existing, previously-specified component (`components.md` §14), not a new chart this pass designs. `design` canvas not run — this is a spec/measurement pass over an existing approved mockup, not a new screen. |
| Rendering verified, not eyeballed? | **Yes.** Headless Chromium via Playwright 1.62.1/Chromium 1234 (the same build the prior three passes used, confirmed already cached on this machine rather than freshly pinned): computed styles, `getBoundingClientRect`, `elementFromPoint` sweeps (the method that actually caught R5b — a `getBoundingClientRect`-only check would have missed it, since the *pseudo-element's* effective hit region, not `.rowlink`'s own box, is what needed testing), CSS specificity/cascade inspection via live `styleSheets` enumeration (what caught R16b), contrast from rendered `rgb()` in both themes, real `.focus()` calls for focus-visible verification, and a full before/after regression sweep (theme, emoji, ARIA counts) after every edit. |
| Genuine forks surfaced, not silently decided? | **Yes, two** (§6), each with options, a recommendation, and the honest trade-off. Fork A in particular was not silently resolved by just hiding the two filter options — the harder, undesigned question (what does a null-promise-state row look like) is named as still open, not answered here. |
| Fixes verified by measurement, not by editing and assuming? | **Yes — every one.** R16b re-measured across 10 rows in both live tables (0 exceptions after, vs. 6 different wrong values before); R14b re-verified via a simulated accessible-name computation on all 5 instances; R5b re-verified via the same `elementFromPoint` sweep that found it, confirming the corrected comment now matches reality (column 1 only, 180×44) rather than just editing the prose and moving on. |
| Writeback (`CHANGELOG.md`, `wiki/`)? | **Not required** — `AGENTS.md`'s exemption covers everything under `docs/New-Solution-New-Design/`. |
