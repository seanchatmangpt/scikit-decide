# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Mechanical proof that ``autofde_lab.powl`` and ``autofde_lab.agent`` are self-contained.

``tests/agent/test_breach_clock_chicago.py`` claims the milestone loop runs on a
clean checkout with ``~/mfw``, ``~/bcinr``, ``~/ggen`` and ``~/mfact`` all
absent, no network and no Azure. A test that merely avoids importing them proves
only that *this* file avoids them; a transitive import three modules deep would
pass unnoticed. So the check is run in a **fresh subprocess** with ``HOME``
pointed at an empty temporary directory and the working directory moved out of
the repository, and the subprocess reports the file of every module it loaded.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SIBLING_REPOS = (
    "mfw",
    "bcinr",
    "ggen",
    "ggen-create",
    "ggen-legacy",
    "mfact",
    "wasm4pm",
    "wasm4pm-compat",
    "praxis",
    "ostar",
)

_PROBE = r"""
import json, os, sys

import autofde_lab.powl
import autofde_lab.agent
from autofde_lab.powl.algebra import Atom, PartialOrder
from autofde_lab.powl.executor import enabled, fire
from autofde_lab.powl.validate import validate_model
from autofde_lab.agent.session import AgentSession
from autofde_lab.agent import replan
from autofde_lab.hub.domain.breach_clock import BreachClockDomain

# not just importable — usable, with no home directory and no network
model = PartialOrder((Atom("a"), Atom("b")))
validate_model(model)
live = enabled(model)
marking = fire(model, __import__("autofde_lab.powl.executor", fromlist=["x"]).INITIAL_MARKING, sorted(live)[0])

files = {}
for name, mod in list(sys.modules.items()):
    path = getattr(mod, "__file__", None)
    if path:
        files[name] = os.path.realpath(path)

print("@@RESULT@@" + json.dumps({
    "home": os.environ.get("HOME"),
    "cwd": os.getcwd(),
    "enabled": sorted(len(p) for p in live),
    "fires": marking.fires,
    "files": files,
}))
"""


def test_powl_and_agent_import_and_run_with_an_empty_home(tmp_path: Path):
    home = tmp_path / "empty-home"
    home.mkdir()
    workdir = tmp_path / "elsewhere"
    workdir.mkdir()

    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        # no network, no Azure, no credentials of any kind are provided
        "PYTHONHASHSEED": "0",
    }
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=workdir,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert proc.returncode == 0, proc.stderr

    marker = "@@RESULT@@"
    assert marker in proc.stdout, proc.stdout
    result = json.loads(proc.stdout.split(marker, 1)[1].strip())

    assert result["home"] == str(home)
    assert list(home.iterdir()) == [], "the probe must not need anything in HOME"
    assert result["fires"] == 1

    # nothing loaded from a sibling repository checkout
    offenders = {
        name: path
        for name, path in result["files"].items()
        if any(f"/{repo}/" in path for repo in SIBLING_REPOS)
    }
    assert offenders == {}, offenders

    # and the modules the milestone test depends on really were loaded
    for required in (
        "autofde_lab.powl.executor",
        "autofde_lab.powl.validate",
        "autofde_lab.agent.session",
        "autofde_lab.agent.replan",
        "autofde_lab.hub.domain.breach_clock.breach_clock",
    ):
        assert required in result["files"], sorted(result["files"])
