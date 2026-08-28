"""E5.1 / issue #36, owner "Fork A" (2026-08-27): the server-computed option-card
differentiator.

`UI-UX/01-driver-chat/components.md` section 2 and `screens.md` section 4 require exactly one
short comparative label per option card and state it is **never computed by the interface**
(U48 -- the interface renders receipts, it never reasons). Before this change no such string
existed anywhere in `backend/` (`implementation-spec.md` section 1.4's "NO SOURCE" row).

These tests pin the three properties that make the label safe to render:

  1. It comes off the server at all (the contract exists).
  2. It is TRUE, not merely comparatively-least -- "no waiting" on an option the driver waits
     an hour and forty minutes for is the exact mis-promise this product exists to remove.
  3. It is deterministic for a given set, the same requirement `recommendation_id_for` has.
"""

from app.scheduling.feasibility import (
    DIFFERENTIATOR_MOST_BUFFER,
    DIFFERENTIATOR_NO_WAITING,
    DIFFERENTIATOR_SOONEST,
    DIFFERENTIATOR_VOCABULARY,
    NO_WAITING_MAX_MINUTES,
    FeasibleSlotOption,
    assign_differentiators,
)


def _option(
    slot_id: str,
    *,
    start: str,
    wait: int,
    slack: int,
) -> FeasibleSlotOption:
    """A FeasibleSlotOption carrying only the fields assign_differentiators reads.

    Built directly rather than through evaluate_candidate_slot on purpose: the label is a
    property of the SET, and driving five real candidates through the full evaluator to vary
    two numbers would test the ranker, not the labeller.
    """
    return FeasibleSlotOption(
        slot_id=slot_id,
        facility_id="FAC-JAI-01",
        dock_id=f"DOCK-{slot_id}",
        dock_code=slot_id[-2:],
        dock_type="STANDARD",
        slot_start_ts=start,
        slot_end_ts=start,
        feasible_start_ts=start,
        feasible_end_ts=start,
        rank_score=1000,
        ranking_factors={
            "wait_after_eta_minutes": wait,
            "fit_slack_minutes": slack,
        },
        ranking_explanation=[],
        checked_constraints=[],
    )


def test_a_three_option_set_gets_the_three_named_labels_one_each():
    """The shape every driver-facing option set is drawn as in mockup.html."""
    options = [
        _option("SLOT-A", start="2026-08-04T12:15:00+05:30", wait=5, slack=20),
        _option("SLOT-B", start="2026-08-04T13:00:00+05:30", wait=10, slack=15),
        _option("SLOT-C", start="2026-08-04T14:30:00+05:30", wait=90, slack=45),
    ]

    assign_differentiators(options)

    assert options[0].differentiator == DIFFERENTIATOR_SOONEST
    assert options[1].differentiator == DIFFERENTIATOR_NO_WAITING
    assert options[2].differentiator == DIFFERENTIATOR_MOST_BUFFER
    # One label, one option -- components.md section 2's "one differentiator line only".
    assert len({o.differentiator for o in options}) == 3


def test_every_emitted_label_is_inside_the_closed_vocabulary():
    """Free text here would put ranking language back somewhere it can drift from the
    ranker. The vocabulary is closed, so an empty string is the only other legal value."""
    options = [
        _option("SLOT-A", start="2026-08-04T12:15:00+05:30", wait=0, slack=30),
        _option("SLOT-B", start="2026-08-04T13:00:00+05:30", wait=8, slack=60),
        _option("SLOT-C", start="2026-08-04T14:30:00+05:30", wait=90, slack=10),
        _option("SLOT-D", start="2026-08-04T15:45:00+05:30", wait=140, slack=5),
    ]

    assign_differentiators(options)

    for option in options:
        assert option.differentiator == "" or option.differentiator in DIFFERENTIATOR_VOCABULARY


def test_no_waiting_is_withheld_when_the_least_wait_is_still_a_real_wait():
    """The load-bearing case. In mockup.html's own artboard the ETA is 11:20 and the card
    labelled "no waiting" starts at 13:00 -- a hundred minutes of waiting. A purely
    comparative rule would print that label; this one must not."""
    options = [
        _option("SLOT-A", start="2026-08-04T12:15:00+05:30", wait=55, slack=20),
        _option("SLOT-B", start="2026-08-04T13:00:00+05:30", wait=100, slack=15),
    ]

    assign_differentiators(options)

    assert options[0].differentiator == DIFFERENTIATOR_SOONEST
    # SLOT-B has the least wait among what is left, and it is still not "no waiting".
    assert DIFFERENTIATOR_NO_WAITING not in {o.differentiator for o in options}


def test_no_waiting_is_granted_exactly_at_the_threshold_not_only_below_it():
    options = [
        _option("SLOT-A", start="2026-08-04T12:15:00+05:30", wait=200, slack=20),
        _option("SLOT-B", start="2026-08-04T13:00:00+05:30", wait=NO_WAITING_MAX_MINUTES, slack=15),
    ]

    assign_differentiators(options)

    assert options[1].differentiator == DIFFERENTIATOR_NO_WAITING


def test_most_buffer_is_withheld_on_a_tie_because_most_would_be_false():
    options = [
        _option("SLOT-A", start="2026-08-04T12:15:00+05:30", wait=200, slack=99),
        _option("SLOT-B", start="2026-08-04T13:00:00+05:30", wait=210, slack=40),
        _option("SLOT-C", start="2026-08-04T14:30:00+05:30", wait=220, slack=40),
    ]

    assign_differentiators(options)

    assert options[0].differentiator == DIFFERENTIATOR_SOONEST
    assert options[1].differentiator == ""
    assert options[2].differentiator == ""


def test_an_option_with_no_true_label_gets_an_empty_string_not_an_invented_one():
    """A 4th and 5th option have no fourth comparative fact available. Blank is the honest
    answer (U81's blank-vs-zero rule); the renderer omits the line."""
    options = [
        _option("SLOT-A", start="2026-08-04T12:15:00+05:30", wait=2, slack=90),
        _option("SLOT-B", start="2026-08-04T13:00:00+05:30", wait=8, slack=30),
        _option("SLOT-C", start="2026-08-04T14:30:00+05:30", wait=90, slack=20),
        _option("SLOT-D", start="2026-08-04T15:45:00+05:30", wait=140, slack=10),
        _option("SLOT-E", start="2026-08-04T17:00:00+05:30", wait=200, slack=5),
    ]

    assign_differentiators(options)

    assert [o.differentiator for o in options] == [
        DIFFERENTIATOR_SOONEST,
        DIFFERENTIATOR_NO_WAITING,
        DIFFERENTIATOR_MOST_BUFFER,
        "",
        "",
    ]


def test_a_single_option_set_gets_exactly_one_label():
    options = [_option("SLOT-A", start="2026-08-04T12:15:00+05:30", wait=3, slack=25)]

    assign_differentiators(options)

    assert options[0].differentiator == DIFFERENTIATOR_SOONEST


def test_assignment_is_deterministic_across_repeated_calls_on_equivalent_sets():
    """Same determinism guarantee recommendation_id_for depends on. Two options tied on
    every ranked value must always resolve the same way, or the same recommendation would
    render different cards on a refresh."""

    def build() -> list[FeasibleSlotOption]:
        return [
            _option("SLOT-B", start="2026-08-04T12:15:00+05:30", wait=5, slack=20),
            _option("SLOT-A", start="2026-08-04T12:15:00+05:30", wait=5, slack=20),
        ]

    first, second = build(), build()
    assign_differentiators(first)
    assign_differentiators(second)

    assert [o.differentiator for o in first] == [o.differentiator for o in second]
    # Tie on feasible_start_ts breaks on slot_id, so SLOT-A wins "soonest" despite being
    # second in the list.
    by_id = {o.slot_id: o.differentiator for o in first}
    assert by_id["SLOT-A"] == DIFFERENTIATOR_SOONEST


def test_empty_option_set_is_a_no_op():
    """NO_FEASIBLE_SLOT returns zero options; the labeller must not raise on that path."""
    options: list[FeasibleSlotOption] = []
    assign_differentiators(options)
    assert options == []


def test_differentiator_defaults_to_blank_so_the_allocation_revalidation_path_is_unchanged():
    """allocation.py builds a FeasibleSlotOption through evaluate_candidate_slot for a single
    slot, where no comparative label is meaningful. That path must keep working untouched."""
    option = _option("SLOT-A", start="2026-08-04T12:15:00+05:30", wait=0, slack=10)
    assert option.differentiator == ""
