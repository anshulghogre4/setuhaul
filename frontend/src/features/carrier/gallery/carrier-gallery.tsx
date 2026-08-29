import { useRef, type ReactNode } from 'react'

import {
  CaughtUpBlock,
  NoFilterMatchBlock,
  NothingYetBlock,
  RegionFailedBlock,
  SectionHead,
  StaleNotice,
  StalledRow,
} from '../components/blocks'
import { ExceptionsList, ExceptionsListSkeleton } from '../components/exceptions-list'
import { OverviewStrip, OverviewStripSkeleton } from '../components/overview-strip'
import {
  ShipmentsTable,
  ShipmentsTableHeader,
  ShipmentsTableSkeleton,
} from '../components/shipments-table'
import { StatusFilter } from '../components/status-filter'
import { CarrierDashboard } from '../screens/dashboard'
import { CarrierDetailCard, CarrierOutOfScope } from '../screens/shipment-detail'
import * as F from './fixtures'

/**
 * `/carrier/_states` — every one of `mockup.html`'s 13 labelled states, rendered by the **real
 * components** rather than re-drawn. Not linked from the app.
 *
 * This exists because the live surface cannot be exercised without a signed-in `CARRIER`
 * identity and live data, and because `tsc -b` proves nothing about what a component actually
 * renders. Same purpose the driver / ops / planner galleries serve.
 *
 * Two states from the mockup are **deliberately not reproducible as static plates** and are
 * labelled as such below rather than faked:
 *   - 4b (filter popover open) — Radix dismisses a `defaultOpen` menu during mount, the same
 *     finding E5.0 recorded for its own popovers. The control renders; it opens on click.
 *   - the first-load "under 1 second, show nothing" band, which is an absence, not a plate.
 *
 * `data-density="comfortable"` is set here because the gallery mounts outside `AppShell`, which
 * is normally what sets it.
 */
export function CarrierStatesGallery() {
  const scrollRef = useRef(0)
  const noop = () => {}

  return (
    <div data-density="comfortable" className="min-h-dvh bg-background p-8">
      <header className="mx-auto mb-10 max-w-[1120px]">
        <p className="text-label text-subtle-foreground uppercase">05 · Carrier portal · E5.5</p>
        <h1 className="mt-1 text-h1">Every screen and state, rendered by the real components</h1>
        <p className="mt-2 max-w-[70ch] text-body text-muted-foreground">
          Single sectioned dashboard, cross-facility, entirely read-only — §7.5.6 has no mutating
          tool for this role. No facility switcher, no action of any kind, no live updates. The{' '}
          <code>SHOWN</code> and <code>HELD</code> variants below are shown with the flag forced
          on for review; on the live route they are off pending issue #53.
        </p>
      </header>

      <Plate id="3" title="Fleet overview strip — three stat tiles and the on-time sparkline">
        <OverviewStrip overview={F.OVERVIEW} performance={F.PERFORMANCE} />
      </Plate>

      <Plate id="4a" title="Your shipments — default">
        <ShipmentsTable rows={F.SHIPMENTS} shownHeldEnabled={false} />
      </Plate>

      <Plate
        id="4b"
        title="Your shipments — status filter (opens on click; Shown/Held omitted while #53 is open)"
      >
        <div className="flex justify-end">
          <StatusFilter value={null} onChange={noop} shownHeldEnabled={false} />
        </div>
      </Plate>

      <Plate id="4b′" title="Status filter — with the #53 flag forced on, all six options">
        <div className="flex justify-end">
          <StatusFilter value={null} onChange={noop} shownHeldEnabled />
        </div>
      </Plate>

      <Plate id="4c" title="Your shipments — filtered, no matches">
        <div className="rounded-md border border-border bg-card shadow-raised">
          <ShipmentsTableHeader />
          <NoFilterMatchBlock onClear={noop} />
        </div>
      </Plate>

      <Plate id="5a" title="Open exceptions — summary rows (all three authorised clauses)">
        <ExceptionsList items={F.EXCEPTIONS.items} />
      </Plate>

      <Plate id="5b" title="Open exceptions — caught up (empty)">
        <div className="rounded-md border border-border bg-card shadow-raised">
          <CaughtUpBlock copy="No open exceptions." />
        </div>
      </Plate>

      <Plate id="6a" title="Dashboard loading — per-section skeletons">
        <OverviewStripSkeleton />
        <div className="mt-5">
          <SectionHead>Your shipments</SectionHead>
          <div className="overflow-hidden rounded-md border border-border bg-card shadow-raised">
            <ShipmentsTableHeader />
            <ShipmentsTableSkeleton />
          </div>
        </div>
        <div className="mt-5">
          <SectionHead>Open exceptions</SectionHead>
          <ExceptionsListSkeleton />
        </div>
      </Plate>

      <Plate id="6b" title="Dashboard loading — tiles resolved, table still in flight (past ~3s)">
        <CarrierDashboard
          carrierName="Rajasthan Roadlines"
          state={F.dashboardState({
            shipments: { data: null, failed: false },
            showLoading: true,
            stalled: true,
          })}
          returnToShipmentId={null}
          onReturnFocusHandled={noop}
          scrollRef={scrollRef}
        />
      </Plate>

      <Plate id="7" title='Dashboard empty — "caught up" (established carrier, currently at zero)'>
        <CarrierDashboard
          carrierName="Rajasthan Roadlines"
          state={F.dashboardState({
            overview: { data: F.OVERVIEW_CAUGHT_UP, failed: false },
            performance: F.PERFORMANCE_CAUGHT_UP,
            shipments: { data: F.shipmentList([], 'NONE_RIGHT_NOW'), failed: false },
            exceptions: { data: F.EXCEPTIONS_EMPTY, failed: false },
          })}
          returnToShipmentId={null}
          onReturnFocusHandled={noop}
          scrollRef={scrollRef}
        />
      </Plate>

      <Plate id="8" title='Dashboard empty — "nothing yet" (new carrier, no history at all)'>
        <CarrierDashboard
          carrierName="Vindhya Carriers"
          state={F.dashboardState({
            overview: { data: F.OVERVIEW_NOTHING_YET, failed: false },
            performance: null,
            shipments: { data: F.shipmentList([], 'NONE_YET'), failed: false },
            exceptions: { data: F.EXCEPTIONS_EMPTY, failed: false },
          })}
          returnToShipmentId={null}
          onReturnFocusHandled={noop}
          scrollRef={scrollRef}
        />
      </Plate>

      <Plate id="9" title="Load failure — shipments table failed (primary content, fails loud)">
        <CarrierDashboard
          carrierName="Rajasthan Roadlines"
          state={F.dashboardState({ shipments: { data: null, failed: true } })}
          returnToShipmentId={null}
          onReturnFocusHandled={noop}
          scrollRef={scrollRef}
        />
      </Plate>

      <Plate
        id="10"
        title="Degradation — trend data failed (secondary content, vanishes silently)"
      >
        <OverviewStrip overview={F.OVERVIEW} performance={null} />
      </Plate>

      <Plate id="11" title="Degradation — refresh failed, data is stale">
        <StaleNotice since="09:41" onRetry={noop} />
        <OverviewStrip overview={F.OVERVIEW} performance={F.PERFORMANCE} />
      </Plate>

      <Plate id="stalled" title="Latency band — past ~3s, Retry joins the skeleton">
        <div className="overflow-hidden rounded-md border border-border bg-card shadow-raised">
          <ShipmentsTableHeader />
          <ShipmentsTableSkeleton rows={3} />
          <StalledRow onRetry={noop} />
        </div>
      </Plate>

      <Plate id="12a" title="Shipment detail — SHOWN (flag forced on; unreachable live, #53)">
        <CarrierDetailCard payload={F.DETAIL_SHOWN} shownHeldEnabled />
      </Plate>

      <Plate id="12b" title="Shipment detail — HELD (flag forced on; unreachable live, #53)">
        <CarrierDetailCard payload={F.DETAIL_HELD} shownHeldEnabled />
      </Plate>

      <Plate id="12c" title="Shipment detail — PENDING CONFIRMATION">
        <CarrierDetailCard payload={F.DETAIL_PENDING} />
      </Plate>

      <Plate id="12d" title="Shipment detail — CONFIRMED (the only state that may use finality language)">
        <CarrierDetailCard payload={F.DETAIL_CONFIRMED} />
      </Plate>

      <Plate
        id="12e"
        title="Shipment detail — no appointment yet (Fork A's undesigned null promise state)"
      >
        <CarrierDetailCard payload={F.DETAIL_NO_APPOINTMENT} />
      </Plate>

      <Plate id="13" title="Shipment detail — out-of-scope refusal">
        <CarrierOutOfScope />
      </Plate>

      <Plate id="fail-region" title="A primary region failed — shipments and exceptions">
        <div className="rounded-md border border-border bg-card shadow-raised">
          <RegionFailedBlock what="shipments" onRetry={noop} />
        </div>
        <div className="mt-4 rounded-md border border-border bg-card shadow-raised">
          <RegionFailedBlock what="open exceptions" onRetry={noop} />
        </div>
      </Plate>

      <Plate id="nothing-yet-block" title='Empty block — "nothing yet", isolated'>
        <div className="rounded-md border border-border bg-card shadow-raised">
          <NothingYetBlock />
        </div>
      </Plate>
    </div>
  )
}

function Plate({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section className="mx-auto mb-12 max-w-[1120px]">
      <p className="mb-2 text-supporting font-semibold text-muted-foreground">
        State {id} — <span className="text-foreground">{title}</span>
      </p>
      <div className="rounded-lg border border-border bg-background p-6">{children}</div>
    </section>
  )
}
