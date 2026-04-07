from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PlanRequest(BaseModel):
    global_outline: str | None = None
    current_arc: str | None = None
    current_phase: str | None = None
    memory_l0: str | None = None
    previous_chapter_ending: str | None = None
    chapter_agenda: str | None = None
    world_rules: str | None = None
    future_waypoints: str | None = None
    guidance_from_future: str | None = None


class PlanResponse(BaseModel):
    chapter_id: str
    chapter_agenda: str
    rag_recall_summary: str
    rag_evidence: list[dict[str, Any]]
    agenda_review_status: str
    recall_trace_id: str
    audit_log_path: str = ""
    audit_warning: str = ""


class ReviewTaskResponse(BaseModel):
    chapter_id: str
    chapter_agenda: str
    rag_recall_summary: str
    rag_evidence: list[dict[str, Any]]
    agenda_review_status: str
    agenda_review_notes: str
    approved_chapter_agenda: str
    approved_rag_recall_summary: str
    recall_trace_id: str
    review_trace_id: str
    audit_log_path: str = ""
    latest_recall_event: dict[str, Any] = Field(default_factory=dict)
    latest_review_event: dict[str, Any] = Field(default_factory=dict)
    updated_at: str = ""


class ReviewRequest(BaseModel):
    agenda_review_status: Literal["pending", "approved", "rejected", "edited"]
    agenda_review_notes: str = ""
    approved_chapter_agenda: str = ""
    approved_rag_recall_summary: str = ""


class ReviewResponse(BaseModel):
    chapter_id: str
    agenda_review_status: str
    agenda_review_notes: str
    approved_chapter_agenda: str
    approved_rag_recall_summary: str
    review_trace_id: str
    recall_trace_id: str
    audit_log_path: str = ""
    audit_warning: str = ""


class DraftResponse(BaseModel):
    chapter_id: str
    agenda_review_status: str
    draft: str
    draft_word_count: int
    rewrite_count: int
    critic_feedback: str = ""
    error: str = ""
    recall_trace_id: str = ""
    review_trace_id: str = ""
