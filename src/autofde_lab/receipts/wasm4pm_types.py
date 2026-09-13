"""Typed observation/receipt shapes reused from ``wasm4pm-compat-pydantic`` — a self-
contained pydantic package (see ``/Users/sac/wasm4pm-compat/python``), with zero
coupling to mfw or ``praxis-graphlaw`` and no native/Rust dependency, unlike the Rust
``wasm4pm-compat`` crate that ``mfw-meaning`` pulls in.

Corrected 2026-08-08: this file previously imported ``pydantic_integration.pydantic_models``
and ``pyproject.toml`` declared a dependency ``wasm4pm-compat-py`` sourced from
``/Users/sac/wasm4pm-compat/wasm4pm-compat-py``. Neither the module nor that path exists
on disk — the import raised ``ModuleNotFoundError`` and ``uv run`` failed repo-wide with
"Distribution not found". The real package is ``wasm4pm-compat-pydantic`` (module
``wasm4pm_compat_pydantic``) at ``/Users/sac/wasm4pm-compat/python``; all eleven names
re-exported below are produced there by ``generated.py`` (ggen-manufactured pydantic
projections of the canonical wasm4pm-compat Rust type graph).

This module is the seam: everything else in ``autofde_lab.receipts`` depends on this
file, not on ``wasm4pm_compat_pydantic`` directly, so swapping/vendoring the upstream
package later touches one file.

Not the default shape for a scikit-decide planning step: a real rollout step
(``planning_types.PlanStepOutcome``) has no ``id``/``type``/``time``/``relationships`` —
these OCEL/process-mining types are for an explicitly separate, optional downstream
adapter (mapping a planning trajectory into synthetic process-mining events), not for
validating raw solver output. See ``planning_types.py``'s module docstring for the
investigation that established this.
"""

from __future__ import annotations

from wasm4pm_compat_pydantic.generated import (  # noqa: F401 - re-export
    ConformanceResult,
    ConformanceVerdict,
    Evidence,
    OcelEvent,
    OcelEventAttribute,
    OcelLog,
    OcelObject,
    OcelObjectAttribute,
    OcelRelationship,
    OcelType,
    Receipt,
)

__all__ = [
    "ConformanceResult",
    "ConformanceVerdict",
    "Evidence",
    "OcelEvent",
    "OcelEventAttribute",
    "OcelLog",
    "OcelObject",
    "OcelObjectAttribute",
    "OcelRelationship",
    "OcelType",
    "Receipt",
]
