from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CalaTransportModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class CalaEntity(CalaTransportModel):
    id: str
    name: str
    entity_type: str
    mentions: list[str] = Field(default_factory=list)
    description: str | None = None


class CalaContextItem(CalaTransportModel):
    id: str
    content: str
    origins: list[dict[str, Any]] = Field(default_factory=list)


class CalaExplainabilityItem(CalaTransportModel):
    content: str
    references: list[str] = Field(default_factory=list)


class CalaKnowledgeQueryResponse(CalaTransportModel):
    results: list[dict[str, Any]] = Field(default_factory=list)
    entities: list[CalaEntity] | None = None


class CalaKnowledgeSearchResponse(CalaTransportModel):
    content: str
    context: list[CalaContextItem] = Field(default_factory=list)
    explainability: list[CalaExplainabilityItem] | None = None
    entities: list[CalaEntity] | None = None
