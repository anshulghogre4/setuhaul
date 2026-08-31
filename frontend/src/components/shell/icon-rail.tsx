import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import {
  ChartGantt,
  Flag,
  Package,
  SlidersHorizontal,
  Warehouse,
  type LucideIcon,
} from 'lucide-react'

import { railDestinationFor, type Facility, type RoleName, type SurfaceId } from '@/core/auth/identity'
import { cn } from '@/shared/lib/utils'

/** iconography.md section "Rail destinations".  `inbox` and `circle-check-big` are bound to
 *  the two empty-state meanings, so neither was available for the ops queue -- which is how
 *  `flag` was chosen.  `chart-line` was dropped when Carrier collapsed to one destination. */
const SURFACE_ICON: Record<SurfaceId, LucideIcon> = {
  ops: Flag,
  planner: ChartGantt,
  gate: Warehouse,
  carrier: Package,
  admin: SlidersHorizontal,
  driver: Package, // unreachable: the driver has no rail
}

/**
 * Artboard 30.  56px fixed, expanding to 240px **as an overlay** on hover/focus.
 *
 * Four things here are load-bearing and were each found by measuring a real render rather
 * than reading markup (implementation-spec 4.7).  Do not "simplify" them:
 *
 *  1. **`z-shell` on the rail is not optional.**  The rail and the content region are
 *     sibling positioned boxes with `z-index: auto`, so the content paints on top of the
 *     rail purely because it comes later in the DOM -- which silently buries the hover
 *     tooltip underneath the content bars.  Confirmed with `elementFromPoint`: the topmost
 *     element across the tooltip was the content, never the tooltip.
 *
 *  2. **The tooltip clears the rail with `left: calc(100% + 16px)`.**  `left: 48px` on a
 *     40px button sitting 5.5px inside a 56px rail put the tooltip's left edge 0.5px
 *     *inside* the rail's right border, so it appeared to grow out of the rail rather than
 *     beside it.
 *
 *  3. **The active marker sits 6-8px in, clearing U40's 0-4px facility stripe.**  At
 *     `left:-8px` the 2px marker landed at 1.5-3.5px -- fully inside the stripe.  On every
 *     facility-scoped rail (planner, ops, gate, admin: four of the five internal roles) the
 *     active marker and the facility colour were painted on top of each other and neither
 *     read correctly.  Two 2-4px vertical bars competing for the same edge is a hazard this
 *     shell creates by design; the clearance is the mitigation.
 *
 *  4. **The expanded rail overlays; it never pushes.**  Reflow under the cursor is the same
 *     class of error as re-sorting under a click (U19).
 *
 * The carrier rail carries **no facility stripe**: carriers are scoped by `carrier_id`, not
 * by facility (section 7.5.6), so there is no facility to colour.
 */
export function IconRail({
  role,
  activeFacility,
  expanded: controlledExpanded,
  landmarkSuffix,
}: {
  role: RoleName
  activeFacility: Facility | null
  /** Forces the expanded overlay open.  Used by the states gallery; in the app the rail
   *  expands on hover/focus and `Cmd/Ctrl+B` pins it. */
  expanded?: boolean
  /** Gallery-only.  A real session has exactly one rail, so the landmark name is unique by
   *  construction; the states gallery renders three side by side and would otherwise give a
   *  screen-reader user duplicate navigation landmark names on one page. */
  landmarkSuffix?: string
}) {
  const [hovered, setHovered] = useState(false)
  const destination = railDestinationFor(role)

  // The driver has no rail at all -- the PWA runs 320-768px and carries its own chrome.
  if (!destination) return null

  const Icon = SURFACE_ICON[destination.surface]
  const expanded = controlledExpanded ?? false
  const stripeColor = activeFacility ? `var(--facility-${activeFacility.accent})` : undefined

  return (
    <nav
      // Distinct landmark label.  Three <nav aria-label="Main"> on one page gives a
      // screen-reader user three identically-named navigation landmarks -- found by the
      // web-design-guidelines audit of section G.
      aria-label={`Main — ${destination.surface}${landmarkSuffix ? `, ${landmarkSuffix}` : ''}`}
      className="relative z-shell flex w-14 shrink-0 flex-col items-center gap-1 border-r border-input bg-card py-2"
      style={
        stripeColor
          ? // U40's 4px facility accent stripe, outer edge.  One of exactly TWO places
            // facility accent may appear in this product.
            { borderInlineStart: `4px solid ${stripeColor}` }
          : undefined
      }
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <RailItem
        to={destination.path}
        icon={Icon}
        label={destination.label}
        showTooltip={hovered && !expanded}
      />

      {expanded ? (
        // No aria-label here.  This is the same navigation landmark in its expanded
        // presentation, not a second one -- and `aria-label` on a plain <div> with no role
        // is inert anyway, which is the kind of dead attribute that reads as accessible
        // without being it.  The <nav> above owns the landmark.
        <div className="absolute inset-y-0 left-0 z-rail-expand flex w-60 flex-col gap-1 border-r border-floating-border bg-popover p-2 shadow-floating">
          <RailItem to={destination.path} icon={Icon} label={destination.label} expanded />
        </div>
      ) : null}
    </nav>
  )
}

function RailItem({
  to,
  icon: Icon,
  label,
  showTooltip,
  expanded,
}: {
  to: string
  icon: LucideIcon
  label: string
  showTooltip?: boolean
  expanded?: boolean
}) {
  const tooltipId = `rail-tip-${to.replace(/\W+/g, '-')}`

  return (
    <NavLink
      to={to}
      end={false}
      aria-describedby={showTooltip ? tooltipId : undefined}
      className={({ isActive }) =>
        cn(
          'relative grid place-items-center rounded-md text-muted-foreground',
          // `tap-floor` (issue #91): the collapsed rail item draws 40x40, which is under the
          // 44px --tap of every `comfortable` surface. The invisible ::after brings the target
          // to the floor without touching the 56px rail's geometry or the item's own box.
          // ::after and not ::before ON PURPOSE -- ::before below is the active-marker accent
          // bar, and a second ::before rule here would silently delete it.
          'tap-floor',
          'transition-colors duration-(--d-fast) ease-(--e-out) hover:bg-hover hover:text-foreground',
          'outline-none focus-visible:outline-2 focus-visible:outline-ring focus-visible:-outline-offset-2',
          expanded ? 'h-10 w-full justify-start gap-3 px-3 text-body' : 'size-10',
          isActive && 'text-foreground',
          // 2px inner accent bar, never a background fill.  In the collapsed rail it sits
          // at -3.5px, which lands it 6-8px from the rail's outer edge: a measured 2px clear
          // of the 0-4px facility stripe.  In the expanded overlay there is no stripe to
          // clear, so it sits flush.
          isActive &&
            (expanded
              ? 'before:absolute before:inset-y-2 before:left-0 before:w-0.5 before:rounded-[1px] before:bg-primary before:content-[""]'
              : 'before:absolute before:inset-y-2 before:-left-[3.5px] before:w-0.5 before:rounded-[1px] before:bg-primary before:content-[""]'),
        )
      }
    >
      {({ isActive }) => (
        <>
          <Icon className="size-6" aria-hidden="true" />
          {expanded ? <span>{label}</span> : <span className="sr-only">{label}</span>}
          {isActive ? <span className="sr-only">(current)</span> : null}
          {showTooltip && !expanded ? (
            <span
              role="tooltip"
              id={tooltipId}
              // z-tooltip, and shadow-floating: elevation-and-depth.md names tooltips at
              // Level 3 explicitly.  left:calc(100% + 16px) -- see the note above.
              className="pointer-events-none absolute top-1/2 left-[calc(100%+16px)] z-tooltip -translate-y-1/2 rounded-md bg-inverse px-2 py-1.5 text-xs font-medium whitespace-nowrap text-inverse-foreground shadow-floating"
            >
              {label}
            </span>
          ) : null}
        </>
      )}
    </NavLink>
  )
}
