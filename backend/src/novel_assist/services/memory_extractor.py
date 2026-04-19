from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from novel_assist.llm.client import generate_text
from novel_assist.services.memory_schema import (
    HarvestBaseItem,
    HarvestEntity,
    HarvestRelation,
    HarvestSections,
)
from novel_assist.state.novel_state import NovelState

DEFAULT_MODEL_NAME = "qwen3-max-preview"
DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 1000
ALLOWED_BASE_TYPES = {"event", "fact"}
ENTITY_CATEGORY_ALIASES = {
    "character": "character",
    "person": "character",
    "role": "character",
    "faction": "faction",
    "organization": "faction",
    "org": "faction",
    "place": "place",
    "location": "place",
    "artifact": "artifact",
    "item": "artifact",
    "object": "artifact",
    "concept": "concept",
}
CHINESE_STOP_WORDS = {
    "时候",
    "那里",
    "他们",
    "我们",
    "自己",
    "已经",
    "一种",
    "没有",
    "不能",
    "因为",
    "如果",
    "于是",
    "然后",
    "只是",
    "这个",
    "那个",
    "事情",
    "问题",
    "声音",
    "目光",
    "空气",
}
LOCATION_HINTS = ("城", "镇", "街", "巷", "港", "塔", "楼", "馆", "山", "谷", "岛", "宫", "殿")
ARTIFACT_HINTS = ("剑", "刀", "钥匙", "印", "镜", "石", "匣", "册", "卷", "珠", "环", "符")
FACTION_HINTS = ("会", "门", "帮", "盟", "军", "队", "阁", "社")

SYSTEM_PROMPT = """
You extract durable story memory from a novel chapter.
Return JSON only. No markdown.

Schema:
{
  "base_items": [
    {
      "memory_type": "event" | "fact",
      "title": "short title",
      "content": "1-2 sentence summary",
      "tags": ["tag"],
      "salience": 0.0,
      "source_excerpt": "short excerpt",
      "entity_refs": ["exact entity names"]
    }
  ],
  "entities": [
    {
      "name": "exact entity name",
      "category": "character" | "faction" | "place" | "artifact" | "concept",
      "summary": "who/what it is in this chapter",
      "tags": ["tag"],
      "salience": 0.0
    }
  ],
  "relations": [
    {
      "left": "exact left entity name",
      "right": "exact right entity name",
      "relation_type": "short snake_case relation",
      "summary": "what changed or was established",
      "tags": ["tag"],
      "salience": 0.0
    }
  ]
}

Rules:
- Focus on reusable memory only. Skip fluff and style.
- Prefer 1-4 base_items, 0-8 entities, 0-8 relations.
- Use exact names from the text.
- If uncertain, omit rather than hallucinate.
""".strip()


def _truncate(text: str, *, limit: int) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit]


def _split_sentences(text: str, *, limit: int | None = None) -> list[str]:
    parts = [segment.strip() for segment in re.split(r"[。！？!?；;\n]+", text) if segment.strip()]
    if limit is None:
        return parts
    return parts[:limit]


def _coerce_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    results: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            results.append(text)
    return list(dict.fromkeys(results))


def _clamp_salience(value: Any, *, default: float) -> float:
    try:
        salience = float(value)
    except (TypeError, ValueError):
        salience = default
    return max(0.0, min(1.0, salience))


def _canonical_entity_category(value: Any) -> str:
    key = str(value or "").strip().lower()
    return ENTITY_CATEGORY_ALIASES.get(key, "concept")


def _extract_json_object(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, count=1)
        cleaned = re.sub(r"\s*```$", "", cleaned, count=1)

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise RuntimeError("Memory extractor did not return a JSON object.")
    return cleaned[start : end + 1]


def _normalize_base_item(raw_item: dict[str, Any]) -> HarvestBaseItem | None:
    title = str(raw_item.get("title", "")).strip()
    content = str(raw_item.get("content", "")).strip()
    if not title or not content:
        return None

    memory_type = str(raw_item.get("memory_type", "event")).strip().lower()
    if memory_type not in ALLOWED_BASE_TYPES:
        memory_type = "event"

    item: HarvestBaseItem = {
        "memory_type": memory_type,
        "title": title,
        "content": content,
        "tags": _coerce_string_list(raw_item.get("tags", [])),
        "salience": _clamp_salience(raw_item.get("salience"), default=0.72),
        "source_excerpt": str(raw_item.get("source_excerpt", "")).strip() or _truncate(content, limit=220),
        "entity_refs": _coerce_string_list(raw_item.get("entity_refs", [])),
    }
    return item


def _normalize_entity(raw_item: dict[str, Any]) -> HarvestEntity | None:
    name = str(raw_item.get("name", "")).strip()
    if not name:
        return None

    item: HarvestEntity = {
        "name": name,
        "category": _canonical_entity_category(raw_item.get("category")),
        "summary": str(raw_item.get("summary", "")).strip() or name,
        "tags": _coerce_string_list(raw_item.get("tags", [])),
        "salience": _clamp_salience(raw_item.get("salience"), default=0.7),
        "aliases": _coerce_string_list(raw_item.get("aliases", [])),
    }
    return item


def _normalize_relation(raw_item: dict[str, Any]) -> HarvestRelation | None:
    left = str(raw_item.get("left", "")).strip()
    right = str(raw_item.get("right", "")).strip()
    if not left or not right or left == right:
        return None

    relation_type = str(raw_item.get("relation_type", "")).strip().lower() or "related_to"
    relation_type = re.sub(r"[^a-z0-9_]+", "_", relation_type).strip("_") or "related_to"
    summary = str(raw_item.get("summary", "")).strip() or f"{left} {relation_type} {right}"
    item: HarvestRelation = {
        "left": left,
        "right": right,
        "relation_type": relation_type,
        "summary": summary,
        "tags": _coerce_string_list(raw_item.get("tags", [])),
        "salience": _clamp_salience(raw_item.get("salience"), default=0.68),
    }
    return item


def _dedupe_entities(entities: list[HarvestEntity]) -> list[HarvestEntity]:
    merged: dict[str, HarvestEntity] = {}
    order: list[str] = []
    for entity in entities:
        key = entity["name"].casefold()
        existing = merged.get(key)
        if existing is None:
            merged[key] = dict(entity)
            order.append(key)
            continue
        existing["tags"] = list(dict.fromkeys([*existing.get("tags", []), *entity.get("tags", [])]))
        existing["aliases"] = list(dict.fromkeys([*existing.get("aliases", []), *entity.get("aliases", [])]))
        if len(str(entity.get("summary", ""))) > len(str(existing.get("summary", ""))):
            existing["summary"] = str(entity.get("summary", ""))
        existing["salience"] = max(float(existing.get("salience", 0.0)), float(entity.get("salience", 0.0)))
        if existing.get("category") == "concept" and entity.get("category") != "concept":
            existing["category"] = entity.get("category", "concept")
    return [merged[key] for key in order]


def _dedupe_relations(relations: list[HarvestRelation]) -> list[HarvestRelation]:
    merged: dict[tuple[str, str, str], HarvestRelation] = {}
    order: list[tuple[str, str, str]] = []
    for relation in relations:
        key = (
            relation["left"].casefold(),
            relation["right"].casefold(),
            relation["relation_type"],
        )
        existing = merged.get(key)
        if existing is None:
            merged[key] = dict(relation)
            order.append(key)
            continue
        existing["tags"] = list(dict.fromkeys([*existing.get("tags", []), *relation.get("tags", [])]))
        if len(str(relation.get("summary", ""))) > len(str(existing.get("summary", ""))):
            existing["summary"] = str(relation.get("summary", ""))
        existing["salience"] = max(float(existing.get("salience", 0.0)), float(relation.get("salience", 0.0)))
    return [merged[key] for key in order]


def _normalize_sections(raw_sections: dict[str, Any]) -> HarvestSections:
    base_items: list[HarvestBaseItem] = []
    for item in raw_sections.get("base_items", []):
        if not isinstance(item, dict):
            continue
        normalized = _normalize_base_item(item)
        if normalized is not None:
            base_items.append(normalized)

    entities: list[HarvestEntity] = []
    for item in raw_sections.get("entities", []):
        if not isinstance(item, dict):
            continue
        normalized = _normalize_entity(item)
        if normalized is not None:
            entities.append(normalized)

    relations: list[HarvestRelation] = []
    for item in raw_sections.get("relations", []):
        if not isinstance(item, dict):
            continue
        normalized = _normalize_relation(item)
        if normalized is not None:
            relations.append(normalized)

    return {
        "base_items": base_items,
        "entities": _dedupe_entities(entities),
        "relations": _dedupe_relations(relations),
    }


def _candidate_name_counts(text: str) -> Counter[str]:
    counts: Counter[str] = Counter()

    for match in re.findall(r"\b[A-Z][a-zA-Z]{1,20}(?:\s+[A-Z][a-zA-Z]{1,20})?\b", text):
        counts[match.strip()] += 1

    for match in re.findall(r"[\u4e00-\u9fff]{2,4}", text):
        if match in CHINESE_STOP_WORDS:
            continue
        counts[match] += 1

    return counts


def _pick_candidate_names(text: str, *, limit: int) -> list[str]:
    counts = _candidate_name_counts(text)
    candidates: list[str] = []
    for name, count in counts.most_common():
        is_cjk = bool(re.fullmatch(r"[\u4e00-\u9fff]{2,4}", name))
        if is_cjk and count < 2:
            continue
        candidates.append(name)
        if len(candidates) >= limit:
            break
    return candidates


def _classify_candidate(name: str) -> str:
    if name.endswith(LOCATION_HINTS):
        return "place"
    if name.endswith(ARTIFACT_HINTS):
        return "artifact"
    if name.endswith(FACTION_HINTS):
        return "faction"
    return "character"


def _tags_from_text(text: str, *, source_tag: str) -> list[str]:
    tags = [source_tag]
    keyword_map = [
        (("追", "追踪", "跟踪", "尾随", "hunt", "follow"), "pursuit"),
        (("查", "调查", "线索", "search", "investigate"), "investigation"),
        (("战", "打", "冲突", "fight", "attack"), "conflict"),
        (("秘密", "隐瞒", "掩盖", "secret", "hidden"), "secret"),
        (("约束", "规则", "禁令", "rule", "constraint"), "constraint"),
    ]
    lowered = text.lower()
    for needles, tag in keyword_map:
        if any(needle in text or needle in lowered for needle in needles):
            tags.append(tag)
    return list(dict.fromkeys(tags))


def _relation_type_for_sentence(sentence: str) -> str:
    lowered = sentence.lower()
    if any(token in sentence or token in lowered for token in ("调查", "追查", "追踪", "investigate", "follow")):
        return "investigates"
    if any(token in sentence or token in lowered for token in ("冲突", "抢", "争夺", "fight", "attack", "seize")):
        return "conflicts_with"
    if any(token in sentence or token in lowered for token in ("持有", "拿着", "拥有", "holds", "carries", "found")):
        return "holds"
    if any(token in sentence or token in lowered for token in ("位于", "在", "inside", "at")):
        return "located_at"
    return "related_to"


def build_heuristic_harvest_sections(
    state: NovelState,
    *,
    ending: str,
    source_tag: str,
) -> HarvestSections:
    draft = str(state.get("draft", "")).strip()
    approved_recall = str(state.get("approved_rag_recall_summary", "")).strip()
    approved_agenda = str(state.get("approved_chapter_agenda", "")).strip()
    context_parts = [draft, approved_recall, approved_agenda]
    if ending and ending not in draft:
        context_parts.append(ending)
    context_text = "\n".join(part for part in context_parts if part)

    base_items: list[HarvestBaseItem] = []
    for index, sentence in enumerate(_split_sentences(draft, limit=3), start=1):
        entity_refs = [name for name in _pick_candidate_names(sentence, limit=4) if name in sentence]
        base_items.append(
            {
                "memory_type": "event",
                "title": f"chapter_event_{index}",
                "content": sentence,
                "tags": ["event", *(_tags_from_text(sentence, source_tag=source_tag))],
                "salience": max(0.45, 0.86 - index * 0.08),
                "source_excerpt": _truncate(sentence, limit=220),
                "entity_refs": entity_refs,
            }
        )

    if approved_recall:
        base_items.append(
            {
                "memory_type": "fact",
                "title": "approved_recall_constraint",
                "content": approved_recall,
                "tags": ["fact", "approved", *(_tags_from_text(approved_recall, source_tag=source_tag))],
                "salience": 0.78,
                "source_excerpt": _truncate(approved_recall, limit=220),
                "entity_refs": [name for name in _pick_candidate_names(approved_recall, limit=4) if name in approved_recall],
            }
        )

    entities: list[HarvestEntity] = []
    for name in _pick_candidate_names(context_text, limit=8):
        entity_sentence = next((sentence for sentence in _split_sentences(context_text) if name in sentence), "")
        category = _classify_candidate(name)
        entities.append(
            {
                "name": name,
                "category": category,
                "summary": _truncate(entity_sentence or name, limit=220),
                "tags": [source_tag, category],
                "salience": 0.72 if category == "character" else 0.66,
            }
        )

    relations: list[HarvestRelation] = []
    seen_relation_keys: set[tuple[str, str, str]] = set()
    for sentence in _split_sentences(draft):
        names_in_sentence = [entity["name"] for entity in entities if entity["name"] in sentence]
        if len(names_in_sentence) < 2:
            continue
        left = names_in_sentence[0]
        right = names_in_sentence[1]
        relation_type = _relation_type_for_sentence(sentence)
        key = (left.casefold(), right.casefold(), relation_type)
        if key in seen_relation_keys:
            continue
        seen_relation_keys.add(key)
        relations.append(
            {
                "left": left,
                "right": right,
                "relation_type": relation_type,
                "summary": _truncate(sentence, limit=220),
                "tags": [source_tag, relation_type],
                "salience": 0.7,
            }
        )

    if not relations and len(entities) >= 2:
        relations.append(
            {
                "left": entities[0]["name"],
                "right": entities[1]["name"],
                "relation_type": "related_to",
                "summary": f"{entities[0]['name']} appears with {entities[1]['name']} in this chapter",
                "tags": [source_tag, "related_to"],
                "salience": 0.58,
            }
        )

    return _normalize_sections(
        {
            "base_items": base_items,
            "entities": entities,
            "relations": relations,
        }
    )


def _mock_harvest_payload(*, state: NovelState, ending: str) -> str:
    sections = build_heuristic_harvest_sections(state, ending=ending, source_tag="llm-extracted")
    return json.dumps(sections, ensure_ascii=False)


def _build_user_prompt(state: NovelState, *, ending: str) -> str:
    draft = _truncate(str(state.get("draft", "")), limit=2200)
    approved_agenda = _truncate(str(state.get("approved_chapter_agenda", "")), limit=400)
    approved_recall = _truncate(str(state.get("approved_rag_recall_summary", "")), limit=400)
    ending = _truncate(str(ending or ""), limit=180)

    return (
        f"[Novel ID]\n{state.get('novel_id', '')}\n\n"
        f"[Chapter ID]\n{state.get('chapter_id', '')}\n\n"
        f"[Chapter Title]\n{state.get('chapter_title', '')}\n\n"
        f"[Approved Agenda]\n{approved_agenda or '(empty)'}\n\n"
        f"[Approved Recall]\n{approved_recall or '(empty)'}\n\n"
        f"[Previous Ending Hint]\n{ending or '(empty)'}\n\n"
        f"[Draft]\n{draft or '(empty)'}\n"
    )


def extract_harvest_sections_with_llm(state: NovelState, *, ending: str) -> HarvestSections:
    raw_text = generate_text(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=_build_user_prompt(state, ending=ending),
        model_name=str(state.get("model_name") or DEFAULT_MODEL_NAME),
        temperature=float(state.get("temperature", DEFAULT_TEMPERATURE) or DEFAULT_TEMPERATURE),
        max_tokens=DEFAULT_MAX_TOKENS,
        use_mock_llm=bool(state.get("use_mock_llm", False)),
        mock_response_factory=lambda: _mock_harvest_payload(state=state, ending=ending),
    )
    payload = json.loads(_extract_json_object(raw_text))
    if not isinstance(payload, dict):
        raise RuntimeError("Memory extractor returned a non-object payload.")
    return _normalize_sections(payload)
