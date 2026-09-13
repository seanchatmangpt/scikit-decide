from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import dspy

from autofde_lab.powl.runner import PowlV2Runner, RunnerConfig, RunStatus

from . import SIGNATURE_REVISION
from .epistemic import (
    EpistemicRoute,
    compute_hypothesis_records,
    discrimination_frontier,
    route_epistemic_state,
)
from .facts import FactStore
from .mcp import McpBroker
from .models import (
    DiagnosisCandidate,
    HypothesisProposal,
    HypothesisRecord,
    MitigationProcessProposal,
)
from .powl_process import (
    McpActivityDriver,
    ProcessAdmissionError,
    canonical_read_identity,
    compile_mitigation_process,
    compile_observation_process,
)
from .signatures import (
    ChallengeDiagnosis,
    CommitDiagnosis,
    ConstructDiscriminationProcess,
    ConstructMitigationProcesses,
    GenerateHypotheses,
    OrientIncident,
    RelateEvidence,
)


def _json(value: Any) -> str:
    if isinstance(value, list):
        payload = [v.model_dump() if hasattr(v, "model_dump") else v for v in value]
    elif hasattr(value, "model_dump"):
        payload = value.model_dump()
    else:
        payload = value
    return json.dumps(payload, sort_keys=True, default=str)


class SignatureProgram:
    """No optimizer or compiler: source signatures are the experimental variable."""

    def __init__(self) -> None:
        self.orient = dspy.Predict(OrientIncident)
        self.hypothesize = dspy.Predict(GenerateHypotheses)
        self.relate = dspy.Predict(RelateEvidence)
        self.discriminate = dspy.Predict(ConstructDiscriminationProcess)
        self.commit = dspy.Predict(CommitDiagnosis)
        self.challenge = dspy.Predict(ChallengeDiagnosis)
        self.mitigate = dspy.Predict(ConstructMitigationProcesses)


async def _wait_for_stage(target: set[str], *, timeout_s: int = 300) -> str:
    host = os.getenv("API_HOSTNAME", "localhost")
    port = os.getenv("API_PORT", "8000")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urlopen(f"http://{host}:{port}/status", timeout=5) as response:
                stage = json.loads(response.read().decode()).get("stage", "error")
        except Exception:
            stage = "error"
        if stage in target:
            return stage
        await asyncio.sleep(1)
    raise TimeoutError(f"benchmark stage did not enter {sorted(target)}")


def _history_entry(
    capability_id: str,
    arguments: dict[str, Any],
    *,
    phase: str,
    round_index: int | None = None,
    repeat_reason: str = "",
) -> dict[str, Any]:
    return {
        "identity": canonical_read_identity(capability_id, arguments),
        "capability_id": capability_id,
        "arguments": arguments,
        "phase": phase,
        "round": round_index,
        "repeat_reason": repeat_reason,
    }


async def _seed_observations(
    broker: McpBroker,
    facts: FactStore,
    capabilities,
    read_history: list[dict[str, Any]],
) -> None:
    available = {(c.surface, c.tool): c for c in capabilities}
    capability = available.get(("kubectl", "exec_kubectl_cmd_safely"))
    if capability is None:
        return
    for cmd in (
        "kubectl api-resources -o wide",
        "kubectl get events -A -o json",
        "kubectl get all -A -o json",
    ):
        arguments = {"cmd": cmd}
        raw = await broker.call("kubectl", capability.tool, arguments)
        identity = canonical_read_identity(capability.id, arguments)
        facts.ingest(identity, raw)
        read_history.append(_history_entry(capability.id, arguments, phase="seed"))


def _process_observations(
    evidence,
    store: FactStore,
    read_history: list[dict[str, Any]],
    *,
    round_index: int,
    repeat_reasons: dict[str, str],
) -> int:
    count = 0
    for record in evidence.activity_records:
        if not record.success:
            continue
        capability_id = str(record.metadata.get("capability_id", ""))
        arguments = dict(record.metadata.get("arguments", {}))
        observation = record.metadata.get("observation")
        if not capability_id or observation is None:
            continue
        identity = canonical_read_identity(capability_id, arguments)
        count += len(store.ingest(identity, str(observation)))
        read_history.append(
            _history_entry(
                capability_id,
                arguments,
                phase="discriminate",
                round_index=round_index,
                repeat_reason=repeat_reasons.get(record.label, ""),
            )
        )
    return count


def _activity_records(evidence) -> list[dict[str, Any]]:
    return [
        {
            "label": record.label,
            "path": list(record.path),
            "attempt": record.attempt,
            "success": record.success,
            "committed": record.committed,
            "metadata": dict(record.metadata),
            "error_type": record.error_type,
            "error_message": record.error_message,
        }
        for record in evidence.activity_records
    ]


def _mitigation_rank(process: MitigationProcessProposal) -> tuple:
    return (
        process.risk,
        sum(step.consequence == "DO" for step in process.steps),
        len(process.steps),
        process.id,
    )


def _diagnosis_identity_is_admitted(
    diagnosis: DiagnosisCandidate,
    records: list[HypothesisRecord],
    admitted_fact_ids: set[str],
) -> bool:
    if not diagnosis.root_causes:
        return False
    supported_ids = {record.id for record in records if record.state == "SUPPORTED"}
    if len(supported_ids) != 1:
        return False
    for root_cause in diagnosis.root_causes:
        if not root_cause.hypothesis_ids:
            return False
        if not set(root_cause.hypothesis_ids) <= supported_ids:
            return False
        if not root_cause.evidence_fact_ids:
            return False
        if not set(root_cause.evidence_fact_ids) <= admitted_fact_ids:
            return False
    return True


def _subject_metadata(model: str) -> dict[str, str]:
    return {
        "autofde_head": os.getenv("AUTOFDE_HEAD", os.getenv("GITHUB_SHA", "UNKNOWN")),
        "sregym_head": os.getenv("SREGYM_SHA", "UNKNOWN"),
        "problem_id": os.getenv("PROBLEM_ID", "UNKNOWN"),
        "model_id": model,
        "signature_revision": SIGNATURE_REVISION,
    }


def _epistemic_signature(
    records: list[HypothesisRecord],
) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((record.id, record.state) for record in records))


def _write_receipt(payload: dict[str, Any]) -> None:
    root = Path(os.getenv("AGENT_LOGS_DIR", "."))
    root.mkdir(parents=True, exist_ok=True)
    path = root / "autofde-sota-receipt.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


async def _refuse_diagnosis(
    broker: McpBroker,
    *,
    subject: dict[str, str],
    standing: str,
    facts: FactStore,
    trajectory: list[dict[str, Any]],
    detail: object | None = None,
) -> dict[str, Any]:
    result = {
        "subject": subject,
        "signature_revision": SIGNATURE_REVISION,
        "standing": standing,
        "facts": len(facts.facts),
        "trajectory": trajectory,
        "detail": detail,
    }
    _write_receipt(result)
    await broker.call("submit", "submit", {"ans": standing})
    return result


async def run() -> dict[str, Any]:
    model = os.getenv(
        "AGENT_MODEL_ID", os.getenv("MODEL_ID", "groq/openai/gpt-oss-120b")
    )
    key = os.getenv("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is required")
    dspy.configure(lm=dspy.LM(model, api_key=key, max_tokens=8000, cache=False))

    subject = _subject_metadata(model)
    broker = McpBroker()
    capabilities = await broker.discover()
    store = FactStore()
    read_history: list[dict[str, Any]] = []
    await _seed_observations(broker, store, capabilities, read_history)

    program = SignatureProgram()
    goal = (
        "restore the benchmarked system to verified healthy operation by "
        "identifying and repairing the causal mechanism"
    )
    orientation = program.orient(
        goal=goal,
        facts_json=_json(store.facts),
        capabilities_json=_json(capabilities),
    ).orientation

    hypotheses: list[HypothesisProposal] = []
    retired_portfolios: list[dict[str, Any]] = []
    records: list[HypothesisRecord] = []
    trajectory: list[dict[str, Any]] = [
        {
            "stage": "orient",
            "orientation": orientation.model_dump(),
            "capability_ids": [capability.id for capability in capabilities],
            "seed_read_history": read_history,
        }
    ]
    max_rounds = int(os.getenv("AUTOFDE_MAX_DISCRIMINATION_ROUNDS", "8"))
    max_process_attempts = int(os.getenv("AUTOFDE_MAX_PROCESS_CANDIDATE_ATTEMPTS", "3"))
    diagnosis: DiagnosisCandidate | None = None
    previous_signature: tuple[tuple[str, str], ...] | None = None

    for round_index in range(max_rounds):
        if not hypotheses:
            if retired_portfolios:
                orientation = program.orient(
                    goal=goal,
                    facts_json=_json(store.facts),
                    capabilities_json=_json(capabilities),
                ).orientation
                trajectory.append(
                    {
                        "stage": "reorient",
                        "round": round_index,
                        "orientation": orientation.model_dump(),
                    }
                )
            predicted = program.hypothesize(
                goal=goal,
                orientation_json=_json(orientation),
                facts_json=_json(store.facts),
                prior_hypotheses_json=_json(retired_portfolios),
                max_hypotheses=6,
            )
            hypotheses = list(predicted.hypotheses)
            ids = [hypothesis.id for hypothesis in hypotheses]
            if not ids or len(ids) != len(set(ids)):
                return await _refuse_diagnosis(
                    broker,
                    subject=subject,
                    standing="REFUSED:HYPOTHESIS_IDENTITY_INVALID",
                    facts=store,
                    trajectory=trajectory,
                    detail={"ids": ids},
                )
            previous_signature = None
            trajectory.append(
                {
                    "stage": "hypothesize",
                    "round": round_index,
                    "hypotheses": [
                        hypothesis.model_dump() for hypothesis in hypotheses
                    ],
                    "retired_portfolio_count": len(retired_portfolios),
                }
            )

        related = program.relate(
            facts_json=_json(store.facts),
            hypotheses_json=_json(hypotheses),
        )
        links = list(related.links)
        admitted_fact_ids = {fact.id for fact in store.facts}
        known_hypothesis_ids = {hypothesis.id for hypothesis in hypotheses}
        rejected_links = sum(
            link.hypothesis_id not in known_hypothesis_ids
            or link.fact_id not in admitted_fact_ids
            for link in links
        )
        records = compute_hypothesis_records(hypotheses, links, admitted_fact_ids)
        route = route_epistemic_state(records)
        signature = _epistemic_signature(records)
        trajectory.append(
            {
                "stage": "epistemic",
                "round": round_index,
                "route": route.value,
                "states": {h.id: h.state for h in records},
                "hypotheses": [h.model_dump() for h in records],
                "fact_count": len(store.facts),
                "rejected_evidence_links": rejected_links,
                "epistemic_signature": list(signature),
            }
        )

        if route is EpistemicRoute.REHYPOTHESIZE:
            retired_portfolios.append(
                {
                    "reason": "ALL_REFUTED",
                    "round": round_index,
                    "hypotheses": [
                        hypothesis.model_dump() for hypothesis in hypotheses
                    ],
                }
            )
            hypotheses = []
            previous_signature = None
            continue

        if route is EpistemicRoute.DISCRIMINATE and previous_signature == signature:
            retired_portfolios.append(
                {
                    "reason": "EPISTEMIC_FRONTIER_UNCHANGED",
                    "round": round_index,
                    "hypotheses": [
                        hypothesis.model_dump() for hypothesis in hypotheses
                    ],
                    "states": {h.id: h.state for h in records},
                }
            )
            trajectory.append(
                {
                    "stage": "epistemic_stagnation",
                    "round": round_index,
                    "action": "retire_and_rehypothesize",
                    "signature": list(signature),
                }
            )
            hypotheses = []
            previous_signature = None
            continue
        previous_signature = signature

        if route is EpistemicRoute.DIAGNOSIS_READY:
            candidate = program.commit(
                facts_json=_json(store.facts),
                hypotheses_json=_json(records),
            ).diagnosis
            if not _diagnosis_identity_is_admitted(
                candidate, records, admitted_fact_ids
            ):
                return await _refuse_diagnosis(
                    broker,
                    subject=subject,
                    standing="REFUSED:DIAGNOSIS_IDENTITY_NOT_ADMITTED",
                    facts=store,
                    trajectory=trajectory,
                    detail=candidate.model_dump(),
                )
            challenged = program.challenge(
                diagnosis_json=_json(candidate),
                facts_json=_json(store.facts),
                hypotheses_json=_json(records),
            )
            if not challenged.obligations:
                diagnosis = candidate
                break
            obligations = list(challenged.obligations)
        else:
            obligations = list(related.obligations)

        frontier = discrimination_frontier(records)
        frontier_ids = {hypothesis.id for hypothesis in frontier}
        read_identities = {str(item["identity"]) for item in read_history}
        rejections: list[dict[str, Any]] = []
        evidence = None
        proposed = None
        for candidate_attempt in range(max_process_attempts):
            proposed = program.discriminate(
                facts_json=_json(store.facts),
                hypotheses_json=_json(frontier),
                obligations_json=_json(obligations),
                capabilities_json=_json(capabilities),
                read_history_json=_json(read_history),
                rejections_json=_json(rejections),
                max_steps=4,
            ).process
            try:
                model_powl = compile_observation_process(
                    proposed,
                    capabilities,
                    hypothesis_ids=frontier_ids,
                    prior_read_identities=read_identities,
                )
            except ProcessAdmissionError as exc:
                rejection = {
                    "candidate_attempt": candidate_attempt,
                    "kind": "PROCESS_ADMISSION",
                    "refusal": str(exc),
                    "process": proposed.model_dump(),
                }
                rejections.append(rejection)
                trajectory.append(
                    {
                        "stage": "discrimination_candidate_refused",
                        "round": round_index,
                        **rejection,
                    }
                )
                continue

            with PowlV2Runner(RunnerConfig(max_workers=4, max_attempts=1)) as runner:
                evidence = await asyncio.to_thread(
                    runner.run,
                    model_powl,
                    McpActivityDriver(broker, capabilities, allow_do=False),
                )
            if evidence.status is RunStatus.COMPLETED:
                break
            rejection = {
                "candidate_attempt": candidate_attempt,
                "kind": "PROCESS_EXECUTION",
                "status": evidence.status.value,
                "detail": evidence.detail,
                "activities": _activity_records(evidence),
                "process": proposed.model_dump(),
            }
            rejections.append(rejection)
            trajectory.append(
                {
                    "stage": "discrimination_candidate_refused",
                    "round": round_index,
                    **rejection,
                }
            )
            evidence = None

        if evidence is None or proposed is None:
            return await _refuse_diagnosis(
                broker,
                subject=subject,
                standing="REFUSED:DISCRIMINATION_PROCESS_NOT_ADMITTED",
                facts=store,
                trajectory=trajectory,
                detail={"rejections": rejections},
            )

        repeat_reasons = {step.id: step.repeat_reason for step in proposed.steps}
        new_facts = _process_observations(
            evidence,
            store,
            read_history,
            round_index=round_index,
            repeat_reasons=repeat_reasons,
        )
        trajectory.append(
            {
                "stage": "discriminate",
                "round": round_index,
                "new_facts": new_facts,
                "powl_sha256": evidence.model_sha256,
                "peak_concurrency": evidence.peak_concurrency,
                "process": proposed.model_dump(),
                "activities": _activity_records(evidence),
                "read_history_count": len(read_history),
            }
        )

    if diagnosis is None:
        return await _refuse_diagnosis(
            broker,
            subject=subject,
            standing="REFUSED:CAUSAL_CLOSURE_NOT_REACHED",
            facts=store,
            trajectory=trajectory,
            detail={
                "retired_portfolios": retired_portfolios,
                "read_history": read_history,
            },
        )

    await broker.call("submit", "submit", {"ans": diagnosis.explanation})
    post_diagnosis_stage = await _wait_for_stage({"mitigation", "done"})
    if post_diagnosis_stage == "done":
        result = {
            "subject": subject,
            "signature_revision": SIGNATURE_REVISION,
            "standing": "BENCHMARK_DONE_AFTER_DIAGNOSIS",
            "diagnosis": diagnosis.model_dump(),
            "facts": len(store.facts),
            "trajectory": trajectory,
        }
        _write_receipt(result)
        return result

    processes = list(
        program.mitigate(
            diagnosis_json=_json(diagnosis),
            facts_json=_json(store.facts),
            capabilities_json=_json(capabilities),
            max_processes=4,
        ).processes
    )
    ids = [process.id for process in processes]
    if not ids or len(ids) != len(set(ids)):
        mitigation_rejections = [
            {"refusal": "MITIGATION_PROCESS_IDENTITY_INVALID", "ids": ids}
        ]
        admitted_mitigations = []
    else:
        mitigation_rejections: list[dict[str, Any]] = []
        admitted_mitigations: list[tuple[MitigationProcessProposal, object]] = []
        for process in processes:
            try:
                powl = compile_mitigation_process(process, capabilities)
            except ProcessAdmissionError as exc:
                mitigation_rejections.append(
                    {
                        "process_id": process.id,
                        "refusal": str(exc),
                        "process": process.model_dump(),
                    }
                )
            else:
                admitted_mitigations.append((process, powl))

    trajectory.append(
        {
            "stage": "mitigation_admission",
            "admitted": [process.id for process, _ in admitted_mitigations],
            "rejections": mitigation_rejections,
        }
    )
    if not admitted_mitigations:
        result = {
            "subject": subject,
            "signature_revision": SIGNATURE_REVISION,
            "standing": "REFUSED:MITIGATION_PROCESS_NOT_ADMITTED",
            "diagnosis": diagnosis.model_dump(),
            "facts": len(store.facts),
            "trajectory": trajectory,
        }
        _write_receipt(result)
        await broker.call("submit", "submit", {"ans": ""})
        return result

    selected, mitigation_powl = min(
        admitted_mitigations, key=lambda pair: _mitigation_rank(pair[0])
    )
    with PowlV2Runner(RunnerConfig(max_workers=4, max_attempts=1)) as runner:
        mitigation_evidence = await asyncio.to_thread(
            runner.run,
            mitigation_powl,
            McpActivityDriver(broker, capabilities, allow_do=True),
        )
    if mitigation_evidence.status is not RunStatus.COMPLETED:
        result = {
            "subject": subject,
            "signature_revision": SIGNATURE_REVISION,
            "standing": "REFUSED:MITIGATION_PROCESS_EXECUTION_FAILED",
            "diagnosis": diagnosis.model_dump(),
            "mitigation_process": selected.model_dump(),
            "mitigation_powl_sha256": mitigation_evidence.model_sha256,
            "facts": len(store.facts),
            "trajectory": trajectory,
            "activities": _activity_records(mitigation_evidence),
        }
        _write_receipt(result)
        await broker.call("submit", "submit", {"ans": ""})
        return result

    await broker.call("submit", "submit", {"ans": ""})
    result = {
        "subject": subject,
        "signature_revision": SIGNATURE_REVISION,
        "standing": "CANDIDATE_EXECUTED",
        "diagnosis": diagnosis.model_dump(),
        "mitigation_process": selected.model_dump(),
        "mitigation_powl_sha256": mitigation_evidence.model_sha256,
        "facts": len(store.facts),
        "trajectory": trajectory,
        "mitigation_activities": _activity_records(mitigation_evidence),
    }
    _write_receipt(result)
    return result


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
