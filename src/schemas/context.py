from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.memory import (
    ArcMemory,
    ChapterMemory,
    CharacterState,
    CompactRagHit,
    OpenLoopItem,
    StickyConstraint,
    WorldState,
)


class ContextPriority(str, Enum):
    p0 = "P0"
    p1 = "P1"
    p2 = "P2"
    p3 = "P3"
    p4 = "P4"
    p5 = "P5"


class ContextBucket(str, Enum):
    system = "system"
    current_task = "current_task"
    sticky = "sticky"
    structured_memory = "structured_memory"
    retrieval = "retrieval"


class BudgetStatus(str, Enum):
    normal = "normal"
    warning = "warning"
    critical = "critical"


class ContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    bucket: ContextBucket
    priority: ContextPriority
    token_estimate: int
    compressible: bool = True
    droppable: bool = True
    included: bool = True
    compression_level: int = 0


class BudgetBucketReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bucket: ContextBucket
    target_tokens: int
    used_tokens: int
    item_count: int


class ContextBudgetReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_budget: int
    used_tokens: int
    status: BudgetStatus
    buckets: list[BudgetBucketReport] = Field(default_factory=list)
    applied_actions: list[str] = Field(default_factory=list)
    items: list[ContextItem] = Field(default_factory=list)


class DetailOutlineContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_meta: dict[str, Any] = Field(default_factory=dict)
    current_chapter: dict[str, Any] = Field(default_factory=dict)
    current_act: dict[str, Any] | None = None
    previous_chapter: dict[str, Any] | None = None
    next_chapter: dict[str, Any] | None = None
    current_progress: dict[str, Any] = Field(default_factory=dict)
    recent_memories: list[ChapterMemory] = Field(default_factory=list)
    arc_memories: list[ArcMemory] = Field(default_factory=list)
    character_state: CharacterState = Field(default_factory=CharacterState)
    world_state: WorldState = Field(default_factory=WorldState)
    open_loops: list[OpenLoopItem] = Field(default_factory=list)
    sticky_constraints: list[StickyConstraint] = Field(default_factory=list)
    rag_hits: list[CompactRagHit] = Field(default_factory=list)
    foreshadowing: list[dict[str, Any]] = Field(default_factory=list)
    global_constraints: list[str] = Field(default_factory=list)
    world_setting: dict[str, str] = Field(default_factory=dict)
    core_characters: list[dict[str, Any]] = Field(default_factory=list)
    budget_report: ContextBudgetReport | None = None


class WriterContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_meta: dict[str, Any] = Field(default_factory=dict)
    chapter_id: int
    title: str
    chapter_goal: str
    writer_packet: dict[str, Any] = Field(default_factory=dict)
    ending_hook: str | None = None
    user_constraints: list[str] = Field(default_factory=list)
    recent_memories: list[ChapterMemory] = Field(default_factory=list)
    arc_memories: list[ArcMemory] = Field(default_factory=list)
    character_state: CharacterState = Field(default_factory=CharacterState)
    world_state: WorldState = Field(default_factory=WorldState)
    open_loops: list[OpenLoopItem] = Field(default_factory=list)
    sticky_constraints: list[StickyConstraint] = Field(default_factory=list)
    rag_hits: list[CompactRagHit] = Field(default_factory=list)
    budget_report: ContextBudgetReport | None = None
