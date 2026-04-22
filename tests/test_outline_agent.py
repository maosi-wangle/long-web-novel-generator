from __future__ import annotations

import unittest

from src.agents.outline_agent import OutlineAgent
from src.agents.outline_continuity import apply_outline_scene_continuity
from src.schemas import (
    ActOutline,
    ChapterPlan,
    NovelOutline,
    ProjectRecord,
    ScenePlan,
    StoryDirectionBatch,
    StoryDirectionCandidate,
)


def build_project() -> ProjectRecord:
    return ProjectRecord(
        project_id="outline-demo",
        title="Outline Demo",
        premise="A hunted disciple escapes a ruined sect and slowly finds a larger conspiracy.",
        genre=["xianxia"],
        tone="tense",
    )


class FakeOutlineClient:
    def __init__(self) -> None:
        self.settings = type("Settings", (), {"outline_model": "fake-outline"})()
        self.calls: list[str] = []

    def chat_model(self, **kwargs):
        response_model = kwargs["response_model"]
        self.calls.append(response_model.__name__)
        if response_model is StoryDirectionBatch and len(self.calls) == 1:
            return StoryDirectionBatch(
                candidates=[
                    StoryDirectionCandidate(label="A", premise="方向 A", strengths=["强冲突"], risks=["节奏风险"]),
                    StoryDirectionCandidate(label="B", premise="方向 B", strengths=["人物成长"], risks=["设定复杂"]),
                    StoryDirectionCandidate(label="C", premise="方向 C", strengths=["悬念"], risks=["世界观偏散"]),
                ]
            )
        if response_model is StoryDirectionBatch and len(self.calls) == 2:
            return StoryDirectionBatch(
                candidates=[
                    StoryDirectionCandidate(label="B", premise="方向 B", strengths=["人物成长"], risks=["设定复杂"], score=9.1),
                    StoryDirectionCandidate(label="A", premise="方向 A", strengths=["强冲突"], risks=["节奏风险"], score=8.4),
                    StoryDirectionCandidate(label="C", premise="方向 C", strengths=["悬念"], risks=["世界观偏散"], score=7.8),
                ]
            )
        if response_model is NovelOutline:
            return NovelOutline(
                title="断桥修补测试",
                genre=["xianxia"],
                tone="tense",
                premise="主角逃亡途中发现更大的阴谋。",
                acts=[
                    ActOutline(
                        act_id=1,
                        title="逃离宗门",
                        summary="从内乱中逃离并意识到敌人不止眼前。",
                        chapters=[
                            ChapterPlan(
                                chapter_id=99,
                                title="人心难测",
                                goal="处理团队内部矛盾",
                                beats=[
                                    "新加入的弟子中混入奸细",
                                    "主角识破但未立即揭穿，选择监控",
                                ],
                                hook="奸细深夜潜入试图窃取阵法图纸",
                            ),
                            ChapterPlan(
                                chapter_id=100,
                                title="血色试炼",
                                goal="通过外部考验巩固地位",
                                beats=[
                                    "反派设下擂台邀请主角赴约",
                                    "战斗中意外触发体内碎片共鸣",
                                ],
                                hook="战斗结束后，对手眼中闪过一丝恐惧而非仇恨",
                            ),
                        ],
                    )
                ],
            )
        raise AssertionError(f"Unexpected response_model: {response_model}")


class OutlineAgentTestCase(unittest.TestCase):
    def test_outline_agent_backfills_scene_chain_from_chapter_only_outline(self) -> None:
        agent = OutlineAgent(client=FakeOutlineClient())

        outline = agent.generate_outline(project=build_project())

        chapters = outline.acts[0].chapters
        self.assertEqual([chapter.chapter_id for chapter in chapters], [1, 2])
        self.assertEqual(chapters[0].scenes[0].scene_id, 1)
        self.assertEqual(chapters[1].scenes[0].scene_id, 2)
        self.assertIn("奸细深夜潜入试图窃取阵法图纸", chapters[1].scenes[0].carry_in)
        self.assertIn("奸细深夜潜入试图窃取阵法图纸", chapters[0].scenes[0].next_scene_must_address)
        self.assertIsNotNone(chapters[1].scenes[0].transition_bridge)

    def test_scene_continuity_pass_preserves_explicit_scenes_and_reassigns_global_ids(self) -> None:
        outline = NovelOutline(
            title="场景链测试",
            genre=["xianxia"],
            premise="主角从逃亡转向反击。",
            acts=[
                ActOutline(
                    act_id=1,
                    title="第一幕",
                    summary="从追杀转为设局。",
                    chapters=[
                        ChapterPlan(
                            chapter_id=1,
                            title="风雪夜",
                            goal="躲开追兵",
                            scenes=[
                                ScenePlan(
                                    scene_id=9,
                                    title="雪林潜行",
                                    objective="带伤穿过雪林并确认是否有人尾随。",
                                    hook="主角发现有人在暗中留下错误路标。",
                                ),
                                ScenePlan(
                                    scene_id=12,
                                    title="破庙试探",
                                    objective="借破庙试探跟踪者身份。",
                                ),
                            ],
                        ),
                        ChapterPlan(
                            chapter_id=2,
                            title="山道转折",
                            goal="把被动逃亡转成主动设局",
                            scenes=[
                                ScenePlan(
                                    scene_id=20,
                                    title="借势设局",
                                    objective="利用错误路标反向布置陷阱。",
                                )
                            ],
                        ),
                    ],
                )
            ],
        )

        normalized = apply_outline_scene_continuity(outline)
        scenes = [scene for act in normalized.acts for chapter in act.chapters for scene in chapter.scenes]

        self.assertEqual([scene.scene_id for scene in scenes], [1, 2, 3])
        self.assertIn("主角发现有人在暗中留下错误路标。", scenes[1].carry_in)
        self.assertIn("主角发现有人在暗中留下错误路标。", scenes[0].next_scene_must_address)
        self.assertEqual(normalized.acts[0].chapters[0].hook, "主角发现有人在暗中留下错误路标。")


if __name__ == "__main__":
    unittest.main()
