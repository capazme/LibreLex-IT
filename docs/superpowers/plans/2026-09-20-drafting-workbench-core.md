# Drafting Workbench, Core (Plan 3 of 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the core what the drafting workbench design needs on its side: the case documents ("allegati") stored per session, sent to the model on demand through a consented `leggi_allegato` hook and listed in every drafting turn; the deterministic base text pre-formatted into the markdown conventions the act styles map from; the recipe amended (attachments as facts, the markdown conventions of an Italian act, short tool names); the tool-name prefixes a proxy injects stripped from the model's prose; the dev CLI able to pass attachments. Plan 4 builds the panel, the document reading and the styles on top of this.

**Architecture:** Everything sits on the existing drafting command (`commands/draft.py`, hooks, `draft_message`, `DraftState`/`DocSession`): attachments are session state like the reference act, with one consent per set (scope `attachments`) and a deny remembered until the set changes; the pre-formatting is a pure function over the generator's text; the prefix stripping is a pure function over the registry's tool names applied to the turn's final text and to the completion summary. No new command in the loop, no protocol version change.

**Tech Stack:** core only (Python 3.12+, pydantic, fastmcp, openai SDK); tests with the fake mcp-legal-it and `ScriptedLLM`.

**Spec:** `docs/superpowers/specs/2026-09-20-drafting-workbench-design.md` §4 (attachments), §5.3 (base pre-formatting and the recipe's conventions), the tool-name note of §1's follow-up (the proxy mangles tool names: `mcp__trade_dress__<word>_<name>`); the main spec §8.2 (consent) and Appendix A. Branch `feature/drafting-workbench` from `main` (2069769 or later), shared with Plan 4.

## Global Constraints

- Core: Python 3.12+, ruff `E F I UP B` line 100; every new module starts with `# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.`; the whole core suite stays green (226 today).
- Code, comments, docs in English; prompt, recipe, tool descriptions and user-facing strings in Italian. No em or en dashes in prose written for docs.
- Protocol: `PROTOCOL_VERSION` stays `1`; `CommandName` gains `set_attachments`; `ConsentSummary.scope` gains `"attachments"`.
- Limits (`agent/state.py`): `MAX_ATTACHMENT_CHARS = 60_000`, `MAX_ATTACHMENTS = 12`, `MAX_ATTACHMENTS_CHARS = 300_000`; `set_attachments` trims each text and refuses (error `bad_request`) a set beyond the counts.
- Consent for the attachments: one `consent_request` per set with `scope="attachments"`, `name` = the names joined by `"; "` as `Doc. N nome`, cut at 200 characters with `…`, `chars` = the total of the set; "document" and "once" both consent for the current set; "deny" is remembered until `set_attachments` is called again; nothing of the attachments in `Status`, `Log` or `Error`.
- Tool names: a proxy may present tools to the model as `mcp__<x>__<word>_<name>`; the core never changes the names it sends, and strips such prefixes from the model's prose (`clean_tool_names`) for every name in the registry.
- Version: core `0.5.0` (`core/pyproject.toml`, `core/src/librelex_core/__init__.py`, `core/tests/test_package.py`).
- Commits: Conventional Commits, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` through several `-m` flags (no heredocs), never amend, never push. Never run LibreOffice from the harness. Never modify anything under `/Users/gpuzio/Desktop/CODE/server-infra2.0/`.
- The extension is not touched by this plan; its headless e2e test keeps passing (the wire it uses is unchanged: `set_attachments` is new and optional).

---

## File structure

```
core/src/librelex_core/
├── agent/state.py              # attachment limits; DocSession.attachments/attachments_consented/attachments_denied
├── protocol.py                 # CommandName set_attachments; ConsentSummary.scope attachments
├── main.py                     # _set_attachments route (no tools)
├── commands/draft.py           # leggi_allegato hook; attachments block in draft_message; base_to_markdown; clean_tool_names applied
├── agent/textclean.py          # clean_tool_names(text, names) (pure)
├── agent/recipes/draft.md      # attachments rule and steps; markdown conventions of an act; short tool names
├── cli.py                      # draft --allegato FILE (repeatable)
core/tests/agent/test_prompt_state.py, commands/test_draft.py, test_main.py, test_protocol.py, test_cli.py, test_package.py,
core/tests/agent/test_textclean.py
docs/superpowers/specs/2026-09-07-librelex-it-design.md (§8.2, Appendix A), core/README.md
```

---

### Task 1: Attachments in the session, `set_attachments`, `leggi_allegato` with consent, the recipe

**Files:**
- Modify: `core/src/librelex_core/agent/state.py`, `core/src/librelex_core/protocol.py`, `core/src/librelex_core/main.py`, `core/src/librelex_core/commands/draft.py`, `core/src/librelex_core/agent/recipes/draft.md`, `core/src/librelex_core/cli.py`, `core/README.md`, `docs/superpowers/specs/2026-09-07-librelex-it-design.md`
- Test: `core/tests/test_protocol.py`, `core/tests/test_main.py`, `core/tests/commands/test_draft.py`, `core/tests/agent/test_prompt_state.py`, `core/tests/test_cli.py`

**Interfaces:**
- `state.py`: `MAX_ATTACHMENT_CHARS = 60_000`, `MAX_ATTACHMENTS = 12`, `MAX_ATTACHMENTS_CHARS = 300_000`; `DocSession.attachments: list[dict] = []` (each `{"n": int, "name": str, "text": str, "chars": int, "kind": str, "troncato": bool}`), `DocSession.attachments_consented: bool = False`, `DocSession.attachments_denied: bool = False`; `state.attachments_label(attachments) -> str` = `"; ".join(f"Doc. {a['n']} {a['name']}")` cut at 200 characters with a trailing `…` when cut; `state.attachments_chars(attachments) -> int`.
- `protocol.py`: `CommandName` gains `"set_attachments"`; `ConsentSummary.scope: Literal["selection", "paragraphs", "reference", "attachments"]`.
- `main.py`: `set_attachments` handled before the `NEEDS_TOOLS` block like `set_reference`: `args["documenti"]` is a list of `{name, text, kind?}`; more than `MAX_ATTACHMENTS` entries, or a total of trimmed texts above `MAX_ATTACHMENTS_CHARS`, or a malformed list → `Error(code="bad_request", message="allegati non validi: al massimo 12 documenti e 300.000 caratteri in totale")`; otherwise the session's list is replaced (numbered from 1 in the given order, texts trimmed to `MAX_ATTACHMENT_CHARS` with `troncato`, `chars` after trimming, `kind` default `"writer"`), `attachments_consented` and `attachments_denied` reset, and the answer is `Final(text=f"Allegati: {N} documenti ({chars} caratteri).", summary={"allegati": [{"n", "name", "chars", "kind", "troncato"}]})`; an empty list clears the set (`Final(text="Allegati rimossi.", summary={"allegati": []})`).
- `commands/draft.py`: a fourth hook tool `LEGGI_ALLEGATO_TOOL` (`leggi_allegato`, parameters `{"numero": {"type": "integer", "description": "Numero dell'allegato (Doc. N)."}}`, required `["numero"]`, description `"Testo dell'allegato numero N del fascicolo (fattura, delibera, decreto, contratto...): i fatti del caso si prendono da qui."`); the hook: no attachments → `("ERRORE: nessun allegato caricato", None)`; a number outside the set → `(f"ERRORE: allegato {n} inesistente (disponibili: 1-{len})", None)`; `session.attachments_denied` → `(CONSENT_DENIED, None)`; not yet consented → `deps.consent(ConsentSummary(scope="attachments", chars=attachments_chars(...), endpoint_host, model, zdr, name=attachments_label(...)))`, "document"/"once" → `attachments_consented = True`, else `attachments_denied = True` and `CONSENT_DENIED`; then `(wrap_data(f"allegato {n} ({name})", text), None)`. `draft_message` gains, right after the reference block, `Allegati del fascicolo: Doc. 1 nome (12.300 caratteri[, troncato]); Doc. 2 …: leggi con leggi_allegato quelli che servono ai fatti; l'elenco "Si allegano" segue questa numerazione.` when the set is non-empty. `draft_summary` gains `"allegati": [{"n", "name", "chars"}]`.
- Recipe (`recipes/draft.md`): rule 6 becomes `RISERVATEZZA: ... (as today about the reference) ...; gli allegati del fascicolo sono i documenti del caso: i loro fatti (date, importi, parti, estremi) vanno usati, i dati personali che contengono entrano nell'atto solo dove l'atto li richiede.`; step 1 gains, before the read_paragraphs sentence: `Se ci sono allegati, leggi con leggi_allegato quelli pertinenti ai fatti prima di chiedere qualsiasi cosa: una domanda la cui risposta è in un documento non va fatta.`; step 4's list of partitions ends with `documenti allegati, uno per riga come "- doc. N: descrizione breve" seguendo la numerazione degli allegati, con "- procura alle liti" per primo quando l'atto la richiede`; a new last rule 7: `STRUMENTI: nelle risposte e nel riepilogo chiama gli strumenti con il nome breve (cite_law, contributo_unificato), mai con prefissi tecnici.`
- CLI: `draft --allegato FILE` (repeatable, `action="append"`): each file read as UTF-8 text and set on the session as an attachment (name = file name, kind `"text"`) before the start turn; the summary line adds `· allegati: N`.
- Docs: main spec §8.2 gains a bullet on the attachments consent (scope `attachments`, the set named, deny remembered until the set changes); Appendix A gains `set_attachments` and `Final.summary.allegati`; `core/README.md` mentions `--allegato`.

- [ ] **Step 1: Failing tests**

`core/tests/test_protocol.py`, append:

```python
def test_set_attachments_command_and_consent_scope():
    p.parse_extension_line(json.dumps({"type": "command", "id": "r", "doc_id": "d",
                                       "name": "set_attachments",
                                       "args": {"documenti": [{"name": "a.pdf", "text": "x"}]}}))
    s = p.ConsentSummary(scope="attachments", chars=10, endpoint_host="h", model="m", zdr=True,
                         name="Doc. 1 a.pdf")
    assert s.scope == "attachments"
```

`core/tests/agent/test_prompt_state.py`, append:

```python
def test_attachment_limits_and_labels():
    from librelex_core.agent.state import (MAX_ATTACHMENT_CHARS, MAX_ATTACHMENTS,
                                           MAX_ATTACHMENTS_CHARS, attachments_chars,
                                           attachments_label)
    assert (MAX_ATTACHMENT_CHARS, MAX_ATTACHMENTS, MAX_ATTACHMENTS_CHARS) == (60_000, 12, 300_000)
    docs = [{"n": 1, "name": "fattura_12.pdf", "chars": 100, "text": "a" * 100},
            {"n": 2, "name": "delibera.docx", "chars": 50, "text": "b" * 50}]
    assert attachments_label(docs) == "Doc. 1 fattura_12.pdf; Doc. 2 delibera.docx"
    assert attachments_chars(docs) == 150
    long = [{"n": i, "name": "x" * 40 + ".pdf", "chars": 1, "text": "x"} for i in range(1, 8)]
    label = attachments_label(long)
    assert len(label) <= 200 and label.endswith("…")
    s = DocSession("d1")
    assert s.attachments == [] and s.attachments_consented is False and s.attachments_denied is False


def test_recipe_mentions_attachments_and_short_tool_names():
    from librelex_core.agent.prompt import load_recipe
    text = load_recipe()
    for needle in ("leggi_allegato", "una domanda la cui risposta è in un documento non va fatta",
                   "- doc. N: descrizione breve", "procura alle liti", "STRUMENTI", "nome breve"):
        assert needle in text, needle
```

`core/tests/test_main.py`, append:

```python
async def test_set_attachments_stores_trims_and_refuses_too_many():
    h = Harness(FakeDocument(["x"]))

    async def scenario(h: Harness):
        await h.send(HELLO)
        await h.pump(p.HelloOk)
        docs = [{"name": "fattura_12.pdf", "text": "FATTURA " * 10, "kind": "pdf"},
                {"name": "delibera.docx", "text": "D" * 70_000}]
        await h.send(p.Command(id="r1", doc_id="d1", name="set_attachments",
                               args={"documenti": docs}))
        await h.pump(p.Final)
        final = h.received[-1]
        assert final.text == "Allegati: 2 documenti (60080 caratteri)."
        assert final.summary["allegati"] == [
            {"n": 1, "name": "fattura_12.pdf", "chars": 80, "kind": "pdf", "troncato": False},
            {"n": 2, "name": "delibera.docx", "chars": 60_000, "kind": "writer", "troncato": True}]
        session = h.server._session("d1")
        assert len(session.attachments[1]["text"]) == 60_000
        session.attachments_consented = session.attachments_denied = True
        await h.send(p.Command(id="r2", doc_id="d1", name="set_attachments",
                               args={"documenti": [{"name": "x", "text": "y"}] * 13}))
        await h.pump(p.Error)
        assert h.received[-1].code == "bad_request" and "12" in h.received[-1].message
        await h.send(p.Command(id="r3", doc_id="d1", name="set_attachments",
                               args={"documenti": []}))
        await h.pump(p.Final)
        assert h.received[-1].summary == {"allegati": []} and session.attachments == []
        assert session.attachments_consented is False and session.attachments_denied is False

    await h.run(scenario)
```

`core/tests/commands/test_draft.py`, append:

```python
async def test_attachments_are_listed_read_with_one_consent_and_denied_until_the_set_changes():
    server, _ = make_fake_legal_server()
    doc = FakeDocument([""], consent_decisions=["once", "once"])
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        session = DocSession("d1")
        session.attachments = [
            {"n": 1, "name": "fattura_12.pdf", "text": "Fattura n. 12 del 3 marzo 2025, Euro 12.000",
             "chars": 43, "kind": "pdf", "troncato": False},
            {"n": 2, "name": "delibera.docx", "text": "Delibera del 25 giugno 2026", "chars": 27,
             "kind": "writer", "troncato": False}]
        llm = ScriptedLLM([
            tool_turn(("leggi_allegato", {"numero": 1}), ("leggi_allegato", {"numero": 2})),
            tool_turn(("leggi_allegato", {"numero": 3})),
            text_turn("letti")])
        deps = await _deps(llm, doc, tools)
        out = await run_draft(session, {"action": "start", "tipo_atto": "atto_di_citazione",
                                        "fields": {"attore": "A"}}, deps, emit, "r1")
    user = llm.calls[0][0][1]["content"]
    assert ("Allegati del fascicolo: Doc. 1 fattura_12.pdf (43 caratteri); "
            "Doc. 2 delibera.docx (27 caratteri)") in user
    assert len(doc.consent_requests) == 1
    req = doc.consent_requests[0]
    assert req.scope == "attachments" and req.name == "Doc. 1 fattura_12.pdf; Doc. 2 delibera.docx"
    assert req.chars == 70
    tool_msgs = [m for m in llm.calls[1][0] if m.get("role") == "tool"]
    assert "<<<DATI: allegato 1 (fattura_12.pdf)>>>" in tool_msgs[0]["content"]
    assert "Delibera del 25 giugno 2026" in tool_msgs[1]["content"]
    third = [m for m in llm.calls[2][0] if m.get("role") == "tool"][-1]["content"]
    assert third == "ERRORE: allegato 3 inesistente (disponibili: 1-2)"
    assert draft_summary(session, out)["allegati"] == [
        {"n": 1, "name": "fattura_12.pdf", "chars": 43}, {"n": 2, "name": "delibera.docx", "chars": 27}]
    names = {t["function"]["name"] for t in llm.calls[0][1]}
    assert "leggi_allegato" in names


async def test_attachments_consent_denied_is_remembered():
    server, _ = make_fake_legal_server()
    doc = FakeDocument([""], consent_decisions=["deny"])
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        session = DocSession("d1")
        session.attachments = [{"n": 1, "name": "a.txt", "text": "abc", "chars": 3,
                                "kind": "text", "troncato": False}]
        llm = ScriptedLLM([tool_turn(("leggi_allegato", {"numero": 1})),
                           tool_turn(("leggi_allegato", {"numero": 1})), text_turn("senza")])
        await run_draft(session, {"action": "start", "tipo_atto": "atto_di_citazione",
                                  "fields": {"attore": "A"}}, await _deps(llm, doc, tools), emit, "r1")
        msgs = [m["content"] for c in llm.calls[1:] for m in c[0] if m.get("role") == "tool"]
        assert all(m.startswith("ERRORE: invio del testo") for m in msgs[-2:])
        assert len(doc.consent_requests) == 1 and session.attachments_denied is True
        llm2 = ScriptedLLM([tool_turn(("leggi_allegato", {"numero": 1})), text_turn("mai")])
        await run_draft(session, {"action": "continue", "message": "vai"},
                        await _deps(llm2, doc, tools), emit, "r2")
        assert len(doc.consent_requests) == 1   # still denied, not asked again
```

`core/tests/test_cli.py`, append:

```python
def test_draft_subcommand_passes_attachments(tmp_path, capsys):
    from tests.fakes import ScriptedLLM, text_turn, tool_turn
    a = tmp_path / "fattura_12.txt"
    a.write_text("Fattura n. 12", encoding="utf-8")
    llm = ScriptedLLM([tool_turn(("leggi_allegato", {"numero": 1})), text_turn("ok")])
    rc = main(["draft", "--tipo", "decreto_ingiuntivo_ordinario", "--campo", "creditore=Alfa",
               "--campo", "debitore=Beta", "--campo", "importo=12000", "--allegato", str(a)],
              tools_factory=_factory(), llm_factory=lambda cfg: llm)
    assert rc == 0
    out = capsys.readouterr()
    assert "allegati: 1" in out.out
    assert 'allegati "Doc. 1 fattura_12.txt": 13 caratteri' in out.err
    assert "Allegati del fascicolo: Doc. 1 fattura_12.txt" in llm.calls[0][0][1]["content"]
```

Run: `cd core && uv run pytest tests/test_protocol.py tests/agent/test_prompt_state.py tests/test_main.py tests/commands/test_draft.py tests/test_cli.py -q` → failures.

- [ ] **Step 2: Implement**

As in Interfaces. `_cli_consent` prints `allegati "<name>": <chars> caratteri` for the `attachments` scope (same shape as the reference line). The attachments block of `draft_message` formats `chars` with the Italian thousands dot (reuse the pattern of the reference block).

- [ ] **Step 3: Run and commit**

`cd core && uv run ruff check . && uv run pytest -q` → green.

```bash
git add core docs/superpowers/specs/2026-09-07-librelex-it-design.md
git commit -m "feat(core): case attachments for the drafting: set_attachments, leggi_allegato with one consent per set, recipe reads the facts from the documents" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Base pre-formatting, act markdown conventions in the recipe, tool-name cleaning, core 0.5.0

**Files:**
- Create: `core/src/librelex_core/agent/textclean.py`
- Modify: `core/src/librelex_core/commands/draft.py`, `core/src/librelex_core/agent/recipes/draft.md`, `core/pyproject.toml`, `core/src/librelex_core/__init__.py`
- Test: `core/tests/agent/test_textclean.py` (new), `core/tests/commands/test_draft.py`, `core/tests/agent/test_prompt_state.py`, `core/tests/test_package.py`

**Interfaces:**
- `textclean.clean_tool_names(text: str, names: Iterable[str]) -> str`: for every name in `names` (longest first), replaces occurrences of `mcp__<token>__<token>_<name>` (`<token>` = `[A-Za-z0-9]+`, the second one may contain underscores only before the name) with `name`, and also `mcp__<token>__<name>`; word boundaries respected; a text without such prefixes is returned unchanged (same object).
- `draft.base_to_markdown(text: str) -> str` replaces `to_markdown` for the base insertion (keep `to_markdown` as the line-splitting helper it is): every line becomes a paragraph; the first non-empty line → `## <line>` (the act's title); a line whose text, stripped, starts with `ILL.MO`, `TRIBUNALE`, `GIUDICE DI PACE`, `CORTE`, `AL SIG.`, `ALL'ILL.MO` (case-insensitive) → `# <line>`; a line of at most 40 characters with at least one letter, all letters uppercase, that is not the first line and not caught above → `### <line>`; a line matching `^\(.*\)$` right after the title (`(Artt. 633 e ss. c.p.c.)`) stays a paragraph; lines matching `^\d+\.\s` or `^-\s` keep their list marker; everything else unchanged. Idempotent on markdown input (a line already starting with `#`, `-`, `>` or a digit-dot is left alone).
- `run_draft`: after the turn, `outcome.text = clean_tool_names(outcome.text, deps.registry.names)`; in the `redazione_completata` hook, `draft.riepilogo = clean_tool_names(riepilogo, names)` where `names` is `deps.registry.names` at hook-building time (pass the list into `hooks_for` through `deps.registry.names`).
- Recipe: the "Stile" section is replaced by the markdown conventions of §5.3 of the workbench design:

```markdown
## Stile e forma dell'atto
Registro forense, formule complete; nelle risposte in chat testo semplice, senza markdown. Nel documento scrivi markdown con queste convenzioni, che diventano gli stili dell'atto: `# ` per l'intestazione del giudice (una riga, in maiuscolo: TRIBUNALE DI MILANO); `## ` per il titolo dell'atto; `### ` per le partizioni in maiuscolo (PREMESSO CHE, RICORRE, INGIUNGERE, P.Q.M., CONCLUSIONI); un paragrafo per ogni capoverso del corpo; `- ` all'inizio di ogni punto delle premesse, dei motivi e dei documenti; `> ` per il testo letterale di una norma o di una massima; il ruolo di una parte da solo su una riga come `- ricorrente -`; `contro` da solo su una riga tra le parti; `* * * * *` su una riga tra le grandi partizioni; in chiusura luogo e data su una riga e la firma su un'altra (`Avv. Nome Cognome`). Nomi delle parti in grassetto la prima volta. Lascia tra parentesi quadre ciò che nessuno ti ha fornito.
```

- Version core `0.5.0`.

- [ ] **Step 1: Failing tests**

`core/tests/agent/test_textclean.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_core.agent.textclean import clean_tool_names

NAMES = ["contributo_unificato", "scadenza_processuale", "cite_law", "leggi_allegato"]


def test_prefixes_are_stripped_only_for_known_names():
    text = ("Calcolo con mcp__trade_dress__swamp_contributo_unificato e "
            "mcp__trade_dress__hello_scadenza_processuale; poi mcp__x__cite_law. "
            "Non tocco mcp__trade_dress__swamp_altro_strumento.")
    out = clean_tool_names(text, NAMES)
    assert out == ("Calcolo con contributo_unificato e scadenza_processuale; poi cite_law. "
                   "Non tocco mcp__trade_dress__swamp_altro_strumento.")
    plain = "Uso contributo_unificato e basta."
    assert clean_tool_names(plain, NAMES) is plain
```

`core/tests/commands/test_draft.py`, append:

```python
def test_base_to_markdown_marks_the_act_structure():
    from librelex_core.commands.draft import base_to_markdown
    text = ("RICORSO PER DECRETO INGIUNTIVO\n(Artt. 633 e ss. c.p.c.)\n\n"
            "ILL.MO SIG. TRIBUNALE DI [SEDE]\n\nRICORSO\n\nIl sottoscritto Avv. [LEGALE] espone.\n"
            "ESPONE\n\nChe il credito è certo.\n\nSi allegano:\n1. Procura alle liti\n2. Fattura\n\n"
            "[Luogo], [Data]\nAvv. [LEGALE]")
    md = base_to_markdown(text)
    lines = [ln for ln in md.split("\n") if ln]
    assert lines[0] == "## RICORSO PER DECRETO INGIUNTIVO"
    assert lines[1] == "(Artt. 633 e ss. c.p.c.)"
    assert lines[2] == "# ILL.MO SIG. TRIBUNALE DI [SEDE]"
    assert lines[3] == "### RICORSO" and lines[5] == "### ESPONE"
    assert lines[7] == "Si allegano:" and lines[8] == "1. Procura alle liti"
    assert lines[-1] == "Avv. [LEGALE]" and lines[-2] == "[Luogo], [Data]"
    assert "\n\n" in md and "\n\n\n" not in md
    assert base_to_markdown("## Già markdown\n\n- punto") == "## Già markdown\n\n- punto"


async def test_final_text_and_riepilogo_lose_the_proxy_prefixes():
    server, _ = make_fake_legal_server()
    doc = FakeDocument([""])
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        session = DocSession("d1")
        llm = ScriptedLLM([
            tool_turn(("redazione_completata", {"riepilogo":
                       "Calcoli: mcp__trade_dress__swamp_contributo_unificato 129,50."}),
                      text="Fatto con mcp__trade_dress__peasant_cite_law.")])
        out = await run_draft(session, {"action": "start", "tipo_atto": "atto_di_citazione",
                                        "fields": {"attore": "A"}},
                              await _deps(llm, doc, tools), emit, "r1")
    assert session.draft.riepilogo == "Calcoli: contributo_unificato 129,50."
    assert out.text == "Fatto con cite_law."
```

(`ScriptedLLM.stream` streams `turn.text` word by word before returning the tool calls, so `out.text` is the streamed prose; the cleaning applies to `outcome.text` after the turn.) The base insertion test `test_start_inserts_the_base_then_the_model_asks_questions_and_stops` asserts the inserted markdown starts with `"RICORSO PER DECRETO INGIUNTIVO\n\n(Artt. 633"`: update it to `"## RICORSO PER DECRETO INGIUNTIVO\n\n(Artt. 633"` and, if the fake's bozza has an `ILL.MO SIG. TRIBUNALE DI [SEDE]` line, assert it became `# ILL.MO SIG. TRIBUNALE DI [SEDE]`. `test_prompt_state.py`: the recipe test gains the needles `"## Stile e forma dell'atto"`, "`# ` per l'intestazione", "`### ` per le partizioni", "`* * * * *`". `test_package.py`: `0.5.0`.

Run: `cd core && uv run pytest tests/agent/test_textclean.py tests/commands/test_draft.py tests/agent/test_prompt_state.py tests/test_package.py -q` → failures.

- [ ] **Step 2: Implement**

`textclean.py` (one compiled regex per call: `re.compile(r"\bmcp__[A-Za-z0-9]+__(?:[A-Za-z0-9]+_)?(" + "|".join(map(re.escape, sorted(names, key=len, reverse=True))) + r")\b")` → `\1`); `base_to_markdown` in `draft.py` with the rules above (helper predicates, no regex soup); the hook and post-turn cleaning; the recipe section; the version.

- [ ] **Step 3: Run and commit**

`cd core && uv run ruff check . && uv run pytest -q` → green; `cd extension && uv run pytest -q -m "not headless"` still green (nothing changed there).

```bash
git add core
git commit -m "feat(core): base text pre-formatted for the act styles, act markdown conventions in the recipe, proxy tool-name prefixes stripped; core 0.5.0" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review notes

- Design coverage: §4.1 to §4.3 → Task 1; §5.3 pre-formatting and recipe conventions → Task 2; the tool-name note → Task 2; main spec §8.2 and Appendix A → Task 1. §4.2 (reading the files) and everything in §3, §5.1, §5.2 are Plan 4.
- Type consistency: `attachments_label`/`attachments_chars` (Task 1) are what the hook and the CLI use; `clean_tool_names` (Task 2) takes `deps.registry.names`, which exists (`ToolRegistry.names`); `base_to_markdown` replaces `to_markdown` at the single call site in `insert_base` (keep `to_markdown` exported: the e2e of Plan 4 asserts on the base's first line `## RICORSO …`).
- Deferred: PDF attachments text quality (extension side); pseudonymisation (v2).
