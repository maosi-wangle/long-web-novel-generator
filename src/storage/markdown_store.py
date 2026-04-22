from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from src.config import DATA_ROOT, get_project_paths
from src.schemas.chapter import ChapterArtifact


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


SECTION_RE = re.compile(r"^##\s+(?P<title>.+?)\s*$", re.MULTILINE)
TITLE_RE = re.compile(r"^#\s+第\s+(?P<chapter_id>\d+)\s+章\s+(?P<title>.+?)\s*$", re.MULTILINE)
META_VALUE_RE = re.compile(r"^- (?P<key>[a-zA-Z0-9_]+): (?P<value>.+?)$", re.MULTILINE)

META_SECTION_TITLE = "元信息"
BODY_SECTION_TITLE = "正文"
SUMMARY_SECTION_TITLE = "章节摘要"
FACTS_SECTION_TITLE = "新增事实"
FORESHADOW_SECTION_TITLE = "伏笔候选"
REFERENCES_SECTION_TITLE = "引用记忆片段"
EMPTY_LIST_MARKER = "无"


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
        return self.parse_chapter_markdown(raw, chapter_id_hint=chapter_id)

    def parse_chapter_markdown(self, markdown: str, *, chapter_id_hint: int | None = None) -> ChapterArtifact:
        title_match = TITLE_RE.search(markdown)
        if title_match is None:
            chapter_label = chapter_id_hint if chapter_id_hint is not None else "unknown"
            raise RuntimeError(f"Chapter markdown {chapter_label} does not contain a valid title line.")

        sections = self._parse_sections(markdown)
        ordered_values = list(sections.values())

        body = sections.get(BODY_SECTION_TITLE)
        summary = sections.get(SUMMARY_SECTION_TITLE)
        new_facts = sections.get(FACTS_SECTION_TITLE)
        foreshadow = sections.get(FORESHADOW_SECTION_TITLE)
        references = sections.get(REFERENCES_SECTION_TITLE)

        if body is None and len(ordered_values) > 1:
            body = ordered_values[1]
        if summary is None and len(ordered_values) > 2:
            summary = ordered_values[2]
        if new_facts is None and len(ordered_values) > 3:
            new_facts = ordered_values[3]
        if foreshadow is None and len(ordered_values) > 4:
            foreshadow = ordered_values[4]
        if references is None and len(ordered_values) > 5:
            references = ordered_values[5]

        return ChapterArtifact(
            chapter_id=int(title_match.group("chapter_id")),
            title=title_match.group("title").strip(),
            markdown_body=(body or "").strip(),
            summary=(summary or "").strip(),
            new_facts=self._parse_list_section(new_facts or ""),
            foreshadow_candidates=self._parse_list_section(foreshadow or ""),
            referenced_chunks=self._parse_list_section(references or ""),
        )

    def load_chapter_versions(self, project_id: str, chapter_id: int) -> tuple[int, int]:
        raw = self.load_chapter_text(project_id, chapter_id)
        if raw is None:
            raise FileNotFoundError(f"Chapter markdown not found for chapter {chapter_id}.")

        meta_values = {match.group("key"): match.group("value").strip() for match in META_VALUE_RE.finditer(raw)}
        outline_version = int(meta_values.get("outline_version", "0"))
        detail_outline_version = int(meta_values.get("detail_outline_version", "0"))
        return outline_version, detail_outline_version

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
            f"## {META_SECTION_TITLE}\n\n"
            f"- chapter_id: {chapter.chapter_id}\n"
            f"- outline_version: {outline_version}\n"
            f"- detail_outline_version: {detail_outline_version}\n"
            f"- created_at: {utc_now_iso()}\n\n"
            f"## {BODY_SECTION_TITLE}\n\n"
            f"{chapter.markdown_body.strip()}\n\n"
            f"## {SUMMARY_SECTION_TITLE}\n\n"
            f"{chapter.summary.strip()}\n\n"
            f"## {FACTS_SECTION_TITLE}\n\n"
            f"{new_facts}\n\n"
            f"## {FORESHADOW_SECTION_TITLE}\n\n"
            f"{foreshadow_candidates}\n\n"
            f"## {REFERENCES_SECTION_TITLE}\n\n"
            f"{referenced_chunks}\n"
        )

    @staticmethod
    def _render_list(items: list[str]) -> str:
        if not items:
            return f"- {EMPTY_LIST_MARKER}"
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
            if value and value != EMPTY_LIST_MARKER:
                items.append(value)
        return items
