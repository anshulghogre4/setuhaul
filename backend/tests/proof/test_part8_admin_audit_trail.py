"""Admin-console audit trail -- the regression suite for GitHub issue #80.

Design citation: `ARCHITECTURE/REQUIREMENTS.md` **FR-ADM-009** (*"Every write on this console is
itself an audit entry via the same M14 pipeline -- no weaker path for admin's own actions"*),
`SOLUTION_DESIGN.md` M14 (*"Audit -- every state change and every agent action is reconstructable:
who, what, when, which policy version, which tool call"*) and section 7.5.7,
`UI-UX/06-admin-console/flows-and-states.md` **Flow 9**, `UI-UX/06-admin-console/screens.md` section 5
(the Audit tab this console's own writes are the primary subject of).

**Not one of section 10's six parts.** Section 10 defines six and this is not one of them, exactly
like `test_part7_read_write_agreement.py`: it lives beside them because it needs the same throwaway
cluster, and because what it proves is the same *kind* of thing -- what PostgreSQL actually accepts
and actually keeps, which no mocked session can answer. The file is named for its position in the
run order, not for a section of the design.

## Why this cannot be a unit test

The unit half of this fix lives in `tests/unit/test_e34_admin_console.py` and pins the payloads. It
cannot pin the three things that would actually break in production, all of which are properties of
the database rather than of Python:

* **`audit_logs_action_type_check`.** Sixteen permitted values
  (`supabase/migrations/20260829134929_d2_held_state_dock_occupancy.sql:290-296`), none of them
  admin-console-specific. That migration's own comment records the near-miss precisely: adding
  `CREATE_HOLD` was needed because otherwise *"every `create_hold` would have failed at COMMIT with
  a CheckViolationError -- a 500 on the very first hold a driver took. No unit test could have
  caught it (they mock the session, so no constraint is ever evaluated)."* Issue #80 deliberately
  adds **no** new value, and this file is what proves the six writes stay inside the vocabulary.
* **`audit_logs.user_id` is `NOT NULL REFERENCES users(user_id)`.** An actor id that does not
  resolve is a foreign-key violation at COMMIT, invisible to a mock.
* **The pre-update values.** Production Supabase is PostgreSQL 17.6, so `RETURNING OLD.*` (a
  PostgreSQL **18** feature) is unavailable and `_set_active`/`update_facility_rule` capture their
  before-values through the aliased self-join the `UPDATE` docs sanction. Whether that construct
  really yields the *pre*-update row is a fact about PostgreSQL's execution, not about the SQL
  string -- a mock returning a dict with `previous_is_active` in it proves nothing at all.

## Transaction coupling, proven rather than asserted

FR-ADM-009 is worthless if a write can commit while its audit entry rolls back. The unit tests can
only check call ordering; `test_audit_and_write_commit_or_roll_back_together` here does the real
thing -- forces a failure after the service's own INSERT and before its COMMIT, then reads the
table back to show that *neither* the change nor its audit row survived.

## Isolation from the rest of the suite

The work database is shared with parts 1, 3, 6 and 7, which book slots and take holds at
`FAC-JAI-01`/`FAC-GGN-01`. Two deliberate choices keep this file from perturbing them:

* **Its own users.** `update_user`/`deactivate_user`/`reactivate_user` act on rows this file
  inserts and deletes, never on a seeded account another part might read.
* **`NO_SHOW_GRACE_MIN` for the rule writes.** That type is outside
  `ENGINE_EVALUATED_RULE_TYPES` -- `scheduling/feasibility.py::check_facility_rules` never
  evaluates it -- so a rule this file creates at a real facility cannot change any feasibility
  outcome even while it exists. Picking `LAST_NEW_START_TIME` instead would have been a live
  constraint on every booking the rest of the suite makes.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.services import admin_governance_service, admin_user_service
from tests.proof.evidence import record_evidence

pytestmark = pytest.mark.asyncio(loop_scope="session")

# Seeded rows this file leans on, all read straight out of `supabase/seed.sql`:
#   USR999 / ROL008 -- the ADMIN account, used as the acting admin AND as the audit FK target.
#   ROL002          -- OPERATIONS_EXECUTIVE, the role the throwaway users are created with.
#   FAC-JAI-01      -- a real facility, so `_validate_scope`'s existence check passes.
ADMIN_USER_ID = "USR999"
OPS_ROLE_ID = "ROL002"
FACILITY = "FAC-JAI-01"
OTHER_FACILITY = "FAC-GGN-01"

# The constraint's own value list, transcribed from the migration that last set it. Kept here (not
# imported) on purpose: this is the *database's* vocabulary, and a copy that can drift from the
# application is precisely what the assertion below is for -- it re-reads the live constraint
# definition out of `pg_constraint` and compares, so a migration that widened or narrowed the CHECK
# without anyone noticing fails here.
PERMITTED_ACTION_TYPES = frozenset(
    {
        "LOGIN", "LOGOUT", "VIEW", "CREATE", "UPDATE", "DELETE",
        "BOOK_APPOINTMENT", "CANCEL_APPOINTMENT", "UPDATE_ETA", "SEND_MESSAGE",
        "RESCHEDULE_APPOINTMENT", "REJECT_APPOINTMENT", "EXPIRE_APPOINTMENT",
        "CREATE_HOLD", "CONFIRM_HELD_SLOT", "EXPIRE_HOLD",
    }
)


def _admin_ctx() -> ExecutionContext:
    """A real admin, identified by a `user_id` that genuinely exists in `users`.

    That last part is load-bearing here and nowhere in the unit tests: `audit_logs.user_id` carries
    a foreign key, so an audit entry written on behalf of a fabricated actor fails at COMMIT. Using
    the seeded ADMIN row is what makes this suite exercise the same constraint production does.
    """
    return ExecutionContext(
        request_id="proof-part8", auth_subject="proof", user_id=ADMIN_USER_ID,
        email="admin@setuhaul.com", full_name="System Administrator",
        role_id="ROL008", role_name=RoleName.ADMIN,
    )


async def _make_user(session, *, role_id: str = OPS_ROLE_ID, facility_id: str | None = FACILITY) -> str:
    """Insert a throwaway `users` row and return its id.

    Not created through `invite_user`, deliberately: that tool calls the Supabase Auth admin API,
    which this suite has no business reaching (the orchestrator blanks every Supabase credential in
    the child environment). The six writes under test are all pure-PostgreSQL, so the fixture only
    needs the row to exist.
    """
    user_id = f"USR-AUD-{uuid4().hex[:8].upper()}"
    await session.execute(
        text(
            """
            INSERT INTO public.users (
              user_id, role_id, full_name, email, password_hash, facility_id, is_active, created_at
            ) VALUES (
              :uid, :role_id, 'Audit Fixture', :email, 'MANAGED_BY_SUPABASE_AUTH', :facility_id,
              1, :created_at
            )
            """
        ),
        {
            "uid": user_id, "role_id": role_id, "email": f"{user_id.lower()}@setuhaul.example",
            "facility_id": facility_id, "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO public.user_scopes (scope_id, user_id, scope_type, scope_value, created_at)
            VALUES (:sid, :uid, 'FACILITY', :facility_id, :created_at)
            """
        ),
        {
            "sid": f"SCP-AUD-{uuid4().hex[:8].upper()}", "uid": user_id,
            "facility_id": facility_id, "created_at": datetime.now(timezone.utc),
        },
    )
    await session.commit()
    return user_id


async def _drop_user(session, user_id: str) -> None:
    """Remove the fixture row and everything that points at it, audit rows included.

    Audit rows are deleted only because the *target* is going away with the test; nothing in the
    application ever deletes from `audit_logs`, and this is fixture teardown, not a code path.
    """
    for statement in (
        "DELETE FROM public.audit_logs WHERE entity_id = :uid AND entity_name = 'users'",
        "DELETE FROM public.user_scopes WHERE user_id = :uid",
        "DELETE FROM public.users WHERE user_id = :uid",
    ):
        await session.execute(text(statement), {"uid": user_id})
    await session.commit()


async def _audit_rows(session, *, entity_name: str, entity_id: str) -> list[dict]:
    rows = (
        await session.execute(
            text(
                """
                SELECT audit_id, user_id, action_type, entity_name, entity_id,
                       old_value_json, new_value_json, created_at
                FROM public.audit_logs
                WHERE entity_name = :entity_name AND entity_id = :entity_id
                ORDER BY created_at, audit_id
                """
            ),
            {"entity_name": entity_name, "entity_id": entity_id},
        )
    ).mappings().all()
    decoded = []
    for row in rows:
        item = dict(row)
        item["new_value"] = json.loads(item["new_value_json"]) if item["new_value_json"] else None
        item["old_value"] = json.loads(item["old_value_json"]) if item["old_value_json"] else None
        decoded.append(item)
    return decoded


@pytest_asyncio.fixture(loop_scope="session")
async def fixture_user(work_session):
    user_id = await _make_user(work_session)
    yield user_id
    await _drop_user(work_session, user_id)


# --------------------------------------------------------------------------------------------
# The constraint itself
# --------------------------------------------------------------------------------------------


async def test_the_live_check_constraint_still_carries_the_vocabulary_this_file_assumes(work_session):
    """Read the CHECK out of `pg_constraint` and confirm the sixteen values are what is deployed.

    Every other assertion in this file rests on "no new `action_type` was needed", so that premise
    is verified against the schema rather than remembered. If a later migration widens the
    vocabulary this fails first, pointing at the file to update, instead of the rest of the suite
    failing mysteriously.
    """
    definition = (
        await work_session.execute(
            text(
                """
                SELECT pg_get_constraintdef(oid) AS def
                FROM pg_constraint
                WHERE conrelid = 'public.audit_logs'::regclass
                  AND conname = 'audit_logs_action_type_check'
                """
            )
        )
    ).scalar_one()
    for value in PERMITTED_ACTION_TYPES:
        assert f"'{value}'" in definition, f"{value} is no longer permitted by the live CHECK"
    # And no admin-console-specific verb has crept in as an action_type -- the design keeps those
    # in `new_value_json.event` (see `_write_audit_entry`'s docstring for why).
    for absent in ("UPDATE_USER", "DEACTIVATE_USER", "PUBLISH_POLICY_VERSION", "CREATE_FACILITY_RULE"):
        assert absent not in definition


# --------------------------------------------------------------------------------------------
# The three user-service writes that audited nothing before issue #80
# --------------------------------------------------------------------------------------------


async def test_update_user_writes_a_real_audit_row_with_both_sides_of_the_change(work_session, fixture_user):
    await admin_user_service.update_user(
        work_session, _admin_ctx(), user_id=fixture_user,
        role="FACILITY_MANAGER", scope=[FACILITY, OTHER_FACILITY],
    )

    rows = await _audit_rows(work_session, entity_name="users", entity_id=fixture_user)
    assert len(rows) == 1
    entry = rows[0]
    assert entry["user_id"] == ADMIN_USER_ID          # the FK resolved -- the row actually landed
    assert entry["action_type"] == "UPDATE"
    assert entry["new_value"]["event"] == "UPDATE_USER"
    # The before was read out of the database, not echoed from the request.
    assert entry["old_value"] == {"role": "OPERATIONS_EXECUTIVE", "scope": [FACILITY]}
    assert entry["new_value"]["role"] == "FACILITY_MANAGER"
    assert sorted(entry["new_value"]["scope"]) == sorted([FACILITY, OTHER_FACILITY])

    # ...and the change it claims to record actually happened.
    role_name = (
        await work_session.execute(
            text(
                "SELECT r.role_name FROM public.users u JOIN public.roles r ON r.role_id = u.role_id "
                "WHERE u.user_id = :uid"
            ),
            {"uid": fixture_user},
        )
    ).scalar_one()
    assert role_name == "FACILITY_MANAGER"


async def test_deactivate_and_reactivate_each_write_their_own_entry_with_the_true_before(
    work_session, fixture_user
):
    """The aliased self-join, proven against a real planner rather than a mock.

    `previous_is_active` has to be 1 for the deactivate and 0 for the reactivate. A construct that
    returned the *post*-update value would produce 0 and 1 -- the assertion below is what tells the
    two apart, and it is the only place in this repo where that is actually tested.
    """
    await admin_user_service.deactivate_user(work_session, _admin_ctx(), fixture_user)
    await admin_user_service.reactivate_user(work_session, _admin_ctx(), fixture_user)

    rows = await _audit_rows(work_session, entity_name="users", entity_id=fixture_user)
    assert [row["new_value"]["event"] for row in rows] == ["DEACTIVATE_USER", "REACTIVATE_USER"]
    assert [row["action_type"] for row in rows] == ["UPDATE", "UPDATE"]
    assert rows[0]["old_value"] == {"is_active": 1} and rows[0]["new_value"]["is_active"] == 0
    assert rows[1]["old_value"] == {"is_active": 0} and rows[1]["new_value"]["is_active"] == 1

    is_active = (
        await work_session.execute(
            text("SELECT is_active FROM public.users WHERE user_id = :uid"), {"uid": fixture_user}
        )
    ).scalar_one()
    assert is_active == 1


async def test_a_refused_reactivate_leaves_no_audit_row(work_session, fixture_user):
    """`removed_at` set means the Auth identity is gone; the refusal is not a write, so it must not
    manufacture evidence of one."""
    await work_session.execute(
        text("UPDATE public.users SET removed_at = :ts, is_active = 0 WHERE user_id = :uid"),
        {"ts": datetime.now(timezone.utc), "uid": fixture_user},
    )
    await work_session.commit()

    with pytest.raises(AppError) as exc:
        await admin_user_service.reactivate_user(work_session, _admin_ctx(), fixture_user)
    assert exc.value.code == "USER_REMOVED"
    await work_session.rollback()

    assert await _audit_rows(work_session, entity_name="users", entity_id=fixture_user) == []


# --------------------------------------------------------------------------------------------
# The three governance writes -- this module wrote NO audit rows at all before issue #80
# --------------------------------------------------------------------------------------------


async def test_create_then_update_a_facility_rule_leaves_two_audit_rows(work_session):
    created = await admin_governance_service.create_facility_rule(
        work_session, _admin_ctx(), facility_id=FACILITY, rule_type="NO_SHOW_GRACE_MIN",
        rule_value="25", description="Audit-trail fixture rule (issue #80).",
    )
    rule_id = created["rule_id"]
    try:
        updated = await admin_governance_service.update_facility_rule(
            work_session, _admin_ctx(), rule_id=rule_id, rule_value="35",
        )
        # The `previous_*` columns are a query mechanism and must not reach the API response.
        assert not [key for key in updated if key.startswith("previous_")]

        rows = await _audit_rows(work_session, entity_name="facility_rules", entity_id=rule_id)
        assert [row["action_type"] for row in rows] == ["CREATE", "UPDATE"]
        assert [row["new_value"]["event"] for row in rows] == [
            "CREATE_FACILITY_RULE", "UPDATE_FACILITY_RULE",
        ]
        assert all(row["user_id"] == ADMIN_USER_ID for row in rows)

        # A created row genuinely has no before.
        assert rows[0]["old_value"] is None
        assert rows[0]["new_value"]["rule_value"] == "25"

        # The edit's before came from the self-join -- 25, the value the create wrote, not 35.
        assert rows[1]["old_value"]["rule_value"] == "25"
        assert rows[1]["new_value"]["rule_value"] == "35"
        # `effective_from`/`effective_to` were omitted from the edit, so COALESCE left them alone
        # and the entry says so on both sides rather than reporting a change that did not happen.
        assert rows[1]["old_value"]["effective_from"] == rows[1]["new_value"]["effective_from"]

        stored = (
            await work_session.execute(
                text("SELECT rule_value FROM public.facility_rules WHERE rule_id = :rid"),
                {"rid": rule_id},
            )
        ).scalar_one()
        assert stored == "35"
    finally:
        await work_session.execute(
            text("DELETE FROM public.audit_logs WHERE entity_name = 'facility_rules' AND entity_id = :rid"),
            {"rid": rule_id},
        )
        await work_session.execute(
            text("DELETE FROM public.facility_rules WHERE rule_id = :rid"), {"rid": rule_id}
        )
        await work_session.commit()


async def test_publish_policy_version_records_the_weight_change_that_publishing_makes(work_session):
    """The highest-consequence write in the product (D7 -- it changes the ranking formula every
    later allocation is scored against) and the one that left no trace at all before issue #80.

    Two publishes in sequence, so the second one's `old_value_json` has a real superseded version
    to name -- which is M14's "which policy version" field, and the only field of M14's set this
    table can carry without a schema change.
    """
    ctx = _admin_ctx()
    first_weights = {"lateness_per_minute": 4}
    second_weights = {"lateness_per_minute": 9}
    published: list[str] = []
    try:
        first = await admin_governance_service.publish_policy_version(
            work_session, ctx, weights=first_weights, idempotency_key=f"p8-{uuid4().hex}",
        )
        published.append(first["policy_version_id"])
        second = await admin_governance_service.publish_policy_version(
            work_session, ctx, weights=second_weights, idempotency_key=f"p8-{uuid4().hex}",
            based_on_version_id=first["policy_version_id"],
        )
        published.append(second["policy_version_id"])

        first_rows = await _audit_rows(
            work_session, entity_name="policy_versions", entity_id=first["policy_version_id"]
        )
        second_rows = await _audit_rows(
            work_session, entity_name="policy_versions", entity_id=second["policy_version_id"]
        )
        assert len(first_rows) == 1 and len(second_rows) == 1

        assert first_rows[0]["action_type"] == "CREATE"
        assert first_rows[0]["user_id"] == ADMIN_USER_ID
        assert first_rows[0]["old_value"] is None  # nothing was superseded
        assert first_rows[0]["new_value"] == {
            "event": "PUBLISH_POLICY_VERSION", "policy_version_id": first["policy_version_id"],
            "weights": first_weights, "superseded_version_id": None,
        }

        # The second entry is the one an auditor actually reads: both version ids and both weight
        # sets, so "what changed, when, by whom" is answerable from this row alone.
        assert second_rows[0]["old_value"] == {
            "policy_version_id": first["policy_version_id"], "weights": first_weights,
        }
        assert second_rows[0]["new_value"]["weights"] == second_weights
        assert second_rows[0]["new_value"]["superseded_version_id"] == first["policy_version_id"]

        record_evidence(
            "part8_admin_audit_publish_records_superseded_weights",
            f"{first_weights} -> {second_weights} (v {first['policy_version_id']} -> "
            f"{second['policy_version_id']})",
        )
    finally:
        for version_id in published:
            await work_session.execute(
                text("DELETE FROM public.audit_logs WHERE entity_name = 'policy_versions' AND entity_id = :vid"),
                {"vid": version_id},
            )
            await work_session.execute(
                text("DELETE FROM public.policy_versions WHERE policy_version_id = :vid"),
                {"vid": version_id},
            )
        await work_session.commit()


# --------------------------------------------------------------------------------------------
# The two properties the whole requirement rests on
# --------------------------------------------------------------------------------------------


async def test_every_action_type_the_console_writes_survives_commit(work_session, fixture_user):
    """Runs all six writes for real and counts the audit rows PostgreSQL kept.

    This is the assertion the D2 migration's own comment says a mocked suite structurally cannot
    make: a verb outside `audit_logs_action_type_check` does not fail when the INSERT is issued, it
    fails at COMMIT -- so the only way to know the six writes are inside the vocabulary is to
    commit them against a real cluster and read them back.
    """
    ctx = _admin_ctx()
    rule_id = None
    version_id = None
    try:
        await admin_user_service.update_user(work_session, ctx, user_id=fixture_user, scope=FACILITY)
        await admin_user_service.deactivate_user(work_session, ctx, fixture_user)
        await admin_user_service.reactivate_user(work_session, ctx, fixture_user)
        created = await admin_governance_service.create_facility_rule(
            work_session, ctx, facility_id=FACILITY, rule_type="NO_SHOW_GRACE_MIN", rule_value="21",
        )
        rule_id = created["rule_id"]
        await admin_governance_service.update_facility_rule(
            work_session, ctx, rule_id=rule_id, rule_value="22"
        )
        published = await admin_governance_service.publish_policy_version(
            work_session, ctx, weights={"lateness_per_minute": 4},
            idempotency_key=f"p8-vocab-{uuid4().hex}",
        )
        version_id = published["policy_version_id"]

        entries = (
            await _audit_rows(work_session, entity_name="users", entity_id=fixture_user)
            + await _audit_rows(work_session, entity_name="facility_rules", entity_id=rule_id)
            + await _audit_rows(work_session, entity_name="policy_versions", entity_id=version_id)
        )
        assert len(entries) == 6, "six writes, six audit rows (Flow 9)"
        assert {entry["new_value"]["event"] for entry in entries} == {
            "UPDATE_USER", "DEACTIVATE_USER", "REACTIVATE_USER",
            "CREATE_FACILITY_RULE", "UPDATE_FACILITY_RULE", "PUBLISH_POLICY_VERSION",
        }
        assert {entry["action_type"] for entry in entries} <= PERMITTED_ACTION_TYPES
        assert all(entry["user_id"] == ADMIN_USER_ID for entry in entries)
        record_evidence("part8_admin_writes_audited", f"{len(entries)}/6 writes produced an audit row")
    finally:
        if rule_id is not None:
            await work_session.execute(
                text("DELETE FROM public.audit_logs WHERE entity_name = 'facility_rules' AND entity_id = :rid"),
                {"rid": rule_id},
            )
            await work_session.execute(
                text("DELETE FROM public.facility_rules WHERE rule_id = :rid"), {"rid": rule_id}
            )
        if version_id is not None:
            await work_session.execute(
                text("DELETE FROM public.audit_logs WHERE entity_name = 'policy_versions' AND entity_id = :vid"),
                {"vid": version_id},
            )
            await work_session.execute(
                text("DELETE FROM public.policy_versions WHERE policy_version_id = :vid"),
                {"vid": version_id},
            )
        await work_session.commit()


async def test_a_write_cannot_survive_a_failed_audit_entry(work_session, fixture_user):
    """FR-ADM-009's real teeth: a write must not be able to commit while its audit entry does not.

    Provoked with the database's own constraint rather than a patched `commit`, so nothing about
    this test is simulated: `audit_logs.user_id` is `NOT NULL REFERENCES users(user_id)`, so an
    actor id that does not resolve makes the audit INSERT fail for real, inside the same
    transaction that has already deactivated the user. The read afterwards shows PostgreSQL kept
    neither the audit row nor the deactivation.

    This is the assertion the unit suite structurally cannot make -- a mocked session has no
    constraints and nothing to roll back -- and it is the one that bites if someone later
    "helpfully" moves the audit write into its own transaction, or after the commit.
    """
    ghost_actor = _admin_ctx().model_copy(update={"user_id": "USR-DOES-NOT-EXIST"})

    with pytest.raises(Exception) as exc:  # noqa: PT011 -- asyncpg/SQLAlchemy FK error class
        await admin_user_service.deactivate_user(work_session, ghost_actor, fixture_user)
    assert "audit_logs" in str(exc.value) or "foreign key" in str(exc.value).lower()
    await work_session.rollback()

    assert await _audit_rows(work_session, entity_name="users", entity_id=fixture_user) == []
    is_active = (
        await work_session.execute(
            text("SELECT is_active FROM public.users WHERE user_id = :uid"), {"uid": fixture_user}
        )
    ).scalar_one()
    assert is_active == 1, "the deactivation rolled back with its audit entry, not without it"


# --------------------------------------------------------------------------------------------
# Issue #104 -- the specific-event filter, against the real column type
# --------------------------------------------------------------------------------------------


async def test_no_writer_puts_non_json_into_the_audit_payload(work_session):
    """Every `audit_logs` payload this suite's writers produce is parseable JSON.

    `audit_logs.new_value_json` is `TEXT` (baseline migration line 375), so #104's event filter and
    its projected `event` column both have to cast. One malformed row anywhere breaks the **whole**
    Audit tab, not one row of it.

    **This scan found a real one on 2026-09-02** -- `eta_service.record_eta_update` was binding
    `str({...})`, a Python dict repr, so every ETA update ever reported left an unparseable audit
    payload (M14's "every state change reconstructable" was false for all of them, and the Audit
    tab would have 500'd outright on any database carrying one). That writer is now fixed and this
    is the regression guard for the whole table rather than for one writer: PostgreSQL is happy to
    store any string in a TEXT column, so nothing but a scan like this makes the class visible.
    """
    bad = (
        await work_session.execute(
            text(
                """
                SELECT audit_id, action_type, entity_name, left(new_value_json, 60) AS snippet
                FROM public.audit_logs
                WHERE new_value_json IS NOT NULL
                  AND NOT pg_input_is_valid(new_value_json, 'jsonb')
                ORDER BY audit_id
                """
            )
        )
    ).mappings().all()
    record_evidence(
        "8. #104: malformed new_value_json rows",
        f"{len(bad)} row(s), action_type(s)={sorted({str(r['action_type']) for r in bad}) or 'none'}",
    )
    assert not bad, (
        "a writer is putting non-JSON into audit_logs.new_value_json, which breaks the whole "
        f"Audit tab rather than one row of it: {[dict(row) for row in bad]}"
    )


async def test_a_malformed_payload_cannot_take_the_whole_audit_tab_down(work_session):
    """The guard, proven against the failure it exists for rather than reasoned about.

    A row whose `new_value_json` is not JSON must project `event = NULL` and drop out of the event
    filter -- it must not abort the statement. Without the `CASE WHEN pg_input_is_valid(...)` in
    `AUDIT_EVENT_EXPR` this test fails with `invalid input syntax for type json`, which is the
    production behaviour the ETA rows above would otherwise cause on every Audit tab load.

    The row is written by hand and removed again: this is about what the *reader* survives, and
    manufacturing it through `record_eta_update` would drag an ETA write and its exception into a
    test about a SELECT.
    """
    audit_id = f"AUD-PART8-{uuid4().hex[:8].upper()}"
    await work_session.execute(
        text(
            """
            INSERT INTO public.audit_logs (
              audit_id, user_id, action_type, entity_name, entity_id,
              old_value_json, new_value_json, ip_address, user_agent, created_at
            ) VALUES (
              :audit_id, :user_id, 'UPDATE_ETA', 'shipments', 'SHP1006',
              NULL, :payload, NULL, NULL, :created_at
            )
            """
        ),
        {
            "audit_id": audit_id,
            "user_id": ADMIN_USER_ID,
            # Byte-for-byte the shape `eta_service` really writes: single quotes, Python `None`.
            "payload": "{'latest_eta_ts': '2026-08-04T11:45:00+05:30', 'exception_id': None}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    await work_session.commit()
    try:
        listing = await admin_governance_service.get_audit_log(work_session, _admin_ctx())
        mine = [item for item in listing["items"] if item["audit_id"] == audit_id]
        assert len(mine) == 1, "the malformed row vanished from the tab instead of degrading"
        assert mine[0]["event"] is None, "a non-JSON payload must project no event, not guess one"

        # ...and it is simply not selected by an event filter, rather than exploding it.
        filtered = await admin_governance_service.get_audit_log(
            work_session, _admin_ctx(), event="PUBLISH_POLICY_VERSION"
        )
        assert all(item["audit_id"] != audit_id for item in filtered["items"])
        record_evidence("8. #104: guard over a malformed payload", "tab degrades to event=NULL")
    finally:
        await work_session.execute(
            text("DELETE FROM public.audit_logs WHERE audit_id = :id"), {"id": audit_id}
        )
        await work_session.commit()


async def test_the_guard_expression_is_the_reason_the_index_note_says_drop_it_first(work_session):
    """The volatility claim in `AUDIT_EVENT_EXPR`'s comment, read out of the catalog not remembered.

    That comment tells a future maintainer to drop the `CASE` guard before building the expression
    index, on the grounds that `pg_input_is_valid` is not `IMMUTABLE` and so cannot appear in an
    index expression. If PostgreSQL ever marks it immutable, the advice becomes wrong and this
    fails, pointing at the comment to correct.
    """
    volatility = (
        await work_session.execute(
            text("SELECT provolatile FROM pg_proc WHERE proname = 'pg_input_is_valid' LIMIT 1")
        )
    ).scalar_one()
    assert volatility != "i", (
        "pg_input_is_valid is now IMMUTABLE -- the guarded expression is indexable after all, so "
        "AUDIT_EVENT_EXPR's index note should stop telling maintainers to drop the guard first"
    )
    record_evidence("8. #104: pg_input_is_valid volatility", f"provolatile={volatility!r}")


async def test_the_event_filter_selects_by_specific_event_and_projects_it(work_session):
    """Issue #104's whole point, end to end: the Audit tab can ask for one specific event.

    Before this, `event_type` filtered `action_type`, which is `UPDATE` for a role change, a
    deactivate, a reactivate, a rule edit **and** a policy publish -- so "show me every user
    removal" was not expressible server-side and the Event column had to be derived by parsing JSON
    in the browser. Both halves are asserted here against real rows rather than against the emitted
    SQL, which is all a mocked session can see.
    """
    user_id = await _make_user(work_session)
    try:
        await admin_user_service.deactivate_user(work_session, _admin_ctx(), user_id)
        await admin_user_service.reactivate_user(work_session, _admin_ctx(), user_id)

        both = await admin_governance_service.get_audit_log(
            work_session, _admin_ctx(), resource="users", event_type="UPDATE"
        )
        mine = [item for item in both["items"] if item["entity_id"] == user_id]
        assert {item["event"] for item in mine} == {"DEACTIVATE_USER", "REACTIVATE_USER"}, (
            "the generic action_type filter cannot tell the two apart -- which is issue #104"
        )

        only_deactivations = await admin_governance_service.get_audit_log(
            work_session, _admin_ctx(), event="DEACTIVATE_USER"
        )
        rows = [item for item in only_deactivations["items"] if item["entity_id"] == user_id]
        assert len(rows) == 1
        assert rows[0]["event"] == "DEACTIVATE_USER"
        # ...and the raw column is still there beside the projection, so the change is additive.
        assert json.loads(rows[0]["new_value_json"])["event"] == "DEACTIVATE_USER"

        csv_text = await admin_governance_service.export_audit_log(
            work_session, _admin_ctx(), event="REACTIVATE_USER"
        )
        exported = [line for line in csv_text.splitlines() if user_id in line]
        assert len(exported) == 1 and "REACTIVATE_USER" in exported[0], (
            "the export ignored the filter the view applied -- SS7.5.7 forbids exactly that"
        )
        record_evidence("8. #104: event filter", "DEACTIVATE_USER/REACTIVATE_USER separable")
    finally:
        await _drop_user(work_session, user_id)


async def test_an_unknown_event_is_refused_before_the_query_runs(work_session):
    """A typo must not read as "no such events happened". Same 422-naming-the-set shape the ops and
    planner vocabularies use."""
    with pytest.raises(AppError) as exc:
        await admin_governance_service.get_audit_log(
            work_session, _admin_ctx(), event="USER_DEACTIVATED"
        )
    assert exc.value.code == "INVALID_AUDIT_EVENT"
    assert "DEACTIVATE_USER" in (exc.value.detail or "")
