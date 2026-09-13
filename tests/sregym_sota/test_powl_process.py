import pytest

from autofde_lab.powl.algebra import PartialOrder
from autofde_lab.sregym_sota.models import (
    Capability,
    MitigationProcessProposal,
    MitigationStep,
    ObservationProcessProposal,
    ObservationStep,
    OutcomePrediction,
)
from autofde_lab.sregym_sota.powl_process import (
    McpActivityDriver,
    ProcessAdmissionError,
    canonical_read_identity,
    compile_mitigation_process,
    compile_observation_process,
    kubectl_command_is_read_only,
)

KUBECTL = Capability(
    id="mcp:kubectl:exec_kubectl_cmd_safely",
    surface="kubectl",
    tool="exec_kubectl_cmd_safely",
    description="execute one safe kubectl command",
    input_schema={
        "type": "object",
        "properties": {"cmd": {"type": "string"}},
        "required": ["cmd"],
    },
)
SUBMIT = Capability(
    id="mcp:submit:submit",
    surface="submit",
    tool="submit",
    input_schema={
        "type": "object",
        "properties": {"ans": {"type": "string"}},
        "required": ["ans"],
    },
)
CAPABILITIES = [KUBECTL, SUBMIT]


def _contrastive_step(
    step_id: str, cmd: str, *, after: list[str] | None = None
) -> ObservationStep:
    return ObservationStep(
        id=step_id,
        capability_id=KUBECTL.id,
        arguments={"cmd": cmd},
        after=after or [],
        discriminates=["H1", "H2"],
        outcomes=[
            OutcomePrediction(
                condition="relationship present", supports=["H1"], refutes=["H2"]
            ),
            OutcomePrediction(
                condition="relationship absent", supports=["H2"], refutes=["H1"]
            ),
        ],
    )


def test_discrimination_compiles_exact_capability_ids_to_real_powl() -> None:
    process = ObservationProcessProposal(
        steps=[
            _contrastive_step("a", "kubectl get services -A -o wide"),
            _contrastive_step("b", "kubectl get endpoints -A -o wide", after=["a"]),
        ]
    )
    model = compile_observation_process(
        process,
        CAPABILITIES,
        hypothesis_ids={"H1", "H2"},
    )
    assert isinstance(model, PartialOrder)
    assert len(model.children) == 2
    assert len(model.order) == 1
    assert model.children[0].bindings["capability_id"] == KUBECTL.id


def test_single_read_is_still_a_valid_powl_process() -> None:
    model = compile_observation_process(
        ObservationProcessProposal(
            steps=[_contrastive_step("a", "kubectl get pods -A")]
        ),
        CAPABILITIES,
        hypothesis_ids={"H1", "H2"},
    )
    assert isinstance(model, PartialOrder)
    assert len(model.children) == 2


def test_discrimination_requires_named_competitors_and_refuting_outcome() -> None:
    missing_targets = ObservationProcessProposal(
        steps=[
            ObservationStep(
                id="a",
                capability_id=KUBECTL.id,
                arguments={"cmd": "kubectl get pods -A"},
                outcomes=[OutcomePrediction(condition="x")],
            )
        ]
    )
    with pytest.raises(ProcessAdmissionError, match="DISCRIMINATION_TARGET_REQUIRED"):
        compile_observation_process(
            missing_targets, CAPABILITIES, hypothesis_ids={"H1", "H2"}
        )

    no_refute = ObservationProcessProposal(
        steps=[
            ObservationStep(
                id="a",
                capability_id=KUBECTL.id,
                arguments={"cmd": "kubectl get pods -A"},
                discriminates=["H1", "H2"],
                outcomes=[OutcomePrediction(condition="x", supports=["H1"])],
            )
        ]
    )
    with pytest.raises(ProcessAdmissionError, match="MUST_REFUTE_COMPETITOR"):
        compile_observation_process(
            no_refute, CAPABILITIES, hypothesis_ids={"H1", "H2"}
        )


def test_exact_repeat_read_requires_temporal_reason() -> None:
    step = _contrastive_step("a", "kubectl get services -A -o wide")
    identity = canonical_read_identity(step.capability_id, step.arguments)
    process = ObservationProcessProposal(steps=[step])
    with pytest.raises(
        ProcessAdmissionError, match="DUPLICATE_READ_WITHOUT_TEMPORAL_REASON"
    ):
        compile_observation_process(
            process,
            CAPABILITIES,
            hypothesis_ids={"H1", "H2"},
            prior_read_identities={identity},
        )

    step.repeat_reason = "compare after a newly observed state transition"
    assert isinstance(
        compile_observation_process(
            process,
            CAPABILITIES,
            hypothesis_ids={"H1", "H2"},
            prior_read_identities={identity},
        ),
        PartialOrder,
    )


def test_unknown_capability_is_refused_before_runner_dispatch() -> None:
    process = ObservationProcessProposal(
        steps=[
            ObservationStep(
                id="a",
                capability_id="mcp:kubectl:invented_tool",
                arguments={"cmd": "kubectl get pods -A"},
            )
        ]
    )
    with pytest.raises(ProcessAdmissionError, match="CAPABILITY_ID_NOT_DISCOVERED"):
        compile_observation_process(process, CAPABILITIES)


def test_capability_schema_refuses_missing_or_unknown_arguments() -> None:
    missing = ObservationProcessProposal(
        steps=[ObservationStep(id="a", capability_id=KUBECTL.id, arguments={})]
    )
    with pytest.raises(ProcessAdmissionError, match="CAPABILITY_ARGUMENT_REQUIRED"):
        compile_observation_process(missing, CAPABILITIES)

    unknown = ObservationProcessProposal(
        steps=[
            ObservationStep(
                id="a",
                capability_id=KUBECTL.id,
                arguments={"cmd": "kubectl get pods", "invented": True},
            )
        ]
    )
    with pytest.raises(ProcessAdmissionError, match="CAPABILITY_ARGUMENT_UNKNOWN"):
        compile_observation_process(unknown, CAPABILITIES)


def test_mitigation_requires_reversibility_and_verification() -> None:
    unsafe = MitigationProcessProposal(
        id="m1",
        reversible=False,
        steps=[
            MitigationStep(
                id="do",
                consequence="DO",
                capability_id=KUBECTL.id,
                arguments={"cmd": "kubectl patch service app -p '{}'"},
            ),
            MitigationStep(
                id="verify",
                consequence="VERIFY",
                capability_id=KUBECTL.id,
                arguments={"cmd": "kubectl get service app -o yaml"},
                after=["do"],
            ),
        ],
    )
    with pytest.raises(ProcessAdmissionError, match="NOT_REVERSIBLE"):
        compile_mitigation_process(unsafe, CAPABILITIES)


def test_reversible_mitigation_with_verify_compiles() -> None:
    process = MitigationProcessProposal(
        id="m1",
        reversible=True,
        risk=0.1,
        steps=[
            MitigationStep(
                id="do",
                consequence="DO",
                capability_id=KUBECTL.id,
                arguments={"cmd": "kubectl patch service app -p '{}'"},
            ),
            MitigationStep(
                id="verify",
                consequence="VERIFY",
                capability_id=KUBECTL.id,
                arguments={"cmd": "kubectl get service app -o yaml"},
                after=["do"],
            ),
        ],
    )
    assert isinstance(compile_mitigation_process(process, CAPABILITIES), PartialOrder)


@pytest.mark.parametrize(
    "command",
    [
        "kubectl get pods -A -o json",
        "kubectl logs pod-a -n ns",
        "kubectl auth can-i patch deployments -n ns",
        "kubectl rollout status deployment/app -n ns",
        "kubectl api-resources -o wide",
    ],
)
def test_kubectl_observation_classifier_admits_only_read_semantics(
    command: str,
) -> None:
    assert kubectl_command_is_read_only(command)


@pytest.mark.parametrize(
    "command",
    [
        "kubectl patch deployment app -p {}",
        "kubectl delete pod app-1",
        "kubectl annotate pod app-1 x=y",
        "kubectl exec app-1 -- rm -rf /tmp/x",
        "kubectl scale deployment app --replicas=0",
    ],
)
def test_kubectl_mutations_cannot_be_relabelled_as_reads(command: str) -> None:
    assert not kubectl_command_is_read_only(command)
    driver = McpActivityDriver(
        broker=object(), capabilities=CAPABILITIES, allow_do=True
    )
    assert (
        driver._authority_refusal(
            capability_id=KUBECTL.id,
            surface="kubectl",
            tool="exec_kubectl_cmd_safely",
            arguments={"cmd": command},
            consequence="READ",
        )
        == "MUTATION_MISLABELED_AS_OBSERVATION"
    )


def test_capability_binding_drift_is_refused() -> None:
    driver = McpActivityDriver(
        broker=object(), capabilities=CAPABILITIES, allow_do=True
    )
    assert (
        driver._authority_refusal(
            capability_id=KUBECTL.id,
            surface="prometheus",
            tool="get_metrics",
            arguments={"cmd": "kubectl get pods"},
            consequence="READ",
        )
        == "CAPABILITY_BINDING_DRIFT"
    )


def test_submit_mcp_is_reserved_from_llm_manufactured_processes() -> None:
    driver = McpActivityDriver(
        broker=object(), capabilities=CAPABILITIES, allow_do=True
    )
    assert (
        driver._authority_refusal(
            capability_id=SUBMIT.id,
            surface="submit",
            tool="submit",
            arguments={"ans": "anything"},
            consequence="DO",
        )
        == "CONTROL_SURFACE_RESERVED"
    )
