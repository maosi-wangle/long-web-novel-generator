from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class SceneBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: int
    title: str | None = None
    location: str | None = None
    characters: list[str] = Field(default_factory=list)
    objective: str
    must_include: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    desired_length: int | None = None


class InternalReasoningPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_progress_assessment: str
    outline_alignment: list[str] = Field(default_factory=list)
    foreshadowing_targets: list[str] = Field(default_factory=list)
    continuity_risks: list[str] = Field(default_factory=list)


class WriterPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: int
    chapter_title: str
    chapter_goal: str
    scene_briefs: list[SceneBrief] = Field(default_factory=list)
    style_rules: list[str] = Field(default_factory=list)
    continuity_notes: list[str] = Field(default_factory=list)
    forbidden_reveals: list[str] = Field(default_factory=list)
    retrieved_context: list[str] = Field(default_factory=list)


class DetailOutline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: int
    title: str
    chapter_goal: str
    internal_reasoning_package: InternalReasoningPackage
    writer_packet: WriterPacket
    ending_hook: str | None = None
    user_constraints: list[str] = Field(default_factory=list)


class ChapterArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: int
    title: str
    markdown_body: str
    summary: str
    new_facts: list[str] = Field(default_factory=list)
    foreshadow_candidates: list[str] = Field(default_factory=list)
    referenced_chunks: list[str] = Field(default_factory=list)


class SceneDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: int
    title: str | None = None
    markdown_body: str
    scene_summary: str
    new_facts: list[str] = Field(default_factory=list)
    foreshadow_candidates: list[str] = Field(default_factory=list)


class ChapterRollup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    new_facts: list[str] = Field(default_factory=list)
    foreshadow_candidates: list[str] = Field(default_factory=list)
