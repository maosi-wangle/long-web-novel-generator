from __future__ import annotations

"""
API startup flow (local development):

1. Optional env config:
   - API_HOST (default: 127.0.0.1)
   - API_PORT (default: 8000)
   - GRAPH_STORE_BACKEND (jsonl or neo4j)
   - REVIEW_AUDIT_PATH / CHAPTER_STATE_PATH / NOVEL_STATE_PATH

2. Start server from repo root:
   python backend/src/novel_assist/cli/run_api.py

3. Verify service:
   - GET /
   - GET /healthz
   - GET /workbench
   - GET /novels

4. HITL API call order:
   - POST /chapters/{chapter_id}/plan
   - GET /chapters/{chapter_id}/review-task
   - POST /chapters/{chapter_id}/review
   - POST /chapters/{chapter_id}/draft
"""

from pathlib import Path

from fastapi.encoders import jsonable_encoder
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from novel_assist.api.chapter_service import ChapterService
from novel_assist.api.schemas import (
    ApiErrorResponse,
    ChapterListResponse,
    ChapterStateResponse,
    CreateNovelRequest,
    DraftResponse,
    NovelListResponse,
    NovelSummary,
    PlanRequest,
    PlanResponse,
    ReviewRequest,
    ReviewResponse,
    ReviewTaskResponse,
)

app = FastAPI(title="Novel Assist HITL API", version="0.1.0")
WORKBENCH_PATH = Path(__file__).with_name("workbench.html")


class ApiErrorException(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        error_code: str,
        message: str,
        detail: object = None,
        trace_id: str = "",
    ) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.detail = detail
        self.trace_id = trace_id
        super().__init__(message)


def _error_payload(exc: ApiErrorException) -> dict[str, object]:
    payload = ApiErrorResponse(
        error_code=exc.error_code,
        message=exc.message,
        detail=exc.detail,
        trace_id=exc.trace_id,
    )
    return payload.model_dump()


@app.middleware("http")
async def ensure_utf8_json_charset(request: Request, call_next):
    # Ensure browser/fetch/Invoke-RestMethod decode Chinese JSON consistently.
    response = await call_next(request)
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("application/json") and "charset=" not in content_type.lower():
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response


@app.exception_handler(ApiErrorException)
async def handle_api_error(_: Request, exc: ApiErrorException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=_error_payload(exc))


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    payload = ApiErrorResponse(
        error_code="REQUEST_VALIDATION_ERROR",
        message="Request validation failed.",
        detail=jsonable_encoder(exc.errors()),
    )
    return JSONResponse(status_code=422, content=payload.model_dump())


@app.get("/")
def root() -> dict[str, object]:
    return {
        "name": "Novel Assist HITL API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/healthz",
        "workbench": "/workbench",
        "endpoints": [
            "GET /novels",
            "POST /novels",
            "GET /novels/{novel_id}/chapters",
            "POST /chapters/{chapter_id}/plan",
            "GET /chapters/{chapter_id}/review-task",
            "POST /chapters/{chapter_id}/review",
            "POST /chapters/{chapter_id}/draft",
            "GET /chapters/{chapter_id}/state",
        ],
    }


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/workbench", response_class=HTMLResponse)
def workbench() -> HTMLResponse:
    return HTMLResponse(WORKBENCH_PATH.read_text(encoding="utf-8"))


@app.get("/novels", response_model=NovelListResponse)
def list_novels() -> NovelListResponse:
    service = ChapterService()
    return NovelListResponse(novels=service.list_novels())


@app.post("/novels", response_model=NovelSummary)
def create_novel(payload: CreateNovelRequest) -> NovelSummary:
    service = ChapterService()
    try:
        novel = service.create_novel(novel_id=payload.novel_id, novel_title=payload.novel_title)
    except FileExistsError as exc:
        raise ApiErrorException(
            status_code=409,
            error_code="NOVEL_ALREADY_EXISTS",
            message="Novel already exists.",
            detail={"novel_id": payload.novel_id, "reason": str(exc)},
        ) from exc

    return NovelSummary(**novel)


@app.get("/novels/{novel_id}/chapters", response_model=ChapterListResponse)
def list_chapters(novel_id: str) -> ChapterListResponse:
    service = ChapterService()
    return ChapterListResponse(**service.list_chapters(novel_id=novel_id))


@app.post("/chapters/{chapter_id}/plan", response_model=PlanResponse)
def create_plan(chapter_id: str, payload: PlanRequest) -> PlanResponse:
    # Step 1 in HITL flow: build agenda + RAG evidence, then wait for human review.
    service = ChapterService()
    state = service.generate_plan(chapter_id=chapter_id, overrides=payload.model_dump())
    return PlanResponse(
        novel_id=str(state.get("novel_id", "")),
        novel_title=str(state.get("novel_title", "")),
        chapter_id=chapter_id,
        chapter_number=state.get("chapter_number"),
        chapter_title=str(state.get("chapter_title", "")),
        chapter_status=str(state.get("chapter_status", "")),
        chapter_agenda=str(state.get("chapter_agenda", "")),
        rag_recall_summary=str(state.get("rag_recall_summary", "")),
        rag_evidence=list(state.get("rag_evidence", [])),
        agenda_review_status=str(state.get("agenda_review_status", "pending")),
        recall_trace_id=str(state.get("recall_trace_id", "")),
        audit_log_path=str(state.get("audit_log_path", "")),
        audit_warning=str(state.get("audit_warning", "")),
    )


@app.get("/chapters/{chapter_id}/review-task", response_model=ReviewTaskResponse)
def get_review_task(chapter_id: str) -> ReviewTaskResponse:
    # Step 2: fetch review task and evidence chain for UI/Editor.
    service = ChapterService()
    task = service.get_review_task(chapter_id=chapter_id)
    if not task:
        raise ApiErrorException(
            status_code=404,
            error_code="CHAPTER_NOT_FOUND",
            message="Chapter review task not found.",
            detail={"chapter_id": chapter_id},
        )
    return ReviewTaskResponse(**task)


@app.get("/chapters/{chapter_id}/state", response_model=ChapterStateResponse)
def get_chapter_state(chapter_id: str) -> ChapterStateResponse:
    service = ChapterService()
    state = service.get_chapter_state(chapter_id=chapter_id)
    if not state:
        raise ApiErrorException(
            status_code=404,
            error_code="CHAPTER_NOT_FOUND",
            message="Chapter state not found.",
            detail={"chapter_id": chapter_id},
        )
    return ChapterStateResponse(chapter_id=chapter_id, state=state)


@app.post("/chapters/{chapter_id}/review", response_model=ReviewResponse)
def submit_review(chapter_id: str, payload: ReviewRequest) -> ReviewResponse:
    # Step 3: save human review decision and approved agenda/summary.
    service = ChapterService()
    try:
        state = service.submit_review(
            chapter_id=chapter_id,
            agenda_review_status=payload.agenda_review_status,
            agenda_review_notes=payload.agenda_review_notes,
            approved_chapter_agenda=payload.approved_chapter_agenda,
            approved_rag_recall_summary=payload.approved_rag_recall_summary,
        )
    except KeyError as exc:
        raise ApiErrorException(
            status_code=404,
            error_code="CHAPTER_NOT_FOUND",
            message="Cannot submit review because chapter state does not exist.",
            detail={"chapter_id": chapter_id, "reason": str(exc)},
        ) from exc

    return ReviewResponse(
        novel_id=str(state.get("novel_id", "")),
        novel_title=str(state.get("novel_title", "")),
        chapter_id=chapter_id,
        chapter_number=state.get("chapter_number"),
        chapter_title=str(state.get("chapter_title", "")),
        chapter_status=str(state.get("chapter_status", "")),
        agenda_review_status=str(state.get("agenda_review_status", "")),
        agenda_review_notes=str(state.get("agenda_review_notes", "")),
        approved_chapter_agenda=str(state.get("approved_chapter_agenda", "")),
        approved_rag_recall_summary=str(state.get("approved_rag_recall_summary", "")),
        review_trace_id=str(state.get("review_trace_id", "")),
        recall_trace_id=str(state.get("recall_trace_id", "")),
        audit_log_path=str(state.get("audit_log_path", "")),
        audit_warning=str(state.get("audit_warning", "")),
    )


@app.post("/chapters/{chapter_id}/draft", response_model=DraftResponse)
def create_draft(chapter_id: str) -> DraftResponse:
    # Step 4: server-side gate keeps draft generation blocked unless approved.
    service = ChapterService()
    try:
        state = service.generate_draft(chapter_id=chapter_id)
    except KeyError as exc:
        raise ApiErrorException(
            status_code=404,
            error_code="CHAPTER_NOT_FOUND",
            message="Cannot generate draft because chapter state does not exist.",
            detail={"chapter_id": chapter_id, "reason": str(exc)},
        ) from exc
    except PermissionError as exc:
        raise ApiErrorException(
            status_code=409,
            error_code="HUMAN_REVIEW_REQUIRED",
            message="Draft generation is blocked until the chapter review is approved.",
            detail={"chapter_id": chapter_id, "reason": str(exc)},
        ) from exc

    return DraftResponse(
        novel_id=str(state.get("novel_id", "")),
        novel_title=str(state.get("novel_title", "")),
        chapter_id=chapter_id,
        chapter_number=state.get("chapter_number"),
        chapter_title=str(state.get("chapter_title", "")),
        chapter_status=str(state.get("chapter_status", "")),
        agenda_review_status=str(state.get("agenda_review_status", "")),
        draft=str(state.get("draft", "")),
        draft_word_count=int(state.get("draft_word_count", 0)),
        rewrite_count=int(state.get("rewrite_count", 0)),
        critic_feedback=str(state.get("critic_feedback", "")),
        error=str(state.get("error", "")),
        recall_trace_id=str(state.get("recall_trace_id", "")),
        review_trace_id=str(state.get("review_trace_id", "")),
    )
