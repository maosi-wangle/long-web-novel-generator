from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from novel_assist.stores.factory import get_graph_store
from novel_assist.stores.jsonl_graph_store import DEFAULT_AUDIT_PATH


def resolve_audit_path() -> Path:
    configured = os.getenv("REVIEW_AUDIT_PATH", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(DEFAULT_AUDIT_PATH).resolve()


def persist_rag_recall_event(
    *,
    chapter_id: str,
    chapter_agenda: str,
    rag_recall_summary: str,
    rag_evidence: list[dict[str, Any]],
    recall_trace_id: str = "",
) -> tuple[str, str]:
    store = get_graph_store()
    return store.persist_rag_recall_event(
        chapter_id=chapter_id,
        chapter_agenda=chapter_agenda,
        rag_recall_summary=rag_recall_summary,
        rag_evidence=rag_evidence,
        recall_trace_id=recall_trace_id,
    )


def persist_human_review_event(
    *,
    chapter_id: str,
    recall_trace_id: str,
    review_trace_id: str = "",
    agenda_review_status: str,
    agenda_review_notes: str,
    approved_chapter_agenda: str,
    approved_rag_recall_summary: str,
) -> tuple[str, str]:
    store = get_graph_store()
    return store.persist_human_review_event(
        chapter_id=chapter_id,
        recall_trace_id=recall_trace_id,
        review_trace_id=review_trace_id,
        agenda_review_status=agenda_review_status,
        agenda_review_notes=agenda_review_notes,
        approved_chapter_agenda=approved_chapter_agenda,
        approved_rag_recall_summary=approved_rag_recall_summary,
    )
