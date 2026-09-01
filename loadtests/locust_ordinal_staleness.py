"""§9.2 race #4 -- `ordinal_staleness`. Net-new (issue #42, sub-item 4).

Design citation: `SOLUTION_DESIGN.md` §9.2 race 4 -- *"driver replies \"2\" against a
`recommendation_id` that has since been re-ranked → rejected and re-presented. Never applied to the
new list."* `TESTING_STRATEGY.md` §3a row 4 says the same in its own words: *"Rejected and
re-presented. Never applied to the new list."* Backend:
`allocation._validate_displayed_recommendation`, `feasibility.recommendation_id_for`.

## The reading this suite implements, recorded because the design's sentence is one layer above HTTP

§9.2 describes a *chat* turn: the driver types "2", and an ordinal is resolved against a list. That
resolution happens in the assistant layer, above this API -- `POST .../slots/{slot_id}/request`
takes a `slot_id`, never an ordinal. So the sentence decomposes into one server obligation and one
client obligation, and only the first is testable here:

* **Server (asserted).** A request carrying a `displayed_recommendation_id` that no longer matches
  the freshly computed one must be **refused** (`SLOT_OPTIONS_STALE`, HTTP 409) and
  **re-presented** (`refreshed_options` carrying the *current* option set and its new
  `recommendation_id`), with **zero writes**. That is exactly what
  `allocation._validate_displayed_recommendation` -> `_stale_recommendation_result` does, and it
  runs *before* any capacity work, so a stale reply cannot reach `create_hold` at all.
* **Client (checked indirectly).** "Never applied to the new list" means ordinal 2 of the *old* list
  must not silently become ordinal 2 of the *new* one. This suite pins the old ordinal-2 slot id,
  submits that, and then asserts that nothing was booked for the shipment at all -- neither the old
  ordinal-2 slot nor the new one. It also reports whether the two ordinals actually differ, because
  if they happen to coincide the strongest form of the assertion is not being exercised and saying
  so is more useful than a green tick that means less than it looks like.

`recommendation_id` is a deterministic fingerprint, not a nonce -- `recommendation_id_for` hashes
`shipment_id | policy_version | effective_eta_ts | ordered option slot ids`
(`feasibility.py:264-274`). That is what makes this testable at all: an unchanged world returns the
same id, so a mismatch really does mean the list moved.

## How the re-rank is caused, and the fork left open for the owner

**Implemented (default):** the driver declares a new ETA for **their own** shipment through
`POST /api/v1/shipments/{id}/eta-updates`, shifted by `SETUHAUL_ORDINAL_ETA_SHIFT_MIN` (default 20)
from the shipment's *own current* effective ETA -- derived, never invented. That changes
`effective_eta_ts`, which is inside the fingerprint, and `eta_service` additionally sets the Redis
"recommendation is stale" marker for this user/shipment (`eta_service.py:567`), so both of the two
staleness gates are exercised.

**Alternative, not implemented (owner fork):** cause the re-rank by *contention* -- have a second
driver take the top-ranked slot, which drops it from the first driver's list. That is closer to the
chat scenario's "the world moved underneath you" flavour and writes no ETA, but it needs a second
seeded shipment sharing a facility and interval, and it makes the trigger probabilistic rather than
deterministic. Flagged here rather than silently chosen; set `SETUHAUL_ORDINAL_TRIGGER=contention`
is **not** wired -- the suite will refuse rather than pretend.

## Expect the positive control to FAIL on this build -- a real defect, found while writing this

Traced 2026-09-02, stated here because a red run should come with its diagnosis attached rather than
looking like a flaky suite:

* `eta_service` marks the Redis "recommendation is stale" flag on every ETA update
  (`eta_service.py:567`), with a 24-hour TTL (`redis_memory.TTL_SECONDS`).
* `allocation._validate_displayed_recommendation` refuses on that flag **alone** -- both branches
  check `redis_stale`, so a `request_slot` is refused `SLOT_OPTIONS_STALE` even when it carries the
  freshest possible `recommendation_id`, and even when it carries none at all.
* The only call to `clear_recommendation_stale` is `allocation.py:1976`, which sits **after** the
  two-phase early return at `allocation.py:1819`
  (`if get_settings().two_phase_hold_enabled: return await _request_slot_as_hold(...)`). Grepped:
  that is the sole call site in `backend/app`.

So with `TWO_PHASE_HOLD_ENABLED` on -- its default (`settings.py:177`) -- nothing ever clears the
flag, and a driver who declares a new ETA cannot take *any* slot for that shipment until the Redis
key expires a day later. §9.2 race 4 promises the driver is "rejected and **re-presented**"; on this
build the re-presented list cannot be acted on either. `leg4_positive_control` therefore fails with
`positive_control_blocked_by_sticky_stale_flag`, which is the finding, not a suite bug. It is also
why `leg3`'s pass is reported with a caveat: on this build the refusal is over-determined (stale
fingerprint *and* stuck flag), so it does not on its own prove the fingerprint comparison works.

## Target set for the coordinator's mutating run

| What | Value |
|---|---|
| Identity | `driver.resched@setuhaul.com` (DRV-RS-01) |
| Shipment | `SHP-RS-OPEN` -- reschedule sandbox, no appointment, has options, FAC-GGN-01 |
| Writes | one `eta_updates` row, `shipments.latest_eta_ts`, one `chat_messages` row (`record_eta_update`'s own footprint), plus one 90-second `HELD` row if the positive control runs |
| Leaves behind | nothing that needs cancelling -- the positive-control hold self-expires; no appointment is ever created |
| Reset | none needed (`reset_demo_day.py` never touches `RS`-prefixed rows). To restore the sandbox ETA exactly, re-seed with `supabase/demo/rollback_reschedule_driver.py --confirm` then `seed_reschedule_driver.py --confirm` |

    locust -f loadtests/locust_ordinal_staleness.py --headless -u 1 -r 1 -t 90s
"""

from __future__ import annotations

import os
import threading
from datetime import datetime, timedelta

import gevent
from locust import HttpUser, SequentialTaskSet, constant, events, task

from common import (
    SANDBOX_DRIVER_EMAIL,
    SANDBOX_OPEN_SHIPMENT,
    auth_headers,
    bff_host,
    env_flag,
    env_float,
    envelope_code,
    envelope_data,
    envelope_detail,
    idem_key,
    mutate_enabled,
    supabase_grant,
)

DRIVER_EMAIL = (os.environ.get("SETUHAUL_ORDINAL_DRIVER_EMAIL") or SANDBOX_DRIVER_EMAIL).strip()
SHIPMENT_ID = (os.environ.get("SETUHAUL_ORDINAL_SHIPMENT") or SANDBOX_OPEN_SHIPMENT).strip()
ETA_SHIFT_MIN = env_float("SETUHAUL_ORDINAL_ETA_SHIFT_MIN", 20.0)
TRIGGER = (os.environ.get("SETUHAUL_ORDINAL_TRIGGER") or "eta").strip().lower()
POSITIVE_CONTROL = env_flag("SETUHAUL_ORDINAL_POSITIVE_CONTROL", default=True)

STALE_CODE = "SLOT_OPTIONS_STALE"

_LOCK = threading.Lock()
_FINDINGS: list[tuple[str, bool, str]] = []

# A `SequentialTaskSet` restarts its task list as soon as it finishes, and `runner.quit()` takes a
# moment to land, so without this guard the flow could begin a *second* cycle -- and in mutating
# mode that second cycle is real writes nobody asked for. One run per process, claimed under a lock.
_RUN_CLAIMED = False


def _claim_the_single_run() -> bool:
    global _RUN_CLAIMED
    with _LOCK:
        if _RUN_CLAIMED:
            return False
        _RUN_CLAIMED = True
        return True



def _finding(name: str, passed: bool, detail: str) -> None:
    with _LOCK:
        _FINDINGS.append((name, passed, detail))
    print(f"ordinal_staleness: {'PASS' if passed else 'FAIL'} {name} -- {detail}")


def _note(detail: str) -> None:
    print(f"ordinal_staleness: NOTE {detail}")


@events.test_start.add_listener
def _reset(environment) -> None:
    global _RUN_CLAIMED
    with _LOCK:
        _FINDINGS.clear()
        _RUN_CLAIMED = False
    print(
        f"ordinal_staleness: shipment={SHIPMENT_ID} trigger={TRIGGER} "
        f"eta_shift={ETA_SHIFT_MIN:.0f}min "
        f"mutate={'ON' if mutate_enabled() else 'OFF (read-only wiring check)'}"
    )


@events.test_stop.add_listener
def _summarise(environment) -> None:
    with _LOCK:
        findings = list(_FINDINGS)
    if not mutate_enabled():
        print("ordinal_staleness: SKIPPED_WRITE_PHASE (SETUHAUL_LOCUST_MUTATE not set)")
        return
    failed = [f for f in findings if not f[1]]
    print(f"ordinal_staleness: {len(findings) - len(failed)}/{len(findings)} assertions passed")
    if failed or not findings:
        environment.process_exit_code = 1
        for name, _, detail in failed:
            print(f"ordinal_staleness: FAIL {name} -- {detail}")
        if not findings:
            print("ordinal_staleness: NO_ASSERTIONS_RECORDED")
    else:
        print("ordinal_staleness: PASS_rejected_and_represented_never_applied")


class OrdinalStalenessFlow(SequentialTaskSet):
    def on_start(self) -> None:
        self.headers = auth_headers(supabase_grant(DRIVER_EMAIL))
        self.rec_before = ""
        self.rec_after = ""
        self.policy_before = None
        self.policy_after = None
        self.old_ordinal_2 = ""
        self.new_ordinal_2 = ""
        self.new_ordinal_1 = ""
        self.effective_eta = ""
        self.aborted = False

    def _stop(self) -> None:
        self.aborted = True
        gevent.spawn_later(1.0, self.user.environment.runner.quit)

    def _feasible(self, name: str) -> dict:
        with self.user.client.get(
            f"/api/v1/shipments/{SHIPMENT_ID}/slots/feasible?limit=5",
            headers=self.headers,
            name=name,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"feasible_{response.status_code}")
                self.aborted = True
                return {}
            response.success()
            return envelope_data(response.json())

    @staticmethod
    def _slot_ids(data: dict) -> list[str]:
        return [
            str(o["slot_id"])
            for o in (data.get("options") or [])
            if isinstance(o, dict) and o.get("slot_id")
        ]

    @task
    def leg1_capture_the_displayed_list(self) -> None:
        if not _claim_the_single_run():
            return self._stop()
        if TRIGGER != "eta":
            _finding(
                "trigger_supported",
                False,
                f"SETUHAUL_ORDINAL_TRIGGER={TRIGGER} is not implemented; only 'eta' is wired "
                "(see this module's docstring for the contention alternative, an open owner fork)",
            )
            return self._stop()

        data = self._feasible("O1_feasible_before")
        # Baseline the live claim state: a control hold from a PREVIOUS run (90s TTL, unswept)
        # can still be visible here, and leg3's "never applied" check must be a DELTA against
        # this, not an absolute emptiness demand (false reds observed 2026-09-02).
        with self.user.client.get(
            f"/api/v1/shipments/{SHIPMENT_ID}/appointment-request/status",
            headers=self.headers, name="O1_status_baseline", catch_response=True,
        ) as response:
            base = envelope_data(response.json()) if response.status_code == 200 else {}
            response.success()
        self.baseline_hold_id = (base.get("hold") or {}).get("hold_id")
        if self.aborted or not data:
            return self._stop()
        slots = self._slot_ids(data)
        self.rec_before = str(data.get("recommendation_id") or "")
        self.policy_before = data.get("policy_version")
        self.effective_eta = str(data.get("effective_eta_ts") or "")
        print(
            f"ordinal_staleness: before recommendation_id={self.rec_before} "
            f"options={len(slots)} eta={self.effective_eta}"
        )

        if not mutate_enabled():
            print(
                "ordinal_staleness: read-only wiring OK -- "
                f"{SHIPMENT_ID} offers {len(slots)} option(s)"
            )
            return self._stop()

        if len(slots) < 2:
            _finding(
                "fixture_has_an_ordinal_2",
                False,
                f"{SHIPMENT_ID} offered {len(slots)} option(s); the scenario is about replying "
                "\"2\", so it needs at least two",
            )
            return self._stop()
        self.old_ordinal_2 = slots[1]
        _finding(
            "fixture_has_an_ordinal_2",
            True,
            f"old ordinal 2 = {self.old_ordinal_2}, recommendation_id={self.rec_before}",
        )

    @task
    def leg2_rerank_the_list(self) -> None:
        if self.aborted or not mutate_enabled():
            return
        # Derived from the shipment's own current ETA -- never a made-up instant.
        try:
            base = datetime.fromisoformat(self.effective_eta.replace("Z", "+00:00"))
        except ValueError:
            _finding("rerank_trigger", False, f"unparseable effective_eta_ts={self.effective_eta!r}")
            return self._stop()
        declared = (base + timedelta(minutes=ETA_SHIFT_MIN)).isoformat()
        key = idem_key("ordinal-eta")
        with self.user.client.post(
            f"/api/v1/shipments/{SHIPMENT_ID}/eta-updates",
            json={
                "declared_eta_ts": declared,
                # `record_eta_update` refuses to write unless the caller confirms the exact
                # interpreted instant (`eta_service.py:284`) -- the same two-step the driver chat
                # performs, not a bypass of it.
                "confirmed": True,
                "confirmation_eta_ts": declared,
                "confidence_code": "MEDIUM",
                "delay_reason_code": "TRAFFIC",
                "exception_type": "DELAY",
                "note": "§9.2 ordinal_staleness re-rank trigger (locust)",
                "client_message_id": key,
            },
            headers={**self.headers, "Idempotency-Key": key},
            name="O2_eta_update",
            catch_response=True,
        ) as response:
            payload = response.json() if response.content else {}
            ok = response.status_code == 200
            if ok:
                response.success()
            else:
                response.failure(f"eta_update_{response.status_code}")
        _finding(
            "rerank_trigger",
            ok,
            f"HTTP {response.status_code} declared_eta={declared} "
            f"{envelope_detail(payload)[:120]}",
        )
        if not ok:
            return self._stop()

        after = self._feasible("O3_feasible_after")
        if self.aborted or not after:
            return self._stop()
        self.rec_after = str(after.get("recommendation_id") or "")
        self.policy_after = after.get("policy_version")
        slots = self._slot_ids(after)
        self.new_ordinal_1 = slots[0] if slots else ""
        self.new_ordinal_2 = slots[1] if len(slots) > 1 else ""
        _finding(
            "list_was_actually_reranked",
            bool(self.rec_after) and self.rec_after != self.rec_before,
            f"before={self.rec_before} after={self.rec_after}",
        )
        if self.old_ordinal_2 and self.new_ordinal_2:
            if self.old_ordinal_2 == self.new_ordinal_2:
                _note(
                    "the slot at ordinal 2 is unchanged by this re-rank "
                    f"({self.old_ordinal_2}); the refusal is still asserted, but the "
                    "'different slot at the same ordinal' form of the race is not exercised"
                )
            else:
                _note(
                    f"ordinal 2 moved: old={self.old_ordinal_2} new={self.new_ordinal_2} "
                    "-- applying the old reply to the new list would book the wrong interval"
                )

    @task
    def leg3_stale_reply_is_rejected_and_represented(self) -> None:
        if self.aborted or not mutate_enabled() or not self.old_ordinal_2:
            return
        key = idem_key("ordinal-stale")
        with self.user.client.post(
            f"/api/v1/shipments/{SHIPMENT_ID}/slots/{self.old_ordinal_2}/request",
            json={
                "note": "§9.2 ordinal_staleness: reply '2' against the pre-rerank list (locust)",
                "displayed_policy_version": self.policy_before,
                # The whole point of this suite: the id the driver was *shown*, now stale.
                "displayed_recommendation_id": self.rec_before,
                "client_message_id": key,
            },
            headers={**self.headers, "Idempotency-Key": key},
            name="O4_request_with_stale_recommendation",
            catch_response=True,
        ) as response:
            payload = response.json() if response.content else {}
            status_code = response.status_code
            if status_code >= 500:
                response.failure(f"request_{status_code}")
            else:
                response.success()
        data = envelope_data(payload)
        code = envelope_code(payload)
        refreshed = data.get("refreshed_options") or {}

        _finding(
            "stale_reply_rejected",
            status_code == 409 and code == STALE_CODE,
            f"HTTP {status_code} code={code} "
            f"reason={(data.get('conflict') or {}).get('reason_code')} "
            "(over-determined on this build: the ETA update both changed the fingerprint and set "
            "the Redis stale flag -- see leg4 and the module docstring)",
        )
        _finding(
            "stale_reply_wrote_nothing",
            (data.get("appointment_writes") or 0) == 0
            and not data.get("appointment_id")
            and not data.get("hold_id"),
            f"appointment_writes={data.get('appointment_writes')} "
            f"appointment_id={data.get('appointment_id')} hold_id={data.get('hold_id')}",
        )
        _finding(
            "rejected_reply_is_re_presented",
            bool(refreshed.get("options")),
            f"refreshed option count={len(refreshed.get('options') or [])} "
            f"refreshed recommendation_id={refreshed.get('recommendation_id')}",
        )
        _finding(
            "re_presented_list_is_the_current_one",
            str(refreshed.get("recommendation_id") or "") == self.rec_after,
            f"refreshed={refreshed.get('recommendation_id')} current={self.rec_after}",
        )

        # "Never applied to the new list": nothing at all was claimed for this shipment -- not the
        # old ordinal-2 slot, and not whatever now sits at ordinal 2. One-shot: this status
        # read is only meaningful BEFORE leg4's positive control claims its own hold; on a
        # SequentialTaskSet re-entry it would misread the control's HELD as an applied stale
        # reply (false red observed 2026-09-02).
        if getattr(self, "_never_applied_checked", False):
            return
        self._never_applied_checked = True
        with self.user.client.get(
            f"/api/v1/shipments/{SHIPMENT_ID}/appointment-request/status",
            headers=self.headers,
            name="O5_status_after_stale_reply",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"status_{response.status_code}")
                status = {}
            else:
                response.success()
                status = envelope_data(response.json())
        _finding(
            "never_applied_to_the_new_list",
            # Terminal states prove non-application as well as emptiness does: the sandbox
            # fixture carries CANCELLED history from earlier verified runs (click-throughs,
            # suite 2's own lapse outcome), and demanding an empty promise_state misread that
            # history as an applied booking (fixed 2026-09-02 after a false red).
            status.get("promise_state") in (None, "", "CANCELLED", "EXPIRED", "HELD")
            and ((status.get("hold") or {}).get("hold_id") in (None, getattr(self, "baseline_hold_id", None)))
            and status.get("code") not in {"APPOINTMENT_PENDING_CONFIRMATION", "APPOINTMENT_CONFIRMED"},
            f"status code={status.get('code')} promise_state={status.get('promise_state')} "
            f"hold={'yes' if status.get('hold') else 'no'} "
            f"(old ordinal2={self.old_ordinal_2}, new ordinal2={self.new_ordinal_2})",
        )

    @task
    def leg4_positive_control(self) -> None:
        """The same request with the *fresh* id must succeed.

        Without this the suite could pass while the endpoint refused everything for an unrelated
        reason -- a refusal-only test cannot tell "correctly rejected because stale" from "broken".
        """
        if self.aborted or not mutate_enabled() or not POSITIVE_CONTROL:
            return self._stop()
        target = self.new_ordinal_1 or self.new_ordinal_2
        if not target or not self.rec_after:
            _finding("positive_control", False, "no fresh option to re-submit")
            return self._stop()
        key = idem_key("ordinal-fresh")
        with self.user.client.post(
            f"/api/v1/shipments/{SHIPMENT_ID}/slots/{target}/request",
            json={
                "note": "§9.2 ordinal_staleness positive control (locust)",
                "displayed_policy_version": self.policy_after,
                "displayed_recommendation_id": self.rec_after,
                "client_message_id": key,
            },
            headers={**self.headers, "Idempotency-Key": key},
            name="O6_request_with_fresh_recommendation",
            catch_response=True,
        ) as response:
            payload = response.json() if response.content else {}
            if response.status_code >= 500:
                response.failure(f"request_{response.status_code}")
            else:
                response.success()
        code = envelope_code(payload)
        if code == STALE_CODE:
            # Named rather than generic: this is the sticky-flag defect traced in the module
            # docstring, and a run that only said "positive control failed" would send the reader
            # hunting for a suite bug instead of the product one.
            _finding(
                "positive_control_blocked_by_sticky_stale_flag",
                False,
                f"a FRESH recommendation_id on {target} was still refused {STALE_CODE}. The Redis "
                "stale flag set by the ETA update is never cleared on the two-phase path: "
                "allocation.py:1976 (clear_recommendation_stale) is unreachable behind the "
                "TWO_PHASE_HOLD_ENABLED early return at allocation.py:1819, and it is the only "
                "call site. The driver cannot book this shipment until the 24h Redis TTL lapses",
            )
        else:
            _finding(
                "positive_control",
                code in {"SLOT_HELD", "SLOT_REQUESTED"},
                f"fresh recommendation on {target} -> {code} (HTTP {response.status_code}); "
                "a HELD row here self-expires in 90s and creates no appointment",
            )
        self._stop()


class OrdinalStalenessUser(HttpUser):
    host = bff_host()
    wait_time = constant(0.1)
    tasks = [OrdinalStalenessFlow]
