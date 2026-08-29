import { useId } from 'react'

import { Input } from '@/shared/ui/input'
import { cn } from '@/shared/lib/utils'
import { TOUCH_CLASS } from '../lib/touch'

/**
 * The two text inputs this surface has, and the only two it will ever have
 * (`accessibility.md`: "text entry is minimized to exactly one field... the shift-identity name
 * field is the only other text input, entered once per shift, not per truck").
 *
 * Built on the shared `Input` rather than a bespoke element, so the focus, hover and
 * `aria-invalid` treatments stay the design system's. Three overrides, each with a reason:
 *   `h-auto min-h-(--tap)` -- the shared control is a fixed 44px; `spacious` density's floor is
 *     56px and `accessibility.md` is explicit that 44px is not generous enough for gloves.
 *   `px-5` -- `spacious`'s own 20px cell padding, against the shared 12px.
 *   the type step -- 24px mono for the lookup field, 20px UI for the officer name, both at weight
 *     400. `text-h1`/`text-h2` carry a semibold weight and a negative tracking in `theme.css`, so
 *     both are explicitly reset; without that the field renders as a heading, not an input.
 *
 * **Label always visible, never a placeholder standing in for one.** There is no placeholder text
 * anywhere on this surface -- the stricter pattern, and the one the mockup uses.
 *
 * **`inputmode="text"`, explicitly** -- `implementation-spec.md` Fork D taken as recommended (b).
 * `components.md` section 2 asks for a "numeric-friendly keyboard by default", but both real values
 * (`SHP1015`, `RJ14 GH 2211`) are alphanumeric and `inputmode="numeric"` would lock the letters out
 * and make a genuine plate unenterable. There is no `inputmode` value for "alphanumeric code", so
 * this states the decision was made rather than overlooked.
 */
export function KioskField({
  label,
  value,
  onChange,
  onSubmit,
  variant,
  helper,
  helperId,
  inputRef,
  invalid,
  describedBy,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  /** Enter submits. `enterkeyhint` below promises the on-screen keyboard's action key does
   *  something, so it has to. */
  onSubmit?: () => void
  /** `lookup` is the shipment-id/plate field; `name` is the once-per-shift officer field. */
  variant: 'lookup' | 'name'
  helper?: string
  helperId?: string
  inputRef?: React.Ref<HTMLInputElement>
  invalid?: boolean
  describedBy?: string
}) {
  const autoId = useId()
  const id = `gate-field-${autoId}`
  const isLookup = variant === 'lookup'

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-body-lg font-semibold text-foreground">
        {label}
      </label>
      <Input
        id={id}
        ref={inputRef}
        name={isLookup ? 'truck_lookup' : 'officer_name'}
        type="text"
        inputMode="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && onSubmit) {
            e.preventDefault()
            onSubmit()
          }
        }}
        aria-invalid={invalid || undefined}
        aria-describedby={describedBy}
        // An autofill dropdown over a 56px field is a gloved-mis-tap hazard and neither field is an
        // auth field; the codes are not words, so red squiggles under them are noise outdoors.
        autoComplete="off"
        spellCheck={false}
        // Both lookup values are uppercase codes and autocorrect actively corrupts them. React
        // passes unknown lowercase DOM attributes through, which is why `autocorrect` is spelled
        // that way -- there is no camelCase React prop for it.
        {...(isLookup ? { autoCapitalize: 'characters', autoCorrect: 'off' } : {})}
        enterKeyHint={isLookup ? 'search' : 'go'}
        className={cn(
          'h-auto min-h-(--tap) px-5',
          TOUCH_CLASS,
          isLookup
            ? 'font-mono text-h1 font-normal tabular-nums tracking-[0.01em]'
            : 'font-sans text-h2 font-normal tracking-normal',
        )}
      />
      {helper ? (
        <p id={helperId} className="text-body-lg text-foreground">
          {helper}
        </p>
      ) : null}
    </div>
  )
}
