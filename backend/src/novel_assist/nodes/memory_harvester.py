from __future__ import annotations

from typing import Any

from novel_assist.state.novel_state import NovelState


def memory_harvester_node(state: NovelState) -> dict[str, Any]:
    """Persist chapter outcome into short-term continuity fields."""
    draft = state.get("draft", "")
    ending = draft[-200:] if draft else state.get("previous_chapter_ending", "")
    return {
        "previous_chapter_ending": ending,
    }
