# Authentication and scoping

> Shared pattern, not repeated per surface (U29). Scope is derived server-side from verified tokens
> (§2, M15) — this file covers only the UI consequences.

## The governing rule

**The interface never decides what a user may see.** Scope arrives from the server, derived from the
authenticated identity. The UI's job is to render what it was given and to fail honestly when it was given
nothing.

This has one concrete consequence that is easy to get wrong: **out-of-scope destinations are absent from
the DOM, not hidden with CSS.** A carrier user's markup contains no ops console link at all. Hiding it
visually while shipping it to the client leaks the shape of the system and invites tampering.

---

## Sign-in

Single sign-in for all six roles. Role determines the landing surface, never a separate login page.

```
┌────────────────────────────────────────┐
│                                        │
│              SetuHaul                  │
│           Dock Command                 │
│                                        │
│  Email or phone                        │
│  ┌──────────────────────────────────┐  │
│  └──────────────────────────────────┘  │
│                                        │
│  Password                              │
│  ┌──────────────────────────────────┐  │
│  └──────────────────────────────────┘  │
│                                        │
│  [ Sign in ]                           │
│                                        │
│  Forgotten your password?              │
└────────────────────────────────────────┘
```

- **Email or phone in one field.** Drivers know their phone number; office staff know their email.
  Disambiguate server-side rather than making the user choose a tab.
- Password managers must work — correct `autocomplete` attributes, no paste blocking.
- **Errors never disclose whether an account exists.** "Those details don't match" for both wrong-user and
  wrong-password.
- Rate-limit messaging is explicit: "Too many attempts. Try again in 5 minutes." — a cause and a next
  action (U32), not a silent failure.

### Role landing

| Role | Lands on |
|---|---|
| `DRIVER` | Active thread, or shipment list if several |
| `OPERATIONS_EXECUTIVE` | Exception queue, cross-facility |
| `WAREHOUSE_PLANNER` | Pending queue for their default facility |
| `OPERATIONS_MANAGER` | Exception queue with escalations pinned |
| `GATE_OFFICER` | Yard queue for the device's facility |
| `TRANSPORT_MANAGER` | Carrier fleet status |
| `ADMIN` | Admin console overview |

**`GATE_OFFICER` added 2026-08-26.** This table shipped with six rows and no gate officer — even though
`SOLUTION_DESIGN.md` §2 marks the role ✅ for v1 with its own kiosk surface, §7.5.2 gives it five tools, and
this file's own "What each role never sees" table below already has a Gate officer row. Found during the
M5/E5.0 pass while deriving rail destinations per role. The landing target is grounded in §2's job list
("gate-in, **yard queue**, call-to-dock…") and §7.5.2's `update_queue_state`, not chosen. Note the facility
is the *device's*, not the user's: `auth-and-scoping.md`'s session table already makes the gate session
device-bound, so a gate officer does not pick a facility at sign-in.

A user with multiple roles picks once at sign-in and can switch from the user menu — the active role is
**always visible in the top bar**, because "which role am I acting as" changes what a click means.

---

## Driver onboarding

Drivers are the only role that may not have used software like this before, and the only one whose
notifications are now a lifeline (U17).

**Push permission is primed, never requested cold.** The browser prompt is one-shot — a denial is
effectively permanent, and a driver who denies it will not learn their hold lapsed.

```
Step 1  Sign in
Step 2  Confirm which load this is about (skipped if only one active)
Step 3  ┌──────────────────────────────────────────┐
        │  Stay informed about your slot           │
        │                                          │
        │  Dock slots can change while you're      │
        │  driving. Notifications let me tell you  │
        │  straight away instead of you finding    │
        │  out at the gate.                        │
        │                                          │
        │  [ Turn on notifications ]               │
        │  [ Not now ]                             │
        └──────────────────────────────────────────┘
Step 4  Browser prompt — only after "Turn on notifications"
```

- **"Not now" is a real option**, and the app remains fully usable without push. Re-ask only after an event
  the driver actually missed, framed by that specific event.
- If push is denied, the status line states it plainly: "Notifications are off — you'll need to keep this
  page open to see changes." Cause and consequence, no nagging.
- **There is no second channel if push is denied** (U17 revised — SMS dropped from v1, see
  `../../TECH-STACK/TECH_STACK.md` §6). This makes the status line above load-bearing rather than
  informational: a driver who declines push has *only* the in-app view, so the app must state that plainly
  and the thread list must always show current promise state on open. Re-asking after a genuinely missed
  event matters more under this constraint than it did when SMS backstopped it.

---

## Session expiry

Different failure modes per surface, and the driver case is the one that matters.

| Surface | Behaviour |
|---|---|
| **Driver** | Long-lived session. Silent refresh. **Never sign a driver out mid-exception** — they are at a roadside with a lapsing hold, and a login screen at that moment is a product failure. |
| **Planner / ops** | Idle warning at 55 min, sign-out at 60. Warning is a modal with [Stay signed in]. |
| **Gate kiosk** | Device-bound session, no idle timeout — an officer cannot re-authenticate with gloves on every few minutes. Signs out only on explicit action or shift change. |
| **Carrier / admin** | Standard idle timeout, 30 min. |

**On expiry, in-flight work is preserved.** A part-written rejection note or an unsent message survives
re-authentication and is restored. Losing typed work to a session timeout is unacceptable in every case,
and unforgivable when it is a driver's delay report.

---

## Driver offline behaviour (U68)

The same principle as session expiry, applied to connectivity rather than authentication: **a driver must
never lose access to what they already have because the network dropped.** Drivers are the users most
likely to lose signal, and the moment they most need the app — at a gate, mid-exception, with a hold
running down — is exactly when that's most likely to happen.

| Stays available offline | Behaviour |
|---|---|
| Thread history | Full read access to the cached transcript — a driver at a gate with no signal still needs to see their dock number |
| Current promise state | Last-known state renders normally, with a subtle "last updated" marker rather than a live countdown that can't be trusted |
| Confirmed appointment details | Dock, time, reference number — always available, this is the single most likely thing a driver needs offline |
| Outbound messages | **Queue and send on reconnect** (`voice-and-tone.md`'s `CONNECTION_LOST` template) — never lost |

| Disabled offline | Why |
|---|---|
| **Option cards (tapping to select/hold)** | This is the one deliberate restriction, and it is not a limitation to work around — it is protecting the product's central promise. A driver who taps an option offline cannot actually be granted a hold; queuing that action for later and silently succeeding or failing on reconnect is precisely the kind of stale-commitment risk this entire system exists to prevent (`SOLUTION_DESIGN.md` §7.1's snapshot-guard logic can't run against data the client hasn't seen in minutes). Option cards render **visibly disabled** with a one-line reason, not hidden. |
| New `find_feasible_slots` requests | Nothing to show — no live data to request against |

**The countdown's behaviour offline follows directly from `components.md` §3**: it already computes from
server time with a measured offset, so a stale local countdown does not free-run inaccurately — it holds
at last-known value with a "last updated Xm ago" marker rather than continuing to tick against a clock
that may no longer be trustworthy.

On reconnect: queued messages send, the thread re-syncs, and any option cards that were showing re-validate
against a fresh snapshot before re-enabling — silently, unless something changed, in which case the normal
`OPTION_WITHDRAWN` or a fresh set (`voice-and-tone.md`) explains what's different.

---

## Degradation policy (U84)

Offline (above) is the binary, easy-to-reason-about case: the network is simply gone. **Degradation is the
harder case that sits between fully-live and fully-offline** — the connection exists, a request is in
flight or partially failed, and data on screen may be stale by an unknown amount. This applies to every
internal surface, not just the driver PWA.

### Primary vs. secondary classification

Every region of every screen is one or the other, and the two fail differently:

| | Definition | On staleness/failure |
|---|---|---|
| **Primary** | The screen is not usable for its job without this | Goes **Inactive** (`components.md` §18) with a reason — never silently stale, never a dead disabled control |
| **Secondary** | Enriches the primary content but isn't required to act correctly | Simply **disappears** — no error state, no placeholder, nothing competing for attention over the thing that actually matters |

Concretely: the **dock board's occupancy data is primary** — a planner acting on stale occupancy could
confirm into a slot someone else just took, which is exactly the double-booking this whole system exists
to prevent. If its freshness can't be guaranteed, it goes Inactive with "Capacity data may be out of
date — refresh before confirming," and Confirm becomes Inactive too until it does. The **carrier on-time
sparkline (U66) is secondary** — if that data can't load, it just isn't there; nothing about it is worth a
retry button or an error message competing with the fleet list around it.

### Rules

- **Never conceal or downplay staleness on primary content.** No quiet "last synced" text in a corner when
  the data is actually load-bearing — see the Inactive treatment above.
- **Cap visible degradation notices at a handful per screen.** A page reporting five separate stale-data
  warnings has stopped being informative and started being noise; if that many regions are degraded, the
  honest signal is a single page-level notice, not five.
- **Muted, not alarming, colour for degradation notices.** A stale-data warning uses `feedback-warning`
  tokens (`color.md`), never `feedback-danger` — a page that *looks* like it's on fire when the real
  problem is "this number is 40 seconds old" trains people to stop trusting the danger colour when it
  actually matters.
- **Retry copy names what's safe, explicitly, for idempotency-keyed actions (U70).** Not "Try again" alone
  — "Try again — this won't double-book you." The whole point of an idempotency key is that retry-after-
  uncertain-failure is safe, and a user who doesn't know that will avoid retrying a Confirm that actually
  needs retrying, out of a reasonable fear of duplicating it.

---

## What each role never sees

M15 is a data-access rule; these are its interface consequences.

| Role | Never rendered |
|---|---|
| **Driver** | Other drivers' shipments. Their own ranking position. Why they lost a contested interval. Any planner-side control. |
| **Carrier manager** | Any other carrier's data, in any aggregate. Cross-carrier benchmarks. Ranking positions. **Not even a count** that would let one be inferred. |
| **Planner** | Facilities outside their assignment. Carrier commercial data. |
| **Gate officer** | Scheduling controls. Anything beyond the current facility's yard. |
| **Ops coordinator** | Policy weights (admin only). User management. |

### The inference risk, stated plainly

Aggregate figures can leak individual facts. "3 requests competed for this slot" tells a carrier something
about competitors' operations. **Carrier-facing views therefore show only that carrier's own data, with no
comparative or aggregate framing at all** — not "you ranked 2nd of 4", not "average carrier on-time is
87%". Their own numbers, and nothing that implies anyone else's.

This is the kind of leak that arrives through a well-meaning "helpful context" addition later, so it is
recorded as a rule rather than left to judgement.

---

## Scope failures

When a user reaches something outside their scope — a stale bookmark, a shared link, a revoked assignment:

```
        [ shield-off icon ]

    This facility isn't in your access scope

    You have access to Jaipur DC and Gurugram Cross-Dock.

           [ Go to Jaipur DC ]
```

- **Never a bare 403.** Name what happened and offer a route (U32).
- **Never confirm the resource exists.** "Isn't in your access scope" covers both cases without disclosing
  whether that shipment is real.
- Log to `audit_logs` — repeated scope failures are a signal worth having.
