from app.scheduling.constraints import load_scheduling_constraints


def test_constraints_registry_loads_from_single_editable_file():
    constraints = load_scheduling_constraints()

    assert constraints.policy_version == "sprint3_constraints_v1"
    assert constraints.delivery_boundary.ai_runtime == "LangChain bind_tools plus bounded manual invoke loop"
    assert constraints.delivery_boundary.data_authority == "PostgreSQL via Supabase"


def test_constraints_preserve_core_authority_boundaries():
    constraints = load_scheduling_constraints()

    assert "postgres_is_authority" in constraints.invariant_ids()
    assert "llm_orchestrates_only" in constraints.invariant_ids()
    assert "no_invented_operations_data" in constraints.invariant_ids()
    assert "Redis as business source of truth" in constraints.delivery_boundary.prohibited_patterns
    assert "slot lock source of truth" in constraints.redis_boundary.forbidden_uses


def test_sprint3_feasibility_rules_are_explicit_and_explainable():
    constraints = load_scheduling_constraints()

    assert "slot_capacity_available" in constraints.hard_constraint_ids()
    assert "latest_eta_only" in constraints.hard_constraint_ids()
    assert constraints.ranking_policy.priority_scores["CRITICAL"] > constraints.ranking_policy.priority_scores["LOW"]
    assert constraints.ranking_policy.score_weights["wait_after_eta_per_minute"] < 0
    assert constraints.ranking_policy.explainability_required is True
    assert constraints.ranking_policy.randomness_allowed is False
    assert constraints.no_slot_escalation.required is True


def test_business_write_safety_requires_transactional_revalidation():
    constraints = load_scheduling_constraints()

    requirements = set(constraints.write_safety.required_for_business_writes)
    assert "verified ExecutionContext" in requirements
    assert "single database transaction" in requirements
    assert "post-commit authoritative reread" in requirements
    assert "audit record" in requirements


def test_deferred_scope_keeps_non_gate_features_out():
    constraints = load_scheduling_constraints()

    deferred = set(constraints.deferred_until_after_sprint3_gate)
    assert "maps and GPS telemetry" in deferred
    assert "user and role administration UI" in deferred
    assert "predictive ETA" in deferred
