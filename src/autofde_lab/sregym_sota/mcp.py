from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass
from typing import Any

from fastmcp import Client
from fastmcp.client import SSETransport

from .models import Capability


@dataclass(frozen=True)
class Surface:
    name: str
    url: str
    required: bool = False


class McpBroker:
    """Discover and invoke only SREGym's public MCP capability surface."""

    def __init__(self) -> None:
        host = os.getenv("API_HOSTNAME", "localhost")
        mcp_port = os.getenv("MCP_SERVER_PORT", "9954")
        api_port = os.getenv("API_PORT", "8000")
        self.session_id = uuid.uuid4().hex
        self.surfaces = (
            Surface("kubectl", f"http://{host}:{mcp_port}/kubectl/sse", True),
            Surface("prometheus", f"http://{host}:{mcp_port}/prometheus/sse"),
            Surface("jaeger", f"http://{host}:{mcp_port}/jaeger/sse"),
            Surface("loki", f"http://{host}:{mcp_port}/loki/sse"),
            Surface("submit", f"http://{host}:{api_port}/submit_mcp/sse", True),
        )
        self._available: dict[str, Surface] = {}

    async def _list_tools_with_retry(self, surface: Surface) -> list[Any]:
        attempts = int(
            os.getenv(
                "AUTOFDE_REQUIRED_MCP_DISCOVERY_ATTEMPTS"
                if surface.required
                else "AUTOFDE_OPTIONAL_MCP_DISCOVERY_ATTEMPTS",
                "12" if surface.required else "3",
            )
        )
        delay = float(os.getenv("AUTOFDE_MCP_DISCOVERY_RETRY_SECONDS", "1"))
        last_error: Exception | None = None
        for attempt in range(1, max(1, attempts) + 1):
            try:
                async with Client(self._transport(surface)) as client:
                    return list(await client.list_tools())
            except Exception as exc:  # SREGym may still be publishing a port-forward.
                last_error = exc
                if attempt < attempts:
                    await asyncio.sleep(delay)
        assert last_error is not None
        raise last_error

    @staticmethod
    def _tool_input_schema(tool: Any) -> dict[str, Any]:
        raw = getattr(tool, "inputSchema", None)
        if raw is None:
            raw = getattr(tool, "input_schema", None)
        if raw is None:
            return {}
        if hasattr(raw, "model_dump"):
            dumped = raw.model_dump()
            return dumped if isinstance(dumped, dict) else {}
        return dict(raw) if isinstance(raw, dict) else {}

    async def discover(self) -> list[Capability]:
        capabilities: list[Capability] = []
        failures: list[str] = []
        self._available.clear()
        for surface in self.surfaces:
            try:
                tools = await self._list_tools_with_retry(surface)
            except Exception as exc:
                if surface.required:
                    failures.append(f"{surface.name}: {type(exc).__name__}: {exc}")
                continue
            self._available[surface.name] = surface
            for tool in tools:
                name = getattr(tool, "name", None) or str(tool)
                description = getattr(tool, "description", "") or ""
                capabilities.append(
                    Capability(
                        id=f"mcp:{surface.name}:{name}",
                        surface=surface.name,
                        tool=name,
                        description=str(description),
                        input_schema=self._tool_input_schema(tool),
                    )
                )
        if failures:
            raise RuntimeError("required MCP discovery failed: " + "; ".join(failures))
        return capabilities

    async def call(
        self, surface_name: str, tool: str, arguments: dict[str, Any]
    ) -> str:
        surface = self._available.get(surface_name)
        if surface is None:
            raise RuntimeError(f"MCP surface not discovered: {surface_name}")
        async with Client(self._transport(surface)) as client:
            result = await client.call_tool(tool, arguments=arguments)
        return self._textify(result)

    def _transport(self, surface: Surface) -> SSETransport:
        headers = {"sregym_ssid": self.session_id} if surface.name == "kubectl" else {}
        return SSETransport(
            url=surface.url,
            headers=headers,
            sse_read_timeout=float(os.getenv("SSE_READ_TIMEOUT", "3600")),
        )

    @staticmethod
    def _textify(result: Any) -> str:
        content = getattr(result, "content", result)
        if not isinstance(content, (list, tuple)):
            content = [content]
        parts: list[str] = []
        for item in content:
            text = getattr(item, "text", None)
            parts.append(str(text if text is not None else item))
        return "\n".join(parts)
