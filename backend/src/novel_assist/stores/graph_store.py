from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class GraphStore(ABC):
    """Storage abstraction for recall evidence and review traceability."""

    @abstractmethod
    def persist_rag_recall_event(
        self,
        *,
        chapter_id: str,
        chapter_agenda: str,
        rag_recall_summary: str,
        rag_evidence: list[dict[str, Any]],
        recall_trace_id: str = "",
    ) -> tuple[str, str]:
        raise NotImplementedError

    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    def persist_memory_items(
        self,
        *,
        novel_id: str,
        chapter_id: str,
        memory_items: list[dict[str, Any]],
    ) -> tuple[str, str]:
        raise NotImplementedError

    @abstractmethod
    def list_memory_items(
        self,
        *,
        novel_id: str,
        chapter_id: str | None = None,
        memory_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def retrieve_memory_candidates(
        self,
        *,
        novel_id: str,
        query_text: str,
        chapter_id: str = "",
        entity_ids: list[str] | None = None,
        tags: list[str] | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def save_chapter_state(self, *, chapter_id: str, state: dict[str, Any]) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_chapter_state(self, *, chapter_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def get_review_task(self, *, chapter_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def create_novel(self, *, novel_id: str, novel_title: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def get_novel(self, *, novel_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def list_novels(self) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def list_chapters(self, *, novel_id: str) -> list[dict[str, Any]]:
        raise NotImplementedError
