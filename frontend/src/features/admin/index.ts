/**
 * E5.6 (issue #41) — admin console.
 *
 * `ADMIN_IDENTITY` was exported here until 2026-09-01 and is now **deleted**, which is what its own
 * docstring said should happen: *"When #52 lands and the shell fetches a real identity, this
 * constant is deleted."* `/admin` renders under the signed-in administrator's real identity from
 * `core/auth/auth-context.tsx`, and `App.tsx`'s `AdminRoute` passes `identity.userId` as
 * `currentUserId`.
 *
 * That last part is correctness, not tidiness: `currentUserId` decides whether the Remove action
 * appears on a row at all (`flows-and-states.md` Flow 4 point 3 — self-removal is Hidden, not
 * Disabled), and the fixture's `USR-DEMO-ADMIN` could never match a real `public.users.user_id`,
 * so that guard never actually fired for anyone.
 *
 * ⚠ One observation the deleted fixture recorded and which is still open, carried here so it is not
 * lost with the file: `hasFacilityScope('ADMIN')` returns `true` (`core/auth/identity.ts:137-139`)
 * and would render a facility switcher, while `06-admin-console/screens.md` §1 says this surface has
 * none. It stays harmless because a real admin's `facilities` array is empty (an `ADMIN` row has no
 * `FACILITY` scope in `user_scopes`), so the switcher has nothing to switch between — the same
 * honest encoding the fixture used. Whether `hasFacilityScope` should exclude `ADMIN` outright is
 * an owner call on shared infrastructure.
 */
export { AdminConsole } from './admin-console'
