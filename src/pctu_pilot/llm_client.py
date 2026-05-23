from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass
class ChatResponse:
    content: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class OpenAICompatibleClient:
    """Small dependency-free client for local OpenAI-compatible model servers."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "not-needed",
        timeout_s: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout_s = timeout_s

    def chat(
        self,
        messages: list[ChatMessage],
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> ChatResponse:
        payload = {
            "model": self.model,
            "messages": [message.__dict__ for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        body = None
        for attempt in range(3):
            request = urllib.request.Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
                    body = json.loads(response.read().decode("utf-8"))
                    break
            except urllib.error.HTTPError as exc:
                if exc.code < 500 or attempt == 2:
                    raise RuntimeError(
                        f"Could not reach OpenAI-compatible server at {self.base_url}: {exc}"
                    ) from exc
                time.sleep(2**attempt)
            except urllib.error.URLError as exc:
                if attempt == 2:
                    raise RuntimeError(
                        f"Could not reach OpenAI-compatible server at {self.base_url}: {exc}"
                    ) from exc
                time.sleep(2**attempt)
        if body is None:
            raise RuntimeError(f"OpenAI-compatible server at {self.base_url} returned no body.")

        choice = body["choices"][0]["message"]["content"]
        usage = body.get("usage") or {}
        return ChatResponse(
            content=choice,
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
        )

    def healthcheck(self) -> bool:
        request = urllib.request.Request(
            f"{self.base_url}/models",
            headers={"Authorization": f"Bearer {self.api_key}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status == 200
        except urllib.error.URLError:
            return False


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse one JSON object from model output, tolerating fenced blocks."""

    stripped = text.strip()
    if stripped.startswith("```"):
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
        if match:
            stripped = match.group(1)
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end <= start:
            raise
        parsed = json.loads(stripped[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object from model output")
    return parsed
