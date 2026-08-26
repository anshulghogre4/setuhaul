import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'

import type { Identity, RoleGrant } from '@/core/auth/identity'
import { useTheme, type ThemeChoice } from '@/shared/lib/theme'
import { Button } from '@/shared/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/ui/popover'
import { SegmentedControl } from '@/shared/ui/segmented-control'
import { cn } from '@/shared/lib/utils'

const THEME_SEGMENTS = [
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
  { value: 'system', label: 'System' },
] as const satisfies readonly { value: ThemeChoice; label: string }[]

/**
 * Artboards 13-14.  280px popover anchored 8px below the top bar.  Non-modal: no scrim,
 * nothing behind it is dimmed or blocked, Escape closes and returns focus to the avatar.
 *
 * Four decisions that are easy to undo by accident:
 *
 *  - **The identity header is inert.**  No hover, no cursor change, no focus ring.  Role and
 *    scope are shown because they change what a click means; the email is not, because it
 *    changes nothing.
 *  - **"Switch role" is absent from the DOM for a single-role account, not greyed** (U83).
 *  - **Appearance is an inline segmented control**, visible without opening anything, marked
 *    by fill AND weight, never colour alone.
 *  - **"Sign out everywhere" expands in place** into a confirmation inside the same popover.
 *    No modal, no separate dialog, no active-sessions list, no device inventory -- one
 *    button, no forensics.
 *
 * No leading icons on menu items: this shell has no menu-icon vocabulary, and inventing one
 * here would commit every future menu to it.  The chevron on "Switch role" is a trailing
 * submenu indicator, not a label icon.
 */
export function UserMenu({
  identity,
  onSwitchRole,
  onSignOut,
  onSignOutEverywhere,
}: {
  identity: Identity
  onSwitchRole?: (grant: RoleGrant) => void
  onSignOut?: () => void
  onSignOutEverywhere?: () => void
}) {
  const [open, setOpen] = useState(false)
  const [confirmingEverywhere, setConfirmingEverywhere] = useState(false)
  const [switchingRole, setSwitchingRole] = useState(false)
  const { choice, setChoice } = useTheme()

  const multiRole = identity.grants.length > 1
  const activeGrant = identity.grants.find((g) => g.role === identity.activeRole)

  return (
    <Popover
      open={open}
      onOpenChange={(next) => {
        setOpen(next)
        if (!next) {
          setConfirmingEverywhere(false)
          setSwitchingRole(false)
        }
      }}
    >
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-haspopup="menu"
          aria-expanded={open}
          aria-label={`Account menu — ${identity.fullName}`}
          className="grid size-8 place-items-center rounded-full bg-avatar text-xs font-semibold text-avatar-foreground transition-shadow duration-(--d-fast) ease-(--e-out) hover:shadow-[0_0_0_2px_var(--color-input)] focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
        >
          {identity.initials}
        </button>
      </PopoverTrigger>

      <PopoverContent
        align="end"
        sideOffset={8}
        role="menu"
        aria-label="Account"
        className="w-70 overflow-hidden rounded-md border border-floating-border bg-popover p-0 shadow-floating"
      >
        {/* Inert.  Not a button, not focusable, no hover -- it is information, not a control. */}
        <div className="px-4 py-3">
          <div className="text-body font-semibold">{identity.fullName}</div>
          <div className="mt-0.5 text-supporting text-muted-foreground">
            {activeGrant ? `${activeGrant.roleLabel} — ${activeGrant.scopeLabel}` : identity.activeRoleLabel}
          </div>
        </div>
        <MenuSeparator />

        {multiRole ? (
          <>
            <button
              type="button"
              role="menuitem"
              aria-haspopup="menu"
              aria-expanded={switchingRole}
              onClick={() => setSwitchingRole((v) => !v)}
              className={menuItemClass()}
            >
              Switch role
              <ChevronRight className="size-3.5 text-subtle-foreground" aria-hidden="true" />
            </button>
            {switchingRole ? (
              <div role="menu" aria-label="Switch role">
                {identity.grants
                  .filter((g) => g.role !== identity.activeRole)
                  .map((g) => (
                    <button
                      key={`${g.role}-${g.scopeLabel}`}
                      type="button"
                      role="menuitem"
                      onClick={() => {
                        onSwitchRole?.(g)
                        setOpen(false)
                      }}
                      className={cn(menuItemClass(), 'bg-sunken pl-8')}
                    >
                      <span>
                        {g.roleLabel}
                        <span className="block text-supporting text-muted-foreground">
                          {g.scopeLabel}
                        </span>
                      </span>
                    </button>
                  ))}
              </div>
            ) : null}
          </>
        ) : null}

        <div className="px-4 py-3">
          <div id="appearance-label" className="mb-2 text-body">
            Appearance
          </div>
          <SegmentedControl
            segments={THEME_SEGMENTS}
            value={choice}
            onValueChange={setChoice}
            labelledBy="appearance-label"
          />
        </div>
        <MenuSeparator />

        <Link to="/settings" role="menuitem" className={menuItemClass()} onClick={() => setOpen(false)}>
          Settings
        </Link>
        <MenuSeparator />

        <button type="button" role="menuitem" onClick={onSignOut} className={menuItemClass('danger')}>
          Sign out
        </button>
        <button
          type="button"
          role="menuitem"
          aria-expanded={confirmingEverywhere}
          onClick={() => setConfirmingEverywhere((v) => !v)}
          className={menuItemClass('danger')}
        >
          Sign out everywhere
        </button>

        {confirmingEverywhere ? (
          <div className="bg-hover px-4 py-3">
            <p className="mb-3 text-supporting text-muted-foreground">
              This signs you out on every device you&rsquo;re signed in on.
            </p>
            <Button variant="destructive" size="sm" full onClick={onSignOutEverywhere}>
              Sign out everywhere
            </Button>
          </div>
        ) : null}
      </PopoverContent>
    </Popover>
  )
}

function MenuSeparator() {
  return <hr className="h-px border-0 bg-border" />
}

function menuItemClass(tone?: 'danger') {
  return cn(
    'flex min-h-11 w-full items-center justify-between gap-2 px-4 py-2.5 text-left text-body no-underline',
    'transition-colors duration-(--d-fast) ease-(--e-out) hover:bg-hover',
    'focus-visible:outline-2 focus-visible:outline-ring focus-visible:-outline-offset-2',
    tone === 'danger' ? 'text-danger-fg' : 'text-foreground',
  )
}
