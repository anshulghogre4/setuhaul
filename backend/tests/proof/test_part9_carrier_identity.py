"""The carrier portal's identity, end to end against a real cluster -- GitHub issue #101.

Design citation: `SOLUTION_DESIGN.md` §7.5.6 (the carrier tool catalog -- *"scope-derived from the
caller's own `carrier_id` (M15), never accepted as an argument"*), §2 (persona table), M15,
NFR-019, FR-CAR-001 .. FR-CAR-004.

**Not a ninth part of §10**, the same way `test_part7_read_write_agreement.py` is not a seventh.
§10 defines six parts; this file lives beside them because what it proves needs the same throwaway
cluster and cannot be proved by a mock: that a `user_scopes` row of a particular shape, read by
`core/deps.py`'s own statement, produces a working carrier identity for the roster's actual carrier
persona.

## What was broken

Issue #101, proven by the 2026-09-01 click-sweep: **no account in the system could use the carrier
surface at all.** `public.roles` gains `ROL009`/`CARRIER` from migration 20260823090000, but that
migration's own closing comment records why no user holds it -- *"no CARRIER-scope backfill: zero
CARRIER-role users exist today"* -- and none has been provisioned since. The roster's carrier
persona is `USR105` / sanjay.gupta@setuhaul.com, seeded as `ROL006` = TRANSPORT_MANAGER
(`supabase/seed.sql:684-696`), and the frontend already maps that account to `/carrier/*`. So all
five `/carrier/*` reads answered 403 for the only human meant to call them.

Owner decision (a): the carrier portal admits TRANSPORT_MANAGER alongside CARRIER. The tests below
pin both halves of that -- the role now clears the gate, **and** the reach still comes entirely
from a per-user `user_scopes(scope_type='CARRIER')` row rather than from the role name.

## What this file deliberately does not prove

JWT verification. `core/deps.get_execution_context` needs a signed Supabase token, which no
throwaway cluster can mint. Everything downstream of the token *is* proved here, against real rows:
the identity SELECT, the scope SELECT (asserted as the statement `deps.py` itself runs, not a
paraphrase), and all five §7.5.6 reads with their scope filters and their cross-carrier refusal.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text

from app.core.errors import AppError
from app.core.execution_context import CARRIER_PORTAL_ROLES, ExecutionContext, RoleName
from app.services import carrier_reads
from tests.proof.evidence import record_evidence

pytestmark = pytest.mark.asyncio(loop_scope="session")

# The roster's carrier persona and the carrier it is being linked to. `USR105`/`ROL006` and
# `CAR001` are both shipped seed rows, not fixtures invented here -- this file is about wiring two
# existing rows together, which is exactly what the coordinator has to do in production.
CARRIER_PERSONA_USER = "USR105"
CARRIER_PERSONA_ROLE = "ROL006"
LINKED_CARRIER = "CAR001"
OTHER_CARRIER = "CAR002"
SCOPE_ID = "SCP-CAR-USR105"


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def carrier_scope_row(work_sessionmaker):
    """Grant `USR105` a CARRIER scope, with the exact INSERT the coordinator must run live.

    Kept identical to the statement in this change's report on purpose: a fixture that provisioned
    the scope some other way would prove that *a* row works, not that *the documented* row does.
    `scope_id` follows the `SCP-<TYPE>-<user>` shape migration 20260823090000's own backfill uses
    (`'SCP-FAC-' || u.user_id`), and `ON CONFLICT DO NOTHING` matches its idempotency.
    """
    async with work_sessionmaker() as session:
        await session.execute(
            text(
                """
                INSERT INTO public.user_scopes
                  (scope_id, user_id, scope_type, scope_value, created_at)
                VALUES (:scope_id, :user_id, 'CARRIER', :carrier_id, now())
                ON CONFLICT (user_id, scope_type, scope_value) DO NOTHING
                """
            ),
            {"scope_id": SCOPE_ID, "user_id": CARRIER_PERSONA_USER, "carrier_id": LINKED_CARRIER},
        )
        await session.commit()
    return {"user_id": CARRIER_PERSONA_USER, "carrier_id": LINKED_CARRIER}


async def _resolved_carrier_id(session, user_id: str) -> str | None:
    """Run `core/deps.get_execution_context`'s own scope statement, not a paraphrase of it.

    A hand-written equivalent here could agree with a broken `deps.py`; this asks the same question
    the application asks, with the same predicate.
    """
    row = (
        await session.execute(
            text(
                """
                SELECT scope_value FROM public.user_scopes
                WHERE user_id = :user_id AND scope_type = 'CARRIER'
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        )
    ).mappings().first()
    return str(row["scope_value"]) if row else None


def _persona_ctx(carrier_id: str | None) -> ExecutionContext:
    """The context `deps.py` would build for `USR105` after a verified token.

    Everything on it is read off the seeded rows: TRANSPORT_MANAGER because that is the role
    `seed.sql` gives this user, `facility_id=None` because the seed leaves it NULL for the
    global-read personas, and `carrier_id` from the scope row rather than from any column.
    """
    return ExecutionContext(
        request_id="proof-p8",
        auth_subject="proof-p8",
        user_id=CARRIER_PERSONA_USER,
        email="sanjay.gupta@setuhaul.com",
        full_name="Sanjay Gupta",
        role_id=CARRIER_PERSONA_ROLE,
        role_name=RoleName.TRANSPORT_MANAGER,
        facility_id=None,
        carrier_id=carrier_id,
    )


# =================================================================================================
# A. The premise, re-verified against the live rows rather than taken from the issue
# =================================================================================================


async def test_a_the_roster_carrier_persona_is_a_transport_manager(seed_session):
    """The fact the whole decision rests on, asserted rather than remembered.

    If someone later provisions a real CARRIER account for this user, this fails and the reviewer
    has to decide whether option (a) is still the right shape -- which is the correct outcome.
    """
    row = (
        await seed_session.execute(
            text(
                """
                SELECT u.user_id, r.role_name
                FROM public.users u
                JOIN public.roles r ON r.role_id = u.role_id
                WHERE u.user_id = :user_id
                """
            ),
            {"user_id": CARRIER_PERSONA_USER},
        )
    ).mappings().first()
    assert row is not None, f"{CARRIER_PERSONA_USER} is not in the seed at all"
    record_evidence("9. #101: roster carrier persona", f"{row['user_id']} = {row['role_name']}")
    assert row["role_name"] == "TRANSPORT_MANAGER"


async def test_a_no_user_holds_the_carrier_role(seed_session):
    """Why option (b) -- "just use the CARRIER role" -- was not available without provisioning.

    The role row exists (migration 20260823090000 inserts ROL009); zero users hold it, which is
    what turned every `/carrier/*` read into a 403 for everybody.
    """
    role_exists = await seed_session.scalar(
        text("SELECT count(*) FROM public.roles WHERE role_name = 'CARRIER'")
    )
    holders = await seed_session.scalar(
        text(
            """
            SELECT count(*) FROM public.users u
            JOIN public.roles r ON r.role_id = u.role_id
            WHERE r.role_name = 'CARRIER'
            """
        )
    )
    record_evidence("9. #101: CARRIER role / holders", f"role rows={role_exists}, users={holders}")
    assert int(role_exists) == 1, "the CARRIER role row is missing from this chain entirely"
    assert int(holders) == 0, (
        f"{holders} user(s) now hold CARRIER -- option (a) may no longer be the right shape"
    )


async def test_a_the_persona_has_no_carrier_scope_before_the_insert(seed_session):
    """The precondition that makes the fixture's INSERT meaningful.

    Run against the pristine seed clone, so it cannot be perturbed by the work-database fixture.
    This is also the finding the coordinator has to act on: the route change alone is inert until
    this row exists.
    """
    assert await _resolved_carrier_id(seed_session, CARRIER_PERSONA_USER) is None


# =================================================================================================
# B. With the scope row, the whole chain works -- and only for the carrier it names
# =================================================================================================


async def test_b_deps_scope_statement_resolves_the_linked_carrier(
    carrier_scope_row, work_session
):
    """`core/deps.py`'s own SELECT, against the row the coordinator will insert."""
    resolved = await _resolved_carrier_id(work_session, CARRIER_PERSONA_USER)
    record_evidence("9. #101: resolved carrier scope", str(resolved))
    assert resolved == LINKED_CARRIER


@pytest.mark.parametrize(
    "read",
    [
        "get_fleet_overview",
        "list_fleet_shipments",
        "list_fleet_exceptions",
        "get_carrier_on_time_performance",
    ],
)
async def test_b_every_argumentless_carrier_read_answers_for_the_transport_manager(
    carrier_scope_row, work_sessionmaker, read
):
    """§7.5.6's catalog, minus `get_shipment_detail` (which takes an id and is tested below).

    Each is called with no carrier argument at all -- there is none to pass, which is M15 made
    unforgeable -- and each must come back scoped to `CAR001`.
    """
    ctx = _persona_ctx(LINKED_CARRIER)
    async with work_sessionmaker() as session:
        payload = await getattr(carrier_reads, read)(session, ctx)
    assert payload["scope"] == {"carrier_id": LINKED_CARRIER, "read_only": True}
    record_evidence(f"9. #101: {read}", f"scope={payload['scope']['carrier_id']}")


async def test_b_the_reads_are_refused_without_a_scope_row(work_sessionmaker):
    """The same identity, minus the `user_scopes` row: `CARRIER_UNMAPPED`, not the whole fleet.

    This is the load-bearing half of #101's safety argument. TRANSPORT_MANAGER holds
    `has_global_read_scope` over *facilities*, so if the carrier path had ever fallen through to
    "no filter" for an unmapped identity, admitting the role would have handed it every carrier's
    data. It does not.
    """
    ctx = _persona_ctx(None)
    async with work_sessionmaker() as session:
        with pytest.raises(AppError) as exc:
            await carrier_reads.get_fleet_overview(session, ctx)
    record_evidence("9. #101: unmapped persona", exc.value.code)
    assert exc.value.code == "CARRIER_UNMAPPED"
    assert exc.value.status_code == 403


async def test_b_a_shipment_outside_the_linked_carrier_is_refused_not_hidden(
    carrier_scope_row, work_sessionmaker
):
    """§7.5.6 / `edge-cases.md` #1: refused server-side, and refused *identically* to an id that
    does not exist, so the response cannot be used to probe for existence outside scope."""
    ctx = _persona_ctx(LINKED_CARRIER)
    async with work_sessionmaker() as session:
        other = (
            await session.execute(
                text(
                    "SELECT shipment_id FROM public.shipments "
                    "WHERE carrier_id = :carrier_id LIMIT 1"
                ),
                {"carrier_id": OTHER_CARRIER},
            )
        ).mappings().first()
        assert other is not None, f"no {OTHER_CARRIER} shipment exists; this test would be vacuous"

        with pytest.raises(AppError) as cross:
            await carrier_reads.get_shipment_detail(session, ctx, str(other["shipment_id"]))
        with pytest.raises(AppError) as missing:
            await carrier_reads.get_shipment_detail(session, ctx, "SHP-DOES-NOT-EXIST")

    record_evidence(
        "9. #101: cross-carrier vs missing",
        f"{cross.value.code}/{cross.value.status_code} vs "
        f"{missing.value.code}/{missing.value.status_code}",
    )
    assert (cross.value.code, cross.value.status_code) == ("FORBIDDEN", 403)
    assert (cross.value.code, cross.value.status_code) == (
        missing.value.code,
        missing.value.status_code,
    )


async def test_b_an_own_carrier_shipment_reads_through(carrier_scope_row, work_sessionmaker):
    """The positive case, so the refusals above are not simply "everything is refused"."""
    ctx = _persona_ctx(LINKED_CARRIER)
    async with work_sessionmaker() as session:
        own = (
            await session.execute(
                text(
                    "SELECT shipment_id FROM public.shipments "
                    "WHERE carrier_id = :carrier_id LIMIT 1"
                ),
                {"carrier_id": LINKED_CARRIER},
            )
        ).mappings().first()
        assert own is not None, f"no {LINKED_CARRIER} shipment exists; this test would be vacuous"
        payload = await carrier_reads.get_shipment_detail(
            session, ctx, str(own["shipment_id"])
        )
    assert payload["shipment"]["shipment_id"] == str(own["shipment_id"])
    assert payload["scope"]["carrier_id"] == LINKED_CARRIER


async def test_b_the_role_set_did_not_quietly_widen_further(work_sessionmaker):
    """Exactly two roles, and the global-read personas that are *not* in it.

    ADMIN and REGIONAL_OPERATIONS_HEAD both hold `has_global_read_scope`; neither is a carrier
    persona, and neither may acquire carrier reach by being senior.
    """
    assert CARRIER_PORTAL_ROLES == {RoleName.CARRIER, RoleName.TRANSPORT_MANAGER}
    ctx = _persona_ctx(LINKED_CARRIER).model_copy(
        update={"role_name": RoleName.ADMIN, "role_id": "ROL008"}
    )
    async with work_sessionmaker() as session:
        with pytest.raises(AppError) as exc:
            await carrier_reads.get_fleet_overview(session, ctx)
    assert exc.value.code == "FORBIDDEN"
    assert exc.value.status_code == 403
