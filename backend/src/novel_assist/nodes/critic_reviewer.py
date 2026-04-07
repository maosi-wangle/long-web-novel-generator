from __future__ import annotations

import os
import re
from typing import Any

from novel_assist.state.novel_state import NovelState


def _contains_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


def critic_node(state: NovelState) -> dict[str, Any]:
    """Validate draft against high-level constraints and manage rewrite counter."""
    draft = state.get("draft", "")
    world_rules = state.get("world_rules", "")
    future_waypoints = state.get("future_waypoints", "")
    rewrite_count = int(state.get("rewrite_count", 0))

    force_fail = os.getenv("CRITIC_FORCE_FAIL", "0").strip().lower() in {"1", "true", "yes", "on"}
    violations: list[str] = []

    if force_fail:
        violations.append("测试开关触发：CRITIC_FORCE_FAIL=1。")

    # Detect actual teleport behavior, not quoted constraints like "不能瞬移".
    if world_rules and "不能瞬移" in world_rules and _contains_any(
        draft, [r"(?<!不能)瞬移", r"(?<!不能)闪现", r"一个瞬移", r"施展瞬移"]
    ):
        violations.append("违背世界规则：检测到“不能瞬移”约束冲突。")

    if future_waypoints and "不能在本章死亡" in future_waypoints:
        # Detect concrete death events, not mention of constraints.
        if _contains_any(
            draft,
            [
                r"跟踪者.{0,8}(被杀|毙命|身亡|死去|当场死亡|倒地而亡)",
                r"(杀死了|击毙了|处决了).{0,8}跟踪者",
            ],
        ):
            violations.append("违背未来约束：关键角色被提前写死。")

    if violations:
        next_count = rewrite_count + 1
        return {
            "error": "CriticRejected: " + "；".join(violations),
            "critic_feedback": "\n".join(f"- {item}" for item in violations),
            "rewrite_count": next_count,
        }

    return {
        "error": "",
        "critic_feedback": "CriticPassed: 未发现规则冲突。",
        "rewrite_count": rewrite_count,
    }
