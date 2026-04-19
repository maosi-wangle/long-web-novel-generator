from __future__ import annotations

from typing import Any

import os

from novel_assist.llm.client import generate_text
from novel_assist.state.novel_state import NovelState, WriterViewState

DEFAULT_MODEL_NAME = "qwen3-max-preview"
DEFAULT_TEMPERATURE = 0.9
SYSTEM_PROMPT = """你是小说写作执行助手。
你只能依据“已人工审核通过”的章节信息写作，不得擅自扩展世界规则或未来剧情。

写作约束：
1. 严格遵守当前阶段节奏（起/承/转/合）。
2. 与上一章结尾保持物理衔接。
3. 只输出小说正文，不要解释。
4. 不要使用小标题或项目符号。"""


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def to_writer_view(state: NovelState) -> WriterViewState:
    """Project global state into the masked writer view."""
    return {
        "current_phase": state.get("current_phase", "起"),
        "memory_l0": state.get("memory_l0", "暂无前文背景（故事开篇阶段）"),
        "previous_chapter_ending": state.get("previous_chapter_ending", "暂无上一章结尾"),
        "approved_chapter_agenda": state.get("approved_chapter_agenda", ""),
        "approved_rag_recall_summary": state.get("approved_rag_recall_summary", ""),
    }


def build_draft_prompt(state: WriterViewState) -> str:
    memory_l0 = state.get("memory_l0") or "暂无前文背景（故事开篇阶段）"
    previous_ending = state.get("previous_chapter_ending") or "暂无上一章结尾"
    current_phase = state.get("current_phase") or "起"
    approved_chapter_agenda = state.get("approved_chapter_agenda") or "未提供审核通过细纲"
    approved_rag_recall_summary = state.get("approved_rag_recall_summary") or "未提供审核通过设定摘要"

    return (
        f"[当前阶段]\n{current_phase}\n\n"
        f"[L0记忆]\n{memory_l0}\n\n"
        f"[上一章结尾]\n{previous_ending}\n\n"
        f"[已审核通过细纲]\n{approved_chapter_agenda}\n\n"
        f"[已审核通过设定摘要]\n{approved_rag_recall_summary}\n\n"
        "请基于以上已审核信息创作本章初稿正文。"
    )


def _mock_draft_response(state: WriterViewState) -> str:
    phase = state.get("current_phase", "起")
    agenda = state.get("approved_chapter_agenda", "")
    setting_hint = state.get("approved_rag_recall_summary", "暂无设定摘要")
    return (
        f"夜色压低了屋檐，风从巷口掠过，带起潮湿的尘土味。"
        f"他想起白天那句没有说完的话，脚步在石阶前停了半拍。"
        f"此刻正是“{phase}”段节奏，所有异样都被轻轻按住，"
        f"却又在沉默里一点点露出锋芒。"
        f"他脑海中不断回闪设定线索：{setting_hint}。"
        f"{agenda}"
    )


def draft_writer_node(state: NovelState) -> dict[str, Any]:
    """Generate draft only when agenda has passed human review."""
    next_state: dict[str, Any] = dict(state)

    review_status = str(state.get("agenda_review_status", "pending"))
    if review_status != "approved":
        next_state.update(
            {
                "draft": "",
                "draft_word_count": 0,
                "error": "HumanReviewRequired: 细纲与RAG设定未通过人工审核，禁止进入DraftWriter。",
            }
        )
        return next_state

    writer_view = to_writer_view(state)
    if not writer_view.get("approved_chapter_agenda"):
        next_state.update(
            {
                "draft": "",
                "draft_word_count": 0,
                "error": "InvalidState: approved_chapter_agenda 为空。",
            }
        )
        return next_state

    prompt = build_draft_prompt(writer_view)
    show_system_prompt = _as_bool(state.get("show_draft_system_prompt")) or _as_bool(
        os.getenv("SHOW_DRAFT_SYSTEM_PROMPT")
    )
    show_prompt = _as_bool(state.get("show_draft_prompt")) or _as_bool(
        os.getenv("SHOW_DRAFT_PROMPT")
    )
    if show_system_prompt:
        print("\n=== DraftWriter SYSTEM_PROMPT ===")
        print(SYSTEM_PROMPT)
        print("=== END SYSTEM_PROMPT ===\n")
    if show_prompt:
        print("\n=== DraftWriter USER_PROMPT ===")
        print(prompt)
        print("=== END USER_PROMPT ===\n")

    use_mock_llm = bool(state.get("use_mock_llm", False))
    model_name = str(state.get("model_name", DEFAULT_MODEL_NAME))
    temperature = float(state.get("temperature", DEFAULT_TEMPERATURE))

    try:
        draft_text = generate_text(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=prompt,
            model_name=model_name,
            temperature=temperature,
            max_tokens=3000,
            use_mock_llm=use_mock_llm,
            mock_response_factory=lambda: _mock_draft_response(writer_view),
            strip_output=False,
        )
        next_state.update(
            {
                "draft": draft_text,
                "draft_word_count": len(draft_text),
                "error": "",
            }
        )
        return next_state
    except Exception as exc:
        next_state.update(
            {
                "draft": "",
                "draft_word_count": 0,
                "error": f"{type(exc).__name__}: {exc}",
            }
        )
        return next_state
