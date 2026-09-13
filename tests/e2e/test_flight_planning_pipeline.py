# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-school pipeline test for the flight-planning domain family.

Real load_registered_domain('FlightPlanningDomain') +
load_registered_solver('pAstar') + check_domain + solve, no mocks or stubs.
tests/flight_planning/test_flight_planning.py already owns deep
domain-internal coverage (aircraft performance models, heuristics, ...);
this file only proves the registration-mechanism pipeline, reusing the same
small, fast instance shape as that file to keep e2e runtime bounded.
"""

import numpy as np

from skdecide import utils

from .conftest import requires_flight_planning_deps

pytestmark = requires_flight_planning_deps


def _make_domain_factory():
    from pygeodesy.ellipsoidalVincenty import LatLon
    from skdecide.hub.domain.flight_planning.aircraft_performance.bean.aircraft_state import (
        AircraftState,
    )
    from skdecide.hub.domain.flight_planning.aircraft_performance.performance.performance_model_enum import (
        PerformanceModelEnum,
    )
    from skdecide.hub.domain.flight_planning.aircraft_performance.performance.phase_enum import (
        PhaseEnum,
    )
    from skdecide.hub.domain.flight_planning.aircraft_performance.performance.rating_enum import (
        RatingEnum,
    )

    aircraft_state = AircraftState(
        model_type="A320",
        performance_model_type=PerformanceModelEnum.POLL_SCHUMANN,
        gw_kg=80_000,
        zp_ft=10_000,
        mach=0.78,
        phase=PhaseEnum.CLIMB,
        rating_level=RatingEnum.MCL,
        cg=0.3,
        gamma_air_deg=0,
    )

    FlightPlanningDomain = utils.load_registered_domain("FlightPlanningDomain")

    return lambda: FlightPlanningDomain(
        aircraft_state=aircraft_state,
        mach_cruise=0.78,
        mach_climb=0.7,
        mach_descent=0.65,
        nb_forward_points=20,
        nb_lateral_points=10,
        nb_climb_descent_steps=5,
        flight_levels_ft=list(np.arange(30_000, 38_000 + 2_000, 2_000)),
        graph_width="medium",
        origin=LatLon(43.629444, 1.363056),
        destination="EDDB",
        objective="fuel",
    )


def test_real_flight_planning_astar_pipeline_solves_and_rolls_out():
    """Real load_registered_domain('FlightPlanningDomain') +
    load_registered_solver('pAstar') round-trips through check_domain and
    solve for a small, real origin/destination instance.
    """
    domain_factory = _make_domain_factory()
    domain = domain_factory()

    AstarSolver = utils.load_registered_solver("pAstar")
    solver = AstarSolver(
        domain_factory=domain_factory, heuristic=lambda d, s: d.heuristic(s)
    )
    solver.solve()

    assert solver.check_domain(domain)
