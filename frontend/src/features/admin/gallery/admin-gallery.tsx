import { useState, type ReactNode } from 'react'

import {
  ACTOR_NAMES,
  AUDIT_FIXTURE,
  FACILITIES_FIXTURE,
  POLICY_ACTIVE_FIXTURE,
  POLICY_DIVERGED_FIXTURE,
  POLICY_DRAFTS_FIXTURE,
  POLICY_NEVER_PUBLISHED_FIXTURE,
  PUBLISH_CONFLICT_FIXTURE,
  PUBLISH_RESULT_FIXTURE,
  RULES_FIXTURE,
  SIMULATION_FIXTURE,
  SIMULATION_VACUOUS_FIXTURE,
  USERS_FIXTURE,
  USERS_NO_INVITES_FIXTURE,
} from './fixtures'
import { AuditTable } from '../components/audit-table'
import { InviteUserDialog } from '../components/invite-user-dialog'
import {
  PublishConflict,
  SimulationPublished,
  SimulationResult,
  SimulationRunning,
} from '../components/policy-simulation-panel'
import { PolicyVersionHeader } from '../components/policy-version-header'
import { PolicyWeightEditor } from '../components/policy-weight-editor'
import {
  InactiveNote,
  LoadFailed,
  NoMatches,
  NothingYet,
  NotYetAvailable,
  TableCard,
  TableSkeleton,
  WriteFailedBanner,
} from '../components/primitives'
import { RemoveUserDialog } from '../components/remove-user-dialog'
import { RulesTable } from '../components/rules-table'
import { FilterSelect, SearchField, Toolbar, ToolbarSpacer } from '../components/toolbar'
import { UsersTable } from '../components/users-table'
import { facilityNameFrom } from '../lib/facilities'
import { ROLE_OPTIONS } from '../lib/roles'
import { Button } from '@/shared/ui/button'

/**
 * Every admin-console screen `implementation-spec.md` §3 marks 🟢 or 🟡, rendered by the **built
 * components** against fixture data — route `/admin/_states`, not linked from the app. Same
 * purpose as `/ops/_states` and `/planner/_states`: "it type-checks" is not "it has been seen
 * rendering."
 *
 * The three 🔴 screens (6 rule editor, 7 dependent-appointment confirmation, 9 fairness Danger
 * Zone) render their honest stub, not a fake plate — a screen with nothing to call must not look
 * like it works.
 *
 * The two modal screens are click-to-open here rather than shown open, because only one Radix
 * dialog can be mounted at a time; the flat reference mockup can depict five simultaneously and a
 * live shell cannot. Same limitation E5.0's gallery recorded for popovers.
 */
export function AdminStatesGallery() {
  const [invite, setInvite] = useState(false)
  const [edit, setEdit] = useState(false)
  const [remove, setRemove] = useState(false)

  // The same shape `useFacilities()` hands the live tab, minus the fetch: `assignable` for the
  // dialog (open facilities only) and `nameOf` for the two tables.
  const assignable = FACILITIES_FIXTURE.filter((f) => f.active_flag === 1).map((f) => ({
    id: f.facility_id,
    name: f.facility_name,
  }))
  const facilityName = (id: string) => facilityNameFrom(FACILITIES_FIXTURE, id)

  return (
    <div className="min-h-dvh bg-background p-6 text-foreground" data-density="comfortable">
      <header className="mb-8">
        <p className="text-label text-primary uppercase">SetuHaul · admin console (E5.6)</p>
        <h1 className="mt-2 text-display text-balance">
          6 screens ship clean, 3 ship reduced, 3 are honestly stubbed
        </h1>
        <p className="mt-2 max-w-[80ch] text-body text-muted-foreground">
          Screens 1, 4, 11 and 12 build clean, joined 2026-08-31 by <strong>8 and 10</strong> — the
          Policy tab, unblocked by <code>GET /admin/policy/active</code> and by{' '}
          <code>publish_policy_version</code>&rsquo;s new <code>based_on_version_id</code> guard.
          Screens 2, 3 and 5 ship in reduced form (issues #72, #73, #70). Screens 6, 7 and 9 render
          stubs: 6 and 7 wait on <em>design</em> for three live rule types (their backend gaps are
          closed), 9 waits on #69&rsquo;s Danger-Zone flow.
        </p>
      </header>

      <div className="flex flex-col gap-10">
        <Plate n="2.1" title="Users tab — all four lifecycle states, including the pending-invite row">
          <Toolbar>
            <FilterSelect
              label="Role"
              value={null}
              onChange={() => {}}
              allLabel="All roles"
              options={ROLE_OPTIONS.map((r) => ({ value: r.value, label: r.label }))}
            />
            <FilterSelect
              label="Facility"
              value={null}
              onChange={() => {}}
              allLabel="All facilities"
              /* EVERY facility, closed ones included — the filter must be able to name a facility
                 users are still scoped to. The invite dialog below takes `assignable` instead. */
              options={FACILITIES_FIXTURE.map((f) => ({
                value: f.facility_id,
                label: f.facility_name,
              }))}
            />
            <SearchField label="Search users" value="" onChange={() => {}} />
            <ToolbarSpacer />
            <Button variant="constructive">Invite user</Button>
          </Toolbar>
          <UsersTable
            users={USERS_FIXTURE}
            /* USR-001 is "self" here so the Hidden-Remove rule (Flow 4.3) is visible on row 1. */
            currentUserId="USR-001"
            facilityName={facilityName}
            onEdit={() => {}}
            onToggleActive={() => {}}
            onRemove={() => {}}
            onResendInvite={() => {}}
            onRevokeInvite={() => {}}
          />
          <p className="mt-3 text-supporting text-muted-foreground">
            Row 1 is scoped to <strong>two</strong> facilities (<code>scoped_facility_ids</code>,
            #72) and its overflow menu has no Remove item — it is the signed-in admin’s own account.
            Row 4 is the pending invitation: no name (em dash, “not yet known”), the badge, and{' '}
            <strong>Resend / Revoke in place of the overflow menu</strong>. The badge is driven by{' '}
            <code>lifecycle_state === &lsquo;INVITED&rsquo;</code> and never by{' '}
            <code>last_login_ts</code> — row 2 has a login stamp and row 4 has none, and neither
            fact touches its badge.
          </p>
        </Plate>

        <Plate
          n="2.2"
          title="Users tab — what production actually renders today: zero invited users"
        >
          <UsersTable
            users={USERS_NO_INVITES_FIXTURE}
            currentUserId="USR-000"
            facilityName={facilityName}
            onEdit={() => {}}
            onToggleActive={() => {}}
            onRemove={() => {}}
            onResendInvite={() => {}}
            onRevokeInvite={() => {}}
          />
          <p className="mt-3 text-supporting text-muted-foreground">
            #73&rsquo;s migration is applied and <strong>deliberately unbackfilled</strong>, so every
            live row has <code>invited_at IS NULL</code> and derives as <code>ACTIVE</code>. This is
            the default state the flag flip actually produces: no badge anywhere, the overflow menu
            on every row. It is the correct rendering of “nobody has been invited yet”, not a failed
            read — which is why it gets its own plate rather than being assumed.
          </p>
        </Plate>

        <Plate n="3" title="Invite / edit user modal — scope shape follows role">
          <div className="flex flex-wrap gap-3">
            <Button variant="neutral" onClick={() => setInvite(true)}>
              Open invite
            </Button>
            <Button variant="neutral" onClick={() => setEdit(true)}>
              Open edit (pre-filled, two facilities)
            </Button>
          </div>
          <p className="mt-3 text-supporting text-muted-foreground">
            Select each role in turn: facility roles get the <strong>facility multi-select</strong>{' '}
            (#72, a native checkbox group rather than the artboard&rsquo;s chip row — reasoning in
            the component header), Carrier manager and Driver render Inactive with the reason, and
            Administrator renders no scope field at all. The options are the two{' '}
            <strong>open</strong> facilities; the closed Indore depot is offered by the filter above
            and withheld here, which is why <code>list_facilities</code> returns{' '}
            <code>active_flag</code> instead of filtering server-side. Edit opens with both of Neha
            B.&rsquo;s facilities already ticked.
          </p>
        </Plate>

        <Plate n="4" title="Remove user — typed confirmation (High tier)">
          <Button variant="destructive" onClick={() => setRemove(true)}>
            Open remove dialog
          </Button>
          <p className="mt-3 text-supporting text-muted-foreground">
            Focus lands on the field. The confirm button is <code>aria-disabled</code> and still
            focusable, with its reason announced; typing{' '}
            <code>priya.sharma@setuhaul.example</code> enables it. A mismatch is not an error state
            — no red border, no message.
          </p>
        </Plate>

        <Plate n="5" title="Facility Rules tab — live five-value registry">
          <RulesTable rules={RULES_FIXTURE} facilityName={facilityName} />
          <p className="mt-3 text-supporting text-muted-foreground">
            These are the five <code>rule_type</code> values the live <code>CHECK</code> constraint
            accepts, not the design docs’ four (#70). Row 4 shows a real absolute effective range;
            the others are “Always”.
          </p>
        </Plate>

        <Plate n="6 / 7" title="Rule editor and dependent-appointment impact — 🔴 stubs">
          <InactiveNote>
            Add rule is Inactive: the type-specific field mechanism is designed around four types
            the constraint rejects (#70), and the effective-window control needs engine support
            (#71).
          </InactiveNote>
          <div className="mt-4">
            <NotYetAvailable
              title="Dependent-appointment impact isn’t available."
              body="No query anywhere counts the appointments a rule edit would affect (issue #74). A guessed count is worse than none."
            />
          </div>
        </Plate>

        {/*
          Screens 8 and 10, built 2026-08-31. The PRESENTATIONAL components are rendered against
          fixtures rather than `<PolicyTab />` itself: the live tab fetches
          `GET /admin/policy/active` on mount and would render nothing but its load-failed state
          here, which is correct behaviour and a useless plate. That split is also the property
          worth showing — the tab cannot display a coefficient it has not been served.
        */}
        <Plate n="8.1" title="Policy tab — weight editor, engine and version in agreement">
          <PolicyVersionHeader policy={POLICY_ACTIVE_FIXTURE} publisherNames={ACTOR_NAMES} />
          <div className="mt-6">
            <PolicyWeightEditor
              live={POLICY_ACTIVE_FIXTURE.live_weights}
              priorityScores={POLICY_ACTIVE_FIXTURE.live_priority_scores}
              drafts={POLICY_DRAFTS_FIXTURE}
              invalidKeys={new Set()}
              onChange={() => {}}
              onSimulate={() => {}}
              simulating={false}
              windowLabel="the last 30 days"
            />
          </div>
          <p className="mt-3 text-supporting text-muted-foreground">
            Every number here — the four coefficients, both caps, the priority tiers,{' '}
            <code>w_fairness</code> — comes from the server. The Danger Zone now carries a real
            Enable action (#69 landed <code>w_fairness</code> as a live formula term);{' '}
            <code>P_churn</code> is still absent entirely, because the API refuses that key with a
            422 naming the sequencer (#49) as its reason.
          </p>
        </Plate>

        <Plate n="8.3, 9" title="Danger Zone unlocked — w_fairness as an ordinary weight row">
          {/* Flow 7 step 2: confirming makes `w_fairness` editable "in the ordinary weight editor
              (§3) rather than immediately publishing anything". So the unlocked state is not a
              special control — it is the same WeightRow every other coefficient uses, with the
              same label/unit/aria wiring, and the Enable button is GONE rather than disabled
              (there is nothing left to enable, and Flow 7 step 3 puts disabling back on the
              ordinary path). Press "Enable fairness term" in the plate above to see Screen 9's
              typed confirmation; it writes nothing anywhere. */}
          <PolicyWeightEditor
            live={POLICY_ACTIVE_FIXTURE.live_weights}
            priorityScores={POLICY_ACTIVE_FIXTURE.live_priority_scores}
            drafts={POLICY_DRAFTS_FIXTURE}
            invalidKeys={new Set()}
            onChange={() => {}}
            onSimulate={() => {}}
            simulating={false}
            windowLabel="the last 30 days"
            fairnessUnlocked
          />
        </Plate>

        <Plate
          n="8.2"
          title="Version header — the engine is NOT running the active version"
        >
          <PolicyVersionHeader policy={POLICY_DIVERGED_FIXTURE} publisherNames={ACTOR_NAMES} />
          <div className="mt-4 border-t border-border pt-4">
            <PolicyVersionHeader
              policy={POLICY_NEVER_PUBLISHED_FIXTURE}
              publisherNames={ACTOR_NAMES}
            />
          </div>
          <p className="mt-3 text-supporting text-muted-foreground">
            Top: <code>engine_matches_active_version: false</code> — the divergence is named key by
            key from the two dicts the server sent, because publishing writes a{' '}
            <code>policy_versions</code> row and deliberately does not rewrite{' '}
            <code>constraints.json</code>. Bottom: nothing published yet, the one case that
            legitimately publishes without a <code>based_on_version_id</code>.
          </p>
        </Plate>

        <Plate n="10.A" title="Simulation — running">
          <SimulationRunning />
          <p className="mt-3 text-supporting text-muted-foreground">
            Skeleton matched to the final layout, not a spinner. The status line changes to
            &ldquo;Still working&rdquo; at ten seconds.
          </p>
        </Plate>

        <Plate n="10.B / 10.C" title="Simulation — result, then the same result gone stale">
          <SimulationResult
            simulation={SIMULATION_FIXTURE}
            stale={false}
            publishing={false}
            onDiscard={() => {}}
            onPublish={() => {}}
          />
          <SimulationResult
            simulation={SIMULATION_FIXTURE}
            stale
            publishing={false}
            onDiscard={() => {}}
            onPublish={() => {}}
          />
          <p className="mt-3 text-supporting text-muted-foreground">
            A case is one shipment and two slots — what the tool actually returns — not the
            mockup&rsquo;s &ldquo;SHP1014 vs SHP1009&rdquo; head-to-head, which it does not compute.
            Stale: Publish is <code>aria-disabled</code> and still focusable, with the reason
            announced.
          </p>
        </Plate>

        <Plate n="10.B (vacuous)" title="Simulation — 0 of 0, which is not evidence">
          <SimulationResult
            simulation={SIMULATION_VACUOUS_FIXTURE}
            stale={false}
            publishing={false}
            onDiscard={() => {}}
            onPublish={() => {}}
          />
          <p className="mt-3 text-supporting text-muted-foreground">
            Publish is refused. A window that matched no appointments says nothing about the change,
            and letting it satisfy the simulate-before-publish gate would make that gate vacuous.
          </p>
        </Plate>

        <Plate n="10.D" title="Published — and the conflict the mockup had no copy for">
          <SimulationPublished result={PUBLISH_RESULT_FIXTURE} />
          <PublishConflict
            message={PUBLISH_CONFLICT_FIXTURE.message}
            detail={PUBLISH_CONFLICT_FIXTURE.detail}
            onDismiss={() => {}}
          />
          <p className="mt-3 text-supporting text-muted-foreground">
            The success banner does <strong>not</strong> say &ldquo;every decision from now on is
            scored against this version&rdquo; — that would be false, because publishing does not
            rewrite the file the engine reads. The conflict names the winning version id and its
            publisher, from the server&rsquo;s own two strings (<code>edge-cases.md</code> #3).
          </p>
        </Plate>

        <Plate n="9" title="Fairness Danger Zone — 🔴 still gated on #69">
          <InactiveNote>
            Screen 9&rsquo;s typed-confirmation flow is not built. The term itself is now real —{' '}
            <code>w_fairness</code> is a live <code>score_weights</code> key and the ranking formula
            multiplies it by a per-carrier concentration count — so the old objection (&ldquo;the
            gate would be confirming something fictional&rdquo;) no longer holds. It stays gated
            because a concurrent agent owns <code>adminFairnessTermEnabled</code> and the work
            behind it. The value round-trips unchanged; this console does not edit it.
          </InactiveNote>
        </Plate>

        <Plate n="11" title="Audit tab — filtered log, (system) actor, derived event labels">
          <Toolbar>
            <FilterSelect
              label="Date range"
              value="7"
              onChange={() => {}}
              allLabel="Last 7 days"
              options={[{ value: '7', label: 'Last 7 days' }]}
            />
            <FilterSelect
              label="Actor"
              value={null}
              onChange={() => {}}
              allLabel="All actors"
              options={Object.entries(ACTOR_NAMES).map(([value, label]) => ({ value, label }))}
            />
            <ToolbarSpacer />
            <Button variant="neutral">Export</Button>
          </Toolbar>
          <AuditTable entries={AUDIT_FIXTURE} actorNames={ACTOR_NAMES} />
          <p className="mt-3 text-supporting text-muted-foreground">
            Row 3 has an empty <code>user_id</code> and renders the literal “(system)”. Rows 2 and 4
            derive “User removed” / “User invited” from the <code>event</code> key in{' '}
            <code>new_value_json</code>; rows 1 and 3 derive from{' '}
            <code>action_type</code> + <code>entity_name</code>.
          </p>
        </Plate>

        <Plate n="12.A" title="Users list — nothing yet">
          <NothingYet
            title="No users have been invited yet."
            body="Once you invite someone, they will show up here."
            action={<Button variant="constructive">Invite user</Button>}
          />
        </Plate>

        <Plate n="12.B / 12.C" title="No results — search, then filter">
          <NoMatches
            title="No user matches “rj14”."
            body="Try a different name, email, or role."
            onClear={() => {}}
            clearLabel="Clear search"
          />
          <div className="mt-4 border-t border-border pt-4">
            <NoMatches
              title="No events match this filter."
              body="Widen the date range, or clear the actor and event-type filters."
              onClear={() => {}}
              clearLabel="Clear filters"
            />
            <div className="mt-3 flex justify-center">
              <Button
                variant="neutral"
                aria-disabled
                tabIndex={0}
                title="There is nothing to export with this filter"
                className="opacity-50"
              >
                Export
              </Button>
            </div>
          </div>
        </Plate>

        <Plate n="12.D" title="Table loading">
          <TableCard>
            <TableSkeleton columns={5} />
          </TableCard>
        </Plate>

        <Plate n="12.E" title="Load failed">
          <LoadFailed what="the user list" onRetry={() => {}} />
        </Plate>

        <Plate n="12.F" title="Write failed — the table beneath is still valid">
          <WriteFailedBanner
            detail="Too many invitation emails have gone out recently, so this one was not sent. Wait a minute, then press Resend again."
            onRetry={() => {}}
          />
          <RulesTable rules={RULES_FIXTURE.slice(0, 2)} facilityName={facilityName} />
          <p className="mt-3 text-supporting text-muted-foreground">
            The detail line is the copy <code>describeWriteFailure</code> renders for a{' '}
            <strong>429 <code>AUTH_EMAIL_RATE_LIMITED</code></strong> — the realistic failure of a
            Resend button, matched on the server&rsquo;s error <em>code</em> via{' '}
            <code>hasApiErrorCode</code>, never on a message string. The server&rsquo;s own sentence
            names Supabase Auth, which an admin cannot act on; this one names what they can do.
          </p>
        </Plate>
      </div>

      <InviteUserDialog
        mode="invite"
        user={null}
        open={invite}
        onOpenChange={setInvite}
        facilities={assignable}
        onSubmit={() => setInvite(false)}
      />
      <InviteUserDialog
        mode="edit"
        user={USERS_FIXTURE[0]}
        open={edit}
        onOpenChange={setEdit}
        facilities={assignable}
        onSubmit={() => setEdit(false)}
      />
      <RemoveUserDialog
        user={USERS_FIXTURE[2]}
        open={remove}
        onOpenChange={setRemove}
        onConfirm={() => setRemove(false)}
      />
    </div>
  )
}

function Plate({ n, title, children }: { n: string; title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-border bg-sunken p-4">
      <h2 className="mb-3 text-h3">
        <span className="font-data text-muted-foreground">{n}</span> — {title}
      </h2>
      {children}
    </section>
  )
}
