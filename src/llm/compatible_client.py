from __future__ import annotations
from dataclasses import dataclass
from typing import Any, TypeVar

import instructor
from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, OpenAIError
from pydantic import BaseModel

from src.config import LLMSettings, get_llm_settings


class LLMResponseError(RuntimeError):
    pass


ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass
class CompatibleLLMClient:
    settings: LLMSettings | None = None

    def __post_init__(self) -> None:
        if self.settings is None:
            self.settings = get_llm_settings()
        assert self.settings is not None
        self._raw_client = OpenAI(
            api_key=self.settings.api_key,
            base_url=self.settings.base_url,
        )
        self._structured_client = instructor.patch(self._raw_client, mode=instructor.Mode.JSON)

    def chat(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        try:
            response = self._raw_client.chat.completions.create(**payload)
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMResponseError(f"LLM network error: {exc}") from exc
        except (APIError, OpenAIError) as exc:
            raise LLMResponseError(f"LLM API error: {exc}") from exc
        try:
            content = response.choices[0].message.content
            if isinstance(content, list):
                return "".join(
                    item.text for item in content if getattr(item, "type", None) == "text" and getattr(item, "text", None)
                )
            if not content:
                raise LLMResponseError("LLM returned empty content.")
            return content
        except (AttributeError, IndexError, TypeError) as exc:
            raise LLMResponseError(f"Unexpected LLM response shape: {response}") from exc

    def chat_model(
        self,
        *,
        model: str,
        response_model: type[ModelT],
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 4000,
        max_retries: int = 2,
    ) -> ModelT:
        payload = {
            "model": model,
            "response_model": response_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "max_retries": max_retries,
        }
        try:
            return self._structured_client.chat.completions.create(**payload)
        except (APIConnectionError, APITimeoutError) as exc:
            raise LLMResponseError(f"LLM network error: {exc}") from exc
        except (APIError, OpenAIError) as exc:
            raise LLMResponseError(f"LLM API error: {exc}") from exc
