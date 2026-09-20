# Guided Drafting, Extension (Plan 2 of 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the guided drafting flow of `docs/superpowers/specs/2026-09-19-guided-drafting-design.md` §6 into the sidebar on top of the core protocol delivered by Plan 1 (`2026-09-19-guided-drafting-core.md`): two new panels, "Redazione" (catalogue, typed fields, notes, reference act, start, partitions, resume, status) and "Domande" (the model's structured questions as fields with "Continua"), the document adapter's `replace_text` and the reference-file reader, transcript separators in "Risposte", the Azioni panel without the old "Redigi da modello" button, and the headless end-to-end test of a decreto ingiuntivo drafted through the new protocol.

**Architecture:** The extension keeps its shape: one `PanelFactory`, one `Session` per document, `layout.build(kind, width)` control tables with fixed heights and visibility toggles (no runtime control creation), `views.CompositeView` routing view methods to the panel of the right kind, `render.py` for plain-text copy. The session mirrors the drafting state it receives in `Final.summary` (`draft_view`) so a rebuilt panel is replayed like consent and usage today. UNO work stays in `document.py` (tracked `replace_text`, hidden-document `read_reference`) and `panel.py` (file picker, drop target). The design's single "Redazione" panel becomes two ("Redazione" + "Domande") for height, per design §9 assumption 1, decided up front.

**Tech Stack:** extension: LibreOffice Python 3.13 stdlib + uno; headless tests through `extension/tests/headless/conftest.py`; core: one sentence in the system prompt.

**Spec:** design doc §4 (protocol, as implemented by Plan 1: `list_templates`, `template_info`, `set_reference`, `draft` with `action` start/answer/continue, `Final.summary` keys `tipo_atto, domande, partizioni, segnaposto_aperti, completata, riepilogo, ended_by`), §5.2 (reference file), §6 (panels), §7 (security), §8 (tests). Main spec §5.1 (panels), §5.3 (`replace_text` row), §5.4 (writes as tracked changes), §8.2 (consent, scope `reference`). Branch `feature/guided-drafting` (Plan 1 merged in, core 0.4.0).

## Global Constraints

- Extension: stdlib + uno only; every UNO call on the UI thread; controls added to the container window's own model; the XDL keeps `withtitlebar="false"`; Italian plain-text copy in the panels; the notice stays; every button has a tooltip; `layout.build` clamps at `MIN_WIDTH` and its heights are width-independent.
- Wire contract (Plan 1, binding): commands `list_templates {query?}` → `Final.summary {modelli: [{tipo_atto, descrizione, categoria, tier}], totale, query}`; `template_info {tipo_atto}` → `Final.summary {tipo_atto, descrizione, categoria, campi_obbligatori, campi_opzionali, tool_calcolo, riferimenti_normativi, avvertenze, istruzioni, routing {tipo, tool, parametri_fissi, resource}, campi: [{nome, tipo: testo|numero|data|sino, obbligatorio, descrizione}]}` or `Error(code="template_not_found")`; `set_reference {name, text}` → `Final.summary {riferimento: {name, chars, troncato} | None}`; `draft {action: "start", tipo_atto, fields, notes}` / `{action: "answer", answers}` / `{action: "continue", message}` → the model-turn `Final` (`text`, `usage`, `summary {stopped?, inserted, flagged, unverified, tool_calls, usage_totals, tipo_atto, domande: [{campo, domanda, esempio, tipo}], partizioni: [{titolo, from_id, to_id}], segnaposto_aperti: [str], completata, riepilogo, ended_by: "questions"|"done"|None, base_errore: str|None}`) or `Error(code="bad_request")` or, on `start` with an unknown `tipo_atto`, `Error(code="template_not_found")`; a cancelled draft turn answers a `Final` with `cancelled: true`, `summary.stopped == "cancelled"` and the same draft keys (partitions inserted so far), and the session merges it into `draft_view` without resetting anything; when `base_errore` is set the Redazione status says `Base non generata: <base_errore>` and the panel appends the same line to Risposte; `doc_call replace_text {query, replacement, undo_label, paragraph_id, all}` → `{count, anchors: [{paragraph_id, start, end}]}`; `consent_request.summary` may carry `scope: "reference"` and `name`.
- The extension trims the reference text to `MAX_REFERENCE_CHARS = 60_000` characters before sending `set_reference` (the constant is duplicated in `session.py` with a comment naming the core's `agent/state.py`; the core trims again): a `set_reference` line must never approach the core's 4 MiB stdio line limit, and the lawyer is told in the reference label when the file was cut (`troncato` from the core's answer).
- Panels: `layout.KINDS == ("Actions", "Drafting", "Questions", "Citations", "Answers")`; `Sidebar.xcu` panels `LibreLexDraftingPanel` ("Redazione", OrderIndex 150, URL suffix `Drafting`) and `LibreLexQuestionsPanel` ("Domande", OrderIndex 160, URL suffix `Questions`); Azioni loses the `Draft` button.
- Field rows: eight in "Redazione" (`FieldLabel1..8` + `Field1..8`) and eight in "Domande" (`QuestionLabel1..8` + `Answer1..8`), hidden until used; a template with more than eight fields puts the rest in the notes hint (label: "Altri campi (scrivili nelle note): a, b").
- Reference file: `.odt`, `.docx`, `.rtf`, `.txt` through `loadComponentFromURL` hidden and read-only; closed right after reading; text trimmed by the core (`MAX_REFERENCE_CHARS`); the panel never keeps the text, only `{name, chars, troncato}` from the core's answer; the drop target accepts one `file://` URI and falls back to the "Sfoglia…" button when it cannot be installed.
- Transcript: model turns (chat, research, draft) are preceded by `Tu: <label>` and their text starts with `LibreLex: `; a blank line closes the turn; deterministic commands keep today's rendering.
- Version: extension `0.6.0` (`extension/librelex_ext/__init__.py`, `extension/description.xml`, `extension/tests/test_paths.py`, `extension/tests/test_build_oxt.py`); core stays `0.4.0` (one prompt sentence only, no version bump).
- Tooling and commits as Plan 1 (ruff E F I UP B line 100; Conventional Commits with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` via several `-m` flags, no heredocs, never amend, never push; never run LibreOffice's bundled python, `unopkg` or `scripts/dev_install.sh`; headless tests via `conftest.py`'s `run_probe`; English code, comments and docs; Italian panel copy; no em or en dashes in prose).

---

## File structure

```
extension/librelex_ext/
├── document.py        # replace_text (tracked), read_reference (hidden document)
├── layout.py          # KINDS five panels; Drafting and Questions tables; Actions without Draft; TOOLTIPS/ACTIONS/BUSY_DISABLED
├── views.py           # ROUTES for the six new view methods; panel_kind
├── render.py          # render_template_notes, render_reference, render_partitions, render_draft_status, render_riepilogo, turn separators
├── session.py         # draft_view state, templates/template/set_reference/clear_reference/draft_start/draft_answer/draft_continue, _on_final routing, separators, replay
└── panel.py           # Drafting/Questions panels, file picker, drop target, View methods, replay
extension/Sidebar.xcu, extension/description.xml, extension/librelex_ext/__init__.py
extension/tests/test_layout.py, test_views.py, test_render.py, test_session.py, test_paths.py, test_build_oxt.py
extension/tests/headless/test_write.py (replace_text), test_reference.py (new), test_install.py (five panels), test_e2e_draft.py (rewritten)
core/src/librelex_core/agent/prompt.py (+ tests/agent/test_prompt_state.py): plain text in chat
README.md, docs/superpowers/specs/2026-09-07-librelex-it-design.md §5.1, docs/superpowers/specs/2026-09-19-guided-drafting-design.md §6.1 (two panels)
```

---

### Task 1: Document adapter: tracked `replace_text` and the reference-file reader

**Files:**
- Modify: `extension/librelex_ext/document.py`, `extension/librelex_ext/session.py` (`dispatch_doc_call` only)
- Test: `extension/tests/headless/test_write.py`, `extension/tests/headless/test_reference.py` (new), `extension/tests/test_session.py` (`test_dispatch_maps_actions_and_wraps_results`)

**Interfaces:**
- Produces: `DocumentAdapter.replace_text(query: str, replacement: str, undo_label: str, paragraph_id: str | None = None, all: bool = False) -> dict` returning `{"count": int, "anchors": [{"paragraph_id", "start", "end"}]}`: occurrences are located first (as `find_text` does, through the index and `para.getString().find`), then replaced from the last to the first (so earlier offsets stay valid) inside one undo context named `undo_label`, with `_identity("LibreLex")` and `_recording(True)` so each replacement is a tracked deletion plus insertion (`cursor = e.container.createTextCursorByRange(e.para.getStart()); cursor.goRight(start, False); cursor.goRight(len(query), True); cursor.setString(replacement)`); `all=False` replaces the first occurrence of the document (or of `paragraph_id`); anchors carry the original `start` and `end = start + len(replacement)` (with `all=True`, later anchors of the same paragraph are approximate, documented in the docstring); empty `query` → `{"count": 0, "anchors": []}`; an unknown `paragraph_id` raises `DocumentActionError` as `_entry` does.
- `document.read_reference(ctx, url: str) -> dict` returning `{"name": <file name, URL-unquoted>, "text": <body paragraphs joined by "\n\n">, "chars": len(text)}`: `desktop.loadComponentFromURL(url, "_blank", 0, (prop("Hidden", True), prop("ReadOnly", True)))`; `None` → `DocumentActionError("impossibile aprire il file: <name>")`; a model without `Text` (a Draw document for a PDF) → `DocumentActionError("formato non supportato (usa odt, docx, rtf o txt): <name>")` after closing it; paragraphs read through a temporary `DocumentAdapter(ctx, model).read_paragraphs()` (body, footnotes and table cells, in document order); `model.close(True)` in a `finally`.
- `session.dispatch_doc_call` gains `if action == "replace_text": return adapter.replace_text(args["query"], args["replacement"], args["undo_label"], args.get("paragraph_id"), bool(args.get("all", False)))`.

- [ ] **Step 1: Failing tests**

`extension/tests/test_session.py`, in `test_dispatch_maps_actions_and_wraps_results` add a `replace_text` call to `FakeAdapter` (add `def replace_text(self, query, replacement, undo_label, paragraph_id=None, all=False): self.calls.append(("replace_text", query, replacement, paragraph_id, all)); return {"count": 1, "anchors": [{"paragraph_id": "p:0", "start": 3, "end": 7}]}`) and assert `dispatch_doc_call(adapter, "replace_text", {"query": "[SEDE]", "replacement": "Roma", "undo_label": "u", "all": True}) == {"count": 1, "anchors": [...]}` and the recorded call `("replace_text", "[SEDE]", "Roma", None, True)`.

`extension/tests/headless/test_write.py`, append (use the file's existing helpers; read it first for `run_probe` usage, `redlines`, `paragraph_texts`):

```python
def test_replace_text_is_a_tracked_deletion_plus_insertion(soffice):
    out = run_probe(soffice, "replace_text", '''
    def probe(ctx, out):
        doc = new_doc(ctx)
        text = doc.Text
        cur = text.createTextCursor()
        text.insertString(cur, "ILL.MO TRIBUNALE DI [SEDE] e ancora [SEDE].", False)
        text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
        text.insertString(cur, "Avv. [LEGALE]", False)
        a = DocumentAdapter(ctx, doc)
        out["first"] = a.replace_text("[SEDE]", "MILANO", "LibreLex: test")
        out["redlines_after_first"] = redlines(doc)
        out["rest"] = a.replace_text("[SEDE]", "MILANO", "LibreLex: test", all=True)
        out["legale"] = a.replace_text("[LEGALE]", "Mario Rossi", "LibreLex: test",
                                       paragraph_id="p:1")
        out["none"] = a.replace_text("[NIENTE]", "x", "LibreLex: test")
        out["texts"] = paragraph_texts(text)
        out["redlines"] = redlines(doc)
        out["undo"] = doc.getUndoManager().getUndoActionsTitle() if hasattr(doc, "getUndoManager") else ""
        doc.close(True)
    ''')
    assert out["first"]["count"] == 1
    assert out["first"]["anchors"] == [{"paragraph_id": "p:0", "start": 20, "end": 26}]
    # every replacement is recorded as a deletion plus an insertion by LibreLex
    kinds = [k for k, _ in out["redlines_after_first"]]
    assert sorted(kinds) == ["Delete", "Insert"]
    assert all(author == "LibreLex" for _, author in out["redlines_after_first"])
    assert out["rest"]["count"] == 1 and out["legale"]["count"] == 1 and out["none"]["count"] == 0
    # the visible text (deleted redline text is still part of getString on 26.8: assert on
    # presence of the replacements and on the redline count, not on exact equality)
    body = [t for _, t in out["texts"]]
    assert "MILANO" in body[0] and "Mario Rossi" in body[1]
    assert len([k for k, _ in out["redlines"] if k == "Insert"]) == 3
    assert len([k for k, _ in out["redlines"] if k == "Delete"]) == 3
```

(If on 26.8 `paragraph_texts` no longer shows the deleted text, tighten the assertion to exact strings and say so in the report.)

`extension/tests/headless/test_reference.py` (new):

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""read_reference: a similar case chosen by the lawyer is read through LibreOffice's own
filters in a hidden document and closed right after (design §5.2)."""
import pytest

from tests.headless.conftest import run_probe

pytestmark = pytest.mark.headless

SAVE = {"docx": "MS Word 2007 XML", "odt": "writer8", "txt": "Text"}


@pytest.mark.parametrize("ext", ["docx", "odt", "txt"])
def test_read_reference_reads_body_paragraphs_and_closes_the_document(soffice, tmp_path, ext):
    path = tmp_path / f"ricorso_rossi.{ext}"
    out = run_probe(soffice, f"reference_{ext}", f'''
    from librelex_ext.document import read_reference

    def probe(ctx, out):
        doc = new_doc(ctx)
        text = doc.Text
        cur = text.createTextCursor()
        text.insertString(cur, "RICORSO PER DECRETO INGIUNTIVO", False)
        text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
        text.insertString(cur, "Il ricorrente espone quanto segue.", False)
        url = uno.systemPathToFileUrl({str(path)!r})
        doc.storeToURL(url, (prop("FilterName", {SAVE[ext]!r}),))
        doc.close(True)
        desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        before = sum(1 for _ in _components(desktop))
        out["ref"] = read_reference(ctx, url)
        out["open_after"] = sum(1 for _ in _components(desktop)) - before

    def _components(desktop):
        e = desktop.getComponents().createEnumeration()
        while e.hasMoreElements():
            yield e.nextElement()
    ''')
    ref = out["ref"]
    assert ref["name"] == f"ricorso_rossi.{ext}"
    assert ref["text"].startswith("RICORSO PER DECRETO INGIUNTIVO")
    assert "Il ricorrente espone quanto segue." in ref["text"]
    assert ref["chars"] == len(ref["text"])
    assert out["open_after"] == 0                 # the hidden document was closed


def test_read_reference_reports_a_missing_file(soffice, tmp_path):
    out = run_probe(soffice, "reference_missing", f'''
    from librelex_ext.document import DocumentActionError, read_reference

    def probe(ctx, out):
        try:
            read_reference(ctx, uno.systemPathToFileUrl({str(tmp_path / "manca.docx")!r}))
        except DocumentActionError as e:
            out["error"] = str(e)
    ''')
    assert out["error"].startswith("impossibile aprire il file: manca.docx")
```

Run: `cd extension && uv run pytest tests/test_session.py -q` (fails on `replace_text`) and `uv run pytest tests/headless/test_write.py tests/headless/test_reference.py -q` (fails: no attribute).

- [ ] **Step 2: Implement**

`document.py`: `replace_text` as in Interfaces (one undo context around all replacements; positions computed with the same loop as `find_text`, grouped by entry; for each entry, replace from the highest start to the lowest; `all=False` stops after the first entry's first occurrence in document order); `read_reference` as in Interfaces (`from urllib.parse import unquote`; name = `unquote(url.rsplit("/", 1)[-1])`; the model is a Writer document when `hasattr(model, "Text")`; close in `finally` with `suppress(Exception)`). `session.dispatch_doc_call`: the new branch.

- [ ] **Step 3: Run and commit**

`cd extension && uv run ruff check . && uv run pytest -q -m "not headless" && uv run pytest tests/headless/test_write.py tests/headless/test_reference.py -q` → green.

```bash
git add extension
git commit -m "feat(extension): tracked replace_text and read_reference through a hidden document" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Layout and registration of the "Redazione" and "Domande" panels

**Files:**
- Modify: `extension/librelex_ext/layout.py`, `extension/librelex_ext/views.py`, `extension/Sidebar.xcu`
- Test: `extension/tests/test_layout.py`, `extension/tests/test_views.py`, `extension/tests/headless/test_install.py`

**Interfaces:**
- `layout.KINDS = ("Actions", "Drafting", "Questions", "Citations", "Answers")`; `layout.FIELD_ROWS = 8`; `layout.PARTITIONS_H = 48`; `layout.NOTES_H = 40`; `layout.QUESTION_LABEL_H = 20`.
- `build("Actions", w)`: as today minus the `Draft` row (the consent block moves up by one row); `ACTIONS` loses `"Draft"`, `BUSY_DISABLED` loses `"Draft"`, `TOOLTIPS` loses `"Draft"`.
- `build("Drafting", w)`, top to bottom (names, kinds, props; every row full width `inner` unless said; heights from the constants; `GAP` between rows): `TemplateSearch` (Edit, w = inner - SMALL_BUTTON_W - GAP, h INPUT_H) + `TemplateRefresh` (Button "Cerca", w SMALL_BUTTON_W, h INPUT_H, right-aligned, same y); `Template` (ListBox, h INPUT_H, `Dropdown: True`, `LineCount: 12`); `TemplateNotes` (FixedText, h 20, `MultiLine`, `TextColor: GRAY`, Label ""); `FieldsLabel` (FixedText section "Campi del modello", bold, h SECTION_H); eight rows `FieldLabel{n}` (FixedText, x MARGIN, w `(inner * 2) // 5`, h INPUT_H, `MultiLine: False`, Label "") + `Field{n}` (Edit, x = MARGIN + label width + GAP, w = rest, h INPUT_H), all `Visible: False`; `NotesLabel` (section "Fatti e note", bold, h SECTION_H); `Notes` (Edit, h NOTES_H, `MultiLine: True`, `VScroll: True`, `AutoVScroll: True`); `ReferenceLabel` (FixedText, h 20, `MultiLine`, Label "Caso simile: nessuno"); `ReferenceBrowse` (Button "Sfoglia…", left column) + `ReferenceClear` (Button "Rimuovi", right column, `Enabled: False`); `Start` (Button "Avvia redazione", `Enabled: False`); `PartitionsLabel` (section "Partizioni inserite", bold, h SECTION_H); `Partitions` (ListBox, h PARTITIONS_H, `Dropdown: False`); `ResumeInput` (Edit, h INPUT_H, `Visible: False`); `Resume` (Button "Continua la redazione", `Visible: False`); `DraftStatus` (FixedText, h STATUS_H, `MultiLine`, Label "Scegli un atto").
- `build("Questions", w)`: `QuestionsHint` (FixedText, h 20, `MultiLine`, `TextColor: GRAY`, Label "Il modello ha bisogno di questi dati: rispondi e premi Continua."); eight rows `QuestionLabel{n}` (FixedText, h QUESTION_LABEL_H, `MultiLine: True`, Label "") + `Answer{n}` (Edit, h INPUT_H) on the next row, all `Visible: False`; `Continue` (Button "Continua", `Visible: False`); `QuestionsStatus` (FixedText, h LABEL_H, Label "Nessuna domanda in sospeso").
- `ACTIONS` gains `"TemplateRefresh": "template_search"`, `"ReferenceBrowse": "reference_browse"`, `"ReferenceClear": "reference_clear"`, `"Start": "draft_start"`, `"Resume": "draft_resume"`, `"Continue": "draft_answer"`; `BUSY_DISABLED` gains `"TemplateRefresh"`, `"ReferenceBrowse"`, `"ReferenceClear"`, `"Start"`, `"Resume"`, `"Continue"`; `TOOLTIPS` for each (Italian, e.g. `TemplateRefresh`: "Filtra il catalogo dei modelli di atto con il testo scritto a sinistra (vuoto: tutto il catalogo)", `Template`: "Tipo di atto da redigere: scegli e compila i campi", `ReferenceBrowse`: "Scegli un atto simile (odt, docx, rtf, txt) da cui il modello prende struttura e stile, mai i fatti", `ReferenceClear`: "Toglie l'atto di riferimento", `Start`: "Avvia la redazione: la base deterministica entra subito nel documento, poi il modello chiede i dati mancanti", `Resume`: "Riprende la redazione dopo un'interruzione, con l'istruzione scritta qui sopra se ne dai una", `Continue`: "Invia le risposte al modello", `Partitions`: "Clic su una partizione: vai al paragrafo", `Notes`: "Fatti del caso e istruzioni per il modello, in forma libera", `TemplateSearch`: "Parola chiave del tipo di atto (es. ingiuntivo, precetto, privacy)"); `SECTIONS` gains `FieldsLabel`, `NotesLabel`, `PartitionsLabel`.
- `views.ROUTES` gains `set_templates`, `set_template`, `set_reference`, `set_partitions`, `set_draft_status` → `"Drafting"` and `set_questions` → `"Questions"`; `CompositeView` gains the six methods with these signatures: `set_templates(labels: list[str], selected: int | None)`, `set_template(info: dict | None)`, `set_reference(text: str, present: bool)`, `set_partitions(labels: list[str])`, `set_draft_status(text: str, started: bool)`, `set_questions(questions: list[dict])`.
- `Sidebar.xcu`: the two panel nodes as the Global Constraints say (same props as the existing ones).

- [ ] **Step 1: Failing tests**

`extension/tests/test_layout.py`: `EXPECTED` becomes five kinds (`Actions` without `Draft`; `Drafting` and `Questions` with every name above); the old `test_draft_button_is_a_full_width_row...` is deleted; `test_copy_and_button_rows` keeps working (no Draft row); append:

```python
def test_drafting_panel_rows_and_hidden_blocks():
    by = {c.name: c for c in build("Drafting", WIDTH)}
    assert by["TemplateSearch"].y == by["TemplateRefresh"].y
    assert by["TemplateRefresh"].x + by["TemplateRefresh"].w == WIDTH - MARGIN
    assert by["Template"].props["Dropdown"] is True and by["Template"].props["LineCount"] == 12
    for n in range(1, FIELD_ROWS + 1):
        label, edit = by[f"FieldLabel{n}"], by[f"Field{n}"]
        assert label.y == edit.y and label.x == MARGIN and edit.x == label.x + label.w + GAP
        assert edit.x + edit.w == WIDTH - MARGIN
        assert label.props["Visible"] is False and edit.props["Visible"] is False
    assert by["Field1"].y > by["FieldsLabel"].y and by["Notes"].props["MultiLine"] is True
    assert by["ReferenceBrowse"].y == by["ReferenceClear"].y
    assert by["ReferenceClear"].props["Enabled"] is False and by["Start"].props["Enabled"] is False
    assert by["Partitions"].props["Dropdown"] is False
    assert by["ResumeInput"].props["Visible"] is False and by["Resume"].props["Visible"] is False
    assert by["DraftStatus"].props["Label"] == "Scegli un atto"
    order = [c.name for c in build("Drafting", WIDTH)]
    assert order.index("Start") < order.index("PartitionsLabel") < order.index("Resume") < order.index("DraftStatus")
    assert total_height(build("Drafting", WIDTH)) <= 460


def test_questions_panel_rows_hidden_until_needed():
    by = {c.name: c for c in build("Questions", WIDTH)}
    for n in range(1, FIELD_ROWS + 1):
        label, edit = by[f"QuestionLabel{n}"], by[f"Answer{n}"]
        assert label.props["MultiLine"] is True and edit.y == label.y + label.h + GAP
        assert label.props["Visible"] is False and edit.props["Visible"] is False
    assert by["Continue"].props["Visible"] is False
    assert by["QuestionsStatus"].props["Label"] == "Nessuna domanda in sospeso"
    assert total_height(build("Questions", WIDTH)) <= 380


def test_actions_lost_the_draft_button_and_the_new_actions_are_wired():
    names = {c.name for c in build("Actions", WIDTH)}
    assert "Draft" not in names and "Draft" not in ACTIONS and "Draft" not in TOOLTIPS
    for name, command in (("TemplateRefresh", "template_search"), ("ReferenceBrowse", "reference_browse"),
                          ("ReferenceClear", "reference_clear"), ("Start", "draft_start"),
                          ("Resume", "draft_resume"), ("Continue", "draft_answer")):
        assert ACTIONS[name] == command and name in BUSY_DISABLED and name in TOOLTIPS
    assert KINDS == ("Actions", "Drafting", "Questions", "Citations", "Answers")
```

(`FIELD_ROWS` imported from layout.) `extension/tests/test_views.py`: `panel_kind(".../Drafting") == "Drafting"`, `panel_kind(".../Questions") == "Questions"`; `ROUTES` maps the six new methods as above; a `CompositeView` with a fake panel attached as `"Drafting"` receives `set_template({"x": 1})` and one attached as `"Questions"` receives `set_questions([])`.

`extension/tests/headless/test_install.py`: the panel set becomes `{"LibreLexActionsPanel", "LibreLexDraftingPanel", "LibreLexQuestionsPanel", "LibreLexCitationsPanel", "LibreLexAnswersPanel"}`.

Run: `cd extension && uv run pytest tests/test_layout.py tests/test_views.py -q` → failures.

- [ ] **Step 2: Implement**

`layout.py`: the constants, `KINDS`, the two `build` branches, the Actions change, `ACTIONS`/`BUSY_DISABLED`/`TOOLTIPS`/`SECTIONS`. `views.py`: `ROUTES` and the six methods. `Sidebar.xcu`: the two nodes (Title `Redazione` / `Domande`, Id, DeckId, ContextList, ImplementationURL `private:resource/toolpanel/LibreLexPanelFactory/Drafting` / `.../Questions`, OrderIndex 150 / 160, WantsCanvas false).

- [ ] **Step 3: Run and commit**

`cd extension && uv run ruff check . && uv run pytest -q -m "not headless"` → green; `uv run pytest tests/headless/test_install.py -q` → green (five panels).

```bash
git add extension
git commit -m "feat(extension): Redazione and Domande panels in the deck layout; Azioni without the Draft button" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Session state and rendering for the guided flow, transcript separators

**Files:**
- Modify: `extension/librelex_ext/session.py`, `extension/librelex_ext/render.py`
- Test: `extension/tests/test_session.py`, `extension/tests/test_render.py`

**Interfaces:**
- `render.py`: `render_template_notes(info: dict) -> str` = the routing line (`"Base deterministica: <tool>"` for `tool_diretto`, `"Base deterministica (adattata): <tool>"` for `tool_enhance`, `"Composizione dal modello (risorsa del catalogo)"` for `resource`, `"Preventivo: <tool>"` for `preventivo_procedura`, `"Composizione dal modello"` otherwise) followed, when `avvertenze` is non-empty, by `" · " + "; ".join(avvertenze)`; `render_reference(ref: dict | None) -> str` = `"Caso simile: nessuno"` or `"Caso simile: <name> (<chars formatted with the Italian dot> caratteri[, troncato])"`; `render_partitions(partizioni: list[dict], open_placeholders: list[str]) -> list[str]` = `"✓ <titolo>"` per partition plus, when `open_placeholders`, a last entry `"… segnaposto aperti: <n>"`; `render_draft_status(view: dict) -> str` (`"Scegli un atto"` when no template; `"Compila i campi obbligatori"` when a template is chosen and not started; `"Redazione in corso…"` while busy; `"In attesa delle tue risposte (pannello Domande)"` when questions are pending; `"Redazione completata"` when done; `"Interrotta: premi Continua la redazione"` when started, not done, no questions, last turn stopped; `"Pronta per il prossimo passo"` otherwise); `render_riepilogo(riepilogo: str) -> str` = `"Riepilogo della redazione:\n" + riepilogo`; `render_questions_hint(n: int) -> str` = `f"Il modello ha bisogno di {n} dati: rispondi e premi Continua."`; `render_field_label(campo: dict) -> str` = `nome` plus `" *"` when mandatory plus a type hint in parentheses for `numero` ("numero"), `data` ("data"), `sino` ("sì/no"); `render_question_label(q: dict) -> str` = `domanda` plus `f" (es. {esempio})"` when `esempio` plus the same type hint.
- `Session`: `self.draft_view: dict` with keys `templates: list[dict]`, `query: str | None`, `template: dict | None`, `fields: dict[str, str]`, `notes: str`, `reference: dict | None`, `questions: list[dict]`, `partitions: list[dict]`, `open_placeholders: list[str]`, `started: bool`, `done: bool`, `stopped: str | None`; methods: `templates(query: str = "")` → `run_command("list_templates", {"query": query.strip()} if query.strip() else {})`; `template(tipo_atto: str)` → `run_command("template_info", {"tipo_atto": tipo_atto})`; `set_reference(name: str, text: str)` → `run_command("set_reference", {"name": name, "text": text})` (the panel reads the file; the session only forwards); `clear_reference()` → `run_command("set_reference", {"text": ""})`; `draft_start(tipo_atto: str, fields: dict[str, str], notes: str)` (refuses with status `"Scegli prima un tipo di atto"` when `tipo_atto` is empty and with `"Compila i campi obbligatori: a, b"` when a mandatory field of `draft_view["template"]["campi"]` is blank; stores `fields`/`notes` in the view) → `run_command("draft", {"action": "start", ...})`; `draft_answer(answers: dict[str, str])` (refuses with `"Nessuna domanda in sospeso"` when `draft_view["questions"]` is empty) → `run_command("draft", {"action": "answer", "answers": answers})`; `draft_continue(message: str = "")` (refuses with `"Nessuna redazione in corso"` when not started) → `run_command("draft", {"action": "continue", "message": message.strip()})`; `goto_partition(index: int)` → `adapter.goto(from_id)` best effort.
- `_on_final` routing (checked in this order before today's branches): `"modelli" in summary` → `draft_view["templates"] = summary["modelli"]`, `draft_view["query"] = summary.get("query")`, `view.set_templates([f"{m['categoria']} · {m['descrizione']}" for m in modelli], selected=None)`, `_append(msg["text"])`; `"campi" in summary and "routing" in summary` → `draft_view["template"] = summary`, `view.set_template(summary)`, `view.set_draft_status(render_draft_status(view), started=False)`, `_append(...)` of the routing line and avvertenze; `"riferimento" in summary` (key present) → `draft_view["reference"] = summary["riferimento"]`, `view.set_reference(render_reference(...), present=bool(...))`, `_append(msg["text"])`; a draft turn (`"partizioni" in summary`): the model-turn branch as today (streamed text, notes, usage) plus `draft_view` updates (`questions`, `partitions`, `open_placeholders`, `done = summary["completata"]`, `started = True`, `stopped = summary.get("stopped")`), `view.set_questions(questions)`, `view.set_partitions(render_partitions(...))`, `view.set_draft_status(render_draft_status(view), started=True)`, and, when `completata` and `riepilogo`, `_append(render_riepilogo(riepilogo))`.
- Transcript separators: `_submit` takes an optional `label: str | None`; `chat(message)` passes `f"Tu: {message}"`, `research(question)` passes `f"Tu: ricerca: {question or 'testo selezionato'}"`, `draft_start` passes `f"Tu: avvio redazione {tipo_atto} ({len(fields)} campi)"`, `draft_answer` passes `f"Tu: risposte a {len(answers)} domande"`, `draft_continue` passes `f"Tu: continua{': ' + message if message else ''}"`; the label is appended to the transcript when the request is actually sent (`_send_payload`), so a refused or queued request does not leave a dangling line; the first delta of a streamed turn is prefixed with `"LibreLex: "` (in the stream buffer too, so replay matches); a non-streamed final text of a model turn is appended as `"LibreLex: " + text`.
- `bind`/replay: `bind` calls `set_templates`, `set_template`, `set_reference`, `set_partitions`, `set_draft_status`, `set_questions` from `draft_view` (the panel's own `_replay` for the two new kinds does the same in Task 4); `set_busy(True)` also drives the status to `"Redazione in corso…"` when a draft request is running (`self._draft_request: bool` set by the three draft methods, cleared on final/error/exit).
- `NullView` and `FakeView` gain the six methods.

- [ ] **Step 1: Failing tests**

`extension/tests/test_render.py`, append:

```python
def test_render_guided_drafting_copy():
    info = {"routing": {"tipo": "tool_diretto", "tool": "decreto_ingiuntivo"},
            "avvertenze": ["Bozza indicativa"]}
    assert render_template_notes(info) == "Base deterministica: decreto_ingiuntivo · Bozza indicativa"
    assert render_template_notes({"routing": {"tipo": "resource"}, "avvertenze": []}) == (
        "Composizione dal modello (risorsa del catalogo)")
    assert render_reference(None) == "Caso simile: nessuno"
    assert render_reference({"name": "ricorso_rossi.docx", "chars": 12345, "troncato": False}) == (
        "Caso simile: ricorso_rossi.docx (12.345 caratteri)")
    assert render_reference({"name": "x.odt", "chars": 70000, "troncato": True}).endswith(", troncato)")
    assert render_partitions([{"titolo": "Base: Ricorso"}, {"titolo": "Premesse in fatto"}], ["[SEDE]"]) == [
        "✓ Base: Ricorso", "✓ Premesse in fatto", "… segnaposto aperti: 1"]
    assert render_field_label({"nome": "importo", "tipo": "numero", "obbligatorio": True}) == "importo * (numero)"
    assert render_field_label({"nome": "provvisoria_esecuzione", "tipo": "sino", "obbligatorio": False}) == (
        "provvisoria_esecuzione (sì/no)")
    assert render_question_label({"campo": "sede", "domanda": "Sede del tribunale?", "esempio": "Milano",
                                  "tipo": "testo"}) == "Sede del tribunale? (es. Milano)"
    assert render_question_label({"campo": "d", "domanda": "Data?", "esempio": "", "tipo": "data"}) == "Data? (data)"
    assert render_questions_hint(3) == "Il modello ha bisogno di 3 dati: rispondi e premi Continua."
    assert render_riepilogo("Calcoli: CU 129,50").startswith("Riepilogo della redazione:\n")
    view = {"template": None, "started": False, "done": False, "questions": [], "stopped": None, "busy": False}
    assert render_draft_status(view) == "Scegli un atto"
    view["template"] = {"tipo_atto": "x"}
    assert render_draft_status(view) == "Compila i campi obbligatori"
    view.update(started=True, busy=True)
    assert render_draft_status(view) == "Redazione in corso…"
    view.update(busy=False, questions=[{"campo": "a"}])
    assert render_draft_status(view) == "In attesa delle tue risposte (pannello Domande)"
    view.update(questions=[], stopped="iterations")
    assert render_draft_status(view) == "Interrotta: premi Continua la redazione"
    view.update(stopped=None, done=True)
    assert render_draft_status(view) == "Redazione completata"
```

(`render_draft_status` reads a `busy` key too; the session passes `{**self.draft_view, "busy": self._draft_request}`.)

`extension/tests/test_session.py`: extend `FakeView` with the six methods recording their last arguments (`self.templates`, `self.template`, `self.reference`, `self.partitions`, `self.draft_status`, `self.questions`); append:

```python
def _hello(s, bridges):
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.4.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})


def test_templates_and_template_info_fill_the_drafting_view():
    s, adapter, view, bridges = make()
    s.templates("  ingiuntivo ")
    _hello(s, bridges)
    assert bridges[0].sent[-1]["name"] == "list_templates" and bridges[0].sent[-1]["args"] == {"query": "ingiuntivo"}
    s.handle_event({"kind": "message", "msg": {"type": "final", "request_id": "r1", "text": "Catalogo: 1 modelli.",
                    "summary": {"modelli": [{"tipo_atto": "decreto_ingiuntivo_ordinario",
                                             "descrizione": "Ricorso per decreto ingiuntivo", "categoria": "atti_introduttivi",
                                             "tier": 1}], "totale": 1, "query": "ingiuntivo"}}})
    assert view.templates == (["atti_introduttivi · Ricorso per decreto ingiuntivo"], None)
    assert s.draft_view["templates"][0]["tipo_atto"] == "decreto_ingiuntivo_ordinario"
    s.template("decreto_ingiuntivo_ordinario")
    assert bridges[0].sent[-1] == {"type": "command", "id": "r2", "doc_id": "d1", "name": "template_info",
                                   "args": {"tipo_atto": "decreto_ingiuntivo_ordinario"}}
    info = {"tipo_atto": "decreto_ingiuntivo_ordinario", "descrizione": "Ricorso", "categoria": "atti_introduttivi",
            "campi": [{"nome": "creditore", "tipo": "testo", "obbligatorio": True, "descrizione": ""},
                      {"nome": "importo", "tipo": "numero", "obbligatorio": True, "descrizione": ""}],
            "routing": {"tipo": "tool_diretto", "tool": "decreto_ingiuntivo", "parametri_fissi": {}, "resource": None},
            "avvertenze": ["Bozza indicativa"], "campi_obbligatori": ["creditore", "importo"], "campi_opzionali": [],
            "tool_calcolo": [], "riferimenti_normativi": [], "istruzioni": ""}
    s.handle_event({"kind": "message", "msg": {"type": "final", "request_id": "r2", "text": "Modello: 2 campi.", "summary": info}})
    assert view.template == info and s.draft_view["template"] == info
    assert view.draft_status == ("Compila i campi obbligatori", False)
    assert "Base deterministica: decreto_ingiuntivo" in view.lines[-1]


def test_draft_start_validates_fields_then_sends_and_the_turn_updates_the_view():
    s, adapter, view, bridges = make()
    s.draft_start("", {}, "")
    assert view.status == "Scegli prima un tipo di atto" and not bridges
    s.draft_view["template"] = {"tipo_atto": "x", "campi": [
        {"nome": "creditore", "tipo": "testo", "obbligatorio": True}, {"nome": "importo", "tipo": "numero", "obbligatorio": True},
        {"nome": "note_extra", "tipo": "testo", "obbligatorio": False}]}
    s.draft_start("x", {"creditore": "Alfa", "importo": " "}, "")
    assert view.status == "Compila i campi obbligatori: importo" and not bridges
    s.draft_start("x", {"creditore": "Alfa", "importo": "12000"}, "fattura 12")
    _hello(s, bridges)
    sent = bridges[0].sent[-1]
    assert sent["name"] == "draft" and sent["args"] == {"action": "start", "tipo_atto": "x",
                                                        "fields": {"creditore": "Alfa", "importo": "12000"}, "notes": "fattura 12"}
    assert s.transcript[-1] == "Tu: avvio redazione x (2 campi)"
    assert view.draft_status == ("Redazione in corso…", True)
    s.handle_event({"kind": "message", "msg": {"type": "delta", "request_id": "r1", "text": "Mi servono"}})
    assert view.stream == "LibreLex: Mi servono"
    s.handle_event({"kind": "message", "msg": {"type": "final", "request_id": "r1", "text": "Mi servono",
                    "usage": {"input_tokens": 10, "output_tokens": 2, "cost_usd": None},
                    "summary": {"tool_calls": 2, "inserted": [{"from_id": "p:1", "to_id": "p:9", "titolo": "Base: Ricorso"}],
                                "flagged": [], "unverified": [], "usage_totals": {"input_tokens": 10, "output_tokens": 2},
                                "tipo_atto": "x", "domande": [{"campo": "sede", "domanda": "Sede?", "esempio": "Milano", "tipo": "testo"}],
                                "partizioni": [{"titolo": "Base: Ricorso", "from_id": "p:1", "to_id": "p:9"}],
                                "segnaposto_aperti": ["[SEDE]"], "completata": False, "riepilogo": "", "ended_by": "questions"}}})
    assert s.transcript[-3:] == ["LibreLex: Mi servono", "", "Inserito nei paragrafi p:1-p:9"]
    assert view.questions == [{"campo": "sede", "domanda": "Sede?", "esempio": "Milano", "tipo": "testo"}]
    assert view.partitions == ["✓ Base: Ricorso", "… segnaposto aperti: 1"]
    assert view.draft_status == ("In attesa delle tue risposte (pannello Domande)", True)
    s.draft_answer({"sede": "Milano"})
    assert bridges[0].sent[-1]["args"] == {"action": "answer", "answers": {"sede": "Milano"}}
    assert s.transcript[-1] == "Tu: risposte a 1 domande"
    s.handle_event({"kind": "message", "msg": {"type": "final", "request_id": "r2", "text": "Fatto.",
                    "usage": {"input_tokens": 10, "output_tokens": 2, "cost_usd": None},
                    "summary": {"tool_calls": 3, "inserted": [{"from_id": "p:10", "to_id": "p:12", "titolo": "Conclusioni"}],
                                "flagged": [], "unverified": [], "usage_totals": {"input_tokens": 20, "output_tokens": 4},
                                "tipo_atto": "x", "domande": [], "partizioni": [{"titolo": "Base: Ricorso", "from_id": "p:1", "to_id": "p:9"},
                                {"titolo": "Conclusioni", "from_id": "p:10", "to_id": "p:12"}], "segnaposto_aperti": [],
                                "completata": True, "riepilogo": "Calcoli: CU 129,50.", "ended_by": "done"}}})
    assert view.questions == [] and view.partitions == ["✓ Base: Ricorso", "✓ Conclusioni"]
    assert view.draft_status == ("Redazione completata", True)
    assert "LibreLex: Fatto." in view.lines and view.lines[-1] == "Riepilogo della redazione:\nCalcoli: CU 129,50."
    s.draft_answer({"x": "y"})
    assert view.status == "Nessuna domanda in sospeso"
    s.draft_continue("aggiungi la provvisoria esecuzione")
    assert bridges[0].sent[-1]["args"] == {"action": "continue", "message": "aggiungi la provvisoria esecuzione"}


def test_reference_round_trip_and_rebind_replays_the_drafting_view():
    s, adapter, view, bridges = make()
    s.set_reference("ricorso_rossi.docx", "RICORSO ...")
    _hello(s, bridges)
    assert bridges[0].sent[-1]["args"] == {"name": "ricorso_rossi.docx", "text": "RICORSO ..."}
    s.handle_event({"kind": "message", "msg": {"type": "final", "request_id": "r1", "text": "Atto di riferimento: ricorso_rossi.docx (11 caratteri).",
                    "summary": {"riferimento": {"name": "ricorso_rossi.docx", "chars": 11, "troncato": False}}}})
    assert view.reference == ("Caso simile: ricorso_rossi.docx (11 caratteri)", True)
    view2 = FakeView()
    s.bind(view2, lambda ev: None)
    assert view2.reference == ("Caso simile: ricorso_rossi.docx (11 caratteri)", True)
    assert view2.draft_status == ("Scegli un atto", False) and view2.questions == [] and view2.partitions == []
    s.clear_reference()
    assert bridges[0].sent[-1]["args"] == {"text": ""}
    s.handle_event({"kind": "message", "msg": {"type": "final", "request_id": "r2", "text": "Atto di riferimento rimosso.",
                    "summary": {"riferimento": None}}})
    assert view.reference == ("Caso simile: nessuno", False)


def test_chat_and_research_get_turn_separators():
    s, adapter, view, bridges = make()
    s.chat("che dice?")
    _hello(s, bridges)
    assert s.transcript[-1] == "Tu: che dice?"
    s.handle_event({"kind": "message", "msg": {"type": "final", "request_id": "r1", "text": "Dice X.",
                    "usage": {"input_tokens": 1, "output_tokens": 1, "cost_usd": None},
                    "summary": {"tool_calls": 0, "inserted": [], "flagged": [], "unverified": [],
                                "usage_totals": {"input_tokens": 1, "output_tokens": 1}}}})
    assert view.lines[-2:] == ["LibreLex: Dice X.", ""]
    s.research("usucapione")
    assert s.transcript[-1] == "Tu: ricerca: usucapione"
```

Existing tests that assert exact transcript contents after chat/research finals (`test_chat_sends_context_streams_deltas_and_shows_usage`, `test_final_cancelled_after_streaming_still_shows_notes_and_usage`, `test_final_with_no_streamed_text_still_shows_the_notes_and_the_usage_line`, `test_research_final_without_deltas_shows_its_text_the_grounding_notes_and_usage`, `test_a_rebuilt_panel_gets_back_the_pending_consent_and_the_usage_line`) are updated for the `Tu:` line and the `LibreLex: ` prefix; the headless `test_e2e_chat.py` asserts `out["stream"] == ANSWER` and `out["transcript"] == [ANSWER, ""]`: update it to `"LibreLex: " + ANSWER` and `["Tu: Di cosa parla?", "LibreLex: " + ANSWER, ""]` (it is run in Task 5's full headless pass; adjust it here, it is a two-line change).

Run: `cd extension && uv run pytest tests/test_render.py tests/test_session.py -q` → failures.

- [ ] **Step 2: Implement**

`render.py`: the helpers above. `session.py`: the view state, methods, routing, separators and replay as in Interfaces; `_submit(name, payload_factory, label=None)` storing the label with the pending payload; `_send_payload` appends the label to the transcript (and the view) before sending; `_on_delta` prefixes the first chunk; `_on_final` model-turn branch appends `"LibreLex: " + text` when nothing was streamed. `NullView` gets the six methods.

- [ ] **Step 3: Run and commit**

`cd extension && uv run ruff check . && uv run pytest -q -m "not headless"` → green.

```bash
git add extension
git commit -m "feat(extension): session state and copy for the guided drafting; Tu/LibreLex turn separators" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Panel wiring: Redazione and Domande behaviour, file picker, drop target, replay, version 0.6.0

**Files:**
- Modify: `extension/librelex_ext/panel.py`, `extension/librelex_ext/__init__.py`, `extension/description.xml`
- Test: `extension/tests/test_paths.py`, `extension/tests/test_build_oxt.py` (versions), `extension/tests/headless/test_panel_drafting.py` (new: the panel's pure-UNO pieces that a hidden document can exercise: `read_reference` through the panel's loader helper and the field collection logic, see below)

**Interfaces:**
- `Panel` gains, for kind `Drafting`: an `XItemListener` on `Template` (selection → `session.template(tipo_atto)` looked up in `session.draft_view["templates"][index]`) and on `Partitions` (selection → `session.goto_partition(index)`); actions `template_search` (`session.templates(TemplateSearch.getText())`), `reference_browse` (file picker: `com.sun.star.ui.dialogs.FilePicker`, `initialize((FILEOPEN_SIMPLE,))` from `com.sun.star.ui.dialogs.TemplateDescription`, `appendFilter("Atti (odt, docx, rtf, txt)", "*.odt;*.docx;*.rtf;*.txt")`, `execute() == 1` → `getSelectedFiles()[0]` (fall back to `getFiles()[0]`) → `self._load_reference(url)`), `reference_clear` (`session.clear_reference()`), `draft_start` (collects `Field{n}` texts for the visible rows, keyed by the field names the panel stored in `self._field_names` when `set_template` ran, plus `Notes.getText()`; `session.draft_start(tipo_atto, fields, notes)`), `draft_resume` (`session.draft_continue(ResumeInput.getText())`, clears the box when taken); for kind `Questions`: action `draft_answer` (collects `Answer{n}` for the visible rows keyed by `self._question_fields`, `session.draft_answer(answers)`).
- `_load_reference(url)`: `ref = document.read_reference(self.ctx, url)`; `session.set_reference(ref["name"], ref["text"])`; a `DocumentActionError` → `set_status`-like feedback through `session.note(f"Caso simile non caricato: {e}")`.
- Drop target (kind `Drafting` only), installed in `getRealInterface` after the controls: `toolkit = ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.Toolkit", ctx)`; `target = toolkit.getDropTarget(self.window.getPeer())`; `target.addDropTargetListener(self)`; `target.setActive(True)`; the panel implements `com.sun.star.datatransfer.dnd.XDropTargetListener` (`drop(dtde)`: for the transferable's flavors pick the first whose `MimeType` starts with `text/uri-list`; `dtde.acceptDrop(dtde.DropAction)`; data = `getTransferData(flavor)` (bytes or str; decode UTF-8, split lines, first line starting with `file://`); `dtde.dropComplete(True)`; `self._load_reference(url)`; anything else → `dtde.rejectDrop()` and `session.note("Trascina un solo file odt, docx, rtf o txt")`; `dragEnter(dtde)`: `dtde.acceptDrag(dtde.DropAction)`; `dragOver`, `dragExit`, `dropActionChanged`: no-ops; `disposing`: no-op). The whole installation is wrapped in `try/except Exception` that logs through `session.note("Trascinamento non disponibile su questo LibreOffice: usa Sfoglia…")` once; the listener methods themselves are wrapped so no exception escapes into UNO.
- View methods on the panel (each a no-op when the control is absent): `set_templates(labels, selected)` (`Template.StringItemList = tuple(labels)`; select `selected` when not None), `set_template(info)` (`TemplateNotes.Label = render_template_notes(info)` or "" when `None`; the first `FIELD_ROWS` fields of `info["campi"]` fill `FieldLabel{n}.Label = render_field_label(campo)` and show the row, the other rows hidden with empty text; more than eight → the extra names appended to `TemplateNotes` as `"Altri campi (scrivili nelle note): a, b"`; `self._field_names = [c["nome"] ...]`; `Start.Enabled = info is not None`), `set_reference(text, present)` (`ReferenceLabel.Label = text`; `ReferenceClear.Enabled = present`), `set_partitions(labels)` (`Partitions.StringItemList`), `set_draft_status(text, started)` (`DraftStatus.Label = text`; `ResumeInput`/`Resume` visible iff `started`), `set_questions(questions)` (rows shown for the questions with `QuestionLabel{n}.Label = render_question_label(q)`, `Answer{n}` emptied, `self._question_fields = [q["campo"] ...]`; `Continue` visible iff questions; `QuestionsHint.Label = render_questions_hint(len(questions))` or the default hint; `QuestionsStatus.Label = "Nessuna domanda in sospeso"` when empty else `""`).
- `_replay` for the two new kinds: from `session.draft_view` through the session's `bind`-style calls (`set_templates`, `set_template`, `set_reference`, `set_partitions`, `set_draft_status`, `set_questions`), plus `set_busy` for the buttons.
- `set_busy` covers the new `BUSY_DISABLED` names (already generic); the `Template` list box stays enabled.
- Versions `0.6.0`.

- [ ] **Step 1: Failing tests**

`extension/tests/test_paths.py` and `extension/tests/test_build_oxt.py` → `0.6.0`.

`extension/tests/headless/test_panel_drafting.py` (new; the panel needs a frame and a parent window the headless run cannot give, so this test exercises the panel's two pure helpers, extracted as module functions in `panel.py`: `collect_fields(names: list[str], values: list[str]) -> dict[str, str]` (strips, keeps empties out) and `first_file_uri(data) -> str | None` (bytes or str `text/uri-list` payload → first `file://` line, `None` otherwise)):

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from tests.headless.conftest import run_probe

pytestmark = pytest.mark.headless


def test_panel_helpers_import_inside_libreoffice_and_behave(soffice):
    out = run_probe(soffice, "panel_helpers", '''
    from librelex_ext.panel import collect_fields, first_file_uri

    def probe(ctx, out):
        out["fields"] = collect_fields(["creditore", "importo", "note"], [" Alfa ", "", "12.000"])
        out["uri_bytes"] = first_file_uri(b"file:///Users/x/ricorso%20rossi.docx\\r\\nfile:///y.odt\\r\\n")
        out["uri_str"] = first_file_uri("https://example.org/x.docx\\n")
        out["uri_none"] = first_file_uri(None)
    ''')
    assert out["fields"] == {"creditore": "Alfa", "note": "12.000"}
    assert out["uri_bytes"] == "file:///Users/x/ricorso%20rossi.docx"
    assert out["uri_str"] is None and out["uri_none"] is None
```

(The probe imports `librelex_ext.panel`, which imports UNO modules: that is why this test is headless. It also proves the module still imports with the drop-target types.)

Run: `cd extension && uv run pytest tests/test_paths.py tests/test_build_oxt.py -q` → version failures; `uv run pytest tests/headless/test_panel_drafting.py -q` → import error on the helpers.

- [ ] **Step 2: Implement**

`panel.py` as in Interfaces (imports: `from com.sun.star.datatransfer.dnd import XDropTargetListener`, `from com.sun.star.ui.dialogs.TemplateDescription import FILEOPEN_SIMPLE`; `render_template_notes`, `render_field_label`, `render_question_label`, `render_questions_hint` from `render`; `read_reference`, `DocumentActionError` from `document`). Keep `Panel.__init__` cheap; the two new kinds register their listeners in `_build_controls` like `Citations` does. Versions.

- [ ] **Step 3: Run and commit**

`cd extension && uv run ruff check . && uv run pytest -q -m "not headless" && uv run pytest tests/headless/test_install.py tests/headless/test_panel_drafting.py -q` → green.

```bash
git add extension
git commit -m "feat(extension): Redazione and Domande panels wired: catalogue, typed fields, reference file (picker and drop), start, answers, resume, partitions (0.6.0)" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: End-to-end drafting test on the new protocol, chat without markdown, docs

**Files:**
- Modify: `extension/tests/headless/test_e2e_draft.py` (rewritten, xfail marker removed), `extension/tests/headless/test_e2e_chat.py` (separator expectations, if not done in Task 3), `core/src/librelex_core/agent/prompt.py`, `core/tests/agent/test_prompt_state.py`, `README.md`, `docs/superpowers/specs/2026-09-07-librelex-it-design.md` (§5.1), `docs/superpowers/specs/2026-09-19-guided-drafting-design.md` (§6.1 note)
- Read: `extension/tests/headless/llm_stub.py`, `extension/tests/headless/conftest.py`, `core/tests/fake_legal_server.py`

**Interfaces:**
- `prompt.py`: the "Uso del documento" section of `SYSTEM_PROMPT` gains the sentence `Nella chat scrivi testo semplice: niente asterischi, cancelletti, trattini di elenco o altri segni markdown, che il pannello non rende.`; `test_prompt_state.py` asserts `"niente asterischi" in SYSTEM_PROMPT` (the existing invariants stay: no digits, length bound; check the bound and raise it by the sentence's length if needed).
- E2E test: drives `Session.templates`, `Session.template`, `Session.set_reference` (from a `.docx` written in the probe with `storeToURL`, read with `document.read_reference`), `Session.draft_start`, `Session.draft_answer` against the real core (`uv run` on the checkout's `core/`), the fake mcp-legal-it (`core/tests/fake_legal_server.py`, which serves `decreto_ingiuntivo` with a `bozza` containing `[SEDE]`) and a scripted `StubLLM`. Stub script, in order: turn 1 (after the core inserted the base): `tool_call_response("leggi_atto_riferimento", {})` then `tool_call_response("chiedi_dati", {"domande": [{"campo": "sede", "domanda": "Sede del tribunale?", "esempio": "Milano"}]})`; turn 2: `tool_call_response("replace_text", {"query": "[SEDE]", "replacement": "MILANO"})`, `tool_call_response("insert_markdown", {"where": "end", "markdown": "## Conclusioni\n\nSi chiede l'ingiunzione di pagamento di Euro 12.000,00."})`, `tool_call_response("redazione_completata", {"riepilogo": "Calcoli: contributo unificato 129,50.\nAllegati: procura, fattura."})`. The probe's `pump` answers every consent with `"once"`. Assertions: `list_templates` filled the view (three entries); `template_info` gave two mandatory fields typed `testo`/`numero` and the routing `decreto_ingiuntivo`; the reference consent was asked once with `scope == "reference"` and `name == "ricorso_rossi.docx"`; the base is in the document as `Insert` redlines by `LibreLex` with the bookmark `LibreLex.atto.decreto_ingiuntivo_ordinario`, before the first model call (the first stub request's messages contain `Base deterministica già nel documento`); turn 1 ended with the question in the Domande view (`view.questions == [...]`), status "In attesa delle tue risposte (pannello Domande)"; after `draft_answer({"sede": "Milano"})`: the stub's second-turn tool messages show `Sostituite 1 occorrenze di «[SEDE]»`, the document contains `MILANO` and a `Conclusioni` heading after the base, redlines include `Delete` and `Insert`, the partitions view lists `✓ Base: ...` and `✓ Conclusioni` with no open placeholders, status "Redazione completata", the transcript carries `Tu: avvio redazione decreto_ingiuntivo_ordinario (3 campi)`, `Tu: risposte a 1 domande`, and the `Riepilogo della redazione:` block; the usage line is set.
- README: the "Redigi da modello" bullet replaced by a subsection "### Guided drafting: the Redazione panel" (English) describing: choose the act (search + list), the typed fields, notes, the similar case (Sfoglia or drag and drop; odt, docx, rtf, txt; consent names the file; structure and style only), Avvia redazione (base inserted at once as a redline with exact legal formulas, then the model's questions in Domande), Continua, the partitions list, resume after an interruption, the summary in Risposte; a line on Italian numeric notation; a line that the drop target may be unavailable on some builds (use Sfoglia).
- Main spec §5.1: "five panels (Azioni, Redazione, Domande, Citazioni, Risposte)" with one sentence per new panel and the removal of the Draft button; design doc §6.1: a note at the top, "Implemented as two panels, Redazione and Domande, per §9 assumption 1 (decided 2026-09-19 for height)".

- [ ] **Step 1: Write the test and the prompt test**

Rewrite `test_e2e_draft.py` on the pattern of `test_e2e_chat.py` (same config, `bridge_factory`, `RecView` extended with the six new view methods recording their last arguments, `pump` granting consent with "once"); build the `.docx` fixture in the probe (`storeToURL` with `FilterName` `MS Word 2007 XML`) containing "RICORSO di riferimento con struttura e stile."; the sequence of session calls with a `pump` after each; collect `out[...]` for every assertion above. Add the prompt assertion.

- [ ] **Step 2: Implement and run**

The prompt sentence; `cd core && uv run pytest tests/agent/test_prompt_state.py -q`; then `cd extension && uv run pytest tests/headless/test_e2e_draft.py -q -x` (up to 7 minutes the first time). Fix the test where the brief left room (call ids, exact heading style), never the meaning of the assertions on redlines, consent, bookmark, partitions and transcript; a product defect found here is fixed with its unit test and reported.

- [ ] **Step 3: Docs, full suites, commit**

README, the two spec edits. `cd core && uv run ruff check . && uv run pytest -q`; `cd extension && uv run ruff check . && uv run pytest -q` (pure + headless, all green, no xfail left).

```bash
git add core extension README.md docs/superpowers/specs
git commit -m "test(extension): end-to-end guided drafting through the Redazione and Domande panels; chat without markdown; docs" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review notes

- Design coverage: §6.1 controls → Tasks 2 and 4 (two panels, ruled); §6.2 session and routing → Task 3; §6.3 Risposte separators and plain text → Tasks 3 and 5; §5.2 file reading → Task 1; §7 (drop target `file://` only, hidden read-only document closed at once, reference text never kept by the panel) → Tasks 1 and 4; §8 extension and headless tests → every task, e2e in Task 5; §9 assumptions 2 and 3 → Task 4 (drop target behind a guard) and Task 1 (hidden `.docx`).
- Type consistency: the six View methods have the same signatures in `views.py` (Task 2), `session.py` (Task 3), `panel.py` (Task 4) and the e2e `RecView` (Task 5); `render_*` names of Task 3 are what Task 4 imports; `collect_fields`/`first_file_uri` of Task 4 are what its headless test imports; the wire contract block is what `session.py` sends and `_on_final` parses.
- Deferred: `requestLayout` dynamic heights; pseudonymisation of the reference; a "recent acts" shortcut; the MCP prompt `redazione_atto` on mcp-legal-it.