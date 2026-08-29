/**
 * E5.6 (issue #41) — admin console. The two things `App.tsx` needs from this feature.
 *
 * A barrel exists here specifically because this build could not edit `App.tsx` (two other
 * surface builds were writing the same tree concurrently), so the coordinator wires the route in
 * one place afterwards. See the report accompanying this build for the exact JSX.
 *
 * Expected wiring:
 *
 *   import { ADMIN_IDENTITY, AdminConsole } from '@/features/admin'
 *   ...
 *   <Route path="/admin" element={<AdminRoute />} />
 *
 *   function AdminRoute() {
 *     return (
 *       <ShellRoute identity={ADMIN_IDENTITY}>
 *         <AdminConsole currentUserId={ADMIN_IDENTITY.userId} />
 *       </ShellRoute>
 *     )
 *   }
 *
 * `currentUserId` is threaded in rather than read from a module global because it decides one
 * real thing: whether the Remove action appears on a row at all (`flows-and-states.md` Flow 4
 * point 3 — self-removal is Hidden, not Disabled). When #52 lands and the shell fetches a real
 * identity, that value comes from the same place the shell's does, with no change here.
 */
export { AdminConsole } from './admin-console'
export { ADMIN_IDENTITY } from './admin-identity'
