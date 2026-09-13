# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Fresh-task generator + blind-discovery harness for Level 4 crown trials.

Generator/solver knowledge separation (mission requirement): this module
knows the hidden transition system (:class:`Recipe`, reused unmodified from
`gym_procedure.py`). The solver never sees the Recipe object directly --
it only gets a :class:`BlindEnvironment` whose ``available_actions()``
returns action *names*, and whose ``try_action()`` returns only whether the
action succeeded plus the raw fact-set delta actually observed (not the
declared precondition/effect rule). All world knowledge the solver uses
must come through those two methods -- there is no third channel.

Isolation: every trial gets a fresh :class:`Trial`, its own uuid4 run_id,
its own evidence directory, its own probe/action log file. No shared
mutable module state; nothing here is written by more than one trial.

Independent verification: :func:`verify_trial` is a separate function that
reads ONLY the evidence log (the solver's actual actuation trace, not its
prose claims) plus the hidden Recipe, and recomputes goal-reachability
itself by literally replaying the recorded actions against the Recipe's own
transition rule -- it does not trust the solver's self-reported
GOAL_REACHED value.
"""

from __future__ import annotations

import json
import random
import uuid
from dataclasses import dataclass
from pathlib import Path

from autofde_lab.hub.domain.gym_procedure.gym_procedure import Recipe, Step

_FACT_POOL = [f"var{i}_set" for i in range(12)]
_DECEPTIVE_FACT_POOL = [f"deceptive{i}" for i in range(4)]


def generate_task(seed: int, n_steps: int = 4, n_irrelevant: int = 2) -> Recipe:
    """Manufacture a structurally distinct, bounded hidden Recipe from a frozen seed.

    Varies state-variable count, action count/names, preconditions, positive
    effects, an irrelevant/deceptive-but-lawful action, and (for seed % 5 == 0)
    a zero-action already-satisfied goal, per the mission's required coverage.
    """
    rng = random.Random(seed)
    facts = rng.sample(_FACT_POOL, k=min(n_steps + 2, len(_FACT_POOL)))

    if seed % 5 == 0:
        # Zero-action, already-satisfied-goal case: steps=(), goal subset of initial.
        initial = frozenset(facts[:2])
        goal = frozenset(facts[:1])
        return Recipe(
            gym="level4-synthetic",
            task=f"seed{seed}-zero-action",
            source_ref=f"generated:seed={seed}",
            initial_facts=initial,
            goal_facts=goal,
            steps=(),
        )

    steps: list[Step] = []
    have = {facts[0]}
    initial = frozenset(have)
    chain_names = [f"do_{i}" for i in range(n_steps)]
    for i, name in enumerate(chain_names):
        pre = frozenset(have)
        eff = frozenset({facts[i + 1]})
        steps.append(
            Step(
                id=name,
                description=f"synthetic step {i}",
                preconditions=pre,
                establishes=eff,
            )
        )
        have.add(facts[i + 1])
    goal = frozenset({facts[n_steps]})

    # Deceptive-but-lawful dead-end actions: always applicable, establish an
    # irrelevant fact not on any path to the goal. Real, executable, wrong.
    deceptive_facts = rng.sample(
        _DECEPTIVE_FACT_POOL, k=min(n_irrelevant, len(_DECEPTIVE_FACT_POOL))
    )
    for j, dfact in enumerate(deceptive_facts):
        steps.append(
            Step(
                id=f"deceptive_{j}",
                description=f"irrelevant lawful action {j}",
                preconditions=frozenset(),
                establishes=frozenset({dfact}),
            )
        )

    rng.shuffle(steps)
    return Recipe(
        gym="level4-synthetic",
        task=f"seed{seed}-chain{n_steps}",
        source_ref=f"generated:seed={seed}",
        initial_facts=initial,
        goal_facts=goal,
        steps=tuple(steps),
    )


@dataclass
class Trial:
    """One isolated crown trial: unique run_id, evidence dir, frozen seed."""

    seed: int
    run_id: str
    evidence_dir: Path
    recipe: Recipe  # hidden from the solver's own reasoning surface -- only used by BlindEnvironment/verifier

    @classmethod
    def new(cls, seed: int, root: Path) -> Trial:
        run_id = str(uuid.uuid4())
        evidence_dir = root / f"trial_{seed}_{run_id}"
        evidence_dir.mkdir(parents=True, exist_ok=False)
        recipe = generate_task(seed)
        return cls(seed=seed, run_id=run_id, evidence_dir=evidence_dir, recipe=recipe)

    def evidence_log(self) -> Path:
        return self.evidence_dir / "probes.jsonl"


class BlindEnvironment:
    """The ONLY interface the solver may use. Wraps a hidden Recipe."""

    def __init__(self, trial: Trial) -> None:
        self._recipe = trial.recipe
        self._state = frozenset(trial.recipe.initial_facts)
        self._log_path = trial.evidence_log()
        self._by_id = {s.id: s for s in trial.recipe.steps}

    def available_actions(self) -> list[str]:
        """Action *names* only -- no preconditions, no effects, no cost."""
        return sorted(self._by_id)

    def try_action(self, action: str) -> dict:
        """Attempt one action; append a durable evidence record; return the raw
        observed outcome (success flag + fact-set delta), never the rule itself."""
        step = self._by_id[action]
        applicable = step.preconditions <= self._state
        record = {
            "action": action,
            "pre_state_size": len(self._state),
            "observed_pre_facts": sorted(self._state),
            "applicable": applicable,
        }
        if applicable:
            new_state = (self._state - step.removes) | step.establishes
            delta_added = sorted(new_state - self._state)
            delta_removed = sorted(self._state - new_state)
            self._state = new_state
            record["delta_added"] = delta_added
            record["delta_removed"] = delta_removed
        else:
            record["delta_added"] = []
            record["delta_removed"] = []
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return record

    def goal_reached_UNSAFE_DEBUG_ONLY(self) -> bool:
        # Never call this from the solving agent -- self-certification is
        # exactly what the mission's SELF_CERTIFIED_POSTCONDITION falsifier
        # forbids. Present only so a human can sanity-check the harness
        # itself in isolation, never wired into the solver's decision loop.
        return self._recipe.goal_facts <= self._state


def blind_discover_and_plan(trial: Trial, max_probes: int = 200) -> list[str]:
    """A minimal real blind-discovery agent: probes every action from the
    current frontier until goal facts appear, using ONLY BlindEnvironment.
    No access to trial.recipe. This is intentionally simple (breadth-first
    probing + greedy commit on first success) -- sufficient to demonstrate
    the discovery/verification pipeline is real, not a claim about optimal
    discovery-agent design.
    """
    env = BlindEnvironment(trial)
    plan: list[str] = []
    tried_this_round: set[tuple[str, int]] = set()
    probes = 0
    # Stopping rule: keep probing until a full sweep produces no new state
    # change, derivable from observation alone -- the solver never sees
    # goal_facts and does not know in advance when it has "arrived".
    while probes < max_probes:
        progressed = False
        for action in env.available_actions():
            if probes >= max_probes:
                break
            key = (action, len(plan))
            if key in tried_this_round:
                continue
            tried_this_round.add(key)
            result = env.try_action(action)
            probes += 1
            if result["applicable"] and result["delta_added"]:
                plan.append(action)
                progressed = True
                tried_this_round.clear()
                break
        if not progressed:
            break
    return plan


def verify_trial(trial: Trial) -> dict:
    """Independent verifier: replays the durable evidence log against the
    hidden Recipe's real transition rule -- never trusts a solver-reported
    GOAL_REACHED value. Detects SELF_CERTIFIED_POSTCONDITION-class fraud by
    construction (there is no "claimed success" field to read)."""
    log_path = trial.evidence_log()
    state = set(trial.recipe.initial_facts)
    by_id = {s.id: s for s in trial.recipe.steps}
    n_records = 0
    if log_path.is_file():
        for line in log_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            n_records += 1
            step = by_id[rec["action"]]
            if step.preconditions <= state:
                state = (state - step.removes) | step.establishes
    goal_reached = trial.recipe.goal_facts <= state
    return {
        "trial_seed": trial.seed,
        "run_id": trial.run_id,
        "goal_reached": goal_reached,
        "final_state": sorted(state),
        "goal_facts": sorted(trial.recipe.goal_facts),
        "n_probe_records_replayed": n_records,
        "evidence_log": str(log_path),
    }
