"""Chicago-style tests for the case-library abstraction-on-write layer.

Real dataclasses, real string parsing/substitution, real assertions on final
state (returned strings, dataclass fields). No mocks, no stubs, no
interaction-based assertions -- see
`.claude/rules/testing-chicago-style.md`.
"""

from __future__ import annotations

import pytest

from autofde_lab.case_library.abstraction import (
    AbstractCase,
    MissingBindingError,
    abstract_raw_case,
    rebind_template,
    retrieve_and_rebind,
)


def test_abstract_raw_case_extracts_deployment_and_namespace_into_placeholders():
    raw_diagnosis = (
        "deployment/social-network-backend in namespace social-network has "
        "0 replicas ready; readiness probe failing."
    )
    raw_mitigation_commands = (
        "kubectl patch deployment social-network-backend -n social-network "
        "-p '{\"spec\":{\"template\":{\"spec\":{\"containers\":[{\"name\":"
        "\"backend\",\"readinessProbe\":{\"initialDelaySeconds\":30}}]}}}}'",
    )
    observed_symptoms = frozenset(
        {"deployment.replicas_ready=0", "probe.readiness=failing"}
    )

    case = abstract_raw_case(
        raw_diagnosis=raw_diagnosis,
        raw_mitigation_commands=raw_mitigation_commands,
        observed_symptoms=observed_symptoms,
        case_id="trial-001",
        outcome_confirmed=True,
    )

    assert case is not None
    assert isinstance(case, AbstractCase)
    assert case.confirmed_outcome is True
    assert case.source_case_ids == ("trial-001",)
    assert case.symptom_signature == observed_symptoms

    # No trace of the original concrete names anywhere in the template.
    assert "social-network-backend" not in case.diagnosis_template
    assert "social-network-backend" not in "\n".join(case.mitigation_template)
    assert "social-network" not in case.diagnosis_template.replace(
        "{{namespace}}", ""
    )

    # Placeholders present instead.
    assert "{{deployment}}" in case.diagnosis_template
    assert "{{namespace}}" in case.diagnosis_template
    assert "{{deployment}}" in case.mitigation_template[0]
    assert "{{namespace}}" in case.mitigation_template[0]

    assert case.placeholder_bindings_schema == {
        "namespace": "k8s_namespace",
        "deployment": "k8s_object_name",
    }


def test_abstract_raw_case_abstracts_space_separated_service_reference():
    """Regression: `_SERVICE_MARKERS` previously only matched slash-prefixed
    forms (`svc/`, `service/`), so a diagnosis phrased as `"service
    billing-api"` (no slash) leaked the concrete service name verbatim into
    the stored template -- pure memorization of that one app, not
    generalization. Confirmed defect this session; fixed by adding a
    space-separated marker alongside the slash-prefixed ones.
    """
    raw_diagnosis = (
        "service billing-api in namespace payments is not receiving traffic; "
        "endpoints list is empty."
    )
    raw_mitigation_commands = (
        "kubectl describe service billing-api -n payments",
    )
    observed_symptoms = frozenset({"service.endpoints=empty"})

    case = abstract_raw_case(
        raw_diagnosis=raw_diagnosis,
        raw_mitigation_commands=raw_mitigation_commands,
        observed_symptoms=observed_symptoms,
        case_id="trial-svc-001",
        outcome_confirmed=True,
    )

    assert case is not None

    # The concrete service name must not leak into the stored template.
    assert "billing-api" not in case.diagnosis_template
    assert "billing-api" not in "\n".join(case.mitigation_template)

    # Replaced with the service placeholder instead.
    assert "{{service}}" in case.diagnosis_template
    assert "{{service}}" in case.mitigation_template[0]
    assert case.placeholder_bindings_schema["service"] == "k8s_object_name"


def test_abstract_raw_case_returns_none_when_outcome_not_confirmed():
    case = abstract_raw_case(
        raw_diagnosis="deployment/foo in namespace bar is crashlooping",
        raw_mitigation_commands=("kubectl delete pod foo-abc -n bar",),
        observed_symptoms=frozenset({"pod.status=CrashLoopBackOff"}),
        case_id="trial-unconfirmed",
        outcome_confirmed=False,
    )
    assert case is None


def test_rebind_template_substitutes_new_bindings_for_a_different_app():
    template_case = AbstractCase(
        symptom_signature=frozenset({"deployment.replicas_ready=0"}),
        diagnosis_template=(
            "deployment/{{deployment}} in namespace {{namespace}} has 0 "
            "replicas ready."
        ),
        mitigation_template=(
            "kubectl rollout restart deployment/{{deployment}} -n {{namespace}}",
        ),
        placeholder_bindings_schema={
            "deployment": "k8s_object_name",
            "namespace": "k8s_namespace",
        },
        source_case_ids=("trial-001",),
        confirmed_outcome=True,
    )

    # A DIFFERENT deployment/namespace than the original case's trial.
    new_bindings = {"deployment": "payments-worker", "namespace": "payments"}

    diagnosis_text, mitigation_commands = rebind_template(template_case, new_bindings)

    assert diagnosis_text == (
        "deployment/payments-worker in namespace payments has 0 replicas ready."
    )
    assert mitigation_commands == (
        "kubectl rollout restart deployment/payments-worker -n payments",
    )
    # Proof of generalization: none of the new output mentions the original
    # trial's own app/namespace names.
    assert "social-network" not in diagnosis_text
    assert "social-network" not in mitigation_commands[0]


def test_rebind_template_raises_on_missing_required_placeholder():
    template_case = AbstractCase(
        symptom_signature=frozenset({"deployment.replicas_ready=0"}),
        diagnosis_template="deployment/{{deployment}} in namespace {{namespace}}",
        mitigation_template=("kubectl get deploy {{deployment}} -n {{namespace}}",),
        placeholder_bindings_schema={
            "deployment": "k8s_object_name",
            "namespace": "k8s_namespace",
        },
        source_case_ids=("trial-002",),
        confirmed_outcome=True,
    )

    with pytest.raises(MissingBindingError):
        rebind_template(template_case, {"deployment": "payments-worker"})


def _scheduling_case() -> AbstractCase:
    return AbstractCase(
        symptom_signature=frozenset(
            {"event.reason=FailedScheduling", "event.detail_class=untolerated_taint"}
        ),
        diagnosis_template=(
            "pod for deployment/{{deployment}} in namespace {{namespace}} cannot "
            "be scheduled: untolerated taint."
        ),
        mitigation_template=(
            "kubectl taint nodes --all node-role.kubernetes.io/control-plane- "
            "-n {{namespace}}",
        ),
        placeholder_bindings_schema={
            "deployment": "k8s_object_name",
            "namespace": "k8s_namespace",
        },
        source_case_ids=("trial-sched-1",),
        confirmed_outcome=True,
    )


def _crashloop_case() -> AbstractCase:
    return AbstractCase(
        symptom_signature=frozenset(
            {"pod.status=CrashLoopBackOff", "container.exit_code=1"}
        ),
        diagnosis_template=(
            "deployment/{{deployment}} in namespace {{namespace}} is "
            "crashlooping with exit code 1."
        ),
        mitigation_template=(
            "kubectl logs deployment/{{deployment}} -n {{namespace}} --previous",
        ),
        placeholder_bindings_schema={
            "deployment": "k8s_object_name",
            "namespace": "k8s_namespace",
        },
        source_case_ids=("trial-crash-1",),
        confirmed_outcome=True,
    )


def _readiness_case() -> AbstractCase:
    return AbstractCase(
        symptom_signature=frozenset(
            {"probe.readiness=failing", "deployment.replicas_ready=0"}
        ),
        diagnosis_template=(
            "deployment/{{deployment}} in namespace {{namespace}} has 0 "
            "replicas ready; readiness probe failing."
        ),
        mitigation_template=(
            "kubectl patch deployment {{deployment}} -n {{namespace}} "
            "--type=json -p '[{\"op\":\"replace\",\"path\":\"/spec/template/spec/"
            "containers/0/readinessProbe/initialDelaySeconds\",\"value\":30}]'",
        ),
        placeholder_bindings_schema={
            "deployment": "k8s_object_name",
            "namespace": "k8s_namespace",
        },
        source_case_ids=("trial-ready-1",),
        confirmed_outcome=True,
    )


def test_retrieve_and_rebind_matches_correct_case_above_threshold():
    stored_cases = [_scheduling_case(), _crashloop_case(), _readiness_case()]

    # New trial's real observed symptoms strongly overlap the readiness case
    # (2/2 tokens match exactly -> Jaccard 1.0) and share nothing with the
    # other two.
    new_symptom_signature = frozenset(
        {"probe.readiness=failing", "deployment.replicas_ready=0"}
    )
    new_bindings = {"deployment": "checkout-service", "namespace": "checkout"}

    result = retrieve_and_rebind(
        stored_cases, new_symptom_signature, new_bindings, min_overlap=0.6
    )

    assert result is not None
    matched_case, diagnosis_text, mitigation_commands = result

    assert matched_case is stored_cases[2]  # the readiness case
    assert "checkout-service" in diagnosis_text
    assert "checkout" in diagnosis_text
    assert "checkout-service" in mitigation_commands[0]
    # Rebound to the NEW app's real names, not the stored case's originals.
    assert "social-network" not in diagnosis_text


def test_retrieve_and_rebind_returns_none_when_nothing_clears_threshold():
    stored_cases = [_scheduling_case(), _crashloop_case(), _readiness_case()]

    # A genuinely novel symptom pattern sharing no tokens with any stored case.
    novel_symptom_signature = frozenset(
        {"pvc.status=Pending", "event.reason=FailedAttachVolume"}
    )
    new_bindings = {"deployment": "orders-db", "namespace": "orders"}

    result = retrieve_and_rebind(
        stored_cases, novel_symptom_signature, new_bindings, min_overlap=0.6
    )

    assert result is None
