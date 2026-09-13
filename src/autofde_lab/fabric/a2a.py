# Copyright (c) AIRBUS and its affiliates.
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

"""A2A 1.0 projection of the shared scikit-decide decision fabric."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from autofde_lab.fabric.canonical import canonical_json
from autofde_lab.fabric.dspy import DecisionCompiler, compile_request_text
from autofde_lab.fabric.models import DecisionRefusal
from autofde_lab.fabric.service import DecisionFabric


class DecisionAgentProtocol:
    """Protocol-neutral A2A job handler, independently testable from HTTP."""

    def __init__(
        self,
        fabric: DecisionFabric,
        compiler: DecisionCompiler | None = None,
    ) -> None:
        self.fabric = fabric
        self.compiler = compiler

    def handle_text(self, text: str) -> dict[str, Any]:
        """Compile if necessary, solve, and return a JSON artifact."""
        try:
            request = compile_request_text(
                text,
                self.fabric.catalog(),
                self.compiler,
            )
            return self.fabric.solve(request).as_dict()
        except DecisionRefusal as error:
            return error.as_dict()


def create_agent_card(url: str) -> Any:
    """Create the discoverable A2A 1.0 Agent Card."""
    try:
        from a2a.types import (
            AgentCapabilities,
            AgentCard,
            AgentInterface,
            AgentSkill,
        )
    except ImportError as error:
        raise RuntimeError(
            "A2A SDK is unavailable; install requirements-agentic.txt"
        ) from error

    skill = AgentSkill(
        id="formal_decision",
        name="Formal Decision Planning",
        description=(
            "Match scikit-decide solvers, compute bounded plans or policies, "
            "and return receipt-addressed trajectories with ERRC cache evidence."
        ),
        input_modes=["application/json", "text/plain"],
        output_modes=["application/json"],
        tags=["planning", "scheduling", "mdp", "pomdp", "pddl", "ppddl"],
        examples=[
            '{"domain":"Maze","solver":"Astar","max_steps":100}',
            "Plan the admitted scheduling job using a compatible solver.",
        ],
    )
    return AgentCard(
        name="scikit-decide Decision Fabric",
        description="Formal planning and decision intelligence exposed through A2A.",
        version="0.1.0",
        default_input_modes=["application/json", "text/plain"],
        default_output_modes=["application/json"],
        capabilities=AgentCapabilities(streaming=False),
        supported_interfaces=[
            AgentInterface(
                protocol_binding="JSONRPC",
                url=url,
                protocol_version="1.0",
            )
        ],
        skills=[skill],
    )


def create_app(
    fabric: DecisionFabric | None = None,
    *,
    compiler: DecisionCompiler | None = None,
    url: str = "http://127.0.0.1:9999",
) -> Any:
    """Build an A2A JSON-RPC Starlette application."""
    try:
        from a2a.server.agent_execution import AgentExecutor
        from a2a.server.events import EventQueue
        from a2a.server.request_handlers import DefaultRequestHandler
        from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
        from a2a.server.tasks import InMemoryTaskStore
        from a2a.types import Message, Part, Role
        from a2a.utils.errors import TaskNotCancelableError
        from starlette.applications import Starlette
    except ImportError as error:
        raise RuntimeError(
            "A2A HTTP runtime is unavailable; install requirements-agentic.txt"
        ) from error

    service = fabric or DecisionFabric()
    protocol = DecisionAgentProtocol(service, compiler)
    card = create_agent_card(url)

    class FabricAgentExecutor(AgentExecutor):
        async def execute(self, context: Any, event_queue: EventQueue) -> None:
            payload = protocol.handle_text(context.get_user_input())
            message = Message(
                message_id=str(uuid4()),
                context_id=context.context_id or "",
                task_id=context.task_id or "",
                role=Role.ROLE_AGENT,
                parts=[
                    Part(
                        text=canonical_json(payload),
                        media_type="application/json",
                    )
                ],
            )
            await event_queue.enqueue_event(message)

        async def cancel(self, context: Any, event_queue: EventQueue) -> None:
            del context, event_queue
            raise TaskNotCancelableError

    handler = DefaultRequestHandler(
        agent_executor=FabricAgentExecutor(),
        task_store=InMemoryTaskStore(),
        agent_card=card,
    )
    routes = [
        *create_agent_card_routes(card),
        *create_jsonrpc_routes(handler, "/"),
    ]
    return Starlette(routes=routes)


def run(
    *,
    host: str = "127.0.0.1",
    port: int = 9999,
    compiler: DecisionCompiler | None = None,
) -> None:
    """Run the A2A server with Uvicorn."""
    try:
        import uvicorn
    except ImportError as error:
        raise RuntimeError("Uvicorn is unavailable") from error
    url = f"http://{host}:{port}"
    uvicorn.run(create_app(compiler=compiler, url=url), host=host, port=port)


if __name__ == "__main__":
    run()
