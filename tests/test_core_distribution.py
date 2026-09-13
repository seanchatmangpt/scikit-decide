from autofde_lab.core import DiscreteDistribution, SingleValueDistribution


def test_discrete_distribution_deduplicates_members_with_combined_weight():
    dist = DiscreteDistribution(
        [("rock", 0.5), ("paper", 0.3), ("rock", 0.2), ("scissors", 0.1), ("paper", 0.1)]
    )
    values = dist.get_values()

    # Only unique population members remain.
    elements = [element for element, _ in values]
    assert elements == ["rock", "paper", "scissors"]
    assert len(elements) == len(set(elements))

    # Weights of duplicate entries are summed, not dropped.
    weights = dict(values)
    assert weights["rock"] == 0.7
    assert weights["paper"] == 0.4
    assert weights["scissors"] == 0.1


def test_discrete_distribution_no_duplicates_unaffected():
    dist = DiscreteDistribution([("a", 0.6), ("b", 0.4)])
    assert dist.get_values() == [("a", 0.6), ("b", 0.4)]


def test_discrete_distribution_sample_still_works_after_dedup():
    dist = DiscreteDistribution([("only", 1.0), ("only", 1.0)])
    assert dist.get_values() == [("only", 2.0)]
    assert dist.sample() == "only"


def test_single_value_distribution_get_values():
    dist = SingleValueDistribution(42)
    assert dist.get_values() == [(42, 1.0)]
    assert dist.sample() == 42
