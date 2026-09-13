"""Fortune-5 SAFe organizational, dependency, role, and cadence topology."""

from __future__ import annotations

import math

from .model import (
    AgileReleaseTrain,
    AgileTeam,
    CadenceBucket,
    Dependency,
    EnterpriseTopology,
    Fortune5Config,
    PersonnelSeat,
    Portfolio,
    RoleAssignment,
    SolutionTrain,
    ValueStream,
    WorkItem,
)

TEAM_ROLES = (
    "product_owner",
    "team_coach",
    "software_engineer",
    "qa_engineer",
    "data_engineer",
    "security_engineer",
    "platform_engineer",
    "business_analyst",
    "ux_designer",
    "reliability_engineer",
)


def build_topology(config: Fortune5Config = Fortune5Config()) -> EnterpriseTopology:
    portfolio_budget = config.annual_budget_usd / config.portfolios
    value_stream_budget = portfolio_budget / config.value_streams_per_portfolio
    art_budget = value_stream_budget / config.arts_per_value_stream

    portfolios: list[Portfolio] = []
    value_streams: list[ValueStream] = []
    arts: list[AgileReleaseTrain] = []
    teams: list[AgileTeam] = []
    people: list[PersonnelSeat] = []
    roles: list[RoleAssignment] = []
    work_items: list[WorkItem] = []
    solution_to_vs = {f"ST-{i:02d}": [] for i in range(config.solution_trains)}
    solution_to_arts = {key: [] for key in solution_to_vs}

    global_vs = global_art = global_team = global_person = 0
    for portfolio_index in range(config.portfolios):
        portfolio_id = f"P-{portfolio_index + 1:02d}"
        value_stream_ids: list[str] = []
        for _ in range(config.value_streams_per_portfolio):
            value_stream_id = f"VS-{global_vs + 1:03d}"
            solution_id = (
                f"ST-{global_vs // config.value_streams_per_solution_train:02d}"
            )
            solution_to_vs[solution_id].append(value_stream_id)
            art_ids: list[str] = []
            for _ in range(config.arts_per_value_stream):
                art_id = f"ART-{global_art + 1:03d}"
                solution_to_arts[solution_id].append(art_id)
                team_ids: list[str] = []
                for _ in range(config.teams_per_art):
                    team_id = f"TEAM-{global_team + 1:04d}"
                    seat_ids: list[str] = []
                    for seat_index in range(config.people_per_team):
                        person_id = f"PERSON-{global_person + 1:05d}"
                        role = TEAM_ROLES[seat_index % len(TEAM_ROLES)]
                        people.append(PersonnelSeat(person_id, team_id, role))
                        seat_ids.append(person_id)
                        global_person += 1
                    teams.append(AgileTeam(team_id, art_id, tuple(seat_ids)))
                    team_ids.append(team_id)
                    global_team += 1
                arts.append(
                    AgileReleaseTrain(
                        art_id,
                        value_stream_id,
                        solution_id,
                        art_budget,
                        tuple(team_ids),
                    )
                )
                art_ids.append(art_id)
                global_art += 1
            value_streams.append(
                ValueStream(
                    value_stream_id,
                    portfolio_id,
                    solution_id,
                    value_stream_budget,
                    tuple(art_ids),
                )
            )
            value_stream_ids.append(value_stream_id)
            global_vs += 1
        portfolios.append(
            Portfolio(portfolio_id, portfolio_budget, tuple(value_stream_ids))
        )

    vs_by_id = {item.id: item for item in value_streams}
    art_by_id = {item.id: item for item in arts}
    team_by_id = {item.id: item for item in teams}
    solutions = tuple(
        SolutionTrain(
            solution_id,
            tuple(sorted({vs_by_id[vs].portfolio_id for vs in value_stream_ids})),
            tuple(value_stream_ids),
            tuple(solution_to_arts[solution_id]),
        )
        for solution_id, value_stream_ids in solution_to_vs.items()
    )

    def first_seats(art_id: str) -> tuple[str, ...]:
        art = art_by_id[art_id]
        return team_by_id[art.team_ids[0]].seat_ids

    for portfolio in portfolios:
        art_id = vs_by_id[portfolio.value_stream_ids[0]].art_ids[0]
        seats = first_seats(art_id)
        for index, role in enumerate(
            ("lpm_lead", "enterprise_architect", "epic_owner")
        ):
            roles.append(RoleAssignment("portfolio", portfolio.id, role, seats[index]))
    for value_stream in value_streams:
        seats = first_seats(value_stream.art_ids[0])
        for index, role in enumerate(("value_stream_owner", "solution_manager")):
            roles.append(
                RoleAssignment("value_stream", value_stream.id, role, seats[index + 3])
            )
    for solution in solutions:
        seats = first_seats(solution.art_ids[0])
        for index, role in enumerate(
            ("solution_train_engineer", "solution_architect", "solution_management")
        ):
            roles.append(
                RoleAssignment("solution_train", solution.id, role, seats[index + 5])
            )
    for art in arts:
        seats = first_seats(art.id)
        for index, role in enumerate(
            (
                "release_train_engineer",
                "product_management",
                "system_architect",
                "business_owner",
            )
        ):
            roles.append(RoleAssignment("art", art.id, role, seats[index]))

    # Explicit SAFe work hierarchy: strategy -> epics -> capabilities -> features -> stories.
    theme_index = epic_index = capability_index = feature_index = story_index = 0
    for portfolio in portfolios:
        for local_theme in range(config.strategic_themes_per_portfolio):
            theme_id = f"THEME-{theme_index + 1:03d}"
            work_items.append(
                WorkItem(
                    theme_id, "strategic_theme", None, portfolio.id, 1000.0, 0.0, 0.0
                )
            )
            for local_epic in range(config.epics_per_theme):
                epic_id = f"EPIC-{epic_index + 1:04d}"
                work_items.append(
                    WorkItem(
                        epic_id,
                        "epic",
                        theme_id,
                        portfolio.id,
                        500.0 + local_epic * 15,
                        180.0 + local_epic * 9,
                        40.0,
                    )
                )
                for local_capability in range(config.capabilities_per_epic):
                    value_stream_id = portfolio.value_stream_ids[
                        (epic_index + local_capability)
                        % len(portfolio.value_stream_ids)
                    ]
                    capability_id = f"CAP-{capability_index + 1:05d}"
                    work_items.append(
                        WorkItem(
                            capability_id,
                            "capability",
                            epic_id,
                            value_stream_id,
                            120.0,
                            55.0 + local_capability * 3,
                            18.0,
                            local_capability == 0,
                        )
                    )
                    value_stream = vs_by_id[value_stream_id]
                    for local_feature in range(config.features_per_capability):
                        art_id = value_stream.art_ids[
                            (capability_index + local_feature)
                            % len(value_stream.art_ids)
                        ]
                        feature_id = f"FEAT-{feature_index + 1:05d}"
                        feature_enabler = local_feature % 5 == 0
                        work_items.append(
                            WorkItem(
                                feature_id,
                                "feature",
                                capability_id,
                                art_id,
                                30.0,
                                13.0 + local_feature,
                                8.0,
                                feature_enabler,
                            )
                        )
                        art = art_by_id[art_id]
                        for local_story in range(config.stories_per_feature):
                            team_id = art.team_ids[
                                (feature_index + local_story) % len(art.team_ids)
                            ]
                            story_id = f"STORY-{story_index + 1:06d}"
                            work_items.append(
                                WorkItem(
                                    story_id,
                                    "story",
                                    feature_id,
                                    team_id,
                                    5.0,
                                    2.0 + (local_story % 4),
                                    1.0 + (local_story % 5),
                                    feature_enabler and local_story < 2,
                                )
                            )
                            story_index += 1
                        feature_index += 1
                    capability_index += 1
                epic_index += 1
            theme_index += 1

    dependencies: list[Dependency] = []
    for art in arts:
        dependencies.extend(
            Dependency(left, right, "team_flow", 0.35)
            for left, right in zip(art.team_ids, art.team_ids[1:])
        )
    for value_stream in value_streams:
        dependencies.extend(
            Dependency(left, right, "art_integration", 0.60)
            for left, right in zip(value_stream.art_ids, value_stream.art_ids[1:])
        )
    for portfolio in portfolios:
        dependencies.extend(
            Dependency(left, right, "value_stream", 0.75)
            for left, right in zip(
                portfolio.value_stream_ids, portfolio.value_stream_ids[1:]
            )
        )
    dependencies.extend(
        Dependency(left.id, right.id, "enterprise", 0.90)
        for left, right in zip(portfolios, portfolios[1:])
    )

    cadence = (
        CadenceBucket("portfolio_sync", config.portfolios * 2, "portfolio"),
        CadenceBucket("strategic_portfolio_review", config.portfolios, "portfolio"),
        CadenceBucket("pre_post_pi", config.solution_trains * 2, "solution_train"),
        CadenceBucket("pi_planning", config.arts, "art"),
        CadenceBucket("art_sync", config.arts * config.iterations_per_pi * 2, "art"),
        CadenceBucket("system_demo", config.arts * config.iterations_per_pi, "art"),
        CadenceBucket(
            "solution_demo",
            config.solution_trains * config.iterations_per_pi,
            "solution_train",
        ),
        CadenceBucket("inspect_and_adapt", config.arts, "art"),
        CadenceBucket(
            "iteration_planning", config.teams * config.iterations_per_pi, "team"
        ),
        CadenceBucket(
            "iteration_review", config.teams * config.iterations_per_pi, "team"
        ),
        CadenceBucket(
            "iteration_retro", config.teams * config.iterations_per_pi, "team"
        ),
        CadenceBucket(
            "team_sync",
            config.teams * config.iterations_per_pi * config.working_days_per_iteration,
            "team",
        ),
    )
    topology = EnterpriseTopology(
        tuple(portfolios),
        tuple(value_streams),
        solutions,
        tuple(arts),
        tuple(teams),
        tuple(people),
        tuple(roles),
        tuple(work_items),
        tuple(dependencies),
        cadence,
    )
    expected = {
        "portfolios": config.portfolios,
        "value_streams": config.value_streams,
        "solution_trains": config.solution_trains,
        "arts": config.arts,
        "teams": config.teams,
        "personnel": config.personnel,
        "strategic_themes": config.strategic_themes,
        "epics": config.epics,
        "capabilities": config.capabilities,
        "features": config.features,
        "stories": config.stories,
    }
    for key, value in expected.items():
        if topology.counts[key] != value:
            raise AssertionError(
                f"topology closure failure for {key}: {topology.counts[key]} != {value}"
            )
    if not math.isclose(
        topology.annual_budget_usd, config.annual_budget_usd, rel_tol=0, abs_tol=0.01
    ):
        raise AssertionError("portfolio budget does not close to enterprise budget")
    return topology
