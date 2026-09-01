from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class RoleName(StrEnum):
    DRIVER = "DRIVER"
    OPERATIONS_EXECUTIVE = "OPERATIONS_EXECUTIVE"
    WAREHOUSE_PLANNER = "WAREHOUSE_PLANNER"
    OPERATIONS_MANAGER = "OPERATIONS_MANAGER"
    FACILITY_MANAGER = "FACILITY_MANAGER"
    TRANSPORT_MANAGER = "TRANSPORT_MANAGER"
    REGIONAL_OPERATIONS_HEAD = "REGIONAL_OPERATIONS_HEAD"
    ADMIN = "ADMIN"
    # E2.3 (issue #23, M15): read-only fleet visibility, scoped to the caller's own carrier_id.
    # Added alongside the existing facility-scoped roles, not replacing anything -- the S7.5.6
    # carrier portal tool catalog (M3) has nowhere to attach without this.
    CARRIER = "CARRIER"
    # Issue #79 (owner-approved 2026-08-29), superseding the 2026-08-24 mapping decision that ran
    # the kiosk under WAREHOUSE_PLANNER/FACILITY_MANAGER. SOLUTION_DESIGN.md section 2 marks
    # "Gate / yard officer" as a v1 persona with its own surface, section 7.5.2 gives it five tools
    # of its own, and UI-UX/00-foundations/auth-and-scoping.md gives it a role-landing row plus a
    # "never sees: scheduling controls" row -- none of which the borrowed planner identity could
    # honour. See api/v1/routers/gate.py's docstring for the least-privilege argument.
    GATE_OFFICER = "GATE_OFFICER"


# Issue #101 (owner decision (a), 2026-09-01). Who may work the §7.5.6 carrier portal.
#
# The problem this fixes, stated plainly: **no account in the system could use the carrier surface
# at all.** `CARRIER` (ROL009) exists as a role row -- migration 20260823090000 inserts it -- but
# that same migration's closing comment records that *zero* users hold it ("no CARRIER-scope
# backfill: zero CARRIER-role users exist today"), and none has been provisioned since. The roster's
# carrier persona is `USR105` / sanjay.gupta@setuhaul.com, seeded as `ROL006` = TRANSPORT_MANAGER
# (`supabase/seed.sql:684-696`), and the frontend's `identity-mapping.ts` already maps that account
# to `/carrier/*`. So the five carrier reads answered 403 for the only human who was ever meant to
# call them, and E5.5's nine screens were built against an identity that cannot exist.
#
# Option (b) -- provision a real CARRIER account -- was the backend's original design and is still
# available; (a) was chosen because it matches the UI mapping and the seeded roster without a new
# identity to manage. Adding `TRANSPORT_MANAGER` here does **not** widen its reach:
# `resolve_carrier_scope` and `can_read_carrier` both still require a non-NULL `carrier_id`, which
# comes only from a `user_scopes` row of `scope_type='CARRIER'` for that user (`core/deps.py`), and
# every carrier query then filters on that single id. A TRANSPORT_MANAGER without such a row gets
# `CARRIER_UNMAPPED`, not the whole fleet table -- so this is "one more role may hold a carrier
# scope", never "a global-read persona may read every carrier".
#
# That is also why `can_read_carrier` still refuses to fall back to `has_global_read_scope`: the
# reach is granted by an explicit per-user scope row, not by role seniority.
CARRIER_PORTAL_ROLES = frozenset({RoleName.CARRIER, RoleName.TRANSPORT_MANAGER})


class ExecutionContext(BaseModel):
    """Trusted request identity derived server-side from a verified JWT + DB mapping."""

    model_config = ConfigDict(frozen=True)

    request_id: str
    auth_subject: str
    user_id: str
    email: str
    full_name: str
    role_id: str
    role_name: RoleName
    driver_id: str | None = None
    facility_id: str | None = None
    # E2.3 (issue #23, M15): the carrier scope, read from user_scopes (scope_type='CARRIER'),
    # not from a column on users -- user_scopes is the identity model's source of truth for this,
    # the same way driver_id/facility_id are columns on users only because they predate it.
    carrier_id: str | None = None
    is_active: bool = True
    permissions: list[str] = Field(default_factory=list)

    @property
    def is_driver(self) -> bool:
        return self.role_name == RoleName.DRIVER

    @property
    def is_carrier(self) -> bool:
        """Read-only fleet persona (E2.3, M15) -- own carrier_id only, never global.

        Membership of `CARRIER_PORTAL_ROLES` rather than `== RoleName.CARRIER` since issue #101 --
        see that constant for why, and for why this is not a scope widening. The `carrier_id`
        check every caller performs afterwards is unchanged and is what actually bounds the read.
        """
        return self.role_name in CARRIER_PORTAL_ROLES

    @property
    def is_operator(self) -> bool:
        """Facility-scoped ops personas (shared ops portal + operator password bucket).

        `GATE_OFFICER` is deliberately **not** here, the same way `CARRIER` is not. This flag is
        what `repositories/scope.py`'s escalation/takeover/search write gates check, and
        `auth-and-scoping.md`'s "What each role never sees" table gives the gate officer
        "Scheduling controls" as a never -- so folding it into `is_operator` would hand a
        device-bound kiosk credential escalation and takeover authority by inheritance rather
        than by decision. Its one legitimate write reach is expressed by `is_gate_officer` plus
        `repositories.scope.assert_gate_write_scope` instead.
        """
        return self.role_name in {
            RoleName.OPERATIONS_EXECUTIVE,
            RoleName.WAREHOUSE_PLANNER,
            RoleName.OPERATIONS_MANAGER,
            RoleName.FACILITY_MANAGER,
        }

    @property
    def is_gate_officer(self) -> bool:
        """The gate/yard kiosk persona (issue #79) -- facility-scoped, section 7.5.2 writes only.

        Facility reach comes from the ordinary `facility_id` column, so `can_read_facility` and
        `repositories.scope.resolve_facility_scope` already behave correctly for this role with no
        change: it is not `has_global_read_scope`, so both resolve to its own facility or refuse.

        The session behind this role is *device-bound and has no idle timeout*
        (`auth-and-scoping.md` "Session expiry"; `frontend/src/core/auth/identity.ts`
        `idlePolicyFor` returns null for it), which is precisely why it must be the narrowest role
        that can do the job rather than a borrowed planner login.
        """
        return self.role_name == RoleName.GATE_OFFICER

    @property
    def is_admin(self) -> bool:
        """Write-authorised global persona.

        This is the flag every *mutating* path checks (escalation resolve, dispatch create,
        appointment confirm/reject/expire/cancel/reschedule), so only ADMIN belongs here.
        TRANSPORT_MANAGER and REGIONAL_OPERATIONS_HEAD were previously included, which handed
        two personas that hold only `*_read_global` permissions (see ROLE_PERMISSIONS in
        core/deps.py) cross-facility write access — an M15/NFR-019 violation. Their global
        *visibility* now comes from `has_global_read_scope` instead; do not re-add them here.
        """
        return self.role_name == RoleName.ADMIN

    @property
    def has_global_read_scope(self) -> bool:
        """Personas that may read across every facility, whether or not they may write.

        Deliberately distinct from `is_admin`: read reach and write authority were one flag
        before, so widening visibility for a read-only persona silently widened its writes too.
        Read paths check this; write paths check `is_admin`.
        """
        return self.role_name in {
            RoleName.ADMIN,
            RoleName.TRANSPORT_MANAGER,
            RoleName.REGIONAL_OPERATIONS_HEAD,
        }

    def assert_driver_self(self, driver_id: str | None) -> bool:
        return self.is_driver and self.driver_id is not None and self.driver_id == driver_id

    def can_read_facility(self, facility_id: str | None) -> bool:
        if self.has_global_read_scope:
            return True
        if facility_id is None:
            return False
        return self.facility_id == facility_id

    def can_read_carrier(self, carrier_id: str | None) -> bool:
        """A carrier persona reads only its own fleet -- never global, unlike facility scope.

        Deliberately does not fall back to `has_global_read_scope`: SOLUTION_DESIGN.md line 1290
        requires a cross-carrier id to be refused server-side, not merely hidden.
        `has_global_read_scope` stays facility-only on purpose -- widening it to also mean "any
        carrier" would let an ADMIN/ops persona's read reach silently expand to carrier data the
        moment this method existed, which is exactly the "silent scope widening" issue #23's
        rollback note warns against.

        Since issue #101 a carrier-portal caller *can* be one of the roles `has_global_read_scope`
        names (TRANSPORT_MANAGER holds global *facility* read reach), which makes the paragraph
        above load-bearing rather than incidental: that persona's carrier reach is still exactly
        the one `carrier_id` names and nothing more. Its global reach over facilities and its
        single-carrier reach over fleets are two independent scoping dimensions, and neither is
        allowed to imply the other.
        """
        if not self.is_carrier:
            return False
        if carrier_id is None:
            return False
        return self.carrier_id == carrier_id
