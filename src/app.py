from __future__ import annotations

import json
from pathlib import Path

import typer

from src.agents import DetailOutlineAgent, OutlineAgent, WriterAgent
from src.config import get_project_paths, load_local_env
from src.schemas import ReviewDecision, ReviewStatus
from src.schemas.tool_io import RagSearchRequest
from src.storage.markdown_store import MarkdownStore
from src.tools import HumanTool, RagTool
from src.orchestrator.workflow import NovelWorkflow
from src.schemas.project import ProjectBootstrapRequest
from src.storage.state_store import StateStore


app = typer.Typer(no_args_is_help=True, help="Novel generator project CLI.")
load_local_env()


@app.command("init-project")
def init_project(
    project_id: str = typer.Argument(..., help="Stable project identifier."),
    title: str = typer.Option(..., "--title", help="Project title."),
    premise: str = typer.Option("", "--premise", help="Optional premise."),
    genre: str = typer.Option("", "--genre", help="Comma separated genres."),
    tone: str = typer.Option("", "--tone", help="Optional tone."),
) -> None:
    workflow = NovelWorkflow()
    request = ProjectBootstrapRequest(
        project_id=project_id,
        title=title,
        premise=premise or None,
        genre=[item.strip() for item in genre.split(",") if item.strip()],
        tone=tone or None,
    )
    _, state = workflow.create_project(request)
    typer.echo(f"Initialized project '{state.project_id}' at chapter index {state.current_chapter_index}.")


@app.command("show-state")
def show_state(
    project_id: str = typer.Argument(..., help="Stable project identifier."),
) -> None:
    state = StateStore().load_state(project_id)
    typer.echo(json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2))


@app.command("generate-outline")
def generate_outline(
    project_id: str = typer.Argument(..., help="Stable project identifier."),
    brief: str = typer.Option("", "--brief", help="Optional extra story brief for this run."),
    require_review: bool = typer.Option(False, "--require-review", help="Pause for human review after generation."),
) -> None:
    workflow = NovelWorkflow()
    project, state = workflow.load_project(project_id)
    agent = OutlineAgent()
    outline = agent.generate_outline(project=project, extra_brief=brief or None)
    state = workflow.save_outline(project_id, outline)
    if require_review:
        review = HumanTool(project_id, workflow).request_review(
            stage="outline_review",
            reason="Outline review requested before proceeding to detail outlines.",
            payload=outline.model_dump(mode="json"),
            source_status=state.status.value,
            source_stage=state.current_stage.value,
        )
        typer.echo(
            f"Saved outline to {get_project_paths(project_id).outline_file} and opened review {review.review_id} "
            f"at {review.payload_file}."
        )
        return
    outline_path = get_project_paths(project_id).outline_file
    typer.echo(
        f"Saved outline to {outline_path} with outline_version={state.outline_version} and status={state.status.value}."
    )


@app.command("show-outline")
def show_outline(
    project_id: str = typer.Argument(..., help="Stable project identifier."),
) -> None:
    outline_path = Path(get_project_paths(project_id).outline_file)
    typer.echo(outline_path.read_text(encoding="utf-8"))


@app.command("generate-detail-outline")
def generate_detail_outline(
    project_id: str = typer.Argument(..., help="Stable project identifier."),
    chapter_id: int = typer.Option(0, "--chapter-id", help="Target chapter id. Defaults to the current pending chapter."),
    brief: str = typer.Option("", "--brief", help="Optional extra chapter guidance for this run."),
    require_review: bool = typer.Option(False, "--require-review", help="Pause for human review after generation."),
) -> None:
    workflow = NovelWorkflow()
    project, state = workflow.load_project(project_id)
    outline = workflow.load_outline(project_id)
    agent = DetailOutlineAgent()
    target_chapter_id = chapter_id or workflow.resolve_default_detail_chapter_id(state)
    detail_outline = agent.generate_detail_outline(
        project=project,
        state=state,
        outline=outline,
        chapter_id=target_chapter_id,
        extra_brief=brief or None,
    )
    state = workflow.save_detail_outline(project_id, detail_outline)
    detail_path = get_project_paths(project_id).detail_outlines_dir / f"{detail_outline.chapter_id:04d}.json"
    if require_review:
        review = HumanTool(project_id, workflow).request_review(
            stage="detail_outline_review",
            reason=f"Detail outline review requested for chapter {detail_outline.chapter_id}.",
            payload=detail_outline.model_dump(mode="json"),
            source_status=state.status.value,
            source_stage=state.current_stage.value,
            target_chapter_id=detail_outline.chapter_id,
        )
        typer.echo(
            f"Saved detail outline for chapter {detail_outline.chapter_id} to {detail_path} and opened review "
            f"{review.review_id} at {review.payload_file}."
        )
        return
    typer.echo(
        f"Saved detail outline for chapter {detail_outline.chapter_id} to {detail_path} "
        f"with detail_outline_version={state.detail_outline_version} and status={state.status.value}."
    )


@app.command("show-detail-outline")
def show_detail_outline(
    project_id: str = typer.Argument(..., help="Stable project identifier."),
    chapter_id: int = typer.Option(0, "--chapter-id", help="Target chapter id. Defaults to the current pending chapter."),
) -> None:
    workflow = NovelWorkflow()
    _, state = workflow.load_project(project_id)
    target_chapter_id = chapter_id or workflow.resolve_default_detail_chapter_id(state)
    detail_outline = workflow.load_detail_outline(project_id, target_chapter_id)
    typer.echo(json.dumps(detail_outline.model_dump(mode="json"), ensure_ascii=False, indent=2))


@app.command("write-chapter")
def write_chapter(
    project_id: str = typer.Argument(..., help="Stable project identifier."),
    chapter_id: int = typer.Option(0, "--chapter-id", help="Target chapter id. Defaults to the current pending chapter."),
    brief: str = typer.Option("", "--brief", help="Optional extra guidance for this write run."),
    require_review: bool = typer.Option(False, "--require-review", help="Pause for human review before archive."),
) -> None:
    workflow = NovelWorkflow()
    project, state = workflow.load_project(project_id)
    target_chapter_id = chapter_id or workflow.resolve_default_detail_chapter_id(state)
    detail_outline = workflow.load_detail_outline(project_id, target_chapter_id)
    agent = WriterAgent()
    chapter = agent.write_chapter(
        project=project,
        detail_outline=detail_outline,
        extra_brief=brief or None,
    )
    if require_review:
        preview_markdown = workflow.markdown_store.render_chapter_markdown(
            chapter=chapter,
            outline_version=state.outline_version,
            detail_outline_version=state.detail_outline_version,
        )
        review = HumanTool(project_id, workflow).request_review(
            stage="chapter_review",
            reason=f"Chapter review requested for chapter {chapter.chapter_id}.",
            payload=chapter.model_dump(mode="json"),
            source_status=state.status.value,
            source_stage=state.current_stage.value,
            target_chapter_id=chapter.chapter_id,
            preview_markdown=preview_markdown,
        )
        typer.echo(
            f"Generated chapter {chapter.chapter_id} draft and opened review {review.review_id} "
            f"at {review.preview_file or review.payload_file}."
        )
        return
    state = workflow.archive_chapter(project_id, chapter)
    ingest_result = RagTool(project_id).ingest_archived_chapter(chapter.chapter_id)
    chapter_path = get_project_paths(project_id).chapters_dir / f"{chapter.chapter_id:04d}.md"
    typer.echo(
        f"Saved chapter {chapter.chapter_id} to {chapter_path} "
        f"with status={state.status.value}, next_stage={state.current_stage.value}, "
        f"chunk_count={ingest_result.chunk_count}, total_indexed_chunks={ingest_result.total_indexed_chunks}."
    )


@app.command("show-chapter")
def show_chapter(
    project_id: str = typer.Argument(..., help="Stable project identifier."),
    chapter_id: int = typer.Option(..., "--chapter-id", help="Target chapter id."),
) -> None:
    chapter_path = Path(get_project_paths(project_id).chapters_dir / f"{chapter_id:04d}.md")
    typer.echo(chapter_path.read_text(encoding="utf-8"))


@app.command("ingest-chapter")
def ingest_chapter(
    project_id: str = typer.Argument(..., help="Stable project identifier."),
    chapter_id: int = typer.Option(..., "--chapter-id", help="Archived chapter id to ingest."),
) -> None:
    result = RagTool(project_id).ingest_archived_chapter(chapter_id)
    typer.echo(
        f"Ingested chapter {result.chapter_id} with chunk_count={result.chunk_count} "
        f"and total_indexed_chunks={result.total_indexed_chunks}."
    )


@app.command("rebuild-rag")
def rebuild_rag(
    project_id: str = typer.Argument(..., help="Stable project identifier."),
) -> None:
    results = RagTool(project_id).rebuild_from_archives()
    total_chunks = results[-1].total_indexed_chunks if results else 0
    typer.echo(
        f"Rebuilt RAG for {project_id} from {len(results)} archived chapters with total_indexed_chunks={total_chunks}."
    )


@app.command("rag-search")
def rag_search(
    project_id: str = typer.Argument(..., help="Stable project identifier."),
    query: str = typer.Argument(..., help="Natural-language query."),
    top_k: int = typer.Option(5, "--top-k", help="Number of hits to return."),
    search_mode: str = typer.Option("hybrid", "--search-mode", help="hybrid | dense | sparse"),
    chapter_from: int = typer.Option(0, "--chapter-from", help="Optional inclusive chapter lower bound."),
    chapter_to: int = typer.Option(0, "--chapter-to", help="Optional inclusive chapter upper bound."),
    entity: list[str] = typer.Option(None, "--entity", help="Optional entity filters; can be repeated."),
) -> None:
    chapter_scope = None
    if chapter_from > 0 and chapter_to > 0:
        chapter_scope = (chapter_from, chapter_to)
    request = RagSearchRequest(
        query=query,
        top_k=top_k,
        search_mode=search_mode,
        chapter_scope=chapter_scope,
        entity_filter=entity or [],
    )
    result = RagTool(project_id).search(request)
    typer.echo(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))


@app.command("request-review")
def request_review(
    project_id: str = typer.Argument(..., help="Stable project identifier."),
    stage: str = typer.Option(..., "--stage", help="outline_review | detail_outline_review | chapter_review"),
    reason: str = typer.Option(..., "--reason", help="Why this review is being requested."),
    chapter_id: int = typer.Option(0, "--chapter-id", help="Target chapter id for detail/chapter review."),
) -> None:
    workflow = NovelWorkflow()
    _, state = workflow.load_project(project_id)
    tool = HumanTool(project_id, workflow)

    if stage == "outline_review":
        outline = workflow.load_outline(project_id)
        review = tool.request_review(
            stage=stage,
            reason=reason,
            payload=outline.model_dump(mode="json"),
            source_status=state.status.value,
            source_stage=state.current_stage.value,
        )
    elif stage == "detail_outline_review":
        if chapter_id <= 0:
            chapter_id = workflow.resolve_default_detail_chapter_id(state)
        detail_outline = workflow.load_detail_outline(project_id, chapter_id)
        review = tool.request_review(
            stage=stage,
            reason=reason,
            payload=detail_outline.model_dump(mode="json"),
            source_status=state.status.value,
            source_stage=state.current_stage.value,
            target_chapter_id=chapter_id,
        )
    elif stage == "chapter_review":
        if chapter_id <= 0:
            raise typer.BadParameter("chapter_review requires --chapter-id.")
        chapter = MarkdownStore().load_chapter_artifact(project_id, chapter_id)
        preview_markdown = MarkdownStore().render_chapter_markdown(
            chapter=chapter,
            outline_version=state.outline_version,
            detail_outline_version=state.detail_outline_version,
        )
        review = tool.request_review(
            stage=stage,
            reason=reason,
            payload=chapter.model_dump(mode="json"),
            source_status=state.status.value,
            source_stage=state.current_stage.value,
            target_chapter_id=chapter_id,
            preview_markdown=preview_markdown,
        )
    else:
        raise typer.BadParameter("stage must be one of: outline_review, detail_outline_review, chapter_review")

    typer.echo(
        f"Opened review {review.review_id} for stage={review.stage} at "
        f"{review.preview_file or review.payload_file}."
    )


@app.command("list-reviews")
def list_reviews(
    project_id: str = typer.Argument(..., help="Stable project identifier."),
    status: str = typer.Option("", "--status", help="Optional filter: pending | resolved"),
) -> None:
    tool = HumanTool(project_id)
    parsed_status = ReviewStatus(status) if status else None
    reviews = tool.list_reviews(parsed_status)
    typer.echo(json.dumps([review.model_dump(mode="json") for review in reviews], ensure_ascii=False, indent=2))


@app.command("show-review")
def show_review(
    project_id: str = typer.Argument(..., help="Stable project identifier."),
    review_id: str = typer.Option(..., "--review-id", help="Review identifier."),
) -> None:
    review = HumanTool(project_id).get_review(review_id)
    typer.echo(json.dumps(review.model_dump(mode="json"), ensure_ascii=False, indent=2))


@app.command("resolve-review")
def resolve_review(
    project_id: str = typer.Argument(..., help="Stable project identifier."),
    review_id: str = typer.Option(..., "--review-id", help="Review identifier."),
    decision: str = typer.Option(..., "--decision", help="approve | reject"),
    instruction: str = typer.Option("", "--instruction", help="Optional operator instruction."),
    edited_file: str = typer.Option("", "--edited-file", help="Optional edited .json or .md file."),
    operator: str = typer.Option("user", "--operator", help="Operator name."),
) -> None:
    record = HumanTool(project_id).resolve_review(
        review_id=review_id,
        decision=ReviewDecision(decision),
        instruction=instruction or None,
        edited_file=edited_file or None,
        operator=operator,
    )
    typer.echo(
        f"Resolved review {record.review_id} with decision={record.resolution.approved if record.resolution else 'unknown'} "
        f"and status={record.status.value}."
    )


def run() -> None:
    app()


if __name__ == "__main__":
    run()
