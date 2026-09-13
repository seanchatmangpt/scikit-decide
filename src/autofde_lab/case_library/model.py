# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Data model for the case-based-reasoning (CBR) case library.

Grounded in Aamodt & Plaza (1994), *Case-Based Reasoning: Foundational
Issues, Methodological Variations, and System Approaches* (AI Communications
7(1), pp. 39-59) -- the retrieve/reuse/revise/retain cycle this package
implements the *retrieve* and *retain* halves of. This module is a fresh,
standalone Python implementation scoped to this repo's own Kubernetes-fault
data shapes; it is not a port of, and does not call,
``wasm4pm-cognition``'s Rust ``cbr`` breed (registry status
``PARTIAL_ALIVE`` / ``DISPATCHABLE`` there is a fact about that crate, not
about this module).

A :class:`ProblemSignature` is a *normalized feature set*, never raw
``kubectl`` output: three explicit fields (namespace, the set of anomalous
object kinds, the set of "field=value" divergences from baseline) chosen
because they are (a) cheap to compute from a diagnosis pass that already ran,
(b) stable across trials of the same underlying fault class, and (c) directly
comparable via set similarity -- see :mod:`autofde_lab.case_library.similarity`.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ProblemSignature:
    """Normalized, comparable features of one diagnosed problem.

    ``namespace`` is a single scalar (a case concerns one namespace at a
    time in this repo's fault model). ``anomalous_kinds`` and
    ``diverged_fields`` are the two *feature sets* the similarity metric in
    :mod:`autofde_lab.case_library.similarity` compares via Jaccard
    similarity.

    :param namespace: Kubernetes namespace the fault was observed in.
    :param anomalous_kinds: Object kinds (``"Deployment"``, ``"CronJob"``,
        ``"Ingress"``, ...) that a detector flagged as anomalous.
    :param diverged_fields: Normalized ``"<kind>.<field>=<value>"`` strings
        naming exactly which field diverged from its expected/baseline
        value -- e.g. ``"Deployment.spec.template.spec.containers[0].readinessProbe.path=/wrong"``.
        Callers own the normalization; this dataclass only requires the
        result be a set of comparable strings.
    """

    namespace: str
    anomalous_kinds: frozenset[str] = field(default_factory=frozenset)
    diverged_fields: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        # Coerce iterables (list/tuple/set) passed by convenience into the
        # frozensets the dataclass is declared to hold, so callers building
        # a signature from `{"Deployment", "Service"}` or `["a", "b"]`
        # both work and both hash/compare identically afterward.
        object.__setattr__(self, "anomalous_kinds", frozenset(self.anomalous_kinds))
        object.__setattr__(self, "diverged_fields", frozenset(self.diverged_fields))

    def feature_set(self) -> frozenset[str]:
        """Return the full comparable feature set for similarity scoring.

        Namespace is included as a single ``"namespace=<value>"`` token so
        that two cases in different namespaces never reach a perfect 1.0
        Jaccard score purely by kind/field coincidence -- see
        :func:`autofde_lab.case_library.similarity.jaccard_similarity`.
        """
        tokens = {f"namespace={self.namespace}"}
        tokens |= {f"kind={kind}" for kind in self.anomalous_kinds}
        tokens |= {f"field={diverged}" for diverged in self.diverged_fields}
        return frozenset(tokens)


@dataclass(frozen=True)
class Case:
    """One solved (or attempted) trial: signature, diagnosis, fix, outcome.

    :param case_id: Caller-assigned stable identifier (e.g. an SREGym trial
        id). Primary key in the persistent store.
    :param signature: The normalized :class:`ProblemSignature` this case was
        retrieved/retained under.
    :param diagnosis: Free-text diagnosis, as produced by the deterministic
        planner or the DSPy fallback.
    :param mitigation_commands: The exact commands run to mitigate the fault,
        in the order they were run.
    :param outcome: ``True`` if the mitigation succeeded, ``False`` if it was
        tried and failed, ``None`` if the outcome is genuinely unknown (never
        coerce ``None`` into ``True``/``False`` -- see
        ``.claude/rules/absence-is-not-evidence.md``).
    :param confirmed_via: How ``outcome`` was reached, mirroring
        :mod:`autofde_lab.case_library.outcome_predicate`'s
        ``OutcomeVerdict``/``ConfirmedVia`` vocabulary: ``"structural_only"``
        or ``"structural_and_oracle"`` for a ``CONFIRMED`` (``outcome=True``)
        case, ``"disputed"`` for a ``DISPUTED`` case (structural re-check
        passed but a present oracle disagreed -- retained with
        ``outcome=None`` rather than coerced into ``True``/``False``, per
        ``.claude/rules/absence-is-not-evidence.md``), or ``"n/a"`` for a
        case that predates this field / carries no verdict provenance.
    """

    case_id: str
    signature: ProblemSignature
    diagnosis: str
    mitigation_commands: tuple[str, ...]
    outcome: bool | None = None
    confirmed_via: str = "n/a"
