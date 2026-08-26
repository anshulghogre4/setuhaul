import { useId, useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'

import { Input } from '@/shared/ui/input'
import { Label } from '@/shared/ui/label'
import { cn } from '@/shared/lib/utils'

/**
 * Password field with an inset show/hide toggle.
 *
 * The toggle is a **button with `aria-pressed`, not a checkbox**, and its accessible name
 * flips between "Show password" and "Hide password" (prompt 1).  It never sits outside the
 * field as a separate labelled control and it never covers typed characters -- the input
 * reserves 40px of right padding for it.
 *
 * The focus ring on the toggle is the same 2px/2px-offset ring every other control gets --
 * not a subtler treatment because it is small.
 *
 * Password managers must work: correct `autocomplete`, and no paste blocking anywhere in
 * this flow (auth-and-scoping.md).  There is no `onPaste` handler here on purpose.
 */
export function PasswordField({
  label,
  name,
  autoComplete = 'current-password',
  defaultValue,
  value,
  onChange,
  invalid,
  describedBy,
  error,
}: {
  label: string
  name: string
  autoComplete?: 'current-password' | 'new-password'
  defaultValue?: string
  value?: string
  onChange?: (v: string) => void
  invalid?: boolean
  describedBy?: string
  error?: string
}) {
  const [revealed, setRevealed] = useState(false)
  const fieldId = useId()
  const errorId = `${fieldId}-error`
  const Icon = revealed ? EyeOff : Eye

  return (
    <div>
      <Label htmlFor={fieldId} className="mb-2 block text-supporting font-medium text-muted-foreground">
        {label}
      </Label>
      <div className="relative">
        <Input
          id={fieldId}
          name={name}
          type={revealed ? 'text' : 'password'}
          autoComplete={autoComplete}
          spellCheck={false}
          defaultValue={defaultValue}
          value={value}
          onChange={onChange ? (e) => onChange(e.target.value) : undefined}
          aria-invalid={invalid || undefined}
          aria-describedby={cn(error ? errorId : undefined, describedBy) || undefined}
          className="pr-10"
        />
        <button
          type="button"
          aria-pressed={revealed}
          aria-label={revealed ? 'Hide password' : 'Show password'}
          onClick={() => setRevealed((r) => !r)}
          className={cn(
            'absolute inset-y-0 right-0 grid w-10 place-items-center rounded-md',
            'text-muted-foreground transition-colors duration-(--d-fast) ease-(--e-out) hover:text-foreground',
            'outline-none focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2',
          )}
        >
          <Icon className="size-5" aria-hidden="true" />
        </button>
      </div>
      {error ? (
        <span id={errorId} className="mt-2 flex items-start gap-2 text-supporting text-danger-fg">
          {error}
        </span>
      ) : null}
    </div>
  )
}
