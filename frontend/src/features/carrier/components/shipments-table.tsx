import { ChevronRight } from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'
import type { MouseEvent } from 'react'

import { cn } from '@/shared/lib/utils'
import { Skeleton } from '@/shared/ui/skeleton'
import { StatusCell } from './status-cell'
import { midTruncate, needsTitle } from '../lib/format'
import { PROMISE_SPOKEN, promiseCell } from '../lib/promise'
import type { FleetShipment } from '../lib/types'

/**
 * "Your shipments" — `stitch-prompts.md` §3, `05-carrier-portal/screens.md` §1,
 * `components.md` §2.
 *
 * Fixed column widths (never auto-width), a sticky header, 44px rows at `comfortable` density,
 * and **no sortable column headers**: sort is fixed at most-recently-updated first
 * (`ORDER BY t.updated_at DESC` in the repository), so a clickable header would promise an
 * interaction this surface does not have.
 *
 * Read-only throughout: no checkbox column, no bulk bar, no overflow menu, no inline
 * Reschedule/Cancel/Message, no swipe, no drag. §7.5.6 has no mutating tool for this role and
 * `components.md` §18 requires a scope-denied control to be **Hidden**, never Disabled — a
 * greyed-out action would misrepresent what this surface can do.
 *
 * ═══════════════════════════════════════════════════════════════════════════════════════════
 * ## R5b — the row-click target, and why this is JS and not CSS
 * ═══════════════════════════════════════════════════════════════════════════════════════════
 *
 * `05-carrier-portal/implementation-spec.md` §4.0's R5b correction is the reason this component
 * has an `onClick` on `<tr>` at all. The short version, measured in the design pass rather than
 * reasoned about:
 *
 *   - `components.md` §2 requires **the whole row** to be one navigation target.
 *   - The mockup implemented that as `.rowlink::after { position: absolute; inset: 0 }`,
 *     intending the pseudo-element to stretch over the `<tr>`.
 *   - R15 (also required, and confirmed necessary against this surface's own 768px floor —
 *     the table's 972px minimum genuinely overflows it) makes the **first `<td>`
 *     `position: sticky`**, which is a *nearer positioned ancestor* to the link than the row.
 *   - So the pseudo-element's containing block resolved to that 180px column, not the 972px
 *     row. An `elementFromPoint` sweep confirmed it: only the point over the ID text hit the
 *     link; the driver, facility, dock, status and chevron cells all missed.
 *
 * **There is no pure-CSS fix** — both patterns need to be the row's nearest positioned ancestor
 * and only one can be. So the row navigates via a pointer delegate, and `<Link>` stays the real
 * focusable, keyboard- and screen-reader-facing element.
 *
 * ### Deliberately a pointer delegate only, not the `onKeyDown` R5b also suggests
 *
 * Adding a key handler to `<tr>` requires making the row focusable, which would put **two tab
 * stops on every row** (the row and the link inside it) for zero gain: `05-carrier-portal/
 * accessibility.md` states plainly that "standard `Tab`/`Shift+Tab`/`Enter` navigation through
 * rows and controls is sufficient and expected" here, and `<Link>` already gives exactly that.
 * The pointer gap was the real defect; the keyboard path was never broken. Narrowed on purpose,
 * and recorded rather than silently dropped.
 *
 * The delegate also refuses to fire when it would break something a user expects:
 * modified clicks (open-in-new-tab), non-primary buttons, clicks that landed on another
 * interactive element, and clicks that end a text selection all fall through untouched.
 */

/**
 * Fixed column widths, from `mockup.html`'s own `<colgroup>` — with **one measured change**.
 *
 * Status is 408px here, not the mockup's 336. Found by rendering, not by reading: on the row that
 * carries a promise chip *and* an exception marker together (`edge-cases.md` #3's "normal, not a
 * bug" case), 336px was not enough for both and the flex row wrapped, taking that row to 55px
 * against the 44px floor `stitch-prompts.md` §3 and the design's own R16b fix both pin.
 *
 * The cause is a knock-on from a deviation already recorded in `status-cell.tsx`: the mockup's
 * chip is 12px, the **shared** chip is 14px (the owner's 2026-08-27 Fork B decision, applied to
 * the component this surface is required to reuse verbatim), and a 14px uppercase
 * `PENDING CONFIRMATION` is ~17% wider than the width 336 was chosen for.
 *
 * Widening the column is the only one of the three available fixes that breaks no locked rule —
 * clipping or wrapping the chip would abbreviate a label `components.md` §2 forbids abbreviating,
 * and restyling the chip smaller would fork the component §2 requires reusing verbatim. The
 * table's minimum width grows 972 -> 1044, which changes nothing structurally: it already
 * overflows this surface's 768px floor, which is exactly why R15's sticky first column exists.
 */
const COLUMNS = [180, 140, 200, 72, 408, 44]
/** Sum of the fixed columns. The container scrolls below this; the first column stays frozen. */
const MIN_TABLE_WIDTH = COLUMNS.reduce((a, b) => a + b, 0)

function shipmentHref(shipmentId: string) {
  return `/carrier/shipments/${encodeURIComponent(shipmentId)}`
}

/** The row's accessible name — every fact the row shows, in one sentence, because a link whose
 *  text is only the shipment id would announce as an id and nothing else. */
function rowLabel(row: FleetShipment, shownHeldEnabled: boolean): string {
  const cell = promiseCell(row.promise_state, shownHeldEnabled)
  const state =
    cell.kind === 'chip'
      ? PROMISE_SPOKEN[cell.state]
      : cell.kind === 'plain'
        ? cell.label.toLowerCase()
        : 'no appointment yet'
  const dock = row.dock_code ? `dock ${row.dock_code}` : 'no dock assigned'
  const exception = row.has_open_exception ? ', exception open' : ''
  return `${row.shipment_id}, driver ${row.driver_name}, ${row.facility_name} ${dock}, ${state}${exception}. Open shipment detail.`
}

function Cell({
  children,
  className,
  sticky = false,
}: {
  children?: React.ReactNode
  className?: string
  sticky?: boolean
}) {
  return (
    <td
      className={cn(
        // Height and padding come from the density variables, not from literals: `comfortable`
        // resolves --row-h to 44px and --cell-px to 16px, which is what `stitch-prompts.md`'s
        // own density note specifies for this surface.
        'h-(--row-h) overflow-hidden border-b border-border px-(--cell-px) py-0 align-middle text-body',
        'bg-card group-hover:bg-hover group-has-[a:focus-visible]:bg-hover',
        sticky && 'sticky left-0 z-sticky',
        className,
      )}
    >
      {children}
    </td>
  )
}

export function ShipmentsTable({
  rows,
  shownHeldEnabled,
  dimmed = false,
  /** Set on return from a detail screen so focus can be restored to the row that was open
   *  (`05-carrier-portal/accessibility.md`'s focus-management table: "the shipment row that was
   *  open — not the top of the list"). */
  rowIdPrefix = 'carrier-row',
}: {
  rows: FleetShipment[]
  shownHeldEnabled: boolean
  dimmed?: boolean
  rowIdPrefix?: string
}) {
  const navigate = useNavigate()

  function handleRowClick(event: MouseEvent<HTMLTableRowElement>, row: FleetShipment) {
    if (event.defaultPrevented) return
    // Primary button only, unmodified: a Ctrl/Cmd/Shift click on a row must not swallow the
    // browser's own open-in-new-tab, and the anchor handles those natively.
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return
    }
    const target = event.target as HTMLElement | null
    // The anchor (and any other interactive element that lands in a row later) handles itself.
    if (target?.closest('a, button, input, select, textarea, [role="button"]')) return
    // Finishing a text selection is not a click on the row.
    if (window.getSelection()?.toString()) return
    navigate(shipmentHref(row.shipment_id))
  }

  return (
    <div
      className={cn(
        // R15: horizontal scroll with a frozen first column, replacing a silent clip. This is a
        // real requirement here, not an imported habit -- `spacing-and-layout.md` gives this
        // surface a 768px floor and the table's own minimum is 972px.
        'overflow-x-auto overflow-y-visible rounded-md border border-border bg-card shadow-raised',
        dimmed && 'opacity-60',
      )}
      aria-busy={dimmed || undefined}
    >
      <table
        className="w-full table-fixed border-collapse text-body"
        style={{ minWidth: MIN_TABLE_WIDTH }}
      >
        <colgroup>
          {COLUMNS.map((w, i) => (
            <col key={i} style={{ width: w }} />
          ))}
        </colgroup>
        <thead>
          <tr>
            <th
              scope="col"
              className="sticky top-0 left-0 z-shell h-(--row-h) border-b border-border bg-card px-(--cell-px) text-left text-label text-subtle-foreground uppercase"
            >
              Shipment
            </th>
            {['Driver', 'Facility', 'Dock', 'Status'].map((h) => (
              <th
                key={h}
                scope="col"
                className="sticky top-0 z-sticky h-(--row-h) border-b border-border bg-card px-(--cell-px) text-left text-label text-subtle-foreground uppercase"
              >
                {h}
              </th>
            ))}
            <th
              scope="col"
              className="sticky top-0 z-sticky h-(--row-h) border-b border-border bg-card px-(--cell-px)"
            >
              <span className="sr-only">Open detail</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.shipment_id}
              // R5b's delegate. See the block comment above for why this is JS.
              onClick={(e) => handleRowClick(e, row)}
              className={cn(
                'group cursor-pointer',
                // The focus ring lands on the ROW, driven by the link inside it -- so the
                // visible focus indicator matches the thing that is actually navigable.
                'has-[a:focus-visible]:outline-2 has-[a:focus-visible]:outline-ring has-[a:focus-visible]:-outline-offset-2',
              )}
            >
              <Cell sticky className="font-mono font-semibold">
                <Link
                  id={`${rowIdPrefix}-${row.shipment_id}`}
                  to={shipmentHref(row.shipment_id)}
                  aria-label={rowLabel(row, shownHeldEnabled)}
                  title={row.shipment_id}
                  // Fills the cell rather than sitting as a 74x20 inline box inside it. Measured
                  // in headless Chromium: as an inline anchor it was 74x20, under WCAG 2.5.8's
                  // 24px floor even though the ROW around it is a 972x44 pointer target. R5b's
                  // own analysis assumes this column is 180x44; this is what makes that true.
                  className="flex h-(--row-h) items-center rounded-sm text-inherit no-underline outline-none"
                >
                  {/* Mid-truncated: the distinguishing suffix must survive
                      (`data-formatting.md`, `edge-cases.md` #6). */}
                  {midTruncate(row.shipment_id)}
                </Link>
              </Cell>

              <Cell>
                <span
                  className="block truncate"
                  // End-truncated -- identity is at the start. The tooltip is reachable on
                  // FOCUS, not hover-only, which is why this carries a tabindex.
                  tabIndex={needsTitle(row.driver_name, 16) ? 0 : undefined}
                  title={needsTitle(row.driver_name, 16) ? row.driver_name : undefined}
                >
                  {row.driver_name}
                </span>
              </Cell>

              <Cell className="font-mono">
                <span
                  className="block truncate"
                  tabIndex={needsTitle(row.facility_name, 22) ? 0 : undefined}
                  title={needsTitle(row.facility_name, 22) ? row.facility_name : undefined}
                >
                  {row.facility_name}
                </span>
              </Cell>

              <Cell className="font-mono">{row.dock_code || '—'}</Cell>

              <Cell>
                <StatusCell
                  promiseState={row.promise_state}
                  hasOpenException={row.has_open_exception}
                  shownHeldEnabled={shownHeldEnabled}
                />
              </Cell>

              <Cell className="text-subtle-foreground">
                <ChevronRight className="size-4" aria-hidden="true" strokeWidth={2} />
              </Cell>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Header-only shell, for the states that replace the table BODY while keeping the columns in
 *  place — the filtered-empty state (`mockup.html` 4c), where nothing about the layout should
 *  move when a match returns. */
export function ShipmentsTableHeader() {
  return (
    <table
      className="w-full table-fixed border-collapse text-body"
      style={{ minWidth: MIN_TABLE_WIDTH }}
    >
      <colgroup>
        {COLUMNS.map((w, i) => (
          <col key={i} style={{ width: w }} />
        ))}
      </colgroup>
      <thead>
        <tr>
          {['Shipment', 'Driver', 'Facility', 'Dock', 'Status'].map((h) => (
            <th
              key={h}
              scope="col"
              className="h-(--row-h) border-b border-border bg-card px-(--cell-px) text-left text-label text-subtle-foreground uppercase"
            >
              {h}
            </th>
          ))}
          <th scope="col" className="h-(--row-h) border-b border-border bg-card px-(--cell-px)">
            <span className="sr-only">Open detail</span>
          </th>
        </tr>
      </thead>
    </table>
  )
}

/**
 * Loading skeleton. Blocks sit at the **exact widths of the columns they stand in for**
 * (72 / 88 / 140 / 120 / 130) so nothing jumps when the real rows arrive, and the section
 * heading and column headers render as real text throughout — what is loading is data, not the
 * application (`stitch-prompts.md` §5).
 */
export function ShipmentsTableSkeleton({ rows = 5 }: { rows?: number }) {
  const widths = [72, 88, 140, 120, 130]
  return (
    <div aria-hidden="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className={cn(
            'flex h-(--row-h) items-center px-(--cell-px)',
            i < rows - 1 && 'border-b border-border',
          )}
        >
          {widths.map((w) => (
            <Skeleton key={w} className="mr-4 h-3 rounded-sm" style={{ width: w }} />
          ))}
        </div>
      ))}
    </div>
  )
}
