import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from novel_assist.nodes.memory_harvester import memory_harvester_node, preview_memory_harvest  # noqa: E402
from novel_assist.stores.factory import get_graph_store  # noqa: E402


class Stage5MemoryHarvestIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = dict(os.environ)
        self._tmp_dir = tempfile.TemporaryDirectory()
        root = Path(self._tmp_dir.name)
        os.environ["USE_MOCK_LLM"] = "1"
        os.environ["GRAPH_STORE_BACKEND"] = "jsonl"
        os.environ["CHAPTER_STATE_PATH"] = str(root / "chapter_state.json")
        os.environ["REVIEW_AUDIT_PATH"] = str(root / "review_audit.jsonl")
        os.environ["NOVEL_STATE_PATH"] = str(root / "novel_state.json")
        os.environ["MEMORY_STATE_PATH"] = str(root / "memory_state.json")

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._old_env)
        self._tmp_dir.cleanup()

    def test_memory_harvest_uses_llm_sections_and_persists_structured_items(self) -> None:
        novel_id = "novel-memory"
        chapter_id = "chapter-memory-001"
        state = {
            "novel_id": novel_id,
            "chapter_id": chapter_id,
            "chapter_number": 1,
            "chapter_title": "Chapter One",
            "approved_chapter_agenda": "Lin Xiao investigates the Black Tower and protects the Glass Key.",
            "approved_rag_recall_summary": "The Glass Key must stay hidden from the Black Tower.",
            "draft": (
                "Lin Xiao followed the Black Tower through Rain Harbor. "
                "Lin Xiao found the Glass Key inside the archive. "
                "Xu Yan tried to seize the Glass Key from Lin Xiao."
            ),
            "review_trace_id": "review-memory-001",
            "model_name": "mock-model",
            "temperature": 0.2,
            "use_mock_llm": True,
        }

        preview = preview_memory_harvest(state)
        self.assertEqual(preview["final_source"], "llm")
        self.assertEqual(preview["llm_extraction_error"], "")
        self.assertGreaterEqual(len(preview["llm_sections"]["base_items"]), 1)
        self.assertGreaterEqual(len(preview["llm_sections"]["entities"]), 2)
        self.assertGreaterEqual(len(preview["final_items"]), 3)

        updates = memory_harvester_node(state)
        self.assertTrue(updates.get("previous_chapter_ending"))
        self.assertEqual(updates.get("memory_harvest_source"), "llm")

        store = get_graph_store()
        items = store.list_memory_items(novel_id=novel_id)
        self.assertGreaterEqual(len(items), 3)
        self.assertTrue(any(item.get("memory_type") == "event" for item in items))
        self.assertTrue(any(item.get("memory_type") == "entity" for item in items))
        self.assertTrue(any(item.get("memory_type") == "relation" for item in items))
        self.assertTrue(any("llm-extracted" in item.get("tags", []) for item in items))
        self.assertTrue(
            any(item.get("memory_type") == "event" and item.get("entity_ids") for item in items)
        )
        self.assertTrue(
            any("character" in item.get("tags", []) for item in items if item.get("memory_type") == "entity")
        )

        hits = store.retrieve_memory_candidates(
            novel_id=novel_id,
            chapter_id=chapter_id,
            query_text="Lin Xiao Glass Key",
            tags=["event"],
            limit=5,
        )
        self.assertGreaterEqual(len(hits), 1)
        self.assertEqual(hits[0]["source_type"], "memory_item")
        self.assertIn("score", hits[0])
        self.assertTrue(any(entity_id.startswith("role:") for entity_id in hits[0].get("entity_ids", [])))


if __name__ == "__main__":
    unittest.main()
