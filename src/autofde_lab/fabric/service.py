# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Protocol-independent decision service shared by all fabric projections."""

from __future__ import annotations

import inspect
from contextlib import nullcontext
from typing import Any, Mapping

from autofde_lab.fabric.backend import DecisionBackend, ScikitDecideBackend
from autofde_lab.fabric.cache import SQLiteERRCCache
from autofde_lab.fabric.canonical import (
    implementation_identity,
    runtime_identity,
    sha256,
    to_jsonable,
)
from autofde_lab.fabric.models import (
    CacheStatus,
    DecisionCatalog,
    DecisionMatch,
    DecisionRefusal,
    DecisionRequest,
    DecisionResult,
    DecisionStanding,
    DecisionStep,
    RefusalCode,
)

# Persisted envelope identifier -- see autofde_lab.schema_ids for why this
# is a version bump and not an edit of the previous string.
from autofde_lab.schema_ids import (  # noqa: E402
    ACCEPTED_FABRIC_SCHEMAS,
    FABRIC_SCHEMA as _FABRIC_SCHEMA,
    LEGACY_FABRIC_SCHEMAS,
)
_CLAIM_CEILING = "REGISTERED_DOMAIN_SOLVER_MATCH_AND_BOUNDED_ROLLOUT_ONLY"
_DETERMINISTIC_REFUSALS = {
    RefusalCode.DOMAIN_UNKNOWN,
    RefusalCode.SOLVER_UNKNOWN,
    RefusalCode.INVALID_ARGUMENTS,
    RefusalCode.SOLVER_INCOMPATIBLE,
    RefusalCode.DOMAIN_CONSTRUCTION_FAILED,
    RefusalCode.SOLVER_CONSTRUCTION_FAILED,
}


def _symbol_name(value: Any) -> str:
    return str(getattr(value, "__name__", value))


def _termination(value: Any) -> bool:
    if isinstance(value, Mapping):
        flags = [bool(flag) for flag in value.values()]
        return bool(flags) and all(flags)
    return bool(value)


class DecisionFabric:
    """Match, solve, cache, receipt, and replay-address decision trajectories."""

    def __init__(
        self,
        backend: DecisionBackend | None = None,
        cache: SQLiteERRCCache | None = None,
    ) -> None:
        self.backend = backend or ScikitDecideBackend()
        self.cache = cache or SQLiteERRCCache()

    def catalog(self) -> DecisionCatalog:
        """Return the deterministic registry catalog."""
        return DecisionCatalog(
            domains=tuple(sorted(self.backend.list_domains())),
            solvers=tuple(sorted(self.backend.list_solvers())),
        )

    def match(
        self,
        domain: str,
        *,
        domain_arguments: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> DecisionMatch:
        """Instantiate a domain and return compatible registered solvers."""
        arguments = to_jsonable(domain_arguments or {})
        domain_type = self.backend.load_domain(domain)
        catalog = self.catalog()
        identity = {
            "schema": _FABRIC_SCHEMA,
            "operation": "match",
            "domain": domain,
            "domain_arguments": arguments,
            "runtime": runtime_identity(),
            "registry_sha256": sha256(catalog.as_dict()),
            "domain_implementation": implementation_identity(domain_type),
        }
        identity_sha = sha256(identity)
        result_key = f"match:{identity_sha}"
        refusal_key = f"refusal:{identity_sha}"

        if use_cache:
            cached = self.cache.get(result_key)
            if cached is not None:
                return DecisionMatch.from_dict(cached, cache_status=CacheStatus.HIT)
            cached_refusal = self.cache.get(refusal_key)
            if cached_refusal is not None:
                raise DecisionRefusal.from_dict(cached_refusal)

        try:
            domain_instance = self._construct_domain(
                domain,
                dict(domain_arguments or {}),
                domain_type=domain_type,
            )
            compatible = tuple(
                sorted(
                    _symbol_name(item)
                    for item in self.backend.match_solvers(domain_instance)
                )
            )
            result = DecisionMatch(
                domain=domain,
                domain_arguments=dict(arguments),
                compatible_solvers=compatible,
                cache_status=CacheStatus.MISS if use_cache else CacheStatus.BYPASS,
                identity_sha256=identity_sha,
            )
            if use_cache:
                self.cache.put(result_key, "match", result.as_dict())
            return result
        except DecisionRefusal as error:
            if use_cache and error.code in _DETERMINISTIC_REFUSALS:
                self.cache.put(
                    refusal_key,
                    "refusal",
                    error.as_dict(),
                    ttl_seconds=300,
                )
            raise

    def solve(self, request: DecisionRequest) -> DecisionResult:
        """Solve a registered domain and capture a bounded trajectory."""
        if request.max_steps < 1:
            raise DecisionRefusal(
                RefusalCode.INVALID_ARGUMENTS,
                "max_steps must be at least 1",
                details={"max_steps": request.max_steps},
            )

        cache_admitted = request.use_cache and request.has_exact_reuse_identity()
        match = self.match(
            request.domain,
            domain_arguments=request.domain_arguments,
            use_cache=request.use_cache,
        )
        selected_solver = request.solver
        if selected_solver is None:
            selected_solver = (
                match.compatible_solvers[0] if match.compatible_solvers else None
            )

        intent_identity = {
            "schema": _FABRIC_SCHEMA,
            "operation": "solve-intent",
            "request": to_jsonable(request.semantic_dict()),
            "selected_solver": selected_solver,
            "match_identity_sha256": match.identity_sha256,
            "runtime": runtime_identity(),
        }
        refusal_key = f"refusal:{sha256(intent_identity)}"
        if cache_admitted:
            cached_refusal = self.cache.get(refusal_key)
            if cached_refusal is not None:
                raise DecisionRefusal.from_dict(cached_refusal)

        try:
            if selected_solver is None:
                raise DecisionRefusal(
                    RefusalCode.SOLVER_INCOMPATIBLE,
                    f"no compatible solver registered for domain {request.domain}",
                    details={"domain": request.domain},
                )
            if selected_solver not in match.compatible_solvers:
                raise DecisionRefusal(
                    RefusalCode.SOLVER_INCOMPATIBLE,
                    f"solver {selected_solver} is not compatible with {request.domain}",
                    details={
                        "domain": request.domain,
                        "solver": selected_solver,
                        "compatible_solvers": list(match.compatible_solvers),
                    },
                )

            domain_type = self.backend.load_domain(request.domain)
            solver_type = self.backend.load_solver(selected_solver)
            input_subject = {
                **intent_identity,
                "operation": "solve",
                "domain_implementation": implementation_identity(domain_type),
                "solver_implementation": implementation_identity(solver_type),
            }
            input_sha = sha256(input_subject)
            result_key = f"solve:{input_sha}"
            refusal_key = f"refusal:{input_sha}"

            if cache_admitted:
                cached = self.cache.get(result_key)
                if cached is not None:
                    return DecisionResult.from_dict(
                        cached,
                        cache_status=CacheStatus.HIT,
                    )
                cached_refusal = self.cache.get(refusal_key)
                if cached_refusal is not None:
                    raise DecisionRefusal.from_dict(cached_refusal)

            domain_instance = self._construct_domain(
                request.domain,
                request.domain_arguments,
                domain_type=domain_type,
            )

            def domain_factory() -> Any:
                return domain_type(**request.domain_arguments)

            solver_instance = self._construct_solver(
                selected_solver,
                solver_type,
                domain_factory,
                request.solver_arguments,
            )
            context = (
                solver_instance
                if hasattr(solver_instance, "__enter__")
                else nullcontext(solver_instance)
            )
            with context as active_solver:
                active_solver.solve()
                initial = domain_instance.reset()
                observation = initial
                steps: list[DecisionStep] = []
                for index in range(request.max_steps):
                    action = active_solver.sample_action(observation)
                    outcome = domain_instance.step(action)
                    next_observation = getattr(outcome, "observation", outcome)
                    terminated = _termination(getattr(outcome, "termination", False))
                    steps.append(
                        DecisionStep(
                            index=index,
                            observation=to_jsonable(observation),
                            action=to_jsonable(action),
                            next_observation=to_jsonable(next_observation),
                            value=to_jsonable(getattr(outcome, "value", None)),
                            termination=terminated,
                            info=to_jsonable(getattr(outcome, "info", None)),
                        )
                    )
                    observation = next_observation
                    if terminated:
                        break

            step_tuple = tuple(steps)
            terminal = bool(step_tuple and step_tuple[-1].termination)
            trajectory_payload = [step.as_dict() for step in step_tuple]
            trajectory_sha = sha256(trajectory_payload)
            standing = DecisionStanding.SOLVED if terminal else DecisionStanding.BOUNDED
            receipt_subject = {
                "schema": _FABRIC_SCHEMA,
                "standing": standing.value,
                "input_sha256": input_sha,
                "trajectory_sha256": trajectory_sha,
                "solver": selected_solver,
                "claim_ceiling": _CLAIM_CEILING,
            }
            result = DecisionResult(
                schema=_FABRIC_SCHEMA,
                standing=standing,
                request=request,
                solver=selected_solver,
                initial_observation=to_jsonable(initial),
                steps=step_tuple,
                terminal=terminal,
                cache_status=(
                    CacheStatus.MISS if cache_admitted else CacheStatus.BYPASS
                ),
                input_sha256=input_sha,
                trajectory_sha256=trajectory_sha,
                receipt_sha256=sha256(receipt_subject),
                claim_ceiling=_CLAIM_CEILING,
            )
            if cache_admitted:
                self.cache.put(result_key, "solve", result.as_dict())
            return result
        except DecisionRefusal as error:
            if cache_admitted and error.code in _DETERMINISTIC_REFUSALS:
                self.cache.put(
                    refusal_key,
                    "refusal",
                    error.as_dict(),
                    ttl_seconds=300,
                )
            raise
        except Exception as error:
            raise DecisionRefusal(
                RefusalCode.SOLVE_FAILED,
                f"decision execution failed for {request.domain}",
                details={
                    "domain": request.domain,
                    "solver": request.solver,
                    "error": str(error),
                },
            ) from error

    def cache_stats(self) -> dict[str, Any]:
        return self.cache.stats()

    def cache_hotset(self) -> dict[str, Any]:
        return self.cache.hotset()

    def _construct_domain(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        domain_type: type[Any] | None = None,
    ) -> Any:
        resolved = domain_type or self.backend.load_domain(name)
        try:
            return resolved(**arguments)
        except DecisionRefusal:
            raise
        except Exception as error:
            raise DecisionRefusal(
                RefusalCode.DOMAIN_CONSTRUCTION_FAILED,
                f"failed to construct domain {name}",
                details={
                    "domain": name,
                    "arguments": to_jsonable(arguments),
                    "error": str(error),
                },
            ) from error

    def _construct_solver(
        self,
        name: str,
        solver_type: type[Any],
        domain_factory: Any,
        arguments: dict[str, Any],
    ) -> Any:
        try:
            signature = inspect.signature(solver_type)
        except (TypeError, ValueError):
            signature = None
        try:
            if signature is None:
                return solver_type(domain_factory=domain_factory, **arguments)

            parameters = signature.parameters
            accepts_kwargs = any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            )
            if "domain_factory" in parameters or accepts_kwargs:
                return solver_type(domain_factory=domain_factory, **arguments)
            if "domain" in parameters:
                return solver_type(domain=domain_factory(), **arguments)
            return solver_type(domain_factory=domain_factory, **arguments)
        except Exception as error:
            raise DecisionRefusal(
                RefusalCode.SOLVER_CONSTRUCTION_FAILED,
                f"failed to construct solver {name}",
                details={
                    "solver": name,
                    "arguments": to_jsonable(arguments),
                    "error": str(error),
                },
            ) from error
