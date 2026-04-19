from __future__ import annotations

import os
from typing import Any

from novel_assist.stores.graph_store import GraphStore
from novel_assist.stores.jsonl_graph_store import JsonlGraphStore


class Neo4jGraphStore(GraphStore):
    """
    Neo4j-backed adapter with JSONL fallback.

    Chapter snapshots and review-task query still rely on local JSON store to
    keep the MVP self-contained and runnable without external infra.
    """

    def __init__(self) -> None:
        self._fallback = JsonlGraphStore()
        self._driver = None

        uri = os.getenv("NEO4J_URI", "").strip()
        username = os.getenv("NEO4J_USERNAME", "").strip()
        password = os.getenv("NEO4J_PASSWORD", "").strip()
        if not (uri and username and password):
            return

        try:
            from neo4j import GraphDatabase  # type: ignore

            self._driver = GraphDatabase.driver(uri, auth=(username, password))
        except Exception:
            self._driver = None

    def _write_to_neo4j(self, query: str, params: dict[str, Any]) -> None:
        if self._driver is None:
            return
        with self._driver.session() as session:
            session.run(query, params)

    def persist_rag_recall_event(
        self,
        *,
        chapter_id: str,
        chapter_agenda: str,
        rag_recall_summary: str,
        rag_evidence: list[dict[str, Any]],
        recall_trace_id: str = "",
    ) -> tuple[str, str]:
        trace_id, path = self._fallback.persist_rag_recall_event(
            chapter_id=chapter_id,
            chapter_agenda=chapter_agenda,
            rag_recall_summary=rag_recall_summary,
            rag_evidence=rag_evidence,
            recall_trace_id=recall_trace_id,
        )
        self._write_to_neo4j(
            """
            MERGE (c:Chapter {chapter_id: $chapter_id})
            MERGE (r:RecallEvent {trace_id: $trace_id})
            SET r.summary = $summary, r.agenda = $agenda, r.evidence = $evidence
            MERGE (c)-[:HAS_RECALL]->(r)
            """,
            {
                "chapter_id": chapter_id,
                "trace_id": trace_id,
                "summary": rag_recall_summary,
                "agenda": chapter_agenda,
                "evidence": rag_evidence,
            },
        )
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
        trace_id, path = self._fallback.persist_human_review_event(
            chapter_id=chapter_id,
            recall_trace_id=recall_trace_id,
            review_trace_id=review_trace_id,
            agenda_review_status=agenda_review_status,
            agenda_review_notes=agenda_review_notes,
            approved_chapter_agenda=approved_chapter_agenda,
            approved_rag_recall_summary=approved_rag_recall_summary,
        )
        self._write_to_neo4j(
            """
            MERGE (c:Chapter {chapter_id: $chapter_id})
            MERGE (r:ReviewEvent {trace_id: $trace_id})
            SET r.status = $status, r.notes = $notes,
                r.approved_agenda = $approved_agenda,
                r.approved_summary = $approved_summary
            MERGE (c)-[:HAS_REVIEW]->(r)
            WITH c, r
            MATCH (re:RecallEvent {trace_id: $recall_trace_id})
            MERGE (r)-[:BASED_ON]->(re)
            """,
            {
                "chapter_id": chapter_id,
                "trace_id": trace_id,
                "recall_trace_id": recall_trace_id,
                "status": agenda_review_status,
                "notes": agenda_review_notes,
                "approved_agenda": approved_chapter_agenda,
                "approved_summary": approved_rag_recall_summary,
            },
        )
        return trace_id, path

    def save_chapter_state(self, *, chapter_id: str, state: dict[str, Any]) -> str:
        return self._fallback.save_chapter_state(chapter_id=chapter_id, state=state)

    def get_chapter_state(self, *, chapter_id: str) -> dict[str, Any] | None:
        return self._fallback.get_chapter_state(chapter_id=chapter_id)

    def get_review_task(self, *, chapter_id: str) -> dict[str, Any] | None:
        return self._fallback.get_review_task(chapter_id=chapter_id)

    def create_novel(self, *, novel_id: str, novel_title: str) -> dict[str, Any]:
        return self._fallback.create_novel(novel_id=novel_id, novel_title=novel_title)

    def get_novel(self, *, novel_id: str) -> dict[str, Any] | None:
        return self._fallback.get_novel(novel_id=novel_id)

    def list_novels(self) -> list[dict[str, Any]]:
        return self._fallback.list_novels()

    def list_chapters(self, *, novel_id: str) -> list[dict[str, Any]]:
        return self._fallback.list_chapters(novel_id=novel_id)

    def persist_memory_items(
        self,
        *,
        novel_id: str,
        chapter_id: str,
        memory_items: list[dict[str, Any]],
    ) -> tuple[str, str]:
        trace_id, path = self._fallback.persist_memory_items(
            novel_id=novel_id,
            chapter_id=chapter_id,
            memory_items=memory_items,
        )
        for item in memory_items:
            memory_id = str(item.get("memory_id", ""))
            if not memory_id:
                continue
            self._write_to_neo4j(
                """
                MERGE (c:Chapter {chapter_id: $chapter_id})
                MERGE (m:MemoryItem {memory_id: $memory_id})
                SET m.novel_id = $novel_id,
                    m.memory_type = $memory_type,
                    m.title = $title,
                    m.content = $content,
                    m.tags = $tags,
                    m.salience = $salience
                MERGE (c)-[:HARVESTED]->(m)
                """,
                {
                    "chapter_id": chapter_id,
                    "memory_id": memory_id,
                    "novel_id": novel_id,
                    "memory_type": str(item.get("memory_type", "")),
                    "title": str(item.get("title", "")),
                    "content": str(item.get("content", "")),
                    "tags": list(item.get("tags", [])),
                    "salience": float(item.get("salience", 0.0) or 0.0),
                },
            )
        return trace_id, path

    def list_memory_items(
        self,
        *,
        novel_id: str,
        chapter_id: str | None = None,
        memory_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        return self._fallback.list_memory_items(
            novel_id=novel_id,
            chapter_id=chapter_id,
            memory_types=memory_types,
            limit=limit,
        )

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
        return self._fallback.retrieve_memory_candidates(
            novel_id=novel_id,
            query_text=query_text,
            chapter_id=chapter_id,
            entity_ids=entity_ids,
            tags=tags,
            limit=limit,
        )
