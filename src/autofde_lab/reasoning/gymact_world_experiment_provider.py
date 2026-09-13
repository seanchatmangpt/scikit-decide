# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""``GymActWorldExperimentProvider`` -- the real ``WorldExperimentProvider``
this repo's laboratory layer (section 10 of
``autofde_lab.reasoning.laboratory``) has, until now, only had a typed
refusal for: ``UnsupportedWorldExperimentProvider``'s own docstring says "no
`gymact` connector exists in this repo's laboratory layer" -- this module is
that connector.

Why a sibling module, not a change inside ``laboratory.py``
-------------------------------------------------------------
``laboratory.py``'s own module docstring is explicit: every
external-contract-dependent type there "is a real `typing.Protocol` this
repo defines the *shape* of, never an implementation of `wasm4pm`/`gymact`
themselves." Putting a concrete `gymact`-importing class inside that module
would falsify that sentence. Per
``.claude/rules/gym-actuation-boundary.md``'s own list of "real, current,
correctly-scoped entry points" -- ``gymact_diagnosis_driver.py`` "and its
siblings" living in this same ``reasoning/`` package -- this module is one
more such sibling: it imports ``gymact.*`` directly, `laboratory.py` still
imports nothing from `gymact` at all.

Why ``gymact.providers.MemoryProvider``, not a live external service
------------------------------------------------------------------------
`gymact`'s own ``providers.py`` module docstring names ``MemoryEnvironment``/
``MemoryProvider`` as "a deterministic executable reference world used for
contract validation" -- the real, standalone package's own designated
minimal integration point. It needs no live external server (no cnv-deploy
process, no sregym Kubernetes cluster) and no network call, so this
provider's Chicago-style test needs no ``pytest.mark.skipif`` for
reachability: the real collaborator it drives is always available in the
same Python process, the same way `autofde_lab.gymact.kernel.GymActKernel`
(this repo's other, pre-existing thin `gymact.runtime.GymAct` wrapper, used
for the fabric/CLI 12-operation surface) already defaults to it for exactly
this reason.

DFLSS/DMEDI curriculum plans (``docs/planning/dflss-dmedi-curriculum/``)
have no existing k8s-fault gym mapping the way sregym's SRE problems do.
Read directly this session (each vendored checkout's own real ``README.md``,
not assumed from its name), none of the 55 real vendored checkouts under
``vendor/gyms/`` -- including ``enterprisebench``, ``itbench``, and
``sre-bench``, the three named as candidates for
"enterprise-process/DFLSS-style tasks" -- models a DFSS tollgate review, a
DMEDI phase gate, or a curriculum-module completion as a scenario/fault:
``enterprisebench``'s own README describes a multi-domain (HR, IT, Sales,
Software Engineering, Business Operations) LLM-agent task sandbox, not a
quality-improvement-methodology curriculum; ``itbench``'s describes
enterprise-IT scenario suites (SRE, FinOps, CISO); ``sre-bench``'s describes
Kubernetes SRE tasks (incident response, infra changes, observability
triage) "inspired by SWE-bench." All three are closer in shape to
`gymact.gyms.sregym` (already wired via `gymact_diagnosis_driver.py`) than
to a DMEDI curriculum plan, and none is any closer a fit than `gymact`'s own
reference world. Per the vendor law itself (``vendor/gyms/`` is
reference-only; ``gymact`` is the only real actuation surface regardless of
which vendored gym's *domain* is closest) this would not change which
package this module imports even if one of them were a closer domain fit --
and none is. Wiring straight to `gymact`'s own real in-process reference
world is therefore the honest minimal choice, not a placeholder standing in
for a "better" gym that does not actually exist for this domain.

Authority: fail-closed by construction, never self-granted
----------------------------------------------------------
Per ``CLAUDE.md``'s law -- "It computes candidate plans. It does not
actuate... nothing here carries ambient authority to change the world" --
this provider constructs its own ``gymact.runtime.GymAct`` instance with
whatever ``AuthorityResolver`` its caller injects at construction time
(default ``None``, meaning `gymact`'s own real default,
``DenyAuthorityResolver`` -- fail-closed, per `gymact`'s own
``.claude/rules/actuation-authority.md``: "An authority_ref is not
permission... Required authority is fail-closed unless the injected
AuthorityResolver explicitly admits the exact operation"). Every
``ExperimentIntent.proposed_actions`` entry is submitted as a real
``DO``-consequence gymact capability call (`MemoryEnvironment`'s "set"
binding). Without an admitted authority, every one of those calls is
honestly, receiptedly ``REFUSED`` -- never silently skipped, never granted
by this module. A caller wanting real actuation to succeed supplies both an
``authority_resolver`` that actually admits a reference (`gymact`'s own real
``AllowListAuthorityResolver``, built for exactly this per its own
docstring -- "tests, demos, and isolated local gyms") and an
``ExperimentIntent`` whose ``authority_requirements`` names that same
reference. This module never manufactures that admission itself.

What ``proposed_actions``/``expected_postconditions`` map onto
-------------------------------------------------------------------
``ExperimentIntent`` (laboratory.py section 10) is a generic, domain-neutral
type -- it carries plain strings, not a predicate language. This provider's
real, honest, minimal mapping: each ``proposed_actions`` entry (e.g. a
solved-plan PDDL action name such as
``"(complete-define-project-charter)"``) becomes one real ``set`` capability
call recording that the action was actually attempted against the real
(bounded, in-memory) materialized world -- ``{key: action, value: True}``.
``expected_postconditions`` (falling back to ``proposed_actions`` when the
candidate declared none) are then independently re-checked via one real
``env.verify()`` call against the same real world state -- never against
each ``act()`` call's own self-reported ``accepted`` flag, matching
`gymact`'s own closed-gap fix ("`GymAct.verify()` trusted a provider's own
self-reported verdict" -- an injected/default ``PostconditionVerifier`` now
renders the actual verdict, independent of what ``act()`` claimed).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import json
from typing import Any

from gymact.authority import AuthorityResolver
from gymact.models import ActuationIntent as _RealActuationIntent
from gymact.models import MaterializationIntent as _RealMaterializationIntent
from gymact.models import Standing as _RealStanding
from gymact.providers import MEMORY_CAPABILITIES, MemoryProvider
from gymact.runtime import GymAct as _RealGymAct

from autofde_lab.reasoning.laboratory import ExperimentIntent, ExperimentReceipt

__all__ = ["GymActWorldExperimentProvider"]

# The one real gymact Capability this provider actuates against -- resolved
# by binding name (never a hardcoded IRI string) so a real change to
# `gymact.providers.MEMORY_CAPABILITIES`'s own IRIs is caught by an
# AttributeError/StopIteration here rather than silently actuating the
# wrong capability.
_SET_CAPABILITY_IRI = next(c.iri for c in MEMORY_CAPABILITIES if c.binding == "set")


def _run_coroutine_sync(coro: Any) -> Any:
    """Run a real coroutine to completion from `submit_experiment`'s
    synchronous `WorldExperimentProvider` contract, without assuming no
    event loop is already running on the calling thread -- the same real,
    unmocked pattern `gymact_diagnosis_driver.py`'s own
    `_run_coroutine_sync` uses, for the identical reason: a caller reached
    from inside an already-running async context must not hit
    `asyncio.run()`'s `RuntimeError: cannot be called from a running event
    loop`."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _ocel_evidence_digest(ocel_log: dict[str, Any]) -> str:
    """A real, deterministic reference digest over the real OCEL 2.0 log
    `gymact.runtime.GymAct.episode_ocel_log` returns -- a reference,
    per `.claude/rules/no-dual-bookkeeping.md`, never a duplicated copy of
    the log itself."""
    return hashlib.sha256(json.dumps(ocel_log, sort_keys=True).encode("utf-8")).hexdigest()[:16]


async def _submit_experiment_async(
    intent: ExperimentIntent, *, authority_resolver: AuthorityResolver | None
) -> ExperimentReceipt:
    """The real materialize -> act(*) -> verify -> teardown sequence, driven
    through one real, freshly constructed `gymact.runtime.GymAct` instance
    registered with the real `gymact.providers.MemoryProvider` -- exactly
    the pattern `.claude/rules/gym-actuation-boundary.md` names as required:
    "every one of these operations builds a real `gymact.models` request,
    drives it through a real `gymact.runtime.GymAct` instance." A fresh
    runtime per call means idempotency-key reuse across two different
    `submit_experiment` calls (even for the same `ExperimentIntent`, whose
    `intent_id` is deterministic) can never collide with a prior call's
    real runtime-internal idempotency cache -- that cache lives only on the
    `_RealGymAct` instance this function itself constructs and discards.
    """
    runtime = _RealGymAct(authority_resolver=authority_resolver)
    runtime.register_provider(MemoryProvider())

    authority_ref = intent.authority_requirements[0] if intent.authority_requirements else None
    receipt_refs: list[str] = []

    materialization = await runtime.materialize(
        _RealMaterializationIntent(
            provider="memory",
            scenario=intent.candidate_id,
            config={"initial": {}, "requires_authority": True},
            authority_ref=authority_ref,
            idempotency_key=intent.intent_id,
        )
    )
    receipt_refs.append(materialization.receipt.receipt_id)

    if not materialization.accepted or materialization.episode is None:
        # Real, honest refusal -- never a fabricated consequence. Matches
        # `.claude/rules/absence-is-not-evidence.md`: no episode was
        # actually materialized, so nothing else in this function may run.
        return ExperimentReceipt(
            intent_id=intent.intent_id,
            observed_outcome_refs=tuple(receipt_refs),
            authority_standing=materialization.standing.value,
            standing=materialization.standing.value,
        )

    real_episode_id = materialization.episode.episode_id

    for action in intent.proposed_actions:
        act_result = await runtime.act(
            _RealActuationIntent(
                episode_id=real_episode_id,
                capability=_SET_CAPABILITY_IRI,
                payload={"key": action, "value": True},
                authority_ref=authority_ref,
            )
        )
        # A real Receipt is minted whether or not the actuation was
        # admitted (confirmed live: a REFUSED act() still returns a real,
        # non-None receipt) -- always real evidence, never conditional on
        # success.
        receipt_refs.append(act_result.receipt.receipt_id)

    verify_keys = intent.expected_postconditions or intent.proposed_actions
    verification = await runtime.verify(real_episode_id, {key: True for key in verify_keys})
    postconditions_observed = tuple(key for key in verify_keys if verification.observed.get(key) is True)
    postconditions_violated = tuple(key for key in verify_keys if verification.observed.get(key) is not True)

    # `episode_ocel_log` reads accumulated Receipts, which teardown does not
    # clear (see `gymact.kernel.GymAct.episode_ocel_log`'s own docstring) --
    # safe to call either before or after teardown; called here before, so a
    # teardown refusal below can never prevent real OCEL evidence from being
    # captured.
    ocel_log = runtime.episode_ocel_log(real_episode_id)
    ocel_evidence_ref = _ocel_evidence_digest(ocel_log)

    teardown_receipt = await runtime.teardown(real_episode_id, authority_ref=authority_ref)
    receipt_refs.append(teardown_receipt.receipt_id)

    standing = (
        _RealStanding.ALIVE.value
        if verification.passed and not postconditions_violated
        else _RealStanding.REFUSED.value
    )

    return ExperimentReceipt(
        intent_id=intent.intent_id,
        observed_outcome_refs=tuple(receipt_refs),
        authority_standing=materialization.standing.value,
        postconditions_observed=postconditions_observed,
        postconditions_violated=postconditions_violated,
        ocel_evidence_ref=ocel_evidence_ref,
        standing=standing,
    )


class GymActWorldExperimentProvider:
    """Real ``WorldExperimentProvider`` implementation (see
    ``autofde_lab.reasoning.laboratory``'s section 10 for the Protocol this
    satisfies). Every ``submit_experiment`` call drives a real
    materialize -> act(*) -> verify -> teardown sequence through a real
    ``gymact.runtime.GymAct`` instance registered with the real
    ``gymact.providers.MemoryProvider`` -- never a stub, never a fabricated
    consequence. See this module's own docstring for why `MemoryProvider`
    (not a live external server) is the honest minimal integration point,
    and why authority is fail-closed by construction unless a real
    `AuthorityResolver` is injected.
    """

    def __init__(self, *, authority_resolver: AuthorityResolver | None = None) -> None:
        self._authority_resolver = authority_resolver

    def submit_experiment(self, intent: ExperimentIntent) -> ExperimentReceipt:
        return _run_coroutine_sync(
            _submit_experiment_async(intent, authority_resolver=self._authority_resolver)
        )
