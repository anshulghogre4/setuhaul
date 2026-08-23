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
        """Read-only fleet persona (E2.3, M15) -- own carrier_id only, never global."""
        return self.role_name == RoleName.CARRIER

    @property
    def is_operator(self) -> bool:
        """Facility-scoped ops personas (shared ops portal + operator password bucket)."""
        return self.role_name in {
            RoleName.OPERATIONS_EXECUTIVE,
            RoleName.WAREHOUSE_PLANNER,
            RoleName.OPERATIONS_MANAGER,
            RoleName.FACILITY_MANAGER,
        }

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
        requires a cross-carrier id to be refused server-side, not merely hidden, and a carrier
        user is never one of the roles `has_global_read_scope` names. `has_global_read_scope`
        stays facility-only on purpose -- widening it to also mean "any carrier" would let an
        ADMIN/ops persona's read reach silently expand to carrier data the moment this method
        existed, which is exactly the "silent scope widening" issue #23's rollback note warns
        against.
        """
        if not self.is_carrier:
            return False
        if carrier_id is None:
            return False
        return self.carrier_id == carrier_id
