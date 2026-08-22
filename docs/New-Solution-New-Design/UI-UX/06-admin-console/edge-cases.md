# Admin console — edge cases

## 1 · Removing a user who is the sole owner of an active escalation

An ops coordinator with an open, acknowledged escalation gets removed. The escalation itself does not
disappear or auto-resolve (matching `02-ops-exception-console/`'s own edge-case #9 principle — an
underlying event never silently closes an SLA-tracked item). The Remove confirmation names this explicitly
("This user owns 2 active escalations — they will show as unowned once removed") so the admin isn't
surprised later by a spike of newly-unowned work; removal still proceeds if confirmed, since blocking it
entirely would let a departed employee's account linger indefinitely.

## 2 · Deactivating a user mid-shift on a shared kiosk (gate/yard)

`04-gate-yard-kiosk/`'s shift model (U111) stamps officer identity once per shift, locally on the device —
deactivating that user's account here does not retroactively invalidate events already written this shift,
and does not force an immediate kiosk-side session end. The next shift-start on that device, under the
deactivated name, is what actually surfaces the block (a sign-in failure, handled by
`auth-and-scoping.md`'s existing sign-in flow, not a new mechanism this console needs to specify).

## 3 · Two admins editing policy weights concurrently

Admin A runs a simulation, then Admin B publishes a new version before A publishes theirs. A's own
Publish attempt now targets a `policy_versions` row that's no longer current.

- The tool refuses with a named conflict (not a silent overwrite) — same shape as every other
  "someone else acted first" race already resolved elsewhere (`confirm_request`'s `ALREADY_ACTIONED`,
  `acknowledge_escalation`'s equivalent).
- A's editor re-fetches the now-current version (B's) as its new baseline and marks A's own simulation
  stale, requiring a fresh simulate-then-publish pass against the actual current state — A cannot publish
  blind on top of a policy they never actually compared against.

## 4 · A facility rule edit invalidates already-confirmed appointments

Tightening `NEW_START_CUTOFF` from 21:00 to 20:00 could make an already-`CONFIRMED` appointment at 20:30
retroactively non-compliant. This is deliberately **not** auto-cancelled or auto-flagged as an exception by
this edit — `components.md` §2's High-tier confirmation names the count of affected appointments *before*
the edit commits, giving the admin the choice to proceed or not, but the edit itself does not reach into
`appointments` and mutate or escalate them. Facility rules govern *future* feasibility checks; they are not
retroactively applied to already-confirmed capacity, consistent with D1's exclusion-constraint model never
un-committing a promise from outside the planner/ops action paths that own that decision.

## 5 · Exporting an audit log filtered to a date range with zero matching events

Named empty state (`components.md` foundations §13) rather than a zero-byte or malformed CSV download —
"No events match this filter" with the export action disabled until the filter returns at least one row,
so an admin never receives a file and has to guess whether it's empty because nothing happened or because
something went wrong.

## 6 · Enabling the fairness term, then immediately publishing without simulating the non-zero value

Flow 7 makes `w_fairness` editable but does not itself publish anything. If an admin sets it to a non-zero
value and attempts Publish without running Flow 6's simulation against that specific value, Publish is
disabled — same staleness rule as any other weight-field change (`components.md` §5). There is no separate
bypass for the fairness field; it re-enters the ordinary weight-editor discipline the instant the Danger-
zone gate has been passed.

## 7 · A `rule_type` is retired or renamed in a future schema revision

Not a live concern today (the registry is fixed per this checkpoint's grounding — `EARLY_LIMIT`,
`DOCK_PIN`, `WEIGHT_LIMIT`, `NEW_START_CUTOFF`, etc.), but worth stating as a known evolution path: existing
rules referencing a retired type render read-only with a note ("This rule type is no longer editable through
this console") rather than breaking the editor or silently reinterpreting the stored value under a new
type. `Source: assumption, untested` (U88) — no such retirement has happened yet; this is a stated
intention for when it eventually does, not a built or tested path.

## 8 · Searching for a user by an email that matches a removed account

`list_users` only returns active/inactive/pending accounts by default — a genuinely removed user does not
reappear in search. This is intentional: `remove_user` is the one truly destructive action on this console
(`edge-cases.md` #1's High tier), and its removal should actually mean gone from this view, not merely
hidden-but-findable. Historical reference to a removed user's past actions still exists in the Audit tab
(actor id preserved, per `components.md` §6), which is the correct place to look for "what did this person
do," not the Users tab.
