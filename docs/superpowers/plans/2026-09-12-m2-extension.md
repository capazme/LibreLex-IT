# M2 Extension Implementation Plan: Chat, Consent, Usage, Research in the Sidebar

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the M2 core (chat turns, research command, consent, usage) in the three-panel sidebar: a message box with "Invia", a "Ricerca" quick action, streamed answers in "Risposte", the consent question answered inside the panel, a usage/cost line, and readable errors when the LLM is not configured. Also cut the per-turn token cost by compacting the tool schemas sent to the model.

**Architecture:** Extension only, plus one core task. The session (`session.py`) gains `chat()`, `research()`, streaming deltas, consent handling and usage rendering; the Actions panel gains the Invia/Ricerca buttons and a consent block that appears only while a `consent_request` is pending; the Answers panel appends streamed text without line breaks. The e2e headless test drives a real core against an in-test OpenAI-compatible SSE stub on localhost. The core's `ToolRegistry` compacts parameter schemas (types, enums, required kept; long descriptions truncated).

**Tech Stack:** as before (extension: LibreOffice Python 3.13 stdlib + uno; core: Python 3.12+).

**Spec:** `docs/superpowers/specs/2026-09-07-librelex-it-design.md` §5.1 (controls), §8.2 (consent: what, to whom, zdr; choices "per questo documento", "solo stavolta", "annulla"; session-scoped), §6.4-6.5 (limits, usage), §11 M2 row. Branch base: `main` (M2 core merged) with `feature/three-panels` merged in.

## Global Constraints

- Extension: stdlib + uno only; UI thread rule; controls on the container window's own model; XDL keeps `withtitlebar="false"`; Italian plain-text copy; the notice stays.
- Wire contract `core/src/librelex_core/protocol.py`: `Chat{id, doc_id, message, context{title, has_selection, cursor_paragraph}}`, `Delta{request_id, text}`, `ConsentRequest{request_id, call_id, summary{scope, chars, endpoint_host, model, zdr}}`, `ConsentResult{id: request_id, call_id, decision: document|once|deny}`, `Final{text, cancelled, usage{input_tokens, output_tokens, cost_usd}, summary{stopped?, inserted?, flagged?, unverified?, tool_calls?, usage_totals?}}`, errors `llm_config`, `llm_http`, `limit`.
- Consent is answered in the panel (no modal dialog): a hidden block in "Azioni" with the summary text and three buttons; while pending, the Cancel button stays enabled (cancelling the request also resolves the consent as `deny` on the core side through the cancel path).
- Streaming: deltas are appended to the transcript without newlines; the final text is not appended again after a streamed turn; a blank line closes the turn.
- Usage line: `Turno: <in> + <out> token · sessione: <total> token[ · costo: $<cost>]` with Italian thousands separators (`.`), cost with two decimals when present.
- Versions: extension `0.4.0` (`__init__` + `description.xml`); core `0.2.1` (schema compaction only).
- Tooling and commits as in the previous plans (ruff E F I UP B line 100; Conventional Commits with trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` via several `-m` flags, no heredocs, never amend, never push; never run LibreOffice's bundled python or unopkg; headless tests via `tests/headless/conftest.py`).

---

## File structure

```
extension/librelex_ext/
├── render.py        # render_usage, render_consent, render_turn_notes, llm_config hint
├── session.py       # chat(), research(), answer_consent(), streaming, usage, consent state
├── layout.py        # Actions: Send/Research row, consent block, Usage; version 0.4.0
└── panel.py         # actions send/research/consent_*, append_stream, set_usage, set_consent
extension/tests/test_render.py, test_session.py, test_layout.py, test_build_oxt.py
extension/tests/headless/test_e2e_chat.py, tests/headless/llm_stub.py   # in-test SSE stub server
core/src/librelex_core/agent/registry.py   # compact_schema(); core/tests/agent/test_profiles_registry.py
README.md, spec §5.1 / §8.2 note
```

---

### Task 1: Session and rendering for chat, streaming, consent and usage

**Files:**
- Modify: `extension/librelex_ext/render.py`, `extension/librelex_ext/session.py`
- Test: `extension/tests/test_render.py`, `extension/tests/test_session.py`

**Interfaces:**
- `View` (and `NullView`, `views.CompositeView`, `views.ROUTES`) gain `append_stream(text) -> Answers`, `set_usage(text) -> Actions`, `set_consent(summary: dict | None) -> Actions`.
- `render.render_usage(usage: dict | None, totals: dict | None) -> str` (empty string when `usage` is None); `render.render_consent(summary: dict) -> str` = `Inviare al modello {model} su {endpoint_host} ({'senza conservazione dati' if zdr else 'con conservazione dati'}) {'il testo selezionato' if scope == 'selection' else 'i paragrafi letti'} ({chars:n} caratteri)?`; `render.render_turn_notes(summary: dict) -> list[str]` (`[interrotto: limite di iterazioni]` / `[interrotto: tempo massimo]` / `[risposta troncata dal limite di lunghezza]` / `[annullato]` for `stopped`; `Inserito nei paragrafi a-b` per `inserted` entry; `Riferimenti segnalati con un commento: …` for `flagged`; `Riferimenti non verificati (fonte non disponibile): …` for `unverified`); `render.render_error` adds, for code `llm_config`, a second line `Configura la sezione [llm] (preset, api_key, model) in {config_path} e riavvia LibreOffice.` (signature `render_error(code, message, config_path="")`).
- `Session.chat(message: str)`: empty message → status `Scrivi un messaggio`; otherwise builds `context` from `adapter.get_document_info()` (`title`, `has_selection`, `cursor_paragraph`; on adapter failure an empty context) and submits `{"type": "chat", "id": rN, "doc_id", "message", "context"}` through the same start/pending/busy logic as `run_command` (refactor: `_submit(name_or_None, payload_factory)`; `pending` stores the payload factory). `Session.research(question: str)`: `run_command("research", {"question": question} if question.strip() else {})`.
- Streaming: `_on_delta` → `view.append_stream(text)` and marks `self._streamed = True`; `_on_final` after a streamed turn appends `""` (a blank line) instead of the final text, then the notes, then `view.set_usage(render_usage(usage, summary.get("usage_totals")))`; transcript replay (`self.transcript`) keeps streamed text as one entry per turn (accumulate deltas into `self._stream_buffer`, flushed into `self.transcript` on final/error/exit).
- Consent: `_on_consent_request` stores `self.pending_consent = (request_id, call_id)` and calls `view.set_consent(summary)` plus status `In attesa del consenso`; `Session.answer_consent(decision)` sends `{"type": "consent_result", "id": request_id, "call_id": call_id, "decision": decision}`, clears the pending consent, `view.set_consent(None)`; `_on_final`/`_on_error`/exit also clear a pending consent (`set_consent(None)`); the M1 auto-deny handler is removed.
- Errors: `_on_error` passes `self.config_path` to `render_error`.

- [ ] **Step 1: Failing tests** (append to the existing test files; extend `FakeView` with `append_stream` (accumulating into `self.stream`), `set_usage` (`self.usage`), `set_consent` (`self.consent`); extend `FakeAdapter.get_document_info` as it is):

```python
def test_render_usage_consent_and_notes():
    assert render_usage({"input_tokens": 40072, "output_tokens": 403, "cost_usd": None},
                        {"input_tokens": 40072, "output_tokens": 403}) == "Turno: 40.072 + 403 token · sessione: 40.475 token"
    assert render_usage({"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.0123}, None) == "Turno: 10 + 5 token · costo: $0.01"
    assert render_usage(None, None) == ""
    assert render_consent({"scope": "paragraphs", "chars": 1234, "endpoint_host": "127.0.0.1", "model": "claude-sonnet-5", "zdr": True}) == (
        "Inviare al modello claude-sonnet-5 su 127.0.0.1 (senza conservazione dati) i paragrafi letti (1.234 caratteri)?")
    assert render_turn_notes({"stopped": "iterations", "inserted": [{"from_id": "p:2", "to_id": "p:4"}],
                              "flagged": ["Cass. n. 9/2024"], "unverified": []}) == [
        "[interrotto: limite di iterazioni]", "Inserito nei paragrafi p:2-p:4",
        "Riferimenti segnalati con un commento: Cass. n. 9/2024"]
    assert render_error("llm_config", "llm.model non impostato", "/cfg/config.toml").splitlines()[1].startswith("Configura la sezione [llm]")


def test_chat_sends_context_streams_deltas_and_shows_usage():
    s, adapter, view, bridges = make()
    s.chat("   ")
    assert view.status == "Scrivi un messaggio" and not bridges
    s.chat("che dice il documento?")
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.2.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    msg = bridges[0].sent[-1]
    assert msg["type"] == "chat" and msg["id"] == "r1" and msg["message"] == "che dice il documento?"
    assert msg["context"] == {"title": "t", "has_selection": False, "cursor_paragraph": "p:0"}
    s.handle_event({"kind": "message", "msg": {"type": "delta", "request_id": "r1", "text": "Il documento "}})
    s.handle_event({"kind": "message", "msg": {"type": "delta", "request_id": "r1", "text": "dice X."}})
    assert view.stream == "Il documento dice X." and view.lines == [] or view.lines[-1] != "Il documento dice X."
    s.handle_event({"kind": "message", "msg": {"type": "final", "request_id": "r1", "text": "Il documento dice X.",
        "cancelled": False, "usage": {"input_tokens": 100, "output_tokens": 20, "cost_usd": None},
        "summary": {"tool_calls": 1, "usage_totals": {"input_tokens": 100, "output_tokens": 20}}}})
    assert view.lines[-1] == "" and "Il documento dice X." not in view.lines      # not duplicated
    assert s.transcript[-2] == "Il documento dice X." and s.state == "ready"
    assert view.usage == "Turno: 100 + 20 token · sessione: 120 token"


def test_consent_request_is_shown_and_answered_in_the_panel():
    s, adapter, view, bridges = make()
    s.chat("leggi")
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.2.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    summary = {"scope": "paragraphs", "chars": 50, "endpoint_host": "h", "model": "m", "zdr": True}
    s.handle_event({"kind": "message", "msg": {"type": "consent_request", "request_id": "r1", "call_id": "k1",
                                               "summary": summary}})
    assert view.consent == summary and view.status == "In attesa del consenso"
    s.answer_consent("once")
    assert bridges[0].sent[-1] == {"type": "consent_result", "id": "r1", "call_id": "k1", "decision": "once"}
    assert view.consent is None and s.pending_consent is None
    s.answer_consent("deny")                                   # nothing pending: ignored
    assert bridges[0].sent[-1]["decision"] == "once"


def test_research_and_llm_config_error_hint():
    s, adapter, view, bridges = make()
    s.research("  ")
    assert bridges[0].sent[0]["type"] == "hello"
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.2.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    assert bridges[0].sent[-1] == {"type": "command", "id": "r1", "doc_id": "d1", "name": "research", "args": {}}
    s.handle_event({"kind": "message", "msg": {"type": "error", "request_id": "r1", "code": "llm_config",
                                               "message": "llm.model non impostato"}})
    assert "Configura la sezione [llm]" in view.lines[-1] and "/cfg/config.toml" in view.lines[-1]
    s.research("usucapione")
    assert bridges[0].sent[-1]["args"] == {"question": "usucapione"}
```

- [ ] **Step 2: Implement** as in Interfaces (keep every existing test green: `run_command`, `select_citation`, `clear_transcript`, cancel flows).

- [ ] **Step 3: Run and commit** — `cd extension && uv run ruff check . && uv run pytest -q -m "not headless"`.

```bash
git add extension/librelex_ext/render.py extension/librelex_ext/session.py extension/librelex_ext/views.py extension/tests/test_render.py extension/tests/test_session.py extension/tests/test_views.py
git commit -m "feat(extension): chat turns with streamed answers, in-panel consent and usage line in the session" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Actions panel controls and wiring

**Files:**
- Modify: `extension/librelex_ext/layout.py`, `extension/librelex_ext/panel.py`, `extension/librelex_ext/__init__.py`, `extension/description.xml`, `extension/dialogs/panel.xdl` (height if needed)
- Test: `extension/tests/test_layout.py`, `extension/tests/test_build_oxt.py`

**Interfaces:**
- Actions kind, top to bottom: `Notice`; `DocumentLabel` + `ListCitations`/`VerifyDocument`, `VerifySelection`/`Cancel`; `ReferenceLabel` now `Messaggio, domanda o riferimento (es. art. 2043 c.c.)`; `Input`; `Send` (`Invia`, chat) / `Research` (`Ricerca`); `ShowText` / `InsertNorm`; consent block `ConsentText` (FixedText multiline, height 30, gray) + `ConsentDocument` (`Per questo documento`) / `ConsentOnce` (`Solo stavolta`) / `ConsentDeny` (`Annulla`) as three equal buttons in one row, all four `Visible: False` initially; `Progress`; `Status`; `Settings` + `Usage`.
- `ACTIONS` gains `Send: "send"`, `Research: "research"`, `ConsentDocument: "consent_document"`, `ConsentOnce: "consent_once"`, `ConsentDeny: "consent_deny"`; `BUSY_DISABLED` gains `Send`, `Research` (consent buttons are never in `BUSY_DISABLED`: they are used while busy); `TOOLTIPS` for the new buttons (`Invia`: `Chiedi al modello; il testo del documento viene inviato solo dopo il tuo consenso`; `Ricerca`: `Cerca precedenti sulla domanda scritta qui sopra (o sul testo selezionato) e inserisce le massime al cursore come revisione`).
- Panel: `send` → `session.chat(input text)` then clears the input; `research` → `session.research(input text)`; `consent_*` → `session.answer_consent(decision)`; view methods `append_stream` (Answers: `Transcript` text += text, capped to `MAX_TRANSCRIPT`), `set_usage` (Actions: `Usage.Label`), `set_consent` (Actions: sets `ConsentText.Label = render_consent(summary)` and toggles the four controls' visibility).
- Version 0.4.0; `test_build_oxt.py` expects `LibreLex-IT-0.4.0.oxt`.

- [ ] **Step 1: Failing tests** — `test_layout.py`: Actions set includes the new names, consent controls have `Visible: False`, `Send`/`Research` share a row, no overlaps at 170/190/260, `ACTIONS`/`BUSY_DISABLED`/`TOOLTIPS` consistency; build test 0.4.0.
- [ ] **Step 2: Implement**; keep `tests/headless/test_read.py`'s panel probes green (they use FakeWindow/FakeModel stand-ins: add the new control names to the stand-ins where required).
- [ ] **Step 3: Run and commit** — `cd extension && uv run ruff check . && uv run pytest -q` (headless included).

```bash
git add extension
git commit -m "feat(extension): Invia and Ricerca buttons, in-panel consent block and usage line" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: End-to-end chat in headless LibreOffice with an SSE stub, docs

**Files:**
- Create: `extension/tests/headless/llm_stub.py`, `extension/tests/headless/test_e2e_chat.py`
- Modify: `README.md`, `docs/superpowers/specs/2026-09-07-librelex-it-design.md` (§5.1: one sentence on the consent block; §8.2: "answered in the panel")

**Interfaces:**
- `llm_stub.StubLLM(responses: list[list[dict]])`: a `threading.Thread` running `http.server.ThreadingHTTPServer` on `127.0.0.1:0`; `base_url` property; every `POST /v1/chat/completions` answers the next scripted response as `text/event-stream` (chunks in the same shape as `core/tests/fakes.py::chunk/sse`), records the request bodies in `requests`; `stop()`. Scripted for the test: response 1 = a tool call `read_paragraphs {}` (finish `tool_calls`), response 2 = text `Il documento parla di responsabilità aquiliana.` (finish `stop`) with usage `{prompt_tokens: 120, completion_tokens: 9}`.
- `test_e2e_chat.py`: writes a temp `config.toml` with `[llm] preset = "custom", base_url = "<stub base_url>", api_key = "x", model = "stub"` and the fake legal server command as in `test_e2e.py`; runs a probe (via `run_probe`) that builds a `Session` with the real `Bridge` (as `test_e2e.py` does), calls `session.chat("Di cosa parla?")`, pumps events; when `view.consent` is set, calls `session.answer_consent("once")`; asserts: the stub received two requests, the second containing a `tool` message with the paragraph text; the streamed text reached `view.stream`; `view.usage` starts with `Turno: 120 + 9 token`; `session.state == "ready"`; nothing was written into the document.

- [ ] **Step 1: Write the stub and the failing test**; **Step 2: make it pass** (adjust only the harness, never the assertions' meaning); **Step 3: docs**: README section "Chat e ricerca" (how to use Invia/Ricerca, the consent block, the usage line, cost note), spec §5.1/§8.2 sentences; **Step 4:** `cd extension && uv run ruff check . && uv run pytest -q`; commit:

```bash
git add extension README.md docs/superpowers/specs/2026-09-07-librelex-it-design.md
git commit -m "test(extension): end-to-end chat through the real core against a localhost SSE stub; docs" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Core, compact tool schemas to cut the per-turn token cost

**Files:**
- Modify: `core/src/librelex_core/agent/registry.py`, `core/pyproject.toml` + `core/src/librelex_core/__init__.py` (0.2.1)
- Test: `core/tests/agent/test_profiles_registry.py`

**Interfaces:**
- `registry.compact_schema(schema: dict, max_desc: int = 120) -> dict`: returns a deep copy keeping `type`, `properties`, `required`, `enum`, `items`, `default` and `description` (truncated to `max_desc` characters at a word boundary with `…`), dropping `$schema`, `title`, `examples`, `additionalProperties` and any other key; applied recursively to nested `properties`/`items`.
- `ToolRegistry` applies `compact_schema` to every legal tool's parameters (document/internal tools are already compact). Byte-stability preserved (deterministic).
- Test: the research profile's tools array serialised with `json.dumps(..., ensure_ascii=False)` is under 30,000 characters when built from the real descriptions captured in a fixture (`core/tests/agent/fixtures/tool_specs_sample.json`: write it by hand from the schemas in the plan's repository knowledge or by running `tool_specs()` against the fake server, whichever the implementer chooses, with at least one 1,000+ character parameter description like `cerca_giurisprudenza_amministrativa.sede` to exercise truncation); `compact_schema` keeps `enum`/`required` and truncates descriptions.

- [ ] **Step 1: Failing tests**; **Step 2: implement**; **Step 3:** `cd core && uv run ruff check . && uv run pytest -q`; commit:

```bash
git add core
git commit -m "perf(core): compact tool parameter schemas sent to the model" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review

- Spec coverage: §5.1 chat input + Invia now active (M2), Ricerca quick action, usage/cost line; §8.2 consent with the three choices and the what/to-whom/zdr summary; §6.4/6.5 limits surfaced as notes; §11 M2 exit criterion reachable from the panel (Ricerca inserts grounded massime). Deviation: consent in-panel instead of a dialog (ruling: no modal UNO dialogs from a sidebar panel; same information and choices).
- Names consistent: `append_stream`, `set_usage`, `set_consent`, `chat`, `research`, `answer_consent`, `pending_consent`, `render_usage`, `render_consent`, `render_turn_notes`, `render_error(code, message, config_path)`, `compact_schema`, control names `Send`, `Research`, `ConsentText`, `ConsentDocument`, `ConsentOnce`, `ConsentDeny`, `Usage`.
