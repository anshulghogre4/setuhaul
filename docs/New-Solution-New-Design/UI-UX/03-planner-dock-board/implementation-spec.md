# Implementation spec — planner dock board (E5.3)

> **M5 / E5.3 (issue #38).** The buildable translation of `03-planner-dock-board/`'s locked design, on top
> of the design system E5.0 shipped and the tool catalog M3 actually closed. **This file defines no new
> design decisions.** Every value is copied from a foundations file, a surface file, `mockup.html`, or
> verified source in `backend/` / `supabase/`, with its source named. Where a value has no source, or two
> sources disagree, it is in §6 as a decision the owner has to make — not resolved here.
>
> **Read for this pass, and only these:** all six `03-planner-dock-board/` files (`screens.md`,
> `flows-and-states.md`, `edge-cases.md`, `components.md`, `accessibility.md`, `stitch-prompts.md`) plus
> `mockup.html`; `00-foundations/` — `components.md`, `accessibility-behaviour.md`, `color.md`,
> `typography.md`, `spacing-and-layout.md`; `SOLUTION_DESIGN.md` §5.1, §7.3, §7.5.1, §7.5.3, §9.2;
> `01-driver-chat/implementation-spec.md` and `02-ops-exception-console/implementation-spec.md` (as
> templates and as the source of the shared-token fixes this surface has to inherit); and the live
> `backend/app/services/planner_service.py`, `backend/app/api/v1/routers/planner.py`,
> `backend/app/api/v1/routers/scheduling.py`, `backend/app/api/v1/routers/operations.py`,
> `backend/app/scheduling/allocation.py`, `backend/app/scheduling/expiry.py`,
> `backend/app/services/operations_reads.py`, `backend/app/repositories/operations.py`, and
> `supabase/migrations/20260823060000_d1_correctness_bedrock.sql`.
>
> **Status: MOSTLY BLOCKED. 10 of 30 states ship now; 3 are gated on one open fork; 17 are blocked on
> backend gaps that are not UI decisions.** Nineteen rendering defects found by measurement, **all
> nineteen fixed and re-measured** (one of them a regression this pass introduced and then caught). Ten
> backend/spec gaps escalated rather than designed over.
>
> **This is the most backend-blocked of the three surfaces audited so far** — E5.1 shipped 24/28, E5.2
> 9/16, E5.3 10/30 — and the reason is specific and checkable, not a vibe: M3's E3.6 scoped the planner
> catalog to `block_dock` / `end_dock_block` only (read its own sub-issue list), on the assumption that
> the rest of §7.5.1 already existed. **It does not.** Six of the nine §7.5.1 tools are absent or have a
> different contract, and `dock_occupancy.state` — the column the entire board is coloured by — is not in
> the shipped schema.

**Owner decisions still open: eight (§6).** Nothing in §5's fix pass required one; everything in §6 does.

---

## 0 · Starting point — what exists, verified not assumed

### 0.1 What M3 actually shipped for this surface

E5.3's issue lists **M3 as a blocker** and M3 is closed. Checked tool-by-tool against `SOLUTION_DESIGN.md`
§7.5.1 and §7.5.3, read off source — not taken from the milestone's closed state, and not taken from
E3.6's issue title either.

| §7.5.1 tool | Shipped? | Source |
|---|---|---|
| `get_planner_queue` | ❌ **NOT SHIPPED in this shape** | Nearest is `operations_reads.get_appointment_schedule` → `repositories/operations.py:85`, which returns `appointment_id / shipment_id / slot_id / appointment_status / is_current / booked_at / confirmed_at / updated_at / facility_id / dock_id / slot_start_ts / slot_end_ts / slot_status`. **None of §7.5.1's seven required fields** — condensed receipt, displacement check, ETA confidence, `latest_acceptable_ts`, TTL remaining, `snapshot_hash`, composite-urgency order. §5.1 G1 |
| `confirm_request` | 🟡 **Different contract** | `scheduling.py:214` → `allocation.confirm_appointment`. Takes `warehouse_confirmation_ref` (**required**, and not in §7.5.1) + `note`. **No `snapshot_hash`.** Returns `ALREADY_ACTIONED` (`allocation.py:263`) but **not** `SNAPSHOT_STALE` and **not** `DISPLACEMENT_DETECTED` — grepped, zero occurrences. §5.1 G2, G3 |
| `counter_offer` | ❌ **NOT SHIPPED** | Zero occurrences in `backend/app/`. §5.1 G4 |
| `reject_request` | 🟡 **Enum not enforced** | `scheduling.py:251`. Takes `rejection_reason: str(min 1, max 500)` — **free prose**. §7.5.1's five-value controlled vocabulary is *not* a server-side constraint. §5.1 G7 |
| `hold_for_information` | ❌ **NOT IMPLEMENTABLE against the live schema** | `expiry.py:77-81` says so itself: *"`public.appointments` has no deadline/expires_at column, so there is nowhere for §7.5.1's `hold_for_information` … to record an extension."* §5.1 G5 |
| `bulk_confirm` | ❌ **NOT SHIPPED** | Zero occurrences. §5.1 G6 |
| `escalate_request` | 🟡 **Exists, different shape** | `operations.py:215` `POST /operations/escalate` → `escalate_exception`. `WAREHOUSE_PLANNER` is inside `OPS_PORTAL_ROLES` (`deps.py:63-69`), so a planner can reach it. Argument shape is `EscalateExceptionCommand`, not §7.5.1's `(appointment_id, reason, owner?)` |
| `block_dock` | ✅ **Fully shipped, and well** | `planner_service.py:299`, `planner.py:68`. Returns `BLOCKED` with the affected set · `ALREADY_BLOCKED` naming the conflict (`planner_service.py:339`) · opens **one** `CAPACITY_EVENT_CASCADE` per block, not one per stranded appointment (`planner_service.py:232`) |
| `end_dock_block` | ✅ **Fully shipped** | `planner_service.py:423`, `planner.py:103`. `UNBLOCKED` / `NOT_BLOCKED` (`planner_service.py:460`) |
| *(bonus, not in §7.5.1)* `get_dock_block_impact` | ✅ | `planner_service.py:187`, `planner.py:48`. This is exactly what the block-dock form's live affected-appointment check needs |

**Two and a half of nine.** Plus §7.5.3 (sequencer) in its entirety:

| §7.5.3 tool | Shipped? |
|---|---|
| `propose_facility_schedule` | ❌ — **open issue #49**, milestone M8 |
| `apply_schedule_proposal` | ❌ — same |
| `get_scheduling_run` | ❌ — same |

**And one schema fact that is larger than any of them.** `components.md` §3 grounds the entire board in
`dock_occupancy.state`, enumerating nine values and mapping each to a chip token. **That column does not
exist.** The shipped table (`supabase/migrations/20260823060000_d1_correctness_bedrock.sql:175-182`) is:

```sql
CREATE TABLE IF NOT EXISTS public.dock_occupancy (
  occupancy_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  dock_id text NOT NULL REFERENCES public.docks(dock_id),
  appointment_id text NOT NULL REFERENCES public.appointments(appointment_id),
  "window" tstzrange NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  EXCLUDE USING gist (dock_id WITH =, "window" WITH &&)
);
```

No `state`, no `expires_at`. `expiry.py:88-95` independently confirms this, verified against production on
2026-08-23. §5.1 G8.

Verified alongside, and this part is genuinely good:

| Fact | Source |
|---|---|
| `block_dock` requires an `Idempotency-Key` and 400s without one (U70) | `planner.py:40-46, 68` |
| The planner router is role-gated to `WAREHOUSE_PLANNER` + `ADMIN`, **deliberately narrower** than `OPS_PORTAL_ROLES`, because `assert_facility_write_scope` alone would let any operator role block a dock | `planner.py:6-11` — the docstring reasons it explicitly |
| `dock_status_events`' `CHECK` admits `MAINTENANCE / BREAKDOWN / CAPACITY_REDUCTION / REOPENED / MANUAL_BLOCK`; `block_dock` writes four of the five | `planner_service.py:34-37` |
| The `CAPACITY_EVENT_CASCADE` dedupe key is `{dock_event_id}:CAPACITY_EVENT_CASCADE` — one incident row per block, which is exactly U65 | `planner_service.py:289` |
| `ALREADY_ACTIONED` names the winning transition rather than returning a bare error, per §9.2 #3 | `allocation.py:247-263` |

### 0.2 The frontend after E5.0 / E5.1 / E5.2

| Fact | Consequence for E5.3 |
|---|---|
| `theme.css` carries every token this surface references, including the four `--priority-*-marker` steps and the promise-state family | Nothing to add for colour. |
| **`00-foundations/color.md` was corrected on 2026-08-29** — `state-shown-border: neutral-500`, `state-held-border: amber-600 / amber-500`, `escalation-sla-warning: amber-700`, `escalation-sla-breach: red-700` | E5.2's Fork F was accepted. **This mockup had not inherited any of it** — §5.3-R3/R4. |
| `identity.ts` gives planner `density: compact`, `hasFacilityScope: true`, a rail | Set `data-density="compact"` once at the route root. |
| **No streaming transport exists except the driver `/chat` SSE turn stream** | Same gap E5.2 filed as its G6. Here it gates the "3 new · press R" affordance, U19's frozen-sort arrivals, and `edge-cases.md` §1's `assertive` announcement. §5.1 G10. |
| Issue **#52 is OPEN** — `/auth/me` returns one `role_name`, not `grants[]` | Less severe here than for ops: this surface is deliberately **single-facility** (`screens.md` §1 — "not 'All facilities'"), so the switcher needs only the user's own facility list, not a cross-facility scope union. |

---

## 1 · The console shell — two tabs, one workspace

`screens.md` §1. One surface, two tabs (U102), never a permanent split.

```
┌──┬────────────────────────────────────────────────────────────────────────────┐
│▌ │ TOP BAR 56px   [Jaipur ▾]  ⟨Queue│Board⟩  search   bell · help · account    │
├──┼────────────────────────────────────────────────────────────────────────────┤
│56│ role="main"                                                                 │
│  │   Queue tab  → the 7-field row, §7.3's 30-second decision                   │
│  │   Board tab  → dock/time Gantt, counter-offer picker, block form, diff      │
├──┴────────────────────────────────────────────────────────────────────────────┤
│ STATUS BAR 28px  ● connection(role=status) · last sync · facility · pending · policy │
└───────────────────────────────────────────────────────────────────────────────┘
```

**Queue and Board are tabs, not routes, and this is a foundations decision rather than a judgement call.**
`00-foundations/components.md`'s *"What is a rail destination, and what is a tab"* table (added 2026-08-26)
names **Planner (Queue · Board)** in its Tabs row explicitly: *"different views or objects within one
workspace the role occupies all shift."* The mockup rendered them as `<a href="#" aria-current="page">` —
page navigation — which is the one thing that table says they are not. Fixed and re-measured: `role="tablist"`
14, `role="tab"` 28, `aria-selected` 28 (§5.3-R13). `accessibility.md` binds `Cmd/Ctrl+1` / `+2` to them,
and a tab shortcut needs tab semantics to move between.

Rail: 56px, **two destinations — this console and Profile.** `screens.md` §1 asserts this and cites
`02-ops-exception-console/`. That surface's own spec then raised the same two items as **Fork E**
(`iconography.md`'s Rail destinations table enumerates *one* destination per role, and puts the user menu
in the top bar). **The same fork applies here and is not re-opened** — see §6 Fork H, which carries it
forward rather than answering it a second time in a different direction.

Breakpoint: `spacing-and-layout.md`'s surface table gives Planner **1280px+, target 1600×900**, with
*"1024–1280px degrades to a reduced column set; below 1024px shows 'use a larger screen'."* State 30
renders the below-1024 statement. **There is no artboard for the 1024–1280 reduced column set** — §6 Fork D.

Measured, all four widths, after the fix pass: no horizontal overflow at 1600 / 1440 / 1280. At **1024 the
board page overflows by 165px**, which is the artboard *sheet* (fixed 1280px-wide cards) overflowing, not
the console — the console at that width has no rendered reference at all. Stated so it is not mistaken for
verification either way.

---

## 2 · The 30-second row, measured

This is the surface's whole thesis, and the brief asked for it to be measured rather than asserted.

### 2.1 Scan density — the number nobody has written down

| Measure | Value | Source |
|---|---|---|
| `compact` row height | **36px** | `spacing-and-layout.md`'s density table |
| Rendered queue row, **two-line** (26 of 40 measured) | **59px modal, 61.2px mean** | Measured, all 7 tables, 1440px |
| Rendered queue row, **one-line** (14 of 40) | **36px modal, 36.1px mean** | Measured |
| Usable list height at the stated 1600×900 target | **708px** (900 − 56 topbar − 28 statusbar − 72 toolbar+bulk bar − 36 header) | Computed from measured chrome |
| **Rows visible per screen at 59px** | **12** | 708 / 59 |
| Rows visible per screen at 36px | 19 | 708 / 36 |
| §7.3's load | **15–35 pending** | `SOLUTION_DESIGN.md` §7.3 |

**So a 35-request spike is three screenfuls, not two.** That is a real throughput fact and it is not
recorded anywhere in the design.

**It is not a defect, and it should not be "fixed" by squeezing to 36px.** The row is 59px because it
carries two identity lines and a two-line condensed receipt, and because `components.md` §1 says the
displacement check **never truncates** — §7.3 calls it "the single most important field," and a truncated
warning is a warning that failed at its one job. Forcing 36px would either truncate that field or drop the
carrier. The trade is correct; what is missing is that anyone made it deliberately. §6 Fork A.

### 2.2 Interaction cost per row — 151 targets under the surface's own floor

`spacing-and-layout.md` gives `compact` a **32px minimum tap target** — the deliberate desktop-and-pointer
exception to the product's 44px rule, with a footnote warning that a later "we only need AA" review must
not shrink anything to 24px.

Measured before the fix pass: **151 of 304 interactive elements below 32px**, and **31 of them below WCAG
2.2 SC 2.5.8's 24×24 Level AA legal floor**:

| Element | Count | Size | Under |
|---|---:|---|---|
| `.ibtn` — the five per-row affordance buttons | 74 | 24×24 | 32px floor |
| `.iconbtn` — top-bar controls | 27 | 24×24 | 32px floor |
| `.cb` — **the selection checkbox** | 30 | **16×16** | **both**, incl. SC 2.5.8 |
| `.ibtn.btn-inactive` | 10 | 24×24 | 32px floor |
| `.radio` — reject-reason options | 2 | 295×**17** | **both** |
| `.lane-open.pick` — board counter-offer targets | 2 | 159.9×**20** | **both** |
| `.pill-btn`, `.btn.btn-neutral` | 5 | 24–28px tall | 32px floor |

The checkbox one matters most: **selection is this surface's throughput feature** (U63's "Select all
eligible (N)", §7.3's five safe-batch predicates), and it was a 16×16 target. All fixed by growing the hit
area around an unchanged glyph, so no artboard moved a pixel. Re-measured: **0 under 32, 0 under 24**
(§5.3-R16).

### 2.3 The seven fields, and one vocabulary collision

`screens.md` §2's seven fields render as 9 table columns (selection+priority · identity · interval ·
receipt · displacement · ETA · limit · TTL · actions). All 7 tables now `table-layout: fixed` — the
flagship artboard was `auto` (§5.3-R17), against `components.md` §1's re-derived **hard** rule that a
reflow during a read is an operational cost on this screen specifically.

**The collision:** the toolbar reads `Filter: CRITICAL · 12 shown` while rows beneath it render receipts
beginning `CRITICAL`, `HIGH`, `NORMAL`, `NORMAL`, `LOW`. Two different vocabularies both use
CRITICAL/HIGH/NORMAL/LOW — the **shipment priority** (which drives the `--priority-*-marker` left edge and
which `screens.md` says the filter filters on) and the **decision receipt's own lead term** (`components.md`
§4's condensed variant, which is the delay/urgency band). A planner reading a CRITICAL filter next to a
NORMAL row cannot tell which one the filter used, and resolving that costs exactly the seconds §7.3
budgets. §6 Fork B — flagged rather than reworded, because relabelling the toolbar papers over a collision
that exists in the vocabulary itself.

---

## 3 · The 30 states → build readiness

30 artboards in `mockup.html`, one per `stitch-prompts.md` screen/state, in that file's order. Copy is
authoritative in `stitch-prompts.md` at the prompt number given.

**Legend:** 🟢 buildable today · 🟡 buildable, one open fork · 🔴 blocked by a §5.1 gap.

### A · Shell (States 4–5)

| # | State | Gap | Build |
|---|---|---|:--:|
| 4 | Console shell, rail expanded as an overlay | — | 🟢 |
| 5 | Console shell, offline — icon **and** text change, never a coloured dot alone | — | 🟢 |

State 5 is the one that now carries `role="status"` on the connection state (§5.3-R15).
`accessibility-behaviour.md` added that row specifically so going offline is not silently swallowed — *"a
planner who goes offline and keeps confirming is acting on stale capacity data."* It was unimplemented.

### B · Queue (States 1, 6–11, 26–27, 29–30)

| # | State | Gap | Build |
|---|---|---|:--:|
| 1 | Queue tab at rest — the 30-second row | G1, G2 | 🔴 |
| 6 | Queue row — the six states, one sheet | G1 | 🔴 |
| 7 | The paused countdown and its resume | **G5 — hard** | 🔴 |
| 8 | Confirm refusals in place: `ALREADY_ACTIONED` · `SNAPSHOT_STALE` · `DISPLACEMENT_DETECTED` | G2, G3 | 🔴 |
| 9 | Bulk confirm — 12 eligible selected, ineligible visible in place | G6 | 🔴 |
| 10 | Confirm 12 in flight — width frozen, label unchanged | G6 | 🔴 |
| 11 | Toast set — bottom-left, max 3 stacked, 5s undo | G1–G6 (nothing to toast yet) | 🔴 |
| 26 | Three empty queues that mean three different things | Fork C | 🟡 |
| 27 | Queue loading — real rows held invisible, exact dimensions | — | 🟢 |
| 29 | Load failed · out of scope · maintenance | — | 🟢 |
| 30 | Under 1024px — a statement, not a squeezed table | — | 🟢 |

**State 8 is the one to protect in review, and it is currently fiction.** Its three refusal codes are the
heart of `edge-cases.md` §1–§3 and §9.2 #3. `ALREADY_ACTIONED` is real (`allocation.py:263`).
**`SNAPSHOT_STALE` and `DISPLACEMENT_DETECTED` do not exist anywhere in `backend/app/`** — grepped. Build
the artboard; do not build a client-side approximation of either, because a client-computed displacement
check is precisely the "auto-confirmation wearing a button" §7.5.1 warns about.

**State 7 is hard-blocked, not merely unbuilt.** `hold_for_information` cannot be implemented against the
live schema at all, and `expiry.py` says so in its own comment, with the reason: faking it by touching
`booked_at` would corrupt the request's history. The Paused countdown state (U67, `components.md` §3) is
one of the better-specified components in the product and has nowhere to run.

**States 27 and 29 are 🟢 and worth calling out as genuinely good.** The skeleton technique — render the
real rows invisible so they keep their exact dimensions, then draw a block over them (U78) — is
independent of any data contract, and State 29 splits load-failure, out-of-scope and maintenance into
three distinct states rather than one generic error.

### C · Board (States 2, 22–23, 28)

| # | State | Gap | Build |
|---|---|---|:--:|
| 2 | Board at rest — bars coloured by `dock_occupancy.state`, outage shown | **G8 — the column does not exist** | 🔴 |
| 22 | Board empty — lanes still render, labelled, with the now-line | G8 | 🔴 |
| 23 | Board failed to load — scoped to the region, queue stays usable | — | 🟢 |
| 28 | Board loading — shaped like lanes, not like rows | — | 🟢 |

**State 2 absorbed four of this pass's fixes and is a different artboard now**: the time axis and the task
bars were on two different coordinate systems (§5.3-R19), the now-indicator stopped at the first dock
(R11), two of six dock lanes were missing (R12), and the outage hatch shared a colour with the empty track
it sat on (R18). All four were invisible in a markup skim and obvious the moment it rendered.

### D · Counter-offer picker (States 3, 24–25)

| # | State | Gap | Build |
|---|---|---|:--:|
| 3 | Picker active (U103) — ineligible dock dimmed, reason **as text in the lane** | G4, G8 | 🔴 |
| 24 | Revalidating a click, and the interval taken a moment ago | G4 | 🔴 |
| 25 | The request expired while the planner was picking a slot | G4, G10 | 🔴 |

The design here is right and the reasoning is worth keeping verbatim: the ineligible lane dims **in place**
rather than hiding, so the planner still sees the whole facility; its reason is text in the lane, *"not a
tooltip a mouse-free user would never find"*; and it is `components.md` §18's **Disabled** (a
prerequisite-driven unavailability specific to *this* shipment, recomputed per shipment), **not** Hidden,
which is what a permission state would be (U83).

**Which is exactly why §5.3-R9 mattered**: the whole lane dimmed to 35% opacity, taking the reason text
with it, so the explanation rendered at **1.73:1** — an explanation nobody can read is not an explanation,
and §18's Disabled contract requires one.

### E · Reject and Hold (States 12–15)

| # | State | Gap | Build |
|---|---|---|:--:|
| 12 | Reject — reason → internal note → preview → send | G7 | 🟡 |
| 13 | Reject — the send failed, dialog stays open, values survive | G7 | 🟡 |
| 14 | Hold for information — the only affordance that stops a clock, one-shot | **G5 — hard** | 🔴 |
| 15 | Hold refusals — send failed, and `HOLD_ALREADY_USED` | **G5 — hard** | 🔴 |

**12/13 are 🟡 rather than 🔴 because the dialog is buildable and the reason picker is not.** `reject_appointment`
exists and works; its `rejection_reason` is a free 500-char string. §7.5.1 is explicit that the enum exists
*"precisely because it is rendered to the driver — free prose here becomes an unreviewed customer-facing
message."* Build the five-option picker; know that until G7 lands the vocabulary is a client-side courtesy,
not a contract — **unlike** ops's `resolve_escalation`/`cancel_escalation`, which E5.2 verified *are*
enforced server-side with a 422 naming the supported set. Two sibling flows, two different guarantees.

### F · Block a dock (States 16–18)

| # | State | Gap | Build |
|---|---|---|:--:|
| 16 | Affected appointments named before the planner commits | — | 🟢 |
| 17 | "checked, none" and "not checked yet" are different facts and look different | — | 🟢 |
| 18 | `ALREADY_BLOCKED` names the conflicting block instead of failing vaguely | — | 🟢 |

**These three are the strongest states on the surface and the only group with a complete backend.**
`block_dock`, `end_dock_block` and `get_dock_block_impact` all shipped in E3.6, the affected set comes back
in the response, `ALREADY_BLOCKED` names the conflict, and the `CAPACITY_EVENT_CASCADE` is opened
server-side as **one** row per block (`planner_service.py:232, 289`) — which is U65, enforced in the
implementation rather than hoped for in the UI.

State 17's distinction is the kind of thing that is easy to lose in a build: **"we checked and there are
none" and "we have not checked yet" are different facts, and `[ Block dock ]` stays Disabled through the
second one.** Keep both states.

Block dock is `cautionary`, **not** `destructive`, and there is deliberately no typed-confirmation gate —
`components.md` §6 reasons it: blocking is reversible via `end_dock_block`, and the named-appointment
warning already supplies the friction. High-tier friction is reserved for genuinely hard-to-reverse
actions.

### G · Sequencer proposal (States 19–21)

| # | State | Gap | Build |
|---|---|---|:--:|
| 19 | Diff drawn on the board itself — current beneath, delta outlined on top | **G9 — issue #49** | 🔴 |
| 20 | Unplaceable shipment listed, not ghosted; and Apply in flight | G9 | 🔴 |
| 21 | `SNAPSHOT_DRIFT` · `PARTIALLY_INFEASIBLE` · `RUN_ALREADY_ACTIVE`, told apart | G9 | 🔴 |

All three are blocked on the same open issue that blocks E5.2's prompt 14 — **#49, §7.5.3 entirely
unbuilt**. This is the planner half of U93's two-surface handoff; the ops half is blocked on the same
issue. Neither side can be built, and neither side is at fault.

State 21's third case is worth protecting: **`RUN_ALREADY_ACTIVE` is an expected condition, not a
failure**, and `edge-cases.md` §4 renders it as an inline state ("A re-sequence is already running — you'll
be notified when it's ready") rather than an error. The mockup gets this right — `role="status"`, not
`role="alert"`. Keep the distinction.

### Tally

**🟢 10 · 🟡 3 · 🔴 17.**

---

## 4 · What E5.3 adds to the design system

**Two component-scoped tokens' worth of CSS, and no new colour.** The board's task bars, outage hatch,
now-indicator and proposal-delta treatments are all built from tokens that already exist:
`--state-{shown,held,pending,confirmed}-*`, `--priority-*-marker`, `--text-tertiary`, `--red-600`,
`--surface-{base,raised,hover}`. Set `data-density="compact"` once at the route root; never per component.

Two additions this pass made, both stated so they are not mistaken for new decisions:

- `.pill-inactive` — mirrors the existing `.btn-inactive` so the two Inactive treatments on this surface
  read as one decision (§5.3-R23). `components.md` §18's Inactive, not Disabled.
- `.nowlayer` — a positioning layer that matches the track's box exactly, so the now-indicator resolves
  against the same scale as the axis and the bars (§5.3-R11/R19). Geometry, not style.

One correction is owed **to** the design system rather than added by it: `color.md`'s TTL-urgency table
(§6 Fork E).

---

## 5 · Readiness call

**Verdict: 10 of 30 states build now. 3 are gated on one open fork. 17 are blocked on backend gaps that
are not UI decisions.** Nineteen rendering defects found by measurement, all nineteen fixed and re-measured;
fourteen contrast readings retracted as correct; one regression introduced by this pass and caught by
re-measurement.

### 5.0 Fix-pass scoreboard — every item re-measured, none assumed

Method: headless Chromium (Playwright 1.62.1) over `file://`. Computed styles and box model across all
artboards, contrast computed from **rendered** `rgb()` values against each element's effective background
(including inherited `opacity` up the ancestor chain), ARIA census over the live DOM, Gantt geometry
measured per board, four viewport widths, forced `prefers-color-scheme` in both directions, opt-in
`data-theme` in both directions, and clipped screenshots at DPR 2 before and after.

| | Before | After |
|---|---|---|
| Contrast failures, light | **51** | **0 real** (14 flagged, all 14 retracted — §5.3 closing) |
| Contrast failures, dark | **18** | **0 real** |
| Targets < 32px (`compact` floor) | **151 / 304** | **0 / 304** |
| Targets < 24px (WCAG 2.2 SC 2.5.8 AA) | **31** | **0** |
| `@media (prefers-color-scheme: dark)` rules | **3** | **0** |
| `--surface-base` under emulated dark OS preference | **`#020617`** | **`#F8FAFC`** |
| `<main>` / `role="main"` | **0** | **14** |
| `<nav>` / `role="navigation"` | **0** | **14** |
| `role="tablist"` / `role="tab"` | **0 / 0** | **14 / 28** |
| `aria-selected` | **0** | **28** |
| `role="status"` | 9 | **23** |
| `role="checkbox"` with no accessible name | **21** | **3** (all inside `aria-busy="true"` skeletons) |
| Gantt axis px/hour vs track px/hour | **120.0 vs 190.3** (1.59× error) | **equal on all 11 boards** |
| Now-indicator height vs lane-stack height | **28px vs 78–206px** | **equal on all 7 boards that have one** |
| `table-layout: auto` queue tables | **1 of 7** (the flagship artboard) | **0 of 7** |
| Task bars rendered | 29 | **30** (`IN_PROGRESS` was specified and rendered nowhere) |
| Dock lanes on State 2 | **4 of 6** | **6 of 6** |

**No regressions:** 30 artboards before and after; **0** text nodes below `typography.md`'s 11px floor
before *and* after; no `transition: all`; the single `outline:none` still carries its `box-shadow`
`:focus-visible` replacement; `…` ×15 with **zero** `...`; no emoji; **no blanket
`*{animation:none!important}` reduced-motion kill** (the pattern E5.0 flagged and E5.1 had to remove — it
does not recur here, same clean inheritance E5.2 got); `overscroll-behavior: contain` present on modals;
opt-in `data-theme="dark"` verified still fully functional after R1, resolving `state-held-border` to
`amber-500` and `state-shown-border` to `neutral-500` exactly as `color.md` specifies for dark.

### 5.1 Ten escalated gaps — none of them a UI decision

Found the standing rule's way: cross-check each job the persona row lists against what a tool actually
does. **G1, G4, G5, G6 and G8 are the same class that produced §7.5.5, §7.5.1's `block_dock`, §7.5.6 and
§7.5.7** — a listed job with no tool, found by looking rather than by assuming a closed milestone closed it.

**The framing that matters:** E3.6's own sub-issue list scopes the planner half of M3 to *"`block_dock` /
`end_dock_block`, writing `dock_status_events`"* — two tools. It corrected `TASKS.md` for **gate/yard**
("only a read exists … this is a from-scratch build") but made no equivalent check for the planner's other
seven. That check is this section.

**G1 · 🔴 `get_planner_queue` does not exist in §7.5.1's shape.** The nearest read,
`operations_reads.get_appointment_schedule`, joins `appointments` to **`appointment_slots`** — not
`dock_occupancy` — and returns none of the seven §7.3 fields (condensed receipt, displacement check, ETA
confidence, `latest_acceptable_ts`, TTL remaining, `snapshot_hash`), nor the composite-urgency ordering
(TTL · priority · physically-waiting via `facility_checkins.queue_state`). Note it also reads the table
§0.9 already resolved *against* — D1 declares `dock_occupancy` the authority. **Gates States 1, 6, 8, 9,
10, 11 — every queue state.**

**G2 · 🔴 `snapshot_hash` does not exist anywhere in the product.** Zero occurrences across
`backend/app/`. It is an argument on four separate §7.5.1/§7.5.3 tools (`confirm_request`, `counter_offer`,
`bulk_confirm`, `apply_schedule_proposal`) and the mechanism behind `SNAPSHOT_STALE` and `SNAPSHOT_DRIFT`.
Without it there is no optimistic-concurrency story for the throughput path at all, and
`flows-and-states.md` Flow 1 step 5's *"never a silent retry with old context"* has nothing to detect stale
context with.

**G3 · 🔴 `confirm_request`'s refusal taxonomy is one-third built, and its argument list is wrong.**
`ALREADY_ACTIONED` is real and good. `SNAPSHOT_STALE` and `DISPLACEMENT_DETECTED` are absent. Separately,
the shipped `ConfirmAppointmentCommand` requires **`warehouse_confirmation_ref`** (`allocation.py:110`) — a
mandatory field that appears in no design file, has no UI anywhere in the 30 artboards, and would block
every confirm. Either the design owes it a field or the tool owes it a default.

**G4 · 🔴 `counter_offer` does not exist.** Zero occurrences. This is U103's entire affordance — the one
that leaves the tab — and the reason the Board tab has an interactive mode at all. **Gates States 3, 24,
25**, and with them `flows-and-states.md` Flow 2 end to end.

**G5 · 🔴 `hold_for_information` is not implementable against the live schema, and the codebase says so.**
`expiry.py:77-81`: *"`public.appointments` has no deadline/expires_at column, so there is nowhere for
§7.5.1's `hold_for_information` … to record an extension. Until that column exists, a planner cannot buy
time on a request — flagged rather than worked around, because faking it by touching `booked_at` would
corrupt the request's own history."* That is the right call and it is why two of thirty states cannot be
built. Needs a migration, not a tool.

**G6 · 🔴 `bulk_confirm` does not exist.** Zero occurrences. §7.3's spike-clearing path and U63's "Select
all eligible (N)" have no server side, and with it goes the server-side re-evaluation of the five safe-batch
predicates at press time — which §7.5.1 identifies as the thing that keeps D6's human authority real
rather than ceremonial. **Gates States 9, 10.**

**G7 · 🟡 `reject_request`'s `reason_code` enum is not enforced.** Shipped as `rejection_reason: str(min 1,
max 500)`. §7.5.1: *"`reason_code` is an enum precisely because it is rendered to the driver — free prose
here becomes an unreviewed customer-facing message."* The five-value vocabulary
(`CAPACITY`/`RULE_VIOLATION`/`PRIORITY_CONFLICT`/`SAFETY`/`DATA_CONFLICT`) appears nowhere in
`backend/app/`. Contrast E5.2's finding that ops's two `reason_code` enums **are** enforced with a 422
naming the supported set — so this is an inconsistency between two sibling flows, not a product-wide
posture.

**G8 · 🔴 `dock_occupancy` has no `state` column, so the board has nothing to colour by.** `components.md`
§3's mapping table — nine `dock_occupancy.state` values mapped to chip tokens, the single most-cited table
in this surface's design — is grounded in a column that is not in the shipped schema
(`20260823060000_d1_correctness_bedrock.sql:175-182`, independently confirmed against production in
`expiry.py:88-95`). The same migration gap also blocks D2's HELD promise-state (**open issue #53**).
**Gates States 2, 3, 22** and the board half of everything else.

**G9 · 🔴 §7.5.3 is entirely unbuilt — open issue #49, milestone M8.** All three sequencer tools absent.
**Gates States 19, 20, 21.** Same issue that gates E5.2's prompt 14; the two surfaces are the two halves of
U93's handoff and both halves are waiting on it.

**G10 · 🔴 No live-update transport exists — the same gap E5.2 filed as its G6, reconfirmed here.** The
only streaming endpoint is the driver `/chat` SSE turn stream. On this surface it gates:

- `stitch-prompts.md`'s **"3 new · press R to re-sort"** affordance and U19's arrivals-accumulate-behind-
  frozen-sort (rendered on State 9);
- `accessibility-behaviour.md`'s **`polite`, count-only** row for *"Planner queue — new row arrives"* — a
  row that file wrote **for this surface by name**;
- its **`assertive`** row for *"the row a user **is** focused on is acted on elsewhere"* — §9.2's nastiest
  race, and `edge-cases.md` §1's central requirement;
- State 25's mid-pick expiry, and the status bar's "synced 3 s ago".

### 5.2 The shared-token reconciliation — and what it turned up

The brief asked whether this surface inherits E5.1's and E5.2's shared-token corrections.

**Direct answer: it did not, and unlike the ops console, this surface genuinely uses them.** E5.2 found
that its own board renders no promise-state chip at all, so the question was moot there. **This board
renders the promise-state tokens on every task bar** (`components.md` §3 — "reuses the promise-state chip's
exact tokens rather than an invented Gantt palette"), so the corrections apply directly.

`00-foundations/color.md` **was** corrected on 2026-08-29 — E5.2's Fork F was accepted, and the file now
carries a dated note explaining the raise. The planner mockup still had the pre-correction values:

| Token | `color.md` (corrected) | Mockup (before) | Measured effect |
|---|---|---|---|
| `state-shown-border` | `neutral-500` / `neutral-500` | `neutral-300` / `neutral-600` | — (SHOWN renders no bar) |
| `state-held-border` | `amber-600` / `amber-500` | `amber-500` / `amber-500` | HELD bar border **1.96:1** against its track |

Both corrected and re-measured (§5.3-R3/R4). The HELD bar's border went **1.96 → 2.91:1**.

**2.91 still does not clear WCAG 1.4.11's 3:1 for a UI component boundary, and this is a foundations
question, not a mockup one.** `amber-600` was tuned against a *chip* background; a Gantt bar sits on a
`surface-hover` track, a lighter-relative context the chip never occupies. Per the standing rule
foundations wins, so the mockup now carries `amber-600` faithfully and the residual 0.09 is escalated
rather than papered over by deviating one step further. §6 Fork F.

Final bar-border contrast, all eight bar treatments, measured:

| Bar | Contrast vs track | Passes 1.4.11 |
|---|---:|---|
| `confirmed` | 3.44 | ✅ |
| `pending` | 3.36 | ✅ |
| **`held`** | **2.91** | ❌ **Fork F** |
| `blocked` (outage) | 4.34 | ✅ (was **1.36**) |
| `confirmed current-dim` | 4.34 | ✅ (was 1.36 after my own R10) |
| `proposed confirmed` | 3.44 | ✅ |
| `proposed pending` | 3.36 | ✅ |
| `revalidating` | 4.34 | ✅ (was **1.36**) |

### 5.3 Nineteen rendering defects — measured, not inspected · **ALL FIXED 2026-08-29**

Scoreboard in §5.0; the diagnoses below are kept because *how* each was found is what stops it recurring.
Every fix carries a dated inline comment in `mockup.html` at the site it changes.

**R1 · The board auto-switches to dark on OS preference — fourth recurrence of one bug.** Three
`@media (prefers-color-scheme:dark){ :root:not([data-theme="light"]){…} }` blocks. Measured: under emulated
dark preference, `--surface-base` resolved `#020617` while `document.documentElement`'s `data-theme` was
`null` — the system, not the user, picked the theme, which is what U69 forbids. **The fix was free, again**:
each block was verified property-by-property to be byte-identical to a `:root[data-theme="dark"]` block
immediately after it (30, 27 and 2 properties, zero differences), so deleting the media wrappers removed
the automatic switch and kept dark fully available. Verified after: opt-in `data-theme="dark"` still
resolves the full dark palette. `color-scheme: light dark` → `light` for the same reason. *(E5.0 removed
this from the shared shell; E5.1 from the driver board; E5.2 from the ops board; it survived here.)*

**R2 · The `theme-color` pair, same bug one layer up.** With R1's CSS fixed,
`<meta name="theme-color" … media="(prefers-color-scheme: dark)" content="#020617">` would have left a
dark-preference browser rendering a light page while painting its own chrome near-black. Replaced with one
unconditional value.

**R3 / R4 · The two E5.1 border corrections had not been inherited.** Diagnosed in §5.2.

**R5 · The top-bar search placeholder is 4.34:1.** `text-tertiary` on `surface-hover`, 13 instances.
Placeholder text is still text. *(Identical to E5.2's R5 — the same construction copied between mockups.)*

**R6 · The displacement check — §7.3's "single most important field" — fails AA.** `.displ-none`
("conflicts with none") at `text-tertiary`, **4.34–4.37:1**, 6 instances. Worth noting how it hid: the
token is correctly named, correctly used, correctly themed, and passes against `surface-base`. It fails
only against `surface-selected`, i.e. on the rows a planner has actually selected. **This is the defect
class that only appears in combination** — no single token is wrong, the pairing is.

**R7 / R8 / R8b · Three more `text-tertiary` values under AA.** `.cell-carrier` (4.34–4.37), `.t-exp` (the
expired countdown, 4.34), `.struck` (the struck interval and receipt on an expired row, 4.37). A struck
value is still read — that is the whole point of showing it struck rather than removing it.

**R9 / R9b · The Disabled lane could not explain itself — and the first fix did not work.**
`.dockrow.dim` set `opacity:.35` on the whole row, so the ineligible dock's identity rendered at **2.23:1**
and its reason text — *"Heavy-load dock — not eligible for this shipment"* — at **1.73:1**. `components.md`
§18 requires a Disabled control to explain itself; an explanation at 1.73:1 does not. **The first fix
failed and re-measurement caught it**: moving the opacity to `.track` and setting `opacity:1` on the child
`.lane-reason` does nothing, because opacity establishes a stacking context a descendant cannot climb out
of. Second attempt recedes the track with a muted fill and a dashed edge, with no opacity anywhere on that
subtree. Recorded because "set opacity back to 1 on the child" is a reflex that does not work.

**R10 / R10b · The proposal overlay's current bars hid the id the diff is read by — and my fix broke
their border.** `.bar.current-dim{opacity:.5}` put `SHP1008`/`SHP1002`/`SHP1009` at **2.21:1**, on the
overlay whose entire job is showing what moved. Replaced opacity with a muted fill so the text keeps full
contrast. **That introduced a regression**: `border-default` against the new fill measures **1.36:1**, so
the bar lost its own boundary. Caught by re-measurement, fixed to `text-tertiary` (**4.34:1**) — the value
R18 had just proved in the same context. Recorded plainly because it is the argument for re-measuring
after every fix rather than after the batch.

**R11 / R11b / R11c · The now-indicator stopped at the first dock, and its label overprinted a tick.**
`.now-line` lived inside a single `.track` with `top:-4px; bottom:-4px`, rendering **28px tall on every
board** against lane stacks 78–206px tall. `screens.md` §3's own ASCII draws it top-to-bottom across every
lane — which is what makes "already in the past" readable on D2/D3/D5 rather than only D1. Hoisted into a
`.nowlayer` that matches the track's box exactly (the same 56px docklabel inset), so it spans the stack
*and* resolves against the same scale R19 gave the axis. Verified: now-line height **equals** lane-stack
height on all 7 boards that carry one.

The label took three attempts, and the failures are the useful part: (a) it was positioned 8% *left* of the
line, landing on the `13:00` tick; (b) centring it on the line just relocated the collision, since the line
is by definition inside some hour cell (measured 785.9–811.7 against the 12:00 tick text at 776–806);
(c) moving it below the lane stack put it outside `.ganttwrap`, whose `overflow-x:auto` computes
`overflow-y` to `auto` as well, so it was clipped and **simply never painted** (labelBottom 1236.5 vs
wrapBottom 1220.5 — a fix that measured as "no collision" precisely because the element was invisible).
The answer is the ordinary Gantt convention: a filled marker pill on the timeline header, `red-600` with
white text (4.8:1), which reads as a marker sitting on the axis rather than as broken text.

**R12 · Two of six dock lanes were missing from the flagship board.** State 2 rendered D1, D2, D3, D5 —
the occupied docks and the blocked one. `screens.md` §3's ASCII draws **D1–D6**, with D4 and D6 entirely
empty, and State 22's own note says *"the lanes stay drawn and labelled."* **A dock board that renders only
occupied docks hides the free capacity a planner is looking for.** An empty lane is a fact, not the absence
of one.

**R16 · 151 of 304 interactive elements sat below the density floor they were built to.** Diagnosed in
§2.2. Fixed by growing hit areas around unchanged glyphs, so nothing moved visually — and the probe was
corrected at the same time to measure the *effective* target (WCAG 2.5.8 measures the target, and a
transparent absolutely-positioned `::after` overlay is part of it) rather than the element's border box,
which understates it.

**R17 · States 1–3 predate the system States 4–30 were built with, and the file says so itself.** The
mockup's own section header reads *"States 1–3 above are unchanged."* They are also the three artboards an
implementer opens first — the same shape as E5.2's R7, where the hero frames were the only ones off-system.
Measured on State 1 specifically: `table-layout: auto` (against `components.md` §1's re-derived **hard**
rule that planner column widths are fixed pixel values, *never* `auto` or `fr`, because a reflow during a
read is an operational cost on this screen and not merely a polish concern); a legacy `.pmark` span
hardcoded to `neutral-800`, which is not any of the four `--priority-*-marker` steps, on row 1 only, with
rows 2 and 3 carrying **no priority marker at all**; carrier sublines as inline `text-tertiary` rather than
the `.cell-carrier` class; and no sort statement.

**R19 / R19b · The time axis did not describe the task bars.** The single most consequential defect in this
pass. `.gantthead` was padded **64px** while `.docklabel` is **56px**, and every tick was a **fixed 120px**
while `.track` is `flex:1` and fluid. Measured at 1440px: the track is **1142px for a 6-hour horizon =
190.3px/hour**, against an axis drawn at **120px/hour** — a **1.59× scale error**. The now-line at x=799
therefore sat under the axis's ~13:53 while the board called it 12:45, and **every bar on every board
artboard was positioned against an axis that did not describe it**. On a Gantt the axis *is* the reading
instrument; `screens.md` §3 grounds bar position in `dock_occupancy.window`, and there was no coordinate
system in which that position and that axis agreed. The axis now shares the track's exact box — the same
56px inset, n−1 fluid interval cells — verified **axis px/hour == track px/hour on all 11 boards**.

R19b is its own small lesson: the first fix gave the closing tick `flex:0 0 0; transform:translateX(-100%)`,
and **a percentage translate on a zero-width box is a 0px translate**, so `15:00` (and every board's closing
hour) rendered at width 0 and was never painted. A fixed 44px box with a matching negative margin ends
exactly on the track's right edge and still contributes zero width to the interval cells.

**R18 · The outage window shared a colour with the empty track it sat on.** `.bar.blocked`'s hatch was
`repeating-linear-gradient(45deg, neutral-300, neutral-300 4px, neutral-100 4px, neutral-100 8px)` — and
`.track`'s own background is `surface-hover`, which resolves to **`neutral-100`**. So half the hatch was
byte-identical to the empty track, and "blocked" differed from "free" only by a 1px border measured at
**1.36:1** light / **1.41:1** dark. A blocked dock is one of two facts on this board that stop a planner
committing capacity. Band moved to `surface-raised`, stripe darkened a step, border to 2px `text-tertiary`
— **4.34:1**, still a hatch, still never a promise-state token (`components.md` §4: a booking and an
unavailability must not share an encoding).

**R20 · The revalidating block had no visible boundary.** `.bar.revalidating`'s border measured **1.36:1**
against the track — on the one element the planner has just clicked and is actively waiting on.

**R13 · The two tabs were page links.** Diagnosed in §1. `role="tablist"` 0 → 14, `role="tab"` 0 → 28,
`aria-selected` 0 → 28, with roving `tabindex`.

**R14 · No landmarks at all.** `<main>` 0, `<nav>` 0, `role="region"` 0 file-wide. Unlike ops, this
surface's `accessibility.md` specifies no pane-jump model, so it needs `main` + `nav` rather than named
regions — but it needs those. Now 14 and 14, `<nav>` open/close balance verified 14/14.

**R15 · The status bar's connection state announced nothing.** `accessibility-behaviour.md` gives it
`polite` (`role="status"`) and says why that row exists: it was **added 2026-08-26 by a `web-design-guidelines`
audit** because the general rule routes ambient state to the status bar and leaves it silent, which would
have silently swallowed going offline. Unimplemented here. Now on all 14 status bars.

**R21 · 21 of 30 selection checkboxes had no accessible name.** A screen-reader user heard "checkbox,
checked" with no idea which request they had just put in the batch — on the surface whose throughput
feature *is* bulk selection. Named from each row's driver. The 3 remaining are inside `aria-busy="true"`
skeleton rows, which is the correct signal for "this has no content yet."

**R22 · `IN_PROGRESS` was specified and rendered nowhere.** `components.md` §3 maps it to the CONFIRMED
tokens **plus a `truck-loading` icon inside the bar** — distinguished by icon, not by a new hue, keeping
the hue budget where U10/U59/U85 fixed it. It appeared zero times in 29 bars. Added on D4 (the lane R12
restored), and added to the legend.

**R23 · `[ Review proposal (0) ]` was not Inactive.** `screens.md` §3: *"is Inactive (`components.md` §18)
with `(0)`."* It rendered as an ordinary pill button, so a planner could not tell a board with no pending
run from one with a run waiting. Now `pill-inactive` + `aria-disabled="true"` + a `title` that actually
explains the two ways a proposal arrives — §18's Inactive is deliberately **not** a faded Disabled: it stays
focusable and explains itself, which is precisely the difference that matters here.

**Fourteen contrast readings retracted, and all fourteen are correct as rendered.** Three are
`<button disabled>` — the Disabled tier used for the right reason (`Clear selection` with nothing selected,
`Send and pause` with no question typed, `Block dock` while the impact check is still running), explicitly
exempt from WCAG 1.4.3. Eleven are inside State 25's `<div class="ganttwrap dim" aria-hidden="true" inert>`
— the board the planner was picking on, after the request expired underneath them, correctly marked both
inert and hidden from assistive tech. Recorded because an automated contrast sweep will flag all fourteen
forever and someone will eventually "fix" the disabled buttons into looking enabled.

### 5.4 `web-design-guidelines` (U38 gate) — actually invoked

Skill invoked via the `Skill` tool; guidelines fetched fresh from
[vercel-labs/web-interface-guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md).
Applied to `mockup.html`. A static reference board legitimately does not carry app semantics; the findings
below are the ones that are not that excuse.

| Finding | Detail |
|---|---|
| Theme auto-switch (×3 blocks) | Fixed, §5.3-R1. |
| `<meta name="theme-color">` must match page background | Fixed, §5.3-R2. |
| No landmarks, no skip link | Landmarks fixed (§5.3-R14). Skip link is board-level, not per-artboard. |
| `<button>` for actions, `<a>` for navigation | Fixed for the tabs (§5.3-R13). The rail correctly stays `<a>` — it *is* navigation. |
| Form controls need `<label>` or `aria-label` | The block-dock form uses `role="combobox"`/`role="textbox" aria-readonly` on `<div>`s with `aria-labelledby` — **defensible for a static board and notably better than E5.2's empty-`<div>` composer**, but the build needs native controls. §6 Fork G. |
| Icon-only buttons need `aria-label` | ✅ all present. |
| Decorative icons need `aria-hidden` | ✅ 270 occurrences. |
| `Intl` not used | All dates, times and durations are hardcoded ("Tue 4 Aug" ×57, "13:00–14:15", "2:14"). `data-formatting.md` and U31 require `Intl` with `en-IN` from the start. **Reported, not fixed** — same position E5.1 and E5.2 took; this is a build requirement, not a board defect. |
| `translate="no"` on identifiers | **0 occurrences.** Shipment ids, dock ids and `scheduling_run_id` are exactly the tokens auto-translation garbles. Worth adding in the build. |
| `tabular-nums` for number columns | ✅ via `.mono`, applied to every interval, TTL, limit and id. |
| Placeholders end with `…` | ✅ `…` ×15, `...` ×0. |
| `overscroll-behavior: contain` in modals | ✅ present. |
| `touch-action`, `-webkit-tap-highlight-color` | ✅ both set on `body`. |
| Large lists need virtualisation | N/A — §7.3 caps this at 15–35 rows and `screens.md` says so. |
| No `user-scalable=no`, no blocked paste, no `transition: all` | ✅ clean. |

### 5.5 `checklist-design` (U34 gate) — actually invoked

Skill invoked via the `Skill` tool; `references/index.md` and three checklists read from the skill's own
bundled files. Audited against source **plus** rendered screenshots at DPR 2, so the "how it looks" items
are answered honestly rather than inferred.

`screens.md`'s own Checklist coverage section cites *Data Table* and *Timeline / Gantt View*. **The
block-dock form and the reject flow are modals and neither was ever derived against a modal checklist** —
so *Modal (Design system)* is audited here as a third, the same correction E5.2 made when it added *Single
Item Detail*.

#### Data Table — Web app

| | Item | Why |
|---|---|---|
| 🟡 | **Sortable columns** | Sort is deliberately fixed (§7.3's composite urgency + U19's freeze-while-focused), which is right — and the checklist's own tip is that the *current sort must always be visible*. Measured before the fix pass: **1 of 7 queue artboards** stated it ("Sort pinned · 3 new · press R to re-sort", State 9). Added to State 1 (§5.3-R17). Still absent on the row-variant sheets, which is defensible — they are component sheets, not screens. |
| ⚪ | **Column visibility and order** | Fixed 7-field row, deliberate (`components.md` §1's fixed-pixel-width rule). Not a table of user-arrangeable columns. |
| 🟢 | **Row selection and bulk actions** | Present and better than the item asks: "Select all eligible (N)" is the *primary* entry point (U63), the persistent bar shows the count ("12 selected"), and ineligible rows keep a **Disabled checkbox carrying the specific failing predicate as its tooltip** rather than a bare greyed control. |
| 🟡 | **Row actions on hover** | Deliberately inverted — five affordances render **always-visible, never hover-revealed** (`components.md` §1, caught in a prior audit). The checklist's tip says two to three max and warns "a row full of icons is hard to scan." Five is a real tension on a scan-speed surface; the stated defence is that `C`/`R`/`O`/`H`/`E` is the primary path and the icons are the mouse fallback. Worth knowing it's a choice, not an oversight. |
| 🟢 | **Search and filter** | Top-bar search plus a priority/ETA-confidence filter stated as toolbar text ("Filter: CRITICAL · 12 shown"). No chips, deliberately — 15–35 rows, not ops's cross-facility set. **But see §2.3's vocabulary collision.** |
| ⚪ | **Pagination** | 15–35 rows per §7.3's load arithmetic — worked live, not paged. Total count *is* shown ("35 pending"), which is the item's own tip. |
| 🔴 | **Frozen columns** | `screens.md`'s Checklist coverage claims *"present — first column fixed on horizontal scroll, `components.md` §6."* Measured: **`position:sticky` appears once in the file, on `<th>` for vertical stick. There is no `left:0` anywhere.** A claim the mockup does not deliver, on a 9-column table at a 1280px floor. §6 Fork D. |
| ⚪ | **Export action** | No tool in §7.5.1, and the product exports deliberately where warranted (§7.5.7's `export_audit_log`), so the absence reads as scoped rather than missed. |
| 🟢 | **Empty and loading states** | States 26–29, and better than the item asks: three *distinct* empty states, regional rather than global load failure, and skeletons that hold the real rows invisible so dimensions are exact (U78). |

#### Timeline / Gantt View — Web app

| | Item | Why |
|---|---|---|
| 🟢 | **Time axis** | Present, horizon-bound (§5.1's rolling 4 hours or `close_time`) rather than free-zoom, which `screens.md` reasons explicitly against U52's unverified Kibo zoom presets. **This item was where R19 lived** — an axis that is present is not automatically an axis that is correct. |
| 🟢 | **Task bars** | Coloured by state from `components.md` §3's mapping table, satisfying the tip ("a monochrome timeline is hard to parse"). `IN_PROGRESS` was missing and is now rendered (§5.3-R22). |
| ⚪ | **Dependencies** | Explicitly out of scope — nothing in `SOLUTION_DESIGN.md` models inter-shipment dependencies. Reasoned in `screens.md`, not silently dropped. |
| 🟢 | **Today indicator** | Present, server-reconciled per `components.md` §3's "server time is authoritative". **This item was where R11 lived** — it spanned one lane of six. |
| 🟢 | **Milestones** | Outage windows are the domain's analogue, from `dock_status_events`, visually distinct from every booking treatment. **This item was where R18 lived.** |
| 🟢 | **Row grouping** | Inherent — one row per dock. **This item was where R12 lived**: grouping by dock only works if every dock has a row. |
| ⚪ | **Drag to reschedule** | Explicitly out of scope under U25, and checked against it again for both U103 and U107 rather than assumed. Every board affordance is a click or a form. |

**Three of the seven Gantt items were nominally "present" and measurably broken.** That is the argument
for running the checklist against a *rendering* rather than against source, and it is worth stating because
`screens.md`'s own coverage note marked all three present in good faith.

#### Modal — Design system

Not previously derived against — added this pass.

| | Item | Why |
|---|---|---|
| 🟢 | **Title** | All 11 dialogs carry an `<h3>` wired with `aria-labelledby`; measured `role="dialog"` 11, `aria-modal` 11, **11/11** — better than E5.2's board managed. |
| 🟢 | **Actionable item** | Specific labels throughout — "Block dock", "Send and pause", never "OK"/"Continue". |
| 🟡 | **Close action** | Every modal has Cancel and `accessibility.md` binds `Escape`. **No `×` affordance on any of the 11.** Defensible on a keyboard-first desktop surface where Cancel is always visible; worth a deliberate decision rather than an inherited one. |
| ⚪ | **Responsiveness** | Desktop-only ≥1280px; State 30 handles below 1024. The 1024–1280 band has no artboard for modals either — same gap as §6 Fork D. |
| 🟢 | **Background change behind modal** | `.scrim` is a **flat dim, never a blur**, per `elevation-and-depth.md`'s explicit no-glassmorphism rule, and the underlying `.main` is `aria-hidden="true" inert`. |
| 🟢 | **Description** | Present where the decision needs it — the block-dock form's affected-appointment warning is the strongest instance, naming shipments by id rather than giving a bare count. |

---

## 6 · Eight forks for the owner

Surfaced, not resolved. Each carries options, a recommendation, and the honest trade-off.

**Fork A · The 30-second row costs three screenfuls on a spike, and nobody wrote that down.**
Measured (§2.1): the row renders at 59px against `compact`'s 36px, giving 12 rows per 1600×900 screen
against §7.3's 15–35 load. The reason is correct — two identity lines plus a two-line receipt, plus
`components.md` §1's rule that the displacement check never truncates.
*Options:* (a) record the trade explicitly in `components.md` §1 ("59px, three screenfuls at peak, in
exchange for never truncating the displacement check") and leave the design alone; (b) add a density
toggle so a planner can drop the carrier line during a spike — but `spacing-and-layout.md` already
considered and rejected a per-user density preference; (c) move the receipt to one line and accept
truncation on the *receipt* (never the displacement check).
*Recommendation:* **(a)**. The design is right; only the record is missing. But it should be a written
number, because "12 rows visible" is the kind of thing a later reviewer will otherwise rediscover as a
surprise during a spike test.

**Fork B · Two vocabularies both use CRITICAL/HIGH/NORMAL/LOW, on the same row.**
Diagnosed in §2.3. The shipment **priority** (the left-edge marker, and what `screens.md` says the filter
narrows on) and the **decision receipt's lead term** (`components.md` §4's condensed variant) share four
words. The rendered artboards show `Filter: CRITICAL · 12 shown` above rows whose receipts read HIGH,
NORMAL and LOW.
*Options:* (a) label the filter with its dimension — "Priority: CRITICAL" — cheapest, and leaves the
underlying collision in place for every other reader; (b) rename the receipt's lead term to a delay-band
vocabulary that shares no words with priority (`SEVERE`/`SIGNIFICANT`/`MINOR`/`NONE`), a `components.md` §4
change affecting the driver surface too; (c) drop the lead term from the *condensed* receipt entirely,
since the "70 min late" that follows it already carries the magnitude.
*Recommendation:* **(a) now, (c) considered separately.** (b) is the cleanest and the most expensive —
the receipt vocabulary is rendered to drivers as well, so it is not a planner-local rename.

**Fork C · The three empty queues need a server-side history check that no tool provides.**
State 26 renders three genuinely distinct empty states — "no pending requests" (caught up), "this facility
has no requests yet" (never had any), "no shipment matches 'RJ14'" (filtered to zero). The middle one is a
different fact from the first and **cannot be derived from `count === 0`** — U74's rule, correctly
implemented in the artboards. G1's missing queue read gives no has-ever-had-requests signal.
*Options:* (a) add the flag to `get_planner_queue`'s response when G1 is specified; (b) collapse the first
two into one empty state and lose the distinction; (c) derive it client-side from whether the facility has
any `appointments` rows at all — a second round-trip on every empty render.
*Recommendation:* **(a)**, and specify it *with* G1 rather than after, because retro-fitting a response
field is how the two states quietly become one.

**Fork D · Three things `screens.md` claims that the mockup does not deliver.**
Grouped because they are one review conversation:
1. **Frozen first column** — the Checklist coverage section says "present — first column fixed on
   horizontal scroll." Measured: no `position:sticky; left:0` anywhere (§5.5).
2. **The 1024–1280px reduced column set** — `spacing-and-layout.md` specifies it; there is no artboard,
   for the console or for its modals. State 30 covers only below-1024.
3. **The sort statement** on the row-variant sheets, now present on State 1 and State 9 only.
*Recommendation:* build 1 and design 2; 3 is arguably fine as-is. Raised together because all three are
"the doc asserts, the render does not," which is the class this whole pass exists to catch.

**Fork E · `color.md`'s TTL-urgency table contradicts `color.md`'s own contrast table.**
The TTL table (§"TTL urgency — the state hue warming toward danger") assigns **`amber-600`** to the 20–50%
band. `color.md`'s **own** contrast table, ~250 lines later, marks `amber-600` at **3.2:1** and *"✗ Fails
normal text — UI/large only."* The planner's TTL renders at **12px**. This is byte-for-byte the same
internal contradiction E5.2 found in the `escalation-sla-warning` row — **and that row was corrected on
2026-08-29 while this one was not**, because the correction was scoped to the token E5.2 had measured.
*Options:* (a) raise the TTL table's 20–50% band to `amber-700` for parity with the `escalation-sla-*`
correction already made; (b) leave it and mark TTL as a large-text/UI context, which it is not at 12px;
(c) add the one-line rule under the contrast table that a token assigned to *text* must clear 4.5:1 —
which is the rule that would have caught both instances at authoring time.
*Recommendation:* **(a) and (c) together.** (c) especially: this is the second time the same file has
disagreed with itself in the same way, and a rule is cheaper than a third audit.

**Fork F · The HELD bar border is 2.91:1 — 0.09 short, and the reason is contextual.**
Measured after inheriting `color.md`'s corrected `amber-600` (§5.2). The promise-state border palette was
tuned against *chip* backgrounds; a Gantt bar sits on a `surface-hover` track, a lighter-relative context
no chip occupies. Every other bar treatment clears 3:1.
*Options:* (a) darken the board's track from `surface-hover` to `surface-base` — changes no token, affects
only this surface, and lifts every bar's border slightly; (b) raise `state-held-border` to `amber-700` in
`color.md`, which changes the chip on three other surfaces to fix one; (c) add a board-scoped
`--dockBar-held-borderColor` under `tokens.md`'s component tier (U85) — the tier that exists for exactly
this case; (d) accept 2.91 on the grounds that the HELD bar is also **dashed** and carries its shipment id
as text, so the border is not the sole carrier.
*Recommendation:* **(c)**, with (d) as the honest fallback. Not fixed here because deviating from a
foundations token is precisely what the standing rule forbids, and the component tier is the sanctioned way
to deviate.

**Fork G · The block-dock form has no native form controls.**
Four fields rendered as `<div role="combobox">` / `<div role="textbox" aria-readonly>` with `tabindex="0"`
and `aria-labelledby`. This is genuinely careful for a static board — better than E5.2's empty-`<div>`
composer — but `flows-and-states.md` Flow 7's live affected-appointment fetch is driven by field changes,
and there is no control to fire one.
*Options:* (a) build with native `<select>` / `<input type="time">` / `<textarea>` and treat the artboards
as visual reference only; (b) update the artboards to native controls so the reference and the build agree;
(c) leave as-is.
*Recommendation:* **(a)**, and note it in `components.md` §6 so the next reader does not copy the `<div>`
pattern out of the mockup. Native `<input type="time">` also gets 24-hour behaviour and keyboard entry for
free, which `screens.md` §5 asks for explicitly.

**Fork H · The rail's second destination — carried forward from E5.2, not re-opened.**
`screens.md` §1 gives this surface two rail destinations (this console + Profile) and cites
`02-ops-exception-console/`. `iconography.md`'s Rail destinations table (added 2026-08-26, governed by
U101) enumerates **one** destination per role, and `spacing-and-layout.md` puts the user menu in the top
bar. The planner mockup renders both a top-bar account control and a rail Profile link. **E5.2 raised this
as its Fork E and it is still open.**
*Recommendation:* whatever is decided for ops applies here unchanged. Flagged only so that answering it for
one surface does not leave the other rendering the rejected pattern — which is exactly what would happen if
this file stayed silent.

**Resolved 2026-08-29: owner picked (a), drop the rail Profile item.** Applied here too, not just to ops —
all 14 rail Profile links removed from this surface's `mockup.html`; the top-bar account control is the
sole entry point. `.railitem`'s CSS is unaffected — still used by the single remaining "Dock command"
item. This decision now applies project-wide; E5.4/E5.5/E5.6's readiness passes (in progress) should not
re-raise it as a new fork if their mockups show the same pattern.

---

## 7 · Suggested order for E5.3

1. **The shell with real tab semantics** (§1) — `role="tablist"`/`tab`/`aria-selected` with roving
   `tabindex`, `Cmd/Ctrl+1` / `+2` bound, `main` and `nav` landmarks, `data-density="compact"` at the route
   root. Everything mounts inside it, and the tab shortcut is the first thing NVDA testing will hit
   (`accessibility.md`'s AT matrix).
2. **The block-dock group (States 16–18) first, not last.** It is the only group with a complete backend,
   it exercises the `Idempotency-Key` path end to end, and it produces the `CAPACITY_EVENT_CASCADE` that
   `02-ops-exception-console/` consumes — so it is also the first real cross-surface integration test
   available in M5.
3. **The negative paths — 23, 26, 27, 28, 29, 30.** Regional error boundaries, the three-way empty split,
   skeletons that hold real dimensions. Do not leave these to the end of the sprint; on this surface they
   are the surface, not decoration. 26 needs Fork C answered first.
4. **The queue shell and row component** — buildable against a fixture while G1 is specified, and it is the
   piece worth getting right before any of it is wired. Ops and planner share this component (U23);
   **E5.2's Fork C (the queue row's ARIA role) is still open and must be answered in
   `00-foundations/components.md` §19, not here** — deciding it inside one surface is how the two diverge.
   Note the two surfaces have *already* diverged in shape: ops renders 4-line `.qrow` cards in a 340px
   pane, planner renders a 9-column `<table>`. Worth confirming U23 still means one component.
5. **Reject (12, 13)** — the highest-confidence write path that actually exists, once G7 decides whether
   the enum is a contract or a courtesy.
6. **The board (2, 22, 28)** — gated on **G8**, the `dock_occupancy.state` migration. This is the largest
   single unblock on the surface: it releases the board, the picker, and D2's HELD state (issue #53) at
   once. Build the render pass as one shared state→token function per `components.md` §3, so a new state
   later gets a mapping-table row rather than a bespoke branch.
7. **Confirm and its refusals (1, 6, 8)** — gated on G2 and G3. `snapshot_hash` first; the refusal taxonomy
   is meaningless without it.
8. **Counter-offer (3, 24, 25)** — gated on G4 and G8.
9. **Bulk confirm (9, 10, 11)** — gated on G6. The server-side predicate re-check at press time is the
   whole point; do not ship a client-side approximation as a stopgap.
10. **Hold (7, 14, 15)** — gated on **G5, which needs a migration**, not a tool. Lowest priority by
    dependency depth, not by importance.
11. **Sequencer proposal (19, 20, 21)** — gated on issue **#49**.
12. `Intl` with `en-IN` for every date, time and duration from the first component, not retrofitted
    (§5.4), and `translate="no"` on every shipment/dock/run identifier at the same time.

**Feature flags.** Name each for its dependency, not its feature: `planner_queue_live_enabled` (G1/G10),
`planner_confirm_enabled` (G2/G3), `planner_counter_offer_enabled` (G4), `planner_hold_enabled` (G5),
`planner_bulk_confirm_enabled` (G6), `dock_board_enabled` (G8), `sequencer_proposal_enabled` (#49). All
default off, each with the issue number in the comment, so it is obvious what removes it rather than
obvious what it hides.

---

## 8 · Constitution Check

| Check | Result |
|---|---|
| Contradicts a locked decision U1–U120? | **No.** U10, U19, U23, U25, U29, U31, U34, U38, U40, U41, U43, U46, U52, U59, U63, U65, U67, U69, U70, U74, U76, U78, U79, U83, U85, U87, U93, U95, U101, U102, U103, U104, U105, U106, U107 are each cited where they constrain a value. **One live U69 violation found and fixed** (§5.3-R1) — fourth recurrence across four mockups. U102's two-tab model is implemented as tabs for the first time (§5.3-R13), matching `00-foundations/components.md`'s own rail-vs-tab table. |
| Amends a foundations or surface file? | **`mockup.html` only** — nineteen fixes across ~60 sites, each with a dated inline comment naming the measurement that motivated it. **No foundations or surface `.md` file was edited.** The `color.md` TTL-table correction this pass identified is §6 Fork E, because it affects every surface. |
| Invents product behaviour? | **No.** All nine §7.5.1 tools and all three §7.5.3 tools were read off `planner_service.py`, `planner.py`, `scheduling.py`, `operations.py`, `allocation.py` and `expiry.py`; the ten gaps are read off absence in source and off the shipped migration, not inferred from design docs. `hold_for_information`'s impossibility is quoted from the codebase's own comment rather than restated. |
| Invents data? | **No.** Where a value has no source (the 1024–1280 column set, the frozen-column claim, the queue row's ARIA role) it is named as absent. The one artboard element added — D4's `IN_PROGRESS` bar — renders a state `components.md` §3 already specifies in full, and its blocked-ness is filed as G8 in the same pass. |
| React 19 frontend (ADR 012)? | Yes — unchanged from E5.0/E5.1/E5.2. |
| Stays inside the named scope? | Yes. The brief named all of `03-planner-dock-board/`, five `00-foundations/` files, and both prior specs as templates. `backend/app/**` and `supabase/migrations/**` were read because the brief's item 4 requires confirming M3's tool catalog against what shipped — including, in its own words, "whether anything here assumes a tool or field beyond what Sprint 3's `backend/app/scheduling/` and M3's tool catalog actually provide" — and that cannot be asserted from design docs. The tracker was read per `AGENTS.md`'s startup rule. |
| Skills actually invoked, not cited? | **Yes, both, via the `Skill` tool.** `web-design-guidelines` (§5.4, guidelines fetched fresh from source) and `checklist-design` (§5.5 — `references/index.md` plus three checklists read from the skill's own bundled files, audited item-by-item in each checklist's own order, kept separate, no blending). **A third checklist — *Modal (Design system)* — was added because the surface's own U34 derivation had missed it**, the same correction E5.2 made with *Single Item Detail*. `dataviz` **considered and not run**: it is scoped to charts, stat tiles and sparklines, and while the dock board is time-axis-shaped, it is an occupancy schedule with no encoded quantity, no legend of series, and no axis of measure — the `dataviz` colour formula and mark specs have nothing to say about it. Stated plainly rather than run for the sake of the checkbox. `design` canvas not run — this is a spec pass over an existing approved mockup, not a new screen. |
| Rendering verified, not eyeballed? | **Yes.** Headless Chromium via Playwright 1.62.1: computed styles and `getBoundingClientRect` across all 30 artboards; contrast computed from rendered `rgb()` against each element's **effective** background including inherited `opacity`; full ARIA census over the live DOM; **Gantt geometry measured per board** (axis px/hour vs track px/hour, now-line height vs lane-stack height, tick clipping); effective target area including transparent `::after` hit overlays; forced `prefers-color-scheme` both directions; opt-in `data-theme` both directions; four viewport widths; clipped screenshots at DPR 2 before and after. Nineteen defects found; **fourteen readings retracted** as correctly-Disabled or correctly-inert; **one regression introduced by this pass and caught by re-measurement** (§5.3-R10b); **two fixes caught wrong by re-measurement and redone** (R9b — opacity's stacking context; R11c — a "fix" that measured clean only because the element had become invisible). |
| Genuine forks surfaced, not silently decided? | **Yes, eight** (§6), each with options, a recommendation and the honest trade-off. **Zero resolved silently.** Fork F in particular was deliberately *not* patched: deviating one step further from `color.md`'s corrected token to win 0.09 is exactly what the standing rule forbids, and `tokens.md`'s component tier exists for that case. Fork H is carried forward from E5.2 rather than answered differently here. |
| Fixes verified by measurement, not by editing and assuming? | **Yes — every one.** All probes re-run after the edits, and the probe itself was corrected mid-pass when it was found to understate target size by measuring border boxes rather than effective targets. The Gantt assertion (axis scale == track scale on all 11 boards; now-line height == lane-stack height on all 7 boards that carry one) is what proves R19 and R11 rather than a screenshot that looks better. |
| Writeback (`CHANGELOG.md`, `wiki/`)? | **Not required** — `AGENTS.md`'s exemption covers everything under `docs/New-Solution-New-Design/`. |
| Empirical numbers tagged? | Yes. All §2, §5.0 and §5.3 figures are *measured*; §0.1's tool table is *source-verified* with file and line; §5.1's ten gaps are *verified by absence in source* (grep across `backend/app/`) or by the shipped migration's own DDL; §2.1's rows-per-screen is *computed from measured chrome* and labelled as such; §6's recommendations are *judgement* and say so. |
