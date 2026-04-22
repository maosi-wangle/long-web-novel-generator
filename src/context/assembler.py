from __future__ import annotations

import re
from typing import Any

from src.context.budget import ContextBudgetManager
from src.orchestrator.state import ProjectState
from src.schemas.context import DetailOutlineContext, WriterContext
from src.schemas.memory import ArcMemory, ChapterMemory, CharacterState, CompactRagHit, OpenLoopItem, StickyConstraint, WorldState
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
        character_state = self.memory_store.load_character_state(project.project_id)
        world_state = self.memory_store.load_world_state(project.project_id)
        open_loops = self.memory_store.load_open_loops(project.project_id).items
        sticky_constraints = self.memory_store.load_sticky_constraints(project.project_id).items
        story_facts = self._build_story_facts(
            recent_memories=recent_memories,
            arc_memories=arc_memories,
            rag_hits=rag_hits,
            continuity_notes=detail_outline.writer_packet.continuity_notes,
        )
        sanitized_story_facts = self._sanitize_text_list(story_facts)

        writer_packet_payload = self._sanitize_writer_payload(detail_outline.writer_packet.model_dump(mode="json"))
        writer_packet_payload["retrieved_context"] = sanitized_story_facts[:8]

        context = WriterContext(
            project_meta=self._project_meta(project, extra_brief),
            chapter_id=detail_outline.chapter_id,
            title=detail_outline.title,
            chapter_goal=detail_outline.chapter_goal,
            writer_packet=writer_packet_payload,
            ending_hook=detail_outline.ending_hook,
            user_constraints=self._sanitize_text_list(detail_outline.user_constraints),
            story_facts=sanitized_story_facts,
            character_snapshot=self._sanitize_text_list(self._character_snapshot(character_state)),
            world_snapshot=self._sanitize_text_list(self._world_snapshot(world_state)),
            active_threads=self._sanitize_text_list(self._active_threads(open_loops)),
            style_rules=self._sanitize_text_list(self._writer_style_rules(sticky_constraints)),
            source_chunk_ids=[hit.chunk_id for hit in rag_hits],
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

    @staticmethod
    def _build_story_facts(
        *,
        recent_memories: list[ChapterMemory],
        arc_memories: list[ArcMemory],
        rag_hits: list[CompactRagHit],
        continuity_notes: list[str],
    ) -> list[str]:
        facts: list[str] = []

        for memory in recent_memories:
            facts.extend(ContextAssembler._unique_nonempty([memory.one_line_summary]))
            facts.extend(ContextAssembler._unique_nonempty(memory.key_events[:2]))
            facts.extend(ContextAssembler._unique_nonempty(memory.new_facts[:2]))
            facts.extend(ContextAssembler._unique_nonempty(memory.unresolved_conflicts[:1]))
            facts.extend(
                ContextAssembler._unique_nonempty([item.summary for item in memory.foreshadowing_opened[:1]])
            )

        for memory in arc_memories:
            facts.extend(ContextAssembler._unique_nonempty(memory.must_remember[:3]))
            facts.extend(ContextAssembler._unique_nonempty(memory.major_character_changes[:2]))
            facts.extend(ContextAssembler._unique_nonempty(memory.open_conflicts[:2]))

        facts.extend(ContextAssembler._unique_nonempty(continuity_notes[:3]))
        facts.extend(ContextAssembler._unique_nonempty([hit.compressed_quote for hit in rag_hits]))
        return ContextAssembler._dedupe_preserve_order(facts)[:14]

    @staticmethod
    def _character_snapshot(state: CharacterState) -> list[str]:
        snapshot: list[str] = []
        for character in state.characters[:8]:
            pieces = [f"{key}: {value}" for key, value in list(character.current_status.items())[:4] if value]
            pieces.extend(flag for flag in character.active_flags[:2] if flag)
            snapshot.extend(ContextAssembler._unique_nonempty([f"{character.name}: {'; '.join(pieces)}" if pieces else character.name]))
        return ContextAssembler._dedupe_preserve_order(snapshot)[:8]

    @staticmethod
    def _world_snapshot(state: WorldState) -> list[str]:
        facts = list(state.facts[:4])
        facts.extend(state.active_conflicts[:3])
        facts.extend(state.active_locations[:3])
        return ContextAssembler._dedupe_preserve_order(ContextAssembler._unique_nonempty(facts))[:8]

    @staticmethod
    def _active_threads(items: list[OpenLoopItem]) -> list[str]:
        threads = []
        for item in items[:8]:
            if item.status != "closed":
                threads.append(item.summary)
        return ContextAssembler._dedupe_preserve_order(ContextAssembler._unique_nonempty(threads))[:8]

    @staticmethod
    def _writer_style_rules(items: list[StickyConstraint]) -> list[str]:
        return ContextAssembler._dedupe_preserve_order(
            ContextAssembler._unique_nonempty([item.instruction for item in items if item.active][:6])
        )[:6]

    @staticmethod
    def _unique_nonempty(items: list[str]) -> list[str]:
        return [item.strip() for item in items if item and item.strip()]

    @staticmethod
    def _dedupe_preserve_order(items: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            ordered.append(item)
        return ordered

    @staticmethod
    def _sanitize_writer_payload(payload: dict[str, Any]) -> dict[str, Any]:
        return ContextAssembler._sanitize_nested_value(payload)

    @staticmethod
    def _sanitize_nested_value(value: Any):
        if isinstance(value, str):
            return ContextAssembler._sanitize_text(value)
        if isinstance(value, list):
            return [ContextAssembler._sanitize_nested_value(item) for item in value]
        if isinstance(value, dict):
            return {key: ContextAssembler._sanitize_nested_value(item) for key, item in value.items()}
        return value

    @staticmethod
    def _sanitize_text_list(items: list[str]) -> list[str]:
        return ContextAssembler._dedupe_preserve_order(
            ContextAssembler._unique_nonempty([ContextAssembler._sanitize_text(item) for item in items])
        )

    @staticmethod
    def _sanitize_text(text: str) -> str:
        sanitized = re.sub(r"第\s*[0-9一二三四五六七八九十百千]+\s*章", "此前", text)
        sanitized = re.sub(r"\b[Cc]hapter\s+\d+\b", "earlier", sanitized)
        sanitized = re.sub(r"上\s*一\s*章", "此前", sanitized)
        sanitized = re.sub(r"前\s*文", "此前", sanitized)
        sanitized = re.sub(r"后\s*文", "后续发展", sanitized)
        sanitized = re.sub(r"本\s*章", "当前这段经历", sanitized)
        sanitized = re.sub(r"章\s*节", "这段经历", sanitized)
        sanitized = sanitized.replace("结尾", "收束处")
        return sanitized.strip()
