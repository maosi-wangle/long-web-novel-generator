from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from src.schemas.outline import ChapterBlueprint, StoryDirectionCandidate


class StoryDirectionBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[StoryDirectionCandidate] = Field(default_factory=list)


class ChapterBlueprintBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapters: list[ChapterBlueprint] = Field(default_factory=list)


class DetailOutlineAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current_progress_assessment: str
    chapter_role_in_story: str
    must_cover: list[str] = Field(default_factory=list)
    must_avoid: list[str] = Field(default_factory=list)
    continuity_notes: list[str] = Field(default_factory=list)
    foreshadowing_targets: list[str] = Field(default_factory=list)
    scene_strategy: list[str] = Field(default_factory=list)
    style_rules: list[str] = Field(default_factory=list)
    ending_hook_focus: str
