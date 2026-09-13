"""Chicago-style TDD prep: real FastAPI ASGI app, real in-process httpx client.

`autofde_lab.gymact.api` does not exist yet -- expected to fail at collection
until the next pass adds a real `create_app()` returning a real `fastapi.FastAPI`
app wired to the real `autofde_lab.gymact.models` types. Uses `httpx.AsyncClient`
against `ASGITransport` -- a real in-process ASGI call, not a mocked HTTP client,
mirroring how tests/fabric/test_mcp.py drives a real server through a real
client rather than faking the transport.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

fastapi = pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from autofde_lab.gymact.api import create_app  # noqa: E402


def _post(app: Any, path: str, json: dict) -> Any:
    async def run() -> Any:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            return await client.post(path, json=json)

    return asyncio.run(run())


def test_create_app_returns_a_real_fastapi_instance() -> None:
    app = create_app()
    assert isinstance(app, fastapi.FastAPI)


def test_post_episodes_returns_a_real_episode_id() -> None:
    app = create_app()

    response = _post(app, "/episodes", json={"subject": "cloudgoat"})

    assert response.status_code == 200
    body = response.json()
    assert "episode_id" in body
    assert isinstance(body["episode_id"], str)
    assert body["episode_id"]


def test_post_episodes_missing_subject_returns_422() -> None:
    app = create_app()

    response = _post(app, "/episodes", json={})

    assert response.status_code == 422
