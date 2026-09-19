# Guided Drafting, Core (Plan 1 of 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the core the drafting flow of the design doc `docs/superpowers/specs/2026-09-19-guided-drafting-design.md`: the plugin's own recipe, a complete `draft` profile, catalogue commands (`list_templates`, `template_info`), the deterministic base inserted by the core, a stateful `draft` command in three shapes (`start`, `answer`, `continue`) with structured questions and a completion summary, the reference act (`set_reference`, `leggi_atto_riferimento` with consent), the `replace_text` document action, a dev CLI that drives it all without LibreOffice. Plan 2 builds the "Redazione" panel on this protocol.

**Architecture:** Everything stays inside the existing agent loop (`agent/loop.py:run_turn`): the draft command adds *state-backed internal tools* through a small hook mechanism in `AgentDeps` (`hooks`: name → handler returning the tool result and an optional stop reason), builds the user message of every turn from `DocSession.draft` (a `DraftState` dataclass) so nothing depends on compacted history, and inserts the generator's base text before the first model call. New deterministic commands read the catalogue through `LegalToolsClient` and cache it per process. Grounding on write, consent, limits and cancellation are untouched.

**Tech Stack:** core only: Python 3.12+, pydantic, fastmcp (`Client.read_resource`), openai SDK; tests with the fake mcp-legal-it of `core/tests/conftest.py` and `ScriptedLLM`.

**Spec:** `docs/superpowers/specs/2026-09-19-guided-drafting-design.md` (binding for the flow) and `docs/superpowers/specs/2026-09-07-librelex-it-design.md` (everything else). Branch: `feature/guided-drafting` from `main` (52d780e or later), shared with Plan 2.

## Global Constraints

- Core: Python 3.12+, ruff `E F I UP B` line 100; every new module starts with `# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.`; the whole core suite stays green (191 tests today).
- Code, comments, docstrings and docs in English; prompts, tool descriptions, panel-facing strings and the recipe in Italian. No em dashes or en dashes in prose written for docs.
- Protocol: `PROTOCOL_VERSION` stays `1`; `CommandName` gains `list_templates`, `template_info`, `set_reference`; `ConsentSummary.scope` gains `"reference"` and the field `name: str | None = None`; the `draft` command takes `args.action` in `start` | `answer` | `continue` (a missing or unknown action answers `Error(code="bad_request")`).
- Profile `draft` legal tools: `genera_modello_atto`, `lista_categorie_atti`, `cite_law`, `fetch_act_index`, `fetch_full_act`, `verifica_citazioni`, `ROUTING_GENERATORS` (20, the exact list in Task 1), `CATALOGUE_CALCULATORS` (17, the exact list in Task 1). Document tools: `read_paragraphs`, `insert_markdown`, `replace_text`. The allowlist becomes 55 names. `GROUNDING_SOURCES` unchanged (15 names). The `review` profile's document tools gain `replace_text`.
- Undo labels: base insertion `LibreLex: base <tipo_atto>` with bookmark `LibreLex.atto.<tipo_atto>`; model turns of a drafting `LibreLex: redazione <tipo_atto>`. Redline author is the loop's `WRITE_AUTHOR` (`LibreLex`).
- Reference act: trimmed to `MAX_REFERENCE_CHARS = 60_000`, never logged, memory only; the first `leggi_atto_riferimento` call in a session asks consent with `scope="reference"`, `name=<file name>`, `chars`, unless `session.consent == "document"`; "deny" returns `CONSENT_DENIED` and the model goes on without it.
- Structured questions: at most 8 per `chiedi_dati` call (more are truncated with an `ERRORE:` line in the tool result asking to keep 8); `tipo` in `testo` | `numero` | `data` | `sino`, default `testo`.
- Limits unchanged (`max_iterations 12`, `turn_timeout_s 180`).
- Version: core `0.4.0` (`core/pyproject.toml`, `core/src/librelex_core/__init__.py`, `core/tests/test_package.py`).
- Commits: Conventional Commits with the trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` through several `-m` flags (no heredocs), never amend, never push. Never run LibreOffice, its bundled python, `unopkg` or `scripts/dev_install.sh`. Never modify anything under `/Users/gpuzio/Desktop/CODE/server-infra2.0/` (read-only reference: `plugin/server/src/data/modelli_atti.json`, `plugin/server/src/tools/*.py`, `plugin/skills/genera-atto/SKILL.md`, `plugin/agents/redattore-atti.md` in the `json-output-and-entrypoint` worktree).
- The extension is not touched by this plan; its headless test `extension/tests/headless/test_e2e_draft.py` (old `draft {message}` shape) is marked `xfail(strict=False, reason="protocol changed by plan 1; rewritten in plan 2")` in Task 5 so the branch's suites stay meaningful until Plan 2 lands.

---

## File structure

```
core/src/librelex_core/
├── mcp/client.py                  # ALLOWLIST 55; read_resource(uri)
├── agent/profiles.py              # ROUTING_GENERATORS, CATALOGUE_CALCULATORS, draft/review profiles
├── agent/tool_overrides.toml      # 20 new concise descriptions
├── agent/internal_tools.py        # leggi_risorsa (needs the tools client: executed by the loop)
├── agent/registry.py              # extra_tools (hook tools) appended as "internal"
├── agent/loop.py                  # hooks in AgentDeps; ended_by; replace_text as a write tool; inserted[].titolo
├── agent/state.py                 # DraftState, DocSession.draft, DocSession.reference
├── agent/recipes/draft.md         # the recipe (Italian), provenance header
├── document.py                    # replace_text on DocumentClient, FakeDocument, BridgeDocument; ReplaceResult
├── protocol.py                    # CommandName, ConsentSummary.scope/name
├── commands/templates.py          # TemplateCatalogue: list(query), info(tipo_atto, specs)
├── commands/draft.py              # start/answer/continue, base insertion, message builder, hooks, summary
├── main.py                        # routes; _send_turn_final(extra); set_reference
└── cli.py                         # templates, template, draft (--tipo/--campo/--note/--riferimento/--risposta)
core/tests/conftest.py             # fake: resource, more catalogue entries, atto_di_precetto with "testo"
core/tests/test_mcp_client.py, agent/test_profiles_registry.py, agent/test_loop.py, agent/test_prompt_state.py,
core/tests/test_document.py, commands/test_templates.py, commands/test_draft.py, test_main.py, test_cli.py,
core/tests/test_protocol.py, test_package.py
docs/superpowers/specs/2026-09-07-librelex-it-design.md (§5.3, §6.3, §6.9, §8.2, App. A, App. B), core/README.md
```

---

### Task 1: Complete allowlist and profile, catalogue resources

**Files:**
- Modify: `core/src/librelex_core/mcp/client.py`, `core/src/librelex_core/agent/profiles.py`, `core/src/librelex_core/agent/tool_overrides.toml`, `core/src/librelex_core/agent/internal_tools.py`, `core/src/librelex_core/agent/loop.py`, `core/tests/conftest.py`
- Test: `core/tests/test_mcp_client.py`, `core/tests/agent/test_profiles_registry.py`, `core/tests/agent/test_loop.py`

**Interfaces:**
- Produces: `profiles.ROUTING_GENERATORS: tuple[str, ...]` = `("attestazione_conformita", "atto_di_precetto", "decreto_ingiuntivo", "dichiarazione_553_cpc", "genera_dpa", "genera_dpia", "genera_informativa_cookie", "genera_informativa_dipendenti", "genera_informativa_privacy", "genera_informativa_videosorveglianza", "genera_notifica_data_breach", "genera_registro_trattamenti", "nota_precisazione_credito", "preventivo_civile", "preventivo_stragiudiziale", "preventivo_volontaria_giurisdizione", "procura_alle_liti", "relata_notifica_pec", "sfratto_morosita", "sollecito_pagamento")` (alphabetical, 20: every `routing.tool` of `modelli_atti.json` on 2026-09-19); `profiles.CATALOGUE_CALCULATORS: tuple[str, ...]` = `("calcolo_hash", "calcolo_tempo_trascorso", "calcolo_valore_catastale", "compenso_ctu", "conta_giorni", "contributo_unificato", "interessi_legali", "interessi_mora", "parcella_avvocato_civile", "pignoramento_stipendio", "rivalutazione_monetaria", "scadenza_processuale", "scadenze_impugnazioni", "spese_mediazione", "termini_processuali_civili", "valutazione_data_breach", "variazioni_istat")` (alphabetical, 17: the 15 names of every `tool_calcolo` plus the two of Appendix B the catalogue does not name); `GENERATORS` is removed (replaced by `ROUTING_GENERATORS`); `CALCULATORS` stays as the Appendix B eight and is used by `review`; `PROFILES["draft"] == Profile(("genera_modello_atto", "lista_categorie_atti", "cite_law", "fetch_act_index", "fetch_full_act", "verifica_citazioni") + ROUTING_GENERATORS + CATALOGUE_CALCULATORS, ("read_paragraphs", "insert_markdown", "replace_text"))` (the document tuple is completed in Task 2; here it is `("read_paragraphs", "insert_markdown")` and Task 2 adds `replace_text`); `PROFILES["review"]` unchanged in this task. `mcp.client.ALLOWLIST` = the 55 names (norms 5, case law 11, templates 2, `ROUTING_GENERATORS` 20, `CATALOGUE_CALCULATORS` 17). `LegalToolsClient.read_resource(uri: str) -> str` (text of the first content item; `ToolError("leggi_risorsa", ...)` on failure). Internal tool `leggi_risorsa(uri)` in `INTERNAL_TOOLS` with the description `"Legge una risorsa di mcp-legal-it (URI legal://...): catalogo dei modelli di atto e modelli pubblicati."`; the loop executes it with the tools client (`internal_tools.run_internal_tool` keeps raising `KeyError` for it: the loop handles it before, like `read_tool`), refusing any URI not starting with `legal://` with `ERRORE: URI non ammesso (solo legal://)` and answering `NO_LEGAL_TOOLS` when `tools is None`. The result is wrapped with `wrap_data("leggi_risorsa", text)` and does not ground.
- Fake server (`make_fake_legal_server`): a resource `legal://riferimenti/modelli-atti-catalogo` returning the text `"# Catalogo modelli atti (fake)\n\n- decreto_ingiuntivo_ordinario\n- atto_di_citazione\n- precetto_ordinario\n"`; a new catalogue entry `precetto_ordinario` (categoria `esecuzione`, descrizione `Atto di precetto su titolo esecutivo`, routing tool_diretto `atto_di_precetto` with `parametri_fissi {}`, campi_obbligatori `["creditore", "debitore", "titolo_esecutivo", "importo_capitale"]`, campi_opzionali `["interessi", "spese"]`, tool_calcolo `["interessi_legali"]`, riferimenti_normativi `["art. 480 c.p.c."]`, avvertenze `[]`); a fake tool `atto_di_precetto(creditore: str, debitore: str, titolo_esecutivo: str, importo_capitale: float, interessi: float = 0, spese: float = 0) -> dict` returning `{"testo": f"ATTO DI PRECETTO\n\n{creditore} intima a {debitore} il pagamento di Euro {importo_capitale:,.2f} in forza di {titolo_esecutivo}.\n\n[Luogo], [Data]\nAvv. [LEGALE]", "totale": importo_capitale + interessi + spese, "riferimento_normativo": "art. 480 c.p.c."}` recorded in `calls["generatori"]` as `("atto_di_precetto", creditore, debitore, importo_capitale)`.

- [ ] **Step 1: Failing tests**

`core/tests/test_mcp_client.py`: `len(ALLOWLIST) == 55`, `"genera_dpa" in ALLOWLIST`, `"variazioni_istat" in ALLOWLIST`; append:

```python
async def test_read_resource_returns_the_text_and_refuses_unknown_uris():
    server, _ = make_fake_legal_server()
    async with LegalToolsClient(server) as client:
        text = await client.read_resource("legal://riferimenti/modelli-atti-catalogo")
        assert text.startswith("# Catalogo modelli atti (fake)")
        with pytest.raises(ToolError):
            await client.read_resource("legal://riferimenti/inesistente")
```

`core/tests/agent/test_profiles_registry.py`, replace the draft assertions of `test_profiles_match_spec_6_3` with:

```python
    assert len(ROUTING_GENERATORS) == 20 and len(CATALOGUE_CALCULATORS) == 17
    assert ROUTING_GENERATORS == tuple(sorted(ROUTING_GENERATORS))
    assert CATALOGUE_CALCULATORS == tuple(sorted(CATALOGUE_CALCULATORS))
    assert set(CALCULATORS) <= set(CATALOGUE_CALCULATORS)
    assert PROFILES["draft"].legal == (
        "genera_modello_atto", "lista_categorie_atti", "cite_law", "fetch_act_index",
        "fetch_full_act", "verifica_citazioni") + ROUTING_GENERATORS + CATALOGUE_CALCULATORS
    assert set(PROFILES["draft"].legal) <= ALLOWLIST
    assert len(ALLOWLIST) == 55
```

and a new test pinning the catalogue names (the copy the design's §8 asks for):

```python
# Every routing tool and every tool_calcolo of modelli_atti.json (mcp-legal-it, 2026-09-19).
CATALOGUE_ROUTING_TOOLS = {
    "attestazione_conformita", "atto_di_precetto", "decreto_ingiuntivo", "dichiarazione_553_cpc",
    "genera_dpa", "genera_dpia", "genera_informativa_cookie", "genera_informativa_dipendenti",
    "genera_informativa_privacy", "genera_informativa_videosorveglianza",
    "genera_notifica_data_breach", "genera_registro_trattamenti", "nota_precisazione_credito",
    "preventivo_civile", "preventivo_stragiudiziale", "preventivo_volontaria_giurisdizione",
    "procura_alle_liti", "relata_notifica_pec", "sfratto_morosita", "sollecito_pagamento"}
CATALOGUE_TOOL_CALCOLO = {
    "calcolo_hash", "calcolo_valore_catastale", "compenso_ctu", "conta_giorni",
    "contributo_unificato", "interessi_legali", "interessi_mora", "parcella_avvocato_civile",
    "pignoramento_stipendio", "rivalutazione_monetaria", "scadenza_processuale",
    "scadenze_impugnazioni", "spese_mediazione", "valutazione_data_breach", "variazioni_istat"}


def test_draft_profile_covers_every_tool_the_catalogue_names():
    legal = set(PROFILES["draft"].legal)
    assert CATALOGUE_ROUTING_TOOLS <= legal and CATALOGUE_TOOL_CALCOLO <= legal
    assert GROUNDING_SOURCES == frozenset(NORM_SOURCES + CASE_LAW)     # unchanged by the growth
```

`test_overrides_cover_the_allowlist_and_are_concise` stays and fails until the 20 descriptions exist. `test_internal_tools` (same file) gains `assert "leggi_risorsa" in names` where `names` is the set of internal tool names.

`core/tests/agent/test_loop.py`, append:

```python
async def test_leggi_risorsa_reads_a_catalogue_resource_and_refuses_other_schemes():
    server, _ = make_fake_legal_server()
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([
            tool_turn(("leggi_risorsa", {"uri": "legal://riferimenti/modelli-atti-catalogo"}),
                      ("leggi_risorsa", {"uri": "file:///etc/passwd"})),
            text_turn("letto")])
        outcome, events, session = await _run(llm, FakeDocument(["x"]), tools, "draft")
    tool_msgs = [m for m in llm.calls[1][0] if m.get("role") == "tool"]
    assert "<<<DATI: leggi_risorsa>>>" in tool_msgs[0]["content"]
    assert "# Catalogo modelli atti (fake)" in tool_msgs[0]["content"]
    assert tool_msgs[1]["content"] == "ERRORE: URI non ammesso (solo legal://)"
    assert outcome.tool_calls == 2
```

Run: `cd core && uv run pytest tests/test_mcp_client.py tests/agent/test_profiles_registry.py tests/agent/test_loop.py -q` → failures (`ImportError` on `ROUTING_GENERATORS`, 35 ≠ 55, no `read_resource`, `leggi_risorsa` unknown).

- [ ] **Step 2: Implement**

`profiles.py`: the two tuples above with a comment naming the JSON and the date; `GENERATORS` removed and every reference to it updated (`grep -rn GENERATORS core/`); draft profile as in Interfaces.

`mcp/client.py`: `ALLOWLIST` rebuilt as `frozenset(NORMS + CASE_LAW_TOOLS + TEMPLATES + ROUTING_GENERATORS + CATALOGUE_CALCULATORS)` where the first three are module tuples (5, 11, 2 names; import `ROUTING_GENERATORS`/`CATALOGUE_CALCULATORS` from `profiles`? No: `profiles` imports `client.ALLOWLIST`, so define the tuples in `client.py` and have `profiles.py` import them from there: `from librelex_core.mcp.client import ALLOWLIST, CATALOGUE_CALCULATORS, ROUTING_GENERATORS`). Add:

```python
    async def read_resource(self, uri: str) -> str:
        """Text of an MCP resource of the server; failures become ToolError."""
        if self._client is None:
            raise RuntimeError("LegalToolsClient used outside 'async with'")
        try:
            contents = await self._client.read_resource(uri)
        except Exception as e:
            raise ToolError("leggi_risorsa", str(e)) from e
        for item in contents:
            text = getattr(item, "text", None)
            if isinstance(text, str):
                return text
        raise ToolError("leggi_risorsa", f"risorsa senza testo: {uri}")
```

`tool_overrides.toml`: 20 entries (read the real signatures in `plugin/server/src/tools/{privacy_gdpr,fatturazione_avvocati,atti_giudiziari}.py`); one line each, Italian, naming the parameters, e.g. `genera_informativa_privacy = "Bozza di informativa privacy ex art. 13 GDPR (titolare, finalità, basi giuridiche, destinatari, conservazione, diritti)."`, `preventivo_civile = "Preventivo dei costi di una causa civile per valore e fasi (D.M. 55/2014, contributo unificato)."`, `variazioni_istat = "Variazioni percentuali dell'indice ISTAT FOI tra due mesi."`.

`internal_tools.py`: append the `leggi_risorsa` entry to `INTERNAL_TOOLS` (parameters `{"uri": {"type": "string"}}`, required `["uri"]`); `run_internal_tool` unchanged (raises `KeyError` for it).

`loop.py`, in `execute`, before `run_internal_tool`:

```python
            if call.name == "leggi_risorsa":
                return await resource_tool(str(args.get("uri", "")))
```

with, next to `legal_tool`:

```python
    async def resource_tool(uri: str) -> str:
        if not uri.startswith("legal://"):
            return "ERRORE: URI non ammesso (solo legal://)"
        if tools is None:
            return NO_LEGAL_TOOLS
        await emit(p.Status(request_id=request_id, text=f"Leggo la risorsa {uri}"))
        try:
            text = await tools.read_resource(uri)
        except ToolError as e:
            return f"ERRORE: {e.message}"
        return wrap_data("leggi_risorsa", text)
```

`conftest.py`: the resource (`@server.resource("legal://riferimenti/modelli-atti-catalogo")` returning the string), the `precetto_ordinario` entry in `_CATALOGO`, the `atto_di_precetto` fake tool.

- [ ] **Step 3: Run and commit**

`cd core && uv run ruff check . && uv run pytest -q` → green.

```bash
git add core
git commit -m "feat(core): draft profile covers every tool the act catalogue names; leggi_risorsa reads legal:// resources" -m "Allowlist 35 to 55 (20 routing generators, 17 calculators). LegalToolsClient.read_resource." -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: `replace_text` document action

**Files:**
- Modify: `core/src/librelex_core/document.py`, `core/src/librelex_core/agent/registry.py`, `core/src/librelex_core/agent/loop.py`, `core/src/librelex_core/agent/profiles.py`
- Test: `core/tests/test_document.py`, `core/tests/agent/test_loop.py`, `core/tests/agent/test_profiles_registry.py`

**Interfaces:**
- Produces: `document.ReplaceResult(BaseModel)` with `count: int` and `anchors: list[Anchor]`; `DocumentClient.replace_text(query: str, replacement: str, undo_label: str, paragraph_id: str | None = None, all: bool = False) -> ReplaceResult`; `FakeDocument.replace_text` (replaces the first occurrence, or all, in the body paragraphs; records `{"where": "replace", "query", "replacement", "undo_label"}` in `self.inserts`); `BridgeDocument.replace_text` (`doc_call` action `replace_text` with args `query`, `replacement`, `undo_label`, `paragraph_id`, `all`; result `{"count": int, "anchors": [...]}`); `registry.DOCUMENT_TOOLS["replace_text"]` (parameters `query`, `replacement`, `paragraph_id` nullable, `all` boolean default false; description: `"Sostituisce nel documento la prima occorrenza (o tutte, con all=true) di un testo esatto con un altro, come modifica tracciata: serve a riempire i segnaposto tra parentesi quadre della base inserita. Le citazioni nuove nel testo sostitutivo vengono verificate prima (grounding)."`); loop: `WRITE_TOOLS` gains `replace_text`, handled in `write_tool` with grounding on `replacement` and `comment_problems` over `InsertedRange(from_id=anchors[0].paragraph_id, to_id=anchors[-1].paragraph_id)` when `count > 0`; the tool result is `"Sostituite N occorrenze di «query»."` (or `"Nessuna occorrenza di «query»."` with count 0, no grounding call needed then: verify only when `count > 0`? No: verify before writing, as for every write; the order stays verify → write → comment); `PROFILES["draft"].document == ("read_paragraphs", "insert_markdown", "replace_text")` and `PROFILES["review"].document == ("read_selection", "replace_selection", "add_comment", "replace_text")`; `ALL_DOCUMENT` gains `replace_text` (chat sees it too).
- Extension side is Plan 2 (adapter `replace_text` as tracked deletion + insertion); the protocol shape above is the contract Plan 2 implements.

- [ ] **Step 1: Failing tests**

`core/tests/test_document.py`, append:

```python
async def test_fake_replace_text_first_or_all_with_anchors():
    doc = FakeDocument(["Il [SEDE] e ancora [SEDE].", "Avv. [LEGALE]"])
    out = await doc.replace_text("[SEDE]", "Tribunale di Milano", "LibreLex: test")
    assert out.count == 1 and out.anchors[0].paragraph_id == "p:0" and out.anchors[0].start == 3
    assert (await doc.read_paragraphs())[0].text == "Il Tribunale di Milano e ancora [SEDE]."
    out = await doc.replace_text("[SEDE]", "Tribunale di Milano", "LibreLex: test", all=True)
    assert out.count == 1
    assert (await doc.replace_text("[NIENTE]", "x", "u")).count == 0
    assert doc.inserts[-1]["where"] == "replace"


async def test_bridge_replace_text_wire_shape():
    sent = []

    async def send(msg):
        sent.append(msg)

    doc = BridgeDocument(send, "r1", timeout_s=1)
    task = asyncio.create_task(doc.replace_text("[SEDE]", "Roma", "u", paragraph_id="p:0"))
    await asyncio.sleep(0)
    call = sent[0]
    assert call.action == "replace_text" and call.args == {
        "query": "[SEDE]", "replacement": "Roma", "undo_label": "u", "paragraph_id": "p:0",
        "all": False}
    doc.resolve(p.DocResult(id="r1", call_id=call.call_id, ok=True, result={
        "count": 1, "anchors": [{"paragraph_id": "p:0", "start": 0, "end": 4}]}))
    out = await task
    assert out.count == 1 and out.anchors[0].end == 4
```

(the file already imports `asyncio`, `p`, `BridgeDocument`; add what is missing.)

`core/tests/agent/test_loop.py`, append:

```python
async def test_replace_text_is_a_grounded_write():
    server, calls = make_fake_legal_server(
        verdicts={"Cass. n. 99999/2024": ("inesistente", "nessuna decisione")})
    doc = FakeDocument(["Come da [PRECEDENTE], si chiede."])
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([
            tool_turn(("replace_text", {"query": "[PRECEDENTE]",
                                        "replacement": "Cass. n. 99999/2024"})),
            text_turn("fatto")])
        outcome, events, session = await _run(llm, doc, tools, "draft")
    assert calls["verifica"] == [["Cass. n. 99999/2024"]]
    assert outcome.flagged == ["Cass. n. 99999/2024"] and len(doc.comments) == 1
    assert (await doc.read_paragraphs())[0].text == "Come da Cass. n. 99999/2024, si chiede."
    tool_msg = [m for m in llm.calls[1][0] if m.get("role") == "tool"][0]["content"]
    assert tool_msg.startswith("Sostituite 1 occorrenze di «[PRECEDENTE]».")
    assert "Riferimenti segnalati con un commento: Cass. n. 99999/2024" in tool_msg
```

`test_profiles_registry.py`: `test_document_tools_mirror_the_actions` gains `"replace_text"` in the expected set; the draft/review document tuples as in Interfaces.

Run: the three files → failures.

- [ ] **Step 2: Implement**

`document.py`:

```python
class ReplaceResult(BaseModel):
    count: int
    anchors: list[Anchor] = Field(default_factory=list)
```

(`from pydantic import BaseModel, Field`); the protocol method; `FakeDocument`:

```python
    async def replace_text(self, query: str, replacement: str, undo_label: str,
                           paragraph_id: str | None = None, all: bool = False) -> ReplaceResult:
        anchors: list[Anchor] = []
        indices = ([int(paragraph_id.split(":")[1])] if paragraph_id
                   else range(len(self._paragraphs)))
        for i in indices:
            text = self._paragraphs[i]
            start = text.find(query)
            while start != -1 and query:
                anchors.append(Anchor(paragraph_id=f"p:{i}", start=start,
                                      end=start + len(replacement)))
                text = text[:start] + replacement + text[start + len(query):]
                if not all:
                    break
                start = text.find(query, start + len(replacement))
            self._paragraphs[i] = text
            if anchors and not all:
                break
        self.inserts.append({"where": "replace", "query": query, "replacement": replacement,
                             "undo_label": undo_label, "bookmark": None, "author": None})
        return ReplaceResult(count=len(anchors), anchors=anchors)
```

`BridgeDocument.replace_text`: `ReplaceResult.model_validate(await self._call("replace_text", query=query, replacement=replacement, undo_label=undo_label, paragraph_id=paragraph_id, all=all))`.

`registry.py`: the `DOCUMENT_TOOLS["replace_text"]` entry. `loop.py`: in `write_tool`, branch on the name:

```python
        text_to_ground = markdown if name != "replace_text" else str(args.get("replacement", ""))
        refs = grounding.unseen(text_to_ground)
        ...
        if name == "insert_markdown":
            inserted = await doc.insert_markdown(...)
        elif name == "replace_text":
            replaced = await doc.replace_text(
                str(args.get("query", "")), text_to_ground, undo_label,
                paragraph_id=args.get("paragraph_id"), all=bool(args.get("all", False)))
            if replaced.count == 0:
                return f"Nessuna occorrenza di «{args.get('query', '')}»."
            inserted = InsertedRange(from_id=replaced.anchors[0].paragraph_id,
                                     to_id=replaced.anchors[-1].paragraph_id)
        else:
            inserted = await doc.replace_selection(markdown, undo_label)
```

and the content line `f"Sostituite {replaced.count} occorrenze di «{query}»."` for `replace_text` (the flagged/unverified suffixes as for inserts). `outcome.inserted` is not appended for `replace_text` (it is not a partition); a new `outcome.replaced: int` counts the occurrences. `profiles.py`: the document tuples.

- [ ] **Step 3: Run and commit**

`cd core && uv run ruff check . && uv run pytest -q` → green.

```bash
git add core
git commit -m "feat(core): replace_text document action, a grounded tracked replacement for placeholders" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Recipe, drafting state, protocol, catalogue commands

**Files:**
- Create: `core/src/librelex_core/agent/recipes/draft.md`, `core/src/librelex_core/commands/templates.py`
- Modify: `core/src/librelex_core/agent/state.py`, `core/src/librelex_core/protocol.py`, `core/src/librelex_core/main.py`
- Test: `core/tests/agent/test_prompt_state.py`, `core/tests/test_protocol.py`, `core/tests/commands/test_templates.py`, `core/tests/test_main.py`

**Interfaces:**
- Produces: `state.DraftState` dataclass (`tipo_atto: str`, `template: dict`, `fields: dict[str, str]`, `notes: str = ""`, `answers: dict[str, str] = {}`, `base: dict | None = None` (`{"from_id", "to_id", "placeholders": [str], "tool": str, "result": dict}`), `partitions: list[dict] = []` (`{"titolo", "from_id", "to_id"}`), `questions: list[dict] = []`, `done: bool = False`, `riepilogo: str = ""`); `DocSession.draft: DraftState | None = None`; `DocSession.reference: dict | None = None` (`{"name", "chars", "text", "troncato"}`); `DocSession.reference_consented: bool = False`.
- `protocol.CommandName` gains `"list_templates"`, `"template_info"`, `"set_reference"`; `ConsentSummary.scope: Literal["selection", "paragraphs", "reference"]` and `name: str | None = None`.
- `commands/templates.py`: `class TemplateCatalogue` built with `LegalToolsClient`: `async list(query: str | None = None) -> dict` returning `{"modelli": [{"tipo_atto", "descrizione", "categoria", "tier"}], "totale": int, "query": query}` (catalogue order flattened by category, category order as the server gives it; the `catalogo` result cached for the process, `cerca` results not cached); `async info(tipo_atto: str, specs: list[ToolSpec]) -> dict` returning `{"tipo_atto", "descrizione", "categoria", "campi_obbligatori", "campi_opzionali", "tool_calcolo", "riferimenti_normativi", "avvertenze", "istruzioni", "routing": {"tipo": "tool_diretto"|"resource"|"tool_enhance"|"preventivo_procedura"|"sconosciuto", "tool": str | None, "parametri_fissi": dict, "resource": str | None}, "campi": [{"nome", "tipo": "testo"|"numero"|"data"|"sino", "obbligatorio": bool, "descrizione": str}]}` (cached per `tipo_atto`); `class TemplateNotFound(Exception)` when the lookup result carries `errore` (message: the server's `errore` plus `; suggerimenti: a, b` when present). Field typing: for a direct tool present in `specs`, the schema of its parameter of that name decides (`integer`/`number` → `numero`, `boolean` → `sino`, a name containing `data` → `data`, else `testo`; `descrizione` = the schema's `description` first 120 chars, else `""`); fields without a schema are `testo`. Mandatory fields first, then optional.
- `main.py`: `list_templates` and `template_info` routed like the other `NEEDS_TOOLS` commands (`NEEDS_TOOLS` gains both), through one `TemplateCatalogue` kept on the server (`self._templates`, created with the tools client at first use); the `Final` text is `"Catalogo: N modelli."` / `"Modello <tipo_atto>: K campi."` and the summary is the dict above; `TemplateNotFound` → `Error(code="template_not_found")`. `set_reference` (no tools): `args.text` non-empty → `session.reference = {"name": args.get("name") or "atto di riferimento", "chars": len(text), "text": text[:MAX_REFERENCE_CHARS], "troncato": len(text) > MAX_REFERENCE_CHARS}`, `session.reference_consented = False`, `Final(text="Atto di riferimento: <name> (<chars> caratteri).", summary={"riferimento": {name, chars, troncato}})`; empty `text` clears it (`Final(text="Atto di riferimento rimosso.", summary={"riferimento": None})`). The reference text never appears in a `Status`, `Log` or error message.
- The recipe: `agent/recipes/draft.md`, loaded once by `commands/draft.py` (Task 4) through `load_recipe() -> str` defined in `agent/prompt.py` (reads the file next to `prompt.py` under `recipes/`, strips the HTML comment header). Content (Italian; the header comment in English):

```markdown
<!-- Derived from mcp-legal-it plugin/skills/genera-atto/SKILL.md and plugin/agents/redattore-atti.md
     (worktree json-output-and-entrypoint, 2026-09-19). Adapted to Writer: the act goes into the
     document one partition per insertion; calculations, verified references, attachments checklist
     and warnings are reported in the panel. Keep the rules in sync with the plugin. -->
# Ricetta di redazione (stessa procedura della skill genera-atto)

## Regole fondamentali
1. CATALOGO: il modello d'atto ti è già stato fornito nei dati di questo messaggio (struttura, campi, strumenti di calcolo, riferimenti normativi, avvertenze): non ridefinirlo, seguilo.
2. ANCORAGGIO: prima di citare qualsiasi norma nel testo dell'atto chiama `cite_law` sul riferimento; le sentenze solo dopo averle lette con uno strumento `leggi_*`.
3. CALCOLI: gli importi (contributo unificato, interessi, rivalutazione, compensi, scadenze) si calcolano sempre con gli strumenti indicati in `tool_calcolo`, mai a mano; riporta nell'atto i risultati e la data del calcolo.
4. COMPLETEZZA: non generare l'atto finché mancano campi obbligatori; chiedili con `chiedi_dati`.
5. FORMULE LEGALI: usa le formule esatte dei generatori e dei modelli, non parafrasarle; se una base deterministica è già nel documento non riscriverla.
6. RISERVATEZZA: se è disponibile un atto di riferimento (caso simile), leggilo con `leggi_atto_riferimento` e prendine struttura, titoli, stile, formule e argomentazioni; non riusare mai i suoi fatti, nomi, importi, date o estremi di causa, e verifica con `cite_law` ogni norma che ne ricavi.

## Procedura
1. Dati: hai già il modello d'atto, i campi compilati dall'utente, le note e, se presente, la base inserita con i suoi segnaposto. Leggi il documento con `read_paragraphs` solo se devi vedere testo già presente (partizioni inserite in un turno precedente, dati scritti dall'avvocato).
2. Domande: se manca un campo obbligatorio o un dato necessario ai calcoli o alle premesse in fatto, chiama `chiedi_dati` una sola volta con tutte le domande (al massimo otto, ciascuna con `campo`, `domanda`, `esempio` e `tipo`), poi fermati: le risposte arrivano nel turno successivo. Non chiedere ciò che i campi, le note o l'atto di riferimento già dicono.
3. Calcoli: chiama ogni strumento di `tool_calcolo` con i dati raccolti.
4. Base: se il documento contiene già la base deterministica, riempi i segnaposto con `replace_text` (uno per chiamata, testo esatto tra parentesi quadre) e poi inserisci le partizioni narrative che mancano con `insert_markdown` (`where="end"`, oppure `after:<id>` per collocarle dopo un paragrafo della base). Se non c'è una base, componi l'atto seguendo la struttura del modello, una partizione per chiamata: intestazione e parti; premesse in fatto; motivi in diritto; conclusioni con le somme calcolate; documenti allegati.
5. Norme: ogni norma nel testo passa da `cite_law` prima di essere citata; la verifica automatica all'inserimento segnala con un commento ciò che non risulta.
6. Chiusura: quando l'atto è completo chiama `redazione_completata` con un riepilogo in testo semplice (senza markdown) in quattro parti: tabella dei calcoli eseguiti (strumento, dati, risultato), riferimenti normativi verificati, elenco degli allegati necessari, avvertenze del modello e ciò che resta da completare a mano. Poi rispondi in chat con due righe.

## Stile
Registro forense, formule complete, nessun asterisco o markdown nelle risposte in chat; nel documento usa titoli per le partizioni ed elenchi numerati per motivi e allegati; lascia tra parentesi quadre ciò che nessuno ti ha fornito.
```

- [ ] **Step 1: Failing tests**

`core/tests/agent/test_prompt_state.py`, append:

```python
def test_recipe_loads_with_the_seven_rules_and_no_header():
    from librelex_core.agent.prompt import load_recipe
    text = load_recipe()
    assert text.startswith("# Ricetta di redazione")
    assert "<!--" not in text
    for needle in ("CATALOGO", "ANCORAGGIO", "CALCOLI", "COMPLETEZZA", "FORMULE LEGALI",
                   "RISERVATEZZA", "chiedi_dati", "replace_text", "redazione_completata",
                   "leggi_atto_riferimento", "senza markdown"):
        assert needle in text, needle
    assert load_recipe() is load_recipe()          # cached: byte-stable across turns


def test_draft_state_and_reference_live_on_the_session():
    from librelex_core.agent.state import DraftState
    s = DocSession("d1")
    assert s.draft is None and s.reference is None and s.reference_consented is False
    s.draft = DraftState(tipo_atto="x", template={"campi_obbligatori": []}, fields={"a": "1"})
    assert s.draft.answers == {} and s.draft.partitions == [] and s.draft.done is False
```

`core/tests/test_protocol.py`, append:

```python
def test_new_commands_and_reference_consent_scope():
    for name in ("list_templates", "template_info", "set_reference"):
        p.parse_extension_line(json.dumps({"type": "command", "id": "r", "doc_id": "d",
                                           "name": name, "args": {}}))
    s = p.ConsentSummary(scope="reference", chars=10, endpoint_host="h", model="m", zdr=True,
                         name="ricorso.docx")
    assert json.loads(p.dump_line(p.ConsentRequest(request_id="r", call_id="k", summary=s)))[
        "summary"]["name"] == "ricorso.docx"
    assert p.ConsentSummary(scope="selection", chars=1, endpoint_host="h", model="m",
                            zdr=False).name is None
```

`core/tests/commands/test_templates.py` (new):

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_core.commands.templates import TemplateCatalogue, TemplateNotFound
from librelex_core.mcp.client import LegalToolsClient
from tests.conftest import make_fake_legal_server


async def test_list_flattens_the_catalogue_and_searches():
    server, calls = make_fake_legal_server()
    async with LegalToolsClient(server) as tools:
        cat = TemplateCatalogue(tools)
        out = await cat.list()
        assert out["totale"] == 3 and [m["tipo_atto"] for m in out["modelli"]] == [
            "decreto_ingiuntivo_ordinario", "atto_di_citazione", "precetto_ordinario"]
        assert out["modelli"][0]["categoria"] == "atti_introduttivi"
        await cat.list()                                    # cached
        assert calls["modelli"].count(("catalogo", {})) == 1
        hits = await cat.list("precetto")
        assert [m["tipo_atto"] for m in hits["modelli"]] == ["precetto_ordinario"]
        assert hits["query"] == "precetto"


async def test_info_types_the_fields_from_the_direct_tool_schema():
    server, _ = make_fake_legal_server()
    async with LegalToolsClient(server) as tools:
        cat = TemplateCatalogue(tools)
        info = await cat.info("decreto_ingiuntivo_ordinario", await tools.tool_specs())
        assert info["routing"] == {"tipo": "tool_diretto", "tool": "decreto_ingiuntivo",
                                   "parametri_fissi": {"tipo_credito": "ordinario"},
                                   "resource": None}
        campi = {c["nome"]: c for c in info["campi"]}
        assert [c["nome"] for c in info["campi"]] == ["creditore", "debitore", "importo",
                                                      "provvisoria_esecuzione"]
        assert campi["importo"]["tipo"] == "numero" and campi["importo"]["obbligatorio"] is True
        assert campi["provvisoria_esecuzione"]["tipo"] == "sino"
        assert campi["provvisoria_esecuzione"]["obbligatorio"] is False
        assert info["tool_calcolo"] == ["contributo_unificato", "parcella_avvocato_civile"]
        res = await cat.info("atto_di_citazione", await tools.tool_specs())
        assert res["routing"]["tipo"] == "resource" and res["routing"]["resource"] == (
            "atti://citazione")
        assert all(c["tipo"] == "testo" for c in res["campi"])
        with pytest.raises(TemplateNotFound, match="non trovato"):
            await cat.info("inesistente", [])
```

`core/tests/test_main.py`, append:

```python
async def test_template_commands_and_set_reference():
    h = Harness(FakeDocument(["x"]))

    async def scenario(h: Harness):
        await h.send(HELLO)
        await h.pump(p.HelloOk)
        await h.send(p.Command(id="r1", doc_id="d1", name="list_templates"))
        await h.pump(p.Final)
        assert h.received[-1].summary["totale"] == 3 and h.received[-1].text == "Catalogo: 3 modelli."
        await h.send(p.Command(id="r2", doc_id="d1", name="template_info",
                               args={"tipo_atto": "precetto_ordinario"}))
        await h.pump(p.Final)
        assert h.received[-1].summary["routing"]["tool"] == "atto_di_precetto"
        assert h.received[-1].text == "Modello precetto_ordinario: 6 campi."
        await h.send(p.Command(id="r3", doc_id="d1", name="template_info",
                               args={"tipo_atto": "boh"}))
        await h.pump(p.Error)
        assert h.received[-1].code == "template_not_found"
        await h.send(p.Command(id="r4", doc_id="d1", name="set_reference",
                               args={"name": "ricorso_rossi.docx", "text": "RICORSO " * 10}))
        await h.pump(p.Final)
        assert h.received[-1].summary["riferimento"] == {
            "name": "ricorso_rossi.docx", "chars": 80, "troncato": False}
        session = h.server._session("d1")
        assert session.reference["text"].startswith("RICORSO ")
        await h.send(p.Command(id="r5", doc_id="d1", name="set_reference", args={"text": ""}))
        await h.pump(p.Final)
        assert session.reference is None and h.received[-1].summary == {"riferimento": None}

    await h.run(scenario)
```

Run the four files → failures.

- [ ] **Step 2: Implement**

`state.py`: `DraftState` and the three session fields as in Interfaces. `protocol.py`: the literal and the two `ConsentSummary` changes. `agent/prompt.py`:

```python
_RECIPES = Path(__file__).with_name("recipes")


@functools.cache
def load_recipe(name: str = "draft") -> str:
    """The drafting recipe (Italian), cached so every turn sends the same bytes."""
    text = (_RECIPES / f"{name}.md").read_text(encoding="utf-8")
    return re.sub(r"^<!--.*?-->\s*", "", text, count=1, flags=re.S)
```

(`import functools, re`; `from pathlib import Path`). Add `recipes/draft.md` with the content above (packaging: hatchling ships every file under the package; `scripts/build_oxt.py` now ships every file under `core/src`, verified by `extension/tests/test_build_oxt.py`).

`commands/templates.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Catalogue of act templates from mcp-legal-it (design §4.1): what the Redazione panel shows
before any model turn. Deterministic, no LLM."""
from __future__ import annotations

import json
from typing import Any

from librelex_core.mcp.client import LegalToolsClient, ToolSpec

FIELD_TYPES = ("testo", "numero", "data", "sino")


class TemplateNotFound(Exception):
    """The catalogue has no such tipo_atto (the server's message and suggestions)."""


def field_type(name: str, schema: dict | None) -> str:
    if schema:
        t = schema.get("type")
        types = t if isinstance(t, list) else [t]
        if "boolean" in types:
            return "sino"
        if "integer" in types or "number" in types:
            return "numero"
    return "data" if "data" in name.lower() else "testo"


class TemplateCatalogue:
    def __init__(self, tools: LegalToolsClient):
        self._tools = tools
        self._catalogue: dict | None = None
        self._info: dict[str, dict] = {}

    async def _lookup(self, tipo_atto: str, parametri: dict | None = None) -> dict:
        text = await self._tools.call("genera_modello_atto", tipo_atto=tipo_atto,
                                      parametri=parametri or {})
        return json.loads(text)

    async def list(self, query: str | None = None) -> dict:
        if query:
            data = await self._lookup("cerca", {"query": query})
            hits = [{"tipo_atto": r["tipo_atto"], "descrizione": r["descrizione"],
                     "categoria": r.get("categoria", ""), "tier": r.get("tier", 0)}
                    for r in data.get("risultati", [])]
            return {"modelli": hits, "totale": len(hits), "query": query}
        if self._catalogue is None:
            data = await self._lookup("catalogo")
            models = [{"tipo_atto": e["tipo_atto"], "descrizione": e["descrizione"],
                       "categoria": cat, "tier": e.get("tier", 0)}
                      for cat, entries in data.get("catalogo", {}).items() for e in entries]
            self._catalogue = {"modelli": models, "totale": len(models), "query": None}
        return self._catalogue

    async def info(self, tipo_atto: str, specs: list[ToolSpec]) -> dict:
        if tipo_atto in self._info:
            return self._info[tipo_atto]
        data = await self._lookup(tipo_atto)
        if data.get("errore"):
            hint = data.get("suggerimenti") or []
            names = ", ".join(s.get("tipo_atto", "") for s in hint if isinstance(s, dict))
            raise TemplateNotFound(data["errore"] + (f"; suggerimenti: {names}" if names else ""))
        routing = _routing(data)
        schema_props: dict[str, Any] = {}
        if routing["tool"]:
            spec = next((s for s in specs if s.name == routing["tool"]), None)
            schema_props = (spec.input_schema.get("properties") or {}) if spec else {}
        campi = [_field(n, True, schema_props) for n in data.get("campi_obbligatori", [])]
        campi += [_field(n, False, schema_props) for n in data.get("campi_opzionali", [])]
        info = {
            "tipo_atto": tipo_atto, "descrizione": data.get("descrizione", ""),
            "categoria": data.get("categoria", ""),
            "campi_obbligatori": list(data.get("campi_obbligatori", [])),
            "campi_opzionali": list(data.get("campi_opzionali", [])),
            "tool_calcolo": list(data.get("tool_calcolo", [])),
            "riferimenti_normativi": list(data.get("riferimenti_normativi", [])),
            "avvertenze": list(data.get("avvertenze", [])),
            "istruzioni": data.get("istruzioni", ""), "routing": routing, "campi": campi,
        }
        self._info[tipo_atto] = info
        return info


def _routing(data: dict) -> dict:
    if data.get("tool_diretto"):
        tipo = "tool_diretto" if "resource_modello" not in data else "tool_enhance"
        if data.get("tool_non_ancora_disponibile"):
            tipo = "preventivo_procedura"
        return {"tipo": tipo, "tool": data["tool_diretto"],
                "parametri_fissi": dict(data.get("parametri_fissi") or {}), "resource": None}
    if data.get("resource_modello"):
        return {"tipo": "resource", "tool": None, "parametri_fissi": {},
                "resource": data["resource_modello"]}
    return {"tipo": "sconosciuto", "tool": None, "parametri_fissi": {}, "resource": None}


def _field(name: str, mandatory: bool, props: dict) -> dict:
    schema = props.get(name)
    desc = (schema or {}).get("description") or ""
    return {"nome": name, "tipo": field_type(name, schema), "obbligatorio": mandatory,
            "descrizione": desc[:120]}
```

(check the real server's `tool_enhance` result: it carries `tool_diretto` and `disponibile_da_fase` but no `resource_modello`; refine `_routing` to use `disponibile_da_fase` presence together with `tool_diretto` for `tool_enhance`; the fake only has `tool_diretto` and `resource`, so add a fake entry only if you need it for a test.)

`main.py`: `NEEDS_TOOLS = ("verify_citations", "insert_norm", "show_text", "list_templates", "template_info")`; `self._templates: TemplateCatalogue | None`; in `_command_body`, after the tools are obtained: `list_templates` → `out = await self._catalogue(tools).list(msg.args.get("query"))`, `Final(text=f"Catalogo: {out['totale']} modelli.", summary=out)`; `template_info` → `try: info = await ...info(str(msg.args.get("tipo_atto") or ""), await tools.tool_specs()) except TemplateNotFound as e: Error(code="template_not_found", message=str(e))`, `Final(text=f"Modello {info['tipo_atto']}: {len(info['campi'])} campi.", summary=info)`; `set_reference` before the tools block (no server needed) as in Interfaces (`MAX_REFERENCE_CHARS = 60_000` defined in `commands/draft.py` in Task 4; define it in `agent/state.py` now and import it).

- [ ] **Step 3: Run and commit**

`cd core && uv run ruff check . && uv run pytest -q` → green.

```bash
git add core
git commit -m "feat(core): drafting recipe from the plugin, DraftState, catalogue commands list_templates and template_info, set_reference" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: The stateful `draft` command: base insertion, hooks, questions, completion, reference

**Files:**
- Modify: `core/src/librelex_core/agent/loop.py`, `core/src/librelex_core/agent/registry.py`, `core/src/librelex_core/commands/draft.py`, `core/src/librelex_core/main.py`
- Test: `core/tests/agent/test_loop.py`, `core/tests/commands/test_draft.py` (rewritten), `core/tests/test_main.py`

**Interfaces:**
- Loop hooks: `AgentDeps.hooks: dict[str, Hook] = field(default_factory=dict)` where `Hook = Callable[[dict], Awaitable[tuple[str, str | None]]]` (returns the tool result text and an optional stop reason); `AgentDeps.hook_tools: list[dict] = field(default_factory=list)` (their OpenAI tool objects, passed to `ToolRegistry(specs, profile, extra_tools=...)`, appended after the internal tools, kind `"internal"`, sorted by name with them). In `execute`, a name in `hooks` runs the hook (before the `run_internal_tool` fallback); a non-`None` stop reason sets `stop_reason` and, after `run_tool_calls`, the loop breaks with `outcome.ended_by = stop_reason` (a new `TurnOutcome.ended_by: str | None = None`; `stopped` stays for interruptions). `TurnOutcome.inserted` entries gain `"titolo"`: the first markdown heading of the inserted text (`# `/`## ` prefix stripped), else the first non-empty line trimmed to 60 characters. `run_turn_with` passes `deps.hooks`.
- `commands/draft.py` (rewritten):
  - `MAX_REFERENCE_CHARS` lives in `agent/state.py` (Task 3); `PROFILE = "draft"`; `undo_label(tipo_atto) -> f"LibreLex: redazione {tipo_atto}"`; `BASE_UNDO = "LibreLex: base {tipo_atto}"`; `BASE_BOOKMARK = "LibreLex.atto.{tipo_atto}"`.
  - `PLACEHOLDER_RE = re.compile(r"\[[^\[\]\n]{1,60}\]|\{[a-z_]+\}")`; `placeholders(text) -> list[str]` (unique, in order).
  - `base_text(result: dict) -> str | None`: `result["testo"]` if a non-empty string, else the first key starting with `bozza` whose value is a non-empty string, else `None`.
  - `to_markdown(text) -> str`: `re.sub(r"\n{2,}", "\n\n", re.sub(r"(?<!\n)\n(?!\n)", "\n\n", text.strip()))` (every line becomes a paragraph), then lines that start with a digit followed by `.` keep working as ordered lists.
  - `coerce_args(fields: dict[str, str], parametri_fissi: dict, schema_props: dict) -> dict`: for every schema parameter present in `fields`: `numero` → `float(value.replace(".", "").replace(",", "."))` (Italian thousands/decimals; on failure the string stays and the generator's error reaches the panel), `sino` → `value.strip().lower() in ("sì", "si", "s", "true", "1", "yes")`, else the string; `parametri_fissi` win over fields; keys not in the schema are dropped.
  - `async insert_base(session, deps, emit, request_id) -> None`: only when `draft.template["routing"]["tipo"] == "tool_diretto"`, the tool is in `deps.registry.names` and `deps.tools` is not `None`: `Status "Genero la base con <tool>"`, `text = await deps.tools.call(tool, **coerce_args(...))`, `result = json.loads(text)` (a `ToolError` or a non-JSON result → `Status "Base non disponibile: <message>"` and return, nothing inserted); `base = base_text(result)`; if `None` → return; `inserted = await deps.doc.insert_markdown("end", to_markdown(base), BASE_UNDO.format(...), bookmark=BASE_BOOKMARK.format(...), author=WRITE_AUTHOR)`; `draft.base = {"from_id", "to_id", "placeholders": placeholders(base), "tool": tool, "result": {k: v for k, v in result.items() if k != "testo" and not k.startswith("bozza")}}`; `draft.partitions.append({"titolo": f"Base: {template['descrizione']}", "from_id", "to_id"})`; `Status "Inserita la base deterministica (<tool>): N segnaposto da riempire"`.
  - `draft_message(session, action, message: str = "") -> str`: the user message of every drafting turn, in this order (each block only when it applies): `Redazione guidata: <descrizione> (<tipo_atto>, <categoria>).`; `Campi forniti dall'utente:` one line per field `- nome: valore`; `Note dell'utente: ...`; `Risposte alle domande precedenti:` one line per answer; on `action == "answer"`: `Risposte appena ricevute:` the new answers; on `action == "continue"` with a message: `Istruzione dell'utente: <message>`; `Atto di riferimento disponibile: <name> (<chars> caratteri): leggilo con leggi_atto_riferimento prima di comporre.` when `session.reference`; `Base deterministica già nel documento (paragrafi a-b), segnaposto ancora aperti: [..], [..]` or `Nessuna base deterministica: componi dal modello.`; `Partizioni già inserite:` one line per partition `- titolo (a-b)` or `nessuna`; `Redazione già completata in un turno precedente: agisci solo sull'istruzione dell'utente.` when `draft.done`; then `wrap_data("modello d'atto", json.dumps(template_without_campi, ensure_ascii=False))` (the `template_info` dict minus `campi`) and, when `draft.base`, `wrap_data(f"risultato di {tool}", json.dumps(draft.base["result"], ensure_ascii=False))`; finally the recipe (`load_recipe()`).
  - `hooks_for(session, deps) -> tuple[dict[str, Hook], list[dict]]`: the three hook tools:
    - `chiedi_dati` (`{"domande": [{"campo": str, "domanda": str, "esempio": str?, "tipo": str?}]}`): validates (a list of dicts with `campo` and `domanda`; `tipo` normalised to `FIELD_TYPES`, default `testo`; at most 8 kept, the rest dropped with the note `ERRORE: al massimo otto domande, le altre sono state scartate` appended to the result); stores `draft.questions`; returns `("Domande inviate all'utente: attendi le risposte nel prossimo turno.", "questions")`; with an empty or malformed list returns `(BAD_ARGUMENTS, None)`.
    - `redazione_completata` (`{"riepilogo": str}`): `draft.done = True`, `draft.riepilogo = riepilogo`, `draft.questions = []`; returns `("Redazione registrata come completata.", "done")`.
    - `leggi_atto_riferimento` (no parameters): `session.reference is None` → `("ERRORE: nessun atto di riferimento caricato", None)`; consent: if `session.consent != "document"` and not `session.reference_consented`: `decision = await deps.consent(ConsentSummary(scope="reference", chars=ref["chars"], endpoint_host=deps.endpoint_host, model=deps.model, zdr=deps.zdr, name=ref["name"]))`; `"document"` → `session.consent = "document"`; `"once"` → `session.reference_consented = True`; `"deny"` → `(CONSENT_DENIED, None)`; then `(wrap_data(f"atto di riferimento ({name})", text), None)`.
    Tool descriptions (Italian): `chiedi_dati`: `"Chiede all'utente i dati mancanti come campi da compilare (al massimo otto) e chiude il turno: le risposte arrivano nel turno successivo."`; `redazione_completata`: `"Segnala che l'atto è completo e consegna il riepilogo finale (calcoli, riferimenti verificati, allegati, avvertenze) in testo semplice; chiude il turno."`; `leggi_atto_riferimento`: `"Testo dell'atto di riferimento (caso simile) caricato dall'utente, da usare per struttura e stile, mai per i fatti."`.
  - `async run_draft(session, args: dict, deps: AgentDeps, emit, request_id) -> TurnOutcome`: `action = args.get("action")`; `start`: requires `tipo_atto` (else `ValueError("tipo_atto mancante")`, mapped by `main.py` to `bad_request`), `fields` dict of strings (values stripped, empty dropped), `notes`; `template = await deps.catalogue.info(tipo_atto, specs)` (a new `AgentDeps.catalogue: TemplateCatalogue | None`; `None` → `ValueError("catalogo non disponibile: mcp-legal-it non raggiungibile")`); `session.draft = DraftState(...)`; `await insert_base(...)`; then the turn. `answer`: requires `session.draft` (else `ValueError("nessuna redazione in corso")`) and `answers` dict; `draft.answers.update(...)`, `draft.questions = []`; the turn. `continue`: requires `session.draft`; the turn with `message`. The turn: `deps.hooks, deps.hook_tools = hooks_for(session, deps)` (the registry is rebuilt by the caller with `hook_tools`; see `main.py`), `outcome = await run_turn_with(deps, session, draft_message(session, action, message), PROFILE, emit, request_id, undo_label(tipo_atto))`; afterwards: every `outcome.inserted` entry not yet in `draft.partitions` (by `from_id`) is appended as `{"titolo", "from_id", "to_id"}`; `open_placeholders = [ph for ph in draft.base["placeholders"] if await deps.doc.find_text(ph)]` when `draft.base` (a `DocumentError` here → keep the previous list); the function returns the outcome and the caller reads the state for the summary through `draft_summary(session) -> dict` = `{"tipo_atto", "domande": draft.questions, "partizioni": draft.partitions, "segnaposto_aperti": open list, "completata": draft.done, "riepilogo": draft.riepilogo, "ended_by": outcome.ended_by}` (store `open_placeholders` in `draft.base["aperti"]` so `draft_summary` needs no document).
- `main.py`: the `draft` route: `action` missing or not in the three → `Error(code="bad_request", message="azione non valida: usa start, answer o continue")`; `ValueError` from `run_draft` → `Error(code="bad_request", message=str(e))`; `_model_turn` gains an `extra_summary: Callable[[], dict] | None` argument merged into the `Final.summary` (so `_send_turn_final` takes `extra: dict`); `_agent_deps` builds the catalogue (`self._catalogue(tools)` when tools are available) into `AgentDeps.catalogue`, and, for the draft profile, rebuilds the registry after `hooks_for`: simplest is to let `run_draft` receive `deps` and construct `deps.registry = ToolRegistry(specs, PROFILE, extra_tools=hook_tools)` itself, with `specs` kept on `AgentDeps.specs: list[ToolSpec]` (new field, set by `_agent_deps` and the CLI). `Final.text` for a draft turn is the model's text as for chat.

- [ ] **Step 1: Failing tests**

`core/tests/agent/test_loop.py`, append:

```python
async def test_hooks_run_as_internal_tools_and_can_end_the_turn():
    server, _ = make_fake_legal_server()
    seen = []

    async def ask(args):
        seen.append(args)
        return "Domande inviate.", "questions"

    hook_tool = {"type": "function", "function": {
        "name": "chiedi_dati", "description": "d",
        "parameters": {"type": "object", "properties": {"domande": {"type": "array"}}}}}
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([tool_turn(("chiedi_dati", {"domande": [{"campo": "x"}]})),
                           text_turn("mai raggiunto")])
        specs = await tools.tool_specs()
        registry = ToolRegistry(specs, "draft", extra_tools=[hook_tool])
        assert "chiedi_dati" in registry.names and registry.kind("chiedi_dati") == "internal"
        session = DocSession("d1")
        events = []

        async def emit(m):
            events.append(m)

        outcome = await run_turn(session, "domanda", "draft", llm, tools, FakeDocument(["x"]),
                                 registry, emit, "r1", LimitsConfig(), FakeDocument(["x"]).ask_consent,
                                 "h", "m", True, "u", hooks={"chiedi_dati": ask})
    assert seen == [{"domande": [{"campo": "x"}]}]
    assert outcome.ended_by == "questions" and outcome.stopped is None and outcome.text == ""
    assert len(llm.turns) == 1                       # the second scripted turn was never asked
    tool_msg = session.turns[0].messages[-1]
    assert tool_msg["role"] == "tool" and tool_msg["content"] == "Domande inviate."


async def test_inserted_entries_carry_a_title():
    server, _ = make_fake_legal_server()
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([
            tool_turn(("insert_markdown", {"where": "end", "markdown": "## Premesse in fatto\n\nTesto"}),
                      ("insert_markdown", {"where": "end", "markdown": "Riga senza titolo che è "
                                                                       "davvero molto lunga e va oltre i sessanta caratteri"})),
            text_turn("ok")])
        outcome, _, _ = await _run(llm, FakeDocument([""]), tools, "draft")
    assert [i["titolo"] for i in outcome.inserted] == [
        "Premesse in fatto", "Riga senza titolo che è davvero molto lunga e va oltre i sess"]
```

(`run_turn` gains a keyword-only `hooks: dict[str, Hook] | None = None` parameter at the end of its signature, default empty.)

`core/tests/commands/test_draft.py` (rewrite the file):

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import json

import pytest

from librelex_core import protocol as p
from librelex_core.agent.loop import AgentDeps
from librelex_core.agent.registry import ToolRegistry
from librelex_core.agent.state import DocSession
from librelex_core.commands.draft import (
    PROFILE,
    base_text,
    coerce_args,
    draft_message,
    draft_summary,
    placeholders,
    run_draft,
    to_markdown,
)
from librelex_core.commands.templates import TemplateCatalogue
from librelex_core.config import LimitsConfig
from librelex_core.document import FakeDocument
from librelex_core.mcp.client import LegalToolsClient
from tests.conftest import make_fake_legal_server
from tests.fakes import ScriptedLLM, text_turn, tool_turn


async def _deps(llm, doc, tools):
    specs = await tools.tool_specs()
    return AgentDeps(llm, tools, doc, ToolRegistry(specs, PROFILE), LimitsConfig(),
                     doc.ask_consent, "fake.local", "m", True, catalogue=TemplateCatalogue(tools),
                     specs=specs)


def _emit_list():
    events = []

    async def emit(m):
        events.append(m)
    return events, emit


def test_pure_helpers():
    assert placeholders("ILL.MO [SEDE] di [SEDE], Avv. [LEGALE], {campo}") == ["[SEDE]", "[LEGALE]", "{campo}"]
    assert base_text({"testo": "T", "bozza_ricorso": "B"}) == "T"
    assert base_text({"bozza_ricorso": "B", "riepilogo": {}}) == "B"
    assert base_text({"riepilogo": {"totale": 1}}) is None
    assert to_markdown("A\nB\n\n\nC") == "A\n\nB\n\nC"
    props = {"importo": {"type": "number"}, "provvisoria_esecuzione": {"type": "boolean"},
             "creditore": {"type": "string"}, "tipo_credito": {"type": "string"}}
    assert coerce_args({"importo": "12.000,50", "provvisoria_esecuzione": "sì",
                        "creditore": "Alfa", "extra": "x", "tipo_credito": "cambiale"},
                       {"tipo_credito": "ordinario"}, props) == {
        "importo": 12000.5, "provvisoria_esecuzione": True, "creditore": "Alfa",
        "tipo_credito": "ordinario"}


async def test_start_inserts_the_base_then_the_model_asks_questions_and_stops():
    server, calls = make_fake_legal_server()
    doc = FakeDocument([""])
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        llm = ScriptedLLM([tool_turn(("chiedi_dati", {"domande": [
            {"campo": "sede", "domanda": "Sede del tribunale?", "esempio": "Milano"},
            {"campo": "data_fattura", "domanda": "Data della fattura?", "tipo": "data"}]}))])
        session = DocSession("d1")
        deps = await _deps(llm, doc, tools)
        out = await run_draft(session, {"action": "start", "tipo_atto": "decreto_ingiuntivo_ordinario",
                                        "fields": {"creditore": "Alfa S.r.l.", "debitore": "Beta S.p.A.",
                                                   "importo": "12.000"},
                                        "notes": "fattura n. 12 del 3 marzo 2025"},
                              deps, emit, "r1")
    # the base was generated with the fixed parameter and inserted before the model ran
    assert calls["generatori"] == [("decreto_ingiuntivo", "Alfa S.r.l.", "Beta S.p.A.", 12000.0)]
    assert doc.inserts[0]["undo_label"] == "LibreLex: base decreto_ingiuntivo_ordinario"
    assert doc.inserts[0]["bookmark"] == "LibreLex.atto.decreto_ingiuntivo_ordinario"
    assert doc.inserts[0]["author"] == "LibreLex" and doc.inserts[0]["where"] == "end"
    assert doc.inserts[0]["markdown"].startswith("RICORSO PER DECRETO INGIUNTIVO\n\n(Artt. 633")
    draft = session.draft
    assert draft.base["placeholders"] == ["[SEDE]"] and draft.base["tool"] == "decreto_ingiuntivo"
    assert draft.base["result"]["giudice_competente"] == "Tribunale"
    assert draft.partitions[0]["titolo"] == "Base: Ricorso per decreto ingiuntivo — credito ordinario"
    # the model saw the state, not a bare message
    user = llm.calls[0][0][1]["content"]
    for needle in ("Redazione guidata: Ricorso per decreto ingiuntivo", "- creditore: Alfa S.r.l.",
                   "Note dell'utente: fattura n. 12", "Base deterministica già nel documento",
                   "[SEDE]", "<<<DATI: modello d'atto>>>", "<<<DATI: risultato di decreto_ingiuntivo>>>",
                   "# Ricetta di redazione", "Nessuna base" ):
        assert (needle in user) != (needle == "Nessuna base"), needle
    names = {t["function"]["name"] for t in llm.calls[0][1]}
    assert {"chiedi_dati", "redazione_completata", "leggi_atto_riferimento", "replace_text",
            "decreto_ingiuntivo", "contributo_unificato"} <= names
    # the questions ended the turn and reached the summary
    assert out.ended_by == "questions" and out.text == ""
    summary = draft_summary(session, out)
    assert summary["domande"] == [
        {"campo": "sede", "domanda": "Sede del tribunale?", "esempio": "Milano", "tipo": "testo"},
        {"campo": "data_fattura", "domanda": "Data della fattura?", "esempio": "", "tipo": "data"}]
    assert summary["segnaposto_aperti"] == ["[SEDE]"] and summary["completata"] is False
    assert any(isinstance(e, p.Status) and "base deterministica" in e.text for e in events)


async def test_answer_fills_placeholders_inserts_partitions_and_completes():
    server, calls = make_fake_legal_server()
    doc = FakeDocument([""])
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        session = DocSession("d1")
        llm1 = ScriptedLLM([tool_turn(("chiedi_dati", {"domande": [
            {"campo": "sede", "domanda": "Sede?"}]}))])
        await run_draft(session, {"action": "start", "tipo_atto": "decreto_ingiuntivo_ordinario",
                                  "fields": {"creditore": "Alfa", "debitore": "Beta", "importo": "12000"}},
                        await _deps(llm1, doc, tools), emit, "r1")
        llm2 = ScriptedLLM([
            tool_turn(("contributo_unificato", {"valore_causa": 12000, "tipo_procedimento": "monitorio"})),
            tool_turn(("replace_text", {"query": "[SEDE]", "replacement": "MILANO"}),
                      ("insert_markdown", {"where": "end", "markdown": "## Premesse in fatto\n\nAlfa ha emesso la fattura."}),
                      ("insert_markdown", {"where": "end", "markdown": "## Conclusioni\n\nEuro 129,50 di contributo unificato (DPR 115/2002)."})),
            tool_turn(("redazione_completata", {"riepilogo": "Calcoli: contributo unificato 129,50.\nAllegati: procura, fattura."})),
        ])
        out = await run_draft(session, {"action": "answer", "answers": {"sede": "Milano"}},
                              await _deps(llm2, doc, tools), emit, "r2")
    user = llm2.calls[0][0][-1]["content"]
    assert "Risposte appena ricevute:\n- sede: Milano" in user
    assert calls["calcoli"] == [("contributo_unificato", 12000.0, "monitorio")]
    paragraphs = [x.text for x in await doc.read_paragraphs()]
    assert any("MILANO" in t for t in paragraphs) and not any("[SEDE]" in t for t in paragraphs)
    draft = session.draft
    assert [pt["titolo"] for pt in draft.partitions] == [
        "Base: Ricorso per decreto ingiuntivo — credito ordinario", "Premesse in fatto", "Conclusioni"]
    assert draft.done is True and draft.riepilogo.startswith("Calcoli:")
    summary = draft_summary(session, out)
    assert summary["completata"] is True and summary["segnaposto_aperti"] == []
    assert summary["ended_by"] == "done" and out.replaced == 1
    assert [i["undo_label"] for i in doc.inserts][1:] == ["LibreLex: redazione decreto_ingiuntivo_ordinario"] * 3


async def test_reference_act_is_read_with_consent_once_and_never_grounds():
    server, calls = make_fake_legal_server()
    doc = FakeDocument([""], consent_decisions=["once", "once"])
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        session = DocSession("d1")
        session.reference = {"name": "ricorso_rossi.docx", "chars": 40,
                             "text": "RICORSO ... come da Cass. n. 99999/2024 ...", "troncato": False}
        llm = ScriptedLLM([
            tool_turn(("leggi_atto_riferimento", {})),
            tool_turn(("leggi_atto_riferimento", {})),
            tool_turn(("insert_markdown", {"where": "end", "markdown": "## Diritto\n\nCass. n. 99999/2024."})),
            text_turn("fatto")])
        deps = await _deps(llm, doc, tools)
        await run_draft(session, {"action": "start", "tipo_atto": "atto_di_citazione",
                                  "fields": {"attore": "A", "convenuto": "B", "oggetto": "O"}},
                        deps, emit, "r1")
    assert len(doc.consent_requests) == 1                     # once per session
    req = doc.consent_requests[0]
    assert req.scope == "reference" and req.name == "ricorso_rossi.docx" and req.chars == 40
    tool_msgs = [m for m in llm.calls[2][0] if m.get("role") == "tool"]
    assert "<<<DATI: atto di riferimento (ricorso_rossi.docx)>>>" in tool_msgs[0]["content"]
    assert calls["verifica"] == [["Cass. n. 99999/2024"]]    # not grounded by the reference
    assert "Atto di riferimento disponibile: ricorso_rossi.docx (40 caratteri)" in llm.calls[0][0][1]["content"]
    assert doc.inserts == [] or doc.inserts[0]["where"] == "end"   # no base: resource routing
    assert session.draft.base is None
    assert "Nessuna base deterministica" in llm.calls[0][0][1]["content"]


async def test_reference_denied_and_missing():
    server, _ = make_fake_legal_server()
    doc = FakeDocument([""], consent_decisions=["deny"])
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        session = DocSession("d1")
        llm = ScriptedLLM([tool_turn(("leggi_atto_riferimento", {})), text_turn("senza")])
        await run_draft(session, {"action": "start", "tipo_atto": "atto_di_citazione",
                                  "fields": {"attore": "A"}}, await _deps(llm, doc, tools), emit, "r1")
        msg = [m for m in llm.calls[1][0] if m.get("role") == "tool"][0]["content"]
        assert msg == "ERRORE: nessun atto di riferimento caricato"
        session.reference = {"name": "x.odt", "chars": 3, "text": "abc", "troncato": False}
        llm2 = ScriptedLLM([tool_turn(("leggi_atto_riferimento", {})), text_turn("senza")])
        await run_draft(session, {"action": "continue", "message": "vai"},
                        await _deps(llm2, doc, tools), emit, "r2")
        msg = [m for m in llm2.calls[1][0] if m.get("role") == "tool"][0]["content"]
        assert msg.startswith("ERRORE: invio del testo")


async def test_bad_actions_raise_value_error():
    server, _ = make_fake_legal_server()
    events, emit = _emit_list()
    async with LegalToolsClient(server) as tools:
        deps = await _deps(ScriptedLLM([]), FakeDocument([""]), tools)
        with pytest.raises(ValueError, match="tipo_atto"):
            await run_draft(DocSession("d"), {"action": "start"}, deps, emit, "r")
        with pytest.raises(ValueError, match="nessuna redazione"):
            await run_draft(DocSession("d"), {"action": "answer", "answers": {}}, deps, emit, "r")
        deps.catalogue = None
        with pytest.raises(ValueError, match="catalogo"):
            await run_draft(DocSession("d"), {"action": "start", "tipo_atto": "x"}, deps, emit, "r")
```

(The `FakeDocument.ask_consent` records `p.ConsentSummary` objects in `consent_requests`: keep that; the `name` attribute comes from Task 3's protocol change.)

`core/tests/test_main.py`: replace `test_draft_dispatch_runs_a_model_turn_and_refuses_an_empty_message` with:

```python
async def test_draft_dispatch_start_answer_and_bad_action():
    llm = ScriptedLLM([tool_turn(("chiedi_dati", {"domande": [{"campo": "sede", "domanda": "Sede?"}]})),
                       tool_turn(("redazione_completata", {"riepilogo": "Nulla da calcolare."}))])
    h = Harness(FakeDocument([""]), llm=llm)

    async def scenario(h: Harness):
        await h.send(HELLO)
        await h.pump(p.HelloOk)
        await h.send(p.Command(id="r0", doc_id="d1", name="draft", args={"message": "vecchio"}))
        await h.pump(p.Error)
        assert h.received[-1].code == "bad_request"
        await h.send(p.Command(id="r1", doc_id="d1", name="draft", args={
            "action": "start", "tipo_atto": "decreto_ingiuntivo_ordinario",
            "fields": {"creditore": "Alfa", "debitore": "Beta", "importo": "12000"}}))
        await h.pump(p.Final)
        final = h.received[-1]
        assert final.summary["tipo_atto"] == "decreto_ingiuntivo_ordinario"
        assert final.summary["domande"][0]["campo"] == "sede" and final.summary["ended_by"] == "questions"
        assert final.summary["partizioni"][0]["titolo"].startswith("Base: ")
        assert final.summary["segnaposto_aperti"] == ["[SEDE]"] and "usage_totals" in final.summary
        assert h.doc.inserts[0]["bookmark"] == "LibreLex.atto.decreto_ingiuntivo_ordinario"
        await h.send(p.Command(id="r2", doc_id="d1", name="draft", args={
            "action": "answer", "answers": {"sede": "Milano"}}))
        await h.pump(p.Final)
        final = h.received[-1]
        assert final.summary["completata"] is True and final.summary["riepilogo"] == "Nulla da calcolare."
        assert final.summary["ended_by"] == "done"
        await h.send(p.Command(id="r3", doc_id="d1", name="draft", args={"action": "start"}))
        await h.pump(p.Error)
        assert h.received[-1].code == "bad_request" and "tipo_atto" in h.received[-1].message

    await h.run(scenario)
```

Run: `cd core && uv run pytest tests/agent/test_loop.py tests/commands/test_draft.py tests/test_main.py -q` → failures.

- [ ] **Step 2: Implement**

`loop.py`: `Hook` alias, `hooks` parameter, `stop_reason` handling in `execute`/`run_tool_calls`/the main loop (`if stop_reason: outcome.ended_by = stop_reason; break` right after `await run_tool_calls(...)`), `TurnOutcome.ended_by`, `TurnOutcome.replaced: int = 0` (Task 2 may have added it), `inserted[].titolo` via:

```python
def _title(markdown: str) -> str:
    for line in markdown.splitlines():
        line = line.strip()
        if line:
            return line.lstrip("#").strip()[:60]
    return ""
```

`AgentDeps` gains `catalogue: Any | None = None`, `specs: list[ToolSpec] = field(default_factory=list)`, `hooks: dict[str, Hook] = field(default_factory=dict)`, `hook_tools: list[dict] = field(default_factory=list)` (all with defaults, after the existing positional fields). `run_turn_with` passes `hooks=deps.hooks`. `registry.py`: `ToolRegistry(specs, profile, extra_tools: list[dict] | None = None)`; the extra tools are merged into the internal group (sorted by name with them, kind `internal`).

`commands/draft.py`: everything in Interfaces; `run_draft` rebuilds `deps.registry = ToolRegistry(deps.specs, PROFILE, extra_tools=hook_tools)` before the turn so the model sees the three hook tools (the CLI and `main.py` pass `specs`). `main.py`: as in Interfaces (`_agent_deps` fills `catalogue` and `specs`; `_model_turn(..., extra_summary=lambda: draft_summary(session, outcome))`, so refactor `_model_turn` to give the runner access to the outcome: simplest is `run` returning the outcome and `extra_summary(outcome)` called after it).

- [ ] **Step 3: Run and commit**

`cd core && uv run ruff check . && uv run pytest -q` → green.

```bash
git add core
git commit -m "feat(core): stateful draft command: deterministic base, structured questions, completion summary, reference act with consent" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Dev CLI, docs, spec amendments, version 0.4.0

**Files:**
- Modify: `core/src/librelex_core/cli.py`, `core/README.md`, `core/pyproject.toml`, `core/src/librelex_core/__init__.py`, `docs/superpowers/specs/2026-09-07-librelex-it-design.md`, `extension/tests/headless/test_e2e_draft.py` (xfail marker only)
- Test: `core/tests/test_cli.py`, `core/tests/test_package.py`

**Interfaces:**
- CLI subcommands: `templates [QUERY]` (prints one line per model `tipo_atto  categoria  descrizione`, then the JSON); `template TIPO_ATTO` (prints `campo  tipo  obbligatorio` lines, then the JSON; `TemplateNotFound` → `errore: ...` exit 1); `draft --tipo TIPO --campo NOME=VALORE ... [--note TEXT] [--riferimento FILE] [--risposta CAMPO=VALORE ...] [--file DOC]`: with `--riferimento`, the file is read as UTF-8 text and set on the session as the reference (name = file name); the `start` turn runs and prints the streamed text; if the turn ended with questions, they are printed as `? campo (tipo): domanda [esempio]` lines; if `--risposta` values were given, an `answer` turn runs right after with them; the final line is the usage/insertion summary of `_model_turn` extended with `· domande: N`, `· partizioni: N`, `· completata` when applicable. The old positional `message` form of `draft` is removed.
- `core/README.md` "Dev CLI": the three commands with one example each (`uv run librelex-dev templates ingiuntivo`, `uv run librelex-dev template decreto_ingiuntivo_ordinario`, `uv run librelex-dev draft --tipo decreto_ingiuntivo_ordinario --campo creditore="Alfa S.r.l." --campo debitore="Beta S.p.A." --campo importo=12000 --note "fattura n. 12 del 3 marzo 2025" --risposta sede=Milano`).
- Spec amendments (the main spec, English, no dashes): §5.3 table gains the `replace_text` row (`query, replacement, paragraph_id (optional), all (default false)` → `count, anchors`; "Tracked deletion + insertion of an exact text; fills placeholders"); §6.3 `draft` row: "genera_modello_atto, lista_categorie_atti, cite_law, fetch_act_index, fetch_full_act, verifica_citazioni, the 20 generators the catalogue routes to, the 17 calculators it names (Appendix B) | read_paragraphs, insert_markdown, replace_text" and `review` gains `replace_text`; §6.9 replaced by: `### 6.9 Drafting from a template (M3, redesigned 2026-09-19)` + one paragraph pointing to `docs/superpowers/specs/2026-09-19-guided-drafting-design.md` as the binding description (recipe from the plugin, deterministic base, stateful draft command with structured questions, reference act with consent, Redazione panel in the extension); §8.2 adds one bullet: "The reference act (a similar case chosen by the lawyer) is document text of a third case: it is sent only after a consent with scope `reference` naming the file and its size; never logged, never persisted."; Appendix A gains the `list_templates`, `template_info`, `set_reference` commands and the three `draft` shapes, plus the `Final.summary` keys of a draft turn (`tipo_atto`, `domande`, `partizioni`, `segnaposto_aperti`, `completata`, `riepilogo`, `ended_by`); Appendix B regrouped: title `(55)`, "Act generators (20): ..." and "Calculators (17): ..." with the exact names of Task 1 (the two Appendix B calculators the catalogue does not name are kept and said so).
- `extension/tests/headless/test_e2e_draft.py`: add `pytest.mark.xfail(strict=False, reason="draft protocol changed by plan 2026-09-19-guided-drafting-core; rewritten in plan 2")` to `pytestmark`; nothing else in the extension changes.
- Version `0.4.0`.

- [ ] **Step 1: Failing tests**

`core/tests/test_cli.py`: replace `test_draft_subcommand_streams_and_summarises` with:

```python
def test_templates_and_template_subcommands(capsys):
    assert main(["templates"], tools_factory=_factory()) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("decreto_ingiuntivo_ordinario  atti_introduttivi")
    assert main(["templates", "precetto"], tools_factory=_factory()) == 0
    assert "precetto_ordinario" in capsys.readouterr().out
    assert main(["template", "decreto_ingiuntivo_ordinario"], tools_factory=_factory()) == 0
    out = capsys.readouterr().out
    assert "importo  numero  obbligatorio" in out and '"tool": "decreto_ingiuntivo"' in out
    assert main(["template", "boh"], tools_factory=_factory()) == 1
    assert capsys.readouterr().err.startswith("errore:")


def test_draft_subcommand_start_questions_answer_and_reference(tmp_path, capsys):
    from tests.fakes import ScriptedLLM, text_turn, tool_turn
    ref = tmp_path / "ricorso_rossi.txt"
    ref.write_text("RICORSO di riferimento", encoding="utf-8")
    llm = ScriptedLLM([
        tool_turn(("chiedi_dati", {"domande": [{"campo": "sede", "domanda": "Sede?", "esempio": "Milano"}]})),
        tool_turn(("leggi_atto_riferimento", {})),
        tool_turn(("insert_markdown", {"where": "end", "markdown": "## Conclusioni\n\nSi chiede."})),
        tool_turn(("redazione_completata", {"riepilogo": "Riepilogo finale."}))])
    rc = main(["draft", "--tipo", "decreto_ingiuntivo_ordinario", "--campo", "creditore=Alfa",
               "--campo", "debitore=Beta", "--campo", "importo=12000", "--note", "fattura 12",
               "--riferimento", str(ref), "--risposta", "sede=Milano"],
              tools_factory=_factory(), llm_factory=lambda cfg: llm)
    assert rc == 0
    out = capsys.readouterr().out
    assert "? sede (testo): Sede? [Milano]" in out
    assert "Riepilogo finale." in out and "completata" in out and "partizioni: 2" in out
    assert "Atto di riferimento disponibile: ricorso_rossi.txt" in llm.calls[0][0][1]["content"]
    assert "<<<DATI: atto di riferimento (ricorso_rossi.txt)>>>" in "".join(
        m["content"] for m in llm.calls[2][0] if m.get("role") == "tool")
```

`core/tests/test_package.py`: `0.4.0`.

Run: `cd core && uv run pytest tests/test_cli.py tests/test_package.py -q` → failures.

- [ ] **Step 2: Implement**

`cli.py`: the three subcommands (`templates`, `template`, `draft` with argparse `--campo`/`--risposta` as `action="append"` parsed on the first `=`); `_draft` builds a `DocSession("cli")`, sets `session.reference` from `--riferimento`, builds deps through the existing `_model_turn` machinery generalised to run a sequence of turns on one session (refactor `_model_turn` into `_with_deps(cfg, factory, llm_factory, path, profile, body)` where `body(session, deps) -> list[TurnOutcome]`; the summary line is printed per turn); questions printed after a turn with `ended_by == "questions"`. `core/README.md`, the spec amendments, the xfail marker, the version.

- [ ] **Step 3: Run and commit**

`cd core && uv run ruff check . && uv run pytest -q` → green; `cd extension && uv run pytest -q -m "not headless"` → green (nothing changed there but the marker import).

```bash
git add core docs/superpowers/specs/2026-09-07-librelex-it-design.md extension/tests/headless/test_e2e_draft.py
git commit -m "feat(core): dev CLI for the guided drafting (templates, template, draft start/answer with reference); spec amendments; core 0.4.0" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review notes

- Spec coverage (design doc): §3.1 recipe → Task 3; §3.2 base → Task 4; §3.3 profile → Tasks 1 and 2; §3.4 resources → Task 1; §4.1 commands → Task 3; §4.2 state → Task 3; §4.3 draft shapes and `replace_text` → Tasks 2 and 4; §4.4 questions → Task 4; §4.5 partitions and completion → Task 4; §5 reference → Tasks 3 and 4; §7 security (consent, no logging, `legal://` only) → Tasks 1, 3, 4; §8 core tests → every task; §10 amendments → Task 5. §6 (panel) and the headless tests are Plan 2.
- Type consistency: `AgentDeps.catalogue/specs/hooks/hook_tools` (Task 4) are what `commands/draft.py`, `main.py` and `cli.py` use; `TemplateCatalogue.info(tipo_atto, specs)` (Task 3) is what `run_draft` calls; `ReplaceResult`/`replace_text` (Task 2) is what the loop and the hooks use; `draft_summary(session, outcome)` (Task 4) is what `main.py` merges into the `Final` and the CLI prints from; `ConsentSummary.name` (Task 3) is what the reference hook fills.
- Deferred: the MCP prompt `redazione_atto` on mcp-legal-it (follow-up PR); pseudonymisation of the reference act (v2); a `tool_enhance` fake entry if a test ever needs that routing.
