# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Exclusive-claim guard for per-trial evidence directories.

Hardening for a REAL prior incident: in earlier Level 3 work, parallel
agents without per-trial isolation wrote to the same scratch filenames and
one run silently consumed another run's state.

`level4_generator.Trial.new` is already safe by construction -- it calls
``evidence_dir.mkdir(parents=True, exist_ok=False)`` on a path containing a
uuid4, so two trials can never share a directory. But
`level4_gymact_bridge.RealBlindEnvironment.__init__` calls
``mkdir(parents=True, exist_ok=True)`` on whatever path it is handed, so a
caller that constructs two environments with the SAME ``evidence_dir``
gets silent interleaving into one ``probes.jsonl`` with no error -- exactly
the incident's shape. This module supplies the missing detection.

The claim is an OS-level ``O_CREAT | O_EXCL`` lockfile, not an in-process
registry: it therefore also holds across processes (real parallelism), and
a crashed holder leaves a stale claim that must be released explicitly
rather than being silently reused.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

LOCKFILE_NAME = ".trial_claim"


class EvidenceDirContention(RuntimeError):
    """Raised when an evidence directory is already claimed by a live trial."""


@dataclass(frozen=True)
class EvidenceClaim:
    """A held, exclusive claim on one evidence directory."""

    path: Path
    claim_id: str
    lockfile: Path

    def release(self) -> None:
        self.lockfile.unlink(missing_ok=True)

    def __enter__(self) -> EvidenceClaim:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.release()


def read_claim(path: Path) -> dict | None:
    """Return the recorded claim for ``path``, or None if unclaimed."""
    lockfile = Path(path) / LOCKFILE_NAME
    if not lockfile.is_file():
        return None
    return json.loads(lockfile.read_text(encoding="utf-8"))


def acquire_exclusive_evidence_dir(path: Path, *, owner: str = "") -> EvidenceClaim:
    """Claim ``path`` exclusively for one trial, or refuse.

    Creates the directory if needed, then claims it with an ``O_EXCL``
    lockfile. If the directory is already claimed by a live (or crashed)
    trial, raises :class:`EvidenceDirContention` -- it never silently
    shares, which is the whole point.
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    lockfile = path / LOCKFILE_NAME
    claim_id = str(uuid.uuid4())
    payload = json.dumps(
        {"claim_id": claim_id, "owner": owner, "pid": os.getpid()}
    ).encode("utf-8")
    try:
        fd = os.open(lockfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    except FileExistsError as exc:
        existing = read_claim(path)
        raise EvidenceDirContention(
            f"evidence dir {path} is already claimed by {existing!r}; "
            "refusing to share -- each trial must have its own directory"
        ) from exc
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)
    return EvidenceClaim(path=path, claim_id=claim_id, lockfile=lockfile)
