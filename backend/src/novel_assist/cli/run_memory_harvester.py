from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from novel_assist.nodes.memory_harvester import preview_memory_harvest
from novel_assist.state.novel_state import NovelState


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def build_manual_state() -> NovelState:
    """Fill the text fields below, then run this file to inspect harvest output."""
    return {
        "novel_id": os.getenv("NOVEL_ID", "manual-novel-001"),
        "novel_title": os.getenv("NOVEL_TITLE", "Manual Harvest Probe"),
        "chapter_id": os.getenv("CHAPTER_ID", "manual-chapter-001"),
        "chapter_number": int(os.getenv("CHAPTER_NUMBER", "1")),
        "chapter_title": os.getenv("CHAPTER_TITLE", "Manual Chapter"),
        "approved_chapter_agenda": os.getenv("APPROVED_CHAPTER_AGENDA", ""),
        "approved_rag_recall_summary": os.getenv("APPROVED_RAG_RECALL_SUMMARY", ""),
        "draft": os.getenv(
            "DRAFT_TEXT",
            "在这里填入章节正文。建议只放本章正文，不要把大段 agenda 和 draft 重复贴进去。",
        ),
        "previous_chapter_ending": os.getenv("PREVIOUS_CHAPTER_ENDING", ""),
        "review_trace_id": os.getenv("REVIEW_TRACE_ID", "manual-review-trace"),
        "model_name": os.getenv("LLM_MODEL_NAME", "qwen3-max-preview"),
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.2")),
        "use_mock_llm": _as_bool(os.getenv("USE_MOCK_LLM", "0")),
    }


def _print_json(title: str, payload: object) -> None:
    print(f"\n=== {title} ===")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    load_dotenv()
    state = build_manual_state()
    result = preview_memory_harvest(state)

    print("=== Memory Harvester Probe ===")
    print(f"use_mock_llm: {state.get('use_mock_llm')}")
    print(f"model_name: {state.get('model_name')}")
    print(f"chapter_id: {state.get('chapter_id')}")
    print(f"draft_length: {len(str(state.get('draft', '')))}")
    print(f"final_source: {result['final_source']}")
    print(f"llm_error: {result['llm_extraction_error'] or '(none)'}")

    _print_json(
        "Input Summary",
        {
            "approved_chapter_agenda": state.get("approved_chapter_agenda", ""),
            "approved_rag_recall_summary": state.get("approved_rag_recall_summary", ""),
            "draft": state.get("draft", ""),
            "previous_chapter_ending": state.get("previous_chapter_ending", ""),
        },
    )
    print(f"\n=== Derived Ending ===\n{result['ending']}")
    _print_json("Fallback Sections", result["fallback_sections"])
    _print_json("LLM Sections", result["llm_sections"])
    _print_json("Final Sections", result["final_sections"])
    _print_json("Final Items", result["final_items"])


if __name__ == "__main__":
    main()
