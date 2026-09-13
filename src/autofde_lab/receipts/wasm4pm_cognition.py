# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Bridge to ``~/wasm4pm``'s cognition kernel (55-breed symbolic-AI layer), consumed as
external evidence by this repo's planner -- never as an actuation signal (this repo
"computes candidate plans. It does not actuate.").

Two ``wpm`` binaries exist side by side in ``~/wasm4pm`` and must not be confused:

- The **Rust** ``wasm4pm-cli`` binary (``~/wasm4pm/target/{debug,release}/wpm``),
  resolved by :func:`autofde_lab.ocel.wasm4pm_bridge.resolve_wpm_binary`, exposes
  ``mining discover/conformance/drift/predict-duration`` only -- no cognition surface.
- The **Node** ``apps/wasm4pm`` package (npm bin ``dist/bin/wpm.js``), resolved here by
  :func:`resolve_wpm_cognition_entry`, exposes the cognition breed kernel. This module
  never touches the Rust binary's resolver, and that resolver is never extended to cover
  this case -- two distinct external tools, two distinct resolvers, matching this repo's
  existing one-bridge-module-per-surface convention.

As of the 2026-08-10 session, ``wpm cognition run`` (the surface documented in
``apps/wasm4pm/src/commands/cognition/run.ts``) was retired and folded under a "lab"
noun-verb machine-protocol surface; the current, live-verified invocation is::

    node <dist/bin/wpm.js> lab cognition run --contract <breed> --input <path.json> \\
        --format json --no-save

confirmed by running it for real against the ``ebl`` breed this session -- not assumed
from source reading alone, since the source-level ``run.ts`` command turned out to no
longer be the live-wired entry point. ``lab cognition`` prints an
``[experimental] ... may change or be removed without notice`` banner to **stderr**
(stdout stays pure JSON) -- confirmed by capturing both streams separately.

On success, stdout is a result envelope::

    {"command": "cognition run", "status": "ok", "message": ..., "exit_code": 0,
     "payload": {"contract", "breed", "status", "output", "run_id", "output_hash",
                 "replay_pointer", "inference_step_count", "rules_evaluated", "saved_path"}}

On failure (unknown breed, malformed input, WASM panic), the process exits non-zero and
stdout is instead ``{"error": {"code": ..., "message": ...}}`` -- no ``status``/``payload``
at all. Both shapes are confirmed live (a real ``ebl`` run and a real
``unknown breed: ...`` rejection), not inferred from the TS source.

This module's :class:`NoEvidence` marks that failure shape explicitly -- callers must
never coerce it into an empty/default candidate (the "absence is not evidence" doctrine
already asserted for other bridges in ``tests/ecosystem/``).
"""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from autofde_lab.fabric.bounded_exec import run_subprocess_bounded

__all__ = [
    "Wasm4pmCognitionUnavailable",
    "NoEvidence",
    "CognitionEvidence",
    "resolve_wpm_cognition_entry",
    "run_cognition",
    "verify_cognition_evidence",
]


class Wasm4pmCognitionUnavailable(RuntimeError):
    """Raised when no built ``apps/wasm4pm`` Node CLI can be found."""


class NoEvidence(RuntimeError):
    """Raised whenever a cognition run does not produce trustworthy evidence: a
    non-``"ok"`` status, a non-zero exit code, a timeout, or a receipt that fails
    :func:`verify_cognition_evidence`. Never caught and silently replaced with an
    empty/default candidate -- per the "absence is not evidence" doctrine, a caller
    that wants to treat missing cognition evidence as "no additional candidates"
    must catch this explicitly and say so, not receive a quietly-empty result.
    """


@dataclass(frozen=True)
class CognitionEvidence:
    """One breed run's output, as external evidence for plan admission."""

    breed: str
    run_id: str
    output_hash: str
    replay_pointer: str
    status: str
    selected: str | None
    explanation: str | None
    inference_trace: list[dict[str, Any]] = field(default_factory=list)
    raw_output: dict[str, Any] = field(default_factory=dict)


def resolve_wpm_cognition_entry() -> tuple[str, str]:
    """Locate ``node`` and the ``apps/wasm4pm`` CLI entry point, or raise
    :class:`Wasm4pmCognitionUnavailable`.

    Checks ``WASM4PM_COGNITION_CLI`` (path to the ``wpm.js`` entry) first, then the
    documented sibling-repo path (``~/wasm4pm/apps/wasm4pm/dist/bin/wpm.js``, matching
    this repo's ``CLAUDE.md`` sibling-repo convention), then a globally-linked ``wpm``
    on ``PATH`` is *not* attempted here since the global name collides with the Rust
    binary's own ``wpm`` -- ambiguity that has to be resolved by an explicit path, not
    guessed at from ``PATH``.

    Returns ``(node_bin, script_path)`` -- the caller invokes
    ``[node_bin, script_path, "lab", "cognition", "run", ...]``, never the script path
    alone (it is not marked executable / has no shebang guarantee across platforms).
    """
    node_bin = shutil.which("node")
    if not node_bin:
        raise Wasm4pmCognitionUnavailable("no 'node' binary found on PATH")

    env_path = os.environ.get("WASM4PM_COGNITION_CLI")
    if env_path and Path(env_path).is_file():
        return node_bin, env_path

    sibling = Path.home() / "wasm4pm" / "apps" / "wasm4pm" / "dist" / "bin" / "wpm.js"
    if sibling.is_file():
        return node_bin, str(sibling)

    raise Wasm4pmCognitionUnavailable(
        "no built apps/wasm4pm CLI found (checked $WASM4PM_COGNITION_CLI and "
        "~/wasm4pm/apps/wasm4pm/dist/bin/wpm.js) -- build it with 'pnpm build' "
        "inside ~/wasm4pm/apps/wasm4pm"
    )


def _breed_input_json(
    *,
    intent: str = "",
    facts: list[dict[str, str]] | None = None,
    rules: list[dict[str, Any]] | None = None,
    cases: list[dict[str, Any]] | None = None,
    goals: list[dict[str, Any]] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    state: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a ``BreedInput`` JSON document -- every field is required by the Rust
    ``deny_unknown_fields`` contract even when empty (confirmed against
    ``crates/wasm4pm-cognition/src/wasm.rs`` and this session's real ``ebl`` run)."""
    return {
        "intent": intent,
        "facts": facts or [],
        "rules": rules or [],
        "cases": cases or [],
        "goals": goals or [],
        "candidates": candidates or [],
        "state": state or [],
    }


async def run_cognition(
    breed: str,
    *,
    intent: str = "",
    facts: list[dict[str, str]] | None = None,
    rules: list[dict[str, Any]] | None = None,
    cases: list[dict[str, Any]] | None = None,
    goals: list[dict[str, Any]] | None = None,
    candidates: list[dict[str, Any]] | None = None,
    state: list[dict[str, Any]] | None = None,
    verify: bool = True,
    timeout_s: float = 30.0,
) -> CognitionEvidence:
    """Run a real cognition breed via subprocess, return typed evidence.

    Raises :class:`NoEvidence` on any non-``"ok"`` outcome (bad exit code, malformed
    output, or -- when ``verify=True`` -- a receipt that fails
    :func:`verify_cognition_evidence`). Never returns a placeholder/default
    :class:`CognitionEvidence` for a failed run.
    """
    node_bin, script_path = resolve_wpm_cognition_entry()
    payload = _breed_input_json(
        intent=intent, facts=facts, rules=rules, cases=cases,
        goals=goals, candidates=candidates, state=state,
    )

    import tempfile

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(payload, tmp)
        tmp_path = tmp.name

    try:
        outcome = await run_subprocess_bounded(
            [
                node_bin, script_path, "lab", "cognition", "run",
                "--contract", breed, "--input", tmp_path,
                "--format", "json", "--no-save",
            ],
            timeout_s=timeout_s,
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    if outcome.standing != "SOLVED":
        # A non-zero exit still writes the real error detail to stdout (confirmed
        # live: `{"error": {"code": "EXECUTION_ERROR", "message": "..."}}`) while
        # stderr carries only the `[experimental] ...` banner -- surface both, since
        # stderr alone silently drops the actual reason for a real rejection.
        raise NoEvidence(
            f"cognition run for breed={breed!r} did not complete "
            f"(standing={outcome.standing}): stdout={outcome.stdout.strip()!r} "
            f"stderr={outcome.stderr.strip()!r}"
        )

    try:
        envelope = json.loads(outcome.stdout)
    except json.JSONDecodeError as exc:
        raise NoEvidence(
            f"cognition run for breed={breed!r} produced non-JSON stdout: {exc}"
        ) from exc

    if "error" in envelope or envelope.get("status") != "ok":
        detail = envelope.get("error", envelope)
        raise NoEvidence(f"cognition run for breed={breed!r} returned no evidence: {detail}")

    body = envelope.get("payload", {})
    if body.get("status") != "ok":
        raise NoEvidence(
            f"cognition run for breed={breed!r} envelope ok but payload status="
            f"{body.get('status')!r}: {body}"
        )

    evidence = CognitionEvidence(
        breed=body["breed"],
        run_id=body["run_id"],
        output_hash=body["output_hash"],
        replay_pointer=body["replay_pointer"],
        status=body["status"],
        selected=(body.get("output") or {}).get("selected"),
        explanation=(body.get("output") or {}).get("explanation"),
        inference_trace=(body.get("output") or {}).get("inference_trace", []),
        raw_output=body.get("output", {}),
    )

    if verify and not verify_cognition_evidence(evidence):
        raise NoEvidence(
            f"cognition run for breed={breed!r} produced a receipt that failed "
            f"causal-consistency verification (run_id={evidence.run_id[:16]}...) "
            "-- treated as no evidence, not partial evidence"
        )

    return evidence


def verify_cognition_evidence(evidence: CognitionEvidence) -> bool:
    """Re-derive, don't trust: verification-only re-implementation of the two cheap
    checks in ``packages/cognition/src/receipt/chain.ts::verifyCausalConsistency``
    (chain construction stays in wasm4pm; this only re-checks a claim already made):

    1. ``run_id == blake3(breed + "|" + output_hash)``
    2. ``replay_pointer == output_hash[:16]``

    Full BLAKE3 link-chain replay (the ``wasm4pm.recpt.v2.link`` MAC in
    ``crates/wasm4pm-cognition/src/autosystems/receipt.rs``) is intentionally not
    reimplemented here -- these two checks are what a live CLI-returned envelope can
    be checked against without a saved receipt chain file; add link-chain replay only
    if this bridge starts independently re-verifying saved receipt files rather than
    trusting a live subprocess's own output.

    Uses the ``blake3`` PyPI package -- verified this session to reproduce a real
    ``wpm lab cognition run`` output's ``run_id`` byte-for-byte. Deliberately does not
    touch or attempt to interoperate with this repo's own ``receipts.core`` sha256
    scheme (a conscious, separate, ERRC-grid choice per that module's docstring) --
    this is a standalone verifier for external wasm4pm-cognition evidence only.
    """
    import blake3 as blake3_lib

    expected_run_id = blake3_lib.blake3(
        f"{evidence.breed}|{evidence.output_hash}".encode("utf-8")
    ).hexdigest()
    if evidence.run_id != expected_run_id:
        return False

    expected_replay_pointer = evidence.output_hash[:16]
    if evidence.replay_pointer != expected_replay_pointer:
        return False

    return True
