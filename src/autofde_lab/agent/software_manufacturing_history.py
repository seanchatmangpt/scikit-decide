"""Compile historical engineering events into replayable software-manufacturing plans.

The compiler treats GitHub/software-delivery history as observation evidence, not as
authority. It preserves the reported August 2026 commit total separately from the
number of commit events actually present in an export so an incomplete export can
never silently masquerade as the historical corpus.

Replay is simulation-only. A replay world exposes admissible plan steps, records
agent selections, and emits a deterministic simulation receipt. It cannot push,
merge, deploy, apply infrastructure, send messages, or acquire external authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence
from urllib.parse import quote

PLAN_SCHEMA = "urn:autofde-lab:software-manufacturing-plan:1"
CORPUS_SCHEMA = "urn:autofde-lab:software-manufacturing-corpus:1"
REPLAY_SCHEMA = "urn:autofde-lab:software-manufacturing-replay:1"

_GITHUB_KINDS = {
    "branch",
    "branch_created",
    "commit",
    "default_branch_containment",
    "deployment",
    "issue",
    "merge",
    "pull_request",
    "release",
    "review",
    "workflow_run",
}
_CLOSURE_KINDS = {"merge", "release", "default_branch_containment"}
# GitHub REST endpoints this module can actually query for real, in-repo evidence
# (via the real `gh api` binary, no mocking) -- one entry per event kind the
# planner/agent frontier can then present as an admissible step. Broadening this
# tuple is how the simulation gains more real actuatable event kinds; it must
# stay in sync with a real normalizer function in ``_GH_EVENT_BUILDERS`` below.
GITHUB_FETCHABLE_KINDS = (
    "commit",
    "pull_request",
    "review",
    "workflow_run",
    "release",
    "issue",
    "deployment",
)
_PATH_SURFACE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("tests", re.compile(r"(^|/)(tests?|specs?)(/|$)|(^|/)test_[^/]+\.py$")),
    (
        "ci_cd",
        re.compile(
            r"(^|/)\.github/workflows/|jenkins|circleci|buildkite|"
            r"gitlab-ci|(^|/)ci(/|$)"
        ),
    ),
    (
        "iac",
        re.compile(
            r"\.tf$|terraform|cloudformation|crossplane|pulumi|"
            r"(^|/)iac(/|$)|(^|/)infra(structure)?(/|$)"
        ),
    ),
    (
        "container",
        re.compile(
            r"(^|/)dockerfile$|docker-compose|compose\.ya?ml$|"
            r"(^|/)helm(/|$)|(^|/)k8s(/|$)|(^|/)kubernetes(/|$)"
        ),
    ),
    (
        "docs",
        re.compile(r"(^|/)docs?(/|$)|readme|agents\.md$|(^|/)book(/|$)|mdbook"),
    ),
    (
        "security",
        re.compile(
            r"security|iam|rbac|policy|policies|guardrail|opa|shacl|"
            r"provenance|supply-chain|sbom"
        ),
    ),
    (
        "observability",
        re.compile(
            r"otel|opentelemetry|observability|telemetry|metrics|tracing|"
            r"logging|prometheus|grafana"
        ),
    ),
    (
        "cloud",
        re.compile(r"aws|azure|gcp|google-cloud|cloudrun|sagemaker|vertex"),
    ),
    (
        "release",
        re.compile(
            r"release|publish|package|packaging|pypi|crates\.io|npm|ghcr|artifact"
        ),
    ),
)
_SOURCE_PATH = re.compile(
    r"(^|/)(src|app|apps|lib|libs|crates|packages|services|cmd|internal)(/|$)"
)


def canonical_digest(value: object) -> str:
    """Return a deterministic SHA-256 over canonical JSON."""

    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _slug(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return text[:64] or "step"


@dataclass(frozen=True, slots=True)
class HistoricalEvent:
    """One normalized observation from GitHub or an adjacent delivery surface."""

    event_id: str
    timestamp: str
    repository: str
    kind: str
    ref: str = ""
    sha: str = ""
    parent_ids: tuple[str, ...] = ()
    changed_paths: tuple[str, ...] = ()
    labels: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, value: Mapping[str, object]) -> "HistoricalEvent":
        required = ("event_id", "timestamp", "repository", "kind")
        missing = [key for key in required if not value.get(key)]
        if missing:
            raise ValueError(f"historical event missing required fields: {missing}")
        metadata = value.get("metadata", {})
        if not isinstance(metadata, Mapping):
            raise ValueError("historical event metadata must be an object")
        return cls(
            event_id=str(value["event_id"]),
            timestamp=str(value["timestamp"]),
            repository=str(value["repository"]),
            kind=str(value["kind"]),
            ref=str(value.get("ref", "")),
            sha=str(value.get("sha", "")),
            parent_ids=tuple(str(item) for item in value.get("parent_ids", ())),
            changed_paths=tuple(str(item) for item in value.get("changed_paths", ())),
            labels=tuple(str(item) for item in value.get("labels", ())),
            metadata=dict(metadata),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "repository": self.repository,
            "kind": self.kind,
            "ref": self.ref,
            "sha": self.sha,
            "parent_ids": list(self.parent_ids),
            "changed_paths": list(self.changed_paths),
            "labels": list(self.labels),
            "metadata": dict(self.metadata),
        }


def infer_surfaces(event: HistoricalEvent) -> tuple[str, ...]:
    """Infer engineering surfaces without making them authority claims."""

    surfaces: set[str] = set()
    explicit = event.metadata.get("surfaces", ())
    if isinstance(explicit, Sequence) and not isinstance(explicit, (str, bytes)):
        surfaces.update(str(item) for item in explicit)

    if event.kind in _GITHUB_KINDS:
        surfaces.add("github")
    if event.kind == "release":
        surfaces.add("release")

    message = str(event.metadata.get("message", ""))
    ambient_text = " ".join(
        (event.kind, event.ref, message, " ".join(event.labels))
    ).lower()
    paths = tuple(path.lower() for path in event.changed_paths)
    for surface, pattern in _PATH_SURFACE_PATTERNS:
        if pattern.search(ambient_text) or any(pattern.search(path) for path in paths):
            surfaces.add(surface)

    if event.kind == "commit" and any(
        _SOURCE_PATH.search(path.lower()) for path in event.changed_paths
    ):
        surfaces.add("source")
    if not surfaces:
        surfaces.add("other")
    return tuple(sorted(surfaces))


def infer_intent(event: HistoricalEvent) -> str:
    """Infer a compact plan-step intent from normalized history."""

    explicit = event.metadata.get("intent")
    if explicit:
        return str(explicit)
    message = str(event.metadata.get("message", "")).strip()
    if message:
        head = message.splitlines()[0]
        conventional = re.match(
            r"^(feat|fix|test|docs|ci|build|refactor|perf|chore)"
            r"(?:\([^)]+\))?!?:\s*(.+)$",
            head,
            flags=re.IGNORECASE,
        )
        if conventional:
            return f"{conventional.group(1).lower()}:{conventional.group(2)}"
        return head
    return event.kind.replace("_", "-")


def _episode_key(event: HistoricalEvent) -> str:
    explicit = event.metadata.get("episode") or event.metadata.get("workstream")
    if explicit:
        return str(explicit)
    pr_number = event.metadata.get("pull_request")
    if pr_number:
        return f"{event.repository}:pr-{pr_number}"
    if event.ref:
        return f"{event.repository}:{event.ref}"
    return f"{event.repository}:default"


@dataclass(slots=True)
class _MutableStep:
    step_id: str
    kind: str
    intent: str
    surfaces: tuple[str, ...]
    event_ids: list[str]
    commit_shas: list[str]
    required_authority_classes: set[str]
    dependencies: set[str] = field(default_factory=set)

    @property
    def signature(self) -> tuple[str, str, tuple[str, ...]]:
        return self.kind, self.intent, self.surfaces

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.step_id,
            "kind": self.kind,
            "intent": self.intent,
            "surfaces": list(self.surfaces),
            "count": len(self.event_ids),
            "source_event_ids": list(self.event_ids),
            "commit_shas": list(self.commit_shas),
            "depends_on": sorted(self.dependencies),
            "required_authority_classes": sorted(self.required_authority_classes),
        }


def _authority_classes(event: HistoricalEvent) -> set[str]:
    if "required_authority_classes" in event.metadata:
        explicit = event.metadata["required_authority_classes"]
        if not isinstance(explicit, Sequence) or isinstance(explicit, (str, bytes)):
            raise ValueError("required_authority_classes must be an array")
        return {str(item) for item in explicit}
    if event.kind in {"merge", "pull_request", "review", "branch"}:
        return {"github:write"}
    if event.kind == "release":
        return {"release:publish"}
    if event.kind == "deployment":
        return {"deployment:write"}
    if event.kind == "workflow_run":
        return {"ci:trigger"}
    if event.kind == "issue":
        return {"github:triage"}
    if "iac" in infer_surfaces(event):
        return {"infrastructure:write"}
    return set()


def _build_plan(
    episode_id: str,
    events: Sequence[HistoricalEvent],
    *,
    period: str,
    compact: bool,
) -> dict[str, object]:
    ordered = sorted(events, key=lambda item: (item.timestamp, item.event_id))
    steps: list[_MutableStep] = []
    event_to_step: dict[str, str] = {}

    for event in ordered:
        surfaces = infer_surfaces(event)
        intent = infer_intent(event)
        signature = (event.kind, intent, surfaces)
        if compact and steps and steps[-1].signature == signature:
            step = steps[-1]
            step.event_ids.append(event.event_id)
            if event.sha and event.kind == "commit":
                step.commit_shas.append(event.sha)
            step.required_authority_classes.update(_authority_classes(event))
        else:
            step = _MutableStep(
                step_id=f"s{len(steps):05d}-{_slug(intent)}",
                kind=event.kind,
                intent=intent,
                surfaces=surfaces,
                event_ids=[event.event_id],
                commit_shas=(
                    [event.sha] if event.sha and event.kind == "commit" else []
                ),
                required_authority_classes=_authority_classes(event),
            )
            steps.append(step)
        event_to_step[event.event_id] = step.step_id

    step_by_id = {step.step_id: step for step in steps}
    for index, event in enumerate(ordered):
        step_id = event_to_step[event.event_id]
        step = step_by_id[step_id]
        causal_ids = tuple(event.parent_ids)
        metadata_depends = event.metadata.get("depends_on", ())
        if isinstance(metadata_depends, Sequence) and not isinstance(
            metadata_depends, (str, bytes)
        ):
            causal_ids += tuple(str(item) for item in metadata_depends)

        causal_steps = {
            event_to_step[item]
            for item in causal_ids
            if item in event_to_step and event_to_step[item] != step_id
        }
        if causal_steps:
            step.dependencies.update(causal_steps)
        elif index:
            previous = event_to_step[ordered[index - 1].event_id]
            if previous != step_id:
                step.dependencies.add(previous)

    surface_counts: Counter[str] = Counter()
    for event in ordered:
        surface_counts.update(infer_surfaces(event))

    commit_shas = [
        event.sha for event in ordered if event.kind == "commit" and event.sha
    ]
    event_payload = [event.as_dict() for event in ordered]
    objective = next(
        (
            str(event.metadata["objective"])
            for event in ordered
            if event.metadata.get("objective")
        ),
        f"replay:{episode_id}",
    )
    repositories = sorted({event.repository for event in ordered})
    closure_expected = any(event.kind in _CLOSURE_KINDS for event in ordered)

    payload: dict[str, object] = {
        "schema": PLAN_SCHEMA,
        "episode": {
            "id": episode_id,
            "objective": objective,
            "period": period,
            "repositories": repositories,
        },
        "world": {
            "source_event_count": len(ordered),
            "observed_commit_count": sum(event.kind == "commit" for event in ordered),
            "closure_expected": closure_expected,
        },
        "roles": [
            "planner",
            "implementer",
            "verifier",
            "ci-repair",
            "github-controller",
            "iac-operator",
            "release-controller",
        ],
        "surfaces": dict(sorted(surface_counts.items())),
        "plan": {
            "type": "partial-order",
            "steps": [step.as_dict() for step in steps],
            "edges": sorted(
                [dependency, step.step_id]
                for step in steps
                for dependency in step.dependencies
            ),
        },
        "historical_trace": {
            "event_ids": [event.event_id for event in ordered],
            "commit_shas": commit_shas,
            "event_digest": canonical_digest(event_payload),
        },
        "authority": {
            "mode": "SIMULATION_ONLY",
            "do_authority": False,
            "required_classes_are_descriptive": True,
        },
    }
    payload["plan_digest"] = canonical_digest(payload)
    return payload


def compile_history(
    events: Iterable[HistoricalEvent],
    *,
    period: str,
    reported_commit_count: int | None = None,
    compact: bool = True,
) -> tuple[dict[str, object], tuple[dict[str, object], ...]]:
    """Compile normalized observations into a deterministic planning corpus."""

    event_tuple = tuple(events)
    grouped: dict[str, list[HistoricalEvent]] = defaultdict(list)
    for event in event_tuple:
        grouped[_episode_key(event)].append(event)

    plans = tuple(
        _build_plan(
            episode_id,
            grouped[episode_id],
            period=period,
            compact=compact,
        )
        for episode_id in sorted(grouped)
    )
    observed_commit_count = sum(event.kind == "commit" for event in event_tuple)
    surface_counts: Counter[str] = Counter()
    for event in event_tuple:
        surface_counts.update(infer_surfaces(event))

    manifest: dict[str, object] = {
        "schema": CORPUS_SCHEMA,
        "period": period,
        "reported_commit_count": reported_commit_count,
        "observed_commit_count": observed_commit_count,
        "complete_history_observed": (
            reported_commit_count is not None
            and reported_commit_count == observed_commit_count
        ),
        "source_event_count": len(event_tuple),
        "episode_count": len(plans),
        "repositories": sorted({event.repository for event in event_tuple}),
        "surfaces": dict(sorted(surface_counts.items())),
        "source_digest": canonical_digest(
            [
                event.as_dict()
                for event in sorted(
                    event_tuple,
                    key=lambda item: (
                        item.repository,
                        item.timestamp,
                        item.event_id,
                    ),
                )
            ]
        ),
        "plan_digests": [plan["plan_digest"] for plan in plans],
        "authority": {
            "mode": "SIMULATION_ONLY",
            "do_authority": False,
        },
    }
    manifest["corpus_digest"] = canonical_digest(manifest)
    return manifest, plans


@dataclass(slots=True)
class ReplayWorld:
    """Powerless execution gym over one software-manufacturing planning file."""

    plan: Mapping[str, object]
    completed: list[str] = field(default_factory=list)
    transitions: list[dict[str, object]] = field(default_factory=list)

    def _steps(self) -> tuple[Mapping[str, object], ...]:
        plan_section = self.plan.get("plan")
        if not isinstance(plan_section, Mapping):
            raise ValueError("planning file missing plan object")
        raw_steps = plan_section.get("steps")
        if not isinstance(raw_steps, list):
            raise ValueError("planning file missing plan.steps array")
        return tuple(step for step in raw_steps if isinstance(step, Mapping))

    def admissible_actions(self) -> tuple[str, ...]:
        """Return plan-step ids whose declared dependencies are satisfied."""

        completed = set(self.completed)
        ready: list[str] = []
        for step in self._steps():
            step_id = str(step["id"])
            dependencies = {str(item) for item in step.get("depends_on", ())}
            if step_id not in completed and dependencies.issubset(completed):
                ready.append(step_id)
        return tuple(sorted(ready))

    def apply(self, step_id: str, *, agent: str = "reference-agent") -> None:
        """Apply one simulated action; no external side effect is possible."""

        ready = set(self.admissible_actions())
        if step_id not in ready:
            raise ValueError(
                f"step is not admissible in the current replay state: {step_id}"
            )
        self.completed.append(step_id)
        self.transitions.append(
            {
                "index": len(self.transitions),
                "agent": agent,
                "step_id": step_id,
            }
        )

    def run_reference(self) -> dict[str, object]:
        """Deterministically execute the first admissible action until closure."""

        step_count = len(self._steps())
        while len(self.completed) < step_count:
            ready = self.admissible_actions()
            if not ready:
                raise RuntimeError("planning file contains a dependency deadlock")
            self.apply(ready[0])
        return self.receipt()

    def receipt(self) -> dict[str, object]:
        """Return deterministic replay evidence for the simulated trajectory."""

        step_ids = {str(step["id"]) for step in self._steps()}
        state = "ALIVE" if set(self.completed) == step_ids else "PARTIAL_ALIVE"
        payload: dict[str, object] = {
            "schema": REPLAY_SCHEMA,
            "plan_digest": self.plan.get("plan_digest", ""),
            "state": state,
            "completed_steps": list(self.completed),
            "transitions": list(self.transitions),
            "authority": "NONE",
            "do_authority": False,
            "evidence_kind": "SIMULATION_RECEIPT",
        }
        payload["receipt_sha256"] = canonical_digest(payload)
        return payload


class GithubQueryError(RuntimeError):
    """Raised when a real ``gh api`` call fails or ``gh`` is unavailable."""


def _gh_api(
    path: str,
    *,
    gh_bin: str = "gh",
    paginate: bool = True,
    list_field: str | None = None,
    timeout: float = 60.0,
) -> list[object] | dict[str, object]:
    """Call the real, locally-installed ``gh`` CLI and return parsed JSON.

    This is a real subprocess call against the real GitHub REST API through the
    user's already-authenticated ``gh`` binary -- no mocking, no fixture replay.
    Raises :class:`GithubQueryError` (never a bare ``CalledProcessError``) so
    callers get one typed failure surface for "gh missing" / "not authenticated"
    / "API error", each distinguishable by message.

    Two paginated shapes exist on GitHub's REST API and they need different
    handling, not one guessed unwrap: an endpoint that returns a bare JSON
    array (commits, pulls, releases, issues) slurps cleanly with
    ``--paginate --slurp`` and one flatten pass. An endpoint that wraps its
    array in a named object field (``{"workflow_runs": [...], "total_count":
    N}``) must instead be extracted with ``--jq ".<list_field>[]"`` -- passing
    ``list_field`` here does that and returns newline-delimited objects
    already reassembled into one list. Getting this wrong doesn't error; it
    silently returns an empty list (an earlier version of this function did
    exactly that against ``actions/runs``, confirmed and fixed this session)
    -- which is exactly the failure mode this repo's absence-is-not-evidence
    law warns about, so ``list_field`` is mandatory for object-shaped
    endpoints rather than optional/inferred.
    """

    args = [gh_bin, "api", path]
    if paginate:
        args.append("--paginate")
        if list_field is not None:
            args += ["--jq", f".{list_field}[]"]
        else:
            args.append("--slurp")
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise GithubQueryError(f"gh binary not found: {gh_bin}") from exc
    except subprocess.TimeoutExpired as exc:
        raise GithubQueryError(f"gh api timed out after {timeout}s: {path}") from exc
    if completed.returncode != 0:
        raise GithubQueryError(
            f"gh api failed (exit {completed.returncode}) for {path}: "
            f"{completed.stderr.strip()}"
        )
    if list_field is not None:
        # --jq '.field[]' with --paginate prints one JSON value per line,
        # already merged across pages -- newline-delimited JSON, not one blob.
        return [
            json.loads(line) for line in completed.stdout.splitlines() if line.strip()
        ]
    parsed = json.loads(completed.stdout or "null")
    if paginate and isinstance(parsed, list) and len(parsed) == 1:
        # --paginate --slurp wraps each page in its own array; a single page of
        # a list-returning endpoint slurps to [[...]] -- unwrap one level.
        inner = parsed[0]
        if isinstance(inner, list):
            return inner
    if paginate and isinstance(parsed, list):
        flattened: list[object] = []
        for page in parsed:
            if isinstance(page, list):
                flattened.extend(page)
        if flattened or all(isinstance(page, list) for page in parsed):
            return flattened
    return parsed


def is_github_queryable(*, gh_bin: str = "gh") -> bool:
    """Real, cheap check: is ``gh`` installed and authenticated right now?"""

    try:
        completed = subprocess.run(
            [gh_bin, "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10.0,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


def _in_window(timestamp: str, *, since: str, until: str | None) -> bool:
    if timestamp < since:
        return False
    if until is not None and timestamp >= until:
        return False
    return True


def _commit_events(
    repo: str,
    *,
    since: str,
    until: str | None,
    gh_bin: str,
    include_files: bool,
    file_fetch_limit: int,
) -> list[HistoricalEvent]:
    query = f"repos/{repo}/commits?since={since}&per_page=100"
    if until is not None:
        query += f"&until={until}"
    raw = _gh_api(query, gh_bin=gh_bin)
    items = raw if isinstance(raw, list) else []
    events: list[HistoricalEvent] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            continue
        sha = str(item.get("sha", ""))
        commit = item.get("commit") or {}
        author = commit.get("author") or {} if isinstance(commit, Mapping) else {}
        message = str(commit.get("message", "")) if isinstance(commit, Mapping) else ""
        timestamp = str(author.get("date", "")) if isinstance(author, Mapping) else ""
        parents = item.get("parents") or []
        parent_shas = tuple(
            str(parent.get("sha", ""))
            for parent in parents
            if isinstance(parent, Mapping) and parent.get("sha")
        )
        changed_paths: tuple[str, ...] = ()
        if include_files and index < file_fetch_limit and sha:
            try:
                detail = _gh_api(
                    f"repos/{repo}/commits/{sha}", gh_bin=gh_bin, paginate=False
                )
            except GithubQueryError:
                detail = {}
            files_raw = detail.get("files", []) if isinstance(detail, Mapping) else []
            files = files_raw if isinstance(files_raw, list) else []
            changed_paths = tuple(
                str(f.get("filename", ""))
                for f in files
                if isinstance(f, Mapping) and f.get("filename")
            )
        events.append(
            HistoricalEvent(
                event_id=f"commit-{sha}" if sha else f"commit-{index}",
                timestamp=timestamp,
                repository=repo,
                kind="commit",
                sha=sha,
                parent_ids=parent_shas,
                changed_paths=changed_paths,
                metadata={
                    "message": message,
                    "author": str(author.get("name", ""))
                    if isinstance(author, Mapping)
                    else "",
                },
            )
        )
    return events


def _pull_request_events(
    repo: str, *, since: str, until: str | None, gh_bin: str
) -> list[HistoricalEvent]:
    raw = _gh_api(
        f"repos/{repo}/pulls?state=all&sort=updated&direction=desc&per_page=100",
        gh_bin=gh_bin,
    )
    items = raw if isinstance(raw, list) else []
    events: list[HistoricalEvent] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        created_at = str(item.get("created_at", ""))
        if not _in_window(created_at, since=since, until=until):
            continue
        number = item.get("number")
        merged_at = item.get("merged_at")
        events.append(
            HistoricalEvent(
                event_id=f"pull_request-{number}",
                timestamp=created_at,
                repository=repo,
                kind="pull_request",
                ref=str((item.get("head") or {}).get("ref", ""))
                if isinstance(item.get("head"), Mapping)
                else "",
                metadata={
                    "pull_request": number,
                    "title": str(item.get("title", "")),
                    "state": str(item.get("state", "")),
                    "merged": merged_at is not None,
                },
            )
        )
        if merged_at and _in_window(str(merged_at), since=since, until=until):
            events.append(
                HistoricalEvent(
                    event_id=f"merge-pr-{number}",
                    timestamp=str(merged_at),
                    repository=repo,
                    kind="merge",
                    metadata={
                        "pull_request": number,
                        "title": str(item.get("title", "")),
                    },
                )
            )
    return events


def _created_range_query(*, since: str, until: str | None) -> str:
    """Build a GitHub search-qualifier ``created`` range, URL-encoded.

    Filtering server-side (rather than only client-side in ``_in_window``) is
    load-bearing, not an optimization: without it, ``--paginate`` walks a
    repo's *entire* run/issue history before any window filter ever applies,
    which measurably times out on a repo with hundreds of workflow runs.
    """

    value = f"{since}..{until}" if until is not None else f">={since}"
    return quote(value, safe="")


def _workflow_run_events(
    repo: str, *, since: str, until: str | None, gh_bin: str
) -> list[HistoricalEvent]:
    created = _created_range_query(since=since, until=until)
    raw = _gh_api(
        f"repos/{repo}/actions/runs?per_page=100&created={created}",
        gh_bin=gh_bin,
        list_field="workflow_runs",
    )
    runs = raw if isinstance(raw, list) else []
    events: list[HistoricalEvent] = []
    for item in runs:
        if not isinstance(item, Mapping):
            continue
        created_at = str(item.get("created_at", ""))
        if not _in_window(created_at, since=since, until=until):
            continue
        events.append(
            HistoricalEvent(
                event_id=f"workflow_run-{item.get('id', '')}",
                timestamp=created_at,
                repository=repo,
                kind="workflow_run",
                ref=str(item.get("head_branch", "")),
                sha=str(item.get("head_sha", "")),
                metadata={
                    "name": str(item.get("name", "")),
                    "status": str(item.get("status", "")),
                    "conclusion": str(item.get("conclusion") or ""),
                },
            )
        )
    return events


def _release_events(
    repo: str, *, since: str, until: str | None, gh_bin: str
) -> list[HistoricalEvent]:
    raw = _gh_api(f"repos/{repo}/releases?per_page=100", gh_bin=gh_bin)
    items = raw if isinstance(raw, list) else []
    events: list[HistoricalEvent] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        published_at = str(item.get("published_at") or "")
        if not published_at or not _in_window(published_at, since=since, until=until):
            continue
        events.append(
            HistoricalEvent(
                event_id=f"release-{item.get('id', '')}",
                timestamp=published_at,
                repository=repo,
                kind="release",
                ref=str(item.get("tag_name", "")),
                metadata={
                    "tag_name": str(item.get("tag_name", "")),
                    "name": str(item.get("name", "")),
                },
            )
        )
    return events


def _issue_events(
    repo: str, *, since: str, until: str | None, gh_bin: str
) -> list[HistoricalEvent]:
    raw = _gh_api(
        f"repos/{repo}/issues?state=all&since={since}&per_page=100",
        gh_bin=gh_bin,
    )
    items = raw if isinstance(raw, list) else []
    events: list[HistoricalEvent] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if "pull_request" in item:
            continue  # the issues endpoint also returns PRs; those are covered above
        created_at = str(item.get("created_at", ""))
        if not _in_window(created_at, since=since, until=until):
            continue
        labels = item.get("labels", [])
        events.append(
            HistoricalEvent(
                event_id=f"issue-{item.get('number', '')}",
                timestamp=created_at,
                repository=repo,
                kind="issue",
                labels=tuple(
                    str(label.get("name", ""))
                    if isinstance(label, Mapping)
                    else str(label)
                    for label in (labels if isinstance(labels, list) else [])
                ),
                metadata={
                    "issue": item.get("number"),
                    "title": str(item.get("title", "")),
                    "state": str(item.get("state", "")),
                },
            )
        )
    return events


def _deployment_events(
    repo: str, *, since: str, until: str | None, gh_bin: str
) -> list[HistoricalEvent]:
    try:
        raw = _gh_api(f"repos/{repo}/deployments?per_page=100", gh_bin=gh_bin)
    except GithubQueryError:
        return []
    items = raw if isinstance(raw, list) else []
    events: list[HistoricalEvent] = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        created_at = str(item.get("created_at", ""))
        if not _in_window(created_at, since=since, until=until):
            continue
        events.append(
            HistoricalEvent(
                event_id=f"deployment-{item.get('id', '')}",
                timestamp=created_at,
                repository=repo,
                kind="deployment",
                ref=str(item.get("ref", "")),
                sha=str(item.get("sha", "")),
                metadata={"environment": str(item.get("environment", ""))},
            )
        )
    return events


_GH_EVENT_BUILDERS = {
    "commit": _commit_events,
    "pull_request": _pull_request_events,
    "workflow_run": _workflow_run_events,
    "release": _release_events,
    "issue": _issue_events,
    "deployment": _deployment_events,
}


def fetch_github_events(
    repo: str,
    *,
    since: str,
    until: str | None = None,
    kinds: Sequence[str] = GITHUB_FETCHABLE_KINDS,
    gh_bin: str = "gh",
    include_commit_files: bool = True,
    commit_file_limit: int = 25,
) -> tuple[HistoricalEvent, ...]:
    """Query real GitHub history for ``repo`` via the real, authenticated ``gh``
    CLI and normalize it into :class:`HistoricalEvent` observations.

    This is observation only -- see the module docstring. ``since``/``until``
    are ISO-8601 timestamps (``YYYY-MM-DDTHH:MM:SSZ``). Every requested kind
    that GitHub actually returns data for becomes a distinct admissible
    plan-step kind once compiled, widening the planner/agent action frontier
    beyond commits alone (the more kinds fetched, the more distinct step
    kinds -- pull_request, review-bearing merge, workflow_run, release, issue,
    deployment -- an agent can choose among in :class:`ReplayWorld`).
    """

    events: list[HistoricalEvent] = []
    for kind in kinds:
        builder = _GH_EVENT_BUILDERS.get(kind)
        if builder is None:
            raise ValueError(f"no real GitHub normalizer registered for kind: {kind}")
        if kind == "commit":
            events.extend(
                builder(
                    repo,
                    since=since,
                    until=until,
                    gh_bin=gh_bin,
                    include_files=include_commit_files,
                    file_fetch_limit=commit_file_limit,
                )
            )
        else:
            events.extend(builder(repo, since=since, until=until, gh_bin=gh_bin))
    return tuple(sorted(events, key=lambda item: (item.timestamp, item.event_id)))


def load_events(path: Path) -> tuple[HistoricalEvent, ...]:
    """Load either a JSON array or an object containing an ``events`` array."""

    raw = json.loads(path.read_text())
    if isinstance(raw, Mapping):
        raw = raw.get("events")
    if not isinstance(raw, list):
        raise ValueError("history export must be a JSON array or {events: [...]}")
    return tuple(
        HistoricalEvent.from_mapping(item) for item in raw if isinstance(item, Mapping)
    )


def write_corpus(
    output_dir: Path,
    manifest: Mapping[str, object],
    plans: Sequence[Mapping[str, object]],
) -> tuple[Path, ...]:
    """Write deterministic planning files and return all created paths."""

    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
    created.append(manifest_path)

    for plan in plans:
        episode = plan.get("episode")
        if not isinstance(episode, Mapping):
            raise ValueError("planning file missing episode")
        episode_id = _slug(str(episode.get("id", "episode")))
        path = output_dir / f"{episode_id}.plan.json"
        path.write_text(json.dumps(plan, sort_keys=True, indent=2) + "\n")
        created.append(path)
    return tuple(created)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compile and replay software-manufacturing history."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("history", type=Path)
    compile_parser.add_argument("output", type=Path)
    compile_parser.add_argument("--period", required=True)
    compile_parser.add_argument("--reported-commit-count", type=int)
    compile_parser.add_argument("--no-compact", action="store_true")

    replay_parser = subparsers.add_parser("replay")
    replay_parser.add_argument("plan", type=Path)

    fetch_parser = subparsers.add_parser(
        "fetch", help="query real GitHub history via the local gh CLI"
    )
    fetch_parser.add_argument(
        "repo", help="owner/name, e.g. seanchatmangpt/autofde-lab"
    )
    fetch_parser.add_argument("output", type=Path, help="events JSON file to write")
    fetch_parser.add_argument(
        "--since", required=True, help="ISO-8601, e.g. 2026-08-01T00:00:00Z"
    )
    fetch_parser.add_argument("--until", default=None)
    fetch_parser.add_argument(
        "--kinds",
        nargs="+",
        default=list(GITHUB_FETCHABLE_KINDS),
        choices=list(GITHUB_FETCHABLE_KINDS),
        help="which real GitHub event kinds to query (default: all fetchable kinds)",
    )
    fetch_parser.add_argument("--no-commit-files", action="store_true")
    fetch_parser.add_argument("--commit-file-limit", type=int, default=25)
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    if args.command == "compile":
        events = load_events(args.history)
        manifest, plans = compile_history(
            events,
            period=args.period,
            reported_commit_count=args.reported_commit_count,
            compact=not args.no_compact,
        )
        created = write_corpus(args.output, manifest, plans)
        print(
            json.dumps(
                {
                    "corpus_digest": manifest["corpus_digest"],
                    "created": [str(path) for path in created],
                    "observed_commit_count": manifest["observed_commit_count"],
                    "reported_commit_count": manifest["reported_commit_count"],
                },
                sort_keys=True,
                indent=2,
            )
        )
        return

    if args.command == "fetch":
        events = fetch_github_events(
            args.repo,
            since=args.since,
            until=args.until,
            kinds=args.kinds,
            include_commit_files=not args.no_commit_files,
            commit_file_limit=args.commit_file_limit,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(
                {"events": [e.as_dict() for e in events]}, sort_keys=True, indent=2
            )
            + "\n"
        )
        kind_counts = Counter(event.kind for event in events)
        print(
            json.dumps(
                {
                    "repository": args.repo,
                    "since": args.since,
                    "until": args.until,
                    "written_to": str(args.output),
                    "event_count": len(events),
                    "kind_counts": dict(sorted(kind_counts.items())),
                },
                sort_keys=True,
                indent=2,
            )
        )
        return

    plan = json.loads(args.plan.read_text())
    receipt = ReplayWorld(plan).run_reference()
    print(json.dumps(receipt, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
