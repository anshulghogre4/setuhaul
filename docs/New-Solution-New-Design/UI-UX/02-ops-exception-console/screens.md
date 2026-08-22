# Ops exception console — screens

> Surface: desktop, Windows-primary, keyboard-first, long dwell. Density `compact` — `spacing-and-layout.md`'s
> density table lists "Planner, ops console" together under `compact`, desktop-and-pointer only, which this
> surface is. Light theme default with dark at full parity (U69), user-switchable. Breakpoint: desktop-only
> per `spacing-and-layout.md`'s surface table — this console is not
> designed below ~1280px. Foundations: `../00-foundations/`. Chat primitives:
> `../00-foundations/ai-chat-primitives.md`.
>
> Structure derived from Checklist Design's *Data table* and *Chat* checklists (Web app) per U34 — see
> *Checklist coverage* at the end for what applies and what deliberately doesn't.

## The surface in one line

Cross-facility triage and thread takeover (§7.4). Escalations and capacity incidents, not pending requests
— those belong to `03-planner-dock-board/`. One screen, three persistent panes (U89): a coordinator works
fewer, harder items over longer dwell than a planner clearing a spike, and should never lose sight of the
queue while working one item.

---

## Screen map

```
Sign in ──▶ Console (single screen, three panes)
              │
              ├── Queue pane        (always visible)
              ├── Detail + thread   (populated on row selection)
              └── Co-pilot pane     (populated only under takeover, U57/U94)
```

There is no navigation *within* this surface beyond selecting a queue row — U89 deliberately trades screen
count for pane persistence. Sign-in, role landing and session expiry are specified once in
`../00-foundations/auth-and-scoping.md` and not repeated here.

---

## 1 · Console shell

```
┌──┬──────────────────────────────────────────────────────────────────────────────────┐
│▌ │ [All facilities ▾]        🔍 Search shipment, driver, carrier…    🔔  ?  ⚙︎ AB    │  56px top bar
├──┼───────────────────────┬──────────────────────────────────┬─────────────────────────┤
│▤ │ ESCALATIONS  (7)      │  ESC-104 · NO_FEASIBLE_SLOT       │  CO-PILOT               │
│  │ ─────────────────────  │  ──────────────────────────────  │  ───────────────────── │
│⚑ │ ▌ESC-104  Unowned      │  ●──●──○──○           Unowned    │  Available on           │
│  │  NO_FEASIBLE_SLOT      │  OPEN ACK IN-PROG RESOLVED        │  takeover threads only  │
│⏱ │  SHP1015 · Jaipur      │                    ⏱ 4:12 to SLA │                          │
│  │  ⏱ 4:12 to breach      │                                    │  [ Take over thread ]  │
│  │ ─────────────────────  │  ── Reason ──────────────────────  │                          │
│  │  ESC-102  Neha B.      │  Reefer SHP1015 pinned to D5      │                          │
│  │  NOTIFICATION_FAILED   │  (RULE003); D5 down 18:00–22:00   │                          │
│  │  SHP1009 · Gurugram    │  (DEVT002). No feasible slot in   │                          │
│  │  ⏱ 22m to breach       │  the search horizon.               │                          │
│  │ ─────────────────────  │                                    │                          │
│  │  ESC-099  Neha B.      │  ── Thread ───────────────────────  │                          │
│  │  AMBIGUOUS_SHIPMENT    │  Driver  Still waiting on a dock,  │                          │
│  │  DRV004 · Kota         │          what's happening?          │                          │
│  │  ⏱ 12m (soft)          │                                    │                          │
│  │ ─────────────────────  │  [ composer — disabled until       │                          │
│  │ ▶🔌 Capacity incident  │    takeover ]                       │                          │
│  │  DOCK-JAI-D3 · 4 shpts │                                    │                          │
│  │  09:15–13:00           │                                    │                          │
│  │  [Review incident]     │                                    │                          │
├──┴───────────────────────┴──────────────────────────────────┴─────────────────────────┤
│ ● Online · synced 4s ago     All facilities     7 pending     Policy v3                 │  28px status bar
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### Shell anatomy

| Element | Rule |
|---|---|
| Icon rail | 56px, per `components.md` §7 — ops destination only in the DOM for ops-scoped roles (U29). **Two destinations, deliberately minimal**: Escalations (this console — the only one, always active since there's nowhere else to navigate within the surface) and Profile. Mirrors `01-driver-chat/`'s two-destination bottom nav (Threads/Profile) rather than inventing extra rail items — nothing in `SOLUTION_DESIGN.md` gives an ops coordinator a second home screen, and `auth-and-scoping.md`'s role table explicitly excludes admin destinations from this role |
| Top bar | Facility switcher defaults to **All facilities** (U91) — rail accent stripe goes neutral in this state, since no single facility owns the view. Selecting one facility narrows the queue and restores that facility's accent on the rail edge, same behaviour as every other surface. |
| Queue pane | Fixed ~340px. Never collapses below a usable row width — narrower than that, this stops being the surface's job (desktop-only, per the breakpoint note above) |
| Detail + thread pane | Flexible width, takes remaining space. Empty state ("Select an escalation") when no row is selected |
| Co-pilot pane | Fixed ~320px. **Present but inert** until a takeover is active (U94) — never hidden entirely, so a coordinator always knows the capability exists; see *Co-pilot pane, inactive* below |
| Status bar | Per `components.md` §7 — connection, last sync, active facility scope (reads "All facilities" or a specific name), pending count, policy version |

---

## 2 · Queue pane (detail)

```
┌───────────────────────────┐
│ ESCALATIONS        (7)    │
│ [Filter: reason ▾] [⚙]    │
├───────────────────────────┤
│ ▌ESC-104        Unowned   │  ← unowned + immediate = pinned top (U95)
│  NO_FEASIBLE_SLOT          │
│  SHP1015 · Jaipur          │
│  ⏱ 4:12 to breach          │  ← escalation-sla-warning (amber)
├───────────────────────────┤
│  ESC-102        Neha B.    │
│  NOTIFICATION_FAILED       │
│  SHP1009 · Gurugram        │
│  ⏱ 22m to breach           │
├───────────────────────────┤
│  ESC-099        Neha B.    │
│  AMBIGUOUS_SHIPMENT        │
│  DRV004 · Kota             │
│  ⏱ 12m (soft posture)      │
├───────────────────────────┤
│ ▶🔌 Capacity incident      │  ← U65: one row, not four
│  DOCK-JAI-D3 · 4 shipments │
│  09:15–13:00               │
│  [ Review incident ]       │
└───────────────────────────┘
```

- **Sort**: time-to-SLA-breach ascending; unowned rows pinned above owned ones regardless of individual
  breach time (U95). Frozen while a row has focus (U19) — arrivals accumulate behind "N new · press R"
  exactly as the shared queue spec (`components.md` §19) already states.
- **Facility identity is plain text**, not an accent dot (U91) — "Jaipur", "Gurugram" read directly in the
  row. When the switcher is scoped to one facility, this line is redundant and the row omits it.
- **Filter** narrows by reason, owner (mine / unowned / all), or SLA posture — does not change sort, only
  membership. **Any active filter renders as a dismissible chip row beneath the filter control** ("Reason:
  NOTIFICATION_FAILED ✕" · "Owner: mine ✕") — caught missing in a `checklist-design` audit against the
  Data Table checklist. Without it a coordinator scanning "(7)" has no way to tell whether that count is
  the whole queue or an already-narrowed view.
- Capacity-incident row uses the shared component (`components.md` §17) verbatim — see `components.md`
  (this folder) for the ops-specific "Review incident" action target.

---

## 3 · Detail + thread pane — escalation (not yet under takeover)

```
┌────────────────────────────────────────────────┐
│ ESC-104 · NO_FEASIBLE_SLOT                      │
│                                                  │
│ ●───●───○───○              Unowned               │
│ OPEN  ACK  IN-PROG  RESOLVED    ⏱ 4:12 to breach │
│                                                  │
│ [ Acknowledge ]                                  │  ← U92: claim to self
│                                                  │
│ ── Reason ──────────────────────────────────────  │
│ Reefer SHP1015 pinned to D5 (RULE003); D5 down    │
│ 18:00–22:00 (DEVT002). No feasible slot in the    │
│ search horizon.                                    │
│                                                    │
│ ── Shipment ────────────────────────────────────  │
│ SHP1015 · Jaipur · Reefer · Priority CRITICAL     │
│                                                    │
│ ── Thread (read-only until takeover) ───────────  │
│ Driver   Still waiting on a dock, what's           │
│          happening?                    09:41       │
│                                                    │
│ [ Take over thread ]                    [ Cancel ] │
└────────────────────────────────────────────────┘
```

- Stepper is the full variant (owner + cause visible), per `components.md` §16.
- Thread history is visible and scrollable but **not composable** — the composer is disabled with a label
  explaining why, until *Take over thread* is pressed (U94). This lets a coordinator read full context
  before deciding whether this escalation needs a human in the conversation at all.
- **Escalate**, **Reassign**, **Cancel** live in an overflow menu once acknowledged — not primary buttons,
  to keep Acknowledge/Take-over as the two decisions this pane foregrounds.

## 3b · Detail + thread pane — under takeover

```
┌────────────────────────────────────────────────┐
│ ESC-104 · NO_FEASIBLE_SLOT          [Hand back] │
│                                                  │
│ ●───●───●───○              You (Anshul G.)       │
│ OPEN  ACK  IN-PROG  RESOLVED    ⏱ 4:12 to breach │
│                                                  │
│ ── Thread ──────────────────────────────────────  │
│ Driver      Still waiting on a dock, what's       │
│             happening?                  09:41      │
│                                                    │
│ ─────────── ⬤ Anshul G. (you) joined ───────────  │  ← U47's takeover divider
│                                                    │
│ [ composer: free text                     ] [Send]│
│                                                    │
│ [ Resolve ]  [ Cancel ]                            │
└────────────────────────────────────────────────┘
```

- The takeover divider is driver-visible in the same conversation the driver is reading — not a
  console-only artefact (§7.4: "the driver is told a human has joined").
- **Resolve** and **Cancel** are two different terminal states with two different driver-facing
  consequences — see `flows-and-states.md` Flow 6.
- Composer follows `components.md` (foundations) form-control rules: 24-hour time if a time is entered,
  `tabular-nums` for any figure.

---

## 4 · Co-pilot pane

**Inactive** (no takeover on the focused escalation):
```
┌─────────────────────────┐
│ CO-PILOT                │
│                          │
│   Available once you     │
│   take over a thread.    │
│                          │
│   Summarise, fetch       │
│   context, and draft     │
│   replies for your       │
│   approval.               │
└─────────────────────────┘
```

**Active** (takeover in progress, U57):
```
┌─────────────────────────┐
│ CO-PILOT                │
│                          │
│ [ Summarise thread ]     │
│ [ Fetch context ]        │
│                          │
│ ── Draft reply ─────────  │
│ [ Draft a reply ]        │
│                          │
│ (after drafting)          │
│ "Your reefer's slot at    │
│  D5 reopens after 22:00.  │
│  I can offer you 22:15."  │
│                          │
│ [ Discard ] [ Approve → ] │
└─────────────────────────┘
```

- This is `components.md`'s (foundations) §18 **Inactive** state, not Disabled — the pane stays
  keyboard-reachable and explains itself, exactly the rule written for "a control a coordinator needs to
  understand why is unavailable right now."
- **Approve** moves the draft into the thread's composer (3b, above); it does not send. See
  `flows-and-states.md` Flow 3 for the full gate sequence (U90).
- Summarise/fetch-context results render inline in this pane, non-editable — they are context, not a
  message. Only a drafted reply ever crosses into the composer.

---

## 5 · Capacity incident — expanded (U65 / U93)

```
┌──────────────────────────────────────────────────┐
│ ▼ 🔌 Capacity incident · DOCK-JAI-D3 · 09:15–13:00 │
│                                                    │
│  SHP1005  CRITICAL  Jaipur  read-only              │
│  SHP1009  HIGH      Jaipur  read-only              │
│  SHP1013  NORMAL    Jaipur  read-only              │
│  SHP1014  CRITICAL  Jaipur  read-only              │
│                                                    │
│  [ Request sequencer proposal ]                    │
└──────────────────────────────────────────────────┘

  (after requesting)
┌──────────────────────────────────────────────────┐
│ ▼ 🔌 Capacity incident · DOCK-JAI-D3 · 09:15–13:00 │
│                                                    │
│  Proposal requested · routed to Planner queue      │
│  4 shipments awaiting a planner's review           │
│                                                    │
│  [ View in planner queue ↗ ]  (if scoped there)    │
└──────────────────────────────────────────────────┘
```

- Individual shipment rows are read-only inside the incident (`components.md` §17's rule) — no
  confirm/reject affordance appears here even though this pane can render a queue-row-shaped item.
- **"Request sequencer proposal" is this surface's only action on an incident** (U93) — applying the
  proposal happens in `03-planner-dock-board/`, which this file does not specify further. The state after
  requesting names the handoff explicitly rather than leaving the coordinator wondering what happens next.

---

## 6 · Empty / caught-up state (U74)

```
┌───────────────────────────┐
│                            │
│      [ check-circle ]      │
│                            │
│   No open escalations.     │
│   New ones appear here     │
│   automatically.           │
│                            │
└───────────────────────────┘
```

This is "nothing right now," not "nothing yet" (U74) — an ops console with genuinely zero history (a
brand-new facility) would instead read "No escalations recorded for this facility yet," since an empty
queue on day one and a fully caught-up queue on a busy day are different facts a coordinator needs told
apart.

---

## Checklist coverage (U34)

Checklist Design's *Data table* (Web app) items applied: sticky header, fixed column behaviour, explicit
empty/loading/error, keyboard row navigation, bulk-action affordance placement — all inherited from
`components.md` §6/§19 rather than re-derived. Items deliberately **not** applied: pagination (the queue is
small enough — 15–35 items per §7.3's load arithmetic — that ops works it live, not paged) and column
customisation (a fixed 7-ish-field row is a deliberate constraint here too, inherited from the planner
console's discipline even though this surface's field count is smaller).

Checklist Design's *Chat* (Web app) items applied: composer disabled/enabled states, sender attribution,
system-event dividers — all inherited from `01-driver-chat/` and `ai-chat-primitives.md` rather than
re-derived, since this is the same rendering substrate scoped to a different sender set (driver / assistant
/ **operations**, not driver / assistant alone).
