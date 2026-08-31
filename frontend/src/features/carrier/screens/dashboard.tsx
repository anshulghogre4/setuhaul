import { useEffect, useRef } from 'react'

import {
  CaughtUpBlock,
  LastUpdatedLine,
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
import { formatRelative, formatTime } from '../lib/format'
import { carrierHeldEnabled } from '../lib/flags'
import type { FleetDashboardState } from '../lib/use-fleet-dashboard'

/**
 * The carrier dashboard — `screens.md` §1, `stitch-prompts.md` §1.
 *
 * **One sectioned page.** No tabs, no facility switcher, no facility filter, no settings beyond
 * account basics: a carrier's fleet spans whatever warehouses it delivers to and is always shown
 * whole, so facility is a value in a row and never a scope control.
 *
 * ## The carrier's own name renders here, not in the top bar — a shell gap, recorded
 *
 * `screens.md` §1 puts the carrier's name in the top bar's left slot, "where other SetuHaul
 * consoles put a facility switcher". E5.0's shared `TopBar` renders `FacilitySwitcher` in that
 * slot, and `FacilitySwitcher` returns `null` for this role (correctly — U83: scope-denied is
 * Hidden, and a greyed switcher would tell a carrier that facilities are something this product
 * scopes by). So the slot is simply empty for a carrier and the shell has no carrier-name field
 * to fill it with. Rather than reach into `components/shell/**` — shared infrastructure, and
 * being read by concurrent builds — the name renders as this screen's own `h1`, which it needed
 * anyway for the route-change focus target. Reported to the coordinator as a shell follow-up.
 *
 * ## Nothing here updates itself
 *
 * No live region, no auto-refresh, no websocket indicator, no "N new" badge. `flows-and-states.md`
 * Flow 5 makes that a deliberate departure from every operational console: a scoped-read
 * dashboard for a role with no time-pressured decision does not need one, and implying real-time
 * urgency this role does not have would misrepresent the data.
 */
export function CarrierDashboard({
  carrierName,
  state,
  /** Set by the portal when the user came back from a detail screen, so focus can return to the
   *  row that was open rather than the top of the list (`accessibility.md` focus management). */
  returnToShipmentId,
  onReturnFocusHandled,
  scrollRef,
}: {
  carrierName: string
  state: FleetDashboardState
  returnToShipmentId: string | null
  onReturnFocusHandled: () => void
  /** The shell's scrolling `<main>`, so the list's scroll position survives a round trip to
   *  detail and back (`flows-and-states.md` Flow 3 step 4). */
  scrollRef: { current: number }
}) {
  const headingRef = useRef<HTMLHeadingElement | null>(null)

  const shipments = state.shipments.data
  const exceptions = state.exceptions.data
  const overview = state.overview.data
  const isNewCarrier = shipments?.empty_reason === 'NONE_YET'

  // Restore scroll and focus on return from detail; save scroll on the way out. `<main>` is the
  // scroll container the shell owns, found by id rather than a ref because the shell is a parent.
  useEffect(() => {
    const main = document.getElementById('content')
    if (main && scrollRef.current > 0) main.scrollTop = scrollRef.current
    return () => {
      const el = document.getElementById('content')
      if (el) scrollRef.current = el.scrollTop
    }
  }, [scrollRef])

  useEffect(() => {
    if (!returnToShipmentId || !shipments) return
    const row = document.getElementById(`carrier-row-${returnToShipmentId}`)
    row?.focus()
    onReturnFocusHandled()
  }, [returnToShipmentId, shipments, onReturnFocusHandled])

  return (
    <div className="mx-auto w-full max-w-[1120px]">
      <h1 ref={headingRef} tabIndex={-1} className="mb-5 text-h3 outline-none">
        {carrierName}
      </h1>

      {/* One notice for the whole page, not one per region. */}
      {state.staleSince ? (
        <StaleNotice since={formatTime(state.staleSince) ?? '—'} onRetry={state.refresh} />
      ) : null}

      {/* ── Overview strip ───────────────────────────────────────────────────────────── */}
      {overview ? (
        <OverviewStrip
          overview={overview}
          performance={state.performance}
          dimmed={state.showLoading && !state.firstLoad}
        />
      ) : state.overview.failed ? (
        <div className="rounded-md border border-border bg-card shadow-raised">
          <RegionFailedBlock what="fleet summary" onRetry={state.refresh} />
        </div>
      ) : state.showLoading ? (
        <OverviewStripSkeleton />
      ) : null}

      <LastUpdatedLine
        relative={formatRelative(state.lastUpdated)}
        refreshing={state.showLoading && !state.firstLoad}
        onRefresh={state.refresh}
      />

      {/* ── Your shipments ───────────────────────────────────────────────────────────── */}
      <SectionHead
        action={
          // Hidden for a brand-new carrier only, matching the mockup exactly: state 7
          // ("caught up") KEEPS the filter control, state 8 ("nothing yet") drops it. The
          // distinction is not cosmetic -- an established carrier at zero today may well want to
          // filter to `Confirmed` and see last week's, while an account with no history at all
          // has nothing any filter value could ever return.
          isNewCarrier ? null : (
            <StatusFilter
              value={state.statusFilter}
              onChange={state.setStatusFilter}
              heldEnabled={carrierHeldEnabled}
            />
          )
        }
      >
        Your shipments
      </SectionHead>

      <div className="mb-5">
        {shipments && shipments.items.length > 0 ? (
          <ShipmentsTable
            rows={shipments.items}
            heldEnabled={carrierHeldEnabled}
            dimmed={state.showLoading && !state.firstLoad}
          />
        ) : state.shipments.failed ? (
          <div className="rounded-md border border-border bg-card shadow-raised">
            <RegionFailedBlock what="shipments" onRetry={state.retryShipments} />
          </div>
        ) : shipments ? (
          <div className="rounded-md border border-border bg-card shadow-raised">
            {/* The filtered-empty state keeps the column headers, so nothing about the layout
                moves when a match returns. The two unfiltered empties replace the table
                entirely -- there is no list to hold a shape for. */}
            {shipments.empty_reason === 'NO_MATCH_FOR_FILTER' ? (
              <>
                <ShipmentsTableHeader />
                <NoFilterMatchBlock onClear={() => state.setStatusFilter(null)} />
              </>
            ) : shipments.empty_reason === 'NONE_YET' ? (
              <NothingYetBlock />
            ) : (
              <CaughtUpBlock copy="No active shipments right now." />
            )}
          </div>
        ) : state.showLoading ? (
          <div className="overflow-hidden rounded-md border border-border bg-card shadow-raised">
            <ShipmentsTableHeader />
            <ShipmentsTableSkeleton />
            {state.stalled ? <StalledRow onRetry={state.retryShipments} /> : null}
          </div>
        ) : null}
      </div>

      {/* ── Open exceptions ──────────────────────────────────────────────────────────────
          Hidden entirely for a brand-new carrier: `stitch-prompts.md` §6 frame B permits either
          hiding it or an `inbox` block, and asks for one choice applied consistently. Hiding is
          the mockup's own pick, kept. */}
      {isNewCarrier ? null : (
        <>
          <SectionHead>Open exceptions</SectionHead>
          {exceptions && exceptions.items.length > 0 ? (
            <ExceptionsList
              items={exceptions.items}
              dimmed={state.showLoading && !state.firstLoad}
            />
          ) : state.exceptions.failed ? (
            <div className="rounded-md border border-border bg-card shadow-raised">
              <RegionFailedBlock what="open exceptions" onRetry={state.retryExceptions} />
            </div>
          ) : exceptions ? (
            <div className="rounded-md border border-border bg-card shadow-raised">
              <CaughtUpBlock copy="No open exceptions." />
            </div>
          ) : state.showLoading ? (
            <ExceptionsListSkeleton />
          ) : null}
        </>
      )}
    </div>
  )
}
