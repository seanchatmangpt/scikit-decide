# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""Chicago-style tests for the ``bcinr-powl`` soundness subprocess bridge.

Real collaborators only: a real :class:`PowlNode` tree, a real conversion
into WF-net request shape, and a real subprocess call to the real
``soundness_cli`` Rust binary (built from ``~/bcinr/crates/bcinr-powl``).
No mocking of the subprocess call -- per
``.claude/rules/testing-chicago-style.md``, if the real binary is
unavailable the test is skipped with a precisely named reason, never faked.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from autofde_lab.powl.algebra import Atom, OrderEdge, PartialOrder
from autofde_lab.powl.soundness_bridge import (
    SoundnessBridgeError,
    SoundnessResult,
    WfNetRequest,
    check_soundness,
    powl_to_wf_net_request,
)


def _find_soundness_cli() -> str:
    found = shutil.which("soundness_cli")
    if found:
        return found
    for candidate in (
        Path.home() / "bcinr" / "target" / "debug" / "soundness_cli",
        Path.home() / "bcinr" / "target" / "release" / "soundness_cli",
    ):
        if candidate.is_file():
            return str(candidate)
    return ""


_SOUNDNESS_CLI = _find_soundness_cli()

skip_if_no_binary = pytest.mark.skipif(
    not _SOUNDNESS_CLI,
    reason="BLOCKED:BCINR_SOUNDNESS_CLI_BINARY_NOT_FOUND",
)


def test_powl_to_wf_net_request_sequence_of_two_atoms() -> None:
    """A real 2-Atom sequential PartialOrder compiles to a real WfNetRequest
    with a unique source place, a unique sink place, and one transition per
    Atom label (plus the silent structural-link transitions the block
    translation requires)."""
    tree = PartialOrder(
        children=(Atom("book_flight"), Atom("book_hotel")),
        order=frozenset({OrderEdge(0, 1)}),
    )

    request = powl_to_wf_net_request(tree)

    assert isinstance(request, WfNetRequest)
    assert request.source in request.places
    assert request.sink in request.places
    assert request.source != request.sink
    named = {name for _, name in request.transitions if name is not None}
    assert named == {"book_flight", "book_hotel"}
    # every place appears in at least one flow arc (no orphan places)
    referenced = {p for src, dst, _ in request.flow for p in (src, dst)}
    for place in request.places:
        assert place in referenced


@skip_if_no_binary
def test_check_soundness_real_subprocess_sequence_is_sound() -> None:
    """Real end-to-end: convert a real 2-Atom sequential POWL tree to a
    WF-net request, invoke the real soundness_cli subprocess, and assert on
    the real returned SoundnessResult. A simple sequential net must be
    sound and safe."""
    tree = PartialOrder(
        children=(Atom("book_flight"), Atom("book_hotel")),
        order=frozenset({OrderEdge(0, 1)}),
    )

    result = check_soundness(tree, executable=_SOUNDNESS_CLI)

    assert isinstance(result, SoundnessResult)
    assert result.truncated is False
    assert result.is_safe is True
    assert result.no_dead_transitions is True
    assert result.option_to_complete is True
    assert result.proper_completion is True
    assert result.sound is True
    assert result.reachable_marking_count > 0


@skip_if_no_binary
def test_check_soundness_real_subprocess_single_atom() -> None:
    """A minimal one-Atom PowlNode tree (below PartialOrder's n>=2 arity
    floor, so this exercises the raw Atom compile path directly) is sound."""
    tree = Atom("ping")

    result = check_soundness(tree, executable=_SOUNDNESS_CLI)

    assert result.sound is True
    assert result.truncated is False


@skip_if_no_binary
def test_check_soundness_real_subprocess_raw_wf_net_request() -> None:
    """Real subprocess call built directly from a hand-constructed
    WfNetRequest (no PowlNode conversion involved), matching the wire
    schema in the shared contract exactly."""
    request = WfNetRequest(
        places=("p1", "p2", "p3"),
        transitions=(("t1", "a"), ("t2", "b")),
        flow=(
            ("p1", "t1", "place_to_transition"),
            ("t1", "p2", "transition_to_place"),
            ("p2", "t2", "place_to_transition"),
            ("t2", "p3", "transition_to_place"),
        ),
        source="p1",
        sink="p3",
    )

    result = check_soundness(request, executable=_SOUNDNESS_CLI)

    assert result == SoundnessResult(
        no_dead_transitions=True,
        option_to_complete=True,
        proper_completion=True,
        is_safe=True,
        truncated=False,
        reachable_marking_count=3,
        sound=True,
    )


def test_check_soundness_transport_unavailable_when_binary_missing() -> None:
    """Real, no mocking: pointing the bridge at a real nonexistent path
    produces a real, typed TRANSPORT_FAILED/TRANSPORT_UNAVAILABLE refusal,
    never a fabricated SoundnessResult."""
    request = WfNetRequest(
        places=("p1", "p2"),
        transitions=(("t1", "a"),),
        flow=(
            ("p1", "t1", "place_to_transition"),
            ("t1", "p2", "transition_to_place"),
        ),
        source="p1",
        sink="p2",
    )

    with pytest.raises(SoundnessBridgeError) as excinfo:
        check_soundness(
            request, executable="/nonexistent/path/to/soundness_cli_binary"
        )

    assert excinfo.value.code in ("TRANSPORT_FAILED", "TRANSPORT_UNAVAILABLE")
