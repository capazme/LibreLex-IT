# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import os
import queue
import sys
from pathlib import Path

import pytest

from librelex_ext.bridge import Bridge, BridgeError
from librelex_ext.paths import BridgeSpec

FAKE = Path(__file__).with_name("fake_core.py")


def spec(tmp_path):
    return BridgeSpec(argv=[sys.executable, str(FAKE)], env=dict(os.environ),
                      stderr_path=tmp_path / "stderr.log", cwd=str(tmp_path))


def wait_for(events: queue.Queue, kind: str, timeout=10):
    while True:
        ev = events.get(timeout=timeout)
        if ev["kind"] == kind:
            return ev


def test_hello_command_doc_call_final(tmp_path):
    events: queue.Queue = queue.Queue()
    b = Bridge(spec(tmp_path), events.put)
    b.start()
    try:
        b.send({"type": "hello", "id": "h1", "protocol": 1, "extension_version": "0.1.0",
                "lo_version": "26.8", "has_markdown_filter": True})
        ok = wait_for(events, "message")["msg"]
        assert ok["type"] == "hello_ok" and ok["protocol"] == 1
        b.send({"type": "command", "id": "r1", "doc_id": "d1", "name": "insert_norm", "args": {}})
        assert wait_for(events, "message")["msg"]["type"] == "status"
        call = wait_for(events, "message")["msg"]
        assert call["type"] == "doc_call" and call["action"] == "get_document_info"
        b.send({"type": "doc_result", "id": call["request_id"], "call_id": call["call_id"],
                "ok": True, "result": {"title": "t"}})
        final = wait_for(events, "message")["msg"]
        assert final["type"] == "final" and final["summary"]["info"] == {"title": "t"}
        assert b.is_alive()
    finally:
        b.stop()
    assert not b.is_alive()
    assert wait_for(events, "exit")["code"] == 0
    assert (tmp_path / "stderr.log").exists()


def test_exit_is_reported_and_send_fails_afterwards(tmp_path):
    events: queue.Queue = queue.Queue()
    b = Bridge(spec(tmp_path), events.put)
    b.start()
    b.send({"type": "hello", "id": "h1", "protocol": 1, "extension_version": "0.1.0",
            "lo_version": "26.8", "has_markdown_filter": True})
    wait_for(events, "message")
    b.send({"type": "command", "id": "r1", "doc_id": "d1", "name": "insert_norm",
            "args": {"crash": True}})
    assert wait_for(events, "exit")["code"] == 3
    with pytest.raises(BridgeError):
        for _ in range(50):          # the pipe may take a few writes to report EPIPE
            b.send({"type": "shutdown"})


def test_unparseable_line_is_reported_as_garbage(tmp_path):
    events: queue.Queue = queue.Queue()
    s = BridgeSpec(argv=[sys.executable, "-c", "print('not json'); print('{\"type\":\"log\"}')"],
                   env=dict(os.environ), stderr_path=tmp_path / "e.log", cwd=str(tmp_path))
    b = Bridge(s, events.put)
    b.start()
    assert wait_for(events, "garbage")["line"] == "not json"
    assert wait_for(events, "message")["msg"] == {"type": "log"}
    assert wait_for(events, "exit")["code"] == 0


def test_start_failure_raises_bridge_error(tmp_path):
    s = BridgeSpec(argv=[str(tmp_path / "missing-binary")], env=dict(os.environ),
                   stderr_path=tmp_path / "e.log", cwd=str(tmp_path))
    with pytest.raises(BridgeError, match="missing-binary"):
        Bridge(s, lambda ev: None).start()
