"""ForwardBench vendor identity and materialization checks.

A vendor path under ``vendor/gyms`` is only a materialized subject when it owns
its Git repository and its observed HEAD equals the superproject gitlink and,
when supplied, the semantic lock pin.  Git's parent-directory discovery must
never let an ordinary directory impersonate a vendor checkout.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Mapping

_GITLINK_MODE = "160000"
_LOCK_RE = re.compile(
    r"/vendor-(?P<slug>[^>]+)>\s+afb:pinnedRevision\s+\"(?P<sha>[0-9a-fA-F]{40})\""
)


class VendorMaterializationState(str, Enum):
    """Evidence state for one pinned ForwardBench vendor."""

    MATERIALIZED_EXACT = "MATERIALIZED_EXACT"
    PINNED_UNMATERIALIZED = "PINNED_UNMATERIALIZED"
    REFUSED_NOT_GITLINK = "REFUSED:VENDOR_NOT_GITLINK"
    REFUSED_PIN_MISMATCH = "REFUSED:VENDOR_PIN_MISMATCH"
    REFUSED_PARENT_INHERITANCE = "REFUSED:VENDOR_PARENT_INHERITANCE"
    REFUSED_REVISION_MISMATCH = "REFUSED:VENDOR_REVISION_MISMATCH"


@dataclass(frozen=True, slots=True)
class VendorAudit:
    path: str
    state: VendorMaterializationState
    gitlink_revision: str | None
    pinned_revision: str | None
    observed_revision: str | None
    observed_root: str | None
    reason: str

    @property
    def materialized(self) -> bool:
        return self.state is VendorMaterializationState.MATERIALIZED_EXACT


def _git(cwd: Path, *args: str, check: bool = True) -> str:
    process = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if check and process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or process.stdout.strip())
    return process.stdout.strip() if process.returncode == 0 else ""


def parse_gym_lock(text: str) -> Mapping[str, str]:
    """Parse the generated ForwardBench pin lock without requiring RDF extras."""

    pins: dict[str, str] = {}
    for match in _LOCK_RE.finditer(text):
        pins[match.group("slug")] = match.group("sha").lower()
    return pins


def gitlink_revision(superproject: Path, relative_path: str) -> str | None:
    """Return the exact index gitlink revision, refusing ordinary tracked paths."""

    output = _git(superproject, "ls-files", "--stage", "--", relative_path, check=False)
    if not output:
        return None
    # Exactly one stage-0 entry is expected for a submodule path.
    line = output.splitlines()[0]
    fields = line.split(maxsplit=3)
    if len(fields) < 4 or fields[0] != _GITLINK_MODE:
        return None
    return fields[1].lower()


def audit_vendor(
    superproject: str | Path,
    relative_path: str,
    *,
    pinned_revision: str | None = None,
) -> VendorAudit:
    """Audit one vendor without allowing parent Git discovery to establish identity."""

    root = Path(superproject).resolve()
    vendor = (root / relative_path).resolve()
    gitlink = gitlink_revision(root, relative_path)
    pinned = pinned_revision.lower() if pinned_revision else None

    if gitlink is None:
        return VendorAudit(
            relative_path,
            VendorMaterializationState.REFUSED_NOT_GITLINK,
            None,
            pinned,
            None,
            None,
            "vendor path is not a stage-0 Git gitlink in the superproject index",
        )

    if pinned is not None and pinned != gitlink:
        return VendorAudit(
            relative_path,
            VendorMaterializationState.REFUSED_PIN_MISMATCH,
            gitlink,
            pinned,
            None,
            None,
            "semantic lock pin does not equal the superproject gitlink revision",
        )

    if not vendor.exists():
        return VendorAudit(
            relative_path,
            VendorMaterializationState.PINNED_UNMATERIALIZED,
            gitlink,
            pinned,
            None,
            None,
            "vendor is pinned structurally but its worktree is absent",
        )

    observed_root_text = _git(vendor, "rev-parse", "--show-toplevel", check=False)
    if not observed_root_text:
        return VendorAudit(
            relative_path,
            VendorMaterializationState.PINNED_UNMATERIALIZED,
            gitlink,
            pinned,
            None,
            None,
            "vendor is pinned structurally but no vendor-owned Git worktree is materialized",
        )

    observed_root = Path(observed_root_text).resolve()
    if observed_root != vendor:
        # An empty directory produced by an uninitialized submodule is not itself
        # malformed. A populated ordinary directory is stronger evidence of drift.
        populated = any(vendor.iterdir()) if vendor.is_dir() else True
        state = (
            VendorMaterializationState.REFUSED_PARENT_INHERITANCE
            if populated
            else VendorMaterializationState.PINNED_UNMATERIALIZED
        )
        return VendorAudit(
            relative_path,
            state,
            gitlink,
            pinned,
            None,
            str(observed_root),
            (
                "vendor path inherited the superproject Git identity"
                if populated
                else "vendor gitlink is not initialized; Git discovery reached the superproject"
            ),
        )

    observed = _git(vendor, "rev-parse", "HEAD").lower()
    if observed != gitlink:
        return VendorAudit(
            relative_path,
            VendorMaterializationState.REFUSED_REVISION_MISMATCH,
            gitlink,
            pinned,
            observed,
            str(observed_root),
            "materialized vendor HEAD does not equal the pinned superproject gitlink",
        )

    return VendorAudit(
        relative_path,
        VendorMaterializationState.MATERIALIZED_EXACT,
        gitlink,
        pinned,
        observed,
        str(observed_root),
        "vendor owns its Git worktree and HEAD equals every admitted pin",
    )
