# Implementation spec — driver chat (E5.1)

> **M5 / E5.1 (issue #36).** The buildable translation of `01-driver-chat/`'s locked design, on top of the
> design system E5.0 actually shipped. **This file defines no new design decisions.** Every value is copied
> from a foundations file, a surface file, `mockup.html`, or verified source in `backend/` / `frontend/`,
> with its source named. Where a value has no source, or two sources disagree, it is in §6 as a decision the
> owner has to make — not resolved here.
>
> **Read for this pass, and only these:** `00-foundations/ai-chat-primitives.md` (required reading before
> this surface, per the standing note), `components.md` §§2–5/13/15/18/19, `accessibility-behaviour.md`,
> `data-formatting.md`, `tokens.md`, `iconography.md`, `spacing-and-layout.md`, `motion.md`, `color.md`,
> `00-foundations/implementation-spec.md` (E5.0's output); all five `01-driver-chat/` files plus
> `stitch-prompts.md` and `mockup.html`; `SOLUTION_DESIGN.md` §5, §7.1, §7.2b, §7.5.4; and the live
> `frontend/src/**` + the driver path in `backend/app/**`.
>
> **Status (revised 2026-08-27 after the fix pass): BUILD-READY. All four forks closed by the owner, all
> nine rendering defects fixed and re-measured, both escalated findings closed, and the
> `accessibility-behaviour.md` / `components.md` §2 contradiction resolved at source.**
>
> **24 of 28 screens ship now. The remaining four are gated on issue #53, not on design** — `HELD`, one of
> the four promise states and the entire reason the 90-second countdown exists, has no representation in
> the live schema and no tool (§5.1). Found the way §7.5.5 and `block_dock` were found: cross-checking the
> design's own tool catalog against what exists. Already known to the codebase and stated in four places
> there; **not** known to `01-driver-chat/`, which specifies the two-step commit as non-negotiable.
>
> **Owner decisions, 2026-08-27 — all four forks closed:**
>
> | Fork | Decision |
> |---|---|
> | **A** — option-card differentiator has no source | **Backend adds a server-computed `differentiator` field** to the option-set tool response. `fullstack-engineer` owns it. §1.4's row is now a contract to build against, not a gap. |
> | **B** — 14px floor / 11px chip / 1.01:1 fill | **Fixed in the mockup and re-measured** (§5.3-R9, §5.2-F1). The chip is 14px; the two failing borders were raised one ramp step; the "fill survives glare" rationale is corrected — see R9. |
> | **C** — tool results only in `done` | **Buffer until `done`, render together.** Matches §1.2's recommendation and today's behaviour; no backend change. |
> | **D** — the four `HELD` screens | **Build all 24 non-HELD screens now; the four `HELD`-dependent screens go behind a feature flag until #53 lands.** Flag defaults off. |

---

## 0 · Starting point — what exists, verified not assumed

### 0.1 The frontend after E5.0

| Fact | Consequence for E5.1 |
|---|---|
| **`@assistant-ui/react ^0.15.16` is already installed** (`frontend/package.json`) | E5.0's spec listed it as "deferred to its own epic." It landed anyway. **No install step; pin-verify the API surface against 0.15.x before writing, because U56 was taken against the library's docs, not against this version.** |
| `vite-plugin-pwa ^1.3.0` installed, **no manifest or SW registration wired yet** | The PWA half of "driver PWA" is E5.1's, not E5.0's. |
| `CountdownProvider` exists and is mounted (`src/shared/lib/countdown.tsx`, `src/providers.tsx`) | One shared 1 Hz tick, server-offset-corrected, freezes offline. **Use it. Do not add a second timer.** Its `useCountdown(expiresAtIso, totalMs)` already returns the four throttle thresholds. |
| `src/core/http/sse.ts` exists, built against the real backend frames | The transport is done. §1 is about what to *do* with the frames, not how to read them. |
| `identity.ts` already encodes the driver: `DRIVER → rail null`, `landingPathFor → '/driver'`, density `comfortable`, `hasFacilityScope false`, `idlePolicyFor null` | The driver's shell exclusions are already code. **Do not mount `<AppShell>` on `/driver`** — it exists to render a rail the driver does not have. |
| `src/features/` has `auth`, `gallery`, `settings` — **no `driver/`** | E5.1 creates it. |
| `theme.css` has every promise-state token incl. `--color-state-*-icon`, `--color-urgent`, `--color-urgent-mid`, `--color-expired-fg/bg` | The chip and countdown are fully tokenised. Nothing to add for colour. |
| `theme.css` has exactly **one** keyframe, `shim` | **The `HELD` border pulse has no keyframe and no token.** §4.1. |
| `theme.css` has **no bottom-nav tokens** | Confirms the design's own flag F5. §4.2. |
| Deps present and relevant: `radix-ui` (unified pkg, not per-component), `sonner`, `cmdk`, `date-fns`, `jotai`, `lodash.throttle`, `@uidotdev/usehooks`, `lucide-react ^1.34` | `date-fns` is installed but `data-formatting.md` + `accessibility.md` both require **`Intl` with `en-IN`**. Use `Intl.DateTimeFormat`; `date-fns` is for arithmetic, not formatting. |

**Issue #52 is OPEN** — `GET /api/v1/auth/me` returns a single `role_name`, not a `grants[]` list. E5.0 works
around it with a named `FIXTURE SEAM`. The driver surface needs `driver_id`, `carrier`, and vehicle for the
Profile screen (screen 13); confirm those come off `/auth/me` or a driver tool before building it.

### 0.2 The backend driver path

Verified against source on 2026-08-27, not from the design docs:

| Fact | Source |
|---|---|
| **11 of §7.5.4's 12 driver tools are bound.** `confirm_held_slot` is absent, with a stated reason. | `backend/app/assistant/tools.py:30-50` |
| `request_slot` inserts an appointment **directly at `'PENDING_CONFIRMATION'`**. There is no intermediate hold. | `backend/app/scheduling/allocation.py:1167` |
| `appointments_appointment_status_check` admits `PENDING_CONFIRMATION / CONFIRMED / IN_PROGRESS / COMPLETED / CANCELLED / NO_SHOW / REJECTED / EXPIRED`. **No `HELD`.** `dock_occupancy` has neither `state` nor `expires_at`. | `backend/app/scheduling/expiry.py:89-103`, verified there against production 2026-08-23 |
| The M8 sweeper's `HELD` leg **returns `supported: false`** with an explicit reason string rather than a zero count. | `expiry.py:148-160` |
| `carrier_reads.py` **refuses** `SHOWN`/`HELD` promise-state filters with a stated reason rather than returning a misleading empty list. | `backend/app/services/carrier_reads.py:39-54` |
| SSE frames: `start` · `token` (text delta) · `status` (`{tool: name}`, **name only, emitted before execution**) · `error` · `done` (full turn result). | `run_assistant.py:663-783`, `routers/chat.py:98-145` |
| `done.data.tool_calls[]` = `{name, args, result, result_preview}` — **the full parsed tool result**. | `run_assistant.py:531-539` |
| `done.data.ux_state` ∈ `confirmation_required` · `clarification_required` · `capability_not_enabled` · `persisted_success` · (default `chat`). `done.data.confirmation` carries the payload. | `run_assistant.py:388-401, 546-547` |

---

## 1 · assistant-ui — the one genuinely new surface

`ai-chat-primitives.md` binds seven primitives to seven decisions. That file names the *fit*; this section
names the *wiring*, and one thing in it is not what the design assumed.

### 1.1 The runtime: `ExternalStoreRuntime`, and why not the alternatives

`ai-chat-primitives.md` deliberately declines to choose a backend adapter. Given the SSE contract in §0.2,
the choice is now forced rather than open:

| Option | Verdict |
|---|---|
| `useChatRuntime` / Data Stream Protocol | **No.** Expects the Vercel AI SDK wire format. Ours is a bespoke `event:`/`data:` stream with a `done` frame carrying a whole turn result. |
| `LangGraphRuntime` | **No.** §9.3 is a custom `bind_tools` loop, not a LangGraph server. |
| `LocalRuntime` (`ChatModelAdapter`) | Workable, but it wants to own message state and re-run turns. Our transcript is also restorable from Redis (`GET /chat/history`) and mutated by *server-pushed* events (U50) — two writers into one store it thinks it owns. |
| **`ExternalStoreRuntime`** | **Yes.** We hold the message array; assistant-ui renders it. This is the only option where "a system event mutates an existing message part in place" (U50) is a normal state update rather than a fight with the runtime. |

Hold messages in a `jotai` atom (already a dependency) keyed by `thread_id`. `streamChat()` from
`core/http/sse.ts` writes into it; the runtime reads from it.

### 1.2 The tool-call seam — and the timing consequence nobody has written down

`ai-chat-primitives.md` is right that `MessagePartPrimitive` is what makes "the interface renders receipts,
it never reasons" architectural. But the *live* stream does not deliver tool results incrementally:

```
event: start   → thread_id, session_id
event: status  → { tool: "find_feasible_slots" }      ← NAME ONLY. no args, no result.
event: token   → { content: "Three options are open " }   ← LLM prose, streaming
event: token   → { content: "right now. Nothing is held yet." }
event: done    → { response, tool_calls: [ {name, args, result, ...} ], ux_state, ... }
                                              ↑ the ONLY place option data appears
```

**Consequence, stated plainly because it changes the screen:** the assistant's sentence *"Three options are
open right now"* renders before the three option cards exist. There is a window — the length of the LLM's
closing text generation — where the driver reads a claim with nothing under it.

Three ways to handle it; **only the first is safe and it is what this spec assumes**:

1. **Hold text parts in a pending buffer until `done`, and commit text + tool parts in one paint.** Costs
   the streaming feel. Keeps the transcript honest at every instant. The `status` frame drives the thinking
   indicator, so the driver is not staring at nothing (`flows-and-states.md` § *Assistant thinking*: 400ms
   delay, 8s "Still working on this…").
2. Stream text, then pop cards in after. Rejected — this is the mis-promise shape this product exists to
   avoid, in miniature.
3. Change the backend to emit a `tool_result` frame. The right long-term answer, out of E5.1's scope, and a
   fork for the owner (§6, Fork C).

`ux_state` from `done` is the branch key, not the prose:

| `ux_state` | Screen |
|---|---|
| `confirmation_required` | Flow 4's preview → confirm gate. Quick replies from `confirmation` payload. |
| `clarification_required` | Screens 22A/23A — disambiguation with quick replies. |
| `capability_not_enabled` | Screen 25C/26 refusal copy. |
| `persisted_success` | The write landed — chip hard-swaps (U75). |

### 1.3 Primitive map, with what each actually renders

| Primitive | Renders | Notes |
|---|---|---|
| `ThreadListPrimitive` / `ThreadListItemPrimitive` | Screen 1 thread list | **Ordering is ours, not the library's** — `screens.md` §1: running-TTL first (soonest deadline), then recency, then resolved. Sort in the store before handing it over. |
| `MessagePrimitive` | U47's three tiers + centred system notices | Tier from `chat_messages.sender_type`. |
| `MessagePartPrimitive` | Option cards, eligibility answer, receipt | §1.4's mapping table. Never text parsing. |
| `SuggestionPrimitive` | Quick replies (U49) | Sends the **literal chip text as a normal driver message** (`01-driver-chat/components.md` §3). Not a special type. |
| `ComposerPrimitive` | The input | **Never disabled**, incl. offline (`components.md` §3). |
| `ErrorPrimitive` | `error` frame → screens 27A/27C | Copy from `voice-and-tone.md`. |
| `AssistantSidebar` | — | **Not on this surface.** Ops only (U57). |

**Styling:** none of assistant-ui's default CSS. Behaviour and a11y only (`ai-chat-primitives.md`
§ *Styling*). Consume our tokens through the classes in §2–§3.

**Virtualisation** at >50 messages (`accessibility.md` § *Low-end device performance*) — verify 0.15.x
provides it before relying on it; U52's lesson was that a library's headline capability may not be in the
version you install.

### 1.4 `find_feasible_slots` → option card: the field mapping

From `backend/app/scheduling/feasibility.py` (`FeasibleSlotOption`, `FeasibleSlotsResult`), not invented:

| Card element | Server field | Note |
|---|---|---|
| Dock | `dock_code` | Never `dock_id` — that is the internal UUID. |
| **Date** | **`slot_local_date`** | ⚠ **Not the date component of `slot_start_ts`.** The ISO timestamps carry a UTC offset, so `2026-08-16T19:00+00:00` is **17 Aug** in `Asia/Kolkata`. The backend added `slot_local_date` for exactly this and says so inline. Using the wrong one is a literal wrong-day booking. |
| Time range | `feasible_start_ts` – `feasible_end_ts` | En dash. `--font-data`, `tabular-nums`. Facility-local (U64). |
| Payload identity | `recommendation_id` + `slot_id` + `dock_id` | Carried, never displayed. U16: **no ordinal in the DOM.** |
| Selectability | `options_are_reserved: false`, `option_status: "DISPLAYED_NOT_RESERVED"` | This is `SHOWN`. The server is explicit that display reserves nothing. |
| **Differentiator line** | **NO SOURCE — see §6 Fork A** | `ranking_factors` gives raw numbers (`wait_after_eta_minutes`, `fit_slack_minutes`, `lateness_minutes`, `dock_match`). There is no `"soonest"` / `"no waiting"` / `"most buffer"` string anywhere in the backend (grepped). The design forbids the interface computing it. |
| Outcome branch | `outcome` ∈ `FEASIBLE` / `NO_SAME_DAY_SLOT` / `NO_FEASIBLE_SLOT` | Maps to screens 4, 19, 20. **Branch on `outcome`, never on `escalation is None`** — the backend says so inline: `NO_SAME_DAY_SLOT` returns options *and* no escalation. |
| Escalation reference | `escalation` | Screen 20's `ESC-…`. |
| Receipt stamp | `policy_version` | `components.md` §4: always stamp it. |

**Name mismatch to fix in one direction or the other:** the design says `score_terms` throughout; the
backend field is `ranking_factors`. Alias at the boundary; do not rename either side in E5.1.

---

## 2 · The promise-state chip and the countdown

The two components the brief singles out. Both were rendered and measured, not read — §5.3 lists what that
found. This section is the corrected build target.

### 2.1 Chip — anatomy and the four states

`components.md` §2 + `color.md`. Driver surface is **`filled`, always** (`accessibility.md` § *Contrast
under glare*). Four redundant encodings (U14): **icon · label · border treatment · colour**.

```tsx
// src/features/driver/components/promise-chip.tsx
const chip = cva(
  'inline-flex items-center gap-1.5 rounded-sm px-2.5 py-1 ' +
  'text-label uppercase whitespace-nowrap',           // text-label = 12px/600/0.04em
  { variants: { state: {
    shown:     'bg-state-shown-bg     text-state-shown-text     border border-state-shown-border',
    held:      'bg-state-held-bg      text-state-held-text      border-2 border-dashed border-state-held-border',
    pending:   'bg-state-pending-bg   text-state-pending-text   border-2 border-state-pending-border',
    confirmed: 'bg-state-confirmed-bg text-state-confirmed-text border-2 border-state-confirmed-border',
  } } },
)
```

| State | Icon (`lucide-react`, 14px, 2px stroke) | Label | Countdown |
|---|---|---|---|
| `SHOWN` | **`list`** | `SHOWN` (or the state-line copy, §2.5) | none |
| `HELD` | `timer` | `HELD` | **mandatory** |
| `PENDING_CONFIRMATION` | `clock-fade` | `PENDING CONFIRMATION` — **never abbreviated**, wraps to two lines instead | **mandatory** |
| `CONFIRMED` | `circle-check` | `CONFIRMED` | none |

Import per-icon, never the barrel (`00-foundations/implementation-spec.md` §3).

**Rules that are code, not review notes:**

- **Hard-swap, never morph (U75).** Remount on state change — a `key={state}` on the chip, at
  `--d-instant`. Do not animate border-colour or width between states. The one permitted exception is entry
  into `CONFIRMED`: a single non-celebratory border settle, no scale, no spring.
- **Only this component may use state hues** (`components.md` §2). Not a card, not a banner, not a bar.
- **Never a feedback colour in the state slot.** A green *banner* means an action succeeded; a green *chip*
  means `CONFIRMED`.
- **Layouts tolerate ~30% text expansion and grow vertically** (U31, `accessibility.md`). No fixed height —
  `PENDING CONFIRMATION` already wraps at 340px.

### 2.2 Countdown — six treatments, and the two the mockup does not have

`components.md` §3. `useCountdown()` already returns `remainingMs`, `threshold`, `expired`, `live`.

| Remaining | Colour token | Weight | Extra |
|---|---|---|---|
| > 50% | the state's own text token | 400 | — |
| **20–50%** | **`--color-urgent-mid`** (`amber-600`) | 400 | see the warning below |
| < 20% | `--color-urgent` (`red-600`) | **600** | **`HELD` only:** border pulses 1 Hz |
| < 10s | `--color-urgent` | 600 | haptic at 10s and 5s |
| **0** | `--color-expired-fg` on `--color-expired-bg` | 400 | **component is replaced in place by the expiry state — never removed** |
| paused (U67) | `neutral-500`, icon → `pause`, **numeric hidden**, reason text instead | 400 | planner-side; not reachable on this surface in v1 |

> ⚠ **The 20–50% amber band is invisible on a `HELD` chip and this is measured, not theoretical.**
> `--color-state-held-text` is `amber-700 #B45309`; `--color-urgent-mid` is `amber-600 #D97706`. On the one
> state where a 90-second clock makes the mid-band matter most, the "urgency has begun" signal is a
> one-step shift inside the same hue that the chip is already painted in. Traced live: at `0:44` of 90 the
> rendered colour was `rgb(180,83,9)` — indistinguishable from rest. **Fork B (§6).**

**Implementation requirements, all from `components.md` §3:**

- `--font-data` + `tabular-nums`. Verified working in the mockup (`0`/`1`/`8` all 66px per ten glyphs).
- **Never animate the digit change.** Ticks read as discrete.
- Server time authoritative via the provider's measured offset. Never bare `Date.now()`.
- Offline: **hold at last known**, do not free-run (`edge-cases.md` §10). The provider's `setLive(false)`
  does this; wire it to the connection state.

### 2.3 The ARIA collision — two politenesses inside one element

This is the item most likely to be built wrong, because **each half is correctly specified in a different
file and nothing states that they collide**:

| Element | `accessibility-behaviour.md` politeness matrix |
|---|---|
| Promise-state chip transition | **`assertive`** — the new state, once, on the hard-swap |
| Countdown | **`polite`, throttled** — only 50%, 20%, 10s, expiry. Never per-tick |

`components.md` §2's anatomy puts the countdown **inside** the chip, and §2 also says *"always
`role="status"`"*. A `role="status"` element whose text node is rewritten every second **is a per-second
live region** — precisely what §3 forbids. The mockup demonstrates the failure: its 1 Hz tick rewrites
`.t.textContent` every second, and one of its five countdowns sits inside a `role="status"` chip.

**Build it as three nodes, not one:**

```tsx
<span className={chip({ state })} key={state}>
  <Timer size={14} aria-hidden="true" />
  <span aria-hidden="true">HELD</span>
  <span aria-hidden="true" className="font-data tabular-nums">{label}</span>

  {/* 1. state transitions — assertive, fires once per hard-swap */}
  <span role="alert" className="sr-only">{`Held. ${spokenRemaining}.`}</span>

  {/* 2. countdown thresholds — polite, fires 4 times per hold, never per tick */}
  <span aria-live="polite" className="sr-only">
    {threshold !== 'none' ? spokenThreshold : ''}
  </span>
</span>
```

The visible content is `aria-hidden`; the two live regions carry the announcements at their own
politeness. Gate region 2 on `threshold` **changing**, not on `now`.

Spoken form uses words, not the glyph string: *"Held. One minute twenty-four seconds remaining."*
(`accessibility.md` § *Screen reader*).

### 2.4 The `HELD` pulse — no keyframe exists, and reduced motion *replaces* it

`theme.css` has exactly one keyframe (`shim`). E5.1 adds:

```css
@theme { --animate-held-pulse: held-pulse 1000ms var(--e-in-out) infinite; }
@keyframes held-pulse {                       /* opacity only — motion.md */
  0%, 100% { border-color: var(--color-state-held-border); }
  50%      { border-color: var(--color-urgent); }
}
```

Applied **only** below 20% remaining, **only** on `HELD` (`components.md` §3), and **never** on `PENDING` —
the mockup's own note is right that a fifteen-minute element pulsing for three minutes is intolerable.

**Under `prefers-reduced-motion` the pulse is replaced, not removed** (`motion.md`, `accessibility.md`):

```css
@media (prefers-reduced-motion: reduce) {
  .held-expiring { animation: none; border-color: var(--color-urgent); border-width: 2px; }
  .held-expiring::after { content: " · expiring"; }   /* externalise for i18n */
}
```

**Do not ship a blanket `* { animation: none !important; transition: none !important }`.** The mockup has
one (`mockup.html:299`) and E5.0 already called that pattern wrong for the app: it would silently delete an
expiry warning for a driver who set an OS preference. Per-motion, per `motion.md`'s table:

| Motion | Reduced-motion behaviour |
|---|---|
| Countdown ticks | **Unchanged** — this is data |
| TTL colour warming | **Unchanged** — already instant |
| `HELD` border pulse | **Replaced** — solid high-contrast border + "expiring" label |
| Typing dots | Replaced by a static `Working…` label |
| Card mutation on withdrawal | Instant |

### 2.5 The persistent state line (`01-driver-chat/components.md` §6)

Header row two, present at all times, tapping scrolls to the establishing message.

| State | Content |
|---|---|
| none | **hidden entirely** — header is one row |
| `SHOWN` | `Options open · nothing held` |
| `HELD` | `⏱ HELD 1:24` |
| `PENDING_CONFIRMATION` | `◷ PENDING · decision by 11:57` |
| `CONFIRMED` | `✓ CONFIRMED · Dock D1 · Tue 4 Aug 13:00` |

Truncate **dock/date before the state word**. `PENDING CONFIRMATION` never abbreviates.

⚠ Two unresolved things here, both pre-existing and both now measured: **F2** (56px cannot hold two rows —
the mockup's header is two rows with no asserted height) and **F3** (no header treatment exists for an
`ESCALATED`/closed thread; the mockup puts `Escalated · ESC-4471` *inside a promise-state chip*, which
`components.md` §2 forbids since `ESCALATED` is not one of the four states). §5.2.

---

## 3 · The 28 screens → components

28 screens, rendered as **43 artboards** across **41 phone frames** in `mockup.html` (the eight hero
artboards are unnumbered; the numbered set runs 2 → 28 with letter suffixes). Copy is authoritative in
`stitch-prompts.md` at the prompt number given. Artboard line numbers are the `<div class="cap">`.

**Legend for Build:** 🟢 buildable today · 🟡 buildable, one open fork · 🔴 blocked by §5.1.

### A · Thread list (screens 1–3)

| # | Screen | Line | Components | Build |
|---|---|---:|---|:--:|
| 1 | Thread list — home | 621 | `ThreadListPrimitive`, thread card, promise chip (`filled`), priority marker (`components.md` §5), countdown | 🟡 F6 |
| 2 | Thread list — loading | 832 | `skeleton` + `animate-shim` (1600ms, **not** `animate-pulse`), cards shaped like final layout | 🟢 |
| 3A | Empty — caught up | 863 | `EmptyState`, `circle-check-big`, **no CTA** (U74 — this is a good state) | 🟢 |
| 3B | Empty — nothing yet | 890 | `EmptyState`, `inbox`. **Distinct from 3A; the distinction is a server-side history check, never `count === 0`** | 🟢 |

Ordering: running TTL (soonest first) → recent activity → resolved. Sort in the store (§1.3).
Single-thread shortcut: exactly one active thread and no resolved history → land in the conversation; Back
still reveals the list.

### B · The four promise states in conversation (screens 4–7)

| # | Screen | Line | Components | Build |
|---|---|---:|---|:--:|
| 4 | Conversation — `SHOWN` | 653 | Transcript, option cards ×3, composer, state line | 🟡 Fork A |
| 5 | `HELD` — 90s live | 679 | Chip `held` + countdown + pulse, option card `held`, two-action quick replies | 🔴 §5.1 |
| 6 | `PENDING CONFIRMATION` — 15 min | 926 | Chip `pending` + countdown, card `Requested · decision by …`, **no quick replies** | 🟡 §5.3-R7 |
| 7 | `CONFIRMED` | 801 | Chip `confirmed`, arrival instructions, reference | 🟢 |

**Screen 7 is the only screen in the product permitted finality language or a success treatment.**

### C · Transcript mechanics (screens 8–11)

| # | Screen | Line | Components | Build |
|---|---|---:|---|:--:|
| 8 | Message tiers + takeover divider | 977 | `MessagePrimitive` ×3 tiers + centred `SYSTEM`; divider is permanent, not dismissible | 🟢 |
| 9 | Option card — full state matrix (8 states) | 1031 | Default / Pressed / Committing / Held / Lost / Withdrawn / Disabled-offline / Superseded | 🔴 (Held) + F8 |
| 10A | Composer + quick replies — five states | 1088 | `ComposerPrimitive`, `SuggestionPrimitive` | 🟡 F7 |
| 10B | Keyboard open | 1137 | `env(safe-area-inset-bottom)`, 16px input (no iOS auto-zoom), scroll anchored to **latest** | 🟢 |
| 11A | Assistant thinking | 1174 | 400ms delay → dots; 8s → "Still working on this…"; driven by the `status` frame | 🟢 |
| 11B | Transcript skeleton | 1206 | 3 alternating bubble shapes | 🟢 |
| 11C | Scroll to latest | 1230 | Floating pill, >1 screen from bottom, counts **messages not events** | 🟢 |

**Never auto-scroll while the driver is reading history.** Both chat checklists call this the common bug.

### D · Read-only answers and profile (screens 12–14)

| # | Screen | Line | Components | Build |
|---|---|---:|---|:--:|
| 12A | Eligibility answer — passes | 1263 | Per-invariant rows from `explain_slot_eligibility`, `check`/`x` **plus** colour, templated verdict | 🟡 F9 |
| 12B | Eligibility answer — fails | 1301 | Failing row red; **passing rows stay neutral, never green** | 🟡 F9 |
| 13 | Profile | 1339 | Read-only identity/vehicle (TMS-owned, §1), notifications re-entry, language (no picker, U31), theme | 🟡 F10, F11 |
| 14A | Push-permission priming | 1378 | Pre-permission explainer | 🟡 F4 |
| 14B | Push denied — consequence stated once | 1404 | Status line + Profile re-entry; re-ask only after a genuinely missed event | 🟢 |

**Every invariant renders, not only the failing one** — a driver who sees only "no" learns nothing
actionable. Read-only: no exception row, no thread-state change, no dedupe key.

### E · The negative paths (screens 15–24) — *the real product*

| # | Screen | Line | Components | Build |
|---|---|---:|---|:--:|
| 15 | Hold lapsed (`HOLD_LAPSED`) | 706 | Card mutates **in place**, struck through, system notice + `[ Find options again ]` | 🔴 §5.1 |
| 16A | Pending expired (`PENDING_EXPIRED`) | 1443 | System notice naming the release **and** the escalation; state line clears | 🟢 |
| 16B | The same event as a push notification | 1468 | High-priority push, same templates as in-app | 🟢 |
| 17 | Lost the race (`SLOT_CONFLICT`) | 1491 | Lost card struck through in place; fresh set below; **never blames the driver**; no penalty haptic | 🟢 |
| 18 | Option withdrawn (`OPTION_WITHDRAWN`) | 1520 | **Only the affected card mutates** (U50); siblings untouched | 🟢 |
| 19 | No same-day slot (`NO_SAME_DAY_SLOT`) | 727 | **Not an escalation.** Tomorrow's cards — **the date is load-bearing**. Names the blocking reason. Offers escalation rather than withholding it | 🟢 |
| 20 | No feasible slot → escalation | 1553 | Reference + promise of contact. **No cards, no retry** | 🟢 |
| 21 | Human takeover (`HUMAN_JOINED`) | 749 | Permanent divider, avatar + name + role, heavier border; assistant stops auto-replying | 🟢 |
| 22A | Ambiguous shipment — disambiguation | 1596 | Human descriptors never IDs; quick replies | 🟢 |
| 22B | After two failed attempts | 1627 | Escalate as `AMBIGUOUS_SHIPMENT`. **Do not loop** (§7.2b's ladder) | 🟢 |
| 23A | Low-confidence ETA — clarification | 1657 | Quick replies; **never derive an ETA from a delay duration** | 🟢 |
| 23B | Risk framed as a choice, not a hidden warning | 1690 | The driver prices their own risk | 🟢 |
| 24 | Offline | 774 | Transcript + confirmed details readable; **cards disabled visibly with a reason**; composer **stays enabled**; countdown holds; staleness marked | 🟢 |

### F · Refusals and failures (screens 25–28)

| # | Screen | Line | Components | Build |
|---|---|---:|---|:--:|
| 25A | "Just confirm it" | 1732 | Copy + `[ Flag as urgent ]` | 🟢 |
| 25B | "Book 7:30 even though I arrive at 8" | 1760 | Names the failing invariant + a feasible set | 🟢 |
| 25C | Off-manifest cargo | 1792 | Copy only. No scheduling continues. Thread → `ESCALATED` | 🟡 F3 |
| 25D | "Give me that truck's slot" | 1823 | Copy + current feasible set | 🟢 |
| 26 | Refusal — safety | 1854 | **The one screen where nothing competes**: no cards, no quick replies, no suggestions. Message + how to reach a human | 🟡 F3 |
| 27A | Message failed to send | 1900 | `⚠ not sent` + inline `[ Retry ]`, text preserved, 300ms haptic | 🟢 |
| 27B | Commit failed — nothing has changed | 1933 | *"That didn't save. **Nothing has changed.**"* — the clause is load-bearing, not padding | 🟢 |
| 27C | Thread failed to load | 1960 | Skeleton → error + `[ Retry ]`, cached transcript if available | 🟢 |
| 28A | Cancelled shipment | 1995 | Refusal is the whole answer. Routes to **dispatch**, not operations | 🟢 |
| 28B | The thread-list consequence | 2026 | | 🟢 |

**Every refusal names the rule and offers a route.** A refusal with no next step drives drivers back to
phone calls, which is the failure this product exists to remove.

### G · Cross-cutting behaviour

**Idempotency (U70) — state it per action, do not assume the loading state covers it.** Every
capacity-affecting call carries a key. The backend already has `chat_mutation_idempotency_key`
(`tools.py:172`) and `client_message_id` on `ChatRequest`. Bind: option tap → `recommendation_id + slot_id`;
message send → client-generated UUID, reused verbatim on Retry (this is what makes screen 27A safe and
screen 11's duplicate invisible).

**Haptics (U21)** — `navigator.vibrate`, degrades silently, **never the only signal**:
tap `10` · hold granted `[10,40,10]` · 10s `[200]` · 5s `[200,100,200]` · lapsed `[400]` ·
confirmed `[10,40,10,40,10]` · send failed `[300]`. No audio anywhere.

**Push (U17 revised)** — web push only; SMS dropped. Four events at high priority: pending expired,
planner rejected, dock down / option withdrawn, and hold lapsed. Deep-link to the **thread**, never the
list. Push copy uses the same templates as in-app — a notification that says something different is a
second source of truth. **Accepted gap, recorded not solved:** a driver who never granted push (or is on
iOS without home-screen install) gets no proactive alert.

---

## 4 · What E5.1 adds to the design system

Everything else is already in `theme.css`. Keep additions this small.

### 4.1 One keyframe

`--animate-held-pulse` + `@keyframes held-pulse` (§2.4). The only motion this surface adds.

### 4.2 Bottom-nav tokens — the driver shell exception (closes F5)

The driver has no icon rail; `spacing-and-layout.md`'s shell model does not cover a two-item bottom nav, and
`theme.css` has no tokens for one. Component-scoped per `tokens.md`'s tier rule (U85) — **not** in `@theme`,
because nothing else in the product has a bottom nav:

```css
/* src/features/driver/components/bottom-nav.css */
.driver-nav      { block-size: 56px; }                       /* accessibility.md floor */
.driver-nav-item { color: var(--color-subtle-foreground); }  /* text-tertiary */
.driver-nav-item[aria-current='page'] { color: var(--color-primary); font-weight: 600; }
```

Derived from the mockup's rendered values, matching the design's own F5 note. `aria-current="page"`
carries the state for AT — colour is not the only signal.

### 4.3 Density

`comfortable`, set **once** at the driver route root (`data-density="comfortable"`), giving `--tap: 44px`.
Never per component, never a user preference.

### 4.4 PWA

`vite-plugin-pwa` is installed but unwired. Manifest `theme_color` should be **`#F8FAFC`** (`surface-base`)
or `#FFFFFF` (`surface-raised`) — E5.0 flagged that the mockup's `#E2E8F0` is the *board's* background, not
an app surface. This is the colour of the phone's status bar for the driver.

---

## 5 · Readiness call

**Verdict, revised 2026-08-27: BUILD-READY. 24 of 28 screens ship now; 4 are flagged behind issue #53.
Zero open forks. Nine rendering defects fixed and re-measured. Two escalated findings closed. One
foundations contradiction resolved at source.**

Nothing here says the design was wrong. The design is unusually complete. What follows is the difference
between a complete design and a buildable one — and, from §5.3 onward, what was actually changed to close
that difference.

### 5.0 Fix-pass scoreboard — every item re-measured, none assumed

Method throughout: headless Chromium over CDP. Computed styles and box model across all **41 phone frames**,
contrast computed from rendered `rgb()` values, and a **53-second live trace** of a 46-second hold through
every countdown band. "Before" numbers are from the audit pass; "after" from the same probes re-run.

| # | Defect | Before | After | Verified by |
|---|---|---|---|---|
| **R1** | Board auto-switched to dark on OS preference | `--state-shown-bg: rgb(30,41,59)` (dark) | `rgb(248,250,252)` (light) · **zero** `@media (prefers-color-scheme)` rules remain | Default render, no theme forced |
| **R2** | 20–50% amber band never fired | one threshold only; `0:44`/90 rendered rest colour | fires at 50% → `rgb(217,119,6)` = `amber-600` | Live trace, t=21s |
| **R3** | Expiry state never rendered — countdown restarted | `0:09 → … → 0:45` | `0:00` → `rgb(100,116,139)` = `neutral-500`, weight 400, `.expired` | Live trace, t=44s |
| **R4** | Chip and option card disagreed on urgency | divergent from t=35s | **0 mismatch frames across all 38 samples** | Paired live trace |
| **R5** | Caption claimed a pulse; zero `@keyframes` existed | `animation-name: none` always | `held-pulse` fires exactly at the `<20%` band, clears at expiry | Live trace, t=35s |
| **R6** | Held card's siblings used `dead` (struck through) beside "Choose a different one" | 5 dimmed cards, 2 with **no status line** | siblings render as plain selectable cards; **3 dimmed cards, all 3 with a full-opacity status line**. **The missing matrix row is now written too** — `01-driver-chat/components.md` §2 gained a *"Sibling of a held card"* state plus the rule explaining why a hold must not dim its alternatives (owner-approved 2026-08-27), so the absence that allowed the defect is closed, not just the instance | Computed opacity + text |
| **R7** | `PENDING` chip carried two competing times, orphaned middot | `PENDING CONFIRMATION 12:44 · DECISION BY 11:57` | chip: `Pending confirmation 12:45`; deadline moved beside it | Rendered label vocabulary |
| **R8** | Back button 18×6.9 against its own 48×48 floor | 7/7 violations | **48×48, 0/7** — plus composer send 38→44 (0/34) | Box model, all frames |
| **R9** | Chip borders failed WCAG 1.4.11 | shown **1.42**, held **2.05** | shown **4.55**, held **3.04**, pending 3.52, confirmed 3.60 — **all pass** | Computed contrast |
| **F1** | Text below the surface's stated 14px floor | **76 of 426** nodes, down to 9px | **9 of 429**, all of them avatar glyphs — a stated, `aria-hidden` exclusion | Computed font-size |
| **F7** | Quick-reply chips below their 44px floor | min 34px, 4/15 | **min 44px, 0/15** | Box model |
| **F5** | Bottom-nav tokens undefined | — | **Closed** — §4.2, component-scoped per U85 | — |

**Bonus fix, same pass — the blanket reduced-motion kill (§2.4).** `mockup.html` carried
`*{animation:none!important; transition:none!important}`, which E5.0 had already called wrong for the app:
it silently deletes the expiry warning for anyone who set an OS preference. Replaced with per-motion rules
and **verified under emulated `prefers-reduced-motion: reduce`**, driving a real 46-second hold into its
`<20%` band:

| What `motion.md` / `accessibility.md` require | Measured |
|---|---|
| Countdown ticks **unchanged** — this is data | `0:08`, `rgb(220,38,38)` — unchanged ✓ |
| Pulse **removed** | `animation-name: none` ✓ |
| …and **replaced**, not just dropped | `border-style: solid`, `border-color: rgb(220,38,38)` ✓ |
| An explicit label so the warning survives as text | `::after` content `" · expiring"` ✓ |

**No regressions:** 43 artboards / 41 phones unchanged; `tabular-nums` and equal-width digits still hold;
**0 of 123 interactive elements are unhittable** (the E5.0 dead-toast class of defect does not appear here);
**0 real `@media (prefers-color-scheme)` rules and 0 `matchMedia` calls** remain in the file.

### 5.1 🔴 BLOCKER — `HELD` has no backend, and `01-driver-chat/` does not know

Found by the standing rule's step 1: cross-check the persona row's jobs against the tool catalog. Same
mechanism that found §7.5.5 and `block_dock`. Four independent confirmations in the live codebase:

| Evidence | Source |
|---|---|
| `confirm_held_slot` is **deliberately not built**; the allowlist binds 11 of §7.5.4's 12 | `tools.py:30-50` |
| `appointments_appointment_status_check` has **no `HELD`**; `dock_occupancy` has **no `state`, no `expires_at`** — verified against production 2026-08-23 | `expiry.py:89-103` |
| The M8 sweeper's `HELD` leg returns `supported: false` with a reason string, deliberately not a zero | `expiry.py:148-160` |
| `carrier_reads` **refuses** `SHOWN`/`HELD` filters rather than silently returning empty | `carrier_reads.py:39-54` |
| `request_slot` inserts **directly at `PENDING_CONFIRMATION`** | `allocation.py:1167` |

**The live promise lifecycle is three states, not four:** `SHOWN → PENDING_CONFIRMATION → CONFIRMED`.

Why this is a UI-blocking finding and not merely a backend note:

- `flows-and-states.md` § *The two-step commit (D2)*: *"The UI must never collapse these into one action to
  save a tap."* Today's backend **has already collapsed them**, and the UI cannot un-collapse a state the
  server cannot hold.
- The 90-second countdown, the `HELD` pulse, the 10s/5s haptics, `HOLD_LAPSED`, and the
  `hold_expiry_vs_confirm` race all hang off a state that cannot exist.
- Screens **5, 9 (Held column), 15**, and the `HELD` half of **1** are not implementable end-to-end.

**Not a UI decision to make.** Options are (a) land the D2 columns from `SOLUTION_DESIGN.md` §0.8 +
`confirm_held_slot` first, or (b) ship E5.1 with the `HELD` path built and behind a flag against a stub.
**§6 Fork D.** Do not silently ship a two-tap UI over a one-step backend — that is a `HELD` chip that is
really a booking, which `components.md` §2 calls a broken promise in the business sense.

### 5.2 The design's own 12 flagged gaps — status after measurement

`stitch-prompts.md` § *Flagged gaps and ambiguities* raised F1–F12 and resolved none. Measuring the render
confirms nine, escalates two, and closes one.

| # | Gap | Status now |
|---|---|---|
| **F1** | 14px floor vs. `text-sm`/`text-micro` in the surface files | **CONFIRMED AND WORSE, THEN FIXED.** Audit found **76 of 426** text nodes inside phone frames below 14px, down to 9px — and **the chip at 11px**, i.e. the most important component on the surface was the third-smallest text on it. **18 rules raised in the fix pass; now 9 of 429**, all of them avatar glyphs. Those are a **stated exclusion, not an oversight**: an avatar initial is a non-text graphic, it is now `aria-hidden`, and the sender's name is spelled out beside it at 14px, so nothing is carried by the glyph alone. Board chrome (`.cap`/`.note`/`.ref`/`.foot-note`) was deliberately left alone — it is the reference board's annotation layer, not driver-facing UI. |
| **F2** | Conversation header height unstated | **Resolved as a side effect of R8.** The header row is now `min-height:48px` to hold a 48×48 back button, so a two-row conversation header is **48 + 48 + 12px padding**, not the 56px the spec asserts for a header it draws two rows inside. |
| **F3** | No header treatment for `ESCALATED`/closed threads | Confirmed. Mockup renders it **inside a promise-state chip**, which §2 forbids (`ESCALATED` is not one of the four states, and the chip is the only component allowed state hues). Affects screens 20, 21, 25C, 26, 28. |
| **F4** | No push-notification preview on the priming screen | Confirmed absent. Highest-leverage item on that checklist. |
| **F5** | Bottom-nav tokens undefined | **CLOSED** by §4.2 — component-scoped per U85's tier rule (not in `@theme`, because nothing else in the product has a bottom nav), derived from the mockup, matching the design's own note. The 56px height floor is now enforced in the mockup too and measures 56px across all 12 instances. |
| **F6** | Unread marker (2px left inset) and priority marker (3px left edge) collide | Confirmed unspecified. Mockup never draws them together. **This is the exact hazard `components.md` §7 names for the rail** — two thin vertical bars competing for one edge — recurring on a different component. |
| **F7** | Quick-reply heights irreconcilable (48px region vs 44px chips) | **CONFIRMED BY MEASUREMENT, THEN FIXED.** Was 4 of 15 chips at 34px against a stated 44px floor; now **min 44px, 0 of 15**. F7's own reading is upheld: the **chip** carries the floor and the region is described by its padding, because 44 + `comfortable`'s padding cannot fit inside 48. |
| **F8** | Four option-card states share 40% opacity | **CONFIRMED AND WORSE, THEN PARTLY FIXED BY R6.** Audit found all 5 dimmed cards at exactly `opacity: 0.4` with **2 carrying no status line at all** — literally indistinguishable (F8 predicted this for Superseded only). R6 removed the two that should never have been dimmed; **the remaining 3 all carry a full-opacity status line**, and `dead` (struck through) is now visually distinct from `off` (not struck through). **Still open in principle:** if Superseded is ever rendered, it needs its own status line rather than inheriting a bare 40%. |
| **F9** | Eligibility card's green step unstated (`green-600` fails AA at 3.8:1) | Confirmed. Use `--color-success-fg` (`green-700`, 5.6:1). The token exists; the surface file should name it. |
| **F10** | Theme row behaviour undefined; `accessibility.md` requires a warning before dark | Confirmed. Copy, form and dismissibility all unspecified. Now urgent — see §5.3-R1. |
| **F11** | Sign-out has no friction tier under `components.md` §19's three-tier model | Confirmed. Signing a driver out mid-exception is what `auth-and-scoping.md` calls a product failure. |
| **F12** | Content padding 24px (foundation) vs 12px (mockup) | Confirmed. Foundation wins. |

### 5.3 Nine rendering defects — measured, not inspected · **ALL FIXED 2026-08-27**

Method per E5.0 §4.7: headless Chromium, computed styles and box model via CDP, plus a live trace of the
countdown through its thresholds. **None of these is visible in the markup** — which is the point of the
method, and why the fix pass re-measured rather than re-read. Scoreboard in §5.0; the diagnoses below are
kept because *how* each was found is what stops it recurring. Every fix carries a dated inline comment in
`mockup.html` at the site it changes.

**R1 · The driver mockup auto-switches to dark on OS preference.** Three `@media (prefers-color-scheme: dark)`
blocks survive (`mockup.html:56, 334`) and the JS resolver falls back to `matchMedia` (`:2097`). The
headless render came up **dark by default** — measured `--state-shown-bg: rgb(30,41,59)`. E5.0 removed
exactly this from `mockup-shared-shell.html` as a U69 violation (its §4.1.4) and did not sweep the surface
mockups. **On this surface it is worse than a U69 violation**, because `accessibility.md` states light
"cannot be overridden to dark without a warning" — dark UI in direct sunlight on a cheap LCD is unreadable.
The reference board currently defaults to the one theme this surface forbids. Fix: delete both media
blocks, resolver returns `'light'`.

**R2 · The `20–50%` countdown band never fires.** The mockup's tick has one threshold
(`c.t <= c.max*0.2`), not two. Traced: `0:44` of 90 (49%) rendered `rgb(180,83,9)` — the rest colour. See
also §2.2: even correctly implemented it is near-invisible on `HELD`.

**R3 · The expiry state is never rendered.** Traced across a full cycle: `0:09 → … → 0:45`. The mockup
loops back to max. `components.md` §3 requires the component be **replaced in place by the expiry state**
(`--color-expired-fg`), not removed and not restarted. There is no artboard of a countdown at zero.

**R4 · `.urgent` reaches the chip's countdown but not the option card's.** At the *same instant* on the
same 46-second hold, measured: chip `rgb(220,38,38)` (red-600, urgent) and the card's inline
`Held for you · 0:09` `rgb(180,83,9)` (amber-700, rest) — because the rule is scoped `.chip .t.urgent` and
the card's copy carries a competing inline `style`. **Two renderings of one hold showing different urgency
simultaneously, on the surface's most consequential component.** This is the defect class the brief
predicted; it is invisible in markup and only appears ~37 seconds into a live render.

**R5 · Zero `@keyframes` exist, yet artboard 3's own caption claims *"the chip's dashed border pulses."***
Measured `animation-name: none` on all five `HELD` elements. The board asserts a behaviour it does not
have, and the reduced-motion *replacement* consequently has no rendered reference either.

**R6 · Sibling option cards during a hold use `class="opt dead"` — strikethrough + 40%.** In artboard 3,
D4 and D2 render struck through while a quick reply directly beneath says **"Choose a different one."** The
interface simultaneously tells the driver those slots are dead and invites them to pick one. No state in
`01-driver-chat/components.md` §2 covers "sibling of a held card"; the nearest, *Committing*, is **dim
only, no strikethrough**. `dead` is the treatment for Lost / Withdrawn / lapsed. This is F8's collapse
doing real semantic damage, and it is only visible rendered.

**R7 · The `PENDING` chip renders two competing time expressions and wraps badly.** Screenshot: *"PENDING
CONFIRMATION `12:44` DECISION BY 11:57"* — a relative countdown and an absolute deadline meaning the same
thing, with the middot separator orphaned onto its own line above "DECISION". `01-driver-chat/components.md`
§6 specifies `◷ PENDING · decision by 11:57` (**no countdown**); `components.md` §2 marks the countdown
**mandatory**. The mockup renders both and the chip breaks. Needs one answer, not both.

**R8 · Touch targets below their own stated floors.** Measured across all 41 frames (`accessibility.md`'s
own table is the floor column):

| Element | Floor | Rendered min | Violations |
|---|---:|---:|---|
| **Back button** | **48×48** | **18 × 6.9** | **7 of 7** |
| Quick reply chip | 44 | 34 | 4 of 15 |
| Composer send | 44×44 | 38 × 38 | 4 of 34 |
| Bottom nav item | 56 | 39 | 2 of 12 |
| Option card | 64 | 64 | 0 of 34 ✓ |
| Thread card | 88 | 116.5 | 0 of 8 ✓ |

The back button is the element `accessibility.md` singles out for being *above* the floor —
*"top-left is the hardest place to hit one-handed"* — and it is the worst miss on the board.

**R9 · Chip fill contrast against the page is 1.00–1.04:1 in light theme.** Measured: `shown` 1.00,
`held` 1.01, `confirmed` 1.01, `pending` 1.04. Text contrast is fine (9.90 / 4.84 / 5.21 / 4.75, all pass
AA). Border-vs-page: `shown` **1.42** and `held` **2.05** both **failed** WCAG 1.4.11's 3:1 for non-text
(`pending` 3.52 and `confirmed` 3.60 passed).

**Resolution — and it is not the one the fork initially proposed.** I swept every step of all four ramps
looking for a tint that clears 3:1 against a near-white page while keeping 4.5:1 text. **There isn't one.**
The best any tint manages is `blue-200` at 1.36; amber tops out at 2.05 (`amber-500`) and only reaches
3.04 at `amber-600`, by which point white text is at 3.19 and fails. The only combinations that satisfy
both constraints are saturated fills with inverse text (`blue-600` 4.94/5.17, `green-700` 5.24/5.48) — and
amber has **no** such step, so `HELD` could not join them even if the others did.

So the honest conclusion is that **`accessibility.md`'s rationale was wrong, not the tokens.** A tint
cannot be "what survives glare," because glare compresses contrast toward white and a 1.01:1 tint has
nothing to lose. Re-saturating the four promise states across driver *and* gate to chase a premise that
amber cannot satisfy would be a large, hue-budget-spending change in service of a sentence.

**What was actually done, and it is the smaller and better fix:**

1. **The two failing borders were raised one ramp step** — `shown` `neutral-300 → neutral-500` (1.42 →
   **4.55**), `held` `amber-500 → amber-600` (2.05 → **3.04**). Both stay inside `color.md`'s existing
   ramps, both keep their hue family, and nothing outside this surface moves. All four states now pass
   1.4.11. The border is a genuine U14 channel, so it had to be a real signal rather than a hairline.
2. **The `filled` variant stays mandatory.** A visible tint still helps in ordinary light and costs
   nothing; it simply is not the load-bearing channel.
3. **The rationale is corrected.** What actually survives glare is (a) the **border *treatment*** — dashed
   vs 2px-solid vs 1px-solid is a *shape* difference and is immune to contrast compression, (b) the
   **icon shape**, (c) the **label text** at 4.84–9.90:1. The mockup's own artboard-3 note already said
   this correctly — *"dashed meaning temporary survives greyscale, glare and colour blindness"* — so the
   file contradicted itself, and the caption was the half that was right.

**One thing measurement *retracted*:** the chips' `textContent` reads sentence case ("Held", "Pending
confirmation"), which looked like a violation of §2's uppercase labels — but `.chip` carries
`text-transform: uppercase` and renders correctly. Caught only by screenshotting. Recorded because it is
the argument for rendering rather than reading, in the opposite direction from the other eight.

### 5.4 `web-design-guidelines` (U38 gate) — actually invoked

Skill invoked via the `Skill` tool; guidelines fetched fresh from
[vercel-labs/web-interface-guidelines](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md).
Applied to `mockup.html`. Findings that transfer to the build (a static reference board legitimately does
not carry app semantics — the ones below are the ones that are not that excuse):

| Finding | Detail |
|---|---|
| `mockup.html:299` — blanket reduced-motion kill | `*{animation:none!important;transition:none!important}`. Wrong for the app; §2.4. |
| Option cards are `<div>` with no role | **0 of 34** carry `role="button"` or an `aria-label`; some are `<div>`, some `<button>` — inconsistently. `accessibility.md` requires `role="button"` and a full label: *"Dock D4, Tuesday 4 August, 12:15 to 13:30, soonest. Tap to hold for 90 seconds."* **Never announce positionally** — "Option 2 of 3" reintroduces the ordinal U16 removed. |
| Promise chips: 6 of 13 have `role="status"` | §2 says always. And see §2.3 — doing it naively creates a per-second live region. |
| Messages: 0 of 54 have `role="listitem"`, inside 24 `role="log"` containers | A `log` with no list items. |
| System notices: 4 of 8 are `role="alert"`, **none** `role="status"` | `accessibility.md` splits these: `status` for informational, `alert` for hold-lapsed / option-withdrawn. Everything currently announces assertively or not at all. |
| No `touch-action: manipulation`, no `-webkit-tap-highlight-color`, no `overscroll-behavior: contain` | 0 occurrences. All three matter on a phone-first PWA: the first removes the 300ms double-tap delay on the option card — the most consequential tap in the product. |
| One `safe-area-inset` occurrence | Screen 10B has it; the composer needs it on every conversation screen. |
| Flex children lack `min-w-0`; one `text-overflow` in the file | The thread card's preview line and the load descriptor are both variable-length. |
| `Intl` not used | `accessibility.md` requires `Intl` with `en-IN` from the start (U31). All dates/times in the mockup are hardcoded strings. |
| Composer placeholder `Message` | Guideline wants a trailing `…`. **Reported, not fixed** — E5.0 took the same position product-wide (its §4.8 finding 7) and parked it for `voice-and-tone.md` to settle once. Fixing it here alone would make the boards inconsistent. |
| No `<meta viewport>`, no `lang`, no `theme-color` | Board-level; **but all three are required on the real PWA** and none exists yet (§4.4). |

**Clean:** no `transition: all`, no `outline: none` without replacement, no blocked paste, no
`user-scalable=no`, `…` used correctly (5 occurrences, zero `...`), 117 `aria-hidden` on decorative
glyphs, `focus-visible` used rather than `focus`. **No `pointer-events: none` traps** — the E5.0 dead-toast
defect does not recur here; all 123 interactive elements are hittable.

### 5.5 `checklist-design` (U34 gate) — actually invoked

Skill invoked; both bundled Chat checklists read from source (`mobile-chat.md`, `web-app-chat.md`). Audited
against source **plus** two rendered screenshots, so the "how it looks" items are answered honestly rather
than inferred.

**Chat — Mobile app** ([checklist.design/mobile/chat](https://www.checklist.design/mobile/chat)) — this is
an operational record, not a messaging app; four ⚪ rows below are deliberate.

| | Item | Why |
|---|---|---|
| 🟢 | **Keyboard push-up** — input bar rising with the keyboard so history is not obscured | Screen 10B, explicit both-platform handling + `env(safe-area-inset-bottom)`. |
| 🟢 | **Input bar** — persistent, text field + send + media, thumb-reachable | Present and bottom-most. No media button, which is the ⚪ row below, not a gap here. |
| 🟢 | **Message bubbles** — sent right, received left | Followed exactly; U47's three tiers sit inside the convention, not against it. |
| ⚪ | **Swipe to reply** | One linear operational thread — there is no message-to-message reply model to thread into. |
| ⚪ | **Long press message actions** — react, reply, copy, delete | `chat_messages` is append-only; a driver deleting their own delay report would corrupt the exception history. Copy stays available via native selection. |
| 🟡 | **Read receipts** — sent/delivered/read below the bubble | Delivery status only (`○ / ✓ / ✓✓ / ⏱ queued / ⚠ not sent`), deliberately no "read" — no human is on the other end in normal operation. `queued` is words not a glyph, so it cannot be misread as sent. 🟡 rather than 🟢 because the item asks for three tiers and this is two by design. |
| ⚪ | **Media and file sharing** | Explicitly not adopted (`ai-chat-primitives.md`); a photo-of-breakdown case is a product requirement first. |
| 🟢 | **Typing indicator** | Screen 11A — 400ms delay, 8s escalation, static label under reduced motion. |
| 🟢 | **Scroll to latest** | Screen 11C — pill above the composer, >1 screen from bottom, counts messages not events. |

**Chat — Web app** ([checklist.design/web-app/chat](https://www.checklist.design/web-app/chat))

| | Item | Why |
|---|---|---|
| 🟡 | **Message thread** — chronological, most recent at the bottom | Correct, and it never auto-scrolls while the driver reads history. 🟡 only because of §1.2: with text streaming ahead of tool results, the thread can briefly show a claim with no cards under it. |
| 🟢 | **Message input** — multi-line | Grows to 3 lines then scrolls; Enter sends, Shift+Enter newlines. |
| 🟢 | **Sender identification** — name and avatar, grouped when consecutive | U47's three tiers; 2-minute grouping window. The AI/human distinction is carried by avatar + real name + heavier border together. |
| 🟢 | **Timestamps** — relative for recent, full for older | Relative under 1h, absolute above, both list and transcript. |
| 🟡 | **Read receipts** — has the other participant seen it | Same as mobile: delivery only, deliberately. |
| ⚪ | **File and media sharing** | As above. |
| ⚪ | **Reactions** | An operational record should not have them. |

**Beyond the checklist — one observation of my own.** Neither checklist has an item for *"a message that
changes after it was sent."* U50's mutate-in-place is the single most distinctive thing about this
transcript and the thing most likely to be built as "send a new bubble" by someone working from the
checklists alone. It has no checklist row to hang on, so it needs to be a stated acceptance criterion on
the epic: **screens 15, 17, 18 must mutate the existing card, not append.**

### 5.6 The ARIA contradiction — **RESOLVED AT SOURCE 2026-08-27. `components.md` §2 was the wrong document.**

The audit raised this and stopped at "raised, not edited." The call has now been made and both files are
amended.

**The collision.** `accessibility-behaviour.md`'s matrix assigns a promise-state transition **`assertive`**
and the countdown **`polite`, throttled to four thresholds**. `components.md` §2 put the countdown *inside*
the chip, §3 makes it mandatory for `HELD` and `PENDING_CONFIRMATION`, and §2 then said *"always
`role="status"` so assistive tech announces transitions."* One element, two rows of the matrix, one live
region.

**Which document is wrong: `components.md` §2, and it was wrong in two ways at once.**

1. **Wrong politeness.** `role="status"` is implicitly `aria-live="polite"`. The matrix says the transition
   is `assertive`. §2 specified the wrong politeness for the very thing it was trying to announce — on the
   one component that must never be misread.
2. **Wrong mechanism, and this is the serious half.** A live region re-announces its **entire contents** on
   any mutation. With a per-second countdown inside it, the literal reading produces *"Held one
   twenty-three… Held one twenty-two…"* every second — exactly what §3 forbids in its own implementation
   requirements and what the matrix promotes to product-wide policy.

**Why not the matrix.** Both of its rows are independently correct and independently justified: a state
transition genuinely must interrupt, and a per-second live region is genuinely unusable. Neither can be
weakened without losing something real. §3 also already states the countdown's throttle correctly. §2's
ARIA bullet was the only one of the three that did not hold up.

**What changed:**

- **`components.md` §2** — the `role="status"` bullet is replaced by the **three-node structure**: visible
  content `aria-hidden`, one `role="alert"` sibling for the transition, one `aria-live="polite"` sibling
  gated on the **threshold changing** (not the tick). Both regions stay mounted and empty so announcements
  fire on content change rather than insertion. Full markup in the file, and in §2.3 here.
- **`accessibility-behaviour.md`** — a callout under the first two matrix rows recording that they land on
  the same element, that the chip's ARIA bullet was the error, and the general lesson worth keeping:
  **when two matrix rows resolve to one element, that element needs one live region per row, not one
  region per element.**

This is the same failure shape as E5.0's `"@ N%"` notation: two documents each internally reasonable, whose
disagreement only becomes visible when you render them together and watch them for a minute.

---

## 6 · Four forks — **ALL CLOSED BY THE OWNER 2026-08-27**

> **Decisions, and what each one means for the build:**
>
> - **A — LOCKED: the backend adds the differentiator.** A server-computed `differentiator` field joins the
>   option-set tool response; `fullstack-engineer` owns it. §1.4's "NO SOURCE" row becomes a contract.
>   This keeps U48's architectural property intact — the interface renders the receipt, it never derives a
>   ranking label from raw `ranking_factors`.
> - **B — LOCKED: fixed in the mockup, and the rationale corrected rather than the palette re-saturated.**
>   Chip at 14px, two borders raised one ramp step so all four states pass WCAG 1.4.11, and
>   `accessibility.md`'s "the fill is what survives" sentence rewritten to name the channels that actually
>   do. See §5.3-R9 for the ramp sweep that ruled out every tint.
> - **C — LOCKED: buffer until `done`, render text and tool parts together.** Matches §1.2's
>   recommendation and today's backend; no change needed. Option (b) — a `tool_result` SSE frame — stays
>   worth filing as a follow-up, but is not a blocker.
> - **D — LOCKED: ship 24, flag 4.** All non-`HELD` screens build now; screens 5, 9's Held column, 15 and
>   the `HELD` half of 1 go behind a feature flag, **default off**, until issue **#53** (the `HELD` backend
>   gap, filed 2026-08-27) lands. Explicitly **not** option (c) — collapsing to a one-step commit would
>   delete D2, and D2 is the mechanism that absorbs "two drivers pick the same slot within seconds"
>   without holding capacity hostage during deliberation.
>
> The original framing of each fork is kept below, because the options that were *rejected* are the part a
> future reader needs.

### The forks as they were surfaced

**Fork A · The option card's differentiator line has no source.**
`01-driver-chat/components.md` §2 and `screens.md` §4 both require exactly one differentiator per card —
"soonest", "no waiting", "most buffer" — read from `score_terms` and **"never computed by the interface."**
Grepped: none of those strings exists in `backend/`. `ranking_factors` gives raw numbers
(`wait_after_eta_minutes`, `fit_slack_minutes`, `lateness_minutes`, `dock_match`); `ranking_explanation`
gives four long internal-voice sentences unusable on a 340px card.
*Options:* (a) backend derives and returns a `differentiator` string per option — consistent with §7.2b's
"the interface renders receipts"; (b) an explicit, written design exception permitting the client to pick a
label from `ranking_factors` by a fixed rule; (c) drop the line for v1 and show dock + date + time only.
*Recommendation:* **(a)**. It is a small addition and it keeps the architectural property U48 exists to
protect. (b) is the one that quietly turns the interface into something that reasons about ranking.

**Fork B · The 14px floor, the 11px chip, and the invisible fill — one decision, three symptoms.**
`typography.md` and `accessibility.md` both state a hard 14px floor on this surface. Measured: 76 of 426
text nodes are below it, the chip label renders at 11px, the `filled` variant's fill measures 1.00–1.04:1
against the page, and `shown`/`held` chip borders fail 1.4.11 at 1.42:1 and 2.05:1. The design's glare
argument — *"the fill is what survives"* — is not supported by the rendered values.
*Options:* (a) enforce the 14px floor and deepen the fill a step (`amber-100`-class) so the glare rationale
becomes true, re-verifying all four pairings; (b) keep the current values and amend `accessibility.md` to
say the *text colour* is what survives glare, dropping the 14px claim to a target; (c) treat the chip as a
stated exception at `text-label` 12px and fix only the sub-12px text.
*Recommendation:* **(a)**, restricted to the chip and the operational lines. This is the one component
`components.md` calls "the most important in the product," and it is currently the third-smallest text on
its own surface with a fill that does not carry.

**Fork C · Tool results arrive only in the terminal `done` frame.**
`status` carries a tool *name* before execution; results appear only at `done`, after the LLM's closing
text has streamed. §1.2's buffer-until-`done` keeps the transcript honest but costs the streaming feel that
E4.3 (issue #33) was built to add.
*Options:* (a) buffer text until `done` — honest, slower-feeling, no backend change; (b) add a
`tool_result` SSE frame so cards render as their tool returns — best UX, backend change, outside E5.1;
(c) stream text and pop cards in after — rejected here, stated so it is not re-proposed.
*Recommendation:* **(a) for E5.1, (b) as a follow-up issue.** Worth noting (b) also makes the "Checking
your options…" status line far more useful.

**Fork D · How to ship four screens whose backend state does not exist (§5.1).**
*Options:* (a) block E5.1 until the D2 columns and `confirm_held_slot` land; (b) build the `HELD` path
fully, behind a flag, against a client-side stub, and ship the other 24 screens now; (c) redesign the
driver flow to one-step commit, matching today's backend.
*Recommendation:* **(b)**, with the flag defaulting off and a stated exit criterion. (c) should not be
chosen quietly — it deletes D2, and D2 is the mechanism that absorbs "two drivers pick the same slot within
seconds" without holding capacity hostage during deliberation.

---

## 7 · Suggested order for E5.1

1. **`features/driver/` route without `<AppShell>`.** `identity.ts` already returns `rail: null` and no
   facility scope for `DRIVER`; the shell exists to render chrome this surface does not have. Set
   `data-density="comfortable"` at the driver route root.
2. **Promise chip + countdown, with §2.3's three-node ARIA structure and §2.4's keyframe.** Before any
   screen consumes them. Test: mount at 100% and let it run to zero — assert the mid-band fires, the
   `<20%` pulse starts, the expiry state *replaces* rather than removes, and the option card's inline
   countdown matches the chip's (R2/R3/R4/R5 are all regression tests, not one-off fixes).
3. **`ExternalStoreRuntime` + the `jotai` message store + `streamChat()` wiring**, with §1.2's
   buffer-until-`done`.
4. **Option card**, all eight states — with R6 resolved (siblings-during-hold is not `dead`) and F8's four
   dimmed states given distinguishing signals beyond a shared 40%.
5. Thread list, composer, message tiers, system notices.
6. The negative paths, screens 15–28. **These are the product** (README principle 5); do not leave them to
   the end of the sprint where they get compressed.
7. PWA: manifest with `theme_color: #F8FAFC`, SW registration, push subscription + the four
   high-priority events, deep-link to thread.
8. `touch-action: manipulation`, `-webkit-tap-highlight-color`, `overscroll-behavior: contain`,
   `env(safe-area-inset-bottom)` on every conversation screen — small, and the first one is on the most
   consequential tap in the product.
9. ~~Fix the reference board's R1.~~ **Done in the fix pass — R1 through R9, F1 and F7 are all corrected in
   `mockup.html` and re-measured (§5.0).** The board implementers copy from now renders light by default,
   fires all three countdown bands plus the expiry state, keeps the chip and the option card in agreement,
   and meets every touch-target floor it states. Treat R2/R3/R4/R5 as **regression tests**, not one-off
   fixes: they are the four that only appear when the component actually runs.

Screens 3A/3B, 11B, 27C and the empty/error states are buildable in parallel with step 3.

**Feature flag (Fork D).** One flag, default off, gating screens 5, 15, the Held column of 9, and the
`HELD` branch of 1. Name it for the dependency, not the feature — something like `held_state_enabled`,
with issue **#53** in the comment — so it is obvious what removes it rather than obvious what it hides.
Everything behind it is already specified here; nothing about the flag is a design decision.

---

## 8 · Constitution Check

| Check | Result |
|---|---|
| Contradicts a locked decision U1–U120? | **No.** U14, U16, U17, U18, U21, U25, U31, U34, U38, U41, U47, U48, U49, U50, U51, U56, U64, U67, U68, U69, U70, U73, U74, U75, U78, U82, U83, U85 are each cited where they constrain a value. **One live U69 violation was found in `mockup.html` and is reported, not silently patched** (§5.3-R1). |
| Amends a foundations or surface file? | **Yes, five — all corrections, none a redesign, each dated and reasoned inline.** `mockup.html` (R1–R9 + F1 + F7, ~20 sites), `00-foundations/components.md` §2 (the ARIA bullet → three-node structure), `00-foundations/accessibility-behaviour.md` (matrix callout for the collision), `01-driver-chat/accessibility.md` (the `filled`-variant rationale), and `01-driver-chat/components.md` §2 (**new "Sibling of a held card" row + the rule explaining why**, owner-approved 2026-08-27 — this was the last item held back as "raised, not changed"). **Nothing is now raised-but-unresolved.** |
| Invents product behaviour? | **No.** Every field in §1.4 is read off `feasibility.py`; the `HELD` blocker is read off four separate files in `backend/`; the differentiator line is reported as **having no source** rather than given one. |
| Invents data? | **No.** Where a value has no source (Fork A's differentiator, F2's header height, F3's escalated header) it is named as absent. |
| React 19 frontend (ADR 012)? | Yes — `package.json` confirms React 19.2. |
| Stays inside the named scope? | Yes. The brief named `01-driver-chat/`, `ai-chat-primitives.md`, and `frontend/src/`. `backend/app/**` was read because the deliverable is an *implementation* spec and §5.1 cannot be asserted from design docs; the tracker was read per `AGENTS.md`'s startup rule. |
| Skills actually invoked, not cited? | **Yes, both, via the `Skill` tool.** `web-design-guidelines` (§5.4, guidelines fetched fresh from source) and `checklist-design` (§5.5, both bundled Chat checklists read from the skill's own files, audited item-by-item in their own order). `dataviz` not run — no chart, sparkline or stat tile on this surface. `design` canvas not run — this is a spec pass over an existing approved mockup, not a new screen. |
| Rendering verified, not eyeballed? | **Yes.** Headless Chromium via CDP: computed styles, `getBoundingClientRect` across all 41 frames, contrast computed from rendered `rgb()` values, a **60-second live trace** of the countdown through its thresholds, and two clipped screenshots. Nine defects found; **one earlier reading retracted** because the screenshot disproved it (§5.3, closing paragraph). |
| Genuine forks surfaced, not silently decided? | **Yes, four** (§6), each with options, a recommendation and the honest trade-off. **All four now closed by the owner**, with the rejected options kept on the record. |
| Fixes verified by measurement, not by editing and assuming? | **Yes — every one.** All probes re-run after the edits: default-render theme, computed contrast on all four chip states, box model across all 41 phone frames, font-size census, and a **53-second paired live trace** proving the chip and the option card now agree at every instant (0 mismatches / 38 samples) and that all three countdown bands plus the expiry state actually fire. §5.0. |
| Writeback (`CHANGELOG.md`, `wiki/`)? | **Not required** — `AGENTS.md`'s exemption covers everything under `docs/New-Solution-New-Design/`. |
| Empirical numbers tagged? | Yes. All §5.3 measurements are *measured*; §5.1's schema facts are *source-verified* (with the codebase's own production-verification date, 2026-08-23); §6's recommendations are *judgement* and say so. |
