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
        os.environ.pop("HUMAN_REVIEW_STATUS", None)
        os.environ.pop("AUTO_APPROVE_REVIEW", None)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._old_env)
        self._tmp_dir.cleanup()

    def test_hitl_end_to_end(self) -> None:
        chapter_id = "chapter-api-0001"

        plan_resp = self.client.post(f"/chapters/{chapter_id}/plan", json={})
        self.assertEqual(plan_resp.status_code, 200)
        plan_data = plan_resp.json()
        self.assertEqual(plan_data["agenda_review_status"], "pending")
        self.assertGreater(len(plan_data.get("rag_evidence", [])), 0)

        review_task_resp = self.client.get(f"/chapters/{chapter_id}/review-task")
        self.assertEqual(review_task_resp.status_code, 200)
        task_data = review_task_resp.json()
        self.assertEqual(task_data["chapter_id"], chapter_id)
        self.assertTrue(task_data["recall_trace_id"].startswith("recall-"))

        blocked_draft_resp = self.client.post(f"/chapters/{chapter_id}/draft")
        self.assertEqual(blocked_draft_resp.status_code, 409)
        self.assertIn("HumanReviewRequired", blocked_draft_resp.json()["detail"])

        review_resp = self.client.post(
            f"/chapters/{chapter_id}/review",
            json={
                "agenda_review_status": "approved",
                "agenda_review_notes": "通过，进入初稿生成。",
                "approved_chapter_agenda": "",
                "approved_rag_recall_summary": "",
            },
        )
        self.assertEqual(review_resp.status_code, 200)
        review_data = review_resp.json()
        self.assertEqual(review_data["agenda_review_status"], "approved")
        self.assertTrue(review_data["review_trace_id"].startswith("review-"))

        draft_resp = self.client.post(f"/chapters/{chapter_id}/draft")
        self.assertEqual(draft_resp.status_code, 200)
        draft_data = draft_resp.json()
        self.assertGreater(int(draft_data.get("draft_word_count", 0)), 0)
        self.assertEqual(draft_data.get("error", ""), "")


if __name__ == "__main__":
    unittest.main()
