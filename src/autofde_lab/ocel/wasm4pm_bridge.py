# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Bridge to the real ``wpm`` (wasm4pm-cli) binary for process discovery and
token-based-replay conformance checking, over this repo's own OCEL logs.

This repo does not reimplement discovery or conformance checking in Python
(no ``pm4py`` dependency, per an explicit instruction this session, given
``pm4py``'s restrictive license): it shells out to a real, independently
built and tested Rust binary -- ``~/wasm4pm``'s ``wasm4pm-cli`` (``wpm``) --
via :func:`autofde_lab.fabric.bounded_exec.run_subprocess_bounded`, the same
subprocess-with-timeout pattern already used elsewhere in this repo (see that
module's own docstring for why a bare blocking ``subprocess.run()`` is unsafe
from a coroutine).

``wpm mining discover --algo ilp-petri-net`` mines a real Petri net from an
event log (ILP-based discovery, ``wasm4pm/wasm4pm/src/ilp_discovery.rs``);
``wpm mining conformance`` replays a log against that Petri net with a real
token-based-replay engine (``wasm4pm/wasm4pm/src/conformance.rs``, citing
van der Aalst 2016) and reports per-case fitness and named deviations. Both
commands were stub ``anyhow::bail!``s before this session's fix to
``crates/wasm4pm-cli/src/commands/mining.rs``.

``wpm mining drift`` detects concept drift (windowed Jaccard + total-variation
distance over consecutive trace windows, Bose/van der Aalst/Žliobaitė/
Pechenizkiy 2011/2014); ``wpm mining predict-duration`` predicts remaining
case duration from a bucketed mean-remaining-time estimator. Both reuse
``wasm4pm``'s tested distance/windowing primitives directly rather than going
through ``wasm4pm::prediction_drift::detect_drift`` /
``wasm4pm::prediction_remaining_time::{build_remaining_time_model,
predict_case_duration}`` themselves: those functions are
``#[wasm_bindgen]``-only (their success value is a ``JsValue``-wrapped JSON
string, unreadable natively via ``JsValue::as_string()`` -- confirmed by
running them off wasm32 this session, not assumed) so the CLI computes the
same tested math directly instead (see ``mining.rs``'s ``Drift``/
``PredictDuration`` command docs). ``predict-duration``'s estimator is
deliberately simpler than ``wasm4pm``'s full bucketed+Weibull
``RemainingTimeModel`` (bucket-mean only, no survival model) -- named here so
the difference isn't silently claimed as equivalent.

Like :mod:`autofde_lab.ocel.powl_replay`, this module only *computes and
reports* -- it never actuates, admits, or issues a receipt implying anything
was authorized. A conformance report is evidence about a log, nothing more.

Requires a built ``wpm`` binary (``cargo build -p wasm4pm-cli`` inside
``~/wasm4pm``, pinned toolchain ``nightly-2026-04-15``) discoverable via the
``WASM4PM_CLI`` environment variable or on ``PATH``; if neither resolves,
callers get :class:`Wasm4pmUnavailable` -- this repo's ``UNSUPPORTED``
vocabulary for an absent optional external tool, not a crash.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from autofde_lab.fabric.bounded_exec import run_subprocess_bounded

__all__ = [
    "Wasm4pmUnavailable",
    "TraceDeviation",
    "DiscoveryResult",
    "ConformanceReport",
    "DriftPoint",
    "PredictionResult",
    "resolve_wpm_binary",
    "session_traces_to_wasm4pm_json",
    "discover_petri_net",
    "check_conformance",
    "detect_drift",
    "predict_remaining_duration",
]

ACTIVITY_KEY = "concept:name"


class Wasm4pmUnavailable(RuntimeError):
    """Raised when no built ``wpm`` binary can be found."""


@dataclass(frozen=True)
class TraceDeviation:
    case_id: str
    trace_fitness: float
    tokens_missing: int
    tokens_remaining: int


@dataclass(frozen=True)
class DiscoveryResult:
    places: int
    transitions: int
    arcs: int
    simplicity: float
    self_fitness: float
    model_path: Path


@dataclass(frozen=True)
class ConformanceReport:
    avg_fitness: float
    conforming_cases: int
    total_cases: int
    deviations: list[TraceDeviation] = field(default_factory=list)
    precision: float | None = None
    """ETConformance precision (Muñoz-Gama & Carmona), from
    ``wasm4pm::etconformance_precision::compute_precision``. ``None`` only if an older
    ``wpm`` build (pre-precision-wiring) is in use and the table row is absent.
    """
    generalization: float | None = None
    """Token-based generalization (Buijs et al. 2012), from
    ``wasm4pm::generalization::compute_quality``. Together with ``avg_fitness`` and
    ``precision`` this closes 3 of van der Aalst's 4 process-mining quality dimensions
    (the 4th, simplicity, is a property of the discovered model alone -- see
    :attr:`DiscoveryResult.simplicity`, not this report). ``None`` only if an older
    ``wpm`` build (pre-generalization-wiring) is in use and the table row is absent.
    """


@dataclass(frozen=True)
class DriftPoint:
    position: int
    jaccard_distance: float
    tv_distance: float
    method: str
    """``"jaccard"``, ``"tv"``, or ``"both"`` -- which signal(s) crossed the threshold."""


@dataclass(frozen=True)
class PredictionResult:
    remaining_ms: float
    method: str
    """``"bucket(activity,prefix_len)"``, ``"activity_avg(activity)"``, or
    ``"global_fallback"`` -- which estimator tier produced the prediction.
    """


def resolve_wpm_binary() -> str:
    """Locate the built ``wpm`` binary, or raise :class:`Wasm4pmUnavailable`.

    Checks ``WASM4PM_CLI`` first, then ``~/wasm4pm/target/{debug,release}/wpm``,
    then ``PATH`` -- mirroring how ``bounded_exec``-based callers elsewhere in
    this repo resolve an external tool without hardcoding one machine's layout.
    """
    env_path = os.environ.get("WASM4PM_CLI")
    if env_path and Path(env_path).is_file():
        return env_path

    for profile in ("debug", "release"):
        candidate = Path.home() / "wasm4pm" / "target" / profile / "wpm"
        if candidate.is_file():
            return str(candidate)

    found = shutil.which("wpm")
    if found:
        return found

    raise Wasm4pmUnavailable(
        "no built 'wpm' binary found (checked $WASM4PM_CLI, "
        "~/wasm4pm/target/{debug,release}/wpm, and PATH) -- build it with "
        "'cargo +nightly-2026-04-15 build -p wasm4pm-cli' inside ~/wasm4pm"
    )


def _string_attr(key: str, value: str) -> dict:
    return {"key": key, "value": {"type": "String", "content": value}, "own_attributes": None}


def session_traces_to_wasm4pm_json(
    conn: sqlite3.Connection, session_ids: list[str]
) -> dict:
    """Build a ``wasm4pm-compat::event_log::EventLog`` JSON document.

    One trace per session id, using :func:`autofde_lab.ocel.queries.session_event_order`
    (real, timestamp-ordered per-session event lists already in this repo) as
    the source of each trace's event sequence. Shape confirmed against
    ``wasm4pm-compat/src/event_log.rs`` (``#[serde(tag = "type", content =
    "content")]`` on ``AttributeValue``) by round-tripping a real log through
    the built ``wpm`` binary this session.
    """
    from autofde_lab.ocel.queries import session_event_order

    traces = []
    for session_id in session_ids:
        rows = session_event_order(conn, session_id)
        events = [_string_attr(ACTIVITY_KEY, row["activity"]) for row in rows]
        traces.append(
            {
                "attributes": [_string_attr(ACTIVITY_KEY, session_id)],
                "events": [{"attributes": [e]} for e in events],
            }
        )

    return {
        "attributes": [],
        "traces": traces,
        "extensions": None,
        "classifiers": None,
        "global_trace_attrs": None,
        "global_event_attrs": None,
    }


_METRIC_ROW = re.compile(r"^(?P<name>[A-Za-z][A-Za-z() ]*?)\s{2,}(?P<value>\S.*?)\s*$")


def _parse_table(stdout: str) -> dict[str, str]:
    """Parse ``wpm``'s printed ``Table`` output into ``{metric: value}``.

    ``wpm`` has no ``--json`` output mode for the mining subcommands (its
    ``Table`` printer is plain aligned text) -- parsed here rather than added
    to the CLI, since this bridge is the only current caller and the table
    format is stable within one CLI version.
    """
    metrics: dict[str, str] = {}
    for line in stdout.splitlines():
        match = _METRIC_ROW.match(line.rstrip())
        if match:
            metrics[match.group("name").strip()] = match.group("value").strip()
    return metrics


async def discover_petri_net(
    log_json_path: str | Path,
    *,
    output_path: str | Path,
    wpm_binary: str | None = None,
    timeout_s: float = 60.0,
) -> DiscoveryResult:
    """Run ``wpm mining discover --algo ilp-petri-net`` for real."""
    binary = wpm_binary or resolve_wpm_binary()
    outcome = await run_subprocess_bounded(
        [binary, "mining", "discover", str(log_json_path), "--algo", "ilp-petri-net",
         "-o", str(output_path)],
        timeout_s=timeout_s,
    )
    if outcome.standing != "SOLVED":
        raise RuntimeError(
            f"wpm mining discover failed (standing={outcome.standing}): {outcome.stderr}"
        )
    metrics = _parse_table(outcome.stdout)
    return DiscoveryResult(
        places=int(metrics["Places"]),
        transitions=int(metrics["Transitions"]),
        arcs=int(metrics["Arcs"]),
        simplicity=float(metrics["Simplicity"]),
        self_fitness=float(metrics["Fitness (self)"]),
        model_path=Path(output_path),
    )


_DRIFT_ROW = re.compile(
    r"^(?P<position>\d+)\s{2,}(?P<jaccard>[\d.]+)\s{2,}(?P<tv>[\d.]+)\s{2,}(?P<method>\S+)\s*$",
    re.MULTILINE,
)


async def detect_drift(
    log_json_path: str | Path,
    *,
    activity_key: str = ACTIVITY_KEY,
    window_size: int = 5,
    wpm_binary: str | None = None,
    timeout_s: float = 60.0,
) -> list[DriftPoint]:
    """Run ``wpm mining drift`` for real. See module docstring for why this
    doesn't call ``wasm4pm::prediction_drift::detect_drift`` directly."""
    binary = wpm_binary or resolve_wpm_binary()
    outcome = await run_subprocess_bounded(
        [binary, "mining", "drift", str(log_json_path),
         "-k", activity_key, "--window-size", str(window_size)],
        timeout_s=timeout_s,
    )
    if outcome.standing != "SOLVED":
        raise RuntimeError(
            f"wpm mining drift failed (standing={outcome.standing}): {outcome.stderr}"
        )
    points: list[DriftPoint] = []
    for row in _DRIFT_ROW.finditer(outcome.stdout):
        points.append(
            DriftPoint(
                position=int(row.group("position")),
                jaccard_distance=float(row.group("jaccard")),
                tv_distance=float(row.group("tv")),
                method=row.group("method"),
            )
        )
    return points


async def predict_remaining_duration(
    log_json_path: str | Path,
    *,
    prefix: list[str],
    activity_key: str = ACTIVITY_KEY,
    timestamp_key: str = "time:timestamp",
    wpm_binary: str | None = None,
    timeout_s: float = 60.0,
) -> PredictionResult:
    """Run ``wpm mining predict-duration`` for real. See module docstring for
    why this doesn't call ``wasm4pm::prediction_remaining_time`` directly."""
    binary = wpm_binary or resolve_wpm_binary()
    outcome = await run_subprocess_bounded(
        [binary, "mining", "predict-duration", str(log_json_path),
         "--prefix", ",".join(prefix), "-k", activity_key,
         "--timestamp-key", timestamp_key],
        timeout_s=timeout_s,
    )
    if outcome.standing != "SOLVED":
        raise RuntimeError(
            f"wpm mining predict-duration failed (standing={outcome.standing}): {outcome.stderr}"
        )
    metrics = _parse_table(outcome.stdout)
    return PredictionResult(
        remaining_ms=float(metrics["Remaining (ms)"]),
        method=metrics["Method"],
    )


async def check_conformance(
    log_json_path: str | Path,
    model_pnml_path: str | Path,
    *,
    wpm_binary: str | None = None,
    timeout_s: float = 60.0,
) -> ConformanceReport:
    """Run ``wpm mining conformance`` for real, over a real ``.pnml`` model."""
    binary = wpm_binary or resolve_wpm_binary()
    outcome = await run_subprocess_bounded(
        [binary, "mining", "conformance", str(log_json_path), str(model_pnml_path)],
        timeout_s=timeout_s,
    )
    if outcome.standing != "SOLVED":
        raise RuntimeError(
            f"wpm mining conformance failed (standing={outcome.standing}): {outcome.stderr}"
        )
    metrics = _parse_table(outcome.stdout)
    conforming_str, _, total_str = metrics["Conforming cases"].partition("/")

    deviations: list[TraceDeviation] = []
    dev_rows = re.finditer(
        r"^(?P<case>\S+)\s{2,}(?P<fitness>[\d.]+)\s{2,}(?P<missing>\d+)\s{2,}(?P<remaining>\d+)\s*$",
        outcome.stdout,
        re.MULTILINE,
    )
    for row in dev_rows:
        deviations.append(
            TraceDeviation(
                case_id=row.group("case"),
                trace_fitness=float(row.group("fitness")),
                tokens_missing=int(row.group("missing")),
                tokens_remaining=int(row.group("remaining")),
            )
        )

    return ConformanceReport(
        avg_fitness=float(metrics["Average fitness"]),
        conforming_cases=int(conforming_str.strip()),
        total_cases=int(total_str.strip()),
        deviations=deviations,
        precision=float(metrics["Precision"]) if "Precision" in metrics else None,
        generalization=float(metrics["Generalization"]) if "Generalization" in metrics else None,
    )


async def discover_and_check(
    conn: sqlite3.Connection, session_ids: list[str], *, timeout_s: float = 60.0
) -> tuple[DiscoveryResult, ConformanceReport]:
    """Full loop: OCEL sessions -> real Petri net -> real conformance report.

    Writes the intermediate ``.json``/``.pnml`` files into a temp dir (cleaned
    up on exit) -- this repo's OCEL data never leaves the local machine.
    """
    binary = resolve_wpm_binary()
    with tempfile.TemporaryDirectory(prefix="wasm4pm_bridge_") as tmp:
        log_path = Path(tmp) / "log.json"
        model_path = Path(tmp) / "model.pnml"
        log_path.write_text(
            json.dumps(session_traces_to_wasm4pm_json(conn, session_ids))
        )
        discovery = await discover_petri_net(
            log_path, output_path=model_path, wpm_binary=binary, timeout_s=timeout_s
        )
        conformance = await check_conformance(
            log_path, model_path, wpm_binary=binary, timeout_s=timeout_s
        )
        return discovery, conformance
