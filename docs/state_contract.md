# NovelState Minimal Contract

This document clarifies the current `NovelState` contract without renaming fields.
The goal is to reduce ambiguity before we add more backend features.

## Principles

- Keep existing field names stable for now.
- Treat `NovelState` as the runtime payload shared by `ChapterService`, workflow nodes, and API responses.
- Prefer documenting field ownership and lifecycle before doing any structural refactor.

## Field Groups

### Identity and persistence

- `novel_id`, `novel_title`, `chapter_id`, `chapter_number`, `chapter_title`
- `version_id`, `parent_version_id`, `chapter_status`
- `recall_trace_id`, `review_trace_id`, `audit_log_path`, `audit_warning`

Owner:
- `ChapterService` initializes the chapter identity fields.
- store implementations persist and reload these fields.
- review and recall nodes update trace and audit fields.

### Author input and planning input

- `global_outline`, `current_arc`, `current_phase`
- `memory_l0`, `previous_chapter_ending`
- `chapter_agenda_draft`
- `world_rules`, `future_waypoints`, `guidance_from_future`

Owner:
- request payloads and `ChapterService` populate these fields.
- chapter inheritance may fill missing values from the previous chapter.

Rule:
- these fields are treated as source context for planning and recall.

### Planner and review outputs

- `chapter_agenda`
- `rag_recall_summary`, `rag_evidence`
- `agenda_review_status`, `agenda_review_notes`
- `approved_chapter_agenda`, `approved_rag_recall_summary`

Owner:
- `PlotPlanner` writes `chapter_agenda`
- `RagRecall` writes recall fields
- `HumanAgendaReview` writes review result fields

Rule:
- `chapter_agenda` is the planner output.
- `approved_*` fields are the only review-approved inputs that `DraftWriter` should rely on.

### Draft and quality control outputs

- `draft`, `draft_word_count`
- `critic_feedback`
- `rewrite_count`, `max_rewrites`

Owner:
- `DraftWriter` writes draft fields.
- `CriticReviewer` writes `critic_feedback` and increments `rewrite_count`.
- `ChapterService` sets loop-level status like `drafting` and `published`.

### Runtime config

- `model_name`, `temperature`, `use_mock_llm`
- `show_draft_system_prompt`, `show_draft_prompt`

Owner:
- CLI entrypoints and API request overrides populate these fields.

## Current Error Semantics

The `error` field is intentionally left unchanged for compatibility, but its current meaning is broader than just exceptions.

It may contain:

- a real node failure, such as missing LLM credentials
- a workflow blocking reason, such as `HumanReviewRequired`
- a quality gate rejection, such as `CriticRejected`

Current rule:

- downstream modules may inspect `error`, but they should not assume it always means an unexpected exception
- routing after critic still uses `error` as its reject or abort signal

Recommended future cleanup:

- keep `error` for operational failures
- add a separate field like `block_reason` or `gate_reason` for expected workflow stops

## Write Boundaries

- `ChapterService.generate_plan()` may reset planning and review fields before invoking planner and recall nodes.
- `submit_review()` is the only path that should finalize `approved_*` fields.
- `generate_draft()` must check `agenda_review_status == "approved"` before calling `DraftWriter`.
- `MemoryHarvester` should only persist continuity or derived memory after a successful draft path.

## Stability Goal

As long as this contract holds, we can safely evolve:

- real RAG retrieval
- richer memory extraction
- new storage backends
- stronger workflow recovery

without renaming a large set of fields first.
