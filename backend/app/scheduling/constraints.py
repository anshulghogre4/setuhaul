from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files

from pydantic import BaseModel, ConfigDict, Field


class ConstraintStatement(BaseModel):
    id: str
    statement: str


class HardConstraint(ConstraintStatement):
    failure_code: str


class DeliveryBoundary(BaseModel):
    active_sprint: str
    frontend: str
    backend: str
    ai_runtime: str
    data_authority: str
    ephemeral_state: str
    prohibited_patterns: list[str]


class RankingPolicy(BaseModel):
    id: str
    ordered_factors: list[str]
    priority_scores: dict[str, int] = Field(default_factory=dict)
    score_weights: dict[str, int] = Field(default_factory=dict)
    explainability_required: bool
    randomness_allowed: bool


class NoSlotEscalation(BaseModel):
    required: bool
    minimum_payload_fields: list[str]
    forbidden_fallbacks: list[str]


class WriteSafety(BaseModel):
    required_for_business_writes: list[str]
    client_supplied_fields_to_ignore_for_authority: list[str]


class RedisBoundary(BaseModel):
    ttl_hours: int = Field(gt=0)
    allowed_uses: list[str]
    forbidden_uses: list[str]


class SchedulingConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy_version: str
    status: str
    source_documents: list[str]
    delivery_boundary: DeliveryBoundary
    non_negotiable_invariants: list[ConstraintStatement]
    feasibility_hard_constraints: list[HardConstraint]
    ranking_policy: RankingPolicy
    appointment_lifecycle: dict[str, str]
    invalidates_displayed_options_when: list[str]
    no_slot_escalation: NoSlotEscalation
    write_safety: WriteSafety
    redis_boundary: RedisBoundary
    deferred_until_after_sprint3_gate: list[str]

    def invariant_ids(self) -> set[str]:
        return {item.id for item in self.non_negotiable_invariants}

    def hard_constraint_ids(self) -> set[str]:
        return {item.id for item in self.feasibility_hard_constraints}


@lru_cache(maxsize=1)
def load_scheduling_constraints() -> SchedulingConstraints:
    constraints_path = files("app.scheduling").joinpath("constraints.json")
    raw = constraints_path.read_text(encoding="utf-8")
    return SchedulingConstraints.model_validate(json.loads(raw))
