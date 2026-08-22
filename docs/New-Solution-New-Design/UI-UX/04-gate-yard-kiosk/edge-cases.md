# Gate/yard kiosk — edge cases

## 1 · `ALREADY_CHECKED_IN`

An officer attempts to gate-in a truck that already has a `facility_checkins` row for this visit — likely
a second officer acting on the same truck, or the same officer re-searching after not seeing the first
outcome clearly. Outcome banner states the existing check-in's timestamp plainly ("Already gated in at
17:52") rather than a bare rejection — the officer needs to know this isn't a new fact, it's a duplicate
of one already recorded. Routes to Flow 8 exactly like a success would, since from the officer's position
the truck genuinely is gated in, whoever did it.

## 2 · `NO_ACTIVE_APPOINTMENT`

A truck arrives with no matching appointment — could be a genuine walk-in, a data problem upstream, or a
shipment whose appointment was cancelled without the driver knowing. This is not a state the kiosk can
resolve on its own (it has no scheduling controls, per `auth-and-scoping.md`'s "what each role never
sees" table). Outcome banner states the fact plainly and offers no further kiosk action — the officer's
real-world next step (calling the facility office, holding the truck in the yard) is outside this
surface's scope, same boundary the rest of the product draws between control-plane action and
conversation-plane/human judgment calls.

## 3 · `INVALID_TRANSITION`

The server rejects a queue-state transition the kiosk itself shouldn't have offered, given U110's
one-valid-action design. Two realistic causes: **(a)** two devices (gate-booth and yard tablet, U108) act
on the same truck in close succession and the kiosk's local view of the truck's state is stale by the time
the tap lands: outcome banner states this plainly ("This truck's status changed — refreshing") and
re-fetches the truck's current state, re-rendering Flow 2 with the now-correct one action rather than
retrying the same rejected transition. **(b)** A genuine bug in the state-mapping table
(`screens.md` §3) — worth stating as a possibility so `INVALID_TRANSITION` is never silently swallowed or
retried blindly; if it recurs for the same transition repeatedly, that's a signal the mapping itself needs
review, not just a transient race.

## 4 · `DOCK_OCCUPIED`

The confirmed dock has another truck's interval genuinely live when dock-in is attempted. This is a real
operational conflict, not a UI bug — the officer cannot resolve it from the kiosk (no scheduling controls
here either). Outcome banner states which dock and, if known, states the truck should wait in the yard
queue rather than attempt dock-in again immediately — the officer's next kiosk action is naturally "Call to
dock" again once the conflict clears, which the state table already offers without needing a special case.

## 5 · Two devices (U108) racing on the same truck

A gate-booth officer and a yard-tablet officer both search the same shipment within seconds of each other
— realistic given trucks move from gate to yard to dock in a short window. Neither device holds a lock; the
server's own state machine (§7.5.2: "the state machine is enforced server-side, not by the kiosk") is what
actually decides which action wins. Whichever device acts second on a now-superseded state gets
`INVALID_TRANSITION` (edge case #3) and re-renders with the truck's real current state — there is no
special cross-device coordination mechanism, because none is needed: the state machine itself is the
coordination mechanism.

## 6 · Searching a truck that has already completed its full cycle

A shipment already gated out (`Flow 7` complete) gets searched again — a genuine repeat lookup, a
correction attempt, or simple confusion about which truck is which. The truck-identity card still renders
(the officer should be able to confirm what happened), but **no action button renders** — the state table
(`screens.md` §3) has no next action past `COMPLETED`+gate-out. The card states the terminal fact plainly
("Gate-out recorded 19:14 · dwell 1h 22m") rather than showing a disabled or greyed button, since there
genuinely is no action here at all, not a temporarily-unavailable one — `components.md` foundations §18's
distinction between Disabled (temporary) and simply absent applies directly.

## 7 · Offline / degraded connectivity

Inherited from `auth-and-scoping.md`'s degradation policy (U84), which states it applies to "every internal
surface, not just the driver PWA" — restated here with this surface's own specifics rather than assumed
silently:

- **The one-dominant-button action is primary-classified** (`auth-and-scoping.md`'s primary/secondary
  split) — if connectivity can't be confirmed, the button goes Inactive with a reason ("Can't confirm this
  will save — check connection") rather than accepting a tap that might silently fail. A gate/yard write
  is exactly the kind of fact that must not be lost or duplicated by a hopeful offline submission.
- **The shift-identity session (Flow 0) is not connectivity-dependent** — it's a local device state, not a
  server write, so a brief connectivity drop mid-shift doesn't force a re-login.
- **Retry copy names what's safe**, per U84/U70's idempotency-key discipline: "Try again — this won't
  record it twice."

## 8 · Officer identity is wrong or needs correction mid-shift

An officer starts a shift under the wrong name (typo, or the previous officer forgot to end theirs). There
is no per-event correction mechanism on this surface — the fix is Flow 9 (end shift) followed by a fresh
Flow 0 under the correct name. Events already written under the wrong name are not editable from the
kiosk; correcting historical attribution, if ever needed, is an admin-console concern
(`06-admin-console/`, not yet written), consistent with this surface never carrying any capability beyond
the six `facility_checkins` writes it exists for.
