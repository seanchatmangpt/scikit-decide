"""Bounded execution limits for GymAct's consequence boundary."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RuntimeLimits(BaseModel):
    """Fail-closed limits applied before and around external boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    authority_timeout_s: float = Field(default=5.0, gt=0, le=300)
    materialize_timeout_s: float = Field(default=60.0, gt=0, le=3600)
    observe_timeout_s: float = Field(default=10.0, gt=0, le=300)
    actuate_timeout_s: float = Field(default=60.0, gt=0, le=3600)
    verify_timeout_s: float = Field(default=30.0, gt=0, le=3600)
    recovery_timeout_s: float = Field(default=60.0, gt=0, le=3600)
    teardown_timeout_s: float = Field(default=60.0, gt=0, le=3600)
    max_input_bytes: int = Field(default=1_048_576, ge=1024, le=64 * 1024 * 1024)
    max_state_bytes: int = Field(default=8_388_608, ge=1024, le=256 * 1024 * 1024)
    max_checkpoint_bytes: int = Field(default=8_388_608, ge=1024, le=256 * 1024 * 1024)
