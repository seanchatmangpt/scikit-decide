# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style, real, `require_standing`-gated attempt at the actual SREGym
`autofde_lab_planner` invocation this repo already cites as its real, working
non-LLM path (`materialize_sregym.py`).

Per `gymact.standing.require_standing`, the real thing is the default: if the real
SREGym checkout, a real reachable Kubernetes cluster, AND real judge-model credentials
are not ALL present, this module FAILS unless the run explicitly sets
`GYMACT_ALLOW_DEGRADED_STANDINGS` to include "LOCAL_GYM:sregym-crown-receipt-live" (or
"*") -- a skip here is something a run must opt into, never something it silently gets.

Honest note: this checkout has a real SREGym vendored checkout and (when a local
colima/k3s cluster is running) a real reachable cluster, but even the non-LLM
`autofde_lab_planner` path's judge pre-flight check requires `OPENAI_API_KEY`, which is
not configured here -- so this module is EXPECTED to fail loudly, naming that exact
real, external gap, rather than being silently absent.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

from gymact.standing import require_standing


def _sregym_root() -> Path:
    return Path.home() / "autofde-lab" / "vendor" / "gyms" / "sregym"


def _sregym_checkout_available() -> bool:
    root = _sregym_root()
    return (root / "main.py").is_file() and (root / "pyproject.toml").is_file()


def _cluster_reachable() -> bool:
    if shutil.which("kubectl") is None:
        return False
    try:
        result = subprocess.run(
            ["kubectl", "cluster-info"],
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _judge_credentials_available() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


require_standing(
    "LOCAL_GYM:sregym-crown-receipt-live",
    available=_sregym_checkout_available()
    and _cluster_reachable()
    and _judge_credentials_available(),
    reason=(
        "real SREGym checkout + real reachable cluster may both be present, but the "
        "benchmark's own judge pre-flight check (even for the non-LLM autofde_lab_planner "
        "path) requires OPENAI_API_KEY, which is not configured -- a real, external, "
        "not-fixable-by-code gap, named here rather than left untested"
    ),
)

from gymact import (
    AllowListAuthorityResolver,
    GymAct,
    MaterializationIntent,
)
from gymact.gyms.sregym import SREGYM_CAPABILITIES
from gymact.models import ActuationIntent

from autofde_lab.sota.materialize_sregym import (
    current_sregym_autofde_lab_planner_basis,
)

AUTHORITY = "urn:test:sregym-crown-receipt-live"


def test_real_sregym_autofde_lab_planner_episode_via_gymact() -> None:
    """One real episode against the real vendored SREGym checkout and real cluster,
    using the exact basis `materialize_sregym.py` already cites as this repo's real,
    working non-LLM point. If real judge credentials are ever configured, this proves
    a genuine live episode end to end; until then, `require_standing` above refuses the
    whole module honestly before this test body ever runs."""
    asyncio.run(_run_real_episode())


async def _run_real_episode() -> None:
    basis = current_sregym_autofde_lab_planner_basis()
    problem_id = basis.extra["problem_id"]

    from gymact.gyms.sregym import SregymVendorProvider

    gym = GymAct(authority_resolver=AllowListAuthorityResolver({AUTHORITY}))
    gym.register_provider(SregymVendorProvider())

    materialization = await gym.materialize(
        MaterializationIntent(
            provider="sregym",
            config={"agent": "autofde_lab_planner", "problem_id": problem_id},
            authority_ref=AUTHORITY,
        )
    )
    assert materialization.accepted is True, materialization.receipt.reason
    episode_id = materialization.episode.episode_id

    run_capability = next(c for c in SREGYM_CAPABILITIES if c.binding == "run")
    outcome = await gym.act(
        ActuationIntent(
            episode_id=episode_id,
            capability=run_capability.iri,
            payload={},
            authority_ref=AUTHORITY,
        )
    )
    assert outcome.accepted is True

    await gym.teardown(episode_id)
