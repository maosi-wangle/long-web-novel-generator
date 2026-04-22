from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.tool_io import HumanInterventionResult


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReviewStatus(str, Enum):
    pending = "pending"
    resolved = "resolved"


class ReviewDecision(str, Enum):
    approve = "approve"
    reject = "reject"


class HumanReviewRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str
    project_id: str
    stage: str
    blocking: bool = True
    status: ReviewStatus = ReviewStatus.pending
    reason: str
    payload_file: str
    preview_file: str | None = None
    target_chapter_id: int | None = None
    source_status: str | None = None
    source_stage: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    resolution: HumanInterventionResult | None = None
