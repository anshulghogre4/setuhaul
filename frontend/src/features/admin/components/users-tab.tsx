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
  resendInvite,
  revokeInvite,
  updateUser,
} from '../lib/api'
import { useFacilities } from '../lib/facilities'
import { ROLE_OPTIONS, roleDisplayName } from '../lib/roles'
import { isActiveUser, type AdminUser } from '../lib/types'
import { formatUserFriendlyError, hasApiErrorCode } from '@/core/http/api'
import { Button } from '@/shared/ui/button'

type LoadState = 'loading' | 'ready' | 'failed'

/**
 * Write failures this tab has copy for, by the server's own error **code**.
 *
 * `hasApiErrorCode` and never a message match: the wiki rule is explicit, and the mechanism is what
 * makes it safe — a transport failure is not an `ApiError`, so it can never accidentally satisfy a
 * code test the way it could satisfy a substring test. Everything unnamed falls through to
 * `formatUserFriendlyError`, which is still the right answer for a 500 or a dropped connection.
 *
 * Three codes earn named copy because each names a *different next action*:
 *
 *  - **`AUTH_EMAIL_RATE_LIMITED` (429)** is the realistic failure of a Resend button — GoTrue's
 *    `over_email_send_rate_limit`, which an impatient admin pressing Resend twice will genuinely
 *    hit. The server's own sentence mentions Supabase Auth by name, which is an implementation
 *    detail the admin cannot act on; "wait a minute and press Resend again" is what they can.
 *  - **`NOT_PENDING_INVITE` (409)** means the row moved on between render and click — the person
 *    accepted, or someone else revoked. The action is to refresh, not to retry.
 *  - **`USER_REMOVED` (409)** means Reactivate was pressed on a removed account whose Supabase Auth
 *    identity is already deleted. Retrying can never work.
 */
function describeWriteFailure(error: unknown): string {
  if (hasApiErrorCode(error, 'AUTH_EMAIL_RATE_LIMITED')) {
    return 'Too many invitation emails have gone out recently, so this one was not sent. Wait a minute, then press Resend again.'
  }
  if (hasApiErrorCode(error, 'NOT_PENDING_INVITE')) {
    return 'This is no longer a pending invitation — the list has moved on since it was drawn. Refresh to see the current status.'
  }
  if (hasApiErrorCode(error, 'USER_REMOVED')) {
    return 'This user was removed. Removal is permanent and cannot be undone here.'
  }
  return formatUserFriendlyError(error)
}

/**
 * Screen 2 — Users tab. **🟢 as of 2026-08-31** (was 🟡, `implementation-spec.md` §3).
 *
 * Real and unconditional: the list itself, the role and facility filters (both genuinely
 * server-side query parameters on `list_users`), Active/Inactive rows, the overflow menu, and all
 * four write actions (invite, edit, deactivate/reactivate, remove).
 *
 * **Both of this tab's reductions closed on 2026-08-31**, each against a shipped backend rather
 * than an issue comment:
 *
 *  - **Multi-facility scope** (A-G4 / #72). `list_users` returns `scoped_facility_ids` per row and
 *    `invite_user`/`update_user` accept `scope: str | list[str]`. Read *and* write are servable, so
 *    `adminMultiFacilityScopeEnabled` is on and the flag was not split.
 *  - **The pending-invitation row** (A-G5 / #73). `list_users` returns a server-derived
 *    `lifecycle_state` and `resend_invite`/`revoke_invite` exist. The badge is gated on
 *    `lifecycle_state === 'INVITED'` and **never** on `last_login_ts`, which is written nowhere in
 *    the application and would have marked essentially every user.
 *
 * A third gap closed underneath both: `GET /admin/facilities` (A-G10 / #78) replaced the derived
 * option list, so a facility with no users and no rules is now pickable and can receive its first
 * user. The `knownFacilityIds` accumulator that used to paper over the derived list's
 * self-narrowing is **deleted, not kept alongside** — see `lib/facilities.ts`.
 *
 * **`include_removed` is not exposed, and that is a decision.** `list_users` supports it, but
 * `edge-cases.md` #8's rule is that a removed user "does not reappear in search", and every action
 * this tab offers is refused on a removed row anyway (`reactivate_user` answers `USER_REMOVED`,
 * `resend_invite`/`revoke_invite` answer `NOT_PENDING_INVITE`). A toggle would add a fifth control
 * whose only outcome is rows nothing can be done to. The audit trail is where a removal is
 * answerable, and the Audit tab already renders it. Reconsider if an admin ever needs to confirm a
 * specific removal without leaving this tab.
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
  const facilities = useFacilities()
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
      setState('ready')
    } catch {
      setState('failed')
    }
  }, [roleFilter, facilityFilter])

  useEffect(() => {
    void load()
  }, [load])

  /**
   * The filter offers **every** facility, closed ones included — a user scoped to a since-closed
   * facility must still be findable. The server already orders by `facility_name`, so no local
   * sort is applied; re-sorting client-side would silently pick a different collation.
   */
  const facilityOptions = useMemo(
    () => facilities.all.map((f) => ({ value: f.facility_id, label: f.facility_name })),
    [facilities.all],
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
      const message = describeWriteFailure(error)
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
          facilityName={facilities.nameOf}
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
          /*
            Both commit immediately — no dialog, so a failure lands in the region banner. Each
            announcement names the reversal path rather than promising an undo affordance that has
            no backing tool, the same treatment Deactivate already gets above.
          */
          onResendInvite={(user) =>
            void runWrite(
              () => resendInvite(user.user_id),
              `Invitation re-sent to ${user.email}. The previous link is replaced by the new one.`,
            )
          }
          onRevokeInvite={(user) =>
            void runWrite(
              () => revokeInvite(user.user_id),
              `Invitation for ${user.email} revoked. The link no longer works; invite the address again to restore access.`,
            )
          }
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
        /* A NEW assignment may only name an open facility, so the picker takes `assignable` while
           the filter above takes `all`. The dialog re-adds any already-held closed facility itself
           in edit mode, so an edit cannot silently drop a scope the user holds. */
        facilities={facilities.assignable.map((f) => ({ id: f.facility_id, name: f.facility_name }))}
        facilitiesUnavailable={facilities.state === 'failed'}
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
