#!/usr/bin/env python3
"""Clean-checkout verification receipt.

Mechanically receipts the load-bearing portability claim of this repository:

    A clean checkout runs the agent-loop suites with no sibling repository
    readable -- not ~/mfw, ~/bcinr, ~/ggen, ~/mfact, ~/praxis, ~/ferroplan,
    ~/wasm4pm-compat -- and with no cloud credentials.

What this script does, in order:

1. ``git clone`` the source repo into a temp dir and check out the exact
   current HEAD commit. The clone is from the local repo, so the receipt
   covers *committed* state only -- an uncommitted working tree is invisible
   to it, by construction, and the dirty-tree flag is recorded in the JSON.
2. Build an environment in the clone with ``uv sync`` (extras selectable;
   see ``--extra``).
3. Run the target suites **by path**. Whole-suite collection is BUILD_BROKEN
   in this repo (basename collision on ``test_pomcp.py`` plus three
   ``test_self_play_dspy_*_chicago.py`` import failures); this script never
   attempts whole-suite collection and never tries to repair it.
4. Run each suite under an environment where the sibling repositories are
   unreachable: ``HOME``/``USERPROFILE`` point at an empty directory and
   every ``*_HOME`` sibling override points at a nonexistent path. The
   variable names and the empty-HOME pattern are taken from
   ``tests/adapters/test_adapters.py``; they are not re-invented here.
5. Emit a JSON receipt with the commit SHA, interpreter, platform, extras,
   per-suite outcome counts, wall clock, every skip with its reason, and the
   sibling paths proven unreachable.
6. Classify every skip into exactly two disjoint classes, never merged:

   * ``UNSUPPORTED`` -- gated on a missing optional dependency or absent
     external tool. An environment gate, not incomplete work.
   * ``RECORDED_NEGATIVE`` -- carries a named blocker (``BLOCKED:<REASON>``).
     This is evidence. It is not a defect and must never be "fixed".

   Anything matching neither is reported as ``UNCLASSIFIED_SKIP`` rather than
   silently folded into one of them.
7. Exit non-zero on any test FAILURE or ERROR. A skip alone never fails the
   receipt.

The receipt is a ``technicalStanding`` artifact only. It says nothing about
organizational or enterprise standing.

Usage::

    python scripts/clean_checkout_receipt.py --out docs/release/receipt.json

"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants that must stay in sync with the repo's own tests
# ---------------------------------------------------------------------------

#: Sibling-repo env overrides. Copied verbatim from ``ENV_OVERRIDES`` in
#: ``tests/adapters/test_adapters.py`` -- do not invent new names here.
SIBLING_ENV_OVERRIDES = (
    "MFW_HOME",
    "BCINR_HOME",
    "FERROPLAN_HOME",
    "MFACT_HOME",
    "GGEN_HOME",
    "OPENCLAW_HOME",
    "WASM4PM_COMPAT_HOME",
)

#: Sibling repositories that must be unreachable during the run. Names are
#: resolved against the *real* home so the receipt can state which of them
#: actually exist on this machine (isolating a path that never existed proves
#: nothing).
SIBLING_DIR_NAMES = (
    "mfw",
    "bcinr",
    "ggen",
    "ggen-create",
    "ggen-legacy",
    "mfact",
    "praxis",
    "ferroplan",
    "wasm4pm",
    "wasm4pm-compat",
    "openclaw",
    "ostar",
)

#: Suites under test, run by path, one pytest invocation each.
TARGET_SUITES = (
    "tests/powl",
    "tests/agent",
    "tests/ocel",
    "tests/adapters",
    "tests/autofde",
    "tests/fabric",
    "tests/ecosystem",
)

#: Credential-ish environment variables stripped from the run environment.
CREDENTIAL_ENV_PREFIXES = (
    "AWS_",
    "AZURE_",
    "GOOGLE_",
    "GCP_",
    "OPENAI_",
    "ANTHROPIC_",
    "HF_",
    "GH_",
    "GITHUB_",
    "DOCKER_",
    "TF_",
)

#: A skip whose reason matches this is a *recorded negative*: a named blocker.
BLOCKED_RE = re.compile(r"BLOCKED:[A-Z0-9_]+")

#: A skip whose reason matches this is an environment gate -> UNSUPPORTED.
UNSUPPORTED_RE = re.compile(
    r"(?i)\b("
    r"could not import|no module named|not installed|requires? [\w.\-\[\]]+|"
    r"unavailable|not available|missing|absent from the environment|"
    r"UNSUPPORTED|not on PATH|executable not found|optional (extra|dependency)"
    r")\b"
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class SkipRecord:
    suite: str
    location: str
    reason: str
    classification: str  # UNSUPPORTED | RECORDED_NEGATIVE | UNCLASSIFIED_SKIP


@dataclass
class SuiteResult:
    suite: str
    exists: bool
    returncode: int
    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    xfailed: int = 0
    xpassed: int = 0
    wall_clock_s: float = 0.0
    status: str = "UNKNOWN"
    stdout_tail: str = ""
    failure_detail: str = ""
    failure_ids: list[str] = field(default_factory=list)


def classify_skip(reason: str) -> str:
    """Two disjoint classes, plus an explicit escape hatch.

    A named blocker wins over an environment-gate match: ``BLOCKED:X`` is a
    deliberate recorded negative even when its prose also mentions something
    being absent.
    """
    if BLOCKED_RE.search(reason):
        return "RECORDED_NEGATIVE"
    if UNSUPPORTED_RE.search(reason):
        return "UNSUPPORTED"
    return "UNCLASSIFIED_SKIP"


# ---------------------------------------------------------------------------
# Shell helpers
# ---------------------------------------------------------------------------


def run(
    cmd: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def git(repo: Path, *args: str) -> str:
    proc = run(["git", *args], cwd=repo)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


# ---------------------------------------------------------------------------
# Isolation environment
# ---------------------------------------------------------------------------


def build_isolated_env(clone: Path, empty_home: Path, venv_bin: Path) -> dict[str, str]:
    """Environment with no sibling repo and no cloud credentials reachable.

    Reuses the pattern from ``tests/adapters/test_adapters.py``: HOME and
    USERPROFILE at an empty directory, every sibling ``*_HOME`` at a
    nonexistent path.

    PATH is narrowed to the clone's venv plus the system directories only --
    ``~/.local/bin`` and Homebrew are deliberately excluded, since a tool
    found there would be a reachability channel the receipt did not account
    for. ``git`` and standard utilities remain available from ``/usr/bin``.
    """
    nonexistent = empty_home / "nonexistent-sibling"
    env: dict[str, str] = {
        "HOME": str(empty_home),
        "USERPROFILE": str(empty_home),
        "PATH": os.pathsep.join([str(venv_bin), "/usr/bin", "/bin", "/usr/sbin", "/sbin"]),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TMPDIR": str(empty_home / "tmp"),
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "VIRTUAL_ENV": str(clone / ".venv"),
        # Belt and braces: no implicit reach back into the developer's home.
        "XDG_CONFIG_HOME": str(empty_home / ".config"),
        "XDG_CACHE_HOME": str(empty_home / ".cache"),
        "XDG_DATA_HOME": str(empty_home / ".local" / "share"),
    }
    for var in SIBLING_ENV_OVERRIDES:
        env[var] = str(nonexistent)
    (empty_home / "tmp").mkdir(parents=True, exist_ok=True)
    return env


def probe_sibling_reachability(empty_home: Path, real_home: Path) -> dict[str, Any]:
    """Record, per sibling, whether it exists in the real home and whether it
    is reachable from the isolated home.

    A sibling that does not exist on this machine is reported as such: it
    contributes no evidence of isolation, and pretending otherwise would
    overstate the receipt.
    """
    entries = []
    for name in SIBLING_DIR_NAMES:
        real = real_home / name
        iso = empty_home / name
        entries.append(
            {
                "sibling": name,
                "real_path": str(real),
                "exists_in_real_home": real.exists(),
                "isolated_path": str(iso),
                "reachable_from_isolated_home": iso.exists(),
            }
        )
    proven = [e["sibling"] for e in entries if e["exists_in_real_home"] and not e["reachable_from_isolated_home"]]
    vacuous = [e["sibling"] for e in entries if not e["exists_in_real_home"]]
    leaked = [e["sibling"] for e in entries if e["reachable_from_isolated_home"]]
    return {
        "entries": entries,
        "proven_unreachable": proven,
        "vacuous_absent_on_this_machine": vacuous,
        "leaked_reachable": leaked,
    }


def scan_for_absolute_sibling_paths(clone: Path) -> list[str]:
    """Static leak check: a hardcoded absolute sibling path in the tree would
    bypass every env override above. Reported, not repaired.
    """
    hits: list[str] = []
    pattern = re.compile(
        r"[\"'](/(?:Users|home)/[^\"'\s]+/(?:" + "|".join(re.escape(n) for n in SIBLING_DIR_NAMES) + r")(?:/[^\"'\s]*)?)[\"']"
    )
    for root in ("src", "tests", "scripts"):
        base = clone / root
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for m in pattern.finditer(text):
                hits.append(f"{path.relative_to(clone)}: {m.group(1)}")
    return sorted(set(hits))


# ---------------------------------------------------------------------------
# pytest parsing
# ---------------------------------------------------------------------------

_COUNT_RE = re.compile(r"(\d+) (passed|failed|error|errors|skipped|xfailed|xpassed|deselected)")
_SUMMARY_TAIL_RE = re.compile(r"\bin \d+(?:\.\d+)?s\b")
_SHORT_SKIP_RE = re.compile(r"^SKIPPED \[(\d+)\] ([^:]+:\d+): (.*)$")
_SKIP_LINE_RE = re.compile(r"^(?:SKIPPED|s)\s")


def parse_pytest_output(text: str) -> dict[str, int]:
    """Parse the final counts line.

    Under ``-q`` the summary has no leading ``=`` (it reads
    ``3 failed, 100 passed, 26 skipped in 51.92s``), so anchoring on ``=``
    silently yields all zeros -- which is exactly how an earlier revision of
    this script reported ALIVE over a red suite. Match the trailing
    ``... in <n>s`` shape instead, decorated or not, last one wins.
    """
    counts = {k: 0 for k in ("passed", "failed", "errors", "skipped", "xfailed", "xpassed")}
    for raw in text.splitlines():
        line = raw.strip().strip("=").strip()
        if not _SUMMARY_TAIL_RE.search(line):
            continue
        found = _COUNT_RE.findall(line)
        if not found:
            continue
        for key in counts:
            counts[key] = 0
        for num, kind in found:
            key = "errors" if kind in ("error", "errors") else kind
            if key in counts:
                counts[key] = int(num)
    return counts


def parse_skips(text: str, suite: str) -> list[SkipRecord]:
    """Parse ``-ra`` short-summary SKIPPED lines.

    ``-ra`` is already in ``addopts``; this parses its output rather than
    depending on a plugin.
    """
    records: list[SkipRecord] = []
    for raw in text.splitlines():
        line = raw.strip()
        m = _SHORT_SKIP_RE.match(line)
        if m:
            count, loc, reason = m.group(1), m.group(2), m.group(3).strip()
            for _ in range(int(count)):
                records.append(
                    SkipRecord(suite=suite, location=loc, reason=reason, classification=classify_skip(reason))
                )
            continue
        if line.startswith("SKIPPED "):
            reason = line[len("SKIPPED ") :].strip()
            records.append(
                SkipRecord(suite=suite, location="<unparsed>", reason=reason, classification=classify_skip(reason))
            )
    return records


def extract_failure_detail(text: str, limit: int = 20000) -> str:
    """Keep the FAILURES/ERRORS blocks verbatim.

    Without this the receipt records that a suite went red but not why, which
    makes it useless for the one question it exists to answer.
    """
    lines = text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if re.search(r"=+ (FAILURES|ERRORS) =+", line):
            start = i
            break
    if start is None:
        return text.strip()[-limit:]
    return "\n".join(lines[start:])[:limit]


def parse_failure_ids(text: str) -> list[str]:
    ids: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(("FAILED ", "ERROR ")):
            ids.append(line)
    return ids


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default=str(Path(__file__).resolve().parents[1]), help="source repo to clone")
    ap.add_argument(
        "--extra",
        action="append",
        default=None,
        help="uv extra to install; repeatable. Default: none (base deps + dev/test groups).",
    )
    ap.add_argument("--out", default=None, help="write JSON receipt here (also printed to stdout)")
    ap.add_argument("--keep", action="store_true", help="keep the temp clone and record its path")
    ap.add_argument("--sync-timeout", type=int, default=3600)
    ap.add_argument("--suite-timeout", type=int, default=1800)
    args = ap.parse_args()

    source = Path(args.source).resolve()
    extras: list[str] = args.extra or []
    started = time.time()
    started_iso = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(started))

    head = git(source, "rev-parse", "HEAD")
    branch = git(source, "rev-parse", "--abbrev-ref", "HEAD")
    dirty = bool(git(source, "status", "--porcelain"))

    tmp = Path(tempfile.mkdtemp(prefix="autofde_lab-clean-checkout-"))
    clone = tmp / "checkout"
    empty_home = tmp / "empty-home"
    empty_home.mkdir()

    receipt: dict[str, Any] = {
        "artifact": "clean-checkout-verification-receipt",
        "standing_dimension": "technicalStanding",
        "standing_note": (
            "This receipt is a technicalStanding artifact only. It says nothing about "
            "organizationalStanding or enterpriseStanding."
        ),
        "started_at": started_iso,
        "source_repo": str(source),
        "commit_sha": head,
        "branch": branch,
        "source_working_tree_dirty": dirty,
        "clone_path": str(clone),
        "clone_retained": bool(args.keep),
        "python_used_to_drive": sys.version,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "platform": platform.platform(),
        },
        "extras_requested": extras,
        "target_suites": list(TARGET_SUITES),
        "whole_suite_collection": "BUILD_BROKEN (known; run by path, not repaired here)",
    }

    try:
        # -- 1. clone at exact HEAD -----------------------------------------
        t0 = time.time()
        proc = run(["git", "clone", "--no-hardlinks", "--quiet", str(source), str(clone)], timeout=1800)
        if proc.returncode != 0:
            receipt["status"] = "BLOCKED:GIT_CLONE_FAILED"
            receipt["detail"] = proc.stderr.strip()[-4000:]
            return emit(receipt, args, tmp, 1)
        co = run(["git", "checkout", "--quiet", head], cwd=clone)
        if co.returncode != 0:
            receipt["status"] = "BLOCKED:GIT_CHECKOUT_FAILED"
            receipt["detail"] = co.stderr.strip()[-4000:]
            return emit(receipt, args, tmp, 1)
        # The compiled hub is built from git submodules under cpp/sdk/. A plain
        # clone leaves those directories empty and CMake configuration fails --
        # measured, not assumed. A true clean checkout is recursive.
        sub = run(
            ["git", "submodule", "update", "--init", "--recursive", "--depth", "1", "--jobs", "4"],
            cwd=clone,
            timeout=1800,
        )
        receipt["submodule_init_returncode"] = sub.returncode
        if sub.returncode != 0:
            receipt["status"] = "BLOCKED:GIT_SUBMODULE_INIT_FAILED"
            receipt["detail"] = sub.stderr.strip()[-4000:]
            return emit(receipt, args, tmp, 1)
        receipt["submodules"] = [
            line.strip() for line in run(["git", "submodule", "status"], cwd=clone).stdout.splitlines()
        ]
        receipt["clone_sha"] = git(clone, "rev-parse", "HEAD")
        receipt["clone_wall_clock_s"] = round(time.time() - t0, 2)
        assert receipt["clone_sha"] == head, "clone is not at source HEAD"

        # -- 2. build the environment ---------------------------------------
        uv = shutil.which("uv")
        if uv is None:
            receipt["status"] = "BLOCKED:UV_NOT_ON_PATH"
            return emit(receipt, args, tmp, 1)
        sync_cmd = [uv, "sync"]
        for e in extras:
            sync_cmd.append(f"--extra={e}")
        t0 = time.time()
        try:
            sync = run(sync_cmd, cwd=clone, timeout=args.sync_timeout)
        except subprocess.TimeoutExpired:
            receipt["status"] = f"BLOCKED:UV_SYNC_TIMEOUT_AFTER_{args.sync_timeout}S"
            receipt["sync_command"] = " ".join(sync_cmd)
            return emit(receipt, args, tmp, 1)
        receipt["sync_command"] = " ".join(sync_cmd)
        receipt["sync_wall_clock_s"] = round(time.time() - t0, 2)
        receipt["sync_returncode"] = sync.returncode
        if sync.returncode != 0:
            receipt["status"] = "BLOCKED:UV_SYNC_FAILED"
            receipt["sync_stderr_tail"] = sync.stderr.strip()[-6000:]
            return emit(receipt, args, tmp, 1)

        venv_bin = clone / ".venv" / "bin"
        py = venv_bin / "python"
        if not py.exists():
            receipt["status"] = "BLOCKED:VENV_PYTHON_MISSING"
            return emit(receipt, args, tmp, 1)

        # -- 3/4. isolation --------------------------------------------------
        env = build_isolated_env(clone, empty_home, venv_bin)
        real_home = Path(os.path.expanduser("~"))
        receipt["isolation"] = {
            "home": str(empty_home),
            "sibling_env_overrides": {k: env[k] for k in SIBLING_ENV_OVERRIDES},
            "path": env["PATH"],
            "credential_env_stripped": True,
            "credential_env_prefixes_excluded": list(CREDENTIAL_ENV_PREFIXES),
            "inherited_env_vars": sorted(env),
            "siblings": probe_sibling_reachability(empty_home, real_home),
            "static_absolute_sibling_path_hits": scan_for_absolute_sibling_paths(clone),
        }

        ver = run([str(py), "-c", "import sys,platform;print(sys.version.split()[0]);print(platform.platform())"], env=env)
        receipt["target_python_version"] = ver.stdout.splitlines()[0] if ver.stdout else "UNKNOWN"
        freeze = run([str(py), "-m", "pip", "freeze"], env=env)
        receipt["installed_packages"] = sorted(
            line.strip() for line in freeze.stdout.splitlines() if line.strip() and not line.startswith("#")
        )

        # -- run the suites --------------------------------------------------
        results: list[SuiteResult] = []
        skips: list[SkipRecord] = []
        for suite in TARGET_SUITES:
            spath = clone / suite
            if not spath.exists():
                results.append(SuiteResult(suite=suite, exists=False, returncode=-1, status="MISSING"))
                continue
            t0 = time.time()
            try:
                proc = run(
                    [str(py), "-m", "pytest", suite, "-p", "no:cacheprovider", "-ra", "-q"],
                    cwd=clone,
                    env=env,
                    timeout=args.suite_timeout,
                )
                out = proc.stdout + "\n" + proc.stderr
                rc = proc.returncode
            except subprocess.TimeoutExpired as exc:
                out = (exc.stdout or b"").decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                rc = 124
            elapsed = round(time.time() - t0, 2)
            counts = parse_pytest_output(out)
            suite_skips = parse_skips(out, suite)
            skips.extend(suite_skips)
            status = (
                "TIMEOUT"
                if rc == 124
                else "PASS"
                if rc == 0
                else "NO_TESTS_COLLECTED"
                if rc == 5
                else "FAIL"
            )
            results.append(
                SuiteResult(
                    suite=suite,
                    exists=True,
                    returncode=rc,
                    wall_clock_s=elapsed,
                    status=status,
                    stdout_tail=out.strip()[-1200:],
                    # Failure detail must survive: a tail alone shows the skip
                    # summary and drops the tracebacks entirely.
                    failure_detail=extract_failure_detail(out) if status != "PASS" else "",
                    failure_ids=parse_failure_ids(out),
                    **counts,
                )
            )

        receipt["suites"] = [asdict(r) for r in results]
        receipt["skips"] = [asdict(s) for s in skips]
        receipt["skip_classification"] = {
            "UNSUPPORTED": sum(1 for s in skips if s.classification == "UNSUPPORTED"),
            "RECORDED_NEGATIVE": sum(1 for s in skips if s.classification == "RECORDED_NEGATIVE"),
            "UNCLASSIFIED_SKIP": sum(1 for s in skips if s.classification == "UNCLASSIFIED_SKIP"),
            "note": (
                "UNSUPPORTED = environment gate (missing optional extra or external tool). "
                "RECORDED_NEGATIVE = a named BLOCKED:<REASON> -- this is evidence, not a defect, "
                "and must never be 'fixed'. These two are never summed into one number."
            ),
        }
        receipt["totals"] = {
            "passed": sum(r.passed for r in results),
            "failed": sum(r.failed for r in results),
            "errors": sum(r.errors for r in results),
            "skipped": sum(r.skipped for r in results),
            "xfailed": sum(r.xfailed for r in results),
            "xpassed": sum(r.xpassed for r in results),
        }
        receipt["total_wall_clock_s"] = round(time.time() - started, 2)

        # Returncode is primary, parsed counts are corroborating only. An
        # earlier revision derived the verdict from the counts alone; a
        # parsing bug zeroed them and the receipt reported ALIVE over a suite
        # that had exited 1. A suite that went red must be able to fail the
        # receipt even if no count was parsed at all.
        red_suites = [r.suite for r in results if r.exists and r.returncode not in (0, 5)]
        bad = len(red_suites) + receipt["totals"]["failed"] + receipt["totals"]["errors"]
        receipt["red_suites"] = red_suites
        timeouts = [r.suite for r in results if r.status == "TIMEOUT"]
        missing = [r.suite for r in results if r.status == "MISSING"]
        leaked = receipt["isolation"]["siblings"]["leaked_reachable"]
        # Anti-vacuity: a suite that exited 0 while collecting nothing is not
        # evidence of anything, and must never read as a green row.
        vacuous = [r.suite for r in results if r.exists and r.status == "PASS" and r.passed == 0]
        receipt["vacuous_suites"] = vacuous
        if timeouts:
            receipt["status"] = "BLOCKED:SUITE_TIMEOUT"
        elif bad:
            receipt["status"] = "BUILD_BROKEN"
        elif missing or leaked or vacuous:
            receipt["status"] = "PARTIAL_ALIVE"
        else:
            receipt["status"] = "ALIVE"
        receipt["self_containment_claim"] = (
            "ESTABLISHED"
            if receipt["status"] == "ALIVE"
            else "PARTIALLY_ESTABLISHED"
            if receipt["status"] == "PARTIAL_ALIVE"
            else "REFUTED"
            if receipt["status"] == "BUILD_BROKEN"
            else "UNKNOWN"
        )
        exit_code = 0 if bad == 0 and not timeouts else 1
        return emit(receipt, args, tmp, exit_code)
    finally:
        if not args.keep and tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)


def emit(receipt: dict[str, Any], args: argparse.Namespace, tmp: Path, code: int) -> int:
    receipt.setdefault("total_wall_clock_s", None)
    receipt["exit_code"] = code
    text = json.dumps(receipt, indent=2, sort_keys=False)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + "\n", encoding="utf-8")
    print(text)
    if args.keep:
        print(f"\n# temp clone retained at: {tmp}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
