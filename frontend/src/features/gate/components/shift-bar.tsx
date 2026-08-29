import { ArrowLeft } from 'lucide-react'

import { cn } from '@/shared/lib/utils'
import { facilityDisplayName } from '../lib/facility-names'
import { deviceLabel, type DeviceContext } from '../lib/device'
import { TOUCH_CLASS } from '../lib/touch'

/**
 * The shift bar (`mockup.html` `.shiftbar`, on every screen from 3 onward).
 *
 * **Plain text on the page background with a 1px rule -- not an app bar.** This surface has no
 * shell at all: no icon rail, no top bar, no status bar, no facility switcher, and therefore no
 * facility accent colour anywhere (U59/U40 confine that palette to the rail stripe and the
 * switcher swatch, neither of which exists on a kiosk). Verified against the mockup, which returns
 * null for `nav, .rail, [aria-label="Profile"]` across all 35 artboards.
 *
 * Both controls are `link-ctl`: de-emphasised by type style, position and the absence of button
 * chrome -- **never by fading**, because fading is what glare destroys first. Both still meet the
 * 56px target, which is why they are `min-h-(--tap) min-w-(--tap)` and not text links.
 *
 * `officerName` is local device state and is never transmitted anywhere -- issue #68 (GY-G2). The
 * bar displays it exactly as U111 specifies; the server-side stamping U111 also promises does not
 * exist. See `lib/session.ts`.
 */
export function ShiftBar({
  device,
  facilityId,
  officerName,
  onBack,
  onEndShift,
}: {
  device: DeviceContext
  facilityId: string
  officerName: string
  /** Omitted on the search screen and on outcome screens -- `mockup.html` renders the back
   *  control only where there is a truck context to go back FROM (screens 6-12, 22b). */
  onBack?: () => void
  onEndShift: () => void
}) {
  return (
    <div
      className={cn(
        'flex min-h-(--row-h) shrink-0 items-center gap-6',
        'mb-8 border-b border-border',
      )}
    >
      {onBack ? (
        <LinkControl onClick={onBack}>
          <ArrowLeft className="size-5" aria-hidden="true" />
          Search
        </LinkControl>
      ) : null}
      <span className="text-body-lg font-medium text-muted-foreground">
        {deviceLabel(device)} · {facilityDisplayName(facilityId)} · Shift: {officerName}
      </span>
      <span className="ml-auto flex items-center">
        <LinkControl onClick={onEndShift}>End shift</LinkControl>
      </span>
    </div>
  )
}

/**
 * `mockup.html` `.link-ctl`. Exported because the outcome screens' "Back to search" is the same
 * control, and duplicating the 56px/no-chrome rules is how one of them drifts.
 */
export function LinkControl({
  children,
  onClick,
}: {
  children: React.ReactNode
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex min-h-(--tap) min-w-(--tap) items-center gap-2 rounded-md px-4',
        'text-body-lg font-semibold text-muted-foreground',
        TOUCH_CLASS,
        'transition-colors duration-(--d-fast) ease-(--e-out) hover:bg-hover',
        'outline-none focus-visible:outline-2 focus-visible:outline-ring focus-visible:outline-offset-2',
      )}
    >
      {children}
    </button>
  )
}
