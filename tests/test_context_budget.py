from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import src.app as app_module
import src.config as config_module
import src.storage.markdown_store as markdown_store_module
import src.storage.memory_store as memory_store_module
from src.context import ContextAssembler, ContextBudgetManager
from src.orchestrator.state import GenerationStage, ProjectState, WorkflowStatus
from src.schemas import (
    ActOutline,
    ChapterArtifact,
    ChapterPlan,
    CharacterProfile,
    DetailOutline,
    ForeshadowingItem,
    InternalReasoningPackage,
    NovelOutline,
    ProjectRecord,
    RagHit,
    RagSearchResult,
    WriterPacket,
)
from src.schemas.context import DetailOutlineContext
from src.schemas.memory import ChapterMemory, CompactRagHit

MarkdownStore = markdown_store_module.MarkdownStore
MemoryStore = memory_store_module.MemoryStore


def build_project(project_id: str = "demo") -> ProjectRecord:
    return ProjectRecord(
        project_id=project_id,
        title="Context Budget Demo",
        premise="Validate context assembly and token budgeting.",
        genre=["xianxia"],
        tone="tense",
    )


def build_outline(*, chapter_count: int = 3) -> NovelOutline:
    chapters = [
        ChapterPlan(
            chapter_id=index,
            title=f"Chapter {index}",
            goal=f"Push chapter {index} toward the next turning point.",
            beats=[
                f"Beat {index}.1 advances the conflict.",
                f"Beat {index}.2 exposes the cost.",
            ],
            hook=f"Hook for chapter {index}",
        )
        for index in range(1, chapter_count + 1)
    ]
    return NovelOutline(
        title="Budgeted Novel",
        genre=["xianxia"],
        tone="tense",
        premise="A fugitive disciple escapes a collapsing sect and uncovers a buried inheritance.",
        world_setting={
            "realm": "Fallen Cloud Range",
            "power_system": "Spirit roots and forbidden sigils",
        },
        characters=[
            CharacterProfile(
                name="Lin Ye",
                role="protagonist",
                goal="Survive the purge and protect his younger sister.",
                conflict="Hunted by the sect elders.",
                arc="From fleeing survivor to defiant heir.",
            ),
            CharacterProfile(
                name="Su Wan",
                role="ally",
                goal="Repay a debt and expose the traitor.",
                conflict="Bound by a blood oath.",
                arc="From cautious observer to committed partner.",
            ),
        ],
        acts=[ActOutline(act_id=1, title="Escape", summary="The sect purge begins.", chapters=chapters)],
        foreshadowing=[
            ForeshadowingItem(
                setup="A cracked bronze token reacts to Lin Ye's blood.",
                payoff_plan="The token opens the inheritance vault after chapter 6.",
                reveal_window="chapters 6-8",
            )
        ],
        constraints=["Keep power growth costly.", "Do not reveal the mastermind yet."],
    )


def build_detail_outline(chapter_id: int) -> DetailOutline:
    return DetailOutline(
        chapter_id=chapter_id,
        title=f"Chapter {chapter_id}",
        chapter_goal=f"Resolve the immediate danger in chapter {chapter_id}.",
        internal_reasoning_package=InternalReasoningPackage(
            current_progress_assessment="The protagonist is still in the escape phase.",
            outline_alignment=["Move the protagonist from flight to tactical resistance."],
            foreshadowing_targets=["Echo the bronze token and the hidden inheritance."],
            continuity_risks=["Do not forget the blood oath pressure on Su Wan."],
        ),
        writer_packet=WriterPacket(
            chapter_id=chapter_id,
            chapter_title=f"Chapter {chapter_id}",
            chapter_goal=f"Resolve the immediate danger in chapter {chapter_id}.",
            scene_briefs=[],
            style_rules=["Keep scenes grounded and physically costly."],
            continuity_notes=["The protagonist is injured after the last ambush."],
            forbidden_reveals=["Do not expose the true mastermind."],
            retrieved_context=[],
        ),
        ending_hook="A sealed cavern door answers the bronze token.",
        user_constraints=["Keep chapter pacing tight."],
    )


def build_chapter(chapter_id: int) -> ChapterArtifact:
    return ChapterArtifact(
        chapter_id=chapter_id,
        title=f"Chapter {chapter_id}",
        markdown_body=(
            f"Lin Ye endures chapter {chapter_id} with bruised ribs, a hidden token, "
            "and the fear that the elders are one step behind."
        ),
        summary=f"Chapter {chapter_id} forces Lin Ye to retreat while learning one new clue.",
        new_facts=[f"Fact {chapter_id}", f"Consequence {chapter_id}"],
        foreshadow_candidates=[f"Foreshadowing {chapter_id}"],
        referenced_chunks=[f"chunk_{chapter_id:04d}_0001"],
    )


def build_rag_result(*, chapter_to: int, count: int) -> RagSearchResult:
    return RagSearchResult(
        query="history evidence",
        hits=[
            RagHit(
                chunk_id=f"chunk_{index:04d}",
                score=1.0 - (index * 0.01),
                chapter_id=min(index + 1, chapter_to),
                text=f"Historical chunk text {index}",
                summary=f"Historical chunk summary {index}",
            )
            for index in range(count)
        ],
    )


def build_state(*, project_id: str = "demo", last_completed_chapter: int = 0) -> ProjectState:
    return ProjectState(
        project_id=project_id,
        title="Context Budget Demo",
        status=WorkflowStatus.outline_ready,
        current_stage=GenerationStage.detail_outline,
        current_chapter_index=last_completed_chapter + 1,
        last_completed_chapter=last_completed_chapter,
        outline_version=1,
    )


def build_heavy_memory(chapter_id: int, *, item_count: int = 6, item_length: int = 1800) -> ChapterMemory:
    payload = "x" * item_length
    return ChapterMemory(
        chapter_id=chapter_id,
        title=f"Memory {chapter_id}",
        one_line_summary=f"Summary {chapter_id}",
        key_events=[f"event-{chapter_id}-{index}-{payload}" for index in range(item_count)],
        new_facts=[f"fact-{chapter_id}-{index}-{payload}" for index in range(item_count)],
        world_state_updates=[f"world-{chapter_id}-{index}-{payload}" for index in range(item_count)],
        timeline_markers=[f"time-{chapter_id}-{index}-{payload}" for index in range(item_count)],
        unresolved_conflicts=[f"conflict-{chapter_id}-{index}-{payload}" for index in range(item_count)],
    )


class ContextBudgetTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tempdir.name) / "projects"
        self.config_patcher = patch.object(config_module, "DATA_ROOT", self.data_root)
        self.markdown_root_patcher = patch.object(markdown_store_module, "DATA_ROOT", self.data_root)
        self.config_patcher.start()
        self.markdown_root_patcher.start()
        self.markdown_store = MarkdownStore()
        self.memory_store = MemoryStore(self.markdown_store)
        self.context_assembler = ContextAssembler(memory_store=self.memory_store)

    def tearDown(self) -> None:
        self.markdown_root_patcher.stop()
        self.config_patcher.stop()
        self.tempdir.cleanup()

    def test_memory_store_falls_back_to_chapter_markdown(self) -> None:
        self.markdown_store.save_chapter("demo", build_chapter(1), outline_version=1, detail_outline_version=1)

        memories = self.memory_store.load_recent_chapter_memories("demo", chapter_to=1, limit=3)

        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].chapter_id, 1)
        self.assertIn("Chapter 1 forces Lin Ye to retreat", memories[0].one_line_summary)
        self.assertEqual(memories[0].new_facts, ["Fact 1", "Consequence 1"])
        self.assertEqual(memories[0].foreshadowing_opened[0].summary, "Foreshadowing 1")

    def test_context_assembler_builds_detail_context_with_budget_report(self) -> None:
        for chapter_id in (1, 2):
            self.markdown_store.save_chapter("demo", build_chapter(chapter_id), outline_version=1, detail_outline_version=1)

        outline = build_outline(chapter_count=3)
        context = self.context_assembler.build_detail_context(
            project=build_project(),
            state=build_state(last_completed_chapter=2),
            outline=outline,
            current_chapter=outline.acts[0].chapters[2].model_dump(mode="json"),
            current_act={"act_id": 1, "act_index": 0, "title": "Escape"},
            previous_chapter=outline.acts[0].chapters[1].model_dump(mode="json"),
            next_chapter=None,
            rag_result=build_rag_result(chapter_to=2, count=5),
            extra_brief="Protect the inheritance reveal.",
        )

        self.assertEqual(context.current_chapter["chapter_id"], 3)
        self.assertEqual(len(context.recent_memories), 2)
        self.assertEqual(len(context.rag_hits), 4)
        self.assertEqual(context.world_setting["realm"], "Fallen Cloud Range")
        self.assertEqual(context.project_meta["extra_brief"], "Protect the inheritance reveal.")
        self.assertIsNotNone(context.budget_report)

    def test_context_assembler_builds_writer_context_and_rewrites_retrieved_context(self) -> None:
        for chapter_id in (1, 2):
            self.markdown_store.save_chapter("demo", build_chapter(chapter_id), outline_version=1, detail_outline_version=1)

        context = self.context_assembler.build_writer_context(
            project=build_project(),
            detail_outline=build_detail_outline(3),
            rag_result=build_rag_result(chapter_to=2, count=5),
            extra_brief="Keep the pursuit pressure high.",
        )

        self.assertEqual(context.chapter_id, 3)
        self.assertEqual(len(context.recent_memories), 2)
        self.assertEqual(len(context.rag_hits), 3)
        self.assertEqual(len(context.writer_packet["retrieved_context"]), 3)
        self.assertTrue(context.writer_packet["retrieved_context"][0].startswith("chunk_0000"))
        self.assertEqual(context.project_meta["extra_brief"], "Keep the pursuit pressure high.")
        self.assertIsNotNone(context.budget_report)

    def test_budget_drops_rag_before_compacting_memories(self) -> None:
        manager = ContextBudgetManager()
        context = DetailOutlineContext(
            project_meta={"title": "demo"},
            current_chapter={"chapter_id": 5, "title": "Chapter 5"},
            current_progress={"last_completed_chapter": 4},
            recent_memories=[build_heavy_memory(4, item_count=1, item_length=200)],
            rag_hits=[
                CompactRagHit(
                    chunk_id=f"chunk_{index:04d}",
                    chapter_id=4,
                    why_relevant="retrieval",
                    compressed_quote="r" * 10000,
                    score=1.0 - (index * 0.01),
                )
                for index in range(8)
            ],
        )

        fitted = manager.fit_detail_context(context)

        self.assertTrue(
            any(action.startswith("drop_") for action in fitted.budget_report.applied_actions),
            fitted.budget_report.applied_actions,
        )
        self.assertNotIn("compact_recent_memories_level_1", fitted.budget_report.applied_actions)
        self.assertLess(len(fitted.rag_hits), len(context.rag_hits))
        self.assertEqual(len(fitted.recent_memories[0].key_events), 1)

    def test_budget_compacts_recent_memories_when_structured_memory_overflows(self) -> None:
        manager = ContextBudgetManager()
        context = DetailOutlineContext(
            project_meta={"title": "demo"},
            current_chapter={"chapter_id": 6, "title": "Chapter 6"},
            current_progress={"last_completed_chapter": 5},
            recent_memories=[
                build_heavy_memory(3),
                build_heavy_memory(4),
                build_heavy_memory(5),
            ],
        )

        fitted = manager.fit_detail_context(context)

        self.assertIn("compact_recent_memories_level_1", fitted.budget_report.applied_actions)
        self.assertLessEqual(len(fitted.recent_memories[0].key_events), 3)
        self.assertLessEqual(len(fitted.recent_memories[0].new_facts), 3)

    def test_budget_trims_world_setting_with_outline_side_context(self) -> None:
        manager = ContextBudgetManager()
        context = DetailOutlineContext(
            project_meta={"title": "demo"},
            current_chapter={"chapter_id": 7, "title": "Chapter 7"},
            current_progress={"last_completed_chapter": 6},
            world_setting={f"setting_{index}": "w" * 2500 for index in range(12)},
            foreshadowing=[{"setup": "f" * 1800, "payoff_plan": "p" * 1800} for _ in range(10)],
            global_constraints=["c" * 1200 for _ in range(10)],
            core_characters=[{"name": f"char_{index}", "arc": "a" * 1800} for index in range(10)],
        )

        fitted = manager.fit_detail_context(context)

        self.assertIn("trim_outline_side_context", fitted.budget_report.applied_actions)
        self.assertLessEqual(len(fitted.world_setting), 8)


if __name__ == "__main__":
    unittest.main()
