"""E5.2 (issues #55, #56, #58): the ops-console coordinator reply path.

Three gaps that are one problem, and one test file because they only make sense together:

* **#55** -- nothing in `backend/app/` wrote `chat_messages.sender_type = 'OPERATIONS'`, so the
  takeover composer had nowhere to send.
* **#56** -- nothing wrote `escalation_status = 'IN_PROGRESS'`, so the console's middle stepper dot
  was unreachable, and `hand_back_thread`'s enforced precondition was the loose workaround that
  fact forced rather than the one two design files state.
* **#58** -- the takeover divider was written to `chat_messages` (Postgres) while the driver's feed
  reads Upstash Redis, so it never reached the driver at all.

The load-bearing test in here is `test_a_coordinator_message_lands_in_the_feed_the_driver_reads`:
it drives a real `ConversationMemory` over a fake Redis and asserts the coordinator's message comes
back out of `load_conversation_for_restore` -- the *exact* call `chat.py`'s `/chat/history` makes
for the driver. Asserting only that an INSERT ran would have passed happily before #58 was fixed.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.errors import AppError
from app.core.execution_context import ExecutionContext, RoleName
from app.core.settings import Settings
from app.services import escalation_service, thread_message_service
from app.services.redis_memory import TTL_SECONDS, ConversationMemory

FACILITY = "FAC-JAI-01"
OTHER_FACILITY = "FAC-GGN-01"
OPS_USER = "USR-OPS-1"
DRIVER_USER = "USR-DRV-9"


def _ops_ctx(*, facility_id: str = FACILITY, user_id: str = OPS_USER,
             role: RoleName = RoleName.OPERATIONS_EXECUTIVE) -> ExecutionContext:
    return ExecutionContext(
        request_id="req-ops-1", auth_subject="sub-ops-1", user_id=user_id,
        email="ops@setuhaul.com", full_name="Priya Nair", role_id="ROL002",
        role_name=role, facility_id=facility_id,
    )


def _driver_ctx() -> ExecutionContext:
    return ExecutionContext(
        request_id="req-drv-1", auth_subject="sub-drv-1", user_id=DRIVER_USER,
        email="driver@setuhaul.com", full_name="Ravi Kumar", role_id="ROL001",
        role_name=RoleName.DRIVER, driver_id="DRV1",
    )


def _session_with(*results) -> AsyncMock:
    """Same sequential `session.execute` mocking shape `test_e32_ops_console.py` uses."""
    mocks = []
    for r in results:
        m = MagicMock()
        if isinstance(r, list):
            m.mappings.return_value.all.return_value = r
            m.mappings.return_value.first.return_value = r[0] if r else None
        else:
            m.mappings.return_value.first.return_value = r
            m.mappings.return_value.one.return_value = r
            m.mappings.return_value.all.return_value = [r] if r else []
        mocks.append(m)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=mocks)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


def _executed(session: AsyncMock) -> list[tuple[str, dict]]:
    """Every `session.execute` call as `(sql_text, params)`, for asserting on what actually ran."""
    out = []
    for call in session.execute.await_args_list:
        sql = str(call.args[0])
        params = call.args[1] if len(call.args) > 1 else {}
        out.append((sql, params))
    return out


def _thread(**overrides) -> dict:
    base = {
        "thread_id": "THR-1", "driver_id": "DRV1", "shipment_id": "SHP1",
        "thread_status": "ESCALATED", "facility_id": FACILITY, "driver_user_id": DRIVER_USER,
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def _no_idempotency_replay(monkeypatch):
    monkeypatch.setattr(thread_message_service, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(thread_message_service, "store_idempotency", AsyncMock())
    monkeypatch.setattr(escalation_service, "lookup_idempotency", AsyncMock(return_value=None))
    monkeypatch.setattr(escalation_service, "store_idempotency", AsyncMock())


# =================================================================================================
# Issue #55 -- post_operations_message
# =================================================================================================


@pytest.mark.asyncio
async def test_post_operations_message_writes_an_operations_sender_row():
    """The literal gap #55 names: a `chat_messages` row with `sender_type = 'OPERATIONS'`."""
    session = _session_with(
        _thread(),  # get_thread_context
        None,       # find_message_by_external_id
        None,       # INSERT chat_messages
    )
    result = await thread_message_service.post_operations_message(
        session, _ops_ctx(), thread_id="THR-1",
        message_text="  Your dock is being cleared now, ETA 20 minutes.  ",
        idempotency_key="idem-msg-1",
    )

    assert result["code"] == "POSTED"
    assert result["sender_type"] == "OPERATIONS"
    # Trimmed, not stored with the coordinator's stray whitespace.
    assert result["message_text"] == "Your dock is being cleared now, ETA 20 minutes."

    insert_sql, insert_params = _executed(session)[-1]
    assert "INSERT INTO public.chat_messages" in insert_sql
    assert insert_params["sender_type"] == "OPERATIONS"
    # The sender is the verified token's user_id, never anything the client sent (M15).
    assert insert_params["sender_reference"] == OPS_USER
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_post_operations_message_refuses_a_thread_in_another_facility():
    """Scope is derived from the thread's shipment server-side; a coordinator scoped to Jaipur
    cannot post into a Gurgaon thread even though they hold the ops role (M15/NFR-019)."""
    session = _session_with(_thread(facility_id=OTHER_FACILITY))
    with pytest.raises(AppError) as exc:
        await thread_message_service.post_operations_message(
            session, _ops_ctx(facility_id=FACILITY), thread_id="THR-1",
            message_text="hello", idempotency_key="idem-msg-2",
        )
    assert exc.value.code == "FORBIDDEN"
    assert not any("INSERT INTO public.chat_messages" in sql for sql, _ in _executed(session))


@pytest.mark.asyncio
async def test_post_operations_message_refuses_a_thread_nobody_took_over():
    """Posting into a live assistant thread would interleave a human and the bot with neither
    aware of the other. `NOT_TAKEN_OVER`, and nothing is written."""
    session = _session_with(_thread(thread_status="OPEN"))
    result = await thread_message_service.post_operations_message(
        session, _ops_ctx(), thread_id="THR-1", message_text="hello", idempotency_key="idem-msg-3",
    )
    assert result["code"] == "NOT_TAKEN_OVER"
    assert result["delivered"] is False
    assert not any("INSERT INTO public.chat_messages" in sql for sql, _ in _executed(session))


@pytest.mark.asyncio
async def test_post_operations_message_refuses_a_thread_with_no_facility_to_scope_to():
    """A thread with no shipment has no facility, so there is no scope to authorise against. It is
    refused rather than written unscoped -- the M15 failure mode is the silently-allowed write."""
    session = _session_with(_thread(shipment_id=None, facility_id=None))
    with pytest.raises(AppError) as exc:
        await thread_message_service.post_operations_message(
            session, _ops_ctx(), thread_id="THR-1", message_text="hello", idempotency_key="idem-4",
        )
    assert exc.value.code == "THREAD_UNSCOPED"


@pytest.mark.asyncio
async def test_post_operations_message_requires_an_idempotency_key():
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await thread_message_service.post_operations_message(
            session, _ops_ctx(), thread_id="THR-1", message_text="hello", idempotency_key="",
        )
    assert exc.value.code == "IDEMPOTENCY_KEY_REQUIRED"
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_operations_message_refuses_a_driver():
    """Who may post as OPERATIONS is decided from the verified token, not from the request."""
    session = AsyncMock()
    session.execute = AsyncMock()
    with pytest.raises(AppError) as exc:
        await thread_message_service.post_operations_message(
            session, _driver_ctx(), thread_id="THR-1", message_text="hello",
            idempotency_key="idem-5",
        )
    assert exc.value.code == "FORBIDDEN"
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_operations_message_replays_instead_of_double_posting(monkeypatch):
    """A retried composer send must not appear twice in a driver's conversation."""
    stored = {"code": "POSTED", "chat_message_id": "MSG-1", "thread_id": "THR-1",
              "sender_type": "OPERATIONS", "delivered": True, "delivery_reason": None}
    monkeypatch.setattr(
        thread_message_service, "lookup_idempotency", AsyncMock(return_value={"response": stored})
    )
    session = AsyncMock()
    session.execute = AsyncMock()
    result = await thread_message_service.post_operations_message(
        session, _ops_ctx(), thread_id="THR-1", message_text="hello", idempotency_key="idem-6",
    )
    assert result["idempotent_replay"] is True
    assert result["chat_message_id"] == "MSG-1"
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_post_operations_message_resolves_a_reused_client_message_id():
    """`chat_messages_external_message_id_uidx` is unique; a client that varies its
    Idempotency-Key but reuses its client_message_id must get a replay, not an IntegrityError."""
    session = _session_with(
        _thread(),
        {"chat_message_id": "MSG-EXISTING", "thread_id": "THR-1", "sender_type": "OPERATIONS",
         "sender_reference": OPS_USER, "message_text": "hello", "message_ts": "2026-08-29T10:00:00+00:00"},
    )
    result = await thread_message_service.post_operations_message(
        session, _ops_ctx(), thread_id="THR-1", message_text="hello",
        idempotency_key="idem-7", client_message_id="cm-1",
    )
    assert result["idempotent_replay"] is True
    assert result["chat_message_id"] == "MSG-EXISTING"
    assert not any("INSERT INTO public.chat_messages" in sql for sql, _ in _executed(session))


# =================================================================================================
# Issue #56 -- IN_PROGRESS becomes reachable, and hand_back's precondition matches its docs
# =================================================================================================


def _queue_state(**overrides) -> dict:
    base = {"escalation_id": "ESC-1", "facility_id": FACILITY,
            "escalation_status": "ACKNOWLEDGED", "owner_user_id": OPS_USER}
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_start_escalation_work_advances_an_acknowledged_case_to_in_progress():
    session = _session_with(
        _queue_state(),
        {"escalation_id": "ESC-1", "shipment_id": "SHP1", "escalation_status": "IN_PROGRESS",
         "owner_user_id": OPS_USER},
    )
    result = await escalation_service.start_escalation_work(session, _ops_ctx(), "ESC-1", "idem-s1")
    assert result["code"] == "IN_PROGRESS"
    # The middle stepper dot, unreachable before this existed.
    assert result["stepper_position"] == escalation_service.STEPPER_POSITIONS["IN_PROGRESS"]
    update_sql, _ = _executed(session)[-1]
    assert "SET escalation_status = 'IN_PROGRESS'" in update_sql
    # Guarded, so a concurrent caller cannot re-advance a case that already moved on.
    assert "AND escalation_status = 'ACKNOWLEDGED'" in update_sql


@pytest.mark.asyncio
async def test_start_escalation_work_refuses_an_unacknowledged_case():
    session = _session_with(_queue_state(escalation_status="OPEN", owner_user_id=None))
    result = await escalation_service.start_escalation_work(session, _ops_ctx(), "ESC-1", "idem-s2")
    assert result["code"] == "NOT_ACKNOWLEDGED"
    assert not any("UPDATE public.escalation_queue" in sql for sql, _ in _executed(session))


@pytest.mark.asyncio
async def test_start_escalation_work_is_a_no_op_on_a_case_already_in_progress():
    session = _session_with(_queue_state(escalation_status="IN_PROGRESS"))
    result = await escalation_service.start_escalation_work(session, _ops_ctx(), "ESC-1", "idem-s3")
    assert result["code"] == "ALREADY_IN_PROGRESS"


@pytest.mark.asyncio
async def test_start_escalation_work_refuses_a_case_owned_by_another_coordinator():
    """Facility scope says "you may act in this building"; ownership says "this case is yours".
    Taking someone else's case goes through `reassign_escalation`, which is audited."""
    session = _session_with(_queue_state(owner_user_id="USR-OPS-2"))
    result = await escalation_service.start_escalation_work(session, _ops_ctx(), "ESC-1", "idem-s4")
    assert result["code"] == "NOT_OWNER"


@pytest.mark.asyncio
async def test_start_escalation_work_refuses_a_cross_facility_escalation():
    session = _session_with(_queue_state(facility_id=OTHER_FACILITY))
    with pytest.raises(AppError) as exc:
        await escalation_service.start_escalation_work(session, _ops_ctx(), "ESC-1", "idem-s5")
    assert exc.value.code == "FORBIDDEN"


@pytest.mark.asyncio
async def test_take_over_thread_advances_the_escalation_to_in_progress():
    """Taking over a driver's conversation is the clearest "real work has started" there is, and
    it is what makes hand_back's IN_PROGRESS precondition satisfiable."""
    session = _session_with(
        _queue_state(),
        {"thread_id": "THR-1", "shipment_id": "SHP1", "thread_status": "OPEN"},
        None, None, None,
    )
    result = await escalation_service.take_over_thread(session, _ops_ctx(), "THR-1", "ESC-1", "idem-t")
    assert result["code"] == "TAKEN_OVER"
    assert result["escalation_status"] == "IN_PROGRESS"
    escalation_updates = [
        sql for sql, _ in _executed(session)
        if "UPDATE public.escalation_queue" in sql and "IN_PROGRESS" in sql
    ]
    assert escalation_updates, "take_over_thread must advance the linked escalation"


@pytest.mark.asyncio
async def test_take_over_thread_refuses_an_unacknowledged_escalation():
    """Symmetric with hand_back's documented refusal, and it closes the trap the IN_PROGRESS
    advance would otherwise open: a thread escalated on an unowned case could never be handed
    back, leaving the assistant permanently suppressed on it."""
    session = _session_with(_queue_state(escalation_status="OPEN", owner_user_id=None))
    result = await escalation_service.take_over_thread(session, _ops_ctx(), "THR-1", "ESC-1", "idem-t2")
    assert result["code"] == "NOT_ACKNOWLEDGED"
    assert not any("UPDATE public.chat_threads" in sql for sql, _ in _executed(session))


@pytest.mark.asyncio
async def test_hand_back_requires_in_progress_not_merely_acknowledged():
    """The enforced precondition now matches `components.md` §5 and `flows-and-states.md` Flow 2
    step 5. Asserted on the SQL predicate, because the previous looser guard is exactly the kind of
    thing a mock-shaped test would keep passing through."""
    session = _session_with(
        {"thread_id": "THR-1", "shipment_id": "SHP1", "thread_status": "ESCALATED"},
        {"escalation_id": "ESC-1", "facility_id": FACILITY, "owner_user_id": OPS_USER},
        None, None,
    )
    result = await escalation_service.hand_back_thread(session, _ops_ctx(), "THR-1")
    assert result["code"] == "HANDED_BACK"
    lookup_sql = _executed(session)[1][0]
    assert "escalation_status = 'IN_PROGRESS'" in lookup_sql
    assert "ACKNOWLEDGED" not in lookup_sql


# =================================================================================================
# Issue #58 -- the message actually reaches the feed the driver reads
# =================================================================================================


class _FakeRedis:
    """Stand-in for the Upstash REST client: enough of the command surface for these paths."""

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    def lrange(self, key, start, end):
        items = self.lists.get(key, [])
        if start < 0:
            start = max(len(items) + start, 0)
        if end < 0:
            end = len(items) + end
        return items[start : end + 1]

    def llen(self, key):
        return len(self.lists.get(key, []))

    def get(self, key):
        return self.values.get(key)

    def rpush(self, key, *values):
        self.lists.setdefault(key, []).extend(values)

    def ltrim(self, key, start, end):
        items = self.lists.get(key, [])
        if start < 0:
            start = max(len(items) + start, 0)
        if end < 0:
            end = len(items) + end
        self.lists[key] = items[start : end + 1]

    def expire(self, key, seconds):
        self.expirations[key] = seconds

    def set(self, key, value, ex):
        self.values[key] = value
        self.expirations[key] = ex

    def pipeline(self):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, client: _FakeRedis) -> None:
        self._client = client
        self._ops: list[tuple[str, tuple, dict]] = []

    def __getattr__(self, name):
        def queue(*args, **kwargs):
            self._ops.append((name, args, kwargs))
            return self

        return queue

    def exec(self):
        results = [getattr(self._client, n)(*a, **k) for n, a, k in self._ops]
        self._ops = []
        return results


def _wired_memory(fake: _FakeRedis) -> ConversationMemory:
    memory = ConversationMemory(Settings(upstash_redis_rest_url="", upstash_redis_rest_token=""))
    memory._client = fake  # type: ignore[attr-defined]
    memory._async_client = None  # type: ignore[attr-defined]
    memory.degraded = False
    memory.degrade_reason = None
    return memory


@pytest.mark.asyncio
async def test_append_turn_records_which_session_a_thread_lives_under():
    """The lookup #58 needs: ops holds a `chat_threads.thread_id` and can derive the driver's
    `user_id`, but the Redis history key also needs the *session* -- and nothing exposed it."""
    fake = _FakeRedis()
    memory = _wired_memory(fake)

    await memory.append_turn(
        user_id=DRIVER_USER, thread_id="THR-1", session_id="SES-A",
        user_message="Where do I dock?", assistant_message="Checking now.",
    )

    assert memory.resolve_thread_session_id(user_id=DRIVER_USER, thread_id="THR-1") == "SES-A"
    # Bounded like everything else in this store -- no unbounded pointer key left behind.
    assert fake.expirations[memory._thread_pointer_key(DRIVER_USER, "THR-1")] == TTL_SECONDS


@pytest.mark.asyncio
async def test_resolve_thread_session_id_returns_none_rather_than_guessing():
    """A wrong guess would append a coordinator's message into a conversation the driver is not
    reading -- worse than not delivering it, because it looks delivered."""
    memory = _wired_memory(_FakeRedis())
    assert memory.resolve_thread_session_id(user_id=DRIVER_USER, thread_id="THR-UNKNOWN") is None


@pytest.mark.asyncio
async def test_a_coordinator_message_lands_in_the_feed_the_driver_reads(monkeypatch):
    """**The test #58 exists for.** Drives the real write path, then reads it back through the
    exact call `chat.py`'s `/chat/history` makes for the driver. Before this fix the message went
    to `chat_messages` and this read returned nothing but the driver's own turns."""
    fake = _FakeRedis()
    memory = _wired_memory(fake)
    # Give the driver an existing conversation, which is what creates the thread pointer.
    await memory.append_turn(
        user_id=DRIVER_USER, thread_id="THR-1", session_id="SES-A",
        user_message="I'm stuck at the gate.", assistant_message="Let me check your appointment.",
    )
    monkeypatch.setattr(thread_message_service, "ConversationMemory", lambda _settings: memory)

    session = _session_with(_thread(), None, None)
    result = await thread_message_service.post_operations_message(
        session, _ops_ctx(), thread_id="THR-1",
        message_text="Priya here from Operations -- go to Dock 4, I've cleared it.",
        idempotency_key="idem-live-1", settings=Settings(),
    )

    assert result["code"] == "POSTED"
    assert result["delivered"] is True, result.get("delivery_reason")

    restored = memory.load_conversation_for_restore(
        user_id=DRIVER_USER, thread_id="THR-1", session_id="SES-A"
    )
    contents = [m["content"] for m in restored["messages"]]
    assert "Priya here from Operations -- go to Dock 4, I've cleared it." in contents

    coordinator_bubble = restored["messages"][-1]
    # Provenance rides on `sender`/`sender_name`, additively -- a consumer that only knows
    # user/assistant still renders it, one that knows more can attribute it to a human.
    assert coordinator_bubble["sender"] == "OPERATIONS"
    assert coordinator_bubble["sender_name"] == "Priya Nair"
    # And an ordinary assistant turn is still labelled, not left null.
    assert restored["messages"][1]["sender"] == "AGENT"


@pytest.mark.asyncio
async def test_delivery_failure_is_reported_not_swallowed(monkeypatch):
    """Postgres is the write of record, so a failed Redis projection must not fail the write --
    but it must not be reported as a delivered message either."""
    memory = _wired_memory(_FakeRedis())  # no pointer: driver has no live conversation
    monkeypatch.setattr(thread_message_service, "ConversationMemory", lambda _settings: memory)

    session = _session_with(_thread(), None, None)
    result = await thread_message_service.post_operations_message(
        session, _ops_ctx(), thread_id="THR-1", message_text="Are you still at the gate?",
        idempotency_key="idem-live-2", settings=Settings(),
    )

    assert result["code"] == "POSTED"          # durable row written
    assert result["delivered"] is False        # but the driver has not seen it
    assert result["delivery_reason"] == "NO_LIVE_DRIVER_SESSION"
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_delivery_refuses_when_the_driver_has_no_user_row():
    """The Redis key is namespaced by `users.user_id`, not `drivers.driver_id`. With no user row
    there is no key to write, and inventing one would silently write nowhere."""
    session = _session_with()
    delivery = await thread_message_service.deliver_to_driver_feed(
        session, settings=Settings(), thread_id="THR-1", content="hi",
        sender="OPERATIONS", sender_name="Priya Nair", message_id="MSG-1",
        thread=_thread(driver_user_id=None),
    )
    assert delivery == {"delivered": False, "reason": "DRIVER_USER_UNMAPPED"}


@pytest.mark.asyncio
async def test_takeover_divider_reaches_the_driver(monkeypatch):
    """`flows-and-states.md` Flow 2 step 3: the driver sees "a person has joined" in
    `01-driver-chat/` at the same moment. Previously written to `chat_messages` only."""
    fake = _FakeRedis()
    memory = _wired_memory(fake)
    await memory.append_turn(
        user_id=DRIVER_USER, thread_id="THR-1", session_id="SES-A",
        user_message="Hello?", assistant_message="How can I help?",
    )
    monkeypatch.setattr(thread_message_service, "ConversationMemory", lambda _settings: memory)

    session = _session_with(
        _queue_state(),
        {"thread_id": "THR-1", "shipment_id": "SHP1", "thread_status": "OPEN"},
        None, None, None,
        _thread(),  # deliver_to_driver_feed's own thread lookup
    )
    result = await escalation_service.take_over_thread(
        session, _ops_ctx(), "THR-1", "ESC-1", "idem-t3", settings=Settings(),
    )

    assert result["code"] == "TAKEN_OVER"
    assert result["delivered"] is True, result.get("delivery_reason")

    restored = memory.load_conversation_for_restore(
        user_id=DRIVER_USER, thread_id="THR-1", session_id="SES-A"
    )
    divider = restored["messages"][-1]
    assert divider["sender"] == "SYSTEM"
    assert "has joined this conversation" in divider["content"]


@pytest.mark.asyncio
async def test_a_projection_error_never_turns_a_committed_write_into_a_500(monkeypatch):
    """The caller has already committed a durable `chat_messages` row when the projection runs. An
    exception escaping here would make the router return 500 for a write that succeeded, and the
    coordinator would retry and post twice."""
    def _explode(_settings):
        raise RuntimeError("upstash exploded")

    monkeypatch.setattr(thread_message_service, "ConversationMemory", _explode)
    session = _session_with(_thread(), None, None)
    result = await thread_message_service.post_operations_message(
        session, _ops_ctx(), thread_id="THR-1", message_text="still there?",
        idempotency_key="idem-live-3", settings=Settings(),
    )
    assert result["code"] == "POSTED"
    assert result["delivered"] is False
    assert result["delivery_reason"] == "PROJECTION_ERROR:RuntimeError"


@pytest.mark.asyncio
async def test_projected_message_is_visible_to_the_assistant_after_hand_back():
    """Role stays `assistant` in Redis on purpose. `run_assistant._prepare_turn` maps `assistant`
    history entries to `AIMessage`, so after hand-back the model can see what the coordinator
    actually promised instead of a hole in the transcript. A third role value would have been
    silently dropped by that mapping."""
    fake = _FakeRedis()
    memory = _wired_memory(fake)
    await memory.append_agent_side_message(
        user_id=DRIVER_USER, thread_id="THR-1", session_id="SES-A",
        content="I've moved you to Dock 4.", sender="OPERATIONS", sender_name="Priya Nair",
        message_id="MSG-1",
    )
    history = memory.load_history(user_id=DRIVER_USER, thread_id="THR-1", session_id="SES-A")
    assert [item["role"] for item in history] == ["assistant"]
    assert json.loads(json.dumps(history[0]))["sender"] == "OPERATIONS"


# =================================================================================================
# Reported by the concurrent #60 pass; fixed here because it is one line in a file already open
# =================================================================================================


@pytest.mark.asyncio
async def test_pending_confirmations_excludes_superseded_appointments():
    """A rescheduled appointment leaves the old row at `PENDING_CONFIRMATION` with
    `is_current = 0`. Without this filter the console showed a coordinator a row awaiting a
    decision that the D9 sweeper (`scheduling/expiry.py:203,250`, which does filter on
    `is_current = 1`) would never act on -- the two disagreed about what "pending" means."""
    session = _session_with([])
    await escalation_service.get_pending_confirmations(session, _ops_ctx(), FACILITY)
    sql, _ = _executed(session)[0]
    assert "a.is_current = 1" in sql
