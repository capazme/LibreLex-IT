# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import json

import pytest
from pydantic import ValidationError

from librelex_core import protocol as p


def test_hello_roundtrip():
    msg = p.Hello(id="r1", protocol=1, extension_version="0.1.0", lo_version="26.8.0.3",
                  has_markdown_filter=True)
    line = p.dump_line(msg)
    assert line.endswith("\n") and line.count("\n") == 1
    back = p.parse_extension_line(line)
    assert isinstance(back, p.Hello) and back == msg


def test_command_defaults_and_discriminator():
    line = json.dumps({"id": "r3", "type": "command", "doc_id": "d1", "name": "verify_citations"})
    msg = p.parse_extension_line(line)
    assert isinstance(msg, p.Command) and msg.args == {}


def test_doc_result_error_form():
    line = '{"id":"r3","type":"doc_result","call_id":"c8","ok":false,"error":"boom"}'
    msg = p.parse_extension_line(line)
    assert (isinstance(msg, p.DocResult) and msg.ok is False and msg.error == "boom"
            and msg.result is None)


def test_unknown_type_rejected():
    with pytest.raises(ValidationError):
        p.parse_extension_line('{"type":"teleport","id":"x"}')


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        p.parse_extension_line('{"type":"shutdown","surprise":1}')


def test_core_messages_roundtrip():
    msgs = [
        p.HelloOk(core_version="0.1.0", protocol=1, mcp_server_version="2.14.0"),
        p.Status(request_id="r2", text="Cerco su Italgiure"),
        p.Delta(request_id="r2", text="ciao"),
        p.DocCall(request_id="r2", call_id="c7", action="read_paragraphs", args={"from": 0}),
        p.ConsentRequest(request_id="r2", call_id="k1",
                         summary=p.ConsentSummary(scope="paragraphs", chars=10, endpoint_host="h",
                                                  model="m", zdr=True)),
        p.Progress(request_id="r3", done=40, total=63),
        p.Final(request_id="r2", text="fatto", usage=p.Usage(input_tokens=1, output_tokens=2)),
        p.Error(request_id="r2", code="llm_http", message="x"),
        p.Log(level="info", text="hi"),
    ]
    for m in msgs:
        back = p.parse_core_line(p.dump_line(m))
        assert back == m


def test_large_payload_roundtrip():
    big = "x" * 1_000_000
    back = p.parse_core_line(p.dump_line(p.Delta(request_id="r", text=big)))
    assert back.text == big
