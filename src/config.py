from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = REPO_ROOT / "data" / "projects"
ENV_FILE = REPO_ROOT / ".env"


@dataclass(frozen=True)
class ProjectPaths:
    project_id: str
    project_root: Path
    project_file: Path
    outline_file: Path
    progress_file: Path
    chapters_dir: Path
    detail_outlines_dir: Path
    reviews_dir: Path
    reviews_index_file: Path
    rag_dir: Path
    faiss_dir: Path
    bm25_dir: Path
    rag_meta_file: Path

    def ensure(self) -> None:
        self.project_root.mkdir(parents=True, exist_ok=True)
        self.chapters_dir.mkdir(parents=True, exist_ok=True)
        self.detail_outlines_dir.mkdir(parents=True, exist_ok=True)
        self.reviews_dir.mkdir(parents=True, exist_ok=True)
        self.faiss_dir.mkdir(parents=True, exist_ok=True)
        self.bm25_dir.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class LLMSettings:
    api_key: str
    base_url: str
    outline_model: str = "qwen3.5-flash"
    detail_outline_model: str = "qwen3.5-flash"
    writer_model: str = "qwen3.5-flash"


@dataclass(frozen=True)
class RagSettings:
    embedding_model: str = "shibing624/text2vec-base-chinese"
    chunk_size: int = 500
    chunk_overlap: int = 100
    dense_weight: float = 0.65
    sparse_weight: float = 0.35


def load_local_env(force: bool = False) -> None:
    if not ENV_FILE.exists():
        return

    for raw_line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if force or key not in os.environ:
            os.environ[key] = value


def get_llm_settings() -> LLMSettings:
    load_local_env()
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1").strip()
    if not api_key:
        raise RuntimeError("Missing DASHSCOPE_API_KEY. Put it in .env or environment variables.")

    return LLMSettings(
        api_key=api_key,
        base_url=base_url,
        outline_model=os.getenv("OUTLINE_MODEL", "qwen3.5-flash").strip() or "qwen3.5-flash",
        detail_outline_model=os.getenv("DETAIL_OUTLINE_MODEL", "qwen3.5-flash").strip() or "qwen3.5-flash",
        writer_model=os.getenv("WRITER_MODEL", "qwen3.5-flash").strip() or "qwen3.5-flash",
    )


def get_rag_settings() -> RagSettings:
    load_local_env()
    chunk_size = int(os.getenv("CHUNK_SIZE", "500").strip() or "500")
    chunk_overlap = int(os.getenv("CHUNK_OVERLAP", "100").strip() or "100")
    return RagSettings(
        embedding_model=os.getenv("EMBEDDING_MODEL", "shibing624/text2vec-base-chinese").strip()
        or "shibing624/text2vec-base-chinese",
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        dense_weight=float(os.getenv("DENSE_WEIGHT", "0.65").strip() or "0.65"),
        sparse_weight=float(os.getenv("SPARSE_WEIGHT", "0.35").strip() or "0.35"),
    )


def get_project_paths(project_id: str) -> ProjectPaths:
    project_root = DATA_ROOT / project_id
    rag_dir = project_root / "rag"
    return ProjectPaths(
        project_id=project_id,
        project_root=project_root,
        project_file=project_root / "project.json",
        outline_file=project_root / "outline.json",
        progress_file=project_root / "progress.json",
        chapters_dir=project_root / "chapters",
        detail_outlines_dir=project_root / "detail_outlines",
        reviews_dir=project_root / "reviews",
        reviews_index_file=project_root / "reviews" / "index.json",
        rag_dir=rag_dir,
        faiss_dir=rag_dir / "faiss",
        bm25_dir=rag_dir / "bm25",
        rag_meta_file=rag_dir / "meta.jsonl",
    )
