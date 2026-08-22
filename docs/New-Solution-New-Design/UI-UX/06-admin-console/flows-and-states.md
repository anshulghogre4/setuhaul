# Admin console — flows and states

## Flow 1 · Invite a user (role + scope, one flow)

1. Users tab → Invite user → form opens (`components.md` §1).
2. Admin enters email, selects role → **scope field changes shape to match the role** (facility multi-
   select for ops/planner/gate, single carrier select for carrier-manager, no scope field for admin roles).
3. Submit → `invite_user(email, role, scope)`.
4. **`INVITED`** → row appears in the list with a pending-invitation badge; email sent (outside this
   surface's scope — the outbox/notification module owns delivery, per §6's module list).
5. **Email already has an account** → named error, form stays open with the email field flagged.

## Flow 2 · Edit a user's role or scope

1. Overflow menu → Edit → same form as Flow 1, pre-filled.
2. `update_user(user_id, role?, scope?)` → **`UPDATED`**, row reflects the change immediately.
3. **Narrowing a user's scope while they have an active session** is not specially handled here — the next
   request under their new (narrower) scope is enforced server-side per M15's own "derived from
   authenticated identity, enforced in the repository layer" architecture; this UI does not need to force a
   session termination, since the enforcement doesn't depend on the session being ended.

## Flow 3 · Deactivate / Reactivate a user

Overflow menu action, immediate, no confirmation modal (Moderate tier, `components.md` §19) — the row's
status updates in place. Reactivating restores exactly the role and scope the user had, unchanged.

## Flow 4 · Remove a user (High tier)

1. Overflow menu → Remove → typed-confirmation dialog (`components.md` §19): admin types the user's email.
2. `remove_user(user_id, Idempotency-Key)` → **`REMOVED`** — row disappears from the active list; the
   removal itself is now an audit-log entry (Audit tab, Flow 9).
3. **Not offered on the currently-signed-in admin's own account** — a self-removal path is a footgun with
   no legitimate use case this console needs to support; the Remove action is simply absent (Hidden, per
   `components.md` §18, not Disabled — matching the same "scope-denied is Hidden" pattern used for every
   other structurally-impossible action across the product).

## Flow 5 · Create or edit a facility rule

0. Facility Rules tab loads via `list_facility_rules(facility_id?)` — every rule's `rule_type`, value, and
   effective window, filterable by facility.
1. Add rule (or edit an existing row) → editor opens (`components.md` §2).
2. Admin selects facility, then `rule_type` → **value fields render per the selected type**.
3. Submit → `create_facility_rule` / `update_facility_rule`.
4. **`CREATED`/`UPDATED`** → takes effect immediately (no simulate-before-publish here — `screens.md` §3's
   stated asymmetry with Policy).
5. **Editing a rule with active dependent appointments** → High-tier confirmation names what's affected
   (`components.md` §2) before the write commits.

## Flow 6 · Edit and simulate policy weights (U27, extended)

```
Policy tab (read-only current version)
        │
   edit weight fields
        │
[ Simulate against last 30 days ]
        │
   simulate_policy_weights(weights, window='30d')  ← read-only, no write
        │
   Result: "N of M decisions would flip" + expandable cases
        │
   ┌────┴────┐
   │         │
Discard   Publish as vN+1
   │         │
 editor    publish_policy_version(weights, Idempotency-Key)
 resets         │
          PUBLISHED — new immutable version, header updates
```

- **Changing a field after a simulation has run marks the result stale** — the Publish action disables
  until Simulate is re-run against the current field values (`components.md` §5).
- **`SNAPSHOT_CONFLICT`-style outcome**: if another admin publishes a version between this admin's
  simulation and their own Publish attempt, the tool refuses — see `edge-cases.md` #3 for the exact
  handling, which mirrors the same "someone else acted first" pattern already established for
  `confirm_request`/`acknowledge_escalation` elsewhere in the product.

## Flow 7 · Enable the fairness term (Danger-zone gate)

1. Fairness box (`components.md` §4) → Enable fairness term → typed confirmation (distinct copy from the
   generic High-tier pattern, naming the actual business decision being made, not a generic "are you sure").
2. On confirming, `w_fairness` becomes an editable field in the ordinary weight editor (§3) rather than
   immediately publishing anything — enabling the *term* and *publishing a policy that uses a non-zero
   value* remain two separate steps, both still gated by Flow 6's simulate-before-publish discipline.
3. Disabling it (setting back to 0) is the ordinary weight-field path, not a second Danger-zone gate — the
   friction is specifically on *turning it on*, since that's the state change the spec singles out as a
   business-risk decision; returning to the safe default doesn't need the same ceremony.

## Flow 8 · Browse and filter the audit log

1. Audit tab loads with the default filter (last 7 days, all actors, all event types), recent-first.
2. Adjusting any filter re-queries `get_audit_log` with the new parameters — no client-side filtering of an
   already-fetched page, since the log can be arbitrarily large and this console has no reason to load more
   than the current filtered view needs.
3. **Export** → `export_audit_log` with the exact current filter set — CSV download.

## Flow 9 · Every write on this console becomes its own audit entry

Not a user-facing flow, but stated because it's a cross-cutting property every prior flow references: every
`invite_user`, `update_user`, `deactivate_user`/`reactivate_user`, `remove_user`,
`create_facility_rule`/`update_facility_rule`, and `publish_policy_version` call is itself logged through
the same M14 mechanism every other tool call in the product uses. This console does not have a separate,
weaker audit path for its own actions — the Audit tab (§8) is capable of showing this console's own history
back to an admin because nothing about admin actions is exempted from the general audit pipeline.
