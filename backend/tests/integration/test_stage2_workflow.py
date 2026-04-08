import os
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from novel_assist.cli.run_stage2 import build_initial_state  # noqa: E402
from novel_assist.graph.workflow import build_workflow_app  # noqa: E402


class Stage2WorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = dict(os.environ)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._old_env)

    def _invoke(self) -> dict:
        app = build_workflow_app()
        return app.invoke(build_initial_state())

    def test_pending_review_blocks_draft_generation(self) -> None:
        os.environ["USE_MOCK_LLM"] = "1"
        os.environ.pop("HUMAN_REVIEW_STATUS", None)
        os.environ.pop("AUTO_APPROVE_REVIEW", None)
        os.environ.pop("CRITIC_FORCE_FAIL", None)

        result = self._invoke()

        self.assertEqual(result.get("agenda_review_status"), "pending")
        draft_count = result.get("draft_word_count")
        self.assertTrue(draft_count in (None, 0))
        self.assertTrue(str(result.get("error", "")).startswith("HumanReviewRequired"))

    def test_approved_review_allows_draft_generation(self) -> None:
        os.environ["USE_MOCK_LLM"] = "1"
        os.environ["HUMAN_REVIEW_STATUS"] = "approved"
        os.environ.pop("CRITIC_FORCE_FAIL", None)

        result = self._invoke()

        self.assertEqual(result.get("agenda_review_status"), "approved")
        self.assertGreater(int(result.get("draft_word_count", 0)), 0)
        self.assertEqual(result.get("error", ""), "")
        self.assertTrue(str(result.get("approved_chapter_agenda", "")).strip())
        self.assertIn("CriticPassed", str(result.get("critic_feedback", "")))

    def test_critic_rewrite_until_abort_by_max_rewrites(self) -> None:
        os.environ["USE_MOCK_LLM"] = "1"
        os.environ["HUMAN_REVIEW_STATUS"] = "approved"
        os.environ["CRITIC_FORCE_FAIL"] = "1"
        os.environ["MAX_REWRITES"] = "2"

        result = self._invoke()

        self.assertEqual(int(result.get("rewrite_count", 0)), 2)
        self.assertTrue(str(result.get("error", "")).startswith("CriticRejected"))
        self.assertIn("CRITIC_FORCE_FAIL", str(result.get("critic_feedback", "")))
        self.assertGreater(int(result.get("draft_word_count", 0)), 0)


if __name__ == "__main__":
    unittest.main()
