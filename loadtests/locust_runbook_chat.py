"""Suite A — runbook Driver chat (docs/DEMO_MANUAL_RUNBOOK.md Phases A–D, E reads).

Hits hosted BFF `/api/v1/chat/message` (JWT → AgentCore when ARN is set).
Default tasks are read/clarify only so a 5-user run cannot wreck the cast.
Set SETUHAUL_LOCUST_MUTATE=1 only for a 1-user walk of C5 / E5.

  locust -f loadtests/locust_runbook_chat.py --headless -u 5 -r 1 -t 3m
"""

from __future__ import annotations

import uuid

from locust import HttpUser, SequentialTaskSet, between, task

from common import RUNBOOK_PROMPTS, auth_headers, bff_host, mutate_enabled, supabase_grant


def _chat(user: HttpUser, message: str, name: str) -> None:
    payload = {
        "message": message,
        "session_id": user.session_id,
        "thread_id": "default",
        "client_message_id": f"locust-{uuid.uuid4()}",
    }
    with user.client.post(
        "/api/v1/chat/message",
        json=payload,
        headers=user.headers,
        name=name,
        timeout=180,
        catch_response=True,
    ) as response:
        if response.status_code != 200:
            response.failure(f"{name} http_{response.status_code}")
            return
        try:
            body = response.json()
        except ValueError:
            response.failure(f"{name} not_json")
            return
        if not body.get("success"):
            response.failure(f"{name} success_false")
            return
        response.success()


class RaviHappyPathReads(SequentialTaskSet):
    """Phase A2 + B1/B2/B5 — Ravi hero shipment, no writes."""

    @task
    def a2_shipments(self) -> None:
        _chat(self.user, RUNBOOK_PROMPTS["A2"], "A2_show_shipments")

    @task
    def b1_lock(self) -> None:
        _chat(self.user, RUNBOOK_PROMPTS["B1"], "B1_lock_ravi")

    @task
    def b2_feasible(self) -> None:
        _chat(self.user, RUNBOOK_PROMPTS["B2"], "B2_feasible_after_6pm")

    @task
    def b5_status(self) -> None:
        _chat(self.user, RUNBOOK_PROMPTS["B5"], "B5_pending_vs_confirmed")

    @task
    def e5_cancel(self) -> None:
        if mutate_enabled():
            _chat(self.user, RUNBOOK_PROMPTS["E5"], "E5_cancel_pending")


class RaviClarify(SequentialTaskSet):
    """Phase A3–A5 — repair≠ETA; A5 is preview only (no write)."""

    @task
    def a3_late(self) -> None:
        _chat(self.user, RUNBOOK_PROMPTS["A3"], "A3_late")

    @task
    def a4_repair(self) -> None:
        _chat(self.user, RUNBOOK_PROMPTS["A4"], "A4_repair_not_eta")

    @task
    def a5_eta_preview(self) -> None:
        _chat(self.user, RUNBOOK_PROMPTS["A5"], "A5_eta_preview")


class VikasNoslot(SequentialTaskSet):
    """Phase D — NOSLOT + multi-shipment disambiguation."""

    @task
    def d1_two_shipments(self) -> None:
        _chat(self.user, RUNBOOK_PROMPTS["D1"], "D1_active_shipments")

    @task
    def d2_noslot(self) -> None:
        _chat(self.user, RUNBOOK_PROMPTS["D2"], "D2_noslot")

    @task
    def d4_multi(self) -> None:
        _chat(self.user, RUNBOOK_PROMPTS["D4"], "D4_multi_b")


class RaviRaceReads(SequentialTaskSet):
    @task
    def c1(self) -> None:
        _chat(self.user, RUNBOOK_PROMPTS["C1"], "C1_lock_race_a")

    @task
    def c3(self) -> None:
        _chat(self.user, RUNBOOK_PROMPTS["C3"], "C3_feasible_race_a")

    @task
    def c5(self) -> None:
        if mutate_enabled():
            _chat(self.user, RUNBOOK_PROMPTS["C5A"], "C5_request_race_a")


class AmitRaceReads(SequentialTaskSet):
    @task
    def c2(self) -> None:
        _chat(self.user, RUNBOOK_PROMPTS["C2"], "C2_lock_race_b")

    @task
    def c4(self) -> None:
        _chat(self.user, RUNBOOK_PROMPTS["C4"], "C4_feasible_race_b")

    @task
    def c5(self) -> None:
        if mutate_enabled():
            _chat(self.user, RUNBOOK_PROMPTS["C5B"], "C5_request_race_b")


class _DriverUser(HttpUser):
    abstract = True
    host = bff_host()
    wait_time = between(2, 5)
    email = ""

    def on_start(self) -> None:
        self.session_id = f"locust-session-{uuid.uuid4()}"
        token = supabase_grant(self.email)
        self.headers = auth_headers(token)
        with self.client.get(
            "/api/v1/auth/me",
            headers=self.headers,
            name="auth_me",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"auth_me_{response.status_code}")
            else:
                response.success()


class RaviUser(_DriverUser):
    weight = 4
    email = "ravi.kumar@setuhaul.com"
    tasks = [RaviHappyPathReads, RaviClarify]


class VikasUser(_DriverUser):
    weight = 2
    email = "vikas.sharma@setuhaul.com"
    tasks = [VikasNoslot]


class RaviRaceUser(_DriverUser):
    weight = 1
    email = "ravi.kumar@setuhaul.com"
    tasks = [RaviRaceReads]


class AmitRaceUser(_DriverUser):
    weight = 1
    email = "amit.singh@setuhaul.com"
    tasks = [AmitRaceReads]
