from __future__ import annotations

from typing import Any

from src.config import RagSettings, get_rag_settings


class EmbeddingEncoder:
    def __init__(self, settings: RagSettings | None = None) -> None:
        self.settings = settings or get_rag_settings()
        self._model: Any | None = None

    @property
    def model_name(self) -> str:
        return self.settings.embedding_model

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._load_model()
        vectors = model.encode(
            texts,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vectors.tolist()

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError("sentence-transformers is not installed in the current environment.") from exc

        self._model = SentenceTransformer(self.settings.embedding_model)
        return self._model

