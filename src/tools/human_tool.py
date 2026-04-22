from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import orjson

from src.config import get_project_paths
from src.orchestrator.state import GenerationStage, WorkflowStatus
from src.orchestrator.workflow import NovelWorkflow
from src.schemas import (
    ChapterArtifact,
    DetailOutline,
    HumanInterventionResult,
    HumanReviewRecord,
    NovelOutline,
    ReviewDecision,
    ReviewStatus,
)
from src.tools.rag_tool import RagTool


class HumanTool:
    def __init__(self, project_id: str, workflow: NovelWorkflow | None = None) -> None:
        self.project_id = project_id
        self.workflow = workflow or NovelWorkflow()
        self.paths = get_project_paths(project_id)
        self.paths.ensure()

    def request_review(
        self,
        *,
        stage: str,
        reason: str,
        payload: dict[str, Any],
        source_status: str | None,
        source_stage: str | None,
        target_chapter_id: int | None = None,
        preview_markdown: str | None = None,
        blocking: bool = True,
    ) -> HumanReviewRecord:
        self._ensure_request_allowed(blocking=blocking)
        record = HumanReviewRecord(
            review_id=self._next_review_id(),
            project_id=self.project_id,
            stage=stage,
            blocking=blocking,
            reason=reason,
            payload_file="",
            preview_file=None,
            target_chapter_id=target_chapter_id,
            source_status=source_status,
            source_stage=source_stage,
        )
        payload_path = self.paths.reviews_dir / f"{record.review_id}_{stage}.json"
        payload_path.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))
        record.payload_file = str(payload_path)

        if preview_markdown:
            preview_path = self.paths.reviews_dir / f"{record.review_id}_{stage}.md"
            preview_path.write_text(preview_markdown, encoding="utf-8")
            record.preview_file = str(preview_path)

        self._upsert_record(record)
        if blocking:
            self.workflow.mark_waiting_human_review(self.project_id, record.review_id)
        return record

    def list_reviews(self, status: ReviewStatus | None = None) -> list[HumanReviewRecord]:
        records = self._load_index()
        if status is None:
            return records
        return [record for record in records if record.status == status]

    def get_review(self, review_id: str) -> HumanReviewRecord:
        for record in self._load_index():
            if record.review_id == review_id:
                return record
        raise FileNotFoundError(f"Review {review_id} was not found for project {self.project_id}.")

    def resolve_review(
        self,
        *,
        review_id: str,
        decision: ReviewDecision,
        instruction: str | None = None,
        edited_file: str | None = None,
        operator: str = "user",
    ) -> HumanReviewRecord:
        record = self.get_review(review_id)
        self._ensure_resolve_allowed(record)
        edited_payload = self._load_edited_payload(record, edited_file)
        result = HumanInterventionResult(
            approved=decision == ReviewDecision.approve,
            edited_payload=edited_payload,
            instruction=instruction or None,
            operator=operator,
        )

        if decision == ReviewDecision.approve:
            self._apply_approved_review(record, result)
        else:
            self._apply_rejected_review(record, result)

        record.status = ReviewStatus.resolved
        record.resolution = result
        record.updated_at = result.timestamp
        self._upsert_record(record)
        return record

    def _apply_approved_review(self, record: HumanReviewRecord, result: HumanInterventionResult) -> None:
        payload = self._load_payload(record)
        note = self._make_resolution_note(record, result)

        if record.stage == "outline_review":
            outline_payload = result.edited_payload or payload
            outline = NovelOutline.model_validate(outline_payload)
            if record.blocking:
                self.workflow.save_outline(self.project_id, outline)
            else:
                self.workflow.state_store.save_outline(self.project_id, outline)
                self.workflow.append_note(self.project_id, note)
            return

        if record.stage == "detail_outline_review":
            detail_payload = result.edited_payload or payload
            detail_outline = DetailOutline.model_validate(detail_payload)
            self._validate_target_chapter(record, detail_outline.chapter_id)
            if record.blocking:
                self.workflow.save_detail_outline(self.project_id, detail_outline)
            else:
                self.workflow.state_store.save_detail_outline(self.project_id, detail_outline)
                self.workflow.append_note(self.project_id, note)
            return

        if record.stage == "chapter_review":
            chapter_payload = result.edited_payload or payload
            chapter = ChapterArtifact.model_validate(chapter_payload)
            self._validate_target_chapter(record, chapter.chapter_id)
            if record.blocking:
                self.workflow.archive_chapter(self.project_id, chapter)
            else:
                self._save_historical_chapter_without_progress_change(chapter)
                self.workflow.append_note(self.project_id, note)
            RagTool(self.project_id).ingest_archived_chapter(chapter.chapter_id)
            return

        if record.blocking:
            self.workflow.clear_waiting_human_review(self.project_id, note=note)
        else:
            self.workflow.append_note(self.project_id, note)

    def _apply_rejected_review(self, record: HumanReviewRecord, result: HumanInterventionResult) -> None:
        note = self._make_resolution_note(record, result)
        if not record.blocking:
            self.workflow.append_note(self.project_id, note)
            return

        restored_status = self._parse_status(record.source_status)
        restored_stage = self._parse_stage(record.source_stage)

        if record.stage == "outline_review":
            self.workflow.clear_waiting_human_review(
                self.project_id,
                status=restored_status or WorkflowStatus.initialized,
                stage=restored_stage or GenerationStage.outline,
                note=note,
            )
            return
        if record.stage == "detail_outline_review":
            self.workflow.clear_waiting_human_review(
                self.project_id,
                status=restored_status or WorkflowStatus.outline_ready,
                stage=restored_stage or GenerationStage.detail_outline,
                note=note,
            )
            return
        if record.stage == "chapter_review":
            self.workflow.clear_waiting_human_review(
                self.project_id,
                status=restored_status or WorkflowStatus.detail_outline_ready,
                stage=restored_stage or GenerationStage.writer,
                note=note,
            )
            return

        self.workflow.clear_waiting_human_review(self.project_id, note=note)

    def _load_payload(self, record: HumanReviewRecord) -> dict[str, Any]:
        return orjson.loads(Path(record.payload_file).read_bytes())

    def _load_edited_payload(
        self,
        record: HumanReviewRecord,
        edited_file: str | None,
    ) -> dict[str, Any]:
        if not edited_file:
            return {}

        path = Path(edited_file)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Edited file does not exist: {path}")

        if path.suffix.lower() == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        if path.suffix.lower() == ".md":
            if record.stage != "chapter_review":
                raise RuntimeError("Markdown edited files are only supported for chapter_review.")
            chapter = self.workflow.markdown_store.parse_chapter_markdown(
                path.read_text(encoding="utf-8"),
                chapter_id_hint=record.target_chapter_id,
            )
            return chapter.model_dump(mode="json")
        raise RuntimeError("Edited file must be either .json or .md")

    def _save_historical_chapter_without_progress_change(self, chapter: ChapterArtifact) -> None:
        state = self.workflow.state_store.load_state(self.project_id)
        markdown_store = self.workflow.markdown_store
        try:
            outline_version, detail_outline_version = markdown_store.load_chapter_versions(
                self.project_id,
                chapter.chapter_id,
            )
        except FileNotFoundError:
            outline_version = state.outline_version
            detail_outline_version = state.detail_outline_version
        markdown_store.save_chapter(
            self.project_id,
            chapter,
            outline_version=outline_version,
            detail_outline_version=detail_outline_version,
        )

    def _ensure_request_allowed(self, *, blocking: bool) -> None:
        state = self.workflow.state_store.load_state(self.project_id)
        if blocking and state.pending_human_review:
            raise RuntimeError(
                f"Project {self.project_id} already has a pending review: {state.pending_review_id}."
            )

    def _ensure_resolve_allowed(self, record: HumanReviewRecord) -> None:
        if record.status != ReviewStatus.pending:
            raise RuntimeError(f"Review {record.review_id} is already resolved and cannot be replayed.")
        if not record.blocking:
            return

        state = self.workflow.state_store.load_state(self.project_id)
        if not state.pending_human_review or state.pending_review_id != record.review_id:
            raise RuntimeError(
                f"Review {record.review_id} is not the current pending review for project {self.project_id}."
            )

    @staticmethod
    def _validate_target_chapter(record: HumanReviewRecord, resolved_chapter_id: int) -> None:
        if record.target_chapter_id is None:
            return
        if resolved_chapter_id != record.target_chapter_id:
            raise RuntimeError(
                f"Review {record.review_id} targets chapter {record.target_chapter_id}, "
                f"but resolved payload points to chapter {resolved_chapter_id}."
            )

    @staticmethod
    def _parse_status(raw: str | None) -> WorkflowStatus | None:
        if not raw:
            return None
        return WorkflowStatus(raw)

    @staticmethod
    def _parse_stage(raw: str | None) -> GenerationStage | None:
        if not raw:
            return None
        return GenerationStage(raw)

    def _next_review_id(self) -> str:
        records = self._load_index()
        return f"review_{len(records) + 1:04d}"

    def _load_index(self) -> list[HumanReviewRecord]:
        if not self.paths.reviews_index_file.exists():
            return []
        raw = orjson.loads(self.paths.reviews_index_file.read_bytes())
        return [HumanReviewRecord.model_validate(item) for item in raw]

    def _save_index(self, records: list[HumanReviewRecord]) -> None:
        payload = [record.model_dump(mode="json") for record in records]
        self.paths.reviews_index_file.write_bytes(orjson.dumps(payload, option=orjson.OPT_INDENT_2))

    def _upsert_record(self, record: HumanReviewRecord) -> None:
        records = self._load_index()
        updated = False
        for index, existing in enumerate(records):
            if existing.review_id == record.review_id:
                records[index] = record
                updated = True
                break
        if not updated:
            records.append(record)
        self._save_index(records)

    @staticmethod
    def _make_resolution_note(record: HumanReviewRecord, result: HumanInterventionResult) -> str:
        decision = "approved" if result.approved else "rejected"
        if result.instruction:
            return f"{record.review_id} {decision}: {result.instruction}"
        return f"{record.review_id} {decision}"
