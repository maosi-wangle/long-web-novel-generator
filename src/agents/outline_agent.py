from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import REPO_ROOT
from src.llm import CompatibleLLMClient
from src.schemas import StoryDirectionBatch
from src.schemas.outline import NovelOutline, StoryDirectionCandidate
from src.schemas.project import ProjectRecord


class OutlineAgent:
    """Generate a global outline using a lightweight ToT workflow."""

    def __init__(self, client: CompatibleLLMClient | None = None) -> None:
        self.client = client or CompatibleLLMClient()
        self.prompt_template = self._load_prompt()

    def generate_outline(
        self,
        project: ProjectRecord,
        extra_brief: str | None = None,
    ) -> NovelOutline:
        candidates = self._generate_candidates(project, extra_brief)
        evaluated = self._evaluate_candidates(project, candidates, extra_brief)
        outline = self._finalize_outline(project, evaluated, extra_brief)
        outline = self._normalize_outline(outline)
        outline.discarded_directions = evaluated[1:]
        return outline

    def _generate_candidates(
        self,
        project: ProjectRecord,
        extra_brief: str | None,
    ) -> list[StoryDirectionCandidate]:
        messages = [
            {"role": "system", "content": self.prompt_template},
            {
                "role": "user",
                "content": (
                    "阶段一：生成 3 到 5 个不同的长篇故事方向候选。\n"
                    "必须只输出 JSON，对应结构：\n"
                    "{\n"
                    '  "candidates": [\n'
                    "    {\n"
                    '      "label": "方向代号",\n'
                    '      "premise": "一句话 premise",\n'
                    '      "strengths": ["优点1"],\n'
                    '      "risks": ["风险1"]\n'
                    "    }\n"
                    "  ]\n"
                    "}\n\n"
                    f"项目信息：\n{self._project_context(project, extra_brief)}"
                ),
            },
        ]
        response = self.client.chat_model(
            model=self.client.settings.outline_model,
            response_model=StoryDirectionBatch,
            messages=messages,
            temperature=0.9,
            max_tokens=2200,
        )
        candidates = response.candidates
        if len(candidates) < 3:
            raise RuntimeError("OutlineAgent expected at least 3 direction candidates from the model.")
        return candidates

    def _evaluate_candidates(
        self,
        project: ProjectRecord,
        candidates: list[StoryDirectionCandidate],
        extra_brief: str | None,
    ) -> list[StoryDirectionCandidate]:
        candidate_json = json.dumps([candidate.model_dump(mode="json") for candidate in candidates], ensure_ascii=False, indent=2)
        messages = [
            {"role": "system", "content": self.prompt_template},
            {
                "role": "user",
                "content": (
                    "阶段二：请对候选故事方向进行评估与筛选。\n"
                    "评分维度：可持续连载性、冲突强度、人物成长空间、题材贴合度、伏笔回收潜力。\n"
                    "给每个方向一个 0-10 的综合 score，并保留 strengths/risks。\n"
                    "必须只输出 JSON，对应结构：\n"
                    "{\n"
                    '  "candidates": [\n'
                    "    {\n"
                    '      "label": "方向代号",\n'
                    '      "premise": "一句话 premise",\n'
                    '      "strengths": ["优点1"],\n'
                    '      "risks": ["风险1"],\n'
                    '      "score": 8.6\n'
                    "    }\n"
                    "  ],\n"
                    '  "selected_label": "最佳方向代号"\n'
                    "}\n\n"
                    f"项目信息：\n{self._project_context(project, extra_brief)}\n\n"
                    f"候选方向：\n{candidate_json}"
                ),
            },
        ]
        response = self.client.chat_model(
            model=self.client.settings.outline_model,
            response_model=StoryDirectionBatch,
            messages=messages,
            temperature=0.4,
            max_tokens=2200,
        )
        evaluated = response.candidates
        if not evaluated:
            raise RuntimeError("OutlineAgent failed to evaluate story directions.")

        scored = sorted(
            evaluated,
            key=lambda item: item.score if item.score is not None else -1.0,
            reverse=True,
        )
        return scored

    def _finalize_outline(
        self,
        project: ProjectRecord,
        evaluated: list[StoryDirectionCandidate],
        extra_brief: str | None,
    ) -> NovelOutline:
        evaluated_json = json.dumps([item.model_dump(mode="json") for item in evaluated], ensure_ascii=False, indent=2)
        schema_hint = {
            "title": "小说标题",
            "genre": ["题材1", "题材2"],
            "tone": "整体语气",
            "premise": "一句话故事简介",
            "world_setting": {"时代": "设定描述"},
            "characters": [
                {
                    "name": "角色名",
                    "role": "角色定位",
                    "goal": "角色目标",
                    "conflict": "角色冲突",
                    "arc": "角色弧光",
                    "public_traits": ["特征1"],
                    "secrets": ["秘密1"],
                }
            ],
            "acts": [
                {
                    "act_id": 1,
                    "title": "篇章标题",
                    "summary": "篇章摘要",
                    "chapters": [
                        {
                            "chapter_id": 1,
                            "title": "章节标题",
                            "goal": "章节目标",
                            "beats": ["情节节拍1"],
                            "hook": "章末钩子",
                        }
                    ],
                }
            ],
            "foreshadowing": [
                {
                    "setup": "伏笔埋设",
                    "payoff_plan": "回收方案",
                    "reveal_window": "大致回收区间",
                }
            ],
            "constraints": ["硬性写作规则"],
            "discarded_directions": [],
        }
        messages = [
            {"role": "system", "content": self.prompt_template},
            {
                "role": "user",
                "content": (
                    "阶段三：根据评分最高的方向，生成最终全局大纲。\n"
                    "要求：\n"
                    "1. 这是长篇小说总纲，不是单章简介。\n"
                    "2. act 至少 3 个，总章节数至少 12 章，建议 12 到 18 章。\n"
                    "3. chapter_id 必须从 1 开始在全书范围内连续递增，不能在不同 act 内重复。\n"
                    "4. 保持后续 Detail Outline Agent 可继续展开的空间。\n"
                    "5. 必须只输出 JSON，字段必须兼容下面的结构示例。\n\n"
                    f"结构示例：\n{json.dumps(schema_hint, ensure_ascii=False, indent=2)}\n\n"
                    f"项目信息：\n{self._project_context(project, extra_brief)}\n\n"
                    f"已评估候选方向：\n{evaluated_json}"
                ),
            },
        ]
        outline = self.client.chat_model(
            model=self.client.settings.outline_model,
            response_model=NovelOutline,
            messages=messages,
            temperature=0.7,
            max_tokens=5000,
        )
        outline.discarded_directions = []
        return outline

    def _normalize_outline(self, outline: NovelOutline) -> NovelOutline:
        chapter_id = 1
        for act in outline.acts:
            for chapter in act.chapters:
                chapter.chapter_id = chapter_id
                chapter_id += 1
        return outline

    def _load_prompt(self) -> str:
        prompt_path = Path(REPO_ROOT) / "src" / "agents" / "prompts" / "outline.md"
        return prompt_path.read_text(encoding="utf-8")

    @staticmethod
    def _project_context(project: ProjectRecord, extra_brief: str | None) -> str:
        payload: dict[str, Any] = project.model_dump(mode="json")
        if extra_brief:
            payload["extra_brief"] = extra_brief
        return json.dumps(payload, ensure_ascii=False, indent=2)
