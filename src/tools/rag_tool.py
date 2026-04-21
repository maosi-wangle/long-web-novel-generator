from __future__ import annotations

from src.memory.hybrid_retriever import HybridRetriever
from src.memory.ingest import MemoryIngestor
from src.schemas.memory import RagIngestResult
from src.schemas.tool_io import RagSearchRequest, RagSearchResult


class RagTool:
    def __init__(self, project_id: str) -> None:
        self.project_id = project_id
        self.retriever = HybridRetriever(project_id)
        self.ingestor = MemoryIngestor()

    def search(self, request: RagSearchRequest) -> RagSearchResult:
        return self.retriever.search(request)

    def ingest_archived_chapter(self, chapter_id: int) -> RagIngestResult:
        return self.ingestor.ingest_archived_chapter(self.project_id, chapter_id)

    def rebuild_from_archives(self) -> list[RagIngestResult]:
        return self.ingestor.rebuild_from_archives(self.project_id)

