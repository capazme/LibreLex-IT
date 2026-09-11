# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Test doubles for the M2 core: SSE fixtures, a mock HTTP transport and a scripted LLM."""
from __future__ import annotations

import json
from typing import Any

import httpx

from librelex_core.llm.client import ToolCallRequest, TurnResult
from librelex_core.protocol import Usage


def chunk(delta: dict | None = None, finish: str | None = None, usage: dict | None = None) -> dict:
    body: dict[str, Any] = {
        "id": "chatcmpl-1", "object": "chat.completion.chunk", "created": 0,
        "model": "fake", "choices": [],
    }
    if delta is not None or finish is not None:
        body["choices"] = [{"index": 0, "delta": delta or {}, "finish_reason": finish}]
    if usage is not None:
        body["usage"] = usage
    return body


def sse(chunks: list[dict]) -> bytes:
    lines = [f"data: {json.dumps(c)}\n\n" for c in chunks]
    return ("".join(lines) + "data: [DONE]\n\n").encode()


def mock_llm(responses: list[bytes | int]) -> httpx.AsyncClient:
    """Answers successive chat/completions calls with SSE bodies (bytes) or HTTP errors (int)."""
    queue = list(responses)
    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content or b"{}"))
        item = queue.pop(0) if queue else 500
        if isinstance(item, int):
            return httpx.Response(item, json={"error": {"message": f"boom {item}"}})
        return httpx.Response(200, content=item, headers={"content-type": "text/event-stream"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client.calls = calls  # type: ignore[attr-defined]
    return client


class ScriptedLLM:
    """Same `stream()` contract as LLMClient; returns pre-built turns in order."""

    def __init__(self, turns: list[TurnResult], model: str = "fake-model",
                host: str = "fake.local"):
        self.turns = list(turns)
        self.model, self.host = model, host
        self.calls: list[tuple[list[dict], list[dict] | None]] = []

    async def stream(self, messages, tools, on_delta) -> TurnResult:
        self.calls.append((json.loads(json.dumps(messages)), tools))
        if not self.turns:
            raise AssertionError("ScriptedLLM: no more scripted turns")
        turn = self.turns.pop(0)
        for piece in turn.text.split(" "):
            await on_delta(piece + (" " if piece != turn.text.split(" ")[-1] else ""))
        return turn


def text_turn(text: str, usage: Usage | None = None) -> TurnResult:
    return TurnResult(text=text, tool_calls=[],
                      usage=usage or Usage(input_tokens=10, output_tokens=5),
                      finish_reason="stop")


def tool_turn(*calls: tuple[str, dict], text: str = "") -> TurnResult:
    reqs = [ToolCallRequest(id=f"call_{i}", name=name, arguments=json.dumps(args))
            for i, (name, args) in enumerate(calls)]
    return TurnResult(text=text, tool_calls=reqs, usage=Usage(input_tokens=20, output_tokens=8),
                      finish_reason="tool_calls")
