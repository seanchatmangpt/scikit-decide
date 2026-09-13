"""Safe materialization of ForwardBench vendor gitlinks."""

from __future__ import annotations

import subprocess
from pathlib import Path

from autofde_lab.fabric.vendor_materialization import (
    VendorAudit,
    VendorMaterializationState,
    audit_vendor,
)


def _submodule_name(superproject: Path, relative_path: str) -> str | None:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(superproject),
            "config",
            "-f",
            ".gitmodules",
            "--get-regexp",
            r"^submodule\..*\.path$",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        try:
            key, path = line.split(maxsplit=1)
        except ValueError:
            continue
        if path.strip() == relative_path:
            return key[len("submodule.") : -len(".path")]
    return None


def materialize_vendor(
    superproject: str | Path,
    relative_path: str,
    *,
    pinned_revision: str | None = None,
    allow_file_protocol: bool = False,
) -> VendorAudit:
    """Materialize one admitted gitlink at its exact pinned revision.

    Existing populated parent-inheriting directories and pin mismatches are
    refused rather than overwritten. ``allow_file_protocol`` exists only for
    hermetic local fixtures; normal remote submodules do not require it.
    """

    root = Path(superproject).resolve()
    before = audit_vendor(root, relative_path, pinned_revision=pinned_revision)
    if before.materialized:
        return before
    if before.state is not VendorMaterializationState.PINNED_UNMATERIALIZED:
        return before

    name = _submodule_name(root, relative_path)
    if name is None:
        return VendorAudit(
            relative_path,
            VendorMaterializationState.REFUSED_NOT_GITLINK,
            before.gitlink_revision,
            before.pinned_revision,
            None,
            before.observed_root,
            "gitlink has no matching .gitmodules declaration",
        )

    args = ["-c", f"submodule.{name}.update=checkout"]
    if allow_file_protocol:
        args += ["-c", "protocol.file.allow=always"]
    args += ["submodule", "update", "--init", "--checkout", "--", relative_path]
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        after = audit_vendor(root, relative_path, pinned_revision=pinned_revision)
        if after.state is VendorMaterializationState.PINNED_UNMATERIALIZED:
            return VendorAudit(
                relative_path,
                after.state,
                after.gitlink_revision,
                after.pinned_revision,
                after.observed_revision,
                after.observed_root,
                f"materialization failed: {result.stderr.strip() or result.stdout.strip()}",
            )
        return after
    return audit_vendor(root, relative_path, pinned_revision=pinned_revision)
