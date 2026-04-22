from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ChunkRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    project_id: str
    chapter_id: int
    source_file: str
    text: str
    summary: str
    char_start: int
    char_end: int
    entities: list[str] = Field(default_factory=list)


class RagIngestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    chapter_id: int
    chunk_count: int
    total_indexed_chunks: int
    embedding_model: str
    status: str = "indexed"


class ForeshadowingMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    summary: str
    expected_payoff_window: str | None = None


class CharacterStateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    character: str
    change: str
    field: str | None = None


class RelationshipUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pair: list[str] = Field(default_factory=list)
    change: str


class ChapterMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: int
    title: str
    one_line_summary: str
    key_events: list[str] = Field(default_factory=list)
    new_facts: list[str] = Field(default_factory=list)
    character_state_updates: list[CharacterStateUpdate] = Field(default_factory=list)
    relationship_updates: list[RelationshipUpdate] = Field(default_factory=list)
    world_state_updates: list[str] = Field(default_factory=list)
    timeline_markers: list[str] = Field(default_factory=list)
    locations_visited: list[str] = Field(default_factory=list)
    foreshadowing_opened: list[ForeshadowingMemory] = Field(default_factory=list)
    foreshadowing_progressed: list[str] = Field(default_factory=list)
    foreshadowing_closed: list[str] = Field(default_factory=list)
    unresolved_conflicts: list[str] = Field(default_factory=list)
    important_quotes_or_rules: list[str] = Field(default_factory=list)
    importance_score: float = 0.5


class ArcMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    arc_id: str
    chapter_range: tuple[int, int]
    arc_summary: str
    must_remember: list[str] = Field(default_factory=list)
    open_foreshadowing_ids: list[str] = Field(default_factory=list)
    major_character_changes: list[str] = Field(default_factory=list)
    major_relationship_changes: list[str] = Field(default_factory=list)
    major_world_changes: list[str] = Field(default_factory=list)
    open_conflicts: list[str] = Field(default_factory=list)


class TemporaryStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    field: str
    value: str
    effective_from_chapter: int
    effective_until_chapter: int | None = None


class CharacterRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    current_status: dict[str, Any] = Field(default_factory=dict)
    last_updated_in_chapter: int | None = None
    active_flags: list[str] = Field(default_factory=list)
    temporary_status: list[TemporaryStatus] = Field(default_factory=list)


class CharacterState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    characters: list[CharacterRecord] = Field(default_factory=list)


class WorldState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: list[str] = Field(default_factory=list)
    active_conflicts: list[str] = Field(default_factory=list)
    active_locations: list[str] = Field(default_factory=list)


class OpenLoopItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    summary: str
    status: str = "open"
    priority: str = "medium"
    related_chapters: list[int] = Field(default_factory=list)


class OpenLoopState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[OpenLoopItem] = Field(default_factory=list)


class TimelineEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: int
    entity: str | None = None
    field: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    reason: str | None = None


class TimelineState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[TimelineEntry] = Field(default_factory=list)


class StickyConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    source: str = "system"
    scope: str = "global"
    priority: str = "medium"
    instruction: str
    rationale: str | None = None
    active: bool = True


class StickyConstraintState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[StickyConstraint] = Field(default_factory=list)


class CompactRagHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str
    chapter_id: int
    why_relevant: str
    compressed_quote: str
    score: float = 0.0
