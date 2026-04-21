from __future__ import annotations

from src.orchestrator.workflow import NovelWorkflow


class WorkflowEngine:
    """Thin wrapper reserved for future orchestration policies and retries."""

    def __init__(self, workflow: NovelWorkflow | None = None) -> None:
        self.workflow = workflow or NovelWorkflow()

