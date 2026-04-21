from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re

from src.config import DATA_ROOT, get_project_paths
from src.schemas.chapter import ChapterArtifact


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


SECTION_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)
TITLE_RE = re.compile(r"^#\s+第\s+(?P<chapter_id>\d+)\s+章\s+(?P<title>.+?)\s*$", re.MULTILINE)


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

    def load_chapter_artifact(self, project_id: str, chapter_id: int) -> ChapterArtifact:
        raw = self.load_chapter_text(project_id, chapter_id)
        if raw is None:
            raise FileNotFoundError(f"Chapter markdown not found for chapter {chapter_id}.")

        title_match = TITLE_RE.search(raw)
        if title_match is None:
            raise RuntimeError(f"Chapter markdown {chapter_id} does not contain a valid title line.")

        sections = self._parse_sections(raw)
        return ChapterArtifact(
            chapter_id=int(title_match.group("chapter_id")),
            title=title_match.group("title").strip(),
            markdown_body=sections.get("正文", "").strip(),
            summary=sections.get("章节摘要", "").strip(),
            new_facts=self._parse_list_section(sections.get("新增事实", "")),
            foreshadow_candidates=self._parse_list_section(sections.get("伏笔候选", "")),
            referenced_chunks=self._parse_list_section(sections.get("引用记忆片段", "")),
        )

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

    @staticmethod
    def _parse_sections(markdown: str) -> dict[str, str]:
        matches = list(SECTION_RE.finditer(markdown))
        sections: dict[str, str] = {}
        for index, match in enumerate(matches):
            title = match.group("title").strip()
            start = match.end()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
            sections[title] = markdown[start:end].strip()
        return sections

    @staticmethod
    def _parse_list_section(content: str) -> list[str]:
        items: list[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if not stripped.startswith("- "):
                continue
            value = stripped[2:].strip()
            if value and value != "无":
                items.append(value)
        return items
