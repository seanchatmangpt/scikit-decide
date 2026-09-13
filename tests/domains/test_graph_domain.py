# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-school tests for autofde_lab.hub.domain.graph_domain.

GraphDomain / GraphDomainUncertain wrap an already-computed dict-based
transition table. They are typically built by GraphExploration subclasses
(FullSpaceExploration, DFSExploration) from another real domain, then queried
directly by search solvers (e.g. Astar) through get_applicable_actions(),
get_next_state(), get_transition_value(), is_terminal(), is_goal() - never
through reset()/step(), because neither class overrides the underlying
_is_terminal()/_get_initial_state_() override points that the generic
Domain.reset()/step() dynamics rely on. These tests exercise the real,
working public API against a real small deterministic domain and real
in-memory graph structures - no mocking of the domain under test.
"""

from __future__ import annotations

import pytest

from autofde_lab import D, DeterministicPlanningDomain, ImplicitSpace, Space, Value
from autofde_lab.hub.domain.graph_domain.GraphDomain import (
    ActionSpace,
    GraphDomain,
    GraphDomainUncertain,
)
from autofde_lab.hub.domain.graph_domain.graph_domain_builders.DFSExploration import (
    DFSExploration,
)
from autofde_lab.hub.domain.graph_domain.graph_domain_builders.FullSpaceExploration import (
    FullSpaceExploration,
)


class ChainDomain(DeterministicPlanningDomain):
    """Tiny real deterministic planning domain: a 4-node line graph.

    0 --right--> 1 --right--> 2 --right--> 3 (goal)
    1 --left--> 0
    2 --left--> 1

    Used as source domain to exercise the graph_domain_builders exploration
    classes end to end (real domain -> real GraphDomain).
    """

    def __init__(self):
        self.transitions = {
            0: {"right": 1},
            1: {"right": 2, "left": 0},
            2: {"right": 3, "left": 1},
            3: {},
        }

    def _get_next_state(self, memory, event):
        return self.transitions[memory][event]

    def _get_transition_value(self, memory, event, next_state=None):
        return Value(cost=1.0)

    def _is_terminal(self, state):
        return state == 3

    def _get_action_space_(self) -> Space[D.T_event]:
        return ImplicitSpace(lambda x: True)

    def _get_applicable_actions_from(self, memory):
        return ActionSpace(list(self.transitions[memory].keys()))

    def _get_goals_(self):
        return ImplicitSpace(lambda x: x == 3)

    def _get_initial_state_(self):
        return 0

    def _get_observation_space_(self):
        return ImplicitSpace(lambda x: True)


def make_graph_domain() -> GraphDomain:
    next_state_map = {
        "A": {"go": "B"},
        "B": {"go": "C", "back": "A"},
        "C": {},
    }
    next_state_attributes = {
        "A": {"go": {"weight": 1.0}},
        "B": {"go": {"weight": 2.0}, "back": {"weight": 0.5}},
        "C": {},
    }
    return GraphDomain(
        next_state_map,
        next_state_attributes,
        targets={"C"},
        attribute_weight="weight",
    )


def make_graph_domain_uncertain() -> GraphDomainUncertain:
    next_state_map = {
        "A": {"go": {"B": (1.0, 1.0)}},
        "B": {"go": {"C": (0.5, 1.0), "A": (0.5, 1.0)}},
        "C": {},
    }
    state_terminal = {"A": False, "B": False, "C": True}
    state_goal = {"A": False, "B": False, "C": True}
    return GraphDomainUncertain(next_state_map, state_terminal, state_goal)


class TestGraphDomain:
    def test_applicable_actions(self):
        domain = make_graph_domain()
        assert set(domain.get_applicable_actions("A").get_elements()) == {"go"}
        assert set(domain.get_applicable_actions("B").get_elements()) == {
            "go",
            "back",
        }
        assert domain.get_applicable_actions("C").get_elements() == []

    def test_get_next_state(self):
        domain = make_graph_domain()
        assert domain.get_next_state("A", "go") == "B"
        assert domain.get_next_state("B", "back") == "A"
        assert domain.get_next_state("B", "go") == "C"

    def test_get_transition_value(self):
        domain = make_graph_domain()
        assert domain.get_transition_value("A", "go", "B").cost == 1.0
        assert domain.get_transition_value("B", "go", "C").cost == 2.0
        assert domain.get_transition_value("B", "back", "A").cost == 0.5

    def test_is_goal_and_terminal(self):
        domain = make_graph_domain()
        assert domain.is_goal("C") is True
        assert domain.is_goal("A") is False
        assert domain.is_goal("B") is False
        assert domain.is_terminal("C") is True
        assert domain.is_terminal("A") is False

    def test_set_nodes_target_updates_targets(self):
        domain = make_graph_domain()
        assert domain.is_goal("C") is True
        domain.set_nodes_target({"A"})
        assert domain.is_goal("A") is True
        assert domain.is_goal("C") is False

    def test_set_sources_targets(self):
        domain = make_graph_domain()
        domain.set_sources_targets(sources={"A"}, targets={"B"})
        assert domain.sources == {"A"}
        assert domain.targets == {"B"}
        assert domain.is_goal("B") is True
        assert domain.is_goal("C") is False

    def test_merge_combines_two_graph_domains(self):
        domain1 = make_graph_domain()
        next_state_map2 = {"C": {"go": "D"}, "D": {}}
        next_state_attributes2 = {"C": {"go": {"weight": 3.0}}, "D": {}}
        domain2 = GraphDomain(
            next_state_map2,
            next_state_attributes2,
            targets={"D"},
            attribute_weight="weight",
        )
        merged = domain1.merge(domain2)

        assert isinstance(merged, GraphDomain)
        # transitions from domain1 preserved
        assert merged.get_next_state("A", "go") == "B"
        assert merged.get_next_state("B", "go") == "C"
        # new transition contributed by domain2 is present
        assert merged.get_next_state("C", "go") == "D"
        assert merged.get_transition_value("C", "go", "D").cost == 3.0
        # targets attribute is inherited from self (domain1), not merged from domain2
        assert merged.targets == {"C"}

    def test_merge_does_not_overwrite_existing_action(self):
        domain1 = make_graph_domain()
        # domain2 redefines A -go-> B with a different weight; merge must keep domain1's
        next_state_map2 = {"A": {"go": "B"}, "B": {}}
        next_state_attributes2 = {"A": {"go": {"weight": 99.0}}, "B": {}}
        domain2 = GraphDomain(
            next_state_map2, next_state_attributes2, attribute_weight="weight"
        )
        merged = domain1.merge(domain2)
        assert merged.get_transition_value("A", "go", "B").cost == 1.0

    def test_reset_is_unsupported(self):
        """GraphDomain does not implement the _get_initial_state_ override
        point, so the generic reset()/step() dynamics are not usable -
        the domain must be queried directly instead."""
        domain = make_graph_domain()
        with pytest.raises(NotImplementedError):
            domain.reset()


class TestGraphDomainUncertain:
    def test_applicable_actions(self):
        domain = make_graph_domain_uncertain()
        assert domain.get_applicable_actions("A").get_elements() == ["go"]
        assert domain.get_applicable_actions("C").get_elements() == []

    def test_next_state_distribution_returns_a_reachable_successor(self):
        domain = make_graph_domain_uncertain()
        next_state, proba = domain.get_next_state_distribution("A", "go")
        assert next_state == "B"
        assert proba == 1.0

        next_state, proba = domain.get_next_state_distribution("B", "go")
        assert next_state in {"A", "C"}
        assert proba == 0.5

    def test_get_transition_value(self):
        domain = make_graph_domain_uncertain()
        assert domain.get_transition_value("A", "go", "B").cost == 1.0

    def test_is_terminal_and_is_goal(self):
        domain = make_graph_domain_uncertain()
        assert domain.is_goal("C") is True
        assert domain._is_terminal("C") is True
        assert domain._is_terminal("A") is False

    def test_is_terminal_when_no_applicable_actions(self):
        domain = GraphDomainUncertain(
            next_state_map={"X": {}},
            state_terminal={"X": False},
            state_goal={"X": False},
        )
        # not flagged terminal, but has no outgoing transitions -> terminal anyway
        assert domain._is_terminal("X") is True

    def test_to_networkx_builds_real_graph_with_matching_edges(self):
        domain = make_graph_domain_uncertain()
        graph = domain.to_networkx()

        assert graph.number_of_nodes() == 3
        assert graph.number_of_edges() == 3

        state_by_id = {i: data["state"] for i, data in graph.nodes(data=True)}
        id_by_state = {v: k for k, v in state_by_id.items()}

        edge_data = graph.get_edge_data(id_by_state["A"], id_by_state["B"])
        assert edge_data["action"] == "go"
        assert edge_data["proba"] == 1.0
        assert edge_data["cost"] == 1.0


class TestFullSpaceExploration:
    def test_build_graph_domain_from_real_domain(self):
        source_domain = ChainDomain()
        explorer = FullSpaceExploration(source_domain)
        graph_domain = explorer.build_graph_domain()

        assert isinstance(graph_domain, GraphDomain)
        # all 4 states of the chain are represented
        assert set(graph_domain.next_state_map.keys()) == {0, 1, 2, 3}
        # transitions match the source domain exactly
        assert graph_domain.get_next_state(0, "right") == 1
        assert graph_domain.get_next_state(1, "right") == 2
        assert graph_domain.get_next_state(1, "left") == 0
        assert graph_domain.get_next_state(2, "right") == 3
        # goal state detected from source domain's is_goal()
        assert graph_domain.targets == {3}
        assert graph_domain.is_goal(3) is True
        assert graph_domain.is_goal(0) is False
        # transition cost carried over from source domain
        assert graph_domain.get_transition_value(0, "right", 1).cost == 1.0

    def test_build_graph_domain_respects_max_nodes(self):
        source_domain = ChainDomain()
        explorer = FullSpaceExploration(source_domain, max_nodes=1)
        graph_domain = explorer.build_graph_domain()
        # exploration must stop once a goal path is found and max_nodes exceeded
        assert graph_domain.targets == {3}


class TestDFSExploration:
    def test_build_graph_domain_from_real_domain(self):
        source_domain = ChainDomain()
        explorer = DFSExploration(source_domain)
        graph_domain = explorer.build_graph_domain(verbose=False)

        assert isinstance(graph_domain, GraphDomain)
        assert graph_domain.get_next_state(0, "right") == 1
        assert graph_domain.get_next_state(2, "right") == 3
        assert graph_domain.targets == {3}
        assert graph_domain.is_goal(3) is True

    def test_build_graph_domain_with_custom_transition_extractor(self):
        source_domain = ChainDomain()
        explorer = DFSExploration(source_domain)
        graph_domain = explorer.build_graph_domain(
            transition_extractor=lambda s, a, s_prime: {"weight": 42.0},
            verbose=False,
        )
        assert (
            graph_domain.next_state_attributes[0]["right"]["weight"] == 42.0
        )
