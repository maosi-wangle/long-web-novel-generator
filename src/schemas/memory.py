from __future__ import annotations

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

