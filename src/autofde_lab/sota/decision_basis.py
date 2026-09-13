# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""The DecisionBasis vocabulary -- D = Model x Planner x ToolPolicy x RepairPolicy x
VerificationPolicy x Budget -- the missing capability this repo's own SOTA-attack work
identified: only ``Model`` was a swappable dimension in practice (proven this session by
pointing both `harbor`'s `terminus-2` agent and `sregym`'s `stratus` agent at a real local
model server); every other axis was a hardcoded fact about whichever vendor driver happened
to be invoked.

**Extraction discipline, not invention.** Every field on every dimension below must trace to
a real, currently-hardcoded fact about an already-executed (or already-configured, in-flight)
real invocation -- never a guessed or aspirational default. Concretely:

- Where the real vendor framework keeps its own config file as the living source of truth
  (`sregym`'s `mitigation_agent_config.yaml`), the corresponding `current_*_basis()` function
  in this package's sibling `materialize_*.py` modules READS that file at call time rather
  than hardcoding a duplicate copy of its values -- a second, independently-typed copy of the
  same fact is exactly the dual-bookkeeping this repo's own
  `.claude/rules/no-dual-bookkeeping.md` forbids, and it would drift the moment the vendor
  file changed underneath it.
- Where no explicit policy exists in the current code (e.g. a driver with no retry logic at
  all), the corresponding field says so plainly (`mode="none"` / `description="no retry logic
  found in source"`) rather than inventing a plausible-sounding one.

This module defines the frozen vocabulary only. Real, cited default points
(``current_sregym_stratus_basis()``, ``current_harbor_terminus2_basis()``) live in
``materialize_sregym.py`` / ``materialize_harbor.py`` next to the real invocation-builders
that consume them, so the "what does D actually equal today" fact and the "how do we run
that" fact never drift apart from each other -- one function produces both.

See ``docs/2026-08-08-decision-basis-lane-b.md`` for the extraction rationale and the full
per-dimension citation trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Model:
    """Which model answers each LLM call, and how to reach it.

    ``api_key_placeholder`` is deliberately never a real secret -- for the local server it is
    the literal ignored placeholder string ("local") this repo's own `dspy_policy.py` and this
    session's real `harbor`/`sregym` invocations already use; for a real paid provider it
    would be an *environment variable name* to read the credential from at invocation time,
    never the credential value itself, so a `DecisionBasis` instance can be logged, diffed, and
    persisted as evidence without ever carrying a secret.
    """

    id: str
    api_base: str | None = None
    api_key_placeholder: str | None = None
    description: str = ""


@dataclass(frozen=True)
class Planner:
    """Which real decision-loop implementation drives the agent -- a vendor driver identity,
    not a new decision-loop this repo invents. ``name`` is the exact, real, addressable
    identity (vendor:driver form) so a materializer can dispatch on it without guessing.
    """

    name: str
    description: str = ""


@dataclass(frozen=True)
class ToolPolicy:
    """The exact, real set of tools/actions currently exposed to the model each turn."""

    tool_names: tuple[str, ...]
    description: str = ""


@dataclass(frozen=True)
class RepairPolicy:
    """How a failed attempt is retried, if at all.

    ``mode`` is the real, named string the vendor framework itself uses where one exists
    (e.g. sregym's real `retry_mode` values: "none" / "naive" / "validate") -- never a
    renamed/reinterpreted label. Where a driver has no attempt-level repair concept at all,
    ``mode="none"`` and ``max_attempts=1`` with a `description` naming that absence plainly.
    """

    mode: str
    max_attempts: int | None = None
    description: str = ""


@dataclass(frozen=True)
class VerificationPolicy:
    """The FINAL, authoritative grading signal -- always the benchmark's own real, unmodified
    evaluator. This is the one dimension this repo's own standing law
    (`.claude/rules/absence-is-not-evidence.md`) treats as a hard constraint, not a free
    variable: a `DecisionBasis` search may vary which model/planner/tools/repair/budget
    produced an attempt, but the verdict on that attempt must always come from
    ``oracle_name`` unmodified, never a repair loop's own internal "weak oracle" (sregym's
    `AlertOracle`/`ClusterStateOracle` are real, but they inform ``RepairPolicy`` -- whether
    to keep retrying -- and must never be conflated with this dimension's real, final signal).
    """

    oracle_name: str
    description: str = ""


@dataclass(frozen=True)
class Budget:
    """The real, current resource ceilings bounding one attempt. Every field is optional
    because different vendor frameworks expose different real knobs; an absent field means
    "no such knob exists in source," never "unlimited" -- see each field's citation in the
    producing `current_*_basis()` function.
    """

    max_steps: int | None = None
    max_retry_attempts: int | None = None
    wall_clock_timeout_s: int | None = None
    llm_max_retries: int | None = None
    description: str = ""


@dataclass(frozen=True)
class DecisionBasis:
    """One point D = (M, P, T, R, V, B) in the architecture-search space.

    Frozen and fully data -- safe to log, diff, hash, and attach to a real evidence record
    (an OCEL episode, a receipt) exactly as `level4_witness.py` already does for the Level 4
    evidence kernel; a `DecisionBasis` instance is the causal-attribution record for "which
    architecture produced this score," matching the discipline
    `.claude/rules/level4-completion-law.md` already requires for actuation evidence.
    """

    model: Model
    planner: Planner
    tool_policy: ToolPolicy
    repair_policy: RepairPolicy
    verification_policy: VerificationPolicy
    budget: Budget
    extra: dict[str, str] = field(default_factory=dict)
