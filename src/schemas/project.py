from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectBootstrapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    title: str
    premise: str | None = None
    genre: list[str] = Field(default_factory=list)
    tone: str | None = None
    user_input: dict[str, Any] = Field(default_factory=dict)


class ProjectRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    title: str
    premise: str | None = None
    genre: list[str] = Field(default_factory=list)
    tone: str | None = None
    user_input: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

