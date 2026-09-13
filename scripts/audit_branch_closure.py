#!/usr/bin/env python3
"""Fail closed when a remote branch still carries commits outside the crown.

This is a repository-topology verifier, not a merger. It observes remote refs,
proves ancestry against the exact crown HEAD, and emits deterministic JSON so
branch deletion can occur only after semantic/source closure is already true.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class BranchObservation:
    branch: str
    sha: str
    standing: str
    unique_commits: int
    changed_paths: tuple[str, ...]


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", *args),
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def remote_branches() -> tuple[str, ...]:
    lines = git(
        "for-each-ref",
        "--format=%(refname:short)",
        "refs/remotes/origin",
    ).stdout.splitlines()
    branches = []
    for ref in lines:
        if ref in {"origin/HEAD", "origin/master"}:
            continue
        if not ref.startswith("origin/"):
            continue
        branches.append(ref.removeprefix("origin/"))
    return tuple(sorted(branches))


def observe(branch: str) -> BranchObservation:
    ref = f"origin/{branch}"
    sha = git("rev-parse", ref).stdout.strip()
    ancestor = git("merge-base", "--is-ancestor", ref, "HEAD", check=False)
    if ancestor.returncode == 0:
        return BranchObservation(branch, sha, "CONTAINED", 0, ())
    if ancestor.returncode != 1:
        raise RuntimeError(
            f"REFUSED:ANCESTRY_UNRESOLVED:{branch}:{ancestor.stderr.strip()}"
        )
    unique = int(git("rev-list", "--count", f"HEAD..{ref}").stdout.strip())
    paths = tuple(
        sorted(
            line
            for line in git("diff", "--name-only", "HEAD", ref).stdout.splitlines()
            if line
        )
    )
    return BranchObservation(branch, sha, "UNRESOLVED_UNIQUE", unique, paths)


def main() -> int:
    subject = git("rev-parse", "HEAD").stdout.strip()
    observations = tuple(observe(branch) for branch in remote_branches())
    unresolved = tuple(o for o in observations if o.standing != "CONTAINED")
    payload = {
        "schema": "autofde-lab.branch-closure/1",
        "subject_sha": subject,
        "remote_branch_count": len(observations),
        "contained_branch_count": len(observations) - len(unresolved),
        "unresolved_branch_count": len(unresolved),
        "observations": [asdict(o) for o in observations],
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    if unresolved:
        for item in unresolved:
            print(
                "REFUSED:UNRESOLVED_UNIQUE_BRANCH "
                f"branch={item.branch} sha={item.sha} "
                f"unique_commits={item.unique_commits} "
                f"changed_paths={','.join(item.changed_paths)}",
                file=sys.stderr,
            )
        return 2
    print(f"BRANCH_CLOSURE=ALIVE subject={subject} branches={len(observations)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
