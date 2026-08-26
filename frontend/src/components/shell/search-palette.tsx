import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { Clock, Search, SearchX } from 'lucide-react'

import { Dialog, DialogContent, DialogTitle } from '@/shared/ui/dialog'
import { EmptyState } from '@/shared/ui/empty-state'
import { cn } from '@/shared/lib/utils'

/** Fixed group order.  A group with no matches is ABSENT entirely, never an empty header. */
export const GROUP_ORDER = [
  'Shipments',
  'Appointments',
  'Drivers',
  'Carriers',
  'Facilities',
] as const
export type SearchGroup = (typeof GROUP_ORDER)[number]

export type SearchResult = {
  id: string
  group: SearchGroup
  /** The mono identifier -- always the first element of the row. */
  identifier: string
  /** Secondary line.  Every appointment result carries its dock, its date and its time, in
   *  that order -- never a bare time. */
  meta: string
  href: string
}

export type RecentSearch = { id: string; query: string }

/**
 * Artboards 19-21.  640px, offset ~15% from the top rather than vertically centred -- it
 * should sit where the eye already is.  Flat scrim, dimming, never blur.
 *
 * **Facility-scoped for v1, and the scope line says so.**  There is deliberately no control
 * to change scope here: a user should never wonder why a Gurugram shipment is missing, and
 * they should also not be able to widen scope from a search box.
 *
 * **The keyboard highlight is background AND a 2px left edge**, never colour alone.  Matched
 * substrings are marked by weight 600, not a coloured highlight, so a match never looks like
 * a state.
 *
 * No result counts, no pagination, no "see all results", no filter UI, no tabs, no AI-answer
 * block.  Those are all deliberate exclusions, not omissions.
 *
 * ⚠ The palette input is the one control in this product with no visible label, against the
 * product-wide "labels always visible" rule.  It carries an `aria-label`, and **the exception
 * stops at this component.**
 */
export function SearchPalette({
  open,
  onOpenChange,
  query,
  onQueryChange,
  results,
  recent,
  scopeLabel,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  query: string
  onQueryChange: (q: string) => void
  results: SearchResult[]
  recent: RecentSearch[]
  /** "Jaipur DC only" -- states the scope, is not a filter control. */
  scopeLabel: string
}) {
  const [highlight, setHighlight] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const grouped = useMemo(() => {
    return GROUP_ORDER.map((g) => ({ group: g, items: results.filter((r) => r.group === g) })).filter(
      (g) => g.items.length > 0,
    )
  }, [results])

  const flat = useMemo(() => grouped.flatMap((g) => g.items), [grouped])

  useEffect(() => setHighlight(0), [query])

  const showRecent = query.trim() === ''
  const showEmpty = !showRecent && flat.length === 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        // Offset from the top, not centred.  The 15% is from prompt 6.
        className="top-[15%] w-full max-w-160 translate-y-0 gap-0 overflow-hidden rounded-xl border-transparent bg-overlay p-0 shadow-overlay dark:border-input"
      >
        <DialogTitle className="sr-only">Search</DialogTitle>

        <div className="flex h-14 items-center gap-3 px-4">
          <Search className="size-6 shrink-0 text-subtle-foreground" aria-hidden="true" />
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            onKeyDown={(e) => {
              // Typing never moves focus out of the input -- the HIGHLIGHT moves, focus does
              // not.  Arrow keys cross group boundaries and skip headers, which is why the
              // flattened list exists.
              if (e.key === 'ArrowDown') {
                e.preventDefault()
                setHighlight((h) => Math.min(h + 1, Math.max(flat.length - 1, 0)))
              } else if (e.key === 'ArrowUp') {
                e.preventDefault()
                setHighlight((h) => Math.max(h - 1, 0))
              } else if (e.key === 'Enter' && flat[highlight]) {
                window.location.assign(flat[highlight].href)
              }
            }}
            autoComplete="off"
            spellCheck={false}
            placeholder="Search shipments, appointments, drivers, carriers, facilities"
            aria-label="Search shipments, appointments, drivers, carriers, facilities"
            className="min-w-0 flex-1 border-0 bg-transparent p-0 text-body-lg text-foreground outline-none placeholder:text-subtle-foreground"
          />
          <kbd className="rounded-sm border border-input bg-card px-2 py-1 font-mono text-[11px] leading-none font-medium text-subtle-foreground">
            Esc
          </kbd>
        </div>

        <div className="px-4 pb-3 text-label tracking-normal text-subtle-foreground normal-case">
          {scopeLabel}
        </div>
        <hr className="h-px border-0 bg-border" />

        {showEmpty ? (
          <EmptyState
            icon={SearchX}
            title={`No shipment matches ‘${query}’.`}
            body={`Try a shipment number, a dock code, or a driver’s name. Search covers ${scopeLabel.replace(/ only$/, '')} only.`}
            actions={
              <button
                type="button"
                onClick={() => onQueryChange('')}
                className="text-body text-link underline underline-offset-2 hover:text-primary-hover"
              >
                Clear search
              </button>
            }
          />
        ) : (
          <div className="max-h-100 overflow-y-auto overscroll-contain pb-2">
            {showRecent ? (
              <>
                <GroupHeader>Recent</GroupHeader>
                {recent.map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => onQueryChange(r.query)}
                    className={rowClass(false)}
                  >
                    <Clock className="size-4 shrink-0 text-subtle-foreground" aria-hidden="true" />
                    <span className="min-w-0 truncate text-supporting text-muted-foreground">
                      {r.query}
                    </span>
                  </button>
                ))}
              </>
            ) : (
              grouped.map((g) => (
                <Fragment key={g.group}>
                  <GroupHeader>{g.group}</GroupHeader>
                  {g.items.map((item) => {
                    const idx = flat.indexOf(item)
                    const active = idx === highlight
                    return (
                      <a
                        key={item.id}
                        href={item.href}
                        aria-current={active || undefined}
                        onMouseEnter={() => setHighlight(idx)}
                        className={rowClass(active)}
                      >
                        <span className="min-w-22 shrink-0 font-mono text-body font-medium text-foreground" translate="no">
                          {item.identifier}
                        </span>
                        <span className="min-w-0 truncate text-supporting text-muted-foreground">
                          {highlightMatch(item.meta, query)}
                        </span>
                      </a>
                    )
                  })}
                </Fragment>
              ))
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function GroupHeader({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-4 pt-3 pb-1 text-label uppercase text-subtle-foreground">{children}</div>
  )
}

function rowClass(active: boolean) {
  return cn(
    'flex min-h-11 w-full items-center gap-3 border-l-2 px-4 py-2.5 text-left no-underline',
    'transition-colors duration-(--d-fast) ease-(--e-out)',
    'focus-visible:outline-2 focus-visible:outline-ring focus-visible:-outline-offset-2',
    active ? 'border-l-primary bg-selected' : 'border-l-transparent hover:bg-hover',
  )
}

/** Matched substrings are marked by WEIGHT, not a coloured background -- a coloured
 *  highlight would make a match look like a promise state. */
function highlightMatch(text: string, query: string) {
  const q = query.trim()
  if (!q) return text
  const idx = text.toLowerCase().indexOf(q.toLowerCase())
  if (idx === -1) return text
  return (
    <>
      {text.slice(0, idx)}
      <b className="font-semibold text-foreground">{text.slice(idx, idx + q.length)}</b>
      {text.slice(idx + q.length)}
    </>
  )
}
