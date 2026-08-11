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
    is_active: bool = True
    permissions: list[str] = Field(default_factory=list)

    @property
    def is_driver(self) -> bool:
        return self.role_name == RoleName.DRIVER

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
        """Global read-only ops personas (shared ops portal + admin password bucket)."""
        return self.role_name in {
            RoleName.ADMIN,
            RoleName.TRANSPORT_MANAGER,
            RoleName.REGIONAL_OPERATIONS_HEAD,
        }

    def assert_driver_self(self, driver_id: str | None) -> bool:
        return self.is_driver and self.driver_id is not None and self.driver_id == driver_id

    def can_read_facility(self, facility_id: str | None) -> bool:
        if self.is_admin:
            return True
        if facility_id is None:
            return False
        return self.facility_id == facility_id
