import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from novel_assist.cli.run_stage2 import build_initial_state  # noqa: E402
from novel_assist.graph.workflow import build_workflow_app  # noqa: E402


class Stage3AuditTrailIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = dict(os.environ)
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.audit_path = Path(self._tmp_dir.name) / "review_audit.jsonl"
        os.environ["REVIEW_AUDIT_PATH"] = str(self.audit_path)
        os.environ["MEMORY_STATE_PATH"] = str(Path(self._tmp_dir.name) / "memory_state.json")

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._old_env)
        self._tmp_dir.cleanup()

    def test_recall_and_review_events_are_both_persisted(self) -> None:
        os.environ["USE_MOCK_LLM"] = "1"
        os.environ["HUMAN_REVIEW_STATUS"] = "approved"
        os.environ["CHAPTER_ID"] = "chapter-integration-0001"
        os.environ.pop("CRITIC_FORCE_FAIL", None)

        app = build_workflow_app()
        result = app.invoke(build_initial_state())

        self.assertEqual(result.get("agenda_review_status"), "approved")
        self.assertTrue(str(result.get("recall_trace_id", "")).startswith("recall-"))
        self.assertTrue(str(result.get("review_trace_id", "")).startswith("review-"))
        self.assertEqual(result.get("audit_warning", ""), "")
        self.assertTrue(self.audit_path.exists())

        records = [
            json.loads(line)
            for line in self.audit_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertGreaterEqual(len(records), 2)

        event_types = [record.get("event_type") for record in records]
        self.assertIn("rag_recall", event_types)
        self.assertIn("human_review", event_types)

        recall_record = next(record for record in records if record.get("event_type") == "rag_recall")
        review_record = next(record for record in records if record.get("event_type") == "human_review")
        self.assertEqual(review_record.get("recall_trace_id"), recall_record.get("trace_id"))
        self.assertEqual(review_record.get("chapter_id"), "chapter-integration-0001")


if __name__ == "__main__":
    unittest.main()
