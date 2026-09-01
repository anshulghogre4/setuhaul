"""Drift guards for `app/scheduling/occupancy.py` -- issue #97's shared liveness predicate.

These need no database. They exist because the defect #97 fixed was not a logic error anyone could
see in one file: it was two files quietly disagreeing about what "this dock interval is taken"
means, with nothing anywhere that would notice. Every assertion below pins one of those meanings to
the migration that actually enforces it.

Design citation: `SOLUTION_DESIGN.md` §0.8 (D2 lazy expiry), §5 Stage 3, D1, D2, M6, FR-SYS-006.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.scheduling import holds, occupancy, snapshot

REPO_ROOT = Path(__file__).resolve().parents[3]
MIGRATIONS = REPO_ROOT / "supabase" / "migrations"
D1_MIGRATION = MIGRATIONS / "20260823060000_d1_correctness_bedrock.sql"
D2_MIGRATION = MIGRATIONS / "20260829134929_d2_held_state_dock_occupancy.sql"
APP_SCHEDULING = REPO_ROOT / "backend" / "app" / "scheduling"


def _fingerprint(sql: str) -> str:
    """Whitespace- and alias-insensitive form, so the same expression written across several lines
    with a different table alias still compares equal. Same normalisation
    `test_scheduling_allocation.py` uses; `r.` is the D1 migration's PL/pgSQL record alias."""
    return re.sub(r"\b(?:o|r|s|sl)\.", "", re.sub(r"\s+", "", sql))


# =================================================================================================
# One tuple, not three
# =================================================================================================


def test_the_capacity_state_tuple_has_exactly_one_definition():
    """`holds` and `snapshot` must *be* `occupancy`'s tuple, not merely equal to it.

    Equality would pass against three separately maintained literals, which is the arrangement this
    module was created to end -- and identity is what proves the copies are gone rather than
    currently in agreement.
    """
    assert holds.CAPACITY_CONSUMING_STATES is occupancy.CAPACITY_CONSUMING_STATES
    assert snapshot.CAPACITY_CONSUMING_STATES is occupancy.CAPACITY_CONSUMING_STATES


def test_the_split_between_timed_and_untimed_states_covers_the_whole_set():
    """The liveness predicate is built by splitting the excluded set in two. If a state ever went
    missing from both halves it would silently stop blocking capacity."""
    assert set(occupancy.UNTIMED_CAPACITY_STATES) | set(occupancy.TIMED_CAPACITY_STATES) == set(
        occupancy.CAPACITY_CONSUMING_STATES
    )
    assert not set(occupancy.UNTIMED_CAPACITY_STATES) & set(occupancy.TIMED_CAPACITY_STATES)
    # Only HELD may carry an `expires_at` -- `dock_occupancy_held_shape_check` -- so it is the only
    # state the clock can apply to.
    assert occupancy.TIMED_CAPACITY_STATES == ("HELD",)


def test_the_held_shape_check_still_makes_held_the_only_timed_state():
    """Read off the migration rather than assumed. If a future migration let a second state carry
    `expires_at`, the split above would be wrong and the predicate would ignore that state's TTL."""
    sql = D2_MIGRATION.read_text(encoding="utf-8")
    check = re.search(
        r"ADD CONSTRAINT dock_occupancy_held_shape_check\s*CHECK \((.*?)\);", sql, re.DOTALL
    )
    assert check, "the held-shape CHECK is no longer where this test looks"
    body = re.sub(r"\s+", " ", check.group(1))
    assert "state = 'HELD' AND expires_at IS NOT NULL AND appointment_id IS NULL" in body
    assert "state <> 'HELD' AND expires_at IS NULL" in body


# =================================================================================================
# The predicate against the constraint it refines
# =================================================================================================


def test_the_predicate_is_the_exclusion_constraints_set_minus_lapsed_holds():
    """The whole of issue #97 in one assertion.

    The generated fragment must (a) reproduce the constraint's own state list verbatim, so the
    partial GiST index stays matchable, and (b) add the time term the constraint structurally
    cannot carry.
    """
    sql = D2_MIGRATION.read_text(encoding="utf-8")
    predicate = re.search(
        r"ADD CONSTRAINT dock_occupancy_dock_id_window_excl.*?WHERE \(state IN \(([^)]*)\)\)",
        sql,
        re.DOTALL,
    )
    assert predicate, "the exclusion constraint's predicate is no longer where this test looks"
    constraint_states = [s.strip().strip("'") for s in predicate.group(1).split(",")]

    fragment = occupancy.live_blocking_occupancy_sql(alias="o", now_param="now")
    # (a) the constraint's set, in the constraint's own order, spelled the constraint's own way.
    quoted = ", ".join(f"'{state}'" for state in constraint_states)
    assert f"o.state IN ({quoted})" in fragment

    # (b) the refinement the constraint cannot express.
    assert "o.state = 'HELD' AND o.expires_at > :now" in fragment
    assert "o.state IN ('PENDING_CONFIRMATION', 'CONFIRMED', 'IN_PROGRESS')" in fragment


def test_the_predicate_binds_the_instant_and_never_calls_sql_now():
    """§9.1: the clock is injected, never read from the database. A `now()` in here would make
    every hold-liveness assertion in the suite a race against its own runtime."""
    fragment = occupancy.live_blocking_occupancy_sql()
    assert ":now" in fragment
    assert "now()" not in fragment


def test_the_alias_and_parameter_name_are_both_honoured():
    """Both are interpolated, so a caller that renames one and not the other would produce SQL
    referring to a table alias that does not exist -- caught here rather than at runtime."""
    fragment = occupancy.live_blocking_occupancy_sql(alias="dz", now_param="as_of")
    assert "dz.state" in fragment
    assert ":as_of" in fragment
    assert "o.state" not in fragment
    assert ":now" not in fragment


# =================================================================================================
# The claim-window expression: four places, one meaning
# =================================================================================================


def _interval_expression(source: str) -> set[str]:
    return {
        _fingerprint(match.group(0))
        for match in re.finditer(r"tstzrange\(.*?'\[\)'\s*\)", source, re.DOTALL)
    }


def test_the_claim_window_matches_the_e11_backfill_and_both_inline_writers():
    """D1's definition of "occupied" is one expression, and four places compute it.

    The E1.1 backfill wrote 613 rows with it; `_claim_dock_occupancy` and `create_hold` write new
    ones with it; issue #97's read anti-join and lazy expiry now *ask about* it. If any of them
    drifted, rows written by one would mean a different interval to another -- and, as
    `_claim_dock_occupancy`'s own docstring says, nothing else in the system would notice.
    """
    canonical = _fingerprint(
        occupancy.claim_window_sql(
            start_expr="sl.slot_start_ts", unload_min_expr="s.expected_unload_min"
        )
    )

    backfill = next(
        line
        for line in D1_MIGRATION.read_text(encoding="utf-8").splitlines()
        if "computed_window :=" in line
    )
    assert canonical in _fingerprint(backfill)

    for module in ("allocation.py", "holds.py"):
        source = (APP_SCHEDULING / module).read_text(encoding="utf-8")
        assert canonical in {_fingerprint(expr) for expr in _interval_expression(source)}, (
            f"{module} computes the claim window differently from occupancy.claim_window_sql"
        )


def test_the_claim_window_carries_the_flat_changeover_buffer():
    """The +15 is D1's changeover buffer, not a rounding artefact. It is stated as a named
    constant so that making it per-facility later is a change to one value, not a grep."""
    assert occupancy.CHANGEOVER_BUFFER_MINUTES == 15
    expression = occupancy.claim_window_sql(start_expr="x", unload_min_expr="y")
    assert "(y + 15)" in expression
    assert "'[)'" in expression, "the range must stay half-open or adjacent slots would collide"


# =================================================================================================
# Both consumers actually consume it
# =================================================================================================


def test_feasibility_and_the_write_path_both_reference_the_shared_module():
    """The anti-regression guard for the *shape* of the fix, not just its behaviour.

    #97's brief was explicitly "define one predicate and have both sides consume it", because the
    tempting alternative -- patching whichever side's symptom was visible -- is what produced the
    divergence in the first place. A future edit that re-inlines either side fails here.
    """
    feasibility = (APP_SCHEDULING / "feasibility.py").read_text(encoding="utf-8")
    assert "live_blocking_occupancy_sql" in feasibility
    assert "from app.scheduling.occupancy import" in feasibility

    holds_source = (APP_SCHEDULING / "holds.py").read_text(encoding="utf-8")
    assert "expire_lapsed_holds_on_interval" in holds_source
    assert "from app.scheduling.occupancy import" in holds_source

    allocation = (APP_SCHEDULING / "allocation.py").read_text(encoding="utf-8")
    assert "expire_lapsed_holds_on_interval" in allocation


def test_the_lazy_expiry_flips_exactly_what_the_sweeper_flips():
    """The lazy path must not invent a different EXPIRED shape from the scheduled one.

    Both must set `state='EXPIRED'` *and* NULL the deadline -- `dock_occupancy_held_shape_check`
    forbids a non-HELD row carrying `expires_at`, so a flip that left it behind would abort the
    claiming transaction rather than merely look untidy.
    """
    source = (APP_SCHEDULING / "holds.py").read_text(encoding="utf-8")
    flips = re.findall(r"SET state = 'EXPIRED'[^\n]*", source)
    assert len(flips) >= 2, "expected the sweeper's flip and the lazy flip"
    for flip in flips:
        assert "expires_at = NULL" in flip, flip

    # And both must guard on `state = 'HELD'`, which is what makes the sweeper idempotent over rows
    # the lazy path already expired (and vice versa).
    assert source.count("AND o.state = 'HELD'") + source.count("WHERE state = 'HELD'") >= 2
