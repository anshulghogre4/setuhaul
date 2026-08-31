import { useCallback, useEffect, useMemo, useState } from 'react'

import { listFacilities } from './api'
import type { AdminFacility } from './types'

/**
 * The facility directory this console reads once per tab and hands to everything that needs a
 * facility id or a facility name.
 *
 * ## What this replaces, and why the replacement is not merely tidier
 *
 * This module supersedes `lib/facility-names.ts`, which held a **hardcoded two-entry name map**
 * plus a `facilityOptionsFrom()` helper that derived the option list from the `facility_id` values
 * that happened to appear in already-loaded user and rule rows. That approach had two defects, and
 * only the first was ever visible:
 *
 *  1. **Self-narrowing.** Selecting "Jaipur" made the response contain only Jaipur users, so every
 *     other facility vanished from the dropdown that had just filtered them out. It was patched by
 *     accumulating ids across loads into a `knownFacilityIds` set — a workaround, and one whose
 *     correctness rested on the first load happening to be unfiltered.
 *  2. **Structurally incomplete, and the accumulator could not fix it.** A facility with no users
 *     and no rules appears in no row, so it was unpickable — meaning a newly-opened facility could
 *     never receive its *first* user through the UI. That is issue #78's actual report, and it is
 *     the reason the accumulator was deleted outright rather than kept alongside the real read:
 *     stacking a workaround on top of the fix would leave two sources of the same list, one of
 *     which is wrong in exactly the case the other exists to serve.
 *
 * `GET /api/v1/admin/facilities` now answers both, so names come from `facilities.facility_name`
 * instead of a two-entry constant that could only ever be stale.
 *
 * ## Why a hook per tab rather than one fetch at the console
 *
 * The Users tab and the Facility Rules tab are the only consumers, they are mounted only while
 * selected (`admin-console.tsx` renders one panel's children at a time), and each already owns its
 * own load/failure state inside its own `RegionErrorBoundary`. Hoisting this to the shell would add
 * a fourth load state above four tabs, three of which do not need it, to save one request against a
 * dimension table with a handful of rows. Per-tab keeps the existing isolation property: a
 * facilities read that fails on Rules cannot blank the Users tab.
 */

export type FacilityDirectoryState = 'loading' | 'ready' | 'failed'

export type FacilityDirectory = {
  state: FacilityDirectoryState
  /**
   * Every facility the server returned, in its own `facility_name` order — closed ones included.
   *
   * This is the list a **filter** uses: a user scoped to a facility that has since been closed must
   * still be findable, and a filter that could not name that facility would hide them.
   */
  all: AdminFacility[]
  /**
   * The facilities a **new** scope assignment may name — `active_flag = 1` only.
   *
   * Note this is a client-side courtesy, not a guarantee: `_validate_scope` existence-checks the id
   * but does not check `active_flag`, so the server would accept a closed facility. Narrowing the
   * picker is the honest thing to offer; it is not a security boundary and is not described as one.
   */
  assignable: AdminFacility[]
  /** Display name for an id. An id the server did not return renders as itself, never a guess. */
  nameOf: (facilityId: string) => string
  reload: () => void
}

/** The pure half, so the states gallery can render the same components without a hook or a fetch. */
export function facilityNameFrom(facilities: AdminFacility[], facilityId: string): string {
  return facilities.find((f) => f.facility_id === facilityId)?.facility_name ?? facilityId
}

export function useFacilities(): FacilityDirectory {
  const [state, setState] = useState<FacilityDirectoryState>('loading')
  const [items, setItems] = useState<AdminFacility[]>([])

  const load = useCallback(async () => {
    setState('loading')
    try {
      const result = await listFacilities()
      setItems(result.items)
      setState('ready')
    } catch {
      // The list stays empty and the state says so. Callers render an explicit "no facility can be
      // selected" note rather than a silently short dropdown — an empty <select> and a failed read
      // are different facts, and the invite form's scope gate depends on telling them apart.
      setItems([])
      setState('failed')
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const nameOf = useCallback(
    (facilityId: string) => facilityNameFrom(items, facilityId),
    [items],
  )

  const assignable = useMemo(() => items.filter((f) => Number(f.active_flag) === 1), [items])

  return {
    state,
    all: items,
    assignable,
    nameOf,
    reload: () => {
      void load()
    },
  }
}
