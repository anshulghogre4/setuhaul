# Driver chat — flows and states

> Happy paths and system states. The failure paths live in `edge-cases.md` — and per README principle 5,
> those are the ones that matter most. Read both.

---

## Flow 1 · Report a delay (the core journey)

The §7.1 end-to-end, which is Phase 1's acceptance criterion.

```
Driver opens app
   │
   ├─ 1 active thread, no history ──▶ lands in conversation directly
   └─ otherwise ──────────────────▶ thread list ──▶ taps a load
   │
   ▼
Types "Traffic after Shahpura. Reaching around 11:20."
   │
   ▼
Assistant confirms context, may ask ONE clarifying question
   │  ("Does that mean arriving 11:00, or another hour from now?")
   │  → quick replies appear: [ Yes, 11:00 ] [ Another hour ]
   ▼
Option set arrives — 2–3 cards, "Nothing is held yet"
   │
   ▼
Driver taps a card ──▶ HELD (90s countdown, haptic)
   │
   ▼
Driver confirms ──▶ PENDING_CONFIRMATION (15 min, planner decides)
   │
   ▼
Planner confirms ──▶ CONFIRMED + arrival instructions
```

**Turn budget.** Best case is three driver messages: the report, one clarification answer (often a quick-reply
tap), and the option selection (a tap, not a message). §13.1 counts clarification turns as a cost — the
quick replies and the tappable cards exist to keep this number low without making the surface less
conversational.

### The two-step commit (D2)

Tapping an option is **not** the request. Tapping yields `HELD` — 90 seconds of exclusivity while the
driver decides — and a second explicit action sends it to the warehouse. This is deliberate: it absorbs
"two drivers pick the same slot within seconds" without holding capacity hostage during deliberation, and
it means a mis-tap costs 90 seconds of one dock's time rather than a wrong booking.

The UI must never collapse these into one action to save a tap.

---

## Flow 2 · Ask for options without a problem

The browse-only path (`SOLUTION_DESIGN.md` §7.2b — THR011 has no `driver_exceptions` row).

```
Driver: "What slots are possible after 1 PM if I reach around 12:45?"
   │
   ▼
Assistant answers with an option set
   │
   ├─ Driver taps one ──▶ becomes the exception path (exception created NOW)
   └─ Driver doesn't  ──▶ nothing persists beyond the thread + recommendation
```

**No exception row, no dedupe key, no SLA clock** until the driver actually acts. Visually this path is
identical to Flow 1 — the difference is entirely server-side — but it matters here because the thread
card must not show a priority marker or an urgency treatment for a thread that is just a question.

---

## Flow 3 · Check status

§8's *Status* conversation type, answered in-thread (no separate screen).

In practice the **persistent state line already answers it** before the driver asks — that is its job. When
they do ask, the assistant replies conversationally with the current state, and the reply is a normal
message carrying the state chip, not a special view.

Three honest answers exist (§7.1's `get_appointment_request_status`), and they must be distinguishable:

| Situation | Reply |
|---|---|
| Still pending | "Still with the warehouse. A planner will decide by 11:57." |
| Expired and released | "No planner responded in time, so that slot was released. I can look again now." |
| Confirmed | "✓ Confirmed — Dock D1 · Tue 4 Aug · 13:00–14:15. Reference APT-1042." |

---

## Flow 4 · Change mind / cancel

```
Driver: "Don't book 7:30, check tomorrow morning"
   │
   ▼
Assistant confirms what will be cancelled, explicitly
   │  "That'll release the 19:30 request. Want me to look at
   │   tomorrow morning instead?"
   ▼
Driver confirms ──▶ released + new search
```

**Every mutation is preview → explicit confirmation → commit** (§7). The assistant never cancels on an
ambiguous statement — "don't book 7:30" could mean "cancel it" or "I wasn't asking you to."

---

## Flow 5 · Add a constraint

The brief's own example: *"I need to leave by 9 PM for my next pickup."* Seeded as EXC002
(`SOLUTION_DESIGN.md` §7 — "I must leave before 1:30"). This can arrive as the *opening* message of an
exception, or mid-conversation after options are already on screen — the flow differs slightly.

```
Driver: "I need to leave by 9 for another pickup"
   │
   ▼
Assistant disambiguates — the brief's own edge case: "9 PM" could mean
gate-out or unload-start, and only the driver knows which
   │  "Should 9 PM be the latest you leave the gate, or the latest
   │   unloading can start?"
   │  → quick replies: [ Leave the gate ] [ Unloading starts ]
   ▼
Driver taps one
   │
   ▼
Assistant confirms what was captured, plainly:
   │  "Got it — I'll only offer slots that let you leave by 9:00 PM."
   ▼
   ├─ No options shown yet ──▶ proceeds to Flow 1, constraint applied from the start
   └─ Options already shown ──▶ existing cards are invalidated (OPTION_WITHDRAWN
                                  treatment, `edge-cases.md`) and a re-filtered set
                                  replaces them
```

### Rules

| Concern | Rule |
|---|---|
| Capture | `latest_acceptable_ts` (leave-by) or `earliest_acceptable_ts` (can't arrive before) — both are hard filters into Stage 1, not preferences (`SOLUTION_DESIGN.md` §5) |
| Disambiguation | **Always ask** when the constraint could mean gate-out or unload-start — never guess. This is the same ambiguity MSG004 models in the seed data. |
| Confirmation | The captured constraint is always echoed back in plain language before it's applied — a driver must be able to correct a misheard time before it silently removes every evening option |
| Mid-conversation arrival | Treated as a **new fact invalidating current options**, using the same visual mutation as `OPTION_WITHDRAWN` (card greys, struck through, replaced) — never a silent re-fetch behind the driver's back |
| No feasible result | If the constraint eliminates every option, this **is** a `NO_SAME_DAY_SLOT` / `NO_FEASIBLE_SLOT` outcome — same templates, same escalation path (`edge-cases.md`) |

---

## Flow 6 · Facility question

The brief's example: *"Does the 7:30 slot accept a 32-foot vehicle?"* — asked before any booking intent,
purely informational. `SOLUTION_DESIGN.md` §7.1 added `explain_slot_eligibility` specifically so this
never becomes the LLM guessing at compatibility, which §6.3 forbids outright.

```
Driver: "Does the 7:30 slot take a 32-foot vehicle?"
   │
   ▼
Assistant calls explain_slot_eligibility — read-only, no booking side effect
   │
   ▼
Renders the Eligibility answer component (below) — a per-invariant
verdict, not a sentence the model composed
   │
   ▼
Assistant adds ONE line of plain-language framing around the structured
answer — never restates the verdict in different words that could drift
from what the tool actually returned
```

### Eligibility answer (new component)

Structurally distinct from the shared decision receipt (`../00-foundations/components.md` §4) — that
renders *why an option ranked where it did*; this renders *whether one specific thing is allowed*. Binary
per invariant, not scored.

```
┌──────────────────────────────────────┐
│  Dock D4 · 32-foot vehicle           │
│                                      │
│  ✓  Vehicle length                  │
│  ✓  Weight (14,500 / 25,000 kg)     │
│  ✓  Dock active                     │
│                                      │
│  Yes — this slot accepts your truck  │
└──────────────────────────────────────┘
```

Or, when it fails:

```
┌──────────────────────────────────────┐
│  Dock D5 · Reefer load               │
│                                      │
│  ✓  Vehicle length                  │
│  ✗  Refrigeration required           │
│     D5 is under maintenance          │
│      18:00–22:00 (RULE003 pins       │
│      reefer loads to D5 only)        │
│                                      │
│  No — try after 22:00 or ask for     │
│  tomorrow's options                  │
└──────────────────────────────────────┘
```

| Element | Source |
|---|---|
| Per-invariant rows | `explain_slot_eligibility`'s Stage 1 verdicts — every row present, not just the failing one, so a driver sees the full picture |
| Failure detail | The specific rule id and reason, in plain language — never "not eligible" alone (`../00-foundations/voice-and-tone.md`'s "a refusal without a route is a dead end" applies here too) |
| Verdict line | Templated pass/fail sentence, not generated — same discipline as the four state templates (§7.2b) |
| Icon | `check`/`x`, never colour alone for the per-row verdict (`../00-foundations/iconography.md`) |

**This is read-only and creates nothing.** No exception, no thread state change, no dedupe key — asking a
facility question is the same "browse-only" category as Flow 2.

---

## System states

### Assistant thinking

```
  ⬡ SetuHaul assistant
  ┌─────────┐
  │ ● ● ●   │   ← three dots, 1.4s loop, ease-in-out
  └─────────┘
```

- Appears after 400ms of no response — not immediately, since a fast reply makes the indicator flash
  distractingly.
- If a turn exceeds **8 seconds**, the indicator gains a line: "Still working on this…" A driver at a
  roadside with no feedback assumes the app is broken.
- Under `prefers-reduced-motion`, dots become a static "Working…" label (`../00-foundations/motion.md`).

### Scroll to latest

When new messages arrive while the driver is scrolled up:

```
        ┌──────────────────┐
        │  ↓  2 new        │   ← floating pill, above composer
        └──────────────────┘
```

- Appears only when scrolled >1 screen from the bottom.
- **The transcript never auto-scrolls while the driver is reading history** (checklist: *Message thread*
  tip). New content arriving must not yank the view.
- Tapping scrolls to the latest and dismisses.
- Counts messages, not events — a card mutating in place doesn't increment it.

### Loading

| Context | Treatment |
|---|---|
| App launch | Thread-list skeleton cards (`../00-foundations/components.md` §13) |
| Opening a thread | Transcript skeleton — 3 alternating bubble shapes |
| Sending a message | Optimistic — bubble appears immediately with `○` sending status |
| Committing an option | Card locks with inline spinner; siblings dim (`components.md` §2) |

### Empty

| Context | Icon | Copy |
|---|---|---|
| No active loads, has history | `circle-check-big` | "No active loads. You'll see delays and slot changes here." |
| No loads ever (U74) | `inbox` | "No loads assigned yet. Your dispatcher assigns these — they'll appear here automatically." |
| Thread with no messages | — | Cannot occur; a thread exists because a message created it |

The "nothing yet" copy points at the TMS boundary (§1) without using the word TMS — a driver knows
"dispatcher," not "Transportation Management System."

---

## Notifications (U17, revised)

Web push + in-app. **SMS was dropped from v1** — see below.

| Event | Push | In-app |
|---|:--:|:--:|
| Hold about to lapse (10s) | — | ✅ + haptic |
| Hold lapsed | ✅ | ✅ |
| **Pending expired — slot released** | ✅ **high priority** | ✅ |
| Planner confirmed | ✅ | ✅ |
| Planner rejected | ✅ **high priority** | ✅ |
| Counter-offer received | ✅ | ✅ |
| **Dock went down — option withdrawn** | ✅ **high priority** | ✅ |
| Human joined the thread | ✅ | ✅ |

**The four capacity-loss / decision-against events keep their elevated treatment** — they are the cases
where a driver who never opens the app still needs to know, because they may be driving toward a dock that
is no longer theirs. Previously that meant an SMS alongside push; now it means push sent at high priority
(`urgency: high`, and a notification the user must dismiss rather than one that auto-expires).

**Why SMS went**: not free, and India's DLT registration with TRAI is a multi-step regulatory precondition
rather than a config flag (`../../TECH-STACK/TECH_STACK.md` §6). **The honest gap this leaves**: a driver
who never granted push permission — or is on iOS without adding the PWA to their home screen — gets no
proactive alert at all for these four events. Nothing is lost (the thread list shows current promise state
on next open), but nothing is pushed either. Recorded as an accepted limitation, not solved.

Push copy uses the same templates as in-app (`../00-foundations/voice-and-tone.md`) — a notification that says something
different from what the app says is a second source of truth.

### Deep-linking

Every notification opens the specific thread, not the list. A driver tapping "your slot was released"
should land on the thread with fresh options already loading.

---

## Haptics (U21)

| Event | Pattern |
|---|---|
| Option card tapped | 10ms |
| Hold granted | 10ms · 40ms pause · 10ms |
| Hold at 10s remaining | 200ms |
| Hold at 5s remaining | 200ms · 100ms · 200ms |
| Hold lapsed | 400ms |
| Confirmed | 10ms · 40ms · 10ms · 40ms · 10ms |
| Message failed to send | 300ms |

Degrades silently where `navigator.vibrate` is unsupported. No audio anywhere (U21) — a truck cab is loud
and the phone is often face-down on the dash, which is exactly why haptics carry this instead.
