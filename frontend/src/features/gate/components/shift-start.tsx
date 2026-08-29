import { useId, useState } from 'react'

import { KioskField } from './kiosk-field'
import { PrimaryAction } from './primary-action'
import { facilityDisplayName } from '../lib/facility-names'

/**
 * Screens 1 and 2 -- Flow 0, U111. **The same component on both device contexts**: same copy, same
 * anatomy, different placement only (U108's "the split is layout, not a different tool contract").
 * The caller positions it; nothing device-specific lives in here.
 *
 * **Attribution, not authentication.** No password, no email, no SSO, no account creation --
 * `components.md` section 1 is explicit that this is a shared-device attribution mechanism and that
 * actual device-level access control is a facility/IT concern outside this surface. Facility is
 * fixed to the device's own assignment and renders as plain text, never a switcher: a kiosk is
 * physically installed at one facility and has no reason to offer one.
 *
 * **Local device state, not a server write** (`edge-cases.md` #7) -- so it stays usable through a
 * connectivity drop, and there is no Inactive/offline treatment on this button at all, unlike every
 * other primary action on the surface.
 *
 * The empty-name button uses the `inert` tier rather than Inactive. That is
 * `implementation-spec.md` Fork B, taken as recommended (a), and it is a genuine judgement call
 * flagged in the build report rather than settled here -- section 18's rule names this surface by
 * name, but its own worked example is a control that *changed while being looked at*, which an
 * empty required field is not: the helper text beside it already states the reason without a press,
 * so activating it would reveal nothing new.
 */
export function ShiftStart({
  facilityId,
  onStart,
}: {
  facilityId: string
  onStart: (officerName: string) => void
}) {
  const [name, setName] = useState('')
  const hintId = useId()
  const ready = name.trim() !== ''

  return (
    <div className="flex flex-col gap-4 rounded-lg border border-border bg-card p-6 shadow-raised">
      <p className="text-h2" translate="no">
        SetuHaul · Gate/Yard
      </p>
      <h1 className="text-h1 text-balance">Start shift</h1>

      <KioskField
        label="Officer name"
        variant="name"
        value={name}
        onChange={setName}
        onSubmit={() => ready && onStart(name)}
        helper={ready ? undefined : 'Enter your name to start'}
        helperId={hintId}
      />

      <p className="text-body-lg">Facility: {facilityDisplayName(facilityId)} (fixed)</p>

      {ready ? (
        <PrimaryAction label="Start shift" onClick={() => onStart(name)} />
      ) : (
        <PrimaryAction label="Start shift" state="inert" reasonId={hintId} />
      )}
    </div>
  )
}
