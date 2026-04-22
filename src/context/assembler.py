from __future__ import annotations

from typing import Any

from src.context.budget import ContextBudgetManager
from src.orchestrator.state import ProjectState
from src.schemas.context import DetailOutlineContext, WriterContext
from src.schemas.memory import CompactRagHit
from src.schemas.outline import NovelOutline
from src.schemas.project import ProjectRecord
from src.schemas.tool_io import RagSearchResult
from src.storage.memory_store import MemoryStore
from src.schemas.chapter import DetailOutline


class ContextAssembler:
    def __init__(
        self,
        memory_store: MemoryStore | None = None,
        budget_manager: ContextBudgetManager | None = None,
    ) -> None:
        self.memory_store = memory_store or MemoryStore()
        self.budget_manager = budget_manager or ContextBudgetManager()

    def build_detail_context(
        self,
        *,
        project: ProjectRecord,
        state: ProjectState,
        outline: NovelOutline,
        current_chapter: dict[str, Any],
        current_act: dict[str, Any] | None,
        previous_chapter: dict[str, Any] | None,
        next_chapter: dict[str, Any] | None,
        rag_result: RagSearchResult,
        extra_brief: str | None = None,
    ) -> DetailOutlineContext:
        target_chapter_id = int(current_chapter.get("chapter_id", 0) or 0)
        recent_memories = self.memory_store.load_recent_chapter_memories(
            project.project_id,
            chapter_to=min(state.last_completed_chapter, target_chapter_id - 1),
            limit=3,
        )
        arc_memories = self.memory_store.load_arc_memories(
            project.project_id,
            chapter_to=min(state.last_completed_chapter, target_chapter_id - 1),
            limit=2,
        )

        context = DetailOutlineContext(
            project_meta=self._project_meta(project, extra_brief),
            current_chapter=current_chapter,
            current_act=current_act,
            previous_chapter=previous_chapter,
            next_chapter=next_chapter,
            current_progress=state.model_dump(mode="json"),
            recent_memories=recent_memories,
            arc_memories=arc_memories,
            character_state=self.memory_store.load_character_state(project.project_id),
            world_state=self.memory_store.load_world_state(project.project_id),
            open_loops=self.memory_store.load_open_loops(project.project_id).items,
            sticky_constraints=self.memory_store.load_sticky_constraints(project.project_id).items,
            rag_hits=self._compact_rag_hits(
                rag_result,
                why_relevant=f"history evidence for planning chapter {target_chapter_id}",
                limit=4,
            ),
            foreshadowing=[item.model_dump(mode="json") for item in outline.foreshadowing],
            global_constraints=outline.constraints,
            world_setting=outline.world_setting,
            core_characters=[character.model_dump(mode="json") for character in outline.characters],
        )
        return self.budget_manager.fit_detail_context(context)

    def build_writer_context(
        self,
        *,
        project: ProjectRecord,
        detail_outline: DetailOutline,
        rag_result: RagSearchResult,
        extra_brief: str | None = None,
    ) -> WriterContext:
        chapter_id = detail_outline.chapter_id
        recent_memories = self.memory_store.load_recent_chapter_memories(
            project.project_id,
            chapter_to=chapter_id - 1,
            limit=2,
        )
        arc_memories = self.memory_store.load_arc_memories(
            project.project_id,
            chapter_to=chapter_id - 1,
            limit=1,
        )
        rag_hits = self._compact_rag_hits(
            rag_result,
            why_relevant=f"history evidence for writing chapter {chapter_id}",
            limit=3,
        )

        writer_packet_payload = detail_outline.writer_packet.model_dump(mode="json")
        writer_packet_payload["retrieved_context"] = [
            f"{hit.chunk_id}: chapter_{hit.chapter_id} {hit.compressed_quote}" for hit in rag_hits
        ]

        context = WriterContext(
            project_meta=self._project_meta(project, extra_brief),
            chapter_id=detail_outline.chapter_id,
            title=detail_outline.title,
            chapter_goal=detail_outline.chapter_goal,
            writer_packet=writer_packet_payload,
            ending_hook=detail_outline.ending_hook,
            user_constraints=detail_outline.user_constraints,
            recent_memories=recent_memories,
            arc_memories=arc_memories,
            character_state=self.memory_store.load_character_state(project.project_id),
            world_state=self.memory_store.load_world_state(project.project_id),
            open_loops=self.memory_store.load_open_loops(project.project_id).items,
            sticky_constraints=self.memory_store.load_sticky_constraints(project.project_id).items,
            rag_hits=rag_hits,
        )
        return self.budget_manager.fit_writer_context(context)

    @staticmethod
    def _project_meta(project: ProjectRecord, extra_brief: str | None) -> dict[str, Any]:
        payload = {
            "project_id": project.project_id,
            "title": project.title,
            "premise": project.premise,
            "genre": project.genre,
            "tone": project.tone,
        }
        if extra_brief:
            payload["extra_brief"] = extra_brief
        return payload

    @staticmethod
    def _compact_rag_hits(
        rag_result: RagSearchResult,
        *,
        why_relevant: str,
        limit: int,
    ) -> list[CompactRagHit]:
        compacted = [
            CompactRagHit(
                chunk_id=hit.chunk_id,
                chapter_id=hit.chapter_id,
                why_relevant=why_relevant,
                compressed_quote=hit.summary.strip() or hit.text.strip()[:160],
                score=hit.score,
            )
            for hit in rag_result.hits
        ]
        return MemoryStore.compact_rag_hits(compacted, limit=limit)
