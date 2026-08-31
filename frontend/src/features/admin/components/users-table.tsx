import { ClockFading, Ellipsis } from 'lucide-react'
import type { ReactNode } from 'react'

import { TableCard } from './primitives'
import { adminMultiFacilityScopeEnabled, adminPendingInvitesEnabled } from '../lib/flags'
import { roleDisplayName } from '../lib/roles'
import { isActiveUser, lifecycleStateOf, type AdminUser } from '../lib/types'
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
 *
 * `facilityName` is injected rather than imported because the names now come from the server
 * (`GET /admin/facilities`, issue #78) and this component must stay fetch-free — the gallery passes
 * a fixture-backed resolver, the live tab passes the directory's.
 */
export function UsersTable({
  users,
  currentUserId,
  facilityName,
  onEdit,
  onToggleActive,
  onRemove,
  onResendInvite,
  onRevokeInvite,
}: {
  users: AdminUser[]
  currentUserId: string
  facilityName: (facilityId: string) => string
  onEdit: (user: AdminUser) => void
  onToggleActive: (user: AdminUser) => void
  onRemove: (user: AdminUser) => void
  /** Only ever called for a row whose `lifecycle_state` is `INVITED`. */
  onResendInvite: (user: AdminUser) => void
  onRevokeInvite: (user: AdminUser) => void
}) {
  return (
    <TableCard>
      <table className="w-full table-fixed border-collapse text-body">
        <colgroup>
          <col className="w-[16%]" />
          <col className="w-[26%]" />
          <col className="w-[14%]" />
          <col className="w-[18%]" />
          {/* Status widened from 12% to 16%: the Invited badge carries the mockup's full
              "Invited, awaiting acceptance" wording, not a one-word abbreviation of it. */}
          <col className="w-[16%]" />
          <col className="w-[10%]" />
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
              facilityName={facilityName}
              onEdit={() => onEdit(user)}
              onToggleActive={() => onToggleActive(user)}
              onRemove={() => onRemove(user)}
              onResendInvite={() => onResendInvite(user)}
              onRevokeInvite={() => onRevokeInvite(user)}
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
  facilityName,
  onEdit,
  onToggleActive,
  onRemove,
  onResendInvite,
  onRevokeInvite,
}: {
  user: AdminUser
  isSelf: boolean
  facilityName: (facilityId: string) => string
  onEdit: () => void
  onToggleActive: () => void
  onRemove: () => void
  onResendInvite: () => void
  onRevokeInvite: () => void
}) {
  const active = isActiveUser(user)
  const label = user.full_name ?? user.email
  /**
   * A-G5 / issue #73. **Gated on the server-derived `lifecycle_state`, never on `last_login_ts`.**
   * That column is read in two places and written nowhere in the application (only `seed.sql` sets
   * it), so the predicate this row used to carry — `user.last_login_ts === null` — would have
   * labelled essentially every user "Invited" the moment the flag flipped. `lifecycle_state` comes
   * from `derive_lifecycle_state`, whose whole content is the precedence between the three stamps.
   */
  const invited = adminPendingInvitesEnabled && lifecycleStateOf(user) === 'INVITED'

  return (
    <tr className="border-b border-border last:border-b-0 hover:bg-hover">
      <td className="truncate px-4 py-3">
        {user.full_name ?? <span aria-label="Name not yet known">—</span>}
      </td>
      <td className="truncate px-4 py-3 font-data">{user.email}</td>
      <td className="truncate px-4 py-3">{roleDisplayName(user.role_name)}</td>
      <td className="truncate px-4 py-3">
        <ScopeCell user={user} facilityName={facilityName} />
      </td>
      <td className="px-4 py-3">
        {invited ? (
          /*
            `stitch-prompts.md`'s Status-column spec, verbatim: a distinct badge with Lucide
            `clock-fade` inline, "because a pending invitation is not an account state, so it must
            not look like one". Lucide renamed that glyph `clock-fading` in its 2025 sweep;
            `ClockFading` is the export present in the pinned lucide-react 1.34.0 (checked against
            the installed package, not assumed from the mockup's `#i-clock-fade` id).

            The mockup's literal hexes (#B45309 on #FFFBEB, border #F59E0B) are exactly
            `theme.css`'s amber-700/amber-50/amber-600 warning triple, so the tokens are used rather
            than hard-coded values that could not follow the dark theme.
          */
          <span className="inline-flex items-center gap-1.5 rounded-sm border border-warning-border bg-warning-bg px-2 py-0.5 text-label font-semibold text-warning-fg">
            <ClockFading className="size-3.5 shrink-0" aria-hidden="true" />
            Invited, awaiting acceptance
          </span>
        ) : active ? (
          <span className="text-success-fg">Active</span>
        ) : (
          <span className="text-subtle-foreground">Inactive</span>
        )}
      </td>
      <td className="px-4 py-3 text-right">
        {invited ? (
          /*
            `screens.md` §2 and `stitch-prompts.md`: "the pending row replaces the overflow menu
            with two inline text buttons". Not an addition to the menu — Edit, Deactivate and
            Remove are all wrong on a row that has no account behind it yet (`update_user` would
            edit a user who may never accept; `_set_active` and `remove_user` both act on an
            accepted account's semantics), and `revoke_invite` is the tool that expresses the one
            thing an admin actually wants here.

            **Revoke commits immediately, with no typed confirmation, and that is a deliberate
            reading of foundations §19 rather than a shortcut.** §19's High tier names "removing a
            user"; the backend deliberately makes `revoke_invite` a *different* audit event from
            `REMOVE_USER` because "we withdrew an invite nobody had used" and "we removed a working
            colleague" are different facts. This is Moderate tier — and since §19's Moderate
            affordance (a 5-second undo) has no backing tool, the success announcement names the
            recovery path instead, exactly as Deactivate already does below.
          */
          <div className="flex justify-end gap-2">
            <InlineAction onClick={onResendInvite} label={`Resend invitation to ${user.email}`}>
              Resend
            </InlineAction>
            <InlineAction onClick={onRevokeInvite} label={`Revoke invitation for ${user.email}`}>
              Revoke
            </InlineAction>
          </div>
        ) : (
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
                "immediate, reversible via Reactivate, no typed confirmation" while foundations
                §19's Moderate tier says "acts immediately, 5-second undo, no modal". Those are two
                different affordances. The mockup renders neither and says it needs an owner call;
                this renders neither either, and names the reversal path in the success
                announcement instead of inventing an undo toast that would need a second write to
                be honest.
              */}
              <DropdownMenuItem onSelect={onToggleActive}>
                {active ? 'Deactivate' : 'Reactivate'}
              </DropdownMenuItem>
              {/*
                Flow 4 point 3: Remove is HIDDEN on the signed-in admin's own account, not disabled
                — the same "structurally impossible action is absent" rule (foundations §18) the
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
        )}
      </td>
    </tr>
  )
}

/**
 * The Scope cell.
 *
 * `components.md` §1's anatomy asks for "scope (facility/carrier/driver names, comma-joined)", and
 * `screens.md` §2's own first example row is a user scoped to two facilities ("Neha B. · Ops ·
 * Jaipur, Gurugram"). `list_users` returns `scoped_facility_ids` as a real array (A-G4 / #72), so
 * the join is over the server's list rather than over the single `users.facility_id` mirror.
 *
 * The `adminMultiFacilityScopeEnabled` branch is not cosmetic: with the flag off, a row is rendered
 * from the single mirror column, which is what a client that cannot *write* a second facility
 * should show. Rendering two facilities while the form can only assign one would state a capability
 * the surface does not have.
 */
function ScopeCell({
  user,
  facilityName,
}: {
  user: AdminUser
  facilityName: (facilityId: string) => string
}) {
  const scoped = user.scoped_facility_ids ?? []
  if (adminMultiFacilityScopeEnabled && scoped.length > 0) {
    return <>{scoped.map((id) => facilityName(id)).join(', ')}</>
  }
  const single = user.facility_id ?? user.driver_id
  // A driver id is shown raw: `facilityName` resolves facilities, and passing a driver id through
  // it would return the id anyway — via a lookup that could one day return a wrong hit.
  if (!single) return <span className="text-subtle-foreground">—</span>
  return <>{user.facility_id ? facilityName(user.facility_id) : single}</>
}

/**
 * The pending row's inline text button (`stitch-prompts.md`: 13px/600, transparent, 8px gap).
 *
 * `implementation-spec.md` §5's R6 caught the mockup's version measuring ~18.5px on the **width**
 * axis, under WCAG 2.2 SC 2.5.8's 24px minimum, and widened its focus/press box. The same
 * correction is made here with real padding plus a `-mx-1.5` pull, so the row's visual rhythm is
 * unchanged.
 *
 * **`min-h-8` rather than the 24px floor**, measured rather than assumed: at `min-h-6` these render
 * 58.9×24 and 57.9×24 — compliant, but the smallest targets on the surface. 32px matches the
 * `Actions for …` icon button that occupies this exact cell on every other row, so the pending row
 * does not have a *smaller* hit area than the row above it purely because its actions are text.
 * The background is transparent, so the extra height is invisible.
 */
function InlineAction({
  onClick,
  label,
  children,
}: {
  onClick: () => void
  label: string
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      className="-mx-1.5 min-h-8 rounded-sm px-1.5 text-supporting font-semibold text-muted-foreground underline-offset-2 outline-none hover:text-foreground hover:underline focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
    >
      {children}
    </button>
  )
}
