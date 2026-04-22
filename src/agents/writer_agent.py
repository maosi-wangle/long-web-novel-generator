from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.context import ContextAssembler
from src.config import REPO_ROOT
from src.llm import CompatibleLLMClient
from src.schemas import WriterContext
from src.schemas.chapter import ChapterArtifact, DetailOutline
from src.schemas.project import ProjectRecord
from src.schemas.tool_io import RagSearchRequest, RagSearchResult
from src.tools import RagTool


class WriterAgent:
    """Write chapter prose from a local writer packet only."""

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
        retrieved_context = list(writer_context.writer_packet.get("retrieved_context", []))
        messages = [
            {"role": "system", "content": self.prompt_template},
            {
                "role": "user",
                "content": (
                    "请根据给定的局部写作包生成本章正文。\n"
                    "要求：\n"
                    "1. 你不知道完整总纲，只能基于下面提供的局部信息写作。\n"
                    "2. 正文使用自然中文 prose，不要输出标题、元信息或额外说明。\n"
                    "3. 必须遵守 forbidden_reveals，不得提前泄露未允许的信息。\n"
                    "4. 必须让 ending_hook 在章节结尾形成明显但自然的悬念。\n"
                    "5. 必须输出合法 JSON，不要使用 Markdown 代码块。\n\n"
                    "输出结构：\n"
                    "{\n"
                    '  "chapter_id": 1,\n'
                    '  "title": "章节标题",\n'
                    '  "markdown_body": "章节正文内容",\n'
                    '  "summary": "150字以内章节摘要",\n'
                    '  "new_facts": ["本章新增事实"],\n'
                    '  "foreshadow_candidates": ["本章可回收伏笔"],\n'
                    '  "referenced_chunks": ["引用过的记忆片段ID或章节标识"]\n'
                    "}\n\n"
                    f"项目信息（仅风格层可用）：\n{self._project_context(project, extra_brief)}\n\n"
                    f"局部写作包：\n{self._writer_context(writer_context)}"
                ),
            },
        ]
        artifact = self.client.chat_model(
            model=self.client.settings.writer_model,
            response_model=ChapterArtifact,
            messages=messages,
            temperature=0.75,
            max_tokens=5200,
        )

        return self._normalize_artifact(artifact, detail_outline, retrieved_context)

    def _normalize_artifact(
        self,
        artifact: ChapterArtifact,
        detail_outline: DetailOutline,
        retrieved_context: list[str],
    ) -> ChapterArtifact:
        artifact.chapter_id = detail_outline.chapter_id
        artifact.title = detail_outline.title
        artifact.markdown_body = artifact.markdown_body.strip()
        artifact.summary = artifact.summary.strip()
        if not artifact.referenced_chunks:
            artifact.referenced_chunks = self._build_reference_list(retrieved_context)
        return artifact

    @staticmethod
    def _build_reference_list(retrieved_context: list[str]) -> list[str]:
        references = []
        for item in retrieved_context:
            if item:
                references.append(item.split(":", 1)[0].strip())
        return references

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

    @staticmethod
    def _writer_context(writer_context: WriterContext) -> str:
        return json.dumps(writer_context.model_dump(mode="json"), ensure_ascii=False, indent=2)
