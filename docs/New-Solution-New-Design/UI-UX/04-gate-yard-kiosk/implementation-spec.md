# Implementation spec — gate/yard kiosk (E5.4)

> **M5 / E5.4 (issue #39, OPEN).** The buildable translation of `04-gate-yard-kiosk/`'s locked design, on
> top of the design system E5.0 shipped and the tool catalog M3 actually closed. **This file defines no new
> design decisions.** Every value is copied from a foundations file, a surface file, `mockup.html`, or
> verified source in `backend/`, with its source named. Where a value has no source, or two sources
> disagree, it is in §6 as a decision the owner has to make — not resolved here.
>
> **Continuation note.** A prior pass on this exact issue was cut off mid-work by an account-wide Opus spend
> limit; its last line was *"Now re-measuring everything after the fixes."* That pass's fixes (R1–R8, all
> carrying dated `E5.4 fix 2026-08-29` comments in `mockup.html`) were **not** trusted on the strength of
> their comments — every one is independently re-measured below, using a fresh headless-Chromium session
> (Playwright 1.62, Chromium 140 — installed this pass; none was present at session start), not inherited
> from the prior pass's own claims. This pass runs on **Claude Sonnet 5**, specifically to avoid the spend
> limit that stopped the prior (Opus) attempt; noted per the model-attribution rule, not as a quality claim.
>
> **Read for this pass, and only these:** all six `04-gate-yard-kiosk/` files (`screens.md`,
> `flows-and-states.md`, `edge-cases.md`, `components.md`, `accessibility.md`, `stitch-prompts.md`) plus
> `mockup.html`; `00-foundations/` — `components.md`, `accessibility-behaviour.md`, `color.md`,
> `typography.md`, `spacing-and-layout.md`, `iconography.md`; `SOLUTION_DESIGN.md` §7.5.2; `02-*` and
> `03-*`'s `implementation-spec.md` (as templates and as the source of the shared-fix-pattern lessons this
> surface has to check against); and the live `backend/app/services/gate_yard_service.py`,
> `backend/app/api/v1/routers/gate.py`, `backend/app/services/search_service.py`,
> `backend/app/services/driver_reads.py`, `backend/app/assistant/tools.py`,
> `backend/app/core/execution_context.py`, and `supabase/migrations/20260805201923_setuhaul_baseline.sql`.
>
> **Status: MOSTLY BUILD-READY ON THE WRITE SIDE, GATED ON ONE READ TOOL. 1 of 22 screens ships clean now;
> 2 more are buildable behind one open fork; 19 are transitively blocked by the single missing tool that is
> the only way to reach any of them — fifteen of those nineteen have their own write logic already fully
> built.** Zero rendering
> defects found this pass (all eight defects the prior pass found and fixed are independently re-verified
> correct below — including one that the prior pass's own fix had silently regressed and then re-caught).
> **Two backend gaps escalated, in the same "listed job with no tool" shape §7.5.5, `block_dock`, §7.5.6 and
> §7.5.7 were all found in** — but the shape here is the inverse of E5.2/E5.3: **the five *write* tools are
> completely and correctly shipped; the *read* tool that reaches them is the one that was never scoped.**
>
> **This is the narrowest backend gap of the three surfaces audited so far** — E5.2 had six gaps across
> sixteen screens, E5.3 had ten gaps across thirty states, this surface has effectively **one** gap (plus one
> data-integrity omission) across twenty-two screens, and the gap is a single, well-scoped tool addition, not
> a missing subsystem.

**Owner decisions still open: seven (§6).** Nothing in §5's fix-verification pass required one; everything
in §6 does.

---

## 0 · Starting point — what exists, verified not assumed

### 0.1 What M3 actually shipped for this surface

E5.4's issue lists **M3 as a blocker** and M3 is closed. `issue #39`'s own body cites a "standing rule" —
*"a value with no foundations source is a bug in the mockup, not a new decision"* — but says nothing about
the tool catalog itself, so it is checked here the same way E5.2 and E5.3 checked theirs: tool-by-tool
against `SOLUTION_DESIGN.md` §7.5.2, read off `backend/app/` source, not taken from the milestone's closed
state or the sub-issue's own title.

| §7.5.2 tool | Shipped? | Source |
|---|---|---|
| `record_gate_in` | ✅ **Fully shipped, and well** | `gate_yard_service.py:345`, `gate.py:87`. Returns `GATE_IN_RECORDED` + computed `arrival_state` · `ALREADY_CHECKED_IN` (states the existing timestamp, doesn't just refuse) · `NO_ACTIVE_APPOINTMENT`. Idempotency-keyed — the only one of the five that the catalog names one for, and the router 400s without it (`gate.py:78-83`) |
| `update_queue_state` | ✅ **Fully shipped** | `gate_yard_service.py:489`, `gate.py:108`. `QUEUE_UPDATED` · `INVALID_TRANSITION` (names the current state so the kiosk can re-render rather than retry blindly). Server-enforced `QUEUE_TRANSITIONS` table, calibrated to `screens.md` §3's own state→action mapping and to `edge-cases.md` #4's requirement that `CALLED_TO_DOCK → WAITING_*` stay reachable |
| `record_dock_in` | ✅ **Fully shipped** | `gate_yard_service.py:593`, `gate.py:131`. `DOCK_IN_RECORDED` · `DOCK_MISMATCH` (deviation, not error — arrival recorded against the actual dock) · `DOCK_OCCUPIED` (nothing recorded, truck returned to `WAITING_DOCK_UNAVAILABLE`, matching `edge-cases.md` #4 exactly) |
| `record_unload_start_end` | ✅ **Fully shipped** | `gate_yard_service.py:704`, `gate.py:153`. `RECORDED` on both phases; `overrun_min` computed and signed (not clamped) on `END` |
| `record_gate_out` | ✅ **Fully shipped** | `gate_yard_service.py:805`, `gate.py:175`. `COMPLETED` + `dwell_min`, verified against seeded `CHK1001` (75 min) and reproduced across all 397 live gated-out rows per the service's own comment. Also returns `ALREADY_GATED_OUT` for a re-search of a terminal truck — `edge-cases.md` #6's exact scenario, though the code is never named in `edge-cases.md` or `stitch-prompts.md` itself (a documentation-completeness gap, not a build one — noted in §5.1) |

**Five of five.** This is the opposite finding from every prior surface in this phase: E3.6's own issue
(`#30`, closed) scoped gate/yard to *exactly* these five writes, and all five are live, correctly
state-machine-guarded, and match their design-doc outcome codes verbatim. The row-level `FOR UPDATE` lock
in `_locked_checkin` (`gate_yard_service.py:220-226`) is what makes `edge-cases.md` #5 (two devices racing
the same truck) resolve as a clean `INVALID_TRANSITION` rather than a lost update — read committed, second
transaction blocks then re-reads the winner's row, exactly as the edge case describes.

**And one tool that was never scoped at all — see §2.** `screens.md` §1's own header claims **"Six §7.5.2
tools"**; `SOLUTION_DESIGN.md` §7.5.2's table lists five, `gate_yard_service.py`'s docstring cites
`FR-GATE-004 .. FR-GATE-008` (five sequential codes, no gap for a sixth), and issue `#30`'s sub-issue list
scopes gate/yard to *"all five write tools"* by name. The miscount in `screens.md`'s header is small on its
own, but it is suggestive: the design's own authoring assumed a sixth tool belonged here, and it was never
actually specified anywhere. That sixth tool is the subject of §2.

### 0.2 The frontend after E5.0–E5.3

| Fact | Consequence for E5.4 |
|---|---|
| `theme.css` and `color.md` carry every promise-state and feedback token this surface references | Nothing new needed for colour, **except** the one row `color.md` never swept — §5.2. |
| This surface is the only one at `spacious` density (`spacing-and-layout.md`'s density table) | Confirmed in the rendered file: `--row-h:64px`, `--tap-min:56px`, `--btn-h:56px` all present and used, not aspirational tokens sitting unused. |
| `E5.2` and `E5.3` both found `color.md`'s promise-state/SLA tables self-contradicting their own contrast section, twice | Checked here too (§5.2) — a **third** instance of the same failure shape was found, in a table neither prior pass touched. |
| No streaming/live-update transport exists anywhere in the product except the driver `/chat` SSE stream (E5.2's G6, E5.3's G10) | **Does not gate this surface.** Every screen here is a single request/response per officer action; nothing on this surface waits on another actor's write the way the ops queue or the dock board does. The one auto-resolving screen (prompt 22, `INVALID_TRANSITION`) re-fetches once, synchronously, not via a push channel. |
| Issue **#52** is OPEN — `/auth/me` returns one `role_name`, not `grants[]` | **Does not gate this surface either.** There is no facility switcher, no cross-facility scope union to resolve — the device's facility is fixed, per `screens.md` §1. |

---

## 1 · The two device contexts, measured

`screens.md`'s header and `stitch-prompts.md`'s own framing both claim two device contexts sharing one
interaction model (U108). Measured directly rather than taken on the file's word:

| Measure | Value | Source |
|---|---|---|
| Total artboards | **35** | Rendered DOM census, `.frame` count |
| Gate-booth frames | **13**, all `1280×800` | `.frame.gate` |
| Yard-tablet frames | **22**, all `800×1280` | `.frame.yard` |
| Screen groups (`stitch-prompts.md` order) | **22** | Header claim, matches |

**Both device contexts render at true device size with no scaling** — `.frame.gate{width:1280px;
height:800px}` / `.frame.yard{width:800px; height:1280px}` are literal pixel values, not viewport-relative,
so every token measured against them (tap target, contrast, spacing) is the real shipped value. Confirmed
distinct: gate-booth is landscape and covers only gate-in/gate-out (`screens.md` §3's own note — "the states
in between never surface on that device in practice"); yard-tablet is portrait and covers the five
in-between states plus the shared search/outcome screens. No screen renders on the wrong device context.

**No app shell anywhere** — verified, not assumed: `document.querySelector('nav, .rail, [aria-label="Profile"]')`
returns null across the whole file. This matches `stitch-prompts.md`'s explicit claim ("No icon rail, no top
bar, no status bar, no facility switcher") and means the **rail-Profile/top-bar-account duplication the
coordinator settled project-wide today does not apply here** — there is no rail and no top-bar account
control to deduplicate. Checked directly rather than assumed from the surface's own framing.

**Tap targets, all 88 measured interactive elements** (`.btn`, `.row`, `.link-ctl`, `.field`), against the
56px `spacious` floor `spacing-and-layout.md` sets and `accessibility.md` reasons from gloves specifically:

| Floor | Under | Method |
|---|---:|---|
| 56×56px (`spacious`, this surface's own floor) | **0 / 88** | `getBoundingClientRect()`, every artboard |
| 44×44px (WCAG SC 2.5.5 AAA, the product's general floor) | **0 / 88** | Same |
| 24×24px (WCAG SC 2.5.8 AA, the legal minimum) | **0 / 88** | Same |

**Zero targets fail even the loosest of the three floors.** This is the cleanest result of any surface
audited in this phase — E5.3 measured 151 of 304 under `compact`'s 32px floor before its fix pass; this
surface's prior pass evidently already found and fixed whatever equivalent existed here, and the `link-ctl`
spacing rule (`components.md` §1 — "End shift... sits >=32px from any other interactive element") measures
**520–1000px** of clearance in the shift bar on every artboard that carries both a back-link and End shift —
nowhere close to the 32px floor being tested, so a gloved mis-tap genuinely cannot bridge the two.

---

## 2 · Search — the one tool this surface's entry point depends on, and does not have

`screens.md` §2 and `flows-and-states.md` Flow 1: typed entry (shipment ID or plate number, U109), routing
to Flow 2 on a match. This is **the highest-frequency interaction on the surface** — `components.md` §2
says the search field "is used far more than any other single control" — and it is the *only* way to reach
any of the eighteen screens between it and an outcome. Checked the same way E5.2 found G1 and E5.3 found
G1/G4/G5/G6/G8: read the actual backend, not the design docs' framing of what should exist.

**No tool matches Flow 1's contract.** Three separate pieces exist, and none of them is it:

**a) `gate.py` has zero read endpoints.** The whole file was read start to finish (§0.1's table) — five
`POST` routes, no `GET` route of any kind. There is no `/gate/search`, no `/gate/shipments/{id}`, nothing.

**b) `GET /api/v1/search` (`search_service.search_records`, §7.5.8) is reachable by this surface's roles but
does not do what the field needs.** `gate.py`'s own role gate is `WAREHOUSE_PLANNER`, `FACILITY_MANAGER`,
`ADMIN` — all three pass `search_records`'s `ctx.is_operator or ctx.is_admin` check
(`execution_context.py:51-59`), so the endpoint is *reachable*. But:
  - `_search_shipments` (`search_service.py:48-82`) matches against `shipment_id`, `order_reference`, and
    `customer_name` only. **It never queries `vehicles.registration_number`** — the schema's actual plate
    field (`20260805201923_setuhaul_baseline.sql:97`, `shipments.vehicle_id → vehicles.registration_number`)
    — so a plate-number search, which `screens.md` §2 and every `stitch-prompts.md` search artboard treat as
    an equally-valid input, has **no matching column anywhere in the query.**
  - The response shape carries `shipment_id`, `order_reference`, `current_status`, `facility_id`, `score` —
    none of `queue_state`, `arrival_state`, the appointment interval, the dock, or the carrier name that
    `components.md` §3's truck-identity card requires. A second call would be needed even if the first one
    matched.

**c) The one function that *does* return the right shape is unreachable.** `driver_reads.get_gate_and_queue_status`
(`driver_reads.py:294-329`) joins `facility_checkins` to `facilities` and returns exactly
`queue_state`/`arrival_state`/the check-in timestamps — the shape Flow 2 needs. `gate_yard_service.py`'s own
docstring names it as the gate/yard catalog's sole pre-existing capability. But:
  - It is **not wired to any router** — grepped across `backend/app/api/`, zero matches. Calling it from a
    kiosk is not possible today at any URL.
  - It is **not registered as an agent tool** either — grepped `assistant/tools.py`, zero matches. It is
    dead code, reachable from nothing.
  - Even if wired, it is scoped to `ctx.is_driver` matching the caller's own `driver_id` (via
    `get_driver_operational_context`) — the wrong role and the wrong scope entirely for an officer looking
    up *any* truck at the gate, not their own.

**Net effect: an officer can type a shipment ID or a plate number into this surface's single most-used
field, and there is no tool anywhere in the product that can answer either query in the shape the truck-
identity card needs.** This is not a partial gap with a workaround — it is the literal entry point to every
other screen on the surface. Gates **every screen from 3 through 22** (§3's table), transitively — of those
twenty screens, three (3, 4, 5) *are* the missing search flow itself, one (12) calls no tool at all, and the
remaining **fifteen have their own write action already fully built and correct**, waiting only on a way to
be reached.

**This is the same gap class §7.5.5, `block_dock`, §7.5.6 and §7.5.7 were all found in** — a listed job with
no tool, found by checking source rather than trusting a closed milestone — but it inverts the usual
severity shape: everywhere else in this phase, the *writes* were missing and the reads existed. Here the
five writes are the best-built tool set audited in this whole phase, and the one *read* that reaches them
was never scoped. **G1**, carried to §5.1 and §6 Fork E.

---

## 3 · The 22 screens → build readiness

22 screen groups / 35 artboards in `mockup.html`, in `stitch-prompts.md` order. Copy is authoritative there
at the prompt number given.

**Legend:** 🟢 buildable and shippable today · 🟡 buildable, one open fork · 🔴 unreachable without G1 (own
write logic is fully built and verified — see the "own tool" column).

| # | Screen | Own tool | Build |
|---|---|---|:--:|
| 1 | Shift start — gate-booth kiosk | N/A — local device state (`edge-cases.md` #7) | 🟡 Fork B |
| 2 | Shift start — yard tablet | N/A — local device state | 🟡 Fork B |
| 3 | Search — idle / in-flight | **G1** | 🔴 |
| 4 | Search — no match | **G1** | 🔴 |
| 5 | Search — multiple matches | **G1** | 🔴 |
| 6 | Truck found — `NOT_QUEUED` → Gate in | `record_gate_in` ✅ | 🔴 (reachability only) |
| 7 | Truck found — `WAITING_EARLY`/`WAITING_LATE` → Call to dock | `update_queue_state` ✅ | 🔴 (reachability only) |
| 8 | Truck found — `WAITING_DOCK_UNAVAILABLE` → Call to dock, retried | `update_queue_state` ✅ | 🔴 (reachability only) |
| 9 | Truck found — `CALLED_TO_DOCK` → Dock in | `record_dock_in` ✅ | 🔴 (reachability only) |
| 10 | Truck found — `IN_DOCK` → Start/End unload | `record_unload_start_end` ✅ | 🔴 (reachability only) |
| 11 | Truck found — `COMPLETED` → Gate out | `record_gate_out` ✅ | 🔴 (reachability only) |
| 12 | Truck found — terminal, no action | N/A — renders the last-known record | 🔴 (reachability only) |
| 13 | Primary action — component state sheet | N/A — static component reference | 🟢 |
| 14 | Outcome — Gate-in recorded | `record_gate_in` ✅ | 🔴 (reachability only) |
| 15 | Outcome — brief success family (queue/dock-in/unload) | ✅ (three tools) | 🔴 (reachability only) |
| 16 | Outcome — Gate-out recorded, dwell | `record_gate_out` ✅ | 🔴 (reachability only) |
| 17 | Outcome — `DOCK_MISMATCH` | `record_dock_in` ✅ | 🔴 (reachability only) |
| 18 | Outcome — unload overrun | `record_unload_start_end` ✅ | 🔴 (reachability only) |
| 19 | Outcome — `ALREADY_CHECKED_IN` | `record_gate_in` ✅ | 🔴 (reachability only) |
| 20 | Outcome — `NO_ACTIVE_APPOINTMENT` | `record_gate_in` ✅ | 🔴 (reachability only) |
| 21 | Outcome — `DOCK_OCCUPIED` | `record_dock_in` ✅ | 🔴 (reachability only) |
| 22 | Outcome — `INVALID_TRANSITION`, refreshing | `update_queue_state` ✅ | 🔴 (reachability only) |

### Tally

**🟢 1 · 🟡 2 · 🔴 19 — all 19 are 🔴 for exactly one reason (G1), and fifteen of them have their own write
logic already fully built and verified in §0.1** (the remaining four: screens 3–5 are the missing search
flow itself, and screen 12 needs no tool call at all). This is worth stating plainly because it changes what
"19 of 22 blocked" means in practice: unlike E5.2 (six independent gaps, one screen group each) or E5.3 (ten
gaps distributed across almost every group), **this surface unblocks in one motion** — the moment a
`search_gate_yard_truck`-shaped tool exists, screens 3–22 all become buildable, and for fifteen of those
twenty the tool they call is one that already works correctly today. Stated as a fact about the *shape* of
the gap, not a claim that it's a small amount of work — a search tool with a plate-number match and a
truck-identity join is real backend work, just narrowly scoped work.

**Screen 13 is the one clean pass and is worth calling out.** It is a static component-state sheet (default
/ pressed / submitting / Inactive), not a live screen, so it depends on nothing beyond the design system,
and it is where `components.md` §18's Inactive tier (offline/connectivity) is correctly, distinctly
implemented — full contrast, `aria-disabled` absent, no fade — see §5.1's note on why this matters against
Fork B.

---

## 4 · What E5.4 adds to the design system

**Nothing.** Every token this surface uses is already in `theme.css`/`color.md` — the promise-state family
is not referenced anywhere on this surface at all (there is no dock board, no option card; U110's one-button
pattern has no promise to render), and the feedback triad, surfaces, text and border ramps are consumed
as-is. `data-density="spacious"` is set once via the `:root` custom properties (`--row-h`, `--tap-min`,
`--btn-h`, etc.), never per component. One correction is owed **to** the design system rather than added by
it — `color.md`'s `feedback-warning-border` row, §5.2, §6 Fork A.

---

## 5 · Readiness call

**Verdict: 1 of 22 screens ships clean now. 2 more are buildable behind one open fork. 19 are unreachable
without G1 — but fifteen of those 19 have fully-built, verified write logic waiting on exactly one tool.**
Zero
rendering defects found this pass. All eight of the prior (interrupted) pass's fixes are independently
re-verified correct below, using a fresh render rather than trusting the fix comments. Two backend gaps and
one documentation-precision issue escalated.

### 5.0 Fix-verification scoreboard — every prior claim re-measured, none trusted

Method: headless Chromium (Playwright 1.62.1, Chromium 140.0.7339.16 — installed fresh this session; not
present when the session started). Computed styles and box model across all 35 artboards; contrast computed
from **rendered** `rgb()` values against each element's own resolved background (not its parent's, and not
assumed — an earlier version of this pass's own probe had that bug and it produced 33 false positives before
being caught and fixed, mirroring E5.3's R9/R9b "the fix didn't work, re-measurement caught it" pattern one
level up, in the *measurement tool* rather than the mockup); ARIA/role census over the live DOM; regex
census for emoji, ellipsis, en-dash usage, and text below the 14px floor.

| | Before (prior pass's claim) | After (this pass's independent re-measurement) |
|---|---|---|
| `feedback-warning-border` contrast (R1) | 2.05–2.07:1 (broken), fixed to amber-600 | **Independently recomputed from first principles (WCAG relative-luminance formula, not the rendered DOM): amber-500 on white 2.15:1, on `#F8FAFC` 2.05:1; amber-600 on the same pair 3.19:1 / 3.04:1. The prior pass's numbers are exactly reproduced.** |
| `color-scheme` declaration (R7) | Absent → added `light` | **Present, verified**: `html{color-scheme:light}` at the single declaration site |
| `touch-action`/`tap-highlight` (R6, partial) | Absent → added to `.btn,.row,.link-ctl,.field` | **Present, verified** on all four selectors |
| Inputs: `autocomplete`/`spellcheck`/`autocapitalize`/`enterkeyhint` (R6) | Absent → added to all 10 inputs | **Present on all 10**, verified per-input (`name`, `autocomplete="off"`, `spellcheck="false"` on every one; `autocapitalize="characters"` + `autocorrect="off"` + `enterkeyhint="search"` on the 4 truck-lookup fields; `enterkeyhint="go"` on the 6 officer-name fields) |
| Disambiguation-list card anchoring (R3) | Bottom-anchored (129px card top) → top-anchored | **Re-measured on the live artboard: cardTop 667px**, inside the claimed 490–759px norm every other truck-found/outcome yard screen uses (verified across all 22 yard frames — see below) |
| `DOCK_OCCUPIED` politeness (R2) | `role="status"` → `role="alert"` | **Verified `role="alert"`**, consistent with the other three "nothing was recorded" outcomes (`NO_ACTIVE_APPOINTMENT`, `INVALID_TRANSITION`) and distinct from the five "something genuinely happened" outcomes, which are all `role="status"` |
| `ON_TIME` enum rendering (R5) | Raw enum in a mono fact line → sentence case | **Verified**: `<span class="mono">SHP1015</span> · <span class="mono">18:04</span> · On time` — no bare `ON_TIME` anywhere in the file |
| `text-wrap:balance` (R8) | Absent → added to `.title`, `.block .headline` | **Present on both selectors**, verified |

**Card-top position census, all 22 yard frames** (the check R3's fix claimed but the diagnosis never
tabulated): shift-start artboards cluster at **289px** (upper-quarter thumb-arc placement, U108); the
component-state sheet has no `.card` at all (buttons render directly, as designed); the one buttonless
auto-resolving artboard (prompt 22's first half) sits at **580px** with no button, matching its own copy
("No button on this artboard — the screen resolves on its own"); every other truck-found/outcome screen —
including the previously-misplaced disambiguation list — falls inside **490–759px**. No outlier remains.

**No regressions found:** 35 artboards before and after; **0** text nodes below the 14px floor; **0** emoji
(regex swept the full rendered `innerText`); ellipsis used correctly (2× `…`, 0× `...`); all 17 rendered
time ranges use an en dash, 0 use a hyphen; all four `outline:none` occurrences carry a `box-shadow`
`:focus-visible` replacement; `reduced-motion` and `forced-colors` media queries both present and,
independently confirmed, **zero actual `@media (prefers-color-scheme)` rules exist anywhere in the file** —
the string only appears once, inside a CSS *comment* explaining why there are none. This is the cleanest
result on U69 of any of the four surfaces audited in this phase so far; the driver, ops and planner boards
all needed an R1-class fix for a live dark-mode auto-switch bug, and this surface never had one to begin
with, per the prior pass's own (now independently confirmed) finding.

### 5.1 Two backend gaps and one precision issue — the first two are not UI decisions

**G1 · 🔴 No tool matches Flow 1's search contract.** Diagnosed in full in §2. Gates screens 3–22
transitively. **This is the escalation; §6 Fork E is the resolution-path fork.**

**G2 · 🔴 `officer_name` — the entire subject of U111 — is never transmitted to, or persisted by, any of the
five write tools.** Checked directly against every Pydantic body model in `gate.py`
(`GateInBody`/`QueueStateBody`/`DockInBody`/`UnloadPhaseBody`/`GateOutBody`) and against `_audit`'s own
signature in `gate_yard_service.py:282-320`: **none accepts an officer name, and `_audit` writes only
`ctx.user_id`** — the identity of whatever Supabase Auth session the shared kiosk device itself is logged in
under (necessarily one of `WAREHOUSE_PLANNER`/`FACILITY_MANAGER`/`ADMIN`, per `gate.py`'s own role gate and
docstring — a real, owner-confirmed 2026-08-24 mapping decision, not guessed), not the individual officer
who typed their name at shift start. This directly contradicts three separate claims in this surface's own
design:
  - `components.md` §1: *"Every event this session writes... carries this officer's identity as an
    attribute of the write, not as a re-asked credential."* There is no argument on any tool for it to be an
    attribute of.
  - `edge-cases.md` #8: *"correcting historical attribution... is an admin-console concern."* There is
    nothing to correct — no individual officer's name was ever recorded against any event, so there is no
    per-officer history for a future admin tool to fix.
  - U111 itself (README decisions log): *"Shared kiosk session, officer identity set once per shift, stamped
    on every event that shift."* The stamping never happens.

The officer-name field is genuinely captured and displayed in the UI (the shift bar reads "Shift: Ramesh
K." on every subsequent screen — confirmed, this part works as a **local, session-scoped display value**),
but it is never sent anywhere. Every event this device writes this shift, and every event any other officer
who ever uses this device writes on any other shift, is indistinguishable in the audit trail — all
attributed to the one shared device credential. **Not gating any screen's build-readiness marker** — the UI
renders correctly regardless — but it is a silent, real product-correctness gap: the thing U111 was written
to guarantee does not exist server-side. §6 Fork F.

**G3 · 🟡 The "every action carries an idempotency key" claim is imprecise, though the underlying behaviour
is safe.** `components.md` §4 and `stitch-prompts.md` prompt 13 both assert idempotency-key protection
"same as every capacity-or-record-affecting action elsewhere in the product" / "every action on this surface
carries an idempotency key." **Checked against the shipped router: only `record_gate_in` accepts or requires
an `Idempotency-Key` header** (`gate.py:78-83, 93-96`) — the catalog names one for exactly this tool and no
other (§0.1). Traced each of the other four for what a genuine double-tap actually does, rather than
assuming the claim's framing:
  - `update_queue_state` — a retry targets a `queue_state` the truck has already reached, which is not in
    its own `QUEUE_TRANSITIONS` set, so it returns `INVALID_TRANSITION` (screen 22), not a duplicate write.
  - `record_dock_in` — a retry's `current != "CALLED_TO_DOCK"` guard (the truck is now `IN_DOCK`) catches it
    the same way.
  - `record_unload_start_end` — both `START` and `END` guard on their own already-set timestamp column.
  - `record_gate_out` — a retry hits the explicit `ALREADY_GATED_OUT` branch (screen 12), which restates the
    fact rather than re-recording it.

**A double-tap is genuinely safe on all five tools — but by two different mechanisms, not one.**
`record_gate_in` replays the exact original response via `lookup_idempotency`/`store_idempotency`; the other
four surface a *different*, state-machine-derived response (`INVALID_TRANSITION` or `ALREADY_GATED_OUT`)
that is safe but not identical to a true idempotent replay. The design's copy overstates a single uniform
mechanism where two exist. §6 Fork G — a documentation fix or a backend consistency fix, not a functional
bug.

**A smaller documentation-completeness note, not escalated as a gap:** `ALREADY_GATED_OUT` is a real,
correctly-implemented outcome code (`gate_yard_service.py:829`, matching `edge-cases.md` #6's narrative
exactly) that is never named as a code anywhere in `screens.md`, `edge-cases.md`, `components.md`, or
`stitch-prompts.md`'s own outcome-tone table (judgement call #5) — every other outcome code in the catalog
is named explicitly. Worth a one-line addition next time those files are touched; not blocking anything.

### 5.2 The color.md self-contradiction — a third instance of a pattern E5.2 and E5.3 both found

E5.2 found `escalation-sla-warning: amber-600` contradicting `color.md`'s own contrast table (3.04:1,
correctly since raised to `amber-700`). E5.3 found the TTL-urgency table's `amber-600` band doing the exact
same thing (correctly since raised to `amber-700`). **Checked the Feedback-colors table — the one neither
prior pass touched — and found a third instance, in a *border* token this time rather than a *text* token:**

```
feedback-warning-border       amber-500          amber-500     (color.md, unchanged)
```

Independently recomputed (not copied from the prior pass's inline comment): `amber-500` `#F59E0B` against
`#FFFFFF` **2.15:1**, against the page background `#F8FAFC` **2.05:1** — both fail WCAG 1.4.11's 3:1 for a
UI component boundary. **This is the identical hex and the identical failing ratio `state-held-border`
carried before its own 2026-08-29 correction** (`color.md`'s own note: *"amber-500 2.05:1"* →
`amber-600` **3.04:1**). That correction was scoped to the promise-state table only and never swept one
section down to Feedback-colors, which still fails today.

**The mockup's own fix history for this token is itself an instructive regression-and-catch story.** The
*original* E5.4 pass (before this issue's interruption) read `stitch-prompts.md`'s "Known mockup deviations"
table, which asserted the mockup's `amber-600` border was a *deviation* from `color.md`'s (uninspected)
`amber-500`, and "corrected" the mockup back to the failing value — applying the standing "foundations wins"
rule to a foundations value that was itself wrong, because nobody had rendered and measured it at the time
that table was written. The *second* (this issue's continuation) pass rendered it, measured 2.05–2.07:1,
recognised the exact match to the already-fixed `state-held-border` defect, and reverted the mockup to
`amber-600` (3.04–3.19:1) — while correctly declining to patch `color.md` itself, per the standing rule that
a foundations-file edit is the owner's call. **Independently re-verified this session**: the arithmetic
checks out exactly (§5.0's table), and `color.md` as written today would, if trusted literally, revert this
mockup's fix a second time. §6 Fork A.

**This defect is not contained to the mockup.** `stitch-prompts.md` itself — a separate deliverable, not
just a cross-reference to the mockup — specifies `#F59E0B` (the same failing amber-500) as the warning-block
border in **four separate prompts**: 13 (the Inactive-state sheet's retry message), 17 (`DOCK_MISMATCH`), 18
(unload overrun), and 21 (`DOCK_OCCUPIED`). All four carry the exact "never `#D97706` for the *text*, that's
3.2:1" warning correctly for their text colour, but never make the equivalent check for the *border* they
also specify. If Stitch is run against these prompts today, it will produce four artboards with the same
2.05:1 border failure the mockup already found and fixed once. Same root cause as `color.md`'s stale row;
same fix (`#F59E0B` → `#D97706` in all four prompts) once §6 Fork A is resolved.

### 5.3 `web-design-guidelines` (U38 gate) — actually invoked

Skill invoked via the `Skill` tool; guidelines fetched fresh from
[vercel-labs/web-interface-guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md).
Applied to `mockup.html`, checked against source and against the rendered DOM, not eyeballed.

| Finding | Detail |
|---|---|
| `<button>` for actions, `<a>` for navigation | ✅ clean. Every row, link-ctl and primary action is a real `<button type="button">`; the disambiguation-list rows are `<button class="row">` inside `<li>`, never a `<div onClick>`. |
| Form controls need `<label>` or `aria-label` | ✅ clean. All 10 inputs carry a real `<label for="...">`, native association, not `aria-label`-only. |
| Inputs need `autocomplete` and a meaningful `name` | ✅ clean after the prior pass's R6 (re-verified §5.0). |
| Use correct `type`/`inputmode` | 🟡 `type="text"` throughout (correct — nothing on this surface is an email/tel/etc field); `inputmode` is unset on both real inputs. **Not a silent gap** — the mockup's own inline comment names it and defers to this file, §6 Fork D. |
| Disable spellcheck on codes | ✅ clean, `spellcheck="false"` on all 10. |
| Placeholders end with `…` | N/A — no placeholder text exists anywhere on this surface; every field carries a real, always-visible label instead, which is the stricter and better pattern. |
| Loading states end with `…` | ✅ — the in-flight search button freezes its label rather than showing a bare spinner, matching `components.md` §2/§4's own stated rule; no placeholder ellipsis needed since the label itself doesn't change. |
| `touch-action: manipulation`, `-webkit-tap-highlight-color` | ✅ clean, verified present on `.btn,.row,.link-ctl,.field` (§5.0). |
| `overscroll-behavior: contain` in modals | N/A — this surface has **no modals anywhere** (U41's no-confirmation-modal philosophy taken to its stated "logical extreme" here, `components.md` §4); the guideline's own scope is modals specifically. |
| Ellipsis `…` not `...` | ✅ 2× `…`, 0× `...`. |
| Curly quotes | ✅ 32 curly apostrophes found (`officer's`, `truck's`, etc.); no straight quotes in rendered copy. |
| `text-wrap: balance` on headings | ✅ present on `.title` and `.block .headline` (§5.0). |
| `font-variant-numeric: tabular-nums` | ✅ via `.mono`, applied to every id, timestamp, dock code and duration. |
| `translate="no"` on identifiers | ✅ 54 occurrences — every shipment id, plate, dock code and mono timestamp. Stronger than several other surfaces audited this phase, which had this at 0 before their own fix passes. |
| `Intl.*` not used | **0 occurrences.** All dates, times and durations are hardcoded strings ("Tue 4 Aug", "18:04", "1h 22m"). Same position taken for every other surface in this phase: **reported, not fixed** — a build requirement, not a board defect. |
| Icon-only buttons need `aria-label` | N/A — **zero icon-only controls exist anywhere on this surface**, by explicit design (`stitch-prompts.md` prompt 13: "an icon-only variant (icon-only controls are forbidden here)"). Every icon on this board is paired with visible text and is `aria-hidden="true"`. |
| Async updates need `aria-live="polite"` | ✅ via semantics, not the raw attribute — `role="status"` (5 success outcomes, `ALREADY_CHECKED_IN`, `DOCK_MISMATCH`, unload overrun) and `role="alert"` (the four "nothing was recorded" outcomes) already imply `polite`/`assertive` live-region behaviour respectively; a bare `aria-live` attribute would be redundant on top of the role. Raw `aria-live` count is 0 by design, not by omission. |
| Warn before navigation with unsaved changes | N/A — no multi-field form exists anywhere that could lose unsaved state; the only text entry is the single-value officer-name field (once per shift) and the single-value search field (submitted immediately). |
| Submit button stays enabled until request starts | ✅ — the in-flight state (`.is-submitting`) is a separate, later state; nothing disables the button pre-submit. |
| Confirmation or undo on destructive actions | N/A by design — `components.md` §4: *"There is never a second button at this decision point... U41's no-confirmation-modal philosophy taken to its logical extreme."* Every action here is a factual record of something that already physically happened, not a reversible commitment; the design argues explicitly against adding either. |

**Clean beyond the table:** no `transition: all`; the single `outline:none` family all carry a `box-shadow`
`:focus-visible` replacement; no `user-scalable=no`; no blocked paste (no `onPaste` at all — nothing here
takes pasted input); no unjustified `autofocus`; no animated GIF; no gesture-only affordance (U25's "no free
dragging" holds trivially, since there is no dragging surface on this board at all).

### 5.4 `checklist-design` — actually invoked, confirmed no match, `critique` mode run instead

Skill invoked via the `Skill` tool. `screens.md`'s and `accessibility.md`'s own headers both already state
that no whole-screen checklist in the 122-item index matches a single-purpose field kiosk, and that this
surface is "the right candidate for a `critique`-mode pass... once something is built." Re-confirmed rather
than trusted: the index was re-read this pass and no checklist targets a search-then-act, one-object-at-a-
time field device — the nearest neighbours (*Single Item Detail*, used by E5.2 for the ops detail pane; *Data
Table*, used by E5.2/E5.3) both assume a list the user navigates away from and back to, which this surface
explicitly does not have (`screens.md`: "There is no list, no dashboard... the entire surface is this loop").

**Ran `critique` mode instead**, per the file's own stated intent, over the rendered artboards:

- **Hierarchy** reads cleanly on every screen — one headline, one supporting block, one button, in that
  order, with no competing element. The identity block's muted background (`surface-hover` inside a
  `surface-raised` card) is the only visual separation used anywhere, and it is used consistently.
- **Consistency across both device contexts** is strong — the landscape and portrait variants of the same
  logical screen (e.g. prompts 1/2, shift start) differ only in card width and vertical placement, never in
  type scale, colour, or copy. This is what U108's "the split is layout, not a different tool contract"
  looks like when actually rendered side by side.
- **One genuine polish gap, not previously flagged**: the "no match" search screen (`screens.md` §2,
  `flows-and-states.md` Flow 1.3) states in prose that *"the search field retains focus so the officer can
  immediately retype"* — but the corresponding artboard does not render the field with the `is-focus` class,
  so the described behaviour has no visual reference on the board. Minor, and the same category as the
  prior finding that SLA-clock ticking has "no rendered reference" on a static mockup — noted so it isn't
  silently assumed correct, not escalated as a defect.
- **Nothing else registered** — no orphaned spacing, no inconsistent radius, no stray hue. The restraint
  this surface's own accessibility framing argues for (large type, single hue for interactive elements, no
  colour-coded state) reads as genuinely calm rather than sparse.

### 5.5 `dataviz` — confirmed does not apply

No chart, sparkline, stat tile, or metric visual exists anywhere on this surface — the closest candidate,
the unload-overrun outcome, is explicitly specified as **not** a gauge or comparison chart
(`stitch-prompts.md` prompt 18: *"Explicitly exclude: a dwell-time gauge, chart, sparkline or benchmark
bar... this surface records; other surfaces evaluate"*). Confirmed rather than assumed; not run.

---

## 6 · Seven forks for the owner

Surfaced, not resolved. Each carries options, a recommendation, and the honest trade-off.

**Fork A · `color.md`'s `feedback-warning-border` needs the same correction `state-held-border` already
got, and `stitch-prompts.md` needs the matching fix in four prompts.** Diagnosed in §5.2. `amber-500`
measures 2.05–2.15:1 against every background it actually renders on; `amber-600` (the value already
adopted for the byte-identical `state-held-border` defect) measures 3.04–3.19:1 and clears WCAG 1.4.11.
*Options:* (a) raise `feedback-warning-border` to `amber-600` in `color.md`'s Feedback-colors table, add the
matching four-prompt fix (`#F59E0B` → `#D97706`) to `stitch-prompts.md`'s prompts 13/17/18/21, and correct
the "Known mockup deviations" table's now-backwards row 1; (b) leave `color.md` as-is and treat the mockup's
`amber-600` as a permanent, documented deviation — reopens the exact revert risk §5.2 traces through this
token's own history; (c) add a component-scoped override token under `tokens.md`'s tier system (U85) rather
than touching the shared `feedback-warning-*` family, on the reasoning that this surface's field-glare
context needs a higher-contrast warning border than a desk surface does.
*Recommendation:* **(a)**. Unlike Fork F in E5.3 (a genuine 0.09-short residual after correction, escalated
because the token's own context differs per-surface), this is the *exact* value and the *exact* fix already
adopted once elsewhere in the same file — there is no new judgement call here, only a sweep that was missed.

**Fork B · The shift-start "empty officer name" button uses the Disabled tier; `components.md` §18 names
the gate kiosk specifically as the surface where Inactive should be preferred.** Measured: `.btn.is-inert`
renders at 2.08:1 (`#94A3B8` on `#E2E8F0`) — legitimately WCAG-exempt if Disabled is the correct tier for
this state (`aria-disabled="true"`, "not exposed as interactive," per U83's own table), paired correctly
with a visible reason line (`components.md §1`/§18's own requirement, satisfied via `aria-describedby`). But
`components.md` §18's own rule reads: *"Use Inactive, not Disabled, for anything a driver or planner needs
to understand why is unavailable right now... this matters most on the gate kiosk: outdoors, low contrast,
in sunlight, a Disabled control is indistinguishable from a rendering failure."* That sentence names this
surface by name and is not scoped to any particular *cause* of unavailability.
*Options:* (a) leave it as Disabled — the case is genuinely different in kind from the rule's own example
(a `HELD` card whose hold silently lapsed, or a request another planner just acted on mid-interaction): the
button was never interactive a moment ago and the static helper text beside it already states the reason
without requiring a press, so there is nothing "activating it" would newly reveal, unlike the rule's own
example where pressing the stale control *is* how the officer learns what happened; (b) convert it to
Inactive — full contrast, focusable, and pressing it while the field is empty surfaces the same "Enter your
name to start" text as an inline explanation rather than (or in addition to) the always-visible helper line,
for literal consistency with §18's blanket gate-kiosk framing; (c) narrow §18's rule itself to state the
distinction implicit in its own example — Inactive is for states that *change while being looked at*,
Disabled remains correct for a static, self-evident prerequisite — so future authors don't have to re-derive
this same read every time.
*Recommendation:* **(a) now, with (c) as the actual foundations fix.** The empty-field case has a
categorical difference from the rule's own worked example that the rule's current wording doesn't capture,
and narrowing the rule (once, in `components.md`) is cheaper than reinterpreting it per occurrence on this
surface's other buttons — of which there are two more identical instances (screens 1 and 2's `s1a`/`s2a`).

**Fork C · `spacing-and-layout.md`'s breakpoint table has no row for the yard tablet, and still calls the
gate kiosk "landscape locked."** `stitch-prompts.md`'s own judgement-call table (#3) already flagged this as
unresolved — re-verified directly against the current `spacing-and-layout.md`: the table's one "Gate kiosk"
row still reads *"1024–1366px, landscape locked... Not supported — shows an orientation prompt"* below
range, with no second row for U108's portrait handheld device at all. Taken literally, an 800×1280 yard
tablet is *below the supported range in the wrong orientation* per this table and should show an orientation
prompt — which would break the entire yard-tablet half of this surface.
*Options:* (a) add a second "Yard tablet" row (`768–1024px, portrait locked`, primary target 800×1280,
below-range: orientation prompt) alongside a corrected "Gate kiosk" row, so the table has one row per real
device rather than one row per surface name; (b) fold both into one "Gate/yard kiosk" row stating both
supported orientations explicitly, since U108 frames them as one surface with two layouts rather than two
surfaces; (c) leave the table as a surface-level generalisation and treat device-specific breakpoints as
this folder's own concern exclusively (they are already fully specified in `stitch-prompts.md`'s frame
dimensions).
*Recommendation:* **(a)**. This table is what a future implementer checks first for "what breakpoint am I
building," and a table that currently says the yard tablet shouldn't work at all is worse than no table —
(c) leaves the contradiction standing for anyone who reads the foundations file before this folder's own
files.

**Fork D · Neither real text input sets `inputmode`, and no existing value fits.** Carried forward verbatim
from the mockup's own inline promise (`mockup.html:284`). `components.md` §2 asks for a "numeric-friendly
keyboard by default," but both real values (`SHP1015`, `RJ14 GH 2211`) are alphanumeric, and
`inputmode="numeric"` would lock the on-screen keyboard to digits only, making a genuine plate or ID
unenterable.
*Options:* (a) leave `inputmode` unset (the current state) so the OS default (full alphanumeric) keyboard
appears — correct but not "numeric-friendly" in the sense `components.md` originally asked for; (b) use
`inputmode="text"` explicitly, which is a no-op functionally but documents the decision was made rather than
overlooked; (c) revisit whether shipment IDs and plates could be constrained to a stricter alphanumeric
pattern that some future custom keyboard layout could target — out of scope for a v1 kiosk build.
*Recommendation:* **(b)**. Costs nothing, and an explicit `inputmode="text"` is the honest record that
`components.md` §2's "numeric-friendly" framing doesn't survive contact with the actual data shape, rather
than a silently-unset attribute a future reviewer might read as an oversight.

**Fork E · How G1 (no search tool) should actually be resolved.** Diagnosed in §2. The pieces exist in
different, incompatible shapes.
*Options:* (a) a dedicated `search_gate_yard_truck(query, facility_id)` tool under §7.5.2 — matches on
`shipment_id`, `order_reference`, and `vehicles.registration_number`, scoped to the caller's facility (the
device's fixed facility, per `screens.md` §1), and returns the joined `facility_checkins` + appointment shape
`components.md` §3's identity card needs in one call; (b) extend `search_records` (§7.5.8) to add
`registration_number` to `_search_shipments`'s match set and a `vehicles` join to its result shape — reuses
existing infrastructure but widens a tool explicitly documented as facility-desk-shell scoped
(`search_service.py`'s own docstring: *"the shared-shell mockup set this catalog closes a gap for... is the
ops/admin desk shell"*) to a device class that isn't part of that shell; (c) wire up and re-scope
`get_gate_and_queue_status` — the dead code already has the right *response* shape, but would need a new
role/scope check (currently driver-only) and a preceding lookup-by-ID-or-plate step it doesn't have either,
so this is really (a) with extra steps through existing code.
*Recommendation:* **(a)**. It is the narrowest, most correctly-scoped option — a facility-fixed device
searching within its own facility only, never the cross-facility reach `search_records` is built for — and
it is the only option that produces exactly the response shape `components.md` §3 already specifies without
a second round-trip.

**Fork F · How G2 (officer attribution) should actually be resolved.** Diagnosed in §5.1.
*Options:* (a) add an `officer_name` argument to all five write tools, and a corresponding column (or a
JSON field inside `audit_logs.new_value_json`, which already carries free-form event detail per-tool) to
record it — the smallest change that makes U111's claim true; (b) give each individual officer their own
Supabase Auth login instead of a shared device credential, and derive attribution from `ctx.user_id` the way
every other surface in the product does — more consistent with the rest of the auth model, but directly
contradicts `components.md` §1's own stated design ("not a re-asked credential," "a shared-device
attribution mechanism, not an authentication boundary") and would require every officer to authenticate
individually on a device meant to be picked up and put down dozens of times a shift; (c) correct
`components.md` §1, U111, and `edge-cases.md` #8 to stop claiming per-officer attribution, and describe the
audit trail honestly as device-level only.
*Recommendation:* **(a)**. It is the option that actually delivers what three separate design documents
already promise, and `audit_logs.new_value_json` already has a proven pattern for carrying event-specific
detail the fixed schema doesn't have a column for (`_audit`'s existing `"event": "GATE_IN"` etc. keys) — the
same mechanism can carry `"officer_name": "Ramesh K."` with no migration required at all.

**Fork G · The idempotency-key claim in `components.md` §4 and `stitch-prompts.md` prompt 13 should either
be corrected or made true.** Diagnosed in §5.1 as G3. The claimed mechanism ("every action... carries an
idempotency key") is uniform; the actual mechanism is two different things (one true idempotent replay, four
state-machine-guarded safe retries) that happen to produce the same safety property.
*Options:* (a) correct the design copy to describe the actual two-mechanism reality, since the *outcome* the
copy promises the officer ("this won't record it twice") is true either way and doesn't need the backend to
change; (b) add real `Idempotency-Key` handling to the other four tools for literal consistency with the
catalog's own framing — more backend work for a property that's already achieved another way; (c) leave both
as-is, since no officer-facing behaviour is actually wrong.
*Recommendation:* **(a)**. The officer-facing promise already holds; only the internal explanation is
imprecise, and a documentation correction is cheaper and lower-risk than adding idempotency-key plumbing to
four tools whose own state machines already make it redundant.

---

## 7 · Suggested order for E5.4

1. **Ship screen 13 (component state sheet) and the shift-start pair (screens 1–2) first** — the only three
   screens that build today without G1, contingent on Fork B's answer for the empty-state button tier.
2. **Resolve Fork E and build the search tool it points to.** This single addition is the entire remaining
   critical path — every other screen's write logic already exists, verified in §0.1, and needs no further
   backend work once a truck can actually be found.
3. **Wire the eighteen truck-found/outcome screens against the five existing writes in one pass**, not
   eighteen separate ones — they share one component (`components.md` §3/§4/§5) and one interaction model
   (U110), and the state→action table (`screens.md` §3) is already the complete implementation spec for all
   seven `queue_state` branches plus the four named non-success outcomes.
4. **Resolve Fork F alongside step 2** — adding `officer_name` to the same five tools' request bodies is a
   small, low-risk addition best done in the same change as whatever touches those tools' contracts for the
   new search tool's response shape, rather than as a separate later pass.
5. **`color.md` and `stitch-prompts.md` fixes (Fork A)** — a two-line foundations edit plus a four-prompt
   text correction; do this before anyone runs the affected `stitch-prompts.md` prompts against Stitch again,
   since running them today reproduces a defect already found and fixed once.
6. **Fork C's breakpoint-table row** — low effort, protects the next implementer who reads
   `spacing-and-layout.md` before this folder's own files, the same failure mode that produced the table's
   current contradiction in the first place.
7. **Fork D and Fork G** — both single-line changes (`inputmode="text"`; a documentation correction), no
   dependency on anything else in this list.

**Feature flags.** Name for the dependency: `gate_search_enabled` (Fork E/G1 — gates screens 3–22 as one
unit, matching §3's finding that they unblock together); `gate_officer_attribution_enabled` (Fork F/G2 — can
ship independently of the search flag, since it changes what the five existing writes record, not whether
they can be reached).

---

## 8 · Constitution Check

| Check | Result |
|---|---|
| Contradicts a locked decision U1–U120? | **No.** U7, U19, U25, U26, U30, U32, U37, U41, U59, U69, U70, U83, U84, U85, U86, U87, U108, U109, U110, U111 are each cited where they constrain a value. U37's already-corrected status (`ui-ux-pro-max` confirmed absent, per the README's own note) is carried forward, not re-litigated. No U69 violation found — the one surface in this phase's four so far that never needed an R1-class fix. |
| Amends a foundations or surface file? | **No file was edited.** Two corrections this pass identified (`color.md`'s `feedback-warning-border` row, `spacing-and-layout.md`'s breakpoint table) are §6 Forks A and C, because both affect readers beyond this one surface. `mockup.html`'s prior-pass fixes were independently re-verified, not re-edited. |
| Invents product behaviour? | **No.** All five §7.5.2 tools were read off `gate_yard_service.py`/`gate.py` directly, with line numbers; the two gaps (G1, G2) are read off absence in source (`gate.py`'s zero `GET` routes; the five Pydantic bodies' missing field; `assistant/tools.py`'s zero match) rather than inferred from design docs. `ALREADY_GATED_OUT`'s undocumented-but-real status is reported as a documentation gap, not silently normalised into the design files. |
| Invents data? | **No.** Where a value has no source (the `inputmode` choice, the Disabled-vs-Inactive tier for an empty required field) it is named as a genuine open question in §6, not resolved by assumption. |
| React 19 frontend (ADR 012)? | Yes — unchanged from E5.0–E5.3; not exercised directly by this pass since no frontend code exists for this surface yet. |
| Stays inside the named scope? | Yes. The brief named all of `04-gate-yard-kiosk/`, the foundations files this surface actually touches, and E5.2/E5.3's specs as templates. `backend/app/services/gate_yard_service.py`, `api/v1/routers/gate.py`, `services/search_service.py`, `services/driver_reads.py`, `assistant/tools.py`, `core/execution_context.py` and the baseline migration were read because the brief's own instruction requires confirming the tool catalog "the same way E5.2 and E5.3 did," which cannot be asserted from design docs alone. Issue #39 and its blocker #30 were read per `AGENTS.md`'s tracker rule. No file outside this surface, its foundations dependencies, and the named backend/tracker sources was read. |
| Skills actually invoked, not cited? | **Yes, three, via the `Skill` tool.** `web-design-guidelines` (§5.3, guidelines fetched fresh from source, applied item-by-item against both source and the rendered DOM). `checklist-design` (§5.4 — index re-checked for a matching whole-screen checklist, confirmed none exists as the surface's own files already claimed, then run in `critique` mode as that file's own header names as the correct next step, producing one genuine new finding — the no-match screen's missing `is-focus` state). `dataviz` considered and confirmed not applicable (§5.5), with the specific line in `stitch-prompts.md` that rules it out cited rather than asserted. `design` canvas not run — this is a spec/verification pass over an existing, previously-drafted mockup, not a new screen. |
| Rendering verified, not eyeballed? | **Yes.** Headless Chromium via Playwright, installed fresh this session (not inherited): computed styles and `getBoundingClientRect()` across all 35 artboards; contrast computed from rendered `rgb()` against each element's own resolved background — **the measurement script's first version had exactly the bug it was checking mockups for** (walking to the parent's background instead of the element's own), producing 33 false-positive `.btn` failures, caught by inspecting the actual `fg`/`bg` pairs before trusting the count, and fixed before any number in this document was drawn from it; ARIA/role census over the live DOM; card-position census across all 22 yard frames; full regex sweep for emoji, ellipsis, en-dash, and sub-14px text. Zero real defects found; the prior pass's eight fixes independently reproduced, not re-trusted from their comments. |
| Genuine forks surfaced, not silently decided? | **Yes, seven** (§6), each with options, a recommendation, and the honest trade-off. **Zero resolved silently.** Fork B in particular states its own recommendation's limits plainly — leaving a foundations rule's blanket wording standing over two more identical instances on this same surface, rather than quietly patching all three and calling the question closed. |
| Fixes verified by measurement, not by editing and assuming? | **Yes — every one, including a defect in the measurement approach itself, caught before publication.** No fix was made this pass (§0's "defines no new design decisions" holds literally — this is a verification pass over an already-fixed file); every claim from the prior pass was independently reproduced from a fresh render rather than copied from its inline comments. |
| Writeback (`CHANGELOG.md`, `wiki/`)? | **Not required** — `AGENTS.md`'s exemption covers everything under `docs/New-Solution-New-Design/`. |
| Empirical numbers tagged? | Yes. All §1, §5.0 and §5.2 figures are *measured*, most independently recomputed from first principles rather than trusted from the prior pass; §0.1's tool table is *source-verified* with file and line; §2's G1 finding is *verified by absence* (zero `GET` routes in `gate.py`, zero matches in `assistant/tools.py`) plus *verified by presence-in-the-wrong-shape* (`search_records`'s actual query and response, read in full); §6's recommendations are *judgement* and say so. |
