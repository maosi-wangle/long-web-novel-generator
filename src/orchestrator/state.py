from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkflowStatus(str, Enum):
    initialized = "initialized"
    outline_ready = "outline_ready"
    detail_outline_ready = "detail_outline_ready"
    drafting = "drafting"
    chapter_archived = "chapter_archived"
    waiting_human_review = "waiting_human_review"
    completed = "completed"
    failed = "failed"


class GenerationStage(str, Enum):
    outline = "outline"
    detail_outline = "detail_outline"
    writer = "writer"
    archive = "archive"


class ProjectState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    title: str
    status: WorkflowStatus = WorkflowStatus.initialized
    current_stage: GenerationStage = GenerationStage.outline
    current_act_index: int = 0
    current_chapter_index: int = 0
    current_scene_index: int = 0
    outline_version: int = 0
    detail_outline_version: int = 0
    last_completed_chapter: int = 0
    pending_human_review: bool = False
    active_chapter_title: str | None = None
    notes: list[str] = Field(default_factory=list)
    last_error: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    def touch(self) -> "ProjectState":
        self.updated_at = utc_now()
        return self

    def mark_status(
        self,
        status: WorkflowStatus,
        stage: GenerationStage | None = None,
    ) -> "ProjectState":
        self.status = status
        if stage is not None:
            self.current_stage = stage
        return self.touch()

    def advance_to_next_chapter(self) -> "ProjectState":
        self.last_completed_chapter = self.current_chapter_index
        self.current_chapter_index += 1
        self.current_scene_index = 0
        self.detail_outline_version = 0
        self.active_chapter_title = None
        self.status = WorkflowStatus.outline_ready
        self.current_stage = GenerationStage.detail_outline
        return self.touch()

