# Ops exception console — components

> Surface-specific components only. Anything shared — the escalation stepper, capacity-incident row,
> countdown, toast, undo affordance, form controls, unavailability taxonomy, queue conventions — is
> specified once in `../00-foundations/components.md` and cross-referenced, not restated.

## 1. Escalation queue row

Scoped variant of the shared queue component (`components.md` §19, U23), rendering an escalation rather
than a pending request.

### Anatomy
```
▌ ESC-104              Unowned
  NO_FEASIBLE_SLOT
  SHP1015 · Jaipur
  ⏱ 4:12 to breach
```

| Element | Rule |
|---|---|
| Priority marker | 3px left edge (`components.md` §5) — the shipment's own priority, not the escalation's |
| ID + owner | Owner name, or **"Unowned"** in `feedback-warning` colour (`components.md` §16) |
| Reason | Text label + icon from `iconography.md`'s Escalation reason table — never icon alone |
| Shipment · facility | Facility as **plain text**, no accent colour (U91) |
| SLA line | Uses `escalation-sla-ok` / `-warning` / `-breach` (`color.md`) — the row's only danger-colour-eligible element, matching §16's rule that the stepper's lifecycle dots stay neutral |

### §7.4 reason coverage

All nine reasons render through the anatomy above by default; five need no bespoke behaviour beyond their
icon and cause text (`iconography.md`). The other four are named explicitly here so none is silently
unhandled:

| Reason | Bespoke behaviour |
|---|---|
| `NO_FEASIBLE_SLOT` | None beyond default rendering |
| `PENDING_EXPIRED_UNACTIONED` | None beyond default rendering — SLA posture is Immediate since capacity was just released |
| `AMBIGUOUS_SHIPMENT` | None beyond default rendering |
| `LOW_CONFIDENCE_ETA` | None beyond default rendering — SLA posture is Soft, same as the "12m (soft posture)" example already in `screens.md` §2 |
| `WAREHOUSE_REPLY_CONFLICT` | **Never offers an auto-reconcile affordance.** §7.4 states this reason is "Immediate, never auto-reconcile" — see `edge-cases.md` #10 |
| `NOTIFICATION_FAILED` | Retry-send action available (edge-cases.md #6) |
| `NOTIFICATION_UNROUTABLE` | Retry-send **not** offered — different fix, different owner (edge-cases.md #6) |
| `SAFETY_OR_REGULATED` | **Co-pilot draft-reply is suppressed** — see §3 (Co-pilot panel) and `edge-cases.md` #11 |
| `CAPACITY_EVENT_CASCADE` | Renders as the capacity-incident row (§17, foundations), not this row shape |

### States
Default · hover (row background lifts one elevation level) · focused (keyboard, roving tabindex per
`components.md` §19) · selected (detail pane shows this row) · **stale** (row's underlying escalation was
acted on elsewhere — see `edge-cases.md` #2, `ALREADY_ACTIONED`).

### Rules
- **Unowned + immediate-SLA-posture rows sort to the top regardless of individual breach time** (U95) —
  the row itself carries no special visual marker for this beyond its position; the sort order *is* the
  signal, consistent with U19's frozen-sort discipline once a row has focus.
- Selecting a row **never** triggers takeover — it opens the detail pane in read-only-thread mode
  (`screens.md` §3). Takeover is always a separate, explicit act (U94).
- **No bulk actions on this queue, deliberately** (caught during a `checklist-design` audit against the
  Data Table checklist, which expects row selection + bulk actions by default). §7.4 never describes a
  bulk need the way §7.3 has `bulk_confirm` — every escalation genuinely requires individual judgment (a
  takeover decision, a reason-specific fix), and the shared queue foundation's selection/bulk model
  (`components.md` §19) is not instantiated here. This is a considered exclusion, not an oversight; if a
  real acknowledgment-spike case ever emerges (e.g. after a facility-wide outage), bulk-*claim* — narrower
  than planner's bulk-confirm, no capacity mutation involved — would be the addition to make, not bulk
  resolve/cancel.

---

## 2. Owner control (U92)

### Anatomy
```
Unowned  →  [ Acknowledge ]        (before)
Neha B.  →  [ Reassign ▾ ]         (after)
```

### Rules
- **Acknowledge names the actor and advances the stepper to `ACKNOWLEDGED` in one action.** No separate
  assignment step — the click that claims the work *is* the click that starts the SLA-owned clock.
- Reassign is a combobox of ops-scoped coordinators (never cross-facility scope leakage — the list is
  derived from the caller's own facility/team assignment, per `auth-and-scoping.md`'s scope rules).
- Reassigning does **not** reset the stepper or the SLA clock — only ownership changes. A reassigned
  escalation keeps its history and its deadline.
- "Unowned" renders in `feedback-warning` text colour wherever it appears (queue row, detail pane,
  stepper) — one token, every location, so a coordinator scanning for unowned work has one colour to look
  for, not several near-identical greys.

---

## 3. Co-pilot panel (U57)

Built on `AssistantSidebar` (`ai-chat-primitives.md`). Three actions, one hard scope boundary: present only
when the focused escalation's thread is under takeover (`chat_threads.thread_status = 'ESCALATED'` **and**
a human has actually taken over — see `edge-cases.md` for the distinction from merely-escalated).

### Anatomy
```
[ Summarise thread ]
[ Fetch context ]

── Draft reply ──────────
[ Draft a reply ]
```

### States

| Action | Idle | Loading | Result | Error |
|---|---|---|---|---|
| Summarise thread | Button, enabled | Button shows spinner, stays labelled (not replaced by a bare spinner — `components.md` §13's rule that loading never removes the action's own label) | 2–4 line condensed summary renders inline below the button, non-editable | Inline message: *"Couldn't summarise — the thread is still readable above."* Never blocks reading the actual transcript |
| Fetch context | Button, enabled | As above | Shipment / appointment / ETA history renders inline, same shape a driver-facing tool call would return (`ai-chat-primitives.md`) | Same pattern — degrades to "context unavailable," never blocks the console |
| Draft a reply | Button, enabled | As above | Draft-reply card (below) appears | *"Couldn't draft a reply — write one directly in the composer."* Co-pilot failure never disables manual reply |

### `SAFETY_OR_REGULATED` suppression

**Draft a reply is Inactive, not merely discouraged, when the focused escalation's reason is
`SAFETY_OR_REGULATED`.** §7.4 marks this reason "Immediate, human-only," the same liability-adjacent
category `voice-and-tone.md`'s refusal templates (U61) already treat specially. This is a hard rule, not a
per-coordinator judgment call — the button renders per `components.md` §18's Inactive contract (fully
focusable, explains itself on activation: *"Not offered on safety-related escalations — write this reply
yourself."*), never Hidden or silently absent. **Summarise thread and Fetch context remain fully
available** — only reply generation is suppressed, since context-gathering carries none of the liability
risk a drafted message does.

### Rules
- **Inactive, not Hidden or Disabled, when no takeover is active** (`components.md` §18) — the pane stays
  visible and explains itself ("Available once you take over a thread"), rather than disappearing or
  presenting a dead control. A coordinator should never wonder whether the co-pilot exists.
- **Summarise and fetch-context results are read-only context, not messages** — they never enter the
  thread transcript and never get a Send action. Only a drafted reply (§4, below) can cross into the
  composer.
- No action here ever posts to the driver directly. Every path that reaches the driver goes through the
  draft-reply gate (§4).

**Thread timestamps** (confirmed applicable here — a `checklist-design` Chat-checklist audit flagged this
as inherited-by-assumption, not stated): follow `data-formatting.md`'s counting-up relative-time bands
("Just now," "N minutes ago," absolute date past 24h), same as every other chat surface in this product.
No surface-specific deviation.

---

## 4. Draft-reply card (U90)

### Anatomy
```
"Your reefer's slot at D5 reopens after 22:00.
 I can offer you 22:15."

[ Discard ]              [ Approve → ]
```

### States
Drafting (co-pilot panel shows loading, no card yet) → **drafted** (card above, both actions enabled) →
**approved** (card collapses; text now sits in the thread composer, editable, unsent) → **discarded**
(card removed, nothing left behind) → **stale** (thread advanced while drafting — see `edge-cases.md` #4).

### Rules
- **Approve moves the text into the composer. It does not send.** This is the second of the two gates —
  the first is Approve itself, the second is the ordinary Send action already specified for the thread
  composer (`screens.md` §3b). A coordinator reads the exact string twice: once in the draft card, once in
  the composer, before it reaches the driver.
- Once in the composer, the text is **fully editable** — Approve is not a commitment to send verbatim, only
  a commitment to consider sending it.
- **Discard leaves no trace** in the thread or the composer — equivalent to the draft never having been
  generated.
- Never auto-populates the composer without an explicit Approve click, and never auto-sends under any
  condition (`ai-chat-primitives.md`: "a drafted message is a suggestion, not an action, until a human
  commits it").

---

## 5. Takeover control

### Anatomy
```
Before:  [ Take over thread ]
During:  ●───●───●───○     [ Hand back ]
```

### Rules
- **Takeover is a single explicit action**, never implied by acknowledging or escalating (U94). Pressing
  it: sets `thread_status = 'ESCALATED'` if not already, disables the assistant's auto-reply on this thread,
  enables the composer, and posts the driver-visible divider (`components.md` §7 sender-attribution rule /
  U47).
- **Hand-back** returns the thread to assistant auto-reply. Requires the escalation to be in
  `IN_PROGRESS` or later — handing back an `OPEN`/unacknowledged escalation isn't offered, since nobody has
  claimed responsibility for the decision that would need to be made if the driver replies immediately
  after.
- Both transitions post a driver-visible divider (`components.md` §7's three-tier sender model / U47): "a
  person has joined" on takeover, and an equivalent notice on hand-back — §7.4's "silent takeover reads as
  the bot ignoring them" applies symmetrically to silently leaving.
- The composer is only interactive while takeover is active — see `screens.md` §3 vs §3b for the two visual
  states of the same pane.

---

## 6. Facility identity (queue row, U91)

Plain text, no colour, no accent dot. Renders as `Facility name · [context]` (e.g. "Jaipur · Reefer dock")
inside a queue row, and is **omitted entirely** when the top-bar switcher is scoped to a single facility
(redundant once the whole console is already that facility). This is the direct consequence of U91: the
facility accent's only two safe render locations are the rail-edge stripe and the switcher swatch
(`color.md` §*Facility accent*), and this console's cross-facility rows must not open a third.
