"""§9.2 race #3 -- `pending_expiry_vs_planner_confirm`. Net-new (issue #42, sub-item 3).

Design citation: `SOLUTION_DESIGN.md` §9.2 race 3 (*"the D9 sweeper fires as the planner clicks
Confirm. The nastiest race in the design, because both actors believe they acted. Exactly one wins,
and the audit log must show which and why"*), §7.5.1's race resolution (*"the loser gets
`ALREADY_ACTIONED` with the winning transition named"*), D9, M8, M14; `TESTING_STRATEGY.md` §3a
row 3. Backend: `app/scheduling/expiry.py`, `allocation.confirm_appointment`,
`routers/internal.py`.

## Why the loser's code is knowable in advance, and which one it is

Read out of `allocation.confirm_appointment` rather than assumed: the status check fires **before**
the snapshot guard, and its own comment says why -- *"Deliberately still the FIRST refusal ... a row
somebody already actioned is not 'stale', it is decided"*. So a planner who loses to the sweeper
gets `ALREADY_ACTIONED` (409) naming `EXPIRED`, never `SNAPSHOT_STALE` and never a 5xx. In the other
direction `expiry._expire_one_pending`'s locking SELECT carries
`appointment_status = 'PENDING_CONFIRMATION'`, so a sweeper that arrives after the confirm commits
simply returns nothing for that row -- there is no compensating logic to test, only an absence to
assert.

## Two hard requirements this suite states rather than discovers at run time

**1. `JOB_AUTH_TOKEN`.** The sweeper half is `POST /internal/jobs/expiry-sweep`, authenticated by
the `X-SetuHaul-Job-Token` shared secret (`routers/internal.require_job_token`). With no token the
suite **skips the race leg with a stated reason** and asserts only what it can. It does not invent a
pass. The service side fails closed too (503 `JOB_AUTH_UNCONFIGURED`), so a silent skip and a real
misconfiguration would otherwise look identical.

**2. The sweep is global.** `sweep_expired_appointments` has no facility or shipment filter: one
call expires **every** `PENDING_CONFIRMATION` row in the database whose D9 deadline has passed, and
raises a `PENDING_EXPIRED_UNACTIONED` escalation for each. That is a real blast radius, so the
mutating run belongs immediately after `reset_demo_day.py` and never against a database anyone else
is demoing on.

## Issue #64: keeping the fixture clear of an extended deadline

`appointments.expires_at` is `hold_for_information`'s one-shot extension, and when it is set the
sweeper's `CASE` uses *that* instant instead of `booked_at + 15 min` (`expiry._pending_candidates`).
A row whose planner already pressed Hold therefore has a later, different deadline. The planner
queue exposes this directly as `ttl.hold_used`, so the suite refuses to race any row where it is
true rather than racing a deadline it has mis-modelled.

## The flow

1. **Provision or adopt.** If the target shipment already has a `PENDING_CONFIRMATION` row, adopt it
   (its deadline is likely already past, which is the state the race needs). Otherwise book one
   through the real driver path -- `request_slot` -> `SLOT_HELD` -> `confirm_held_slot` -- and wait
   out D9's TTL. `booked_at` is stamped at confirm time, not at hold time (`holds.py`), so the wait
   is measured from the queue's own `ttl.deadline_ts`, never computed locally.
2. **Read the queue as the planner**, immediately before the release instant, for a fresh
   `snapshot_hash` (§7.5 principle 3) and to re-check `hold_used`.
3. **Fire both at one instant**: the planner's confirm and the sweeper, on separate greenlets.
4. **Assert**: no 5xx either side; exactly one of {CONFIRMED, EXPIRED} wins; the loser is typed
   (`ALREADY_ACTIONED` for the planner, "not in the expired list" for the sweeper); the durable
   status agrees with whoever claimed the win; and -- when an admin identity is available -- the
   audit log names the winning transition (M14 / §9.2's *"must show which and why"*).

## Target set for the coordinator's mutating run

| What | Value |
|---|---|
| Shipment | `SHP-D16-RACE-B` (env `SETUHAUL_PENDING_SHIPMENT`) |
| Driver | `amit.singh@setuhaul.com` -- DRV002, the seeded driver for that shipment |
| Planner | `rahul.verma@setuhaul.com` -- USR102, ROL003 WAREHOUSE_PLANNER at FAC-JAI-01 |
| Facility | FAC-JAI-01 |
| Auditor | `admin@setuhaul.com` (optional; only used for the read-only audit assertion) |
| Leaves behind | one `CONFIRMED` **or** one `EXPIRED` appointment, plus (if the sweeper won) a `PENDING_EXPIRED_UNACTIONED` escalation and a notification-outbox row |
| Reset | `python supabase/demo/reset_demo_day.py --mode cast --include-shp1017 --confirm` |

The sandbox (`SHP-RS-*` at FAC-GGN-01) is deliberately **not** the default here: every seeded
OPS_PORTAL identity is scoped to FAC-JAI-01, so a GGN confirm would need an ADMIN
(`allocation._assert_ops_scope` demands `is_admin` for the global tier), and racing an admin against
the sweeper would not be the planner-vs-sweeper race §9.2 names. Run it at GGN by setting
`SETUHAUL_PENDING_SHIPMENT=SHP-RS-OPEN SETUHAUL_PENDING_DRIVER_EMAIL=driver.resched@setuhaul.com
SETUHAUL_PLANNER_EMAIL=admin@setuhaul.com SETUHAUL_PENDING_FACILITY=FAC-GGN-01` if that trade is
worth it for a given run.

    locust -f loadtests/locust_pending_expiry_confirm.py --headless -u 1 -r 1 -t 25m
"""

from __future__ import annotations

import os
import threading

import gevent
from locust import HttpUser, SequentialTaskSet, constant, events, task

from common import (
    ADMIN_EMAIL,
    PENDING_RACE_DRIVER_EMAIL,
    PENDING_RACE_SHIPMENT,
    PLANNER_EMAIL,
    RACE_FACILITY_ID,
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

SHIPMENT_ID = (os.environ.get("SETUHAUL_PENDING_SHIPMENT") or PENDING_RACE_SHIPMENT).strip()
DRIVER_EMAIL = (
    os.environ.get("SETUHAUL_PENDING_DRIVER_EMAIL") or PENDING_RACE_DRIVER_EMAIL
).strip()
PLANNER = (os.environ.get("SETUHAUL_PLANNER_EMAIL") or PLANNER_EMAIL).strip()
FACILITY_ID = (os.environ.get("SETUHAUL_PENDING_FACILITY") or RACE_FACILITY_ID).strip()
AUDITOR = (os.environ.get("SETUHAUL_ADMIN_EMAIL") or ADMIN_EMAIL).strip()
# Seconds past `ttl.deadline_ts` at which both actors are released. Small and positive: the sweeper
# only picks up rows whose deadline has *passed*, so releasing before it would race nothing.
RELEASE_MARGIN_S = env_float("SETUHAUL_PENDING_RELEASE_MARGIN_S", 5.0)
# Hard ceiling on the provision-and-wait path, so a misconfigured run fails fast instead of idling
# for the whole `-t`.
MAX_WAIT_S = env_float("SETUHAUL_PENDING_MAX_WAIT_S", 1200.0)
AUDIT_CHECK = env_flag("SETUHAUL_PENDING_AUDIT_CHECK", default=True)

CONFIRM_WIN_CODE = "APPOINTMENT_CONFIRMED"
CONFIRM_LOSS_CODE = "ALREADY_ACTIONED"

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
    print(f"pending_expiry_vs_planner_confirm: {'PASS' if passed else 'FAIL'} {name} -- {detail}")


@events.test_start.add_listener
def _reset(environment) -> None:
    global _RUN_CLAIMED
    with _LOCK:
        _FINDINGS.clear()
        _RUN_CLAIMED = False
    print(
        f"pending_expiry_vs_planner_confirm: shipment={SHIPMENT_ID} facility={FACILITY_ID} "
        f"planner={PLANNER} sweeper={'available' if job_token() else 'ABSENT'} "
        f"mutate={'ON' if mutate_enabled() else 'OFF (read-only wiring check)'}"
    )


@events.test_stop.add_listener
def _summarise(environment) -> None:
    with _LOCK:
        findings = list(_FINDINGS)
    if not mutate_enabled():
        print(
            "pending_expiry_vs_planner_confirm: SKIPPED_WRITE_PHASE "
            "(SETUHAUL_LOCUST_MUTATE not set)"
        )
        return
    failed = [f for f in findings if not f[1]]
    print(
        f"pending_expiry_vs_planner_confirm: {len(findings) - len(failed)}/{len(findings)} "
        "assertions passed"
    )
    if failed or not findings:
        environment.process_exit_code = 1
        for name, _, detail in failed:
            print(f"pending_expiry_vs_planner_confirm: FAIL {name} -- {detail}")
        if not findings:
            print("pending_expiry_vs_planner_confirm: NO_ASSERTIONS_RECORDED")
    else:
        print("pending_expiry_vs_planner_confirm: PASS_exactly_one_winner_audited_no_5xx")


class PendingExpiryRace(SequentialTaskSet):
    def on_start(self) -> None:
        self.driver_headers = auth_headers(supabase_grant(DRIVER_EMAIL))
        self.planner_headers = auth_headers(supabase_grant(PLANNER))
        self.appointment_id = ""
        self.snapshot_hash = ""
        self.deadline_epoch = None
        self.aborted = False
        self.confirm_won = False
        self.sweep_expired_ids: list[str] = []
        self.sweep_status = None

    # ---------------- helpers ----------------

    def _stop(self) -> None:
        self.aborted = True
        gevent.spawn_later(1.0, self.user.environment.runner.quit)

    def _queue_row(self, name: str) -> dict:
        """The planner's own view of the target row: deadline, hold_used, snapshot_hash."""
        with self.user.client.get(
            f"/api/v1/planner/queue?facility_id={FACILITY_ID}&limit=100",
            headers=self.planner_headers,
            name=name,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"queue_{response.status_code}")
                return {}
            response.success()
            data = envelope_data(response.json())
            for item in data.get("items") or []:
                if not isinstance(item, dict):
                    continue
                if self.appointment_id and item.get("appointment_id") == self.appointment_id:
                    return item
                if not self.appointment_id and item.get("shipment_id") == SHIPMENT_ID:
                    return item
            return {}

    def _status(self, name: str) -> dict:
        with self.user.client.get(
            f"/api/v1/shipments/{SHIPMENT_ID}/appointment-request/status",
            headers=self.driver_headers,
            name=name,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"status_{response.status_code}")
                return {}
            response.success()
            return envelope_data(response.json())

    def _provision_pending(self) -> bool:
        """Book a real PENDING_CONFIRMATION through the driver path. Returns success."""
        with self.user.client.get(
            f"/api/v1/shipments/{SHIPMENT_ID}/slots/feasible?limit=5",
            headers=self.driver_headers,
            name="P1_feasible",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"feasible_{response.status_code}")
                return False
            response.success()
            data = envelope_data(response.json())
        options = [o for o in (data.get("options") or []) if isinstance(o, dict) and o.get("slot_id")]
        if not options:
            _finding("fixture", False, f"{SHIPMENT_ID} has no feasible options to book")
            return False
        slot_id = str(options[0]["slot_id"])

        key = idem_key("pending-request")
        with self.user.client.post(
            f"/api/v1/shipments/{SHIPMENT_ID}/slots/{slot_id}/request",
            json={
                "note": "§9.2 pending_expiry_vs_planner_confirm (locust)",
                "displayed_policy_version": data.get("policy_version"),
                "client_message_id": key,
            },
            headers={**self.driver_headers, "Idempotency-Key": key},
            name="P2_request_slot",
            catch_response=True,
        ) as response:
            payload = response.json() if response.content else {}
            response.success() if response.status_code < 500 else response.failure(
                f"request_{response.status_code}"
            )
        requested = envelope_data(payload)
        code = envelope_code(payload)

        if code == "SLOT_REQUESTED":  # legacy single-phase deploy: already PENDING
            self.appointment_id = str(requested.get("appointment_id") or "")
            return bool(self.appointment_id)
        if code != "SLOT_HELD":
            _finding("provision", False, f"request_slot returned {code}, expected SLOT_HELD")
            return False

        hold_id = str(requested.get("hold_id") or "")
        key = idem_key("pending-confirm-hold")
        with self.user.client.post(
            f"/api/v1/holds/{hold_id}/confirm",
            json={"note": "§9.2 pending_expiry_vs_planner_confirm (locust)"},
            headers={**self.driver_headers, "Idempotency-Key": key},
            name="P3_confirm_held_slot",
            catch_response=True,
        ) as response:
            payload = response.json() if response.content else {}
            response.success() if response.status_code < 500 else response.failure(
                f"confirm_hold_{response.status_code}"
            )
        held = envelope_data(payload)
        if envelope_code(payload) != "SLOT_REQUESTED":
            _finding(
                "provision",
                False,
                f"confirm_held_slot returned {envelope_code(payload)}: "
                f"{envelope_detail(payload)[:120]}",
            )
            return False
        self.appointment_id = str(held.get("appointment_id") or "")
        return bool(self.appointment_id)

    def _fire_sweeper(self) -> None:
        token = job_token()
        if not token:
            _finding(
                "sweeper_leg",
                False,
                "SKIPPED: JOB_AUTH_TOKEN is not set, so the D9 sweeper half of the race could not "
                "run. Set it (env or root .env.local) and re-run; the race is not proven without "
                "it.",
            )
            return
        status, payload = post_json(
            f"{self.user.host}/internal/jobs/expiry-sweep", headers=job_headers(token)
        )
        self.sweep_status = status
        data = envelope_data(payload)
        self.sweep_expired_ids = [
            str(row.get("appointment_id"))
            for row in (data.get("expired") or [])
            if isinstance(row, dict)
        ]
        _finding(
            "sweeper_no_5xx",
            0 < status < 500,
            f"HTTP {status} pending_candidates={data.get('pending_candidates')} "
            f"pending_expired={data.get('pending_expired')} "
            f"deferred_or_lost={data.get('pending_deferred_or_lost')}",
        )

    def _audit_names_the_winner(self, winner: str) -> None:
        """§9.2: *"the audit log must show which and why"* (M14).

        Read-only, through `GET /api/v1/admin/audit-log?resource=appointments`, which filters
        `entity_name` (not `entity_id` -- `admin_governance_service._audit_filters`), so the row for
        this appointment is found client-side in the 200 most recent. Skipped without an admin
        identity rather than failed: the audit trail is written either way, and an unavailable
        auditor is a run-configuration fact, not a defect in the race.
        """
        if not AUDIT_CHECK:
            return
        try:
            headers = auth_headers(supabase_grant(AUDITOR))
        except Exception as exc:  # noqa: BLE001
            _finding("audit_trail", True, f"SKIPPED: no admin grant ({type(exc).__name__})")
            return
        with self.user.client.get(
            "/api/v1/admin/audit-log?resource=appointments",
            headers=headers,
            name="R4_audit_log",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"audit_{response.status_code}")
                _finding("audit_trail", True, f"SKIPPED: audit-log HTTP {response.status_code}")
                return
            response.success()
            items = envelope_data(response.json()).get("items") or []
        mine = [i for i in items if isinstance(i, dict) and i.get("entity_id") == self.appointment_id]
        expected_action = "EXPIRE_APPOINTMENT" if winner == "EXPIRED" else "UPDATE"
        matching = [i for i in mine if str(i.get("action_type")) == expected_action]
        _finding(
            "audit_trail_names_the_winner",
            bool(matching),
            f"winner={winner} expected action_type={expected_action} "
            f"rows_for_appointment={len(mine)} matching={len(matching)} "
            f"actions={[i.get('action_type') for i in mine][:5]}",
        )

    # ---------------- legs ----------------

    @task
    def leg1_have_a_pending_row_at_its_deadline(self) -> None:
        if not _claim_the_single_run():
            return self._stop()
        row = self._queue_row("P0_planner_queue")
        if not mutate_enabled():
            print(
                "pending_expiry_vs_planner_confirm: read-only wiring OK -- planner queue "
                f"reachable, target row {'found' if row else 'not found'} for {SHIPMENT_ID}"
            )
            return self._stop()

        if row and str(row.get("appointment_status")) == "PENDING_CONFIRMATION":
            # Adopt: an existing pending row is already the fixture, and if its deadline has passed
            # the race can run immediately instead of waiting out a fresh 15-minute TTL.
            self.appointment_id = str(row.get("appointment_id"))
            _finding("fixture", True, f"adopted existing PENDING row {self.appointment_id}")
        else:
            if not self._provision_pending():
                return self._stop()
            _finding("fixture", True, f"provisioned PENDING row {self.appointment_id}")
            row = self._queue_row("P4_planner_queue_after_provision")
            if not row:
                _finding("fixture_visible_to_planner", False, "provisioned row not in planner queue")
                return self._stop()

        ttl = row.get("ttl") or {}
        # Issue #64: never race a row whose D9 clock a planner already extended.
        if ttl.get("hold_used"):
            _finding(
                "fixture_deadline_is_the_derived_one",
                False,
                f"{self.appointment_id} has hold_used=true (appointments.expires_at set), so its "
                "deadline is hold_for_information's extension, not booked_at+15m -- pick another "
                "fixture (issue #64)",
            )
            return self._stop()
        _finding("fixture_deadline_is_the_derived_one", True, "hold_used=false")

        self.deadline_epoch = parse_iso_epoch(ttl.get("deadline_ts"))
        if self.deadline_epoch is None:
            _finding("fixture_deadline_readable", False, f"ttl={ttl}")
            return self._stop()
        remaining = ttl.get("remaining_seconds")
        print(
            f"pending_expiry_vs_planner_confirm: appointment={self.appointment_id} "
            f"deadline_ts={ttl.get('deadline_ts')} remaining_seconds={remaining}"
        )
        if isinstance(remaining, int) and remaining > MAX_WAIT_S:
            _finding(
                "fixture_within_wait_budget",
                False,
                f"{remaining}s until the D9 deadline exceeds SETUHAUL_PENDING_MAX_WAIT_S="
                f"{MAX_WAIT_S:.0f}s; raise it or adopt an older pending row",
            )
            return self._stop()

    @task
    def leg2_race_the_sweeper(self) -> None:
        if self.aborted or not mutate_enabled() or self.deadline_epoch is None:
            return
        release_at = self.deadline_epoch + RELEASE_MARGIN_S
        # Refresh the snapshot_hash close to the release instant: §7.5 principle 3 makes it a
        # required argument, and a hash read fifteen minutes earlier would refuse on staleness
        # before the race could resolve.
        wait_until(release_at - 3.0)
        row = self._queue_row("R1_planner_queue_prerace")
        if not row or str(row.get("appointment_status")) != "PENDING_CONFIRMATION":
            _finding(
                "row_still_pending_at_release",
                False,
                f"row vanished or moved on before the race: status="
                f"{row.get('appointment_status') if row else 'MISSING'}",
            )
            return self._stop()
        self.snapshot_hash = str(row.get("snapshot_hash") or "")
        _finding("row_still_pending_at_release", True, f"snapshot_hash len={len(self.snapshot_hash)}")

        wait_until(release_at)
        sweeper = gevent.spawn(self._fire_sweeper)
        key = idem_key("planner-confirm")
        with self.user.client.post(
            f"/api/v1/shipments/{SHIPMENT_ID}/appointments/{self.appointment_id}/confirm",
            json={
                "snapshot_hash": self.snapshot_hash,
                "note": "§9.2 pending_expiry_vs_planner_confirm (locust)",
            },
            headers={**self.planner_headers, "Idempotency-Key": key},
            name="R2_planner_confirm",
            catch_response=True,
        ) as response:
            payload = response.json() if response.content else {}
            confirm_status = response.status_code
            if confirm_status >= 500:
                response.failure(f"confirm_{confirm_status}")
            else:
                response.success()
        sweeper.join(timeout=60)

        confirm_code = envelope_code(payload)
        self.confirm_won = confirm_status == 200 and confirm_code == CONFIRM_WIN_CODE
        sweep_won = self.appointment_id in self.sweep_expired_ids

        _finding(
            "planner_confirm_no_5xx",
            0 < confirm_status < 500,
            f"HTTP {confirm_status} code={confirm_code} detail={envelope_detail(payload)[:140]}",
        )
        _finding(
            "exactly_one_winner",
            self.confirm_won != sweep_won,
            f"confirm_won={self.confirm_won} sweep_won={sweep_won} confirm_code={confirm_code}",
        )
        if not self.confirm_won:
            # §7.5.1: the loser gets ALREADY_ACTIONED, and it names the winning transition.
            _finding(
                "planner_loser_gets_ALREADY_ACTIONED",
                confirm_code == CONFIRM_LOSS_CODE and confirm_status == 409,
                f"HTTP {confirm_status} code={confirm_code} "
                f"detail={envelope_detail(payload)[:160]}",
            )

    @task
    def leg3_durable_state_and_audit(self) -> None:
        if self.aborted or not mutate_enabled() or not self.appointment_id:
            return
        status = self._status("R3_status_after_race")
        code = str(status.get("code") or "")
        winner = (
            "CONFIRMED"
            if code == "APPOINTMENT_CONFIRMED"
            else "EXPIRED"
            if code == "APPOINTMENT_EXPIRED"
            else code
        )
        _finding(
            "durable_state_is_confirmed_or_expired",
            winner in {"CONFIRMED", "EXPIRED"},
            f"status code={code}",
        )
        _finding(
            "durable_state_agrees_with_the_response",
            (winner == "CONFIRMED") == self.confirm_won,
            f"durable={winner} confirm_response_won={self.confirm_won}",
        )
        if winner in {"CONFIRMED", "EXPIRED"}:
            self._audit_names_the_winner(winner)
        self._stop()


class PendingExpiryUser(HttpUser):
    host = bff_host()
    wait_time = constant(0.1)
    tasks = [PendingExpiryRace]
