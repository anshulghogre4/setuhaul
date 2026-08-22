# Driver chat — edge cases

> README principle 5: *failure paths are the real product.* §12.2 explicitly requires demonstrating what
> a driver is shown when an option changes or disappears, and at least one case ending in escalation.
> Copy for each is in `../00-foundations/voice-and-tone.md`; this file is what the *screen* does.
>
> Every case below is traceable to a seeded fixture in `SOLUTION_DESIGN.md` §9.2.

---

## 1 · Hold lapses (`HOLD_LAPSED`)

90 seconds expire before the driver confirms.

```
BEFORE                          AFTER
┌──────────────────────────┐    ┌──────────────────────────┐
│ Dock D1 · Tue 4 Aug      │    │ ~~Dock D1 · Tue 4 Aug~~  │  40% opacity
│ 13:00 – 14:15            │ ─▶ │ ~~13:00 – 14:15~~        │  struck through
│ ⏱ HELD 0:03              │    │ Hold lapsed              │
└──────────────────────────┘    └──────────────────────────┘

              + system notice: "That hold has lapsed — Dock D1 ·
                13:00–14:15 is available to other drivers again."
              + [ Find options again ]
```

- **The card is replaced in place, never removed** (`../00-foundations/motion.md`). A driver who looks up to find their
  option simply gone learns nothing and trusts less.
- Haptic at 10s, 5s, and 400ms on lapse — the driver may not be looking at the screen.
- The `[ Find options again ]` action is part of the notice, not something they must think to ask for.
- Persistent state line clears back to no-active-promise.

**Race:** hold expires in the same moment the driver taps confirm. Exactly one outcome resolves
(§9.2's `hold_expiry_vs_confirm`) — the UI shows either the lapse or the pending state, **never both**.
The card locks on tap and only resolves once the server answers.

---

## 2 · Pending expires (`PENDING_EXPIRED`) — D9

15 minutes pass with no planner action.

```
◷ PENDING CONFIRMATION 0:00
        │
        ▼
System notice: "No planner responded in time, so Dock D1 ·
13:00–14:15 has been released. This has been escalated to
operations, and I can look for fresh options now."
                                    [ Find options again ]
```

- **High-priority push** (U17 revised — SMS dropped from v1) — capacity was lost while the driver may have
  been driving toward it, so this is one of the four events that gets elevated treatment. If push was never
  granted, the driver sees this on next app open; there is no second channel.
- The escalation is stated plainly, not hidden. A driver whose request timed out should know a human now
  owns it (§7.4's `PENDING_EXPIRED_UNACTIONED`).
- State line clears; the thread stays active with fresh options loading.

---

## 3 · Lost the race (`SLOT_CONFLICT`)

Another driver committed first.

```
System notice: "Another driver requested Dock D1 · 13:00–14:15
a moment before you. That one's gone — here's what's open now."
                              ↓
                    [ fresh option set ]
```

- The lost card struck through in place; the new set appears immediately below.
- **Never blames the driver for being slow.** State the fact, move to alternatives.
- No haptic penalty pattern — losing a race is not the driver's error.
- Seeded: `same_interval_race` (§9.2).

---

## 4 · Option withdrawn mid-conversation (`OPTION_WITHDRAWN`)

A dock goes out of service while the driver is deciding — DEVT002, D5 down 18:00–22:00.

```
┌──────────────────────────┐
│ ~~Dock D5 · Tue 4 Aug~~  │  ← this card only
│ ~~18:00 – 19:15~~        │
│ No longer available      │
└──────────────────────────┘
┌──────────────────────────┐
│ Dock D2 · Tue 4 Aug      │  ← siblings unaffected
│ 19:00 – 20:15            │
└──────────────────────────┘

System notice: "Dock D5 has just gone out of service, so the
18:00 option is no longer available. The other two options
are still open."
```

**Only the affected card mutates** (U50). Withdrawing an entire option set because one member died would
be both wrong and alarming. This is the clearest expression of why cards mutate in place rather than the
assistant sending a new message — the driver sees *which* option died without matching prose to cards from
memory.

---

## 5 · No same-day slot (`NO_SAME_DAY_SLOT`) — not an escalation

Stage 0's multi-day horizon. **This is a distinct outcome from "no feasible slot" and must not look like a
failure.**

```
"Nothing works at Jaipur DC today — the reefer dock is down
for maintenance until 22:00 and the site closes then. The
earliest I can offer is tomorrow."

┌──────────────────────────┐
│ Dock D5 · Wed 5 Aug      │  ← DATE IS LOAD-BEARING HERE
│ 06:00 – 07:15            │
└──────────────────────────┘
┌──────────────────────────┐
│ Dock D5 · Wed 5 Aug      │
│ 07:30 – 08:45            │
└──────────────────────────┘

"Nothing is held yet. If waiting overnight doesn't work,
I'll bring in operations."
              [ That doesn't work — get help ]
```

- The date on these cards is doing real work — a driver reading "06:00" as this morning has been
  mis-promised by formatting. This is precisely why every card carries its date unconditionally
  (`../00-foundations/voice-and-tone.md`).
- The escalation route is **offered, not withheld** until the driver thinks to ask.
- Names the specific blocking reason (reefer dock, maintenance, closing time) — not "no availability."

---

## 6 · No feasible slot at all (`NO_FEASIBLE_SLOT`) → escalation

The whole horizon is exhausted. §12.2's required escalation case — seeded as SHP1015.

```
"I can't find a workable slot for this load at Jaipur DC —
the only reefer dock is out of service past your arrival
time, and there's nothing tomorrow either.

I've passed this to operations. Reference ESC-4471.
Someone will contact you directly."
```

- **Always carries a reference and a promise of contact.** An escalation without a reference feels like
  being dropped.
- Thread state becomes `ESCALATED`; the assistant stops auto-replying on it (§7.4).
- No option cards, no "try again" — offering a retry that will fail identically is worse than not offering
  one.

---

## 7 · Human takes over (`HUMAN_JOINED`)

```
  ────────────────────────────────
    Neha from Operations joined
  ────────────────────────────────

  Neha · Operations
  ┌──────────────────────────────┐
  │ Hi Manoj — I'm looking at    │
  │ your reefer load now.        │
  └──────────────────────────────┘
```

- Divider is permanent, not dismissible.
- Subsequent operations messages carry avatar + name + role, visually heavier than assistant messages
  (U47).
- **The assistant stops auto-replying** on this thread. If it contributes again it is because a human
  used the co-pilot to draft something (U57) — and that message posts as the human, not the assistant.
- Push notification fires: a driver should know a person is now involved.

---

## 8 · Ambiguous shipment (DRV004 / THR010)

Driver has two active loads and sends a delay with no identifier.

**Structurally prevented on this surface.** The thread list means a driver picks a load before typing, so
a message arrives already scoped to a shipment. The ambiguity that THR010 models — `chat_threads.shipment_id`
NULL — arises from a channel with no such affordance.

It can still occur if a driver messages about a *different* load than the thread they are in:

```
"Actually I meant the Kota load"
        │
        ▼
"You have two Kota loads today. The one due 08:45,
or the later one due 18:00?"

  [ The 08:45 one ]  [ The 18:00 one ]
```

- Human descriptors, never IDs (`../00-foundations/voice-and-tone.md`).
- Quick replies make disambiguation one tap.
- **After two failed attempts, escalate as `AMBIGUOUS_SHIPMENT`** — do not loop (§7.2b's disambiguation
  ladder).

---

## 9 · Low-confidence ETA (SHP1013 / ETA008)

"I am late by one hour" — `confidence_code = LOW`.

```
"Does that mean your new arrival is 11:00, or that the
delay may continue for another hour?"

  [ Arriving 11:00 ]  [ Might be longer ]
```

If the driver proceeds with a low-confidence time, options come with risk framed as a **choice**, not a
hidden warning:

```
"I can hold 11:00, but if that time is uncertain, the 12:15
window gives you an hour of cushion and avoids a second
reschedule."
```

- **Never derive an ETA from a delay duration.** A 45-minute repair is not a 45-minute ETA shift.
- Never silently commit a LOW-confidence time — the driver prices their own risk.

---

## 10 · Offline (U68)

```
┌────────────────────────────────────┐
│ ‹  Kota load → IndustrialHub       │
│    ⏱ HELD 1:24 · updated 2m ago    │  ← staleness marked
├────────────────────────────────────┤
│  [ transcript — fully readable ]   │
│                                    │
│  ┌──────────────────────────────┐  │
│  │ ⚡ Dock D4 · Tue 4 Aug        │  │  ← 40% opacity
│  │ 12:15 – 13:30                │  │
│  │ Offline — can't select now   │  │
│  └──────────────────────────────┘  │
│                                    │
│  ⚡ You're offline. I'll send this  │
│     as soon as you're back.        │
├────────────────────────────────────┤
│ │ Message · will send when back │➤ │  ← composer STAYS ENABLED
└────────────────────────────────────┘
```

| Available | Disabled |
|---|---|
| Full transcript, cached | Option card selection |
| Confirmed appointment details — **the thing most needed at a gate** | New option requests |
| Promise state, marked stale | — |
| Typing and queueing messages | — |

**Option cards are disabled, visibly, with a reason.** Queuing a selection for later would mean a driver
believing they hold a slot they may not — the exact broken promise this product exists to prevent. The
countdown holds at last-known rather than free-running against an untrustworthy local clock
(`../00-foundations/components.md` §3).

**On reconnect:** queued messages send, thread re-syncs, cards re-validate against a fresh snapshot before
re-enabling. If anything changed, the normal `OPTION_WITHDRAWN` or a fresh set explains it — silently
where nothing changed.

---

## 11 · Duplicate message (THR001 / THR009)

Driver taps send twice on a bad connection; the same message arrives twice.

- Client: send button locks until the request resolves; the optimistic bubble is not duplicated.
- Server: `dedupe_key` collapses it — **one exception, one action, one notification** (M9).
- **The driver never sees an error about it.** A duplicate that was handled correctly is not a problem
  worth surfacing; showing "duplicate detected" would imply they did something wrong.

Seeded: `duplicate_retry` (§9.2).

---

## 12 · Cancelled shipment (THR012 / SHP1019)

Driver asks about a slot for a shipment that was cancelled.

```
"That shipment and its appointment were cancelled.
Please contact dispatch before travelling."
```

- **No option cards, no scheduling path offered.** The refusal is the whole answer.
- Thread closes after the reply.
- Routes to dispatch, not to operations — this is a TMS-side matter (§1), and sending the driver to the
  wrong place wastes a phone call.

---

## 13 · Refusals (§7.2)

Five patterns, full copy in `../00-foundations/voice-and-tone.md`. Screen behaviour:

| Refusal | Screen |
|---|---|
| "Just confirm it" | Copy + `[ Flag as urgent ]` action |
| "Book 7:30 even though I arrive 8" | Copy naming the failing invariant + a feasible option set |
| Off-manifest cargo | Copy only. **No scheduling continues.** Thread → `ESCALATED` |
| Brake safety | Copy only, escalation reference shown. **No cards, no actions except contact info** |
| "Give me that truck's slot" | Copy + the current feasible set |

**Every refusal names the rule and offers a route** (§7.2). A refusal with no next step is a dead end, and
dead ends drive drivers back to phone calls — which is the failure mode this product exists to remove.

The safety refusal is the one screen in this product where nothing else should compete for attention: no
option cards, no quick replies, no suggestions. Just the message and how to reach a human.

---

## 14 · Session and connection failures

| Case | Behaviour |
|---|---|
| Session expires mid-exception | **Never sign a driver out mid-exception** (`../00-foundations/auth-and-scoping.md`). Silent refresh. |
| Message fails to send | `⚠ not sent` + inline `[ Retry ]`. Text preserved. 300ms haptic. |
| Thread fails to load | Skeleton → error state with `[ Retry ]`, cached transcript shown if available |
| Push denied at onboarding | Status line: "Notifications are off — you'll need to keep this page open to see changes." Re-ask only after a genuinely missed event. |
| Server error on commit | Card unlocks, state unchanged, "That didn't save. **Nothing has changed.**" |

That last line is not boilerplate. In a system where a tap commits capacity, a driver must know a failure
left no partial state — otherwise the rational response is to tap again, which is exactly what
idempotency (U70) is there to survive.
