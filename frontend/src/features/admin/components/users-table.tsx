import { Ellipsis } from 'lucide-react'

import { TableCard } from './primitives'
import { facilityDisplayName } from '../lib/facility-names'
import { adminPendingInvitesEnabled } from '../lib/flags'
import { roleDisplayName } from '../lib/roles'
import { isActiveUser, type AdminUser } from '../lib/types'
import { Button } from '@/shared/ui/button'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/shared/ui/dropdown-menu'

/**
 * The Users table, presentational only — it takes rows and callbacks, and never fetches.
 *
 * Split out from `users-tab.tsx` for the reason E5.2's `QueuePane` was: the states gallery has to
 * render the **built** component against fixtures, not a copy of its markup, or "it type-checks"
 * quietly becomes "it has been seen rendering". Everything stateful (loading, filters, dialogs,
 * writes) stays in the tab.
 */
export function UsersTable({
  users,
  currentUserId,
  onEdit,
  onToggleActive,
  onRemove,
}: {
  users: AdminUser[]
  currentUserId: string
  onEdit: (user: AdminUser) => void
  onToggleActive: (user: AdminUser) => void
  onRemove: (user: AdminUser) => void
}) {
  return (
    <TableCard>
      <table className="w-full table-fixed border-collapse text-body">
        <colgroup>
          <col className="w-[18%]" />
          <col className="w-[30%]" />
          <col className="w-[16%]" />
          <col className="w-[18%]" />
          <col className="w-[12%]" />
          <col className="w-[6%]" />
        </colgroup>
        <thead>
          <tr className="border-b border-border text-left text-label text-muted-foreground uppercase tracking-wide">
            <th scope="col" className="px-4 py-3">Name</th>
            <th scope="col" className="px-4 py-3">Email</th>
            <th scope="col" className="px-4 py-3">Role</th>
            <th scope="col" className="px-4 py-3">Scope</th>
            <th scope="col" className="px-4 py-3">Status</th>
            <th scope="col" className="px-4 py-3">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <UserRow
              key={user.user_id}
              user={user}
              isSelf={user.user_id === currentUserId}
              onEdit={() => onEdit(user)}
              onToggleActive={() => onToggleActive(user)}
              onRemove={() => onRemove(user)}
            />
          ))}
        </tbody>
      </table>
    </TableCard>
  )
}

/**
 * `components.md` §1: an inactive user's row "stays fully legible, only the status column signals
 * it" — the dimming is scoped to the Status cell, never applied to the row.
 *
 * `.st-on`/`.st-off` in the mockup resolve to `--status-active` (green-700 light, green-400 dark
 * per `implementation-spec.md` §5.3's R17) and text-tertiary. `theme.css` has no `--color-status-*`
 * token; `text-success-fg` resolves to exactly those two values across the two themes, so it is
 * used rather than adding a token to a shared file two other builds are reading right now.
 */
function UserRow({
  user,
  isSelf,
  onEdit,
  onToggleActive,
  onRemove,
}: {
  user: AdminUser
  isSelf: boolean
  onEdit: () => void
  onToggleActive: () => void
  onRemove: () => void
}) {
  const active = isActiveUser(user)
  const scopeId = user.facility_id ?? user.driver_id
  const label = user.full_name ?? user.email

  return (
    <tr className="border-b border-border last:border-b-0 hover:bg-hover">
      <td className="truncate px-4 py-3">
        {user.full_name ?? <span aria-label="Name not yet known">—</span>}
      </td>
      <td className="truncate px-4 py-3 font-data">{user.email}</td>
      <td className="truncate px-4 py-3">{roleDisplayName(user.role_name)}</td>
      <td className="truncate px-4 py-3">
        {/*
          A-G4 / issue #72: at most one facility is knowable here, because `list_users` reads
          `users.facility_id` and never joins `user_scopes`. This cell is where the comma-joined
          scope list renders once #72 lands and `adminMultiFacilityScopeEnabled` flips — there is
          deliberately no second branch today, because a branch producing the same single value
          would read as "multi-facility is handled" when nothing produces it.
        */}
        {scopeId ? facilityDisplayName(scopeId) : <span className="text-subtle-foreground">—</span>}
      </td>
      <td className="px-4 py-3">
        {/*
          A-G5 / issue #73: there is no third, "Invited" status to render — `invite_user` writes
          `is_active = 1` immediately, and `last_login_ts IS NULL` conflates "pending" with
          "hasn't signed in yet", which is a different fact.
        */}
        {adminPendingInvitesEnabled && user.last_login_ts === null ? (
          <span className="text-warning-fg">Invited</span>
        ) : active ? (
          <span className="text-success-fg">Active</span>
        ) : (
          <span className="text-subtle-foreground">Inactive</span>
        )}
      </td>
      <td className="px-4 py-3 text-right">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label={`Actions for ${label}`}>
              <Ellipsis aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={onEdit}>Edit</DropdownMenuItem>
            {/*
              Moderate tier (`components.md` §19): immediate, no modal. Reactivate in this same
              menu is the reversal path.

              ⚠ Unresolved design conflict, carried forward rather than invented over —
              `mockup.html` §2.2 flags it as its own "gap 9": `screens.md` says Deactivate is
              "immediate, reversible via Reactivate, no typed confirmation" while foundations §19's
              Moderate tier says "acts immediately, 5-second undo, no modal". Those are two
              different affordances. The mockup renders neither and says it needs an owner call;
              this renders neither either, and names the reversal path in the success announcement
              instead of inventing an undo toast that would need a second write to be honest.
            */}
            <DropdownMenuItem onSelect={onToggleActive}>
              {active ? 'Deactivate' : 'Reactivate'}
            </DropdownMenuItem>
            {/*
              Flow 4 point 3: Remove is HIDDEN on the signed-in admin's own account, not disabled —
              the same "structurally impossible action is absent" rule (foundations §18) the
              product applies to scope-denied actions everywhere else.
            */}
            {isSelf ? null : (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem variant="destructive" onSelect={onRemove}>
                  Remove
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </td>
    </tr>
  )
}
