"""Abstraction-on-write layer for the SRE fault-diagnosis case library.

A naive case library stores raw solved-trial data verbatim -- e.g. a literal
``kubectl patch deployment social-network-backend -n social-network ...`` --
which only ever retrieves again for that *exact* deployment/namespace. That is
pure memorization, not generalization.

This module generalizes a successful trial into a reusable ``AbstractCase``
template *before* storage: concrete, environment-specific tokens (deployment
names, namespaces, ...) are replaced with typed ``{{placeholder}}`` tokens.
At retrieval time, the best-matching template (by symptom-signature Jaccard
similarity) is rebound to the *new* trial's real observed values -- an old
literal command is never replayed against a new target.

No LLM calls. Deterministic, pure-function string parsing and substitution
only, so every claim here is testable without a network or a mocked
collaborator (see ``.claude/rules/testing-chicago-style.md``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


class MissingBindingError(KeyError):
    """Raised by :func:`rebind_template` when a required placeholder has no binding."""


@dataclass(frozen=True)
class AbstractCase:
    """A generalized, reusable diagnosis/mitigation template.

    Attributes:
        symptom_signature: app-agnostic symptom tokens observed in the trial
            that produced this case, e.g. ``"deployment.replicas_ready=0"``,
            ``"event.reason=FailedScheduling"``. Never a raw app/namespace
            specific string.
        diagnosis_template: free text diagnosis with ``{{placeholder}}`` tokens
            in place of concrete environment-specific names.
        mitigation_template: ``kubectl`` command strings with
            ``{{placeholder}}`` tokens in place of concrete names.
        placeholder_bindings_schema: maps each placeholder name appearing in
            the templates to a semantic type, e.g. ``{"deployment":
            "k8s_object_name", "namespace": "k8s_namespace"}``.
        source_case_ids: provenance -- the raw trial case id(s) this template
            was generalized from. Never silently discarded.
        confirmed_outcome: must be ``True``. A template is only ever built
            from an observed real success.
    """

    symptom_signature: frozenset[str]
    diagnosis_template: str
    mitigation_template: tuple[str, ...]
    placeholder_bindings_schema: dict[str, str]
    source_case_ids: tuple[str, ...]
    confirmed_outcome: bool = field(default=True)

    def __post_init__(self) -> None:
        if not self.confirmed_outcome:
            raise ValueError(
                "AbstractCase.confirmed_outcome must be True: a template may "
                "only be constructed from an observed, confirmed success."
            )


# Patterns that precede a concrete k8s object name in typical kubectl
# invocations / diagnosis text. Each maps a leading marker (regex, matched
# literally then followed by the captured name) to the placeholder name and
# semantic type to assign it.
_DEPLOYMENT_MARKERS = (
    r"deployment/(?P<name>[a-zA-Z0-9][a-zA-Z0-9._-]*)",
    r"deploy/(?P<name>[a-zA-Z0-9][a-zA-Z0-9._-]*)",
    r"deployment\s+(?P<name>[a-zA-Z0-9][a-zA-Z0-9._-]*)",
)
_SERVICE_MARKERS = (
    r"svc/(?P<name>[a-zA-Z0-9][a-zA-Z0-9._-]*)",
    r"service/(?P<name>[a-zA-Z0-9][a-zA-Z0-9._-]*)",
    r"service\s+(?P<name>[a-zA-Z0-9][a-zA-Z0-9._-]*)",
)
_NAMESPACE_MARKERS = (
    r"-n\s+(?P<name>[a-zA-Z0-9][a-zA-Z0-9._-]*)",
    r"--namespace[= ](?P<name>[a-zA-Z0-9][a-zA-Z0-9._-]*)",
    r"namespace/(?P<name>[a-zA-Z0-9][a-zA-Z0-9._-]*)",
)


def _find_first(markers: tuple[str, ...], text: str) -> str | None:
    for pattern in markers:
        m = re.search(pattern, text)
        if m:
            return m.group("name")
    return None


def _replace_all(text: str, literal: str, placeholder: str) -> str:
    """Replace every whole-token occurrence of ``literal`` with ``{{placeholder}}``."""
    return re.sub(
        r"(?<![a-zA-Z0-9._-])" + re.escape(literal) + r"(?![a-zA-Z0-9._-])",
        "{{" + placeholder + "}}",
        text,
    )


def abstract_raw_case(
    raw_diagnosis: str,
    raw_mitigation_commands: tuple[str, ...],
    observed_symptoms: frozenset[str],
    case_id: str,
    outcome_confirmed: bool,
) -> AbstractCase | None:
    """Generalize a raw, confirmed-successful trial into a reusable ``AbstractCase``.

    Extracts concrete k8s object names/namespaces from ``raw_diagnosis`` and
    ``raw_mitigation_commands`` via deterministic regex parsing (no LLM call)
    and replaces every occurrence with a typed ``{{placeholder}}`` token,
    building ``placeholder_bindings_schema`` from what it found.

    Returns ``None`` -- never a fabricated template -- if
    ``outcome_confirmed`` is ``False``: a template may only ever be built from
    an observed real success.
    """
    if not outcome_confirmed:
        return None

    combined = raw_diagnosis + "\n" + "\n".join(raw_mitigation_commands)

    deployment_name = _find_first(_DEPLOYMENT_MARKERS, combined)
    service_name = _find_first(_SERVICE_MARKERS, combined)
    namespace_name = _find_first(_NAMESPACE_MARKERS, combined)

    bindings_schema: dict[str, str] = {}
    diagnosis_template = raw_diagnosis
    mitigation_template = raw_mitigation_commands

    # Namespace first: unlike deployment/service names it has no distinctive
    # marker prefix once found, so substituting it after a deployment name
    # that happens to equal the namespace string would double-replace. Doing
    # namespace first and deployment/service second, and skipping a name that
    # is identical to the namespace, avoids that collision.
    def sub_all(literal: str, placeholder: str) -> None:
        nonlocal diagnosis_template, mitigation_template
        diagnosis_template = _replace_all(diagnosis_template, literal, placeholder)
        mitigation_template = tuple(
            _replace_all(cmd, literal, placeholder) for cmd in mitigation_template
        )

    if namespace_name:
        sub_all(namespace_name, "namespace")
        bindings_schema["namespace"] = "k8s_namespace"

    if deployment_name and deployment_name != namespace_name:
        sub_all(deployment_name, "deployment")
        bindings_schema["deployment"] = "k8s_object_name"

    if service_name and service_name != namespace_name and service_name != deployment_name:
        sub_all(service_name, "service")
        bindings_schema["service"] = "k8s_object_name"

    return AbstractCase(
        symptom_signature=observed_symptoms,
        diagnosis_template=diagnosis_template,
        mitigation_template=mitigation_template,
        placeholder_bindings_schema=bindings_schema,
        source_case_ids=(case_id,),
        confirmed_outcome=True,
    )


_PLACEHOLDER_RE = re.compile(r"\{\{(?P<name>[a-zA-Z0-9_]+)\}\}")


def _required_placeholders(case: AbstractCase) -> set[str]:
    found: set[str] = set(_PLACEHOLDER_RE.findall(case.diagnosis_template))
    for cmd in case.mitigation_template:
        found.update(_PLACEHOLDER_RE.findall(cmd))
    return found


def rebind_template(
    case: AbstractCase, new_bindings: dict[str, str]
) -> tuple[str, tuple[str, ...]]:
    """Substitute ``new_bindings`` into ``case``'s templates for a NEW trial.

    Returns the concrete ``(diagnosis_text, mitigation_commands)`` for this
    trial. Raises :class:`MissingBindingError` -- never performs a silent
    partial substitution -- if ``new_bindings`` is missing a placeholder the
    template actually requires.
    """
    required = _required_placeholders(case)
    missing = required - new_bindings.keys()
    if missing:
        raise MissingBindingError(
            f"missing bindings for required placeholder(s): {sorted(missing)}"
        )

    def substitute(text: str) -> str:
        def repl(m: re.Match[str]) -> str:
            return new_bindings[m.group("name")]

        return _PLACEHOLDER_RE.sub(repl, text)

    diagnosis_text = substitute(case.diagnosis_template)
    mitigation_commands = tuple(substitute(cmd) for cmd in case.mitigation_template)
    return diagnosis_text, mitigation_commands


def _jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity: |A ∩ B| / |A ∪ B|. Both-empty sets score 0.0."""
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def retrieve_and_rebind(
    stored_cases: list[AbstractCase],
    new_symptom_signature: frozenset[str],
    new_bindings: dict[str, str],
    *,
    min_overlap: float = 0.6,
) -> tuple[AbstractCase, str, tuple[str, ...]] | None:
    """Find the best-matching stored case by symptom-signature Jaccard similarity
    and rebind it to the new trial's real observed values.

    Jaccard similarity between the new symptom signature ``S_new`` and a
    stored case's ``S_stored`` is ``|S_new ∩ S_stored| / |S_new ∪ S_stored|``.

    Returns ``(matched_case, diagnosis_text, mitigation_commands)`` for the
    highest-similarity stored case if its similarity is ``>= min_overlap``.
    Returns ``None`` -- never a low-confidence fabricated guess -- if no
    stored case clears the threshold.
    """
    if not stored_cases:
        return None

    best_case: AbstractCase | None = None
    best_score = -1.0
    for candidate in stored_cases:
        score = _jaccard(new_symptom_signature, candidate.symptom_signature)
        if score > best_score:
            best_score = score
            best_case = candidate

    if best_case is None or best_score < min_overlap:
        return None

    diagnosis_text, mitigation_commands = rebind_template(best_case, new_bindings)
    return best_case, diagnosis_text, mitigation_commands
