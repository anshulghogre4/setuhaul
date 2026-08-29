import { useCallback, useEffect, useMemo, useState } from 'react'

import { InviteUserDialog } from './invite-user-dialog'
import {
  LoadFailed,
  NoMatches,
  NothingYet,
  TableCard,
  TableSkeleton,
  WriteFailedBanner,
} from './primitives'
import { UsersTable } from './users-table'
import { RemoveUserDialog } from './remove-user-dialog'
import { FilterSelect, SearchField, Toolbar, ToolbarSpacer } from './toolbar'
import {
  deactivateUser,
  inviteUser,
  listUsers,
  reactivateUser,
  removeUser,
  updateUser,
} from '../lib/api'
import { facilityDisplayName } from '../lib/facility-names'
import { ROLE_OPTIONS, roleDisplayName } from '../lib/roles'
import { isActiveUser, type AdminUser } from '../lib/types'
import { formatUserFriendlyError } from '@/core/http/api'
import { Button } from '@/shared/ui/button'

type LoadState = 'loading' | 'ready' | 'failed'

/**
 * Screen 2 — Users tab. **🟡, built in reduced form** (`implementation-spec.md` §3).
 *
 * Real and unconditional: the list itself, the role and facility filters (both genuinely
 * server-side query parameters on `list_users`), Active/Inactive rows, the overflow menu, and all
 * four write actions (invite, edit, deactivate/reactivate, remove).
 *
 * Two reductions, both flagged in code where they bite:
 *
 *  - **Scope renders at most one facility** (A-G4 / issue #72). `list_users` reads only
 *    `users.facility_id`, never `user_scopes`, so `screens.md`'s own example row
 *    ("Neha B. · Ops · Jaipur, Gurugram") is not producible. Behind
 *    `adminMultiFacilityScopeEnabled`.
 *  - **No pending-invitation row** (A-G5 / issue #73). `invite_user` sets `is_active = 1` at
 *    creation, so there is no "invited, not yet accepted" state to render and no
 *    resend/revoke tool to point the actions at. Behind `adminPendingInvitesEnabled`.
 *
 * **Search is client-side, and deliberately so** — unlike the Audit tab, where
 * `flows-and-states.md` Flow 8 forbids it. `list_users` has no search parameter at all, and it
 * returns the whole (LIMIT 200) page in one call, so filtering the three fields `mockup.html`
 * §12.B's own empty-state copy names — name, email, role — is honest at this product's scale.
 * The 200-row ceiling is the real limit; past that, a server-side search parameter is needed.
 */
export function UsersTab({ currentUserId }: { currentUserId: string }) {
  const [state, setState] = useState<LoadState>('loading')
  const [users, setUsers] = useState<AdminUser[]>([])
  /** See `load` below — the facility filter's options must not be derived from the rows the
   *  facility filter already narrowed. Also the only source of facility ids the invite form has,
   *  since no facilities-list endpoint exists (`lib/facility-names.ts`). */
  const [knownFacilityIds, setKnownFacilityIds] = useState<Set<string>>(() => new Set())
  const [roleFilter, setRoleFilter] = useState<string | null>(null)
  const [facilityFilter, setFacilityFilter] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const [inviteOpen, setInviteOpen] = useState(false)
  const [editing, setEditing] = useState<AdminUser | null>(null)
  const [removing, setRemoving] = useState<AdminUser | null>(null)
  const [busy, setBusy] = useState(false)
  const [writeError, setWriteError] = useState<string | null>(null)
  const [dialogError, setDialogError] = useState<string | null>(null)
  /** `accessibility.md`: a successful high-consequence commit is announced assertively, not left
   *  to a toast that can be missed. Lives here rather than in the dialog, which unmounts on
   *  success. */
  const [committed, setCommitted] = useState<string | null>(null)

  const load = useCallback(async () => {
    setState('loading')
    try {
      const result = await listUsers({ roleFilter, facilityFilter })
      setUsers(result.items)
      // Accumulate rather than derive-from-current-rows. Deriving the option list from `users`
      // is self-narrowing: once "Jaipur" is selected the response contains only Jaipur users, so
      // every other facility disappears from the dropdown that just filtered them out and the
      // admin cannot switch directly to another one. The first load is unfiltered, so this set
      // starts complete; later loads can only add to it.
      setKnownFacilityIds((known) => {
        const next = new Set(known)
        for (const user of result.items) if (user.facility_id) next.add(user.facility_id)
        return next.size === known.size ? known : next
      })
      setState('ready')
    } catch {
      setState('failed')
    }
  }, [roleFilter, facilityFilter])

  useEffect(() => {
    void load()
  }, [load])

  const facilityOptions = useMemo(
    () =>
      [...knownFacilityIds]
        .map((id) => ({ value: id, label: facilityDisplayName(id) }))
        .sort((a, b) => a.label.localeCompare(b.label)),
    [knownFacilityIds],
  )

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    if (needle === '') return users
    return users.filter(
      (user) =>
        (user.full_name ?? '').toLowerCase().includes(needle) ||
        user.email.toLowerCase().includes(needle) ||
        roleDisplayName(user.role_name).toLowerCase().includes(needle),
    )
  }, [users, search])

  async function runWrite(action: () => Promise<unknown>, announce: string) {
    setBusy(true)
    setWriteError(null)
    setDialogError(null)
    try {
      await action()
      setCommitted(announce)
      setInviteOpen(false)
      setEditing(null)
      setRemoving(null)
      await load()
    } catch (error) {
      const message = formatUserFriendlyError(error)
      // A dialog that is open keeps its own inline error and stays open with its field values
      // intact (`components.md` §1: "form stays open with the email field flagged"); a
      // menu-driven write with no dialog has nowhere inline to put it, so it surfaces as the
      // region banner (Screen 12.F) above the still-valid table instead.
      const dialogOpen = inviteOpen || editing !== null || removing !== null
      if (dialogOpen) setDialogError(message)
      else setWriteError(message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col">
      <span role="alert" className="sr-only">
        {committed ?? ''}
      </span>

      {writeError ? <WriteFailedBanner detail={writeError} onRetry={() => void load()} /> : null}

      <Toolbar>
        <FilterSelect
          label="Role"
          value={roleFilter}
          onChange={setRoleFilter}
          allLabel="All roles"
          options={ROLE_OPTIONS.map((r) => ({ value: r.value, label: r.label }))}
        />
        <FilterSelect
          label="Facility"
          value={facilityFilter}
          onChange={setFacilityFilter}
          allLabel="All facilities"
          options={facilityOptions}
        />
        <SearchField label="Search users" value={search} onChange={setSearch} />
        <ToolbarSpacer />
        <Button
          variant="constructive"
          onClick={() => {
            setDialogError(null)
            setInviteOpen(true)
          }}
        >
          Invite user
        </Button>
      </Toolbar>

      {state === 'loading' ? (
        <TableCard>
          <TableSkeleton columns={5} />
        </TableCard>
      ) : state === 'failed' ? (
        <LoadFailed what="the user list" onRetry={() => void load()} />
      ) : users.length === 0 ? (
        <NothingYet
          title="No users have been invited yet."
          body="Once you invite someone, they will show up here."
          action={
            <Button variant="constructive" onClick={() => setInviteOpen(true)}>
              Invite user
            </Button>
          }
        />
      ) : visible.length === 0 ? (
        <NoMatches
          title={`No user matches “${search.trim()}”.`}
          body="Try a different name, email, or role."
          onClear={() => setSearch('')}
          clearLabel="Clear search"
        />
      ) : (
        <UsersTable
          users={visible}
          currentUserId={currentUserId}
          onEdit={(user) => {
            setDialogError(null)
            setEditing(user)
          }}
          onToggleActive={(user) =>
            void runWrite(
              () =>
                isActiveUser(user) ? deactivateUser(user.user_id) : reactivateUser(user.user_id),
              isActiveUser(user)
                ? `${user.email} deactivated. Reactivate from the same menu to reverse it.`
                : `${user.email} reactivated.`,
            )
          }
          onRemove={(user) => {
            setDialogError(null)
            setRemoving(user)
          }}
        />
      )}

      <InviteUserDialog
        mode={editing ? 'edit' : 'invite'}
        user={editing}
        open={inviteOpen || editing !== null}
        onOpenChange={(open) => {
          if (open) return
          setInviteOpen(false)
          setEditing(null)
        }}
        facilities={facilityOptions.map((f) => ({ id: f.value, name: f.label }))}
        busy={busy}
        errorDetail={dialogError}
        onSubmit={(payload) => {
          if (editing) {
            void runWrite(
              () => updateUser(editing.user_id, { role: payload.role, scope: payload.scope }),
              `${editing.email} updated.`,
            )
          } else {
            void runWrite(() => inviteUser(payload), `Invitation sent to ${payload.email}.`)
          }
        }}
      />

      <RemoveUserDialog
        user={removing}
        open={removing !== null}
        onOpenChange={(open) => {
          if (!open) setRemoving(null)
        }}
        busy={busy}
        errorDetail={dialogError}
        onConfirm={(user) =>
          void runWrite(
            () => removeUser(user.user_id),
            `${user.email} removed. Their past actions stay attributable in the Audit tab.`,
          )
        }
      />
    </div>
  )
}
