from __future__ import annotations

import re

from src.config import RagSettings, get_rag_settings
from src.schemas.memory import ChunkRecord


SECTION_SPLIT_RE = re.compile(r"\n\s*\n+")
ENTITY_RE = re.compile(r"[\u4e00-\u9fff]{2,8}|[A-Za-z][A-Za-z0-9_]{1,31}")


class TextChunker:
    def __init__(self, settings: RagSettings | None = None) -> None:
        self.settings = settings or get_rag_settings()

    def chunk_text(
        self,
        *,
        project_id: str,
        chapter_id: int,
        text: str,
        source_file: str,
    ) -> list[ChunkRecord]:
        normalized = self._normalize_text(text)
        if not normalized:
            return []

        raw_chunks = self._slice_text(normalized)
        records: list[ChunkRecord] = []
        for index, (char_start, char_end, chunk_text) in enumerate(raw_chunks, start=1):
            records.append(
                ChunkRecord(
                    chunk_id=f"{chapter_id:04d}_{index:02d}",
                    project_id=project_id,
                    chapter_id=chapter_id,
                    source_file=source_file,
                    text=chunk_text,
                    summary=self._make_summary(chunk_text),
                    char_start=char_start,
                    char_end=char_end,
                    entities=self._extract_entities(chunk_text),
                )
            )
        return records

    def _slice_text(self, text: str) -> list[tuple[int, int, str]]:
        chunk_size = self.settings.chunk_size
        overlap = self.settings.chunk_overlap
        step = max(1, chunk_size - overlap)
        total = len(text)
        chunks: list[tuple[int, int, str]] = []
        start = 0
        while start < total:
            end = min(total, start + chunk_size)
            chunk = text[start:end].strip()
            if chunk:
                chunks.append((start, end, chunk))
            if end >= total:
                break
            start += step
        return chunks

    @staticmethod
    def _normalize_text(text: str) -> str:
        parts = [part.strip() for part in SECTION_SPLIT_RE.split(text.replace("\r\n", "\n")) if part.strip()]
        return "\n\n".join(parts).strip()

    @staticmethod
    def _make_summary(text: str, limit: int = 80) -> str:
        normalized = text.replace("\n", " ").strip()
        if len(normalized) <= limit:
            return normalized
        return f"{normalized[:limit].rstrip()}..."

    @staticmethod
    def _extract_entities(text: str, limit: int = 20) -> list[str]:
        entities: list[str] = []
        seen: set[str] = set()
        for match in ENTITY_RE.findall(text):
            token = match.strip()
            if len(token) < 2:
                continue
            if token in seen:
                continue
            seen.add(token)
            entities.append(token)
            if len(entities) >= limit:
                break
        return entities

