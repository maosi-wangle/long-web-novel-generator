from __future__ import annotations

import os
from collections.abc import Callable

from dotenv import load_dotenv
from openai import OpenAI

DEFAULT_TIMEOUT_SECONDS = 90.0
DEFAULT_MAX_RETRIES = 2
RETRYABLE_ERROR_NAMES = {"APITimeoutError", "APIConnectionError"}


def generate_text(
    *,
    system_prompt: str,
    user_prompt: str,
    model_name: str,
    temperature: float,
    max_tokens: int,
    use_mock_llm: bool,
    mock_response_factory: Callable[[], str] | None = None,
    timeout_seconds: float | None = None,
    max_retries: int | None = None,
    strip_output: bool = True,
) -> str:
    """Run a shared text-generation request with env loading and light retries."""
    if use_mock_llm:
        if mock_response_factory is None:
            raise RuntimeError("Mock LLM mode requires a mock response factory.")
        return mock_response_factory()

    load_dotenv()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not configured.")
    if not base_url:
        raise RuntimeError("LLM_BASE_URL is not configured.")

    resolved_timeout = timeout_seconds
    if resolved_timeout is None:
        resolved_timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))

    resolved_retries = max_retries
    if resolved_retries is None:
        resolved_retries = int(os.getenv("LLM_MAX_RETRIES", str(DEFAULT_MAX_RETRIES)))

    client = OpenAI(api_key=api_key, base_url=base_url, max_retries=resolved_retries)
    last_error: Exception | None = None

    for _ in range(resolved_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=resolved_timeout,
            )
            content = response.choices[0].message.content
            if not content:
                raise RuntimeError("LLM returned an empty response.")
            return content.strip() if strip_output else content
        except Exception as exc:
            last_error = exc
            if type(exc).__name__ not in RETRYABLE_ERROR_NAMES:
                raise

    raise RuntimeError(f"LLM request failed after retries: {last_error}")
