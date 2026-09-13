from __future__ import annotations

import importlib
import sys
import types
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
SRC = ROOT / "src"

# Load only the interchange package for this crown. AutoFDE's root package eagerly
# imports the full planner/solver surface; the interchange package deliberately has
# a stdlib-only boundary and must remain independently importable.
autofde = types.ModuleType("autofde_lab")
autofde.__path__ = [str(SRC / "autofde_lab")]
sys.modules["autofde_lab"] = autofde
m = importlib.import_module("autofde_lab.interchange")


class Space:
    def __init__(self, values):
        self.values = list(values)

    def get_elements(self):
        return list(self.values)


@dataclass
class Value:
    reward: float = 0.0
    cost: float = 0.0


class DeterministicDomain:
    def get_initial_state(self):
        return 0

    def get_applicable_actions(self, state):
        return Space(["advance"] if state < 2 else [])

    def get_next_state(self, state, action):
        assert action == "advance"
        return state + 1

    def get_transition_value(self, state, action, next_state):
        return Value(cost=1.0)

    def is_terminal(self, state):
        return state >= 2


class Distribution:
    def __init__(self, values):
        self.values = values

    def get_values(self):
        return list(self.values)


class ProbabilisticDomain:
    def get_initial_state(self):
        return "start"

    def get_applicable_actions(self, state):
        return Space(["launch"] if state == "start" else [])

    def get_next_state_distribution(self, state, action):
        assert state == "start" and action == "launch"
        return Distribution([("success", 7.0), ("degraded", 3.0)])

    def get_transition_value(self, state, action, next_state):
        return Value(reward=10.0 if next_state == "success" else 2.0)

    def is_terminal(self, state):
        return state != "start"


class TemporalState:
    def __init__(self, time):
        self._time = float(time)
        self._atoms = (frozenset({("online",)}),)
        self._fluents = (frozenset({((), float(time))}),)
        self._active_da = ()

    @property
    def time(self):
        return self._time

    def __repr__(self):
        return f"TemporalState({self._time:g})"


class TemporalAction:
    NOOP = 0
    INSTANTANEOUS = 1
    DURATIVE_START = 2

    def __init__(self, kind=NOOP):
        self.kind = kind
        self.action_id = -1
        self.arguments = ()

    def __repr__(self):
        return "(noop)"

    __str__ = __repr__


class TemporalDomain:
    def get_initial_state(self):
        return TemporalState(0)

    def get_applicable_actions(self, state):
        return Space([TemporalAction()] if state.time < 2 else [])

    def get_next_state(self, state, action):
        return TemporalState(state.time + 1)

    def get_transition_value(self, state, action, next_state):
        return Value(cost=next_state.time - state.time)

    def is_terminal(self, state):
        return state.time >= 2


@dataclass
class Outcome:
    observation: object
    value: Value
    termination: bool


class RDDLDomain:
    def __init__(self):
        self.state = 0

    def reset(self):
        self.state = 0
        return {"demand": 10, "capacity": 10}

    def step(self, action):
        self.state += 1
        return Outcome(
            observation={"demand": 10 + self.state, "capacity": 10 + action},
            value=Value(reward=float(action)),
            termination=self.state >= 2,
        )


@dataclass(frozen=True)
class OrderEdge:
    src: int
    dst: int


@dataclass(frozen=True)
class ChoiceGraphEdge:
    src: int
    dst: int
    guard: object | None = None


@dataclass(frozen=True)
class Guard:
    predicate_name: str
    predicate_args: dict

    @property
    def key(self):
        return self.predicate_name

    def __hash__(self):
        return hash((self.predicate_name, tuple(sorted(self.predicate_args.items()))))


class Atom:
    def __init__(self, label, consequence="PURE", bindings=None):
        self.label = label
        self.consequence = consequence
        self.bindings = bindings or {}
        self.key = f"atom:{label}:{consequence}"


class Silent:
    pass


class PartialOrder:
    def __init__(self, children, order):
        self.children = tuple(children)
        self.order = frozenset(order)
        self.depth = 2


class ChoiceGraph:
    def __init__(self, children, edges, start=0, end=1):
        self.children = tuple(children)
        self.edges = frozenset(edges)
        self.start = start
        self.end = end
        self.depth = 2


def test_pddl_exports_state_action_and_direct_state_transitions():
    export = m.export_pddl_domain(DeterministicDomain(), subject="deterministic")
    payload = export.canonical_dict()
    assert payload["formalism"] == "pddl"
    assert any(node["kind"] == "action" for node in payload["nodes"])
    assert any(edge["kind"] == "transition" for edge in payload["edges"])
    assert payload["metadata"]["authority"] == "non-actuating"


def test_ppddl_normalizes_probability_weights_and_preserves_value():
    export = m.export_ppddl_domain(ProbabilisticDomain(), subject="uncertain")
    payload = export.canonical_dict()
    probability_edges = [
        edge for edge in payload["edges"] if edge["kind"] == "probabilistic"
    ]
    probabilities = sorted(
        {
            edge["attributes"]["probability"]
            for edge in probability_edges
            if "probability" in edge["attributes"]
        }
    )
    assert probabilities == [0.3, 0.7]
    assert any("reward" in edge["attributes"] for edge in probability_edges)


def test_tpddl_exports_time_and_duration_for_timeline_and_gantt():
    export = m.export_tpddl_domain(TemporalDomain(), subject="temporal")
    payload = export.canonical_dict()
    assert payload["formalism"] == "pddl+"
    assert any("time" in node["attributes"] for node in payload["nodes"])
    assert any(
        node["kind"] == "action" and "duration" in node["attributes"]
        for node in payload["nodes"]
    )
    assert any(edge["kind"] == "temporal" for edge in payload["edges"])


def test_rddl_exports_observed_policy_rollout_only():
    export = m.export_rddl_rollout(RDDLDomain(), [1, 2, 3], subject="rddl-policy")
    payload = export.canonical_dict()
    assert payload["formalism"] == "rddl"
    assert payload["metadata"]["export_mode"] == "observed-bounded-rollout"
    assert payload["metadata"]["steps"] == 2
    assert payload["metadata"]["terminated"] is True


def test_powl_partial_order_does_not_invent_concurrency_edges():
    root = PartialOrder(
        (Atom("rights"), Atom("marketing"), Atom("release")),
        {OrderEdge(0, 2)},
    )
    payload = m.export_powl(root, subject="release-plan").canonical_dict()
    precedence = [edge for edge in payload["edges"] if edge["kind"] == "precedence"]
    assert len(precedence) == 1
    labels = {node["id"]: node["label"] for node in payload["nodes"]}
    assert labels[precedence[0]["source"]] == "rights"
    assert labels[precedence[0]["target"]] == "release"
    assert not any(
        {labels[edge["source"]], labels[edge["target"]]} == {"rights", "marketing"}
        for edge in payload["edges"]
    )


def test_powl_choice_graph_preserves_cycle_and_guard():
    loop = ChoiceGraph(
        (Silent(), Silent(), Atom("tool-call")),
        {
            ChoiceGraphEdge(0, 1),
            ChoiceGraphEdge(0, 2, Guard("enter", {})),
            ChoiceGraphEdge(2, 2, Guard("repeat", {"bounded": True})),
            ChoiceGraphEdge(2, 1, Guard("exit", {})),
        },
    )
    payload = m.export_powl(loop, subject="agent-loop").canonical_dict()
    action = next(node for node in payload["nodes"] if node["label"] == "tool-call")
    assert any(
        edge["source"] == action["id"]
        and edge["target"] == action["id"]
        and edge["attributes"].get("guard", {}).get("predicate_name") == "repeat"
        for edge in payload["edges"]
    )


def test_export_is_deterministic_and_receives_explicit_claim_ceiling():
    left = m.export_pddl_domain(DeterministicDomain(), subject="same")
    right = m.export_pddl_domain(DeterministicDomain(), subject="same")
    assert left.canonical_json() == right.canonical_json()
    assert left.digest() == right.digest()
    assert left.canonical_dict()["metadata"]["claim_ceiling"] == m.CLAIM_CEILING


def test_invalid_limits_refuse():
    with pytest.raises(m.PlanningExportError, match="AFL-MMDIO-001"):
        m.export_pddl_domain(
            DeterministicDomain(),
            subject="bad",
            limits=m.ExportLimits(max_states=0),
        )
