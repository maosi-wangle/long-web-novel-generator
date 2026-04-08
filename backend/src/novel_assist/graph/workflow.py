from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from novel_assist.nodes.critic_reviewer import critic_node
from novel_assist.nodes.draft_writer import draft_writer_node
from novel_assist.nodes.human_review_gate import human_agenda_review_gate
from novel_assist.nodes.memory_harvester import memory_harvester_node
from novel_assist.nodes.plot_planner import plotting_node
from novel_assist.nodes.rag_recall import rag_recall_node
from novel_assist.state.novel_state import NovelState
from novel_assist.state.routing import route_after_critic, route_after_human_review


def build_workflow_app():
    """Build phase-2 backend MVP workflow."""
    workflow = StateGraph(NovelState)

    workflow.add_node("PlotPlanner", plotting_node)
    workflow.add_node("RagRecall", rag_recall_node)
    workflow.add_node("HumanAgendaReview", human_agenda_review_gate)
    workflow.add_node("DraftWriter", draft_writer_node)
    workflow.add_node("CriticReviewer", critic_node)
    workflow.add_node("MemoryHarvester", memory_harvester_node)

    workflow.add_edge(START, "PlotPlanner")
    workflow.add_edge("PlotPlanner", "RagRecall")
    workflow.add_edge("RagRecall", "HumanAgendaReview")

    # For synchronous invoke(), pending review should stop this run and wait for UI/API callback.
    workflow.add_conditional_edges(
        "HumanAgendaReview",
        route_after_human_review,
        {
            "NeedHumanReview": END,
            "Rejected": "PlotPlanner",
            "Approved": "DraftWriter",
        },
    )

    workflow.add_edge("DraftWriter", "CriticReviewer")
    workflow.add_conditional_edges(
        "CriticReviewer",
        route_after_critic,
        {
            "Rejected": "DraftWriter",
            "Approved": "MemoryHarvester",
            "Abort": END,
            # Defensive mapping: this route is not expected from route_after_critic.
            "NeedHumanReview": END,
        },
    )

    workflow.add_edge("MemoryHarvester", END)
    return workflow.compile()
