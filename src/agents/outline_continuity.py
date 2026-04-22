from __future__ import annotations

from src.schemas.outline import ChapterPlan, NovelOutline, ScenePlan


def apply_outline_scene_continuity(outline: NovelOutline) -> NovelOutline:
    _ensure_scene_containers(outline)
    _assign_global_scene_ids(outline)
    _apply_scene_continuity(outline)
    _sync_chapter_fields_from_scenes(outline)
    return outline


def _ensure_scene_containers(outline: NovelOutline) -> None:
    for act in outline.acts:
        for chapter in act.chapters:
            if chapter.scenes:
                continue
            chapter.scenes = [
                ScenePlan(
                    scene_id=0,
                    title=chapter.title,
                    objective=chapter.goal,
                    beats=_unique_texts(chapter.beats),
                    hook=chapter.hook,
                )
            ]


def _assign_global_scene_ids(outline: NovelOutline) -> None:
    scene_id = 1
    for act in outline.acts:
        for chapter in act.chapters:
            for scene in chapter.scenes:
                scene.scene_id = scene_id
                scene_id += 1


def _apply_scene_continuity(outline: NovelOutline) -> None:
    scenes = [scene for act in outline.acts for chapter in act.chapters for scene in chapter.scenes]
    for index, scene in enumerate(scenes):
        scene.carry_in = _unique_texts(scene.carry_in)
        scene.entry_state = _unique_texts(scene.entry_state)
        scene.exit_state = _unique_texts(scene.exit_state)
        scene.open_threads_created = _unique_texts(scene.open_threads_created)
        scene.open_threads_resolved = _unique_texts(scene.open_threads_resolved)
        scene.next_scene_must_address = _unique_texts(scene.next_scene_must_address)
        if index == 0:
            continue

        previous = scenes[index - 1]
        inherited_items = _unique_texts(previous.next_scene_must_address)
        if previous.hook:
            inherited_items = _unique_texts([*inherited_items, previous.hook])

        if inherited_items and not _scene_mentions_any(scene, inherited_items):
            scene.carry_in = _unique_texts([*inherited_items, *scene.carry_in])

        if previous.exit_state and not scene.entry_state:
            scene.entry_state = _unique_texts(previous.exit_state[:2])

        if previous.hook and not previous.next_scene_must_address:
            previous.next_scene_must_address = [previous.hook]

        if previous.hook and not scene.transition_bridge:
            scene.transition_bridge = (
                f"先承接上一场景遗留的问题“{previous.hook}”，"
                f"再自然转入当前场景“{scene.title}”。"
            )


def _sync_chapter_fields_from_scenes(outline: NovelOutline) -> None:
    for act in outline.acts:
        for chapter in act.chapters:
            if not chapter.scenes:
                continue
            if not chapter.summary:
                chapter.summary = "；".join(scene.objective for scene in chapter.scenes[:3])
            chapter.beats = _unique_texts(
                [
                    *chapter.beats,
                    *[scene.objective for scene in chapter.scenes if scene.objective],
                ]
            )
            last_hook = next((scene.hook for scene in reversed(chapter.scenes) if scene.hook), None)
            if last_hook:
                chapter.hook = last_hook


def _scene_mentions_any(scene: ScenePlan, items: list[str]) -> bool:
    haystack = " ".join(
        [
            scene.title,
            scene.objective,
            *(scene.beats or []),
            *(scene.carry_in or []),
            *(scene.entry_state or []),
            *(scene.exit_state or []),
            *(scene.next_scene_must_address or []),
            scene.transition_bridge or "",
            scene.hook or "",
        ]
    )
    return any(item and item in haystack for item in items)


def _unique_texts(items: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for item in items:
        text = item.strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized
