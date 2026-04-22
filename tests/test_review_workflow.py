from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

import src.app as app_module
import src.config as config_module
import src.storage.markdown_store as markdown_store_module
from src.orchestrator.state import GenerationStage, WorkflowStatus
from src.orchestrator.workflow import NovelWorkflow
from src.schemas import (
    ActOutline,
    ChapterArtifact,
    ChapterPlan,
    DetailOutline,
    InternalReasoningPackage,
    NovelOutline,
    ProjectBootstrapRequest,
    ReviewDecision,
    WriterPacket,
)
from src.schemas.memory import RagIngestResult
from src.tools.human_tool import HumanTool


def build_outline(*, chapter_count: int = 4) -> NovelOutline:
    chapters = [
        ChapterPlan(
            chapter_id=index,
            title=f"第{index}章",
            goal=f"推进第{index}章剧情",
            beats=[f"情节点 {index}.1", f"情节点 {index}.2"],
            hook=f"第{index}章钩子",
        )
        for index in range(1, chapter_count + 1)
    ]
    return NovelOutline(
        title="测试小说",
        genre=["悬疑"],
        tone="冷峻",
        premise="用于验证 review 工作流的最小项目。",
        world_setting={"时代": "近未来"},
        acts=[ActOutline(act_id=1, title="第一幕", summary="开局", chapters=chapters)],
        constraints=["章节需要首尾呼应"],
    )


def build_detail_outline(chapter_id: int) -> DetailOutline:
    return DetailOutline(
        chapter_id=chapter_id,
        title=f"第{chapter_id}章细纲",
        chapter_goal=f"完成第{chapter_id}章任务",
        internal_reasoning_package=InternalReasoningPackage(
            current_progress_assessment=f"当前推进到第{chapter_id}章",
            outline_alignment=[f"对齐总纲第{chapter_id}章"],
            foreshadowing_targets=[f"伏笔 {chapter_id}"],
            continuity_risks=[f"连续性风险 {chapter_id}"],
        ),
        writer_packet=WriterPacket(
            chapter_id=chapter_id,
            chapter_title=f"第{chapter_id}章细纲",
            chapter_goal=f"完成第{chapter_id}章任务",
            scene_briefs=[],
            style_rules=["第三人称有限视角"],
            continuity_notes=[f"连续性提示 {chapter_id}"],
            forbidden_reveals=[f"禁揭示 {chapter_id}"],
            retrieved_context=[f"历史上下文 {chapter_id}"],
        ),
        ending_hook=f"第{chapter_id}章结尾钩子",
        user_constraints=[f"约束 {chapter_id}"],
    )


def build_chapter(chapter_id: int, *, body_suffix: str = "原始正文") -> ChapterArtifact:
    return ChapterArtifact(
        chapter_id=chapter_id,
        title=f"第{chapter_id}章标题",
        markdown_body=f"这是第{chapter_id}章的{body_suffix}。",
        summary=f"第{chapter_id}章摘要",
        new_facts=[f"事实 {chapter_id}"],
        foreshadow_candidates=[f"伏笔 {chapter_id}"],
        referenced_chunks=[f"chunk_{chapter_id:04d}_0001"],
    )


class DummyRagTool:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id

    def ingest_archived_chapter(self, chapter_id: int) -> RagIngestResult:
        return RagIngestResult(
            project_id=self.project_id,
            chapter_id=chapter_id,
            chunk_count=1,
            total_indexed_chunks=1,
            embedding_model="dummy",
        )


class ReviewWorkflowTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tempdir.name) / "projects"
        self.config_patcher = patch.object(config_module, "DATA_ROOT", self.data_root)
        self.markdown_root_patcher = patch.object(markdown_store_module, "DATA_ROOT", self.data_root)
        self.config_patcher.start()
        self.markdown_root_patcher.start()
        self.runner = CliRunner()
        self.workflow = NovelWorkflow()

    def tearDown(self) -> None:
        self.markdown_root_patcher.stop()
        self.config_patcher.stop()
        self.tempdir.cleanup()

    def init_project(self, project_id: str = "demo") -> None:
        request = ProjectBootstrapRequest(
            project_id=project_id,
            title="测试项目",
            premise="用于 review 流程测试",
        )
        self.workflow.create_project(request)

    def load_state(self, project_id: str = "demo"):
        return self.workflow.state_store.load_state(project_id)

    def test_generate_outline_require_review_keeps_draft_out_of_official_outline(self) -> None:
        self.init_project()
        outline = build_outline()

        with patch.object(app_module.OutlineAgent, "generate_outline", return_value=outline):
            result = self.runner.invoke(app_module.app, ["generate-outline", "demo", "--require-review"])

        self.assertEqual(result.exit_code, 0, result.stdout)
        paths = config_module.get_project_paths("demo")
        self.assertFalse(paths.outline_file.exists(), "outline.json should not be written before approval")

        state = self.load_state()
        self.assertTrue(state.pending_human_review)
        self.assertEqual(state.status, WorkflowStatus.waiting_human_review)
        self.assertEqual(state.current_stage, GenerationStage.outline)

        blocked_generate = self.runner.invoke(app_module.app, ["generate-outline", "demo"])
        self.assertNotEqual(blocked_generate.exit_code, 0)

        blocked_request = self.runner.invoke(
            app_module.app,
            ["request-review", "demo", "--stage", "outline_review", "--reason", "重复提审"],
        )
        self.assertNotEqual(blocked_request.exit_code, 0)
        state = self.load_state()
        self.assertTrue(state.pending_human_review)
        self.assertEqual(state.pending_review_id, "review_0001")

        HumanTool("demo", self.workflow).resolve_review(
            review_id=state.pending_review_id or "",
            decision=ReviewDecision.reject,
            instruction="驳回大纲草稿",
        )

        self.assertFalse(paths.outline_file.exists(), "Rejected outline draft must not remain in official outline.json")
        state = self.load_state()
        self.assertFalse(state.pending_human_review)
        self.assertEqual(state.status, WorkflowStatus.initialized)
        self.assertEqual(state.current_stage, GenerationStage.outline)

    def test_generate_detail_outline_require_review_keeps_draft_out_of_official_detail_file(self) -> None:
        self.init_project()
        self.workflow.save_outline("demo", build_outline())
        detail_outline = build_detail_outline(1)

        with patch.object(app_module.DetailOutlineAgent, "generate_detail_outline", return_value=detail_outline):
            result = self.runner.invoke(
                app_module.app,
                ["generate-detail-outline", "demo", "--chapter-id", "1", "--require-review"],
            )

        self.assertEqual(result.exit_code, 0, result.stdout)
        detail_file = config_module.get_project_paths("demo").detail_outlines_dir / "0001.json"
        self.assertFalse(detail_file.exists(), "detail outline draft should not be saved before approval")

        state = self.load_state()
        self.assertTrue(state.pending_human_review)
        self.assertEqual(state.status, WorkflowStatus.waiting_human_review)

        HumanTool("demo", self.workflow).resolve_review(
            review_id=state.pending_review_id or "",
            decision=ReviewDecision.reject,
            instruction="驳回细纲草稿",
        )

        self.assertFalse(detail_file.exists(), "Rejected detail outline draft must not remain in detail_outlines/")
        state = self.load_state()
        self.assertFalse(state.pending_human_review)
        self.assertEqual(state.status, WorkflowStatus.outline_ready)
        self.assertEqual(state.current_stage, GenerationStage.detail_outline)

    def test_resolved_or_non_current_blocking_review_cannot_be_replayed(self) -> None:
        self.init_project()
        outline = build_outline()
        tool = HumanTool("demo", self.workflow)

        review = tool.request_review(
            stage="outline_review",
            reason="阻塞提审",
            payload=outline.model_dump(mode="json"),
            source_status=WorkflowStatus.initialized.value,
            source_stage=GenerationStage.outline.value,
            blocking=True,
        )
        tool.resolve_review(review_id=review.review_id, decision=ReviewDecision.approve, instruction="首次通过")

        with self.assertRaisesRegex(RuntimeError, "already resolved"):
            tool.resolve_review(review_id=review.review_id, decision=ReviewDecision.approve)

        review = tool.request_review(
            stage="outline_review",
            reason="新的阻塞提审",
            payload=outline.model_dump(mode="json"),
            source_status=WorkflowStatus.outline_ready.value,
            source_stage=GenerationStage.detail_outline.value,
            blocking=True,
        )
        state = self.load_state()
        state.pending_review_id = "review_fake"
        self.workflow.state_store.save_state("demo", state)

        with self.assertRaisesRegex(RuntimeError, "not the current pending review"):
            tool.resolve_review(review_id=review.review_id, decision=ReviewDecision.reject)

    def test_historical_chapter_review_stays_standalone_and_does_not_rewind_progress(self) -> None:
        self.init_project()
        self.workflow.save_outline("demo", build_outline(chapter_count=4))

        for chapter_id in (1, 2, 3):
            self.workflow.save_detail_outline("demo", build_detail_outline(chapter_id))
            self.workflow.archive_chapter("demo", build_chapter(chapter_id))

        state_before = self.load_state()
        self.assertEqual(state_before.last_completed_chapter, 3)
        self.assertEqual(state_before.status, WorkflowStatus.outline_ready)
        self.assertEqual(state_before.current_stage, GenerationStage.detail_outline)

        request_result = self.runner.invoke(
            app_module.app,
            [
                "request-review",
                "demo",
                "--stage",
                "chapter_review",
                "--chapter-id",
                "1",
                "--reason",
                "回看历史章节",
            ],
        )
        self.assertEqual(request_result.exit_code, 0, request_result.stdout)

        review = HumanTool("demo", self.workflow).list_reviews()[-1]
        self.assertFalse(review.blocking, "manual request-review should remain standalone")

        edited_markdown = self.workflow.markdown_store.render_chapter_markdown(
            build_chapter(1, body_suffix="修订正文"),
            outline_version=1,
            detail_outline_version=1,
        )
        edited_file = Path(self.tempdir.name) / "edited_0001.md"
        edited_file.write_text(edited_markdown, encoding="utf-8")

        with patch("src.tools.human_tool.RagTool", DummyRagTool):
            HumanTool("demo", self.workflow).resolve_review(
                review_id=review.review_id,
                decision=ReviewDecision.approve,
                edited_file=str(edited_file),
                instruction="只修历史章节，不推进流程",
            )

        state_after = self.load_state()
        self.assertEqual(state_after.last_completed_chapter, 3)
        self.assertEqual(state_after.current_chapter_index, state_before.current_chapter_index)
        self.assertEqual(state_after.status, state_before.status)
        self.assertEqual(state_after.current_stage, state_before.current_stage)
        self.assertFalse(state_after.pending_human_review)

        chapter = self.workflow.markdown_store.load_chapter_artifact("demo", 1)
        self.assertIn("修订正文", chapter.markdown_body)
        self.assertIn("review_0001 approved", state_after.notes[-1])


if __name__ == "__main__":
    unittest.main()
