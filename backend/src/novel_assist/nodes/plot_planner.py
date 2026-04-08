from __future__ import annotations

from typing import Any

from novel_assist.state.novel_state import NovelState

DEFAULT_AGENDA = "主角在黑市追踪线索，确认议会势力正在回收关键证物。"


def plotting_node(state: NovelState) -> dict[str, Any]:
    """Create or refresh chapter agenda candidates before human review."""
    current_agenda = state.get("chapter_agenda") or DEFAULT_AGENDA
    review_status = state.get("agenda_review_status", "pending")
    review_notes = state.get("agenda_review_notes", "").strip()

    if review_status == "rejected" and review_notes:
        next_agenda = f"{current_agenda}\n（已根据人工驳回意见调整：{review_notes}）"
    else:
        next_agenda = current_agenda

    return {
        "chapter_agenda": next_agenda,
        "agenda_review_status": "pending",
        "agenda_review_notes": "",
        "approved_chapter_agenda": "",
        "approved_rag_recall_summary": "",
        "error": "",
    }
