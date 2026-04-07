from __future__ import annotations

"""
API startup flow (local development):

1. Optional env config:
   - API_HOST (default: 127.0.0.1)
   - API_PORT (default: 8000)
   - GRAPH_STORE_BACKEND (jsonl or neo4j)
   - REVIEW_AUDIT_PATH / CHAPTER_STATE_PATH

2. Start server from repo root:
   python backend/src/novel_assist/cli/run_api.py

3. Verify service:
   - GET /healthz
   - GET /docs

4. HITL API call order:
   - POST /chapters/{chapter_id}/plan
   - GET /chapters/{chapter_id}/review-task
   - POST /chapters/{chapter_id}/review
   - POST /chapters/{chapter_id}/draft
"""

from fastapi import FastAPI, HTTPException

from novel_assist.api.chapter_service import ChapterService
from novel_assist.api.schemas import (
    DraftResponse,
    PlanRequest,
    PlanResponse,
    ReviewRequest,
    ReviewResponse,
    ReviewTaskResponse,
)

app = FastAPI(title="Novel Assist HITL API", version="0.1.0")


@app.middleware("http")
async def ensure_utf8_json_charset(request, call_next):
    # Ensure Invoke-RestMethod and other clients decode Chinese JSON correctly.
    response = await call_next(request) #返回一个response
    content_type = response.headers.get("content-type", "")
    if content_type.startswith("application/json") and "charset=" not in content_type.lower():
        response.headers["content-type"] = "application/json; charset=utf-8"
    return response


@app.get("/")
def root() -> dict[str, object]:
    return {
        "name": "Novel Assist HITL API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/healthz",
        "endpoints": [
            "POST /chapters/{chapter_id}/plan",
            "GET /chapters/{chapter_id}/review-task",
            "POST /chapters/{chapter_id}/review",
            "POST /chapters/{chapter_id}/draft",
        ],
    }


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chapters/{chapter_id}/plan", response_model=PlanResponse)
def create_plan(chapter_id: str, payload: PlanRequest) -> PlanResponse:
    # Step 1 in HITL flow: build agenda + RAG evidence, then wait for human review.
    service = ChapterService()
    state = service.generate_plan(chapter_id=chapter_id, overrides=payload.model_dump())
    return PlanResponse(
        chapter_id=chapter_id,
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
        raise HTTPException(status_code=404, detail="chapter not found")
    return ReviewTaskResponse(**task)


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
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return ReviewResponse(
        chapter_id=chapter_id,
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
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return DraftResponse(
        chapter_id=chapter_id,
        agenda_review_status=str(state.get("agenda_review_status", "")),
        draft=str(state.get("draft", "")),
        draft_word_count=int(state.get("draft_word_count", 0)),
        rewrite_count=int(state.get("rewrite_count", 0)),
        critic_feedback=str(state.get("critic_feedback", "")),
        error=str(state.get("error", "")),
        recall_trace_id=str(state.get("recall_trace_id", "")),
        review_trace_id=str(state.get("review_trace_id", "")),
    )
