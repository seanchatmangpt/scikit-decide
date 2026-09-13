# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Planner-neutral, causally-honest discovered-model IR for Level 4.

`DiscoveredDomain`/`DiscoveredProblem` are the canonical output of blind
discovery -- NOT a `Recipe`. A `Recipe` (see `gym_procedure.py`) is one
*projection* of a `DiscoveredDomain`, chosen because `GymProcedureDomain` +
the existing solver registry already consume it; a PDDL projection is a
second. Neither projection is the definition of what was learned.

Causal honesty: naively intersecting pre-states across every successful
call to an action produces a *superset* precondition hypothesis that may
include facts that are merely correlated with success, not causal (e.g. if
`unlock` only ever succeeded while `{A,B,C}` all held, intersection yields
`{A,B,C}` even if only `B` is load-bearing). `propose_discriminating_probe`
generates the probe that would tell them apart (hold the rest fixed, flip
one fact); `refine_from_probe` shrinks the hypothesis when the flipped fact
turns out not to matter. This is deliberately a hypothesis-refinement loop,
not a one-shot STRIPS reconstruction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from autofde_lab.hub.domain.gym_procedure.gym_procedure import Recipe, Step


@dataclass(frozen=True)
class DiscoveredAction:
    """One action as currently understood -- a hypothesis, not ground truth."""

    id: str
    preconditions: frozenset[str] = field(default_factory=frozenset)
    positive_effects: frozenset[str] = field(default_factory=frozenset)
    negative_effects: frozenset[str] = field(default_factory=frozenset)
    applicability_evidence: tuple[
        int, ...
    ] = ()  # probe-log line indices where this action succeeded
    refusal_evidence: tuple[
        int, ...
    ] = ()  # probe-log line indices where this action was attempted and refused
    confidence: float = 0.0  # fraction of probes of this action that are consistent with the current hypothesis
    unresolved_semantics: bool = True  # True until >=1 discriminating probe has run, or only 1 candidate fact remained
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiscoveredDomain:
    """The learned causal object. Planner-neutral: A*, other solvers, PDDL,
    Recipe are all *consumers* of this, never its definition."""

    state_variables: frozenset[str]
    actions: dict[str, DiscoveredAction] = field(default_factory=dict)
    unknown_actions: frozenset[str] = field(
        default_factory=frozenset
    )  # probed, effect not yet resolved
    invariants: frozenset[str] = field(
        default_factory=frozenset
    )  # facts observed stable across irrelevant actions

    def declared_projections(self) -> frozenset[str]:
        return frozenset({"recipe", "pddl"})


@dataclass(frozen=True)
class DiscoveredProblem:
    initial_state: frozenset[str]
    goal: frozenset[str]
    preservation_constraints: frozenset[str] = field(default_factory=frozenset)
    cost_bound: float | None = None


@dataclass(frozen=True)
class Probe:
    """A specific action to attempt next, and why."""

    action: str
    rationale: str


def induce_discovered_domain(probe_log: list[dict]) -> DiscoveredDomain:
    """First-pass causal hypothesis: intersect pre-states across successful
    calls per action (a superset precondition candidate -- see module
    docstring), union deltas for effects. This is the fast, cheap prior
    that `propose_discriminating_probe`/`refine_from_probe` subsequently
    interrogate; it is never treated as ground truth on its own.
    """
    by_action: dict[str, list[dict]] = {}
    for i, rec in enumerate(probe_log):
        by_action.setdefault(rec["action"], []).append({**rec, "_idx": i})

    state_vars: set[str] = set()
    actions: dict[str, DiscoveredAction] = {}
    unknown: set[str] = set()

    for action_id, records in by_action.items():
        successes = [r for r in records if r.get("applicable")]
        refusals = [r for r in records if not r.get("applicable")]
        pos = (
            frozenset().union(*(frozenset(r.get("delta_added", [])) for r in successes))
            if successes
            else frozenset()
        )
        neg = (
            frozenset().union(
                *(frozenset(r.get("delta_removed", [])) for r in successes)
            )
            if successes
            else frozenset()
        )
        state_vars |= pos | neg

        if not successes:
            unknown.add(action_id)
            actions[action_id] = DiscoveredAction(
                id=action_id,
                refusal_evidence=tuple(r["_idx"] for r in refusals),
                confidence=0.0,
                unresolved_semantics=True,
            )
            continue

        # Precondition hypothesis needs the *pre-state* each successful call
        # observed -- probe records only expose delta, not the raw
        # pre-state fact-set, so callers that want a real precondition
        # hypothesis must include "observed_pre_facts" in each record
        # (BlindEnvironment.try_action does this for the real bridge; the
        # in-memory harness may omit it, in which case preconditions stay
        # empty/unresolved rather than fabricated).
        pre_states = [
            frozenset(r["observed_pre_facts"])
            for r in successes
            if "observed_pre_facts" in r
        ]
        if pre_states:
            precond_hypothesis = frozenset.intersection(*pre_states)
        else:
            precond_hypothesis = frozenset()

        actions[action_id] = DiscoveredAction(
            id=action_id,
            preconditions=precond_hypothesis,
            positive_effects=pos,
            negative_effects=neg,
            applicability_evidence=tuple(r["_idx"] for r in successes),
            refusal_evidence=tuple(r["_idx"] for r in refusals),
            confidence=len(successes) / len(records),
            unresolved_semantics=len(precond_hypothesis)
            > 1,  # >1 candidate fact => still ambiguous until discriminated
        )

    return DiscoveredDomain(
        state_variables=frozenset(state_vars),
        actions=actions,
        unknown_actions=frozenset(unknown),
    )


def propose_discriminating_probe(
    domain: DiscoveredDomain, action_id: str
) -> Probe | None:
    """If `action_id`'s precondition hypothesis has >1 candidate fact,
    propose re-attempting it -- the caller is expected to hold all but one
    hypothesized fact fixed and flip the remaining one (harness-level
    concern; this function names the target action and the reason).
    Returns None once the hypothesis is already minimal (<=1 fact) or the
    action has no recorded hypothesis at all.
    """
    act = domain.actions.get(action_id)
    if act is None or len(act.preconditions) <= 1:
        return None
    return Probe(
        action=action_id,
        rationale=(
            f"precondition hypothesis {sorted(act.preconditions)} has "
            f"{len(act.preconditions)} candidate facts -- re-probe with one "
            f"flipped at a time to falsify non-causal members"
        ),
    )


def refine_from_probe(
    domain: DiscoveredDomain,
    action_id: str,
    held_facts: frozenset[str],
    flipped_fact: str,
    succeeded: bool,
) -> DiscoveredDomain:
    """Update `action_id`'s precondition hypothesis given one discriminating
    probe result: if the action still succeeded with `flipped_fact` absent
    (i.e. `held_facts` alone were sufficient), `flipped_fact` is not causal
    and is dropped from the hypothesis. If it failed, `flipped_fact` stays
    (still a candidate, though not yet proven singly sufficient).
    """
    act = domain.actions.get(action_id)
    if act is None:
        return domain
    if succeeded:
        new_precond = frozenset(f for f in act.preconditions if f != flipped_fact)
    else:
        new_precond = act.preconditions
    new_act = DiscoveredAction(
        id=act.id,
        preconditions=new_precond,
        positive_effects=act.positive_effects,
        negative_effects=act.negative_effects,
        applicability_evidence=act.applicability_evidence,
        refusal_evidence=act.refusal_evidence,
        confidence=act.confidence,
        unresolved_semantics=len(new_precond) > 1,
        evidence_refs=act.evidence_refs,
    )
    new_actions = dict(domain.actions)
    new_actions[action_id] = new_act
    return DiscoveredDomain(
        state_variables=domain.state_variables,
        actions=new_actions,
        unknown_actions=domain.unknown_actions,
        invariants=domain.invariants,
    )


def project_to_recipe(
    domain: DiscoveredDomain,
    problem: DiscoveredProblem,
    gym: str,
    task: str,
    source_ref: str,
) -> Recipe:
    """The one projection wired to the existing solver registry this pass.
    Actions still marked `unresolved_semantics` are included with their
    current best hypothesis (Recipe/Astar have no "unknown" representation
    -- see gym_procedure.py's own three-tier convention notes) rather than
    silently dropped, since an incomplete-but-present hypothesis is still
    more honest than omission for planning purposes; callers that need
    strict causal certainty before planning should gate on
    `unresolved_semantics` themselves before calling this.
    """
    steps = tuple(
        Step(
            id=act.id,
            description=f"discovered action (confidence={act.confidence:.2f})",
            preconditions=act.preconditions,
            establishes=act.positive_effects,
            removes=act.negative_effects,
            source=f"induced:evidence_refs={list(act.evidence_refs)}",
        )
        for act in domain.actions.values()
        if act.id not in domain.unknown_actions
    )
    return Recipe(
        gym=gym,
        task=task,
        source_ref=source_ref,
        initial_facts=problem.initial_state,
        goal_facts=problem.goal,
        steps=steps,
    )


def project_to_pddl(domain: DiscoveredDomain, problem: DiscoveredProblem) -> str:
    """Second projection, feeding this repo's existing PDDL engine
    (`fabric/pddl_engine.py`). Deliberately minimal (:strips only, no
    :derived-predicates/:constraints/:preferences -- CLAUDE.md's own
    requirements gate forbids ever emitting those without real support)."""
    actions_pddl = []
    for act in domain.actions.values():
        if act.id in domain.unknown_actions:
            continue
        precond = " ".join(f"(fact-{f})" for f in sorted(act.preconditions)) or ""
        add = " ".join(f"(fact-{f})" for f in sorted(act.positive_effects))
        deln = " ".join(f"(not (fact-{f}))" for f in sorted(act.negative_effects))
        effect = " ".join(x for x in (add, deln) if x)
        actions_pddl.append(
            f"  (:action {act.id}\n"
            f"   :parameters ()\n"
            f"   :precondition (and {precond})\n"
            f"   :effect (and {effect})\n"
            f"  )"
        )
    all_facts = sorted(domain.state_variables)
    predicates = " ".join(f"(fact-{f})" for f in all_facts)
    return (
        "(define (domain discovered)\n"
        "  (:requirements :strips)\n"
        f"  (:predicates {predicates})\n" + "\n".join(actions_pddl) + "\n)"
    )
