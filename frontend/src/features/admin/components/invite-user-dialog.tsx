import { CircleAlert } from 'lucide-react'
import { useEffect, useId, useRef, useState } from 'react'

import { InactiveNote } from './primitives'
import { adminMultiFacilityScopeEnabled } from '../lib/flags'
import { ROLE_OPTIONS, roleOption } from '../lib/roles'
import type { AdminUser } from '../lib/types'
import { Button } from '@/shared/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/ui/dialog'
import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'

/**
 * Screen 3 — invite / edit user. **🟡, built in reduced form** (`implementation-spec.md` §3).
 *
 * What is real: role and scope in **one submission**, never a two-step create-then-scope sequence.
 * That is the whole point `SOLUTION_DESIGN.md` §7.5.7 states and `admin_user_service.py`'s own
 * module docstring repeats — "a user briefly existing with a role but no scope is a real
 * authorization gap, not a UX nicety" — and `invite_user` genuinely implements it.
 *
 * Four honest reductions against the artboards, each with its cause:
 *
 *  1. **Single facility, not the chip multi-select.** A-G4 / issue #72:
 *     `invite_user`/`update_user` take `scope: str | None`, a bare single value, and
 *     `_validate_scope` requires exactly one. The "+ Add facility" affordance has nowhere to send
 *     a second value, so it is behind `adminMultiFacilityScopeEnabled`.
 *  2. **Facility options come from facilities already present in the loaded rows**, because there
 *     is no facilities-list endpoint anywhere in the API (see `lib/facility-names.ts`'s header).
 *     When that set is empty the field is Inactive with the reason stated, not a free-text box —
 *     the server existence-checks the id (`_validate_scope`, lines 137-141), so a typed guess
 *     would fail on submit rather than at the point of the mistake.
 *  3. **Carrier and driver scopes are Inactive.** No endpoint anywhere lists carriers or drivers
 *     for an admin, and `_validate_scope` does not even existence-check `carrier_id` (line
 *     143-146) — a free-text field here would let a typo create a user scoped to a carrier that
 *     does not exist, with no error. Same Inactive-with-explanation posture E5.2 used for ops'
 *     "Take over thread".
 *  4. **Email is read-only in edit mode.** `update_user` accepts `role` and `scope` only
 *     (`admin.py:64-68`); the address lives in the Supabase Auth identity, which this tool never
 *     touches. `mockup.html` §3.5 draws it as an editable field — rendering it editable would
 *     offer a change the tool silently discards.
 *
 * Focus lands on the first field, never a submit button; Cancel is first in DOM order (U79).
 */
export function InviteUserDialog({
  mode,
  user,
  open,
  onOpenChange,
  onSubmit,
  facilities,
  busy,
  errorDetail,
}: {
  mode: 'invite' | 'edit'
  /** Pre-fill source in edit mode; ignored in invite mode. */
  user: AdminUser | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (payload: { email: string; role: string; scope?: string }) => void
  facilities: Array<{ id: string; name: string }>
  busy?: boolean
  errorDetail?: string | null
}) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('')
  const [scope, setScope] = useState('')
  const [emailTouched, setEmailTouched] = useState(false)

  const emailRef = useRef<HTMLInputElement | null>(null)
  const roleRef = useRef<HTMLSelectElement | null>(null)
  const emailId = useId()
  const roleId = useId()
  const scopeId = useId()
  const emailErrId = useId()

  // Re-seed whenever the dialog opens so an Edit never inherits the previous row's values.
  useEffect(() => {
    if (!open) return
    setEmail(mode === 'edit' ? (user?.email ?? '') : '')
    setRole(mode === 'edit' ? (user?.role_name ?? '') : '')
    setScope(mode === 'edit' ? (user?.facility_id ?? user?.driver_id ?? '') : '')
    setEmailTouched(false)
  }, [open, mode, user])

  const selectedRole = roleOption(role)
  const scopeKind = selectedRole?.scope ?? null

  // Validated on blur, not on keystroke (`mockup.html` §3.4). A bare shape check only — the
  // authoritative "this email already has an account" verdict comes from Supabase Auth via the
  // server's own named error, which is surfaced through `errorDetail` below.
  const emailShapeInvalid = emailTouched && email.trim() !== '' && !email.includes('@')

  const scopeSatisfied =
    scopeKind === null
      ? false
      : scopeKind === 'none'
        ? true
        : scopeKind === 'facility'
          ? scope !== ''
          : // carrier / driver: no source of valid ids exists, so the form can never be complete
            false

  const canSubmit =
    !busy && role !== '' && scopeSatisfied && (mode === 'edit' || (email.trim() !== '' && email.includes('@')))
  const whyUnavailable = busy
    ? 'Submitting…'
    : role === ''
      ? 'Choose a role first.'
      : !scopeSatisfied
        ? 'This role needs a scope that can’t be selected yet.'
        : 'Enter an email address.'

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-md"
        onOpenAutoFocus={(event) => {
          event.preventDefault()
          if (mode === 'edit') roleRef.current?.focus()
          else emailRef.current?.focus()
        }}
      >
        <DialogHeader>
          <DialogTitle>{mode === 'edit' ? 'Edit user' : 'Invite user'}</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-2">
          <Label htmlFor={emailId}>Email</Label>
          <Input
            ref={emailRef}
            id={emailId}
            type="email"
            value={email}
            readOnly={mode === 'edit'}
            required
            autoComplete="off"
            spellCheck={false}
            aria-invalid={emailShapeInvalid || undefined}
            aria-describedby={emailShapeInvalid ? emailErrId : undefined}
            className="font-data"
            onBlur={() => setEmailTouched(true)}
            onChange={(e) => setEmail(e.currentTarget.value)}
          />
          {emailShapeInvalid ? (
            <p id={emailErrId} className="flex items-center gap-2 text-supporting text-danger-fg">
              <CircleAlert className="size-3.5 shrink-0" aria-hidden="true" />
              That doesn’t look like an email address.
            </p>
          ) : null}
          {mode === 'edit' ? (
            <InactiveNote>
              The address belongs to the Supabase Auth identity; <code>update_user</code> changes
              role and scope only.
            </InactiveNote>
          ) : null}
        </div>

        <div className="flex flex-col gap-2">
          <Label htmlFor={roleId}>Role</Label>
          <select
            ref={roleRef}
            id={roleId}
            required
            value={role}
            onChange={(e) => {
              setRole(e.currentTarget.value)
              // The scope's meaning changes with the role, so a value carried over from the
              // previous selection would be a facility id submitted as a carrier id.
              setScope('')
            }}
            className="h-11 rounded-md border border-input bg-card px-3 text-body text-foreground outline-none transition-colors duration-(--d-fast) hover:border-strong focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
          >
            <option value="">Select a role</option>
            {ROLE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        {/*
          The scope field's SHAPE follows the role (`components.md` §1), and a role that needs no
          scope renders no field at all — absent from the layout, not shown disabled
          (`mockup.html` §3.5: "the row that assigns scope to everyone else does not itself carry
          one").
        */}
        {role === '' ? (
          <p className="text-supporting text-muted-foreground">
            The scope field appears once a role is selected — its shape depends on the role.
          </p>
        ) : null}

        {scopeKind === 'facility' ? (
          <div className="flex flex-col gap-2">
            <Label htmlFor={scopeId}>Facility scope</Label>
            {facilities.length === 0 ? (
              <InactiveNote>
                No facility can be selected — nothing in the API lists facilities, and no loaded
                user or rule names one to derive the list from.
              </InactiveNote>
            ) : (
              <select
                id={scopeId}
                required
                value={scope}
                onChange={(e) => setScope(e.currentTarget.value)}
                className="h-11 rounded-md border border-input bg-card px-3 text-body text-foreground outline-none transition-colors duration-(--d-fast) hover:border-strong focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
              >
                <option value="">Select a facility</option>
                {facilities.map((facility) => (
                  <option key={facility.id} value={facility.id}>
                    {facility.name}
                  </option>
                ))}
              </select>
            )}
            {adminMultiFacilityScopeEnabled ? null : (
              <InactiveNote>
                One facility only. Multi-facility scope needs issue #72 —{' '}
                <code>user_scopes</code> exists in the schema but these tools never read or write
                it.
              </InactiveNote>
            )}
          </div>
        ) : null}

        {scopeKind === 'carrier' || scopeKind === 'driver' ? (
          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium">
              {scopeKind === 'carrier' ? 'Carrier scope' : 'Driver scope'}
            </span>
            <InactiveNote>
              No endpoint lists {scopeKind === 'carrier' ? 'carriers' : 'drivers'} for an admin, so
              there is nothing to choose from. A free-text id is deliberately not offered:{' '}
              {scopeKind === 'carrier'
                ? '_validate_scope does not existence-check carrier_id at all, so a typo would create a user scoped to a carrier that does not exist.'
                : 'the id has to match a real drivers row and there is no way to look one up here.'}
            </InactiveNote>
          </div>
        ) : null}

        {errorDetail ? (
          <p role="alert" className="flex items-start gap-2 text-supporting text-danger-fg">
            <CircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            <span>{errorDetail}</span>
          </p>
        ) : null}

        <DialogFooter>
          <Button variant="neutral" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="constructive"
            aria-disabled={!canSubmit}
            tabIndex={0}
            title={canSubmit ? undefined : whyUnavailable}
            className={canSubmit ? undefined : 'opacity-50'}
            onClick={() => {
              if (!canSubmit) return
              onSubmit({
                email: email.trim(),
                role,
                scope: scopeKind === 'none' ? undefined : scope,
              })
            }}
          >
            {mode === 'edit' ? 'Save changes' : 'Send invite'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
