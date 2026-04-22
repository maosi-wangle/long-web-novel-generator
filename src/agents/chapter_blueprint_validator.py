from __future__ import annotations

from src.schemas.outline import ChapterBlueprint, StoryStructure


def validate_and_repair_chapter_blueprints(
    story_structure: StoryStructure,
    chapter_blueprints: list[ChapterBlueprint],
) -> list[ChapterBlueprint]:
    normalized = [_normalize_blueprint(blueprint, index) for index, blueprint in enumerate(chapter_blueprints, start=1)]
    if not normalized:
        return normalized

    if not normalized[0].entering_state:
        normalized[0].entering_state = list(story_structure.start_state)

    for index, chapter in enumerate(normalized):
        if not chapter.chapter_summary:
            chapter.chapter_summary = chapter.core_function

        if not chapter.hook and chapter.exit_obligation:
            chapter.hook = chapter.exit_obligation[0]

        if index == 0:
            continue

        previous = normalized[index - 1]
        chapter.must_resolve = _merge(previous.exit_obligation, chapter.must_resolve)
        if previous.state_delta:
            chapter.entering_state = _merge(previous.state_delta, chapter.entering_state)

    last = normalized[-1]
    if story_structure.target_end_state:
        last.state_delta = _merge(last.state_delta, story_structure.target_end_state)

    return normalized


def _normalize_blueprint(chapter: ChapterBlueprint, chapter_id: int) -> ChapterBlueprint:
    chapter.chapter_id = chapter_id
    chapter.entering_state = _dedupe(chapter.entering_state)
    chapter.must_resolve = _dedupe(chapter.must_resolve)
    chapter.must_advance = _dedupe(chapter.must_advance)
    chapter.cannot_cross = _dedupe(chapter.cannot_cross)
    chapter.foreshadow_op = _dedupe(chapter.foreshadow_op)
    chapter.state_delta = _dedupe(chapter.state_delta)
    chapter.exit_obligation = _dedupe(chapter.exit_obligation)
    if not chapter.chapter_summary:
        chapter.chapter_summary = chapter.core_function
    return chapter


def _merge(left: list[str], right: list[str]) -> list[str]:
    return _dedupe([*left, *right])


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for item in items:
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        values.append(text)
    return values
