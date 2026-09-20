# Drafting Workbench, Extension (Plan 4 of 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the two drafting panels into one Redazione panel with four steps (act and data, questions, drafting in progress with a live log, end), let the lawyer give the case documents as numbered attachments (Writer formats and PDF, read through LibreOffice), format every drafting insertion with the `LibreLex` act styles that reproduce the firm's canon, and put each act on a selectable letterhead template built from the firm's Word letterhead files.

**Architecture:** Three pure modules carry the logic the dev machine can test (the style classifier, the PDF line rebuild, the letterhead folder and index); the adapter gains four UNO functions (`ensure_act_styles`/`_apply_act_styles`, `apply_letterhead`, `make_letterhead`, `read_document`); the Session keeps the whole workbench state (step, log, attachments, letterheads) and drives the transitions; the panel is one XDL window whose four step groups are pre-created and toggled by visibility, as the consent block is today. The wire to the core is Plan 3's: `set_attachments`, `Final.summary.allegati`, the consent scope `attachments`.

**Tech Stack:** extension only (Python 3.12 pure modules, UNO under LibreOffice 26.8 for the adapter and the panel); tests: pure pytest on the dev machine, headless probes through `tests/headless/conftest.py`'s `run_probe`, the e2e drafting test with the real core.

**Spec:** `docs/superpowers/specs/2026-09-20-drafting-workbench-design.md` §3 (the panel), §4.2 (reading the documents), §5.1 to §5.4 (styles, templates, applying them, the script), §6 (security), §7 (tests), §8 (assumptions), §9 (amendments). Depends on Plan 3 (`2026-09-20-drafting-workbench-core.md`, same branch `feature/drafting-workbench`): the core must already answer `set_attachments` and expose `leggi_allegato`.

## Global Constraints

- Extension: Python 3.12 (LibreOffice's), stdlib + UNO only in `librelex_ext` (no third-party imports); `layout.py`, `views.py`, `render.py`, `session.py`, `paths.py` and the three new pure modules import no UNO; every new module starts with `# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.`; ruff `E F I UP B` line 100; the pure suite (`cd extension && uv run pytest -q -m "not headless"`) stays green at every commit.
- Code, comments, docs in English; every user-facing string in Italian; no em or en dashes in docs prose.
- Limits duplicated from the core (`session.py`, kept in sync by hand as `MAX_REFERENCE_CHARS` is): `MAX_ATTACHMENT_CHARS = 60_000`, `MAX_ATTACHMENTS = 12`, `MAX_ATTACHMENTS_CHARS = 300_000`; `MAX_LOG_LINES = 200`.
- Deck: four panels, `KINDS = ("Actions", "Drafting", "Citations", "Answers")`; `Sidebar.xcu` loses `LibreLexQuestionsPanel`; the Redazione panel's four steps share one area of `DRAFT_AREA_H = 404` dialog units plus the status line (total ≤ 440).
- Security (§6): documents read in hidden, read-only documents with `MacroExecutionMode` 0 and `UpdateDocMode` 0, closed in a `finally`; the panel holds names and sizes only (the Session keeps the attachment texts in memory for the replace-all resend, never on disk, never in the transcript or the log); templates under `<config dir>/modelli/`, never overwritten; drops accept `file://` URIs only.
- Version: extension `0.7.0` (`extension/librelex_ext/__init__.py`, `extension/description.xml`, `extension/tests/test_build_oxt.py`).
- Commits: Conventional Commits, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` through several `-m` flags, never amend, never push. Never run `unopkg` or LibreOffice's bundled python from the harness; headless tests go through `run_probe` (soffice with a private profile). Never modify anything under `/Users/gpuzio/Desktop/CODE/server-infra2.0/`.
- Deviations from the spec, decided here (low impact, both documented in the README): the letterhead added from the panel takes the source file's stem as its name (a name prompt would need a dialog of its own; the script and the index file allow any name); one document per drop or pick (a multi-file drop takes the first and says so), because every add is one `set_attachments` round trip and the session refuses a second request while one runs.

---

## File structure

```
extension/librelex_ext/
├── styles.py          # NEW, pure: ACT_STYLES table, act_style_for(text, origin, from_end), list_prefix(label)
├── pdftext.py         # NEW, pure: rebuild_lines(frames) for the Draw PDF import
├── letterheads.py     # NEW, pure: templates_dir, index load/save, list/register/remember, slug, NONE_LABEL
├── document.py        # ensure_act_styles, _apply_act_styles, insert_markdown(act_styles=), apply_letterhead, make_letterhead, read_document (+ read_reference alias)
├── layout.py          # KINDS without Questions; Drafting table in four steps; DRAFT_STEPS, DRAFT_SHARED, DRAFT_CONSENT
├── views.py           # ROUTES for the new methods; BROADCAST = (set_busy, set_consent)
├── render.py          # step-aware render_draft_status; render_attachments, render_expected_partitions, render_log_insert, render_summary, letterhead labels
├── session.py         # draft_view step/log/expected/attachments/letterheads/letterhead; attachments API; letterhead at start; transitions; act_styles on doc calls; drop_role
├── panel.py           # one Redazione panel, four steps; attachments and letterhead controls; log; collapse of the other panels
├── Sidebar.xcu        # four panels
scripts/make_letterhead.py   # NEW: NAME SOURCE [--out DIR], headless LibreOffice on the pattern of lo_install.py
extension/tests/test_styles.py, test_pdftext.py, test_letterheads.py (new), test_layout.py, test_views.py, test_render.py, test_session.py, test_build_oxt.py
extension/tests/headless/test_styles.py, test_letterhead.py, test_document.py (new), test_reference.py (folded into test_document.py), test_panel_drafting.py, test_e2e_draft.py
README.md, docs/superpowers/specs/2026-09-07-librelex-it-design.md (§5.1, §5.3, §8.2, Appendix A), docs/superpowers/specs/2026-09-19-guided-drafting-design.md (§6 pointer)
```

---

### Task 1: The pure foundations (styles, PDF lines, letterhead folder, rendering)

**Files:**
- Create: `extension/librelex_ext/styles.py`, `extension/librelex_ext/pdftext.py`, `extension/librelex_ext/letterheads.py`
- Modify: `extension/librelex_ext/render.py`
- Test: `extension/tests/test_styles.py`, `extension/tests/test_pdftext.py`, `extension/tests/test_letterheads.py`, `extension/tests/test_render.py`

**Interfaces (produced, used by Tasks 2 to 5):**
- `styles.py`: `STYLE_PREFIX = "LibreLex "`; `COMMON = {"CharFontName": "Times New Roman", "CharHeight": 12.0, "ParaLineSpacing": ("PROP", 150), "ParaFirstLineIndent": 0, "ParaTopMargin": 0, "ParaBottomMargin": 0}`; `ACT_STYLES: dict[str, dict]` with the ten names of design §5.1 and these properties on top of `COMMON` (`ParaAdjust` as the enum name string, margins in 1/100 mm, `CharWeight` 150.0 for bold): `"LibreLex Intestazione": {"ParaAdjust": "CENTER", "ParaBottomMargin": 200}`, `"LibreLex Titolo atto": {"ParaAdjust": "CENTER", "CharWeight": 150.0}`, `"LibreLex Sezione": {"ParaAdjust": "CENTER", "CharWeight": 150.0, "ParaTopMargin": 300}`, `"LibreLex Corpo": {"ParaAdjust": "BLOCK"}`, `"LibreLex Punto": {"ParaAdjust": "BLOCK", "ParaLeftMargin": 500, "ParaFirstLineIndent": -500}`, `"LibreLex Ruolo parte": {"ParaAdjust": "RIGHT", "CharWeight": 150.0}`, `"LibreLex Contro": {"ParaAdjust": "CENTER", "CharWeight": 150.0}`, `"LibreLex Separatore": {"ParaAdjust": "CENTER"}`, `"LibreLex Citazione": {"ParaAdjust": "BLOCK", "ParaLeftMargin": 1000, "ParaRightMargin": 1000, "CharHeight": 11.0}`, `"LibreLex Firma": {"ParaAdjust": "RIGHT"}`; `style_properties(name) -> dict` = `{**COMMON, **ACT_STYLES[name]}`; `ORIGINS = ("heading1", "heading2", "heading3", "list", "quote", "body")`; `act_style_for(text: str, origin: str, from_end: int) -> str` implementing design §5.3 in this order, first match wins: `heading1` → Intestazione, `heading2` → Titolo atto, `heading3` → Sezione; stripped text matching `^(\*\s*){3,7}$` → Separatore; stripped text lowercased `== "contro"` → Contro; matching `^- .{2,40} -$` → Ruolo parte; `list` → Punto; `quote` → Citazione; text starting with `Avv. ` or equal to `[Luogo], [Data]` or (`from_end < 5` and matching `^[A-ZÀ-Ù][a-zà-ù]+, \d{1,2} [a-z]+ \d{4}$`) → Firma; else Corpo. `list_prefix(label: str) -> str`: `"N. "` when the label starts with digits (the digits kept), else `"- "`.
- `pdftext.py`: `Frame = tuple[int, int, int, int, str]` as `(page, y, x, height, text)`; `rebuild_lines(frames: list[Frame]) -> str`: frames grouped by page (ascending), within a page sorted by `y` then `x`; a frame joins the current line when `abs(centre - line_centre) < 0.5 * max(height, line_height)` (centre = y + height/2, the line's centre and height are those of its first frame); at flush the line's frames are sorted by `x` and their stripped texts joined with one space, empty texts dropped; lines joined with `\n`; pages after the first are preceded by the line `--- pagina N ---` (N = page number, 1-based); no frame with text at all → `""`.
- `letterheads.py`: `INDEX_NAME = "modelli.json"`; `NONE_LABEL = "Nessuna (impaginazione del documento)"`; `templates_dir() -> Path` = `paths.config_path().parent / "modelli"` (so `LIBRELEX_CONFIG` redirects it in tests); `slug(name) -> str` (letters, digits, spaces, `-` and `_` kept, other characters dropped, runs of spaces collapsed, stripped, `"modello"` when empty); `load_index(folder=None) -> dict` = `{"templates": [ {"name", "file", "default": bool} ], "last": str | None}`, a missing or unreadable or malformed file gives the empty index; `save_index(index, folder=None)` (folder 0700, file 0600, `ensure_private` of `paths`); `list_letterheads(folder=None) -> list[dict]` = `[{"name", "path": str, "default": bool}]`: the index entries whose file exists under the folder, in index order, then every `*.ott` in the folder not named by the index, sorted by name, with `name` = file stem and `default` False; `register_letterhead(name, filename, folder=None, default=False) -> dict` (the index gains the entry unless a same-name entry exists, in which case its `file` is updated; returns the entry); `remember_choice(name: str | None, folder=None)` (sets `last`); `initial_choice(entries, index) -> str | None` = `index["last"]` if it names an entry, else the first `default` entry's name, else None; `template_path(name, folder=None) -> Path` = `folder / (slug(name) + ".ott")`.
- `render.py`: `EXPECTED_PARTITIONS = ("Intestazione", "Parti", "Premesse", "Diritto", "Conclusioni", "Allegati")`; `render_expected_partitions(expected: list[str], partitions: list[dict]) -> list[str]` marks `"✓ "` the expected names whose first five letters (lowercased) occur in some inserted partition's `titolo` (lowercased), `"· "` the others; `render_attachments(attachments) -> list[str]` = `f"Doc. {n} · {name} ({chars} caratteri)"` + `", troncato"` inside the parentheses when `troncato`; `render_log_insert(markdown) -> str` = `"Inserito: " + first non-empty line without leading `#`, `-`, `>`, `*` and spaces, cut at 60 characters with `…`; `render_summary(summary) -> str` = lines: `"Riepilogo:\n" + riepilogo` when present, `"Allegati: Doc. 1 nome; Doc. 2 nome"` when `allegati`, `"Segnaposto aperti: a, b"` when any, `render_base_error` when `base_errore`, the `_STOP_NOTES` line when `stopped`, joined by `"\n"`, `"Nessun riepilogo."` when nothing applies; `render_letterhead_labels(entries) -> list[str]` = `[NONE_LABEL, *names]`; `render_questions_hint(n)` = `f"Il modello ha bisogno di {n} dati: rispondi e premi Continua; una casella vuota vale come risposta non disponibile."`; `render_draft_status(view)` becomes step-aware over `view["step"]`: step 1 → `"Scegli un atto"` without template, else `"Compila i campi obbligatori e premi Avvia redazione"`; step 2 → `f"Rispondi alle {len(questions)} domande e premi Continua"`; step 3 → `"Redazione in corso: il modello lavora sul documento"` when `busy` else `"In attesa del core"`; step 4 → `render_base_error(base_errore)` when `base_errore` and not `done`, else `"Redazione completata: Verifica citazioni, poi Nuova redazione"` when `done`, else `"Interrotta: Riprendi per continuare"` when `stopped`, else `"Turno concluso: Riprendi per continuare o Nuova redazione"`.

- [ ] **Step 1: Failing tests**

`extension/tests/test_styles.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_ext.styles import ACT_STYLES, COMMON, act_style_for, list_prefix, style_properties


def test_ten_styles_with_the_canon_on_top_of_the_common_font():
    assert len(ACT_STYLES) == 10 and all(n.startswith("LibreLex ") for n in ACT_STYLES)
    corpo = style_properties("LibreLex Corpo")
    assert corpo["CharFontName"] == "Times New Roman" and corpo["CharHeight"] == 12.0
    assert corpo["ParaLineSpacing"] == ("PROP", 150) and corpo["ParaAdjust"] == "BLOCK"
    assert style_properties("LibreLex Punto")["ParaFirstLineIndent"] == -500
    assert style_properties("LibreLex Citazione")["CharHeight"] == 11.0
    assert style_properties("LibreLex Sezione")["ParaTopMargin"] == 300
    assert COMMON["ParaFirstLineIndent"] == 0


def test_act_style_for_follows_the_pattern_order():
    cases = [
        ("TRIBUNALE DI MILANO", "heading1", 9, "LibreLex Intestazione"),
        ("ATTO DI CITAZIONE", "heading2", 9, "LibreLex Titolo atto"),
        ("PREMESSO CHE", "heading3", 9, "LibreLex Sezione"),
        ("* * * * *", "body", 9, "LibreLex Separatore"),
        ("***", "body", 9, "LibreLex Separatore"),
        ("contro", "body", 9, "LibreLex Contro"),
        ("CONTRO", "list", 9, "LibreLex Contro"),
        ("- ricorrente -", "body", 9, "LibreLex Ruolo parte"),
        ("- opponente -", "list", 9, "LibreLex Ruolo parte"),
        ("il credito è certo", "list", 9, "LibreLex Punto"),
        ("Art. 633 c.p.c.: ...", "quote", 9, "LibreLex Citazione"),
        ("Avv. Mario Rossi", "body", 9, "LibreLex Firma"),
        ("[Luogo], [Data]", "body", 9, "LibreLex Firma"),
        ("Milano, 3 marzo 2026", "body", 1, "LibreLex Firma"),
        ("Milano, 3 marzo 2026", "body", 5, "LibreLex Corpo"),
        ("Il sottoscritto espone quanto segue.", "body", 0, "LibreLex Corpo"),
        ("- un trattino lungo che non è un ruolo di parte perché supera i quaranta -",
         "body", 9, "LibreLex Corpo"),
    ]
    for text, origin, from_end, want in cases:
        assert act_style_for(text, origin, from_end) == want, (text, origin)


def test_list_prefix_keeps_numbers_and_dashes_everything_else():
    assert list_prefix("1.") == "1. " and list_prefix("12)") == "12. "
    assert list_prefix("•") == "- " and list_prefix("") == "- "
```

`extension/tests/test_pdftext.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_ext.pdftext import rebuild_lines


def test_words_on_one_baseline_become_one_line_in_x_order():
    frames = [(1, 1000, 3000, 400, "espone"), (1, 1010, 1000, 400, "Il"),
              (1, 990, 2000, 400, "ricorrente"), (1, 1005, 4000, 400, "quanto segue.")]
    assert rebuild_lines(frames) == "Il ricorrente espone quanto segue."


def test_lines_pages_and_empty_frames():
    frames = [(2, 500, 1000, 400, "Seconda pagina"), (1, 1000, 1000, 400, "Prima riga"),
              (1, 1600, 1000, 400, "Seconda riga"), (1, 1600, 3000, 400, "  "),
              (1, 2300, 1000, 400, "")]
    assert rebuild_lines(frames) == "Prima riga\nSeconda riga\n--- pagina 2 ---\nSeconda pagina"
    assert rebuild_lines([]) == "" and rebuild_lines([(1, 0, 0, 10, " ")]) == ""
```

`extension/tests/test_letterheads.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_ext import letterheads


def test_folder_follows_the_config_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRELEX_CONFIG", str(tmp_path / "cfg" / "config.toml"))
    assert letterheads.templates_dir() == tmp_path / "cfg" / "modelli"
    assert letterheads.slug("SAPG Legal") == "SAPG Legal"
    assert letterheads.slug(" Carta / intestata: 2025 ") == "Carta intestata 2025"
    assert letterheads.slug("///") == "modello"
    assert letterheads.template_path("SAPG Legal", tmp_path) == tmp_path / "SAPG Legal.ott"


def test_index_round_trip_listing_and_choice(tmp_path):
    assert letterheads.load_index(tmp_path) == {"templates": [], "last": None}
    (tmp_path / "SAPG Legal.ott").write_bytes(b"x")
    (tmp_path / "Vecchia.ott").write_bytes(b"x")
    letterheads.register_letterhead("SAPG Legal", "SAPG Legal.ott", tmp_path, default=True)
    letterheads.register_letterhead("Manca", "manca.ott", tmp_path)
    entries = letterheads.list_letterheads(tmp_path)
    assert [e["name"] for e in entries] == ["SAPG Legal", "Vecchia"]   # index first, strays after
    assert entries[0]["default"] is True and entries[0]["path"] == str(tmp_path / "SAPG Legal.ott")
    assert entries[1] == {"name": "Vecchia", "path": str(tmp_path / "Vecchia.ott"),
                          "default": False}
    index = letterheads.load_index(tmp_path)
    assert letterheads.initial_choice(entries, index) == "SAPG Legal"
    letterheads.remember_choice("Vecchia", tmp_path)
    assert letterheads.initial_choice(entries, letterheads.load_index(tmp_path)) == "Vecchia"
    letterheads.remember_choice(None, tmp_path)
    assert letterheads.load_index(tmp_path)["last"] is None
    letterheads.register_letterhead("SAPG Legal", "sapg2.ott", tmp_path)   # same name: updated
    assert [t["file"] for t in letterheads.load_index(tmp_path)["templates"]] == [
        "sapg2.ott", "manca.ott"]
    (tmp_path / "modelli.json").write_text("{not json", encoding="utf-8")
    assert letterheads.load_index(tmp_path) == {"templates": [], "last": None}
```

`extension/tests/test_render.py`, append:

```python
def test_workbench_rendering():
    from librelex_ext.render import (EXPECTED_PARTITIONS, render_attachments, render_draft_status,
                                     render_expected_partitions, render_letterhead_labels,
                                     render_log_insert, render_questions_hint, render_summary)
    assert EXPECTED_PARTITIONS[0] == "Intestazione" and EXPECTED_PARTITIONS[-1] == "Allegati"
    marks = render_expected_partitions(["Premesse", "Conclusioni"],
                                       [{"titolo": "Premesse in fatto"}])
    assert marks == ["✓ Premesse", "· Conclusioni"]
    assert render_attachments([{"n": 1, "name": "fattura.pdf", "chars": 1200, "troncato": False},
                               {"n": 2, "name": "delibera.docx", "chars": 60000,
                                "troncato": True}]) == [
        "Doc. 1 · fattura.pdf (1.200 caratteri)", "Doc. 2 · delibera.docx (60.000 caratteri, troncato)"]
    assert render_log_insert("### PREMESSO CHE\n\ntesto") == "Inserito: PREMESSO CHE"
    assert render_log_insert("- " + "x" * 80) == "Inserito: " + "x" * 60 + "…"
    assert render_summary({}) == "Nessun riepilogo."
    text = render_summary({"riepilogo": "Calcoli: ok", "allegati": [{"n": 1, "name": "a.pdf"}],
                           "segnaposto_aperti": ["[SEDE]"], "stopped": "timeout"})
    assert text == ("Riepilogo:\nCalcoli: ok\nAllegati: Doc. 1 a.pdf\nSegnaposto aperti: [SEDE]\n"
                    "[interrotto: tempo massimo]")
    assert render_letterhead_labels([{"name": "SAPG Legal"}]) == [
        "Nessuna (impaginazione del documento)", "SAPG Legal"]
    assert render_questions_hint(3).endswith("una casella vuota vale come risposta non disponibile.")
    base = {"template": {"x": 1}, "questions": [], "done": False, "stopped": None,
            "base_errore": None, "busy": False}
    assert render_draft_status({**base, "step": 1, "template": None}) == "Scegli un atto"
    assert render_draft_status({**base, "step": 1}) == (
        "Compila i campi obbligatori e premi Avvia redazione")
    assert render_draft_status({**base, "step": 2, "questions": [{}, {}]}) == (
        "Rispondi alle 2 domande e premi Continua")
    assert render_draft_status({**base, "step": 3, "busy": True}) == (
        "Redazione in corso: il modello lavora sul documento")
    assert render_draft_status({**base, "step": 4, "done": True}) == (
        "Redazione completata: Verifica citazioni, poi Nuova redazione")
    assert render_draft_status({**base, "step": 4, "stopped": "cancelled"}) == (
        "Interrotta: Riprendi per continuare")
    assert render_draft_status({**base, "step": 4, "base_errore": "tool giù"}) == (
        "Base non generata: tool giù")
    assert render_draft_status({**base, "step": 4}) == (
        "Turno concluso: Riprendi per continuare o Nuova redazione")
```

The existing `test_render_guided_drafting_copy` asserts the old status strings: replace its `render_draft_status` and `render_questions_hint` assertions with the ones above (keep the rest).

Run: `cd extension && uv run pytest tests/test_styles.py tests/test_pdftext.py tests/test_letterheads.py tests/test_render.py -q` → failures.

- [ ] **Step 2: Implement** the three modules and the render additions as in Interfaces (`rebuild_lines` with a small `_Line` helper: frames list, centre, height; `letterheads` with `json` and `paths.ensure_private`).

- [ ] **Step 3: Run and commit**

`cd extension && uv run ruff check . && uv run pytest -q -m "not headless"` → green (the session tests that read `render_draft_status` through the session keep passing only if the session still passes `step`; it does not yet, so `render_draft_status` must default `step` to 1 when absent: `view.get("step", 1)`, and the old session tests that expect "In attesa delle tue risposte (pannello Domande)" etc. are rewritten in Task 4; until then mark nothing, just keep the default so Task 1 lands green: with step 1 defaulted, a started drafting reads "Compila i campi…"; adjust the two session tests that assert the old strings (`test_draft_start_validates_fields_then_sends_and_the_turn_updates_the_view`, `test_base_errore_reports_the_missing_base_in_status_and_transcript`, `test_cancelled_draft_turn_merges_into_the_view_without_resetting_it`, `test_choosing_another_template_mid_drafting_keeps_the_resume_controls`, `test_a_core_that_dies_mid_drafting_stops_claiming_a_running_turn`) to the step-1 strings now; Task 4 rewrites them with the real steps).

```bash
git add extension
git commit -m "feat(ext): pure foundations of the drafting workbench: act style table and classifier, PDF line rebuild, letterhead folder and index, step-aware rendering" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: The adapter: act styles, letterhead, template building, document reading with PDF

**Files:**
- Modify: `extension/librelex_ext/document.py`, `extension/librelex_ext/session.py` (only `dispatch_doc_call`'s new `act_styles` parameter)
- Test: `extension/tests/headless/test_styles.py` (new), `extension/tests/headless/test_letterhead.py` (new), `extension/tests/headless/test_document.py` (new; absorbs `test_reference.py`, which is deleted), `extension/tests/test_session.py` (`dispatch_doc_call` passes the flag)

**Interfaces (produced):**
- `DocumentAdapter.ensure_act_styles() -> list[str]`: creates every `styles.ACT_STYLES` name missing from the document's `ParagraphStyles` family (`doc.createInstance("com.sun.star.style.ParagraphStyle")`, `ParentStyle = "Standard"`, then the properties of `styles.style_properties(name)` converted: `ParaAdjust` through `uno.Enum("com.sun.star.style.ParagraphAdjust", value)`, `ParaLineSpacing` through a `com.sun.star.style.LineSpacing` struct with `Mode = 0` (PROP) and `Height = 150`, the rest as given); returns the names created; a style already present is left untouched (§6).
- `DocumentAdapter._origin_of(para) -> str` (one of `styles.ORIGINS`): `ParaStyleName` starting with `Heading ` → `heading1`/`heading2`/`heading3` (levels above 3 count as 3); `NumberingIsNumber` True or `ListLabelString` non-empty → `list`; `ParaStyleName == "Quotations"` → `quote`; else `body`.
- `DocumentAdapter._apply_act_styles(container, paras: list, author) -> None`: for each inserted paragraph, `style = act_style_for(text, origin, from_end)`; list items first get the literal prefix `styles.list_prefix(para.ListLabelString)` inserted at their start with recording ON (so it belongs to the same tracked insertion, signed by the caller's identity context) and their numbering removed with recording OFF (`setPropertyToDefault("NumberingRules")`, then `NumberingStyleName = ""`, each in its own `suppress(Exception)`); then `ParaStyleName = style` with recording OFF (no Format redlines). Called from `_insert_block` after `_fix_first_style` when `act_styles` is True, after `ensure_act_styles()`.
- `DocumentAdapter.insert_markdown(where, markdown, undo_label, bookmark=None, author=None, act_styles=False)` and `_insert_block(cur, container, markdown, bookmark, author, act_styles=False)`; `session.dispatch_doc_call(adapter, action, args, act_styles=False)` passes it to `insert_markdown` only.
- `DocumentAdapter.apply_letterhead(url: str | None) -> dict` = `{"letterhead": bool, "created": list[str]}`: with a url, `doc.getStyleFamilies().loadStylesFromURL(url, (LoadPageStyles True, LoadFrameStyles True, LoadTextStyles False, LoadNumberingStyles False, OverwriteStyles True))` then a second call `(LoadTextStyles True, the other three False, OverwriteStyles False)` so the template's own `LibreLex` styles come in without touching the document's existing paragraph styles; then `ensure_act_styles()`; a failing load raises `DocumentActionError(f"carta intestata non applicabile: {name}")` (name = the file name, unquoted). With `None`, only `ensure_act_styles()` runs.
- `make_letterhead(ctx, source_url: str, out_path: str) -> str` (module function): refuses an existing `out_path` with `DocumentActionError(f"modello già presente: {basename}")`; opens a new hidden Writer document (`private:factory/swriter`), `DocumentAdapter(ctx, doc).apply_letterhead(source_url)`, `storeToURL(file url of out_path, (FilterName "writer8_template",))`, closes it in a `finally`; returns `out_path`. The body stays empty.
- `read_document(ctx, url: str) -> dict` = `{"name", "text", "chars", "kind"}` with `kind` in `("writer", "pdf")`: the file name's extension decides: `.pdf` → loaded with the extra `FilterName "draw_pdf_import"` (the other load properties as today), the result must expose `DrawPages`; every shape of every page with a non-empty `getString()` (guarded) becomes a `pdftext` frame `(page 1-based, shape.Position.Y, shape.Position.X, shape.Size.Height, text)`; `text = rebuild_lines(frames)`; empty → `DocumentActionError(f"PDF senza testo (scansione): non leggibile: {name}")`. Anything else → the Writer path of today's `read_reference` (`Text` attribute, `read_paragraphs`, `"\n\n".join`), error `formato non supportato (usa odt, docx, doc, rtf, txt o pdf): {name}`. The model is closed in a `finally` in both paths. `read_reference = read_document` stays exported for the callers of the guided-drafting plans.

- [ ] **Step 1: Failing headless tests**

`extension/tests/headless/test_document.py` (move the two tests of `test_reference.py` here, renamed to `read_document`, `SAVE` gaining `"doc": "MS Word 97"`, and the `ext` parametrisation `["docx", "odt", "txt", "doc"]`; assert `out["ref"]["kind"] == "writer"`), plus:

```python
PNG_1PX = ("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def test_read_document_rebuilds_the_lines_of_a_two_page_pdf_with_a_header_image(soffice, tmp_path):
    pdf = tmp_path / "diffida.pdf"
    png = tmp_path / "logo.png"
    out = run_probe(soffice, "document_pdf", f'''
    import base64
    from com.sun.star.style.BreakType import PAGE_BEFORE
    from librelex_ext.document import read_document

    def probe(ctx, out):
        with open({str(png)!r}, "wb") as f:
            f.write(base64.b64decode({PNG_1PX!r}))
        doc = new_doc(ctx)
        page = doc.StyleFamilies.getByName("PageStyles").getByName("Standard")
        page.HeaderIsOn = True
        gp = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.graphic.GraphicProvider", ctx)
        graphic = gp.queryGraphic((prop("URL", uno.systemPathToFileUrl({str(png)!r})),))
        img = doc.createInstance("com.sun.star.text.TextGraphicObject")
        img.Graphic = graphic
        header = page.HeaderText
        header.insertTextContent(header.createTextCursor(), img, False)
        text = doc.Text
        cur = text.createTextCursor()
        text.insertString(cur, "Il ricorrente espone quanto segue in questa riga giustificata.", False)
        cur.ParaAdjust = 2      # BLOCK: the PDF import then gives one frame per word
        text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
        text.insertString(cur, "Seconda riga.", False)
        text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
        cur.BreakType = PAGE_BEFORE
        text.insertString(cur, "Pagina due.", False)
        url = uno.systemPathToFileUrl({str(pdf)!r})
        doc.storeToURL(url, (prop("FilterName", "writer_pdf_Export"),))
        doc.close(True)
        desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        before = sum(1 for _ in _components(desktop))
        out["doc"] = read_document(ctx, url)
        out["open_after"] = sum(1 for _ in _components(desktop)) - before

    def _components(desktop):
        e = desktop.getComponents().createEnumeration()
        while e.hasMoreElements():
            yield e.nextElement()
    ''')
    d = out["doc"]
    assert d["name"] == "diffida.pdf" and d["kind"] == "pdf" and d["chars"] == len(d["text"])
    lines = d["text"].split("\n")
    assert "Il ricorrente espone quanto segue in questa riga giustificata." in lines, lines
    assert "Seconda riga." in lines and "--- pagina 2 ---" in lines and "Pagina due." in lines
    assert lines.index("--- pagina 2 ---") < lines.index("Pagina due.")
    assert out["open_after"] == 0


def test_read_document_refuses_a_pdf_without_text(soffice, tmp_path):
    pdf = tmp_path / "scansione.pdf"
    out = run_probe(soffice, "document_pdf_empty", f'''
    from librelex_ext.document import DocumentActionError, read_document

    def probe(ctx, out):
        doc = new_doc(ctx)          # empty body: the export carries no text frame at all
        url = uno.systemPathToFileUrl({str(pdf)!r})
        doc.storeToURL(url, (prop("FilterName", "writer_pdf_Export"),))
        doc.close(True)
        try:
            read_document(ctx, url)
        except DocumentActionError as e:
            out["error"] = str(e)
    ''')
    assert out["error"] == "PDF senza testo (scansione): non leggibile: scansione.pdf"
```

`extension/tests/headless/test_styles.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""The LibreLex act styles: created once, never overwritten, applied by pattern to a
drafting insertion after the Markdown filter (design §5.1, §5.3)."""
import pytest

from tests.headless.conftest import run_probe

pytestmark = pytest.mark.headless

ACT = """# TRIBUNALE DI MILANO

## ATTO DI CITAZIONE

**Alfa S.r.l.**, in persona del legale rappresentante

- attrice -

contro

**Beta S.p.A.**

- convenuta -

### PREMESSO CHE

- il credito è certo, liquido ed esigibile;
- la fattura n. 12 è rimasta insoluta.

1. primo motivo;
2. secondo motivo.

> Art. 633 c.p.c.: su domanda di chi è creditore di una somma liquida.

* * * * *

### CONCLUSIONI

Voglia il Tribunale accogliere la domanda.

Milano, 3 marzo 2026

Avv. Mario Rossi
"""


def test_act_styles_are_created_once_and_applied_by_pattern(soffice):
    out = run_probe(soffice, "act_styles", f'''
    def probe(ctx, out):
        doc = new_doc(ctx)
        adapter = DocumentAdapter(ctx, doc)
        family = doc.StyleFamilies.getByName("ParagraphStyles")
        custom = doc.createInstance("com.sun.star.style.ParagraphStyle")
        family.insertByName("LibreLex Corpo", custom)
        custom.CharHeight = 13.0                     # the lawyer's own adjustment
        out["created"] = adapter.ensure_act_styles()
        out["created_again"] = adapter.ensure_act_styles()
        out["corpo_height"] = family.getByName("LibreLex Corpo").CharHeight
        sezione = family.getByName("LibreLex Sezione")
        out["sezione"] = [sezione.CharFontName, sezione.CharHeight, sezione.CharWeight,
                          sezione.ParaAdjust.value, sezione.ParaTopMargin,
                          sezione.ParaLineSpacing.Height]
        punto = family.getByName("LibreLex Punto")
        out["punto"] = [punto.ParaLeftMargin, punto.ParaFirstLineIndent]
        res = adapter.insert_markdown("end", {ACT!r}, "LibreLex: atto", "LibreLex.atto.test",
                                      "LibreLex", act_styles=True)
        out["range"] = [res["from_id"], res["to_id"]]
        paras = []
        for style, text in paragraph_texts(doc.Text):
            paras.append([style, text])
        out["paras"] = paras
        out["numbered"] = []
        enum = doc.Text.createEnumeration()
        while enum.hasMoreElements():
            el = enum.nextElement()
            if el.supportsService("com.sun.star.text.Paragraph") and el.ListLabelString:
                out["numbered"].append(el.getString())
        out["redlines"] = redlines(doc)
    ''')
    assert len(out["created"]) == 9 and "LibreLex Corpo" not in out["created"]
    assert out["created_again"] == [] and out["corpo_height"] == 13.0
    assert out["sezione"] == ["Times New Roman", 12.0, 150.0, 3, 300, 150]   # 3 = CENTER
    assert out["punto"] == [500, -500]
    by_text = {t: s for s, t in out["paras"] if t}
    expect = {
        "TRIBUNALE DI MILANO": "LibreLex Intestazione",
        "ATTO DI CITAZIONE": "LibreLex Titolo atto",
        "Alfa S.r.l., in persona del legale rappresentante": "LibreLex Corpo",
        "- attrice -": "LibreLex Ruolo parte",
        "contro": "LibreLex Contro",
        "- convenuta -": "LibreLex Ruolo parte",
        "PREMESSO CHE": "LibreLex Sezione",
        "- il credito è certo, liquido ed esigibile;": "LibreLex Punto",
        "- la fattura n. 12 è rimasta insoluta.": "LibreLex Punto",
        "1. primo motivo;": "LibreLex Punto",
        "2. secondo motivo.": "LibreLex Punto",
        "Art. 633 c.p.c.: su domanda di chi è creditore di una somma liquida.": "LibreLex Citazione",
        "* * * * *": "LibreLex Separatore",
        "CONCLUSIONI": "LibreLex Sezione",
        "Voglia il Tribunale accogliere la domanda.": "LibreLex Corpo",
        "Milano, 3 marzo 2026": "LibreLex Firma",
        "Avv. Mario Rossi": "LibreLex Firma",
    }
    for text, style in expect.items():
        assert by_text.get(text) == style, (text, by_text.get(text), out["paras"])
    assert out["numbered"] == []                      # the list numbering became literal text
    assert out["redlines"] == [["Insert", "LibreLex"]]  # one tracked insertion, no Format redline
```

(If on 26.8 the Markdown filter renders the bullet label differently, the literal prefixes are still `- ` and `N. ` by `list_prefix`; the assertion is on the resulting text. If two adjacent Insert redlines by the same author do not merge, the assertion becomes "every redline is Insert by LibreLex": adjust with a comment, but no Format redline is allowed.)

`extension/tests/headless/test_letterhead.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""apply_letterhead and make_letterhead (design §5.2, §5.3): the template's page style with
its header image and footer text lands in the document; the act styles are created; the
lawyer's own LibreLex style is kept."""
import pytest

from tests.headless.conftest import run_probe
from tests.headless.test_document import PNG_1PX

pytestmark = pytest.mark.headless

BUILD_SOURCE = '''
    def build_source(ctx, path, png):
        """A letterhead document: header with a logo, footer with the addresses, empty body."""
        import base64
        with open(png, "wb") as f:
            f.write(base64.b64decode({png_b64!r}))
        doc = new_doc(ctx)
        page = doc.StyleFamilies.getByName("PageStyles").getByName("Standard")
        page.HeaderIsOn = True
        page.FooterIsOn = True
        gp = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.graphic.GraphicProvider", ctx)
        img = doc.createInstance("com.sun.star.text.TextGraphicObject")
        img.Graphic = gp.queryGraphic((prop("URL", uno.systemPathToFileUrl(png)),))
        page.HeaderText.insertTextContent(page.HeaderText.createTextCursor(), img, False)
        page.FooterText.insertString(page.FooterText.createTextCursor(), "Via Roma 1, Milano", False)
        family = doc.StyleFamilies.getByName("ParagraphStyles")
        corpo = doc.createInstance("com.sun.star.style.ParagraphStyle")
        family.insertByName("LibreLex Corpo", corpo)
        corpo.CharHeight = 13.0
        url = uno.systemPathToFileUrl(path)
        doc.storeToURL(url, (prop("FilterName", "MS Word 2007 XML"),))
        doc.close(True)
        return url

    def page_facts(doc):
        page = doc.StyleFamilies.getByName("PageStyles").getByName("Standard")
        family = doc.StyleFamilies.getByName("ParagraphStyles")
        return {{"header": page.HeaderIsOn, "footer": page.FooterIsOn,
                 "footer_text": page.FooterText.getString() if page.FooterIsOn else "",
                 "graphics": doc.GraphicObjects.getCount(),
                 "styles": [n for n in family.getElementNames() if n.startswith("LibreLex ")],
                 "corpo_height": family.getByName("LibreLex Corpo").CharHeight
                 if family.hasByName("LibreLex Corpo") else None}}
'''


def test_apply_letterhead_brings_the_page_style_and_keeps_the_templates_own_style(soffice, tmp_path):
    src, png = tmp_path / "carta.docx", tmp_path / "logo.png"
    out = run_probe(soffice, "apply_letterhead", BUILD_SOURCE.format(png_b64=PNG_1PX) + f'''
    def probe(ctx, out):
        url = build_source(ctx, {str(src)!r}, {str(png)!r})
        doc = new_doc(ctx)
        doc.Text.insertString(doc.Text.createTextCursor(), "Testo del cliente.", False)
        out["before"] = page_facts(doc)
        out["result"] = DocumentAdapter(ctx, doc).apply_letterhead(url)
        out["after"] = page_facts(doc)
        out["body"] = doc.Text.getString()
        try:
            DocumentAdapter(ctx, doc).apply_letterhead(uno.systemPathToFileUrl({str(tmp_path / "manca.docx")!r}))
        except DocumentActionError as e:
            out["error"] = str(e)
        out["none"] = DocumentAdapter(ctx, new_doc(ctx)).apply_letterhead(None)
    ''')
    assert out["before"]["graphics"] == 0 and out["before"]["styles"] == []
    assert out["result"]["letterhead"] is True
    assert "LibreLex Corpo" not in out["result"]["created"] and len(out["result"]["created"]) == 9
    after = out["after"]
    assert after["header"] and after["footer"] and after["footer_text"] == "Via Roma 1, Milano"
    assert after["graphics"] == 1 and len(after["styles"]) == 10
    assert after["corpo_height"] == 13.0                # the template's own style, kept
    assert out["body"] == "Testo del cliente."           # the body is untouched
    assert out["error"] == "carta intestata non applicabile: manca.docx"
    assert out["none"]["letterhead"] is False and len(out["none"]["created"]) == 10


def test_make_letterhead_writes_a_template_with_the_letterhead_and_an_empty_body(soffice, tmp_path):
    src, png = tmp_path / "carta.docx", tmp_path / "logo.png"
    target = tmp_path / "modelli" / "SAPG Legal.ott"
    target.parent.mkdir()
    out = run_probe(soffice, "make_letterhead", BUILD_SOURCE.format(png_b64=PNG_1PX) + f'''
    from librelex_ext.document import make_letterhead

    def probe(ctx, out):
        url = build_source(ctx, {str(src)!r}, {str(png)!r})
        out["path"] = make_letterhead(ctx, url, {str(target)!r})
        desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        tpl = desktop.loadComponentFromURL(uno.systemPathToFileUrl({str(target)!r}), "_blank", 0,
                                           (prop("Hidden", True), prop("AsTemplate", True)))
        out["facts"] = page_facts(tpl)
        out["body"] = tpl.Text.getString()
        tpl.close(True)
        try:
            make_letterhead(ctx, url, {str(target)!r})
        except DocumentActionError as e:
            out["error"] = str(e)
    ''')
    assert out["path"] == str(target) and target.exists()
    facts = out["facts"]
    assert facts["header"] and facts["footer_text"] == "Via Roma 1, Milano" and facts["graphics"] == 1
    assert len(facts["styles"]) == 10 and out["body"] == ""
    assert out["error"] == "modello già presente: SAPG Legal.ott"
```

`extension/tests/test_session.py`: in `test_dispatch_maps_actions_and_wraps_results`, add that `dispatch_doc_call(a, "insert_markdown", {...}, act_styles=True)` records `act_styles=True` in `FakeAdapter.insert_markdown` (extend the fake's signature with `act_styles=False` and append it to the recorded tuple).

Run: `cd extension && uv run pytest tests/headless/test_document.py tests/headless/test_styles.py tests/headless/test_letterhead.py -q -m headless` → failures (import errors); `uv run pytest tests/test_session.py -q` → the dispatch test fails.

- [ ] **Step 2: Implement** as in Interfaces. Notes for the implementer: `paragraph_texts` in the probe preamble returns `[ParaStyleName, text]`; `ListLabelString` is a read-only paragraph property on Writer; `setPropertyToDefault` comes from `XPropertyState` on the paragraph; the second `loadStylesFromURL` call is what keeps the template's own `LibreLex Corpo` at 13 pt (the first call must not load text styles, or the document's paragraph styles would be overwritten); `read_document` decides the path by the lower-cased extension before loading.

- [ ] **Step 3: Run and commit**

`cd extension && uv run ruff check . && uv run pytest -q -m "not headless" && uv run pytest -q -m headless tests/headless/test_document.py tests/headless/test_styles.py tests/headless/test_letterhead.py tests/headless/test_e2e_draft.py` → green (the e2e still passes: nothing sends `act_styles` yet).

```bash
git add extension
git commit -m "feat(ext): adapter for the workbench: LibreLex act styles applied by pattern, letterhead from a template, template building, documents read incl. PDF through Draw" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Layout, views and the deck: one Redazione panel with four steps

**Files:**
- Modify: `extension/librelex_ext/layout.py`, `extension/librelex_ext/views.py`, `extension/Sidebar.xcu`
- Test: `extension/tests/test_layout.py`, `extension/tests/test_views.py`

**Interfaces (produced):**
- `layout.KINDS = ("Actions", "Drafting", "Citations", "Answers")`; new constants `DRAFT_AREA_H = 404`, `LOG_H = 200`, `EXPECTED_H = 80`, `ATTACHMENTS_H = 36`, `SUMMARY_H = 140`, `STEP_PARTITIONS_H = 60`, `NOTES_H = 30`, `DRAFT_CONSENT_TEXT_H = 30`, `DRAFT_CONSENT_H = DRAFT_CONSENT_TEXT_H + GAP + BUTTON_H + GAP + BUTTON_H` (70), `LETTERHEAD_LABEL_W = 60`, `REFERENCE_ROW_H = 16`.
- `layout.DRAFT_CONSENT = ("DraftConsentText", "DraftConsentDocument", "DraftConsentOnce", "DraftConsentDeny")` (same labels as `CONSENT_LABELS`, same commands, hidden by default, positioned once at `y = MARGIN + DRAFT_AREA_H - DRAFT_CONSENT_H` and shared by steps 2 and 3); `layout.DRAFT_STEPS: dict[int, tuple[str, ...]]`:
  - 1: `TemplateSearch, TemplateRefresh, Template, TemplateNotes, FieldsLabel, FieldLabel1..8, Field1..8, NotesLabel, Notes, AttachmentsLabel, Attachments, AttachmentAdd, AttachmentRemove, ReferenceInfo, ReferenceBrowse, ReferenceClear, LetterheadLabel, Letterhead, LetterheadAdd, Start`
  - 2: `QuestionsHint, QuestionLabel1..8, Answer1..8, Continue, *DRAFT_CONSENT`
  - 3: `Log, ExpectedLabel, Expected, DraftCancel, *DRAFT_CONSENT`
  - 4: `PartitionsLabel, Partitions, Summary, VerifyAct, ResumeInput, Resume, NewDraft`
  - `layout.DRAFT_SHARED = ("DraftStatus",)` at `y = MARGIN + DRAFT_AREA_H + GAP`, height `STATUS_H`.
- Geometry of each step, all laid out from `y = MARGIN` (heights in dialog units, `GAP` between rows unless said otherwise): step 1: search row (`INPUT_H`), `Template` dropdown (`INPUT_H`), `TemplateNotes` (20), `FieldsLabel` (`SECTION_H`), eight packed field rows (`INPUT_H` each, no gap), `NotesLabel` (`SECTION_H`), `Notes` (`NOTES_H` 30), `AttachmentsLabel` (`SECTION_H`, copy `"Allegati del fascicolo (Doc. 1, 2, …)"`), `Attachments` list box (`ATTACHMENTS_H`, `Dropdown` False), `AttachmentAdd` "Aggiungi…" and `AttachmentRemove` "Togli" (two-column row, `BUTTON_H`, Togli `Enabled` False), the reference row (`ReferenceInfo` `FixedText` MultiLine at `MARGIN`, width `inner - 2 * (SMALL_BUTTON_W + GAP)`, height `REFERENCE_ROW_H`; `ReferenceBrowse` "Sfoglia…" at `width - MARGIN - 2 * SMALL_BUTTON_W - GAP` and `ReferenceClear` "Rimuovi" at `width - MARGIN - SMALL_BUTTON_W`, both `SMALL_BUTTON_W` × `INPUT_H`, Rimuovi `Enabled` False), the letterhead row (`LetterheadLabel` `FixedText` "Carta intestata" width `LETTERHEAD_LABEL_W`; `Letterhead` `ListBox` `Dropdown` True `LineCount` 8 from `MARGIN + LETTERHEAD_LABEL_W + GAP` to `width - MARGIN - SMALL_BUTTON_W - GAP`; `LetterheadAdd` "Aggiungi…" `SMALL_BUTTON_W` × `INPUT_H` at the right), `Start` "Avvia redazione" full width (`Enabled` False). Step 2: `QuestionsHint` (20, GRAY, the `render_questions_hint`-style default copy "Il modello ha bisogno di questi dati: rispondi e premi Continua; una casella vuota vale come risposta non disponibile."), eight rows of `QuestionLabel{n}` (`QUESTION_LABEL_H`, MultiLine) directly followed by `Answer{n}` (`INPUT_H`) with no gap inside the row and no gap between rows, `Continue` "Continua" full width (`Visible` False). Step 3: `Log` (`Edit`, MultiLine, ReadOnly, VScroll, AutoVScroll, `LOG_H`), `ExpectedLabel` (`SECTION_H`, copy "Partizioni attese"), `Expected` list box (`EXPECTED_H`, `Dropdown` False), `DraftCancel` "Annulla" full width (`Enabled` False). Step 4: `PartitionsLabel` (`SECTION_H`, copy "Partizioni inserite"), `Partitions` list (`STEP_PARTITIONS_H`), `Summary` (`Edit`, MultiLine, ReadOnly, VScroll, `SUMMARY_H`), `VerifyAct` "Verifica citazioni" full width, `ResumeInput` (`INPUT_H`), `Resume` "Riprendi" full width, `NewDraft` "Nuova redazione" full width. Every control of steps 2, 3 and 4 gets `"Visible": False` in its props (step 1 is the initial step); the field, question and answer rows keep `Visible` False as today.
- `layout.ACTIONS` gains `"AttachmentAdd": "attachment_add"`, `"AttachmentRemove": "attachment_remove"`, `"LetterheadAdd": "letterhead_add"`, `"DraftCancel": "cancel"`, `"VerifyAct": "verify_document"`, `"NewDraft": "draft_new"`, `"DraftConsentDocument": "consent_document"`, `"DraftConsentOnce": "consent_once"`, `"DraftConsentDeny": "consent_deny"`; `BUSY_DISABLED` gains `AttachmentAdd, AttachmentRemove, LetterheadAdd, Letterhead, VerifyAct, NewDraft` (the consent buttons stay out; `DraftCancel` is enabled only while busy, like `Cancel`); `TOOLTIPS` for every new button (Italian, one line each: e.g. `AttachmentAdd`: "Aggiunge un documento del caso (pdf, odt, docx, doc, rtf, txt): il modello lo legge per i fatti dopo il tuo consenso", `AttachmentRemove`: "Toglie l'allegato selezionato", `LetterheadAdd`: "Crea un modello di carta intestata da un file odt, docx o doc dello studio", `Letterhead`: "Carta intestata su cui impaginare l'atto", `DraftCancel`: "Interrompe la redazione in corso", `VerifyAct`: "Controlla le citazioni dell'atto sulle fonti ufficiali", `NewDraft`: "Torna al primo passo per un altro atto; allegati e carta intestata restano", `Resume`: "Riprende la redazione, con l'istruzione scritta qui sopra se ne dai una", `Log`: "Attività del modello durante la redazione", `Expected`: "Partizioni dell'atto: ✓ quelle già inserite", `Attachments`: "I documenti del caso, numerati come nell'atto"); `SECTIONS` gains `AttachmentsLabel`, `ExpectedLabel`, `LetterheadLabel` ("Carta intestata") and `PartitionsLabel` keeps its copy.
- `views.py`: `ROUTES` loses the `Questions` entries and routes `set_questions`, `set_answer_values`, `set_step`, `set_log`, `append_log`, `set_expected_partitions`, `set_attachments`, `set_letterheads`, `set_summary` to `"Drafting"`; `BROADCAST = ("set_busy", "set_consent")` and `_call` broadcasts those (every attached panel gets them); `CompositeView` gains the seven new methods.
- `Sidebar.xcu`: the `LibreLexQuestionsPanel` node removed; four panels remain (order 100, 150, 200, 300).

- [ ] **Step 1: Failing tests**

`extension/tests/test_layout.py`: `EXPECTED` becomes four kinds; `"Drafting"` = the union of `DRAFT_STEPS` values and `DRAFT_SHARED`; `_no_overlap` for Drafting is checked per step (the controls of that step plus `DRAFT_SHARED`), since the steps share the area:

```python
def _drafting_groups(controls):
    by = {c.name: c for c in controls}
    for step, names in DRAFT_STEPS.items():
        yield step, [by[n] for n in (*names, *DRAFT_SHARED)]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("width", [MIN_WIDTH, WIDTH, 260])
def test_each_kind_fits_its_width_without_overlaps(kind, width):
    controls = build(kind, width)
    if kind == "Drafting":
        for _step, group in _drafting_groups(controls):
            _no_overlap(group, width)
        assert len({c.name for c in controls}) == len(controls)
    else:
        _no_overlap(controls, width)
    assert {c.name for c in controls} == EXPECTED[kind]
    assert total_height(controls) == total_height(build(kind, WIDTH))


def test_drafting_steps_share_one_area_and_the_status_sits_under_it():
    controls = build("Drafting", WIDTH)
    by = {c.name: c for c in controls}
    names = {c.name for c in controls}
    assert set().union(*DRAFT_STEPS.values()) | set(DRAFT_SHARED) == names
    for step, group in _drafting_groups(controls):
        for c in group:
            if c.name not in DRAFT_SHARED:
                assert c.y >= MARGIN and c.y + c.h <= MARGIN + DRAFT_AREA_H, (step, c.name)
    assert by["DraftStatus"].y == MARGIN + DRAFT_AREA_H + GAP
    assert total_height(controls) <= 440
    for name in (*DRAFT_STEPS[2], *DRAFT_STEPS[3], *DRAFT_STEPS[4]):
        assert by[name].props.get("Visible") is False, name        # only step 1 shows at first
    for name in ("TemplateSearch", "Template", "Notes", "Attachments", "Start", "Letterhead"):
        assert by[name].props.get("Visible", True) is True, name
    # the consent block is one block, shared by steps 2 and 3, right above the status
    assert set(DRAFT_CONSENT) <= set(DRAFT_STEPS[2]) and set(DRAFT_CONSENT) <= set(DRAFT_STEPS[3])
    text, document, once, deny = (by[n] for n in DRAFT_CONSENT)
    assert text.y == MARGIN + DRAFT_AREA_H - DRAFT_CONSENT_H and text.h == DRAFT_CONSENT_TEXT_H
    assert document.y == text.y + text.h + GAP and once.y == deny.y == document.y + BUTTON_H + GAP
    assert deny.y + deny.h <= MARGIN + DRAFT_AREA_H
    assert by["Continue"].y + by["Continue"].h <= text.y                # step 2 fits above it
    assert by["DraftCancel"].y + by["DraftCancel"].h <= text.y           # step 3 too
    assert [by[n].props["Label"] for n in DRAFT_CONSENT[1:]] == list(CONSENT_LABELS)


def test_step_one_rows():
    by = {c.name: c for c in build("Drafting", WIDTH)}
    assert by["Attachments"].props["Dropdown"] is False and by["Attachments"].h == ATTACHMENTS_H
    assert by["AttachmentAdd"].y == by["AttachmentRemove"].y
    assert by["AttachmentRemove"].props["Enabled"] is False
    assert by["ReferenceInfo"].y == by["ReferenceBrowse"].y == by["ReferenceClear"].y
    assert by["ReferenceClear"].x + by["ReferenceClear"].w == WIDTH - MARGIN
    assert by["ReferenceBrowse"].x + by["ReferenceBrowse"].w + GAP == by["ReferenceClear"].x
    assert by["ReferenceInfo"].x + by["ReferenceInfo"].w <= by["ReferenceBrowse"].x
    assert by["LetterheadLabel"].y == by["Letterhead"].y == by["LetterheadAdd"].y
    assert by["Letterhead"].props["Dropdown"] is True
    assert by["LetterheadAdd"].x + by["LetterheadAdd"].w == WIDTH - MARGIN
    assert by["Start"].props["Enabled"] is False and by["Start"].y > by["Letterhead"].y
    order = [c.name for c in build("Drafting", WIDTH) if c.name in DRAFT_STEPS[1]]
    assert order.index("Notes") < order.index("Attachments") < order.index("ReferenceInfo") \
        < order.index("Letterhead") < order.index("Start")


def test_steps_two_three_four_rows():
    by = {c.name: c for c in build("Drafting", WIDTH)}
    for n in range(1, FIELD_ROWS + 1):
        label, edit = by[f"QuestionLabel{n}"], by[f"Answer{n}"]
        assert edit.y == label.y + label.h and label.props["MultiLine"] is True
    assert by["Log"].props["ReadOnly"] is True and by["Log"].h == LOG_H
    assert by["Expected"].props["Dropdown"] is False and by["DraftCancel"].props["Enabled"] is False
    assert by["Summary"].props["ReadOnly"] is True
    assert by["VerifyAct"].props["Label"] == "Verifica citazioni"
    assert by["NewDraft"].props["Label"] == "Nuova redazione" and by["Resume"].props["Label"] == "Riprendi"
    assert by["ResumeInput"].y < by["Resume"].y < by["NewDraft"].y


def test_workbench_buttons_are_wired():
    for name, command in (("AttachmentAdd", "attachment_add"),
                          ("AttachmentRemove", "attachment_remove"),
                          ("LetterheadAdd", "letterhead_add"), ("DraftCancel", "cancel"),
                          ("VerifyAct", "verify_document"), ("NewDraft", "draft_new"),
                          ("DraftConsentDocument", "consent_document"),
                          ("DraftConsentOnce", "consent_once"), ("DraftConsentDeny", "consent_deny")):
        assert ACTIONS[name] == command and name in TOOLTIPS
    for name in ("AttachmentAdd", "AttachmentRemove", "LetterheadAdd", "Letterhead", "VerifyAct",
                 "NewDraft", "Start", "Resume", "Continue"):
        assert name in BUSY_DISABLED
    assert not (set(DRAFT_CONSENT) | {"DraftCancel"}) & set(BUSY_DISABLED)
    assert KINDS == ("Actions", "Drafting", "Citations", "Answers")
    with pytest.raises(ValueError):
        build("Questions", WIDTH)
```

Delete `test_questions_panel_rows_hidden_until_needed` and update `test_drafting_panel_rows_and_hidden_blocks` (drop the Partitions/Resume ordering assertions that assumed one column; keep the field-row and Template assertions; the height bound moves to the new test) and `test_actions_lost_the_draft_button_and_the_new_actions_are_wired` (the `KINDS` line). `test_views.py`: `panel_kind("…/Questions")` now raises; the two drafting tests route everything to `Drafting`; a new test:

```python
def test_consent_and_busy_are_broadcast_and_the_workbench_methods_reach_drafting():
    v = CompositeView()
    actions, drafting = Rec(), Rec()
    v.attach("Actions", actions)
    v.attach("Drafting", drafting)
    v.set_consent({"scope": "attachments"})
    v.set_step(3)
    v.append_log("Inserito: Premesse")
    v.set_log(["a"])
    v.set_expected_partitions(["· Premesse"])
    v.set_attachments(["Doc. 1 · a.pdf (10 caratteri)"])
    v.set_letterheads(["Nessuna (impaginazione del documento)", "SAPG Legal"], 1)
    v.set_summary("Riepilogo:\nok")
    v.set_questions([]); v.set_answer_values({})
    assert actions.calls == [("set_consent", ({"scope": "attachments"},))]
    assert [c[0] for c in drafting.calls] == [
        "set_consent", "set_step", "append_log", "set_log", "set_expected_partitions",
        "set_attachments", "set_letterheads", "set_summary", "set_questions", "set_answer_values"]
    assert BROADCAST == ("set_busy", "set_consent") and "set_consent" not in ROUTES
```

Run: `cd extension && uv run pytest tests/test_layout.py tests/test_views.py -q` → failures.

- [ ] **Step 2: Implement** the Drafting table as four inner helper blocks (`step1()`, `step2()`, `step3()`, `step4()`, each resetting `y = MARGIN`, plus `consent_block()` at its fixed `y`), the hidden props, `DRAFT_STEPS`/`DRAFT_SHARED`/`DRAFT_CONSENT`, the views change, `Sidebar.xcu`. The `Questions` branch is deleted.

- [ ] **Step 3: Run and commit**

`cd extension && uv run ruff check . && uv run pytest -q -m "not headless"` → green except the session tests that still name `Questions` routes (there are none: the session routes through the composite by method name) and `panel.py` is not imported by the pure suite; `views.panel_kind` of a `Questions` URL raising is fine because the deck no longer asks for it.

```bash
git add extension
git commit -m "feat(ext): one Redazione panel in four steps: layout tables, broadcast consent, deck of four panels" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: The Session: steps, log, attachments, letterhead, transitions

**Files:**
- Modify: `extension/librelex_ext/session.py`
- Test: `extension/tests/test_session.py`

**Interfaces (produced, consumed by Task 5):**
- Constants: `MAX_ATTACHMENT_CHARS = 60_000`, `MAX_ATTACHMENTS = 12`, `MAX_ATTACHMENTS_CHARS = 300_000`, `MAX_LOG_LINES = 200`, `ACT_EXTENSIONS = (".odt", ".docx", ".doc", ".rtf", ".txt")`; module function `drop_role(name: str, reference_present: bool) -> str` = `"reference"` when the lower-cased name ends with one of `ACT_EXTENSIONS` and no reference is present, else `"attachment"`.
- `View`/`NullView` gain `set_step(step: int)`, `set_log(lines: list[str])`, `append_log(line: str)`, `set_expected_partitions(labels: list[str])`, `set_attachments(labels: list[str])`, `set_letterheads(labels: list[str], selected: int)`, `set_summary(text: str)`.
- `draft_view` gains `"step": 1`, `"log": []`, `"expected_partitions": []`, `"attachments": []` (each `{n, name, chars, kind, troncato}`), `"letterheads": []` (each `{name, path, default}`), `"letterhead": None`; private `_attachment_texts: list[dict]` (`{name, text, kind, troncato}`, the committed set), `_attachments_pending: list[dict] | None` (the set sent and not yet confirmed), `_attachments_request_id: str | None`.
- `add_attachment(name, text, kind) -> bool`: `text = text[:MAX_ATTACHMENT_CHARS]`, `troncato = len(original) > MAX_ATTACHMENT_CHARS`; refuses (`_refuse_draft`, returns False) `"Allegati: al massimo 12 documenti"` when the set is full and `"Allegati: al massimo 300.000 caratteri in totale"` when the total would exceed; builds `pending = [*self._attachment_texts, new]` and `_send_attachments(pending, label=f"Tu: allegato {name}")`. `remove_attachment(index) -> bool`: out of range → False; `pending` without that entry, label `f"Tu: tolgo l'allegato {name}"`. `_send_attachments(pending, label) -> bool`: `run_command("set_attachments", {"documenti": [{"name", "text", "kind"} …]}, label)`; when taken, `_attachments_pending = pending`, `_attachments_request_id = self.request_id` (None while queued behind the hello, filled by `_send_payload` the way `_draft_start_request_id` is: generalise that hook to a list of "pending id" attributes, or add a second flag `_attachments_id_pending`). `_on_final` with `"allegati" in summary`: `_attachment_texts = _attachments_pending or []` (an empty `allegati` clears both), `draft_view["attachments"] = [{**a, "troncato": a.get("troncato") or local.troncato}]` (local matched by position), `view.set_attachments(render_attachments(...))`, `_append(msg["text"])`, `_attachments_pending = None`. `_on_error` for that request id, and `exit`: `_attachments_pending = None` (the committed set stands; the panel still shows the committed list).
- `set_letterheads(entries: list[dict]) -> None` (the panel passes `letterheads.list_letterheads()`): stores them, `draft_view["letterhead"] = letterheads.initial_choice(entries, letterheads.load_index())` unless a choice is already stored and still listed; `view.set_letterheads(render_letterhead_labels(entries), selected)` with `selected` = 0 for None else `1 + index of the chosen name`. `choose_letterhead(index: int) -> None`: 0 → None, else `entries[index - 1]["name"]`; stores it and calls `letterheads.remember_choice(name)` inside `suppress(OSError)`. `letterhead_path() -> str | None`: the chosen entry's `path`.
- `draft_start(tipo_atto, fields, notes)`: validation as today; once the request is taken: `self._apply_letterhead()` (calls `adapter.apply_letterhead(file url of letterhead_path() or None)`, any exception → `_log(f"Carta intestata non applicata: {e}")` and `_append` of the same line; note the URL conversion: the session has no UNO, so it passes the path through `"file://" + urllib.parse.quote(path)`; the adapter accepts a file URL), then `draft_view["log"] = []`, `_log(f"Avvio della redazione: {tipo_atto}")`, `draft_view["expected_partitions"]` = `["Base"]` when the template's routing `tipo` is `tool_diretto` (prepended) plus `render.EXPECTED_PARTITIONS`, `view.set_expected_partitions(render_expected_partitions(...))`, `_set_step(3)`.
- `_set_step(step)`: stores and `view.set_step(step)` then `_refresh_draft_status()`. `_log(line)`: appends to `draft_view["log"]` (dropping the oldest beyond `MAX_LOG_LINES`) and `view.append_log(line)`.
- `_on_status`: as today, plus `_log(text)` while `_draft_request`. `_on_doc_call`: passes `act_styles=self._draft_request` to `dispatch_doc_call`; after a successful `insert_markdown` during a draft request `_log(render_log_insert(args["markdown"]))`, after a successful `replace_text` `_log(f"Sostituito: «{args['query']}»")`.
- `_merge_draft_turn(summary)`: as today, then `_set_step(2 if questions else 4)`; on step 4 `view.set_summary(render_summary(summary))` (with `"allegati": draft_view["attachments"]` merged in when the summary lacks it); `draft_view["expected_partitions"]` re-rendered with the new partitions (`view.set_expected_partitions`). `draft_answer` and `draft_continue`, once taken: `_set_step(3)` and `_log("Risposte inviate")` / `_log(f"Riprendo: {message or 'continua'}")`. `_on_error` during a draft: `_log(f"Errore: {message}")`, step unchanged (a failed start goes back to step 1 through `_abandon_draft_request`, which now also calls `_set_step(1)` when it drops `started`). `exit` mid-draft: `_log("Il core si è chiuso")`, step unchanged.
- `new_drafting()`: keeps `templates, query, template, fields, notes, reference, attachments, letterheads, letterhead`; resets `answers_draft, questions, partitions, open_placeholders, started, done, stopped, base_errore, log, expected_partitions`; `view.set_questions([])`, `set_answer_values({})`, `set_partitions([])`, `set_log([])`, `set_expected_partitions([])`, `set_summary("")`, `_set_step(1)`. Refused while `_draft_request` (`_refuse_draft("Attendi la fine del turno o premi Annulla")`).
- `verify_act()`: `run_command("verify_citations", {"scope": "document"}, label="Tu: verifica citazioni dell'atto")`.
- `replay_drafting(view)`: the eight calls of today (with `set_questions`/`set_answer_values` now landing on Drafting) plus `set_attachments`, `set_letterheads`, `set_log(draft_view["log"])`, `set_expected_partitions`, `set_summary(self._summary_text)` (the last rendered summary, kept as `_summary_text`), and `set_step(draft_view["step"])` last.
- `_status_view()` includes `step` (it already spreads `draft_view`).

- [ ] **Step 1: Failing tests** (`extension/tests/test_session.py`; `FakeView` gains the seven methods recording their last argument, e.g. `self.step`, `self.log: list[str]` appended by `append_log` and replaced by `set_log`, `self.expected`, `self.attachments`, `self.letterheads = (labels, selected)`, `self.summary`; `FakeAdapter` gains `apply_letterhead(url)` recording `("apply_letterhead", url)` and returning `{"letterhead": url is not None, "created": []}`):

```python
def test_drop_role_sends_acts_to_the_reference_slot_once():
    assert drop_role("ricorso.docx", False) == "reference"
    assert drop_role("RICORSO.ODT", False) == "reference"
    assert drop_role("ricorso.docx", True) == "attachment"
    assert drop_role("fattura.pdf", False) == "attachment"


def test_attachments_are_sent_as_a_whole_set_and_committed_on_the_final(monkeypatch):
    s, view, bridge = _ready_session()          # the helper the drafting tests already use
    assert s.add_attachment("fattura_12.pdf", "F" * 70_000, "pdf") is True
    sent = bridge.sent[-1]
    assert sent["name"] == "set_attachments"
    assert [d["name"] for d in sent["args"]["documenti"]] == ["fattura_12.pdf"]
    assert len(sent["args"]["documenti"][0]["text"]) == MAX_ATTACHMENT_CHARS
    assert s.draft_view["attachments"] == []            # nothing committed before the final
    _final(s, sent["id"], "Allegati: 1 documenti (60000 caratteri).",
           {"allegati": [{"n": 1, "name": "fattura_12.pdf", "chars": 60_000, "kind": "pdf",
                          "troncato": False}]})
    assert s.draft_view["attachments"][0]["troncato"] is True      # the extension's own cut
    assert view.attachments == ["Doc. 1 · fattura_12.pdf (60.000 caratteri, troncato)"]
    assert s.transcript[-1] == "Allegati: 1 documenti (60000 caratteri)."
    assert s.add_attachment("delibera.docx", "D" * 10, "writer") is True
    docs = bridge.sent[-1]["args"]["documenti"]
    assert [d["name"] for d in docs] == ["fattura_12.pdf", "delibera.docx"]   # the whole set
    _final(s, bridge.sent[-1]["id"], "Allegati: 2 documenti (60010 caratteri).",
           {"allegati": [{"n": 1, "name": "fattura_12.pdf", "chars": 60_000, "kind": "pdf",
                          "troncato": False},
                         {"n": 2, "name": "delibera.docx", "chars": 10, "kind": "writer",
                          "troncato": False}]})
    assert s.remove_attachment(0) is True
    assert [d["name"] for d in bridge.sent[-1]["args"]["documenti"]] == ["delibera.docx"]
    _error(s, bridge.sent[-1]["id"], "bad_request", "allegati non validi")
    assert [a["name"] for a in s.draft_view["attachments"]] == ["fattura_12.pdf", "delibera.docx"]
    assert s.remove_attachment(5) is False


def test_attachment_limits_are_refused_before_any_request():
    s, view, bridge = _ready_session()
    s._attachment_texts = [{"name": f"d{i}", "text": "x", "kind": "writer", "troncato": False}
                           for i in range(12)]
    n = len(bridge.sent)
    assert s.add_attachment("tredici.pdf", "x", "pdf") is False
    assert view.draft_status[0] == "Allegati: al massimo 12 documenti" and len(bridge.sent) == n
    s._attachment_texts = [{"name": "big", "text": "x" * 250_000, "kind": "writer",
                            "troncato": False}]
    assert s.add_attachment("altro.pdf", "y" * 60_000, "pdf") is False
    assert view.draft_status[0] == "Allegati: al massimo 300.000 caratteri in totale"


def test_letterheads_choice_is_remembered_and_applied_at_start(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRELEX_CONFIG", str(tmp_path / "config.toml"))
    from librelex_ext import letterheads
    folder = letterheads.templates_dir()
    folder.mkdir(parents=True)
    (folder / "SAPG Legal.ott").write_bytes(b"x")
    (folder / "SAPG Legaltech.ott").write_bytes(b"x")
    letterheads.register_letterhead("SAPG Legal", "SAPG Legal.ott", default=True)
    letterheads.register_letterhead("SAPG Legaltech", "SAPG Legaltech.ott")
    s, view, bridge = _ready_session_with_template()      # template_info answered, fields ok
    s.set_letterheads(letterheads.list_letterheads())
    assert view.letterheads == (["Nessuna (impaginazione del documento)", "SAPG Legal",
                                 "SAPG Legaltech"], 1)
    s.choose_letterhead(2)
    assert s.draft_view["letterhead"] == "SAPG Legaltech"
    assert letterheads.load_index()["last"] == "SAPG Legaltech"
    s.draft_start("decreto_ingiuntivo_ordinario", {"creditore": "A", "debitore": "B",
                                                   "importo": "1"}, "")
    assert s.adapter.calls[-1] == ("apply_letterhead",
                                   "file://" + str(folder / "SAPG Legaltech.ott").replace(" ", "%20"))
    assert s.draft_view["step"] == 3 and view.step == 3
    assert s.draft_view["log"] == ["Avvio della redazione: decreto_ingiuntivo_ordinario"]
    assert view.expected == ["· Base", "· Intestazione", "· Parti", "· Premesse", "· Diritto",
                             "· Conclusioni", "· Allegati"]
    s.choose_letterhead(0)
    assert s.draft_view["letterhead"] is None and letterheads.load_index()["last"] is None


def test_the_steps_follow_the_turns_and_the_log_follows_the_core():
    s, view, bridge = _ready_session_with_template()
    s.draft_start("decreto_ingiuntivo_ordinario", {"creditore": "A", "debitore": "B",
                                                   "importo": "1"}, "")
    assert s.adapter.calls[-1] == ("apply_letterhead", None)      # no letterhead chosen
    rid = bridge.sent[-1]["id"]
    s.handle_event(_msg({"type": "status", "id": rid, "text": "Chiamo decreto_ingiuntivo"}))
    s.handle_event(_msg({"type": "doc_call", "request_id": rid, "call_id": "c1",
                         "action": "insert_markdown",
                         "args": {"where": "end", "markdown": "### PREMESSO CHE\n\nx",
                                  "undo_label": "u"}}))
    s.handle_event(_msg({"type": "doc_call", "request_id": rid, "call_id": "c2",
                         "action": "replace_text",
                         "args": {"query": "[SEDE]", "replacement": "MILANO", "undo_label": "u"}}))
    assert s.adapter.calls[-2][0] == "insert_markdown" and s.adapter.calls[-2][-1] is True
    assert view.log[-3:] == ["Chiamo decreto_ingiuntivo", "Inserito: PREMESSO CHE",
                             "Sostituito: «[SEDE]»"]
    _final(s, rid, "", {"partizioni": [{"titolo": "Premesse in fatto", "from_id": "p:1"}],
                        "domande": [{"campo": "sede", "domanda": "Sede?", "tipo": "testo"}],
                        "segnaposto_aperti": [], "completata": False, "usage_totals": {}})
    assert s.draft_view["step"] == 2 and view.step == 2
    assert view.draft_status[0] == "Rispondi alle 1 domande e premi Continua"
    assert view.expected[3] == "✓ Premesse"
    s.draft_answer({"sede": "Milano"})
    assert view.step == 3 and view.log[-1] == "Risposte inviate"
    rid = bridge.sent[-1]["id"]
    _final(s, rid, "", {"partizioni": [{"titolo": "Premesse in fatto", "from_id": "p:1"}],
                        "domande": [], "segnaposto_aperti": ["[X]"], "completata": True,
                        "riepilogo": "Calcoli: ok", "usage_totals": {}})
    assert view.step == 4
    assert view.draft_status[0] == "Redazione completata: Verifica citazioni, poi Nuova redazione"
    assert view.summary == "Riepilogo:\nCalcoli: ok\nSegnaposto aperti: [X]"
    s.verify_act()
    assert bridge.sent[-1]["name"] == "verify_citations"
    _final(s, bridge.sent[-1]["id"], "ok", {"citazioni_uniche": 0, "citazioni_totali": 0,
                                              "commenti_inseriti": 0, "per_verdetto": {}})
    s.draft_continue("aggiungi le conclusioni")
    assert view.step == 3 and view.log[-1] == "Riprendo: aggiungi le conclusioni"
    _final(s, bridge.sent[-1]["id"], "", {"partizioni": [], "domande": [], "segnaposto_aperti": [],
                                          "completata": False, "stopped": "timeout",
                                          "usage_totals": {}})
    assert view.step == 4 and view.draft_status[0] == "Interrotta: Riprendi per continuare"
    s.new_drafting()
    assert view.step == 1 and s.draft_view["partitions"] == [] and s.draft_view["log"] == []
    assert s.draft_view["template"] is not None and s.draft_view["started"] is False


def test_errors_keep_the_step_and_a_failed_start_goes_back_to_step_one():
    s, view, bridge = _ready_session_with_template()
    s.draft_start("decreto_ingiuntivo_ordinario", {"creditore": "A", "debitore": "B",
                                                   "importo": "1"}, "")
    _error(s, bridge.sent[-1]["id"], "template_not_found", "manca")
    assert view.step == 1 and s.draft_view["started"] is False
    assert view.log[-1] == "Errore: manca"
    s.draft_start("decreto_ingiuntivo_ordinario", {"creditore": "A", "debitore": "B",
                                                   "importo": "1"}, "")
    _final(s, bridge.sent[-1]["id"], "", {"partizioni": [{"titolo": "Base", "from_id": "p:1"}],
                                          "domande": [{"campo": "s", "domanda": "?", "tipo": "testo"}],
                                          "segnaposto_aperti": [], "completata": False,
                                          "usage_totals": {}})
    s.draft_answer({"s": "x"})
    _error(s, bridge.sent[-1]["id"], "llm", "giù")
    assert view.step == 3 and s.draft_view["started"] is True       # the drafting is real
    assert s.new_drafting() is None and view.step == 1


def test_a_rebuilt_panel_gets_the_whole_workbench_state_back():
    s, view, bridge = _ready_session_with_template()
    s.draft_view.update(step=3, log=["a", "b"], attachments=[{"n": 1, "name": "x.pdf", "chars": 5,
                                                              "kind": "pdf", "troncato": False}])
    s._summary_text = "Riepilogo:\nok"
    fresh = FakeView()
    s.replay_drafting(fresh)
    assert fresh.step == 3 and fresh.log == ["a", "b"]
    assert fresh.attachments == ["Doc. 1 · x.pdf (5 caratteri)"] and fresh.summary == "Riepilogo:\nok"
    assert fresh.calls[-1][0] == "set_step"          # last, after every content call


def test_the_log_is_capped():
    s, view, bridge = _ready_session()
    for i in range(250):
        s._log(f"r{i}")
    assert len(s.draft_view["log"]) == MAX_LOG_LINES and s.draft_view["log"][0] == "r50"
```

(`_ready_session`, `_ready_session_with_template`, `_final`, `_error`, `_msg` are the helpers of the file, or small additions to it: `_final(s, rid, text, summary)` delivers `{"type": "final", "id": rid, "text": text, "summary": summary}`; `_error(s, rid, code, message)` an `error` message with `request_id`; `FakeView.calls` records every method call in order.) The older tests asserting the removed statuses ("In attesa delle tue risposte (pannello Domande)", "Interrotta: premi Continua la redazione", "Redazione completata", "Pronta per il prossimo passo", "Compila i campi obbligatori") are updated to the step-aware strings of Task 1 and the steps they now imply.

Run: `cd extension && uv run pytest tests/test_session.py -q` → failures.

- [ ] **Step 2: Implement** as in Interfaces. Keep `_draft_start_request_id`/`_draft_start_pending` and add `_attachments_request_id`/`_attachments_id_pending` with the same "filled on the first send after the hello" rule in `_send_payload`.

- [ ] **Step 3: Run and commit**

`cd extension && uv run ruff check . && uv run pytest -q -m "not headless"` → green.

```bash
git add extension
git commit -m "feat(ext): session state of the drafting workbench: four steps, live log, attachments as one replaced set, letterhead chosen and applied at start" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: The panel: four steps, attachments, letterhead, log, collapse; the letterhead script

**Files:**
- Modify: `extension/librelex_ext/panel.py`
- Create: `scripts/make_letterhead.py`
- Test: `extension/tests/headless/test_panel_drafting.py`, `extension/tests/test_make_letterhead.py` (new, pure: argument parsing and the macro text), `scripts/make_letterhead.py` run by hand on the two firm files at the end of the plan (the lawyer's step, not the harness's)

**Interfaces:**
- `panel.py` constants: `REFERENCE_FILTER` as today; `ATTACHMENT_FILTER = ("Documenti del caso (pdf, odt, docx, doc, rtf, txt)", "*.pdf;*.odt;*.docx;*.doc;*.rtf;*.txt")`; `LETTERHEAD_FILTER = ("Carta intestata (odt, docx, doc)", "*.odt;*.docx;*.doc")`; `DROP_REFUSED = "Trascina un file locale (pdf, odt, docx, doc, rtf, txt)"`; `DROP_ONE_AT_A_TIME = "Un file alla volta: preso il primo, trascina gli altri dopo"`; `file_uris(data) -> list[str]` replaces `first_file_uri` (every `file://` line; the headless helper test updates its expectations: `["file:///Users/x/ricorso%20rossi.docx", "file:///y.odt"]`, `[]`, `[]`).
- `Panel` for kind `Drafting`: `self._step = 1`, `self._consent_pending = False`, `self._attachment_count = 0`, `self._letterhead_entries: list[dict] = []`; `_pick_file(filter) -> str | None` generalises `_pick_reference`; `_load_reference(url)` stays (reads through `read_document`, forwards `set_reference`); `_load_attachment(url)`: `read_document` → `session.add_attachment(name, text, kind)`; errors as for the reference with the prefix `"Allegato non caricato: "`; `_add_letterhead(url)`: `name = Path(unquote(url)).stem`, `out = letterheads.template_path(name)`; `make_letterhead(self.ctx, url, str(out))` then `letterheads.register_letterhead(name, out.name)` and `self.session.set_letterheads(letterheads.list_letterheads())`, `session.note(f"Carta intestata aggiunta: {name} ({out})")`; a `DocumentActionError` or any exception → `session.note(f"Carta intestata non creata: {e}")`. Commands: `attachment_add` → pick with `ATTACHMENT_FILTER` then `_load_attachment`; `attachment_remove` → `session.remove_attachment(selected row of Attachments)`; `letterhead_add` → pick with `LETTERHEAD_FILTER` then `_add_letterhead`; `draft_new` → `session.new_drafting()`; `verify_document` and `cancel` as in Azioni (same command strings, so `actionPerformed` needs no new branch for them); `draft_resume` reads `ResumeInput` as today. `itemStateChanged`: `Letterhead` → `session.choose_letterhead(index)`; `Attachments` → enables `AttachmentRemove` when a row is selected (`_apply_enabled`). Drop: `uris = file_uris(...)`; none → `DROP_REFUSED`; the first is routed by `drop_role(name, self._reference_present)` to `_load_reference` or `_load_attachment`; more than one → a `DROP_ONE_AT_A_TIME` note after loading the first.
- After `_attach_panel_set` on a Drafting panel: `self.session.set_letterheads(letterheads.list_letterheads())` inside `suppress(Exception)` (a bad folder must not break the panel).
- View methods: `set_step(step)`: shows the controls of `DRAFT_STEPS[step]` and hides those of the other steps (a control in both 2 and 3, the consent block, follows `_consent_pending` and `step in (2, 3)`), stores `self._step`; when the step goes from 1 to 3, `_collapse_other_panels()`. `set_consent(summary)`: for a Drafting panel, `_consent_pending = summary is not None`, the `DraftConsentText` label = `render_consent(summary)` and the block visible only when pending and `step in (2, 3)` (for the Actions panel, as today). `set_log(lines)`: `Log` text = `"\n".join(lines)`; `append_log(line)`: appends with a newline (and keeps the box scrolled: set the text, then `ctrl.setSelection` at the end inside `suppress(Exception)`). `set_expected_partitions(labels)`: `Expected` `StringItemList`. `set_attachments(labels)`: `Attachments` `StringItemList`, `_attachment_count = len(labels)`, `_apply_enabled`. `set_letterheads(labels, selected)`: `Letterhead` `StringItemList` and `SelectedItems = (selected,)` under `_quiet_items`. `set_summary(text)`: `Summary` text. `set_questions`/`set_answer_values`/`set_field_values`/`set_template`/`set_reference`/`set_partitions`/`set_draft_status` as today but all on the Drafting model (`set_draft_status` no longer toggles `ResumeInput`/`Resume`: they belong to step 4 and follow `set_step`). `_apply_enabled` adds `AttachmentRemove` (a row selected, not busy, `_attachment_count > 0`) and `DraftCancel` (`_busy`).
- `_collapse_other_panels()`: `sidebar = self.frame.getController().getSidebar()`; `deck = sidebar.getDecks().getByName("LibreLexDeck")`; `panels = deck.getPanels()`; for `LibreLexActionsPanel` and `LibreLexCitationsPanel`: `panels.getByName(id).collapse()`; the whole thing in one `suppress(Exception)` (design §3.5: best effort, nothing re-expanded). Verified by the field test only (headless LibreOffice has no sidebar).
- `_store_typed_values` on `dispose`: fields, notes and `answers_draft` (the Drafting panel holds the answer rows now).
- `_replay`: for `Drafting`, `session.replay_drafting(self)` then `set_busy(...)` as today; `Questions` branch removed; the module docstring names the four panels.
- `scripts/make_letterhead.py`: `python3 scripts/make_letterhead.py NAME SOURCE [--out DIR]`: `SOURCE` an odt/docx/doc; `DIR` defaults to `<config dir>/modelli` (computed by importing `librelex_ext.paths` and `librelex_ext.letterheads` with `extension/` on `sys.path`; both are pure); writes a macro `librelex_make_letterhead.py` into a fresh private profile's `user/Scripts/python/` (the `run_probe` pattern: `-env:UserInstallation=<file URI>`, `--headless --norestore --nologo`, the script URL `vnd.sun.star.script:librelex_make_letterhead.py$main?language=Python&location=user`) that puts `extension/` on `sys.path`, imports `librelex_ext.document.make_letterhead`, reads `LIBRELEX_LH_SOURCE`/`LIBRELEX_LH_OUT` from the environment, writes `OK <path>` or `FAILED <traceback>` to `LIBRELEX_LH_RESULT`, and terminates the desktop; on `OK` the script registers the template (`letterheads.register_letterhead(name, filename, out_dir)`) and prints the path; on failure prints the message and exits 1; refuses to overwrite (the adapter already does; the script checks first for a clear message). `SOFFICE` env override as in `dev_install.sh`; the temp profile is removed afterwards. Pure helpers `macro_text(ext_dir) -> str` and `parse_args(argv) -> Namespace` for the unit test.

- [ ] **Step 1: Failing tests**

`extension/tests/headless/test_panel_drafting.py`: `file_uris` replaces `first_file_uri` (expectations above); add `drop_role` import check through `librelex_ext.session` (pure, but the probe proves `panel.py` still imports under soffice with the new names: `from librelex_ext.panel import ATTACHMENT_FILTER, LETTERHEAD_FILTER, collect_fields, file_uris`).

`extension/tests/test_make_letterhead.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("make_letterhead",
                                                  REPO / "scripts" / "make_letterhead.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_letterhead"] = module
    spec.loader.exec_module(module)
    return module


def test_arguments_and_macro(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRELEX_CONFIG", str(tmp_path / "config.toml"))
    m = _load()
    args = m.parse_args(["SAPG Legal", "carta.docx"])
    assert args.name == "SAPG Legal" and args.source == "carta.docx"
    assert Path(args.out) == tmp_path / "modelli"
    args = m.parse_args(["X", "c.odt", "--out", str(tmp_path / "m")])
    assert Path(args.out) == tmp_path / "m"
    macro = m.macro_text(str(REPO / "extension"))
    assert "from librelex_ext.document import make_letterhead" in macro
    assert "LIBRELEX_LH_SOURCE" in macro and "LIBRELEX_LH_RESULT" in macro
    assert "g_exportedScripts = (main,)" in macro
```

Run: `cd extension && uv run pytest tests/test_make_letterhead.py -q` → fails (no script); the headless helper test fails on the import.

- [ ] **Step 2: Implement** `panel.py` and the script as in Interfaces. The panel's step switch must never raise inside a listener: every `getControl` of a name absent from the model is skipped (`hasByName`), as today.

- [ ] **Step 3: Run, check the panel under soffice, commit**

`cd extension && uv run ruff check . && uv run pytest -q -m "not headless" && uv run pytest -q -m headless tests/headless/test_panel_drafting.py tests/headless/test_registry.py` → green. Also `cd .. && uv run --project extension ruff check scripts/make_letterhead.py`.

```bash
git add extension scripts/make_letterhead.py
git commit -m "feat(ext): Redazione panel in four steps with attachments, letterhead choice, live log and the letterhead script" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: End to end, docs, version 0.7.0

**Files:**
- Modify: `extension/tests/headless/test_e2e_draft.py`, `extension/librelex_ext/__init__.py`, `extension/description.xml`, `extension/tests/test_build_oxt.py`, `README.md`, `docs/superpowers/specs/2026-09-07-librelex-it-design.md`, `docs/superpowers/specs/2026-09-19-guided-drafting-design.md`

**Interfaces:** none new; the e2e drives the Session exactly as the panel does.

- [ ] **Step 1: Extend the e2e test** (`test_e2e_draft.py`), keeping the existing assertions unless named here:
  - `RecView` gains the seven workbench methods (`step`, `log` list, `expected`, `attachments`, `letterheads`, `summary`).
  - Before `draft_start`: build a letterhead template in the probe (the `build_source` of `tests/headless/test_letterhead.py`, imported from there, gives a `.docx`; `make_letterhead(ctx, url, str(modelli / "SAPG Legal.ott"))` produces the `.ott`; `letterheads.register_letterhead("SAPG Legal", "SAPG Legal.ott", modelli)`; the test sets `LIBRELEX_CONFIG` to a config under `tmp_path` already, so `letterheads.templates_dir()` is `tmp_path / "modelli"`), then `s.set_letterheads(letterheads.list_letterheads())` and `s.choose_letterhead(1)`.
  - An attachment: the probe writes `fattura_12.txt` ("Fattura n. 12 del 3 marzo 2025 di Euro 12.000,00.") and calls `s.add_attachment(*read_document(...))` (name, text, kind), then `pump`; assert `view.attachments == ["Doc. 1 · fattura_12.txt (N caratteri)"]`.
  - The stub's turn 1 becomes: `leggi_atto_riferimento`, then `leggi_allegato {"numero": 1}`, then `chiedi_dati` (with usage); turn 2: `replace_text`, `insert_markdown` with `"### CONCLUSIONI\n\nSi chiede l'ingiunzione di pagamento di Euro 12.000,00.\n\n- doc. 1: fattura n. 12"`, `redazione_completata`. `len(stub.requests) == 6`.
  - Consents: two, in order `reference` (name `ricorso_rossi.docx`) then `attachments` (name `"Doc. 1 fattura_12.txt"`, `chars` = the file's length); `consent_pending is None` at the end.
  - Steps: after `draft_start` + pump `view.step == 2` and `status_start == ["Rispondi alle 1 domande e premi Continua", True]`; the log contains `"Avvio della redazione: decreto_ingiuntivo_ordinario"` and a line starting with `"Inserito: "` for the base (the core inserts it through `insert_markdown`); after `draft_answer` + pump `view.step == 4`, `status_end == ["Redazione completata: Verifica citazioni, poi Nuova redazione", True]`, `view.summary` starts with `"Riepilogo:\n" + RIEPILOGO` and contains `"Allegati: Doc. 1 fattura_12.txt"`; the log's last lines include `"Sostituito: «[SEDE]»"` and `"Inserito: CONCLUSIONI"`.
  - Styles and letterhead: `paragraph_texts` after the drafting: the base's first paragraph (`## RICORSO PER DECRETO INGIUNTIVO` from Plan 3's `base_to_markdown`) carries `LibreLex Titolo atto`, the `ILL.MO SIG. TRIBUNALE DI MILANO` paragraph `LibreLex Intestazione`, `CONCLUSIONI` `LibreLex Sezione`, `- doc. 1: fattura n. 12` `LibreLex Punto`, and the lawyer's own first paragraph keeps its style (`Standard` or `Default Paragraph Style`, whatever `new_doc` gives: assert it is not a `LibreLex` style); `page_facts(doc)` (from the letterhead test module) reports `header` True and `graphics == 1` and `len(styles) == 10`.
  - The transcript: the `set_attachments` line `"Allegati: 1 documenti (N caratteri)."` and the `"Tu: allegato fattura_12.txt"` label appear between the reference line and the start label; `t[...]` indexes updated accordingly.
  - The wire: `first["messages"][1]["content"]` contains `"Allegati del fascicolo: Doc. 1 fattura_12.txt"`; the tool set includes `leggi_allegato`; the attachment travelled once, wrapped as `<<<DATI: allegato 1 (fattura_12.txt)>>>`; `blob.count(the attachment text) == 1`.
- [ ] **Step 2: Version and docs**: `__version__ = "0.7.0"`, `description.xml` `0.7.0`, `test_build_oxt.py` names `LibreLex-IT-0.7.0.oxt`; README: the "Guided drafting" section rewritten for the four steps (Atto e dati with Allegati and Carta intestata, Domande, Redazione in corso with the log, Fine with Verifica citazioni / Riprendi / Nuova redazione), the drop rule, the attachment limits, the letterhead templates (`modelli/`, `modelli.json`, "Aggiungi…" takes the file's stem as the name, `scripts/make_letterhead.py NAME SOURCE`, PDF letterheads out of scope), the act styles (the ten names, adjustable in the template), the "Usage" paragraph naming four panels; main spec §5.1 (four panels), §5.3 (`read_document`, `apply_letterhead` as adapter helpers), §8.2 (already amended by Plan 3: check), Appendix A (`leggi_allegato` listed under the internal tools); guided-drafting design §6: a one-line pointer to the workbench design §3.
- [ ] **Step 3: Run everything and commit**

`cd core && uv run ruff check . && uv run pytest -q` → green; `cd extension && uv run ruff check . && uv run pytest -q -m "not headless" && uv run pytest -q -m headless` (all headless files, including `test_e2e_draft.py`, `test_install.py` on a private profile) → green; `uv run pytest tests/test_build_oxt.py -q` → green.

```bash
git add extension README.md docs
git commit -m "feat(ext): drafting workbench end to end: attachment read after consent, act styles on the letterhead page style; extension 0.7.0" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## After the plan (the lawyer's go, not part of the SDD run)

1. Merge `feature/drafting-workbench` into `main` (no fast-forward, message `merge: drafting workbench (M3.6): one Redazione panel, attachments, act styles, letterheads`).
2. With LibreOffice closed: `scripts/dev_install.sh` (installs 0.7.0 into the real profile).
3. Build the two templates from the firm's files with `scripts/make_letterhead.py "SAPG Legal" "/Users/gpuzio/Downloads/NUOVA CARTA INTESTATA_RM.docx"` and `scripts/make_letterhead.py "SAPG Legaltech" "/Users/gpuzio/Library/CloudStorage/Dropbox/SAPG Legal Tech/Modelli societario/Carta intesta SAPG 2025/carta intestata legal tech.docx"`, then set `"default": true` on SAPG Legal in `~/Library/Application Support/LibreLex/modelli/modelli.json`. The firm's files never enter the repo.
4. Field test: the step flow, the collapse of Azioni and Citazioni, a PDF attachment dropped on the panel, the act on both letterheads.

## Self-review notes

- Design coverage: §3.1 to §3.6 → Tasks 3, 4, 5 (the log, the expected partitions, the consent block in steps 2 and 3, the drop rule, the collapse, the session mirror and its replay); §4.2 → Task 2 (`read_document`, PDF via Draw, the refusal of a textless PDF) and Task 4 (limits, the replace-all set); §5.1 → Tasks 1 and 2 (the table, `ensure_act_styles`); §5.2 → Tasks 1, 2 and 5 (`letterheads.py`, `make_letterhead`, "Aggiungi…", the script); §5.3 → Tasks 2 and 4 (`apply_letterhead` at start, `_apply_act_styles` after the Markdown filter; the base pre-formatting is Plan 3's); §5.4 → Task 5; §6 → Tasks 2, 4, 5 (hidden loads, texts in the session only, templates never overwritten, `file://` only); §7 → each task's tests plus the e2e of Task 6; §8 assumption 1 is best effort by design (field test), assumptions 2 and 3 are validated by the headless tests of Task 2; §9 → Task 6.
- Type consistency: `act_style_for(text, origin, from_end)` and `list_prefix(label)` (Task 1) are what `_apply_act_styles` (Task 2) calls; `rebuild_lines(frames)` with `(page, y, x, height, text)` (Task 1) is what `read_document` (Task 2) feeds; `letterheads.list_letterheads()` entries `{name, path, default}` (Task 1) are what `Session.set_letterheads` (Task 4) stores and `render_letterhead_labels` (Task 1) renders; `dispatch_doc_call(..., act_styles=)` (Task 2) is what `_on_doc_call` (Task 4) passes; `DRAFT_STEPS`/`DRAFT_CONSENT` (Task 3) drive `set_step` (Task 5); `drop_role` (Task 4) is used by the panel's drop (Task 5); `read_document` returns `kind`, which `add_attachment(name, text, kind)` takes (Tasks 2, 4, 5).
- Deferred (ledger): PDF letterheads (v2); pseudonymisation (v2); a name prompt for "Aggiungi…"; multi-file drops as one `set_attachments`; the deck height after the field test; the parked minors of the guided-drafting plans.
