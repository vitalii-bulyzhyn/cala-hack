from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LivenessResponse(BaseModel):
    status: Literal["ok"]


class DependencyCheck(BaseModel):
    status: Literal["ok", "error"]
    required: bool
    latency_ms: float = Field(ge=0)


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, DependencyCheck]


class ProviderStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    configured: bool
    model: str | None = None
    base_url: str | None = None


class ProviderStatusResponse(BaseModel):
    providers: dict[str, ProviderStatus]
