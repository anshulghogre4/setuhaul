# Admin console — screens

> Surface: desktop, `comfortable` density (`spacing-and-layout.md`'s table lists "Carrier, admin, driver
> chat" together). Light theme default, dark at parity (U69). Foundations: `../00-foundations/`.
>
> Structure derived from three matching Checklist Design checklists (Web app) — *User Management*, *Admin
> Panel*, *Audit Log* — read directly before drafting, per the standing rule. Several Admin Panel items
> explicitly don't apply and are stated as excluded, not silently dropped: *Organisation settings*
> (name/logo/SSO/domains — this isn't a multi-tenant SaaS product managing its own account branding) and
> *Billing and plan management* (SetuHaul has no subscription/seat model for its own operators). See
> *Checklist coverage* at the end.

## The surface in one line

Four tabs — **Users · Facility Rules · Policy · Audit** — covering the four genuinely distinct areas
`SOLUTION_DESIGN.md` §2's persona table scopes to this role. §7.5.7 (added this checkpoint — the fourth
missing tool catalog found this project) backs every action. This is the one surface whose own writes are
the primary subject of the audit trail it also displays.

---

## Screen map

```
Sign in ──▶ Console (four tabs, no default preference stated — first tab, Users, opens by default)
              │
              ├── Users              ──▶ Invite/edit user (role + scope, one flow, U-locked this checkpoint)
              ├── Facility Rules     ──▶ Create/edit rule (typed registry form)
              ├── Policy             ──▶ Edit weights → Simulate → Publish (U27)
              └── Audit              ──▶ (no drill-down beyond the log itself — see §4)
```

---

## 1 · Console shell

```
┌──┬──────────────────────────────────────────────────────────────────────────────────┐
│▌ │ Admin          [ Users ] Facility Rules  Policy  Audit         🔔  ?  ⚙︎ AB       │  56px top bar
├──┼───────────────────────────────────────────────────────────────────────────────────┤
│▤ │  (active tab content)                                                             │
│👤│                                                                                     │
└──┴──────────────────────────────────────────────────────────────────────────────────┘
```

| Element | Rule |
|---|---|
| Icon rail | 56px, minimal two-destination model (this console + Profile), same as ops/planner/gate — no facility switcher, since admin actions span facilities by nature (a user's scope, a rule's facility, are set per-action, not by a global view filter) |
| Tabs | Four, no badge/count on any — this surface has no "pending work" framing the way ops/planner's queues do; every tab is a management area, not a queue to clear |

---

## 2 · Users tab

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ [ Filter: role ▾ ]  [ Filter: facility ▾ ]        🔍 Search        [ Invite user ] │
│ ┌────────┬──────────────┬──────────┬────────────────────┬────────┬──────────────┐ │
│ │Name    │Email         │Role      │Scope               │Status  │              │ │
│ ├────────┼──────────────┼──────────┼────────────────────┼────────┼──────────────┤ │
│ │Neha B. │neha@...      │Ops       │Jaipur, Gurugram     │Active  │      ⋯       │ │
│ │Ramesh K│ramesh@...    │Gate/Yard │Jaipur               │Active  │      ⋯       │ │
│ │Priya S.│priya@...     │Gate/Yard │Jaipur               │Inactive│      ⋯       │ │
│ │—       │amit.d@...    │Ops       │Gurugram             │◔ Invited│ Resend │Revoke│
│ └────────┴──────────────┴──────────┴────────────────────┴────────┴──────────────┘ │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### Invite / edit user — one flow (locked this checkpoint)

```
┌──────────────────────────────────────┐
│ Invite user                           │
│                                       │
│ Email        [                     ]  │
│ Role         [ Ops coordinator ▾ ]    │
│ Scope        [ Jaipur ▾ ] [ + add ]   │  ← scope options change shape per role
│                                       │
│         [ Cancel ]   [ Send invite ] │
└──────────────────────────────────────┘
```

### Rules
- **Role and scope are set in the same form, one submission** (`invite_user`, §7.5.7) — never a two-step
  "create the account, assign scope later" sequence. This closes exactly the gap M15's "foundational
  architecture, not an auth requirement" framing exists to prevent: a user who exists with a role but no
  scope is a real security hole, however brief.
- **Scope's shape depends on the selected role** — a planner or gate/yard role scopes to one or more
  facilities; a carrier-manager role scopes to a single `carrier_id`; an ops coordinator can scope to
  multiple facilities (matching `02-ops-exception-console/`'s own "All facilities" default, U91). The form
  adapts its scope field rather than offering an irrelevant picker.
- **Deactivate vs. Remove are two different actions with two different levels of friction**
  (`components.md` §19's 3-tier model): Deactivate is Moderate — immediate, reversible via Reactivate, no
  typed confirmation. **Remove is High-tier** — typed confirmation (the admin types the user's name or
  email before it commits), since it's the one genuinely hard-to-reverse action on this tab.
- **Pending invitations show their own status row** (User Management checklist item) — "Invited, awaiting
  acceptance" — with Resend/Revoke actions, distinct from an already-active user's row.

---

## 3 · Facility Rules tab

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ [ Filter: facility ▾ ]                                    [ + Add rule ]           │
│ ┌──────────────┬─────────────────┬────────────┬─────────────────────────────────┐ │
│ │Facility      │Rule type        │Value        │Effective                        │ │
│ ├──────────────┼─────────────────┼────────────┼─────────────────────────────────┤ │
│ │Jaipur        │EARLY_LIMIT      │60 min       │Always                            │ │
│ │Jaipur        │DOCK_PIN         │Reefer → D5  │Always                            │ │
│ │Jaipur        │NEW_START_CUTOFF │21:00        │Weekdays only, 18:00–23:59         │ │
│ └──────────────┴─────────────────┴────────────┴─────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### Rules
- **`rule_type` is a dropdown from the registry enum, never free text** (§0.9 issue 10's resolution,
  §7.5.7) — this is the concrete UI consequence of the spec's own decision to stop string-matching rule
  text. Each `rule_type` shows only its own relevant value fields (a `DOCK_PIN` rule asks for a dock and a
  cargo type; a `NEW_START_CUTOFF` rule asks for a time; an `EARLY_LIMIT` rule asks for a minute count).
- **`effective_from`/`effective_to` genuinely support intraday effectivity** — a rule can be scoped to
  specific hours on specific days ("Weekdays only, 18:00–23:59"), not just a bare date range, closing the
  exact gap the spec named as unimplementable in the shipped schema.
- **No simulate-before-publish here** — unlike Policy (§4), a facility rule change takes effect
  immediately on save. This asymmetry is deliberate: policy weights affect *every* ranking decision system-
  wide and are expensive to get wrong at scale (U27's whole reason for existing); a single facility rule
  (e.g. correcting a dock-pin typo) is narrower in blast radius and doesn't carry the same simulate-first
  justification. Genuinely destructive edits (removing a rule that active appointments already depend on)
  still get the High-tier typed-confirmation treatment, same as user removal.

---

## 4 · Policy tab

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  Current policy: v3 · published 2026-08-11 · Anshul G.                             │
│                                                                                      │
│  Priority weights        CRITICAL 4000  HIGH 3000  NORMAL 2000  LOW 1000            │
│  Lateness (w_lateness)   [ 4  ] /min, cap 720                                       │
│  Wait (w_wait)           [ -6 ] /min                                                │
│  Slack (w_slack)         [ 1  ] /min, cap 120                                       │
│  Dock mismatch (P_dock)  [ -25 ]                                                    │
│  Churn (P_churn)         [ 30 ] weighted-min-equivalent per moved promise           │
│                                                                                      │
│  ┌─ Fairness term (w_fairness) ───────────────────────────────────────────────┐    │
│  │ ⚠ Currently disabled (0). Enabling this is a business-risk decision, not    │    │
│  │   routine tuning — see the carrier-concentration canary on this tab.        │    │
│  │   [ Enable fairness term ] (separated, typed confirmation to proceed)       │    │
│  └───────────────────────────────────────────────────────────────────────────┘    │
│                                                                                      │
│                                          [ Simulate against last 30 days ]          │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### Simulation result (U27, extended per this checkpoint's lock)

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│  Simulation: proposed weights vs. current policy v3                                 │
│                                                                                      │
│  12 of 340 decisions in the last 30 days would flip                                 │
│                                                                                      │
│  ▶ SHP1014 vs SHP1009 — under these weights, SHP1014 loses to SHP1009               │
│  ▶ SHP1002 vs SHP1021 — under these weights, SHP1002 wins (was: loses)              │
│  ... 10 more                                                                        │
│                                                                                      │
│         [ Discard ]              [ Publish as v4 ]                                  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### Rules
- **Simulation shows aggregate impact first, examples second** (locked this checkpoint) — "12 of 340 would
  flip" is the headline; individual before/after cases (U27's own original example) are expandable detail
  underneath. An admin publishing a weight change needs to know the *scale* of what they're about to
  change, not just that a plausible single case exists.
- **`simulate_policy_weights` is read-only** (§7.5.7) — running a simulation never touches
  `policy_versions`; only **Publish** does, and it creates a new version rather than mutating the current
  one (D7). The current policy is always visible above the editor so an admin can see what they're changing
  *from*.
- **The fairness term is visually separated with its own warning box and a typed-confirmation gate**
  (locked this checkpoint, matching the Admin Panel checklist's Danger Zone pattern and
  `components.md` §19's High tier) — every other weight field is routine tuning; this one is a stated
  business-risk decision the spec itself singles out.
- **Publish requires the simulation to have been run against the current field values** — changing a
  weight after simulating invalidates the simulation result (shown stale, re-run required) rather than
  letting a published version diverge from what was actually previewed.

---

## 5 · Audit tab

```
┌───────────────────────────────────────────────────────────────────────────────────┐
│ [ Date range: last 7 days ▾ ]  [ Actor ▾ ]  [ Event type ▾ ]  🔍       [ Export ]  │
│ ┌──────────────┬──────────────┬─────────────────┬──────────────────────────────┐ │
│ │Time          │Actor         │Event             │Resource                      │ │
│ ├──────────────┼──────────────┼─────────────────┼──────────────────────────────┤ │
│ │14:02 today   │Anshul G.     │Policy published  │policy_versions v4             │ │
│ │13:40 today   │Neha B.       │User removed      │priya@... (Gate/Yard, Jaipur)  │ │
│ │11:15 today   │(system)      │Rule updated      │Jaipur · NEW_START_CUTOFF      │ │
│ └──────────────┴──────────────┴─────────────────┴──────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────────────┘
```

### Rules
- **Recent-first, always** (Audit Log checklist's own stated default rationale) — an admin investigating
  something starts at "what just happened" and works backwards.
- **Actor identification carries both name and a stable id** (checklist item) — a display name can change;
  the logged reference doesn't, so a renamed user's historical actions stay attributable.
- **System-generated events are attributed to `(system)`, never a blank actor field** — the D9 sweeper
  expiring a hold, for instance, is itself an auditable event with no human actor, and must read that way
  rather than as a mysterious gap in the log.
- **Export respects the current filter set** — a CSV export of "last 7 days, actor: Neha B." exports
  exactly that, never a silent full-table dump ignoring what the admin was actually looking at (§7.5.7's
  own stated rule for `export_audit_log`).
- **No drill-down beyond the log row itself** — clicking "policy_versions v4" does not open a separate
  policy-detail view; the Policy tab already is that view, and duplicating it here would be two places to
  maintain one fact.

---

## Checklist coverage

**User Management**: user list ✓ · invite ✓ · roles and permissions ✓ · pending invitation status ✓ ·
search/filter ✓ · remove/deactivate distinction ✓. **Admin Panel**: role-based access ✓ (inherent — this
console doesn't render at all outside the admin role, per `auth-and-scoping.md`) · user management ✓ ·
**organisation settings and billing/plan management explicitly excluded** — not applicable to SetuHaul's
operator-facing (not customer-facing SaaS) product · usage overview → folds into Audit's own filtering
rather than a separate metrics view, since this console has no analytics job beyond what §13.1 already
assigns elsewhere (planner/ops for operational KPIs, the deferred regional-ops persona for strategic ones)
· audit log ✓ (its own tab) · danger zone ✓ (Remove user, the fairness toggle, destructive rule edits).
**Audit Log**: event list ✓ · actor identification ✓ · event type ✓ · affected resource ✓ · date range
filter ✓ · search/filter ✓ · export ✓ — full coverage, no gaps found on this checklist.
