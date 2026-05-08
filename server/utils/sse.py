from __future__ import annotations

import json


def sse_event(event: str, data: object | None = None) -> str:
    payload = json.dumps({} if data is None else data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def sse_token(content: str) -> str:
    return sse_event("token", content)


def sse_done() -> str:
    return sse_event("done")


def sse_error(message: str) -> str:
    return sse_event("error", {"message": message})
