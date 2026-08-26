# Accessibility behaviour

> A product-wide contract for what gets announced, at what politeness, and where focus goes when the thing
> holding it changes or disappears. New file, U82. Distinct from per-component ARIA (`components.md`) and
> from each surface's `accessibility.md` (which covers that surface's physical ergonomics — glare, gloves,
> target sizes). This is cross-cutting behaviour that would otherwise be reinvented six times, once per
> surface, inconsistently. Informed by Primer's focus-management and announcements guidance — the clearest
> first-party treatment found in research — adapted to this product's specific hazards.

## Why this file exists, stated plainly

This product's two hardest states are **time-based and invisible without a deliberate decision**: a `HELD`
chip burning 90 seconds and a live-updating planner queue both change constantly, and neither has an
obvious, single "make it accessible" checkbox. Sighted users see a countdown escalate and a row's contrast
recede. A screen-reader user gets nothing unless specific thresholds are chosen to announce — and getting
this wrong doesn't just create friction, it silently breaks the same promise the whole visual design
exists to protect: a `HELD` slot that lapses without the driver hearing about it is a broken promise
exactly as much as one they didn't see.

---

## Announcement politeness matrix

Every live-updating region in the product resolves to one row below. `aria-live="polite"` waits for the
user's current task to pause; `"assertive"` interrupts. Silence is a deliberate choice, not a default.

| Region | Politeness | What's announced |
|---|---|---|
| Promise-state chip transition (`components.md` §2) | `assertive` | The new state, once, on the hard-swap — "Confirmed, Dock D1, 13:00" |
| Countdown (`components.md` §3) | `polite`, throttled | **Only** at 50%, 20%, 10s and expiry — never per-tick. A per-second live region is unusable and is explicitly called out as such in the countdown's own implementation requirements; this file is where that throttle is promoted from one component's rule to the product's general announcement policy. |
| Planner queue — new row arrives | `polite` | The count only ("3 new requests"), not each row's content — announcing full row detail for every arrival during a spike is Primer's "distracting stream" case, and a spike is exactly when this would fire most |
| Planner queue — a row a user is not focused on disappears (confirmed/expired elsewhere) | **Silent** | No announcement. This is the frozen-sort-on-focus principle (U19) extended to audio: a background change to a row the user isn't attending to must not interrupt them any more than it visually reorders under them |
| Planner queue — the row a user **is** focused on is acted on elsewhere (`ALREADY_ACTIONED`, §7.5.1) | `assertive` | This is the nastiest race in the product (`SOLUTION_DESIGN.md` §9.2) — a user about to act on a row that just changed underneath them must be interrupted, not politely queued |
| Location changes (route navigation) | `assertive`, on the new view's heading | Matches Primer's "always announce" tier |
| Unsuccessful user actions (write failed, validation error) | `assertive` | Matches Primer's "always announce" tier — silence on failure is the single worst accessibility failure mode available |
| Successful writes | `polite` | A success does not need to interrupt; a failure does |
| Toast content (`components.md` §8) | `role="status"` (info/success) or `role="alert"` (error) — already specified there | Cross-referenced, not restated |
| Capacity-incident row expanding/collapsing (§17) | `polite`, count only | "4 shipments affected" — the same principle as the queue-arrival row above |
| **Status bar — connection state** (`components.md` §7) | `polite` (`role="status"`) | The new state on transition only — "Offline", "Connected". **Added 2026-08-26**, found by a `web-design-guidelines` audit of the status-bar artboard: the general rule below routes ambient state *to* the status bar and leaves it silent, which would have silently swallowed going offline. That is not ambient — a planner who goes offline and keeps confirming is acting on stale capacity data (`auth-and-scoping.md`'s degradation policy). Polite rather than assertive because the *consequence* carries the urgency: primary content goes Inactive and Confirm goes with it, and that Inactive state is what interrupts |
| **Status bar — last sync, pending count, active facility, policy version** | **Silent** | These tick and churn continuously. A live region here would make the status bar unusable with a screen reader, for the same reason the countdown is throttled to four thresholds. They are readable on demand, which is precisely the role the general rule below assigns the status bar |

**The general rule underneath the table:** announce **location changes** and **unsuccessful actions**
always; announce **other changes case-by-case**, weighing whether the change is something the user is
actively waiting to hear (assertive-worthy) or ambient state they'd only want on request (silent, or
available via the persistent state line / status bar instead of a push).

---

## Focus management contract

Designers annotate focus movement as part of the spec, not as an engineering afterthought discovered at
build time. Every one of the following must be decided per screen, not left to "wherever the DOM puts it."

| Event | Focus goes to |
|---|---|
| Content **added** (new row, new message) | The first added item, **unless** a more contextually logical target exists — e.g. after sending a chat message, focus stays in the composer, it does not jump to the new message bubble |
| Content **removed** (a row confirmed/expired and taken out of the list) | An adjacent item — the row that took its place at the same position, or the nearest remaining row. **Never the top of the list** — a planner working row 20 of 35 who loses focus to row 1 has effectively lost their place in the spike |
| **Filtering** a list (queue filters, admin search) | Stays on the filter control. Results update; focus does not jump into the result set — a user typing into a filter should not have their next keystroke land somewhere else entirely |
| **Modal / drawer opens** (`components.md` §10) | The first interactive element — explicitly **never a destructive button** (already stated in §10, restated here as the general rule that section is one instance of) |
| **Modal / drawer closes** | Returns to the element that triggered it |
| **Route change** | The new view's primary heading, so the announcement (above) and the focus target are the same element |
| **Session/idle warning modal appears** (`auth-and-scoping.md`) | The "Stay signed in" button — the recoverable action, not the countdown |
| **A row the user is focused on is acted on by someone else** | Stays on that row's now-changed content (the `ALREADY_ACTIONED` state), never silently moved — the user needs to see what happened to the exact thing they were about to act on |

### The one open collision this file resolves

**U41's 5-second undo toast and screen-reader reachability are in direct tension**, and the tension is
real rather than theoretical: a toast a sighted user can click within 5 seconds may be functionally
unreachable for a screen-reader user who has to first hear the "assertive" toast announced, then navigate
to it, in the same 5 seconds.

**Resolution:** the undo affordance is **not toast-only**. It is also available, for the same window, as
a keyboard shortcut (`Cmd/Ctrl+Z`, matching the platform-standard undo gesture) that fires regardless of
where focus currently is, for the specific action just taken. The toast remains the visible/discoverable
form for a sighted mouse user; the shortcut is what makes the same 5-second guarantee actually reachable
for a keyboard/screen-reader user without requiring them to race a countdown to a specific pixel. This
does not extend the window — it adds a second, always-available path to the same window.

---

## Assistive-technology testing matrix

The minimum pairing set this spec is written against. Not exhaustive AT coverage — the pairing that
actually matters for the users this product has:

| Surface | Test with |
|---|---|
| Planner / ops / admin (Windows desktop) | NVDA + Chrome, NVDA + Firefox |
| Carrier portal | NVDA + Chrome (desktop-primary per `spacing-and-layout.md`'s breakpoint table) |
| Driver PWA | VoiceOver + Safari (iOS), TalkBack + Chrome (Android) — both required, since the driver base is not assumed single-platform |
| Gate kiosk | Not a primary AT target — device-bound, single-purpose tablet — but must not actively break if a device-level screen reader is enabled, since accessibility software on a shared kiosk is a real possibility outside this product's control |

A screen not tested against its row's pairing has not been verified accessible, regardless of how
carefully the ARIA was written — attribute correctness and actual announcement behaviour diverge often
enough between AT/browser combinations that this list is a requirement, not a suggestion.
