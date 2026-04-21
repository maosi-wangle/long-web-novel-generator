from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from src.config import REPO_ROOT
from src.llm import CompatibleLLMClient
from src.orchestrator.state import ProjectState
from src.schemas.chapter import DetailOutline
from src.schemas.outline import ActOutline, ChapterPlan, NovelOutline
from src.schemas.project import ProjectRecord
from src.schemas.tool_io import RagSearchRequest, RagSearchResult
from src.storage.markdown_store import MarkdownStore
from src.tools import RagTool


@dataclass(frozen=True)
class ChapterSelection:
    act_index: int
    act: ActOutline
    chapter: ChapterPlan


class DetailOutlineAgent:
    """Generate chapter-level detail outlines and writer packets."""

    def __init__(
        self,
        client: CompatibleLLMClient | None = None,
        markdown_store: MarkdownStore | None = None,
    ) -> None:
        self.client = client or CompatibleLLMClient()
        self.markdown_store = markdown_store or MarkdownStore()
        self.prompt_template = self._load_prompt()

    def generate_detail_outline(
        self,
        *,
        project: ProjectRecord,
        state: ProjectState,
        outline: NovelOutline,
        chapter_id: int | None = None,
        extra_brief: str | None = None,
    ) -> DetailOutline:
        selection = self._resolve_target_chapter(outline, state, chapter_id)
        rag_result = self._retrieve_context(project.project_id, selection, state)
        chapter_context = self._build_chapter_context(outline, selection, state, project.project_id, rag_result)
        analysis = self._analyze_chapter(project, state, outline, chapter_context, extra_brief)
        detail_outline = self._draft_detail_outline(project, state, outline, chapter_context, analysis, extra_brief)
        detail_outline = self._normalize_detail_outline(detail_outline, selection, rag_result)
        return detail_outline

    def _resolve_target_chapter(
        self,
        outline: NovelOutline,
        state: ProjectState,
        chapter_id: int | None,
    ) -> ChapterSelection:
        flattened: list[ChapterSelection] = []
        for act_index, act in enumerate(outline.acts):
            for chapter in act.chapters:
                flattened.append(ChapterSelection(act_index=act_index, act=act, chapter=chapter))

        if not flattened:
            raise RuntimeError("Outline does not contain any chapters.")

        target_id = chapter_id
        if target_id is None:
            if state.current_chapter_index > state.last_completed_chapter:
                target_id = state.current_chapter_index
            else:
                target_id = state.last_completed_chapter + 1

        if target_id <= 0:
            target_id = 1

        for selection in flattened:
            if selection.chapter.chapter_id == target_id:
                return selection

        raise RuntimeError(
            f"Requested chapter_id={target_id} is outside the outline range 1-{flattened[-1].chapter.chapter_id}."
        )

    def _build_chapter_context(
        self,
        outline: NovelOutline,
        selection: ChapterSelection,
        state: ProjectState,
        project_id: str,
        rag_result: RagSearchResult,
    ) -> dict[str, Any]:
        flattened = [chapter for act in outline.acts for chapter in act.chapters]
        current_index = next(
            index for index, chapter in enumerate(flattened) if chapter.chapter_id == selection.chapter.chapter_id
        )
        previous_chapter = flattened[current_index - 1] if current_index > 0 else None
        next_chapter = flattened[current_index + 1] if current_index + 1 < len(flattened) else None

        recent_ids = [chapter.chapter_id for chapter in flattened if chapter.chapter_id <= state.last_completed_chapter][-2:]
        recent_written_context = self.markdown_store.load_recent_chapter_context(
            project_id,
            chapter_ids=recent_ids,
        )

        return {
            "current_act_index": selection.act_index,
            "current_act": selection.act.model_dump(mode="json"),
            "current_chapter": selection.chapter.model_dump(mode="json"),
            "previous_chapter": previous_chapter.model_dump(mode="json") if previous_chapter else None,
            "next_chapter": next_chapter.model_dump(mode="json") if next_chapter else None,
            "recent_written_context": recent_written_context,
            "rag_hits": [hit.model_dump(mode="json") for hit in rag_result.hits],
            "project_progress": state.model_dump(mode="json"),
            "foreshadowing": [item.model_dump(mode="json") for item in outline.foreshadowing],
            "global_constraints": outline.constraints,
            "world_setting": outline.world_setting,
            "core_characters": [character.model_dump(mode="json") for character in outline.characters],
        }

    def _retrieve_context(
        self,
        project_id: str,
        selection: ChapterSelection,
        state: ProjectState,
    ) -> RagSearchResult:
        history_upper_bound = min(state.last_completed_chapter, selection.chapter.chapter_id - 1)
        if history_upper_bound <= 0:
            return RagSearchResult(query="", hits=[])

        query = self._build_retrieval_query(selection)
        request = RagSearchRequest(
            query=query,
            top_k=4,
            search_mode="hybrid",
            chapter_scope=(1, history_upper_bound),
        )
        return RagTool(project_id).search(request)

    @staticmethod
    def _build_retrieval_query(selection: ChapterSelection) -> str:
        beats = "; ".join(selection.chapter.beats[:4])
        return (
            f"chapter_title: {selection.chapter.title}\n"
            f"chapter_goal: {selection.chapter.goal}\n"
            f"act_title: {selection.act.title}\n"
            f"beats: {beats}"
        )

    def _analyze_chapter(
        self,
        project: ProjectRecord,
        state: ProjectState,
        outline: NovelOutline,
        chapter_context: dict[str, Any],
        extra_brief: str | None,
    ) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": self.prompt_template},
            {
                "role": "user",
                "content": (
                    "阶段一：先分析当前进度和当前章节职责，不要直接写正文。\n"
                    "你必须基于全局大纲、项目状态和最近已写内容，给出结构化章节分析。\n"
                    "必须只输出 JSON，结构如下：\n"
                    "{\n"
                    '  "current_progress_assessment": "当前写作进度判断",\n'
                    '  "chapter_role_in_story": "这一章在全书中的职责",\n'
                    '  "must_cover": ["本章必须覆盖的信息"],\n'
                    '  "must_avoid": ["本章不能写穿的信息"],\n'
                    '  "continuity_notes": ["与前文衔接注意点"],\n'
                    '  "foreshadowing_targets": ["本章应埋设/推进的伏笔"],\n'
                    '  "scene_strategy": ["场景拆分原则"],\n'
                    '  "style_rules": ["给 Writer 的风格规则"],\n'
                    '  "ending_hook_focus": "本章结尾应该制造的钩子"\n'
                    "}\n\n"
                    f"项目信息：\n{self._project_context(project, extra_brief)}\n\n"
                    f"全局总纲概览：\n{self._outline_context(outline)}\n\n"
                    f"当前章节上下文：\n{json.dumps(chapter_context, ensure_ascii=False, indent=2)}"
                ),
            },
        ]
        return self.client.chat_json(
            model=self.client.settings.detail_outline_model,
            messages=messages,
            temperature=0.5,
            max_tokens=2600,
        )

    def _draft_detail_outline(
        self,
        project: ProjectRecord,
        state: ProjectState,
        outline: NovelOutline,
        chapter_context: dict[str, Any],
        analysis: dict[str, Any],
        extra_brief: str | None,
    ) -> DetailOutline:
        messages = [
            {"role": "system", "content": self.prompt_template},
            {
                "role": "user",
                "content": (
                    "阶段二：根据章节分析结果，输出当前章节的 DetailOutline。\n"
                    "要求：\n"
                    "1. 这是写作细纲，不是正文。\n"
                    "2. scene_briefs 建议 3 到 5 个。\n"
                    "3. writer_packet 只能包含当前章节局部信息，不能泄露完整总纲。\n"
                    "4. internal_reasoning_package 可保留全局对齐信息。\n"
                    "5. retrieved_context 只能使用给定的 recent_written_context 和 rag_hits，不要虚构检索结果。\n"
                    "6. 必须只输出合法 JSON，且兼容 DetailOutline schema。\n\n"
                    "DetailOutline schema 关键字段示例：\n"
                    "{\n"
                    '  "chapter_id": 1,\n'
                    '  "title": "章节标题",\n'
                    '  "chapter_goal": "本章目标",\n'
                    '  "internal_reasoning_package": {\n'
                    '    "current_progress_assessment": "当前进度判断",\n'
                    '    "outline_alignment": ["与总纲的对齐点"],\n'
                    '    "foreshadowing_targets": ["伏笔目标"],\n'
                    '    "continuity_risks": ["连续性风险"]\n'
                    "  },\n"
                    '  "writer_packet": {\n'
                    '    "chapter_id": 1,\n'
                    '    "chapter_title": "章节标题",\n'
                    '    "chapter_goal": "本章目标",\n'
                    '    "scene_briefs": [\n'
                    "      {\n"
                    '        "scene_id": 1,\n'
                    '        "title": "场景标题",\n'
                    '        "location": "场景地点",\n'
                    '        "characters": ["角色A"],\n'
                    '        "objective": "本场景目标",\n'
                    '        "must_include": ["必须出现的信息"],\n'
                    '        "avoid": ["不能直接写出的信息"],\n'
                    '        "desired_length": 900\n'
                    "      }\n"
                    "    ],\n"
                    '    "style_rules": ["风格规则"],\n'
                    '    "continuity_notes": ["衔接提醒"],\n'
                    '    "forbidden_reveals": ["禁泄露信息"],\n'
                    '    "retrieved_context": ["历史正文摘要"]\n'
                    "  },\n"
                    '  "ending_hook": "结尾钩子",\n'
                    '  "user_constraints": ["额外限制"]\n'
                    "}\n\n"
                    f"项目信息：\n{self._project_context(project, extra_brief)}\n\n"
                    f"全局总纲概览：\n{self._outline_context(outline)}\n\n"
                    f"当前章节上下文：\n{json.dumps(chapter_context, ensure_ascii=False, indent=2)}\n\n"
                    f"章节分析结果：\n{json.dumps(analysis, ensure_ascii=False, indent=2)}"
                ),
            },
        ]
        raw = self.client.chat_json(
            model=self.client.settings.detail_outline_model,
            messages=messages,
            temperature=0.6,
            max_tokens=3800,
        )
        try:
            return DetailOutline.model_validate(raw)
        except ValidationError as exc:
            raise RuntimeError(f"DetailOutlineAgent returned invalid detail outline schema: {exc}") from exc

    def _normalize_detail_outline(
        self,
        detail_outline: DetailOutline,
        selection: ChapterSelection,
        rag_result: RagSearchResult,
    ) -> DetailOutline:
        detail_outline.chapter_id = selection.chapter.chapter_id
        detail_outline.title = selection.chapter.title
        detail_outline.chapter_goal = selection.chapter.goal
        detail_outline.writer_packet.chapter_id = selection.chapter.chapter_id
        detail_outline.writer_packet.chapter_title = selection.chapter.title
        detail_outline.writer_packet.chapter_goal = selection.chapter.goal

        actual_context = self._format_rag_context(rag_result)
        if actual_context:
            detail_outline.writer_packet.retrieved_context = actual_context
        elif not detail_outline.writer_packet.retrieved_context:
            detail_outline.writer_packet.retrieved_context = self._format_rag_context(rag_result)

        normalized_scenes = []
        for index, scene in enumerate(detail_outline.writer_packet.scene_briefs, start=1):
            scene.scene_id = index
            normalized_scenes.append(scene)
        detail_outline.writer_packet.scene_briefs = normalized_scenes
        return detail_outline

    @staticmethod
    def _format_rag_context(rag_result: RagSearchResult) -> list[str]:
        contexts: list[str] = []
        for hit in rag_result.hits:
            contexts.append(f"{hit.chunk_id}: chapter_{hit.chapter_id} {hit.summary}")
        return contexts

    def _load_prompt(self) -> str:
        prompt_path = Path(REPO_ROOT) / "src" / "agents" / "prompts" / "detail_outline.md"
        return prompt_path.read_text(encoding="utf-8")

    @staticmethod
    def _project_context(project: ProjectRecord, extra_brief: str | None) -> str:
        payload: dict[str, Any] = project.model_dump(mode="json")
        if extra_brief:
            payload["extra_brief"] = extra_brief
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _outline_context(outline: NovelOutline) -> str:
        payload = {
            "title": outline.title,
            "genre": outline.genre,
            "tone": outline.tone,
            "premise": outline.premise,
            "acts": [act.model_dump(mode="json") for act in outline.acts],
            "foreshadowing": [item.model_dump(mode="json") for item in outline.foreshadowing],
            "constraints": outline.constraints,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
