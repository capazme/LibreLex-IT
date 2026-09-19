# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""M3 exit criterion, headless: a decreto ingiuntivo drafted from the template through the
real core, with the amounts of the generator, inserted section by section as redlines.

The model is the localhost SSE stub scripted to look the template up, read the document
(consent), call the generator and insert two sections; everything else is real (Session,
Bridge, core subprocess, DocumentAdapter, the fake mcp-legal-it with its catalogue)."""
import shutil

import pytest

from librelex_ext import paths
from tests.headless.conftest import run_probe
from tests.headless.llm_stub import StubLLM, text_response, tool_call_response

pytestmark = [pytest.mark.headless,
              pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")]

CORE = paths.repo_core_dir()
PARAGRAPH = "Fattura n. 12 del 3 marzo 2025 di Euro 12.000,00 emessa da Alfa S.r.l. a Beta S.p.A."
HEADING = ("# RICORSO PER DECRETO INGIUNTIVO\n\n(artt. 633 e ss. c.p.c.)\n\n"
           "**Alfa S.r.l.**, ricorrente, contro **Beta S.p.A.**, resistente.")
CONCLUSIONS = ("## Conclusioni\n\nVoglia l'Ill.mo Tribunale ingiungere a Beta S.p.A. il pagamento "
               "di Euro 12.000,00, oltre contributo unificato di Euro 129,50 (DPR 115/2002).")
ANSWER = "Inserite intestazione e conclusioni; restano da indicare la sede e i codici fiscali."


@pytest.fixture
def stub():
    server = StubLLM([
        tool_call_response("genera_modello_atto", {"tipo_atto": "decreto_ingiuntivo_ordinario"},
                           "call_1"),
        tool_call_response("read_paragraphs", {}, "call_2"),
        tool_call_response("decreto_ingiuntivo", {"creditore": "Alfa S.r.l.",
                                                  "debitore": "Beta S.p.A.", "importo": 12000.0},
                           "call_3"),
        tool_call_response("insert_markdown", {"where": "end", "markdown": HEADING}, "call_4"),
        tool_call_response("insert_markdown", {"where": "end", "markdown": CONCLUSIONS}, "call_5"),
        text_response(ANSWER, tokens=(2400, 60))])
    server.start()
    try:
        yield server
    finally:
        server.stop()


def test_decreto_ingiuntivo_drafted_from_the_template_inside_libreoffice(soffice, stub, tmp_path):
    cfg = tmp_path / "config.toml"
    server = CORE / "tests" / "fake_legal_server.py"
    cfg.write_text(
        "[mcp_legal_it]\nmode = \"local\"\n"
        f"command = [\"uv\", \"run\", \"--project\", \"{CORE}\", \"python\", \"{server}\"]\n"
        "\n[llm]\npreset = \"custom\"\n"
        f"base_url = \"{stub.base_url}\"\napi_key = \"x\"\nmodel = \"stub\"\n",
        encoding="utf-8")
    uv_dir = str(paths.Path(shutil.which("uv")).parent)
    out = run_probe(soffice, "e2e_draft", f'''
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
        s.draft("decreto ingiuntivo per la fattura del documento")
        out["state"] = pump(s, view, events)
        out["stream"] = view.stream
        out["usage"] = view.usage
        out["consents"] = view.consents
        out["lines"] = list(view.lines)
        out["transcript"] = list(s.transcript)
        out["paragraphs_after"] = paragraph_texts(text)
        out["redlines"] = redlines(doc)
        s.shutdown()
        doc.close(True)
    ''', timeout=420, env={"LIBRELEX_CONFIG": str(cfg)})
    assert out["state"] == "ready", out
    # Six model calls: five tool calls, then the answer.
    assert len(stub.requests) == 6, [r["messages"][-1] for r in stub.requests]
    first = stub.requests[0]
    assert first["messages"][1]["content"].startswith("Redazione guidata da modello.")
    names = {t["function"]["name"] for t in first["tools"]}
    assert {"genera_modello_atto", "decreto_ingiuntivo", "contributo_unificato",
            "insert_markdown", "read_paragraphs"} <= names
    assert "cerca_giurisprudenza" not in names and "replace_selection" not in names
    tool_msgs = [m for m in stub.requests[-1]["messages"] if m.get("role") == "tool"]
    assert len(tool_msgs) == 5
    assert "<<<DATI: genera_modello_atto>>>" in tool_msgs[0]["content"]
    assert "tool_diretto" in tool_msgs[0]["content"]
    assert PARAGRAPH in tool_msgs[1]["content"]                 # read after consent
    assert "<<<DATI: decreto_ingiuntivo>>>" in tool_msgs[2]["content"]
    # FastMCP serializes the fake tool's structured dict return compactly (no space after
    # ":"/","), unlike _as_json's json.dumps default used for local document-tool results.
    assert '"giudice_competente":"Tribunale"' in tool_msgs[2]["content"]
    assert tool_msgs[3]["content"].startswith("Inserito nei paragrafi ")
    assert tool_msgs[4]["content"].startswith("Inserito nei paragrafi ")
    # Consent was asked once, before the document text entered the messages.
    assert len(out["consents"]) == 1 and out["consents"][0]["chars"] == len(PARAGRAPH)
    # Two sections at the end of the document, each a tracked insertion by LibreLex.
    texts = [t for _, t in out["paragraphs_after"]]
    assert texts[0] == PARAGRAPH
    assert "RICORSO PER DECRETO INGIUNTIVO" in texts[1], texts
    assert any("Euro 129,50" in t for t in texts), texts
    assert texts.index("Conclusioni") > texts.index("RICORSO PER DECRETO INGIUNTIVO")
    assert out["redlines"] and all(kind == "Insert" and author == "LibreLex"
                                   for kind, author in out["redlines"]), out["redlines"]
    # The panel: streamed answer, the blank separator, one note per inserted section, usage.
    assert out["stream"] == ANSWER
    notes = [line for line in out["lines"] if line.startswith("Inserito nei paragrafi ")]
    assert len(notes) == 2, out["lines"]
    # render_usage formats with the Italian thousands separator above 999 (spec §5.1).
    assert out["usage"].startswith("Turno: 2.400 + 60 token"), out["usage"]
    assert out["transcript"][0] == ANSWER and out["transcript"][1] == ""
