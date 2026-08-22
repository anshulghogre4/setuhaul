# Ops exception console — edge cases

## 1 · SLA breach while owned and in progress

An acknowledged, in-progress escalation crosses its SLA deadline before resolution.

- SLA clock transitions `escalation-sla-warning` → `escalation-sla-breach` (`color.md`) — colour change
  only, `instant` (`motion.md`'s threshold-crossing rule, U77), never a gradual fade a coordinator could
  miss.
- The row does **not** re-sort out of the coordinator's current view if they have it focused (U19) — a
  breach happening under someone's eyes must not also relocate the thing they're looking at.
- Breach does **not** auto-escalate further or auto-reassign. §7.4 gives ownership meaning precisely because
  someone chose to take the work; an automatic reassignment on breach would recreate "just a list" with an
  extra step.
- A breached, still-open escalation is the one case that legitimately competes with a fresh unowned-immediate
  arrival for the top of the queue (U95 sorts unowned above owned regardless of breach) — this is
  intentional: an *owned* item, even breached, has a named human already accountable for it; an *unowned*
  item has nobody, which is the worse state.

---

## 2 · Two coordinators acknowledge the same escalation simultaneously

The ops-side instance of the nastiest race in the product (`SOLUTION_DESIGN.md` §9.2 #3, generalised from
`confirm_request`/D9 to `escalate`/acknowledge).

- Both coordinators' clients believe their Acknowledge succeeded. Server-side, exactly one commits under
  the same transactional discipline as §9.2's original case.
- The loser's UI receives `ALREADY_ACTIONED` with the winning owner named — same shape as §7.5.1's
  `confirm_request` outcome, reused rather than inventing a parallel one.
- Per `accessibility-behaviour.md`'s politeness matrix: if the loser is **focused on that exact row**, the
  update is `assertive` — this is the one case the matrix calls out by name as needing interruption ("a
  user about to act on a row that just changed underneath them must be interrupted, not politely queued").
  If they're not focused on it, the change is silent per the same matrix's frozen-sort-on-focus extension.
- The row updates in place to show the winning owner — never removed and re-inserted, which would read as
  a new escalation rather than the same one someone else claimed.

---

## 3 · Driver replies mid-takeover / driver goes silent mid-takeover

- **Replies**: message renders in the thread immediately, same three-tier sender rendering as
  `01-driver-chat/` (U47) — driver messages are never held back from ops the way option-card staleness
  might hold back driver-side content.
- **Goes silent**: no timeout-driven auto-hand-back. A coordinator's takeover does not expire on its own —
  §7.4 gives no SLA for "driver stopped responding," and inventing one would be an unstated policy, not a
  spec-grounded one. The coordinator hands back manually (Flow 2) when they judge the thread no longer
  needs a human, or leaves it active indefinitely while waiting.

---

## 4 · Co-pilot returns a draft that references stale context

The thread advances (driver replies, or another coordinator's action changes the shipment state) while a
draft is being generated or sits unapproved.

- On generation completing against now-stale context: the draft-reply card renders with a visible **stale**
  marker (`components.md` §4's stale state) — "Thread updated since this was drafted" — rather than
  silently presenting outdated advice as current.
- A stale draft can still be Approved or Discarded, but Approve carries the same marker into the composer
  as a reminder before Send — the coordinator, not the system, decides whether the draft is still good
  advice.
- This never blocks manual reply — the composer is always available independent of draft freshness.

---

## 5 · Co-pilot unavailable or erroring

- Every co-pilot action degrades independently and visibly (`components.md` §3's per-action error copy) —
  a failure in "Fetch context" does not disable "Summarise thread" or the composer.
- The console is **fully operable with the co-pilot entirely down** — takeover, manual reply, acknowledge,
  resolve, cancel, reassign, and incident triage have no dependency on it. This is the direct consequence
  of `auth-and-scoping.md`'s degradation policy (U84): the co-pilot is **secondary** — it enriches the
  takeover workflow but the workflow's actual job (a human replying to a driver) does not require it. On
  failure it simply doesn't offer results; it never blocks the primary path.

---

## 6 · `NOTIFICATION_UNROUTABLE` vs `NOTIFICATION_FAILED` — must not look alike

Directly from §7.4's own distinction: one fails before a send is attempted (no valid recipient), the other
fails in flight. Different fix, different owner — the interface must not collapse them into one generic
"notification problem."

- Different icons (`iconography.md`): `mail-x` (`UNROUTABLE`) vs `mail-warning` (`FAILED`) — chosen
  specifically distinct, per the iconography file's own note.
- Different reason text in the detail pane: `UNROUTABLE` names the missing/invalid contact field and
  routes toward fixing the contact record; `FAILED` names the failed channel and offers a retry.
- `UNROUTABLE`'s resolution is **never** "retry send" — retrying against a NULL recipient is pointless, and
  offering that action would mislead the coordinator into believing retry is the fix.

---

## 7 · A capacity incident's affected set changes after the proposal was requested

Between requesting a sequencer proposal (Flow 4) and a planner acting on it, a new shipment becomes affected
(a further cascading conflict) or an already-affected shipment resolves independently (e.g. cancelled).

- The incident row's affected count is **not frozen** at request time — it reflects the current true set,
  consistent with the rule that a stale count is worse than a changing one on a primary-classified region
  (`auth-and-scoping.md`'s degradation policy, U84).
- If the set changes after the proposal was generated, the planner-side surface (`03-planner-dock-board/`,
  out of this file's scope) is responsible for re-validating before applying — this file's obligation ends
  at making the ops-side count honest, not stale.
- The ops queue row does not need a second "Request proposal" click for a set that grew — the existing
  request already covers the incident; this is stated so it isn't assumed to require re-triggering.

---

## 8 · Hand-back attempted on a thread the assistant can no longer serve

E.g. the shipment underlying the thread was cancelled or the exception it was created for no longer exists.

- Hand-back still succeeds mechanically (assistant auto-reply re-enables), but the console surfaces a
  warning before confirming: *"This thread's shipment has changed since takeover — the assistant may not
  have current context."* Non-blocking — the coordinator can proceed anyway, but not silently.
- This is a `feedback-warning`-toned inline notice (`color.md`), not a modal — consistent with U41's
  "no confirmation modals for routine actions," treating this as informational rather than a gate.

---

## 9 · Escalation on a shipment confirmed or cancelled elsewhere underneath the coordinator

A planner confirms (or rejects, or another process cancels) the shipment an open escalation refers to,
while a coordinator is actively working that escalation.

- The escalation does **not** auto-resolve or auto-cancel — the underlying event and the escalation's own
  lifecycle are tracked separately, since automatically closing an escalation the coordinator hasn't
  actioned would silently discard whatever work-in-progress note or partial takeover existed.
- The detail pane surfaces the new fact inline ("SHP1015 was confirmed by another planner at 09:58") as
  soon as it's known, using the same `assertive` announcement treatment as edge case #2 if the coordinator
  has that row focused.
- The coordinator is left to Resolve or Cancel deliberately, with the new fact as visible context for that
  decision — matching Flow 6's requirement that closing an SLA-tracked item always states a reason.

---

## 10 · `WAREHOUSE_REPLY_CONFLICT` — never offered an auto-reconcile path

§7.4: "reply contradicts stored schedule … Immediate, never auto-reconcile." The interface must not make
automatic reconciliation *look* available even as a convenience shortcut.

- No "Accept warehouse's version" / "Keep our version" one-click resolution exists anywhere in this
  reason's detail pane — both the stored schedule and the conflicting reply render side by side, read-only,
  and the coordinator's only path forward is the ordinary takeover → manual resolution flow (Flow 2), same
  as any other reason.
- This is a genuinely different posture from `NOTIFICATION_FAILED`'s retry action (edge-cases.md #6) —
  retry is safe to automate because it re-attempts an idempotent send; reconciling two conflicting accounts
  of a schedule is a judgment call that must not be automated even partially, since a wrong auto-merge is
  indistinguishable from a correct one until it's too late.
- Resolving this reason still requires a stated reason code (`ISSUE_FIXED`) per Flow 6 — there is no
  reason-specific shortcut that skips that requirement either.

---

## 11 · `SAFETY_OR_REGULATED` — co-pilot draft suppressed, human-composed reply only

§7.4: "brief §9.3 … Immediate, human-only." The same liability-adjacent category `voice-and-tone.md`'s
refusal templates (U61) already treat specially.

- On selecting an escalation with this reason, the co-pilot panel's **Draft a reply** action renders
  Inactive immediately (`components.md` §3, §18) — not after an attempt fails, so a coordinator never
  wastes a generation cycle on a reply that was never going to be offered.
- **Summarise thread and Fetch context remain available** — gathering context carries none of the
  liability a drafted message does, and a coordinator working a safety escalation still benefits from
  quick context-gathering.
- If takeover occurs, the composer is fully human-typed with no pre-filled text from any source. The
  reply-preview discipline already used elsewhere (`components.md` foundations §11's "nobody sends copy
  they haven't read") applies with extra weight here — but there is no co-pilot draft to preview in the
  first place, since one was never generated.
- This suppression is **reason-specific, not takeover-wide** — a coordinator handling a `NOTIFICATION_
  FAILED` escalation on an adjacent thread still has full co-pilot access; only the safety-reason
  escalation's own draft action is affected.
