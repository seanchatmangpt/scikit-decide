# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Session-wide pytest fixtures/setup.

Import numpy for real before anything else in the test session can import
`dspy`: dspy's `dspy.utils.lazy_import.require("numpy")` only returns the
real numpy module if numpy is already present in `sys.modules` at the exact
moment it is called; otherwise it installs a `_LazyModule` proxy whose first
attribute access re-execs numpy's own `__init__.py` in a second module
object, which recurses infinitely (`RecursionError`) under numpy 2.x. This
is a real, reproduced dspy/numpy interaction bug, not a defect in any
scikit-decide code -- conftest.py is loaded before any test module is
collected, so this import ordering guarantee holds regardless of which test
file first happens to import dspy.

The import is best-effort: some CI jobs (e.g. the "Crown kernel" pr-ci.yml
job) deliberately run a minimal, numpy-less environment (only `pytest`
itself is installed) against a fixed subset of tests that never import
dspy. In that environment there is no dspy/numpy ordering hazard to guard
against, so a missing numpy must not fail collection for every test file --
only for whichever specific test actually needs numpy or dspy, which will
raise its own ImportError/ModuleNotFoundError as usual.
"""

try:
    import numpy  # noqa: F401
except ModuleNotFoundError:
    pass

import os
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

# Shared real TurboFieldfareServer fixtures/marker for DSPyPolicy Chicago-school
# tests (both the RockPaperScissors-only file and the all-domains file):
# a real local TurboFieldfareServer subprocess
# (https://github.com/drumih/turbo-fieldfare), real health-check polling over
# HTTP, and real teardown. Factored here (rather than duplicated per test
# file) so every DSPyPolicy test file shares exactly one server-lifecycle
# implementation; `real_turbo_fieldfare_server` is module-scoped so each test
# module gets its own fixture instance, but since it first checks whether a
# real server is already healthy on the expected port and reuses it rather
# than starting a second one, running multiple test modules against an
# already-running server (as during normal `pytest tests/` collection) is
# safe and does not attempt to bind the port twice.

TURBO_FIELDFARE_DIR = Path.home() / "turbo-fieldfare"
SERVER_BINARY = TURBO_FIELDFARE_DIR / ".build" / "release" / "TurboFieldfareServer"
MODEL_PATH = TURBO_FIELDFARE_DIR / "scratch" / "gemma4.gturbo"
PORT = 8080
BASE_URL = f"http://127.0.0.1:{PORT}"

requires_real_turbo_fieldfare_binary_and_model = pytest.mark.skipif(
    not (SERVER_BINARY.exists() and MODEL_PATH.exists()),
    reason=(
        f"Real TurboFieldfareServer binary ({SERVER_BINARY}) or real model "
        f"weights ({MODEL_PATH}) not present -- build/install them per "
        "turbo-fieldfare's README before running this real end-to-end test."
    ),
)


def _real_server_is_healthy() -> bool:
    try:
        with urllib.request.urlopen(f"{BASE_URL}/health", timeout=1) as resp:
            return resp.status == 200
    except OSError:
        return False


@pytest.fixture(scope="module")
def real_turbo_fieldfare_server():
    """Start the real TurboFieldfareServer process for the duration of this module.

    If a real server is already listening on the expected port (started
    separately by the caller, or by another already-loaded test module in
    the same session), reuse it and do not manage its lifecycle.
    """
    if _real_server_is_healthy():
        yield BASE_URL
        return

    process = subprocess.Popen(
        [
            str(SERVER_BINARY),
            "--model",
            str(MODEL_PATH),
            "--port",
            str(PORT),
            "--max-context",
            "4096",
        ],
        cwd=str(TURBO_FIELDFARE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if _real_server_is_healthy():
                break
            if process.poll() is not None:
                pytest.fail(
                    f"Real TurboFieldfareServer process exited early with "
                    f"code {process.returncode} before becoming healthy."
                )
            time.sleep(1)
        else:
            pytest.fail(
                "Real TurboFieldfareServer did not report healthy within 60s."
            )
        yield BASE_URL
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()


@pytest.fixture()
def real_dspy_lm(real_turbo_fieldfare_server):
    import dspy

    from autofde_lab.hub.solver.dspy_policy import DEFAULT_LM_MODEL

    lm = dspy.LM(DEFAULT_LM_MODEL, api_base=f"{real_turbo_fieldfare_server}/v1", api_key="local")
    dspy.configure(lm=lm)
    return lm


# Real Groq-backed alternative to `real_dspy_lm` for the same non-sregym
# DSPyPolicy tests: no local server process required, so this exercises the
# real DSPyPolicy action-resolution code paths (ChooseMove /
# GenerateStructuredAction) against a real, always-reachable Groq endpoint
# instead of depending on a locally-built TurboFieldfareServer binary + model
# weights being present on this machine. `llama-3.1-8b-instant` is Groq's
# smallest/fastest hosted chat model -- adequate for these short,
# structured-output prompts and cheap enough to run per-test, matching the
# gpt-oss-20b choice other GROQ_API_KEY-gated tests in this repo use for the
# same "small model, real call, never a mock" reasoning.
GROQ_DSPY_POLICY_MODEL = "groq/llama-3.1-8b-instant"

_GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

requires_real_groq_key = pytest.mark.skipif(
    not _GROQ_API_KEY,
    reason=(
        "GROQ_API_KEY is not set in this environment -- a real live Groq "
        "call is required for this test and no mock substitute is used per "
        ".claude/rules/testing-chicago-style.md."
    ),
)


@pytest.fixture()
def real_groq_dspy_lm():
    import dspy

    lm = dspy.LM(GROQ_DSPY_POLICY_MODEL, api_key=_GROQ_API_KEY, cache=False)
    dspy.configure(lm=lm)
    return lm
