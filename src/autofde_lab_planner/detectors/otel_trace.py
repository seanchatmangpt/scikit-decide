"""Category-B6 Detector: OpenTelemetry / Jaeger Trace Diffing."""

from __future__ import annotations

import ast
import json
from collections import defaultdict
from typing import Any

from autofde_lab_planner.models import ParsedSpan, ServiceMetrics, TraceAnomalyResult, TraceTree


def parse_jaeger_traces_json(raw_json: str | list[Any] | dict[str, Any]) -> list[TraceTree]:
    """Parses Jaeger trace payloads into typed TraceTree structures."""
    if isinstance(raw_json, str):
        raw_str = raw_json.strip()
        if not raw_str:
            return []
        try:
            data = json.loads(raw_str)
        except json.JSONDecodeError:
            try:
                data = ast.literal_eval(raw_str)
            except (ValueError, SyntaxError):
                return []
    else:
        data = raw_json

    if isinstance(data, dict):
        traces_list = data.get("data", [data])
    elif isinstance(data, list):
        traces_list = data
    else:
        return []

    trees: list[TraceTree] = []

    for trace_item in traces_list:
        if not isinstance(trace_item, dict):
            continue

        trace_id = str(trace_item.get("traceID", ""))
        spans_raw = trace_item.get("spans", [])
        processes_raw = trace_item.get("processes", {})

        spans_by_id: dict[str, ParsedSpan] = {}
        children_by_parent: dict[str, list[str]] = defaultdict(list)
        root_span_ids: list[str] = []

        for s in spans_raw:
            if not isinstance(s, dict):
                continue
            span_id = str(s.get("spanID", ""))
            process_id = str(s.get("processID", ""))
            process = processes_raw.get(process_id, {})
            service_name = process.get("serviceName") or s.get("serviceName") or "unknown"

            op_name = str(s.get("operationName", ""))
            # duration in microseconds -> convert to ms
            duration_raw = s.get("duration", 0)
            duration_ms = float(duration_raw) / 1000.0 if duration_raw else 0.0

            tags_raw = s.get("tags", [])
            tags_dict: dict[str, Any] = {}
            has_error = False
            status_code = None

            if isinstance(tags_raw, list):
                for t in tags_raw:
                    if isinstance(t, dict):
                        k = t.get("key")
                        v = t.get("value")
                        if k:
                            tags_dict[k] = v
                        if k == "error" and v in (True, "true", "True", 1):
                            has_error = True
                        if k in ("http.status_code", "rpc.grpc.status_code"):
                            status_code = str(v)
                            if k == "http.status_code" and str(v).startswith(("4", "5")):
                                has_error = True
                            elif k == "rpc.grpc.status_code" and str(v) != "0":
                                has_error = True

            parent_span_id = None
            refs = s.get("references", [])
            if isinstance(refs, list):
                for r in refs:
                    if isinstance(r, dict) and r.get("refType") == "CHILD_OF":
                        parent_span_id = str(r.get("spanID", ""))
                        break

            parsed_span = ParsedSpan(
                span_id=span_id,
                trace_id=trace_id,
                operation_name=op_name,
                service_name=service_name,
                duration_ms=duration_ms,
                has_error=has_error,
                status_code=status_code,
                parent_span_id=parent_span_id,
                tags=tags_dict,
            )
            spans_by_id[span_id] = parsed_span

            if parent_span_id:
                children_by_parent[parent_span_id].append(span_id)
            else:
                root_span_ids.append(span_id)

        if spans_by_id:
            trees.append(
                TraceTree(
                    trace_id=trace_id,
                    spans_by_id=spans_by_id,
                    children_by_parent=dict(children_by_parent),
                    root_span_ids=root_span_ids,
                )
            )

    return trees


def detect_otel_trace_anomalies(
    raw_traces_by_service: dict[str, Any],
    latency_threshold_ms: float = 2000.0,
    error_rate_threshold: float = 0.20,
) -> TraceAnomalyResult:
    """Isolates the root-cause downstream service from Jaeger traces by building call DAGs.

    Accepts dict mapping service_name -> raw trace JSON string / payload.
    """
    all_trees: list[TraceTree] = []

    for svc, raw_data in raw_traces_by_service.items():
        parsed = parse_jaeger_traces_json(raw_data)
        all_trees.extend(parsed)

    if not all_trees:
        return TraceAnomalyResult(has_anomaly=False, reasoning="No valid Jaeger trace trees parsed.")

    # Aggregate per-service metrics & build call graph (parent_svc -> child_svc)
    service_spans: dict[str, list[ParsedSpan]] = defaultdict(list)
    call_graph: dict[str, set[str]] = defaultdict(set)

    for tree in all_trees:
        for span in tree.spans_by_id.values():
            service_spans[span.service_name].append(span)

            if span.parent_span_id and span.parent_span_id in tree.spans_by_id:
                parent_span = tree.spans_by_id[span.parent_span_id]
                if parent_span.service_name != span.service_name:
                    call_graph[parent_span.service_name].add(span.service_name)

    metrics_by_service: dict[str, ServiceMetrics] = {}
    failing_services: set[str] = set()

    for svc_name, spans in service_spans.items():
        total = len(spans)
        errors = sum(1 for s in spans if s.has_error)
        durations = [s.duration_ms for s in spans]
        avg_dur = sum(durations) / float(total) if total > 0 else 0.0
        max_dur = max(durations) if durations else 0.0
        error_rate = float(errors) / float(total) if total > 0 else 0.0

        metrics_by_service[svc_name] = ServiceMetrics(
            service_name=svc_name,
            total_spans=total,
            error_spans=errors,
            error_rate=error_rate,
            avg_duration_ms=avg_dur,
            max_duration_ms=max_dur,
            downstream_call_count=len(call_graph.get(svc_name, set())),
        )

        if error_rate >= error_rate_threshold or avg_dur >= latency_threshold_ms:
            failing_services.add(svc_name)

    if not failing_services:
        return TraceAnomalyResult(
            has_anomaly=False,
            metrics_by_service=metrics_by_service,
            reasoning="All observed services meet error rate and latency thresholds.",
        )

    # Isolate root cause service: find the deepest downstream service in failing_services
    # A service S is root cause if S is failing AND no downstream child C in call_graph[S] is failing
    root_candidates: list[str] = []
    for svc in failing_services:
        children = call_graph.get(svc, set())
        failing_children = children.intersection(failing_services)
        if not failing_children:
            root_candidates.append(svc)

    if not root_candidates:
        # Fallback to service with highest error rate or highest max duration
        root_cause = max(
            failing_services,
            key=lambda s: (metrics_by_service[s].error_rate, metrics_by_service[s].max_duration_ms),
        )
    else:
        root_cause = max(
            root_candidates,
            key=lambda s: (metrics_by_service[s].error_rate, metrics_by_service[s].max_duration_ms),
        )

    m = metrics_by_service[root_cause]
    reason = (
        f"Service {root_cause!r} isolated as root cause: "
        f"error_rate={m.error_rate:.2%}, avg_duration={m.avg_duration_ms:.1f}ms, "
        f"max_duration={m.max_duration_ms:.1f}ms across {m.total_spans} spans."
    )

    return TraceAnomalyResult(
        has_anomaly=True,
        root_cause_service=root_cause,
        affected_services=tuple(sorted(failing_services)),
        anomalous_traces_count=len(all_trees),
        metrics_by_service=metrics_by_service,
        reasoning=reason,
    )
