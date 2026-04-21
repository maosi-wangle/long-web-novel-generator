from __future__ import annotations

import json
import re

from src.config import get_project_paths
from src.schemas.memory import ChunkRecord


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def tokenize_for_bm25(text: str) -> list[str]:
    base_tokens = [token.lower() for token in TOKEN_RE.findall(text)]
    bigrams: list[str] = []
    for index in range(len(base_tokens) - 1):
        if len(base_tokens[index]) == 1 and len(base_tokens[index + 1]) == 1:
            bigrams.append(f"{base_tokens[index]}{base_tokens[index + 1]}")
    return base_tokens + bigrams


class BM25Store:
    def __init__(self, project_id: str) -> None:
        paths = get_project_paths(project_id)
        self.docs_path = paths.bm25_dir / "documents.json"

    def build(self, records: list[ChunkRecord]) -> None:
        self.docs_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "chunk_id": record.chunk_id,
                "text": record.text,
                "tokens": tokenize_for_bm25(record.text),
            }
            for record in records
        ]
        self.docs_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def search(self, query: str, top_k: int) -> list[tuple[str, float]]:
        if not self.docs_path.exists():
            return []

        payload = json.loads(self.docs_path.read_text(encoding="utf-8"))
        if not payload:
            return []

        try:
            from rank_bm25 import BM25Okapi
        except ImportError as exc:
            raise RuntimeError("rank-bm25 is not installed in the current environment.") from exc

        corpus = [item["tokens"] for item in payload]
        bm25 = BM25Okapi(corpus)
        query_tokens = tokenize_for_bm25(query)
        scores = bm25.get_scores(query_tokens)
        paired = list(zip(payload, scores.tolist() if hasattr(scores, "tolist") else list(scores)))
        paired.sort(key=lambda item: item[1], reverse=True)
        results: list[tuple[str, float]] = []
        for item, score in paired[: max(top_k, 1)]:
            results.append((item["chunk_id"], float(score)))
        return results

