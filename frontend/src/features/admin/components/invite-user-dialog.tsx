import { CircleAlert } from 'lucide-react'
import { useEffect, useId, useMemo, useRef, useState } from 'react'

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
 * **Two of the four reductions this dialog shipped with are gone as of 2026-08-31.**
 *
 *  1. **Multi-facility scope is real** (A-G4 / issue #72). `invite_user`/`update_user` take
 *     `scope: str | list[str] | None`, `normalize_scope` de-duplicates, and `_validate_scope`
 *     checks a whole multi-select in one `= ANY(:ids)` round trip naming every missing id at once.
 *     The form sends an array. `screens.md` §2's own first example row ("Neha B. · Ops · Jaipur,
 *     Gurugram") is now producible end to end.
 *  2. **The facility options are a real read** (A-G10 / issue #78). `GET /admin/facilities`
 *     replaced the previous list, which was derived from facilities that happened to appear in
 *     already-loaded rows — so a facility with no users and no rules was unpickable and could
 *     never receive its first user. Options now come from `lib/facilities.ts`'s directory, narrowed
 *     to `active_flag = 1` for a *new* assignment.
 *
 * Two reductions remain, each with its cause:
 *
 *  3. **Carrier and driver scopes are Inactive.** No endpoint anywhere lists carriers or drivers
 *     for an admin, and `_validate_scope` does not even existence-check `carrier_id` — a free-text
 *     field here would let a typo create a user scoped to a carrier that does not exist, with no
 *     error. Same Inactive-with-explanation posture E5.2 used for ops' "Take over thread". Note
 *     #78 does **not** unblock these: it lists facilities, not carriers or drivers.
 *  4. **Email is read-only in edit mode.** `update_user` accepts `role` and `scope` only; the
 *     address lives in the Supabase Auth identity, which this tool never touches. `mockup.html`
 *     §3.5 draws it as an editable field — rendering it editable would offer a change the tool
 *     silently discards.
 *
 * ## The multi-select's shape, and why it is not the mockup's chips
 *
 * `screens.md` draws `[ Jaipur ▾ ] [ + add ]` — a chip row with an "add" affordance, the pattern a
 * long option list needs so it does not fill the dialog. This build uses a **native checkbox group
 * in a `<fieldset>` with a `<legend>`** instead, for the same reason E5.3's Fork G took native
 * controls over the mockup's `role="combobox"` divs: every facility is visible at once at this
 * product's scale, selection state is announced by the platform rather than by hand-written ARIA,
 * and there is no popup to trap focus in. The chip pattern is worth building the moment the
 * facility count outgrows a visible list; it is not worth hand-rolling a combobox to save vertical
 * space that is not scarce. **Flagged as a deliberate divergence from the artboard, not an
 * oversight.**
 *
 * **`GATE_OFFICER` gets the single `<select>` instead, not the checkbox group** (owner-decided
 * 2026-09-01). It is facility-scoped like the other four but capped at one facility, because the
 * gate session belongs to a device rather than a person (`auth-and-scoping.md:66-68`), and the
 * server refuses a second with `GATE_OFFICER_SINGLE_FACILITY` (422). The arity is read from
 * `lib/roles.ts`'s `multiScope`, so the control follows the role's own contract rather than a
 * special case spelled out here. One consequence, traced rather than assumed: opening Edit on a
 * gate officer who somehow already holds two facilities (only creatable in the 2026-08-29 to
 * 2026-09-01 window) shows the first in the `<select>` while `scope` state still holds both, so an
 * untouched Save is refused by name and picking a facility collapses it to one. A refusal that
 * names the problem, not a silent narrowing — which is the right way round for a row that is now
 * invalid.
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
  facilitiesUnavailable,
  busy,
  errorDetail,
}: {
  mode: 'invite' | 'edit'
  /** Pre-fill source in edit mode; ignored in invite mode. */
  user: AdminUser | null
  open: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (payload: { email: string; role: string; scope?: string[] }) => void
  /** The facilities a new scope assignment may name — `active_flag = 1`, server-ordered. */
  facilities: Array<{ id: string; name: string }>
  /** True when the facilities read itself failed, as opposed to genuinely returning none. The two
   *  need different copy: one is "try again", the other is "there are none to pick". */
  facilitiesUnavailable?: boolean
  busy?: boolean
  errorDetail?: string | null
}) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('')
  const [scope, setScope] = useState<string[]>([])
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
    // Pre-fill from the server's own scope array when there is one, falling back to the single
    // mirror column for a row that predates E2.3's backfill. Editing a two-facility user must not
    // silently drop their second facility just because the form once held one value.
    setScope(
      mode === 'edit'
        ? (user?.scoped_facility_ids?.length
            ? [...user.scoped_facility_ids]
            : [user?.facility_id ?? user?.driver_id].filter((v): v is string => Boolean(v)))
        : [],
    )
    setEmailTouched(false)
  }, [open, mode, user])

  const selectedRole = roleOption(role)
  const scopeKind = selectedRole?.scope ?? null

  /**
   * Whether the facility control is a multi-select at all.
   *
   * Two independent reasons it may not be, and they need different copy below because they are
   * different facts: the flag is "not yet", the role cap is "never".
   *  - `adminMultiFacilityScopeEnabled` off — the whole A-G4 / #72 capability is gated.
   *  - `multiScope: false` on the role — `GATE_OFFICER` is facility-scoped but device-bound, so
   *    `_validate_scope` refuses a second facility with `GATE_OFFICER_SINGLE_FACILITY` (422).
   *    Offering checkboxes here would be a form that fails only on submit, which is the exact
   *    failure `lib/roles.ts` exists to prevent.
   */
  const multiFacility = adminMultiFacilityScopeEnabled && (selectedRole?.multiScope ?? false)

  /**
   * The options this form may offer.
   *
   * In edit mode a facility the user is **already** scoped to stays selectable even if it is now
   * closed (`active_flag = 0`, so absent from `facilities`) — otherwise opening Edit on that user
   * would silently drop a scope they hold, and saving would revoke it without ever saying so.
   */
  const facilityOptions = useMemo(() => {
    const known = new Set(facilities.map((f) => f.id))
    const carried = scope
      .filter((id) => !known.has(id))
      .map((id) => ({ id, name: `${id} (no longer active)` }))
    return [...facilities, ...carried]
  }, [facilities, scope])

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
          ? scope.length > 0
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
              setScope([])
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
            {facilityOptions.length === 0 ? (
              <>
                <span className="text-sm font-medium">Facility scope</span>
                <InactiveNote>
                  {facilitiesUnavailable
                    ? 'The facility list could not be loaded, so no scope can be chosen. Close this dialog and retry the list — a typed id is deliberately not offered, because the server existence-checks it and a guess would fail on submit rather than at the point of the mistake.'
                    : 'No facility exists to scope this role to. Create a facility first; a typed id is deliberately not offered, because the server existence-checks it.'}
                </InactiveNote>
              </>
            ) : multiFacility ? (
              /*
                The multi-select (A-G4 / #72). A native checkbox group rather than the mockup's chip
                row — see this component's header for the reasoning and the flagged divergence.
                `<fieldset>`/`<legend>` is what gives the group an accessible name without a
                hand-written `aria-labelledby`, and each box is its own label-wrapped control.
              */
              <fieldset className="flex flex-col gap-2 border-0 p-0">
                <legend className="mb-1 text-sm font-medium">Facility scope</legend>
                <div className="flex flex-col gap-1 rounded-md border border-input bg-card p-2">
                  {facilityOptions.map((facility) => (
                    <label
                      key={facility.id}
                      className="flex min-h-9 items-center gap-2 rounded-sm px-2 text-body hover:bg-hover has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-ring has-[:focus-visible]:outline-offset-2"
                    >
                      <input
                        type="checkbox"
                        className="size-4 accent-[var(--color-primary)]"
                        checked={scope.includes(facility.id)}
                        onChange={(event) => {
                          /*
                            Read `checked` HERE, not inside the functional updater below.

                            MDN, `Event.currentTarget` (checked 2026-08-31): "the value of
                            `currentTarget` is only available in a handler for the event. Outside
                            an event handler it will be `null` ... if you take a reference to the
                            Event object inside an event handler and then access its
                            `currentTarget` property outside the event handler, its value will be
                            `null`." React's event object mirrors that. A functional updater runs
                            *later*, during render — outside the handler — so
                            `e.currentTarget.checked` in there is a read on `null` and the box
                            silently never ticks.

                            Found by a headless click-through, not by review: it type-checks, reads
                            correctly, and fails only when a human (or Playwright) clicks it.
                          */
                          const nowChecked = event.currentTarget.checked
                          setScope((current) =>
                            nowChecked
                              ? // De-duplicated here as well as server-side: `user_scopes` carries
                                // UNIQUE (user_id, scope_type, scope_value), and a form that could
                                // submit the same id twice would be leaning on the backend to save
                                // it.
                                current.includes(facility.id)
                                ? current
                                : [...current, facility.id]
                              : current.filter((id) => id !== facility.id),
                          )
                        }}
                      />
                      {facility.name}
                    </label>
                  ))}
                </div>
                <p className="text-supporting text-muted-foreground">
                  {scope.length === 0
                    ? 'Choose at least one facility.'
                    : `${scope.length} selected.`}
                </p>
              </fieldset>
            ) : (
              <>
                <Label htmlFor={scopeId}>Facility scope</Label>
                <select
                  id={scopeId}
                  required
                  value={scope[0] ?? ''}
                  onChange={(e) =>
                    setScope(e.currentTarget.value === '' ? [] : [e.currentTarget.value])
                  }
                  className="h-11 rounded-md border border-input bg-card px-3 text-body text-foreground outline-none transition-colors duration-(--d-fast) hover:border-strong focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
                >
                  <option value="">Select a facility</option>
                  {facilityOptions.map((facility) => (
                    <option key={facility.id} value={facility.id}>
                      {facility.name}
                    </option>
                  ))}
                </select>
                <InactiveNote>
                  {selectedRole?.multiScope === false ? (
                    <>
                      One facility only. The gate session is bound to a <strong>device</strong>, not
                      to a person, so the kiosk’s facility is the one it stands at — an officer
                      covering two gates uses a device session at each. A second facility would be
                      access nothing in the kiosk can reach.
                    </>
                  ) : (
                    <>
                      One facility only, while <code>adminMultiFacilityScopeEnabled</code> is off.
                    </>
                  )}
                </InactiveNote>
              </>
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
                // Omitted entirely for a global role rather than sent empty — `_validate_scope`
                // returns early for GLOBAL_ROLES, and an empty array would be a claim about scope
                // where the honest encoding is silence.
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
