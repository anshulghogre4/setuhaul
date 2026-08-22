# Planner dock board — edge cases

## 1 · The nastiest race in the product (`SOLUTION_DESIGN.md` §9.2 #3)

`confirm_request` and the D9 expiry sweeper firing on the same row. Both actors believe they acted.

- Server-side, the sweeper's transition and the confirm take the row under the same transaction — exactly
  one commits.
- The loser's UI receives `ALREADY_ACTIONED` **with the winning transition named** — never a bare error. A
  planner who clicks Confirm and sees the slot vanish gets told what happened, not just that it failed.
- If the planner is focused on that exact row when this resolves, the update is `assertive`
  (`accessibility-behaviour.md`'s "a user about to act on a row that just changed underneath them must be
  interrupted, not politely queued"). If unfocused, the row updates silently per U19's frozen-sort rule.
- The row does **not** disappear and reappear — it updates in place to show the actual outcome, so the
  planner can see what won without losing their place in the queue.

## 2 · `SNAPSHOT_STALE` on confirm

The planner's rendered view is older than the current server state, but no actual conflict exists (unlike
`DISPLACEMENT_DETECTED`, below). Row re-renders with fresh data; the confirm is not silently retried
against stale data — the planner reads the refreshed row and decides again. Costs one extra glance, not a
false confirm.

## 3 · `DISPLACEMENT_DETECTED` on confirm

A real conflict appeared since render — someone else's action would be quietly hurt by this confirm.
Refuses outright, re-renders the displacement column with the new conflict named (never truncated,
`components.md` §1). This is §7.3's "the single most important field" doing its actual job under load, not
just at first render.

## 4 · `RUN_ALREADY_ACTIVE` — a sequencer run requested while one is already running for this facility

§5.1's debounce rule (one run per facility, serialised) expressed as a UI outcome. The "Request
re-sequence" / "Request sequencer proposal" action shows an inline state ("A re-sequence is already
running — you'll be notified when it's ready") rather than a bare rejection, since this is an expected,
recoverable condition, not a failure.

## 5 · `SNAPSHOT_DRIFT` / `PARTIALLY_INFEASIBLE` on apply

Covered in `flows-and-states.md` Flow 9 steps 4–5; restated here as the edge case it is: **applying a
proposal is never a blind retry.** Drift means the world moved since the proposal was computed (a new
request, another action) — the fix is a fresh proposal, not forcing the stale one through. Partial
infeasibility means the whole batch is invalid together — the tool's own all-or-nothing contract means
there is no "apply what's still valid" fallback to offer, and the UI does not pretend otherwise.

## 6 · `HOLD_ALREADY_USED`

Covered as a Disabled-state rule in `flows-and-states.md` Flow 4 and `components.md` foundations §1 — an
attempted second hold is prevented before the call, not after a rejected request. Restated here because
it's the one place on this surface where the *prevention* (disabled control, tooltip) matters more than
the *error handling* (there should be no error to handle if the UI does its job).

## 7 · Bulk confirm's server-side re-check drops a row that looked eligible at select-time

Between clicking "Select all eligible (N)" and pressing Confirm, a selected row's eligibility genuinely
changes (e.g. an escalation opens on it from another surface). The server re-checks at press time
(§7.3/`components.md` §6) and the per-id outcome list reflects reality, not the stale client selection.

- The skipped row **stays visible in the queue**, not silently removed — a planner needs to know it still
  needs individual attention.
- The summary toast names it specifically ("5 confirmed, 1 skipped — SHP1013 no longer eligible"), not
  just a count mismatch a planner would have to investigate.
- This is not a bug to design around — it's the exact reason `bulk_confirm` re-checks server-side at all
  (§7.3: "rather than trusting the client's selection").

## 8 · Blocking a dock that already has confirmed appointments inside the window

The block-dock form's affected-appointment warning (`screens.md` §5, `components.md` §6) is the honest,
mandatory version of this — but the edge case worth stating explicitly is what happens *after* submission:

- The `BLOCKED` response's affected-appointment set is what the backend uses to open the
  `CAPACITY_EVENT_CASCADE` escalation — this surface does not create the escalation, only triggers the
  condition that causes it.
- **The board's own display updates immediately** (the outage marker appears) even though the
  affected appointments' own `dock_occupancy` rows haven't been resolved yet — a blocked dock is
  immediately true; what happens to the stranded appointments is a separate, slightly slower process
  (the escalation lifecycle in `02-ops-exception-console/`).
- This is the seeded DEVT001/SHP1005 scenario, made reachable as a real planner-initiated action instead of
  only pre-seeded data — the interface must handle a planner triggering it live exactly as gracefully as
  the pre-seeded case.

## 9 · A capacity incident's sequencer proposal arriving while its originating ops escalation is still being triaged

Ops requests a proposal (their Flow 4) before acknowledging the escalation, or while a different
coordinator is still working it. The proposal arrives on this surface regardless of the escalation's own
lifecycle position — **the two are linked by `scheduling_run_id`/`escalation_id` but track independently**
(same principle as `02-ops-exception-console/`'s own edge-case #7: an incident's affected set isn't frozen
at request time). A planner can review and apply the proposal even if the ops-side escalation is still
`OPEN` — applying the schedule fix does not require the escalation to be `ACKNOWLEDGED` first, since
capacity correctness (this surface's job) and ownership/triage (ops's job) are genuinely separate concerns
that must not block each other.

## 10 · Counter-offer picker opened, then the underlying request expires mid-pick

A planner is mid-pick on the board (§4) when the original request's own D9/TTL clock runs out before they
click a slot. The banner updates in place to reflect the expiry ("This request expired while you were
picking a slot") rather than letting a click silently fail against a row that no longer exists — the
picker session ends, returning to the Queue tab where the row now shows its expired state
(`PENDING_EXPIRED_UNACTIONED`, already a defined §7.4 reason should this become an escalation).
