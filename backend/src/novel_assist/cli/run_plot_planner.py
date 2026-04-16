from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from novel_assist.nodes.plot_planner import build_plot_prompt, plotting_node
from novel_assist.state.novel_state import NovelState


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def build_initial_state() -> NovelState:
    use_mock = _as_bool(os.getenv("USE_MOCK_LLM", "1"))
    return {
        "novel_id": os.getenv("NOVEL_ID", "demo-novel-001"),
        "novel_title": os.getenv("NOVEL_TITLE", "测试小说"),
        "chapter_id": os.getenv("CHAPTER_ID", "demo-chapter-001"),
        "chapter_number": int(os.getenv("CHAPTER_NUMBER", "1")),
        "chapter_title": os.getenv("CHAPTER_TITLE", "第一章"),
        "global_outline": os.getenv(
            "GLOBAL_OUTLINE",
            "主角意外卷入城市下层与议会势力的冲突，并逐步逼近父亲失踪的真相。",
        ),
        "current_arc": os.getenv(
            "CURRENT_ARC",
            "主角刚接触黑市与反抗组织，开始发现自己被更大势力盯上。",
        ),
        "current_phase": os.getenv("CURRENT_PHASE", "起"),
        "memory_l0": os.getenv(
            "MEMORY_L0",
            "主角林澈擅长观察细节，刚捡到带有议会徽记的损坏芯片。",
        ),
        "previous_chapter_ending": os.getenv(
            "PREVIOUS_CHAPTER_ENDING",
            "暴雨刚停，林澈意识到芯片背后牵扯的人远超自己想象。",
        ),
        "chapter_agenda_draft": os.getenv(
            "CHAPTER_AGENDA_DRAFT",
            "主角在黑市找解码师，确认自己被人跟踪。",
        ),
        "chapter_agenda": "",
        "world_rules": os.getenv("WORLD_RULES", "筑基期不能瞬移。"),
        "future_waypoints": os.getenv("FUTURE_WAYPOINTS", "跟踪者不能在本章死亡。"),
        "guidance_from_future": os.getenv(
            "GUIDANCE_FROM_FUTURE",
            "这一章要强化被监视感，并埋下父亲失踪真相的后续线索。",
        ),
        "agenda_review_status": os.getenv("AGENDA_REVIEW_STATUS", "pending"),
        "agenda_review_notes": os.getenv("AGENDA_REVIEW_NOTES", ""),
        "approved_chapter_agenda": "",
        "approved_rag_recall_summary": "",
        "chapter_status": "planning",
        "rewrite_count": 0,
        "max_rewrites": int(os.getenv("MAX_REWRITES", "3")),
        "model_name": os.getenv("LLM_MODEL_NAME", "qwen3-max-preview"),
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.7")),
        "use_mock_llm": use_mock,
        "error": "",
    }


def main() -> None:
    load_dotenv()
    state = build_initial_state()
    show_prompt = _as_bool(os.getenv("SHOW_PLOT_PROMPT", "0"))

    print("=== PlotPlanner Node Runner ===")
    print(f"use_mock_llm: {state.get('use_mock_llm')}")
    print(f"model_name: {state.get('model_name')}")
    print(f"chapter_id: {state.get('chapter_id')}")
    print(f"chapter_title: {state.get('chapter_title')}")
    print("\n--- Agenda Draft Input ---")
    print(state.get("chapter_agenda_draft", ""))

    if show_prompt:
        print("\n--- Plot Prompt ---")
        print(build_plot_prompt(state))

    result = plotting_node(state)

    print("\n=== PlotPlanner Result ===")
    print(f"agenda_review_status: {result.get('agenda_review_status', '')}")
    print(f"error: {result.get('error', '')}")
    print("\n--- Planned Agenda ---")
    print(result.get("chapter_agenda", ""))


if __name__ == "__main__":
    main()
