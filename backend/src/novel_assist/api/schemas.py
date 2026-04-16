from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class CreateNovelRequest(BaseModel):
    novel_id: str = Field(description="小说 ID。")
    novel_title: str = Field(description="小说标题。")

    @field_validator("novel_id", "novel_title")
    @classmethod
    def ensure_non_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Value cannot be blank.")
        return cleaned


class PlanRequest(BaseModel):
    novel_id: str | None = Field(default=None, description="小说 ID，用于多小说分组。")
    novel_title: str | None = Field(default=None, description="小说标题。")
    chapter_number: int | None = Field(default=None, description="章节序号。")
    chapter_title: str | None = Field(default=None, description="章节标题。")
    use_mock_llm: bool | None = Field(default=None, description="是否使用 mock LLM。")
    global_outline: str | None = Field(default=None, description="全书总纲。")
    current_arc: str | None = Field(default=None, description="当前剧情弧线目标。")
    current_phase: str | None = Field(default=None, description="当前章节节奏阶段。")
    memory_l0: str | None = Field(default=None, description="近程记忆摘要。")
    previous_chapter_ending: str | None = Field(default=None, description="上一章结尾。")
    chapter_agenda_draft: str | None = Field(default=None, description="作者输入的章节细纲草案。")
    chapter_agenda: str | None = Field(default=None, description="兼容旧字段：章节细纲草案。")
    world_rules: str | None = Field(default=None, description="世界硬规则。")
    future_waypoints: str | None = Field(default=None, description="未来关键路标。")
    guidance_from_future: str | None = Field(default=None, description="来自未来剧情的约束提示。")


class PlanResponse(BaseModel):
    novel_id: str = Field(description="小说 ID。")
    novel_title: str = Field(description="小说标题。")
    chapter_id: str = Field(description="章节 ID。")
    chapter_number: int | None = Field(default=None, description="章节序号。")
    chapter_title: str = Field(description="章节标题。")
    chapter_status: str = Field(description="章节当前生命周期状态。")
    use_mock_llm: bool = Field(description="本章 plan 阶段是否使用 mock LLM。")
    chapter_agenda_draft: str = Field(description="作者输入的章节细纲草案。")
    chapter_agenda: str = Field(description="PlotPlanner 产出的当前章节细纲。")
    rag_recall_summary: str = Field(description="RAG/GraphRAG 召回摘要。")
    rag_evidence: list[dict[str, Any]] = Field(description="召回到的证据列表。")
    agenda_review_status: str = Field(description="人工审核状态。")
    recall_trace_id: str = Field(description="召回链路追踪 ID。")
    audit_log_path: str = Field(default="", description="审计日志路径。")
    audit_warning: str = Field(default="", description="审计写入告警。")
    error: str = Field(default="", description="plan 阶段错误信息。")


class ReviewTaskResponse(BaseModel):
    novel_id: str = Field(description="小说 ID。")
    novel_title: str = Field(description="小说标题。")
    chapter_id: str = Field(description="章节 ID。")
    chapter_number: int | None = Field(default=None, description="章节序号。")
    chapter_title: str = Field(description="章节标题。")
    chapter_status: str = Field(description="章节当前生命周期状态。")
    chapter_agenda_draft: str = Field(description="作者输入的章节细纲草案。")
    chapter_agenda: str = Field(description="当前章节细纲。")
    rag_recall_summary: str = Field(description="当前章节召回摘要。")
    rag_evidence: list[dict[str, Any]] = Field(description="证据链列表。")
    agenda_review_status: str = Field(description="审核状态，固定为 pending/approved/rejected/edited。")
    agenda_review_notes: str = Field(description="人工审核说明。")
    approved_chapter_agenda: str = Field(description="最终放行给 DraftWriter 的细纲。")
    approved_rag_recall_summary: str = Field(description="最终放行给 DraftWriter 的召回摘要。")
    recall_trace_id: str = Field(description="召回 trace ID。")
    review_trace_id: str = Field(description="审核 trace ID。")
    audit_log_path: str = Field(default="", description="审计日志路径。")
    audit_warning: str = Field(default="", description="审计写入告警。")
    latest_recall_event: dict[str, Any] = Field(default_factory=dict, description="最近一次召回事件。")
    latest_review_event: dict[str, Any] = Field(default_factory=dict, description="最近一次审核事件。")
    updated_at: str = Field(default="", description="章节状态最近更新时间。")


class ReviewRequest(BaseModel):
    agenda_review_status: Literal["pending", "approved", "rejected", "edited"] = Field(
        description="审核结论。"
    )
    agenda_review_notes: str = Field(default="", description="审核说明。")
    approved_chapter_agenda: str = Field(
        default="",
        description="人工改写后的放行细纲；为空时回退到当前章节细纲。",
    )
    approved_rag_recall_summary: str = Field(
        default="",
        description="人工改写后的放行召回摘要；为空时回退到当前召回摘要。",
    )


class ReviewResponse(BaseModel):
    novel_id: str = Field(description="小说 ID。")
    novel_title: str = Field(description="小说标题。")
    chapter_id: str = Field(description="章节 ID。")
    chapter_number: int | None = Field(default=None, description="章节序号。")
    chapter_title: str = Field(description="章节标题。")
    chapter_status: str = Field(description="章节当前生命周期状态。")
    agenda_review_status: str = Field(description="审核状态。")
    agenda_review_notes: str = Field(description="审核说明。")
    approved_chapter_agenda: str = Field(description="放行细纲。")
    approved_rag_recall_summary: str = Field(description="放行召回摘要。")
    review_trace_id: str = Field(description="审核 trace ID。")
    recall_trace_id: str = Field(description="关联召回 trace ID。")
    audit_log_path: str = Field(default="", description="审计日志路径。")
    audit_warning: str = Field(default="", description="审计写入告警。")


class DraftResponse(BaseModel):
    novel_id: str = Field(description="小说 ID。")
    novel_title: str = Field(description="小说标题。")
    chapter_id: str = Field(description="章节 ID。")
    chapter_number: int | None = Field(default=None, description="章节序号。")
    chapter_title: str = Field(description="章节标题。")
    chapter_status: str = Field(description="章节当前生命周期状态。")
    agenda_review_status: str = Field(description="生成初稿时的审核状态。")
    draft: str = Field(description="生成出的初稿。")
    draft_word_count: int = Field(description="初稿字数。")
    rewrite_count: int = Field(description="重写次数。")
    critic_feedback: str = Field(default="", description="Critic 反馈。")
    error: str = Field(default="", description="当前链路错误信息。")
    recall_trace_id: str = Field(default="", description="关联召回 trace ID。")
    review_trace_id: str = Field(default="", description="关联审核 trace ID。")


class ChapterStateResponse(BaseModel):
    chapter_id: str = Field(description="章节 ID。")
    state: dict[str, Any] = Field(description="完整章节状态快照。")


class NovelSummary(BaseModel):
    novel_id: str = Field(description="小说 ID。")
    novel_title: str = Field(description="小说标题。")
    chapter_count: int = Field(description="该小说已存在的章节数。")
    latest_chapter_id: str = Field(default="", description="最近更新章节 ID。")
    latest_chapter_title: str = Field(default="", description="最近更新章节标题。")
    updated_at: str = Field(default="", description="最近更新时间。")


class NovelListResponse(BaseModel):
    novels: list[NovelSummary] = Field(description="小说列表。")


class ChapterSummary(BaseModel):
    chapter_id: str = Field(description="章节 ID。")
    novel_id: str = Field(description="所属小说 ID。")
    novel_title: str = Field(description="所属小说标题。")
    chapter_number: int | None = Field(default=None, description="章节序号。")
    chapter_title: str = Field(default="", description="章节标题。")
    chapter_status: str = Field(default="", description="章节生命周期状态。")
    agenda_review_status: str = Field(default="", description="人工审核状态。")
    draft_word_count: int = Field(default=0, description="当前初稿字数。")
    updated_at: str = Field(default="", description="最近更新时间。")


class ChapterListResponse(BaseModel):
    novel_id: str = Field(description="小说 ID。")
    novel_title: str = Field(default="", description="小说标题。")
    chapters: list[ChapterSummary] = Field(description="该小说下的章节列表。")


class ApiErrorResponse(BaseModel):
    error_code: str = Field(description="统一错误码。")
    message: str = Field(description="错误消息。")
    detail: Any = Field(default=None, description="错误详情。")
    trace_id: str = Field(default="", description="链路追踪 ID。")
