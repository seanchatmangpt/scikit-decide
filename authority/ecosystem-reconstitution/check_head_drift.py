#!/usr/bin/env python3
"""
check_head_drift.py -- detect HEAD-staleness drift for the gym-fleet
reconstitution manifest.

The manifest's head_binding is
"PER_REPOSITORY_DEFAULT_BRANCH_HEAD_AT_OBSERVATION_DAY", meaning any
sources[] entry whose id ends in "-main-head" or "-default-branch-head"
claims to represent the repository's CURRENT default-branch HEAD at the
moment the manifest was authored. Nothing re-checks that claim after
authoring -- this script does, by fetching the real, live default-branch
HEAD via `gh api repos/{repo}/branches/{default_branch}` and diffing it
against the recorded sha.

Usage:
    python3 check_head_drift.py <manifest.json>

Exit codes:
    0  -- all HEAD-claiming sources still MATCH the live default branch HEAD
    1  -- at least one HEAD-claiming source has DRIFTED (informational, not
          necessarily a blocking error -- but distinguishable for automation)
    2  -- usage / fetch / manifest error
"""
import json
import subprocess
import sys


def gh_api(path: str) -> dict:
    """Real `gh api` call. No mocking -- this hits the live GitHub API."""
    proc = subprocess.run(
        ["gh", "api", path],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"gh api {path} failed (exit {proc.returncode}): {proc.stderr.strip()}"
        )
    return json.loads(proc.stdout)


def get_commit_date(repo: str, sha: str) -> str:
    """Fetch the real committer date for a commit sha. Returns '' if not found."""
    try:
        data = gh_api(f"repos/{repo}/commits/{sha}")
    except (RuntimeError, json.JSONDecodeError):
        return "UNKNOWN (sha not fetchable)"
    try:
        return data["commit"]["committer"]["date"]
    except (KeyError, TypeError):
        return "UNKNOWN (no committer date in response)"


def is_head_claiming_source(source_id: str) -> bool:
    return source_id.endswith("-main-head") or source_id.endswith(
        "-default-branch-head"
    )


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <manifest.json>", file=sys.stderr)
        return 2

    manifest_path = sys.argv[1]
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"ERROR: could not load manifest {manifest_path}: {e}", file=sys.stderr)
        return 2

    head_binding = manifest.get("head_binding", "<unset>")
    repositories = manifest.get("repositories", [])

    print("=" * 78)
    print("HEAD-staleness drift check")
    print(f"manifest:      {manifest_path}")
    print(f"head_binding:  {head_binding}")
    print(f"observation_day: {manifest.get('observation_day', '<unset>')}")
    print(f"repositories:  {len(repositories)}")
    print("=" * 78)

    checked = []
    errors = []

    for repo_entry in repositories:
        repo = repo_entry.get("repository")
        default_branch = repo_entry.get("default_branch")
        sources = repo_entry.get("sources", [])

        head_sources = [
            s for s in sources if is_head_claiming_source(s.get("id", ""))
        ]
        if not head_sources:
            continue

        if not repo or not default_branch:
            errors.append(
                f"{repo or '<unknown repo>'}: missing repository/default_branch "
                "field, cannot check HEAD-claiming source(s)"
            )
            continue

        try:
            branch_data = gh_api(f"repos/{repo}/branches/{default_branch}")
            live_sha = branch_data["commit"]["sha"]
        except (RuntimeError, KeyError, TypeError, json.JSONDecodeError) as e:
            errors.append(
                f"{repo}: failed to fetch live default_branch "
                f"'{default_branch}' HEAD via gh api: {e}"
            )
            continue

        for source in head_sources:
            recorded_sha = source.get("sha")
            source_id = source.get("id")

            if recorded_sha == live_sha:
                checked.append(
                    {
                        "repo": repo,
                        "source_id": source_id,
                        "status": "MATCH",
                    }
                )
                print(
                    f"\n[MATCH] {repo}  (source: {source_id})\n"
                    f"    default_branch: {default_branch}\n"
                    f"    sha (recorded == live): {live_sha}"
                )
            else:
                old_date = get_commit_date(repo, recorded_sha)
                new_date = get_commit_date(repo, live_sha)
                checked.append(
                    {
                        "repo": repo,
                        "source_id": source_id,
                        "status": "DRIFT",
                        "recorded_sha": recorded_sha,
                        "live_sha": live_sha,
                    }
                )
                print(
                    f"\n[DRIFT] {repo}  (source: {source_id})\n"
                    f"    default_branch: {default_branch}\n"
                    f"    recorded sha: {recorded_sha}\n"
                    f"        committed: {old_date}\n"
                    f"    live sha:     {live_sha}\n"
                    f"        committed: {new_date}\n"
                    f"    -> the manifest's recorded HEAD is stale relative to "
                    f"the real, current default-branch HEAD."
                )

    print("\n" + "=" * 78)
    print("SUMMARY")
    print("=" * 78)

    if errors:
        for e in errors:
            print(f"[ERROR] {e}")

    if not checked and not errors:
        print("No sources[] entries with id ending in '-main-head' or "
              "'-default-branch-head' were found in this manifest.")
        return 0

    n_match = sum(1 for c in checked if c["status"] == "MATCH")
    n_drift = sum(1 for c in checked if c["status"] == "DRIFT")
    print(f"checked: {len(checked)}  match: {n_match}  drift: {n_drift}  "
          f"errors: {len(errors)}")

    if errors:
        return 2
    if n_drift > 0:
        print(
            "\nDRIFT detected: the manifest's head_binding "
            f"'{head_binding}' no longer holds for {n_drift} source(s) -- "
            "these no longer represent the real, current default-branch "
            "HEAD. This is informational/expected here, not a hard failure, "
            "but the exit code reflects it for automation to key off."
        )
        return 1

    print("\nAll HEAD-claiming sources MATCH the real, current "
          "default-branch HEAD. No drift detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
