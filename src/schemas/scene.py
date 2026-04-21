from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SceneProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    act_index: int = 0
    chapter_index: int = 0
    scene_index: int = 0
    completed_scene_ids: list[int] = Field(default_factory=list)


class RetrievedContextSnippet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    chapter_id: int
    summary: str
    text: str
    score: float | None = None

