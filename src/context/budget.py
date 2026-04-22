from __future__ import annotations

import json
from enum import Enum
from math import ceil
from typing import Any

from src.schemas.context import (
    BudgetBucketReport,
    BudgetStatus,
    ContextBucket,
    ContextBudgetReport,
    ContextItem,
    ContextPriority,
    DetailOutlineContext,
    WriterContext,
)
from src.schemas.memory import ArcMemory, ChapterMemory, CharacterRecord, CharacterState, WorldState


class ContextBudgetManager:
    DETAIL_TOTAL_BUDGET = 24_000
    WRITER_TOTAL_BUDGET = 16_000

    DETAIL_BUCKET_TARGETS = {
        ContextBucket.system: 3_000,
        ContextBucket.current_task: 5_000,
        ContextBucket.sticky: 3_000,
        ContextBucket.structured_memory: 7_000,
        ContextBucket.retrieval: 3_000,
    }
    WRITER_BUCKET_TARGETS = {
        ContextBucket.system: 2_500,
        ContextBucket.current_task: 5_000,
        ContextBucket.sticky: 2_500,
        ContextBucket.structured_memory: 3_000,
        ContextBucket.retrieval: 2_000,
    }

    def fit_detail_context(self, context: DetailOutlineContext) -> DetailOutlineContext:
        fitted = context.model_copy(deep=True)
        actions: list[str] = []
        used = self._estimate_tokens(fitted)

        if used > self.DETAIL_TOTAL_BUDGET:
            while len(fitted.rag_hits) > 2 and used > self.DETAIL_TOTAL_BUDGET:
                fitted.rag_hits.pop()
                actions.append("drop_low_ranked_rag_hit")
                used = self._estimate_tokens(fitted)

        if used > self.DETAIL_TOTAL_BUDGET and fitted.rag_hits:
            fitted.rag_hits = []
            actions.append("drop_all_rag_hits")
            used = self._estimate_tokens(fitted)

        if used > self.DETAIL_TOTAL_BUDGET and fitted.recent_memories:
            fitted.recent_memories = [self._compact_chapter_memory(memory, level=1) for memory in fitted.recent_memories]
            actions.append("compact_recent_memories_level_1")
            used = self._estimate_tokens(fitted)

        if used > self.DETAIL_TOTAL_BUDGET and len(fitted.recent_memories) > 2:
            fitted.recent_memories = fitted.recent_memories[-2:]
            actions.append("keep_two_recent_memories")
            used = self._estimate_tokens(fitted)

        if used > self.DETAIL_TOTAL_BUDGET and fitted.arc_memories:
            fitted.arc_memories = [self._compact_arc_memory(memory, level=1) for memory in fitted.arc_memories]
            actions.append("compact_arc_memories_level_1")
            used = self._estimate_tokens(fitted)

        if used > self.DETAIL_TOTAL_BUDGET and len(fitted.arc_memories) > 1:
            fitted.arc_memories = fitted.arc_memories[-1:]
            actions.append("keep_latest_arc_memory")
            used = self._estimate_tokens(fitted)

        if used > self.DETAIL_TOTAL_BUDGET and fitted.recent_memories:
            fitted.recent_memories = [self._compact_chapter_memory(memory, level=2) for memory in fitted.recent_memories[-1:]]
            actions.append("keep_one_compacted_recent_memory")
            used = self._estimate_tokens(fitted)

        if used > self.DETAIL_TOTAL_BUDGET:
            fitted.character_state = self._compact_character_state(fitted.character_state, level=1)
            fitted.world_state = self._compact_world_state(fitted.world_state, level=1)
            fitted.open_loops = fitted.open_loops[:6]
            actions.append("compact_state_payloads_level_1")
            used = self._estimate_tokens(fitted)

        if used > self.DETAIL_TOTAL_BUDGET:
            fitted.foreshadowing = fitted.foreshadowing[:8]
            fitted.core_characters = fitted.core_characters[:8]
            fitted.global_constraints = fitted.global_constraints[:8]
            fitted.world_setting = dict(list(fitted.world_setting.items())[:8])
            actions.append("trim_outline_side_context")
            used = self._estimate_tokens(fitted)

        fitted.budget_report = self._build_detail_report(fitted, actions)
        return fitted

    def fit_writer_context(self, context: WriterContext) -> WriterContext:
        fitted = context.model_copy(deep=True)
        actions: list[str] = []
        used = self._estimate_tokens(fitted)

        if used > self.WRITER_TOTAL_BUDGET:
            while len(fitted.rag_hits) > 2 and used > self.WRITER_TOTAL_BUDGET:
                fitted.rag_hits.pop()
                actions.append("drop_low_ranked_rag_hit")
                used = self._estimate_tokens(fitted)

        if used > self.WRITER_TOTAL_BUDGET and fitted.rag_hits:
            fitted.rag_hits = []
            writer_packet = dict(fitted.writer_packet)
            writer_packet["retrieved_context"] = []
            fitted.writer_packet = writer_packet
            actions.append("drop_all_rag_hits")
            used = self._estimate_tokens(fitted)

        if used > self.WRITER_TOTAL_BUDGET and fitted.recent_memories:
            fitted.recent_memories = [self._compact_chapter_memory(memory, level=1) for memory in fitted.recent_memories]
            actions.append("compact_recent_memories_level_1")
            used = self._estimate_tokens(fitted)

        if used > self.WRITER_TOTAL_BUDGET and len(fitted.recent_memories) > 2:
            fitted.recent_memories = fitted.recent_memories[-2:]
            actions.append("keep_two_recent_memories")
            used = self._estimate_tokens(fitted)

        if used > self.WRITER_TOTAL_BUDGET and fitted.arc_memories:
            fitted.arc_memories = [self._compact_arc_memory(memory, level=1) for memory in fitted.arc_memories[-1:]]
            actions.append("keep_latest_compacted_arc_memory")
            used = self._estimate_tokens(fitted)

        if used > self.WRITER_TOTAL_BUDGET:
            fitted.character_state = self._compact_character_state(fitted.character_state, level=1)
            fitted.world_state = self._compact_world_state(fitted.world_state, level=1)
            fitted.open_loops = fitted.open_loops[:5]
            actions.append("compact_state_payloads_level_1")
            used = self._estimate_tokens(fitted)

        if used > self.WRITER_TOTAL_BUDGET and fitted.recent_memories:
            fitted.recent_memories = [self._compact_chapter_memory(memory, level=2) for memory in fitted.recent_memories[-1:]]
            actions.append("keep_one_compacted_recent_memory")

        fitted.budget_report = self._build_writer_report(fitted, actions)
        return fitted

    def _build_detail_report(
        self,
        context: DetailOutlineContext,
        actions: list[str],
    ) -> ContextBudgetReport:
        payloads = {
            ContextBucket.system: None,
            ContextBucket.current_task: {
                "project_meta": context.project_meta,
                "current_chapter": context.current_chapter,
                "current_act": context.current_act,
                "previous_chapter": context.previous_chapter,
                "next_chapter": context.next_chapter,
                "current_progress": context.current_progress,
                "foreshadowing": context.foreshadowing,
                "global_constraints": context.global_constraints,
                "world_setting": context.world_setting,
                "core_characters": context.core_characters,
            },
            ContextBucket.sticky: context.sticky_constraints,
            ContextBucket.structured_memory: {
                "recent_memories": context.recent_memories,
                "arc_memories": context.arc_memories,
                "character_state": context.character_state,
                "world_state": context.world_state,
                "open_loops": context.open_loops,
            },
            ContextBucket.retrieval: context.rag_hits,
        }
        return self._build_report(
            total_budget=self.DETAIL_TOTAL_BUDGET,
            targets=self.DETAIL_BUCKET_TARGETS,
            payloads=payloads,
            actions=actions,
        )

    def _build_writer_report(
        self,
        context: WriterContext,
        actions: list[str],
    ) -> ContextBudgetReport:
        payloads = {
            ContextBucket.system: None,
            ContextBucket.current_task: {
                "project_meta": context.project_meta,
                "chapter_id": context.chapter_id,
                "title": context.title,
                "chapter_goal": context.chapter_goal,
                "writer_packet": context.writer_packet,
                "ending_hook": context.ending_hook,
                "user_constraints": context.user_constraints,
            },
            ContextBucket.sticky: context.sticky_constraints,
            ContextBucket.structured_memory: {
                "recent_memories": context.recent_memories,
                "arc_memories": context.arc_memories,
                "character_state": context.character_state,
                "world_state": context.world_state,
                "open_loops": context.open_loops,
            },
            ContextBucket.retrieval: context.rag_hits,
        }
        return self._build_report(
            total_budget=self.WRITER_TOTAL_BUDGET,
            targets=self.WRITER_BUCKET_TARGETS,
            payloads=payloads,
            actions=actions,
        )

    def _build_report(
        self,
        *,
        total_budget: int,
        targets: dict[ContextBucket, int],
        payloads: dict[ContextBucket, Any],
        actions: list[str],
    ) -> ContextBudgetReport:
        bucket_reports: list[BudgetBucketReport] = []
        items: list[ContextItem] = []
        used_tokens = 0

        for bucket, payload in payloads.items():
            bucket_tokens = self._estimate_tokens(payload)
            used_tokens += bucket_tokens
            item_count = len(payload) if isinstance(payload, list) else int(payload is not None)
            bucket_reports.append(
                BudgetBucketReport(
                    bucket=bucket,
                    target_tokens=targets[bucket],
                    used_tokens=bucket_tokens,
                    item_count=item_count,
                )
            )
            if payload is None:
                continue
            items.append(
                ContextItem(
                    source=bucket.value,
                    bucket=bucket,
                    priority=self._priority_for_bucket(bucket),
                    token_estimate=bucket_tokens,
                    compressible=bucket != ContextBucket.system,
                    droppable=bucket == ContextBucket.retrieval,
                    included=True,
                    compression_level=1 if any(bucket.value in action for action in actions) else 0,
                )
            )

        return ContextBudgetReport(
            total_budget=total_budget,
            used_tokens=used_tokens,
            status=self._status_for_usage(used_tokens, total_budget),
            buckets=bucket_reports,
            applied_actions=actions,
            items=items,
        )

    @staticmethod
    def _priority_for_bucket(bucket: ContextBucket) -> ContextPriority:
        if bucket == ContextBucket.system:
            return ContextPriority.p0
        if bucket == ContextBucket.current_task:
            return ContextPriority.p0
        if bucket == ContextBucket.sticky:
            return ContextPriority.p1
        if bucket == ContextBucket.structured_memory:
            return ContextPriority.p3
        return ContextPriority.p4

    @staticmethod
    def _status_for_usage(used_tokens: int, total_budget: int) -> BudgetStatus:
        ratio = used_tokens / max(total_budget, 1)
        if ratio >= 0.9:
            return BudgetStatus.critical
        if ratio >= 0.75:
            return BudgetStatus.warning
        return BudgetStatus.normal

    @staticmethod
    def _estimate_tokens(payload: Any) -> int:
        if payload is None:
            return 0
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump(mode="json")
        serialized = json.dumps(payload, ensure_ascii=False, default=ContextBudgetManager._json_default)
        return max(1, ceil(len(serialized) / 2))

    @staticmethod
    def _json_default(value: Any) -> Any:
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        if isinstance(value, Enum):
            return value.value
        raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")

    @staticmethod
    def _compact_chapter_memory(memory: ChapterMemory, *, level: int) -> ChapterMemory:
        compacted = memory.model_copy(deep=True)
        if level >= 1:
            compacted.key_events = compacted.key_events[:3]
            compacted.new_facts = compacted.new_facts[:3]
            compacted.character_state_updates = compacted.character_state_updates[:2]
            compacted.relationship_updates = compacted.relationship_updates[:2]
            compacted.world_state_updates = compacted.world_state_updates[:2]
            compacted.timeline_markers = compacted.timeline_markers[:2]
            compacted.locations_visited = compacted.locations_visited[:2]
            compacted.foreshadowing_opened = compacted.foreshadowing_opened[:2]
            compacted.foreshadowing_progressed = compacted.foreshadowing_progressed[:2]
            compacted.foreshadowing_closed = compacted.foreshadowing_closed[:2]
            compacted.unresolved_conflicts = compacted.unresolved_conflicts[:2]
            compacted.important_quotes_or_rules = compacted.important_quotes_or_rules[:1]
        if level >= 2:
            compacted.key_events = compacted.key_events[:1]
            compacted.new_facts = compacted.new_facts[:2]
            compacted.character_state_updates = compacted.character_state_updates[:1]
            compacted.relationship_updates = []
            compacted.world_state_updates = []
            compacted.timeline_markers = compacted.timeline_markers[:1]
            compacted.locations_visited = []
            compacted.foreshadowing_opened = compacted.foreshadowing_opened[:1]
            compacted.foreshadowing_progressed = compacted.foreshadowing_progressed[:1]
            compacted.foreshadowing_closed = compacted.foreshadowing_closed[:1]
            compacted.unresolved_conflicts = compacted.unresolved_conflicts[:1]
            compacted.important_quotes_or_rules = []
        return compacted

    @staticmethod
    def _compact_arc_memory(memory: ArcMemory, *, level: int) -> ArcMemory:
        compacted = memory.model_copy(deep=True)
        if level >= 1:
            compacted.must_remember = compacted.must_remember[:4]
            compacted.open_foreshadowing_ids = compacted.open_foreshadowing_ids[:4]
            compacted.major_character_changes = compacted.major_character_changes[:3]
            compacted.major_relationship_changes = compacted.major_relationship_changes[:3]
            compacted.major_world_changes = compacted.major_world_changes[:3]
            compacted.open_conflicts = compacted.open_conflicts[:3]
        return compacted

    @staticmethod
    def _compact_character_state(state: CharacterState, *, level: int) -> CharacterState:
        compacted = state.model_copy(deep=True)
        max_characters = 8 if level == 1 else 5
        compacted.characters = [ContextBudgetManager._compact_character_record(item, level=level) for item in compacted.characters[:max_characters]]
        return compacted

    @staticmethod
    def _compact_character_record(record: CharacterRecord, *, level: int) -> CharacterRecord:
        compacted = record.model_copy(deep=True)
        status_items = list(compacted.current_status.items())
        keep_fields = 5 if level == 1 else 3
        compacted.current_status = dict(status_items[:keep_fields])
        compacted.active_flags = compacted.active_flags[:3]
        compacted.temporary_status = compacted.temporary_status[:2]
        return compacted

    @staticmethod
    def _compact_world_state(state: WorldState, *, level: int) -> WorldState:
        compacted = state.model_copy(deep=True)
        compacted.facts = compacted.facts[: (6 if level == 1 else 4)]
        compacted.active_conflicts = compacted.active_conflicts[: (4 if level == 1 else 3)]
        compacted.active_locations = compacted.active_locations[: (4 if level == 1 else 3)]
        return compacted
