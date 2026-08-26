import { useRef } from 'react'

import { AuthShell } from '@/features/auth/auth-shell'
import type { RoleGrant } from '@/core/auth/identity'

/**
 * Artboard 5.  Interstitial between password submit and the landing surface.
 *
 * **Never renders with one row.**  An account resolving to a single role skips this screen
 * entirely and goes straight to its landing surface -- the guard is at the top of the
 * component, not left to the caller, because "render a one-option chooser" is a bug that
 * looks like a feature.
 *
 * Deliberately a plain list of buttons, NOT a radio-group and NOT a command list.  The whole
 * row is the target and activating it proceeds immediately: no selected state, no radio, no
 * "Continue".  A selection step would add a decision that the click already made.
 *
 * No icons and no facility swatch: accent colour is reserved for the rail stripe and the
 * facility switcher, and spending it here would break the "exactly two locations" argument
 * that makes it safe at all.
 *
 * Hover changes background only -- never lift, scale, or shift.
 */
export function RolePicker({
  grants,
  onChoose,
}: {
  grants: RoleGrant[]
  onChoose: (grant: RoleGrant) => void
}) {
  const rowRefs = useRef<(HTMLButtonElement | null)[]>([])

  if (grants.length < 2) return null

  const move = (from: number, delta: number) => {
    const next = (from + delta + grants.length) % grants.length
    rowRefs.current[next]?.focus()
  }

  return (
    <AuthShell>
      <h1 className="text-h2">Choose how to sign in</h1>
      <p className="mt-2 text-body text-muted-foreground">
        You have more than one role. This decides what you see.
      </p>
      <div className="mt-6 border-t border-border">
        {grants.map((grant, i) => (
          <button
            key={`${grant.role}-${grant.scopeLabel}`}
            ref={(el) => {
              rowRefs.current[i] = el
            }}
            type="button"
            onClick={() => onChoose(grant)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') {
                e.preventDefault()
                move(i, 1)
              } else if (e.key === 'ArrowUp') {
                e.preventDefault()
                move(i, -1)
              }
            }}
            className="block min-h-11 w-full border-b border-border px-4 py-3 text-left transition-colors duration-(--d-fast) ease-(--e-out) hover:bg-hover focus-visible:outline-2 focus-visible:outline-ring focus-visible:-outline-offset-2"
          >
            <span className="block text-body font-semibold text-foreground">{grant.roleLabel}</span>
            <span className="mt-0.5 block text-supporting text-muted-foreground">
              {grant.scopeLabel}
            </span>
          </button>
        ))}
      </div>
    </AuthShell>
  )
}
