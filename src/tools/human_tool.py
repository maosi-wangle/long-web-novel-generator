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
    ) -> HumanReviewRecord:
        record = HumanReviewRecord(
            review_id=self._next_review_id(),
            project_id=self.project_id,
            stage=stage,
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

        if record.stage == "outline_review":
            outline_payload = result.edited_payload or payload
            outline = NovelOutline.model_validate(outline_payload)
            if result.edited_payload:
                self.workflow.save_outline(self.project_id, outline)
            else:
                self.workflow.clear_waiting_human_review(
                    self.project_id,
                    status=WorkflowStatus.outline_ready,
                    stage=GenerationStage.detail_outline,
                    note=self._make_resolution_note(record, result),
                )
            return

        if record.stage == "detail_outline_review":
            detail_payload = result.edited_payload or payload
            detail_outline = DetailOutline.model_validate(detail_payload)
            if result.edited_payload:
                self.workflow.save_detail_outline(self.project_id, detail_outline)
            else:
                self.workflow.clear_waiting_human_review(
                    self.project_id,
                    status=WorkflowStatus.detail_outline_ready,
                    stage=GenerationStage.writer,
                    note=self._make_resolution_note(record, result),
                )
            return

        if record.stage == "chapter_review":
            chapter_payload = result.edited_payload or payload
            chapter = ChapterArtifact.model_validate(chapter_payload)
            self.workflow.archive_chapter(self.project_id, chapter)
            RagTool(self.project_id).ingest_archived_chapter(chapter.chapter_id)
            return

        self.workflow.clear_waiting_human_review(
            self.project_id,
            note=self._make_resolution_note(record, result),
        )

    def _apply_rejected_review(self, record: HumanReviewRecord, result: HumanInterventionResult) -> None:
        note = self._make_resolution_note(record, result)
        if record.stage == "outline_review":
            self.workflow.clear_waiting_human_review(
                self.project_id,
                status=WorkflowStatus.initialized,
                stage=GenerationStage.outline,
                note=note,
            )
            return
        if record.stage == "detail_outline_review":
            self.workflow.clear_waiting_human_review(
                self.project_id,
                status=WorkflowStatus.outline_ready,
                stage=GenerationStage.detail_outline,
                note=note,
            )
            return
        if record.stage == "chapter_review":
            self.workflow.clear_waiting_human_review(
                self.project_id,
                status=WorkflowStatus.detail_outline_ready,
                stage=GenerationStage.writer,
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
            payload = self._load_payload(record)
            if record.stage != "chapter_review":
                raise RuntimeError("Markdown edited files are only supported for chapter_review.")
            payload["markdown_body"] = path.read_text(encoding="utf-8").strip()
            return payload
        raise RuntimeError("Edited file must be either .json or .md")

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

