# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""FastMCP projection of the shared scikit-decide decision fabric."""

from __future__ import annotations

from typing import Any

from autofde_lab.fabric.dspy import DecisionCompiler, compile_request_text
from autofde_lab.fabric.issue_reasoning import CompiledIssueReasoner
from autofde_lab.fabric.models import DecisionRequest
from autofde_lab.fabric.service import DecisionFabric
from autofde_lab.ocel.mcp_instrumentation import OcelSessionRecorder, instrumented


def create_server(
    fabric: DecisionFabric | None = None,
    *,
    compiler: DecisionCompiler | None = None,
    ocel_recorder: OcelSessionRecorder | None = None,
    issue_reasoner: CompiledIssueReasoner | None = None,
) -> Any:
    """Create a FastMCP server without duplicating decision semantics.

    ``ocel_recorder``, when supplied, makes every tool call on this server a
    real OCEL 2.0 event automatically (`autofde_lab.ocel.mcp_instrumentation`)
    -- the caller owns the recorder's lifetime and calls
    :meth:`OcelSessionRecorder.close` when done (typically once, after the
    server/session ends) to obtain the validated log. ``None`` (the default)
    adds no instrumentation and no dependency on it.
    """
    try:
        from fastmcp import FastMCP
    except ImportError as error:
        raise RuntimeError(
            "FastMCP is unavailable; install requirements-agentic.txt"
        ) from error

    service = fabric or DecisionFabric()
    diagnostics = issue_reasoner or CompiledIssueReasoner()
    server = FastMCP("scikit-decide-fabric")

    def _record(activity: str, objects_fn):
        """No-op passthrough when ocel_recorder is None; instruments otherwise."""
        if ocel_recorder is None:
            return lambda fn: fn
        return instrumented(ocel_recorder, activity=activity, objects_fn=objects_fn)

    @server.tool
    @_record("decision_catalog", lambda: [])
    def decision_catalog() -> dict[str, Any]:
        """List registered decision domains and solvers."""
        return service.catalog().as_dict()

    @server.tool
    @_record(
        "decision_match",
        lambda domain, domain_arguments=None, use_cache=True: [
            (f"domain-{domain}", "Domain")
        ],
    )
    def decision_match(
        domain: str,
        domain_arguments: dict[str, Any] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Return compatible solvers for a constructed domain."""
        return service.match(
            domain,
            domain_arguments=domain_arguments,
            use_cache=use_cache,
        ).as_dict()

    @server.tool
    @_record(
        "decision_solve",
        lambda request: [
            (f"domain-{request['domain']}", "Domain"),
            *(
                [(f"solver-{request['solver']}", "Solver")]
                if request.get("solver")
                else []
            ),
        ],
    )
    def decision_solve(request: dict[str, Any]) -> dict[str, Any]:
        """Solve and return a receipt-bearing bounded trajectory."""
        return service.solve(DecisionRequest.from_dict(request)).as_dict()

    @server.tool
    @_record("issue_reasoning_catalog", lambda: [])
    def issue_reasoning_catalog() -> dict[str, Any]:
        """List compiled diagnostic archetypes and their evidence contracts."""
        return {
            "archetypes": diagnostics.catalog(),
            "authority": "CANDIDATE_ONLY",
            "actuation": "REFUSED",
        }

    @server.tool
    @_record("issue_reason", lambda evidence: [])
    def issue_reason(evidence: dict[str, Any] | list[str]) -> dict[str, Any]:
        """Compile structured issue evidence into a bounded diagnostic candidate.

        The result is not an admission or action.  ``MATCHED`` means the evidence
        fits a finite compiled diagnostic graph; ``FALLBACK_NOVELTY`` delegates
        causal discovery to cognition; ``REFUSED_EVIDENCE`` means the selected
        graph lacks or contradicts required evidence.
        """
        return diagnostics.reason(evidence).as_dict()

    @server.tool
    @_record("decision_cache_stats", lambda: [])
    def decision_cache_stats() -> dict[str, Any]:
        """Return exact reuse and avoidance metrics."""
        return service.cache_stats()

    @server.tool
    @_record("decision_cache_hotset", lambda: [])
    def decision_cache_hotset() -> dict[str, Any]:
        """Return the measured 80/20 hot set."""
        return service.cache_hotset()

    if compiler is not None:

        @server.tool
        @_record("decision_compile", lambda job: [])
        def decision_compile(job: str) -> dict[str, Any]:
            """Compile a natural-language job at the DSPy frontier."""
            return compile_request_text(job, service.catalog(), compiler).as_dict()

    return server


def main() -> None:
    """Run the MCP server over stdio."""
    create_server().run()


if __name__ == "__main__":
    main()
