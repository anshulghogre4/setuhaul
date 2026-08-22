# Driver chat — accessibility

> Baseline is WCAG 2.2 AA plus the field-condition overlay (U30). This file covers what is specific to
> *this* surface's physical context; shared rules live in `../00-foundations/`.

## The actual usage context

Not "mobile." Specifically:

- **Outdoors, often in direct sunlight** — a phone screen at 400 nits against Rajasthan afternoon glare
- **One hand**, the other on a steering wheel, a door, or a phone-to-ear call with dispatch
- **Cheap Android**, mid-range at best, on a connection that drops
- **Stressed and time-pressured** — something has already gone wrong, that's why they're here
- **Possibly gloved**, and possibly with hands that have been driving for eleven hours
- **Bilingual reality** — comfortable in Hindi/Hinglish, reading English (U31 ships English only for now)

Every rule below follows from at least one of these, not from a compliance checklist.

---

## Touch targets

| Element | Size | Note |
|---|---|---|
| Option card | Full width × **≥64px** | The most consequential tap in the product — oversized on purpose |
| Composer send | 44×44 | Floor |
| Quick reply chip | ≥44px tall | Floor |
| Thread card | Full width × **≥88px** | Whole card is the target, not just the title |
| Bottom nav item | ≥56px tall | |
| Back button | 48×48 | Larger than floor — top-left is the hardest place to hit one-handed |
| Help affordance `ⓘ` | 44×44 **hit area**, 14px visual | Small icon, large target |

**44×44 is our self-imposed AAA overlay (SC 2.5.5), not the AA requirement (SC 2.5.8 is 24×24)** — stated
in `../00-foundations/spacing-and-layout.md` so nobody later shrinks it believing AA permits it. Gloved
hands and a moving vehicle justify the extra.

**≥8px between adjacent targets.** Two option cards 2px apart is a mis-tap that commits the wrong dock.

### One-handed reach

The bottom third of the screen is the comfortable thumb zone. Ordered by importance:

```
┌─────────────────┐
│ ← back          │  hard to reach, but rarely urgent
│                 │
│   transcript    │  read-only, scroll works anywhere
│                 │
│  OPTION CARDS   │  ← mid-screen, reachable
│                 │
│ [quick replies] │  ← thumb zone
│ [ composer   ]➤ │  ← thumb zone
└─────────────────┘
```

**Nothing destructive sits in the thumb zone.** There is no "cancel appointment" button within easy
accidental reach — that path goes through the conversation with an explicit confirmation
(`flows-and-states.md` Flow 4).

---

## Contrast under glare

| Rule | Why |
|---|---|
| **Light theme is the default and cannot be overridden to dark without a warning** | Dark UI in direct sunlight on a cheap LCD is genuinely unreadable |
| **Promise-state chips use the `filled` variant here, always** | An outline chip loses its signal under glare — the fill is what survives |
| **Body text is `text-primary` only** | `text-secondary` is reserved for genuinely secondary content; nothing operational uses it on this surface |
| Minimum body size **16px** (`text-body-lg`) | Also prevents iOS auto-zoom, but the reason is legibility at arm's length |
| No text below **14px** on this surface | The 11px floor elsewhere does not apply here |

Verified pairings are in `../00-foundations/color.md`. The ones that matter most here — `neutral-900` on
white at 17.9:1, and the `filled` state chips — clear AA comfortably, which is the margin glare eats into.

---

## Screen reader

| Element | Behaviour |
|---|---|
| **Promise-state chip** | `role="status"`. Announces on transition: "Held. One minute twenty-four seconds remaining." |
| **Countdown** | `aria-live="polite"`, **throttled to 50%, 20%, 10s, and expiry only** (`../00-foundations/components.md` §3). A per-second live region is unusable. |
| **Option card** | `role="button"`, labelled fully: *"Dock D4, Tuesday 4 August, 12:15 to 13:30, soonest. Tap to hold for 90 seconds."* Never "Option 1." |
| **Message** | `role="listitem"` within a `role="log"` transcript. Sender announced on tier change, not per message. |
| **Takeover divider** | `role="status"`, announced: "Neha from Operations joined the conversation." |
| **System notice** | `role="status"` for informational, `role="alert"` for hold lapsed / option withdrawn |
| **Quick replies** | Grouped, labelled "Suggested replies" |
| **Delivery status** | Part of the message's accessible name — "sent", "queued, will send when back online" |

**Option cards must never be announced positionally.** "Option 2 of 3" reintroduces the ordinal that U16
removed — a screen-reader user who says "select option 2" to a voice assistant must not be able to act on
a stale position. The dock and time *are* the identifier.

### Announcement discipline

The transcript is a `log`, not a live region that re-announces everything. Only these interrupt:

- Promise-state transitions
- Countdown thresholds (four per hold)
- Option withdrawn / hold lapsed
- Human joined

Everything else is read on navigation. A driver using a screen reader while an option set arrives should
not have three cards announced over the assistant's message.

---

## Motion and reduced motion

Per `../00-foundations/motion.md`, but the driver-specific consequences:

| Motion | Under `prefers-reduced-motion` |
|---|---|
| Countdown ticks | **Unchanged** — this is data |
| TTL colour warming | **Unchanged** — already instant |
| **HELD border pulse** | **Replaced, not removed** — solid high-contrast border + an explicit "expiring" label |
| Typing dots | Static "Working…" label |
| Card mutation on withdrawal | Instant |

The pulse replacement matters: silently dropping the expiry warning for someone who set a system
preference would be an accessibility failure dressed as compliance.

---

## Haptics as an accessibility channel

Haptics here are not polish — they are the channel that works when the screen doesn't:

- Phone face-down on the dash
- Screen unreadable in glare
- Driver mid-conversation with dispatch
- Low-vision user who benefits from non-visual confirmation

The 10s / 5s hold warnings (`flows-and-states.md`) are the clearest case: a driver who has looked away
gets told their hold is expiring without needing to see anything. Where `navigator.vibrate` is
unsupported, this degrades silently — **so haptics are never the only signal**, always paired with the
visual pulse and the countdown.

---

## Language and i18n readiness (U31)

English only in v1, structured so Hindi is a translation job:

- All copy externalised as keys — **especially the state templates**, which are the most painful to
  extract retroactively
- **Layouts tolerate ~30% expansion.** Devanagari also runs taller, so no fixed-height text containers:
  the state chip, option card, and quick replies must all grow vertically
- Dates and numbers via `Intl` with `en-IN` from the start
- Inter covers Latin only; Devanagari would need Noto Sans Devanagari added (`../00-foundations/typography.md`)

**The highest-value future translation is the four state templates and the eight negative-path messages.**
Those carry the promises. Conversational glue matters less — a driver who half-understands
"I'll find you fresh options" is fine; one who misreads "held" as "booked" is not.

---

## Low-end device performance

An accessibility concern here, not just an engineering one — an unresponsive UI is an unusable one under
time pressure.

- Target **60fps on a mid-range Android**. If a motion can't hold it, cut it (`../00-foundations/motion.md`).
- **One shared 1 Hz tick** for all countdowns, not one timer per component.
- Transcript virtualises beyond ~50 messages (`../00-foundations/ai-chat-primitives.md` — assistant-ui provides this).
- Animate `transform` and `opacity` only.
- Font subset to Latin, four Inter weights and two mono weights, nothing more (`../00-foundations/typography.md`).

---

## Testing checklist

Beyond automated contrast and axe checks:

- [ ] **Take the phone outside in direct sun.** Read the state chip. This is the real test and no
      simulator substitutes for it.
- [ ] Operate the entire happy path one-handed, thumb only, without shifting grip
- [ ] Greyscale: all four promise states remain distinguishable
- [ ] Deuteranopia simulation: `HELD` amber vs `CONFIRMED` green remain distinguishable
- [ ] 200% text zoom: no truncation of any state word, no horizontal scroll
- [ ] Screen reader: complete a hold-and-confirm without sighted assistance
- [ ] Airplane mode mid-conversation: transcript readable, appointment details readable, cards visibly
      disabled with a reason, composer still accepts input
- [ ] `prefers-reduced-motion`: the expiry warning is still perceivable
- [ ] Throttled 3G: thinking indicator appears, 8s message appears, nothing appears frozen
