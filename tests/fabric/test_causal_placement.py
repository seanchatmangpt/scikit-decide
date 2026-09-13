from autofde_lab.fabric.causal_placement import (
    ControllerPlacement,
    PlacementStanding,
    select_causal_placement,
)
from autofde_lab.fabric.metrics import CausalLatency


def c(name, diameter, *, authority=True, safety=True, model=False):
    return ControllerPlacement(
        name,
        authority,
        safety,
        CausalLatency(observe_s=diameter / 2, actuate_s=diameter / 2),
        model_required=model,
        evidence_ref=f"receipt:{name}",
    )


def test_local_admitted_controller_beats_central_by_causal_diameter():
    decision = select_causal_placement(
        [c("central-frontier", 2.0, model=True), c("edge-manufactured", 0.02)]
    )
    assert decision.standing is PlacementStanding.SELECTED
    assert decision.selected == ("edge-manufactured",)
    assert decision.causal_diameter_s == 0.02


def test_unauthorized_fast_edge_controller_cannot_win():
    decision = select_causal_placement(
        [c("central", 2), c("edge", 0.01, authority=False)]
    )
    assert decision.selected == ("central",)


def test_unsafe_fast_edge_controller_cannot_win():
    decision = select_causal_placement([c("central", 2), c("edge", 0.01, safety=False)])
    assert decision.selected == ("central",)


def test_equal_causal_diameter_is_a_tie_not_false_winner():
    decision = select_causal_placement([c("a", 1), c("b", 1)])
    assert decision.standing is PlacementStanding.TIED
    assert decision.selected == ("a", "b")


def test_no_authorized_safe_placement_fails_closed():
    decision = select_causal_placement(
        [c("a", 1, authority=False), c("b", 1, safety=False)]
    )
    assert decision.standing is PlacementStanding.REFUSED_NO_ADMISSIBLE_PLACEMENT
    assert decision.selected == ()
