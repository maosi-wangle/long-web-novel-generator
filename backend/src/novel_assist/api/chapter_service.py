from __future__ import annotations

from typing import Any

from novel_assist.cli.run_stage2 import build_initial_state
from novel_assist.nodes.critic_reviewer import critic_node
from novel_assist.nodes.draft_writer import draft_writer_node
from novel_assist.nodes.human_review_gate import human_agenda_review_gate
from novel_assist.nodes.memory_harvester import memory_harvester_node
from novel_assist.nodes.plot_planner import plotting_node
from novel_assist.nodes.rag_recall import rag_recall_node
from novel_assist.state.routing import route_after_critic
from novel_assist.stores.factory import get_graph_store


class ChapterService:
    """Application service for chapter planning, review, draft generation, and chapter browsing."""

    def __init__(self) -> None:
        self._store = get_graph_store()

    @staticmethod
    def _coerce_metadata(state: dict[str, Any], *, chapter_id: str) -> None:
        state["novel_id"] = str(state.get("novel_id") or "novel-demo-001")
        state["novel_title"] = str(state.get("novel_title") or state["novel_id"])
        state["chapter_id"] = chapter_id
        state["chapter_title"] = str(state.get("chapter_title") or chapter_id)
        state["chapter_number"] = int(state.get("chapter_number") or 1)

    @staticmethod
    def _default_chapter_title(chapter_number: int) -> str:
        return f"第{chapter_number}章"

    def _find_previous_chapter_state(self, *, novel_id: str, chapter_number: int) -> dict[str, Any] | None:
        if chapter_number <= 1:
            return None

        previous_candidates = [
            item
            for item in self._store.list_chapters(novel_id=novel_id)
            if isinstance(item.get("chapter_number"), int) and int(item["chapter_number"]) < chapter_number
        ]
        if not previous_candidates:
            return None

        previous_summary = previous_candidates[-1]
        previous_chapter_id = str(previous_summary.get("chapter_id", ""))
        if not previous_chapter_id:
            return None
        return self._store.get_chapter_state(chapter_id=previous_chapter_id)

    @staticmethod
    def _ending_for_next_chapter(previous_state: dict[str, Any]) -> str:
        draft = str(previous_state.get("draft", ""))
        if draft:
            return draft[-200:]
        return str(previous_state.get("previous_chapter_ending", ""))

    def _inherit_previous_chapter_context(self, *, state: dict[str, Any], overrides: dict[str, Any]) -> None:
        previous_state = self._find_previous_chapter_state(
            novel_id=str(state.get("novel_id", "")),
            chapter_number=int(state.get("chapter_number", 1) or 1),
        )
        if not previous_state:
            if overrides.get("chapter_title") is None:
                state["chapter_title"] = self._default_chapter_title(int(state.get("chapter_number", 1) or 1))
            return

        inherited_values = {
            "novel_title": str(previous_state.get("novel_title", "")),
            "global_outline": str(previous_state.get("global_outline", "")),
            "current_arc": str(previous_state.get("current_arc", "")),
            "memory_l0": str(previous_state.get("memory_l0", "")),
            "previous_chapter_ending": self._ending_for_next_chapter(previous_state),
            "world_rules": str(previous_state.get("world_rules", "")),
            "future_waypoints": str(previous_state.get("future_waypoints", "")),
            "guidance_from_future": str(previous_state.get("guidance_from_future", "")),
        }

        for key, value in inherited_values.items():
            if overrides.get(key) is None and value:
                state[key] = value

        if overrides.get("chapter_title") is None:
            state["chapter_title"] = self._default_chapter_title(int(state.get("chapter_number", 1) or 1))

    def generate_plan(self, *, chapter_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
        state = build_initial_state()
        for key, value in overrides.items():
            if value is not None:
                state[key] = value

        self._coerce_metadata(state, chapter_id=chapter_id)
        self._inherit_previous_chapter_context(state=state, overrides=overrides)
        state.update(
            {
                "agenda_review_status": "pending",
                "agenda_review_notes": "",
                "approved_chapter_agenda": "",
                "approved_rag_recall_summary": "",
                "chapter_status": "review_pending",
                "error": "",
            }
        )

        state.update(plotting_node(state))
        state.update(rag_recall_node(state))
        state["error"] = "HumanReviewRequired: chapter agenda and recall evidence must be approved before drafting."

        self._store.save_chapter_state(chapter_id=chapter_id, state=state)
        return state

    def get_review_task(self, *, chapter_id: str) -> dict[str, Any] | None:
        return self._store.get_review_task(chapter_id=chapter_id)

    def get_chapter_state(self, *, chapter_id: str) -> dict[str, Any] | None:
        return self._store.get_chapter_state(chapter_id=chapter_id)

    def create_novel(self, *, novel_id: str, novel_title: str) -> dict[str, Any]:
        return self._store.create_novel(novel_id=novel_id, novel_title=novel_title)

    def list_novels(self) -> list[dict[str, Any]]:
        return self._store.list_novels()

    def list_chapters(self, *, novel_id: str) -> dict[str, Any]:
        chapters = self._store.list_chapters(novel_id=novel_id)
        novel_title = ""
        if chapters:
            novel_title = str(chapters[0].get("novel_title", ""))
        else:
            novel = self._store.get_novel(novel_id=novel_id)
            if novel:
                novel_title = str(novel.get("novel_title", ""))
        return {
            "novel_id": novel_id,
            "novel_title": novel_title,
            "chapters": chapters,
        }

    def submit_review(
        self,
        *,
        chapter_id: str,
        agenda_review_status: str,
        agenda_review_notes: str,
        approved_chapter_agenda: str,
        approved_rag_recall_summary: str,
    ) -> dict[str, Any]:
        state = self._store.get_chapter_state(chapter_id=chapter_id)
        if not state:
            raise KeyError(f"chapter_id not found: {chapter_id}")

        self._coerce_metadata(state, chapter_id=chapter_id)
        state.update(
            {
                "agenda_review_status": agenda_review_status,
                "agenda_review_notes": agenda_review_notes,
                "approved_chapter_agenda": approved_chapter_agenda,
                "approved_rag_recall_summary": approved_rag_recall_summary,
                "enforce_state_review_status": True,
            }
        )
        state.update(human_agenda_review_gate(state))

        final_status = str(state.get("agenda_review_status", "pending"))
        if final_status == "approved":
            state["chapter_status"] = "approved"
        elif final_status == "rejected":
            state["chapter_status"] = "regenerate_required"
        else:
            state["chapter_status"] = "review_pending"

        self._store.save_chapter_state(chapter_id=chapter_id, state=state)
        return state

    def generate_draft(self, *, chapter_id: str) -> dict[str, Any]:
        state = self._store.get_chapter_state(chapter_id=chapter_id)
        if not state:
            raise KeyError(f"chapter_id not found: {chapter_id}")
        if str(state.get("agenda_review_status", "pending")) != "approved":
            raise PermissionError(
                "HumanReviewRequired: draft generation is blocked until agenda review is approved."
            )

        self._coerce_metadata(state, chapter_id=chapter_id)
        state["chapter_status"] = "drafting"

        max_rewrites = int(state.get("max_rewrites", 3))
        decision = "Approved"
        for _ in range(max_rewrites + 1):
            state.update(draft_writer_node(state))
            state.update(critic_node(state))
            decision = route_after_critic(state)
            if decision == "Rejected":
                continue
            if decision == "Approved":
                state.update(memory_harvester_node(state))
            break

        if decision == "Abort":
            state["chapter_status"] = "regenerate_required"
        elif decision == "Approved":
            state["chapter_status"] = "published"

        self._store.save_chapter_state(chapter_id=chapter_id, state=state)
        return state
