from __future__ import annotations

import re
from pathlib import Path

import orjson

from src.config import RagSettings, get_project_paths, get_rag_settings
from src.memory.bm25_store import BM25Store
from src.memory.chunker import TextChunker
from src.memory.embedding import EmbeddingEncoder
from src.memory.faiss_store import FaissStore
from src.schemas.memory import ChunkRecord, RagIngestResult


SECTION_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)


class MemoryIngestor:
    """Rebuilds project-level RAG artifacts from archived chapter markdown."""

    def __init__(
        self,
        *,
        settings: RagSettings | None = None,
        encoder: EmbeddingEncoder | None = None,
    ) -> None:
        self.settings = settings or get_rag_settings()
        self.encoder = encoder or EmbeddingEncoder(self.settings)
        self.chunker = TextChunker(self.settings)

    def ingest_archived_chapter(self, project_id: str, chapter_id: int) -> RagIngestResult:
        chapter_path = get_project_paths(project_id).chapters_dir / f"{chapter_id:04d}.md"
        if not chapter_path.exists():
            raise FileNotFoundError(f"Archived chapter markdown not found: {chapter_path}")

        markdown = chapter_path.read_text(encoding="utf-8")
        sections = self._parse_markdown_sections(markdown)
        body = sections.get("正文", "").strip()
        if not body:
            raise RuntimeError(f"Chapter markdown {chapter_path} does not contain a '正文' section.")

        records = self.chunker.chunk_text(
            project_id=project_id,
            chapter_id=chapter_id,
            text=body,
            source_file=str(Path("chapters") / chapter_path.name),
        )

        all_records = [record for record in self._load_records(project_id) if record.chapter_id != chapter_id]
        all_records.extend(records)
        all_records.sort(key=lambda item: (item.chapter_id, item.chunk_id))
        self._write_records(project_id, all_records)

        embeddings = self.encoder.embed_texts([record.text for record in all_records]) if all_records else []
        FaissStore(project_id).build([record.chunk_id for record in all_records], embeddings)
        BM25Store(project_id).build(all_records)

        return RagIngestResult(
            project_id=project_id,
            chapter_id=chapter_id,
            chunk_count=len(records),
            total_indexed_chunks=len(all_records),
            embedding_model=self.encoder.model_name,
        )

    def rebuild_from_archives(self, project_id: str) -> list[RagIngestResult]:
        chapter_files = sorted(get_project_paths(project_id).chapters_dir.glob("*.md"))
        results: list[RagIngestResult] = []
        for chapter_file in chapter_files:
            chapter_id = int(chapter_file.stem)
            results.append(self.ingest_archived_chapter(project_id, chapter_id))
        return results

    @staticmethod
    def _parse_markdown_sections(markdown: str) -> dict[str, str]:
        matches = list(SECTION_RE.finditer(markdown))
        sections: dict[str, str] = {}
        for index, match in enumerate(matches):
            title = match.group("title").strip()
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
            sections[title] = markdown[start:end].strip()
        return sections

    @staticmethod
    def _load_records(project_id: str) -> list[ChunkRecord]:
        meta_path = get_project_paths(project_id).rag_meta_file
        if not meta_path.exists():
            return []
        records: list[ChunkRecord] = []
        for line in meta_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            records.append(ChunkRecord.model_validate(orjson.loads(line)))
        return records

    @staticmethod
    def _write_records(project_id: str, records: list[ChunkRecord]) -> None:
        meta_path = get_project_paths(project_id).rag_meta_file
        meta_path.parent.mkdir(parents=True, exist_ok=True)
        if not records:
            meta_path.write_text("", encoding="utf-8")
            return
        payload = "\n".join(orjson.dumps(record.model_dump(mode="json")).decode("utf-8") for record in records)
        meta_path.write_text(payload + "\n", encoding="utf-8")

