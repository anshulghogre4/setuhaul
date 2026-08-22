# Driver chat — screens

> Surface: PWA, phone-first, hostile conditions. Density `comfortable`, light theme default, 320–768px
> (primary target 390×844). Foundations: `../00-foundations/`. Chat primitives: `../00-foundations/ai-chat-primitives.md`.
>
> Structure derived from Checklist Design's *Chat* checklists (Mobile app + Web app) per U34 — see
> *Checklist coverage* at the end for what applies and what deliberately doesn't.

## The surface in one line

Two screens and a profile: a **thread list** (home) and a **conversation**. Nothing else. §8 of the brief
asks for a genuinely chat-based experience, and a driver at a roadside should never have to navigate to
find out what is happening to them.

---

## Screen map

```
Sign in ──▶ Thread list ──▶ Conversation
              (home)          (back to list)
                │
                └──▶ Profile
```

Sign-in and push-permission priming are specified once in `../00-foundations/auth-and-scoping.md` and not
repeated here.

---

## 1 · Thread list (home)

One card per active exception thread, plus resolved threads muted below. This is where the §7.2b
disambiguation ladder gets solved structurally: a driver with two loads picks the right one **before**
typing, rather than the assistant guessing from context and asking a clarifying question that costs a turn
(§13.1 counts clarification turns as a cost).

```
┌────────────────────────────────────┐
│ SetuHaul                    ⚙︎     │  56px header
├────────────────────────────────────┤
│                                    │
│ ┌────────────────────────────────┐ │
│ │ ▌Kota load → IndustrialHub     │ │  ← priority marker (3px, left)
│ │  ORD-260804-004                │ │
│ │                                │ │
│ │  ⏱ HELD  1:24                  │ │  ← promise-state chip, FILLED
│ │  Dock D1 · Tue 4 Aug · 13:00   │ │
│ │                                │ │
│ │  "Option 2 is held for you…"   │ │  ← last message preview, 1 line
│ │                          09:41 │ │
│ └────────────────────────────────┘ │
│                                    │
│ ┌────────────────────────────────┐ │
│ │ ▌Neemrana load → RajRetail     │ │
│ │  ORD-260804-017                │ │
│ │                                │ │
│ │  ◷ PENDING CONFIRMATION        │ │
│ │  Decision by 11:57             │ │
│ │                                │ │
│ │  "The warehouse hasn't…"       │ │
│ │                          09:32 │ │
│ └────────────────────────────────┘ │
│                                    │
│  ─── Resolved ───────────────────  │
│                                    │
│ ┌────────────────────────────────┐ │
│ │  Jodhpur load → HomeCraft      │ │  ← 60% opacity, no priority marker
│ │  ✓ CONFIRMED · Mon 3 Aug       │ │
│ └────────────────────────────────┘ │
│                                    │
├────────────────────────────────────┤
│      Threads          Profile      │  bottom nav, 56px
└────────────────────────────────────┘
```

### Card anatomy

| Element | Rule |
|---|---|
| **Load descriptor** | `text-body-lg` 600. **Human descriptor, never the shipment ID** — "Kota load → IndustrialHub", per `../00-foundations/voice-and-tone.md`'s mechanics. The order reference sits beneath in `text-micro`, `--font-data`. |
| **Priority marker** | 3px left edge, neutral value ramp (`components.md` §5). Active threads only. |
| **Promise-state chip** | **`filled` variant, mandatory** — this surface is used in glare (`../00-foundations/color.md`, field-condition contrast). Carries its countdown when `HELD` or `PENDING`. |
| **Operational line** | Dock · dated range, always together, never a bare time (`../00-foundations/voice-and-tone.md`). |
| **Last message preview** | One line, truncated. `text-sm`, `text-secondary`. |
| **Timestamp** | `text-micro`, relative under 1h ("9m ago"), absolute above ("09:41"). |

### Ordering

1. Threads with a **running TTL** (`HELD`, then `PENDING`) — the ones with a deadline, soonest first
2. Other active threads, most recent activity first
3. Resolved, most recent first

A `HELD` thread with 20 seconds left is always the first thing on screen. This is the same
urgency-over-recency logic as the planner's queue ordering (§7.3), applied to a driver's own loads.

### States

| State | Treatment |
|---|---|
| **Loading** | Skeleton cards matching final layout (`components.md` §13) |
| **Nothing right now** | `circle-check-big` · "No active loads. You'll see delays and slot changes here." |
| **Nothing yet** | `inbox` · "No loads assigned yet. Your dispatcher assigns these — they'll appear here automatically." (U74 — and note this correctly points at the TMS boundary, §1) |
| **Offline** | List renders from cache with a status line; see `edge-cases.md` |

### Single-thread shortcut

**A driver with exactly one active thread and no resolved history lands directly in the conversation**,
skipping the list. The list is navigation, and navigating a list of one is friction. Back from that
conversation still reveals the list, so the model stays consistent — it is a launch shortcut, not a
different information architecture.

---

## 2 · Conversation

The primary surface. Chat as the spine with structured cards inside the transcript (U18).

```
┌────────────────────────────────────┐
│ ‹  Kota load → IndustrialHub       │  56px, back + descriptor
│    ⏱ HELD 1:24                     │  ← persistent state line
├────────────────────────────────────┤
│                                    │
│  ┌──────────────────────────────┐  │
│  │ Traffic after Shahpura.      │  │  ← driver, right-aligned
│  │ Reaching around 11:20.       │  │
│  └──────────────────────────────┘  │
│                          09:34  ✓✓ │
│                                    │
│  ⬡ SetuHaul assistant              │  ← AI tier
│  ┌──────────────────────────────┐  │
│  │ Your current slot is 10:00–  │  │
│  │ 11:00 at Jaipur DC. Three    │  │
│  │ options are open right now.  │  │
│  │ Nothing is held yet.         │  │
│  └──────────────────────────────┘  │
│                                    │
│  ┌──────────────────────────────┐  │
│  │ Dock D4 · Tue 4 Aug          │  │  ← OPTION CARD (tappable)
│  │ 12:15 – 13:30                │  │
│  │ soonest                      │  │
│  └──────────────────────────────┘  │
│  ┌──────────────────────────────┐  │
│  │ Dock D1 · Tue 4 Aug          │  │
│  │ 13:00 – 14:15                │  │
│  │ no waiting                   │  │
│  └──────────────────────────────┘  │
│                          09:34     │
│                                    │
│  ────────────────────────────────  │
│    Neha from Operations joined     │  ← takeover divider (U47)
│  ────────────────────────────────  │
│                                    │
├────────────────────────────────────┤
│ [ Yes, 11:00 ] [ Another hour ]    │  ← quick replies (U49)
├────────────────────────────────────┤
│ ┌────────────────────────────┐ ➤  │  composer
│ │ Message                    │    │
│ └────────────────────────────┘    │
└────────────────────────────────────┘
```

### Regions

| Region | Height | Behaviour |
|---|---|---|
| **Header** | 56px | Back · load descriptor · persistent state line. Sticky. |
| **Transcript** | fills | Scrolls. Auto-scrolls to latest on open; **never auto-scrolls while the driver is reading history** (checklist: *Message thread*). |
| **Quick replies** | 0 or 48px | Present only when contextual replies exist. Horizontally scrollable if >2. |
| **Composer** | 56px min | Grows to 3 lines max, then scrolls internally. Rises with the keyboard. |

### The persistent state line

The header carries the current promise state and countdown **at all times**, not just when the relevant
message is on screen. A driver who scrolls up to re-read something must not lose sight of a hold burning
down — and "what's happening with my slot right now" is §8's *Status* conversation type answered without
costing a message (the decision to answer status in-thread means the assistant still replies conversationally
when asked, but the driver rarely needs to ask).

Tapping the state line scrolls to the message that established it.

### Keyboard behaviour

Explicit handling on both platforms (checklist: *Keyboard push-up* — its tip names this as the common bug):

- Composer and quick replies rise with the keyboard; transcript shrinks and holds its scroll position
  relative to the **latest** message, not the top.
- `env(safe-area-inset-bottom)` respected so the composer clears the home indicator.
- 16px input font (`text-body-lg`) prevents iOS Safari auto-zoom on focus — already the driver body size
  (`../00-foundations/typography.md`), so this costs nothing.
- Composer is **thumb-reachable in all grip positions** — it is the bottom-most interactive element, full
  width, 44px minimum target.

---

## 3 · Message tiers (U47)

Three visual treatments, plus dividers for events. Consecutive messages from the same sender group without
repeating the attribution (checklist: *Sender identification* tip).

| Sender | Alignment | Treatment |
|---|---|---|
| `DRIVER` | Right | Filled bubble, `surface-selected`. Delivery status beneath. |
| `AGENT` | Left | Bubble on `surface-raised`, `border-subtle`. Header: `⬡ SetuHaul assistant`. |
| `OPERATIONS` / `WAREHOUSE` | Left | Bubble on `surface-raised`, `border-default` (heavier). Header: **person's name + role** — `Neha · Operations`, with avatar. |
| `SYSTEM` | Centred | **No bubble** — centred `text-sm` `text-secondary` notice. Events, not messages. |

**The AI/human distinction must survive a glance.** A driver who thinks they are still talking to a bot
will phrase things differently than one who knows a person is reading — the avatar, the real name, and the
heavier border together carry that, not any one of them alone.

### Takeover divider

When `OPERATIONS` posts for the first time in a thread, a full-width divider precedes their message:

```
  ────────────────────────────────
    Neha from Operations joined
  ────────────────────────────────
```

Not a message, not dismissible, permanent in the transcript. §7.4: *"Silent takeover reads as the bot
ignoring them."*

---

## 4 · Option cards (U16, U48)

The replacement for ordinals. **No number is ever displayed or accepted** — the card carries
`recommendation_id`, `dock_id` and `start_ts` in its payload, so §7.2b's ordinal trap is not merely
defended against, it is unreachable.

```
┌──────────────────────────────┐
│ Dock D4 · Tue 4 Aug          │  ← dock + date, never separable
│ 12:15 – 13:30                │  ← en dash, --font-data, tabular
│ soonest                      │  ← ONE differentiator from score_terms
└──────────────────────────────┘
```

| Element | Source |
|---|---|
| Dock + date | Tool result. **Date always present** even when all options are today (`../00-foundations/voice-and-tone.md`) |
| Time range | `start_ts`–`end_ts`, facility-local (U64) |
| Differentiator | Read from `score_terms` — "soonest", "no waiting", "most buffer". **Never computed by the interface** (`../00-foundations/ai-chat-primitives.md`) |

- Minimum 64px tall, full width minus margins — a large, unambiguous tap target.
- Tapping fires haptic (10ms), then the card transitions to the `HELD` state in place.
- **Disabled offline** with a visible reason (U68) — greyed, not hidden.
- Cards render through `MessagePartPrimitive` as tool-call output, never as parsed text.

**Comparison is read, never computed.** If a driver asks "which has the shortest wait?", the assistant
answers from the same `score_terms` already on the cards — it does not rank them itself (§7.2b).

---

## 5 · Profile

Minimal. Everything here is read-only except notification settings.

```
┌────────────────────────────────────┐
│ Profile                            │
├────────────────────────────────────┤
│  Manoj Sharma                      │
│  +91-9000010006                    │
│  Carrier: Rajasthan Roadlines      │
│                                    │
│  Vehicle                           │
│  UP14GT4106 · 32ft multi-axle      │
│                                    │
│  ─────────────────────────────     │
│                                    │
│  Notifications          [ On  ▸ ]  │
│  Language               English    │
│  Theme                  Light      │
│                                    │
│  ─────────────────────────────     │
│  Sign out                          │
└────────────────────────────────────┘
```

- **No editing of driver, vehicle or carrier data** — TMS-owned (§1). Displayed for confirmation only.
- Notifications row is the re-entry point for a driver who denied push at onboarding
  (`../00-foundations/auth-and-scoping.md`).
- Language shows English with no picker in v1 (U31) — present so the setting has an obvious future home.

---

## Checklist coverage

Against Checklist Design's *Chat* (Mobile app + Web app), per U34.

| Item | Status |
|---|---|
| Keyboard push-up | ✅ Explicit both-platform handling, §2 |
| Input bar | ✅ Composer + quick replies, thumb-reachable |
| Message bubbles (sent right / received left) | ✅ Convention followed exactly — U47's three tiers sit *within* it, not against it |
| Message thread, chronological, no scroll interruption | ✅ §2 |
| Message input, multi-line | ✅ Grows to 3 lines; Enter sends, Shift+Enter newlines on hardware keyboards |
| Sender identification + grouping | ✅ U47, consecutive grouping |
| Timestamps, relative then absolute | ✅ Thread list and transcript |
| Scroll to latest | ✅ See `flows-and-states.md` |
| Typing indicator | ✅ Assistant thinking state, `flows-and-states.md` |
| Read receipts | ⚠️ **Delivery status only** — sent / delivered / failed. No "read" receipt: there is no human on the other end during normal operation, and implying one would misrepresent the assistant. Delivery *does* matter because of offline queuing (U68). |
| Swipe to reply | ❌ **Not applicable.** One linear operational thread; there is no message-to-message reply model to thread into. |
| Long-press message actions (react, delete, copy) | ❌ **Not applicable.** The transcript is an operational record — `chat_messages` is append-only and a driver deleting their own delay report would corrupt the exception history. Copy is available via native text selection (`../00-foundations/typography.md` forbids disabling selection). |
| Reactions | ❌ Same reason |
| Media and file sharing | ❌ **Deliberately not adopted** (`../00-foundations/ai-chat-primitives.md`). Nothing in the driver conversation model requires a file; if a future case needs one (photo of a breakdown), that is a product requirement first. |

Four omissions, each with a stated reason. Worth reading them as design decisions rather than gaps — a
messaging app would need all four, and an operational record specifically should not have three of them.
