from __future__ import annotations

import unittest

from src.agents.chapter_blueprint_validator import validate_and_repair_chapter_blueprints
from src.agents.outline_agent import OutlineAgent
from src.schemas import (
    ChapterBlueprint,
    ChapterBlueprintBatch,
    NovelOutline,
    ProjectRecord,
    StoryDirectionBatch,
    StoryDirectionCandidate,
    StoryStructure,
    TurningPoint,
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
                    StoryDirectionCandidate(label="B", premise="方向 B", strengths=["闭环清晰"], risks=["人物少"]),
                    StoryDirectionCandidate(label="C", premise="方向 C", strengths=["悬念强"], risks=["后劲不足"]),
                ]
            )
        if response_model is StoryDirectionBatch and len(self.calls) == 2:
            return StoryDirectionBatch(
                candidates=[
                    StoryDirectionCandidate(label="B", premise="方向 B", strengths=["闭环清晰"], risks=["人物少"], score=9.2),
                    StoryDirectionCandidate(label="A", premise="方向 A", strengths=["强冲突"], risks=["节奏风险"], score=8.5),
                    StoryDirectionCandidate(label="C", premise="方向 C", strengths=["悬念强"], risks=["后劲不足"], score=7.4),
                ]
            )
        if response_model is StoryStructure:
            return StoryStructure(
                story_id="arc_001",
                title="残碑夜渡",
                premise="少年带着宗门残碑逃亡，并在追杀中查清灭门真相。",
                theme="在失去中夺回主动",
                core_conflict="主角必须在被追杀前破解残碑线索，否则会被敌人夺走唯一证据。",
                protagonist_goal="在六章内保住残碑、确认内奸、反制追杀者。",
                antagonistic_force="追杀主角的执法队与隐藏在宗门内部的内奸。",
                stakes="若失败，残碑会落入敌手，主角也会被扣成灭门罪人。",
                start_state=["主角重伤逃离宗门", "残碑在主角手中", "敌人正在搜捕"],
                target_end_state=["主角确认内奸身份", "追杀危机阶段性解除", "残碑秘密被保住"],
                must_preserve=["残碑不能被夺走", "内奸身份不能在前三章直接揭露"],
                constraints=["这是一个 6 章闭环故事"],
                major_turning_points=[
                    TurningPoint(
                        id="tp_1",
                        label="第一次转折",
                        function="主角从被动逃亡转为主动设局试探内奸。",
                        expected_chapter_window="chapter_3",
                    )
                ],
                chapter_budget=6,
            )
        if response_model is ChapterBlueprintBatch:
            return ChapterBlueprintBatch(
                chapters=[
                    ChapterBlueprint(
                        chapter_id=7,
                        title="火夜奔逃",
                        chapter_role="铺垫章",
                        core_function="建立逃亡困境并确认残碑的重要性。",
                        entering_state=["宗门覆灭", "主角重伤"],
                        must_advance=["建立残碑价值", "建立追杀压力"],
                        chapter_summary="主角带着残碑逃离火海，发现敌人追索的不只是自己。",
                        state_delta=["主角暂时脱身", "确认残碑会引来持续追杀"],
                        exit_obligation=["找到能解读残碑的人"],
                    ),
                    ChapterBlueprint(
                        chapter_id=9,
                        title="荒镇藏锋",
                        chapter_role="推进章",
                        core_function="主角尝试求助并第一次意识到内奸可能就在幸存者之中。",
                        entering_state=["主角藏身荒镇"],
                        must_advance=["引入幸存同门", "增加怀疑"],
                        chapter_summary="主角在荒镇接触幸存同门，发现有人故意误导线索。",
                        state_delta=["出现伪线索", "主角开始怀疑内部泄密"],
                        exit_obligation=["验证伪线索来源"],
                    ),
                    ChapterBlueprint(
                        chapter_id=12,
                        title="反钩试探",
                        chapter_role="转折章",
                        core_function="主角借假线索反钓追兵，确认内奸就在身边。",
                        entering_state=["主角决定设局"],
                        must_advance=["把故事从逃跑转为试探"],
                        chapter_summary="主角放出假消息，借追兵反应锁定内奸范围。",
                        state_delta=["内奸范围缩小", "主角夺回部分主动权"],
                        exit_obligation=["逼内奸暴露真实目的"],
                    ),
                    ChapterBlueprint(
                        chapter_id=15,
                        title="碑文开口",
                        chapter_role="代价升级章",
                        core_function="主角解读部分碑文，但因此暴露位置并付出代价。",
                        entering_state=["主角掌握试探结果"],
                        must_advance=["解读残碑", "升级敌人压力"],
                        chapter_summary="主角短暂解开碑文秘密，却因此触发更猛烈追杀。",
                        state_delta=["残碑秘密露出一角", "敌人完成包围"],
                        exit_obligation=["突破包围并保住残碑"],
                    ),
                    ChapterBlueprint(
                        chapter_id=16,
                        title="雪岭对撞",
                        chapter_role="核心对抗章",
                        core_function="主角正面对上内奸与追兵，回收前文试探线。",
                        entering_state=["主角被逼入雪岭"],
                        must_advance=["正面对抗", "回收伪线索"],
                        chapter_summary="主角在雪岭设伏逼内奸现形，双方撕破伪装。",
                        state_delta=["内奸身份坐实", "主角保住残碑"],
                        exit_obligation=["切断追杀链条"],
                    ),
                    ChapterBlueprint(
                        chapter_id=18,
                        title="残灯未灭",
                        chapter_role="收束章",
                        core_function="阶段性解除追杀危机并完成闭环收束。",
                        entering_state=["内奸身份已坐实"],
                        must_advance=["解除追杀危机", "完成阶段闭环"],
                        chapter_summary="主角借内奸暴露的证据反制执法队，暂时洗清罪名。",
                        state_delta=["追杀危机阶段性解除"],
                        exit_obligation=[],
                    ),
                ]
            )
        raise AssertionError(f"Unexpected response_model: {response_model}")


class OutlineAgentTestCase(unittest.TestCase):
    def test_outline_agent_generates_story_structure_and_blueprints(self) -> None:
        agent = OutlineAgent(client=FakeOutlineClient())

        outline = agent.generate_outline(project=build_project())

        self.assertEqual(outline.story_structure.chapter_budget, 6)
        self.assertEqual(len(outline.chapter_blueprints), 6)
        self.assertEqual([chapter.chapter_id for chapter in outline.chapter_blueprints], [1, 2, 3, 4, 5, 6])
        self.assertEqual(outline.chapter_blueprints[0].must_resolve, [])
        self.assertIn("找到能解读残碑的人", outline.chapter_blueprints[1].must_resolve)
        self.assertIn("主角暂时脱身", outline.chapter_blueprints[1].entering_state)
        self.assertIn("主角确认内奸身份", outline.chapter_blueprints[-1].state_delta)
        self.assertEqual(len(outline.acts), 1)
        self.assertEqual(len(outline.acts[0].chapters), 6)
        self.assertEqual(outline.acts[0].chapters[0].goal, "建立逃亡困境并确认残碑的重要性。")
        self.assertEqual(agent.client.calls, ["StoryDirectionBatch", "StoryDirectionBatch", "StoryStructure", "ChapterBlueprintBatch"])

    def test_validator_repairs_missing_state_links(self) -> None:
        structure = StoryStructure(
            story_id="arc_002",
            title="测试",
            premise="测试",
            core_conflict="核心冲突",
            protagonist_goal="完成目标",
            antagonistic_force="敌人",
            stakes="失败会出事",
            start_state=["开局重伤"],
            target_end_state=["危机解除"],
            chapter_budget=5,
        )
        chapters = [
            ChapterBlueprint(
                chapter_id=3,
                title="第一章",
                core_function="建立问题",
                chapter_summary="建立问题",
                state_delta=["发现线索"],
                exit_obligation=["追查线索来源"],
            ),
            ChapterBlueprint(
                chapter_id=9,
                title="第二章",
                core_function="推进问题",
                chapter_summary="推进问题",
                state_delta=["遭到反扑"],
                exit_obligation=["解决反扑后果"],
            ),
        ]

        repaired = validate_and_repair_chapter_blueprints(structure, chapters)

        self.assertEqual([chapter.chapter_id for chapter in repaired], [1, 2])
        self.assertEqual(repaired[0].entering_state, ["开局重伤"])
        self.assertIn("追查线索来源", repaired[1].must_resolve)
        self.assertIn("发现线索", repaired[1].entering_state)
        self.assertIn("危机解除", repaired[-1].state_delta)

    def test_novel_outline_syncs_blueprints_into_acts_view(self) -> None:
        outline = NovelOutline(
            title="闭环测试",
            premise="用于验证兼容视图。",
            chapter_blueprints=[
                ChapterBlueprint(
                    chapter_id=1,
                    title="建立问题",
                    core_function="建立问题",
                    chapter_summary="建立问题",
                    state_delta=["问题出现"],
                    exit_obligation=["处理问题"],
                ),
                ChapterBlueprint(
                    chapter_id=2,
                    title="解决问题",
                    core_function="解决问题",
                    chapter_summary="解决问题",
                    state_delta=["问题解决"],
                    exit_obligation=[],
                ),
            ],
        )

        self.assertEqual(len(outline.acts), 1)
        self.assertEqual([chapter.chapter_id for chapter in outline.acts[0].chapters], [1, 2])
        self.assertEqual(outline.acts[0].chapters[0].hook, "处理问题")


if __name__ == "__main__":
    unittest.main()
