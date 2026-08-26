import type { Facility, Identity } from '@/core/auth/identity'
import type { NotificationItem } from '@/components/shell/notifications-panel'
import type { RecentSearch, SearchResult } from '@/components/shell/search-palette'

/**
 * Fixtures for the states gallery ONLY.  Never imported by an application route.
 *
 * Every value here is copied from `mockup-shared-shell.html` / `stitch-prompts-shared-shell.md`
 * rather than invented -- operational data is not something to make up, and the reference
 * board is the one place these strings are authorised.
 *
 * ⚠ Only TWO facility names exist in any document in scope (Jaipur DC, Gurugram Cross-Dock)
 * against section 2's six facilities.  The remaining four hues are already fixed in color.md
 * and assigned by creation order; the names are not stated anywhere and are deliberately not
 * invented here.
 */

export const FACILITIES: Facility[] = [
  { id: 'FAC-JAI-01', name: 'Jaipur DC', accent: 1 },
  { id: 'FAC-GGN-01', name: 'Gurugram Cross-Dock', accent: 2 },
]

export const PLANNER_MULTI_ROLE: Identity = {
  userId: 'USR-DEMO-PLANNER',
  fullName: 'Priya Nair',
  initials: 'PN',
  email: 'priya.nair@setuhaul.in',
  activeRole: 'WAREHOUSE_PLANNER',
  activeRoleLabel: 'Warehouse Planner',
  grants: [
    { role: 'WAREHOUSE_PLANNER', roleLabel: 'Warehouse Planner', scopeLabel: 'Jaipur DC' },
    { role: 'OPERATIONS_MANAGER', roleLabel: 'Operations Manager', scopeLabel: 'All facilities' },
    { role: 'GATE_OFFICER', roleLabel: 'Gate Officer', scopeLabel: 'Gurugram Cross-Dock' },
  ],
  facilities: FACILITIES,
  activeFacilityId: 'FAC-JAI-01',
  canSelectAllFacilities: false,
  carrierId: null,
}

export const GATE_SINGLE_ROLE: Identity = {
  userId: 'USR-DEMO-GATE',
  fullName: 'Rahul Sethi',
  initials: 'RS',
  email: 'rahul.sethi@setuhaul.in',
  activeRole: 'GATE_OFFICER',
  activeRoleLabel: 'Gate Officer',
  grants: [{ role: 'GATE_OFFICER', roleLabel: 'Gate Officer', scopeLabel: 'Gurugram Cross-Dock' }],
  facilities: [FACILITIES[1]],
  activeFacilityId: 'FAC-GGN-01',
  canSelectAllFacilities: false,
  carrierId: null,
}

/** Carrier: no facilities, no switcher, no rail stripe -- scoped by carrier_id. */
export const CARRIER: Identity = {
  userId: 'USR-DEMO-CARRIER',
  fullName: 'Devi Menon',
  initials: 'DM',
  email: 'devi.menon@example.in',
  activeRole: 'TRANSPORT_MANAGER',
  activeRoleLabel: 'Transport Manager',
  grants: [{ role: 'TRANSPORT_MANAGER', roleLabel: 'Transport Manager', scopeLabel: 'Kota Roadlines' }],
  facilities: [],
  activeFacilityId: null,
  canSelectAllFacilities: false,
  carrierId: 'CAR001',
}

/** Cross-facility ops: the only roles that get "All facilities". */
export const OPS_MANAGER: Identity = {
  ...PLANNER_MULTI_ROLE,
  activeRole: 'OPERATIONS_MANAGER',
  activeRoleLabel: 'Operations Manager',
  canSelectAllFacilities: true,
}

export const NOTIFICATIONS: NotificationItem[] = [
  {
    id: 'n1',
    title: 'Escalation raised',
    reference: 'ESC-4471',
    body: 'No feasible slot for the Kota load at Jaipur DC.',
    timestamp: '2m',
    unread: true,
    href: '#',
  },
  {
    id: 'n2',
    title: 'Slot confirmed',
    reference: 'APT-1042',
    // Every operational time carries its dock AND its date.
    body: 'Dock D1 · Tue 4 Aug · 13:00–14:15, Jaipur DC.',
    timestamp: '18m',
    unread: true,
    href: '#',
  },
  {
    id: 'n3',
    title: 'Policy published',
    reference: 'v12',
    body: 'Fairness weights changed by A. Rao.',
    timestamp: '1h',
    unread: true,
    href: '#',
  },
  {
    id: 'n4',
    title: 'Appointment changed',
    reference: 'APT-1039',
    body: 'Moved to Dock D2 · Tue 4 Aug · 09:30–10:45, Jaipur DC.',
    timestamp: 'Tue',
    unread: false,
    href: '#',
  },
]

export const SEARCH_RESULTS: SearchResult[] = [
  {
    id: 's1',
    group: 'Shipments',
    identifier: 'SHP1015',
    meta: 'Kota load · Reefer · due Tue 4 Aug 08:45',
    href: '#',
  },
  {
    id: 's2',
    group: 'Shipments',
    identifier: 'SHP1004',
    meta: 'Kota load → IndustrialHub · Standard · due Tue 4 Aug 18:00',
    href: '#',
  },
  {
    id: 's3',
    group: 'Appointments',
    identifier: 'APT-1042',
    meta: 'Dock D1 · Tue 4 Aug · 13:00–14:15 · Jaipur DC',
    href: '#',
  },
  { id: 's4', group: 'Drivers', identifier: 'DRV-207', meta: 'Manoj Kumar · Kota depot', href: '#' },
]

export const RECENT_SEARCHES: RecentSearch[] = [
  { id: 'r1', query: 'SHP1015' },
  { id: 'r2', query: 'Dock D1 Tue' },
  { id: 'r3', query: 'Manoj' },
]
