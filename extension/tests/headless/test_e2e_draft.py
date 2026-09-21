# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""M3.6 exit criterion, headless: a decreto ingiuntivo drafted through the one-panel Redazione
workbench, on a letterhead template, with a case attachment, on the guided-drafting protocol.

Everything between the panel and the endpoint is real: the session's drafting commands
(`list_templates`, `template_info`, `set_reference`, `set_attachments`, `draft` start/answer),
the Bridge, the core subprocess with its `draft` command, the DocumentAdapter (letterhead and
act styles included) and the fake mcp-legal-it with its catalogue and its `decreto_ingiuntivo`
generator. Only the model is scripted (the localhost SSE stub): it reads the similar case and
the case attachment (one consent each), asks for the missing datum through `chiedi_dati`, then
fills the base's `[SEDE]` placeholder, adds a section listing the attachment and closes with
`redazione_completata`.
"""
import json
import shutil

import pytest

from librelex_ext import paths
from tests.headless.conftest import run_probe
from tests.headless.llm_stub import StubLLM, chunk, tool_call_response, usage
from tests.headless.test_document import PNG_1PX
from tests.headless.test_letterhead import BUILD_SOURCE

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
# The case document (design §4): a fact the model must find here instead of asking for it,
# listed by number in the base's "Si allegano" section below.
ATTACHMENT_NAME = "fattura_12.txt"
ATTACHMENT_TEXT = "Fattura n. 12 del 3 marzo 2025 di Euro 12.000,00."
CONCLUSIONS = ("### CONCLUSIONI\n\nSi chiede l'ingiunzione di pagamento di Euro 12.000,00.\n\n"
               "- doc. 1: fattura n. 12")
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
        # turn 1 (the core has already inserted the base): read the similar case, read the
        # one case attachment, then ask for the one datum neither carries, ending the turn.
        tool_call_response("leggi_atto_riferimento", {}, "call_ref"),
        tool_call_response("leggi_allegato", {"numero": 1}, "call_allegato"),
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
    letterhead_src = tmp_path / "carta.docx"
    letterhead_png = tmp_path / "logo.png"
    attachment_path = tmp_path / ATTACHMENT_NAME
    server = CORE / "tests" / "fake_legal_server.py"
    cfg.write_text(
        "[mcp_legal_it]\nmode = \"local\"\n"
        f"command = [\"uv\", \"run\", \"--project\", \"{CORE}\", \"python\", \"{server}\"]\n"
        "\n[llm]\npreset = \"custom\"\n"
        f"base_url = \"{stub.base_url}\"\napi_key = \"x\"\nmodel = \"stub\"\n",
        encoding="utf-8")
    uv_dir = str(paths.Path(shutil.which("uv")).parent)
    out = run_probe(soffice, "e2e_draft", BUILD_SOURCE.format(png_b64=PNG_1PX) + f'''
    import os, queue
    from librelex_ext import letterheads, paths
    from librelex_ext.bridge import Bridge
    from librelex_ext.document import make_letterhead, read_document
    from librelex_ext.session import Session

    class RecView:
        """The four panels as one recorder: the last argument of every View method."""
        def __init__(self):
            self.lines, self.status = [], []
            self.stream, self.usage, self.consent = "", None, None
            self.consents = []
            self.templates, self.template = ([], None), None
            self.reference, self.partitions, self.questions = ["", False], [], []
            self.draft_status = ["", False]
            self.field_values, self.answer_values = [{{}}, ""], {{}}
            self.step, self.log = 1, []
            self.expected, self.attachments = [], []
            self.letterheads, self.summary = ([], 0), ""
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
        def set_field_values(self, fields, notes): self.field_values = [dict(fields), notes]
        def set_answer_values(self, answers): self.answer_values = dict(answers)
        def set_step(self, step): self.step = step
        def set_log(self, lines): self.log = list(lines)
        def append_log(self, line): self.log.append(line)
        def set_expected_partitions(self, labels): self.expected = list(labels)
        def set_attachments(self, labels): self.attachments = list(labels)
        def set_letterheads(self, labels, selected): self.letterheads = [list(labels), selected]
        def set_summary(self, text): self.summary = text

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

        ref = read_document(ctx, ref_url)
        out["reference_chars"] = ref["chars"]
        s.set_reference(ref["name"], ref["text"])
        out["state_reference"] = pump(s, view, events)
        out["reference_label"] = list(view.reference)

        # Letterhead template (design §5.2): a Word source with a header logo and a footer,
        # built into a .ott, registered in the folder LIBRELEX_CONFIG points the index at,
        # then chosen for this drafting.
        letterhead_url = build_source(ctx, {str(letterhead_src)!r}, {str(letterhead_png)!r})
        modelli = letterheads.templates_dir()
        make_letterhead(ctx, letterhead_url, str(modelli / "SAPG Legal.ott"))
        letterheads.register_letterhead("SAPG Legal", "SAPG Legal.ott", modelli)
        s.set_letterheads(letterheads.list_letterheads())
        s.choose_letterhead(1)
        out["letterhead_labels"] = list(view.letterheads[0])

        # A case document (design §4): read the way the panel reads a drop or a pick, then
        # handed to the session; the model reads it back through leggi_allegato after consent.
        with open({str(attachment_path)!r}, "w", encoding="utf-8") as f:
            f.write({ATTACHMENT_TEXT!r})
        att = read_document(ctx, uno.systemPathToFileUrl({str(attachment_path)!r}))
        s.add_attachment(att["name"], att["text"], att["kind"])
        out["state_attachment"] = pump(s, view, events)
        out["attachment_chars"] = att["chars"]
        out["attachments_after_add"] = list(view.attachments)

        s.draft_start({TIPO_ATTO!r}, {FIELDS!r}, {NOTES!r})
        out["state_start"] = pump(s, view, events)
        out["questions"] = list(view.questions)
        out["status_start"] = list(view.draft_status)
        out["partitions_start"] = list(view.partitions)
        out["step_start"] = view.step
        out["paragraphs_start"] = paragraph_texts(text)
        out["redlines_start"] = redlines(doc)
        out["bookmarks"] = list(doc.getBookmarks().getElementNames())

        s.draft_answer({{"sede": "Milano"}})
        out["state_answer"] = pump(s, view, events)
        out["questions_end"] = list(view.questions)
        out["status_end"] = list(view.draft_status)
        out["partitions"] = list(view.partitions)
        out["step_end"] = view.step
        out["paragraphs"] = paragraph_texts(text)
        out["redlines"] = redlines(doc)
        out["redline_texts"] = redline_texts(doc)
        out["usage"] = view.usage
        out["consents"] = view.consents
        out["consent_pending"] = view.consent
        out["stream"] = view.stream
        out["lines"] = list(view.lines)
        out["log"] = list(view.log)
        out["summary"] = view.summary
        out["transcript"] = list(s.transcript)
        out["page_facts"] = page_facts(doc)
        s.shutdown()
        doc.close(True)
    ''', timeout=600, env={"LIBRELEX_CONFIG": str(cfg)})
    for key in ("state_catalogue", "state_template", "state_reference", "state_attachment",
                "state_start", "state_answer"):
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

    # --- the letterhead: registered, chosen, not yet applied to the document --
    assert out["letterhead_labels"] == ["Nessuna (impaginazione del documento)", "SAPG Legal"]

    # --- the attachment: read by the panel, listed with its number and size ---
    assert out["attachments_after_add"] == [
        f"Doc. 1 · {ATTACHMENT_NAME} ({out['attachment_chars']} caratteri)"]

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

    # --- turn 1: the question landed in the Domande step, step 2 of 4 ---------
    assert out["questions"] == [{"campo": "sede", "domanda": "Sede del tribunale?",
                                 "esempio": "Milano", "tipo": "testo"}]
    assert out["step_start"] == 2
    assert out["status_start"] == [
        "Passo 2 di 4 · Rispondi alla domanda e premi Continua", True]
    assert out["partitions_start"] == [BASE_PARTITION, "… segnaposto aperti: 1"]

    # --- the reference act and the attachment: one consent each, in order -----
    assert len(out["consents"]) == 2, out["consents"]
    ref_summary, att_summary = out["consents"]
    assert ref_summary["scope"] == "reference" and ref_summary["name"] == REFERENCE_NAME
    assert ref_summary["chars"] == len(REFERENCE)
    assert ref_summary["model"] == "stub" and ref_summary["endpoint_host"] == "127.0.0.1"
    assert att_summary["scope"] == "attachments"
    assert att_summary["name"] == f"Doc. 1 {ATTACHMENT_NAME}"
    assert att_summary["chars"] == out["attachment_chars"]
    assert out["consent_pending"] is None

    # --- turn 2: placeholder filled, section added, drafting closed -----------
    assert out["questions_end"] == []
    assert out["step_end"] == 4
    assert out["status_end"] == [
        "Passo 4 di 4 · Redazione completata: Verifica citazioni, poi Nuova redazione", True]
    assert out["partitions"] == [BASE_PARTITION, "✓ CONCLUSIONI"]
    paras = out["paragraphs"]
    base_i = next(i for i, (_, t) in enumerate(paras) if "RICORSO PER DECRETO INGIUNTIVO" in t)
    concl_i = next(i for i, (_, t) in enumerate(paras) if t == "CONCLUSIONI")
    assert concl_i > base_i, paras
    assert any("MILANO" in t for _, t in paras), paras

    # --- act styles: base and turn-2 insertions carry the LibreLex canon ------
    by_text = {t: s for s, t in paras}
    assert by_text.get("RICORSO PER DECRETO INGIUNTIVO") == "LibreLex Titolo atto", paras
    assert by_text.get("ILL.MO SIG. TRIBUNALE DI MILANO") == "LibreLex Intestazione", paras
    assert by_text.get("CONCLUSIONI") == "LibreLex Sezione", paras
    assert by_text.get("- doc. 1: fattura n. 12") == "LibreLex Punto", paras
    lawyer_style = next(s for s, t in paras if t == PARAGRAPH)
    assert not lawyer_style.startswith("LibreLex "), lawyer_style

    # --- the letterhead's page style and the ten act styles landed for real ---
    facts = out["page_facts"]
    assert facts["header"] is True and facts["graphics"] == 1
    assert len(facts["styles"]) == 10, facts["styles"]

    # The placeholder was filled as a tracked change: the old text is a Delete redline.
    # No Delete redline: the placeholder sat inside LibreLex's own insertion, not yet
    # accepted, so Writer drops the old text outright instead of recording a deletion. The
    # whole drafting is therefore one pending insertion, which also covers the section added
    # afterwards, and it starts after the lawyer's own paragraph.
    assert out["redlines"] == [["Insert", "LibreLex"]], out["redlines"]
    assert len(out["redline_texts"]) == 1, out["redline_texts"]
    tracked = out["redline_texts"][0]
    for needle in ("RICORSO PER DECRETO INGIUNTIVO", "TRIBUNALE DI MILANO", "CONCLUSIONI",
                   "doc. 1: fattura n. 12"):
        assert needle in tracked, (needle, tracked)
    assert "[SEDE]" not in tracked and PARAGRAPH not in tracked, tracked

    # --- what the panels show -------------------------------------------------
    assert out["stream"] == ""          # every turn ended on a tool call, not on prose
    assert out["lines"] == out["transcript"]
    log = out["log"]
    assert log[0] == f"Avvio della redazione: {TIPO_ATTO}"
    assert any(line.startswith("Inserito: ") for line in log), log
    assert log[-2:] == ["Sostituito: «[SEDE]»", "Inserito: CONCLUSIONI"], log
    assert out["summary"].startswith("Riepilogo:\n" + RIEPILOGO)
    assert f"Allegati: Doc. 1 {ATTACHMENT_NAME}" in out["summary"], out["summary"]
    t = out["transcript"]
    assert t[0] == f"Catalogo: {len(tipi)} modelli."
    assert t[1].startswith("Base deterministica: decreto_ingiuntivo · Bozza indicativa")
    assert t[2] == f"Atto di riferimento: {REFERENCE_NAME} ({len(REFERENCE)} caratteri)."
    assert t[3] == f"Tu: allegato {ATTACHMENT_NAME}"
    assert t[4] == f"Allegati: 1 documenti ({out['attachment_chars']} caratteri)."
    assert t[5] == f"Tu: avvio redazione {TIPO_ATTO} (3 campi)"
    assert t[6] == ""                   # the separator a turn opens with
    assert t[7] == "Tu: risposte a 1 domande"
    assert t[8] == ""
    assert t[9].startswith("Inserito nei paragrafi ")
    assert t[10] == "Riepilogo della redazione:\n" + RIEPILOGO
    assert len(t) == 11, t
    # render_usage formats with the Italian thousands separator above 999 (spec §5.1).
    assert out["usage"] == "Turno: 2.400 + 60 token · sessione: 4.000 token", out["usage"]

    # --- what reached the endpoint -------------------------------------------
    assert len(stub.requests) == 6, [r["messages"][-1] for r in stub.requests]
    first = stub.requests[0]
    assert first["model"] == "stub" and first["stream"] is True
    user = first["messages"][1]["content"]
    assert user.startswith("Redazione guidata: Ricorso per decreto ingiuntivo")
    assert "- importo: 12.000" in user and f"Note dell'utente: {NOTES}" in user
    assert "Base deterministica già nel documento" in user
    assert "segnaposto ancora aperti: [SEDE]" in user
    assert f"Atto di riferimento disponibile: {REFERENCE_NAME} ({len(REFERENCE)} caratteri)" in user
    assert f"Allegati del fascicolo: Doc. 1 {ATTACHMENT_NAME}" in user
    assert "# Ricetta di redazione" in user
    names = {tool["function"]["name"] for tool in first["tools"]}
    assert {"chiedi_dati", "redazione_completata", "leggi_atto_riferimento", "leggi_allegato",
            "genera_modello_atto", "decreto_ingiuntivo", "contributo_unificato",
            "read_paragraphs", "insert_markdown", "replace_text"} <= names, sorted(names)
    assert not ({"cerca_giurisprudenza", "replace_selection", "add_comment"} & names)
    assert tool_messages(first) == []
    # The reference act travelled once, wrapped as data, after the consent.
    ref_msgs = tool_messages(stub.requests[1])
    assert len(ref_msgs) == 1, ref_msgs
    assert ref_msgs[0]["content"] == (
        f"<<<DATI: atto di riferimento ({REFERENCE_NAME})>>>\n{REFERENCE}\n<<<FINE DATI>>>")
    # The attachment travelled once too, wrapped the same way, right after its own consent.
    att_msgs = tool_messages(stub.requests[2])
    assert len(att_msgs) == 2, att_msgs
    assert att_msgs[1]["content"] == (
        f"<<<DATI: allegato 1 ({ATTACHMENT_NAME})>>>\n{ATTACHMENT_TEXT}\n<<<FINE DATI>>>")
    # The last call of the second turn: the first turn's three tool calls compacted, this
    # turn's two writes.
    last = tool_messages(stub.requests[5])
    assert len(last) == 5, last
    assert last[0]["content"].startswith("[risultato di leggi_atto_riferimento omesso")
    assert last[1]["content"].startswith("[risultato di leggi_allegato omesso")
    assert last[2]["content"].startswith("[risultato di chiedi_dati omesso")
    assert last[3]["content"].startswith("Sostituite 1 occorrenze di «[SEDE]».")
    assert last[4]["content"].startswith("Inserito nei paragrafi ")
    blob = json.dumps(stub.requests, ensure_ascii=False)
    # The reference act is read at the turn's second call and stays in history for the turn's
    # third (the one that reads the attachment too), then both are compacted out of turn 2.
    assert blob.count(REFERENCE) == 2
    assert blob.count(ATTACHMENT_TEXT) == 1     # read only at the turn's last call
    assert PARAGRAPH not in blob                # never read: the document asked for no consent
