from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from src.config import REPO_ROOT
from src.context import ContextAssembler
from src.llm import CompatibleLLMClient
from src.schemas import WriterContext
from src.schemas.chapter import ChapterArtifact, ChapterRollup, DetailOutline, SceneBrief, SceneDraft
from src.schemas.project import ProjectRecord
from src.schemas.tool_io import RagSearchRequest, RagSearchResult
from src.tools import RagTool


class WriterAgent:
    """Write chapter prose scene by scene from a local writer packet."""

    MIN_SCENE_LENGTH = 1400

    def __init__(
        self,
        client: CompatibleLLMClient | None = None,
        context_assembler: ContextAssembler | None = None,
    ) -> None:
        self.client = client or CompatibleLLMClient()
        self.context_assembler = context_assembler or ContextAssembler()
        self.prompt_template = self._load_prompt()

    def write_chapter(
        self,
        *,
        project: ProjectRecord,
        detail_outline: DetailOutline,
        extra_brief: str | None = None,
    ) -> ChapterArtifact:
        rag_result = self._retrieve_context(project.project_id, detail_outline)
        writer_context = self.context_assembler.build_writer_context(
            project=project,
            detail_outline=detail_outline,
            rag_result=rag_result,
            extra_brief=extra_brief,
        )

        scene_briefs = detail_outline.writer_packet.scene_briefs or [
            SceneBrief(
                scene_id=1,
                title=detail_outline.title,
                objective=detail_outline.chapter_goal,
                desired_length=self.MIN_SCENE_LENGTH,
            )
        ]

        drafted_scenes: list[SceneDraft] = []
        for scene_index, scene_brief in enumerate(scene_briefs, start=1):
            drafted_scenes.append(
                self._write_scene(
                    project=project,
                    writer_context=writer_context,
                    scene_brief=scene_brief,
                    drafted_scenes=drafted_scenes,
                    scene_index=scene_index,
                    total_scenes=len(scene_briefs),
                )
            )

        chapter_rollup = self._rollup_chapter(
            project=project,
            writer_context=writer_context,
            detail_outline=detail_outline,
            drafted_scenes=drafted_scenes,
        )
        artifact = ChapterArtifact(
            chapter_id=detail_outline.chapter_id,
            title=detail_outline.title,
            markdown_body="\n\n".join(scene.markdown_body.strip() for scene in drafted_scenes if scene.markdown_body.strip()),
            summary=chapter_rollup.summary,
            new_facts=self._merge_list_fields([scene.new_facts for scene in drafted_scenes], chapter_rollup.new_facts),
            foreshadow_candidates=self._merge_list_fields(
                [scene.foreshadow_candidates for scene in drafted_scenes],
                chapter_rollup.foreshadow_candidates,
            ),
            referenced_chunks=list(writer_context.source_chunk_ids),
        )
        return self._normalize_artifact(artifact, detail_outline)

    def _write_scene(
        self,
        *,
        project: ProjectRecord,
        writer_context: WriterContext,
        scene_brief: SceneBrief,
        drafted_scenes: list[SceneDraft],
        scene_index: int,
        total_scenes: int,
    ) -> SceneDraft:
        messages = [
            {"role": "system", "content": self.prompt_template},
            {
                "role": "user",
                "content": (
                    "请只完成当前场景的正文写作，并返回 SceneDraft JSON。\n\n"
                    f"项目上下文：\n{self._project_context(project, writer_context.project_meta.get('extra_brief'))}\n\n"
                    f"当前场景写作包：\n{self._scene_context(writer_context, scene_brief, drafted_scenes, scene_index, total_scenes)}"
                ),
            },
        ]
        scene_draft = self.client.chat_model(
            model=self.client.settings.writer_model,
            response_model=SceneDraft,
            messages=messages,
            temperature=0.82,
            max_tokens=3200,
        )
        scene_draft.scene_id = scene_brief.scene_id
        if scene_brief.title:
            scene_draft.title = scene_brief.title
        scene_draft.markdown_body = self._strip_scene_headings(scene_draft.markdown_body)
        scene_draft.scene_summary = scene_draft.scene_summary.strip()
        return scene_draft

    def _rollup_chapter(
        self,
        *,
        project: ProjectRecord,
        writer_context: WriterContext,
        detail_outline: DetailOutline,
        drafted_scenes: list[SceneDraft],
    ) -> ChapterRollup:
        messages = [
            {"role": "system", "content": self.prompt_template},
            {
                "role": "user",
                "content": (
                    "基于已经写好的全部场景，整理整章摘要、关键新事实和伏笔候选，返回 ChapterRollup JSON。\n\n"
                    f"项目上下文：\n{self._project_context(project, writer_context.project_meta.get('extra_brief'))}\n\n"
                    f"章节写作上下文：\n{self._writer_context(writer_context)}\n\n"
                    f"章节目标：\n{json.dumps({'chapter_id': detail_outline.chapter_id, 'title': detail_outline.title, 'chapter_goal': detail_outline.chapter_goal}, ensure_ascii=False, indent=2)}\n\n"
                    f"已完成场景：\n{self._scene_rollup_payload(drafted_scenes)}"
                ),
            },
        ]
        rollup = self.client.chat_model(
            model=self.client.settings.writer_model,
            response_model=ChapterRollup,
            messages=messages,
            temperature=0.45,
            max_tokens=1200,
        )
        rollup.summary = rollup.summary.strip()
        return rollup

    def _normalize_artifact(
        self,
        artifact: ChapterArtifact,
        detail_outline: DetailOutline,
    ) -> ChapterArtifact:
        artifact.chapter_id = detail_outline.chapter_id
        artifact.title = detail_outline.title
        artifact.markdown_body = artifact.markdown_body.strip()
        artifact.summary = artifact.summary.strip()
        artifact.new_facts = self._dedupe_preserve_order(artifact.new_facts)
        artifact.foreshadow_candidates = self._dedupe_preserve_order(artifact.foreshadow_candidates)
        artifact.referenced_chunks = self._dedupe_preserve_order(artifact.referenced_chunks)
        return artifact

    def _retrieve_context(self, project_id: str, detail_outline: DetailOutline) -> RagSearchResult:
        if detail_outline.chapter_id <= 1:
            return RagSearchResult(query="", hits=[])

        request = RagSearchRequest(
            query=self._build_retrieval_query(detail_outline),
            top_k=3,
            search_mode="hybrid",
            chapter_scope=(1, detail_outline.chapter_id - 1),
        )
        return RagTool(project_id).search(request)

    @staticmethod
    def _build_retrieval_query(detail_outline: DetailOutline) -> str:
        scene_goals = "; ".join(scene.objective for scene in detail_outline.writer_packet.scene_briefs[:4])
        must_include = []
        for scene in detail_outline.writer_packet.scene_briefs[:4]:
            must_include.extend(scene.must_include[:2])
        return (
            f"chapter_title: {detail_outline.title}\n"
            f"chapter_goal: {detail_outline.chapter_goal}\n"
            f"scene_objectives: {scene_goals}\n"
            f"must_include: {'; '.join(must_include[:6])}"
        )

    def _load_prompt(self) -> str:
        prompt_path = Path(REPO_ROOT) / "src" / "agents" / "prompts" / "writer.md"
        return prompt_path.read_text(encoding="utf-8")

    @staticmethod
    def _project_context(project: ProjectRecord, extra_brief: str | None) -> str:
        payload: dict[str, Any] = {
            "title": project.title,
            "premise": project.premise,
            "genre": project.genre,
            "tone": project.tone,
        }
        if extra_brief:
            payload["extra_brief"] = extra_brief
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _scene_context(
        self,
        writer_context: WriterContext,
        scene_brief: SceneBrief,
        drafted_scenes: list[SceneDraft],
        scene_index: int,
        total_scenes: int,
    ) -> str:
        scene_plan = [
            {
                "scene_id": scene.scene_id,
                "title": scene.title,
                "objective": scene.objective,
            }
            for scene in self._scene_briefs_from_packet(writer_context)
        ]
        payload = {
            "chapter": {
                "chapter_id": writer_context.chapter_id,
                "title": writer_context.title,
                "chapter_goal": writer_context.chapter_goal,
                "ending_hook": writer_context.ending_hook,
            },
            "scene_position": {
                "scene_index": scene_index,
                "total_scenes": total_scenes,
            },
            "scene_plan": scene_plan,
            "current_scene": {
                "scene_id": scene_brief.scene_id,
                "title": scene_brief.title,
                "location": scene_brief.location,
                "characters": scene_brief.characters,
                "objective": scene_brief.objective,
                "must_include": scene_brief.must_include,
                "avoid": scene_brief.avoid,
                "target_length": max(scene_brief.desired_length or 0, self.MIN_SCENE_LENGTH),
            },
            "story_facts": writer_context.story_facts,
            "character_snapshot": writer_context.character_snapshot,
            "world_snapshot": writer_context.world_snapshot,
            "active_threads": writer_context.active_threads,
            "style_rules": writer_context.style_rules,
            "writer_packet": {
                "style_rules": writer_context.writer_packet.get("style_rules", []),
                "continuity_notes": writer_context.writer_packet.get("continuity_notes", []),
                "forbidden_reveals": writer_context.writer_packet.get("forbidden_reveals", []),
                "retrieved_context": writer_context.writer_packet.get("retrieved_context", []),
            },
            "completed_scene_summaries": [
                {
                    "scene_id": scene.scene_id,
                    "title": scene.title,
                    "summary": scene.scene_summary,
                }
                for scene in drafted_scenes
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _writer_context(writer_context: WriterContext) -> str:
        payload = {
            "project_meta": writer_context.project_meta,
            "chapter_id": writer_context.chapter_id,
            "title": writer_context.title,
            "chapter_goal": writer_context.chapter_goal,
            "writer_packet": writer_context.writer_packet,
            "ending_hook": writer_context.ending_hook,
            "user_constraints": writer_context.user_constraints,
            "story_facts": writer_context.story_facts,
            "character_snapshot": writer_context.character_snapshot,
            "world_snapshot": writer_context.world_snapshot,
            "active_threads": writer_context.active_threads,
            "style_rules": writer_context.style_rules,
            "budget_report": writer_context.budget_report.model_dump(mode="json") if writer_context.budget_report else None,
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _scene_rollup_payload(drafted_scenes: list[SceneDraft]) -> str:
        payload = [
            {
                "scene_id": scene.scene_id,
                "title": scene.title,
                "scene_summary": scene.scene_summary,
                "new_facts": scene.new_facts,
                "foreshadow_candidates": scene.foreshadow_candidates,
            }
            for scene in drafted_scenes
        ]
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _scene_briefs_from_packet(writer_context: WriterContext) -> list[SceneBrief]:
        return [SceneBrief.model_validate(item) for item in writer_context.writer_packet.get("scene_briefs", [])]

    @staticmethod
    def _merge_list_fields(scene_lists: list[list[str]], rollup_items: list[str]) -> list[str]:
        merged: list[str] = []
        for items in scene_lists:
            merged.extend(items)
        merged.extend(rollup_items)
        return WriterAgent._dedupe_preserve_order(merged)

    @staticmethod
    def _dedupe_preserve_order(items: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for item in items:
            normalized = item.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered

    @staticmethod
    def _strip_scene_headings(markdown_body: str) -> str:
        cleaned_lines = []
        for line in markdown_body.splitlines():
            if re.match(r"^\s{0,3}#{1,6}\s+", line):
                continue
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()
