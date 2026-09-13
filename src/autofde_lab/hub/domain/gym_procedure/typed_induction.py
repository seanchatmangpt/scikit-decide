# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Typed effect induction -- the repair for unsound add-list flattening.

The defect this exists to fix, found by a real trial run against the live
`cube_counter` provider: `induce_discovered_domain` unions observed deltas
across every successful call to an action. Probing `increment` at counter
0->1, 1->2, 2->3 therefore yields

    increment.positive_effects = {counter=1, counter=2, counter=3, solved=True}

which says a single `increment` establishes `solved=True`. That model is
unsound, it validated a 1-step plan for a 3-step goal, and *30 planners
agreed on it* -- so planner consensus provided no protection. Consensus
over a wrong model is confidently wrong, not right.

Root cause: a metric dimension's transition is **relative** (`counter += 1`),
but a propositional add-list can only express **absolute** facts. Flattening
one into the other loses the invariant and invents unconditional effects.

Repair: induce per-dimension, typed.

* metric dimensions (INTEGER/CONTINUOUS) -> a learned **delta** (`+1`), valid
  only if every observed transition of that action showed the SAME delta;
  otherwise the dimension is recorded as context-dependent and NOT claimed.
* non-metric dimensions (BOOLEAN/CATEGORICAL) -> an absolute value, and only
  when every observation agreed; a dimension that took different values in
  different contexts (e.g. `solved`, which depends on `counter == target`)
  is recorded as **derived/context-dependent** rather than asserted as an
  unconditional effect.

A derived dimension is not a gap to paper over -- it is the honest statement
that this action's effect on that dimension depends on state the add-list
cannot carry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Optional

from autofde_lab.hub.domain.gym_procedure.state_typing import (
    DimensionKind,
    StateDimension,
    classify_observation,
)


@dataclass(frozen=True)
class TypedEffect:
    """What one action does to one dimension, in that dimension's own terms."""

    dimension: str
    kind: DimensionKind
    delta: Optional[float] = None  # metric dims: the constant relative change
    absolute_value: Any = None  # non-metric dims: the constant value it lands on
    flip: bool = False  # boolean dims: the constant RELATIVE change (negation)
    context_dependent: bool = False  # observed inconsistently -> NOT claimed
    observations: int = 0
    repeatability_unknown: bool = True
    """Was this effect ever observed to REPEAT?

    Induced from a single observation, an effect says what happened once. It
    does NOT say the action may be applied again for the same gain -- and
    absence of refusal evidence is not permission. Measured: `force_latch`
    (lock_and_key) succeeded once, was never seen refused, was modelled as a
    repeatable `locks_open +1`, and BFS stacked it `depth` times; in reality
    it is ONE-SHOT and jams the rack forever. Same defect wearing two other
    costumes: `toggle_switch[i]` (the second toggle turns the switch back
    OFF) and `burn_catalyst` (the catalyst is spent; the second call is
    REFUSED).

    Repeatability is `observed` -- and this flag cleared -- only when the
    action succeeded at least TWICE from DIFFERENT pre-states with the SAME
    delta. Anything less stays unknown, and an unknown must not be modelled
    as a permission.
    """

    def describe(self) -> str:
        if self.context_dependent:
            return f"{self.dimension}: CONTEXT_DEPENDENT (not claimed as an unconditional effect)"
        suffix = " [ONCE_ONLY: repeatability unobserved]" if self.repeatability_unknown else ""
        if self.delta is not None:
            return f"{self.dimension}: {self.delta:+g} (relative){suffix}"
        if self.flip:
            return f"{self.dimension}: NOT (relative){suffix}"
        return f"{self.dimension}: ={self.absolute_value} (absolute){suffix}"


#: Cap on how many VARYING boolean dimensions a count-derivation may be
#: searched over. The search is a real subset enumeration (2**k), so it is
#: bounded rather than left to blow up on a wide observation. Above the cap
#: the derivation is simply not claimed -- absence of a search is not
#: evidence of absence of a derivation.
DERIVED_COUNT_MAX_BOOL_DIMS = 14


@dataclass(frozen=True)
class DerivedDimension:
    """A metric dimension that is not independently settable -- it is a
    FUNCTION of other dimensions, and must be RECOMPUTED after every effect
    rather than claimed as an effect.

    The measured defect: `switchboard`'s `required_on` is
    ``sum(switches[i] for i in required)``. Typed induction saw
    `toggle_switch[2]` move it 0 -> 1 and (before the self-inverse rule)
    claimed a monotonic `+1`, which BFS stacked for a free gain while the
    real switch flipped back off. The self-inverse rule correctly stopped
    that claim -- and then NOTHING claimed `required_on` at all, so the goal
    ``master and required_on == required_count`` became unreachable in the
    model and every `switchboard` seed ended NO_TYPED_VALID_PLAN for a
    representational reason rather than a real one.

    Neither claiming it nor abandoning it is right, because it is neither an
    effect nor unknowable: it is DERIVED. `kind="count_of"` records
    ``value == |{b in over : state[b] is True}|``, verified against EVERY
    observation -- a derivation supported by all but one observation is not
    claimed at all.
    """

    name: str
    kind: str  # currently only "count_of"
    over: frozenset[str]
    support: int = 0  # observations the derivation was checked against

    def recompute(self, state: dict[str, Any]) -> Optional[int]:
        if self.kind != "count_of":
            return None
        if any(d not in state for d in self.over):
            return None
        return sum(1 for d in self.over if state[d] is True)

    def describe(self) -> str:
        return (
            f"{self.name} = count_of({', '.join(sorted(self.over))}) "
            f"[verified on {self.support} observations]"
        )


@dataclass(frozen=True)
class RelationalPrecondition:
    """A precondition that no flat ``dimension -> constant`` map can express:
    applicability depends on the JOINT value of two dimensions.

    `lock_and_key`'s `open_lock` requires ``held_key == perm[locks_open]``
    for a permutation the environment never discloses. The flat induction
    learned `held_key == 0` (the one pair it happened to observe) and so
    claimed `open_lock` applicable at `locks_open == 1` while holding key 0
    -- a state reality refuses whenever ``perm[1] != 0``.

    What is honestly known is the set of (dim_a, dim_b) pairs under which the
    action was really OBSERVED to succeed. An unobserved pair is UNKNOWN: not
    permitted (the planner may not assume it works) and not forbidden (a
    later probe may observe it). `permits` therefore returns False for an
    unobserved pair, which can only ever make the model MORE restrictive --
    its failure mode is an honest NO_TYPED_VALID_PLAN, never a plan wrongly
    believed to run.
    """

    dim_a: str
    dim_b: str
    observed_pairs: frozenset[tuple[Any, Any]]

    def permits(self, state: dict[str, Any]) -> bool:
        if self.dim_a not in state or self.dim_b not in state:
            return False
        return (state[self.dim_a], state[self.dim_b]) in self.observed_pairs

    def describe(self) -> str:
        pairs = ", ".join(repr(p) for p in sorted(self.observed_pairs, key=repr))
        return f"({self.dim_a}, {self.dim_b}) in {{{pairs}}} (observed only)"


@dataclass(frozen=True)
class TypedAction:
    id: str
    effects: dict[str, TypedEffect] = field(default_factory=dict)
    preconditions: dict[str, Any] = field(default_factory=dict)  # non-metric dims that always held
    metric_lower_bounds: dict[str, float] = field(default_factory=dict)
    n_successes: int = 0
    n_refusals: int = 0
    repeatability_unknown: bool = True
    """True when ANY claimed effect of this action has unobserved
    repeatability. Such an action may be applied AT MOST ONCE in a plan --
    see `TypedDomain.simulate` and `search_plan_typed`."""
    n_distinct_success_states: int = 0
    relational_preconditions: tuple[RelationalPrecondition, ...] = ()
    """EVERY two-dimension hypothesis consistent with the observed
    successes and refusals, conjoined.

    Picking one candidate pair arbitrarily is unsound: for `lock_and_key`'s
    `open_lock` both `(held_key, locks_open)` and `(held_key, holding_key)`
    separate the observed successes from the observed refusals, yet they
    disagree about the future -- the second permits opening at
    `locks_open == 1` while holding key 0, which reality refuses whenever
    ``perm[1] != 0``. Conjoining every consistent hypothesis permits a state
    only when NO consistent hypothesis forbids it, so the model can never be
    less restrictive than the evidence supports."""
    unrepresentable: Optional[str] = None
    """Set when the FLAT precondition map provably cannot explain this
    action's observed refusals.

    `TypedAction.preconditions` is a flat ``dimension -> constant`` map. Some
    real preconditions are RELATIONAL -- `lock_and_key`'s `open_lock`
    requires ``held_key == permutation[locks_open]``, a lookup keyed on
    ANOTHER dimension, which no flat map can express at any value. The
    detector is a real falsification, not a guess: if some observed REFUSAL
    satisfies every induced precondition and lower bound, then the model
    claims that state applicable while reality refused it, so the model is
    wrong there and must say so.

    A plan containing such an action is rejected by `validate_plan_typed` and
    never generated by `search_plan_typed`. An honest NO_TYPED_VALID_PLAN
    beats a confidently wrong plan."""

    def applicable_in(self, state: dict[str, Any]) -> bool:
        for dim, required in self.preconditions.items():
            if state.get(dim) != required:
                return False
        for dim, bound in self.metric_lower_bounds.items():
            value = state.get(dim)
            if not isinstance(value, (int, float)) or value < bound:
                return False
        for rel in self.relational_preconditions:
            if not rel.permits(state):
                return False
        return True

    def context_dependent_dimensions(self) -> list[str]:
        return sorted(d for d, e in self.effects.items() if e.context_dependent)

    def apply(self, state: dict[str, Any]) -> dict[str, Any]:
        """Apply this action's learned typed effects to a real state dict."""
        new = dict(state)
        for dim, eff in self.effects.items():
            if eff.context_dependent:
                continue  # honestly unknown -- leave the dimension alone
            if eff.delta is not None:
                base = new.get(dim, 0)
                if isinstance(base, (int, float)):
                    result = base + eff.delta
                    new[dim] = int(result) if eff.kind is DimensionKind.INTEGER else result
            elif eff.flip:
                new[dim] = not bool(new.get(dim))
            else:
                new[dim] = eff.absolute_value
        return new


@dataclass(frozen=True)
class TypedDomain:
    dimensions: dict[str, StateDimension]
    actions: dict[str, TypedAction]
    derived: dict[str, DerivedDimension] = field(default_factory=dict)

    def apply_action(self, act: TypedAction, state: dict[str, Any]) -> dict[str, Any]:
        """Apply an action's effects, then RECOMPUTE every derived dimension.

        This is the single place a derived dimension acquires a value. No
        action may set one (`induce_typed_domain` strips such claims), and no
        derived dimension is left stale after an effect changes a dimension
        it counts over."""
        new = act.apply(state)
        for derived in self.derived.values():
            recomputed = derived.recompute(new)
            if recomputed is not None:
                new[derived.name] = recomputed
        return new

    def derived_dimensions(self) -> list[str]:
        """Dimensions no action claims unconditionally -- i.e. derived from
        others (e.g. `solved` == `counter == target`). Naming them is what
        stops a planner from believing one increment sets `solved`."""
        derived: set[str] = set(self.derived)
        for act in self.actions.values():
            derived.update(act.context_dependent_dimensions())
        return sorted(derived)

    def simulate(self, initial: dict[str, Any], plan: tuple[str, ...]) -> Optional[dict[str, Any]]:
        """Simulate, REFUSING to reuse an action whose repeatability is unknown.

        This is the enforcement point for the inverted default. A plan that
        stacks a once-observed action (`force_latch` x depth,
        `toggle_switch[index=2]` twice, `burn_catalyst` twice) is
        inapplicable under the typed model, so it can never be validated and
        committed. The failure mode is an honest NO_TYPED_VALID_PLAN, never a
        plan wrongly believed to run.
        """
        state = dict(initial)
        used: set[str] = set()
        for action_id in plan:
            act = self.actions.get(action_id)
            if act is None:
                return None
            if act.repeatability_unknown and action_id in used:
                return None
            if not act.applicable_in(state):
                return None
            used.add(action_id)
            state = self.apply_action(act, state)
        return state


def detect_derived_dimensions(
    observations: list[dict[str, Any]], dims: dict[str, StateDimension]
) -> dict[str, DerivedDimension]:
    """Find metric dimensions that are a COUNT over boolean dimensions.

    Evidence standard, deliberately strict in three ways:

    1. **Every observation must agree.** A subset consistent with all but one
       observation is not claimed at all. Absence of a counter-example inside
       a subset of the data is not proof of the derivation
       (`.claude/rules/absence-is-not-evidence.md`).
    2. **The derivation must be UNIQUE.** If two different boolean subsets
       both reproduce the dimension on every observation, the data does not
       determine which one is real, so neither is claimed and the dimension
       stays context-dependent.
    3. **The dimension must actually VARY.** A constant integer is
       reproduced by the empty subset (when it is 0) and carries no evidence
       of a counting relationship.

    Candidate booleans are restricted to those that VARY across the
    observations: a constant boolean contributes a constant offset that no
    exact count can distinguish, so including it could only ever manufacture
    an ambiguity, never resolve one.
    """
    if len(observations) < 3:
        return {}
    shared = set(observations[0])
    for obs in observations[1:]:
        shared &= set(obs)

    bool_dims = sorted(
        d
        for d in shared
        if dims.get(d) is not None
        and dims[d].kind is DimensionKind.BOOLEAN
        and len({bool(o[d]) for o in observations}) > 1
    )
    if not bool_dims or len(bool_dims) > DERIVED_COUNT_MAX_BOOL_DIMS:
        return {}

    metric_dims = [
        d
        for d in sorted(shared)
        if dims.get(d) is not None
        and dims[d].is_metric()
        and all(isinstance(o[d], int) and not isinstance(o[d], bool) for o in observations)
        and len({o[d] for o in observations}) > 1
    ]

    found: dict[str, DerivedDimension] = {}
    for metric in metric_dims:
        candidates: list[frozenset[str]] = []
        pool = [b for b in bool_dims if b != metric]
        for size in range(1, len(pool) + 1):
            for subset in combinations(pool, size):
                if all(
                    obs[metric] == sum(1 for b in subset if obs[b] is True)
                    for obs in observations
                ):
                    candidates.append(frozenset(subset))
            if len(candidates) > 1:
                break  # already ambiguous; no need to enumerate further
        if len(candidates) == 1:
            found[metric] = DerivedDimension(
                name=metric,
                kind="count_of",
                over=candidates[0],
                support=len(observations),
            )
    return found


def _flip_invariant_metrics(
    successes: list[dict], flip_dims: list[str], dims: dict[str, StateDimension]
) -> set[str]:
    """Metric dimensions PROVEN independent of a self-inverse boolean flip.

    The blanket self-inverse rule below demotes every metric dimension an
    action touches when that action is its own inverse on some boolean. That
    is right for a DERIVED dimension (`required_on` really does un-count when
    the switch flips back) and wrong for a genuine counter: `toggles` is
    incremented by `toggle_switch[i]` in BOTH directions, so toggling on and
    then off leaves the switch where it started and `toggles` at +2. Demoting
    it made `engage_master`'s real, refusal-evidenced ``toggles >= 2`` bound
    unsatisfiable in the model, and every `switchboard` seed stayed
    NO_TYPED_VALID_PLAN even after `required_on` was correctly derived.

    The exemption is a real falsification, not a relaxation: the SAME
    constant delta must have been observed in BOTH directions of the flip
    (pre=False and pre=True). A dimension that un-counts with the boolean
    yields ``+1`` one way and ``-1`` the other, so its delta set is not a
    singleton and it can never qualify -- measured, that is exactly what
    `required_on` does. Absence of one direction in the evidence is not
    proof of invariance, so both must actually be present.
    """
    out: set[str] = set()
    for dim_name, dim in dims.items():
        if not dim.is_metric():
            continue
        by_direction: dict[bool, set[float]] = {}
        for rec in successes:
            pre, post = rec["observed_pre"], rec["observed_post"]
            if dim_name not in pre or dim_name not in post:
                continue
            directions = {bool(pre[f]) for f in flip_dims if f in pre}
            if len(directions) != 1:
                continue  # ambiguous which way the flip went; no evidence
            by_direction.setdefault(next(iter(directions)), set()).add(
                post[dim_name] - pre[dim_name]
            )
        if set(by_direction) != {True, False}:
            continue  # only ever seen one way round -- UNKNOWN, not invariant
        deltas = {d for direction in by_direction.values() for d in direction}
        if len(deltas) == 1:
            out.add(dim_name)
    return out


def _independently_supported_preconditions(
    preconds: dict[str, Any], refusals: list[dict]
) -> dict[str, Any]:
    """Keep only precondition claims some refusal supports ON ITS OWN.

    "Constant across the successes AND some refusal differed here" is weaker
    evidence than it looks, because one refusal differs on several dimensions
    at once. Measured on `switchboard`: `engage_master` really requires only
    ``switch_0 and switch_1``, but the refusal
    ``switch_0=False, switch_1=False, switch_2=True`` differs on `switch_2`
    too, so `switch_2=False` and `switch_3=False` were claimed as
    preconditions as well. That contradicts the goal
    (``required_on == required_count`` needs both those switches ON) and made
    the seed unreachable for a purely representational reason.

    A dimension earns a claim only when some refusal differs on IT and agrees
    with the claimed value on every OTHER candidate dimension -- that refusal
    is then explained by that dimension alone. A dimension that could not
    have been the reason for any observed refusal is a dimension the evidence
    never tested, and claiming it asserts an unchecked factor
    (`.claude/rules/absence-is-not-evidence.md`).

    The pruning is guarded: the surviving map must still explain every
    refusal the full map explained. If it does not, the full map is kept and
    the model stays honestly over-restrictive rather than becoming permissive
    on unexamined evidence.
    """
    if not preconds:
        return preconds
    refusal_pres = [
        r["observed_pre"] for r in refusals if isinstance(r.get("observed_pre"), dict)
    ]

    def explains(mapping: dict[str, Any], pre: dict[str, Any]) -> bool:
        return any(d in pre and pre[d] != v for d, v in mapping.items())

    supported: set[str] = set()
    for pre in refusal_pres:
        differing = [d for d, v in preconds.items() if d in pre and pre[d] != v]
        if len(differing) == 1:
            supported.add(differing[0])

    pruned = {d: v for d, v in preconds.items() if d in supported}
    if not pruned:
        return preconds
    for pre in refusal_pres:
        if explains(preconds, pre) and not explains(pruned, pre):
            return preconds  # pruning would lose real refusal coverage
    return pruned


def _induce_relational_preconditions(
    successes: list[dict], refusals: list[dict], dims: dict[str, StateDimension]
) -> tuple[RelationalPrecondition, ...]:
    """Every two-dimension hypothesis consistent with the real evidence.

    A candidate pair ``(a, b)`` is admitted only when the set of
    ``(state[a], state[b])`` values observed on SUCCESS excludes every value
    observed on a REFUSAL -- i.e. the pair really does separate what worked
    from what was refused. Both dimensions must VARY across the evidence: a
    constant dimension separates nothing and would only pad the conjunction.

    All admitted candidates are returned and later conjoined, because they
    agree about the past and disagree about the future, and there is no
    evidence to choose between them.
    """
    if not successes or not refusals:
        return ()
    shared = set(successes[0]["observed_pre"])
    for rec in successes[1:] + refusals:
        pre = rec.get("observed_pre")
        if not isinstance(pre, dict):
            return ()
        shared &= set(pre)

    varying = sorted(
        d
        for d in shared
        if len({repr(r["observed_pre"][d]) for r in successes + refusals}) > 1
    )
    success_states = [r["observed_pre"] for r in successes]
    refusal_states = [r["observed_pre"] for r in refusals]

    out: list[RelationalPrecondition] = []
    for a, b in combinations(varying, 2):
        good = {(s[a], s[b]) for s in success_states}
        if any((r[a], r[b]) in good for r in refusal_states):
            continue  # this pair cannot tell the successes from the refusals
        out.append(RelationalPrecondition(a, b, frozenset(good)))
    return tuple(out)


def _dimensions_with_arithmetic_evidence(
    probe_records: list[dict], dims: dict[str, StateDimension]
) -> set[str]:
    """Real, affirmative evidence that a `CATEGORICAL_ID`-classified integer
    dimension is actually a genuine arithmetic quantity, not an identity or
    sentinel.

    `state_typing._is_categorical_id`'s static value-set heuristic (a small
    distinct integer set including a negative value) is a real false
    positive for any dimension that legitimately traverses negative
    territory via consistent arithmetic -- measured live on `cube_counter`'s
    `counter`: its own `decrement` action falsifies that discriminator's
    stated premise ("counter/raw/output/locks_open... never negative"), so
    `counter` was reclassified `CATEGORICAL_ID`, `is_metric()` returned
    `False`, and `increment`'s effect on it was recorded `CONTEXT_DEPENDENT`
    instead of `delta=+1` -- even though `reward` in the same trial, same
    action, correctly generalized to `delta=+0.166667`. The delta-induction
    machinery works; the dimension never reached it.

    This function supplies the behavioral discriminator the static
    value-set morphology alone cannot: affirmative transition evidence
    outweighs a negative-value coincidence. The bar is set precisely so it
    does not reopen the bug `_is_categorical_id` exists to fix
    (`lock_and_key`'s `held_key=-1` sentinel): a dimension qualifies only
    when some SINGLE action was observed succeeding from >= 2 DISTINCT
    pre-state values of that dimension, with the SAME delta each time.
    `held_key` never clears this bar for any of its actions --
    `pick_key[key=K]` is only ever observed from the one pre-state
    `held_key=-1` (the environment requires an empty hand to pick), and
    `drop_key`/`open_lock` set an ABSOLUTE value (`-1`) from varying
    pre-states, which is an inconsistent "delta" by construction, not a
    repeated quantity update. Repeating from one starting point, however
    many times, is not composability evidence -- the same discipline
    `repeatability_unknown`/`distinct_pre` already apply below in this
    module, applied one layer earlier, at dimension classification instead
    of at effect claiming.
    """
    by_action: dict[str, list[dict]] = {}
    for rec in probe_records:
        by_action.setdefault(rec["action"], []).append(rec)

    qualifies: set[str] = set()
    for records in by_action.values():
        successes = [
            r
            for r in records
            if r.get("applicable") and "observed_pre" in r and "observed_post" in r
        ]
        for dim_name, dim in dims.items():
            if dim.kind is not DimensionKind.CATEGORICAL_ID:
                continue
            pairs = [
                (r["observed_pre"][dim_name], r["observed_post"][dim_name])
                for r in successes
                if dim_name in r["observed_pre"]
                and dim_name in r["observed_post"]
                and isinstance(r["observed_pre"][dim_name], (int, float))
                and not isinstance(r["observed_pre"][dim_name], bool)
                and isinstance(r["observed_post"][dim_name], (int, float))
                and not isinstance(r["observed_post"][dim_name], bool)
            ]
            distinct_pre_values = {pre for pre, _ in pairs}
            if len(distinct_pre_values) < 2:
                continue  # one starting point repeated is not composability evidence
            deltas = {post - pre for pre, post in pairs}
            if len(deltas) == 1:
                qualifies.add(dim_name)
    return qualifies


def induce_typed_domain(probe_records: list[dict]) -> TypedDomain:
    """Induce a typed, delta-aware action model from real probe records.

    Each record must carry `observed_pre` and `observed_post` dicts of REAL
    typed values (not `"name=value"` strings) plus `action` and `applicable`.
    """
    observations = [r["observed_pre"] for r in probe_records if "observed_pre" in r]
    observations += [r["observed_post"] for r in probe_records if "observed_post" in r]
    dims = classify_observation(observations)

    # See `_dimensions_with_arithmetic_evidence`'s docstring: real transition
    # evidence outweighs `_is_categorical_id`'s value-set heuristic. Applied
    # here, before `derived_dims`/effect induction, so a reclassified
    # dimension is treated as metric everywhere downstream -- not patched
    # only at the one call site that first exposed the bug.
    arithmetic_evidence = _dimensions_with_arithmetic_evidence(probe_records, dims)
    if arithmetic_evidence:
        dims = {
            name: (
                StateDimension(
                    name=name, kind=DimensionKind.INTEGER, observed_values=dim.observed_values
                )
                if name in arithmetic_evidence
                else dim
            )
            for name, dim in dims.items()
        }

    derived_dims = detect_derived_dimensions(observations, dims)

    by_action: dict[str, list[dict]] = {}
    for rec in probe_records:
        by_action.setdefault(rec["action"], []).append(rec)

    actions: dict[str, TypedAction] = {}
    for action_id, records in by_action.items():
        successes = [r for r in records if r.get("applicable") and "observed_pre" in r and "observed_post" in r]
        refusals = [r for r in records if not r.get("applicable")]

        # Repeatability evidence. An effect induced from successes that all
        # started in the SAME pre-state carries no evidence the action may be
        # applied again -- one observation of "it worked here" is not a
        # licence to stack it. Distinct pre-states are counted on the real
        # observed values, so two probes from genuinely different world
        # states are what it takes to clear the flag.
        def _state_key(rec: dict) -> tuple:
            return tuple(sorted((k, repr(v)) for k, v in rec["observed_pre"].items()))

        distinct_pre = {_state_key(r) for r in successes}
        repeat_observed = len(distinct_pre) >= 2
        unknown = not repeat_observed

        effects: dict[str, TypedEffect] = {}
        touched = {k for r in successes for k in r["observed_post"] if r["observed_post"].get(k) != r["observed_pre"].get(k)}

        for dim_name in sorted(touched):
            dim = dims.get(dim_name)
            kind = dim.kind if dim else DimensionKind.UNKNOWN
            if kind in (DimensionKind.INTEGER, DimensionKind.CONTINUOUS):
                deltas = {
                    r["observed_post"][dim_name] - r["observed_pre"][dim_name]
                    for r in successes
                    if dim_name in r["observed_post"] and dim_name in r["observed_pre"]
                }
                if len(deltas) == 1:
                    effects[dim_name] = TypedEffect(dim_name, kind, delta=float(next(iter(deltas))), observations=len(successes), repeatability_unknown=unknown)
                else:
                    # Different deltas in different contexts -- a real
                    # context dependency (e.g. a rate that varies), not a
                    # constant effect. Do not claim it.
                    effects[dim_name] = TypedEffect(dim_name, kind, context_dependent=True, observations=len(successes))
            else:
                values = {r["observed_post"][dim_name] for r in successes if dim_name in r["observed_post"]}
                paired = [
                    r for r in successes
                    if dim_name in r["observed_post"] and dim_name in r["observed_pre"]
                ]
                if len(values) == 1:
                    effects[dim_name] = TypedEffect(dim_name, kind, absolute_value=next(iter(values)), observations=len(successes), repeatability_unknown=unknown)
                elif paired and all(
                    isinstance(r["observed_pre"][dim_name], bool)
                    and isinstance(r["observed_post"][dim_name], bool)
                    and r["observed_post"][dim_name] is (not r["observed_pre"][dim_name])
                    for r in paired
                ):
                    # A boolean TOGGLE is a *relative* effect, exactly as
                    # `counter += 1` is. Forcing it into an absolute value is
                    # the same category error that made add-list flattening
                    # unsound -- here it fails the other way: observing
                    # `switch_0` go False->True and True->False yields two
                    # values, so the dimension was written off as
                    # CONTEXT_DEPENDENT and the action modelled as a no-op.
                    # Measured: that made every `switchboard` goal
                    # unreachable (NO_TYPED_VALID_PLAN) the moment probing
                    # observed a toggle in both directions.
                    effects[dim_name] = TypedEffect(dim_name, kind, flip=True, observations=len(successes), repeatability_unknown=unknown)
                else:
                    # THE cube_counter case: `solved` was False after some
                    # increments and True after the last one. It is derived
                    # from counter==target, not set by increment. Refusing to
                    # claim it here is what prevents the unsound "one
                    # increment establishes solved=True" model.
                    effects[dim_name] = TypedEffect(dim_name, kind, context_dependent=True, observations=len(successes))

        # SELF-INVERSE / DERIVED-METRIC RULE.
        #
        # `toggle_switch[i]` was learned as BOTH `switch_i: NOT (relative)`
        # and `required_on: +1`. Those two claims are mutually inconsistent:
        # an action that is its own inverse cannot move a monotonic counter
        # in one direction forever, and `required_on` is not an independent
        # dimension at all -- it is a COUNT DERIVED from the booleans. The
        # planner exploited exactly that gap, stacking toggles for a free
        # `required_on` gain while the real switches flipped back off.
        #
        # A metric dimension touched by an action that is observed to be
        # self-inverse on a boolean is therefore recorded as
        # CONTEXT_DEPENDENT, not given a constant delta. It is derived, and
        # the honest statement is that we do not know its value in a
        # different context.
        # SCOPE. A metric dimension observed to take the SAME delta in BOTH
        # directions of the flip is proven independent of it and keeps its
        # delta -- see `_flip_invariant_metrics`. A derived one (`required_on`)
        # cannot qualify, because its deltas cancel.
        self_inverse_dims = sorted(d for d, e in effects.items() if e.flip)
        if self_inverse_dims:
            invariant = _flip_invariant_metrics(successes, self_inverse_dims, dims)
            for dim_name, eff in list(effects.items()):
                if eff.flip or eff.context_dependent or dim_name in invariant:
                    continue
                dim = dims.get(dim_name)
                if dim is not None and dim.is_metric():
                    effects[dim_name] = TypedEffect(
                        dim_name, eff.kind, context_dependent=True, observations=eff.observations
                    )

        # DERIVED DIMENSIONS ARE NEVER AN EFFECT. A dimension proven to be a
        # count over booleans is recomputed by `TypedDomain.apply_action`
        # from those booleans; letting an action also claim a delta on it
        # would double-count. This is the constructive half of the
        # self-inverse rule above: that rule refuses the unsound claim, this
        # one supplies the sound derivation in its place.
        for dim_name in list(effects):
            if dim_name in derived_dims:
                effects[dim_name] = TypedEffect(
                    dim_name,
                    effects[dim_name].kind,
                    context_dependent=True,
                    observations=effects[dim_name].observations,
                )

        # Preconditions: only non-metric dimensions whose value was constant
        # across every success (a metric dimension varying across successes
        # is evidence it is NOT a precondition, not evidence it is one).
        preconds: dict[str, Any] = {}
        if successes and refusals:
            candidate_dims = {k for k in successes[0]["observed_pre"]}
            for dim_name in candidate_dims:
                dim = dims.get(dim_name)
                if dim and dim.is_metric():
                    continue
                vals = {r["observed_pre"].get(dim_name) for r in successes}
                if len(vals) != 1:
                    continue
                value = next(iter(vals))
                # REFUSAL EVIDENCE REQUIRED. "Constant across the successes we
                # happened to observe" is not evidence of a precondition -- with
                # a handful of probes nearly every boolean dimension looks
                # constant. Claiming them all is the same unsound inference as
                # the add-list union this module was written to repair, and it
                # fails the opposite way: measured, every `switchboard` action
                # acquired `switch_3=False, switch_4=False, master=False`, so
                # toggling one switch made the others inapplicable and the goal
                # unreachable (NO_TYPED_VALID_PLAN) even though the effects had
                # been learned correctly.
                #
                # A precondition is claimed only when the action was really
                # REFUSED somewhere this dimension differed -- the same
                # evidence standard the metric lower bounds below use.
                if any(
                    isinstance(r.get("observed_pre"), dict)
                    and dim_name in r["observed_pre"]
                    and r["observed_pre"][dim_name] != value
                    for r in refusals
                ):
                    preconds[dim_name] = value

        # INDEPENDENT SUPPORT. One refusal differs on several dimensions at
        # once, so "some refusal differed here" over-claims. Keep only the
        # claims a refusal supports on its own -- see
        # `_independently_supported_preconditions`.
        preconds = _independently_supported_preconditions(preconds, refusals)

        # Metric preconditions, inferred ONLY from real refusal evidence.
        #
        # Metric dimensions are deliberately excluded from the equality
        # preconditions above (a value varying across successes is evidence
        # it is NOT a constant precondition). That left a hole: `assemble`
        # really requires `refined >= 1`, so a model with no metric
        # precondition believed it was always applicable and planned it from
        # an empty pool -- measured, the real step came back REFUSED.
        #
        # A bound is claimed only when refusals were actually observed BELOW
        # every success. This can only ever make the model MORE restrictive,
        # so its failure mode is an honest NO_TYPED_VALID_PLAN, never a plan
        # that is wrongly believed to run.
        lower_bounds: dict[str, float] = {}
        if successes and refusals:
            for dim_name, dim in dims.items():
                if not dim.is_metric():
                    continue
                success_values = [
                    r["observed_pre"][dim_name] for r in successes if dim_name in r["observed_pre"]
                ]
                refusal_values = [
                    r["observed_pre"][dim_name]
                    for r in refusals
                    if isinstance(r.get("observed_pre"), dict) and dim_name in r["observed_pre"]
                ]
                if not success_values or not refusal_values:
                    continue
                threshold = min(success_values)
                if all(v < threshold for v in refusal_values) and any(
                    v < threshold for v in refusal_values
                ):
                    lower_bounds[dim_name] = float(threshold)

        # RELATIONAL PRECONDITION DETECTION. Any refusal the flat model calls
        # applicable falsifies the flat model for this action. See
        # `TypedAction.unrepresentable`.
        unrepresentable: Optional[str] = None
        relational: tuple[RelationalPrecondition, ...] = ()
        flat_falsified = False
        for r in refusals:
            pre = r.get("observed_pre")
            if not isinstance(pre, dict):
                continue
            if all(pre.get(d) == v for d, v in preconds.items()) and all(
                isinstance(pre.get(d), (int, float)) and pre[d] >= b
                for d, b in lower_bounds.items()
            ):
                flat_falsified = True
                break

        if not successes:
            # An action never once observed succeeding is not a falsified
            # flat model -- there is no model to falsify. Reporting it as
            # RELATIONAL_PRECONDITION (which the falsification test did,
            # because every `all(...)` over an empty precondition map is
            # vacuously true) named the wrong defect: measured on
            # `switchboard`, `engage_master` was never seen applicable at a
            # 12-probe budget and was reported as relationally
            # unrepresentable when the real state of affairs was that
            # probing never established its precondition.
            unrepresentable = "UNREPRESENTABLE:NEVER_OBSERVED_APPLICABLE"
        elif flat_falsified:
            # The flat map is provably wrong here. Before declaring the
            # action unrepresentable, look for a RELATIONAL precondition
            # that really does separate the observed successes from the
            # observed refusals. Only when no pair of dimensions does is the
            # honest verdict UNREPRESENTABLE.
            relational = _induce_relational_preconditions(successes, refusals, dims)
            if not relational:
                unrepresentable = "UNREPRESENTABLE:RELATIONAL_PRECONDITION"

        actions[action_id] = TypedAction(
            id=action_id,
            effects=effects,
            preconditions=preconds,
            metric_lower_bounds=lower_bounds,
            relational_preconditions=relational,
            unrepresentable=unrepresentable,
            n_successes=len(successes),
            n_refusals=len(refusals),
            repeatability_unknown=any(
                e.repeatability_unknown for e in effects.values() if not e.context_dependent
            ),
            n_distinct_success_states=len(distinct_pre),
        )

    return TypedDomain(dimensions=dims, actions=actions, derived=derived_dims)


def validate_plan_typed(
    domain: TypedDomain, initial: dict[str, Any], plan: tuple[str, ...], goal_predicate
) -> tuple[bool, Optional[dict[str, Any]], str]:
    """Independently validate a plan against the TYPED model.

    `goal_predicate` is a callable over a state dict, so a goal that depends
    on a derived dimension (`counter == target`) is evaluated on real
    simulated values instead of on an add-list atom the model was never
    entitled to assert.
    """
    for action_id in plan:
        act = domain.actions.get(action_id)
        if act is not None and act.unrepresentable:
            return False, None, act.unrepresentable
    final = domain.simulate(initial, plan)
    if final is None:
        return False, None, "PLAN_INAPPLICABLE_UNDER_TYPED_MODEL"
    if not goal_predicate(final):
        return False, final, "GOAL_NOT_REACHED_UNDER_TYPED_MODEL"
    return True, final, "VALID"


def search_plan_typed(
    domain: TypedDomain, initial: dict[str, Any], goal_predicate, max_len: int = 12
) -> Optional[tuple[str, ...]]:
    """Breadth-first search over the typed model. Deliberately simple and
    model-faithful: its only job is to produce a candidate the typed
    validator will accept, so that a projection-level unsoundness cannot
    smuggle a bad plan past validation."""
    from collections import deque

    def key(s: dict[str, Any]) -> tuple:
        return tuple(sorted((k, v) for k, v in s.items()))

    start = dict(initial)
    if goal_predicate(start):
        return ()
    # An action whose repeatability was never observed may appear at most
    # ONCE, so the search state is (world state, set of such actions already
    # spent) -- deduplicating on the world state alone would wrongly prune
    # branches that differ only in what remains available.
    seen = {(key(start), frozenset())}
    queue = deque([(start, (), frozenset())])
    action_ids = sorted(domain.actions)
    while queue:
        state, path, spent = queue.popleft()
        if len(path) >= max_len:
            continue
        for action_id in action_ids:
            act = domain.actions[action_id]
            if act.unrepresentable:
                continue  # the model provably cannot express when it applies
            if act.repeatability_unknown and action_id in spent:
                continue
            if not act.applicable_in(state):
                continue
            nxt = domain.apply_action(act, state)
            new_spent = spent | {action_id} if act.repeatability_unknown else spent
            k = (key(nxt), new_spent)
            if k in seen:
                continue
            new_path = path + (action_id,)
            if goal_predicate(nxt):
                return new_path
            seen.add(k)
            queue.append((nxt, new_path, new_spent))
    return None
