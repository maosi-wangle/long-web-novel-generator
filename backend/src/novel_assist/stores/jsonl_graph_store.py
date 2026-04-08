from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from novel_assist.stores.graph_store import GraphStore

DEFAULT_RUNTIME_DIR = Path(__file__).resolve().parents[3] / "runtime"
DEFAULT_AUDIT_PATH = DEFAULT_RUNTIME_DIR / "review_audit.jsonl"
DEFAULT_STATE_PATH = DEFAULT_RUNTIME_DIR / "chapter_state.json"
DEFAULT_NOVEL_PATH = DEFAULT_RUNTIME_DIR / "novel_state.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _as_int(value: Any, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class JsonlGraphStore(GraphStore):
    """JSONL + JSON implementation for local development."""

    def __init__(self) -> None:
        self._audit_path = self._resolve_audit_path()
        self._state_path = self._resolve_state_path()
        self._novel_path = self._resolve_novel_path()

    @staticmethod
    def _resolve_audit_path() -> Path:
        configured = os.getenv("REVIEW_AUDIT_PATH", "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        return DEFAULT_AUDIT_PATH.resolve()

    @staticmethod
    def _resolve_state_path() -> Path:
        configured = os.getenv("CHAPTER_STATE_PATH", "").strip()
        if configured:
            return Path(configured).expanduser().resolve()
        return DEFAULT_STATE_PATH.resolve()

    @staticmethod
    def _resolve_novel_path() -> Path:
        configured = os.getenv("NOVEL_STATE_PATH", "").strip()
        if configured:
            return Path(configured).expanduser().resolve()

        chapter_state_configured = os.getenv("CHAPTER_STATE_PATH", "").strip()
        if chapter_state_configured:
            return Path(chapter_state_configured).expanduser().resolve().with_name("novel_state.json")

        return DEFAULT_NOVEL_PATH.resolve()

    def _append_record(self, record: dict[str, Any]) -> str:
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)#如果父目录没有就创建，已经有就静默往下执行
        with self._audit_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")#dumps，上下文管理器
        return str(self._audit_path)

    def _read_state_map(self) -> dict[str, dict[str, Any]]:
        if not self._state_path.exists():
            return {}
        raw = self._state_path.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): v for k, v in data.items() if isinstance(v, dict)}
        return {}

    def _write_state_map(self, data: dict[str, dict[str, Any]]) -> str:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(self._state_path)

    def _read_novel_map(self) -> dict[str, dict[str, Any]]:
        if not self._novel_path.exists():
            return {}
        raw = self._novel_path.read_text(encoding="utf-8").strip()
        if not raw:
            return {}
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): v for k, v in data.items() if isinstance(v, dict)}
        return {}

    def _write_novel_map(self, data: dict[str, dict[str, Any]]) -> str:
        self._novel_path.parent.mkdir(parents=True, exist_ok=True)
        self._novel_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(self._novel_path)

    @staticmethod
    def _novel_summary_from_record(record: dict[str, Any]) -> dict[str, Any]:
        return {
            "novel_id": str(record.get("novel_id", "")),
            "novel_title": str(record.get("novel_title", "")),
            "chapter_count": int(record.get("chapter_count", 0) or 0),
            "latest_chapter_id": str(record.get("latest_chapter_id", "")),
            "latest_chapter_title": str(record.get("latest_chapter_title", "")),
            "updated_at": str(record.get("updated_at", "")),
        }

    def _upsert_novel_record(self, *, novel_id: str, novel_title: str, updated_at: str = "") -> dict[str, Any]:
        novel_map = self._read_novel_map()
        current = novel_map.get(novel_id, {})
        timestamp = updated_at or _utc_now_iso()
        record = {
            "novel_id": novel_id,
            "novel_title": str(novel_title or current.get("novel_title") or novel_id),
            "created_at": str(current.get("created_at") or timestamp),
            "updated_at": timestamp,
        }
        novel_map[novel_id] = record
        self._write_novel_map(novel_map)
        return record

    @staticmethod
    def _chapter_summary(chapter_id: str, state: dict[str, Any]) -> dict[str, Any]:
        chapter_number = _as_int(state.get("chapter_number"))
        return {
            "chapter_id": chapter_id,
            "novel_id": str(state.get("novel_id", "")),
            "novel_title": str(state.get("novel_title", "")),
            "chapter_number": chapter_number,
            "chapter_title": str(state.get("chapter_title", "")),
            "chapter_status": str(state.get("chapter_status", "")),
            "agenda_review_status": str(state.get("agenda_review_status", "pending")),
            "draft_word_count": _as_int(state.get("draft_word_count"), 0) or 0,
            "updated_at": str(state.get("updated_at", "")),
        }

    def persist_rag_recall_event(
        self,
        *,
        chapter_id: str,
        chapter_agenda: str,
        rag_recall_summary: str,
        rag_evidence: list[dict[str, Any]],
        recall_trace_id: str = "",
    ) -> tuple[str, str]:
        trace_id = recall_trace_id or f"recall-{uuid.uuid4().hex}"
        record = {
            "event_type": "rag_recall",
            "trace_id": trace_id,
            "chapter_id": chapter_id,
            "chapter_agenda": chapter_agenda,
            "rag_recall_summary": rag_recall_summary,
            "rag_evidence": rag_evidence,
            "recorded_at": _utc_now_iso(),
        }
        path = self._append_record(record)
        return trace_id, path

    def persist_human_review_event(
        self,
        *,
        chapter_id: str,
        recall_trace_id: str,
        review_trace_id: str = "",
        agenda_review_status: str,
        agenda_review_notes: str,
        approved_chapter_agenda: str,
        approved_rag_recall_summary: str,
    ) -> tuple[str, str]:
        trace_id = review_trace_id or f"review-{uuid.uuid4().hex}"
        record = {
            "event_type": "human_review",
            "trace_id": trace_id,
            "recall_trace_id": recall_trace_id,
            "chapter_id": chapter_id,
            "agenda_review_status": agenda_review_status,
            "agenda_review_notes": agenda_review_notes,
            "approved_chapter_agenda": approved_chapter_agenda,
            "approved_rag_recall_summary": approved_rag_recall_summary,
            "recorded_at": _utc_now_iso(),
        }
        path = self._append_record(record)
        return trace_id, path

    def save_chapter_state(self, *, chapter_id: str, state: dict[str, Any]) -> str:
        data = self._read_state_map()
        copied = dict(state)
        copied["chapter_id"] = chapter_id
        copied["novel_id"] = str(copied.get("novel_id") or "novel-demo-001")
        copied["novel_title"] = str(copied.get("novel_title") or copied["novel_id"])
        copied["chapter_title"] = str(copied.get("chapter_title") or chapter_id)
        copied["chapter_number"] = _as_int(copied.get("chapter_number"), 1) or 1
        copied["updated_at"] = _utc_now_iso()
        data[chapter_id] = copied
        path = self._write_state_map(data)
        self._upsert_novel_record(
            novel_id=copied["novel_id"],
            novel_title=copied["novel_title"],
            updated_at=str(copied["updated_at"]),
        )
        return path

    def get_chapter_state(self, *, chapter_id: str) -> dict[str, Any] | None:
        data = self._read_state_map()
        state = data.get(chapter_id)
        return dict(state) if state else None

    def _latest_events_by_type(self, *, chapter_id: str) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        if not self._audit_path.exists():
            return result
        for line in self._audit_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            record = json.loads(line)
            if record.get("chapter_id") != chapter_id:
                continue
            event_type = str(record.get("event_type", ""))
            if event_type:
                result[event_type] = record
        return result

    def get_review_task(self, *, chapter_id: str) -> dict[str, Any] | None:
        state = self.get_chapter_state(chapter_id=chapter_id)
        if not state:
            return None

        events = self._latest_events_by_type(chapter_id=chapter_id)
        recall_event = events.get("rag_recall", {})
        review_event = events.get("human_review", {})

        return {
            "novel_id": str(state.get("novel_id", "")),
            "novel_title": str(state.get("novel_title", "")),
            "chapter_id": chapter_id,
            "chapter_number": _as_int(state.get("chapter_number")),
            "chapter_title": str(state.get("chapter_title", "")),
            "chapter_status": str(state.get("chapter_status", "")),
            "chapter_agenda": state.get("chapter_agenda", ""),
            "rag_recall_summary": state.get("rag_recall_summary", ""),
            "rag_evidence": state.get("rag_evidence", []),
            "agenda_review_status": state.get("agenda_review_status", "pending"),
            "agenda_review_notes": state.get("agenda_review_notes", ""),
            "approved_chapter_agenda": state.get("approved_chapter_agenda", ""),
            "approved_rag_recall_summary": state.get("approved_rag_recall_summary", ""),
            "recall_trace_id": state.get("recall_trace_id", ""),
            "review_trace_id": state.get("review_trace_id", ""),
            "audit_log_path": state.get("audit_log_path", str(self._audit_path)),
            "audit_warning": state.get("audit_warning", ""),
            "latest_recall_event": recall_event,
            "latest_review_event": review_event,
            "updated_at": state.get("updated_at", ""),
        }

    def create_novel(self, *, novel_id: str, novel_title: str) -> dict[str, Any]:
        if self.get_novel(novel_id=novel_id):
            raise FileExistsError(f"novel_id already exists: {novel_id}")

        record = self._upsert_novel_record(novel_id=novel_id, novel_title=novel_title)
        return self._novel_summary_from_record(record)

    def get_novel(self, *, novel_id: str) -> dict[str, Any] | None:
        for novel in self.list_novels():
            if str(novel.get("novel_id", "")) == novel_id:
                return dict(novel)
        return None

    def list_novels(self) -> list[dict[str, Any]]:
        grouped: dict[str, dict[str, Any]] = {}
        for novel_id, record in self._read_novel_map().items():
            summary = self._novel_summary_from_record(record)
            summary["latest_chapter_updated_at"] = ""
            grouped[novel_id] = summary

        for chapter_id, state in self._read_state_map().items():
            novel_id = str(state.get("novel_id") or "novel-demo-001")
            novel_title = str(state.get("novel_title") or novel_id)
            updated_at = str(state.get("updated_at", ""))
            current = grouped.get(novel_id)
            if current is None:
                grouped[novel_id] = {
                    "novel_id": novel_id,
                    "novel_title": novel_title,
                    "chapter_count": 1,
                    "latest_chapter_id": chapter_id,
                    "latest_chapter_title": str(state.get("chapter_title", "")),
                    "latest_chapter_updated_at": updated_at,
                    "updated_at": updated_at,
                }
                continue

            current["chapter_count"] = int(current.get("chapter_count", 0)) + 1
            if not str(current.get("novel_title", "")).strip() or updated_at >= str(current.get("updated_at", "")):
                current["novel_title"] = novel_title
            if updated_at >= str(current.get("latest_chapter_updated_at", "")):
                current["latest_chapter_id"] = chapter_id
                current["latest_chapter_title"] = str(state.get("chapter_title", ""))
                current["latest_chapter_updated_at"] = updated_at
            if updated_at >= str(current.get("updated_at", "")):
                current["updated_at"] = updated_at

        novels = list(grouped.values())
        for novel in novels:
            novel.pop("latest_chapter_updated_at", None)
        novels.sort(key=lambda item: (str(item.get("updated_at", "")), str(item.get("novel_id", ""))), reverse=True)
        return novels

    def list_chapters(self, *, novel_id: str) -> list[dict[str, Any]]:
        chapters: list[dict[str, Any]] = []
        for chapter_id, state in self._read_state_map().items():
            state_novel_id = str(state.get("novel_id") or "novel-demo-001")
            if state_novel_id != novel_id:
                continue
            chapters.append(self._chapter_summary(chapter_id, state))

        chapters.sort(
            key=lambda item: (
                item.get("chapter_number") is None,
                item.get("chapter_number") if item.get("chapter_number") is not None else 0,
                str(item.get("chapter_id", "")),
            )
        )
        return chapters
