from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langgraph.graph import END, START, StateGraph

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from novel_assist.nodes.draft_writer import draft_writer_node
from novel_assist.state.novel_state import NovelState


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def build_stage1_graph():
    workflow = StateGraph(NovelState)
    workflow.add_node("draft_writer", draft_writer_node)
    workflow.add_edge(START, "draft_writer")
    workflow.add_edge("draft_writer", END)
    return workflow.compile()


def build_initial_state() -> NovelState:
    use_mock = os.getenv("USE_MOCK_LLM", "0").strip().lower() in {"1", "true", "yes", "on"}
    show_system_prompt = _as_bool(os.getenv("SHOW_DRAFT_SYSTEM_PROMPT", "0"))
    show_prompt = _as_bool(os.getenv("SHOW_DRAFT_PROMPT", "0"))
    review_status = os.getenv("AGENDA_REVIEW_STATUS", "approved").strip().lower()
    chapter_agenda = "林澈在地下黑市寻找能读取芯片的人，却发现自己被人跟踪。"
    rag_summary = "跟踪者身份与议会矿区势力相关，不能在本章死亡，后续用于揭示父亲失踪真相。"
    return {
        "chapter_id": os.getenv("CHAPTER_ID", "demo-chapter-001"),
        "global_outline": "在旧工业城邦的废墟上，一群年轻人试图揭开能源垄断背后的真相。",
        "current_arc": "主角第一次接触反抗组织，并意识到自己父亲的失踪并非意外。",
        "current_phase": "起",
        "memory_l0": "主角林澈，机械修理铺学徒，谨慎克制，擅长观察细节。",
        "previous_chapter_ending": "林澈在暴雨夜捡到一枚带有议会徽记的损坏数据芯片。",
        "chapter_agenda": chapter_agenda,
        "world_rules": "境界顺序不可跳跃；筑基期不能瞬移；跨城传送需借助阵法与高额代价。",
        "future_waypoints": "第50章主角必须坠崖失忆；第100章主角与终极反派在天渊城决战。",
        "guidance_from_future": "跟踪者不能在本章死亡，他将在中后期揭示主角父亲失踪真相。",
        "rag_recall_summary": rag_summary,
        "rag_evidence": [
            {
                "source_id": "rule-foreshadow-001",
                "title": "跟踪者线索约束",
                "snippet": "跟踪者不得在本章死亡，将在中后期揭示主角父亲失踪真相。",
                "score": 0.92,
            }
        ],
        "agenda_review_status": review_status,
        "agenda_review_notes": "编辑确认细纲与设定一致。",
        "approved_chapter_agenda": chapter_agenda if review_status == "approved" else "",
        "approved_rag_recall_summary": rag_summary if review_status == "approved" else "",
        "critic_feedback": "",
        "rewrite_count": 0,
        "max_rewrites": 3,
        "model_name": os.getenv("LLM_MODEL_NAME", "qwen3-max-preview"),
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.9")),
        "use_mock_llm": use_mock,
        "show_draft_system_prompt": show_system_prompt,
        "show_draft_prompt": show_prompt,
    }


def main() -> None:
    load_dotenv()
    app = build_stage1_graph()
    initial_state = build_initial_state()
    mode = "MOCK" if initial_state["use_mock_llm"] else "REAL"
    review_status = initial_state.get("agenda_review_status", "pending")
    show_system_prompt = bool(initial_state.get("show_draft_system_prompt", False))
    show_prompt = bool(initial_state.get("show_draft_prompt", False))
    print(f"run_mode: {mode}")
    print(f"agenda_review_status: {review_status}")
    print(f"show_draft_system_prompt: {show_system_prompt}")
    print(f"show_draft_prompt: {show_prompt}")
    if initial_state["use_mock_llm"]:
        print("tip: 使用真实模型请先执行 `Remove-Item Env:USE_MOCK_LLM` 或设置 `USE_MOCK_LLM=0`")
    if review_status != "approved":
        print("tip: 当前状态不会生成初稿；将返回 HumanReviewRequired。")
    result = app.invoke(initial_state)

    print("=== Stage 1 Graph Invoke Completed ===")
    print(f"word_count: {result.get('draft_word_count', 0)}")
    print(f"error: {result.get('error', '')}")
    print("\n--- Draft Preview ---")
    draft = str(result.get("draft", ""))
    preview = draft[:500] + ("..." if len(draft) > 500 else "")
    print(preview)


if __name__ == "__main__":
    main()
