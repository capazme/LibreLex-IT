# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Extension ⇄ core messages (spec §4.2, Appendix A). One JSON object per line."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class _Msg(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --- extension → core ------------------------------------------------------

class Hello(_Msg):
    type: Literal["hello"] = "hello"
    id: str
    protocol: int
    extension_version: str
    lo_version: str
    has_markdown_filter: bool


class DocContext(_Msg):
    title: str = ""
    has_selection: bool = False
    cursor_paragraph: str | None = None


class Chat(_Msg):
    type: Literal["chat"] = "chat"
    id: str
    doc_id: str
    message: str
    context: DocContext = Field(default_factory=DocContext)


CommandName = Literal["verify_citations", "insert_norm", "research", "draft", "review"]


class Command(_Msg):
    type: Literal["command"] = "command"
    id: str
    doc_id: str
    name: CommandName
    args: dict[str, Any] = Field(default_factory=dict)


class DocResult(_Msg):
    type: Literal["doc_result"] = "doc_result"
    id: str
    call_id: str
    ok: bool
    result: dict[str, Any] | None = None
    error: str | None = None


class ConsentResult(_Msg):
    type: Literal["consent_result"] = "consent_result"
    id: str
    call_id: str
    decision: Literal["document", "once", "deny"]


class Cancel(_Msg):
    type: Literal["cancel"] = "cancel"
    id: str
    doc_id: str


class Shutdown(_Msg):
    type: Literal["shutdown"] = "shutdown"


ExtensionMessage = Annotated[
    Hello | Chat | Command | DocResult | ConsentResult | Cancel | Shutdown,
    Field(discriminator="type"),
]

# --- core → extension ------------------------------------------------------

class HelloOk(_Msg):
    type: Literal["hello_ok"] = "hello_ok"
    core_version: str
    protocol: int
    mcp_server_version: str | None = None
    warnings: list[str] = Field(default_factory=list)


class Status(_Msg):
    type: Literal["status"] = "status"
    request_id: str
    text: str


class Delta(_Msg):
    type: Literal["delta"] = "delta"
    request_id: str
    text: str


class DocCall(_Msg):
    type: Literal["doc_call"] = "doc_call"
    request_id: str
    call_id: str
    action: str
    args: dict[str, Any] = Field(default_factory=dict)


class ConsentSummary(_Msg):
    scope: Literal["selection", "paragraphs"]
    chars: int
    endpoint_host: str
    model: str
    zdr: bool


class ConsentRequest(_Msg):
    type: Literal["consent_request"] = "consent_request"
    request_id: str
    call_id: str
    summary: ConsentSummary


class Progress(_Msg):
    type: Literal["progress"] = "progress"
    request_id: str
    done: int
    total: int


class Usage(_Msg):
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None


class Final(_Msg):
    type: Literal["final"] = "final"
    request_id: str
    text: str = ""
    cancelled: bool = False
    usage: Usage | None = None
    summary: dict[str, Any] = Field(default_factory=dict)


class Error(_Msg):
    type: Literal["error"] = "error"
    request_id: str | None = None
    code: str
    message: str


class Log(_Msg):
    type: Literal["log"] = "log"
    level: Literal["debug", "info", "warning", "error"] = "info"
    text: str


CoreMessage = Annotated[
    HelloOk | Status | Delta | DocCall | ConsentRequest | Progress | Final | Error | Log,
    Field(discriminator="type"),
]

_extension_adapter: TypeAdapter[ExtensionMessage] = TypeAdapter(ExtensionMessage)
_core_adapter: TypeAdapter[CoreMessage] = TypeAdapter(CoreMessage)


def parse_extension_line(line: str) -> ExtensionMessage:
    return _extension_adapter.validate_json(line)


def parse_core_line(line: str) -> CoreMessage:
    return _core_adapter.validate_json(line)


def dump_line(msg: BaseModel) -> str:
    """Serialise a message as a single line (no embedded newlines: JSON escapes them)."""
    return msg.model_dump_json() + "\n"
