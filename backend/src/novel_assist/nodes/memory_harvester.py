from __future__ import annotations

import re
from typing import Any

from novel_assist.services.memory_extractor import (
    build_heuristic_harvest_sections,
    extract_harvest_sections_with_llm,
)
from novel_assist.services.memory_schema import HarvestSections, MemoryItem
from novel_assist.stores.factory import get_graph_store
from novel_assist.state.novel_state import NovelState

ENTITY_PREFIX_MAP = {
    "character": "role",
    "faction": "faction",
    "place": "place",
    "artifact": "artifact",
    "concept": "concept",
}
CATEGORY_TAG_MAP = {
    "character": "character",
    "faction": "faction",
    "place": "location",
    "artifact": "artifact",
    "concept": "concept",
}


def _truncate(text: str, *, limit: int) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit]


def _entity_key(name: str) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip()).casefold()


def _slugify(label: str) -> str:
    compact = re.sub(r"\s+", "_", str(label or "").strip())
    compact = re.sub(r"[^\w\u4e00-\u9fff]+", "_", compact)
    return compact.strip("_") or "entity"


def _entity_id(name: str, category: str) -> str:
    prefix = ENTITY_PREFIX_MAP.get(category, "concept")
    return f"{prefix}:{_slugify(name)}"


def _relation_id(left_id: str, right_id: str) -> str:
    return f"relation:{left_id}--{right_id}"


def _source_trace_id(state: NovelState) -> str:
    return str(state.get("review_trace_id") or state.get("chapter_id") or "")


def _base_memory_payload(state: NovelState, *, memory_type: str, title: str, content: str) -> dict[str, Any]:
    chapter_number = int(state.get("chapter_number", 1) or 1)
    return {
        "novel_id": str(state.get("novel_id", "")),
        "chapter_id": str(state.get("chapter_id", "")),
        "chapter_number": chapter_number,
        "memory_type": memory_type,
        "title": title,
        "content": content,
        "valid_from_chapter": chapter_number,
        "status": "active",
        "source_trace_id": _source_trace_id(state),
    }


def _has_sections(sections: HarvestSections) -> bool:
    return any(bool(sections.get(key)) for key in ("base_items", "entities", "relations"))


def _build_entity_registry(sections: HarvestSections) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}

    def ensure(
        name: str,
        *,
        category: str = "concept",
        summary: str = "",
        tags: list[str] | None = None,
        salience: float = 0.62,
    ) -> None:
        normalized_name = str(name or "").strip()
        if not normalized_name:
            return
        key = _entity_key(normalized_name)
        entity_id = _entity_id(normalized_name, category)
        existing = registry.get(key)
        if existing is None:
            registry[key] = {
                "name": normalized_name,
                "category": category,
                "entity_id": entity_id,
                "summary": summary or normalized_name,
                "tags": list(dict.fromkeys(tags or [])),
                "salience": salience,
            }
            return

        if existing["category"] == "concept" and category != "concept":
            existing["category"] = category
            existing["entity_id"] = entity_id
        if len(summary) > len(str(existing.get("summary", ""))):
            existing["summary"] = summary
        existing["tags"] = list(dict.fromkeys([*existing.get("tags", []), *(tags or [])]))
        existing["salience"] = max(float(existing.get("salience", 0.0)), salience)

    for entity in sections.get("entities", []):
        ensure(
            str(entity.get("name", "")),
            category=str(entity.get("category", "concept")),
            summary=str(entity.get("summary", "")),
            tags=list(entity.get("tags", [])),
            salience=float(entity.get("salience", 0.62) or 0.62),
        )

    for relation in sections.get("relations", []):
        ensure(str(relation.get("left", "")))
        ensure(str(relation.get("right", "")))

    for item in sections.get("base_items", []):
        for ref in item.get("entity_refs", []):
            ensure(str(ref))

    return registry


def _build_entity_items(state: NovelState, registry: dict[str, dict[str, Any]]) -> list[MemoryItem]:
    items: list[MemoryItem] = []
    for entry in registry.values():
        category = str(entry["category"])
        public_tag = CATEGORY_TAG_MAP.get(category, category)
        tags = list(dict.fromkeys(["entity", public_tag, *entry.get("tags", [])]))
        item: MemoryItem = {
            **_base_memory_payload(
                state,
                memory_type="entity",
                title=str(entry["name"]),
                content=str(entry.get("summary", "") or entry["name"]),
            ),
            "tags": tags,
            "entity_ids": [str(entry["entity_id"])],
            "relation_ids": [],
            "salience": max(0.35, min(1.0, float(entry.get("salience", 0.62) or 0.62))),
            "source_excerpt": _truncate(str(entry.get("summary", "") or entry["name"]), limit=220),
        }
        items.append(item)
    return items


def _build_relation_items(state: NovelState, sections: HarvestSections, registry: dict[str, dict[str, Any]]) -> list[MemoryItem]:
    items: list[MemoryItem] = []
    seen: set[str] = set()

    for relation in sections.get("relations", []):
        left_key = _entity_key(str(relation.get("left", "")))
        right_key = _entity_key(str(relation.get("right", "")))
        left = registry.get(left_key)
        right = registry.get(right_key)
        if left is None or right is None:
            continue

        relation_id = _relation_id(str(left["entity_id"]), str(right["entity_id"]))
        if relation_id in seen:
            continue
        seen.add(relation_id)

        relation_type = str(relation.get("relation_type", "related_to"))
        summary = str(relation.get("summary", "")).strip() or f"{left['name']} {relation_type} {right['name']}"
        tags = list(dict.fromkeys(["relation", relation_type, *relation.get("tags", [])]))
        item: MemoryItem = {
            **_base_memory_payload(
                state,
                memory_type="relation",
                title=f"{left['name']} -> {right['name']}",
                content=summary,
            ),
            "tags": tags,
            "entity_ids": [str(left["entity_id"]), str(right["entity_id"])],
            "relation_ids": [relation_id],
            "salience": max(0.35, min(1.0, float(relation.get("salience", 0.65) or 0.65))),
            "source_excerpt": _truncate(summary, limit=220),
        }
        items.append(item)

    return items


def _entity_ids_for_base_item(item: dict[str, Any], registry: dict[str, dict[str, Any]]) -> list[str]:
    matched: list[str] = []
    refs = [str(value) for value in item.get("entity_refs", [])]
    content = " ".join([str(item.get("title", "")), str(item.get("content", ""))])

    for ref in refs:
        entity = registry.get(_entity_key(ref))
        if entity is not None:
            matched.append(str(entity["entity_id"]))

    if matched:
        return list(dict.fromkeys(matched))

    for entry in registry.values():
        name = str(entry["name"])
        if name and name in content:
            matched.append(str(entry["entity_id"]))
    return list(dict.fromkeys(matched))


def _relation_ids_for_entity_ids(entity_ids: list[str], relation_items: list[MemoryItem]) -> list[str]:
    entity_set = set(entity_ids)
    relation_ids: list[str] = []
    for item in relation_items:
        pair = set(str(value) for value in item.get("entity_ids", []))
        if pair and pair.issubset(entity_set):
            relation_ids.extend(str(value) for value in item.get("relation_ids", []))
    return list(dict.fromkeys(relation_ids))


def _build_base_items(
    state: NovelState,
    sections: HarvestSections,
    registry: dict[str, dict[str, Any]],
    relation_items: list[MemoryItem],
) -> list[MemoryItem]:
    items: list[MemoryItem] = []
    for raw in sections.get("base_items", []):
        title = str(raw.get("title", "")).strip()
        content = str(raw.get("content", "")).strip()
        if not title or not content:
            continue

        entity_ids = _entity_ids_for_base_item(raw, registry)
        relation_ids = _relation_ids_for_entity_ids(entity_ids, relation_items)
        memory_type = str(raw.get("memory_type", "event")).strip().lower()
        if memory_type not in {"event", "fact"}:
            memory_type = "event"

        item: MemoryItem = {
            **_base_memory_payload(state, memory_type=memory_type, title=title, content=content),
            "tags": list(dict.fromkeys([memory_type, *raw.get("tags", [])])),
            "entity_ids": entity_ids,
            "relation_ids": relation_ids,
            "salience": max(0.3, min(1.0, float(raw.get("salience", 0.7) or 0.7))),
            "source_excerpt": _truncate(str(raw.get("source_excerpt", "")).strip() or content, limit=220),
        }
        items.append(item)
    return items


def _memory_identity(item: MemoryItem) -> tuple[Any, ...]:
    memory_type = str(item.get("memory_type", ""))
    if memory_type == "entity":
        return ("entity", tuple(sorted(str(value) for value in item.get("entity_ids", []))))
    if memory_type == "relation":
        return ("relation", tuple(sorted(str(value) for value in item.get("relation_ids", []))))
    return (
        memory_type,
        str(item.get("title", "")).strip(),
        str(item.get("content", "")).strip(),
    )


def _merge_memory_items(items: list[MemoryItem]) -> list[MemoryItem]:
    merged: dict[tuple[Any, ...], MemoryItem] = {}
    order: list[tuple[Any, ...]] = []

    for raw_item in items:
        item = dict(raw_item)
        identity = _memory_identity(item)
        existing = merged.get(identity)
        if existing is None:
            merged[identity] = item
            order.append(identity)
            continue

        existing["tags"] = list(dict.fromkeys([*existing.get("tags", []), *item.get("tags", [])]))
        existing["entity_ids"] = list(dict.fromkeys([*existing.get("entity_ids", []), *item.get("entity_ids", [])]))
        existing["relation_ids"] = list(
            dict.fromkeys([*existing.get("relation_ids", []), *item.get("relation_ids", [])])
        )
        existing["salience"] = max(float(existing.get("salience", 0.0) or 0.0), float(item.get("salience", 0.0) or 0.0))
        if not str(existing.get("source_excerpt", "")).strip():
            existing["source_excerpt"] = str(item.get("source_excerpt", ""))

    return [merged[key] for key in order]


def _build_memory_items_from_sections(state: NovelState, sections: HarvestSections) -> list[MemoryItem]:
    registry = _build_entity_registry(sections)
    entity_items = _build_entity_items(state, registry)
    relation_items = _build_relation_items(state, sections, registry)
    base_items = _build_base_items(state, sections, registry, relation_items)
    return _merge_memory_items([*base_items, *entity_items, *relation_items])


def preview_memory_harvest(state: NovelState) -> dict[str, Any]:
    """Build diagnostic harvest layers without persisting anything."""
    draft = str(state.get("draft", ""))
    ending = draft[-200:] if draft else str(state.get("previous_chapter_ending", ""))

    fallback_sections = build_heuristic_harvest_sections(
        state,
        ending=ending,
        source_tag="fallback-extracted",
    )

    llm_sections: HarvestSections = {"base_items": [], "entities": [], "relations": []}
    llm_extraction_error = ""
    try:
        llm_sections = extract_harvest_sections_with_llm(state, ending=ending)
    except Exception as exc:
        llm_extraction_error = f"{type(exc).__name__}: {exc}"

    final_source = "llm" if _has_sections(llm_sections) else "fallback"
    final_sections = llm_sections if final_source == "llm" else fallback_sections
    final_items = _build_memory_items_from_sections(state, final_sections)

    return {
        "ending": ending,
        "fallback_sections": fallback_sections,
        "llm_sections": llm_sections,
        "llm_extraction_error": llm_extraction_error,
        "final_sections": final_sections,
        "final_source": final_source,
        "final_items": final_items,
    }


def _merge_warning(existing_warning: str, new_warning: str) -> str:
    existing_warning = existing_warning.strip()
    new_warning = new_warning.strip()
    if not existing_warning:
        return new_warning
    if not new_warning:
        return existing_warning
    if new_warning in existing_warning:
        return existing_warning
    return f"{existing_warning} | {new_warning}"


def memory_harvester_node(state: NovelState) -> dict[str, Any]:
    """Persist chapter memory for future recall."""
    preview = preview_memory_harvest(state)
    updates: dict[str, Any] = {
        "previous_chapter_ending": preview["ending"],
        "memory_harvest_source": preview["final_source"],
        "memory_harvest_count": len(preview["final_items"]),
    }

    if preview["final_source"] != "llm" and preview["llm_extraction_error"]:
        updates["audit_warning"] = _merge_warning(
            str(state.get("audit_warning", "")),
            f"MemoryHarvestFallback: {preview['llm_extraction_error']}",
        )

    novel_id = str(state.get("novel_id", "")).strip()
    chapter_id = str(state.get("chapter_id", "")).strip()
    if not novel_id or not chapter_id:
        return updates

    if not preview["final_items"]:
        return updates

    try:
        store = get_graph_store()
        store.persist_memory_items(
            novel_id=novel_id,
            chapter_id=chapter_id,
            memory_items=[dict(item) for item in preview["final_items"]],
        )
    except Exception as exc:
        updates["audit_warning"] = _merge_warning(
            str(updates.get("audit_warning") or state.get("audit_warning", "")),
            f"MemoryHarvestWriteFailed: {type(exc).__name__}: {exc}",
        )

    return updates
