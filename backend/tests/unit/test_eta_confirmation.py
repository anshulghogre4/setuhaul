from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.execution_context import ExecutionContext, RoleName
from app.services import eta_service
from app.services.eta_service import (
    ALLOWED_EXCEPTION_TYPES,
    AUDIT_ACTION_UPDATE_ETA,
    EtaUpdateCommand,
    confirmation_preview,
    format_eta_display,
    record_eta_update,
)
from app.services.idempotency import payload_hash


def test_audit_action_type_matches_baseline_check():
    # Baseline CHECK allows UPDATE_ETA, not synonyms like ETA_UPDATE.
    assert AUDIT_ACTION_UPDATE_ETA == "UPDATE_ETA"


def test_default_exception_type_is_allowed():
    cmd = EtaUpdateCommand(declared_eta_ts="2026-08-07T21:00:00+05:30")
    assert cmd.exception_type in ALLOWED_EXCEPTION_TYPES
    assert "LATE_ETA" not in ALLOWED_EXCEPTION_TYPES


def test_repair_duration_is_not_treated_as_eta_in_preview():
    cmd = EtaUpdateCommand(
        declared_eta_ts="2026-08-07T20:30:00+05:30",
        repair_duration_min=45,
        confirmed=False,
    )
    preview = confirmation_preview(cmd)
    assert preview["status"] == "CONFIRMATION_REQUIRED"
    assert preview["repair_duration_min"] == 45
    assert "Repair duration is not an ETA" in preview["note"]


def test_format_eta_display_includes_timezone():
    text = format_eta_display("2026-08-07T20:30:00+05:30")
    assert "2026-08-07" in text
    assert "Asia/Kolkata" in text


def test_payload_hash_stable():
    a = payload_hash({"b": 1, "a": 2})
    b = payload_hash({"a": 2, "b": 1})
    assert a == b
    assert a != payload_hash({"a": 2, "b": 3})


def test_confirmation_required_without_confirmed_flag():
    cmd = EtaUpdateCommand(declared_eta_ts="2026-08-07T21:00:00+05:30", confirmed=False)
    preview = confirmation_preview(cmd)
    assert preview["requires_confirmation"] is True
    assert preview["declared_eta_ts"] == "2026-08-07T21:00:00+05:30"


# --- Issue #47: E1.1 timestamptz bind types ----------------------------------------------
# `eta_updates.declared_eta_ts / created_at` and `shipments.latest_eta_ts / updated_at` became
# `timestamptz` in E1.1, while `chat_messages`, `driver_exceptions` and `audit_logs` were
# deliberately left as `text`. asyncpg refuses a `str` for the former and a `datetime` for the
# latter, so this one write path has to bind both shapes correctly at the same time. A mock session
# never encodes a parameter, which is why every one of these has to be asserted explicitly.

_TIMESTAMPTZ_BINDS = {
    "public.eta_updates": ("declared_eta_ts", "created_at"),
    "public.shipments": ("latest_eta_ts", "updated_at"),
}
_TEXT_BINDS = {
    "public.chat_messages": ("message_ts", "extracted_eta_ts"),
    "public.driver_exceptions": ("reported_at", "declared_eta_ts"),
    "public.audit_logs": ("created_at",),
    "public.chat_threads": ("opened_at",),
}


def _driver_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="req",
        auth_subject="auth",
        user_id="USR001",
        email="ravi.kumar@setuhaul.com",
        full_name="Ravi Kumar",
        role_id="ROL001",
        role_name=RoleName.DRIVER,
        driver_id="DRV001",
    )


@pytest.mark.asyncio
async def test_record_eta_update_binds_datetimes_and_strings_to_the_right_columns(monkeypatch):
    session = AsyncMock()
    session.execute.return_value = MagicMock()
    session.execute.return_value.mappings.return_value.first.return_value = None

    monkeypatch.setattr(eta_service, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(eta_service, "store_idempotency", AsyncMock())
    monkeypatch.setattr(
        eta_service,
        "_assert_driver_owns_shipment",
        AsyncMock(return_value={"shipment_id": "SHP1017", "driver_id": "DRV001",
                                "destination_facility_id": "FAC-JAI-01",
                                "latest_eta_ts": None, "original_eta_ts": None}),
    )
    monkeypatch.setattr(eta_service, "_ensure_thread", AsyncMock(return_value="THR001"))
    monkeypatch.setattr(eta_service, "_reread", AsyncMock(return_value={"status": "PERSISTED"}))

    await record_eta_update(
        session,
        ctx=_driver_ctx(),
        shipment_id="SHP1017",
        command=EtaUpdateCommand(
            declared_eta_ts="2026-08-07T21:00:00+05:30",
            confirmed=True,
            confirmation_eta_ts="2026-08-07T21:00:00+05:30",
        ),
        idempotency_key="eta-bind-key",
    )

    checked = 0
    for call in session.execute.await_args_list:
        if len(call.args) < 2 or not isinstance(call.args[1], dict):
            continue
        sql, params = str(call.args[0]), call.args[1]
        for table, columns in _TIMESTAMPTZ_BINDS.items():
            if table not in sql:
                continue
            for column in columns:
                if column in params:
                    assert isinstance(params[column], datetime), (
                        f"{table}.{column} is timestamptz after E1.1 but was bound as "
                        f"{type(params[column]).__name__}; asyncpg would raise DataError."
                    )
                    checked += 1
        for table, columns in _TEXT_BINDS.items():
            if table not in sql:
                continue
            for column in columns:
                if column in params:
                    assert isinstance(params[column], str), (
                        f"{table}.{column} was deliberately left as text by E1.1 and must stay a "
                        f"string bind; a datetime raises the mirror-image asyncpg DataError."
                    )
                    checked += 1

    # eta_updates x2 (declared_eta_ts, created_at), shipments x2 (latest_eta_ts, updated_at),
    # chat_messages x2, driver_exceptions x2 (the INSERT branch -- this fixture has no open
    # exception, so the UPDATE branch is not exercised here), audit_logs x1.
    assert checked == 9
