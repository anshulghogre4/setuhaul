import { Search } from 'lucide-react'
import { useId, type ReactNode } from 'react'

import { cn } from '@/shared/lib/utils'

/**
 * The filter/search bar every table tab carries (`mockup.html` §2.1, §5, §11.1).
 *
 * **Native `<select>` and `<input type="search">`, not the mockup's `.pill` button + floating
 * `.menu` pattern.** This follows E5.3's Fork G resolution verbatim — the mockup depicts a
 * pop-up menu because a static HTML reference cannot depict a native select's own dropdown, not
 * because a custom listbox was specified. A native control gets keyboard behaviour, mobile
 * pickers, forced-colors support and `<label>` association for free, and every one of those was
 * something the custom pattern would have had to re-implement. Stated here so the divergence from
 * the artboard is on the record rather than discovered later.
 */

export function Toolbar({ children }: { children: ReactNode }) {
  return <div className="mb-4 flex flex-wrap items-end gap-3">{children}</div>
}

/** Pushes everything after it to the right edge of the toolbar (`mockup.html` §5's flex spacer). */
export function ToolbarSpacer() {
  return <span className="flex-1" aria-hidden="true" />
}

export function FilterSelect({
  label,
  value,
  onChange,
  options,
  allLabel,
  className,
}: {
  label: string
  value: string | null
  onChange: (value: string | null) => void
  options: Array<{ value: string; label: string }>
  /** The "no filter" option's wording, e.g. "All roles". Never a bare blank entry. */
  allLabel: string
  className?: string
}) {
  const id = useId()
  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <label htmlFor={id} className="text-label text-muted-foreground uppercase tracking-wide">
        {label}
      </label>
      <select
        id={id}
        value={value ?? ''}
        onChange={(e) => onChange(e.currentTarget.value === '' ? null : e.currentTarget.value)}
        className="h-(--btn-h) min-w-40 rounded-md border border-input bg-card px-3 text-body text-foreground outline-none transition-colors duration-(--d-fast) hover:border-strong focus-visible:border-ring focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2"
      >
        <option value="">{allLabel}</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  )
}

/**
 * The search field.
 *
 * The visible label is `sr-only` and the icon is decorative, matching `mockup.html` §2.1's own
 * `<span class="vh">Search users</span>` — the field is never left to a placeholder alone, which
 * disappears on input and is not an accessible name.
 *
 * `implementation-spec.md` §5.3's R24: the mockup's `.srch input{outline:none}` had no focus
 * replacement until that pass added `.srch:focus-within`. The same treatment is applied here via
 * `focus-within:` on the wrapper, so the 40px row shows the ring rather than the 18px input alone
 * — which is also what makes the whole row the real hit area (R7/§5.3's retracted tap-target
 * readings).
 */
export function SearchField({
  label,
  value,
  onChange,
  placeholder = 'Search',
}: {
  label: string
  value: string
  onChange: (value: string) => void
  placeholder?: string
}) {
  const id = useId()
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <div className="flex h-(--btn-h) items-center gap-2 rounded-md border border-input bg-card px-3 transition-colors duration-(--d-fast) hover:border-strong focus-within:border-ring focus-within:outline-2 focus-within:outline-ring focus-within:outline-offset-2">
        <Search className="size-4 shrink-0 text-subtle-foreground" aria-hidden="true" />
        <input
          id={id}
          type="search"
          value={value}
          placeholder={placeholder}
          autoComplete="off"
          spellCheck={false}
          onChange={(e) => onChange(e.currentTarget.value)}
          className="h-full w-48 min-w-0 bg-transparent text-body text-foreground outline-none placeholder:text-subtle-foreground"
        />
      </div>
    </div>
  )
}
