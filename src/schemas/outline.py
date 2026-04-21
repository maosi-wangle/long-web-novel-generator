from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CharacterProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    role: str
    goal: str | None = None
    conflict: str | None = None
    arc: str | None = None
    public_traits: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)


class ChapterPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: int
    title: str
    goal: str
    beats: list[str] = Field(default_factory=list)
    hook: str | None = None


class ActOutline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    act_id: int
    title: str
    summary: str
    chapters: list[ChapterPlan] = Field(default_factory=list)


class ForeshadowingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    setup: str
    payoff_plan: str
    reveal_window: str | None = None


class StoryDirectionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    premise: str
    strengths: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    score: float | None = None


class NovelOutline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    genre: list[str] = Field(default_factory=list)
    tone: str | None = None
    premise: str
    world_setting: dict[str, str] = Field(default_factory=dict)
    characters: list[CharacterProfile] = Field(default_factory=list)
    acts: list[ActOutline] = Field(default_factory=list)
    foreshadowing: list[ForeshadowingItem] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    discarded_directions: list[StoryDirectionCandidate] = Field(default_factory=list)

