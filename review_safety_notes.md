# Human Review Safety Notes

## Current Semantics

- `generate-outline --require-review`, `generate-detail-outline --require-review`, and `write-chapter --require-review` now create a blocking draft review first.
- Blocking draft reviews do not write official artifacts until the review is approved.
- While a blocking review is pending, generation commands and manual `request-review` are blocked.
- Manual `request-review` uses standalone mode by default and is intended for re-reviewing already saved artifacts.

## Resolve Rules

- A review can only be resolved once.
- Blocking reviews can only be resolved if they are still the project's current `pending_review_id`.
- Rejecting a blocking review restores the recorded `source_status` and `source_stage`.
- Standalone historical chapter review approval rewrites only the target chapter file and re-ingests RAG; it does not advance or rewind project progress.

## Chapter Review Safety

- `chapter_review` and `detail_outline_review` approvals validate that the resolved payload still points to the original `target_chapter_id`.
- Edited `.md` files for `chapter_review` are parsed as full chapter markdown, not injected into `markdown_body` as raw text.

## Regression Coverage

- `tests/test_review_workflow.py`
  - blocking outline draft does not leak into `outline.json`
  - blocking detail-outline draft does not leak into `detail_outlines/*.json`
  - pending blocking review blocks new generation/review entrypoints
  - resolved or stale blocking review cannot be replayed
  - standalone historical chapter review does not rewind workflow state
