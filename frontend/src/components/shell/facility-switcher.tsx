import { useMemo, useState } from 'react'
import { Check, ChevronDown, Search } from 'lucide-react'

import { hasFacilityScope, type Facility, type RoleName } from '@/core/auth/identity'
// The sentinel moved to `core/auth/active-facility.ts` (issue #99.1): it is now read by the auth
// provider's validation gate as well as by this component, and a constant that decides what a
// read may be scoped to does not belong inside a popover.
import { ALL_FACILITIES } from '@/core/auth/active-facility'
import { Popover, PopoverContent, PopoverTrigger } from '@/shared/ui/popover'

/**
 * Artboard 32.  A search-filterable combobox that **always shows the facility name**, never
 * an icon alone.
 *
 * The swatch here and the rail stripe are the only two places facility accent may appear in
 * this product (U59).  That restriction is what makes spending a hue on facility identity
 * safe at all, so it is worth being blunt: if you find yourself adding a third, the fix is
 * to not.
 *
 * **Absent from the DOM entirely for the carrier role, not disabled** (U83).  A greyed-out
 * switcher would tell a carrier that facilities exist as something this product scopes by --
 * the same structural leak auth-and-scoping.md's inference rule already forbids for data.
 *
 * **Changing facility clears row focus and any pending selection**, so a stale selection can
 * never be acted on in a new context.  The caller owns that reset; it is surfaced here as an
 * explicit callback rather than left implicit.
 *
 * ARIA content model, fixed after a real audit finding: a `listbox` may contain only
 * `option`/`group` children, so the filter input and the separator sit OUTSIDE it.  The
 * input is a `combobox` with `aria-controls` pointing at the inner list; the rule is
 * `aria-hidden`.  The original markup had the input and two `<hr>`s inside the listbox,
 * which is an invalid content model no assistive tech can interpret.
 *
 * "All facilities" carries a **dashed outline, not a hue** -- it is not a facility and must
 * not borrow one's swatch.  It renders only for the cross-facility ops roles (section 7.5.5
 * takes an optional `facility_id`; omitted means every facility in scope).
 */
export function FacilitySwitcher({
  role,
  facilities,
  activeFacilityId,
  canSelectAll,
  onChange,
}: {
  role: RoleName
  facilities: Facility[]
  activeFacilityId: string | null
  canSelectAll: boolean
  onChange: (facilityId: string) => void
}) {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState('')

  const visible = useMemo(
    () => facilities.filter((f) => f.name.toLowerCase().includes(filter.trim().toLowerCase())),
    [facilities, filter],
  )

  if (!hasFacilityScope(role)) return null

  const active = facilities.find((f) => f.id === activeFacilityId) ?? null
  const showingAll = activeFacilityId === ALL_FACILITIES

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-haspopup="listbox"
          aria-expanded={open}
          className="inline-flex h-10 items-center gap-2 rounded-md border border-border bg-transparent px-3 text-body font-medium text-foreground transition-colors duration-(--d-fast) ease-(--e-out) hover:bg-hover focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
        >
          {showingAll ? (
            <span
              aria-hidden="true"
              className="size-3 shrink-0 rounded-sm border border-dashed border-strong"
            />
          ) : (
            <span
              aria-hidden="true"
              className="size-3 shrink-0 rounded-sm"
              style={{ background: `var(--facility-${active?.accent ?? 1})` }}
            />
          )}
          <span translate="no">{showingAll ? 'All facilities' : (active?.name ?? 'Select facility')}</span>
          <ChevronDown className="size-3.5" aria-hidden="true" />
        </button>
      </PopoverTrigger>

      <PopoverContent
        align="start"
        sideOffset={8}
        className="w-70 overscroll-contain rounded-md border border-floating-border bg-popover p-0 shadow-floating"
      >
        <div className="flex items-center gap-2 px-3 py-2">
          <Search className="size-4 text-subtle-foreground" aria-hidden="true" />
          <input
            type="search"
            role="combobox"
            aria-expanded
            aria-controls="facility-listbox"
            aria-label="Filter facilities"
            placeholder="Filter facilities"
            autoComplete="off"
            spellCheck={false}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="min-w-0 flex-1 border-0 bg-transparent p-0 text-body text-foreground outline-none placeholder:text-subtle-foreground"
          />
        </div>
        <hr aria-hidden="true" className="h-px border-0 bg-border" />

        <div id="facility-listbox" role="listbox" aria-label="Facility">
          {visible.map((f) => (
            <button
              key={f.id}
              type="button"
              role="option"
              aria-selected={f.id === activeFacilityId}
              onClick={() => {
                onChange(f.id)
                setOpen(false)
              }}
              className="flex min-h-11 w-full items-center gap-2.5 border-0 bg-transparent px-3 py-2.5 text-left text-body text-foreground transition-colors duration-(--d-fast) ease-(--e-out) hover:bg-hover focus-visible:outline-2 focus-visible:outline-ring focus-visible:-outline-offset-2"
            >
              <span
                aria-hidden="true"
                className="size-3 shrink-0 rounded-sm"
                style={{ background: `var(--facility-${f.accent})` }}
              />
              <span translate="no">{f.name}</span>
              {f.id === activeFacilityId ? (
                <Check className="ml-auto size-3.5 text-primary" aria-hidden="true" />
              ) : null}
            </button>
          ))}

          {canSelectAll ? (
            <>
              <hr aria-hidden="true" className="h-px border-0 bg-border" />
              <button
                type="button"
                role="option"
                aria-selected={showingAll}
                onClick={() => {
                  onChange(ALL_FACILITIES)
                  setOpen(false)
                }}
                className="flex min-h-11 w-full items-center gap-2.5 border-0 bg-transparent px-3 py-2.5 text-left text-body text-foreground transition-colors duration-(--d-fast) ease-(--e-out) hover:bg-hover focus-visible:outline-2 focus-visible:outline-ring focus-visible:-outline-offset-2"
              >
                <span
                  aria-hidden="true"
                  className="size-3 shrink-0 rounded-sm border border-dashed border-strong"
                />
                All facilities
                {showingAll ? (
                  <Check className="ml-auto size-3.5 text-primary" aria-hidden="true" />
                ) : null}
              </button>
            </>
          ) : null}
        </div>
      </PopoverContent>
    </Popover>
  )
}
