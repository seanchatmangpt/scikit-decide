"""Reduced from ``mfw-meaning``'s TTL admit-graph + SHACL validation pipeline to plain
dict shape-checking. Same *step* in the circulation (admit -> validate -> refuse-with-
reason), none of the RDF/oxigraph machinery — that's the ERRC grid's Reduce row.

Refusals raise autofde-lab's own ``standing.py`` exception hierarchy rather than a new
one: this is the one seam where this package and the rest of autofde-lab already share
a vocabulary, so it is reused, not reinvented.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from autofde_lab.standing import Blocked, Unsupported

from .core import Digest


@dataclass(frozen=True)
class AdmissionResult:
    admitted: bool
    observation_digest: str
    reason: str = ""


def admit(observation: dict, shape: dict) -> AdmissionResult:
    """Admit ``observation`` if it has every key ``shape`` requires, with a value of
    the declared type. ``shape`` is ``{key: type}}``, e.g. ``{"action": dict, "id": str}``.

    Raises ``Unsupported`` if ``shape`` itself is empty (nothing to validate against —
    an environment/config gate, not a data problem) and ``Blocked`` naming the first
    missing/mistyped key on refusal, mirroring mfw-meaning's "admit or refuse with a
    named reason" discipline.
    """
    if not shape:
        raise Unsupported("admission shape is empty; nothing to validate against")

    for key, expected_type in shape.items():
        if key not in observation:
            raise Blocked(f"observation missing required key {key!r}")
        if not isinstance(observation[key], expected_type):
            raise Blocked(
                f"observation[{key!r}] has type {type(observation[key]).__name__}, "
                f"expected {expected_type.__name__}"
            )

    return AdmissionResult(
        admitted=True, observation_digest=str(Digest.of_json(observation))
    )


def admit_typed(observation: dict, model: type[BaseModel]) -> AdmissionResult:
    """Admit ``observation`` against a real pydantic model shape — e.g. the
    process-mining types in ``wasm4pm_types`` (``OcelEvent``, ``Receipt``, ...) —
    instead of ``admit``'s plain ``{key: type}`` mapping. This is the richer-typed
    sibling of ``admit``: same admit-or-refuse-with-a-named-reason discipline, but
    validated by pydantic (nested models, unions, defaults) rather than a flat
    ``isinstance`` check.

    Raises ``Blocked`` naming every pydantic validation error on refusal, digesting
    the *model-normalized* observation (``model.model_dump()``) rather than the raw
    input, so two observations that mean the same thing after validation (e.g.
    differing key order, or a field pydantic coerced) produce the same digest.
    """
    try:
        validated = model.model_validate(observation)
    except ValidationError as exc:
        reasons = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in exc.errors()
        )
        raise Blocked(
            f"observation failed {model.__name__} validation: {reasons}"
        ) from exc

    return AdmissionResult(
        admitted=True, observation_digest=str(Digest.of_json(validated.model_dump()))
    )
