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

Tightening `LAST_NEW_START_TIME` from 21:00 to 20:00 could make an already-`CONFIRMED` appointment at 20:30
retroactively non-compliant. This is deliberately **not** auto-cancelled or auto-flagged as an exception by
this edit — `components.md` §2's High-tier confirmation names the count of affected appointments *before*
the edit commits, giving the admin the choice to proceed or not, but the edit itself does not reach into
`appointments` and mutate or escalate them. Facility rules govern *future* feasibility checks; they are not
retroactively applied to already-confirmed capacity, consistent with D1's exclusion-constraint model never
un-committing a promise from outside the planner/ops action paths that own that decision.

**Built 2026-08-29 (A-G6, issue #74).** `GET /api/v1/admin/facility-rules/{rule_id}/impact` produces that
count. It is a pure read — `update_facility_rule` is unchanged, so the "does not mutate or escalate"
guarantee above is structural, not merely intended. The preview evaluates by calling the live engine's own
`active_facility_rules` + `check_facility_rules` rather than re-deciding rule semantics locally, so the
dialog and the check that will actually reject future bookings can never disagree — including on the
boundary this exact scenario turns on (RULE005 forbids starting *after* the cutoff, so 20:00 sharp against a
20:00 cutoff is still compliant). The scan is bounded by the **proposed rule's own effectivity window**, not
by `now()`: this engine has no injected clock (§9.1), and a wall-clock filter would return a confident
"0 affected" against any dataset whose snapshot clock differs from the wall clock.

*(The rule type in this scenario was written `NEW_START_CUTOFF` until 2026-08-29 — a name that was never
built. See `screens.md` §3's registry correction, A-G2/issue #70. The scenario itself is unchanged.)*

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

**Backed by a real term as of 2026-08-29 (A-G1, issue #69).** `w_fairness` now exists in
`constraints.json`'s `score_weights` at `0` and is genuinely evaluated by `feasibility.py::_rank_slot` and
by the simulator's copy of that formula, so a simulation run against a non-zero value returns a
`flip_count` the field actually produced. Before this, `weights` was an untyped map and a `w_fairness` an
admin typed was **silently dropped** — the staleness rule above would have been enforced against a
simulation that never used the value. The response now also carries `fairness_term_evaluated`, so the UI
can state that the term participated rather than inferring it. **`P_churn` is still not implementable** —
it counts promises the sequencer moved and the sequencer (issue #49) is unbuilt — but it is now **refused
by name with that reason** rather than accepted and ignored, so the Churn field on Screen 8 has an honest
server response to render instead of a false success.

## 7 · A `rule_type` is retired or renamed in a future schema revision

Not a live concern today (the registry is fixed by a live `CHECK` constraint — `LAST_NEW_START_TIME`,
`HEAVY_DOCK_REQUIRED_KG`, `REEFER_DOCK_REQUIRED`, `CHECKIN_EARLY_LIMIT_MIN`, `NO_SHOW_GRACE_MIN`), but worth
stating as a known evolution path: existing rules referencing a retired type render read-only with a note
("This rule type is no longer editable through this console") rather than breaking the editor or silently
reinterpreting the stored value under a new type. `Source: assumption, untested` (U88) — no such retirement
has happened yet; this is a stated intention for when it eventually does, not a built or tested path.

**A near-miss worth recording, because it is the case this edge case was written for and it went the other
way.** This section listed `EARLY_LIMIT`/`DOCK_PIN`/`WEIGHT_LIMIT`/`NEW_START_CUTOFF` as the live registry
until 2026-08-29. Those four were never built — they were `SOLUTION_DESIGN.md` §7.5.7's illustrative names,
and E3.4 shipped a different five (A-G2, issue #70). So the real event was not a *retirement* but a
**rename-before-launch that the design files never caught up on**, and the read-only-with-a-note behaviour
above would not have helped: no stored rule ever referenced the stale names, so nothing rendered wrong —
the docs were simply describing a registry that did not exist. The lesson is about verification, not about
this fallback: the engine's `CHECK` constraint is the registry, and a design file naming rule types should
be checked against it rather than against another design file.

## 8 · Searching for a user by an email that matches a removed account

`list_users` only returns active/inactive/pending accounts by default — a genuinely removed user does not
reappear in search. This is intentional: `remove_user` is the one truly destructive action on this console
(`edge-cases.md` #1's High tier), and its removal should actually mean gone from this view, not merely
hidden-but-findable. Historical reference to a removed user's past actions still exists in the Audit tab
(actor id preserved, per `components.md` §6), which is the correct place to look for "what did this person
do," not the Users tab.
