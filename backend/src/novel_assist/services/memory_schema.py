from __future__ import annotations

from typing import Literal, TypedDict


MemoryType = Literal["event", "fact", "entity", "relation"]
MemoryStatus = Literal["active", "archived"]
EntityCategory = Literal["character", "faction", "place", "artifact", "concept"]


class HarvestBaseItem(TypedDict, total=False):
    memory_type: Literal["event", "fact"]
    title: str
    content: str
    tags: list[str]
    salience: float
    source_excerpt: str
    entity_refs: list[str]


class HarvestEntity(TypedDict, total=False):
    name: str
    category: EntityCategory
    summary: str
    tags: list[str]
    salience: float
    aliases: list[str]


class HarvestRelation(TypedDict, total=False):
    left: str
    right: str
    relation_type: str
    summary: str
    tags: list[str]
    salience: float


class HarvestSections(TypedDict, total=False):
    base_items: list[HarvestBaseItem]
    entities: list[HarvestEntity]
    relations: list[HarvestRelation]


class MemoryItem(TypedDict, total=False):
    """Structured knowledge harvested from a chapter for future retrieval."""

    memory_id: str
    novel_id: str
    chapter_id: str
    chapter_number: int
    memory_type: MemoryType
    title: str
    content: str
    tags: list[str]
    entity_ids: list[str]
    relation_ids: list[str]
    salience: float
    valid_from_chapter: int
    status: MemoryStatus
    source_excerpt: str
    source_trace_id: str
    created_at: str


class RetrievalHit(TypedDict, total=False):
    """Normalized retrieval result shape, designed to stay stable for future GraphRAG."""

    source_id: str
    source_type: str
    title: str
    snippet: str
    score: float
    reason: str
    chapter_id: str
    entity_ids: list[str]
    memory_type: MemoryType
    tags: list[str]
