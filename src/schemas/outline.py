from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CharacterProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    role: str
    goal: str | None = None
    conflict: str | None = None
    arc: str | None = None
    public_traits: list[str] = Field(default_factory=list)
    secrets: list[str] = Field(default_factory=list)


class ScenePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scene_id: int = 0
    title: str
    objective: str
    beats: list[str] = Field(default_factory=list)
    location: str | None = None
    hook: str | None = None
    carry_in: list[str] = Field(default_factory=list)
    entry_state: list[str] = Field(default_factory=list)
    exit_state: list[str] = Field(default_factory=list)
    open_threads_created: list[str] = Field(default_factory=list)
    open_threads_resolved: list[str] = Field(default_factory=list)
    next_scene_must_address: list[str] = Field(default_factory=list)
    transition_bridge: str | None = None


class ChapterPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: int
    title: str
    goal: str
    summary: str | None = None
    beats: list[str] = Field(default_factory=list)
    hook: str | None = None
    scenes: list[ScenePlan] = Field(default_factory=list)


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


class TurningPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    function: str
    expected_chapter_window: str | None = None


class StoryStructure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    story_id: str
    title: str
    premise: str
    theme: str | None = None
    core_conflict: str
    protagonist_goal: str
    antagonistic_force: str
    stakes: str
    start_state: list[str] = Field(default_factory=list)
    target_end_state: list[str] = Field(default_factory=list)
    must_preserve: list[str] = Field(default_factory=list)
    world_setting: dict[str, str] = Field(default_factory=dict)
    key_characters: list[CharacterProfile] = Field(default_factory=list)
    foreshadowing: list[ForeshadowingItem] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    major_turning_points: list[TurningPoint] = Field(default_factory=list)
    ending_type: str = "阶段性闭合但允许留尾钩"
    chapter_budget: int = 6


class ChapterBlueprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapter_id: int
    title: str
    chapter_role: str = "推进章"
    core_function: str
    entering_state: list[str] = Field(default_factory=list)
    must_resolve: list[str] = Field(default_factory=list)
    must_advance: list[str] = Field(default_factory=list)
    cannot_cross: list[str] = Field(default_factory=list)
    foreshadow_op: list[str] = Field(default_factory=list)
    twist_level: str = "medium"
    suspense_density: str = "medium"
    chapter_summary: str
    state_delta: list[str] = Field(default_factory=list)
    exit_obligation: list[str] = Field(default_factory=list)
    recommended_scene_count: int = 3
    hook: str | None = None


class NovelOutline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    genre: list[str] = Field(default_factory=list)
    tone: str | None = None
    premise: str
    world_setting: dict[str, str] = Field(default_factory=dict)
    characters: list[CharacterProfile] = Field(default_factory=list)
    story_structure: StoryStructure | None = None
    chapter_blueprints: list[ChapterBlueprint] = Field(default_factory=list)
    acts: list[ActOutline] = Field(default_factory=list)
    foreshadowing: list[ForeshadowingItem] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    discarded_directions: list[StoryDirectionCandidate] = Field(default_factory=list)

    @model_validator(mode="after")
    def sync_outline_views(self) -> "NovelOutline":
        if not self.chapter_blueprints and self.acts:
            self.chapter_blueprints = [
                ChapterBlueprint(
                    chapter_id=chapter.chapter_id,
                    title=chapter.title,
                    core_function=chapter.goal,
                    chapter_summary=chapter.summary or chapter.goal,
                    state_delta=_compact_list([*(chapter.beats or []), chapter.hook or ""]),
                    exit_obligation=_compact_list([chapter.hook] if chapter.hook else []),
                    hook=chapter.hook,
                )
                for act in self.acts
                for chapter in act.chapters
            ]

        if not self.acts and self.chapter_blueprints:
            self.acts = [_build_closed_story_act(self.chapter_blueprints)]

        if self.acts and self.chapter_blueprints:
            self.acts = [_build_closed_story_act(self.chapter_blueprints)]

        return self


def _build_closed_story_act(chapter_blueprints: list[ChapterBlueprint]) -> ActOutline:
    chapters = [
        ChapterPlan(
            chapter_id=blueprint.chapter_id,
            title=blueprint.title,
            goal=blueprint.core_function,
            summary=blueprint.chapter_summary,
            beats=_compact_list([*blueprint.must_resolve, *blueprint.must_advance, *blueprint.state_delta]),
            hook=blueprint.hook or (blueprint.exit_obligation[0] if blueprint.exit_obligation else None),
        )
        for blueprint in chapter_blueprints
    ]
    act_title = "闭环故事"
    act_summary = "；".join(blueprint.chapter_summary for blueprint in chapter_blueprints[:3]) or "闭环推进"
    return ActOutline(act_id=1, title=act_title, summary=act_summary, chapters=chapters)


def _compact_list(items: list[str]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for item in items:
        text = item.strip() if item else ""
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
    return values
