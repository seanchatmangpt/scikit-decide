# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-school tests for real DSPyPolicy against real "advanced planning"
domains (PDDL, scheduling/RCPSP, unified-planning, and RDDL) beyond the
toy-game domains covered by `tests/test_self_play_dspy_all_domains_chicago.py`.

These domains exercise two real extensions to `DSPyPolicy`'s action
resolution, both added alongside this test file (see
`src/autofde_lab/hub/solver/dspy_policy/dspy_policy.py`):

- **Per-state applicable-actions enumeration** (`PDDLDomain`, `RCPSP`,
  `MRCPSP`): these domains' *static* `get_action_space()` is not enumerable
  (`PDDLDomain` returns a real `ImplicitSpace` with no `get_elements()`;
  `RCPSP`/`MRCPSP` return `None`), but `domain.get_applicable_actions()`
  returns a real, finite, enumerable space at the domain's current state.
  Verified directly against real instances of each domain before writing
  these tests. `RCPSP`/`MRCPSP` also required relaxing `DSPyPolicy.T_domain`
  from `UnrestrictedActions` to its real superclass `Actions` in the mixin
  chain (`Events -> Actions -> UnrestrictedActions`), since scheduling
  domains only implement `Actions` -- a real, backward-compatible widening
  since every domain that provides `UnrestrictedActions` already provides
  `Actions` too.
- **Structured JSON generation** (`RDDLDomain`'s `TowerOfHanoi_arcade`):
  the real action space here is a real gymnasium `Dict` of `Discrete(2)`
  sub-spaces (one boolean move-flag per disk/rod pair) with no
  `get_elements()` anywhere -- not even `get_applicable_actions()`, which
  is real but was found, empirically, to be impractically slow to enumerate
  for this domain. `DSPyPolicy` instead asks the LLM to generate a JSON
  object matching the action's real field schema and validates it with the
  domain's real `action_space.contains(...)` before returning it.

`UPDomain` (unified-planning bridge) is exercised too: its static
`get_action_space()` is already enumerable, but it also only implements
`Actions` (not `UnrestrictedActions`), so it only became usable through
`DSPyPolicy` after the same `T_domain` widening described above -- it was
NOT constructible against `DSPyPolicy` before that change (verified
directly: `DSPyPolicy.check_domain(UPDomain(problem))` was `False` before
the widening and `True` after).

No mocks anywhere in this file: every assertion below was run against the
real, already-running TurboFieldfareServer before being written, per this
repo's Chicago-school convention. Reuses the shared
`real_turbo_fieldfare_server`/`real_dspy_lm` fixtures and
`requires_real_turbo_fieldfare_binary_and_model` marker factored into
`tests/conftest.py` -- no server-lifecycle code is duplicated here.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# `requires_real_turbo_fieldfare_binary_and_model` is redefined locally rather
# than imported from `tests/conftest.py`: `tests/` has no `__init__.py`
# markers (see `.claude/rules/standing-law.md`'s "Former standing exception"
# section on the bare-conftest module-name collision this repo hit before),
# so `tests/conftest.py` and any sibling `tests/<subdir>/conftest.py` both
# import under the same bare module name `conftest` in pytest's default
# "prepend" mode. `from conftest import requires_real_turbo_fieldfare_binary_and_model`
# is therefore order-dependent on which conftest.py pytest happened to import
# first in this process -- exactly the real `ImportError` already found and
# fixed the same way in `tests/test_self_play_dspy_groq_chicago.py`.
_TURBO_FIELDFARE_DIR = Path.home() / "turbo-fieldfare"
_SERVER_BINARY = _TURBO_FIELDFARE_DIR / ".build" / "release" / "TurboFieldfareServer"
_MODEL_PATH = _TURBO_FIELDFARE_DIR / "scratch" / "gemma4.gturbo"

requires_real_turbo_fieldfare_binary_and_model = pytest.mark.skipif(
    not (_SERVER_BINARY.exists() and _MODEL_PATH.exists()),
    reason=(
        f"Real TurboFieldfareServer binary ({_SERVER_BINARY}) or real model "
        f"weights ({_MODEL_PATH}) not present -- build/install them per "
        "turbo-fieldfare's README before running this real end-to-end test."
    ),
)

# The RCPSP/MRCPSP instances below come from the `discrete_optimization` benchmark
# corpus, which is not vendored into this repository. Resolve it from the
# environment so a clean checkout skips with a named blocker instead of failing on
# a machine-specific absolute path.
DISCRETE_OPTIMIZATION_DATA = os.path.expanduser(
    os.environ.get("DISCRETE_OPTIMIZATION_DATA", "~/discrete_optimization_data")
)


def _rcpsp_instance(relative_path: str) -> str:
    """Return an absolute path to a benchmark instance, or skip if the corpus is absent."""
    instance_file = os.path.join(DISCRETE_OPTIMIZATION_DATA, relative_path)
    if not os.path.isfile(instance_file):
        pytest.skip(
            f"BLOCKED:DISCRETE_OPTIMIZATION_DATA_ABSENT: {instance_file} not found. "
            "Set DISCRETE_OPTIMIZATION_DATA to the benchmark corpus root."
        )
    return instance_file


PDDL_DOMAIN_FILE = "cpp/tests/data/pddl/ipc-1998/domains/gripper-round-1-strips/domain.pddl"
PDDL_INSTANCE_FILE = (
    "cpp/tests/data/pddl/ipc-1998/domains/gripper-round-1-strips/instances/instance-1.pddl"
)


@requires_real_turbo_fieldfare_binary_and_model
def test_real_dspy_policy_solves_real_pddl_gripper_domain_via_real_applicable_actions_enumeration(
    real_dspy_lm,
):
    """Real domain: PDDLDomain (gripper-round-1-strips, deterministic STRIPS).

    Real check: `PDDLDomain.get_action_space()` returns a real
    `ImplicitSpace` with no `get_elements()` -- DSPyPolicy must fall back to
    the real, per-state `domain.get_applicable_actions()` (a real
    `ListSpace`) to find an enumerable set of legal moves, and the action it
    returns is really a member of that real per-state applicable-actions
    space (`PDDLAction` has no `__eq__`, so real members are compared by
    their real `str()` -- the same real string identity DSPyPolicy itself
    matches the model's answer against).
    """
    from autofde_lab.hub.domain.pddl.domain import PDDLDomain
    from autofde_lab.hub.solver.dspy_policy import DSPyPolicy

    def domain_factory() -> PDDLDomain:
        return PDDLDomain(PDDL_DOMAIN_FILE, PDDL_INSTANCE_FILE)

    assert DSPyPolicy.check_domain(PDDLDomain(PDDL_DOMAIN_FILE, PDDL_INSTANCE_FILE))

    with DSPyPolicy(domain_factory=domain_factory, lm=real_dspy_lm) as solver:
        solver.solve()
        observation = solver._domain.reset()
        action = solver.sample_action(observation)

        legal_actions = solver._domain.get_applicable_actions()["agent"].get_elements()
        assert str(action) in {str(a) for a in legal_actions}


@requires_real_turbo_fieldfare_binary_and_model
def test_real_dspy_policy_solves_real_rcpsp_via_real_applicable_actions_enumeration(
    real_dspy_lm,
):
    """Real domain: RCPSP (single-mode resource-constrained project
    scheduling, real discrete-optimization instance data `j301_4.sm`).

    Real check: `RCPSP.get_action_space()` returns real `None` -- DSPyPolicy
    must fall back to the real `domain.get_applicable_actions()` (a real
    `SchedulingActionSpace`) to find legal moves. Also exercises the real
    `T_domain` widening from `UnrestrictedActions` to `Actions`: `RCPSP`
    only implements `Actions`, so `DSPyPolicy.check_domain` on it was real
    `False` before that widening.
    """
    from autofde_lab.hub.domain.rcpsp.rcpsp_sk_parser import load_domain
    from autofde_lab.hub.solver.dspy_policy import DSPyPolicy

    instance_file = _rcpsp_instance("rcpsp/j301_4.sm")

    def domain_factory():
        return load_domain(instance_file)

    assert DSPyPolicy.check_domain(load_domain(instance_file))

    with DSPyPolicy(domain_factory=domain_factory, lm=real_dspy_lm) as solver:
        solver.solve()
        observation = solver._domain.reset()
        action = solver.sample_action(observation)

        legal_actions = solver._domain.get_applicable_actions()["agent"].get_elements()
        assert str(action) in {str(a) for a in legal_actions}


@requires_real_turbo_fieldfare_binary_and_model
def test_real_dspy_policy_solves_real_mrcpsp_via_real_applicable_actions_enumeration(
    real_dspy_lm,
):
    """Real domain: MRCPSP (multi-mode resource-constrained project
    scheduling, real discrete-optimization instance data `j1010_1.mm`).

    Real check: same real `Actions`-only / `get_action_space() is None`
    shape as `RCPSP` above, on the real multi-mode subclass returned by
    `load_domain` for a real `.mm` instance file (`load_domain` auto-
    dispatches to `MRCPSP` when `rcpsp_model.is_rcpsp_multimode()` is real
    `True`, verified directly against this exact instance file).
    """
    from autofde_lab.hub.domain.rcpsp.rcpsp_sk_parser import load_domain
    from autofde_lab.hub.solver.dspy_policy import DSPyPolicy

    instance_file = _rcpsp_instance("rcpsp/j1010_1.mm")

    def domain_factory():
        return load_domain(instance_file)

    assert DSPyPolicy.check_domain(load_domain(instance_file))

    with DSPyPolicy(domain_factory=domain_factory, lm=real_dspy_lm) as solver:
        solver.solve()
        observation = solver._domain.reset()
        action = solver.sample_action(observation)

        legal_actions = solver._domain.get_applicable_actions()["agent"].get_elements()
        assert str(action) in {str(a) for a in legal_actions}


@requires_real_turbo_fieldfare_binary_and_model
def test_real_dspy_policy_solves_real_updomain_robot_moves_problem(real_dspy_lm):
    """Real domain: UPDomain wrapping a real, hand-built unified-planning
    `Problem` (a 3-location robot-navigation problem: l1 -> l2 -> l3).

    Real check: `UPDomain.get_action_space()` is already a real enumerable
    `ListSpace`, but `UPDomain` only implements `Actions` (not
    `UnrestrictedActions`) -- so this domain only became real-usable through
    `DSPyPolicy` after the same `T_domain` widening exercised by the RCPSP/
    MRCPSP tests above (verified directly:
    `DSPyPolicy.check_domain(UPDomain(problem))` was real `False` before the
    widening).
    """
    import unified_planning.shortcuts as up
    from unified_planning.model import Fluent, InstantaneousAction, Object, Problem

    from autofde_lab.hub.domain.up import UPDomain
    from autofde_lab.hub.solver.dspy_policy import DSPyPolicy

    def build_problem() -> Problem:
        location = up.UserType("Location")
        robot_at = Fluent("robot_at", up.BoolType(), l=location)
        connected = Fluent(
            "connected", up.BoolType(), l_from=location, l_to=location
        )
        move = InstantaneousAction("move", l_from=location, l_to=location)
        l_from, l_to = move.parameter("l_from"), move.parameter("l_to")
        move.add_precondition(connected(l_from, l_to))
        move.add_precondition(robot_at(l_from))
        move.add_effect(robot_at(l_from), False)
        move.add_effect(robot_at(l_to), True)
        l1, l2, l3 = (
            Object("l1", location),
            Object("l2", location),
            Object("l3", location),
        )
        problem = Problem("robot_moves")
        problem.add_fluent(robot_at, default_initial_value=False)
        problem.add_fluent(connected, default_initial_value=False)
        problem.add_action(move)
        problem.add_objects([l1, l2, l3])
        problem.set_initial_value(robot_at(l1), True)
        problem.set_initial_value(connected(l1, l2), True)
        problem.set_initial_value(connected(l2, l3), True)
        problem.add_goal(robot_at(l3))
        return problem

    def domain_factory() -> UPDomain:
        return UPDomain(build_problem())

    assert DSPyPolicy.check_domain(UPDomain(build_problem()))

    with DSPyPolicy(domain_factory=domain_factory, lm=real_dspy_lm) as solver:
        solver.solve()
        observation = solver._domain.reset()
        action = solver.sample_action(observation)

        legal_actions = solver._domain.get_action_space()["agent"].get_elements()
        assert action in legal_actions


@requires_real_turbo_fieldfare_binary_and_model
def test_real_dspy_policy_solves_real_flight_planning_domain_lfpg_to_lfbo(real_dspy_lm):
    """Real domain: FlightPlanningDomain, real LFPG -> LFBO route, real A320
    OPENAP performance model (`aircraft_performance.bean.aircraft_state.AircraftState`).

    Real check: `FlightPlanningDomain.get_action_space()` was empirically
    verified to already be a real, directly enumerable `EnumSpace` (the
    `H_Action` heading-change enum) -- unlike the input task list's
    `non_enumerable_or_continuous` label for this domain, which this test's
    own construction run found to be stale: no DSPyPolicy extension was
    needed for this specific domain/instance, only the real
    `Actions`-widened `T_domain` already required by RCPSP/MRCPSP/UPDomain
    above (this domain already had `UnrestrictedActions`, so it was
    unaffected by that widening either way).
    """
    from autofde_lab.hub.domain.flight_planning.aircraft_performance.bean.aircraft_state import (
        AircraftState,
    )
    from autofde_lab.hub.domain.flight_planning.aircraft_performance.performance.performance_model_enum import (
        PerformanceModelEnum,
    )
    from autofde_lab.hub.domain.flight_planning.domain import FlightPlanningDomain
    from autofde_lab.hub.solver.dspy_policy import DSPyPolicy

    def domain_factory() -> FlightPlanningDomain:
        aircraft_state = AircraftState(
            performance_model_type=PerformanceModelEnum.OPENAP,
            model_type="A320",
            mach=0.78,
            gw_kg=60000.0,
        )
        return FlightPlanningDomain(
            aircraft_state=aircraft_state, origin="LFPG", destination="LFBO"
        )

    assert DSPyPolicy.check_domain(domain_factory())

    with DSPyPolicy(domain_factory=domain_factory, lm=real_dspy_lm) as solver:
        solver.solve()
        observation = solver._domain.reset()
        action = solver.sample_action(observation)

        legal_actions = solver._domain.get_action_space()["agent"].get_elements()
        assert action in legal_actions


@requires_real_turbo_fieldfare_binary_and_model
def test_real_dspy_policy_generates_a_real_valid_action_for_real_rddl_tower_of_hanoi(
    real_dspy_lm,
):
    """Real domain: RDDLDomain wrapping `TowerOfHanoi_arcade` instance `0`
    from `rddlrepository` (real pyRDDLGym problem, no mocked domain
    dynamics).

    Real check: this domain's real action space is a real gymnasium `Dict`
    of `Discrete(2)` sub-spaces (one boolean `move___dX__rY` flag per
    disk/rod pair) -- it has no `get_elements()` anywhere DSPyPolicy could
    enumerate from (confirmed directly: neither the static action space nor
    `get_applicable_actions()` exposes one, and the latter was additionally
    found to be impractically slow to enumerate for this domain). DSPyPolicy
    must use its real structured-generation path: ask the LLM for a real
    JSON object matching the action's real field schema, then validate the
    real parsed result against the domain's real
    `action_space.contains(...)`.
    """
    from rddlrepository.core.manager import RDDLRepoManager

    from autofde_lab.hub.domain.rddl import RDDLDomain
    from autofde_lab.hub.solver.dspy_policy import DSPyPolicy

    def build_domain() -> RDDLDomain:
        # rebuild=True: RDDLRepoManager's on-disk archive cache was built
        # while this repo lived at ~/scikit-decide (pre-rename) and still
        # points rddlrepository entries at that now-nonexistent path
        # (RDDLRepoDomainNotExistError citing
        # /Users/sac/scikit-decide/.venv/.../TowerOfHanoi/domain.rddl).
        # rebuild=False trusts that stale cache; True re-derives it against
        # the current install.
        manager = RDDLRepoManager(rebuild=True)
        problem = manager.get_problem("TowerOfHanoi_arcade")
        return RDDLDomain(
            rddl_domain=problem.get_domain(),
            rddl_instance=problem.get_instance("0"),
            display_with_pygame=False,
        )

    assert DSPyPolicy.check_domain(build_domain())

    with DSPyPolicy(domain_factory=build_domain, lm=real_dspy_lm) as solver:
        solver.solve()
        observation = solver._domain.reset()
        action = solver.sample_action(observation)

        action_space = solver._domain.get_action_space()["agent"]
        assert action_space.contains(action)
