# Structured Output Notes

## What Changed

- `src/llm/compatible_client.py` now uses the official `openai` client plus `instructor`.
- Structured generation goes through `CompatibleLLMClient.chat_model(...)`.
- The structured client is patched with `instructor.Mode.JSON`.

## Why JSON Mode

- The runtime target is DashScope's OpenAI-compatible base URL, not the native OpenAI endpoint.
- `Mode.JSON` keeps the integration provider-friendly while still enforcing Pydantic validation and retry behavior.
- Plain text calls can still use `CompatibleLLMClient.chat(...)`.

## Agent Usage

- `OutlineAgent`
  - story-direction generation uses `StoryDirectionBatch`
  - final outline uses `NovelOutline`
- `DetailOutlineAgent`
  - chapter analysis uses `DetailOutlineAnalysis`
  - final detail outline uses `DetailOutline`
- `WriterAgent`
  - chapter drafting uses `ChapterArtifact`

## New Schemas

- `src/schemas/agent_outputs.py`
  - `StoryDirectionBatch`
  - `DetailOutlineAnalysis`

## Validation Status

- local unit tests: passed
- CLI import path: passed
- real provider smoke test: passed
  - response payload: `{"answer":"instructor ok","tags":["json","pydantic"]}`

## Maintenance Note

- If a future provider supports tool calling more reliably than JSON mode, `CompatibleLLMClient` is the only place that needs mode changes.
