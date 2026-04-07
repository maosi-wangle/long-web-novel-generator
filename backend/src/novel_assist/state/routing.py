from __future__ import annotations

from novel_assist.state.novel_state import NovelState, RouteDecision


def route_after_human_review(state: NovelState) -> RouteDecision:
    """Decide whether to continue after the human agenda review gate."""
    status = state.get("agenda_review_status", "pending")
    if status in {"pending", "edited"}:
        return "NeedHumanReview"
    if status == "rejected":
        return "Rejected"
    return "Approved"


def route_after_critic(state: NovelState) -> RouteDecision:
    """Decide whether to rewrite, proceed, or abort after critic check."""
    if state.get("error"):
        if state.get("rewrite_count", 0) >= state.get("max_rewrites", 3):
            return "Abort"
        return "Rejected"
    return "Approved"
