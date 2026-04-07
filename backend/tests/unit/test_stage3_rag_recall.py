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

from novel_assist.nodes.rag_recall import rag_recall_node  # noqa: E402


class Stage3RagRecallTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = dict(os.environ)
        self._tmp_dir = tempfile.TemporaryDirectory()
        self.audit_path = Path(self._tmp_dir.name) / "review_audit.jsonl"
        os.environ["REVIEW_AUDIT_PATH"] = str(self.audit_path)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._old_env)
        self._tmp_dir.cleanup()

    def test_layered_recall_and_audit_log_persistence(self) -> None:
        state = {
            "chapter_id": "chapter-0001",
            "chapter_agenda": "主角在黑市找解码师，确认被人跟踪。",
            "world_rules": "筑基期不能瞬移。跨城传送需借助阵法。",
            "future_waypoints": "跟踪者不能在本章死亡。第50章主角坠崖失忆。",
            "guidance_from_future": "跟踪者会揭示父亲失踪真相。",
            "previous_chapter_ending": "上一章结尾：主角拿到损坏芯片。",
            "memory_l0": "主角谨慎克制，擅长观察。",
            "current_arc": "主角第一次接触反抗组织。",
        }

        result = rag_recall_node(state)
        evidence = result.get("rag_evidence", [])

        self.assertTrue(result.get("recall_trace_id", "").startswith("recall-"))
        self.assertTrue(Path(str(result.get("audit_log_path", ""))).exists())
        self.assertEqual(result.get("audit_warning", ""), "")
        self.assertGreaterEqual(len(evidence), 4)
        self.assertTrue(str(evidence[0].get("source_id", "")).startswith("hard-constraint-"))
        self.assertEqual(evidence[0].get("title"), "硬规则/宿命约束")

        records = [
            json.loads(line)
            for line in self.audit_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].get("event_type"), "rag_recall")
        self.assertEqual(records[0].get("chapter_id"), "chapter-0001")
        self.assertEqual(records[0].get("trace_id"), result.get("recall_trace_id"))


if __name__ == "__main__":
    unittest.main()
