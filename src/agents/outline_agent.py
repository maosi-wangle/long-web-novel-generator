from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agents.chapter_blueprint_validator import validate_and_repair_chapter_blueprints
from src.config import REPO_ROOT
from src.llm import CompatibleLLMClient
from src.schemas import ChapterBlueprintBatch, StoryDirectionBatch
from src.schemas.outline import NovelOutline, StoryDirectionCandidate, StoryStructure
from src.schemas.project import ProjectRecord


class OutlineAgent:
    """Generate a closed-loop story structure and chapter blueprints."""

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
        story_structure = self._generate_story_structure(project, evaluated, extra_brief)
        chapter_blueprints = self._generate_chapter_blueprints(project, story_structure, extra_brief)
        chapter_blueprints = validate_and_repair_chapter_blueprints(story_structure, chapter_blueprints)
        return self._assemble_outline(project, story_structure, chapter_blueprints, evaluated[1:])

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
                    "阶段一：生成 3 到 5 个不同的闭环故事方向候选。\n"
                    "要求：\n"
                    "1. 每个方向都必须能压缩成 5-6 章完整闭环故事。\n"
                    "2. 候选必须强调核心冲突、阶段目标和闭合方式。\n"
                    "3. 必须只输出 JSON。\n\n"
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
                    "阶段二：对候选闭环故事方向进行评估。\n"
                    "评分维度：闭环完整性、连续性、冲突升级自然度、人物驱动力、伏笔回收能力。\n"
                    "给每个方向一个 0-10 的 score，并保留 strengths/risks。\n"
                    "必须只输出 JSON。\n\n"
                    "{\n"
                    '  "candidates": [\n'
                    "    {\n"
                    '      "label": "方向代号",\n'
                    '      "premise": "一句话 premise",\n'
                    '      "strengths": ["优点1"],\n'
                    '      "risks": ["风险1"],\n'
                    '      "score": 8.6\n'
                    "    }\n"
                    "  ]\n"
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
            temperature=0.3,
            max_tokens=2200,
        )
        evaluated = response.candidates
        if not evaluated:
            raise RuntimeError("OutlineAgent failed to evaluate story directions.")
        return sorted(
            evaluated,
            key=lambda item: item.score if item.score is not None else -1.0,
            reverse=True,
        )

    def _generate_story_structure(
        self,
        project: ProjectRecord,
        evaluated: list[StoryDirectionCandidate],
        extra_brief: str | None,
    ) -> StoryStructure:
        evaluated_json = json.dumps([item.model_dump(mode="json") for item in evaluated], ensure_ascii=False, indent=2)
        schema_hint = {
            "story_id": "arc_001",
            "title": "故事标题",
            "premise": "一句话故事前提",
            "theme": "主题",
            "core_conflict": "核心矛盾",
            "protagonist_goal": "主角阶段目标",
            "antagonistic_force": "阻力来源",
            "stakes": "失败代价",
            "start_state": ["故事开始时成立的事实"],
            "target_end_state": ["第 6 章结束时必须成立的事实"],
            "must_preserve": ["不能破坏的规则"],
            "world_setting": {"时代": "世界设定"},
            "key_characters": [
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
            "foreshadowing": [{"setup": "伏笔", "payoff_plan": "回收", "reveal_window": "chapter_4_to_6"}],
            "constraints": ["必须遵守的约束"],
            "major_turning_points": [
                {
                    "id": "tp_1",
                    "label": "第一次转折",
                    "function": "把被动躲避推成主动试探",
                    "expected_chapter_window": "chapter_2_to_3",
                }
            ],
            "ending_type": "阶段性闭合但允许留尾钩",
            "chapter_budget": 6,
        }
        messages = [
            {"role": "system", "content": self.prompt_template},
            {
                "role": "user",
                "content": (
                    "阶段三：基于最佳候选方向，生成一个 5-6 章闭环故事的 Story Structure。\n"
                    "要求：\n"
                    "1. 不直接写章节列表。\n"
                    "2. 重点定义开始状态、目标终态、核心冲突、关键转折。\n"
                    "3. chapter_budget 只能是 5 或 6。\n"
                    "4. 故事必须能阶段性闭合，不能把主要问题拖到下一卷才能成立。\n"
                    "5. 必须只输出 JSON。\n\n"
                    f"结构示例：\n{json.dumps(schema_hint, ensure_ascii=False, indent=2)}\n\n"
                    f"项目信息：\n{self._project_context(project, extra_brief)}\n\n"
                    f"已评估候选方向：\n{evaluated_json}"
                ),
            },
        ]
        structure = self.client.chat_model(
            model=self.client.settings.outline_model,
            response_model=StoryStructure,
            messages=messages,
            temperature=0.5,
            max_tokens=3200,
        )
        structure.chapter_budget = 5 if structure.chapter_budget <= 5 else 6
        return structure

    def _generate_chapter_blueprints(
        self,
        project: ProjectRecord,
        story_structure: StoryStructure,
        extra_brief: str | None,
    ) -> list:
        structure_json = json.dumps(story_structure.model_dump(mode="json"), ensure_ascii=False, indent=2)
        schema_hint = {
            "chapters": [
                {
                    "chapter_id": 1,
                    "title": "章节标题",
                    "chapter_role": "铺垫章",
                    "core_function": "这一章完成后剧情产生的具体变化",
                    "entering_state": ["开始时的状态"],
                    "must_resolve": ["必须处理的遗留问题"],
                    "must_advance": ["必须推进的主线/人物线"],
                    "cannot_cross": ["不能提前揭示的内容"],
                    "foreshadow_op": ["埋设/强化/回收 哪条线"],
                    "twist_level": "low",
                    "suspense_density": "medium",
                    "chapter_summary": "这一章发生什么以及留下什么影响",
                    "state_delta": ["章末新增的事实状态"],
                    "exit_obligation": ["下一章必须承接的事项"],
                    "recommended_scene_count": 3,
                    "hook": "这一章留给下一章的直接牵引",
                }
            ]
        }
        template_text = (
            "六章推荐模板：\n"
            "1. 建立问题\n"
            "2. 初次应对\n"
            "3. 结构转折\n"
            "4. 代价升级\n"
            "5. 核心对抗\n"
            "6. 阶段闭合\n\n"
            "五章推荐模板：\n"
            "1. 建立问题\n"
            "2. 初次应对\n"
            "3. 转折升级\n"
            "4. 核心对抗\n"
            "5. 阶段闭合"
        )
        messages = [
            {"role": "system", "content": self.prompt_template},
            {
                "role": "user",
                "content": (
                    "阶段四：把 Story Structure 切成章节蓝图。\n"
                    "要求：\n"
                    "1. 只生成 5 或 6 章。\n"
                    "2. 每章都必须回答：怎么接上前一章、推进什么、不能越过什么、章末把故事推到哪里。\n"
                    "3. exit_obligation 必须能成为下一章 must_resolve 的来源。\n"
                    "4. state_delta 必须能推出下一章 entering_state。\n"
                    "5. 不允许出现无来源的新任务、新地点、新对手。\n"
                    "6. 必须只输出 JSON。\n\n"
                    f"推荐模板：\n{template_text}\n\n"
                    f"结构示例：\n{json.dumps(schema_hint, ensure_ascii=False, indent=2)}\n\n"
                    f"项目信息：\n{self._project_context(project, extra_brief)}\n\n"
                    f"Story Structure：\n{structure_json}"
                ),
            },
        ]
        batch = self.client.chat_model(
            model=self.client.settings.outline_model,
            response_model=ChapterBlueprintBatch,
            messages=messages,
            temperature=0.5,
            max_tokens=4200,
        )
        return batch.chapters

    def _assemble_outline(
        self,
        project: ProjectRecord,
        story_structure: StoryStructure,
        chapter_blueprints: list,
        discarded_directions: list[StoryDirectionCandidate],
    ) -> NovelOutline:
        return NovelOutline(
            title=story_structure.title or project.title,
            genre=project.genre,
            tone=project.tone,
            premise=story_structure.premise or (project.premise or ""),
            world_setting=story_structure.world_setting,
            characters=story_structure.key_characters,
            story_structure=story_structure,
            chapter_blueprints=chapter_blueprints,
            foreshadowing=story_structure.foreshadowing,
            constraints=story_structure.constraints or story_structure.must_preserve,
            discarded_directions=discarded_directions,
        )

    def _load_prompt(self) -> str:
        prompt_path = Path(REPO_ROOT) / "src" / "agents" / "prompts" / "outline.md"
        return prompt_path.read_text(encoding="utf-8")

    @staticmethod
    def _project_context(project: ProjectRecord, extra_brief: str | None) -> str:
        payload: dict[str, Any] = project.model_dump(mode="json")
        if extra_brief:
            payload["extra_brief"] = extra_brief
        return json.dumps(payload, ensure_ascii=False, indent=2)
