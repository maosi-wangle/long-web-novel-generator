from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RagSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    top_k: int = 5
    search_mode: str = "hybrid"
    chapter_scope: tuple[int, int] | None = None
    entity_filter: list[str] = Field(default_factory=list)


class RagHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    score: float
    chapter_id: int
    text: str
    summary: str


class RagSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str
    hits: list[RagHit] = Field(default_factory=list)


class HumanInterventionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    reason: str
    payload: dict


class HumanInterventionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approved: bool
    edited_payload: dict = Field(default_factory=dict)
    instruction: str | None = None
    operator: str = "user"
    timestamp: datetime = Field(default_factory=utc_now)

