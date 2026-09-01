"""§9.2 race #2 -- `hold_expiry_vs_confirm`. Net-new (issue #42, sub-item 2).

Design citation: `SOLUTION_DESIGN.md` §9.2 race 2 (*"the 90-second hold lapses in the same
millisecond the driver confirms. Must resolve to exactly one outcome; never both a lapse notice and
a pending appointment"*), §0.8 (D2's TTL and the lazy-expiry rule), §4 (the promise lifecycle),
§7.1 (`confirm_held_slot`); `TESTING_STRATEGY.md` §3a row 2. Backend: `app/scheduling/holds.py`.

## The typed refusals this asserts, read out of the code rather than guessed

`holds.confirm_held_slot` resolves a dead hold through `_locked_hold` (which carries
`state = 'HELD' AND expires_at > :now`) and, on a miss, `_hold_epitaph`, which produces exactly two
codes (`holds.py:630-648`):

* **`HOLD_EXPIRED`** -- the row is still `HELD` but its deadline passed. §0.8's lazy expiry: *"Never
  depend on the sweeper for correctness -- only for hygiene."* This is the code the loser gets when
  the TTL wins, and it arrives as a 409 (`routers/scheduling.py:246`), never a 5xx.
* **`HOLD_ALREADY_ACTIONED`** -- the row left `HELD` some other way (the sweeper flipped it to
  `EXPIRED`, or it was already converted).

Both are `HOLD_EXPIRED`-class for the purposes of §9.2, and the suite accepts either as a valid
lapse outcome while reporting which one actually occurred -- they answer different questions about
*who* retired the hold, and flattening them would throw away the evidence M14 wants.

## The three legs, run in sequence by one virtual user

1. **Lapse leg (deterministic).** Take a hold, wait until `hold_expires_at + margin`, confirm.
   Must be a 409 with a `HOLD_EXPIRED`-class code and `appointment_writes == 0`, and the shipment's
   status read must show **no** `PENDING_CONFIRMATION` appointment -- the "never both" half of the
   §9.2 sentence, checked against durable state rather than against the response alone.
2. **Re-acquire leg.** Request the *same* interval again. Must come back `SLOT_HELD`. This is the
   issue #97 regression in miniature: the exclusion constraint's predicate carries no time term, so
   a lapsed-but-unswept `HELD` row goes on refusing overlapping inserts until something writes to
   it (`holds.expire_lapsed_holds_on_interval`). If this leg returns
   `SLOT_CONFLICT_REFRESH_REQUIRED`, the interval a lapsed hold no longer reserves is still blocked,
   and §0.8 is being violated by the table.
3. **Race leg.** Confirm the new hold at `hold_expires_at - lead_ms` -- the genuine "same
   millisecond" case. Exactly one outcome is acceptable and *both* are passes: either a
   `SLOT_REQUESTED` / `PENDING_CONFIRMATION` appointment exists and no lapse was reported, or a
   `HOLD_EXPIRED`-class refusal was returned and no appointment exists. Never both, never a 5xx.
   When `JOB_AUTH_TOKEN` is available the sweeper is fired at the same instant, so the third actor
   §9.2 mentions (`sweep_held_holds` vs `confirm_held_slot`) is in the race too; without it the leg
   still tests the lazy-expiry path, which §0.8 says is the correctness path anyway.

## Target set for the coordinator's mutating run

Self-provisioning on the **isolated reschedule sandbox**, which is why this scenario consumes no
cast row at all:

| What | Value |
|---|---|
| Identity | `driver.resched@setuhaul.com` (DRV-RS-01, seeded by `supabase/demo/seed_reschedule_driver.py`) |
| Shipment | `SHP-RS-OPEN` -- no appointment, has feasible options, at FAC-GGN-01 |
| Interval | whichever slot the shipment's own `feasible` call ranks first; never invented |
| Leaves behind | at most one `PENDING_CONFIRMATION` appointment (race leg won), which the suite then cancels; otherwise only `EXPIRED` `dock_occupancy` rows |
| Reset | none needed -- `reset_demo_day.py` never touches `RS`-prefixed rows in either mode |

Runtime is dominated by two 90-second TTLs plus margins, so budget `-t 5m`.

    locust -f loadtests/locust_hold_expiry_confirm.py --headless -u 1 -r 1 -t 5m
"""

from __future__ import annotations

import os
import threading

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
    job_headers,
    job_token,
    mutate_enabled,
    parse_iso_epoch,
    post_json,
    supabase_grant,
    wait_until,
)

DRIVER_EMAIL = (os.environ.get("SETUHAUL_HOLD_DRIVER_EMAIL") or SANDBOX_DRIVER_EMAIL).strip()
SHIPMENT_ID = (os.environ.get("SETUHAUL_HOLD_SHIPMENT") or SANDBOX_OPEN_SHIPMENT).strip()
# How far past `hold_expires_at` the deterministic lapse leg waits before confirming.
LAPSE_MARGIN_S = env_float("SETUHAUL_HOLD_LAPSE_MARGIN_S", 3.0)
# How far *before* `hold_expires_at` the race leg fires. 150 ms is inside a hosted round trip, so
# the request genuinely arrives around the deadline rather than comfortably before it.
RACE_LEAD_MS = env_float("SETUHAUL_HOLD_RACE_LEAD_MS", 150.0)
CLEANUP = env_flag("SETUHAUL_LOCUST_CLEANUP", default=True)

LAPSE_CODES = {"HOLD_EXPIRED", "HOLD_ALREADY_ACTIONED"}
CONFIRM_WIN_CODE = "SLOT_REQUESTED"

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
    print(f"hold_expiry_vs_confirm: {'PASS' if passed else 'FAIL'} {name} -- {detail}")


@events.test_start.add_listener
def _reset(environment) -> None:
    global _RUN_CLAIMED
    with _LOCK:
        _FINDINGS.clear()
        _RUN_CLAIMED = False
    print(
        f"hold_expiry_vs_confirm: shipment={SHIPMENT_ID} lapse_margin={LAPSE_MARGIN_S}s "
        f"race_lead={RACE_LEAD_MS}ms sweeper={'available' if job_token() else 'ABSENT'} "
        f"mutate={'ON' if mutate_enabled() else 'OFF (read-only wiring check)'}"
    )


@events.test_stop.add_listener
def _summarise(environment) -> None:
    with _LOCK:
        findings = list(_FINDINGS)
    if not mutate_enabled():
        print("hold_expiry_vs_confirm: SKIPPED_WRITE_PHASE (SETUHAUL_LOCUST_MUTATE not set)")
        return
    failed = [f for f in findings if not f[1]]
    print(f"hold_expiry_vs_confirm: {len(findings) - len(failed)}/{len(findings)} assertions passed")
    if failed or not findings:
        environment.process_exit_code = 1
        for name, _, detail in failed:
            print(f"hold_expiry_vs_confirm: FAIL {name} -- {detail}")
        if not findings:
            print("hold_expiry_vs_confirm: NO_ASSERTIONS_RECORDED (the flow never reached a leg)")
    else:
        print("hold_expiry_vs_confirm: PASS_exactly_one_outcome_no_5xx")


class HoldExpiryFlow(SequentialTaskSet):
    """One driver, three legs, in order. `-u 1` -- this is a correctness sequence, not load."""

    def on_start(self) -> None:
        self.headers = auth_headers(supabase_grant(DRIVER_EMAIL))
        self.slot_id = ""
        self.policy_version = None
        self.hold_id = ""
        self.hold_expires_epoch = None
        self.appointment_id = None
        self.aborted = False

    # ---------------- helpers ----------------

    def _feasible(self, name: str) -> list[dict]:
        with self.user.client.get(
            f"/api/v1/shipments/{SHIPMENT_ID}/slots/feasible?limit=5",
            headers=self.headers,
            name=name,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"feasible_{response.status_code}")
                self.aborted = True
                return []
            payload = response.json()
            data = envelope_data(payload)
            self.policy_version = data.get("policy_version")
            response.success()
            return [o for o in (data.get("options") or []) if isinstance(o, dict) and o.get("slot_id")]

    def _request_hold(self, slot_id: str, name: str) -> dict:
        key = idem_key("holdrace")
        with self.user.client.post(
            f"/api/v1/shipments/{SHIPMENT_ID}/slots/{slot_id}/request",
            json={
                "note": "§9.2 hold_expiry_vs_confirm (locust)",
                "displayed_policy_version": self.policy_version,
                "client_message_id": key,
            },
            headers={**self.headers, "Idempotency-Key": key},
            name=name,
            catch_response=True,
        ) as response:
            try:
                payload = response.json()
            except ValueError:
                response.failure("request_not_json")
                return {"status": response.status_code, "code": "NOT_JSON"}
            # A typed conflict is a legitimate answer on this route; only 5xx is a failure.
            if response.status_code >= 500:
                response.failure(f"request_{response.status_code}")
            else:
                response.success()
            data = envelope_data(payload)
            data["_status"] = response.status_code
            data["_code"] = envelope_code(payload)
            return data

    def _confirm_hold(self, hold_id: str, name: str) -> dict:
        key = idem_key("holdconfirm")
        with self.user.client.post(
            f"/api/v1/holds/{hold_id}/confirm",
            json={"note": "§9.2 hold_expiry_vs_confirm (locust)"},
            headers={**self.headers, "Idempotency-Key": key},
            name=name,
            catch_response=True,
        ) as response:
            try:
                payload = response.json()
            except ValueError:
                response.failure("confirm_not_json")
                return {"_status": response.status_code, "_code": "NOT_JSON", "_detail": ""}
            if response.status_code >= 500:
                response.failure(f"confirm_{response.status_code}")
            else:
                response.success()
            data = envelope_data(payload)
            data["_status"] = response.status_code
            data["_code"] = envelope_code(payload)
            data["_detail"] = envelope_detail(payload)
            return data

    def _status(self, name: str) -> dict:
        with self.user.client.get(
            f"/api/v1/shipments/{SHIPMENT_ID}/appointment-request/status",
            headers=self.headers,
            name=name,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"status_{response.status_code}")
                return {}
            response.success()
            return envelope_data(response.json())

    def _fire_sweeper(self) -> None:
        """The sweeper leg, fired from its own greenlet so it overlaps the confirm.

        Skipped with a stated reason when no token is configured. `routers/internal.py` documents
        the fail-closed posture on the other side: with `JOB_AUTH_TOKEN` unset the route answers 503
        and does nothing, so a missing token here would otherwise show up as an unexplained
        non-event.
        """
        token = job_token()
        if not token:
            _finding(
                "sweeper_leg",
                True,
                "SKIPPED: JOB_AUTH_TOKEN not set, so the D2 HELD sweep could not be raced; the "
                "lazy-expiry path in confirm_held_slot was still exercised (§0.8)",
            )
            return
        status, payload = post_json(
            f"{self.user.host}/internal/jobs/expiry-sweep", headers=job_headers(token)
        )
        held = (envelope_data(payload) or {}).get("held") or {}
        detail = (
            f"HTTP {status} supported={held.get('supported')} held_expired={held.get('expired')} "
            f"pending_expired={(envelope_data(payload) or {}).get('pending_expired')}"
        )
        _finding("sweeper_leg", status < 500 and status != 0, detail)

    def _stop(self) -> None:
        self.aborted = True
        gevent.spawn_later(1.0, self.user.environment.runner.quit)

    # ---------------- legs ----------------

    @task
    def leg1_take_hold_and_let_it_lapse(self) -> None:
        if not _claim_the_single_run():
            return self._stop()
        options = self._feasible("H1_feasible")
        if self.aborted:
            return self._stop()
        if not options:
            _finding("fixture", False, f"{SHIPMENT_ID} has no feasible options; nothing to hold")
            return self._stop()
        self.slot_id = str(options[0]["slot_id"])

        if not mutate_enabled():
            print(
                f"hold_expiry_vs_confirm: read-only wiring OK -- {SHIPMENT_ID} offers "
                f"{len(options)} option(s), first={self.slot_id}"
            )
            return self._stop()

        result = self._request_hold(self.slot_id, "H1_request_hold")
        code = result.get("_code")
        if code != "SLOT_HELD":
            _finding(
                "leg1_hold_acquired",
                False,
                f"expected SLOT_HELD, got {code} (HTTP {result.get('_status')}); "
                "TWO_PHASE_HOLD_ENABLED off, or the interval was already claimed",
            )
            return self._stop()
        self.hold_id = str(result.get("hold_id") or "")
        self.hold_expires_epoch = parse_iso_epoch(result.get("hold_expires_at"))
        _finding(
            "leg1_hold_acquired",
            bool(self.hold_id and self.hold_expires_epoch),
            f"hold_id={self.hold_id} ttl={result.get('hold_ttl_seconds')}s "
            f"expires_at={result.get('hold_expires_at')}",
        )
        if not self.hold_expires_epoch:
            return self._stop()

        # Deterministic lapse: wait past the deadline, then confirm.
        wait_until(self.hold_expires_epoch + LAPSE_MARGIN_S)
        lapsed = self._confirm_hold(self.hold_id, "H1_confirm_after_lapse")
        _finding(
            "leg1_lapsed_confirm_is_typed_409",
            lapsed.get("_status") == 409 and lapsed.get("_code") in LAPSE_CODES,
            f"HTTP {lapsed.get('_status')} code={lapsed.get('_code')} "
            f"writes={lapsed.get('appointment_writes')}",
        )
        _finding(
            "leg1_lapsed_confirm_wrote_nothing",
            (lapsed.get("appointment_writes") or 0) == 0 and not lapsed.get("appointment_id"),
            f"appointment_writes={lapsed.get('appointment_writes')} "
            f"appointment_id={lapsed.get('appointment_id')}",
        )
        status = self._status("H1_status_after_lapse")
        _finding(
            "leg1_no_pending_appointment_after_lapse",
            status.get("code") != "APPOINTMENT_PENDING_CONFIRMATION",
            f"status code={status.get('code')} promise_state={status.get('promise_state')} "
            "(§9.2: never both a lapse notice and a pending appointment)",
        )

    @task
    def leg2_reacquire_the_same_interval(self) -> None:
        if self.aborted or not mutate_enabled():
            return
        result = self._request_hold(self.slot_id, "H2_reacquire_same_interval")
        code = result.get("_code")
        _finding(
            "leg2_interval_reacquirable_after_lapse",
            code == "SLOT_HELD",
            f"code={code} HTTP {result.get('_status')} "
            f"reason={(result.get('conflict') or {}).get('reason_code')} "
            "(a lapsed HELD row must not keep blocking -- issue #97 lazy expiry)",
        )
        if code != "SLOT_HELD":
            return self._stop()
        self.hold_id = str(result.get("hold_id") or "")
        self.hold_expires_epoch = parse_iso_epoch(result.get("hold_expires_at"))
        if not self.hold_expires_epoch:
            return self._stop()

    @task
    def leg3_confirm_in_the_same_millisecond_as_expiry(self) -> None:
        if self.aborted or not mutate_enabled() or not self.hold_expires_epoch:
            return
        # Both actors leave at the same instant: the driver's confirm here, the sweeper on its own
        # greenlet. `spawn` rather than a sequential call so they genuinely overlap.
        target = self.hold_expires_epoch - (RACE_LEAD_MS / 1000.0)
        wait_until(target)
        sweeper = gevent.spawn(self._fire_sweeper)
        confirmed = self._confirm_hold(self.hold_id, "H3_confirm_at_deadline")
        sweeper.join(timeout=30)

        code = confirmed.get("_code")
        status_code = confirmed.get("_status")
        _finding(
            "leg3_no_5xx",
            isinstance(status_code, int) and 0 < status_code < 500,
            f"HTTP {status_code} code={code}",
        )
        confirm_won = code == CONFIRM_WIN_CODE and status_code == 200
        lapse_won = code in LAPSE_CODES
        _finding(
            "leg3_exactly_one_typed_outcome",
            confirm_won != lapse_won,
            f"confirm_won={confirm_won} lapse_won={lapse_won} code={code} "
            f"detail={(confirmed.get('_detail') or '')[:120]}",
        )

        status = self._status("H3_status_after_race")
        durable_pending = status.get("code") == "APPOINTMENT_PENDING_CONFIRMATION"
        _finding(
            "leg3_response_matches_durable_state",
            durable_pending == confirm_won,
            f"response_said_confirmed={confirm_won} durable_pending={durable_pending} "
            f"status_code={status.get('code')} promise_state={status.get('promise_state')}",
        )
        self.appointment_id = confirmed.get("appointment_id") or status.get("appointment_id")

        if confirm_won and CLEANUP and self.appointment_id:
            key = idem_key("holdcleanup")
            with self.user.client.post(
                f"/api/v1/shipments/{SHIPMENT_ID}/appointments/{self.appointment_id}/cancel",
                json={
                    "cancellation_reason": "locust §9.2 hold_expiry_vs_confirm cleanup",
                    "client_message_id": key,
                },
                headers={**self.headers, "Idempotency-Key": key},
                name="H4_cleanup_cancel",
                catch_response=True,
            ) as response:
                ok = response.status_code == 200
                response.success() if ok else response.failure(f"cleanup_{response.status_code}")
                _finding("cleanup_cancel", ok, f"HTTP {response.status_code} {self.appointment_id}")
        self._stop()


class HoldExpiryUser(HttpUser):
    host = bff_host()
    wait_time = constant(0.1)
    tasks = [HoldExpiryFlow]
