import { useEffect, useState } from 'react'

import { DisambiguationList } from './components/disambiguation-list'
import { OutcomeScreen } from './components/outcome-screen'
import { SearchPanel } from './components/search-panel'
import { ShiftBar } from './components/shift-bar'
import { ShiftStart } from './components/shift-start'
import { TruckAction } from './components/truck-action'
import { currentDeviceContext, watchDeviceContext, type DeviceContext } from './lib/device'
import { endShift, loadShiftSession, startShift } from './lib/session'
import type { GateEventResult, GateTruckMatch } from './lib/types'

/**
 * The gate/yard kiosk route root (E5.4, issue #39).
 *
 * ## No `<AppShell>`, and that is the design, not an omission
 *
 * `stitch-prompts.md` and `mockup.html` both state it and the rendered board proves it: **no icon
 * rail, no top bar, no status bar, no facility switcher**, and therefore no facility accent colour
 * anywhere (U59/U40 confine that palette to the rail stripe and the switcher swatch, neither of
 * which exists on a kiosk). There is also **no idle timeout** on this surface, so no session-expiry
 * affordance renders. Mounting `AppShell` here would render chrome for a device the design
 * explicitly strips it from -- the same call `DriverShell` makes, for a different reason.
 *
 * **Consequence for `App.tsx`:** this route must NOT be wrapped in `ShellRoute`. `/gate` currently
 * is (E5.0's placeholder), and leaving that wrapper in place would put a rail and a facility
 * switcher on a gate booth.
 *
 * ## Density, set once
 *
 * `data-density="spacious"` at the route root -- `--tap: 56px`, `--row-h: 64px`, `--btn-h: 56px`,
 * `--content-p: 32px`. This is the only surface in the product that uses `spacious`, and it is
 * physical rather than aesthetic: a gloved fingertip's contact area is larger than a bare one, so
 * the 44px AAA floor used on the driver PWA is not generous enough (`accessibility.md`). Set once
 * at the root, never per component (U8).
 *
 * ## What ships and what does not
 *
 * All 22 screens are built and wired against live endpoints: `SearchPanel` against
 * `GET /api/v1/gate/trucks` (issue #67, shipped concurrently with this build) and `TruckAction` /
 * `OutcomeScreen` against the five `/api/v1/gate/*` writes E3.6 shipped. `gateSearchEnabled` is the
 * one switch between the full flow and an honest stub at the search field; it is now on, and
 * `lib/flags.ts` records both why it existed and exactly what about it is and is not verified.
 * `/gate/_states` renders every screen from labelled fixtures.
 */
export function GateKiosk({ facilityId }: { facilityId: string }) {
  const [device, setDevice] = useState<DeviceContext>(currentDeviceContext)
  const [officerName, setOfficerName] = useState<string | null>(
    () => loadShiftSession()?.officerName ?? null,
  )
  const [phase, setPhase] = useState<Phase>({ kind: 'search' })

  useEffect(() => watchDeviceContext(setDevice), [])

  // Flow 9. No confirmation modal -- ending a shift has no destructive consequence, and this
  // surface uses no confirmation modals at all (U41 taken to its stated logical extreme here).
  function handleEndShift() {
    endShift()
    setOfficerName(null)
    setPhase({ kind: 'search' })
  }

  if (officerName === null) {
    return (
      <KioskFrame device={device}>
        {/* U108: the card sits vertically centred on the mounted landscape booth and roughly 25%
            down the portrait tablet, so the button falls in a one-handed thumb arc on a device
            gripped at the bottom. The bottom third stays empty rather than being stretched into. */}
        <div
          className={
            device === 'yard-tablet'
              ? 'flex flex-1 flex-col pt-[288px]'
              : 'flex flex-1 items-center justify-center'
          }
        >
          <div className={device === 'yard-tablet' ? 'w-full' : 'w-[560px]'}>
            <ShiftStart
              facilityId={facilityId}
              onStart={(name) => {
                startShift(name)
                setOfficerName(name.trim())
              }}
            />
          </div>
        </div>
      </KioskFrame>
    )
  }

  return (
    <KioskFrame device={device}>
      <ShiftBar
        device={device}
        facilityId={facilityId}
        officerName={officerName}
        onBack={phase.kind === 'truck' ? () => setPhase({ kind: 'search' }) : undefined}
        onEndShift={handleEndShift}
      />
      <KioskBody device={device}>
        {phase.kind === 'search' ? (
          <SearchPanel
            onFound={(truck) => setPhase({ kind: 'truck', truck })}
            onDisambiguate={(query, matches) => setPhase({ kind: 'disambiguate', query, matches })}
          />
        ) : null}

        {phase.kind === 'disambiguate' ? (
          <DisambiguationList
            query={phase.query}
            matches={phase.matches}
            onPick={(truck) => setPhase({ kind: 'truck', truck })}
          />
        ) : null}

        {phase.kind === 'truck' ? (
          <TruckAction
            truck={phase.truck}
            // U111 / issue #68: this component owns the shift session, so it is where the officer
            // label enters the write path. It is non-null here only because this branch renders
            // below the `officerName === null` early return above -- `TruckAction` still accepts
            // null, because a device whose shift ended between render and tap must still record.
            officerName={officerName}
            onOutcome={(result) => setPhase({ kind: 'outcome', result, truck: phase.truck })}
          />
        ) : null}

        {phase.kind === 'outcome' ? (
          <OutcomeScreen
            result={phase.result}
            truck={phase.truck}
            // edge-cases.md #3: INVALID_TRANSITION has no button and resolves on its own -- the
            // surface re-fetches the truck's real state and re-renders Flow 2 rather than retrying
            // the rejected transition. That re-fetch is the search tool (#67), so today the honest
            // behaviour is to return to the search field, which is where a re-fetch would start
            // from anyway. Flow 8's "Search next truck" is the same destination for every other
            // outcome, which is why one handler covers both.
            onNext={
              phase.result.code === 'INVALID_TRANSITION'
                ? null
                : () => setPhase({ kind: 'search' })
            }
          />
        ) : null}
      </KioskBody>
    </KioskFrame>
  )
}

/**
 * Flow 1 -> 2 -> 8 -> 1, and nothing else. There is no list, no dashboard, no history and no
 * settings beyond shift start -- `screens.md`: "the entire surface is this loop, repeated once per
 * truck", the literal interpretation of U26 rather than a simplification of something bigger. A
 * discriminated union rather than four booleans, so two phases cannot both be true.
 */
type Phase =
  | { kind: 'search' }
  | { kind: 'disambiguate'; query: string; matches: GateTruckMatch[] }
  | { kind: 'truck'; truck: GateTruckMatch }
  | { kind: 'outcome'; result: GateEventResult; truck: GateTruckMatch }

/** The device frame: density, theme surface, and the 32px safe area the mockup's `.safe` sets.
 *  Nothing interactive comes within 16px of a viewport edge; the protective case eats the bezel,
 *  so 24px is the minimum and `--content-p` (32px) clears it. */
function KioskFrame({ device, children }: { device: DeviceContext; children: React.ReactNode }) {
  return (
    <div
      data-density="spacious"
      data-surface="gate"
      data-device={device}
      className="flex h-dvh min-h-0 flex-col bg-background p-(--content-p) text-foreground"
    >
      {children}
    </div>
  )
}

/**
 * Where the card sits under the shift bar, per device.
 *
 * Landscape booth: centred in the space left over. The 800px-tall frame is deliberately not filled
 * -- the card is ~720px wide and the surrounding whitespace is the design, not a gap to close.
 *
 * Portrait tablet: pushed down by a flexible spacer with a fixed 200px pad below, so the primary
 * button lands in the one-handed thumb arc and never flush to the bottom edge. Measured across the
 * mockup's own 22 yard frames as a 490-759px card-top band.
 */
function KioskBody({ device, children }: { device: DeviceContext; children: React.ReactNode }) {
  if (device === 'gate-booth') {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="w-[720px] rounded-lg border border-border bg-card p-6 shadow-raised">
          {children}
        </div>
      </div>
    )
  }
  return (
    <div className="flex flex-1 flex-col">
      <div className="min-h-4 flex-1" />
      <div className="w-full rounded-lg border border-border bg-card p-6 shadow-raised">
        {children}
      </div>
      <div className="h-[200px] shrink-0" />
    </div>
  )
}
