# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Streaming client for OpenAI-compatible endpoints (spec §6.1)."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

import httpx
import openai
from openai import NOT_GIVEN

from librelex_core.config import ConfigError, Endpoint, LLMConfig, resolve_llm_endpoint
from librelex_core.protocol import Usage


class LLMError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class ToolCallRequest:
    id: str
    name: str
    arguments: str


@dataclass
class TurnResult:
    text: str
    tool_calls: list[ToolCallRequest]
    usage: Usage
    finish_reason: str = "stop"


@dataclass
class _Partial:
    id: str = ""
    name: str = ""
    arguments: list[str] = field(default_factory=list)


class LLMClient:
    def __init__(self, cfg: LLMConfig, http_client: httpx.AsyncClient | None = None):
        if not cfg.model:
            raise LLMError("llm_config", "llm.model non impostato nel file di configurazione")
        try:
            self.endpoint: Endpoint = resolve_llm_endpoint(cfg)
        except ConfigError as e:
            raise LLMError("llm_config", str(e)) from e
        self.model = cfg.model
        self._client = openai.AsyncOpenAI(
            base_url=self.endpoint.base_url, api_key=cfg.api_key or "none",
            default_headers=self.endpoint.headers or None, max_retries=2, timeout=60.0,
            http_client=http_client)

    async def stream(self, messages: list[dict], tools: list[dict] | None,
                     on_delta: Callable[[str], Awaitable[None]]) -> TurnResult:
        kwargs: dict[str, Any] = {}
        if self.endpoint.extra_body:
            kwargs["extra_body"] = self.endpoint.extra_body
        try:
            response = await self._client.chat.completions.create(
                model=self.model, messages=messages, tools=tools or NOT_GIVEN, stream=True,
                stream_options={"include_usage": True}, **kwargs)
            text: list[str] = []
            partial: dict[int, _Partial] = {}
            usage = Usage()
            finish = "stop"
            async for chunk in response:
                if chunk.usage is not None:
                    extra = getattr(chunk.usage, "model_extra", None) or {}
                    usage = Usage(input_tokens=chunk.usage.prompt_tokens or 0,
                                  output_tokens=chunk.usage.completion_tokens or 0,
                                  cost_usd=extra.get("cost"))
                for choice in chunk.choices:
                    delta = choice.delta
                    if delta is not None and delta.content:
                        text.append(delta.content)
                        await on_delta(delta.content)
                    for tc in (delta.tool_calls or []) if delta is not None else []:
                        p = partial.setdefault(tc.index, _Partial())
                        if tc.id:
                            p.id = tc.id
                        if tc.function is not None:
                            if tc.function.name:
                                p.name = tc.function.name
                            if tc.function.arguments:
                                p.arguments.append(tc.function.arguments)
                    if choice.finish_reason:
                        finish = choice.finish_reason
        except (openai.APIStatusError, openai.APIConnectionError, openai.APITimeoutError) as e:
            status = getattr(e, "status_code", None)
            detail = f"HTTP {status}" if status else "connessione fallita"
            raise LLMError("llm_http",
                           f"{type(e).__name__}: {detail} ({self.endpoint.host})") from e
        calls = [ToolCallRequest(id=p.id or f"call_{i}", name=p.name,
                                 arguments="".join(p.arguments) or "{}")
                 for i, p in sorted(partial.items())]
        return TurnResult(text="".join(text), tool_calls=calls, usage=usage, finish_reason=finish)
