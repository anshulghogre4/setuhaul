"""Suite B — runbook Phase G / PDF §11.2 scarce evening (REST, no LLM).

10 Drivers (`driver.drv004@…`–`drv013@`) request feasible evening slots for
`SHP-D16-CONTEND-01..10`. Slot IDs come from GET feasible — never invented.
Pass: at most one SLOT_REQUESTED winner per slot_id.

  locust -f loadtests/locust_slot_contention.py --headless -u 10 -r 10 -t 90s
"""

from __future__ import annotations

import threading
import uuid
from collections import defaultdict

from locust import HttpUser, constant, events, task

from common import CONTEND_CAST, auth_headers, bff_host, supabase_grant

_ASSIGN_LOCK = threading.Lock()
_NEXT = 0
_RESULTS: list[tuple[str, str, str]] = []


def _assign_cast() -> tuple[str, str]:
    global _NEXT
    with _ASSIGN_LOCK:
        email, shipment_id = CONTEND_CAST[_NEXT % len(CONTEND_CAST)]
        _NEXT += 1
        return email, shipment_id


def _record(slot_id: str, code: str, shipment_id: str) -> None:
    with _ASSIGN_LOCK:
        _RESULTS.append((slot_id, code, shipment_id))


@events.test_start.add_listener
def _reset(_environment) -> None:
    global _NEXT
    with _ASSIGN_LOCK:
        _NEXT = 0
        _RESULTS.clear()


@events.test_stop.add_listener
def _assert_no_double_books(environment) -> None:
    winners: dict[str, list[str]] = defaultdict(list)
    with _ASSIGN_LOCK:
        snapshot = list(_RESULTS)
    for slot_id, code, shipment_id in snapshot:
        if code == "SLOT_REQUESTED" and slot_id:
            winners[slot_id].append(shipment_id)
    doubled = {slot: ships for slot, ships in winners.items() if len(ships) > 1}
    print(
        "contend_requests",
        len(snapshot),
        "winner_slots",
        len(winners),
        "conflicts",
        sum(1 for _, code, _ in snapshot if code != "SLOT_REQUESTED"),
    )
    if doubled:
        environment.process_exit_code = 1
        print("FAIL_double_book", {k: v for k, v in doubled.items()})
    else:
        print("PASS_zero_double_books")


class ContendUser(HttpUser):
    host = bff_host()
    wait_time = constant(0.05)

    def on_start(self) -> None:
        self.email, self.shipment_id = _assign_cast()
        self.session_id = f"locust-session-{uuid.uuid4()}"
        self.headers = auth_headers(supabase_grant(self.email))
        self.slot_id = ""
        self.recommendation_id = None
        self.policy_version = None
        self.done = False

    def _options(self, payload: dict) -> list[dict]:
        data = payload.get("data") or {}
        options = data.get("options") or []
        return [item for item in options if isinstance(item, dict) and item.get("slot_id")]

    @task
    def request_evening_slot(self) -> None:
        if self.done:
            return
        with self.client.get(
            f"/api/v1/shipments/{self.shipment_id}/slots/feasible?limit=5",
            headers=self.headers,
            name="G_feasible",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"feasible_{response.status_code}")
                self.done = True
                return
            payload = response.json()
            data = payload.get("data") or {}
            options = self._options(payload)
            if not options:
                response.success()
                _record("", "NO_FEASIBLE", self.shipment_id)
                self.done = True
                return
            # REC- / policy live on the result, not each option. Never invent a slot_id.
            chosen = options[0]
            self.slot_id = str(chosen["slot_id"])
            self.recommendation_id = data.get("recommendation_id")
            self.policy_version = data.get("policy_version")
            response.success()

        key = f"locust-contend-{self.shipment_id}-{uuid.uuid4()}"
        body = {
            "note": "runbook Phase G locust",
            "displayed_policy_version": self.policy_version,
            "displayed_recommendation_id": self.recommendation_id,
            "client_message_id": key,
        }
        headers = {**self.headers, "Idempotency-Key": key}
        with self.client.post(
            f"/api/v1/shipments/{self.shipment_id}/slots/{self.slot_id}/request",
            json=body,
            headers=headers,
            name="G_request_slot",
            catch_response=True,
        ) as response:
            try:
                payload = response.json()
            except ValueError:
                response.failure("request_not_json")
                self.done = True
                return
            data = payload.get("data") or {}
            code = str(data.get("code") or "")
            if response.status_code == 200 and code == "SLOT_REQUESTED":
                _record(self.slot_id, code, self.shipment_id)
                response.success()
            elif response.status_code == 409 or code in {
                "SLOT_CONFLICT_REFRESH_REQUIRED",
                "SLOT_OPTIONS_STALE",
            }:
                _record(self.slot_id, code or "CONFLICT", self.shipment_id)
                response.success()
            else:
                response.failure(f"request_{response.status_code}_{code}")
        self.done = True
