from __future__ import annotations

from typing import Literal, TypedDict

Phase = Literal["起", "承", "转", "合"]
ReviewStatus = Literal["pending", "approved", "rejected", "edited"]
RouteDecision = Literal["NeedHumanReview", "Rejected", "Approved", "Abort"]
ChapterLifecycleStatus = Literal[
    "planning",
    "review_pending",
    "approved",
    "drafting",
    "published",
    "dirty",
    "regenerate_required",
]


class RagEvidence(TypedDict, total=False):
    source_id: str  # 证据唯一标识，便于追踪来源
    title: str  # 证据标题，用于审核页展示
    snippet: str  # 命中的原文片段
    score: float  # 召回相关性分数


class WriterViewState(TypedDict, total=False):
    """DraftWriter 唯一允许读取的状态切片。"""

    current_phase: Phase  # 当前章节节奏（起/承/转/合）
    memory_l0: str  # 近程记忆摘要
    previous_chapter_ending: str  # 上一章结尾，保证章节衔接
    approved_chapter_agenda: str  # 人工审核通过后的细纲
    approved_rag_recall_summary: str  # 人工审核通过后的设定摘要


class NovelState(TypedDict, total=False):
    """Global state flowing through LangGraph nodes."""

    # 追踪字段
    novel_id: str  # 小说 ID，用于多小说分组与检索
    novel_title: str  # 小说标题，供管理面板展示
    chapter_id: str  # 章节唯一 ID，接口与存储主键
    chapter_number: int  # 章节序号，便于排序和章节管理
    chapter_title: str  # 章节标题，供管理面板展示
    version_id: str  # 当前章节版本 ID，为未来多版本章节治理预留
    parent_version_id: str  # 当前版本来源的父版本 ID，为后续分叉/回改预留
    chapter_status: ChapterLifecycleStatus  # 章节生命周期状态，为回改传播治理预留
    recall_trace_id: str  # 本轮召回事件追踪 ID
    review_trace_id: str  # 本轮人工审核事件追踪 ID
    audit_log_path: str  # 审计日志实际落盘路径
    audit_warning: str  # 审计写入告警（为空表示正常）
    enforce_state_review_status: bool  # True 时仅信任 state 审核状态，不使用环境变量覆盖

    # 上帝视角字段（编剧/质检可见）
    world_rules: str  # 世界硬规则（能力边界、物理约束等）
    global_outline: str  # 全书总纲
    future_waypoints: str  # 未来宿命点/关键里程碑
    guidance_from_future: str  # 来自未来剧情的约束提示
    current_arc: str  # 当前剧情弧线目标

    # 局部执行字段
    current_phase: Phase  # 当前章节处于起承转合哪个阶段
    memory_l0: str  # 本章写作所需的近程上下文记忆
    previous_chapter_ending: str  # 上章结尾摘要/片段
    chapter_agenda_draft: str  # 作者/前端输入的本章细纲草案，供 PlotPlanner 读取
    chapter_agenda: str  # PlotPlanner 产出的正式本章细纲，供后续 recall / review 使用

    # RAG 召回与人工审阅字段
    rag_recall_summary: str  # 本轮设定召回摘要
    rag_evidence: list[RagEvidence]  # 结构化召回证据链
    agenda_review_status: ReviewStatus  # 人工审核状态
    agenda_review_notes: str  # 人工审核备注（通过/驳回原因）
    approved_chapter_agenda: str  # 人工最终放行的细纲
    approved_rag_recall_summary: str  # 人工最终放行的设定摘要

    # 产物与控制字段
    draft: str  # 生成出的章节初稿正文
    draft_word_count: int  # 初稿字数
    critic_feedback: str  # 质检节点反馈
    rewrite_count: int  # 当前重写次数
    max_rewrites: int  # 最大允许重写次数，超限走 Abort

    # 运行配置
    model_name: str  # 生成模型名称
    temperature: float  # 模型采样温度
    use_mock_llm: bool  # 是否使用本地 mock 生成（开发测试）
    show_draft_system_prompt: bool  # 是否打印 DraftWriter 系统提示词
    show_draft_prompt: bool  # 是否打印 DraftWriter 用户提示词
    error: str  # 当前步骤错误信息/阻断原因
