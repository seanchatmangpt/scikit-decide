"""PDDL, PPDDL and PDDL+/TPDDL native runtime exporters."""

from __future__ import annotations

import math
from typing import Any, Mapping

from .model import (
    Builder,
    ExportLimits,
    PlanningExport,
    PlanningExportError,
    canonical,
    canonical_json,
    digest,
    short_label,
)


def export_pddl_domain(
    domain: Any, *, subject: str, limits: ExportLimits = ExportLimits()
) -> PlanningExport:
    limits.validate()
    builder = Builder(
        "pddl",
        subject,
        {
            "source": "autofde-lab:PDDLDomain",
            "export_mode": "bounded-runtime-state-space",
        },
    )
    _export_deterministic(
        domain, builder, domain.get_initial_state(), limits, temporal=False
    )
    return builder.finish()


def export_ppddl_domain(
    domain: Any, *, subject: str, limits: ExportLimits = ExportLimits()
) -> PlanningExport:
    limits.validate()
    builder = Builder(
        "ppddl",
        subject,
        {
            "source": "autofde-lab:PPDDLDomain",
            "export_mode": "bounded-runtime-state-space",
        },
    )
    initial = domain.get_initial_state()
    queue: list[tuple[Any, int]] = [(initial, 0)]
    queued = {_state_id(initial)}
    expanded: set[str] = set()
    truncated = False

    while queue:
        state, depth = queue.pop(0)
        sid = _add_state(builder, state, initial=(depth == 0))
        if sid in expanded:
            continue
        expanded.add(sid)
        if depth >= limits.max_depth:
            truncated = truncated or not _safe_terminal(domain, state)
            continue
        if len(expanded) >= limits.max_states:
            truncated = truncated or bool(queue)
            break
        for action in _actions(domain, state, limits):
            aid = _add_action(builder, action, sid)
            builder.edge(sid, aid, "precondition", "applicable")
            values = list(
                domain.get_next_state_distribution(state, action).get_values()
            )
            if len(values) > limits.max_successors_per_action:
                values = values[: limits.max_successors_per_action]
                truncated = True
            total = sum(float(weight) for _, weight in values)
            if not math.isfinite(total) or total <= 0:
                raise PlanningExportError(
                    "AFL-MMDIO-008",
                    "PPDDL successor weights need a positive finite sum",
                )
            for successor, weight in values:
                probability = float(weight) / total
                nsid = _add_state(builder, successor)
                attrs = {"probability": probability}
                attrs.update(_transition_value(domain, state, action, successor))
                builder.edge(aid, nsid, "probabilistic", "outcome", attrs)
                builder.edge(sid, nsid, "probabilistic", _action_label(action), attrs)
                if (
                    nsid not in expanded
                    and nsid not in queued
                    and len(queued) < limits.max_states
                ):
                    queue.append((successor, depth + 1))
                    queued.add(nsid)
    builder.metadata.update(
        {
            "expanded_states": len(expanded),
            "truncated": truncated,
            "limits": limits.as_dict(),
        }
    )
    return builder.finish()


def export_tpddl_domain(
    domain: Any, *, subject: str, limits: ExportLimits = ExportLimits()
) -> PlanningExport:
    limits.validate()
    builder = Builder(
        "pddl+",
        subject,
        {
            "source": "autofde-lab:TPDDLDomain",
            "export_mode": "bounded-temporal-runtime-state-space",
        },
    )
    _export_deterministic(
        domain, builder, domain.get_initial_state(), limits, temporal=True
    )
    return builder.finish()


def _export_deterministic(
    domain: Any, builder: Builder, initial: Any, limits: ExportLimits, *, temporal: bool
) -> None:
    queue: list[tuple[Any, int]] = [(initial, 0)]
    queued = {_state_id(initial)}
    expanded: set[str] = set()
    truncated = False
    while queue:
        state, depth = queue.pop(0)
        sid = _add_state(builder, state, initial=(depth == 0), temporal=temporal)
        if sid in expanded:
            continue
        expanded.add(sid)
        if depth >= limits.max_depth:
            truncated = truncated or not _safe_terminal(domain, state)
            continue
        if len(expanded) >= limits.max_states:
            truncated = truncated or bool(queue)
            break
        for action in _actions(domain, state, limits):
            next_state = domain.get_next_state(state, action)
            nsid = _add_state(builder, next_state, temporal=temporal)
            action_attrs: dict[str, Any] = {}
            edge_attrs = _transition_value(domain, state, action, next_state)
            direct_kind = "transition"
            if temporal:
                start, end = _state_time(state), _state_time(next_state)
                if start is not None:
                    action_attrs["start"] = start
                if start is not None and end is not None:
                    duration = max(0.0, end - start)
                    action_attrs["duration"] = duration
                    edge_attrs["duration"] = duration
                kind = getattr(action, "kind", None)
                if kind is not None:
                    action_attrs["tpddl_kind"] = _tpddl_kind_name(action, kind)
                direct_kind = "temporal"
            aid = _add_action(builder, action, sid, attributes=action_attrs)
            builder.edge(sid, aid, "precondition", "applicable")
            builder.edge(aid, nsid, "effect", "outcome", edge_attrs)
            builder.edge(sid, nsid, direct_kind, _action_label(action), edge_attrs)
            if (
                nsid not in expanded
                and nsid not in queued
                and len(queued) < limits.max_states
            ):
                queue.append((next_state, depth + 1))
                queued.add(nsid)
    builder.metadata.update(
        {
            "expanded_states": len(expanded),
            "truncated": truncated,
            "limits": limits.as_dict(),
        }
    )


def _actions(domain: Any, state: Any, limits: ExportLimits) -> list[Any]:
    space = domain.get_applicable_actions(state)
    getter = getattr(space, "get_elements", None)
    if getter is None:
        raise PlanningExportError(
            "AFL-MMDIO-009", "applicable action space is not enumerable"
        )
    actions = list(getter())
    actions.sort(key=lambda action: canonical_json(_action_payload(action)))
    return actions[: limits.max_actions_per_state]


def _add_state(
    builder: Builder, state: Any, *, initial: bool = False, temporal: bool = False
) -> str:
    node_id = _state_id(state)
    attrs: dict[str, Any] = {"initial": True} if initial else {}
    if temporal and (time := _state_time(state)) is not None:
        attrs["time"] = time
    return builder.node(node_id, "state", _state_label(state), attrs)


def _add_action(
    builder: Builder,
    action: Any,
    source_id: str,
    *,
    attributes: Mapping[str, Any] | None = None,
) -> str:
    payload = _action_payload(action)
    node_id = f"action_{digest({'source': source_id, 'action': payload})[:20]}"
    attrs = {"ground": payload}
    attrs.update(dict(attributes or {}))
    return builder.node(node_id, "action", _action_label(action), attrs)


def _state_id(state: Any) -> str:
    return f"state_{digest(_state_payload(state))[:20]}"


def _state_payload(state: Any) -> Any:
    payload: dict[str, Any] = {"type": type(state).__name__}
    observed = False
    for attr, name in (
        ("_atoms", "atoms"),
        ("_fluents", "fluents"),
        ("_time", "time"),
        ("_active_da", "active_durative_actions"),
    ):
        if hasattr(state, attr):
            payload[name] = canonical(getattr(state, attr))
            observed = True
    if not observed:
        payload["value"] = canonical(state)
    return payload


def _action_payload(action: Any) -> Any:
    payload: dict[str, Any] = {"type": type(action).__name__}
    observed = False
    for attr in ("action_id", "arguments", "kind"):
        if hasattr(action, attr):
            payload[attr] = canonical(getattr(action, attr))
            observed = True
    if not observed:
        payload["value"] = canonical(action)
    payload["native_text"] = _action_native_text(action)
    payload["label"] = _action_label(action)
    return payload


def _state_label(state: Any) -> str:
    time = _state_time(state)
    base = short_label(state)
    return f"t={time:g} {base}" if time is not None else base


def _state_time(state: Any) -> float | None:
    value = getattr(state, "time", getattr(state, "_time", None))
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    ):
        return float(value)
    return None


def _action_native_text(action: Any) -> str:
    try:
        return str(action)
    except Exception:
        return type(action).__name__


def _action_label(action: Any) -> str:
    """Return a Mermaid-safe display label while preserving native text in the payload."""
    text = _action_native_text(action).strip()
    if len(text) >= 2 and text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    translation = str.maketrans({char: " " for char in "()[]{}<>|"})
    text = " ".join(text.translate(translation).split())
    return text or type(action).__name__


def _tpddl_kind_name(action: Any, kind: Any) -> str:
    for name in ("NOOP", "INSTANTANEOUS", "DURATIVE_START"):
        if getattr(action, name, object()) == kind:
            return name.lower()
    return str(kind)


def _safe_terminal(domain: Any, state: Any) -> bool:
    try:
        return bool(domain.is_terminal(state))
    except Exception:
        return False


def _transition_value(
    domain: Any, state: Any, action: Any, next_state: Any
) -> dict[str, Any]:
    try:
        value = domain.get_transition_value(state, action, next_state)
    except Exception:
        return {}
    attrs: dict[str, Any] = {}
    for name in ("reward", "cost"):
        candidate = getattr(value, name, None)
        if (
            isinstance(candidate, (int, float))
            and not isinstance(candidate, bool)
            and math.isfinite(float(candidate))
        ):
            attrs[name] = float(candidate)
    return attrs
