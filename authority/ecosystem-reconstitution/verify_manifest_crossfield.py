#!/usr/bin/env python3
"""Cross-field verifier for the gym-fleet-reconstitution manifest.

Closes 5 schema gaps that JSON Schema structural validation cannot express:

  1. content_receipts binding: for every sources[] entry with a
     content_receipts map, re-fetch each real path from GitHub at that
     entry's own sha via `gh api repos/{repo}/contents/{path}?ref={sha}`,
     recompute sha256 of the decoded content, and confirm it matches the
     embedded digest.
  2. sources[].id uniqueness within each repository entry.
  3. sha uniqueness ACROSS repositories (canonical_reconstruction_sha and
     every sources[].sha) -- a sha repeated within the SAME repo (e.g. a
     default-branch source and a candidate source pointing at the same
     commit) is legitimate and must not be flagged; only cross-repository
     collisions are real defects.
  4. depends_on dangling-reference check: every depends_on string must
     resolve to an actual repositories[].repository value in the same
     manifest.
  5. expected_repository_count equality: expected_repository_count must
     equal len(repositories) -- JSON Schema draft 2020-12 has no $data
     reference so this cannot be a schema-level constraint; see the
     schema's own $comment on expected_repository_count.

Gap 4 from the session's numbering (disposition/merged/pr_state
consistency) is intentionally NOT covered here -- that is a schema-level
if/then fix, tracked separately.

Usage:
    python3 verify_manifest_crossfield.py <manifest.json>

Exit code 0 iff all checks pass, 1 otherwise. Every failure names the
exact repo/source/path/sha responsible -- never a bare boolean.
"""

import base64
import hashlib
import json
import subprocess
import sys
from collections import defaultdict


def gh_api_content_sha256(repo: str, path: str, ref: str) -> str:
    """Fetch a real file's content from GitHub at an exact ref and return its sha256 hex digest."""
    url = f"repos/{repo}/contents/{path}?ref={ref}"
    result = subprocess.run(
        ["gh", "api", url, "--jq", ".content"],
        capture_output=True,
        text=True,
        check=True,
    )
    b64_content = result.stdout.strip()
    raw = base64.b64decode(b64_content)
    return hashlib.sha256(raw).hexdigest()


def check_content_receipts(manifest: dict) -> tuple[bool, list[str]]:
    """Gap 1: content_receipts must bind to the real file at the source's own sha."""
    failures = []
    checked = 0
    for repo_entry in manifest.get("repositories", []):
        repo = repo_entry["repository"]
        for source in repo_entry.get("sources", []):
            source_id = source.get("id", "<no-id>")
            sha = source.get("sha")
            receipts = source.get("content_receipts", {})
            for path, expected_digest in receipts.items():
                checked += 1
                try:
                    actual_digest = gh_api_content_sha256(repo, path, sha)
                except subprocess.CalledProcessError as exc:
                    failures.append(
                        f"repo={repo} source={source_id} path={path} sha={sha}: "
                        f"gh api fetch failed: {exc.stderr.strip()}"
                    )
                    continue
                if actual_digest != expected_digest:
                    failures.append(
                        f"repo={repo} source={source_id} path={path} sha={sha}: "
                        f"sha256 mismatch -- manifest claims {expected_digest}, "
                        f"real content at that sha hashes to {actual_digest}"
                    )
    if not failures:
        return True, [f"{checked} content_receipts entries verified against real GitHub content"]
    return False, failures


def check_source_id_uniqueness(manifest: dict) -> tuple[bool, list[str]]:
    """Gap 2: sources[].id must be unique within each repository entry."""
    failures = []
    checked_repos = 0
    for repo_entry in manifest.get("repositories", []):
        repo = repo_entry["repository"]
        checked_repos += 1
        ids_seen = defaultdict(int)
        for source in repo_entry.get("sources", []):
            ids_seen[source.get("id")] += 1
        for source_id, count in ids_seen.items():
            if count > 1:
                failures.append(
                    f"repo={repo}: source id '{source_id}' appears {count} times "
                    f"(must be unique within a repository entry)"
                )
    if not failures:
        return True, [f"sources[].id uniqueness held across {checked_repos} repository entries"]
    return False, failures


def check_sha_cross_repo_uniqueness(manifest: dict) -> tuple[bool, list[str]]:
    """Gap 3: sha values must be unique ACROSS repositories, not within one repo."""
    failures = []
    # sha -> set of repos it appears under
    sha_to_repos = defaultdict(set)
    # sha -> list of (repo, locator) for reporting
    sha_to_locations = defaultdict(list)
    total_shas = 0
    for repo_entry in manifest.get("repositories", []):
        repo = repo_entry["repository"]
        canonical = repo_entry.get("canonical_reconstruction_sha")
        if canonical:
            sha_to_repos[canonical].add(repo)
            sha_to_locations[canonical].append(f"{repo}:canonical_reconstruction_sha")
            total_shas += 1
        for source in repo_entry.get("sources", []):
            sha = source.get("sha")
            if sha:
                sha_to_repos[sha].add(repo)
                sha_to_locations[sha].append(f"{repo}:sources[{source.get('id')}]")
                total_shas += 1
    for sha, repos in sha_to_repos.items():
        if len(repos) > 1:
            locs = ", ".join(sha_to_locations[sha])
            failures.append(
                f"sha {sha} appears under {len(repos)} DIFFERENT repositories "
                f"({sorted(repos)}): {locs} -- a commit sha cannot legitimately "
                f"belong to more than one repository"
            )
    if not failures:
        return True, [
            f"{total_shas} sha references checked, 0 cross-repository collisions "
            f"(same-repo repeats, if any, are legitimate and not flagged)"
        ]
    return False, failures


def check_depends_on_resolves(manifest: dict) -> tuple[bool, list[str]]:
    """Gap 5: every depends_on entry must name a real repositories[].repository in this manifest."""
    failures = []
    known_repos = {r["repository"] for r in manifest.get("repositories", [])}
    checked = 0
    for repo_entry in manifest.get("repositories", []):
        repo = repo_entry["repository"]
        for dep in repo_entry.get("depends_on", []):
            checked += 1
            if dep not in known_repos:
                failures.append(
                    f"repo={repo}: depends_on references '{dep}', which does not "
                    f"match any repositories[].repository value in this manifest "
                    f"(known repos: {sorted(known_repos)})"
                )
    if not failures:
        return True, [f"{checked} depends_on references all resolved to real repositories[] entries"]
    return False, failures


def check_expected_repository_count(manifest: dict) -> tuple[bool, list[str]]:
    """Gap 6: expected_repository_count must equal len(repositories).

    JSON Schema draft 2020-12 has no $data reference, so this equality
    cannot be expressed at the schema level (see the schema's own
    $comment on expected_repository_count) -- it is a verifier-time
    obligation only.
    """
    expected = manifest.get("expected_repository_count")
    actual = len(manifest.get("repositories", []))
    if expected == actual:
        return True, [f"expected_repository_count ({expected}) == len(repositories) ({actual})"]
    return False, [
        f"expected_repository_count declares {expected} but repositories[] "
        f"contains {actual} entries -- these must be equal"
    ]


CHECKS = [
    ("content_receipts sha256 binding (gap 1)", check_content_receipts),
    ("sources[].id uniqueness within repo (gap 2)", check_source_id_uniqueness),
    ("sha uniqueness across repositories (gap 3)", check_sha_cross_repo_uniqueness),
    ("depends_on dangling-reference check (gap 5)", check_depends_on_resolves),
    ("expected_repository_count == len(repositories) (gap 6)", check_expected_repository_count),
]


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: verify_manifest_crossfield.py <manifest.json>", file=sys.stderr)
        return 1

    manifest_path = sys.argv[1]
    with open(manifest_path) as f:
        manifest = json.load(f)

    print(f"Verifying: {manifest_path}")
    print("=" * 78)

    all_passed = True
    for name, check_fn in CHECKS:
        ok, evidence = check_fn(manifest)
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}")
        for line in evidence:
            print(f"    {line}")
        if not ok:
            all_passed = False
        print()

    print("=" * 78)
    if all_passed:
        print(f"RESULT: PASS (all {len(CHECKS)} cross-field checks passed)")
        return 0
    else:
        print("RESULT: FAIL (see FAIL entries above for exact defects)")
        return 1


if __name__ == "__main__":
    sys.exit(main())
