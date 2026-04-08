from __future__ import annotations

import os
from typing import Any

from novel_assist.stores.factory import get_graph_store
from novel_assist.state.novel_state import NovelState


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def human_agenda_review_gate(state: NovelState) -> dict[str, Any]:
    """
    Human-in-the-loop gate.

    In phase-2 backend MVP, this node supports two modes:
    1) Real blocking mode: keep status as pending/rejected/edited, workflow stops/loops by routing.
    2) Dev auto-approve mode via AUTO_APPROVE_REVIEW=1 for quick local validation.
    """
    status = str(state.get("agenda_review_status", "pending"))
    chapter_agenda = state.get("chapter_agenda", "")
    rag_summary = state.get("rag_recall_summary", "")
    enforce_state_review_status = _as_bool(state.get("enforce_state_review_status"))

    if not enforce_state_review_status:
        env_status = os.getenv("HUMAN_REVIEW_STATUS", "").strip().lower()
        if env_status in {"pending", "approved", "rejected", "edited"}:
            status = env_status

        auto_approve = _as_bool(os.getenv("AUTO_APPROVE_REVIEW", "0"))
        if status == "pending" and auto_approve:
            status = "approved"

    updates: dict[str, Any] = {"agenda_review_status": status}

    if status == "approved":
        updates.update(
            {
                "agenda_review_notes": state.get("agenda_review_notes", "人工审核通过。"),
                "approved_chapter_agenda": state.get("approved_chapter_agenda") or chapter_agenda,
                "approved_rag_recall_summary": state.get("approved_rag_recall_summary") or rag_summary,
                "error": "",
            }
        )
    elif status == "rejected":
        updates.update(
            {
                "agenda_review_notes": state.get("agenda_review_notes", "人工驳回：请重做细纲。"),
                "approved_chapter_agenda": "",
                "approved_rag_recall_summary": "",
                "error": "HumanReviewRejected: 细纲被人工驳回，返回 PlotPlanner。",
            }
        )
    else:
        updates.update(
            {
                "approved_chapter_agenda": "",
                "approved_rag_recall_summary": "",
                "error": "HumanReviewRequired: 等待人工审核细纲与RAG设定。",
            }
        )

    chapter_id = str(state.get("chapter_id", "chapter-unknown"))
    recall_trace_id = str(state.get("recall_trace_id", ""))
    review_trace_id = str(state.get("review_trace_id", ""))
    audit_log_path = str(state.get("audit_log_path", ""))

    try:
        store = get_graph_store()
        review_trace_id, audit_log_path = store.persist_human_review_event(
            chapter_id=chapter_id,
            recall_trace_id=recall_trace_id,
            review_trace_id=review_trace_id,
            agenda_review_status=status,
            agenda_review_notes=str(updates.get("agenda_review_notes", "")),
            approved_chapter_agenda=str(updates.get("approved_chapter_agenda", "")),
            approved_rag_recall_summary=str(updates.get("approved_rag_recall_summary", "")),
        )
        updates["review_trace_id"] = review_trace_id
        updates["audit_log_path"] = audit_log_path
        updates["audit_warning"] = ""
    except Exception as exc:
        updates["audit_warning"] = f"AuditLogWriteFailed: {type(exc).__name__}: {exc}"

    return updates
