# Implementation spec — ops exception console (E5.2)

> **M5 / E5.2 (issue #37).** The buildable translation of `02-ops-exception-console/`'s locked design, on
> top of the design system E5.0 shipped and the tool catalog M3 actually closed. **This file defines no new
> design decisions.** Every value is copied from a foundations file, a surface file, `mockup.html`, or
> verified source in `backend/` / `frontend/`, with its source named. Where a value has no source, or two
> sources disagree, it is in §6 as a decision the owner has to make — not resolved here.
>
> **Read for this pass, and only these:** all six `02-ops-exception-console/` files (`screens.md`,
> `flows-and-states.md`, `edge-cases.md`, `components.md`, `accessibility.md`, `stitch-prompts.md`) plus
> `mockup.html`; `00-foundations/` — `components.md`, `accessibility-behaviour.md`, `color.md`,
> `typography.md`, `spacing-and-layout.md`, `iconography.md`, `tokens.md`, `ai-chat-primitives.md`;
> `SOLUTION_DESIGN.md` §7.4, §7.5.1, §7.5.3, §7.5.5, §7.5.8; `01-driver-chat/implementation-spec.md` (E5.1,
> as the template and as the source of the shared-token fixes this surface has to inherit); and the live
> `backend/app/services/escalation_service.py`, `backend/app/api/v1/routers/operations.py`,
> `backend/app/assistant/run_assistant.py`, `frontend/src/core/http/sse.ts`.
>
> **Status: PARTIALLY BUILD-READY. 9 of 16 screens ship now; 3 are gated on one open fork; 4 are blocked
> on backend gaps that are not UI decisions.** Twelve rendering defects found by measurement, **all twelve
> fixed and re-measured**. One measurement retracted. Six backend/spec gaps escalated rather than designed
> over — including two of the same class that produced §7.5.5 and `block_dock`, found the same way.

**Owner decisions still open: six (§6).** Nothing in §5's fix pass required one; everything in §6 does.

---

## 0 · Starting point — what exists, verified not assumed

### 0.1 What M3 actually shipped for this surface

E5.2's issue lists **M3 as a blocker** and M3 is closed. Checked tool-by-tool against
`SOLUTION_DESIGN.md` §7.5.5, not taken from the milestone's closed state:

| §7.5.5 tool | Shipped? | Source |
|---|---|---|
| `get_escalation_queue` | ✅ `GET /operations/escalation-queue` | `escalation_service.py:215` (`get_exception_queue`), `operations.py:66` |
| `acknowledge_escalation` | ✅ with the `ALREADY_ACTIONED` race | `escalation_service.py:522`, `operations.py:119` |
| `reassign_escalation` | ✅ with `NOT_ACKNOWLEDGED` | `escalation_service.py:592`, `operations.py:136` |
| `take_over_thread` | ✅ with `ALREADY_TAKEN_OVER` | `escalation_service.py:652`, `operations.py:152` |
| `hand_back_thread` | ✅ with `NOT_IN_PROGRESS` | `escalation_service.py:739`, `operations.py:170` |
| `resolve_escalation` | ✅ `reason_code` enum enforced | `escalation_service.py:324`, `operations.py:78` |
| `cancel_escalation` | ✅ `reason_code` enum enforced | `escalation_service.py:431`, `operations.py:98` |
| **`request_sequencer_proposal`** | ❌ **NOT SHIPPED** | Blocked on **open issue #49** (§5.1, G1) |

**Seven of eight.** The eighth is not an oversight — E3.2's own Understand pass found it depends entirely
on §7.5.3's sequencer, which does not exist anywhere in the codebase, and filed #49 rather than stubbing
it. That is the right call and it is why one of this surface's sixteen screens cannot be built end-to-end.

Verified alongside, and all of it good news:

| Fact | Source |
|---|---|
| `reason_code` enums are **enforced server-side**, not merely documented — a wrong value is a 422 `INVALID_REASON_CODE` naming the supported set | `escalation_service.py:38-39, 344, 448` |
| The acknowledge race is a real `WHERE escalation_status = 'OPEN'` guard, so the loser gets `ALREADY_ACTIONED` with the winning owner, not a second silent claim | `escalation_service.py:558-578` |
| `STEPPER_POSITIONS` exists and maps `escalation_status` → 0–3, with `RESOLVED`/`CANCELLED` deliberately sharing 3 | `escalation_service.py:21-26` |
| `affected_shipments` is populated **only** for `CAPACITY_EVENT_CASCADE` rows | `escalation_service.py:280-282` |
| The queue sorts `(owner_user_id is not None, sla_remaining_min)` — unowned above owned, then SLA ascending | `escalation_service.py:289` |
| The §7.4 nine-reason enum was reconciled in E2.4 and matches the design exactly | `escalation_service.py:40-61` + `supabase/migrations/20260823100000_e24_escalation_vocabulary.sql` |
| `take_over_thread` sets `chat_threads.thread_status = 'ESCALATED'` and `run_assistant.py` **actually reads it** to suppress auto-reply | `escalation_service.py:711`, `run_assistant.py:191-200` |
| Every capacity/state-affecting write requires an `Idempotency-Key` header and 400s without one (U70) | `operations.py:58-64` |
| `chat_messages.sender_type` admits `'OPERATIONS'` in the schema | `supabase/migrations/20260805201923_setuhaul_baseline.sql:269-270` |

### 0.2 The frontend after E5.0 / E5.1

| Fact | Consequence for E5.2 |
|---|---|
| `theme.css` carries every token this surface references, including `--color-sla-ok/-warning/-breach` and the four `--priority-*-marker` steps | Nothing to add for colour. |
| **`frontend/src/core/http/sse.ts` is the only streaming transport in the product**, and it is the driver `/chat` turn stream | **There is no server-push channel for the ops queue.** §5.1 G6 — this is load-bearing for four separate specified behaviours. |
| `identity.ts` gives ops `density: compact`, `hasFacilityScope: true`, a rail | Set `data-density="compact"` once at the route root → `--tap: 32px`. |
| `01-driver-chat/` shipped `promise-chip.tsx` and the shared countdown | **Not reused here.** This surface renders no promise-state chip at all (§5.2, F-A). |
| Issue **#52 is OPEN** — `/auth/me` returns one `role_name`, not `grants[]` | The facility switcher's "All facilities" scope (U91) and `reassign_escalation`'s same-facility coordinator list both need the grant list. Same `FIXTURE SEAM` E5.0 named. |

---

## 1 · The three-pane shell

`screens.md` §1 + `spacing-and-layout.md`. One screen, three persistent panes (U89), **a scoped exception
to U44 that does not generalise** — `03-planner-dock-board/`'s queue still expands inline.

```
┌──┬───────────────────────────────────────────────────────────────────────┐
│▌ │ TOP BAR  56px   facility switcher · search · bell/help/settings/account│
├──┼──────────────┬───────────────────────────┬──────────────────────────────┤
│56│ QUEUE 340px  │ DETAIL + THREAD  flexible │ CO-PILOT 320px               │
│  │ role=region  │ role=region               │ role=region                  │
│  │ Ctrl+1       │ Ctrl+2                    │ Ctrl+3                       │
├──┴──────────────┴───────────────────────────┴──────────────────────────────┤
│ STATUS BAR 28px  connection · last sync · scope · pending · policy version │
└────────────────────────────────────────────────────────────────────────────┘
```

**The three panes are `role="region"` with an `aria-label` each, and this is not optional decoration.**
`accessibility.md` gives this surface `Cmd/Ctrl+1/2/3` to "jump focus directly to queue pane / detail pane /
co-pilot pane" and calls them "three simultaneously-live regions." A pane-jump shortcut needs a landmark to
jump *to*, and a screen-reader user needs a region list to move between. The mockup had **zero** — no
`<main>`, `<nav>`, `<aside>`, and `role="region"` count 0 file-wide (§5.3-R8, now fixed and re-measured at
51 across all 17 frames).

Rail: 56px, **one destination — `flag`, "Exceptions"** per `iconography.md`'s Rail destinations table.
Facility accent is `--facility-accent`, `neutral-300` under "All facilities" (U91) — correct in the mockup,
measured. **A second rail item ("Profile") is rendered and is not in that table — §6 Fork E.**

Breakpoint: desktop-only, ≥1280px (`spacing-and-layout.md`'s surface table). Measured: no horizontal
overflow at 1600 / 1440 / 1280 / 1024. **This proves nothing about the console's own responsiveness** —
the artboards are fixed-width cards on a scrolling board, so the three-pane collapse behaviour at 1280 has
no rendered reference. Stated so it isn't mistaken for verification.

---

## 2 · The queue row and the SLA clock

The two components this surface's 30-second-per-row budget hangs off. Both were rendered and measured.

### 2.1 Row anatomy

`components.md` (this folder) §1. Measured type and colour, all four lines:

| Line | Rendered | Token | Contrast |
|---|---|---|---|
| ID | 14px / 600 / `--font-data` / tabular | `text-primary` | 17.06:1 |
| Owner (right) | 11px / 500 / `.02em` | `text-secondary` **(was `text-tertiary`, §5.3-R4)** | 4.61:1 |
| Owner — **Unowned** | 11px / 600 | `feedback-warning-text` (`amber-700`) | 4.80:1 |
| Reason | 12px / 600 / uppercase / `.04em` + icon | `text-secondary` | 7.24:1 |
| Shipment · facility | 13px / 400 | `text-secondary` | 7.24:1 |
| SLA | 13px / 600 / `--font-data` / tabular | `sla-warning` **(was `amber-600`, §5.3-R2)** | 4.58–4.80:1 |
| SLA — breach | 13px / 700 | `sla-breach` **(was `red-600`, §5.3-R3)** | 5.95–6.18:1 |

**Five type sizes in one row (11/12/13/14) is worth a second look but is not a defect** —
`typography.md`'s "never use size to create hierarchy inside a table row" is written about a *table* row,
and this is a four-line card. Recorded as an observation, not raised as a finding, because the file it
would cite doesn't actually cover this shape.

**The priority marker specified in `components.md` §1 — "3px left edge, the shipment's own priority" — is
rendered on zero queue rows.** `.pri-crit/-high/-norm/-low` exist and consume the four
`--priority-*-marker` tokens correctly, but are applied only to the four `.shiprow` elements inside the
incident detail. Prompt 1's own caption says the selection edge "overrid[es] the priority marker that edge
is otherwise reserved for (**Prompt 7**)" — and Prompt 7 has zero. §6 Fork D.

### 2.2 The SLA clock — and the contradiction inside `color.md`

`color.md` assigns `escalation-sla-warning: amber-600` (light). `color.md`'s **own** contrast table, 180
lines further down, says `amber-600 #D97706 | 3.2:1 | ✗ Fails normal text — UI/large only`. The mockup
did what the token said and measured **3.04:1 at 13px/600** — 44 instances, the single most
operationally-important field on the surface.

This is the same failure shape E5.1 found in `01-driver-chat/accessibility.md`: one file asserting two
things that cannot both be true, invisible until rendered. `amber-700` is one step down the same ramp,
keeps the hue family, changes nothing outside this token, and measures **4.80:1**. Fixed and re-measured;
**`color.md`'s token row should be corrected at source rather than only in this mockup** — §6 Fork F.

Three postures, per `color.md`:

| Posture | Token | Trigger |
|---|---|---|
| ok | `--color-sla-ok` = `text-secondary` — **deliberately no colour** | > 25% of window remaining |
| warning | `--color-sla-warning` = `amber-700` | < 25% remaining |
| breach | `--color-sla-breach` = `red-700`, weight 700 | deadline passed |

Threshold crossing is **`instant`, never a fade** (`edge-cases.md` §1, `motion.md`'s U77 rule). The colour
is never the sole carrier — the text says "4:12 to breach" / "6m past breach" either way, which is also
what makes this survive `forced-colors: active` (`accessibility.md`, U87).

**The mockup has zero `@keyframes` and zero `<script>`.** Unlike `01-driver-chat/`'s board, nothing here
ticks, so the warning→breach transition has **no rendered reference** and E5.1's R2/R3/R4-class defects
(a band that never fires, an expiry state that never renders, two views of one clock disagreeing) are
**not detectable on this board**. Build them as regression tests from the start; do not assume their
absence from §5.3 means they were checked.

### 2.3 Sort — load-bearing, and unstated on screen

The queue's order is a real decision (U95: unowned pinned above owned, then time-to-breach ascending) and
it is **frozen while a row has focus** (U19). Measured: a regex for any sort statement across the entire
rendered document returns **zero matches**. A coordinator has no on-screen way to know why ESC-104 sits
above ESC-102. Checklist Design's Data Table checklist calls this out in its own tip. §6 Fork D.

There is also a **three-way disagreement about what U95 actually says**:

| Source | Says |
|---|---|
| `screens.md` §2 | "unowned + immediate = pinned top" |
| `components.md` §1 | "Unowned + immediate-SLA-posture rows sort to the top" |
| `edge-cases.md` §1 | "U95 sorts unowned above owned **regardless** of breach" |
| **Shipped backend** | `sort(key=(owner is not None, sla_remaining_min))` — **plain unowned-above-owned, no posture term** |

The backend matches `edge-cases.md`. Two of the three design files add a posture qualifier the
implementation does not have. Alias at the boundary or fix the prose; do not build a third behaviour.

**And the posture vocabulary itself has no backend field.** The mockup renders `12m (soft posture)`;
§7.4 speaks of Immediate/Soft postures; the shipped service uses `severity_code` ∈ HIGH/MEDIUM/LOW with
`SLA_BUDGET_MIN = {HIGH: 120, MEDIUM: 480, LOW: 1440}` explicitly flagged **`Source: assumption,
untested`** in its own comment (`escalation_service.py:28-35`). Flag it the same way anywhere it renders.

---

## 3 · The 16 screens → build readiness

16 prompts, rendered as **23 artboard blocks plus 3 whole-console hero frames** in `mockup.html`
(17 `.frame` elements total). Copy is authoritative in `stitch-prompts.md` at the prompt number given.

**Legend:** 🟢 buildable today · 🟡 buildable, one open fork · 🔴 blocked by a §5.1 gap.

### A · Queue pane (prompts 1–6)

| # | Screen | Line | Components | Build |
|---|---|---:|---|:--:|
| 1 | Queue row — default / hover / keyboard focus / selected | 929 | `.qrow` ×4 states, reason icon, SLA line, owner | 🟡 Forks C, D |
| 2a | Queue filtered — active filter chips | 989 | Filter control + dismissible chip row + "Clear all" | 🟢 |
| 2b | Filtered to zero — empty-search treatment | 1056 | `EmptyState`, `search-x`, distinct from 6a/6b | 🟢 |
| 3 | Live arrivals held behind the frozen sort | 1111 | "N new · press R" pill, U19 frozen sort | 🔴 G6 |
| 4 | Queue loading — shell never unmounts | 1185 | Skeleton rows at final row height, `aria-busy` | 🟢 |
| 5a | Queue load failed — regional, not global | 1237 | `role="alert"` state block + Retry; other panes unaffected | 🟢 |
| 5b | Error boundary — scoped per pane, never whole-app | 1286 | Same, at boundary level | 🟢 |
| 6a | Empty — variant A, caught up | 1361 | `circle-check-big`, **no CTA** (U74) | 🟢 |
| 6b | Empty — variant B, nothing yet | 1405 | `inbox`. **Distinct from 6a; the distinction is a server-side history check, never `count === 0`** | 🟢 |

Hover changes background and border only — **no lift, no scale** (`motion.md`). Focus is the two-ring
treatment drawn inset so an `overflow:auto` pane cannot clip it; verified present and using
`box-shadow` replacement, never a bare `outline:none`.

**No bulk actions on this queue, deliberately** (`components.md` §1) — a considered exclusion with a
stated reason, already caught and closed in a prior `checklist-design` audit. Do not add one.

### B · Detail pane (prompts 7–10)

| # | Screen | Line | Components | Build |
|---|---|---:|---|:--:|
| 7a | Detail — escalation selected, before takeover | 1454 | Stepper (full variant), owner control, Reason, Shipment, read-only thread | 🟡 G3 |
| 7b | Reason-specific Reason section — `NOTIFICATION_FAILED` vs `NOTIFICATION_UNROUTABLE` | 1557 | `mail-warning` vs `mail-x`; retry offered vs **never** offered | 🟢 |
| 8 | Under takeover — a human is now in the driver's conversation | 1627 | Takeover divider, live composer, Resolve/Cancel, Hand back | 🔴 G2, G5 |
| 9 | `WAREHOUSE_REPLY_CONFLICT` — two accounts, no auto-reconcile | 1734 | Side-by-side read-only, **no one-click reconcile anywhere** | 🟢 |
| 10a | `ALREADY_ACTIONED` — lost the acknowledge race | 1831 | Row updates **in place**, winning owner named, `role="alert"` | 🟢 |
| 10b | The underlying shipment changed under the coordinator | 1918 | Inline `role="alert"` notice; escalation does **not** auto-close | 🔴 G6 |

**7b is the one to protect in review.** §7.4 makes `UNROUTABLE` vs `FAILED` a different fix with a
different owner, and `edge-cases.md` §6 forbids offering "retry send" on `UNROUTABLE` — retrying against a
NULL recipient is pointless and offering it misleads the coordinator into thinking retry is the fix. Both
icons and both reason texts are already distinct in the mockup; keep them distinct.

**Screen 9 is a posture, not a layout.** No "Accept warehouse's version" / "Keep ours" shortcut exists
anywhere in this reason's pane, and none should be added as a convenience later. `edge-cases.md` §10 is
explicit that a wrong auto-merge is indistinguishable from a correct one until it's too late.

### C · Co-pilot pane (prompts 11–13)

| # | Screen | Line | Components | Build |
|---|---|---:|---|:--:|
| 11 | Co-pilot — Inactive, the state it sits in most of the time | 1968 | `components.md` §18 **Inactive**, not Disabled, not Hidden | 🟡 Fork B |
| 12 | Co-pilot active — three fixed capabilities, and the two-gate draft | 1997 | `AssistantSidebar`, draft-reply card, Discard / Approve → | 🔴 G4, G2 |
| 13 | Co-pilot degradations — stale draft, safety suppression, per-action errors | 2095 | Stale marker, `SAFETY_OR_REGULATED` Inactive, per-action error copy | 🔴 G4 |

**The two-gate rule is the whole point and must not be collapsed** (U90): Draft → **Approve** (moves the
text into the composer, *does not send*) → **Send**. The coordinator reads the exact string twice. There is
no "Approve and send." This is the pattern for any future AI-generated driver-facing text, not just here.

`SAFETY_OR_REGULATED` renders **Draft a reply** Inactive **immediately on selection**, not after a
generation fails — so a coordinator never spends a cycle on a reply that was never going to be offered.
Summarise and Fetch context stay fully available; context-gathering carries none of the liability a
drafted message does. Reason-specific, **not** takeover-wide.

Screen 11's copy is genuinely well-handled and worth keeping: the capacity-incident variant reads *"Not
applicable to a capacity incident — there is no single driver thread to take over,"* which is a better
answer than the generic Inactive line. **But `components.md` §18's Inactive contract requires the control
to be focusable and to explain itself on activation, and the pane currently renders as plain text with no
focusable element** — §6 Fork B.

### D · Incident, reason picker, feedback (prompts 14–16)

| # | Screen | Line | Components | Build |
|---|---|---:|---|:--:|
| 14 | Capacity incident — collapsed, expanded, handed off, scope-denied | 2164 | One row not four (U65), read-only affected set, Request proposal | 🔴 G1 |
| 15a | Reason picker — Cancel variant, over a flat scrim, with a toast above it | 2270 | `role="dialog" aria-modal` + `aria-labelledby`, 3 reason codes | 🟢 |
| 15b | Resolve variant, and the commit gated until a reason is chosen | 2379 | 1 reason code, commit Disabled until chosen | 🟢 |
| 16a | Toast stack — bottom-left, max three, older collapsed | 2433 | `role="status"` info/success, `role="alert"` error, 5s undo | 🟢 |
| 16b | Inline failed write, and the non-blocking warning | 2523 | *"That didn't save. **Nothing has changed.**"* | 🟢 |

**15a/15b are the strongest screens on the board** and match the shipped backend exactly: the
`reason_code` enums are enforced server-side with a 422 naming the supported set, so the picker's
controlled vocabulary is a real contract rather than a client-side courtesy. The Resolve variant's commit
button is genuinely `aria-disabled="true"` with a `title` explaining why — U83's **Disabled** tier, used
correctly and for the right reason (nothing to explain by activating it; a reason is simply required).

**16b's clause is load-bearing, not padding.** "Nothing has changed" is the sentence that stops a
coordinator retrying a write that already landed. Keep it verbatim.

**Idempotency (U70), stated per action rather than assumed:** every one of Acknowledge, Take over,
Resolve, Cancel carries an `Idempotency-Key`; the shipped endpoints **400 without one**
(`operations.py:58-64`). Bind the key to `escalation_id + action`, reused verbatim on retry. Reassign
deliberately does not require one — it is Low-tier and reversible by reassigning again (Flow 5).

**Undo (U41), not a confirmation modal.** The 5-second window delays the *notification*, not the write.
Per `accessibility-behaviour.md`'s resolution of the U41 collision, the undo must **also** be reachable as
`Cmd/Ctrl+Z` regardless of focus, or it is functionally unavailable to a screen-reader user who has to
hear the toast, navigate to it, and click it inside five seconds.

---

## 4 · What E5.2 adds to the design system

**Nothing.** Every token this surface needs is already in `theme.css`. That is the correct outcome and it
is worth stating: the ops console consumes `--color-sla-*`, `--priority-*-marker`, `--facility-accent`, the
feedback triad, and the surface/text/border ramps, and introduces no new colour, no keyframe, and no
component-scoped token. Set `data-density="compact"` once at the route root; never per component.

One correction is owed **to** the design system rather than added by it: `color.md`'s
`escalation-sla-warning` row (§2.2, §6 Fork F).

---

## 5 · Readiness call

**Verdict: 9 of 16 screens build now. 3 are gated on one open fork. 4 are blocked on backend gaps that are
not UI decisions.** Twelve rendering defects found by measurement, all twelve fixed and re-measured; one
reading retracted.

### 5.0 Fix-pass scoreboard — every item re-measured, none assumed

Method: headless Chromium (Playwright 1.62 / Chromium 1234) over CDP. Computed styles and box model across
all 17 frames, contrast computed from **rendered** `rgb()` values against each element's effective
background, ARIA census over the live DOM, four viewport widths, and clipped screenshots at DPR 2 before
and after. "Before" is the audit pass; "after" is the same probes re-run.

| # | Defect | Before | After | Verified by |
|---|---|---|---|---|
| **R1** | Board auto-switched to dark on OS preference (U69, third recurrence) | `--surface-base: #020617` under `prefers-color-scheme: dark` | **`#F8FAFC`** under the same emulation · **0** `@media (prefers-color-scheme)` CSS rules remain | Forced-scheme render, both directions |
| **R2** | SLA warning fails AA as text | `amber-600`, **3.04 / 2.93 / 2.91:1**, 44 instances at 12–13px | `amber-700`, **4.58 / 4.61 / 4.80:1**, all pass | Computed contrast, every instance |
| **R3** | SLA breach fails AA on a selected row | `red-600`, **4.44:1**, 2 instances | `red-700`, **5.95 / 6.18:1** | Computed contrast |
| **R4** | Owner name and row meta fail AA on a selected row | `text-tertiary`, **4.37:1**, 8 instances | `text-secondary`, **≥4.5:1**, 0 fail | Computed contrast |
| **R5** | Search-bar placeholder fails AA | `text-tertiary` on `neutral-100`, **4.34:1**, 20 instances | `text-secondary`, passes | Computed contrast |
| **R6** | Targets below `compact`'s 32px floor | **46 of 197** — rail links 34 @ 24×20, `.chip-x` 4 @ **16×16**, `.b-text` 6 @ 20×14, `.pill-btn` @ 25, `.newpill` @ 26, incident disclosure @ 16, Dismiss @ 20×20 | **0 of 199** | Box model, all frames |
| **R7** | The three hero frames bypassed the file's own icon system | **29 emoji glyphs** (🏢🔍🔔⚙︎👤⚑🔌⏱▶▼▾) where a lucide symbol already existed for every one | **0 emoji**; sprite uses 236 → **275** | Markup census + screenshot |
| **R8** | Three panes, zero programmatic regions | `role="region"` **0**, no `<main>`/`<nav>`/`<aside>` — `Ctrl+1/2/3` had nothing to target | **51 regions across 17 frames**, verified rail + queue + detail + co-pilot **in order, 17/17** | DOM structure assertion |
| **R10** | Takeover divider announced politely, against this surface's own spec | `role="status"` (implicitly polite); `accessibility.md` says **`assertive`** | `role="alert"` | ARIA census |
| **R11** | Co-pilot completion had no live region at all | `aria-live` **0** file-wide; `accessibility.md`'s polite row unrepresented | `role="status" aria-live="polite"` on every `.cp-result` | ARIA census |
| **R12** | Incident disclosure had no expanded state | `aria-expanded` **0** on both `.incident-row` controls; `▶`/`▼` text glyphs only | **2**, `role="button" tabindex="0"`, correct true/false | ARIA census |
| **R13** | Two of three reason-picker dialogs lacked modal semantics | `role="dialog"` **3**, `aria-modal` **1** | **3 / 3** | ARIA census |

**Bonus, same pass — the `theme-color` pair.** With R1's CSS fixed, `<meta name="theme-color" … media="(prefers-color-scheme: dark)" content="#020617">` would have left a dark-preference browser rendering a
light page while painting its own chrome near-black. The same U69 failure one layer up. Replaced with one
unconditional value.

**No regressions:** 17 frames and 23 artboard blocks unchanged; **0** text nodes below `typography.md`'s
11px floor before *and* after; `tabular-nums` still on all 15 sites; no `transition: all`; both
`outline:none` occurrences still carry their `box-shadow` focus replacement; `…` used correctly (19
occurrences, **zero** `...`); `min-width:0` present on the flex bodies that need truncation.

**And one thing this board got right that `01-driver-chat/`'s did not:** there is **no blanket
`*{animation:none!important}`** reduced-motion kill. E5.0 flagged that pattern, E5.1 had to remove it from
the driver board, and it does not recur here. Recorded because a clean inheritance is worth as much as a
caught defect.

### 5.1 Six escalated gaps — none of them a UI decision

Found the standing rule's way: cross-check each job the persona row lists against what a tool actually
does. **G1 and G6 are the same class that produced §7.5.5, §7.5.1's `block_dock`, §7.5.6 and §7.5.7.**

**G1 · 🔴 `request_sequencer_proposal` does not exist.** §7.5.5 defines it as a thin delegate to §7.5.3's
`propose_facility_schedule`; §7.5.3 is unbuilt in its entirety, tracked as **open issue #49**. E3.2 shipped
its other seven tools and filed the gap rather than stubbing it. **Gates prompt 14 (all four states),
hero State 3, `screens.md` §5, and Flow 4** — i.e. the entire ops half of U93's two-surface handoff. Not
fixable here: the ops side is "triage and request," and there is nothing to request from.

**G2 · 🔴 A coordinator cannot actually reply. No tool posts a message as `OPERATIONS`.** `take_over_thread`
enables a composer; **nothing in §7.5.5, §7.5.8, or anywhere in `backend/app/` writes a `chat_messages` row
with `sender_type = 'OPERATIONS'`** (grepped; the schema admits the value, no code produces it).
`flows-and-states.md` Flow 3 says "Send follows the ordinary thread-composer send path" — but the ordinary
path is `/chat`, which *runs the assistant*, which is precisely what takeover just switched off. **This is
the surface's reason to exist and it has no contract.** Gates prompt 8, prompt 12's second gate, and
hero State 2. Same gap class as §7.5.5 itself: a listed job with no tool.

**G3 · 🟡 Nothing advances an escalation to `IN_PROGRESS`.** `STEPPER_POSITIONS` maps it to 2 and the
stepper draws four positions, but `escalation_status = 'IN_PROGRESS'` is **never written** anywhere
(`grep` over `escalation_service.py`: the only writes are `ACKNOWLEDGED`, `RESOLVED`, `CANCELLED`).
`flows-and-states.md` Flow 1 step 4 says "a status the coordinator sets explicitly"; `components.md` §5 and
§7.5.5 both make `hand_back_thread` require `IN_PROGRESS`. The shipped implementation works around this by
accepting `escalation_status IN ('ACKNOWLEDGED','IN_PROGRESS')` (`escalation_service.py:771`). So the
third stepper dot is currently unreachable and hand-back's stated precondition is not the one enforced.
§7.5.5 needs an eighth-and-a-half tool or the stepper needs three positions.

**G4 · 🔴 The co-pilot has no contract at all.** §7.5.5 deliberately excludes summarise / fetch-context /
draft-reply from its table, reasoning that they are "LLM-assisted actions scoped to an active takeover,
not new mutating tools." That reasoning is sound for *mutation* and leaves **three of sixteen screens with
no endpoint, no request shape, no error taxonomy, and no owner** — while §7.4 calls the co-pilot "where the
LLM adds the most value per token in this whole product." §6 Fork A. Note the design already specifies the
hard parts (the two gates, the stale-draft marker, the safety suppression, per-action independent
degradation); what is missing is the wire.

**G5 · 🔴 The driver-visible takeover divider does not reach the driver.** `take_over_thread` inserts a
`SYSTEM` `chat_messages` row — and `take_over_thread`'s own docstring says plainly that the live driver
surface renders history from Redis (`ConversationMemory`) and **nothing in the turn path reads
`chat_messages`**. So `flows-and-states.md` Flow 2 step 3 ("the driver sees it in `01-driver-chat/` at the
same moment") and §7.4's "a silent takeover reads as the bot ignoring them" are both unmet today. The
auto-reply suppression works; the *notice* does not. Cross-surface, affects `01-driver-chat/` screen 21.

**G6 · 🔴 There is no live-update transport for this console.** The only streaming endpoint in the product
is the driver `/chat` SSE turn stream (`chat.py:127-143`); `GET /operations/escalation-queue` is plain
request/response and no polling interval is specified anywhere. Four separately-specified behaviours
depend on knowing something changed without a page reload:

- prompt 3's "N new · press R" and U19's arrivals-accumulate-behind-frozen-sort;
- `edge-cases.md` §2's **`assertive`** announcement when another coordinator wins the acknowledge race
  while you are focused on that row;
- `edge-cases.md` §9's inline "SHP1015 was confirmed by another planner at 09:58" (prompt 10b);
- the status bar's "synced 4s ago" and its **`polite`** connection-state row in
  `accessibility-behaviour.md` — which that file added specifically because a planner who goes offline and
  keeps acting is acting on stale capacity data.

This is the largest gap by screen count and it is not named in any design file. Filing it is the finding.

### 5.2 The E5.1 shared-token reconciliation — and what it turned up

The brief asked whether this surface inherits E5.1's two chip-border contrast fixes correctly.

**Direct answer: they do not apply here. This surface renders no promise-state chip at all** — `SHOWN`,
`HELD`, `PENDING_CONFIRMATION` and `CONFIRMED` appear **zero** times in `mockup.html`, and no
`--color-state-*` token is referenced. So there is nothing to inherit and nothing broken.

**But checking it turned up something worse, and it is live.** E5.1 raised the two failing borders in
`frontend/src/styles/theme.css` (`--color-state-shown-border: neutral-300 → neutral-500`,
`--color-state-held-border: amber-500 → amber-600`) — and **`00-foundations/color.md` was never updated.**
Its Semantic-tokens table still reads:

```
state-shown-border            neutral-300        neutral-600
state-held-border             amber-500          amber-500
```

Confirmed against `git show --stat fddbb12`: `color.md` is not in E5.1's commit, and
`git log -S` places the `neutral-500` value in `theme.css` in that commit alone. So **the design system's
source of truth still documents the two values E5.1 measured at 1.42:1 and 2.05:1 and rejected**, while the
code carries the fix.

Per this project's own standing rule — *"if the mockup and a `00-foundations/` file disagree, foundations
wins"* — `color.md` as written would **revert E5.1's fix**. That is not hypothetical: it is exactly what the
next implementer reading `color.md` for a chip would do. §6 Fork F, which also carries §2.2's
`escalation-sla-warning` correction, since both are one edit to one table.

**F-A, stated as a finding rather than fixed here:** the E5.1 pass fixed the value and not the record.
This is a two-line edit to `color.md` plus a note, and it is a foundations change, so it is the owner's,
not this pass's.

### 5.3 Twelve rendering defects — measured, not inspected · **ALL FIXED 2026-08-29**

Scoreboard in §5.0; the diagnoses below are kept because *how* each was found is what stops it recurring.
Every fix carries a dated inline comment in `mockup.html` at the site it changes.

**R1 · The board auto-switches to dark on OS preference — third recurrence of one bug.** Two
`@media (prefers-color-scheme:dark){ :root:not([data-theme="light"]){…} }` blocks. Measured: under emulated
dark preference, `--surface-base` resolved `#020617` and `document.documentElement`'s `data-theme` was
`null` — i.e. the system, not the user, picked the theme, which is precisely what U69 forbids ("one
consistent default rather than per-surface or **system-following** defaults"). E5.0 removed this from
`mockup-shared-shell.html`; E5.1 removed it from `01-driver-chat/mockup.html`; it survived here. **The fix
was free**: an explicit `:root[data-theme="dark"]` block already existed and is a byte-for-byte duplicate,
so deleting the media wrapper removed the automatic switch and kept the dark theme fully available.
`color-scheme: light dark` → `light` for the same reason.

**R2 · The SLA line — the surface's most important field — fails WCAG AA as text, and `color.md`
contradicts itself about it.** Diagnosed in §2.2. 44 instances at 2.91–3.04:1. Worth noting *how* it
hid: the token is correctly named, correctly used, and correctly themed. Only rendering it and computing
the ratio against the actual painted background exposes it.

**R3 / R4 · The selected row's blue-50 tint pushes three more values under AA.** `red-600` breach 4.44,
`text-tertiary` owner 4.37, `text-tertiary` meta 4.37 — all three pass against `surface-base` and fail
against `surface-selected`. **This is the defect class that only appears in combination**: no single token
is wrong, the pairing is. Any future surface tinting a row background needs the same sweep.

**R5 · The top-bar search placeholder is 4.34:1.** `text-tertiary` on `surface-hover`. Placeholder text is
still text.

**R6 · 46 of 197 interactive elements sit below the density floor they were built to.** `compact`'s
32px minimum (`spacing-and-layout.md`, the deliberate desktop-and-pointer exception to 44px). Worst:
`.chip-x`, the filter-chip dismiss control at **16×16** — which fails not only our 32px but **WCAG 2.2 SC
2.5.8's 24×24 Level AA legal minimum**, as do the 20×14 text buttons and the 24×20 rail links (on height).
Fixed by growing hit areas around unchanged glyphs (negative margins), so nothing moved visually.

**R7 · The three whole-console hero frames bypass the icon system the rest of the file uses.** 29 emoji
glyphs — and the same file already defines a **29-symbol lucide sprite used 236 times elsewhere**,
including `#i-building`, `#i-search`, `#i-bell`, `#i-settings`, `#i-user`, `#i-flag`, `#i-network`,
`#i-timer`, `#i-chev-right/down` — one for every glyph replaced. An emoji renders in the OS colour font,
ignores `currentColor`, ignores the `stroke-width: 2` the sizing scale sets, and looks different on every
machine. **This is the single biggest visual improvement in the pass** and it is invisible in a markup
skim: the heroes are the artboards an implementer opens first, and they were the only ones off-system.
(Likely cause: the sprite is defined at line 905, *after* the hero frames at 292–500.)

**R8 · Three panes, zero regions.** Diagnosed in §1. The fix required two attempts — the first labelled
panes positionally per rail and silently rotated the labels by one across frames, which the DOM assertion
caught. Recorded because it is the argument for asserting structure rather than counting attributes: an
`role="region"` count of 51 looked correct and was wrong.

**R10 · The takeover divider announces politely; this surface's own `accessibility.md` says assertive.**
`role="status"` is implicitly `aria-live="polite"`. `accessibility.md`'s politeness additions table gives
takeover / hand-back **`assertive`**, with the reason stated: *"a coordinator who doesn't register they've
taken over may not realise the composer just became live."* Same shape as E5.1's chip/countdown collision
— a file specifying the right politeness and a mockup implementing a different one.

**R11 · The other row of that same table has no implementation at all.** `aria-live` count was **0**
file-wide. The co-pilot's "Summary ready" / "Context loaded" / "Draft ready" polite announcement had
nothing to fire from.

**R12 / R13 · Disclosure and modal semantics.** `aria-expanded` 0 on both incident disclosures (state
carried by a `▶`/`▼` text glyph). `aria-modal` on 1 of 3 dialogs.

**One thing measurement *retracted*.** `"Cancel escalation"` renders at **2.08:1** — the worst ratio on the
board — and it is **correct**. It is `class="b b-dis" aria-disabled="true" title="Choose a reason first."`,
prompt 15b's deliberately Disabled commit button: U83's Disabled tier, used for the right reason, and
explicitly exempt from WCAG 1.4.3's contrast minimum. Left alone. Recorded because an automated contrast
sweep will flag it forever and someone will eventually "fix" it into looking enabled.

### 5.4 `web-design-guidelines` (U38 gate) — actually invoked

Skill invoked via the `Skill` tool; guidelines fetched fresh from
[vercel-labs/web-interface-guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md).
Applied to `mockup.html`. A static reference board legitimately does not carry app semantics; the findings
below are the ones that are not that excuse.

| Finding | Detail |
|---|---|
| `mockup.html:77, 579` (before the fix) — theme auto-switch | Fixed, §5.3-R1. |
| `<div>` with interactive semantics | **26 `.qrow` + 7 `.row`** are `<div>` with no `role`, no `tabindex`, no `aria-selected`, no `aria-label`. Guideline's own anti-pattern list. **Reported, not fixed** — §6 Fork C, because the shared queue foundation never names the role. |
| Form controls without labels | `.composer` is an **empty `<div>`** — no `<textarea>`, no `<input>`, no label. Flow 2's three composer states (disabled pre-takeover / enabled / disabled post-hand-back) have no control to carry `disabled`/`readonly`/`aria-disabled`. §6 Fork B. |
| `Intl` not used | All dates, times and durations are hardcoded strings ("18 minutes ago", "09:15–13:00", "4:12 to breach"). `data-formatting.md` and U31 require `Intl` with `en-IN` from the start. **Reported, not fixed** — same position E5.1 took; this is a build requirement, not a board defect. |
| No `touch-action: manipulation`, no `-webkit-tap-highlight-color` | 0 occurrences. Low priority on a stated desktop-only surface, but `overscroll-behavior: contain` **is** present (2) on the modals, which is the one that matters here. |
| No skip link, no landmarks | Landmarks fixed (§5.3-R8). Skip link is board-level. |
| Icon-only buttons | ✅ **All** carry `aria-label` — `tb-btn` ×4, `chip-x` ×4, rail links, Dismiss. Clean. |
| Placeholders end with `…` | ✅ "Search shipment, driver, carrier…". Clean, and better than the driver board, which E5.1 had to park. |

**Clean:** no `transition: all`; both `outline:none` carry a `box-shadow` replacement and use
`:focus-visible` not `:focus`; `…` ×19 with zero `...`; curly quotes in copy; `tabular-nums` ×15;
`min-width:0` ×9 on the flex bodies; `text-wrap` used on headings; `overscroll-behavior: contain` on
modals; **no blanket reduced-motion kill**; no `user-scalable=no`; no blocked paste; 360 `aria-hidden` on
decorative glyphs.

### 5.5 `checklist-design` (U34 gate) — actually invoked

Skill invoked via the `Skill` tool; `references/index.md` and three checklists read from the skill's own
bundled files. Audited against source **plus** three rendered screenshots at DPR 2, so the "how it looks"
items are answered honestly rather than inferred.

**A note on which checklists.** `screens.md`'s own Checklist coverage section cites *Data Table* and
*Chat* (Web app). **The detail pane is a textbook *Single Item Detail*** — "the full details of a single
record after selecting it from a list" — and that checklist was never derived against. Running it produced
a real finding the other two miss, so it is audited here as a third.

#### Data Table — Web app ([checklist.design/web-app/data-table](https://www.checklist.design/web-app/data-table))

| | Item | Why |
|---|---|---|
| 🔴 | **Sortable columns** — Column headers that sort rows by that value on click, toggling ascending and descending | Sort is deliberately fixed (U95 + U19), which is a good decision — but **nothing on screen states what the sort is.** A regex for any sort statement across the whole rendered document returns zero matches. A coordinator has no way to know why ESC-104 precedes ESC-102, which is exactly what the checklist's own tip warns about. Fork D. |
| ⚪ | **Column visibility and order** — Controls to show or hide individual columns and drag to reorder them | A fixed ~5-field row is a deliberate constraint inherited from the planner console's discipline (`screens.md`). Not a table of columns. |
| ⚪ | **Row selection and bulk actions** — Checkboxes on each row and a persistent action bar appearing when rows are selected | Excluded with a stated reason (`components.md` §1): every escalation needs individual judgment, §7.4 never describes a bulk need the way §7.3 has `bulk_confirm`, and if one ever emerges it would be bulk-*claim*, not bulk resolve/cancel. A considered exclusion, already caught in a prior audit. |
| 🟡 | **Row actions on hover** — Contextual actions (edit, delete, view) appearing when hovering over a row | Hover changes background and border only. The incident row carries an in-row "Review incident" button, but escalation rows have no hover affordance — Acknowledge lives one click away in the detail pane. Defensible for a 30-second triage budget; worth knowing it's a choice. |
| 🟢 | **Search and filter** — A search input for quick lookup alongside filter controls for narrowing by specific attributes | Prompt 2 has it, including the checklist's exact tip: active filters render as dismissible chips above the list, plus "Clear all". |
| ⚪ | **Pagination** — Controls to navigate between pages of results, with an option to choose how many rows show per page | 15–35 items per §7.3's load arithmetic — worked live, not paged. Stated in `screens.md`. |
| ⚪ | **Frozen columns** — The first column pinned so it remains visible when the user scrolls horizontally | Card-shaped rows in a 340px pane; there is no horizontal scroll to survive. |
| ⚪ | **Export action** — A way to download the visible or selected rows as CSV, spreadsheet, or another format | §7.5.5 has no export tool and the product does export deliberately where it's warranted (§7.5.7's `export_audit_log`), so the absence here reads as a scoped decision rather than an omission. |
| 🟢 | **Empty and loading states** — The states shown when the table has no rows or when data is being fetched | Prompts 4, 5a, 5b, 6a, 6b — and better than the item asks: skeleton rows match final row height, load failure is **regional not global**, and empty is split into caught-up vs nothing-yet (U74). |

#### Chat — Web app ([checklist.design/web-app/chat](https://www.checklist.design/web-app/chat))

This is an operational record scoped to a takeover, not a messaging product — three ⚪ rows are deliberate.

| | Item | Why |
|---|---|---|
| 🟢 | **Message thread** — A chronological display of messages in the conversation, with the most recent at the bottom | Present, read-only before takeover, composable after. |
| 🔴 | **Message input** — A text field for composing and sending messages, with support for multi-line input | `.composer` is an **empty `<div>`** — no `<textarea>`, no label, no `aria-label`. Flow 2 specifies three distinct composer states and there is no form control to carry any of them. Fork B. |
| 🔴 | **Sender identification** — The sender's name and avatar displayed alongside each message, making the conversation easy to follow | The thread renders **one sender tier — `Driver`, 6 instances, no avatar.** There is **no `AGENT` message and no `OPERATIONS` message anywhere on the board.** The surface whose entire purpose is a human joining a conversation never shows what that human's message looks like — and with three possible senders, U47's three-tier model is exactly what tells them apart. Fork G. |
| 🟢 | **Timestamps** — When each message was sent, using relative time for recent messages and a full timestamp for older ones | "18 minutes ago"; `components.md` §3 confirms `data-formatting.md`'s counting-up bands apply with no surface-specific deviation. (Hardcoded rather than `Intl` — §5.4.) |
| ⚪ | **Read receipts** — An indicator showing whether the other participant has seen a message | An ops coordinator posting into an operational record does not need a driver's read state, and surfacing one would invite treating silence as an outcome. `edge-cases.md` §3 is explicit that a silent driver triggers no automatic behaviour. |
| ⚪ | **File and media sharing** — The ability to attach images, files, or links within the conversation | Not adopted product-wide (`ai-chat-primitives.md`); a photo-of-breakdown case is a product requirement first. |
| ⚪ | **Reactions** — Emoji reactions on individual messages as a lightweight way to respond without sending a full reply | An operational record should not have them, and `chat_messages` is append-only. |

#### Single Item Detail — Web app ([checklist.design/web-app/single-item-detail](https://www.checklist.design/web-app/single-item-detail))

Not previously derived against — added this pass.

| | Item | Why |
|---|---|---|
| 🟢 | **Clear title or identifier** — The name, ID, or primary label of the item, shown prominently at the top of the screen | `ESC-104 · NO_FEASIBLE_SLOT`, mono, top-left, largest thing in the pane. |
| 🟢 | **Status indicator (if applicable)** — A clear signal of the item's current state (active, pending, completed, archived) | The four-position stepper with word labels (`OPEN — ACK — IN PROGRESS — RESOLVED`), plus owner and SLA. Meets the checklist's tip exactly: never colour alone. (The third position has no tool behind it — G3.) |
| 🟡 | **Key details section** — The most important attributes of the item surfaced prominently, with secondary details available below or in a sidebar | Reason / Shipment / Thread are well grouped. 🟡 for the incident variant: four affected shipments render CRITICAL/HIGH/NORMAL as identical plain mono text with no priority marker, so the one thing a coordinator triages a cascade *by* carries no visual weight. Related to Fork D. |
| 🟢 | **Edit action** — A clear way to modify the item's details, either inline or via an edit mode | Acknowledge → Reassign → Take over → Resolve/Cancel, each in its correct lifecycle position, with Escalate/Reassign/Cancel demoted to an overflow menu once acknowledged so the pane foregrounds two decisions. |
| 🟡 | **Related items or activity** — Associated records, linked content, or a history of changes related to this item | The thread is the activity log and reads well. But the shipment (`SHP1015`) is plain text with no route to its detail, and there is no record of *who acknowledged when* — `reassign_escalation` explicitly preserves that history (`components.md` §2) and nothing renders it. |
| ⚪ | **Breadcrumb or back navigation** — A way to return to the list or parent context | The queue never leaves the screen. U89 trades screen count for pane persistence precisely so there is nothing to go back to. |
| 🟡 | **Destructive actions** — Delete or archive options, available on the detail screen but kept visually separate from the primary actions | **The board answers this two different ways.** Prompt 8 puts Resolve/Cancel on their own row 48px below Send, and its caption asserts "≥16px from `Send` and visually grouped apart" — correct. **The hero frame puts all three on one row** (measured: same `y`, 416px apart). Since the hero is the whole-console view an implementer copies first, the weaker treatment is the more visible one. Flow 6 calls conflating Resolve and Cancel "the likeliest real mistake a coordinator could make under time pressure." Fork D. |

**Beyond the checklists — one observation of my own.** No checklist has an item for *"the count in the
header doesn't match the rows below it."* All three hero frames read **`Escalations (7)`** while rendering
3, 3 and 1 escalation rows, with several hundred pixels of visible empty space beneath — so nothing is
scrolled off. It may be that the incident's four affected shipments are meant to count toward the total,
but U65's whole point is that an incident is **one row, not four**, and no file states the rule either way.
`screens.md` §2 already worried about exactly this ambiguity for *filters* and solved it with chips; the
same ambiguity in the unfiltered count went unnoticed. Fork D.

---

## 6 · Seven forks for the owner

Surfaced, not resolved. Each carries options, a recommendation, and the honest trade-off.

**Fork A · The co-pilot's three capabilities have no contract (G4).**
§7.5.5 deliberately excludes summarise / fetch-context / draft-reply from its tool table on the grounds
that they are not *mutating* tools. That reasoning holds for mutation and leaves prompts 11, 12 and 13
with no endpoint, no request shape, no error taxonomy and no owner — on the feature §7.4 calls "where the
LLM adds the most value per token in this whole product."
*Options:* (a) add a §7.5.5 sub-table for the three read/generate capabilities, scoped to an active
takeover, explicitly non-mutating, so they have a contract without becoming capacity-affecting tools;
(b) define them in a new §7.5.9 alongside other LLM-assisted-but-non-mutating capabilities, since this
will not be the last one; (c) build them client-side against the existing `/chat` endpoint with an ops
system prompt — cheapest, and it puts an LLM call on a path with no typed contract, which is the thing
`AGENTS.md` says the LLM must never be.
*Recommendation:* **(a)**. The design already specifies the hard parts — two gates, stale marker, safety
suppression, independent degradation. What is missing is the wire, and it belongs where the other seven
ops tools live. (c) should not be chosen quietly.

**Fork B · The co-pilot's Inactive state and the composer are both plain `<div>`s.**
`components.md` §18's Inactive contract requires a control that is "fully focusable, explains itself on
activation." The co-pilot pane renders as centred prose with no focusable element, and the thread composer
is an empty `<div>` with no label — so Flow 2's three composer states have nothing to carry `disabled` /
`readonly` / `aria-disabled`.
*Options:* (a) build both as real controls now — the Inactive pane gets a focusable button carrying the
explanation, the composer is a `<textarea>` with `readonly` pre-takeover; (b) treat the mockup's prose
rendering as the spec and downgrade §18's Inactive contract for panes as opposed to buttons; (c) leave the
board and fix it only in code.
*Recommendation:* **(a)**, and update the artboards. §18's contract exists so a coordinator never wonders
whether the co-pilot exists, and prose is not reachable by the keyboard-first user this surface is built
for. (b) weakens a foundations rule to match a mockup, which is the wrong direction of travel.

**Fork C · The shared queue row has no ARIA role, and this is a foundations decision, not a surface one.**
`components.md` §19 specifies the keyboard model (roving tabindex, `j`/`k`/arrows, `Enter` expands,
`Space` selects) but names **no** ARIA role for the row or container. Measured: 26 `.qrow` + 7 `.row` are
`<div>` with `role`, `tabindex`, `aria-selected` and `aria-label` all null. **Ops and planner share this
component (U23)**, so choosing here would either bind planner silently or guarantee two different answers.
*Options:* (a) `role="listbox"` + `role="option"` + `aria-selected` — matches "select one, detail follows,"
which is exactly this surface's model, and roving tabindex is the listbox's own native pattern;
(b) `role="grid"` + `role="row"` + `role="gridcell"` — right if the planner queue's seven fields are
genuinely columnar and individually navigable; (c) `<button>` per row inside a `role="list"` — simplest,
loses `aria-selected`.
*Recommendation:* **(a), decided in `00-foundations/components.md` §19, not here.** The selection semantics
are the load-bearing part and (b) buys cell navigation neither surface has asked for. Flagged rather than
patched precisely because patching it in the ops mockup is how the two surfaces diverge.

**Fork D · Four queue/detail affordances that the design specifies and the board does not render.**
Grouped because they are one review conversation, not four:
1. **Priority marker** — `components.md` §1 specifies a 3px left edge on the queue row; rendered on zero
   rows. Prompt 1's caption defers to Prompt 7; Prompt 7 has none. And the selection state claims the same
   3px edge, which is the genuine conflict Prompt 1 already noticed and did not resolve.
2. **Sort indicator** — zero statements of the sort order anywhere (§2.3).
3. **The `(7)` count** vs 3/3/1 rendered rows, with no stated rule for whether an incident contributes 1
   or N (§5.5).
4. **Resolve/Cancel vs Send grouping** — hero says one row, Prompt 8 says separate row; Prompt 8 is right.
*Recommendation:* fix 2, 3 and 4 as stated-but-unrendered; treat 1 as a real design question, because
"priority marker and selection marker share one 3px edge" needs an answer (a second channel — weight,
a leading glyph, or an inset rule — rather than a contested edge), not just an application of the class.

**Fork E · The rail has a second destination that `iconography.md`'s table does not list.**
`screens.md` §1 asserts two rail destinations (Escalations, Profile), citing `01-driver-chat/`'s bottom
nav. `iconography.md`'s Rail destinations table — added 2026-08-26, *after* `screens.md`, and governed by
U101 — enumerates **one destination per role** ("one destination per role — one surface per role") and
gives ops exactly one: **`flag`, "Exceptions."** `spacing-and-layout.md` puts the user menu in the **top
bar**. The mockup renders both a top-bar Account button and a rail Profile link — two entry points to the
same place. Also: `iconography.md` calls it **"Exceptions"**; `screens.md` and the mockup's `aria-label`
say **"Escalations."**
*Options:* (a) drop the rail Profile item and keep the top-bar account menu, aligning with
`iconography.md` and `spacing-and-layout.md`; (b) add Profile to `iconography.md`'s table as a
cross-cutting non-surface destination for every role; (c) leave both and accept the duplication.
*Recommendation:* **(a)**, plus settle the Exceptions/Escalations name in one direction. This is exactly
the U101 failure mode the owner caught by looking at a rendered mockup once before.

**Resolved 2026-08-29: owner picked (a).** All 17 rail Profile links removed from `mockup.html`; the
top-bar account menu is the sole entry point. `.railitem`'s CSS is unaffected — still used by the single
remaining Escalations item. The Exceptions/Escalations naming mismatch is **not** settled by this and
remains open (a naming-only follow-up, separate from the duplication itself).

**Fork F · `00-foundations/color.md` needs two corrections and they are one edit.**
1. **E5.1's fix was never written back.** `theme.css` carries `state-shown-border: neutral-500` and
   `state-held-border: amber-600`; `color.md` still documents `neutral-300` and `amber-500` — the values
   E5.1 measured at 1.42:1 and 2.05:1 and rejected. Foundations wins by rule, so the record currently
   instructs a revert (§5.2).
2. **`escalation-sla-warning: amber-600` contradicts `color.md`'s own contrast table** two hundred lines
   later, which marks `amber-600` as failing normal text. Measured 3.04:1 at 13px (§2.2). `amber-700`
   measures 4.80:1.
*Recommendation:* make both edits in `color.md` and add a one-line note under the contrast table that a
token assigned to *text* must clear 4.5:1, which is the rule that would have caught (2) at authoring time.
Not done here — this is a foundations change affecting every surface, so it is the owner's call.

**Fork G · The thread never renders an `AGENT` or `OPERATIONS` message.**
Six message instances, all `Driver`, no avatar. With G2 unresolved there is also no tool to produce an
`OPERATIONS` message, so this is partly downstream of that — but the *artboard* gap is independent: a
coordinator needs to see, before building, what their own message looks like next to the assistant's and
the driver's, and U47's three-tier model is the thing that keeps them apart.
*Options:* (a) add the two missing tiers to prompt 8 and to the hero takeover frame; (b) inherit
`01-driver-chat/`'s rendering wholesale and add no artboard, accepting that the third sender (OPERATIONS)
has no reference anywhere; (c) defer until G2 is answered.
*Recommendation:* **(a)**. The driver surface has two senders and this one has three; the third is the
only one this surface introduces, and it is the one that reaches a driver.

---

## 7 · Suggested order for E5.2

1. **The three-pane shell with real regions** (§1) — `role="region"` × 3 with labels, `Ctrl+1/2/3` bound,
   `data-density="compact"` at the route root. Everything else mounts inside it, and the pane-jump
   shortcut is the thing NVDA testing will hit first (`accessibility.md`'s AT matrix).
2. **The shared queue component** (U23) — but only after Fork C is answered in `components.md` §19. This
   is the one piece that must not be decided twice.
3. **Queue row + SLA clock**, with the three postures and the `instant` threshold crossing. Test by letting
   a clock run warning → breach; the board has no live reference, so E5.1's R2/R3/R4 are **regression
   tests to write from scratch here**, not defects already caught.
4. **Detail pane, prompts 7a/7b/9** — including the `UNROUTABLE`-never-offers-retry rule, which is a
   correctness requirement rather than copy.
5. **Reason picker and toasts, prompts 15/16.** The backend contract is complete and enforced; these are
   the highest-confidence screens on the surface and they exercise the undo window and the idempotency
   key end-to-end.
6. **The negative paths — 5a, 5b, 6a, 6b, 10a.** Regional error boundaries and the caught-up/nothing-yet
   split. Do not leave these to the end of the sprint; they are the surface, not decoration.
7. **Takeover (prompt 8)** — gated on G2. Build the pane; leave Send behind a flag until a tool exists.
8. **Co-pilot (prompts 11–13)** — gated on Fork A. Prompt 11's Inactive state can ship first and standalone,
   since it is what a coordinator sees most of the time.
9. **Capacity incident (prompt 14)** — gated on issue **#49**. Build the collapsed/expanded/scope-denied
   states; the handoff state has nothing to hand off to yet.
10. `Intl` with `en-IN` for every date, time and duration from the first component, not retrofitted
    (§5.4). And bind `Cmd/Ctrl+Z` to the undo window at the same time as the toast, not after.

**Feature flags.** Name each for its dependency, not its feature: `ops_send_message_enabled` (G2),
`ops_copilot_enabled` (Fork A), `sequencer_proposal_enabled` (#49). All default off, each with the issue
number in the comment, so it is obvious what removes it rather than obvious what it hides.

---

## 8 · Constitution Check

| Check | Result |
|---|---|
| Contradicts a locked decision U1–U120? | **No.** U19, U23, U25, U29, U31, U34, U38, U41, U44, U46, U47, U57, U59, U61, U65, U69, U70, U74, U77, U79, U82, U83, U84, U85, U87, U88, U89, U90, U91, U92, U93, U94, U95, U101 are each cited where they constrain a value. **One live U69 violation was found and fixed** (§5.3-R1) — third recurrence of the same bug across three mockups. U89's three-pane exception is noted as scoped, not generalised. |
| Amends a foundations or surface file? | **`mockup.html` only** — twelve fixes across ~40 sites, each with a dated inline comment. **No foundations or surface `.md` file was edited.** The two `color.md` corrections this pass identified are in §6 Fork F as the owner's call, because both affect every surface. |
| Invents product behaviour? | **No.** All eight §7.5.5 tools were read off `escalation_service.py` and `operations.py`; the six gaps are read off absence in source, not inferred from design docs; the co-pilot is reported as **having no contract** rather than given one. |
| Invents data? | **No.** Where a value has no source (the SLA posture vocabulary, the `(7)` count rule, the queue-row ARIA role) it is named as absent. `SLA_BUDGET_MIN`'s `Source: assumption, untested` flag is carried forward, not laundered. |
| React 19 frontend (ADR 012)? | Yes — unchanged from E5.0/E5.1. |
| Stays inside the named scope? | Yes. The brief named all of `02-ops-exception-console/`, four `00-foundations/` files, and E5.1's spec as template. `backend/app/services/escalation_service.py`, `routers/operations.py`, `run_assistant.py`, `chat.py` and `supabase/migrations/` were read because the brief's item 5 requires confirming M3's tool catalog against what shipped, and that cannot be asserted from design docs. The tracker was read per `AGENTS.md`'s startup rule. |
| Skills actually invoked, not cited? | **Yes, both, via the `Skill` tool.** `web-design-guidelines` (§5.4, guidelines fetched fresh from source) and `checklist-design` (§5.5 — `references/index.md` plus three checklists read from the skill's own bundled files, audited item-by-item in each checklist's own order, kept separate, no blending). **A third checklist — *Single Item Detail* — was added because the surface's own U34 derivation had missed it**, and it produced a finding the other two do not. `dataviz` not run — no chart, sparkline or stat tile on this surface. `design` canvas not run — this is a spec pass over an existing approved mockup, not a new screen. |
| Rendering verified, not eyeballed? | **Yes.** Headless Chromium via Playwright/CDP: computed styles and `getBoundingClientRect` across all 17 frames, contrast computed from rendered `rgb()` against each element's **effective** background, full ARIA census over the live DOM, forced `prefers-color-scheme` in both directions, four viewport widths, and clipped screenshots at DPR 2 before and after. Twelve defects found; **one reading retracted** because the element turned out to be a correctly-Disabled control (§5.3, closing paragraph); **one fix caught wrong by re-measurement** and redone (§5.3-R8). |
| Genuine forks surfaced, not silently decided? | **Yes, seven** (§6), each with options, a recommendation and the honest trade-off. **Zero resolved silently.** Fork C in particular was deliberately *not* patched, because patching it here is how ops and planner would diverge on a component U23 says they share. |
| Fixes verified by measurement, not by editing and assuming? | **Yes — every one.** All probes re-run after the edits: forced-scheme render both directions, computed contrast on every failing combination, box model across all 17 frames, ARIA census, emoji/sprite census, and a DOM assertion that all 17 frames carry rail + queue + detail + co-pilot regions **in order**. That last assertion is what caught the first region fix being silently rotated by one. |
| Writeback (`CHANGELOG.md`, `wiki/`)? | **Not required** — `AGENTS.md`'s exemption covers everything under `docs/New-Solution-New-Design/`. |
| Empirical numbers tagged? | Yes. All §5.0/§5.3 figures are *measured*; §0.1's tool table is *source-verified* with file and line; §5.1's six gaps are *verified by absence in source* (grep across `backend/app/`); §6's recommendations are *judgement* and say so. `SLA_BUDGET_MIN` is carried with the codebase's own `Source: assumption, untested` flag intact. |
