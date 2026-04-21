from __future__ import annotations

import json
from pathlib import Path

from src.config import get_project_paths


class FaissStore:
    def __init__(self, project_id: str) -> None:
        paths = get_project_paths(project_id)
        self.index_path = paths.faiss_dir / "index.faiss"
        self.mapping_path = paths.faiss_dir / "mapping.json"

    def build(self, chunk_ids: list[str], embeddings: list[list[float]]) -> None:
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.mapping_path.parent.mkdir(parents=True, exist_ok=True)
        if not chunk_ids or not embeddings:
            self._clear()
            return

        faiss = self._import_faiss()
        import numpy as np

        matrix = np.asarray(embeddings, dtype="float32")
        dim = matrix.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(matrix)
        faiss.write_index(index, str(self.index_path))
        self.mapping_path.write_text(json.dumps(chunk_ids, ensure_ascii=False, indent=2), encoding="utf-8")

    def search(self, query_embedding: list[float], top_k: int) -> list[tuple[str, float]]:
        if not self.index_path.exists() or not self.mapping_path.exists():
            return []

        faiss = self._import_faiss()
        import numpy as np

        index = faiss.read_index(str(self.index_path))
        mapping = json.loads(self.mapping_path.read_text(encoding="utf-8"))
        if not mapping:
            return []

        limit = min(max(top_k, 1), len(mapping))
        query = np.asarray([query_embedding], dtype="float32")
        scores, indices = index.search(query, limit)
        results: list[tuple[str, float]] = []
        for score, idx in zip(scores[0].tolist(), indices[0].tolist()):
            if idx < 0 or idx >= len(mapping):
                continue
            results.append((mapping[idx], float(score)))
        return results

    def _clear(self) -> None:
        if self.index_path.exists():
            self.index_path.unlink()
        if self.mapping_path.exists():
            self.mapping_path.unlink()

    @staticmethod
    def _import_faiss():
        try:
            import faiss
        except ImportError as exc:
            raise RuntimeError("faiss-cpu is not installed in the current environment.") from exc
        return faiss

