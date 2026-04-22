from __future__ import annotations

from pathlib import Path

import orjson

from src.config import get_project_paths
from src.schemas.memory import (
    ArcMemory,
    ChapterMemory,
    CharacterState,
    CompactRagHit,
    ForeshadowingMemory,
    OpenLoopState,
    StickyConstraintState,
    TimelineState,
    WorldState,
)
from src.storage.markdown_store import MarkdownStore


class MemoryStore:
    def __init__(self, markdown_store: MarkdownStore | None = None) -> None:
        self.markdown_store = markdown_store or MarkdownStore()

    def load_recent_chapter_memories(
        self,
        project_id: str,
        *,
        chapter_to: int,
        limit: int = 3,
    ) -> list[ChapterMemory]:
        if chapter_to <= 0 or limit <= 0:
            return []

        chapter_ids = list(range(max(1, chapter_to - limit + 1), chapter_to + 1))
        memories: list[ChapterMemory] = []
        for chapter_id in chapter_ids:
            path = self._chapter_memory_path(project_id, chapter_id)
            if path.exists():
                memories.append(ChapterMemory.model_validate(orjson.loads(path.read_bytes())))
                continue
            memories.append(self._fallback_chapter_memory(project_id, chapter_id))
        return memories

    def load_arc_memories(
        self,
        project_id: str,
        *,
        chapter_to: int,
        limit: int = 2,
    ) -> list[ArcMemory]:
        if chapter_to <= 0 or limit <= 0:
            return []

        memories: list[ArcMemory] = []
        arc_dir = self._arc_memory_dir(project_id)
        if not arc_dir.exists():
            return memories

        for path in sorted(arc_dir.glob("*.json")):
            memory = ArcMemory.model_validate(orjson.loads(path.read_bytes()))
            if memory.chapter_range[1] <= chapter_to:
                memories.append(memory)
        return memories[-limit:]

    def load_character_state(self, project_id: str) -> CharacterState:
        return self._load_state_file(project_id, "character_state.json", CharacterState)

    def load_world_state(self, project_id: str) -> WorldState:
        return self._load_state_file(project_id, "world_state.json", WorldState)

    def load_open_loops(self, project_id: str) -> OpenLoopState:
        return self._load_state_file(project_id, "open_loops.json", OpenLoopState)

    def load_timeline(self, project_id: str) -> TimelineState:
        return self._load_state_file(project_id, "timeline.json", TimelineState)

    def load_sticky_constraints(self, project_id: str) -> StickyConstraintState:
        return self._load_state_file(project_id, "sticky_constraints.json", StickyConstraintState)

    @staticmethod
    def compact_rag_hits(
        rag_hits: list[CompactRagHit],
        *,
        limit: int,
    ) -> list[CompactRagHit]:
        if limit <= 0:
            return []
        return sorted(rag_hits, key=lambda item: item.score, reverse=True)[:limit]

    def _load_state_file(self, project_id: str, filename: str, model_type):
        path = self._state_dir(project_id) / filename
        if not path.exists():
            return model_type()
        return model_type.model_validate(orjson.loads(path.read_bytes()))

    def _fallback_chapter_memory(self, project_id: str, chapter_id: int) -> ChapterMemory:
        artifact = self.markdown_store.load_chapter_artifact(project_id, chapter_id)
        summary = artifact.summary.strip() or artifact.markdown_body.strip()[:120]
        key_events = [summary] if summary else []
        foreshadowing = [
            ForeshadowingMemory(
                id=f"fh_{chapter_id:04d}_{index}",
                summary=item,
            )
            for index, item in enumerate(artifact.foreshadow_candidates, start=1)
        ]
        quote_candidates = [artifact.markdown_body.strip()[:100]] if artifact.markdown_body.strip() else []
        return ChapterMemory(
            chapter_id=artifact.chapter_id,
            title=artifact.title,
            one_line_summary=summary or f"Chapter {artifact.chapter_id} summary unavailable.",
            key_events=key_events,
            new_facts=artifact.new_facts,
            foreshadowing_opened=foreshadowing,
            important_quotes_or_rules=quote_candidates,
        )

    @staticmethod
    def _chapter_memory_path(project_id: str, chapter_id: int) -> Path:
        return MemoryStore._chapter_memory_dir(project_id) / f"{chapter_id:04d}.json"

    @staticmethod
    def _chapter_memory_dir(project_id: str) -> Path:
        return get_project_paths(project_id).project_root / "chapter_memory"

    @staticmethod
    def _arc_memory_dir(project_id: str) -> Path:
        return get_project_paths(project_id).project_root / "arc_memory"

    @staticmethod
    def _state_dir(project_id: str) -> Path:
        return get_project_paths(project_id).project_root / "state"
