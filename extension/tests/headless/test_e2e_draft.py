# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""M3 exit criterion, headless: a decreto ingiuntivo drafted through the Redazione and
Domande panels, on the guided-drafting protocol.

Everything between the panels and the endpoint is real: the session's drafting commands
(`list_templates`, `template_info`, `set_reference`, `draft` start/answer), the Bridge, the
core subprocess with its `draft` command, the DocumentAdapter and the fake mcp-legal-it with
its catalogue and its `decreto_ingiuntivo` generator. Only the model is scripted (the
localhost SSE stub): it reads the similar case (consent), asks for the missing datum through
`chiedi_dati`, then fills the base's `[SEDE]` placeholder, adds a section and closes with
`redazione_completata`.
"""
import json
import shutil

import pytest

from librelex_ext import paths
from tests.headless.conftest import run_probe
from tests.headless.llm_stub import StubLLM, chunk, tool_call_response, usage

pytestmark = [pytest.mark.headless,
              pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")]

CORE = paths.repo_core_dir()
TIPO_ATTO = "decreto_ingiuntivo_ordinario"
# The document the lawyer is working on: never read by this drafting (no read_paragraphs in
# the script), so it must never appear in a request.
PARAGRAPH = "Fattura n. 12 del 3 marzo 2025 di Euro 12.000,00 emessa da Alfa S.r.l. a Beta S.p.A."
REFERENCE = "RICORSO di riferimento con struttura e stile."
REFERENCE_NAME = "ricorso_rossi.docx"
NOTES = "Il credito è documentato dalla fattura allegata."
# "12.000" is the Italian notation the panel sends as a string: the core's parse_number turns
# it into twelve thousand, which the generator answers with "TRIBUNALE" (over ten thousand).
FIELDS = {"creditore": "Alfa S.r.l.", "debitore": "Beta S.p.A.", "importo": "12.000"}
QUESTIONS = [{"campo": "sede", "domanda": "Sede del tribunale?", "esempio": "Milano"}]
CONCLUSIONS = "## Conclusioni\n\nSi chiede l'ingiunzione di pagamento di Euro 12.000,00."
RIEPILOGO = "Calcoli: contributo unificato 129,50.\nAllegati: procura, fattura."
BASE_PARTITION = "✓ Base: Ricorso per decreto ingiuntivo — credito ordinario"


def with_usage(response: list[dict], tokens: tuple[int, int]) -> list[dict]:
    """The scripted turn plus the usage chunk a real endpoint sends last (include_usage)."""
    return [*response, chunk(usage=usage(*tokens))]


def tool_messages(request: dict) -> list[dict]:
    return [m for m in request["messages"] if m.get("role") == "tool"]


@pytest.fixture
def stub():
    server = StubLLM([
        # turn 1 (the core has already inserted the base): read the similar case, then ask
        # for the one datum the template does not carry, which ends the turn.
        tool_call_response("leggi_atto_riferimento", {}, "call_ref"),
        with_usage(tool_call_response("chiedi_dati", {"domande": QUESTIONS}, "call_ask"),
                   (1500, 40)),
        # turn 2 (the answers): fill the placeholder, add a section, close the drafting.
        tool_call_response("replace_text", {"query": "[SEDE]", "replacement": "MILANO"},
                           "call_sede"),
        tool_call_response("insert_markdown", {"where": "end", "markdown": CONCLUSIONS},
                           "call_concl"),
        with_usage(tool_call_response("redazione_completata", {"riepilogo": RIEPILOGO},
                                      "call_done"), (2400, 60)),
    ])
    server.start()
    try:
        yield server
    finally:
        server.stop()


def test_guided_drafting_through_the_redazione_and_domande_panels(soffice, stub, tmp_path):
    cfg = tmp_path / "config.toml"
    ref_path = tmp_path / REFERENCE_NAME
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
    from librelex_ext.document import read_reference
    from librelex_ext.session import Session

    class RecView:
        """The five panels as one recorder: the last argument of every View method."""
        def __init__(self):
            self.lines, self.status = [], []
            self.stream, self.usage, self.consent = "", None, None
            self.consents = []
            self.templates, self.template = ([], None), None
            self.reference, self.partitions, self.questions = ["", False], [], []
            self.draft_status = ["", False]
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
        def set_templates(self, labels, selected): self.templates = [list(labels), selected]
        def set_template(self, info): self.template = info
        def set_reference(self, text, present): self.reference = [text, present]
        def set_partitions(self, labels): self.partitions = list(labels)
        def set_draft_status(self, text, started): self.draft_status = [text, started]
        def set_questions(self, questions): self.questions = list(questions)

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

    def redline_texts(doc):
        """The text each tracked change covers, to show what is (and is not) inside it."""
        out, enum = [], doc.Redlines.createEnumeration()
        while enum.hasMoreElements():
            r = enum.nextElement()
            cur = doc.Text.createTextCursorByRange(r.RedlineStart)
            cur.gotoRange(r.RedlineEnd, True)
            out.append(cur.getString())
        return out

    def probe(ctx, out):
        # The similar case, written through LibreOffice's own .docx filter and read back the
        # way the Sfoglia… button does.
        ref_doc = new_doc(ctx)
        ref_doc.Text.insertString(ref_doc.Text.createTextCursor(), {REFERENCE!r}, False)
        ref_url = uno.systemPathToFileUrl({str(ref_path)!r})
        ref_doc.storeToURL(ref_url, (prop("FilterName", "MS Word 2007 XML"),))
        ref_doc.close(True)

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

        s.templates()
        out["state_catalogue"] = pump(s, view, events)
        out["template_labels"] = list(view.templates[0])
        out["templates"] = list(s.draft_view["templates"])

        s.template({TIPO_ATTO!r})
        out["state_template"] = pump(s, view, events)
        out["template_info"] = view.template

        ref = read_reference(ctx, ref_url)
        out["reference_chars"] = ref["chars"]
        s.set_reference(ref["name"], ref["text"])
        out["state_reference"] = pump(s, view, events)
        out["reference_label"] = list(view.reference)

        s.draft_start({TIPO_ATTO!r}, {FIELDS!r}, {NOTES!r})
        out["state_start"] = pump(s, view, events)
        out["questions"] = list(view.questions)
        out["status_start"] = list(view.draft_status)
        out["partitions_start"] = list(view.partitions)
        out["paragraphs_start"] = paragraph_texts(text)
        out["redlines_start"] = redlines(doc)
        out["bookmarks"] = list(doc.getBookmarks().getElementNames())

        s.draft_answer({{"sede": "Milano"}})
        out["state_answer"] = pump(s, view, events)
        out["questions_end"] = list(view.questions)
        out["status_end"] = list(view.draft_status)
        out["partitions"] = list(view.partitions)
        out["paragraphs"] = paragraph_texts(text)
        out["redlines"] = redlines(doc)
        out["redline_texts"] = redline_texts(doc)
        out["usage"] = view.usage
        out["consents"] = view.consents
        out["consent_pending"] = view.consent
        out["stream"] = view.stream
        out["lines"] = list(view.lines)
        out["transcript"] = list(s.transcript)
        s.shutdown()
        doc.close(True)
    ''', timeout=600, env={"LIBRELEX_CONFIG": str(cfg)})
    for key in ("state_catalogue", "state_template", "state_reference", "state_start",
                "state_answer"):
        assert out[key] == "ready", (key, out[key], out.get("transcript"))

    # --- the Redazione panel before the drafting -----------------------------
    # list_templates filled the list box from the fake catalogue of core/tests/conftest.py.
    tipi = [m["tipo_atto"] for m in out["templates"]]
    assert len(tipi) >= 3 and TIPO_ATTO in tipi, tipi
    assert len(out["template_labels"]) == len(tipi)
    assert out["template_labels"][tipi.index(TIPO_ATTO)].startswith(
        "atti_introduttivi · Ricorso per decreto ingiuntivo")
    # template_info typed the fields and named the deterministic generator behind the act.
    info = out["template_info"]
    assert info["tipo_atto"] == TIPO_ATTO
    assert info["routing"]["tipo"] == "tool_diretto"
    assert info["routing"]["tool"] == "decreto_ingiuntivo"
    assert {c["nome"]: (c["tipo"], c["obbligatorio"]) for c in info["campi"]} == {
        "creditore": ("testo", True), "debitore": ("testo", True),
        "importo": ("numero", True), "provvisoria_esecuzione": ("sino", False)}
    # set_reference: the panel read the .docx itself and only the text reached the core.
    assert out["reference_chars"] == len(REFERENCE)
    assert out["reference_label"] == [
        f"Caso simile: {REFERENCE_NAME} ({len(REFERENCE)} caratteri)", True]

    # --- the deterministic base, before the first model call ------------------
    assert f"LibreLex.atto.{TIPO_ATTO}" in out["bookmarks"], out["bookmarks"]
    assert out["redlines_start"], out["redlines_start"]
    assert all(kind == "Insert" and author == "LibreLex"
               for kind, author in out["redlines_start"]), out["redlines_start"]
    start_texts = [t for _, t in out["paragraphs_start"]]
    assert start_texts[0] == PARAGRAPH
    assert "RICORSO PER DECRETO INGIUNTIVO" in start_texts[1], start_texts
    # The generator's own formula, verbatim, with its placeholder still open: "TRIBUNALE" is
    # the court the fake picks over ten thousand euro, so "12.000" was read as such.
    assert any("ILL.MO SIG. TRIBUNALE DI [SEDE]" in t for t in start_texts), start_texts

    # --- turn 1: the question landed in the Domande panel ---------------------
    assert out["questions"] == [{"campo": "sede", "domanda": "Sede del tribunale?",
                                 "esempio": "Milano", "tipo": "testo"}]
    assert out["status_start"] == ["In attesa delle tue risposte (pannello Domande)", True]
    assert out["partitions_start"] == [BASE_PARTITION, "… segnaposto aperti: 1"]

    # --- the reference act: one consent, for the file, by name ----------------
    assert len(out["consents"]) == 1, out["consents"]
    summary = out["consents"][0]
    assert summary["scope"] == "reference" and summary["name"] == REFERENCE_NAME
    assert summary["chars"] == len(REFERENCE)
    assert summary["model"] == "stub" and summary["endpoint_host"] == "127.0.0.1"
    assert out["consent_pending"] is None

    # --- turn 2: placeholder filled, section added, drafting closed -----------
    assert out["questions_end"] == []
    assert out["status_end"] == ["Redazione completata", True]
    assert out["partitions"] == [BASE_PARTITION, "✓ Conclusioni"]
    paras = out["paragraphs"]
    base_i = next(i for i, (_, t) in enumerate(paras) if "RICORSO PER DECRETO INGIUNTIVO" in t)
    concl_i = next(i for i, (_, t) in enumerate(paras) if t == "Conclusioni")
    assert concl_i > base_i, paras
    assert paras[concl_i][0] == "Heading 2", paras[concl_i]
    assert any("MILANO" in t for _, t in paras), paras
    # The placeholder was filled as a tracked change: the old text is a Delete redline.
    # No Delete redline: the placeholder sat inside LibreLex's own insertion, not yet
    # accepted, so Writer drops the old text outright instead of recording a deletion. The
    # whole drafting is therefore one pending insertion, which also covers the section added
    # afterwards, and it starts after the lawyer's own paragraph.
    assert out["redlines"] == [["Insert", "LibreLex"]], out["redlines"]
    assert len(out["redline_texts"]) == 1, out["redline_texts"]
    tracked = out["redline_texts"][0]
    for needle in ("RICORSO PER DECRETO INGIUNTIVO", "TRIBUNALE DI MILANO", "Conclusioni"):
        assert needle in tracked, (needle, tracked)
    assert "[SEDE]" not in tracked and PARAGRAPH not in tracked, tracked

    # --- what the panels show -------------------------------------------------
    assert out["stream"] == ""          # every turn ended on a tool call, not on prose
    assert out["lines"] == out["transcript"]
    t = out["transcript"]
    assert t[0] == f"Catalogo: {len(tipi)} modelli."
    assert t[1].startswith("Base deterministica: decreto_ingiuntivo · Bozza indicativa")
    assert t[2] == f"Atto di riferimento: {REFERENCE_NAME} ({len(REFERENCE)} caratteri)."
    assert t[3] == f"Tu: avvio redazione {TIPO_ATTO} (3 campi)"
    assert t[4] == ""                   # the separator a turn opens with
    assert t[5] == "Tu: risposte a 1 domande"
    assert t[6] == ""
    assert t[7].startswith("Inserito nei paragrafi ")
    assert t[8] == "Riepilogo della redazione:\n" + RIEPILOGO
    assert len(t) == 9, t
    # render_usage formats with the Italian thousands separator above 999 (spec §5.1).
    assert out["usage"] == "Turno: 2.400 + 60 token · sessione: 4.000 token", out["usage"]

    # --- what reached the endpoint -------------------------------------------
    assert len(stub.requests) == 5, [r["messages"][-1] for r in stub.requests]
    first = stub.requests[0]
    assert first["model"] == "stub" and first["stream"] is True
    user = first["messages"][1]["content"]
    assert user.startswith("Redazione guidata: Ricorso per decreto ingiuntivo")
    assert "- importo: 12.000" in user and f"Note dell'utente: {NOTES}" in user
    assert "Base deterministica già nel documento" in user
    assert "segnaposto ancora aperti: [SEDE]" in user
    assert f"Atto di riferimento disponibile: {REFERENCE_NAME} ({len(REFERENCE)} caratteri)" in user
    assert "# Ricetta di redazione" in user
    names = {tool["function"]["name"] for tool in first["tools"]}
    assert {"chiedi_dati", "redazione_completata", "leggi_atto_riferimento",
            "genera_modello_atto", "decreto_ingiuntivo", "contributo_unificato",
            "read_paragraphs", "insert_markdown", "replace_text"} <= names, sorted(names)
    assert not ({"cerca_giurisprudenza", "replace_selection", "add_comment"} & names)
    assert tool_messages(first) == []
    # The reference act travelled once, wrapped as data, after the consent.
    ref_msgs = tool_messages(stub.requests[1])
    assert len(ref_msgs) == 1, ref_msgs
    assert ref_msgs[0]["content"] == (
        f"<<<DATI: atto di riferimento ({REFERENCE_NAME})>>>\n{REFERENCE}\n<<<FINE DATI>>>")
    # The last call of the second turn: the first turn compacted, this turn's two writes.
    last = tool_messages(stub.requests[4])
    assert len(last) == 4, last
    assert last[0]["content"].startswith("[risultato di leggi_atto_riferimento omesso")
    assert last[1]["content"].startswith("[risultato di chiedi_dati omesso")
    assert last[2]["content"].startswith("Sostituite 1 occorrenze di «[SEDE]».")
    assert last[3]["content"].startswith("Inserito nei paragrafi ")
    blob = json.dumps(stub.requests, ensure_ascii=False)
    assert blob.count(REFERENCE) == 1          # compacted out of the second turn's history
    assert PARAGRAPH not in blob               # never read: the document asked for no consent
