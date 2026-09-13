"""Real FastAPI ASGI app over GymActKernel.

`create_app()` returns a real `fastapi.FastAPI` instance -- exactly what
`tests/test_api.py` asserts against.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI
from pydantic import BaseModel

from autofde_lab.gymact.kernel import GymActKernel


class _CreateEpisodeRequest(BaseModel):
    subject: str


class _CreateEpisodeResponse(BaseModel):
    episode_id: str


def create_app() -> FastAPI:
    app = FastAPI(title="GymAct")
    kernel = GymActKernel()

    @app.post("/episodes", response_model=_CreateEpisodeResponse)
    def create_episode(request: _CreateEpisodeRequest) -> _CreateEpisodeResponse:
        episode_id = str(uuid.uuid4())
        kernel.discover(subject=request.subject, episode_id=episode_id)
        return _CreateEpisodeResponse(episode_id=episode_id)

    return app
