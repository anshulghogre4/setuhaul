"""Suite B / §9.2 race #1 -- `same_interval_race` at E1.1's 50-way target (REST, no LLM).

Design citation: `SOLUTION_DESIGN.md` §9.2 race 1 (*"50 simultaneous requests on one interval →
exactly 1 `HELD`, 49 `SLOT_CONFLICT_REFRESH_REQUIRED`, zero 5xx"*) and §10.1; `TESTING_STRATEGY.md`
§3a row 1 and §11 risk #2. GitHub issue #42, sub-item 1 ("extend, don't write a new suite").

## What changed from the 10-driver version, and why each change was necessary

**1. One interval, not ten.** The original picked `options[0]` per driver, so ten drivers at
FAC-JAI-01 spread across whatever the four open evening slots offered them, and the assertion was
only *"no slot has two winners"*. That is a double-booking test, not `same_interval_race`. Every
user now races the *same* `slot_id` -- `D16-SLT-RACE` (DOCK-JAI-D1 19:00-19:30), the one interval
the demo generator reserves for exactly this (`generate_demo_day.py`'s `race_window`).

The slot id is still never invented: each user reads `GET .../slots/feasible` first and records
whether the target appears in its own option set. Where it does, that user's refusal is genuine D1
contention; where it does not, the server still answers with a *typed* refusal (a Stage-1
feasibility failure is wrapped in the same `SLOT_CONFLICT_REFRESH_REQUIRED` code by
`allocation._conflict_result`), so the headline split holds either way and the reason-code
breakdown below says which happened.

**2. The winner is `SLOT_HELD`, not `SLOT_REQUESTED`.** `TWO_PHASE_HOLD_ENABLED` defaults to true
(`app/core/settings.py:177`), so `request_slot` ends in `_request_slot_as_hold` and returns
`status="HELD"` / `code="SLOT_HELD"` with `appointment_id=None` and `appointment_writes=0`
(`allocation.py:1593-1610`). §10.1 is explicit that this is the correct winning outcome:
*"PENDING_CONFIRMATION only follows a `confirm_held_slot` inside the TTL"*. The suite accepts
`SLOT_REQUESTED` as the winner too, but only reports it as the legacy single-phase path -- it is
what a deploy with the flag off would produce, and calling that a failure would misdiagnose a
configuration as a defect.

**3. No `displayed_recommendation_id` is sent.** This one is load-bearing and was verified by
reading the write path rather than assumed. Since issue #97, `find_feasible_slots` anti-joins live
`dock_occupancy` claims (`feasibility.py:143-183`), so the instant the winner's hold commits, every
other user's recomputed option list *loses this slot* and therefore has a different
`recommendation_id`. `allocation._validate_displayed_recommendation` compares the displayed id
against a freshly computed one, so had the suite sent it, most losers would come back
`SLOT_OPTIONS_STALE` instead of `SLOT_CONFLICT_REFRESH_REQUIRED` and the §9.2 split would fail for
a reason that is not a defect. The proof suite's own N=50 harness sends exactly the same command
shape this suite now sends -- `note` + `displayed_policy_version`, no recommendation id
(`backend/tests/proof/test_part1_concurrency.py:_one_request`).

**4. An explicit release barrier.** `TESTING_STRATEGY.md` §11 risk #2: *"Ramping 50 VUs is not the
same as 50 requests landing together."* Users arm (token, feasibility read) during a spawn window
and then all block on one absolute wall-clock instant -- see `common.ReleaseBarrier` for why an
instant rather than a counting barrier.

**5. The POST is behind `SETUHAUL_LOCUST_MUTATE=1`.** The 10-driver version wrote unconditionally,
which contradicted the README's own guard. Without the flag this file now performs the read half
only and prints a wiring report; it never books anything.

## Target set for the coordinator's mutating run

| What | Value |
|---|---|
| Contested interval | `D16-SLT-RACE` -- DOCK-JAI-D1, 19:00-19:30, FAC-JAI-01 |
| Identities | the ten contention drivers `driver.drv004@` - `driver.drv013@` |
| Shipments | `SHP-D16-CONTEND-01` .. `-10`, round-robin across the 50 users |
| Leaves behind | one live `HELD` `dock_occupancy` row, self-expiring in 90 s; no appointment |
| Reset | `python supabase/demo/reset_demo_day.py --mode cast --include-shp1017 --confirm` |

Fifty users over ten shipments means five users share each shipment. That is deliberate and does
not weaken the test: a hold creates no `appointments` row (§4), so `request_slot`'s
active-appointment pre-check cannot see a sibling's hold, and all five reach `create_hold` and
contend on the exclusion constraint like everyone else.

    locust -f loadtests/locust_slot_contention.py --headless -u 50 -r 50 -t 90s
"""

from __future__ import annotations

import os
import threading
import uuid
from collections import Counter, defaultdict

import gevent
from locust import HttpUser, constant, events, task

from common import (
    CONTEND_CAST,
    RACE_SLOT_ID,
    ReleaseBarrier,
    auth_headers,
    bff_host,
    env_float,
    envelope_data,
    idem_key,
    mutate_enabled,
    supabase_grant,
)

TARGET_SLOT_ID = (os.environ.get("SETUHAUL_RACE_SLOT_ID") or RACE_SLOT_ID).strip()
# `named` (default): race the configured interval, and refuse to race at all if the arming reads
# show it is not on offer to anybody -- see `_resolve_target`. `leader`: fall back to the interval
# most of the armed users rank first, which keeps a run productive on a cast whose evening capacity
# is already consumed, at the cost of racing an interval the report then has to name explicitly.
TARGET_MODE = (os.environ.get("SETUHAUL_RACE_TARGET_MODE") or "named").strip().lower()
# The arming window: long enough for `-r 50` to finish spawning and for every user's token grant
# and feasibility read to complete. Ten Supabase grants (cached per identity) plus fifty
# `GET .../feasible` calls fit comfortably; raise it for a hosted run on a slow link.
ARM_SECONDS = env_float("SETUHAUL_RACE_ARM_SECONDS", 20.0)

WINNER_CODES = {"SLOT_HELD", "SLOT_REQUESTED"}
REFUSAL_CODE = "SLOT_CONFLICT_REFRESH_REQUIRED"
# The reason code `allocation` stamps when PostgreSQL itself refused the claim -- the only outcome
# that is direct evidence D1's exclusion constraint did the deciding (`allocation.py:1573`,
# `holds.create_hold`'s docstring: *"This INSERT is the concurrency decision, not a pre-check"*).
DB_CONFLICT_REASON = "POSTGRES_UNIQUE_ALLOCATION_CONFLICT"

_LOCK = threading.Lock()
_NEXT = 0
_BARRIER = ReleaseBarrier()
_ATTEMPTS: list[dict] = []
_ARMED: list[dict] = []
_TARGET: dict[str, str] = {"slot_id": "", "why": ""}

# The reset that has to precede a mutating run, quoted so a failed pre-flight prints the fix rather
# than only the symptom (`loadtests/README.md`, `supabase/demo/README.md`).
RESET_COMMAND = "python supabase/demo/reset_demo_day.py --mode cast --include-shp1017 --confirm"


def _resolve_target() -> tuple[str, str]:
    """Decide, once, which interval the race actually runs on. Called after the barrier releases.

    Verified live on 2026-09-02 against the local stack: on an un-reset cast the evening capacity at
    FAC-JAI-01 is already consumed -- `D16-SLT-RACE` was offered to nobody, and six of the ten
    contention shipments returned `NO_FEASIBLE_SLOT` outright. Racing anyway would produce fifty
    typed refusals, zero winners, and a red run that says "no winner" when the truth is "no fixture".

    So the arming reads decide: if the named interval is on offer to at least one armed user, race
    it. Otherwise refuse to write at all (`named` mode) or fall back to the interval most users rank
    first (`leader` mode, opt-in). Never invents a slot id in either case -- both come out of a real
    `feasible` response.
    """
    with _LOCK:
        if _TARGET["slot_id"] or _TARGET["why"]:
            return _TARGET["slot_id"], _TARGET["why"]
        armed = list(_ARMED)
        visible = [a for a in armed if a.get("target_visible")]
        if visible:
            _TARGET["slot_id"] = TARGET_SLOT_ID
            _TARGET["why"] = f"named interval, on offer to {len(visible)}/{len(armed)} armed users"
        elif TARGET_MODE == "leader":
            counted = Counter(a["first_option"] for a in armed if a.get("first_option"))
            if counted:
                slot, seen = counted.most_common(1)[0]
                _TARGET["slot_id"] = slot
                _TARGET["why"] = (
                    f"leader fallback: {TARGET_SLOT_ID} was offered to nobody; {slot} is the "
                    f"top-ranked option for {seen}/{len(armed)} armed users"
                )
            else:
                _TARGET["why"] = "leader fallback found no options at all"
        else:
            _TARGET["why"] = (
                f"{TARGET_SLOT_ID} was offered to none of the {len(armed)} armed users -- the cast "
                f"has no free capacity on that interval. Reset first: {RESET_COMMAND} "
                "(or set SETUHAUL_RACE_TARGET_MODE=leader to race the cast's own top interval)"
            )
        return _TARGET["slot_id"], _TARGET["why"]


def _assign_cast() -> tuple[str, str]:
    global _NEXT
    with _LOCK:
        email, shipment_id = CONTEND_CAST[_NEXT % len(CONTEND_CAST)]
        _NEXT += 1
        return email, shipment_id


def _record(entry: dict) -> None:
    with _LOCK:
        _ATTEMPTS.append(entry)


@events.test_start.add_listener
def _reset(environment) -> None:
    global _NEXT
    with _LOCK:
        _NEXT = 0
        _ATTEMPTS.clear()
        _ARMED.clear()
        _TARGET.update(slot_id="", why="")
    _BARRIER.reset()
    _BARRIER.arm(ARM_SECONDS)
    # `parsed_options` is None under `locust.debug.run_single_user`, so it is read defensively.
    target_users = getattr(getattr(environment, "parsed_options", None), "num_users", None)
    print(
        f"same_interval_race: target_slot={TARGET_SLOT_ID} users={target_users} "
        f"arm_window={ARM_SECONDS:.0f}s "
        f"mutate={'ON' if mutate_enabled() else 'OFF (read-only wiring check)'}"
    )


@events.test_stop.add_listener
def _assert_race_contract(environment) -> None:
    with _LOCK:
        attempts = list(_ATTEMPTS)
        armed = list(_ARMED)

    visible = sum(1 for a in armed if a.get("target_visible"))
    starved = sum(1 for a in armed if not a.get("option_count"))
    resolved, why = _TARGET["slot_id"], _TARGET["why"]
    print(
        f"same_interval_race: armed={len(armed)} target_in_own_options={visible} "
        f"armed_with_no_options={starved} attempts={len(attempts)}"
    )
    if why:
        print(f"same_interval_race: raced_interval={resolved or '(none)'} -- {why}")

    if not mutate_enabled():
        # Read-only wiring check. There is nothing to assert about a race that was never run, and
        # inventing a pass here would be exactly the "claimed, not executed" failure
        # `TESTING_STRATEGY.md` §8 calls out.
        print("same_interval_race: SKIPPED_WRITE_PHASE (SETUHAUL_LOCUST_MUTATE not set)")
        return

    failures: list[str] = []
    if not attempts:
        environment.process_exit_code = 1
        if not resolved:
            # Named, not generic: "no fixture" and "no winner" are different diagnoses and only one
            # of them is a product defect.
            print(f"same_interval_race: FAIL_fixture_not_raceable -- {why}")
        else:
            print("same_interval_race: NO_ATTEMPTS_RECORDED")
        return

    winners = [a for a in attempts if a["code"] in WINNER_CODES]
    refusals = [a for a in attempts if a["code"] == REFUSAL_CODE]
    others = [a for a in attempts if a["code"] not in WINNER_CODES | {REFUSAL_CODE}]
    server_errors = [a for a in attempts if a["status"] >= 500 or a["status"] == 0]
    reasons = Counter(a.get("reason_code") or "-" for a in refusals)

    print(
        f"same_interval_race: N={len(attempts)} -> {len(winners)} winner "
        f"/ {len(refusals)} {REFUSAL_CODE} / {len(others)} other / {len(server_errors)} 5xx"
    )
    print(f"same_interval_race: refusal reason_codes={dict(reasons)}")

    # §9.2 / §3a assertion 1 -- "Zero 5xx is an assertion, not a hope."
    if server_errors:
        failures.append(
            f"FAIL_5xx {len(server_errors)} request(s) returned >=500 or failed transport: "
            + "; ".join(f"{a['shipment_id']}:{a['status']}:{a['code']}" for a in server_errors[:5])
        )
    # assertion 2 -- exactly one winner.
    if len(winners) != 1:
        failures.append(
            f"FAIL_winner_count expected exactly 1 winner, got {len(winners)}: "
            + "; ".join(f"{a['shipment_id']}:{a['code']}" for a in winners[:5])
        )
    # assertion 3 -- everybody else is refused, and typed.
    if len(refusals) != len(attempts) - len(winners):
        failures.append(
            f"FAIL_refusal_count expected {len(attempts) - len(winners)} {REFUSAL_CODE}, "
            f"got {len(refusals)}"
        )
    if others:
        failures.append(
            "FAIL_unexpected_codes "
            + "; ".join(f"{a['shipment_id']}:{a['status']}:{a['code']}" for a in others[:5])
        )
    # assertion 4 -- §10.1's "with fresh options": a bare 409 fails this. Split by cause, because a
    # loser offered nothing when its shipment *had* nothing at arming time is a fixture that has run
    # out of capacity, not a server that forgot to re-present. Only the latter is a defect.
    armed_by_shipment = {a["shipment_id"]: a for a in armed}
    optionless = [a for a in refusals if not a.get("refreshed_option_count")]
    fixture_starved = [
        a
        for a in optionless
        if (armed_by_shipment.get(a["shipment_id"], {}).get("option_count") or 0) <= 1
    ]
    genuine = [a for a in optionless if a not in fixture_starved]
    if genuine:
        failures.append(
            f"FAIL_refusal_without_options {len(genuine)} refusal(s) offered no fresh options "
            "despite the shipment having alternatives at arming time: "
            + "; ".join(a["shipment_id"] for a in genuine[:5])
        )
    if fixture_starved:
        print(
            f"same_interval_race: WARN_fixture_capacity {len(fixture_starved)} refusal(s) had no "
            "alternative to offer because their shipment had none to begin with -- reset the cast "
            f"to make §10.1's 'with fresh options' assertion meaningful: {RESET_COMMAND}"
        )
    if any(not a.get("reason_code") for a in refusals):
        failures.append("FAIL_refusal_without_reason_code")
    # assertion 5 -- at least one loser lost to PostgreSQL, not to a pre-check. Without this the
    # suite could "pass" while never touching D1's exclusion constraint at all.
    if reasons.get(DB_CONFLICT_REASON, 0) == 0:
        failures.append(
            "FAIL_no_db_level_contention no refusal carried "
            f"{DB_CONFLICT_REASON}; the exclusion constraint never decided this race"
        )
    # assertion 6 -- the winner's shape (§4 "Held != booked").
    for winner in winners:
        if winner["code"] == "SLOT_HELD":
            if winner.get("appointment_id") or winner.get("appointment_writes"):
                failures.append(
                    f"FAIL_held_wrote_appointment {winner['shipment_id']} "
                    f"appointment_id={winner.get('appointment_id')} "
                    f"writes={winner.get('appointment_writes')}"
                )
            if not winner.get("hold_id") or not winner.get("hold_expires_at"):
                failures.append(f"FAIL_held_without_hold_fields {winner['shipment_id']}")
        else:
            print(
                "same_interval_race: NOTE winner is SLOT_REQUESTED -- this deploy has "
                "TWO_PHASE_HOLD_ENABLED off (legacy single-phase path)."
            )
    # assertion 7 -- the original suite's invariant, kept: no interval has two winners.
    per_slot: dict[str, list[str]] = defaultdict(list)
    for winner in winners:
        per_slot[winner["slot_id"]].append(winner["shipment_id"])
    doubled = {slot: ships for slot, ships in per_slot.items() if len(ships) > 1}
    if doubled:
        failures.append(f"FAIL_double_book {doubled}")

    if failures:
        environment.process_exit_code = 1
        for line in failures:
            print(f"same_interval_race: {line}")
    else:
        print("same_interval_race: PASS_one_winner_zero_double_books_zero_5xx")


class ContendUser(HttpUser):
    host = bff_host()
    wait_time = constant(0.05)

    def on_start(self) -> None:
        self.email, self.shipment_id = _assign_cast()
        self.session_id = f"locust-session-{uuid.uuid4()}"
        self.headers = auth_headers(supabase_grant(self.email))
        self.policy_version = None
        self.target_visible = False
        self.done = False

    def _options(self, payload: dict) -> list[dict]:
        data = envelope_data(payload)
        options = data.get("options") or []
        return [item for item in options if isinstance(item, dict) and item.get("slot_id")]

    @task
    def race_the_contested_interval(self) -> None:
        if self.done:
            return
        self.done = True

        # ---- arm: read the real option set, never invent a slot id ----
        with self.client.get(
            f"/api/v1/shipments/{self.shipment_id}/slots/feasible?limit=5",
            headers=self.headers,
            name="G_feasible",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"feasible_{response.status_code}")
                return
            payload = response.json()
            data = envelope_data(payload)
            options = self._options(payload)
            self.policy_version = data.get("policy_version")
            self.target_visible = any(o["slot_id"] == TARGET_SLOT_ID for o in options)
            response.success()

        self.option_count = len(options)
        with _LOCK:
            _ARMED.append(
                {
                    "shipment_id": self.shipment_id,
                    "target_visible": self.target_visible,
                    "option_count": len(options),
                    "first_option": options[0]["slot_id"] if options else "",
                }
            )

        if not mutate_enabled():
            return

        # ---- fire: every user leaves the barrier at the same wall-clock instant ----
        lateness = _BARRIER.wait()
        target_slot, why = _resolve_target()
        if not target_slot:
            # Pre-flight refused the race. Writing fifty requests at an interval nobody can take
            # would burn the fixture and prove nothing; the reason is reported in the summary.
            return
        key = idem_key(f"contend-{self.shipment_id}")
        body = {
            "note": "§9.2 same_interval_race (locust)",
            # Deliberately no `displayed_recommendation_id` -- see this module's docstring, point 3.
            "displayed_policy_version": self.policy_version,
            "client_message_id": key,
        }
        headers = {**self.headers, "Idempotency-Key": key}
        with self.client.post(
            f"/api/v1/shipments/{self.shipment_id}/slots/{target_slot}/request",
            json=body,
            headers=headers,
            name="G_request_slot",
            catch_response=True,
        ) as response:
            try:
                payload = response.json()
            except ValueError:
                _record(
                    {
                        "shipment_id": self.shipment_id,
                        "slot_id": target_slot,
                        "status": response.status_code,
                        "code": "NOT_JSON",
                        "reason_code": None,
                        "refreshed_option_count": 0,
                        "lateness_ms": int(lateness * 1000),
                    }
                )
                response.failure("request_not_json")
                return
            data = envelope_data(payload)
            code = str(data.get("code") or "")
            conflict = data.get("conflict") or {}
            refreshed = data.get("refreshed_options") or {}
            _record(
                {
                    "shipment_id": self.shipment_id,
                    "slot_id": str(data.get("slot_id") or target_slot),
                    "status": response.status_code,
                    "code": code or f"HTTP_{response.status_code}",
                    "reason_code": conflict.get("reason_code"),
                    "refreshed_option_count": len(refreshed.get("options") or []),
                    "appointment_id": data.get("appointment_id"),
                    "appointment_writes": data.get("appointment_writes"),
                    "hold_id": data.get("hold_id"),
                    "hold_expires_at": data.get("hold_expires_at"),
                    "target_visible": self.target_visible,
                    "lateness_ms": int(lateness * 1000),
                }
            )
            # A lost race is a *pass*, so it must not be recorded as a Locust failure -- only a 5xx
            # or an untyped answer is a real failure of the contract.
            if response.status_code >= 500 or not code:
                response.failure(f"request_{response.status_code}_{code or 'untyped'}")
            else:
                response.success()

        # Every user fires exactly once, so there is nothing left to do; end the run rather than
        # idling to `-t`. Scheduled on a separate greenlet so `quit()` does not kill this one
        # mid-statement.
        gevent.spawn_later(1.0, self.environment.runner.quit)
