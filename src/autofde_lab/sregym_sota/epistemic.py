from __future__ import annotations

from collections import defaultdict
from enum import StrEnum

from .models import EvidenceLinkProposal, HypothesisProposal, HypothesisRecord


class EpistemicRoute(StrEnum):
    DIAGNOSIS_READY = "DIAGNOSIS_READY"
    DISCRIMINATE = "DISCRIMINATE"
    REHYPOTHESIZE = "REHYPOTHESIZE"


def compute_hypothesis_records(
    hypotheses: list[HypothesisProposal],
    links: list[EvidenceLinkProposal],
    admitted_fact_ids: set[str],
) -> list[HypothesisRecord]:
    """Compute standing mechanically from admitted evidence relationships.

    The LM may *propose* an evidence link, but a proposal only affects standing
    when both referenced identities exist in the kernel's admitted state. An
    invented fact ID is therefore epistemically inert.

    SUPPORTED requires admitted support and no admitted refutation. REFUTED
    requires admitted refutation and no admitted support. Missing or conflicting
    evidence is UNKNOWN, so contradiction can never be silently crowned.
    """

    support: dict[str, set[str]] = defaultdict(set)
    refute: dict[str, set[str]] = defaultdict(set)
    known_hypotheses = {h.id for h in hypotheses}
    for link in links:
        if link.hypothesis_id not in known_hypotheses:
            continue
        if link.fact_id not in admitted_fact_ids:
            continue
        if link.relation == "SUPPORTS":
            support[link.hypothesis_id].add(link.fact_id)
        elif link.relation == "REFUTES":
            refute[link.hypothesis_id].add(link.fact_id)

    records: list[HypothesisRecord] = []
    for hypothesis in hypotheses:
        supporting = sorted(support[hypothesis.id])
        refuting = sorted(refute[hypothesis.id])
        if supporting and not refuting:
            state = "SUPPORTED"
        elif refuting and not supporting:
            state = "REFUTED"
        else:
            state = "UNKNOWN"
        records.append(
            HypothesisRecord(
                **hypothesis.model_dump(),
                state=state,
                supporting_fact_ids=supporting,
                refuting_fact_ids=refuting,
            )
        )
    return records


def discrimination_frontier(records: list[HypothesisRecord]) -> list[HypothesisRecord]:
    """Every survivor remains discriminable, including multiple SUPPORTED ones."""

    return [h for h in records if h.state in {"SUPPORTED", "UNKNOWN"}]


def route_epistemic_state(records: list[HypothesisRecord]) -> EpistemicRoute:
    supported = [h for h in records if h.state == "SUPPORTED"]
    unknown = [h for h in records if h.state == "UNKNOWN"]

    # DiagnosisReady iff |SUPPORTED| == 1 and |UNKNOWN| == 0.
    if len(supported) == 1 and not unknown:
        return EpistemicRoute.DIAGNOSIS_READY

    # Multiple supported competitors are overdetermined, not resolved.
    if supported or unknown:
        return EpistemicRoute.DISCRIMINATE

    # Every candidate was refuted: manufacture a new portfolio.
    return EpistemicRoute.REHYPOTHESIZE
