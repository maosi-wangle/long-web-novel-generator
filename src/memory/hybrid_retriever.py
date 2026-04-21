from __future__ import annotations

from pathlib import Path

import orjson

from src.config import RagSettings, get_project_paths, get_rag_settings
from src.memory.bm25_store import BM25Store
from src.memory.embedding import EmbeddingEncoder
from src.memory.faiss_store import FaissStore
from src.schemas.memory import ChunkRecord
from src.schemas.tool_io import RagHit, RagSearchRequest, RagSearchResult


class HybridRetriever:
    def __init__(
        self,
        project_id: str,
        *,
        encoder: EmbeddingEncoder | None = None,
        settings: RagSettings | None = None,
    ) -> None:
        self.project_id = project_id
        self.settings = settings or get_rag_settings()
        self.encoder = encoder or EmbeddingEncoder(self.settings)
        self.faiss_store = FaissStore(project_id)
        self.bm25_store = BM25Store(project_id)
        self.meta_path = get_project_paths(project_id).rag_meta_file

    def search(self, request: RagSearchRequest) -> RagSearchResult:
        records = self._load_records()
        if not records:
            return RagSearchResult(query=request.query, hits=[])

        allowed_chunk_ids = {
            record.chunk_id
            for record in records
            if self._record_allowed(record, request)
        }
        if not allowed_chunk_ids:
            return RagSearchResult(query=request.query, hits=[])

        search_pool = max(request.top_k * 5, 20)
        dense_hits: list[tuple[str, float]] = []
        sparse_hits: list[tuple[str, float]] = []

        if request.search_mode in {"hybrid", "dense"}:
            query_embedding = self.encoder.embed_texts([request.query])[0]
            dense_hits = [
                item for item in self.faiss_store.search(query_embedding, search_pool) if item[0] in allowed_chunk_ids
            ]

        if request.search_mode in {"hybrid", "sparse"}:
            sparse_hits = [
                item for item in self.bm25_store.search(request.query, search_pool) if item[0] in allowed_chunk_ids
            ]

        combined = self._combine_scores(dense_hits, sparse_hits, request.search_mode)
        record_map = {record.chunk_id: record for record in records}
        hits: list[RagHit] = []
        for chunk_id, score in combined[: request.top_k]:
            record = record_map.get(chunk_id)
            if record is None:
                continue
            hits.append(
                RagHit(
                    chunk_id=record.chunk_id,
                    score=round(score, 6),
                    chapter_id=record.chapter_id,
                    text=record.text,
                    summary=record.summary,
                )
            )
        return RagSearchResult(query=request.query, hits=hits)

    def _load_records(self) -> list[ChunkRecord]:
        if not self.meta_path.exists():
            return []
        records: list[ChunkRecord] = []
        for line in self.meta_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            records.append(ChunkRecord.model_validate(orjson.loads(line)))
        return records

    @staticmethod
    def _record_allowed(record: ChunkRecord, request: RagSearchRequest) -> bool:
        if request.chapter_scope is not None:
            start, end = request.chapter_scope
            if not (start <= record.chapter_id <= end):
                return False
        if request.entity_filter:
            lowered = [entity.lower() for entity in record.entities]
            for needle in request.entity_filter:
                candidate = needle.lower()
                if any(candidate in entity for entity in lowered):
                    return True
            return False
        return True

    def _combine_scores(
        self,
        dense_hits: list[tuple[str, float]],
        sparse_hits: list[tuple[str, float]],
        search_mode: str,
    ) -> list[tuple[str, float]]:
        if search_mode == "dense":
            return self._normalize_pairs(dense_hits)
        if search_mode == "sparse":
            return self._normalize_pairs(sparse_hits)

        dense_norm = dict(self._normalize_pairs(dense_hits))
        sparse_norm = dict(self._normalize_pairs(sparse_hits))
        chunk_ids = set(dense_norm) | set(sparse_norm)
        combined = []
        for chunk_id in chunk_ids:
            score = self.settings.dense_weight * dense_norm.get(chunk_id, 0.0) + self.settings.sparse_weight * sparse_norm.get(chunk_id, 0.0)
            combined.append((chunk_id, score))
        combined.sort(key=lambda item: item[1], reverse=True)
        return combined

    @staticmethod
    def _normalize_pairs(pairs: list[tuple[str, float]]) -> list[tuple[str, float]]:
        if not pairs:
            return []
        max_score = max(score for _, score in pairs)
        min_score = min(score for _, score in pairs)
        if max_score == min_score:
            normalized = [(chunk_id, 1.0 if max_score > 0 else 0.0) for chunk_id, _ in pairs]
        else:
            normalized = [(chunk_id, (score - min_score) / (max_score - min_score)) for chunk_id, score in pairs]
        normalized.sort(key=lambda item: item[1], reverse=True)
        return normalized

