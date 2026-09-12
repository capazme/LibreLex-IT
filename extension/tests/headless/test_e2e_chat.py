# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""M2 exit criterion, headless: a full chat turn (stream, consent, usage) through the real core.

The model is a localhost SSE stub (``llm_stub``) scripted to read the document and then
answer: everything between the panel and the endpoint is real (Session, Bridge, the core
subprocess, DocumentAdapter, the fake mcp-legal-it), so this covers the consent round-trip
of spec §8.2 and the usage line of §5.1 end to end.
"""
import shutil

import pytest

from librelex_ext import paths
from tests.headless.conftest import run_probe
from tests.headless.llm_stub import StubLLM, text_response, tool_call_response

pytestmark = [pytest.mark.headless,
              pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")]

CORE = paths.repo_core_dir()
PARAGRAPH = "Il presente parere tratta della responsabilità aquiliana del custode."
ANSWER = "Il documento parla di responsabilità aquiliana."


@pytest.fixture
def stub():
    server = StubLLM([tool_call_response("read_paragraphs", {}),
                      text_response(ANSWER, tokens=(120, 9))])
    server.start()
    try:
        yield server
    finally:
        server.stop()


def test_chat_turn_with_consent_from_inside_libreoffice(soffice, stub, tmp_path):
    cfg = tmp_path / "config.toml"
    server = CORE / "tests" / "fake_legal_server.py"
    cfg.write_text(
        "[mcp_legal_it]\nmode = \"local\"\n"
        f"command = [\"uv\", \"run\", \"--project\", \"{CORE}\", \"python\", \"{server}\"]\n"
        "\n[llm]\npreset = \"custom\"\n"
        f"base_url = \"{stub.base_url}\"\napi_key = \"x\"\nmodel = \"stub\"\n",
        encoding="utf-8")
    uv_dir = str(paths.Path(shutil.which("uv")).parent)
    out = run_probe(soffice, "e2e_chat", f'''
    import os, queue
    from librelex_ext import paths
    from librelex_ext.bridge import Bridge
    from librelex_ext.session import Session

    class RecView:
        def __init__(self):
            self.lines, self.status = [], []
            self.stream, self.usage, self.consent = "", None, None
            self.consents = []
        def append(self, t): self.lines.append(t)
        def set_transcript(self, t): pass
        def set_status(self, t): self.status.append(t)
        def set_busy(self, b): pass
        def set_citations(self, labels): pass
        def set_progress(self, done, total): pass
        def append_stream(self, t): self.stream += t
        def set_usage(self, t): self.usage = t
        def set_consent(self, summary):
            self.consent = summary
            if summary is not None:
                self.consents.append(summary)

    def pump(session, view, events, until_state="ready", timeout=300):
        """Drive the session to `until_state`, granting consent once when it is asked."""
        import time
        deadline = time.time() + timeout
        while session.state != until_state and time.time() < deadline:
            try:
                ev = events.get(timeout=1)
            except queue.Empty:
                pass
            else:
                session.handle_event(ev)
            if view.consent is not None:
                session.answer_consent("once")
        return session.state

    def probe(ctx, out):
        doc = new_doc(ctx)
        text = doc.Text
        cur = text.createTextCursor()
        text.insertString(cur, {PARAGRAPH!r}, False)
        adapter = DocumentAdapter(ctx, doc)
        events = queue.Queue()
        config = {{"extension": {{"uv": os.path.join({uv_dir!r}, "uv")}}}}
        def bridge_factory(on_event):
            spec = paths.bridge_spec(paths.Path("/nonexistent-pkg"), config)
            env = dict(spec.env)
            env["UV_PROJECT_ENVIRONMENT"] = str(paths.repo_core_dir() / ".venv")
            return Bridge(paths.BridgeSpec(spec.argv, env, spec.stderr_path, spec.cwd), on_event)
        view = RecView()
        s = Session(adapter, bridge_factory, doc_id=doc.RuntimeUID, lo_version=lo_version(ctx),
                    has_markdown_filter=has_markdown_filter(ctx), config_path={str(cfg)!r})
        s.bind(view, events.put)
        out["paragraphs_before"] = paragraph_texts(text)
        s.chat("Di cosa parla?")
        out["state"] = pump(s, view, events)
        out["stream"] = view.stream
        out["usage"] = view.usage
        out["consents"] = view.consents
        out["consent_pending"] = view.consent
        out["lines"] = list(view.lines)
        out["status"] = list(view.status)
        out["transcript"] = list(s.transcript)
        out["paragraphs_after"] = paragraph_texts(text)
        out["redlines"] = redlines(doc)
        s.shutdown()
        doc.close(True)
    ''', timeout=420, env={"LIBRELEX_CONFIG": str(cfg)})
    assert out["state"] == "ready", out
    # Two model turns reached the stub: the tool call, then the answer with the tool result.
    assert len(stub.requests) == 2, stub.requests
    first, second = stub.requests
    assert first["model"] == "stub" and first["stream"] is True
    assert [m for m in first["messages"] if m.get("role") == "tool"] == []
    tool_msgs = [m for m in second["messages"] if m.get("role") == "tool"]
    assert len(tool_msgs) == 1, second["messages"]
    # The document text travelled once, wrapped as data (spec §6.5), only after consent.
    assert "<<<DATI: read_paragraphs>>>" in tool_msgs[0]["content"]
    assert PARAGRAPH in tool_msgs[0]["content"]
    # Consent was asked before the text entered the messages, with the real endpoint in it.
    assert len(out["consents"]) == 1, out["consents"]
    summary = out["consents"][0]
    assert summary["scope"] == "paragraphs" and summary["chars"] == len(PARAGRAPH)
    assert summary["model"] == "stub" and summary["endpoint_host"] == "127.0.0.1"
    assert out["consent_pending"] is None
    # The answer streamed into the panel and the usage line carries the stub's tokens.
    assert out["stream"] == ANSWER, out
    assert out["usage"].startswith("Turno: 120 + 9 token"), out["usage"]
    # The streamed text is what the reopened panel replays; the trailing blank line is the
    # separator _on_final adds after a streamed turn, and no note follows it (nothing was
    # inserted, flagged or left unverified).
    assert out["transcript"] == [ANSWER, ""], out["transcript"]
    # A chat turn writes nothing: no insertion, no redline.
    assert out["paragraphs_after"] == out["paragraphs_before"]
    assert [t for _, t in out["paragraphs_after"]] == [PARAGRAPH]
    assert out["redlines"] == []
