# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""A localhost SSE stub of an OpenAI-compatible endpoint, for the headless chat probe.

The real core runs in its own process (spawned by the extension's Bridge inside soffice),
so it cannot be handed an httpx mock transport the way ``core/tests/fakes.py::mock_llm``
does: it needs a socket. This serves scripted ``text/event-stream`` responses over
``127.0.0.1`` (the only scheme/host pair for which ``resolve_llm_endpoint`` accepts
``http://``) and records the request bodies the core sent, so the test can assert on the
messages the core built.

The chunk shapes mirror ``core/tests/fakes.py`` so both layers script the same wire.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

PATH = "/v1/chat/completions"


def chunk(delta: dict | None = None, finish: str | None = None, usage: dict | None = None) -> dict:
    body: dict[str, Any] = {
        "id": "chatcmpl-stub", "object": "chat.completion.chunk", "created": 0,
        "model": "stub", "choices": [],
    }
    if delta is not None or finish is not None:
        body["choices"] = [{"index": 0, "delta": delta or {}, "finish_reason": finish}]
    if usage is not None:
        body["usage"] = usage
    return body


def sse(chunks: list[dict]) -> bytes:
    lines = [f"data: {json.dumps(c, ensure_ascii=False)}\n\n" for c in chunks]
    return ("".join(lines) + "data: [DONE]\n\n").encode()


def usage(prompt_tokens: int, completion_tokens: int) -> dict:
    return {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens}


def tool_call_response(name: str, args: dict, call_id: str = "call_stub_1") -> list[dict]:
    """One assistant turn that only asks for ``name(args)`` (finish reason ``tool_calls``)."""
    return [
        chunk({"role": "assistant", "content": None}),
        chunk({"tool_calls": [{"index": 0, "id": call_id, "type": "function",
                               "function": {"name": name, "arguments": ""}}]}),
        chunk({"tool_calls": [{"index": 0,
                               "function": {"arguments": json.dumps(args)}}]}),
        chunk(finish="tool_calls"),
    ]


def text_response(text: str, tokens: tuple[int, int] | None = None) -> list[dict]:
    """One assistant turn streaming ``text`` word by word (finish reason ``stop``)."""
    words = text.split(" ")
    pieces = [w + (" " if i < len(words) - 1 else "") for i, w in enumerate(words)]
    chunks = [chunk({"role": "assistant", "content": ""})]
    chunks += [chunk({"content": piece}) for piece in pieces]
    chunks.append(chunk(finish="stop"))
    if tokens is not None:
        chunks.append(chunk(usage=usage(*tokens)))
    return chunks


class _Handler(BaseHTTPRequestHandler):
    # HTTP/1.1 plus an explicit Content-Length: the body is scripted, so it is sent in one
    # write and the openai SDK's connection pool can keep the socket alive between turns.
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:                            # noqa: N802  (stdlib naming)
        if self.path.rstrip("/") != PATH:
            self.send_error(404, "unknown path")
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        chunks = self.server.stub.take(json.loads(raw or b"{}"))   # type: ignore[attr-defined]
        if chunks is None:
            self.send_error(500, "no scripted response left")
            return
        body = sse(chunks)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:                             # noqa: N802  (stdlib naming)
        self.send_error(404, "unknown path")

    def log_message(self, fmt: str, *args: Any) -> None:
        """Silence the stdlib access log: pytest output stays readable."""


class StubLLM(threading.Thread):
    """Serves ``responses`` in order, one per ``POST /v1/chat/completions``.

    Each response is a list of chunk dicts (see ``chunk``); ``requests`` collects the
    decoded JSON bodies the core sent, in order.
    """

    def __init__(self, responses: list[list[dict]]):
        super().__init__(daemon=True, name="librelex-llm-stub")
        self._pending = list(responses)
        self.requests: list[dict] = []
        self._lock = threading.Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.stub = self                          # type: ignore[attr-defined]

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def take(self, request: dict) -> list[dict] | None:
        """Record one request (handler thread) and hand back the next scripted response."""
        with self._lock:
            self.requests.append(request)
            return self._pending.pop(0) if self._pending else None

    def run(self) -> None:
        self._server.serve_forever(poll_interval=0.1)

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self.join(5)
