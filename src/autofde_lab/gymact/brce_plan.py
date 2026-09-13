"""AutoFDE SELECT/CONSTRUCT -> GymAct BRCE DO composition.

AutoFDE owns candidate-plan geometry. GymAct owns consequential execution.
This module projects a flat admitted plan into POWL2, converts that document
through AutoFDE's existing POWL bridge, and binds each structural fire to an
already-authorized :class:`gymact.brce.BrokerRequest`. It never constructs an
ExecutionGrant, infers a capability, or calls a provider/runtime ``act`` port.

For bounded autonomous testing, :class:`AdmittedActuationSession` accepts one
finite, caller-authorized request bundle and then drives the complete admitted
plan without per-step caller intervention. The whole bundle is mechanically
preflighted before the first DO so structural identity/scope defects cannot
produce an avoidable prefix consequence.

When a cached :class:`~autofde_lab.agent.continuous_planning.PlanArtifact` is
supplied, this boundary additionally proves that the artifact names the exact
projected POWL model and freshly admits it against the supplied planning
context before the first DO. Cache presence is therefore never execution
admission. The resulting plan identity is carried through GymAct's powerless
PreparedAction and its exclusive BRCE boundary into the verified receipt.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from gymact.action_contract import admit_execution
from gymact.brce import BRCEBroker, BrokerRequest
from gymact.crown_runtime import VerifiedTransition
from gymact.models import Standing

from autofde_lab.agent.continuous_planning import (
    PlanArtifact,
    PlanningContext,
    admit_plan,
)
from autofde_lab.fabric.powl import parse_powl_turtle, project_plan_to_powl
from autofde_lab.ocel.log import OcelLog
from autofde_lab.ocel.powl_replay import ActionBinding, replay_structural_fires
from autofde_lab.powl.algebra import Atom, PartialOrder, PowlNode
from autofde_lab.powl.identity import node_id
from autofde_lab.powl.turtle_bridge import powl_model_to_node

__all__ = [
    "AdmittedActuationSession",
    "AdmittedPowlExecution",
    "execute_plan_lines_via_gymact_brce",
]


@dataclass(frozen=True, slots=True)
class AdmittedPowlExecution:
    """The exact projected document, structural trace, and verified DO results."""

    powl_turtle: str
    ocel_log: OcelLog
    transitions: tuple[VerifiedTransition, ...]
    plan_binding_digests: tuple[str, ...] = ()

    @property
    def alive(self) -> bool:
        """True only when every consequential transition independently verifies."""
        return bool(self.transitions) and all(
            transition.standing is Standing.ALIVE
            and transition.verification is not None
            and transition.verification.passed
            and transition.receipt.verified is True
            for transition in self.transitions
        )


@dataclass(frozen=True, slots=True)
class AdmittedActuationSession:
    """One finite authority bundle that AutoFDE may execute autonomously.

    The caller remains responsible for manufacturing the prepared actions and
    identity-bound execution grants. After this session is created, AutoFDE
    needs no per-action callback: ``run`` preflights the complete bundle and
    drives every admitted consequence exclusively through ``BRCEBroker``.
    """

    broker: BRCEBroker
    request_binding: Mapping[str, BrokerRequest]
    scope_ref: str

    def __post_init__(self) -> None:
        if not self.scope_ref:
            raise ValueError("REFUSED:EMPTY_ACTUATION_SCOPE")
        if not self.request_binding:
            raise ValueError("REFUSED:EMPTY_ACTUATION_BUNDLE")

    def run(
        self,
        plan_lines: Sequence[str],
        *,
        base_iri: str,
        domain_path: str | None = None,
        problem_path: str | None = None,
        planner_run: str = "run-autofde-lab-autonomous-brce",
        domain_iri: str | None = None,
        plan_artifact: PlanArtifact | None = None,
        planning_context: PlanningContext | None = None,
    ) -> AdmittedPowlExecution:
        """Autonomously execute one admitted plan inside this exact scope."""
        return execute_plan_lines_via_gymact_brce(
            plan_lines,
            base_iri=base_iri,
            broker=self.broker,
            request_binding=self.request_binding,
            required_scope_ref=self.scope_ref,
            domain_path=domain_path,
            problem_path=problem_path,
            planner_run=planner_run,
            domain_iri=domain_iri,
            plan_artifact=plan_artifact,
            planning_context=planning_context,
        )


def _run_async(coro: Any) -> Any:
    """Drive one GymAct broker coroutine without borrowing ambient authority."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _flat_atoms(tree: PowlNode) -> tuple[Atom, ...]:
    """Return the exact flat atom set admitted by AutoFDE's Turtle bridge."""
    if isinstance(tree, Atom):
        return (tree,)
    if isinstance(tree, PartialOrder) and all(
        isinstance(child, Atom) for child in tree.children
    ):
        return tree.children  # type: ignore[return-value]
    raise ValueError(
        "REFUSED:UNSUPPORTED_POWL_EXECUTION_SHAPE: expected the flat Atom/PartialOrder "
        "shape produced by project_plan_to_powl"
    )


def _preflight_request_bundle(
    atoms: tuple[Atom, ...],
    request_binding: Mapping[str, BrokerRequest],
    *,
    required_scope_ref: str | None,
) -> None:
    """Admit the complete finite request bundle before any consequential DO."""
    action_refs: list[str] = []
    for atom in atoms:
        action_ref = atom.action
        if not isinstance(action_ref, str) or not action_ref:
            raise ValueError(f"REFUSED:MISSING_IMPLEMENTS_ACTION: label={atom.label!r}")
        action_refs.append(action_ref)

    expected_refs = set(action_refs)
    missing = sorted(expected_refs - set(request_binding))
    if missing:
        raise ValueError(f"REFUSED:UNBOUND_IMPLEMENTS_ACTION: action(s)={missing!r}")

    extra = sorted(set(request_binding) - expected_refs)
    if extra:
        raise ValueError(f"REFUSED:UNUSED_BROKER_REQUEST: action(s)={extra!r}")

    for action_ref in action_refs:
        request = request_binding[action_ref]
        identities = {
            request.action.semantic_id,
            request.prepared.action_ref,
            request.grant.action_ref,
        }
        if identities != {action_ref}:
            raise ValueError(
                "REFUSED:BROKER_REQUEST_ACTION_IDENTITY_DRIFT: "
                f"binding={action_ref!r} identities={sorted(identities)!r}"
            )
        if (
            required_scope_ref is not None
            and required_scope_ref not in request.grant.scope_refs
        ):
            raise PermissionError(
                "REFUSED:ACTUATION_SCOPE_MISMATCH: "
                f"action={action_ref!r} required_scope={required_scope_ref!r} "
                f"grant_scopes={sorted(request.grant.scope_refs)!r}"
            )

        admission = admit_execution(
            request.action,
            request.prepared,
            request.grant,
            current_revision=request.current_revision,
        )
        if not admission.admitted:
            raise PermissionError(
                "REFUSED:BRCE_PREFLIGHT: "
                f"action={action_ref!r} reason={admission.reason}"
            )


def _admit_cached_plan(
    tree: PowlNode,
    *,
    plan_artifact: PlanArtifact | None,
    planning_context: PlanningContext | None,
) -> None:
    """Prove cached-plan structure and applicability before any broker preflight."""
    if (plan_artifact is None) != (planning_context is None):
        raise ValueError(
            "REFUSED:INCOMPLETE_PLAN_ADMISSION: plan_artifact and planning_context "
            "must be supplied together"
        )
    if plan_artifact is None:
        return
    projected_sha256 = node_id(tree)
    if projected_sha256 != plan_artifact.model_sha256:
        raise ValueError(
            "REFUSED:PLAN_MODEL_IDENTITY_DRIFT: "
            f"projected={projected_sha256} cached={plan_artifact.model_sha256}"
        )
    assert planning_context is not None
    admission = admit_plan(plan_artifact, planning_context)
    if not admission.admitted:
        codes = ",".join(code.value for code in admission.codes)
        raise PermissionError(f"REFUSED:PLAN_APPLICABILITY:{codes}")


def _plan_step_identity(
    tree: PowlNode,
    *,
    plan_artifact: PlanArtifact,
    atom_index: int,
    atom: Atom,
) -> tuple[str, tuple[str, ...]]:
    """Return deterministic step identity and direct structural parent identities."""
    step_id = f"{plan_artifact.exact_key}:{atom_index}:{atom.label}"
    if not isinstance(tree, PartialOrder):
        return step_id, ()
    parent_ids = tuple(
        f"{plan_artifact.exact_key}:{edge.src}:{tree.children[edge.src].label}"
        for edge in sorted(tree.order)
        if edge.dst == atom_index and isinstance(tree.children[edge.src], Atom)
    )
    return step_id, parent_ids


def execute_plan_lines_via_gymact_brce(
    plan_lines: Sequence[str],
    *,
    base_iri: str,
    broker: BRCEBroker,
    request_binding: Mapping[str, BrokerRequest],
    required_scope_ref: str | None = None,
    domain_path: str | None = None,
    problem_path: str | None = None,
    planner_run: str = "run-autofde-lab-brce",
    domain_iri: str | None = None,
    plan_artifact: PlanArtifact | None = None,
    planning_context: PlanningContext | None = None,
) -> AdmittedPowlExecution:
    """Project POWL geometry and execute every fired action through GymAct BRCE.

    ``request_binding`` is keyed by the exact ``mfwp:implementsAction`` IRI
    emitted into the POWL document. Every request must already contain its
    ``PreparedAction`` and identity-bound ``ExecutionGrant``; this function
    is intentionally incapable of manufacturing either. The complete bundle
    is mechanically preflighted before structural replay begins.

    A cached ``plan_artifact`` is optional for legacy callers. If supplied,
    ``planning_context`` is mandatory: exact structural identity and fresh
    applicability admission are both proven before broker preflight and the
    plan digest is then carried through GymAct's exclusive BRCE DO path.
    """
    turtle = project_plan_to_powl(
        plan_lines,
        base_iri,
        domain_path=domain_path,
        problem_path=problem_path,
        planner_run=planner_run,
        domain_iri=domain_iri,
    )
    tree = powl_model_to_node(parse_powl_turtle(turtle))
    atoms = _flat_atoms(tree)

    labels = [atom.label for atom in atoms]
    if len(labels) != len(set(labels)):
        raise ValueError(
            "REFUSED:AMBIGUOUS_POWL_ACTION_LABEL: BRCE bindings require one unique label "
            "per structural activity in this flat execution adapter"
        )

    _admit_cached_plan(
        tree,
        plan_artifact=plan_artifact,
        planning_context=planning_context,
    )
    _preflight_request_bundle(
        atoms,
        request_binding,
        required_scope_ref=required_scope_ref,
    )

    transitions: list[VerifiedTransition] = []
    plan_binding_digests: list[str] = []
    action_bindings: dict[str, ActionBinding] = {}

    for atom_index, atom in enumerate(atoms):
        action_ref = atom.action
        assert isinstance(action_ref, str)
        request = request_binding[action_ref]

        def execute_bound(
            atom_attrs: dict[str, Any],
            *,
            expected_action: str = action_ref,
            bound_request: BrokerRequest = request,
            bound_atom: Atom = atom,
            bound_atom_index: int = atom_index,
        ) -> dict[str, Any]:
            if atom_attrs.get("action") != expected_action:
                raise ValueError(
                    "REFUSED:POWL_ACTION_IDENTITY_DRIFT: "
                    f"fired={atom_attrs.get('action')!r} expected={expected_action!r}"
                )
            if plan_artifact is None:
                transition = _run_async(broker.execute(bound_request))
            else:
                try:
                    from gymact.planning import (
                        PlanProvenance,
                        bind_plan,
                        execute_planned,
                    )
                except ImportError as exc:
                    raise RuntimeError(
                        "UNSUPPORTED:GYMACT_PLAN_PROVENANCE_API"
                    ) from exc
                step_id, parent_step_ids = _plan_step_identity(
                    tree,
                    plan_artifact=plan_artifact,
                    atom_index=bound_atom_index,
                    atom=bound_atom,
                )
                provenance = PlanProvenance(
                    plan_id=plan_artifact.exact_key,
                    plan_version=str(plan_artifact.version),
                    plan_step_id=step_id,
                    parent_step_ids=parent_step_ids,
                    expected_state_digest=None,
                    required_authority_classes=plan_artifact.required_authority_classes,
                )
                planned = bind_plan(bound_request, provenance)
                planned_transition = _run_async(execute_planned(broker, planned))
                transition = planned_transition.transition
                plan_binding_digests.append(planned_transition.binding.binding_digest)
            transitions.append(transition)
            return {
                "standing": transition.standing.value,
                "receipt_id": transition.receipt.receipt_id,
                "verified": transition.receipt.verified,
                "verification_passed": bool(
                    transition.verification is not None
                    and transition.verification.passed
                ),
            }

        action_bindings[atom.label] = execute_bound

    ocel_log = replay_structural_fires(tree, action_bindings=action_bindings)
    return AdmittedPowlExecution(
        powl_turtle=turtle,
        ocel_log=ocel_log,
        transitions=tuple(transitions),
        plan_binding_digests=tuple(plan_binding_digests),
    )
