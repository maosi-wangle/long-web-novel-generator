from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from novel_assist.graph.workflow import build_workflow_app
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
        "novel_title": os.getenv("NOVEL_TITLE", "默认演示小说"),
        "chapter_id": os.getenv("CHAPTER_ID", "demo-chapter-001"),
        "chapter_number": int(os.getenv("CHAPTER_NUMBER", "1")),
        "chapter_title": os.getenv("CHAPTER_TITLE", "第一章"),
        "global_outline": "在旧工业城邦的废墟上，一群年轻人试图揭开能源垄断背后的真相。",
        "current_arc": "主角第一次接触反抗组织，并意识到父亲失踪并非意外。",
        "current_phase": "起",
        "memory_l0": "主角林澈，机械修理铺学徒，擅长观察细节。",
        "previous_chapter_ending": "林澈在暴雨夜捡到一枚带有议会徽记的损坏数据芯片。",
        "chapter_agenda": "林澈在地下黑市寻找能读取芯片的人，却发现自己被人跟踪。",
        "world_rules": "境界顺序不可跳跃；筑基期不能瞬移；跨城传送需借助阵法与高额代价。",
        "future_waypoints": "跟踪者不能在本章死亡；第50章主角坠崖失忆；第100章天渊城决战。",
        "guidance_from_future": "跟踪者将在中后期揭示主角父亲失踪真相。",
        "agenda_review_status": "pending",
        "agenda_review_notes": "",
        "approved_chapter_agenda": "",
        "approved_rag_recall_summary": "",
        "chapter_status": "planning",
        "rewrite_count": 0,
        "max_rewrites": int(os.getenv("MAX_REWRITES", "3")),
        "model_name": os.getenv("LLM_MODEL_NAME", "qwen3-max-preview"),
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.9")),
        "use_mock_llm": use_mock,
        "show_draft_system_prompt": _as_bool(os.getenv("SHOW_DRAFT_SYSTEM_PROMPT", "0")),
        "show_draft_prompt": _as_bool(os.getenv("SHOW_DRAFT_PROMPT", "0")),
    }


def main() -> None:
    load_dotenv()
    app = build_workflow_app()
    initial_state = build_initial_state()

    print("=== Stage 2 Backend Graph MVP ===")
    print(f"use_mock_llm: {initial_state.get('use_mock_llm')}")
    print(f"HUMAN_REVIEW_STATUS: {os.getenv('HUMAN_REVIEW_STATUS', '(unset)')}")
    print(f"AUTO_APPROVE_REVIEW: {os.getenv('AUTO_APPROVE_REVIEW', '(unset)')}")
    print(f"CRITIC_FORCE_FAIL: {os.getenv('CRITIC_FORCE_FAIL', '(unset)')}")
    print(f"max_rewrites: {initial_state.get('max_rewrites')}")

    result = app.invoke(initial_state)

    print("\n=== Result ===")
    print(f"agenda_review_status: {result.get('agenda_review_status', '')}")
    print(f"rewrite_count: {result.get('rewrite_count', 0)}")
    print(f"error: {result.get('error', '')}")
    print(f"critic_feedback: {result.get('critic_feedback', '')}")
    print(f"draft_word_count: {result.get('draft_word_count', 0)}")
    print(f"recall_trace_id: {result.get('recall_trace_id', '')}")
    print(f"review_trace_id: {result.get('review_trace_id', '')}")
    print(f"audit_log_path: {result.get('audit_log_path', '')}")
    print(f"audit_warning: {result.get('audit_warning', '')}")
    print("\n--- Approved Agenda ---")
    print(str(result.get("approved_chapter_agenda", ""))[:300])
    print("\n--- RAG Summary ---")
    print(str(result.get("rag_recall_summary", ""))[:300])
    print("\n--- Draft Preview ---")
    draft = str(result.get("draft", ""))
    preview = draft[:500] + ("..." if len(draft) > 500 else "")
    print(preview)


if __name__ == "__main__":
    main()
