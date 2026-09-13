# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Typed prediction-mismatch evidence: the model was wrong, and the process was not.

The finding this module exists to represent, measured on real archived
evidence and reproducible from disk:

    ``resource_flow`` seed ``3979297810`` committed the plan
    ``[mine, refine, assemble, burn_catalyst]``. All four steps executed
    ``ALIVE``. The receipt chain verified step to step. There are **zero**
    per-step divergences: the induced model's applicability and effect claims
    agreed with every act receipt. And the final state still came out:

        ``dead_end``  predicted ``True``   observed ``False``
        ``solved``    predicted ``False``  observed ``True``

The process conformed and the model was still wrong about the world. Those
are three separate claims and this module refuses to let them collapse:

    process correctness != causal-model correctness != goal consequence

``crown_factor.CrownFactor`` made "the factor was never observed" impossible
to score as a pass. ``level4_evidence`` made "the process conformed"
impossible to read as "the goal was reached". This module makes **"the model
predicted correctly"** impossible to express as a boolean at all.

Consequences that are structural, not stylistic:

* **No boolean anywhere names the comparison.** No ``prediction_correct``,
  ``matched``, ``ok``, ``accurate``, ``agrees``. A comparison that collapses
  to one bit cannot distinguish "predicted ``False``, observed ``False``"
  from "the model carries no representation of this dimension at all" -- and
  the second is the finding, not the noise. ``reward`` is real in the
  observation of four archived trials and the induced model has no dimension
  for it; coerced to a bool that reads as a correct prediction of ``False``.
  :class:`UnmodeledDimension` is the type that refuses that coercion.
* **No ``__bool__``, on any type here.** ``if mismatch:`` must never compile
  to a verdict. Same law as ``CrownFactor``.
* **Every mismatch carries three identities, all mandatory**: which model
  predicted it, which durable OCEL observation contradicted it, and which
  committed plan the pair is anchored to. A mismatch that cannot say whose
  model and whose observation is an anecdote.
* **Absence is typed as absence.** :class:`UnmodeledDimension` has no
  ``predicted`` field to fill in, so there is nothing to coerce; its
  :attr:`~UnmodeledDimension.predicted` accessor is
  :data:`UNMODELED` -- a sentinel that is not ``None``, not ``False``, and
  raises on truth-testing.

See ``.claude/rules/absence-is-not-evidence.md``. This module reads real data
through :func:`dogfood.compare_discovered_model_vs_observed` and
:func:`dogfood.ingest_episode`; it re-implements neither.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Union

from autofde_lab.hub.domain.gym_procedure.dogfood import (
    EpisodeOcel,
    ModelObservationDivergence,
    Unknown,
    _read_commitment,
    compare_discovered_model_vs_observed,
    ingest_episode,
)


class MismatchConstructionError(TypeError):
    """Raised when typed mismatch evidence is asked to exist without the
    identities that make it evidence. A ``TypeError``: a mismatch built from
    a bare bool is a type error, not a value that happens to be wrong."""


# ── the sentinel that cannot be read as a prediction ──────────────────────


class _Unmodeled:
    """The value of a dimension the model carries no representation for.

    Not ``None`` (which reads as "absent value of a modelled dimension"),
    not ``False`` (which reads as a prediction that happens to be wrong),
    and deliberately unusable in a boolean context: ``bool(UNMODELED)``
    raises rather than answering. The whole defect this module targets is a
    missing representation quietly scoring as a prediction.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "UNMODELED"

    def __bool__(self) -> bool:
        raise MismatchConstructionError(
            "UNMODELED_IS_NOT_A_TRUTH_VALUE: this dimension has no representation in "
            "the model; it was not predicted False, it was not predicted at all"
        )


#: Singleton for "the model has no dimension for this at all".
UNMODELED = _Unmodeled()


# ── dimension identity ────────────────────────────────────────────────────


class DimensionKind(str, Enum):
    """What kind of quantity a state dimension is.

    Kept separate from the value so a mismatch on a ``BOOLEAN`` dimension
    (``dead_end``, ``solved``) is not silently comparable to one on a
    ``NUMERIC`` dimension (``reward``) -- the numeric case is where "close
    enough" reasoning would otherwise leak in.
    """

    BOOLEAN = "BOOLEAN"
    NUMERIC = "NUMERIC"
    SYMBOLIC = "SYMBOLIC"
    UNTYPED = "UNTYPED"

    @classmethod
    def of(cls, value: Any) -> "DimensionKind":
        if isinstance(value, bool):
            return cls.BOOLEAN
        if isinstance(value, (int, float)):
            return cls.NUMERIC
        if isinstance(value, str):
            return cls.SYMBOLIC
        return cls.UNTYPED


@dataclass(frozen=True)
class StateDimension:
    """One named axis of the world state, with its typed kind."""

    name: str
    kind: DimensionKind

    def __post_init__(self) -> None:
        if not self.name:
            raise MismatchConstructionError("STATE_DIMENSION_REQUIRES_NAME")
        if not isinstance(self.kind, DimensionKind):
            raise MismatchConstructionError(
                f"STATE_DIMENSION_REQUIRES_TYPED_KIND: {self.name!r} got "
                f"{type(self.kind).__name__}"
            )

    def describe(self) -> str:
        return f"{self.name}:{self.kind.value}"


# ── the three identities ──────────────────────────────────────────────────


@dataclass(frozen=True)
class ModelIdentity:
    """WHICH model made the prediction.

    ``digest`` is the ``powl:modelDigest`` the trial itself committed to, so
    a prediction cannot be attributed to a model reconstructed later under
    different assumptions. ``induced_from`` names the durable probe log the
    model was induced from, and ``n_probes`` how much observation it had --
    a model wrong after 3 probes and one wrong after 300 are different
    findings.
    """

    digest: str
    induced_from: str
    n_probes: int

    def __post_init__(self) -> None:
        if not self.digest:
            raise MismatchConstructionError("MODEL_IDENTITY_REQUIRES_DIGEST")
        if not self.induced_from:
            raise MismatchConstructionError("MODEL_IDENTITY_REQUIRES_INDUCTION_SOURCE")
        if self.n_probes <= 0:
            raise MismatchConstructionError(
                f"MODEL_IDENTITY_REQUIRES_OBSERVATION: n_probes={self.n_probes}; a model "
                f"induced from nothing did not predict, it guessed"
            )

    def describe(self) -> str:
        return f"model:{self.digest}(n_probes={self.n_probes})"


@dataclass(frozen=True)
class ObservationIdentity:
    """WHICH durable observation contradicted it.

    ``ocel_digest`` is :meth:`OcelLog.digest` over the trial's real
    ``episode.ocel.json``, so the contradicting observation is pinned to an
    exact durable document rather than to "what the runner said".
    """

    run_id: str
    ocel_path: str
    ocel_digest: str
    ledger_ref: str

    def __post_init__(self) -> None:
        for name in ("run_id", "ocel_path", "ocel_digest", "ledger_ref"):
            if not getattr(self, name):
                raise MismatchConstructionError(f"OBSERVATION_IDENTITY_REQUIRES:{name}")

    def describe(self) -> str:
        return f"observation:{self.run_id}@{self.ocel_digest[:16]}"


@dataclass(frozen=True)
class CommitmentIdentity:
    """WHICH plan the model and the observation are both anchored to.

    Without this a predicted state and an observed state are two unrelated
    dicts. With it they are the two ends of one committed execution.
    """

    plan: tuple[str, ...]
    plan_digest: str
    commitment_ref: str

    def __post_init__(self) -> None:
        if not self.plan:
            raise MismatchConstructionError(
                "COMMITMENT_IDENTITY_REQUIRES_PLAN: nothing was committed, so no "
                "prediction was ever held against an execution"
            )
        if not self.plan_digest:
            raise MismatchConstructionError("COMMITMENT_IDENTITY_REQUIRES_PLAN_DIGEST")
        if not self.commitment_ref:
            raise MismatchConstructionError("COMMITMENT_IDENTITY_REQUIRES_COMMITMENT_REF")

    def describe(self) -> str:
        return f"plan:{self.plan_digest}[{' -> '.join(self.plan)}]"


# ── predicted / observed states ───────────────────────────────────────────


@dataclass(frozen=True)
class PredictedState:
    """The final state the model said the committed plan would produce.

    Carries the model identity that produced it. ``dimensions()`` is the
    exact set the model has a representation for -- everything outside it is
    :class:`UnmodeledDimension` territory, never a defaulted value.
    """

    model: ModelIdentity
    values: dict[str, Any]
    modeled_dimensions: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.model, ModelIdentity):
            raise MismatchConstructionError(
                f"PREDICTED_STATE_REQUIRES_MODEL_IDENTITY: got {type(self.model).__name__}"
            )

    def models(self, name: str) -> bool:
        """Whether the model has ANY representation of this dimension. Note
        this asks about the model's vocabulary, not about a value."""
        return name in self.modeled_dimensions

    def predicted(self, name: str) -> Any:
        """The predicted value, or :data:`UNMODELED` -- never ``None`` as a
        stand-in for "the model does not know about this"."""
        if name not in self.modeled_dimensions:
            return UNMODELED
        return self.values.get(name)


@dataclass(frozen=True)
class ObservedState:
    """The final state the durable evidence actually recorded.

    Carries the observation identity, so an observed value can always be
    traced back to the exact OCEL document and ledger row that carried it.
    """

    observation: ObservationIdentity
    values: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.observation, ObservationIdentity):
            raise MismatchConstructionError(
                f"OBSERVED_STATE_REQUIRES_OBSERVATION_IDENTITY: got "
                f"{type(self.observation).__name__}"
            )

    def observed(self, name: str) -> Any:
        return self.values.get(name)


# ── the two findings ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class PredictionMismatch:
    """The model HAD a representation of this dimension and got it wrong.

    Both values are recorded verbatim and separately; there is no derived
    field summarising the pair. Constructing one with equal values is
    refused -- an agreement is not a mismatch, and a "mismatch" record whose
    two values agree is exactly the accounting slop that lets a scoreboard
    count agreements and disagreements in one column.
    """

    dimension: StateDimension
    predicted_value: Any
    observed_value: Any
    model: ModelIdentity
    observation: ObservationIdentity
    commitment: CommitmentIdentity

    def __post_init__(self) -> None:
        if not isinstance(self.dimension, StateDimension):
            raise MismatchConstructionError(
                f"MISMATCH_REQUIRES_STATE_DIMENSION: got {type(self.dimension).__name__}"
            )
        if isinstance(self.predicted_value, _Unmodeled):
            raise MismatchConstructionError(
                f"UNMODELED_IS_NOT_A_MISMATCH:{self.dimension.name}: the model carries no "
                f"representation of this dimension; that is UnmodeledDimension, and "
                f"recording it here would assert a prediction that was never made"
            )
        if self.predicted_value == self.observed_value:
            raise MismatchConstructionError(
                f"MISMATCH_REQUIRES_DISAGREEMENT:{self.dimension.name}: predicted and "
                f"observed values are equal ({self.predicted_value!r})"
            )
        for name, expected in (
            ("model", ModelIdentity),
            ("observation", ObservationIdentity),
            ("commitment", CommitmentIdentity),
        ):
            if not isinstance(getattr(self, name), expected):
                raise MismatchConstructionError(
                    f"MISMATCH_REQUIRES_{name.upper()}_IDENTITY: got "
                    f"{type(getattr(self, name)).__name__}"
                )

    def describe(self) -> str:
        return (
            f"MISMATCH {self.dimension.describe()}: predicted "
            f"{self.predicted_value!r} observed {self.observed_value!r} "
            f"[{self.model.describe()} | {self.observation.describe()} | "
            f"{self.commitment.describe()}]"
        )


@dataclass(frozen=True)
class UnmodeledDimension:
    """Real in the observation, ABSENT from the model. Never a wrong prediction.

    This type has **no** ``predicted_value`` field: there is no slot in which
    to record a value the model never had, so no coercion is available. The
    :attr:`predicted` accessor answers :data:`UNMODELED`, which raises on
    truth-testing, so ``reward`` cannot silently pass as a correct prediction
    of ``False``/``0``.

    Construction is refused if the model *does* carry the dimension -- that
    case is a :class:`PredictionMismatch` (or an agreement), and mislabelling
    it here would understate the model's error.
    """

    dimension: StateDimension
    observed_value: Any
    model: ModelIdentity
    observation: ObservationIdentity
    commitment: CommitmentIdentity
    modeled_dimensions: frozenset[str] = field(default_factory=frozenset)
    status: str = "UNMODELED"

    def __post_init__(self) -> None:
        if not isinstance(self.dimension, StateDimension):
            raise MismatchConstructionError(
                f"UNMODELED_REQUIRES_STATE_DIMENSION: got {type(self.dimension).__name__}"
            )
        if self.dimension.name in self.modeled_dimensions:
            raise MismatchConstructionError(
                f"DIMENSION_IS_MODELED:{self.dimension.name}: the model carries a "
                f"representation of this dimension, so its disagreement is a "
                f"PredictionMismatch, not an absent representation"
            )
        for name, expected in (
            ("model", ModelIdentity),
            ("observation", ObservationIdentity),
            ("commitment", CommitmentIdentity),
        ):
            if not isinstance(getattr(self, name), expected):
                raise MismatchConstructionError(
                    f"UNMODELED_REQUIRES_{name.upper()}_IDENTITY: got "
                    f"{type(getattr(self, name)).__name__}"
                )

    @property
    def predicted(self) -> _Unmodeled:
        """Always :data:`UNMODELED`. Not ``None``, not ``False``, and it
        raises rather than answering ``bool()``."""
        return UNMODELED

    def describe(self) -> str:
        return (
            f"UNMODELED {self.dimension.describe()}: observed "
            f"{self.observed_value!r}, model has NO representation "
            f"[{self.model.describe()} | {self.observation.describe()}]"
        )


#: Everything a single dimension's comparison can be. Callers
#: ``isinstance``/``match``; no member is truthy-testable into a verdict.
DimensionFinding = Union[PredictionMismatch, UnmodeledDimension]


# ── the episode-level record ──────────────────────────────────────────────


@dataclass(frozen=True)
class CausalModelError:
    """One episode's model error, held apart from its process conformance.

    ``per_step_divergences`` is carried verbatim precisely so the
    ``resource_flow 3979297810`` case reads correctly: it is **empty**, every
    step conformed, and :attr:`mismatches` is still non-empty. There is
    deliberately no field combining the two into a score, because that score
    is the thing that would erase the finding.
    """

    trial_dir: str
    provider: str
    model: ModelIdentity
    observation: ObservationIdentity
    commitment: CommitmentIdentity
    predicted_state: PredictedState
    observed_state: ObservedState
    mismatches: tuple[PredictionMismatch, ...]
    unmodeled: tuple[UnmodeledDimension, ...]
    per_step_divergences: tuple[tuple[str, ...], ...]

    @property
    def process_conformed(self) -> bool:
        """Whether every committed step agreed with its receipt. Named for
        the PROCESS only. It is not, and must never be read as, a statement
        about the model: for ``resource_flow 3979297810`` this is ``True``
        while :attr:`mismatches` carries two entries."""
        return not any(self.per_step_divergences)

    def findings(self) -> tuple[DimensionFinding, ...]:
        return tuple(self.mismatches) + tuple(self.unmodeled)

    def describe(self) -> list[str]:
        lines = [
            f"trial={self.trial_dir}",
            f"provider={self.provider}",
            f"{self.commitment.describe()}",
            f"{self.model.describe()}",
            f"{self.observation.describe()}",
            f"per_step_divergences={sum(len(d) for d in self.per_step_divergences)} "
            f"over {len(self.per_step_divergences)} committed steps",
        ]
        lines += [f.describe() for f in self.findings()]
        return lines


# ── construction from real archived artifacts ─────────────────────────────


def causal_model_error_from_trial(trial_dir: Path | str) -> Union[CausalModelError, Unknown]:
    """Build typed mismatch evidence from one real archived trial directory.

    Reads through :func:`dogfood.compare_discovered_model_vs_observed` (the
    measurement) and :func:`dogfood.ingest_episode` (the durable OCEL
    identity); neither is re-implemented here. Any absence propagates as the
    dogfood :class:`~dogfood.Unknown` it already is, rather than becoming an
    empty result that reads as "no mismatches".
    """
    trial = Path(trial_dir)
    divergence = compare_discovered_model_vs_observed(trial)
    if isinstance(divergence, Unknown):
        return divergence

    episode = ingest_episode(trial)
    if isinstance(episode, Unknown):
        return episode

    commitment_path = trial / "actuation" / "commitment.ttl"
    raw_commitment = _read_commitment(commitment_path)
    if raw_commitment is None or not raw_commitment.get("model_digest"):
        return Unknown(
            question="causal_model_error_from_trial",
            absent=(f"{commitment_path}::powl:modelDigest",),
            detail=(
                "no committed model digest: the prediction cannot be attributed to an "
                "exact model, so a mismatch here would be unattributed."
            ),
        )

    if divergence.observed_final_state is None:
        return Unknown(
            question="causal_model_error_from_trial",
            absent=divergence.unresolved,
            detail=(
                "observed final state absent on disk: nothing to hold the prediction "
                "against. Absent, not agreeing."
            ),
        )

    ledger_ref = next(
        (s for s in divergence.sources if s.endswith("crown_run.json")), episode.source
    )
    model = ModelIdentity(
        digest=raw_commitment["model_digest"],
        induced_from=str(trial / "typed_probe_log.json"),
        n_probes=divergence.n_probes,
    )
    observation = ObservationIdentity(
        run_id=episode.run_id,
        ocel_path=episode.source,
        ocel_digest=episode.digest,
        ledger_ref=ledger_ref,
    )
    commitment = CommitmentIdentity(
        plan=tuple(divergence.committed_plan),
        plan_digest=raw_commitment["plan_digest"] or "",
        commitment_ref=str(commitment_path),
    )

    predicted = divergence.predicted_final_state
    observed = divergence.observed_final_state
    # The model's vocabulary is exactly what it predicted a value for; the
    # dogfood measurement already separated the dimensions it had no
    # representation for into `unmodelled_dimensions`.
    modeled = frozenset(predicted) - frozenset(divergence.unmodelled_dimensions)

    predicted_state = PredictedState(
        model=model, values=dict(predicted), modeled_dimensions=modeled
    )
    observed_state = ObservedState(observation=observation, values=dict(observed))

    mismatches = tuple(
        PredictionMismatch(
            dimension=StateDimension(
                name=row["dimension"],
                kind=DimensionKind.of(
                    row["observed"] if row["observed"] is not None else row["predicted"]
                ),
            ),
            predicted_value=row["predicted"],
            observed_value=row["observed"],
            model=model,
            observation=observation,
            commitment=commitment,
        )
        for row in divergence.final_state_mismatches
    )

    unmodeled = tuple(
        UnmodeledDimension(
            dimension=StateDimension(name=name, kind=DimensionKind.of(observed.get(name))),
            observed_value=observed.get(name),
            model=model,
            observation=observation,
            commitment=commitment,
            modeled_dimensions=modeled,
        )
        for name in divergence.unmodelled_dimensions
    )

    return CausalModelError(
        trial_dir=str(trial),
        provider=divergence.provider or "UNRECORDED_PROVIDER",
        model=model,
        observation=observation,
        commitment=commitment,
        predicted_state=predicted_state,
        observed_state=observed_state,
        mismatches=mismatches,
        unmodeled=unmodeled,
        per_step_divergences=tuple(a.divergences for a in divergence.per_action),
    )
