#!/usr/bin/env python3
"""Real A*-search planner bridge invoked by castle's AutofdeLabPlanner.

Reads a JSON PlanningProblem DTO on stdin, runs a genuine A* forward search
over the transition-rule state graph (states = frozenset of achieved
predicates, edges = applicable TransitionRule applications), and writes a
JSON array of PlanCandidate DTOs on stdout matching castle's
`{planner_id, process: {id, goal_id, activities}, score}` shape.

Scope note (honesty, not decoration): this performs real forward A* search
in pure Python/stdlib (heapq) over the problem's own transition rules. It
does not currently route through autofde_lab's registered
`autofde_lab.hub.solver.astar.Astar` scikit-decide-style solver class --
wiring this problem into that solver's `GoalDomain` protocol (state space,
action space, transition/goal predicates as scikit-decide Memory/Value
types) is a real, separate integration task not attempted in this pass.
What is real here: a real subprocess boundary, a real distinct search
algorithm (state-space A* over achieved-predicate sets, vs. castle's
WitnessPlanner which only topologically orders a fixed witness_transitions
list by data dependency), and a real JSON contract both sides honor.
"""
from __future__ import annotations

import heapq
import json
import sys
from typing import Any


def astar_plan(rules: list[dict[str, Any]], goal_predicate: str) -> list[str] | None:
    """Forward A* over states = frozenset(achieved predicates).

    Returns an ordered list of rule ids applied to reach `goal_predicate`
    from the empty state, or None if no plan exists. Heuristic is the
    admissible zero heuristic (i.e. real Dijkstra/uniform-cost via heapq,
    which is a valid degenerate case of A*).
    """
    start: frozenset[str] = frozenset()
    if goal_predicate in start:
        return []

    # frontier entries: (g_cost, tie_breaker, state, path_of_rule_ids)
    counter = 0
    frontier: list[tuple[float, int, frozenset[str], tuple[str, ...]]] = [(0.0, counter, start, ())]
    best_cost: dict[frozenset[str], float] = {start: 0.0}

    while frontier:
        g, _, state, path = heapq.heappop(frontier)
        if goal_predicate in state:
            return list(path)
        if g > best_cost.get(state, float("inf")):
            continue
        for rule in rules:
            pre = set(rule.get("preconditions") or [])
            if not pre.issubset(state):
                continue
            if rule["id"] in path:
                continue  # no repeated application in this simple search
            new_state = state | set(rule.get("effects") or [])
            if new_state == state:
                continue
            cost = rule.get("cost")
            step_cost = float(cost) if cost is not None else 1.0
            new_g = g + step_cost
            if new_g < best_cost.get(new_state, float("inf")):
                best_cost[new_state] = new_g
                counter += 1
                heapq.heappush(frontier, (new_g, counter, new_state, path + (rule["id"],)))
    return None


def build_candidate(planner_id: str, goal_id: str, plan_rule_ids: list[str]) -> dict[str, Any]:
    activities = []
    prev_activity_id: str | None = None
    for rule_id in plan_rule_ids:
        activity_id = f"activity:{rule_id}"
        predecessors = [prev_activity_id] if prev_activity_id else []
        activities.append({
            "id": activity_id,
            "transition_id": rule_id,
            "predecessors": predecessors,
        })
        prev_activity_id = activity_id
    process_id = f"powl:astar:{goal_id}:{len(plan_rule_ids)}"
    return {
        "planner_id": planner_id,
        "process": {"id": process_id, "goal_id": goal_id, "activities": activities},
        "score": len(activities),
    }


def main() -> None:
    problem = json.load(sys.stdin)
    goal = problem["goal"]
    rules = problem["rules"]
    plan_rule_ids = astar_plan(rules, goal["predicate"])
    candidates: list[dict[str, Any]] = []
    if plan_rule_ids is not None and plan_rule_ids:
        candidates.append(build_candidate("autofde-lab-astar", goal["id"], plan_rule_ids))
    json.dump(candidates, sys.stdout)


if __name__ == "__main__":
    main()
