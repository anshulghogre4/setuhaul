import { useCallback, useRef, useState } from 'react'
import { Route, Routes } from 'react-router-dom'

import { NotFound } from '@/components/states/region-states'
import type { Identity } from '@/core/auth/identity'
import { CarrierDashboard } from './screens/dashboard'
import { CarrierShipmentDetail } from './screens/shipment-detail'
import { useFleetDashboard } from './lib/use-fleet-dashboard'

/**
 * E5.5 (issue #40) — the carrier portal. **Entirely read-only, `carrier_id`-scoped.**
 *
 * Mount inside the shared shell at `/carrier/*`. Two screens, one detail destination:
 *
 *   /carrier                          → dashboard (`screens.md` §1)
 *   /carrier/shipments/:shipmentId    → read-only detail (`screens.md` §2)
 *
 * ## The read-only guarantee is the SERVER's, and this component must not imitate it
 *
 * Verified in source during this build, not assumed from a docstring:
 * `backend/app/api/v1/routers/carrier.py` contains five `@router.get` and zero
 * POST/PATCH/DELETE; `services/carrier_reads.py` has no `session.commit()` anywhere;
 * every statement in `repositories/carrier.py` carries `carrier_id = :carrier_id` in its own
 * `WHERE`; and `repositories/scope.resolve_carrier_scope(ctx)` takes **no parameter at all**
 * beyond the context, so there is no wire format — path, query or body — in which a client
 * could name a carrier other than its own (M15).
 *
 * **So there is deliberately no client-side scope check anywhere in this feature.** Rendering
 * one would produce a guard that looks load-bearing and protects nothing, and the first person
 * to read it would reasonably assume the real check lives here. This surface renders what the
 * server returns and renders the refusal when the server refuses.
 *
 * ## Why the dashboard's data lives up here
 *
 * `flows-and-states.md` Flow 3 step 4: "Back returns to the dashboard with the shipment list's
 * scroll position and filter preserved — a carrier checking on several shipments in sequence
 * shouldn't lose their place each time." This component does not unmount when the detail route
 * renders, so holding the fleet data, the active filter, the scroll offset and the
 * last-opened-row id here is what makes that true — the alternative, refetching on every back
 * navigation, would lose all four and re-spend four requests to do it.
 *
 * ## What this surface deliberately has none of
 *
 * No tabs (the three sections are sections, not tabs — `identity.ts`'s rail comment says so
 * explicitly), no facility switcher or filter, no date-range picker (the 30-day window is fixed
 * by decision *and* by `carrier_reads._SUPPORTED_WINDOWS`), no sort control, no live updates, no
 * bulk select, and no action of any kind.
 */
export function CarrierPortal({ identity }: { identity: Identity }) {
  const state = useFleetDashboard()

  // Preserved across the round trip to detail and back. Plain refs/state on a component that
  // stays mounted, rather than a store: nothing else needs to read them.
  const scrollRef = useRef(0)
  const [returnTo, setReturnTo] = useState<string | null>(null)
  const handleOpened = useCallback((shipmentId: string) => setReturnTo(shipmentId), [])
  const clearReturnTo = useCallback(() => setReturnTo(null), [])

  return (
    <Routes>
      <Route
        index
        element={
          <CarrierDashboard
            carrierName={carrierNameFrom(identity)}
            state={state}
            returnToShipmentId={returnTo}
            onReturnFocusHandled={clearReturnTo}
            scrollRef={scrollRef}
          />
        }
      />
      <Route
        path="shipments/:shipmentId"
        element={<CarrierShipmentDetail onOpened={handleOpened} />}
      />
      <Route
        path="*"
        element={<NotFound backHref="/carrier" backLabel="Back to dashboard" />}
      />
    </Routes>
  )
}

/**
 * The carrier's own display name for the dashboard heading.
 *
 * `screens.md` §1 calls this "the account context" and puts it where other consoles put a
 * facility switcher. It comes from the identity's own grant scope label (`Kota Roadlines`),
 * because **no §7.5.6 payload returns a carrier name** — `_scope_block` returns
 * `{carrier_id, read_only}` and nothing else, which is correct for a scope block and simply
 * isn't a display name. Falls back to the role label rather than rendering a bare id: showing
 * `CAR001` as a company name would be showing plumbing.
 */
function carrierNameFrom(identity: Identity): string {
  const grant = identity.grants.find((g) => g.role === identity.activeRole)
  return grant?.scopeLabel ?? identity.activeRoleLabel
}
