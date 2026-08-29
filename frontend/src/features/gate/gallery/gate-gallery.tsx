import type { ReactNode } from 'react'
import { TriangleAlert } from 'lucide-react'

import { DisambiguationList } from '../components/disambiguation-list'
import { KioskField } from '../components/kiosk-field'
import { OutcomeScreen } from '../components/outcome-screen'
import { PrimaryAction } from '../components/primary-action'
import { OutcomeBlock, OutcomeFact } from '../components/outcome-block'
import { SearchPanel } from '../components/search-panel'
import { ShiftBar } from '../components/shift-bar'
import { ShiftStart } from '../components/shift-start'
import { ButtonVoid, TruckIdentityCard } from '../components/truck-identity-card'
import * as fx from './fixtures'
import type { GateTruckMatch } from '../lib/types'
import { actionFor } from '../lib/queue-states'

/**
 * All 22 gate/yard screens, rendered by the **built components** at true device width.
 * Route `/gate/_states`, not linked from the app. Same purpose as `/ops/_states`,
 * `/planner/_states` and `/driver/_states`: "it type-checks" is not "it has been seen rendering",
 * and on this surface most screens are reachable in the app only by searching a real truck at a
 * real facility, which this page does not require.
 *
 * **Every truck and every outcome on this page is a fixture, and the plates say so.** Nothing here
 * reaches `/gate`, which shows an honest "not available yet" at the search field instead. The
 * fixture values are copied from `mockup.html`'s own artboards so the two are comparable side by
 * side rather than being two differently-wrong sets of numbers.
 *
 * Every screen is rendered rather than replaced with a note -- deliberately different from
 * `/planner/_states`, and for a reason specific to this surface: on the planner board the blocked
 * screens had **no backend at all** and rendering them would have meant inventing a queue. Here
 * every tool behind every screen is shipped, so a plate driven by a labelled fixture is an honest
 * picture of a real path rather than a mock-up of an imaginary one.
 */
export function GateStatesGallery() {
  return (
    <div className="min-h-dvh bg-background p-6 text-foreground" data-density="spacious">
      <header className="mb-8">
        {/* `text-body` (14px), not the `text-label` (12px) the other galleries use. Caught by
            measuring this page rather than by reading it: `typography.md`'s floor for the gate and
            driver surfaces is 14px, and `mockup.html` deliberately holds its OWN gallery chrome to
            the same floor ("so nothing in this file renders below it") rather than exempting the
            documentation around the artboards. Followed here for the same reason. */}
        <p className="text-body font-semibold tracking-[0.04em] text-primary uppercase">
          SetuHaul · gate/yard kiosk (E5.4)
        </p>
        <h1 className="mt-2 text-display text-balance">
          All 22 screens, rendered by the built components
        </h1>
        <p className="mt-2 max-w-[80ch] text-body text-muted-foreground">
          The five section 7.5.2 write tools and the Flow 1 search (issue #67) are all shipped, and
          the components below are the same ones that call them. Every truck and outcome on this
          page is a fixture, so no plate here can reach the backend; `/gate` itself renders none of
          them.
        </p>
      </header>

      <div className="flex flex-col gap-10">
        <Plate n="1" title="Shift start — gate booth (1280×800, card 560px, vertically centred)">
          <GateFrame>
            <div className="flex flex-1 items-center justify-center">
              <div className="w-[560px]">
                <ShiftStart facilityId="FAC-JAI-01" onStart={() => {}} />
              </div>
            </div>
          </GateFrame>
        </Plate>

        <Plate n="2" title="Shift start — yard tablet (800×1280, full width, ~25% down)">
          <YardFrame>
            <div className="flex flex-1 flex-col pt-[288px]">
              <ShiftStart facilityId="FAC-JAI-01" onStart={() => {}} />
            </div>
          </YardFrame>
        </Plate>

        <Plate
          n="3"
          title="Search — the live entry point (flag on; the honest stub renders here when it is off)"
        >
          <GateFrame>
            <ShiftBar
              device="gate-booth"
              facilityId="FAC-JAI-01"
              officerName="Ramesh K."
              onEndShift={() => {}}
            />
            <GateCard>
              <SearchPanel onFound={() => {}} onDisambiguate={() => {}} />
            </GateCard>
          </GateFrame>
        </Plate>

        {/*
          Screens 3b and 4, composed from the same primitives `SearchPanel` uses.

          Composed here rather than driven through `SearchPanel` itself because both states need a
          backend response to reach -- a typed-but-unsubmitted value and a real `NO_MATCH` -- and a
          gallery must never issue a live request. The trade-off is stated rather than hidden: these
          two plates show `KioskField` + `PrimaryAction` + `OutcomeBlock` for real, but not
          `SearchPanel`'s own state machine, which only a live search exercises.
        */}
        <Plate n="3b" title="Search — a typed value, before submit">
          <GateFrame>
            <ShiftBar device="gate-booth" facilityId="FAC-JAI-01" officerName="Ramesh K." onEndShift={() => {}} />
            <GateCard>
              <div className="flex flex-col gap-4">
                <h2 className="text-h1 text-balance">Search</h2>
                <KioskField
                  label="Shipment ID or plate number"
                  variant="lookup"
                  value="SHP1015"
                  onChange={() => {}}
                />
                <PrimaryAction label="Search" />
              </div>
            </GateCard>
          </GateFrame>
        </Plate>

        <Plate n="4" title="Search — no match: named cause below the field, nothing above it shifts">
          <YardFrame>
            <ShiftBar device="yard-tablet" facilityId="FAC-JAI-01" officerName="Priya S." onEndShift={() => {}} />
            <YardCard>
              <div className="flex flex-col gap-4">
                <h2 className="text-h1 text-balance">Search</h2>
                {/* SHP1O15 -- a letter O for a zero, the realistic mistype, which is what makes the
                    mono typeface earn its place. The field keeps its failed value. */}
                <KioskField
                  label="Shipment ID or plate number"
                  variant="lookup"
                  value="SHP1O15"
                  onChange={() => {}}
                  invalid
                />
                <OutcomeBlock
                  tone="danger"
                  live="alert"
                  icon={TriangleAlert}
                  headline="No shipment matches that ID or plate."
                  align="inline"
                >
                  <OutcomeFact>Check the number and try again.</OutcomeFact>
                </OutcomeBlock>
                <PrimaryAction label="Try again" />
              </div>
            </YardCard>
          </YardFrame>
        </Plate>

        <Plate n="5" title="Search — multiple matches (rows, never a dropdown; whole row is the target)">
          <YardFrame>
            <ShiftBar
              device="yard-tablet"
              facilityId="FAC-JAI-01"
              officerName="Priya S."
              onEndShift={() => {}}
            />
            <YardCard>
              <DisambiguationList
                query="RJ14 GH 2211"
                matches={fx.DISAMBIGUATION_MATCHES}
                onPick={() => {}}
              />
            </YardCard>
          </YardFrame>
        </Plate>

        <TruckPlate n="6" title="NOT_QUEUED → Gate in (no state row at all — absence is the signal)" device="gate" truck={fx.TRUCK_NOT_QUEUED} officer="Ramesh K." />
        <TruckPlate n="7a" title="WAITING_LATE → Call to dock" device="yard" truck={fx.TRUCK_WAITING_LATE} officer="Priya S." />
        <TruckPlate n="7b" title="WAITING_EARLY → Call to dock (same label, same action)" device="yard" truck={fx.TRUCK_WAITING_EARLY} officer="Priya S." />
        <TruckPlate n="8" title="WAITING_DOCK_UNAVAILABLE → Call to dock, retried (door-closed glyph, same colour)" device="yard" truck={fx.TRUCK_DOCK_UNAVAILABLE} officer="Priya S." />
        <TruckPlate n="9" title="CALLED_TO_DOCK → Dock in (no dock selector; the appointment’s dock is submitted)" device="yard" truck={fx.TRUCK_CALLED_TO_DOCK} officer="Priya S." />
        <TruckPlate n="10a" title="IN_DOCK, no unload → Start unload" device="yard" truck={fx.TRUCK_IN_DOCK} officer="Priya S." />
        <TruckPlate n="10b" title="IN_DOCK, unload started → End unload (a recorded fact, not a live counter)" device="yard" truck={fx.TRUCK_UNLOADING} officer="Priya S." />
        <TruckPlate n="11" title="COMPLETED → Gate out (the check is deliberately not green)" device="gate" truck={fx.TRUCK_COMPLETED} officer="Ramesh K." />

        <Plate n="12" title="Terminal — no button renders at all, and the space is held open">
          <GateFrame>
            <ShiftBar device="gate-booth" facilityId="FAC-JAI-01" officerName="Ramesh K." onBack={() => {}} onEndShift={() => {}} />
            <GateCard>
              <div className="flex flex-col gap-4">
                <TruckIdentityCard truck={fx.TRUCK_GATED_OUT} />
                <ButtonVoid />
              </div>
            </GateCard>
          </GateFrame>
        </Plate>

        <Plate n="13" title="Primary action — every state (the one screen with no backend dependency)">
          <YardFrame>
            <div className="flex flex-col gap-8">
              <SheetItem caption="Default">
                <PrimaryAction label="Gate in" />
              </SheetItem>
              <SheetItem caption="Keyboard focus — two rings, 2px offset, never a soft glow">
                {/* The real component with the real focus classes forced on by a wrapper, rather
                    than a `demoState` prop that would put a gallery concern into shipped code. */}
                <div className="[&>button]:outline-2 [&>button]:outline-ring [&>button]:outline-offset-2">
                  <PrimaryAction label="Gate in" />
                </div>
              </SheetItem>
              <SheetItem caption="Pressed — colour step only, no scale, no ripple, no shadow change">
                <div className="[&>button]:bg-primary-pressed">
                  <PrimaryAction label="Gate in" />
                </div>
              </SheetItem>
              <SheetItem caption="Submitting — label stays, spinner leads (appears only after 1s, per U84)">
                <PrimaryAction label="Gate in" state="submitting" />
              </SheetItem>
              <SheetItem caption="Inactive — full contrast, focusable, operable; not a faded Disabled">
                <PrimaryAction
                  label="Gate in"
                  state="inactive"
                  reason="Can’t confirm this will save — check connection"
                />
              </SheetItem>
              <SheetItem caption="Disabled tier — empty required field (Fork B, recommendation (a))">
                <PrimaryAction label="Start shift" state="inert" />
              </SheetItem>
              <SheetItem caption="Retry message after a failed write">
                <OutcomeBlock
                  tone="warning"
                  live="alert"
                  icon={TriangleAlert}
                  headline="That didn’t record — nothing has changed."
                  align="inline"
                >
                  <OutcomeFact>Try again — this won’t record it twice.</OutcomeFact>
                </OutcomeBlock>
              </SheetItem>
            </div>
          </YardFrame>
        </Plate>

        <OutcomePlate n="14" title="Gate-in recorded (arrival_state surfaced, sentence case)" device="gate" result={fx.RESULT_GATE_IN} truck={fx.TRUCK_NOT_QUEUED} officer="Ramesh K." />
        <OutcomePlate n="15a" title="Called to dock" device="yard" result={fx.RESULT_QUEUE_UPDATED} truck={fx.TRUCK_WAITING_LATE} officer="Priya S." />
        <OutcomePlate n="15b" title="Dock-in recorded" device="yard" result={fx.RESULT_DOCK_IN} truck={fx.TRUCK_CALLED_TO_DOCK} officer="Priya S." />
        <OutcomePlate n="15c" title="Unload started" device="yard" result={fx.RESULT_UNLOAD_START} truck={fx.TRUCK_IN_DOCK} officer="Priya S." />
        <OutcomePlate n="16" title="Gate-out recorded, with dwell (a measured fact, not an assessment)" device="gate" result={fx.RESULT_GATE_OUT} truck={fx.TRUCK_COMPLETED} officer="Ramesh K." />
        <OutcomePlate n="17" title="DOCK_MISMATCH — warning, not danger; the confirmed dock has no code in the response" device="yard" result={fx.RESULT_DOCK_MISMATCH} truck={fx.TRUCK_CALLED_TO_DOCK} officer="Priya S." />
        <OutcomePlate n="18" title="Unload overrun — a fact, not a question asked of the officer" device="yard" result={fx.RESULT_UNLOAD_OVERRUN} truck={fx.TRUCK_UNLOADING} officer="Priya S." />
        <OutcomePlate n="18b" title="Unload ended on time — no artboard exists; copy inferred from screen 15’s family" device="yard" result={fx.RESULT_UNLOAD_ON_TIME} truck={fx.TRUCK_UNLOADING} officer="Priya S." />
        <OutcomePlate n="19" title="ALREADY_CHECKED_IN — informational: not green, not red" device="gate" result={fx.RESULT_ALREADY_CHECKED_IN} truck={fx.TRUCK_NOT_QUEUED} officer="Ramesh K." />
        <OutcomePlate n="20" title="NO_ACTIVE_APPOINTMENT — danger, and the button label differs on purpose" device="gate" result={fx.RESULT_NO_APPOINTMENT} truck={fx.TRUCK_NOT_QUEUED} officer="Ramesh K." />
        <OutcomePlate n="21" title="DOCK_OCCUPIED — warning tone, assertive politeness; the truck’s state did change" device="yard" result={fx.RESULT_DOCK_OCCUPIED} truck={fx.TRUCK_CALLED_TO_DOCK} officer="Priya S." />
        <OutcomePlate n="22a" title="INVALID_TRANSITION — no button; the screen resolves on its own" device="yard" result={fx.RESULT_INVALID_TRANSITION} truck={fx.TRUCK_IN_DOCK} officer="Priya S." />

        <TruckPlate n="22b" title="Re-rendered with the truck’s real state — the card IS the resolution" device="yard" truck={fx.TRUCK_UNLOADING} officer="Priya S." />

        <OutcomePlate n="—" title="ALREADY_GATED_OUT — a real shipped code no design file ever names" device="gate" result={fx.RESULT_ALREADY_GATED_OUT} truck={fx.TRUCK_GATED_OUT} officer="Ramesh K." />
      </div>
    </div>
  )
}

function Plate({ n, title, children }: { n: string; title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-body font-semibold">
        <span className="font-mono text-muted-foreground">{n}</span> · {title}
      </h2>
      {children}
    </section>
  )
}

/** True device size, so every token measured against these plates is the shipped value. */
function GateFrame({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-[800px] w-[1280px] flex-col overflow-hidden rounded-lg border border-border bg-background p-(--content-p) shadow-overlay">
      {children}
    </div>
  )
}

function YardFrame({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-[1280px] w-[800px] flex-col overflow-hidden rounded-lg border border-border bg-background p-(--content-p) shadow-overlay">
      {children}
    </div>
  )
}

function GateCard({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-1 items-center justify-center">
      <div className="w-[720px] rounded-lg border border-border bg-card p-6 shadow-raised">
        {children}
      </div>
    </div>
  )
}

function YardCard({ children }: { children: ReactNode }) {
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

function SheetItem({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-body-lg font-semibold text-muted-foreground">{caption}</p>
      {children}
    </div>
  )
}

/**
 * Screens 6-12 and 22b. Renders `TruckIdentityCard` plus the button the server's own `next_action` selects --
 * **the real mapping**, not a per-plate hardcoded label, so a plate showing the wrong verb is a
 * real defect in the fixture's `next_action` or in `actionFor`, rather than a typo in this file.
 *
 * `TruckAction` itself is not used here on purpose: it would arm a live write against a fixture
 * shipment id, and a gallery page must never be one mis-click away from a real gate event.
 */
function TruckPlate({
  n,
  title,
  device,
  truck,
  officer,
}: {
  n: string
  title: string
  device: 'gate' | 'yard'
  truck: GateTruckMatch
  officer: string
}) {
  const next = actionFor(truck.next_action)
  const Frame = device === 'gate' ? GateFrame : YardFrame
  const Card = device === 'gate' ? GateCard : YardCard
  return (
    <Plate n={n} title={title}>
      <Frame>
        <ShiftBar
          device={device === 'gate' ? 'gate-booth' : 'yard-tablet'}
          facilityId="FAC-JAI-01"
          officerName={officer}
          onBack={() => {}}
          onEndShift={() => {}}
        />
        <Card>
          <div className="flex flex-col gap-4">
            <TruckIdentityCard truck={truck} />
            {next ? <PrimaryAction label={next.label} /> : <ButtonVoid />}
          </div>
        </Card>
      </Frame>
    </Plate>
  )
}

/** Screens 14-22a. The shift bar carries no back control on an outcome screen -- the only way
 *  forward is the outcome's own button (Flow 8). */
function OutcomePlate({
  n,
  title,
  device,
  result,
  truck,
  officer,
}: {
  n: string
  title: string
  device: 'gate' | 'yard'
  result: Parameters<typeof OutcomeScreen>[0]['result']
  truck: GateTruckMatch
  officer: string
}) {
  const Frame = device === 'gate' ? GateFrame : YardFrame
  const Card = device === 'gate' ? GateCard : YardCard
  return (
    <Plate n={n} title={title}>
      <Frame>
        <ShiftBar
          device={device === 'gate' ? 'gate-booth' : 'yard-tablet'}
          facilityId="FAC-JAI-01"
          officerName={officer}
          onEndShift={() => {}}
        />
        <Card>
          <OutcomeScreen
            result={result}
            truck={truck}
            onNext={result.code === 'INVALID_TRANSITION' ? null : () => {}}
          />
        </Card>
      </Frame>
    </Plate>
  )
}
