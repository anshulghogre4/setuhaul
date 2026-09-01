"""Section 10 part 6 -- chaos-lite: kill Redis mid-conversation.

Design citation: `SOLUTION_DESIGN.md` section 10.6 -- "Kill Redis mid-conversation; the next turn
must still answer correctly from Postgres. **Freshness comes from the database, never from cache.**"
Also section 0's Redis boundary ("Upstash Redis holds bounded, non-authoritative conversation/
session state") and `AGENTS.md`'s "PostgreSQL is the business source of truth". GitHub issue #44.

## What "answers correctly" is taken to mean here, and why the weaker reading was rejected

The easy test is "the turn did not raise". That would pass against a system that served the *same
stale answer it had cached before the outage* -- which is precisely the failure the second half of
section 10.6's sentence forbids. So the load-bearing test in this file
(`test_the_next_turn_reflects_a_postgres_change_made_after_redis_died`) does this instead:

    turn 1 with Redis alive  -> the driver's ETA is E1
    kill Redis
    write a NEW ETA (E2) straight into PostgreSQL
    turn 2 with Redis still dead -> the answer must say E2

Only a turn that genuinely re-read Postgres can produce E2. A cache-backed answer produces E1, and
a hard-failing turn produces neither.

## Which Redis is killed

A local in-process fake (`tests/proof/fake_redis.py`), injected by monkeypatching the
`ConversationMemory` constructor `run_assistant.py` calls. The shared Upstash instance is never
contacted: the orchestrator blanks `UPSTASH_REDIS_REST_URL`/`_TOKEN`/`_NATIVE_URL` in the child
environment, so even an un-patched `ConversationMemory` would construct with `_client is None`
rather than reaching the network.

## Why the real `_prepare_turn` and not a hand-rolled stand-in

`_prepare_turn` is where a real driver turn loads Redis history, checks for a duplicate message,
checks for an escalated-thread takeover, and prefetches the operational context from Postgres. The
interesting question -- does an outage in step 1 damage step 4 -- only exists in that function. Only
the LLM itself is stubbed, because a model call is neither deterministic nor available in CI.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.assistant import run_assistant
from app.assistant.run_assistant import PreparedTurn, _prepare_turn
from app.core.settings import get_settings
from app.services import driver_reads
from app.services.redis_memory import ConversationMemory
from tests.proof.evidence import record_evidence
from tests.proof.fake_redis import FakeUpstashRedis, RedisKilled
from tests.proof.harness import seed_race

pytestmark = pytest.mark.asyncio(loop_scope="session")

IST = timezone(timedelta(hours=5, minutes=30))

PREFETCH_MARKER = "Driver operational context (PostgreSQL-backed, prefetched for this turn"


class _StubLLM:
    """Stands in for the chat model. Never invoked -- `_prepare_turn` only builds and binds it."""

    model_name = "proof-suite-stub"

    def bind_tools(self, tools):  # noqa: ANN001 - mirrors the LangChain surface used
        self.bound_tools = tools
        return self


def _memory_with(fake: FakeUpstashRedis) -> ConversationMemory:
    """A real `ConversationMemory` wired to the fake client.

    The class is constructed for real -- all of its key derivation, pipelining, degrade-flag
    handling and exception mapping is the production code under test. Only the transport underneath
    it is swapped.
    """
    memory = ConversationMemory(get_settings())
    memory._client = fake  # noqa: SLF001 - transport injection is the whole point
    memory._async_client = None  # noqa: SLF001 - force the REST path production uses today
    memory.degraded = False
    memory.degrade_reason = None
    return memory


def _prefetched_context(prepared: PreparedTurn) -> dict:
    """Pull the prefetched Postgres payload back out of the assembled system messages."""
    for message in prepared.messages:
        content = str(getattr(message, "content", ""))
        if content.startswith(PREFETCH_MARKER):
            _, _, payload = content.partition("): ")
            return json.loads(payload)
    raise AssertionError("the turn carried no PostgreSQL-backed prefetch block at all")


@pytest.fixture(scope="session")
def chaos_run_id() -> str:
    return uuid4().hex[:8].upper()


# ----------------------------------------------------------------------------------------------
# 1. The memory layer itself
# ----------------------------------------------------------------------------------------------


async def test_the_fake_records_a_turn_while_it_is_alive(chaos_run_id):
    """A precondition, asserted rather than assumed: if the fake never stored anything, "killing"
    it would prove nothing, because there would have been no cache to lose."""
    fake = FakeUpstashRedis()
    memory = _memory_with(fake)
    await memory.append_turn(
        user_id="USR-CHAOS", thread_id=f"THR-CHAOS-{chaos_run_id}", session_id="SES-CHAOS",
        user_message="Where should I dock?", assistant_message="Checking your options now.",
    )
    assert memory.degraded is False
    context = await memory.load_turn_context(
        user_id="USR-CHAOS", thread_id=f"THR-CHAOS-{chaos_run_id}", session_id="SES-CHAOS"
    )
    assert [entry["role"] for entry in context["history"]] == ["user", "assistant"]
    assert context["history"][0]["content"] == "Where should I dock?"


async def test_a_killed_redis_degrades_the_memory_without_raising(chaos_run_id):
    """The outage must surface as a *flag*, never as an exception the turn has to survive.

    Both hot-path methods are exercised, because they degrade through separate `except` blocks and
    a fix to one has historically not implied the other.
    """
    fake = FakeUpstashRedis()
    memory = _memory_with(fake)
    await memory.append_turn(
        user_id="USR-CHAOS", thread_id=f"THR-CHAOS-{chaos_run_id}", session_id="SES-CHAOS",
        user_message="first", assistant_message="ack",
    )
    fake.kill()

    context = await memory.load_turn_context(
        user_id="USR-CHAOS", thread_id=f"THR-CHAOS-{chaos_run_id}", session_id="SES-CHAOS"
    )
    assert context == {"history": [], "summaries": [], "session": {}}
    assert memory.degraded is True
    assert RedisKilled.__name__ in str(memory.degrade_reason), memory.degrade_reason

    # A write during the outage must also not raise -- the driver's turn continues, the bubble is
    # simply not remembered.
    await memory.append_turn(
        user_id="USR-CHAOS", thread_id=f"THR-CHAOS-{chaos_run_id}", session_id="SES-CHAOS",
        user_message="second", assistant_message="ack2",
    )
    assert memory.degraded is True
    assert fake.calls_after_kill >= 2


# ----------------------------------------------------------------------------------------------
# 2. A real turn, prepared with Redis dead
# ----------------------------------------------------------------------------------------------


async def test_the_next_turn_still_prepares_and_answers_from_postgres(
    work_sessionmaker, monkeypatch, chaos_run_id
):
    """The literal section 10.6 assertion: kill Redis mid-conversation, then take the next turn.

    "Answers correctly" is checked against the database directly -- the prefetched block embedded in
    the turn is compared field-for-field with a fresh `get_driver_operational_context` read, rather
    than merely being non-empty.
    """
    async with work_sessionmaker() as session:
        fixture = await seed_race(
            session, run_id=f"C{chaos_run_id[:7]}", contenders=1, start_offset_minutes=960
        )
    contender = fixture.contenders[0]
    ctx = contender.ctx()

    fake = FakeUpstashRedis()
    memory = _memory_with(fake)
    thread_id = f"THR-CHAOS-{chaos_run_id}"

    # -- turn 1: Redis is healthy and remembers the exchange -------------------------------
    await memory.append_turn(
        user_id=ctx.user_id, thread_id=thread_id, session_id="SES-CHAOS",
        user_message="I am running late.", assistant_message="Understood, checking options.",
    )
    assert memory.degraded is False
    assert fake.store, "turn 1 stored nothing, so there is no cache for the outage to remove"

    # -- the kill, mid-conversation --------------------------------------------------------
    fake.kill()

    monkeypatch.setattr(run_assistant, "ConversationMemory", lambda _settings: memory)
    monkeypatch.setattr(run_assistant, "build_chat_model", lambda _settings: _StubLLM())

    settings = get_settings().model_copy(
        # `_prepare_turn` refuses outright without an LLM credential. A placeholder is enough: the
        # model itself is stubbed above and is never invoked in this test.
        update={"openai_api_key": "proof-suite-stub-not-a-real-key"}
    )

    async with work_sessionmaker() as session:
        prepared = await _prepare_turn(
            session=session,
            ctx=ctx,
            settings=settings,
            message="What is my current ETA and appointment?",
            thread_id=thread_id,
            session_id="SES-CHAOS",
            client_message_id=None,
        )
        assert isinstance(prepared, PreparedTurn), (
            f"the turn short-circuited instead of preparing: {prepared}"
        )
        prefetched = _prefetched_context(prepared)
        direct = await driver_reads.get_driver_operational_context(session, ctx)

    # The outage is visible...
    assert memory.degraded is True
    assert RedisKilled.__name__ in str(memory.degrade_reason)
    # ...and the history the turn assembled is empty, i.e. it really did lose the cache rather
    # than quietly serving a copy from somewhere else.
    assert prepared.full_history == []

    # ...but the operational answer is complete, live, and Postgres-sourced.
    assert prefetched["source"] == "postgresql"
    assert prefetched["freshness"] == "live"
    volatile = {"as_of"}
    for key in set(prefetched) | set(direct):
        if key in volatile:
            continue
        assert json.dumps(prefetched.get(key), sort_keys=True, default=str) == json.dumps(
            direct.get(key), sort_keys=True, default=str
        ), f"the turn's prefetched {key!r} does not match a direct PostgreSQL read"

    record_evidence(
        "6. chaos-lite: next turn after the kill",
        f"prepared OK, memory.degraded={memory.degraded} "
        f"reason={memory.degrade_reason} history_entries={len(prepared.full_history)} "
        f"prefetch source={prefetched['source']}/{prefetched['freshness']}",
    )
    assert prefetched["primary_shipment"] is not None
    assert prefetched["primary_shipment"]["shipment_id"] == contender.shipment_id


async def test_the_next_turn_reflects_a_postgres_change_made_after_redis_died(
    work_sessionmaker, monkeypatch, chaos_run_id
):
    """"Freshness comes from the database, never from cache" -- the assertion that can only pass
    if the turn genuinely re-read Postgres.

    A cached answer would still be showing the pre-outage ETA. A broken turn would show nothing.
    Only a live read shows the value written *after* the outage began.
    """
    run = f"F{chaos_run_id[:7]}"
    async with work_sessionmaker() as session:
        fixture = await seed_race(session, run_id=run, contenders=1, start_offset_minutes=1440)
    contender = fixture.contenders[0]
    ctx = contender.ctx()

    fake = FakeUpstashRedis()
    memory = _memory_with(fake)
    thread_id = f"THR-FRESH-{chaos_run_id}"

    monkeypatch.setattr(run_assistant, "ConversationMemory", lambda _settings: memory)
    monkeypatch.setattr(run_assistant, "build_chat_model", lambda _settings: _StubLLM())
    settings = get_settings().model_copy(
        update={"openai_api_key": "proof-suite-stub-not-a-real-key"}
    )

    async def prepare(session):
        prepared = await _prepare_turn(
            session=session, ctx=ctx, settings=settings,
            message="What is my ETA?", thread_id=thread_id, session_id="SES-FRESH",
            client_message_id=None,
        )
        assert isinstance(prepared, PreparedTurn)
        return _prefetched_context(prepared)

    async def declare_eta(eta_id: str, declared, created_at) -> None:
        async with work_sessionmaker() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO public.eta_updates (
                      eta_update_id, shipment_id, source_type, reported_by_driver_id,
                      declared_eta_ts, confidence_code, delay_reason_code, note, created_at
                    ) VALUES (
                      :eta_id, :shipment_id, 'DRIVER_DECLARED', :driver_id,
                      :declared, 'HIGH', 'TRAFFIC', :note, :created_at
                    )
                    """
                ),
                {
                    "eta_id": eta_id,
                    "shipment_id": contender.shipment_id,
                    "driver_id": contender.driver_id,
                    # eta_updates.declared_eta_ts and .created_at are both timestamptz since
                    # migration 20260823060000; asyncpg refuses a str for either.
                    "declared": declared,
                    "created_at": created_at,
                    "note": f"proof-suite {eta_id}",
                },
            )
            await session.commit()

    def declared_eta_of(payload) -> str:
        latest = payload.get("latest_eta")
        assert latest is not None, "the prefetched context carried no latest ETA at all"
        return str(latest["declared_eta_ts"])

    # -- an ETA exists BEFORE the outage, so the comparison is value-to-value ---------------
    # A None-to-value transition would also pass a naive check while proving much less; the point
    # is that a *different* answer arrives, not merely that a first answer eventually does.
    first_eta = fixture.eta
    stamped_at = datetime.now(timezone.utc)
    await declare_eta(f"ETA-CHAOS-{run}-A", first_eta, stamped_at)

    # -- turn 1, Redis alive ---------------------------------------------------------------
    async with work_sessionmaker() as session:
        before = await prepare(session)
    eta_before = declared_eta_of(before)
    assert memory.degraded is False

    # -- kill Redis, then move the truth in Postgres ---------------------------------------
    fake.kill()

    revised_eta = first_eta + timedelta(minutes=37)
    await declare_eta(f"ETA-CHAOS-{run}-B", revised_eta, stamped_at + timedelta(seconds=1))

    # -- turn 2, Redis still dead: must show the NEW value ----------------------------------
    async with work_sessionmaker() as session:
        after = await prepare(session)

    assert memory.degraded is True, "the outage healed itself; this test proved nothing"
    eta_after = declared_eta_of(after)
    assert eta_after != eta_before, (
        "the next turn returned the pre-outage ETA -- freshness came from cache, not the database"
    )
    record_evidence(
        "6. chaos-lite: freshness after the kill",
        f"ETA before outage {eta_before} -> after a Postgres-only write {eta_after}",
    )
    assert datetime.fromisoformat(eta_after).astimezone(timezone.utc) == revised_eta.astimezone(
        timezone.utc
    ), f"expected the post-outage ETA {revised_eta}, got {eta_after}"


async def test_driver_tools_still_answer_from_postgres_during_the_outage(
    work_sessionmaker, monkeypatch, chaos_run_id
):
    """The tools the model would call next must work too, not just the prefetch.

    `find_feasible_slots` is the sharpest case: `build_driver_tools` passes the same
    `ConversationMemory` into the tool closure (it consults Redis for the active `REC-` id), so a
    dead Redis is directly in that tool's path. It must still return real options off the same
    contested slot the harness seeded.
    """
    run = f"T{chaos_run_id[:7]}"
    async with work_sessionmaker() as session:
        fixture = await seed_race(session, run_id=run, contenders=1, start_offset_minutes=1920)
    contender = fixture.contenders[0]
    ctx = contender.ctx()

    fake = FakeUpstashRedis()
    memory = _memory_with(fake)
    fake.kill()

    monkeypatch.setattr(run_assistant, "ConversationMemory", lambda _settings: memory)
    monkeypatch.setattr(run_assistant, "build_chat_model", lambda _settings: _StubLLM())
    settings = get_settings().model_copy(
        update={"openai_api_key": "proof-suite-stub-not-a-real-key"}
    )

    async with work_sessionmaker() as session:
        prepared = await _prepare_turn(
            session=session, ctx=ctx, settings=settings,
            message="Show me my slot options.", thread_id=f"THR-TOOLS-{chaos_run_id}",
            session_id="SES-TOOLS", client_message_id=None,
        )
        assert isinstance(prepared, PreparedTurn)
        tool_map = prepared.tool_map
        assert "find_feasible_slots" in tool_map
        assert "get_driver_operational_context" in tool_map

        raw = await tool_map["find_feasible_slots"].coroutine(
            **{"shipment_id": contender.shipment_id}
        )
        payload = json.loads(raw)

    assert memory.degraded is True, "Redis came back up; the tool was not exercised under outage"
    assert payload.get("source") == "postgresql"
    assert payload.get("freshness") == "live"
    assert payload.get("options"), (
        "the slot search returned nothing while Redis was down; it should not depend on Redis at all"
    )
    offered = {option["slot_id"] for option in payload["options"]}
    assert fixture.slot_id in offered, (
        f"the seeded contested slot {fixture.slot_id} was not offered: {sorted(offered)}"
    )
    # The recommendation fingerprint is computed from PostgreSQL rows and the policy version, so it
    # must still be produced with the cache gone -- otherwise staleness detection would break for
    # the whole duration of a Redis outage.
    record_evidence(
        "6. chaos-lite: tools during the outage",
        f"find_feasible_slots returned {len(payload['options'])} option(s), "
        f"{payload.get('recommendation_id')}, redis calls refused={fake.calls_after_kill}",
    )
    assert str(payload.get("recommendation_id", "")).startswith("REC-")


async def test_a_write_still_commits_to_postgres_while_redis_is_down(
    work_sessionmaker, monkeypatch, chaos_run_id
):
    """Redis is non-authoritative, so an outage must not block a business write.

    `record_eta_update`'s own comment states the rule -- "a Redis outage must never turn a
    committed PostgreSQL ETA update into a failed write" -- and this is the assertion behind it:
    the write path's post-commit `mark_recommendation_stale` call runs against a dead client and
    the row is still there afterwards.
    """
    from app.services.eta_service import EtaUpdateCommand, record_eta_update

    run = f"W{chaos_run_id[:7]}"
    async with work_sessionmaker() as session:
        fixture = await seed_race(session, run_id=run, contenders=1, start_offset_minutes=2400)
    contender = fixture.contenders[0]
    ctx = contender.ctx()

    fake = FakeUpstashRedis()
    fake.kill()
    monkeypatch.setattr(
        "app.services.eta_service.ConversationMemory", lambda _settings: _memory_with(fake)
    )

    declared = (fixture.eta + timedelta(minutes=25)).isoformat()
    key = f"proof-chaos-write-{run}"
    async with work_sessionmaker() as session:
        result = await record_eta_update(
            session,
            ctx=ctx,
            shipment_id=contender.shipment_id,
            command=EtaUpdateCommand(
                declared_eta_ts=declared,
                delay_reason_code="TRAFFIC",
                confidence_code="HIGH",
                exception_type="TRAFFIC",
                description="Declared while Redis was down.",
                confirmed=True,
                confirmation_eta_ts=declared,
            ),
            idempotency_key=key,
        )
    assert result.get("idempotent_replay") is False

    async with work_sessionmaker() as session:
        stored = await session.scalar(
            text(
                "SELECT count(*) FROM public.eta_updates "
                "WHERE shipment_id = :s AND source_type = 'DRIVER_DECLARED'"
            ),
            {"s": contender.shipment_id},
        )
        effective = await session.scalar(
            text("SELECT effective_eta_ts FROM public.v_latest_eta WHERE shipment_id = :s"),
            {"s": contender.shipment_id},
        )
    assert int(stored) == 1, "the ETA write was lost because Redis was unavailable"
    assert effective is not None
    assert fake.calls_after_kill >= 1, (
        "the write path never touched Redis at all, so this test did not exercise the outage"
    )
