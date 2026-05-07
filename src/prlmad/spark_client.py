from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Iterable, Iterator
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class SparkAPIError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatChunk:
    content: str = ""
    reasoning_content: str = ""
    raw: dict[str, Any] | None = None


class SparkClient:
    def __init__(
        self,
        api_key: str | None,
        base_url: str,
        model: str = "spark-x",
        user_id: str = "prlmad-demo-user",
        enable_web_search: bool = False,
        timeout: int = 90,
    ):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.user_id = user_id
        self.enable_web_search = enable_web_search
        self.timeout = timeout

    def _authorization(self) -> str:
        if not self.api_key or "your_api_password_here" in self.api_key:
            raise SparkAPIError("SPARK_API_KEY is not configured. Copy .env to .env first.")
        if self.api_key.lower().startswith("bearer "):
            return self.api_key
        return f"Bearer {self.api_key}"

    def _body(self, messages: list[dict[str, str]], stream: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "user": self.user_id,
            "messages": messages,
            "stream": stream,
        }
        if self.enable_web_search:
            body["tools"] = [
                {
                    "type": "web_search",
                    "web_search": {"enable": True, "search_mode": "deep"},
                }
            ]
        return body

    def _request(self, messages: list[dict[str, str]], stream: bool):
        payload = json.dumps(self._body(messages, stream), ensure_ascii=False).encode("utf-8")
        request = Request(
            self.base_url,
            data=payload,
            headers={
                "Authorization": self._authorization(),
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            return urlopen(request, timeout=self.timeout)
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SparkAPIError(f"Spark API returned HTTP {exc.code}: {detail}") from exc
        except URLError as exc:
            raise SparkAPIError(f"Spark API request failed: {exc.reason}") from exc

    def stream_chat(self, messages: list[dict[str, str]]) -> Iterator[ChatChunk]:
        with self._request(messages, stream=True) as response:
            for raw_line in response:
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith(b"data:"):
                    line = line[5:].strip()
                if line == b"[DONE]":
                    break
                try:
                    payload = json.loads(line.decode("utf-8"))
                except json.JSONDecodeError:
                    continue
                choice = (payload.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                yield ChatChunk(
                    content=delta.get("content") or "",
                    reasoning_content=delta.get("reasoning_content") or "",
                    raw=payload,
                )

    def chat(self, messages: list[dict[str, str]], stream: bool = True) -> str:
        if stream:
            return "".join(chunk.content for chunk in self.stream_chat(messages))

        with self._request(messages, stream=False) as response:
            payload = json.loads(response.read().decode("utf-8"))
        choice = (payload.get("choices") or [{}])[0]
        message = choice.get("message") or choice.get("delta") or {}
        return message.get("content") or ""


class FakeSparkClient:
    """Deterministic client used by tests and offline smoke checks."""

    def __init__(self, prefix: str = "FAKE"):
        self.prefix = prefix
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, messages: list[dict[str, str]], stream: bool = True) -> str:
        self.calls.append(messages)
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return f"{self.prefix}: {last_user[:180]}"

