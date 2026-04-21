from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib import error, request

from src.config import LLMSettings, get_llm_settings


class LLMResponseError(RuntimeError):
    pass


@dataclass
class CompatibleLLMClient:
    settings: LLMSettings | None = None

    def __post_init__(self) -> None:
        if self.settings is None:
            self.settings = get_llm_settings()

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
        response = self._post_json("/chat/completions", payload)
        try:
            return response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(f"Unexpected LLM response shape: {response}") from exc

    def chat_json(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 4000,
    ) -> dict[str, Any]:
        content = self.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return self._extract_json(content)

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.settings is not None
        endpoint = f"{self.settings.base_url.rstrip('/')}{path}"
        raw_payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            endpoint,
            data=raw_payload,
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=120) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise LLMResponseError(f"LLM HTTP error {exc.code}: {body}") from exc
        except error.URLError as exc:
            raise LLMResponseError(f"LLM network error: {exc.reason}") from exc

    def _extract_json(self, content: str) -> dict[str, Any]:
        content = content.strip()
        if content.startswith("```"):
            lines = content.splitlines()
            if len(lines) >= 3:
                content = "\n".join(lines[1:-1]).strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass

        start = content.find("{")
        if start < 0:
            raise LLMResponseError(f"Model did not return JSON content: {content[:500]}")

        depth = 0
        for index in range(start, len(content)):
            char = content[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    snippet = content[start : index + 1]
                    try:
                        return json.loads(snippet)
                    except json.JSONDecodeError as exc:
                        raise LLMResponseError(f"Failed to parse JSON snippet: {snippet[:500]}") from exc

        raise LLMResponseError(f"Unbalanced JSON content from model: {content[:500]}")

