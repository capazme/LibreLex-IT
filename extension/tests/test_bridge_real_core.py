# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""The real librelex-core over real pipes, with the fake legal server: no LibreOffice."""
import queue
import shutil

import pytest

from librelex_ext import PROTOCOL_VERSION, paths
from librelex_ext.bridge import Bridge

pytestmark = pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")

CORE = paths.repo_core_dir()


def write_config(tmp_path):
    cfg = tmp_path / "config.toml"
    server = CORE / "tests" / "fake_legal_server.py"
    cfg.write_text(
        "[mcp_legal_it]\nmode = \"local\"\n"
        f"command = [\"uv\", \"run\", \"--project\", \"{CORE}\", \"python\", \"{server}\"]\n",
        encoding="utf-8")
    return cfg


def wait_for(events, pred, timeout=120):
    while True:
        ev = events.get(timeout=timeout)
        if pred(ev):
            return ev


def test_verify_citations_roundtrip_with_real_core(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRELEX_CONFIG", str(write_config(tmp_path)))
    spec = paths.bridge_spec(tmp_path / "nopkg", {})
    env = dict(spec.env)
    env["UV_PROJECT_ENVIRONMENT"] = str(CORE / ".venv")   # reuse the synced dev environment
    spec = paths.BridgeSpec(argv=spec.argv, env=env, stderr_path=spec.stderr_path, cwd=spec.cwd)
    events: queue.Queue = queue.Queue()
    b = Bridge(spec, events.put)
    b.start()
    try:
        b.send({"type": "hello", "id": "h1", "protocol": PROTOCOL_VERSION,
                "extension_version": "0.1.0", "lo_version": "26.8", "has_markdown_filter": True})
        ok = wait_for(events, lambda e: e["kind"] == "message")["msg"]
        assert ok["type"] == "hello_ok" and ok["protocol"] == PROTOCOL_VERSION, ok
        b.send({"type": "command", "id": "r1", "doc_id": "d1", "name": "verify_citations",
                "args": {"scope": "document"}})
        paragraphs = [{"id": "p:0", "text": "Vedi art. 2043 c.c. e Cass. n. 99999/2024.",
                       "style": "Text body", "kind": "body"}]
        comments = []
        while True:
            ev = wait_for(events, lambda e: e["kind"] in ("message", "exit"))
            assert ev["kind"] == "message", f"core exited: {ev}"
            msg = ev["msg"]
            if msg["type"] == "doc_call":
                a = msg["action"]
                if a == "read_paragraphs":
                    assert set(msg["args"]) == {"from_", "to"}
                    result = {"paragraphs": paragraphs}
                elif a == "remove_comments":
                    result = {"count": 0}
                elif a == "add_comment":
                    comments.append(msg["args"])
                    result = {"anchored": "exact"}
                else:
                    raise AssertionError(a)
                b.send({"type": "doc_result", "id": msg["request_id"], "call_id": msg["call_id"],
                        "ok": True, "result": result})
            elif msg["type"] == "final":
                assert msg["summary"]["commenti_inseriti"] == 1
                assert msg["summary"]["per_verdetto"] == {"verificata": 1, "inesistente": 1}
                break
            elif msg["type"] == "error":
                raise AssertionError(msg)
        assert comments[0]["author"] == "LibreLex · verifica"
        assert comments[0]["expected_text"] == "Cass. n. 99999/2024"
    finally:
        b.stop()
    assert "Traceback" not in spec.stderr_path.read_text(encoding="utf-8", errors="replace")
