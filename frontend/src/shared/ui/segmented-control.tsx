import { useId, useRef } from 'react'

import { cn } from '@/shared/lib/utils'

export type Segment<T extends string> = { value: T; label: string }

/**
 * components.md section 12.
 *
 * For switching between 2-4 mutually exclusive VIEWS of the same data.  Not a form field's
 * value (that's radio, which supports more options and per-option help), and not navigation
 * between destinations (that's tabs).
 *
 * Two corrections locked 2026-08-26, both internal contradictions rather than preferences:
 *
 *  1. **4px inset, not 2px.** 2px is not a multiple of the 4px base unit, which
 *     spacing-and-layout.md's opening line forbids without exception.  radius-sm segments
 *     inside a radius-md container get the same non-colliding corners on the grid.
 *
 *  2. **Unselected hover is a text-colour change, not a `surface-hover` fill.**  The fill
 *     was literally unimplementable: the container is `surface-sunken`, and sunken and hover
 *     are the SAME value in light mode (neutral-100), so the specified hover was invisible.
 *
 * The container's mandatory 1px border is what keeps the track legible in dark, where
 * surface-sunken matches the page (color.md's sunken rule).
 *
 * ARIA: a real radiogroup with roving tabindex.  Never a bare set of buttons sharing a
 * visual style -- a sighted user reads the selected fill as a state; a screen-reader user
 * needs the same fact asserted, not implied.
 */
export function SegmentedControl<T extends string>({
  segments,
  value,
  onValueChange,
  label,
  labelledBy,
  className,
}: {
  segments: readonly Segment<T>[]
  value: T
  onValueChange: (next: T) => void
  label?: string
  labelledBy?: string
  className?: string
}) {
  const groupId = useId()
  const refs = useRef<(HTMLButtonElement | null)[]>([])

  const move = (from: number, delta: number) => {
    const next = (from + delta + segments.length) % segments.length
    onValueChange(segments[next].value)
    refs.current[next]?.focus()
  }

  return (
    <div
      role="radiogroup"
      aria-label={labelledBy ? undefined : label}
      aria-labelledby={labelledBy}
      id={groupId}
      className={cn(
        'flex gap-1 rounded-md border border-border bg-sunken p-1',
        className,
      )}
    >
      {segments.map((seg, i) => {
        const selected = seg.value === value
        return (
          <button
            key={seg.value}
            ref={(el) => {
              refs.current[i] = el
            }}
            type="button"
            role="radio"
            aria-checked={selected}
            // Roving tabindex, so arrow keys move selection the way a native radio group does
            tabIndex={selected ? 0 : -1}
            onClick={() => onValueChange(seg.value)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
                e.preventDefault()
                move(i, 1)
              } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                e.preventDefault()
                move(i, -1)
              }
            }}
            className={cn(
              'h-8 flex-1 rounded-sm px-2 text-supporting transition-colors duration-(--d-fast) ease-(--e-out)',
              'outline-none focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2',
              selected
                ? 'bg-card text-foreground font-semibold shadow-raised'
                : 'bg-transparent text-muted-foreground font-medium hover:text-foreground',
            )}
          >
            {seg.label}
          </button>
        )
      })}
    </div>
  )
}
