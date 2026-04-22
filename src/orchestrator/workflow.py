from __future__ import annotations

from src.orchestrator.state import GenerationStage, ProjectState, WorkflowStatus
from src.schemas.chapter import ChapterArtifact, DetailOutline
from src.schemas.outline import NovelOutline
from src.schemas.project import ProjectBootstrapRequest, ProjectRecord
from src.storage.markdown_store import MarkdownStore
from src.storage.state_store import StateStore


class NovelWorkflow:
    """Minimal workflow shell used by the CLI and future agents."""

    def __init__(
        self,
        state_store: StateStore | None = None,
        markdown_store: MarkdownStore | None = None,
    ) -> None:
        self.state_store = state_store or StateStore()
        self.markdown_store = markdown_store or MarkdownStore()

    def create_project(self, request: ProjectBootstrapRequest) -> tuple[ProjectRecord, ProjectState]:
        record = ProjectRecord(**request.model_dump())
        state = ProjectState(project_id=request.project_id, title=request.title)
        self.state_store.initialize_project(record=record, state=state)
        return record, state

    def load_project(self, project_id: str) -> tuple[ProjectRecord, ProjectState]:
        return (
            self.state_store.load_project_record(project_id),
            self.state_store.load_state(project_id),
        )

    def load_outline(self, project_id: str) -> NovelOutline:
        return self.state_store.load_outline(project_id)

    def load_detail_outline(self, project_id: str, chapter_id: int) -> DetailOutline:
        return self.state_store.load_detail_outline(project_id, chapter_id)

    def save_outline(self, project_id: str, outline: NovelOutline) -> ProjectState:
        state = self.state_store.load_state(project_id)
        state.outline_version += 1
        state.pending_human_review = False
        state.pending_review_id = None
        state.mark_status(WorkflowStatus.outline_ready, stage=GenerationStage.detail_outline)
        self.state_store.save_outline(project_id, outline)
        self.state_store.save_state(project_id, state)
        return state

    def save_detail_outline(self, project_id: str, detail_outline: DetailOutline) -> ProjectState:
        state = self.state_store.load_state(project_id)
        outline = self.state_store.load_outline(project_id)
        act_index = self._find_act_index_for_chapter(outline, detail_outline.chapter_id)
        state.detail_outline_version += 1
        state.current_act_index = act_index
        state.current_chapter_index = detail_outline.chapter_id
        state.pending_human_review = False
        state.pending_review_id = None
        state.active_chapter_title = detail_outline.title
        state.mark_status(WorkflowStatus.detail_outline_ready, stage=GenerationStage.writer)
        self.state_store.save_detail_outline(project_id, detail_outline)
        self.state_store.save_state(project_id, state)
        return state

    def archive_chapter(self, project_id: str, chapter: ChapterArtifact) -> ProjectState:
        state = self.state_store.load_state(project_id)
        outline = self.state_store.load_outline(project_id)
        self.markdown_store.save_chapter(
            project_id=project_id,
            chapter=chapter,
            outline_version=state.outline_version,
            detail_outline_version=state.detail_outline_version,
        )
        state.current_act_index = self._find_act_index_for_chapter(outline, chapter.chapter_id)
        state.current_chapter_index = chapter.chapter_id
        state.last_completed_chapter = chapter.chapter_id
        state.pending_human_review = False
        state.pending_review_id = None
        if self._is_last_chapter(outline, chapter.chapter_id):
            state.mark_status(WorkflowStatus.completed, stage=GenerationStage.archive)
        else:
            state.mark_status(WorkflowStatus.outline_ready, stage=GenerationStage.detail_outline)
        self.state_store.save_state(project_id, state)
        return state

    def mark_waiting_human_review(self, project_id: str, review_id: str) -> ProjectState:
        state = self.state_store.load_state(project_id)
        state.pending_human_review = True
        state.pending_review_id = review_id
        state.mark_status(WorkflowStatus.waiting_human_review)
        self.state_store.save_state(project_id, state)
        return state

    def clear_waiting_human_review(
        self,
        project_id: str,
        *,
        status: WorkflowStatus | None = None,
        stage: GenerationStage | None = None,
        note: str | None = None,
    ) -> ProjectState:
        state = self.state_store.load_state(project_id)
        state.pending_human_review = False
        state.pending_review_id = None
        if note:
            state.notes.append(note)
        if status is not None or stage is not None:
            state.mark_status(status or state.status, stage=stage)
        else:
            state.touch()
        self.state_store.save_state(project_id, state)
        return state

    def append_note(self, project_id: str, note: str) -> ProjectState:
        state = self.state_store.load_state(project_id)
        state.notes.append(note)
        state.touch()
        self.state_store.save_state(project_id, state)
        return state

    @staticmethod
    def resolve_default_detail_chapter_id(state: ProjectState) -> int:
        if state.current_chapter_index > state.last_completed_chapter:
            return state.current_chapter_index
        return max(1, state.last_completed_chapter + 1)

    @staticmethod
    def _find_act_index_for_chapter(outline: NovelOutline, chapter_id: int) -> int:
        for act_index, act in enumerate(outline.acts):
            if any(chapter.chapter_id == chapter_id for chapter in act.chapters):
                return act_index
        raise RuntimeError(f"Chapter {chapter_id} was not found inside the saved outline.")

    @staticmethod
    def _is_last_chapter(outline: NovelOutline, chapter_id: int) -> bool:
        last_id = max(chapter.chapter_id for act in outline.acts for chapter in act.chapters)
        return chapter_id >= last_id
