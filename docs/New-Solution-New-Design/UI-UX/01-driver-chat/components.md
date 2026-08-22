# Driver chat — components

> Surface-specific only. Shared components (button, promise-state chip, countdown, receipt, empty/error
> states) are in `../00-foundations/components.md` and are **not** redefined here. Chat primitives bind to
> assistant-ui per `../00-foundations/ai-chat-primitives.md`.

---

## 1. Thread card

The thread list's row. Anatomy in `screens.md` §1.

### States

| State | Treatment |
|---|---|
| Default | `surface-raised`, `border-subtle`, `radius-lg` |
| Pressed | `surface-hover`, no scale or lift (`../00-foundations/motion.md`) |
| **Active with running TTL** | Promise-state chip shows `filled` variant + live countdown |
| **Resolved** | 60% opacity, priority marker removed, chip shows terminal state, no countdown |
| **Unread activity** | 2px `border-focus` left inset + the descriptor at weight 700 |
| Offline (cached) | Renders normally; the countdown holds at last-known with an "updated Xm ago" marker (U68) |

### Rules

- **The promise-state chip is always `filled` here**, never `outline` — the thread list is glanced at in
  sunlight, and outline chips lose their fill under glare (`../00-foundations/color.md`, field-condition contrast).
- Resolved cards keep their state chip. A driver checking "what dock did I agree to last Tuesday" is a
  real need, and the card is the record.
- Whole card is the tap target — minimum 88px tall, well past the 44×44 floor.

---

## 2. Option card

The single most consequential component on this surface (U16, U48). Anatomy in `screens.md` §4.

### States

| State | Treatment |
|---|---|
| **Default (selectable)** | `surface-raised`, `border-default`, full opacity |
| **Pressed** | `surface-hover` + 10ms haptic, fires immediately on touch-down for perceived responsiveness |
| **Committing** | Card locks, inline spinner replaces the differentiator line, other cards in the set dim to 40% |
| **Held (won)** | Transitions in place to `HELD` treatment — 2px dashed amber border, countdown appears |
| **Lost (conflict)** | Struck through, 40% opacity, `SLOT_CONFLICT` notice below (U50) |
| **Withdrawn** | Struck through, 40% opacity, `OPTION_WITHDRAWN` notice — dock went down mid-conversation |
| **Disabled (offline)** | 40% opacity, `wifi-off` icon, one-line reason. **Visible, never hidden** (U68) |
| **Superseded** | When a newer option set arrives, older sets grey to 40% and become non-interactive |

### Rules

- **No ordinal, ever.** Not displayed, not accepted, not in the DOM. This is what makes §7.2b's trap
  unreachable rather than merely guarded.
- **One differentiator line only.** Three cards each carrying a full receipt is unreadable on a phone at a
  roadside; the full receipt is one tap away via the contextual help affordance
  (`../00-foundations/components.md` §15).
- **Cards mutate in place** rather than being replaced by a new message (U50) — the driver sees *which*
  thing changed, not just that something did.
- Tapping a superseded or disabled card does nothing and gives no haptic — silence is the correct feedback
  for a non-target.

---

## 3. Composer

Free text plus contextual quick replies (U49).

```
┌────────────────────────────────────┐
│ [ Yes, 11:00 ] [ Another hour ]    │  ← quick replies, when present
├────────────────────────────────────┤
│ ┌────────────────────────────┐ ➤  │
│ │ Message                    │    │
│ └────────────────────────────┘    │
└────────────────────────────────────┘
```

### Quick replies

| Rule | Detail |
|---|---|
| **When shown** | Only when the assistant's last message asked something with an obvious closed answer — a clarification with two readings (`../00-foundations/voice-and-tone.md`), or a confirm/decline |
| **How many** | 2–3. More than 3 is a form, not a conversation, and horizontal scroll on a phone hides options |
| **What they send** | The literal text on the chip, as a normal driver message. **Not** a special message type — the transcript must read as a conversation afterwards |
| **Dismissal** | Typing anything dismisses them; they do not reappear for that question |
| Source | `SuggestionPrimitive` (`../00-foundations/ai-chat-primitives.md`) |

Quick replies exist because a stressed driver answering "does that mean 11:00, or another hour?" on a
phone keyboard at a roadside is a real cost, and §13.1 counts clarification turns. One tap is the
difference between a resolved exception and an abandoned one.

### Text input

| Concern | Rule |
|---|---|
| Size | `text-body-lg` (16px) — prevents iOS auto-zoom, and is the driver body size anyway |
| Growth | 1 line default, grows to 3, then scrolls internally |
| Send | `➤` button, 44×44, `constructive` intent. Enabled only when non-empty |
| Hardware keyboard | Enter sends, Shift+Enter newline (checklist: *Message input* tip) |
| Offline | **Stays fully enabled** — the driver types, it queues (U68). Placeholder changes to "Message · will send when you're back online" |

**The composer is never disabled.** Whatever else is unavailable, a driver must always be able to say
something — that message queueing safely is the whole point of `CONNECTION_LOST` (`../00-foundations/voice-and-tone.md`).

---

## 4. Message bubble

Three tiers (U47), detailed in `screens.md` §3.

### Delivery status

Driver messages only, beneath the bubble, `text-micro`:

| Status | Indicator |
|---|---|
| Sending | `○` |
| Sent | `✓` |
| Delivered | `✓✓` |
| **Queued (offline)** | `⏱ queued` — explicit words, not a symbol, so it cannot be mistaken for sent |
| **Failed** | `⚠ not sent` + a [Retry] affordance inline |

No "read" receipt — see `screens.md`'s checklist coverage for why.

### Grouping

Consecutive messages from the same sender within 2 minutes group: attribution header on the first only,
timestamp on the last only. Reduces clutter without losing the record (checklist: *Sender identification*
tip).

---

## 5. System notice

Centred, no bubble. The `SYSTEM` tier from U47.

```
        ────────────────────────────
          Neha from Operations joined
        ────────────────────────────

        Dock D5 has gone out of service
```

| Variant | Treatment |
|---|---|
| **Takeover** | Full-width divider rules above and below, `text-secondary` (U47) |
| **Event** (option withdrawn, hold lapsed, pending expired) | No rules, centred `text-sm`, paired with the affected card mutating in place (U50) |
| **Connection** | Same, plus a `wifi-off` icon |

Never dismissible. These are the transcript's record of what happened, and §12.2 requires the driver be
shown when an option changes or disappears.

---

## 6. Persistent state line

Header element carrying current promise state + countdown at all times (`screens.md` §2).

| State | Content |
|---|---|
| No active promise | Hidden entirely — the header shows only the load descriptor |
| `SHOWN` | `Options open · nothing held` |
| `HELD` | `⏱ HELD 1:24` — countdown live, urgency colours per `../00-foundations/components.md` §3 |
| `PENDING_CONFIRMATION` | `◷ PENDING · decision by 11:57` |
| `CONFIRMED` | `✓ CONFIRMED · Dock D1 · Tue 4 Aug 13:00` |

- Tapping scrolls the transcript to the message that established the state.
- **Truncates the dock/date before it truncates the state word** — `PENDING CONFIRMATION` is never
  abbreviated (`../00-foundations/components.md` §2).
- Uses the shared 1 Hz tick, not its own timer.

---

## 7. Contextual help on state

The one place this surface uses the shared help affordance
(`../00-foundations/components.md` §15).

```
⏱ HELD 1:24  ⓘ
              └─ "Held means this slot is reserved for you for
                 90 seconds. It's not booked yet — send it to
                 the warehouse to request it."
```

- Attached to the promise-state chip, in the header and on option cards after selection.
- Copy is **state-specific and drawn from the same source as `../00-foundations/voice-and-tone.md`'s templates** — not
  generic product help.
- This is the driver's entire help surface (U73). There is no FAQ, and the four state explanations are the
  thing most worth explaining in the whole product.

---

## 8. Eligibility answer

Renders `explain_slot_eligibility` (`SOLUTION_DESIGN.md` §7.1). See `flows-and-states.md` Flow 6 for the
full flow — anatomy and rules here.

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

### States
| State | Treatment |
|---|---|
| Loading | Skeleton rows matching the final invariant count — never a spinner (`../00-foundations/components.md` §13) |
| Pass | Green `check` per row, green verdict line |
| Fail | Red `x` on the failing row(s) only — passing rows stay their normal neutral colour, never green; a mixed-verdict card is not the place to introduce a second meaning for a colour already spent on promise state |
| Error (tool call failed) | "Couldn't check that — try asking again." Never a guessed answer (`../00-foundations/voice-and-tone.md`'s empty/error rule) |

### Rules
- **Every invariant renders, not just the failing one.** A driver who sees only "no" learns nothing they
  can act on; seeing which specific thing failed is what turns a refusal into a route (§7.2).
- **Verdict line is templated**, matching the discipline `voice-and-tone.md` applies to the four state
  messages — this is also a sentence that declares a fact, not conversational glue.
- Renders through `MessagePartPrimitive` as tool-call output (`../00-foundations/ai-chat-primitives.md`) —
  never as text the model composed from the invariant list itself.
- **Read-only.** No exception, no thread-state change, no dedupe key — same browse-only category as the
  Flow 2 option-preview path.
