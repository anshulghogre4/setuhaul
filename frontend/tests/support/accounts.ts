/**
 * The race cast: which real POC account plays each role in the seven suites.
 *
 * **No passwords here.** This file is committed; passwords are resolved at run time by
 * `credentials.ts` from the gitignored roster or from the environment. Every account below is a
 * real row in `public.users` with a live Supabase Auth identity -- the mapping is copied from the
 * gitignored `POC_TEAM_ACCOUNTS.local.md`, and each `userId` / `roleName` / `facilityId` was
 * verified against a live `GET /api/v1/auth/me` on the local backend before being written down
 * (2026-09-01), not transcribed on trust.
 *
 * `userId` is recorded because `storage-state-isolation.spec.ts` asserts the server agrees that
 * two contexts are two different people -- a claim it cannot make from the storage file alone.
 */

export type Bucket = 'Driver' | 'Operations' | 'Admin'

export type Account = {
  /** Stable key; also the storageState filename (`tests/.auth/<key>.json`). */
  key: string
  email: string
  bucket: Bucket
  /** `public.users.user_id`, as returned by `GET /api/v1/auth/me`. */
  userId: string
  roleName: string
  facilityId: string | null
}

/**
 * Two ops executives at the SAME facility is the load-bearing detail for races 3 and 4: an
 * escalation is facility-scoped, so two coordinators can only contend for it if they share
 * `FAC-JAI-01`. `USR101`/`USR107` are the only such pair in the roster.
 *
 * There is exactly ONE `WAREHOUSE_PLANNER` (`USR102`). That is fine -- race 5 is planner *versus
 * the D9 sweeper*, not planner versus planner.
 *
 * Race 6's two contexts are the same account on purpose: `04-gate-yard-kiosk` is one device
 * account driving two device *contexts* (booth and yard tablet), not two humans. They still get
 * two separate storageState files and two separately-minted sessions -- see `auth.setup.ts`.
 */
export const ACCOUNTS = {
  'driver-a': {
    key: 'driver-a',
    email: 'ravi.kumar@setuhaul.com',
    bucket: 'Driver',
    userId: 'USR001',
    roleName: 'DRIVER',
    facilityId: 'FAC-JAI-01',
  },
  'driver-b': {
    key: 'driver-b',
    email: 'amit.singh@setuhaul.com',
    bucket: 'Driver',
    userId: 'USR002',
    roleName: 'DRIVER',
    facilityId: 'FAC-JAI-01',
  },
  /**
   * The isolated reschedule sandbox driver at `FAC-GGN-01`. `POC_TEAM_ACCOUNTS.local.md` records
   * it as "never touched by the cast or `reset_demo_day.py`" -- so it is the only driver identity
   * these suites may safely drive a WRITE through. `driver-a`/`driver-b` are the `SHP-D16-*` demo
   * cast and are read-only here.
   */
  'driver-sandbox': {
    key: 'driver-sandbox',
    email: 'driver.resched@setuhaul.com',
    bucket: 'Driver',
    userId: 'USR-RS-01',
    roleName: 'DRIVER',
    facilityId: 'FAC-GGN-01',
  },
  'ops-a': {
    key: 'ops-a',
    email: 'priya.mehta@setuhaul.com',
    bucket: 'Operations',
    userId: 'USR101',
    roleName: 'OPERATIONS_EXECUTIVE',
    facilityId: 'FAC-JAI-01',
  },
  'ops-b': {
    key: 'ops-b',
    email: 'kavita.rao@setuhaul.com',
    bucket: 'Operations',
    userId: 'USR107',
    roleName: 'OPERATIONS_EXECUTIVE',
    facilityId: 'FAC-JAI-01',
  },
  /**
   * The only `OPERATIONS_EXECUTIVE` at `FAC-GGN-01` -- the facility the write-safe reschedule
   * sandbox lives in. Race 5 needs an ops identity that can confirm/expire an appointment created
   * by `driver-sandbox`, and Jaipur's coordinators cannot: an appointment is facility-scoped.
   */
  'ops-ggn': {
    key: 'ops-ggn',
    email: 'arvind.nair@setuhaul.com',
    bucket: 'Operations',
    userId: 'USR108',
    roleName: 'OPERATIONS_EXECUTIVE',
    facilityId: 'FAC-GGN-01',
  },
  planner: {
    key: 'planner',
    email: 'rahul.verma@setuhaul.com',
    bucket: 'Operations',
    userId: 'USR102',
    roleName: 'WAREHOUSE_PLANNER',
    facilityId: 'FAC-JAI-01',
  },
  /**
   * Gate booth and yard tablet. `WAREHOUSE_PLANNER` is in `GATE_KIOSK_ROLES`
   * (`backend/app/core/deps.py:99-104`, alongside `GATE_OFFICER`, `FACILITY_MANAGER`, `ADMIN`),
   * and the roster has no `GATE_OFFICER` account -- issue #79 added the enum member and the role
   * gate, but no kiosk credential has been provisioned. Recorded as a real limitation on race 6
   * rather than papered over.
   */
  'gate-booth': {
    key: 'gate-booth',
    email: 'rahul.verma@setuhaul.com',
    bucket: 'Operations',
    userId: 'USR102',
    roleName: 'WAREHOUSE_PLANNER',
    facilityId: 'FAC-JAI-01',
  },
  'gate-yard': {
    key: 'gate-yard',
    email: 'rahul.verma@setuhaul.com',
    bucket: 'Operations',
    userId: 'USR102',
    roleName: 'WAREHOUSE_PLANNER',
    facilityId: 'FAC-JAI-01',
  },
  'admin-a': {
    key: 'admin-a',
    email: 'meera.iyer@setuhaul.com',
    bucket: 'Admin',
    userId: 'USR997',
    roleName: 'ADMIN',
    facilityId: null,
  },
  'admin-b': {
    key: 'admin-b',
    email: 'suresh.menon@setuhaul.com',
    bucket: 'Admin',
    userId: 'USR998',
    roleName: 'ADMIN',
    facilityId: null,
  },
} as const satisfies Record<string, Account>

export type RoleKey = keyof typeof ACCOUNTS

export const ROLE_KEYS = Object.keys(ACCOUNTS) as RoleKey[]

/**
 * The role keys that must resolve to genuinely DIFFERENT humans.
 *
 * `gate-booth`/`gate-yard` are excluded because they are deliberately the same account (one
 * device credential, two device contexts) -- asserting they differ would encode a false
 * requirement. Everything else is a distinct `public.users` row and the isolation self-test
 * proves it.
 */
export const DISTINCT_IDENTITY_KEYS: RoleKey[] = [
  'driver-a',
  'driver-b',
  'driver-sandbox',
  'ops-a',
  'ops-b',
  'ops-ggn',
  'planner',
  'admin-a',
  'admin-b',
]
