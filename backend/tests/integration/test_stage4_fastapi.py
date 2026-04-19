import os
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from novel_assist.api.app import app  # noqa: E402


class Stage4FastApiIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = dict(os.environ)
        self._tmp_dir = tempfile.TemporaryDirectory()
        os.environ["USE_MOCK_LLM"] = "1"
        os.environ["GRAPH_STORE_BACKEND"] = "jsonl"
        os.environ["CHAPTER_STATE_PATH"] = str(Path(self._tmp_dir.name) / "chapter_state.json")
        os.environ["REVIEW_AUDIT_PATH"] = str(Path(self._tmp_dir.name) / "review_audit.jsonl")
        os.environ["NOVEL_STATE_PATH"] = str(Path(self._tmp_dir.name) / "novel_state.json")
        os.environ["MEMORY_STATE_PATH"] = str(Path(self._tmp_dir.name) / "memory_state.json")
        os.environ.pop("HUMAN_REVIEW_STATUS", None)
        os.environ.pop("AUTO_APPROVE_REVIEW", None)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._old_env)
        self._tmp_dir.cleanup()

    def test_hitl_end_to_end(self) -> None:
        chapter_id = "chapter-api-0001"

        plan_resp = self.client.post(
            f"/chapters/{chapter_id}/plan",
            json={
                "novel_id": "novel-api-001",
                "novel_title": "测试小说",
                "chapter_number": 1,
                "chapter_title": "第一章",
            },
        )
        self.assertEqual(plan_resp.status_code, 200)
        plan_data = plan_resp.json()
        self.assertEqual(plan_data["agenda_review_status"], "pending")
        self.assertEqual(plan_data["novel_id"], "novel-api-001")
        self.assertEqual(plan_data["chapter_title"], "第一章")
        self.assertEqual(
            plan_data["error"],
            "HumanReviewRequired: chapter agenda and recall evidence must be approved before drafting.",
        )
        self.assertGreater(len(plan_data.get("rag_evidence", [])), 0)
        self.assertIn("chapter_agenda_draft", plan_data)

        review_task_resp = self.client.get(f"/chapters/{chapter_id}/review-task")
        self.assertEqual(review_task_resp.status_code, 200)
        task_data = review_task_resp.json()
        self.assertEqual(task_data["chapter_id"], chapter_id)
        self.assertIn("chapter_agenda_draft", task_data)
        self.assertEqual(task_data["novel_title"], "测试小说")
        self.assertTrue(task_data["recall_trace_id"].startswith("recall-"))

        blocked_draft_resp = self.client.post(f"/chapters/{chapter_id}/draft")
        self.assertEqual(blocked_draft_resp.status_code, 409)
        blocked_payload = blocked_draft_resp.json()
        self.assertEqual(blocked_payload["error_code"], "HUMAN_REVIEW_REQUIRED")
        self.assertIn("Draft generation is blocked", blocked_payload["message"])

        review_resp = self.client.post(
            f"/chapters/{chapter_id}/review",
            json={
                "agenda_review_status": "approved",
                "agenda_review_notes": "通过，进入初稿生成",
                "approved_chapter_agenda": "",
                "approved_rag_recall_summary": "",
            },
        )
        self.assertEqual(review_resp.status_code, 200)
        review_data = review_resp.json()
        self.assertEqual(review_data["agenda_review_status"], "approved")
        self.assertEqual(review_data["chapter_status"], "approved")
        self.assertTrue(review_data["review_trace_id"].startswith("review-"))

        draft_resp = self.client.post(f"/chapters/{chapter_id}/draft")
        self.assertEqual(draft_resp.status_code, 200)
        draft_data = draft_resp.json()
        self.assertGreater(int(draft_data.get("draft_word_count", 0)), 0)
        self.assertEqual(draft_data.get("error", ""), "")
        self.assertEqual(draft_data["chapter_status"], "published")

        state_resp = self.client.get(f"/chapters/{chapter_id}/state")
        self.assertEqual(state_resp.status_code, 200)
        state_data = state_resp.json()
        self.assertEqual(state_data["chapter_id"], chapter_id)
        self.assertEqual(state_data["state"]["agenda_review_status"], "approved")
        self.assertEqual(state_data["state"]["novel_id"], "novel-api-001")

    def test_plan_can_switch_use_mock_llm_from_request(self) -> None:
        chapter_id = "chapter-api-real-0001"

        plan_resp = self.client.post(
            f"/chapters/{chapter_id}/plan",
            json={
                "novel_id": "novel-api-real",
                "novel_title": "真实模型切换测试",
                "chapter_number": 1,
                "chapter_title": "第一章",
                "use_mock_llm": False,
            },
        )
        self.assertEqual(plan_resp.status_code, 200)

        state_resp = self.client.get(f"/chapters/{chapter_id}/state")
        self.assertEqual(state_resp.status_code, 200)
        state_data = state_resp.json()["state"]
        self.assertFalse(state_data["use_mock_llm"])

    def test_plan_real_llm_failure_is_visible(self) -> None:
        chapter_id = "chapter-api-real-fail-0001"
        os.environ["LLM_API_KEY"] = ""
        os.environ["LLM_BASE_URL"] = ""

        plan_resp = self.client.post(
            f"/chapters/{chapter_id}/plan",
            json={
                "novel_id": "novel-api-real-fail",
                "novel_title": "真实模型失败可见性测试",
                "chapter_number": 1,
                "chapter_title": "第一章",
                "use_mock_llm": False,
            },
        )
        self.assertEqual(plan_resp.status_code, 200)
        plan_data = plan_resp.json()
        self.assertIn("LLM_API_KEY", plan_data["error"])
        self.assertEqual(plan_data["rag_evidence"], [])

        state_resp = self.client.get(f"/chapters/{chapter_id}/state")
        self.assertEqual(state_resp.status_code, 200)
        state_data = state_resp.json()["state"]
        self.assertIn("LLM_API_KEY", state_data["error"])

    def test_multi_novel_and_chapter_management_routes(self) -> None:
        payloads = [
            {
                "chapter_id": "chapter-a-001",
                "novel_id": "novel-a",
                "novel_title": "小说 A",
                "chapter_number": 2,
                "chapter_title": "第二章",
            },
            {
                "chapter_id": "chapter-a-000",
                "novel_id": "novel-a",
                "novel_title": "小说 A",
                "chapter_number": 1,
                "chapter_title": "第一章",
            },
            {
                "chapter_id": "chapter-b-001",
                "novel_id": "novel-b",
                "novel_title": "小说 B",
                "chapter_number": 1,
                "chapter_title": "序章",
            },
        ]

        for item in payloads:
            response = self.client.post(
                f"/chapters/{item['chapter_id']}/plan",
                json={
                    "novel_id": item["novel_id"],
                    "novel_title": item["novel_title"],
                    "chapter_number": item["chapter_number"],
                    "chapter_title": item["chapter_title"],
                },
            )
            self.assertEqual(response.status_code, 200)

        novels_resp = self.client.get("/novels")
        self.assertEqual(novels_resp.status_code, 200)
        novels_data = novels_resp.json()["novels"]
        self.assertEqual(len(novels_data), 2)

        novel_index = {item["novel_id"]: item for item in novels_data}
        self.assertEqual(novel_index["novel-a"]["chapter_count"], 2)
        self.assertEqual(novel_index["novel-b"]["chapter_count"], 1)

        chapters_resp = self.client.get("/novels/novel-a/chapters")
        self.assertEqual(chapters_resp.status_code, 200)
        chapters_data = chapters_resp.json()
        self.assertEqual(chapters_data["novel_title"], "小说 A")
        self.assertEqual([item["chapter_number"] for item in chapters_data["chapters"]], [1, 2])
        self.assertEqual(chapters_data["chapters"][0]["chapter_title"], "第一章")

        empty_chapters_resp = self.client.get("/novels/not-exists/chapters")
        self.assertEqual(empty_chapters_resp.status_code, 200)
        self.assertEqual(empty_chapters_resp.json()["chapters"], [])

    def test_create_empty_novel_and_keep_it_visible(self) -> None:
        create_resp = self.client.post(
            "/novels",
            json={
                "novel_id": "novel-empty",
                "novel_title": "空小说",
            },
        )
        self.assertEqual(create_resp.status_code, 200)
        create_data = create_resp.json()
        self.assertEqual(create_data["novel_id"], "novel-empty")
        self.assertEqual(create_data["novel_title"], "空小说")
        self.assertEqual(create_data["chapter_count"], 0)

        novels_resp = self.client.get("/novels")
        self.assertEqual(novels_resp.status_code, 200)
        novel_index = {item["novel_id"]: item for item in novels_resp.json()["novels"]}
        self.assertIn("novel-empty", novel_index)
        self.assertEqual(novel_index["novel-empty"]["chapter_count"], 0)
        self.assertEqual(novel_index["novel-empty"]["latest_chapter_id"], "")

        chapters_resp = self.client.get("/novels/novel-empty/chapters")
        self.assertEqual(chapters_resp.status_code, 200)
        chapters_data = chapters_resp.json()
        self.assertEqual(chapters_data["novel_title"], "空小说")
        self.assertEqual(chapters_data["chapters"], [])

        duplicate_resp = self.client.post(
            "/novels",
            json={
                "novel_id": "novel-empty",
                "novel_title": "重复标题",
            },
        )
        self.assertEqual(duplicate_resp.status_code, 409)
        self.assertEqual(duplicate_resp.json()["error_code"], "NOVEL_ALREADY_EXISTS")

    def test_next_chapter_plan_inherits_previous_chapter_context(self) -> None:
        first_chapter_id = "chapter-seq-001"
        second_chapter_id = "chapter-seq-002"

        first_plan = self.client.post(
            f"/chapters/{first_chapter_id}/plan",
            json={
                "novel_id": "novel-seq",
                "novel_title": "连续章节小说",
                "chapter_number": 1,
                "chapter_title": "第一章",
                "world_rules": "筑基期不能瞬移。",
                "future_waypoints": "跟踪者不能在本章死亡。",
                "guidance_from_future": "第二章继续强化被监视感。",
            },
        )
        self.assertEqual(first_plan.status_code, 200)

        review_resp = self.client.post(
            f"/chapters/{first_chapter_id}/review",
            json={
                "agenda_review_status": "approved",
                "agenda_review_notes": "通过",
                "approved_chapter_agenda": "",
                "approved_rag_recall_summary": "",
            },
        )
        self.assertEqual(review_resp.status_code, 200)

        draft_resp = self.client.post(f"/chapters/{first_chapter_id}/draft")
        self.assertEqual(draft_resp.status_code, 200)
        first_state_resp = self.client.get(f"/chapters/{first_chapter_id}/state")
        first_state = first_state_resp.json()["state"]

        second_plan = self.client.post(
            f"/chapters/{second_chapter_id}/plan",
            json={
                "novel_id": "novel-seq",
                "chapter_number": 2,
                "chapter_agenda_draft": "主角沿着上一章留下的线索追查到旧港口。",
            },
        )
        self.assertEqual(second_plan.status_code, 200)
        second_plan_data = second_plan.json()
        self.assertEqual(second_plan_data["chapter_title"], "第2章")

        second_state_resp = self.client.get(f"/chapters/{second_chapter_id}/state")
        second_state = second_state_resp.json()["state"]
        self.assertEqual(second_state["novel_title"], "连续章节小说")
        self.assertEqual(second_state["previous_chapter_ending"], first_state["previous_chapter_ending"])
        self.assertEqual(second_state["world_rules"], first_state["world_rules"])
        self.assertEqual(second_state["future_waypoints"], first_state["future_waypoints"])
        self.assertEqual(second_state["guidance_from_future"], first_state["guidance_from_future"])

    def test_uniform_error_payloads(self) -> None:
        missing_resp = self.client.get("/chapters/not-found/review-task")
        self.assertEqual(missing_resp.status_code, 404)
        self.assertEqual(missing_resp.json()["error_code"], "CHAPTER_NOT_FOUND")

        invalid_review = self.client.post(
            "/chapters/demo/review",
            json={"agenda_review_status": "bad-status"},
        )
        self.assertEqual(invalid_review.status_code, 422)
        self.assertEqual(invalid_review.json()["error_code"], "REQUEST_VALIDATION_ERROR")

        invalid_novel = self.client.post(
            "/novels",
            json={"novel_id": "   ", "novel_title": ""},
        )
        self.assertEqual(invalid_novel.status_code, 422)
        self.assertEqual(invalid_novel.json()["error_code"], "REQUEST_VALIDATION_ERROR")


if __name__ == "__main__":
    unittest.main()
