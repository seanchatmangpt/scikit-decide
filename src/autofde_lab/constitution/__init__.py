"""Direct Python projection of the AutoFDE Lab semantic constitution.

Every sibling module in this package (``lab.py``, ``world.py``, ``planning.py``,
``process.py``, ``authority.py``, ``evidence.py``, ``standing.py``,
``interop.py``) is manufactured by ``ggen sync run`` from the matching
``ontology/*.ttl`` file added in PR #37 ("ontology: working-backwards Lab
constitution"). This ``__init__.py`` is hand-written and intentionally does
not re-export from the manufactured modules -- import from the specific
module you need (``from autofde_lab.constitution.standing import
StandingValue``), matching the precedent in
``wasm4pm_compat_pydantic`` (``generated.py`` is not re-exported from that
package's own ``__init__.py`` either).

Manufacture is provenance, not architecture (``ontology/manufacture.ttl``):
this package sits at an ordinary import path and is additive only. It is not
wired into any existing runtime code path -- no planner, no ``level4_crown``,
no gymact bridge imports anything here. The live Level4-crown standing types
(``FactorState``, ``CrownStanding`` in
``hub/domain/gym_procedure/crown_factor.py`` and
``level4_crown_runner.py``) are untouched and unrelated to this package.
"""
