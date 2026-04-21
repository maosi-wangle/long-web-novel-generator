from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from src.config import DATA_ROOT, get_project_paths
from src.schemas.chapter import ChapterArtifact


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class MarkdownStore:
    def __init__(self, data_root: Path | None = None) -> None:
        self.data_root = data_root or DATA_ROOT

    def save_chapter(
        self,
        project_id: str,
        chapter: ChapterArtifact,
        outline_version: int,
        detail_outline_version: int,
    ) -> Path:
        paths = get_project_paths(project_id)
        paths.ensure()
        file_path = paths.chapters_dir / f"{chapter.chapter_id:04d}.md"
        file_path.write_text(
            self.render_chapter_markdown(
                chapter=chapter,
                outline_version=outline_version,
                detail_outline_version=detail_outline_version,
            ),
            encoding="utf-8",
        )
        return file_path

    def load_chapter_text(self, project_id: str, chapter_id: int) -> str | None:
        file_path = get_project_paths(project_id).chapters_dir / f"{chapter_id:04d}.md"
        if not file_path.exists():
            return None
        return file_path.read_text(encoding="utf-8")

    def load_recent_chapter_context(
        self,
        project_id: str,
        *,
        chapter_ids: list[int],
        max_chars_per_chapter: int = 1200,
    ) -> list[str]:
        contexts: list[str] = []
        for chapter_id in chapter_ids:
            raw = self.load_chapter_text(project_id, chapter_id)
            if not raw:
                continue
            excerpt = raw.strip()
            if len(excerpt) > max_chars_per_chapter:
                excerpt = f"{excerpt[:max_chars_per_chapter].rstrip()}..."
            contexts.append(f"chapter_{chapter_id}:\n{excerpt}")
        return contexts

    def render_chapter_markdown(
        self,
        chapter: ChapterArtifact,
        outline_version: int,
        detail_outline_version: int,
    ) -> str:
        new_facts = self._render_list(chapter.new_facts)
        foreshadow_candidates = self._render_list(chapter.foreshadow_candidates)
        referenced_chunks = self._render_list(chapter.referenced_chunks)
        return (
            f"# 第 {chapter.chapter_id} 章 {chapter.title}\n\n"
            "## 元信息\n\n"
            f"- chapter_id: {chapter.chapter_id}\n"
            f"- outline_version: {outline_version}\n"
            f"- detail_outline_version: {detail_outline_version}\n"
            f"- created_at: {utc_now_iso()}\n\n"
            "## 正文\n\n"
            f"{chapter.markdown_body.strip()}\n\n"
            "## 章节摘要\n\n"
            f"{chapter.summary.strip()}\n\n"
            "## 新增事实\n\n"
            f"{new_facts}\n\n"
            "## 伏笔候选\n\n"
            f"{foreshadow_candidates}\n\n"
            "## 引用记忆片段\n\n"
            f"{referenced_chunks}\n"
        )

    @staticmethod
    def _render_list(items: list[str]) -> str:
        if not items:
            return "- 无"
        return "\n".join(f"- {item}" for item in items)
