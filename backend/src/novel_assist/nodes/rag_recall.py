from __future__ import annotations

import re
from typing import Any

from novel_assist.stores.factory import get_graph_store
from novel_assist.state.novel_state import NovelState


def _extract_sentences(text: str, *, limit: int) -> list[str]:
    if not text.strip():
        return []
    chunks = [seg.strip() for seg in re.split(r"[。！？!?；;\n]+", text) if seg.strip()]
    return chunks[:limit]


def rag_recall_node(state: NovelState) -> dict[str, Any]:
    """Layered recall: hard constraints first, then near context evidence."""
    chapter_agenda = state.get("chapter_agenda", "")
    world_rules = state.get("world_rules", "")
    future_waypoints = state.get("future_waypoints", "")
    guidance_from_future = state.get("guidance_from_future", "")
    previous_chapter_ending = state.get("previous_chapter_ending", "")
    memory_l0 = state.get("memory_l0", "")
    current_arc = state.get("current_arc", "")

    hard_constraints = (
        _extract_sentences(world_rules, limit=2)
        + _extract_sentences(future_waypoints, limit=2)
        + _extract_sentences(guidance_from_future, limit=1)
    )
    near_context = (
        _extract_sentences(previous_chapter_ending, limit=1)
        + _extract_sentences(memory_l0, limit=1)
        + _extract_sentences(current_arc, limit=1)
    )

    evidence: list[dict[str, Any]] = []
    for idx, snippet in enumerate(hard_constraints, start=1):
        evidence.append(
            {
                "source_id": f"hard-constraint-{idx:02d}",
                "title": "硬规则/宿命约束",
                "snippet": snippet,
                "score": round(max(0.75, 0.96 - idx * 0.03), 2),
            }
        )
    for idx, snippet in enumerate(near_context, start=1):
        evidence.append(
            {
                "source_id": f"near-context-{idx:02d}",
                "title": "相邻章节上下文",
                "snippet": snippet,
                "score": round(max(0.55, 0.78 - idx * 0.04), 2),
            }
        )

    if not evidence:
        evidence = [
            {
                "source_id": "fallback-001",
                "title": "默认召回",
                "snippet": "未命中有效设定，需人工补充关键约束。",
                "score": 0.1,
            }
        ]

    recall_summary = (
        f"本轮召回共 {len(evidence)} 条证据。"
        f"优先命中硬约束 {len(hard_constraints)} 条，"
        f"补充上下文 {len(near_context)} 条。"
        f"当前细纲：{chapter_agenda or '未提供'}"
    )

    recall_trace_id = str(state.get("recall_trace_id", "")).strip()
    chapter_id = str(state.get("chapter_id", "chapter-unknown"))
    audit_warning = ""
    audit_log_path = str(state.get("audit_log_path", ""))

    try:
        store = get_graph_store()
        recall_trace_id, audit_log_path = store.persist_rag_recall_event(
            chapter_id=chapter_id,
            chapter_agenda=chapter_agenda,
            rag_recall_summary=recall_summary,
            rag_evidence=evidence,
            recall_trace_id=recall_trace_id,
        )
    except Exception as exc:
        audit_warning = f"AuditLogWriteFailed: {type(exc).__name__}: {exc}"

    return {
        "rag_recall_summary": recall_summary,
        "rag_evidence": evidence,
        "recall_trace_id": recall_trace_id,
        "audit_log_path": audit_log_path,
        "audit_warning": audit_warning,
    }
