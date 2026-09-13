# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style test for the `_EXECUTE_SCRIPT` materialize-refusal guard.

The defect this pins: `_EXECUTE_SCRIPT` accessed `m.episode.episode_id`
without checking `m.accepted` first -- unlike `_BRIDGE_SCRIPT` (the
discovery-side script), which does check. Any actuation-time materialize
refusal therefore crashed the subprocess with an unhandled
`AttributeError: 'NoneType' object has no attribute 'episode_id'`, which
`commit_and_execute` re-raised as an opaque `RuntimeError`, which propagated
out of `run_real_trial` as an unhandled exception -- contradicting this
module's own stated design ("a trial that cannot be modelled is a FAILED
trial with a named reason, never an absent one"), applied everywhere else in
`run_real_trial` but not here.

Found and reproduced live via a real, external condition (the local colima
Docker daemon becoming unreachable between an earlier successful `docker
info` check and a `cube_container_counter` trial's actuation step). That
exact trigger is transient and not safely reproducible on demand, so this
test uses a different, real, deterministic, environment-independent trigger
for the identical code path: a `MaterializationIntent` naming a provider
that was never registered under that name, which `gymact`'s own kernel
refuses with a real `UNKNOWN_PROVIDER` receipt (`accepted=False`,
`episode=None`) -- confirmed live before writing this test.

Every collaborator is real: the actual `_EXECUTE_SCRIPT` module constant
(not a copy), a real subprocess in `~/gymact`'s own venv, the real `gymact`
kernel, the real `cube_counter` provider class. No mocks.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from autofde_lab.hub.domain.gym_procedure.level4_crown import (
    GYMACT,
    GYMACT_VENV_PYTHON,
    _EXECUTE_SCRIPT,
)

pytestmark = pytest.mark.skipif(
    not Path(GYMACT_VENV_PYTHON).exists(),
    reason=f"real gymact interpreter absent at {GYMACT_VENV_PYTHON}",
)


def test_execute_script_reports_typed_refusal_not_a_crash(tmp_path: Path) -> None:
    """Direct test of the real `_EXECUTE_SCRIPT` constant: a genuine,
    deterministic materialize refusal (unregistered provider name) must
    come back as a typed `{"materialize_failed": True, "reason": ...}`
    result with a clean exit code, never a subprocess crash."""
    script = tmp_path / "execute.py"
    script.write_text(_EXECUTE_SCRIPT, encoding="utf-8")
    ledger_path = tmp_path / "receipts.sqlite3"

    completed = subprocess.run(
        [
            str(GYMACT_VENV_PYTHON), str(script),
            "gymact.gyms.cube_counter", "CubeCounterProvider",
            "WRONG-NAME-NOT-REGISTERED",  # deterministic refusal trigger
            json.dumps({"target": 3}), json.dumps(["increment"]),
            json.dumps([{"counter": 1, "solved": False}]), json.dumps([{}]),
            str(ledger_path),
        ],
        capture_output=True, text=True, cwd=str(GYMACT), timeout=60,
    )

    assert completed.returncode == 0, (
        f"script crashed instead of reporting a typed refusal:\n"
        f"stdout={completed.stdout}\nstderr={completed.stderr}"
    )
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert result.get("materialize_failed") is True
    assert result.get("reason") == "UNKNOWN_PROVIDER"

    # `commit_and_execute`'s corresponding `result.get("materialize_failed")`
    # branch (raising `ActuationMaterializeRefused` instead of proceeding to
    # index into a malformed result) is not independently unit-tested here:
    # `commit_and_execute` looks up `provider_name` from its own
    # `_PROVIDERS[provider_key]` registry, which by construction always
    # agrees with what gets registered, so this exact deterministic trigger
    # cannot be driven through `commit_and_execute`'s public signature
    # without mutating shared module state. That branch's real, live
    # behavior -- against the real dependency genuinely unavailable, not a
    # synthetic result -- is independently confirmed end to end: a real
    # `cube_container_counter` trial raised `ActuationMaterializeRefused`
    # (reason `PROVIDER_ERROR:CalledProcessError`) while colima was down,
    # and the identical trial reached real `EXECUTED`/`Level4AliveEvidence`
    # once colima was restarted -- both runs are recorded in
    # `docs/level4-migration-matrix.md` with exact evidence, not asserted
    # from memory.
