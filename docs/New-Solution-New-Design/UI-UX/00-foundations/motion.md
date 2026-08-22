# Motion

> Decisions follow `../README.md` U13 (functional motion only), U19 (frozen sort), U21 (haptics), U41 (undo window).

## The rule

**Every animation must carry meaning. If you cannot say what a motion communicates, delete it.**

This is not minimalism for its own sake. Three reasons specific to this product:

1. Drivers run this on cheap Android over poor connections — every animation costs frames and battery.
2. Planners scan a live queue for anomalies. Decorative motion competes with the motion that *matters*
   (a TTL going critical, a new CRITICAL request arriving) and trains people to ignore movement.
3. Motion that draws the eye is a scarce resource. Spending it on a hover lift means having less of it
   when a slot disappears mid-conversation.

---

## The motion-budget allocation rule (U76)

A sharper form of "every animation must carry meaning," specifically for any view showing several
live-updating rows at once (the planner queue, the ops console, the dock board):

**Only the element currently changing animates. Everything that has already settled shifts back and loses
contrast, rather than staying visually loud.**

Concretely: when a new request arrives in the queue, that row gets the arrival flash (below) — every other
row does *not* re-animate, re-highlight, or re-draw, even though the list re-rendered. A row that finished
its transition ten seconds ago has no ongoing visual claim on attention and should recede toward
`text-secondary`/`border-subtle`, not sit at full contrast indefinitely.

This is the rule that makes a live queue scannable during a spike. Twenty rows all holding full visual
weight is the same as none of them holding it — a planner's eye has no way to find the one thing that
actually needs a decision. Allocating motion (and, by extension, visual weight) only to what changed is
what keeps a CRITICAL arrival findable at row thirty during a 35-request spike.

---

## Duration and easing

```
duration-instant   0ms      State changes that must not be perceived as gradual
duration-fast      120ms    Hover, focus, small state changes
duration-base      200ms    Most transitions — panels, expansions, toasts
duration-slow      320ms    Drawers, modals, large surfaces entering
```

```
ease-out      cubic-bezier(0.16, 1, 0.3, 1)      Entering — decelerate into place
ease-in       cubic-bezier(0.7, 0, 0.84, 0)      Exiting — accelerate away
ease-in-out   cubic-bezier(0.65, 0, 0.35, 1)     Moving between two on-screen positions
```

Entering uses `ease-out` so content arrives quickly and settles. Exiting uses `ease-in` so it gets out of
the way. No spring or bounce anywhere — overshoot reads as playful, and nothing in a capacity-commitment
system should.

---

## The motion inventory

Complete list. Anything not here does not animate.

| What | Duration | Easing | Why it earns motion |
|---|---|---|---|
| **Countdown digit change** | `instant` | — | Must read as discrete ticks, not a smooth sweep |
| **TTL threshold crossing** (colour warming) | `instant` | — | A *state* change, not a gradient. Gradual fade risks going unnoticed. |
| **Promise-state transition** | `base` | `ease-out` | The most important change in the product — it must be seen |
| **Row expansion** (U44) | `base` | `ease-out` | Shows where the content came from and preserves list position |
| **Toast enter / exit** | `base` / `fast` | `ease-out` / `ease-in` | Draws attention on arrival, leaves without lingering |
| **Undo countdown** (U41) | 5000ms linear | linear | A depleting bar — linear because it represents literal elapsed time |
| **Drawer / modal** | `slow` | `ease-out` | Large surface; too fast is jarring |
| **Rail expand / collapse** (U39) | `fast` | `ease-out` | Frequent, must feel immediate |
| **Skeleton shimmer** | 1600ms loop | `ease-in-out` | Signals "loading", distinct from "empty" |
| **New-item arrival flash** | `base`, once | `ease-out` | Marks a row that arrived while looking elsewhere |
| **Focus ring** | `fast` | `ease-out` | Keyboard navigation needs to feel connected |
| **Hover background** | `fast` | `ease-out` | Confirms the target under the pointer |

### Explicitly not animated

- Page and route transitions — instant. A planner switching views is doing work, not enjoying a journey.
- Table sorting and re-ordering — instant. See below.
- Number counting up. Values are not scores.
- Anything on the dock board Gantt except a genuine data change.
- Chart draw-in.
- Any hover effect that moves an element (lift, scale). Colour and border only.

---

## Motion and the frozen sort (U19)

The hardest interaction problem here. Requests arrive during a spike and the queue's correct order
changes — but a row moving under a planner's cursor causes a wrong confirm.

**Resolution: nothing re-orders while a row has focus.**

```
Idle, nothing focused    →  New rows insert with a single arrival flash.
                            No re-sort animation; the list re-renders in correct order.

Row focused              →  Order is PINNED. New arrivals accumulate behind a
                            "3 new · press R to re-sort" affordance in the header.
                            Nothing above the focused row moves. Ever.

User triggers re-sort    →  List re-renders instantly at the new order, focus
                            follows the same row by id, and that row flashes once
                            so the planner can find it again.
```

**The re-sort is instant, not animated.** An animated re-sort looks helpful but means several hundred
milliseconds during which the visible order matches neither the old nor the new state — exactly the window
in which a keypress does the wrong thing. Instant is safer, and the focus-follow plus flash is what
preserves orientation.

---

## Expiry motion — the product's signature interaction

`HELD` (~90s) and `PENDING` (15 min) expire while visible. Their motion is specified precisely because
this is where a design failure becomes a broken promise.

```
> 50% remaining     Countdown ticks. Nothing else moves.

20–50%              Countdown ticks. Colour warms (instant transition).

< 20%               Countdown ticks in weight 600.
                    HELD only: border pulses once per second —
                    opacity 1 → 0.6 → 1, 1000ms, ease-in-out.

< 10s (HELD)        Pulse continues. Haptic pulse at 10s and 5s (U21).

Expiry              NO fade-out. The card is REPLACED, in place, by the
                    expiry state — struck-through details plus the
                    HOLD_LAPSED message and a "find me new options" action.
```

**The card must never simply vanish.** A driver who looks up to find their option gone learns nothing and
trusts less. Replacement-in-place means the transcript retains a record that the thing existed and what
happened to it — which is §12.2's requirement that the driver is shown when an option disappears.

**Only `HELD` pulses.** A 15-minute `PENDING` that pulsed for its final three minutes would be
intolerable, and a planner queue of pulsing rows communicates nothing. Pulse is reserved for the
90-second case where a driver has seconds to act.

**The threshold-only escalation rule (U77), stated explicitly since the table above is an instance of it
without naming it:** colour and urgency escalate **only at a threshold crossing** (50%, 20%, 10s) —
never continuously, never as a gradient tied to the raw remaining-seconds value. A countdown that
recolours every second is noise; a countdown that steps at three fixed points is a signal. This is also
why the countdown's numeral, not its colour, is the element required to change at every tick — colour is
allowed to sit still between thresholds precisely because the number is doing the continuous work.

---

## Latency bands (U84)

When something appears while a request is in flight, and what it looks like, scaled to how long the wait
has actually gone on — distinct from `duration`/`easing` above, which govern how a *state change* animates
once it happens. This governs *whether anything appears at all* yet.

| Elapsed | Shown | Why |
|---|---|---|
| **< 1s** | Nothing | An indicator that flashes for under a second is pure distraction — by the time a user has registered it, the response has already arrived |
| **1–3s** | Indeterminate — the existing loading treatments (skeleton shimmer, button spinner) | Long enough to need *some* signal that something is happening, not yet long enough to promise a completion time |
| **3–10s** | Determinate, where the action can express progress (e.g. a multi-step admin operation) | The user is owed more than "something is happening" — a stalled-looking indeterminate spinner past 3s reads as broken |
| **> 10s** | Determinate + an explicit "still working" message, and for capacity-affecting actions specifically, elapsed time relative to any active TTL | A driver's Confirm that's taken 10 seconds has burned roughly 11% of a 90-second hold — they are owed that context, not just a spinner that looks identical at 2s and 40s |

This is what governs the `flows-and-states.md`-level "Assistant thinking → Still working on this…" pattern
already specified in `01-driver-chat/` — that pattern is this table's 8-second instance, restated here so
future surfaces (the ops co-pilot, admin's policy-simulation run) inherit the same bands rather than each
picking their own threshold.

---

## Haptics (U21)

Driver PWA and gate kiosk only. `navigator.vibrate`, degrading silently where unsupported.

| Event | Pattern | Surface |
|---|---|---|
| Option card selected | 10ms | Driver |
| Hold granted | 10ms, 40ms pause, 10ms | Driver |
| Hold at 10s remaining | 200ms | Driver |
| Hold at 5s remaining | 200ms, 100ms pause, 200ms | Driver |
| Hold lapsed | 400ms | Driver |
| Confirmed | 10ms, 40ms, 10ms, 40ms, 10ms | Driver |
| Gate event recorded | 15ms | Gate |
| Gate action rejected | 300ms | Gate |

**No audio anywhere.** Warehouses are loud enough that alerts go unheard, and offices are shared enough
that they are unwelcome. Haptics reach a driver whose phone is face-down on the dash and a gloved officer
who cannot feel a tap register.

---

## Reduced motion

`prefers-reduced-motion: reduce` is respected throughout, but **not by disabling everything** — some
motion here is informational, and removing it removes information.

| Motion | Under reduced-motion |
|---|---|
| Skeleton shimmer | Becomes a static grey block |
| Toast enter/exit | Instant appear/disappear, same duration on screen |
| Row expansion | Instant |
| Drawer / modal | Instant |
| Hover / focus transitions | Instant |
| **Countdown ticks** | **Unchanged** — this is data, not decoration |
| **TTL colour warming** | **Unchanged** — already instant |
| **HELD border pulse** | **Replaced, not removed** — border switches to a solid high-contrast treatment plus an explicit "expiring" text label |
| **Arrival flash** | **Replaced** — a persistent "new" badge on the row until acknowledged |

The principle: where motion carries information, reduced-motion gets an equivalent *static* signal rather
than losing the information. Silently dropping the expiry warning for a user who set a system preference
would be an accessibility failure dressed as accessibility compliance.

---

## Performance

- Animate `transform` and `opacity` only. Never `width`, `height`, `top` or `left`.
- Row expansion animates `transform: scaleY` on the panel with the content faded in — not `height`.
- `will-change` only on elements actively animating; removed after.
- **Countdowns update once per second via a single shared interval**, not one timer per component. A
  planner queue with 35 pending rows must not run 35 timers.
- Target 60fps on a mid-range Android for the driver surface. If a motion cannot hold that, cut it.
