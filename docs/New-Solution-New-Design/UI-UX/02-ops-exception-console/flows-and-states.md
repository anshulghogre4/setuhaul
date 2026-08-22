# Ops exception console — flows and states

## Flow 1 · Triage an escalation

The default path for every reason in §7.4's table, from arrival to a terminal state.

```
OPEN ──Acknowledge (U92)──▶ ACKNOWLEDGED ──▶ IN_PROGRESS ──▶ RESOLVED
                                                    │
                                                    └──▶ CANCELLED
```

1. Escalation arrives in the queue pane, sorted by U95's rule. If it's the first unowned-immediate item,
   it's now at the top.
2. Coordinator selects the row → detail pane opens in **read-only-thread mode** (`screens.md` §3). Nothing
   about selecting a row is destructive or committing — a coordinator can select, read, and move on.
3. **Acknowledge** → stepper advances to `ACKNOWLEDGED`, owner is set to the acting coordinator (U92). This
   is also the moment `IN_PROGRESS` becomes reachable — the escalation is now genuinely being worked, not
   merely looked at.
4. Coordinator works the reason-specific resolution (§7.4's table: fix a contact record for
   `NOTIFICATION_UNROUTABLE`, retry a send for `NOTIFICATION_FAILED`, take over the thread for
   `AMBIGUOUS_SHIPMENT`, request a sequencer proposal for `CAPACITY_EVENT_CASCADE` — Flow 4 below). Advancing
   to `IN_PROGRESS` is a status the coordinator sets explicitly once real work has started, not an automatic
   side effect of acknowledging.
5. **Resolve** vs **Cancel** — two different terminal states with two different meanings, not
   interchangeable "done" buttons:
   - **Resolve**: the underlying issue is fixed. If a takeover was active, the driver has been told the
     outcome via the thread before this fires (enforced by `screens.md` §3b keeping Resolve inside the
     takeover pane).
   - **Cancel**: the escalation no longer applies — e.g. the shipment itself was cancelled elsewhere. No
     resolution message is implied because there was nothing to resolve.

### Loading / empty / error
- **Loading**: skeleton queue rows matching final row height (`components.md` foundations §13) — never a
  centred spinner over the whole pane, which would hide the queue depth count a coordinator relies on.
- **Empty**: `screens.md` §6, the caught-up state (U74).
- **Error** (queue fails to load): "Couldn't load escalations — usually a connection problem." / [ Retry ],
  per the standard empty/loading/error anatomy (`components.md` foundations §13).

---

## Flow 2 · Take over a thread, post as OPERATIONS, hand back

1. From the detail pane (read-only-thread mode), coordinator presses **Take over thread** (U94).
2. Thread status becomes `ESCALATED` if not already; assistant auto-reply is disabled on this thread only —
   other threads are unaffected.
3. A driver-visible divider posts in the same conversation the driver is reading: *"A person has joined."*
   This is not a console-only artefact — the driver sees it in `01-driver-chat/` at the same moment.
4. Composer becomes interactive (`screens.md` §3b). Coordinator writes free text or uses a co-pilot draft
   (Flow 3).
5. **Hand back** — available once the escalation has reached `IN_PROGRESS` (`components.md` §5's rule: not
   offered on an unacknowledged escalation). Posts a symmetric driver-visible divider on hand-back, then
   restores assistant auto-reply.
6. If the driver replies after hand-back and the underlying issue recurs, a **new** escalation is created
   rather than reopening the resolved one — consistent with `SOLUTION_DESIGN.md`'s general rule that a
   closed record stays closed and a fresh problem gets a fresh record with its own audit trail.

### States
- **Composer disabled** (pre-takeover): read-only thread, label states why (`components.md` §5's
  Inactive/Read-only distinction — this is genuinely Read-only, not Inactive, since there's nothing to
  explain by activating it; taking over is the explicit unlock).
- **Composer enabled** (post-takeover, pre hand-back).
- **Composer disabled again** (post hand-back): same read-only shape as before takeover, but the thread
  history now shows the completed human exchange.

---

## Flow 3 · Draft a reply with the co-pilot and send it (U90)

The full gate sequence, stated once here since `components.md`'s draft-reply card only specifies the
component, not the end-to-end flow.

```
[ Draft a reply ] ──▶ loading ──▶ Draft-reply card
                                       │
                        ┌──────────────┼──────────────┐
                        ▼                              ▼
                   [ Discard ]                   [ Approve → ]
                   card removed,                  text moves into
                   nothing sent                    the composer, editable
                                                          │
                                                          ▼
                                                   coordinator edits
                                                   (or doesn't) and
                                                   presses [ Send ]
                                                          │
                                                          ▼
                                                   message reaches
                                                   the driver
```

- **Two reads, two gates.** The coordinator sees the exact string in the draft card, decides whether it's
  worth sending at all (Approve/Discard), then sees it again in the composer before Send. Neither gate is
  skippable — there is no "Approve and send" combined action.
- If the coordinator edits the text after Approve, what gets sent is the **edited** text — Approve is not
  a commitment to the co-pilot's exact wording.
- Discard at the card stage requires no confirmation (Low-tier, `components.md` §19's destructive-action
  tiering) — nothing was ever shown to the driver, so there's nothing to lose.
- Send follows the ordinary thread-composer send path (`ai-chat-primitives.md`'s `ComposerPrimitive`) — no
  special co-pilot-originated send behaviour, deliberately, so a message's origin (typed vs. drafted) is
  invisible to the delivery mechanism once approved.

---

## Flow 4 · Triage a capacity incident and request a sequencer proposal (U93)

1. Incident arrives as a single queue row (`components.md` foundations §17) — never as N separate
   escalations, regardless of how many shipments are affected.
2. Coordinator expands the row → reads the affected shipment list, read-only (`screens.md` §5).
3. **Request sequencer proposal** — the coordinator's only action on the incident itself. This does not
   apply any capacity change; it asks the sequencer (D5) to compute one.
4. Row updates to a handoff state: *"Proposal requested · routed to Planner queue · N shipments awaiting a
   planner's review."* The incident row **persists** in the ops queue in this state — it does not
   disappear once handed off, since the coordinator who triaged it may still need to track it to
   resolution.
5. A planner applies (or rejects) the proposal in `03-planner-dock-board/` — out of this file's scope past
   the handoff, per U93's division of responsibility.
6. Once the planner's action resolves all affected shipments, the incident row in ops reflects a resolved
   state and can be marked `RESOLVED` on the escalation lifecycle (§7.4's `CAPACITY_EVENT_CASCADE` reason),
   closing the loop the coordinator opened in step 1.

### Why this is a flow and not just a component rule
The incident is the one item in this console that is **worked by two different roles across two different
surfaces**, and the moment of handoff is exactly where "who owns this right now" could otherwise go
ambiguous — the explicit handoff state in step 4 is what keeps that from happening.

---

## Flow 5 · Reassign an escalation to another owner

1. From an acknowledged (or later) escalation's owner control (`components.md` §2), coordinator opens
   **Reassign**.
2. Combobox of ops-scoped coordinators, same-facility/team scope only (`auth-and-scoping.md`).
3. Selecting a name reassigns immediately — Low-tier action (`components.md` foundations §19), no
   confirmation, since reassignment within an already-owned escalation is low-consequence and reversible by
   reassigning again.
4. Stepper position and SLA clock are **unaffected** — only the owner field changes. History (who
   acknowledged, when) is preserved, not overwritten.

---

## Flow 6 · Resolve vs. Cancel — the two terminal states

Stated as its own flow because conflating these is the likeliest real mistake a coordinator could make
under time pressure.

| | Resolve | Cancel |
|---|---|---|
| Meaning | The underlying issue is fixed | The escalation no longer applies |
| Typical trigger | `NOTIFICATION_FAILED` retried and confirmed delivered; `AMBIGUOUS_SHIPMENT` clarified via takeover; capacity incident's affected shipments all resolved | Shipment cancelled elsewhere; escalation created in error; duplicate of another open escalation |
| Driver notified? | Only if a takeover occurred and the thread's own resolution message already covers it — Resolve itself does not send a separate message | Never automatically — a cancelled escalation implies nothing changed from the driver's perspective |
| Reversible? | New escalation on recurrence (Flow 2, step 6), not reopening | Same — no reopening |

Both require selecting a **reason** before committing — `resolve_escalation` / `cancel_escalation`'s
`reason_code` argument (`SOLUTION_DESIGN.md` §7.5.5), mirroring the reject flow's controlled-vocabulary
discipline (`components.md` foundations §11). A bare "Resolve" or "Cancel" button with no reason leaves no
audit trail for why an SLA-tracked item closed.

| Action | `reason_code` values |
|---|---|
| Resolve | `ISSUE_FIXED` |
| Cancel | `SHIPMENT_CANCELLED` · `DUPLICATE` · `CREATED_IN_ERROR` |

**`Source: assumption, untested`** (U88) — unlike `reject_request`'s `reason_code` (§7.5.1), no seeded
case in `SOLUTION_DESIGN.md` grounds this exact value set; it's inferred from what §7.4 already
distinguishes rather than drawn from an existing example. Revisit if real usage surfaces a reason these
three don't cover.
