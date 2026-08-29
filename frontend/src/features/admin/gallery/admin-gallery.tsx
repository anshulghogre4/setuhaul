import { useState, type ReactNode } from 'react'

import { ACTOR_NAMES, AUDIT_FIXTURE, RULES_FIXTURE, USERS_FIXTURE } from './fixtures'
import { AuditTable } from '../components/audit-table'
import { InviteUserDialog } from '../components/invite-user-dialog'
import { PolicyTab } from '../components/policy-tab'
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

  const facilities = [
    { id: 'FAC-JAI-01', name: 'Jaipur' },
    { id: 'FAC-GGN-01', name: 'Gurugram' },
  ]

  return (
    <div className="min-h-dvh bg-background p-6 text-foreground" data-density="comfortable">
      <header className="mb-8">
        <p className="text-label text-primary uppercase">SetuHaul · admin console (E5.6)</p>
        <h1 className="mt-2 text-display text-balance">
          4 screens ship clean, 3 ship reduced, 5 are honestly stubbed
        </h1>
        <p className="mt-2 max-w-[80ch] text-body text-muted-foreground">
          Screens 1, 4, 11 and 12 build clean. Screens 2, 3 and 5 ship in reduced form (issues #72,
          #73, #70). Screens 6, 7, 8, 9 and 10 render stubs — the Policy tab is a stronger block
          than the readiness spec's own table, because no endpoint reads the active policy version
          or the live score weights.
        </p>
      </header>

      <div className="flex flex-col gap-10">
        <Plate n="2.1" title="Users tab — list, Active and Inactive rows, overflow menu">
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
              options={facilities.map((f) => ({ value: f.id, label: f.name }))}
            />
            <SearchField label="Search users" value="" onChange={() => {}} />
            <ToolbarSpacer />
            <Button variant="constructive">Invite user</Button>
          </Toolbar>
          <UsersTable
            users={USERS_FIXTURE}
            /* USR-001 is "self" here so the Hidden-Remove rule (Flow 4.3) is visible on row 1. */
            currentUserId="USR-001"
            onEdit={() => {}}
            onToggleActive={() => {}}
            onRemove={() => {}}
          />
          <p className="mt-3 text-supporting text-muted-foreground">
            Row 4 has no name (em dash, “not yet known”) and a null <code>last_login_ts</code> — it
            still renders Active, not “Invited”, because the backend has no pending state (#73).
            Row 1’s overflow menu has no Remove item: it is the signed-in admin’s own account.
          </p>
        </Plate>

        <Plate n="3" title="Invite / edit user modal — scope shape follows role">
          <div className="flex flex-wrap gap-3">
            <Button variant="neutral" onClick={() => setInvite(true)}>
              Open invite
            </Button>
            <Button variant="neutral" onClick={() => setEdit(true)}>
              Open edit (pre-filled)
            </Button>
          </div>
          <p className="mt-3 text-supporting text-muted-foreground">
            Select each role in turn: facility roles get a single-facility select plus the #72
            note, Carrier manager and Driver render Inactive with the reason, and Administrator
            renders no scope field at all.
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
          <RulesTable rules={RULES_FIXTURE} />
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

        <Plate n="8 / 9 / 10" title="Policy tab — weight editor, Danger Zone, simulation">
          <PolicyTab />
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
          <WriteFailedBanner detail="SetuHaul server is temporarily busy." onRetry={() => {}} />
          <RulesTable rules={RULES_FIXTURE.slice(0, 2)} />
        </Plate>
      </div>

      <InviteUserDialog
        mode="invite"
        user={null}
        open={invite}
        onOpenChange={setInvite}
        facilities={facilities}
        onSubmit={() => setInvite(false)}
      />
      <InviteUserDialog
        mode="edit"
        user={USERS_FIXTURE[0]}
        open={edit}
        onOpenChange={setEdit}
        facilities={facilities}
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
