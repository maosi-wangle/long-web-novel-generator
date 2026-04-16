from __future__ import annotations

import os
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from novel_assist.state.novel_state import NovelState

DEFAULT_AGENDA = "主角在黑市追踪线索，确认议会势力正在回收关键证物。"
DEFAULT_MODEL_NAME = "qwen3-max-preview"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_TIMEOUT_SECONDS = 90.0
DEFAULT_MAX_RETRIES = 2

SYSTEM_PROMPT = """你是小说策划智能体。
你的任务不是直接写正文，而是为当前章节生成一条可执行的章节细纲。

要求：
1. 细纲必须与世界规则、当前剧情弧线、未来路标保持一致。
2. 只输出一段细纲文本，不要解释，不要分点，不要加标题。
3. 如果输入里已有作者草案，要在尊重原意的基础上润色和补足冲突张力。
4. 如果有人工驳回意见，必须吸收这些意见后再生成新的细纲。
5. 细纲只需要大致框架即可，不要写得过于细节"""


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def build_plot_prompt(state: NovelState) -> str:
    current_agenda = str(state.get("chapter_agenda_draft") or DEFAULT_AGENDA)
    global_outline = str(state.get("global_outline", "") or "未提供全书总纲")
    current_arc = str(state.get("current_arc", "") or "未提供当前剧情弧线")
    current_phase = str(state.get("current_phase", "") or "起")
    memory_l0 = str(state.get("memory_l0", "") or "未提供近程记忆")
    previous_chapter_ending = str(state.get("previous_chapter_ending", "") or "未提供上一章结尾")
    world_rules = str(state.get("world_rules", "") or "未提供世界规则")
    future_waypoints = str(state.get("future_waypoints", "") or "未提供未来路标")
    guidance_from_future = str(state.get("guidance_from_future", "") or "未提供来自未来的约束")
    review_status = str(state.get("agenda_review_status", "pending"))
    review_notes = str(state.get("agenda_review_notes", "")).strip() or "无"

    return (
        f"[章节细纲草案]\n{current_agenda}\n\n"
        f"[全书总纲]\n{global_outline}\n\n"
        f"[当前剧情弧线]\n{current_arc}\n\n"
        f"[当前节奏阶段]\n{current_phase}\n\n"
        f"[近程记忆]\n{memory_l0}\n\n"
        f"[上一章结尾]\n{previous_chapter_ending}\n\n"
        f"[世界规则]\n{world_rules}\n\n"
        f"[未来路标]\n{future_waypoints}\n\n"
        f"[来自未来的约束]\n{guidance_from_future}\n\n"
        f"[当前审核状态]\n{review_status}\n\n"
        f"[人工驳回/编辑意见]\n{review_notes}\n\n"
        "请基于以上信息生成本章细纲。"
    )


def _mock_plot_response(state: NovelState) -> str:
    seed = str(state.get("chapter_agenda_draft") or DEFAULT_AGENDA).strip()
    phase = str(state.get("current_phase", "起") or "起")
    review_notes = str(state.get("agenda_review_notes", "")).strip()
    if review_notes:
        return f"{seed} 本章保持“{phase}”段推进，并吸收人工意见：{review_notes}"
    return f"{seed} 本章保持“{phase}”段推进，强化冲突、目标与阻碍。"


def call_llm(
    *,
    state: NovelState,
    prompt: str,
    model_name: str,
    temperature: float,
    use_mock_llm: bool,
) -> str:
    if use_mock_llm:
        return _mock_plot_response(state)

    load_dotenv()
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")

    if not api_key:
        raise RuntimeError("LLM_API_KEY 未配置。")
    if not base_url:
        raise RuntimeError("LLM_BASE_URL 未配置。")

    timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    max_retries = int(os.getenv("LLM_MAX_RETRIES", str(DEFAULT_MAX_RETRIES)))
    client = OpenAI(api_key=api_key, base_url=base_url, max_retries=max_retries)

    last_error: Exception | None = None
    for _ in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=600,
                timeout=timeout_seconds,
            )
            content = response.choices[0].message.content
            if not content:
                raise RuntimeError("模型返回空内容。")
            return content.strip()
        except Exception as exc:
            last_error = exc
            error_name = type(exc).__name__
            if error_name not in {"APITimeoutError", "APIConnectionError"}:
                raise

    raise RuntimeError(f"调用模型失败，重试后仍超时或连接失败：{last_error}")


def plotting_node(state: NovelState) -> dict[str, Any]:
    """Create or refresh chapter agenda candidates before human review."""
    prompt = build_plot_prompt(state)
    use_mock_llm = bool(state.get("use_mock_llm", False))
    model_name = str(state.get("model_name", DEFAULT_MODEL_NAME))
    temperature = float(state.get("temperature", DEFAULT_TEMPERATURE))

    try:
        next_agenda = call_llm(
            state=state,
            prompt=prompt,
            model_name=model_name,
            temperature=temperature,
            use_mock_llm=use_mock_llm,
        )
        return {
            "chapter_agenda": next_agenda,
            "agenda_review_status": "pending",
            "agenda_review_notes": "",
            "approved_chapter_agenda": "",
            "approved_rag_recall_summary": "",
            "error": "",
        }
    except Exception as exc:
        return {
            "chapter_agenda": str(state.get("chapter_agenda_draft") or DEFAULT_AGENDA),
            "agenda_review_status": "pending",
            "agenda_review_notes": "",
            "approved_chapter_agenda": "",
            "approved_rag_recall_summary": "",
            "error": f"{type(exc).__name__}: {exc}",
        }
