# M1 Extension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the LibreOffice Writer extension (`.oxt`) that drives the existing `librelex-core` process, so that a lawyer can verify the citations of a real act and insert a norm from the sidebar panel, with no LLM involved (spec §11, M1 exit criterion).

**Architecture:** The extension is a thin Python-UNO package: a sidebar panel (LibreThinker skeleton, MPL-2.0 files) that binds one `Session` per document; the session owns a `Bridge` (spawns `uv run --frozen --project <core> librelex-core`, JSON lines over stdio, reader thread → `queue.Queue` → `com.sun.star.awt.AsyncCallback`) and a `DocumentAdapter` that executes the nine document actions of spec §5.3 through UNO on the UI thread. The core (`core/`, already built, 112 tests) stays untouched except for the follow-ups of Tasks 1 and 2. The `.oxt` embeds the `core/` tree; `uv` builds its environment on first use.

**Tech Stack:** LibreOffice 26.2+ (26.8.0.3 verified) with its bundled Python 3.13 (extension code is stdlib + `uno` only); `uv`; `librelex-core` 0.1.0 (pydantic, fastmcp); pytest for the extension's pure-Python tests (dev machine Python 3.12+); headless LibreOffice macros (`vnd.sun.star.script:` URLs on `soffice --headless`) for the adapter tests, launched from pytest.

**Spec:** `docs/superpowers/specs/2026-09-07-librelex-it-design.md` (binding; §4, §5, §7, §8, §9, §11, §12 results, Appendix A). Facts used here that the spec records only as results come from `spike/evidence/*.txt` and `spike/README.md`.

## Global Constraints

- LibreOffice 26.2 or newer (Markdown import filter, spec §4.5); `description.xml` declares `LibreOffice-minimal-version 26.2`.
- Extension code runs in LibreOffice's bundled Python: **stdlib and `uno`/`unohelper` only**, no third-party imports, no pydantic (spec §13 "Extension code minimal, stdlib only").
- All UNO calls happen on the UI thread; background threads only push to a `queue.Queue` and call `AsyncCallback.addCallback` (spec §5.1).
- Panel controls are added to the container window's own model (`window.getModel()` + `createInstance`/`insertByName`), never via `setModel` (spec §5.1, Assumption 4 result).
- Subprocesses are spawned with fixed argv lists, never shell strings (spec §8.4). `http://` is accepted only for localhost (enforced by the core).
- Config directory 0700, files 0600 (spec §8.1): macOS `~/Library/Application Support/LibreLex/`, Linux `$XDG_CONFIG_HOME/librelex` or `~/.config/librelex`, Windows `%APPDATA%\LibreLex`; `LIBRELEX_CONFIG` overrides the file path. Keys never appear in logs or in the panel.
- Temporary markdown files live in a private 0700 directory (file 0600) and are unlinked right after insertion (spec §5.4, §8.4).
- Every text write is a tracked change under `RecordChanges`, wrapped in one undo context named after the action, e.g. `LibreLex: inserisci art. 2043 c.c.` (spec §5.4).
- Redline author "LibreLex" via a temporary switch of `/org.openoffice.UserProfile/Data` `givenname`/`sn`, restored in `finally` (spec §5.4 item 3); the core decides the author (`author` argument, `None` = keep the user identity).
- Comments: `com.sun.star.text.textfield.Annotation`, anchored on a cursor spanning the range with `insertTextContent(cursor, ann, True)`, verified through `Anchor.getString()`; orphan fields removed (spec §5.5). Comment author for the verification pipeline is the literal `LibreLex · verifica`.
- Paragraph ids: `p:<index>` (body paragraphs only, tables excluded from the count), `fn:<n>/p:<i>` (footnote n, 1-based, in document order), `t:<table>/c:<cell>/p:<i>` (spec §5.3).
- Wire contract = `core/src/librelex_core/protocol.py`. Pinned quirks: `read_paragraphs` args are `from_` and `to` (both keys always present, may be null); `DocResult.id` must equal the `DocCall.request_id`, `DocResult.call_id` the `DocCall.call_id`; the core waits at most 120 s for a `doc_result`; `hello_ok.mcp_server_version` is always `null` in M1; one command in flight per `doc_id`.
- Panel copy is Italian, plain text; the permanent notice reads exactly `Le citazioni vanno sempre controllate dal professionista.` (spec §5.1). Code, comments, commit messages and docs are English.
- Files derived from LibreThinker keep the MPL-2.0 header (`# Derived from LibreThinker (https://github.com/mihailthebuilder/librethinker-extension), MPL-2.0.`) and are listed in `NOTICE` (spec §4.6). New files carry `# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.`
- Tooling: `uv`, `ruff` (E F I UP B, line length 100), pytest with `asyncio_mode = "auto"` where async tests exist. Conventional Commits, one commit per task, trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`, commit messages passed with several `-m` flags (no heredocs).
- Environment restriction (spec §9.2): LibreOffice's bundled `python` binary and `unopkg`'s out-of-process helper are SIGKILLed when launched from the automation harness. Headless **macros** work. Therefore: adapter tests run as macros inside `soffice --headless` with a private profile; `unopkg add` (`scripts/dev_install.sh`) is run by the user from a Terminal; the GUI smoke test (spec §9.5 screenshot) is the user's.

---

## File structure

```
LibreLex-IT/
├── core/                                   # existing uv project; Tasks 1-2 touch these files only
│   ├── src/librelex_core/citations/norms.py          # accept "n. <numero> del <anno>"
│   ├── src/librelex_core/commands/insert_norm.py     # source labels, heading strip + rubrica, author param
│   ├── src/librelex_core/citations/verifier.py       # no duplicate progress event
│   ├── src/librelex_core/config.py                   # ensure_private on load, [extension] section
│   ├── src/librelex_core/mcp/client.py               # FASTMCP_* env for the local server
│   ├── src/librelex_core/main.py                     # author from config, first-connect status
│   └── tests/fake_legal_server.py                    # stdio fake of mcp-legal-it for integration tests
├── extension/                              # sources of the .oxt (zip root = this directory minus tests/ and pyproject.toml)
│   ├── META-INF/manifest.xml               # declares librelex_component.py, Factories.xcu, Sidebar.xcu
│   ├── description.xml                     # org.librelex.extension, version, LibreOffice-minimal-version 26.2
│   ├── Sidebar.xcu                         # deck "LibreLex", panel "Copilota legale" (MPL header)
│   ├── Factories.xcu                       # toolpanel factory LibreLexPanelFactory (MPL header)
│   ├── dialogs/panel.xdl                   # empty container window
│   ├── librelex_component.py               # UNO component: sys.path + registers PanelFactory
│   ├── librelex_ext/
│   │   ├── __init__.py                     # __version__, PROTOCOL_VERSION, EXTENSION_ID
│   │   ├── paths.py                        # config dir/file, template, uv lookup, core dir, BridgeSpec (no uno needed)
│   │   ├── bridge.py                       # subprocess + reader thread + JSON lines (stdlib only)
│   │   ├── render.py                       # Italian transcript text for final summaries (pure)
│   │   ├── session.py                      # per-document state machine, doc_call dispatch (pure)
│   │   ├── document.py                     # DocumentAdapter: the nine actions over UNO
│   │   ├── registry.py                     # sessions per RuntimeUID, model dispose + terminate listeners (uno)
│   │   └── panel.py                        # PanelFactory + Panel: controls, listeners, AsyncCallback (MPL header)
│   ├── pyproject.toml                      # dev-only uv project for the extension tests (pytest, ruff)
│   └── tests/
│       ├── test_paths.py, test_bridge.py, test_render.py, test_session.py, test_layout.py
│       ├── fake_core.py                    # stdlib stand-in for librelex-core used by test_bridge
│       ├── test_bridge_real_core.py        # spawns the real core + fake legal server
│       └── headless/                       # macro-driven tests, skipped when soffice is absent
│           ├── conftest.py                 # run_probe(): private profile, macro file, watchdog, JSON evidence
│           ├── test_read.py, test_write.py, test_comments.py, test_e2e.py
├── scripts/
│   ├── build_oxt.py                        # dist/LibreLex-IT-<version>.oxt + .sha256
│   └── dev_install.sh                      # build + unopkg add --force (user's Terminal)
├── .github/workflows/ci.yml                # + extension job, + headless job (best effort)
├── NOTICE, README.md                       # extension files listed, install/usage instructions
```

Module dependency rule inside `librelex_ext/`: `paths.py`, `bridge.py`, `render.py`, `session.py` import no UNO module (unit-testable on the dev machine); `document.py`, `registry.py`, `panel.py` import `uno`/`unohelper`. `document.py` imports nothing from the package (it is imported alone inside the headless macros).

---

### Task 1: Core follow-ups on citations and norm formatting

**Files:**
- Modify: `core/src/librelex_core/citations/norms.py:25` (`_NUM_YEAR`) and `:44-47` (`_STANDALONE_ACT_RE`)
- Modify: `core/src/librelex_core/commands/insert_norm.py` (`SOURCE_LABELS`, `format_norm_markdown`)
- Test: `core/tests/citations/test_norms.py`, `core/tests/commands/test_insert_norm.py`

**Interfaces:**
- Consumes: `extract_norms(text)`, `NormCitation.canonical()`, `format_norm_markdown(data, today)` as they exist.
- Produces: `source_label(fonte: str) -> str`; `split_heading(testo: str) -> tuple[str | None, str]` (rubrica, remaining text); `format_norm_markdown` output `**<Riferimento> (<rubrica>)**` when the server text starts with a heading carrying a rubrica.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/citations/test_norms.py`:

```python
def test_number_del_year_form_is_accepted():
    text = "ai sensi dell'art. 5 del d.lgs. n. 231 del 2001 e del d.lgs. n. 196 del 2003"
    cits = extract_norms(text)
    assert cits[0].canonical() == "art. 5 D.Lgs. 231/2001"
    assert cits[1].article is None and cits[1].number == "196" and cits[1].year == "2003"
    for c in cits:
        assert text[c.start:c.end] == c.display_text


def test_del_followed_by_a_day_number_is_not_a_year():
    cits = extract_norms("art. 2 l. n. 3 del 15 marzo")
    assert cits[0].number is None and cits[0].year is None and cits[0].canonical() is None
```

Append to `core/tests/commands/test_insert_norm.py` (add `source_label, split_heading` to the import list):

```python
def test_source_label_covers_akn_and_eurlex_variants():
    assert source_label("normattiva") == "Normattiva"
    assert source_label("normattiva-akn") == "Normattiva"
    assert source_label("eurlex") == "EUR-Lex"
    assert source_label("") == "fonte ufficiale"


def test_split_heading_strips_server_headings_and_keeps_rubrica():
    assert split_heading("### Art. 2043 - Risarcimento per fatto illecito\nQualunque fatto") == (
        "Risarcimento per fatto illecito", "Qualunque fatto")
    assert split_heading("Art. 2043.\n\nQualunque fatto") == (None, "Qualunque fatto")
    assert split_heading("Art. 2043 (Risarcimento per fatto illecito)\nQualunque") == (
        "Risarcimento per fatto illecito", "Qualunque")
    assert split_heading("Qualunque fatto") == (None, "Qualunque fatto")


def test_format_markdown_uses_rubrica_and_akn_label():
    data = {**ARTICLE_2043, "fonte": "normattiva-akn",
            "testo": "### Art. 2043 - Risarcimento per fatto illecito\n" + ARTICLE_2043["testo"]}
    md = format_norm_markdown(data, date(2026, 9, 7))
    assert md.startswith("**Art. 2043 c.c. (Risarcimento per fatto illecito)**\n\n> Qualunque fatto")
    assert "### Art." not in md and "fonte Normattiva," in md
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/citations/test_norms.py tests/commands/test_insert_norm.py -q`
Expected: FAIL (`canonical()` is `None` for the "del 2001" form; `ImportError` for `source_label`/`split_heading`).

- [ ] **Step 3: Implement**

In `core/src/librelex_core/citations/norms.py` replace the two regex definitions:

```python
# "196/2003" or "n. 196 del 2003"; the "del" form requires a four-digit year so that
# "l. n. 3 del 15 marzo" does not turn the day into a year (M1 follow-up a).
_NUM_SEP = r"(?:\s*/\s*(?=\d{2,4}\b)|\s+del\s+(?=(?:19|20)\d{2}\b))"
_NUM_YEAR = rf"(?:\s+n\.?\s*)?(?:\s*(\d+){_NUM_SEP}(\d{{2,4}}))?"
```

and

```python
_STANDALONE_ACT_RE = re.compile(
    r"(?:^|(?<=[\s (\"'’]))(" + ABBREV_PATTERN + r")\s+(?:n\.?\s*)?(\d+)" + _NUM_SEP + r"(\d{2,4})",
    re.IGNORECASE,
)
```

In `core/src/librelex_core/commands/insert_norm.py` replace `SOURCE_LABELS` and `format_norm_markdown`:

```python
_HEADING_RE = re.compile(
    r"^\s*(?:#{1,6}\s*)?art(?:\.|icolo)?\s*\d+(?:\s*-?\s*(?:bis|ter|quater|quinquies|sexies|"
    r"septies|octies|novies|decies))?\.?\s*(?:[-–—:(]\s*(?P<rubrica>[^)]+?)\)?)?\s*$",
    re.IGNORECASE,
)


def source_label(fonte: str) -> str:
    """Human label of the JSON `fonte` field ("normattiva", "normattiva-akn", "eurlex", ...)."""
    f = (fonte or "").lower()
    if f.startswith("normattiva"):
        return "Normattiva"
    if f.startswith("eur"):
        return "EUR-Lex"
    return "fonte ufficiale"


def split_heading(testo: str) -> tuple[str | None, str]:
    """Strip the server's leading heading line(s) ("### Art. 2043", "Art. 2043.") and return
    (rubrica, remaining text). The rubrica, when the heading carries one, goes into the
    bold title instead of the blockquote (spec §7.2 item 3)."""
    lines = testo.splitlines()
    rubrica: str | None = None
    while lines and (m := _HEADING_RE.match(lines[0])):
        rubrica = rubrica or ((m.group("rubrica") or "").strip() or None)
        lines.pop(0)
    while lines and not lines[0].strip():
        lines.pop(0)
    return rubrica, "\n".join(lines)


def format_norm_markdown(data: dict[str, Any], today: date) -> str:
    heading = data["riferimento"]
    heading = heading[0].upper() + heading[1:]
    rubrica, body = split_heading(data["testo"])
    if rubrica:
        heading = f"{heading} ({rubrica})"
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    quote = "\n".join(f"> {ln}" for ln in lines) if lines else "> (testo non disponibile)"
    label = source_label(data.get("fonte", ""))
    when = f"{today.day} {MONTHS[today.month - 1]} {today.year}"
    return f"**{heading}**\n\n{quote}\n\n*Testo vigente al {when}, fonte {label}, {data['url']}*\n"
```

Delete the old `SOURCE_LABELS` constant.

- [ ] **Step 4: Run the whole core suite**

Run: `cd core && uv run ruff check . && uv run pytest -q`
Expected: all tests pass (112 existing + 5 new).

- [ ] **Step 5: Commit**

```bash
git add core/src/librelex_core/citations/norms.py core/src/librelex_core/commands/insert_norm.py core/tests/citations/test_norms.py core/tests/commands/test_insert_norm.py
git commit -m "fix(core): accept 'n. N del YYYY' numbering, AKN source label and server heading lines" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: Core follow-ups on server, config and transport

**Files:**
- Modify: `core/src/librelex_core/commands/insert_norm.py` (`run_insert_norm` signature)
- Modify: `core/src/librelex_core/main.py` (`_run_command`)
- Modify: `core/src/librelex_core/config.py` (`ExtensionConfig`, `load_config`)
- Modify: `core/src/librelex_core/mcp/client.py` (`from_config` env)
- Modify: `core/src/librelex_core/citations/verifier.py` (`verify_citations` progress)
- Modify: `docs/superpowers/specs/2026-09-07-librelex-it-design.md` (Appendix A `from_`, Appendix D `[extension]`)
- Test: `core/tests/commands/test_insert_norm.py`, `core/tests/test_main.py`, `core/tests/test_config.py`, `core/tests/test_mcp_client.py`, `core/tests/citations/test_verifier.py`

**Interfaces:**
- Consumes: `CoreServer`, `Harness` (tests), `LegalToolsClient.from_config`, `verify_citations`.
- Produces: `run_insert_norm(doc, tools, reference, emit, request_id, author: str | None = "LibreLex")`; `Config.extension.uv: str` (default `""`); the core emits one `Status` `mcp-legal-it <version> collegato` on the first successful connection; `load_config` makes the config directory private; the local mcp-legal-it subprocess env contains `FASTMCP_SHOW_CLI_BANNER=false` and `FASTMCP_LOG_LEVEL=WARNING`.

- [ ] **Step 1: Write the failing tests**

`core/tests/commands/test_insert_norm.py`, append:

```python
async def test_run_insert_norm_author_none_keeps_user_identity():
    doc = FakeDocument(["x"])
    server, _ = make_fake_legal_server()

    async def emit(m):
        pass

    async with LegalToolsClient(server) as tools:
        await run_insert_norm(doc, tools, "art. 2043 c.c.", emit, "r1", author=None)
    assert doc.inserts[0]["author"] is None
```

`core/tests/test_main.py`: give `Harness.__init__` an optional `config: Config | None = None` parameter and use `CoreServer(config or Config(), ...)`; then append:

```python
async def test_redline_author_user_passes_author_none_and_announces_server():
    from librelex_core.config import DocumentConfig
    doc = FakeDocument(["x"])
    h = Harness(doc, config=Config(document=DocumentConfig(redline_author="user")))

    async def scenario(h: Harness):
        await h.send(HELLO)
        await h.pump(p.HelloOk)
        await h.send(p.Command(
            id="r1", doc_id="d1", name="insert_norm", args={"reference": "art. 2043 c.c."}))
        await h.pump(p.Final)
        assert doc.inserts[0]["author"] is None
        statuses = [m.text for m in h.received if isinstance(m, p.Status)]
        assert statuses[0] == "mcp-legal-it 2.14.0 collegato"

    await h.run(scenario)
```

`core/tests/test_config.py`, append:

```python
def test_extension_section_and_private_dir(tmp_path):
    path = tmp_path / "cfg" / "config.toml"
    path.parent.mkdir()
    path.write_text('[extension]\nuv = "/opt/homebrew/bin/uv"\n', encoding="utf-8")
    cfg = c.load_config(path)
    assert cfg.extension.uv == "/opt/homebrew/bin/uv"
    if os.name == "posix":
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert c.load_config(tmp_path / "missing.toml").extension.uv == ""
```

`core/tests/test_mcp_client.py`, append:

```python
def test_local_transport_silences_the_fastmcp_banner():
    from librelex_core.config import McpConfig
    client = LegalToolsClient.from_config(McpConfig())
    env = client.transport.env
    assert env["FASTMCP_SHOW_CLI_BANNER"] == "false" and env["FASTMCP_LOG_LEVEL"] == "WARNING"
    assert env["LEGAL_PROFILE"] == "full" and env["MCP_TRANSPORT"] == "stdio"
```

`core/tests/citations/test_verifier.py`, append:

```python
async def test_progress_is_not_repeated_when_nothing_is_retried():
    server, _ = make_fake_legal_server()
    seen = []

    async def progress(done, total):
        seen.append((done, total))

    async with LegalToolsClient(server) as tools:
        await verify_citations(["art. 2043 c.c.", "art. 1218 c.c."], tools, progress=progress)
    assert seen == [(2, 2)]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/commands/test_insert_norm.py tests/test_main.py tests/test_config.py tests/test_mcp_client.py tests/citations/test_verifier.py -q`
Expected: 5 failures (`TypeError` on `author`, `AttributeError` on `extension`, missing env keys, `seen == [(2, 2), (2, 2)]`, statuses mismatch).

- [ ] **Step 3: Implement**

`insert_norm.py`: change the signature and the call:

```python
async def run_insert_norm(
    doc: DocumentClient, tools: LegalToolsClient, reference: str | None,
    emit: Callable[[Any], Awaitable[None]], request_id: str,
    author: str | None = "LibreLex",
) -> dict[str, Any]:
```

and `inserted = await doc.insert_markdown("cursor", markdown, f"LibreLex: inserisci {canonical}", bookmark=bookmark, author=author)`.

`main.py`: in `CoreServer.__init__` add `self._announced = False`; in `_run_command`, right after `tools = await self._get_tools()` succeeds (after the `except` blocks):

```python
            if not self._announced:
                self._announced = True
                await self.send(p.Status(
                    request_id=msg.id, text=f"mcp-legal-it {tools.server_version} collegato"))
```

and in the `else` branch:

```python
                author = "LibreLex" if self.config.document.redline_author == "librelex" else None
                out = await run_insert_norm(doc, tools, msg.args.get("reference"), emit, msg.id,
                                            author=author)
```

`config.py`: add after `LoggingConfig`:

```python
class ExtensionConfig(_Section):
    """Read by the LibreOffice extension (stdlib tomllib), validated here so the file has one schema."""
    uv: str = ""   # absolute path of the uv binary when it is not on LibreOffice's PATH
```

add `extension: ExtensionConfig = Field(default_factory=ExtensionConfig)` to `Config`, and at the top of `load_config`:

```python
    path = path or config_path()
    try:
        ensure_private(path)   # directory 0700 / file 0600 on every load (spec §8.1)
    except OSError:
        pass                   # read-only or foreign location: loading still works
```

`mcp/client.py`: in `from_config`, local branch:

```python
            transport = StdioTransport(cfg.command[0], cfg.command[1:], env={
                "LEGAL_PROFILE": "full", "MCP_TRANSPORT": "stdio",
                # The server's CLI banner and "Starting MCP server" log line otherwise reach
                # the extension's stderr log on every start.
                "FASTMCP_SHOW_CLI_BANNER": "false", "FASTMCP_LOG_LEVEL": "WARNING",
            })
```

`verifier.py`, `verify_citations`: report through one helper that skips repeats:

```python
    last_reported = -1

    async def report(done: int) -> None:
        nonlocal last_reported
        if progress and done != last_reported:
            last_reported = done
            await progress(done, total)

    async def run(batch: list[str]) -> None:
        async with sem:
            verdicts.update(await _verify_batch(batch, tools))
        await report(min(len(verdicts), total))

    batches = [refs[i:i + batch_size] for i in range(0, total, batch_size)]
    await asyncio.gather(*(run(b) for b in batches))

    retry = [r for r in refs if verdicts[r].verdetto == RETRYABLE]
    for i in range(0, len(retry), batch_size):
        verdicts.update(await _verify_batch(retry[i:i + batch_size], tools))
    if total:
        await report(total)
```

Spec edits: in Appendix A change `"args": {"from": 0, "to": 40}` to `"args": {"from_": 0, "to": 40}` and add the sentence "The `read_paragraphs` keys are `from_` and `to` (Python parameter names), both always present, `null` when unbounded." In Appendix D append:

```toml
[extension]
uv = ""                        # absolute path of uv when LibreOffice's PATH does not contain it
```

- [ ] **Step 4: Run the whole core suite**

Run: `cd core && uv run ruff check . && uv run pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add core docs/superpowers/specs/2026-09-07-librelex-it-design.md
git commit -m "feat(core): author from config, first-connect status, private config dir, quiet mcp banner, [extension] section" -m "Also drops the duplicated final progress event and pins the read_paragraphs wire keys in the spec." -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 3: Extension scaffold, paths module and test project

**Files:**
- Create: `extension/META-INF/manifest.xml`, `extension/description.xml`, `extension/Sidebar.xcu`, `extension/Factories.xcu`, `extension/dialogs/panel.xdl`, `extension/librelex_component.py`
- Create: `extension/librelex_ext/__init__.py`, `extension/librelex_ext/paths.py`
- Create: `extension/pyproject.toml`, `extension/tests/__init__.py`, `extension/tests/test_paths.py`
- Modify: `.gitignore` (add `extension/.venv/` is already covered by `.venv/`; add `dist/` already present; nothing else)

**Interfaces:**
- Produces: `librelex_ext.__version__ = "0.1.0"`, `PROTOCOL_VERSION = 1`, `EXTENSION_ID = "org.librelex.extension"`, `IMPLEMENTATION_NAME = "org.librelex.extension.PanelFactory"`; `paths.config_dir() -> Path`, `paths.config_path() -> Path`, `paths.ensure_private(path)`, `paths.read_config() -> dict`, `paths.write_template_if_missing(path) -> bool`, `paths.find_uv(configured="") -> str | None`, `paths.repo_core_dir() -> Path`, `paths.core_dir(package_dir: Path) -> Path`, `paths.BridgeSpec(argv: list[str], env: dict[str, str], stderr_path: Path, cwd: str)`, `paths.bridge_spec(package_dir: Path, config: dict) -> BridgeSpec`, `paths.UvNotFound` exception. `panel.py` later resolves `package_dir` from the UNO `PackageInformationProvider`; `paths` itself never imports `uno`.

- [ ] **Step 1: Write the failing tests**

`extension/tests/__init__.py`: empty file.

`extension/tests/test_paths.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import os
import stat
import sys
from pathlib import Path

import pytest

from librelex_ext import EXTENSION_ID, PROTOCOL_VERSION, __version__, paths

REPO = Path(__file__).resolve().parents[2]


def test_constants():
    assert __version__ == "0.1.0" and PROTOCOL_VERSION == 1
    assert EXTENSION_ID == "org.librelex.extension"


def test_config_dir_follows_the_core_rule(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert paths.config_dir() == Path.home() / "Library" / "Application Support" / "LibreLex"
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg")
    assert paths.config_dir() == Path("/tmp/xdg/librelex")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", "C:/Users/x/AppData/Roaming")
    assert paths.config_dir() == Path("C:/Users/x/AppData/Roaming/LibreLex")


def test_config_path_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("LIBRELEX_CONFIG", str(tmp_path / "c.toml"))
    assert paths.config_path() == tmp_path / "c.toml"


def test_template_written_once_and_private(tmp_path, monkeypatch):
    monkeypatch.delenv("LIBRELEX_CONFIG", raising=False)
    path = tmp_path / "LibreLex" / "config.toml"
    assert paths.write_template_if_missing(path) is True
    assert paths.write_template_if_missing(path) is False
    text = path.read_text(encoding="utf-8")
    assert "[mcp_legal_it]" in text and "[extension]" in text and "api_key" in text
    if os.name == "posix":
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_read_config_tolerates_missing_and_broken_files(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRELEX_CONFIG", str(tmp_path / "none.toml"))
    assert paths.read_config() == {}
    broken = tmp_path / "broken.toml"
    broken.write_text("[extension\nuv = ", encoding="utf-8")
    monkeypatch.setenv("LIBRELEX_CONFIG", str(broken))
    assert paths.read_config() == {}
    good = tmp_path / "good.toml"
    good.write_text('[extension]\nuv = "/x/uv"\n', encoding="utf-8")
    monkeypatch.setenv("LIBRELEX_CONFIG", str(good))
    assert paths.read_config()["extension"]["uv"] == "/x/uv"


def test_find_uv_prefers_configured_then_path_then_candidates(tmp_path, monkeypatch):
    fake = tmp_path / "uv"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    assert paths.find_uv(str(fake)) == str(fake)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert paths.find_uv("") == str(fake)
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setattr(paths, "UV_CANDIDATES", [tmp_path / "missing", fake])
    assert paths.find_uv("") == str(fake)
    monkeypatch.setattr(paths, "UV_CANDIDATES", [])
    assert paths.find_uv("") is None


def test_core_dir_prefers_bundled_then_repo(tmp_path):
    bundled = tmp_path / "pkg" / "core"
    bundled.mkdir(parents=True)
    (bundled / "pyproject.toml").write_text("[project]\n")
    assert paths.core_dir(tmp_path / "pkg") == bundled
    assert paths.core_dir(tmp_path / "elsewhere") == paths.repo_core_dir()
    assert (paths.repo_core_dir() / "pyproject.toml").exists()


def test_bridge_spec_is_a_fixed_argv_with_private_env(tmp_path, monkeypatch):
    fake = tmp_path / "uv"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("LIBRELEX_CONFIG", str(tmp_path / "config.toml"))
    spec = paths.bridge_spec(tmp_path / "nopkg", {"extension": {"uv": str(fake)}})
    core = paths.repo_core_dir()
    assert spec.argv == [str(fake), "run", "--frozen", "--project", str(core), "librelex-core"]
    assert spec.env["UV_PROJECT_ENVIRONMENT"] == str(tmp_path / "core-env")
    assert spec.env["PYTHONUNBUFFERED"] == "1"
    assert spec.env["PATH"].split(os.pathsep)[0] == str(tmp_path)
    assert spec.stderr_path == tmp_path / "core-stderr.log"
    assert spec.cwd == str(core)


def test_bridge_spec_without_uv_raises_a_readable_error(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setattr(paths, "UV_CANDIDATES", [])
    with pytest.raises(paths.UvNotFound, match="uv non trovato"):
        paths.bridge_spec(tmp_path, {})
```

- [ ] **Step 2: Create the test project and run the tests to verify they fail**

`extension/pyproject.toml`:

```toml
# Dev-only project: runs the extension's pure-Python tests and ruff on the dev machine.
# The extension itself is never installed as a package; LibreOffice imports it from the .oxt.
[project]
name = "librelex-extension-dev"
version = "0.1.0"
description = "Test and lint harness for the LibreLex-IT LibreOffice extension"
requires-python = ">=3.12"
dependencies = []

[dependency-groups]
dev = ["pytest>=8", "ruff>=0.6"]

[tool.uv]
package = false

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
markers = ["headless: runs a macro inside soffice --headless (skipped when soffice is absent)"]

[tool.ruff]
line-length = 100
target-version = "py312"
extend-exclude = ["dialogs"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

Run: `cd extension && uv sync && uv run pytest -q`
Expected: FAIL with `ModuleNotFoundError: librelex_ext`.

- [ ] **Step 3: Write the static extension files**

`extension/META-INF/manifest.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="http://openoffice.org/2001/manifest">
  <manifest:file-entry manifest:media-type="application/vnd.sun.star.uno-component;type=Python"
                       manifest:full-path="librelex_component.py"/>
  <manifest:file-entry manifest:media-type="application/vnd.sun.star.configuration-data"
                       manifest:full-path="Factories.xcu"/>
  <manifest:file-entry manifest:media-type="application/vnd.sun.star.configuration-data"
                       manifest:full-path="Sidebar.xcu"/>
</manifest:manifest>
```

`extension/description.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<description xmlns="http://openoffice.org/extensions/description/2006"
             xmlns:d="http://openoffice.org/extensions/description/2006"
             xmlns:lo="http://libreoffice.org/extensions/description/2011"
             xmlns:xlink="http://www.w3.org/1999/xlink">
  <identifier value="org.librelex.extension"/>
  <version value="0.1.0"/>
  <platform value="all"/>
  <display-name>
    <name lang="en">LibreLex-IT</name>
    <name lang="it">LibreLex-IT</name>
  </display-name>
  <publisher>
    <name xlink:href="https://github.com/capazme" lang="en">Guglielmo Puzio</name>
  </publisher>
  <dependencies>
    <lo:LibreOffice-minimal-version value="26.2" d:name="LibreOffice 26.2"/>
  </dependencies>
</description>
```

`extension/Sidebar.xcu` (MPL header kept; ids renamed):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Derived from LibreThinker (https://github.com/mihailthebuilder/librethinker-extension), MPL-2.0. -->
<oor:component-data oor:name="Sidebar" oor:package="org.openoffice.Office.UI"
    xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <node oor:name="Content">
    <node oor:name="DeckList">
      <node oor:name="LibreLexDeck" oor:op="replace">
        <prop oor:name="Title" oor:type="xs:string"><value xml:lang="en-US">LibreLex</value></prop>
        <prop oor:name="Id" oor:type="xs:string"><value>LibreLexDeck</value></prop>
        <prop oor:name="ContextList"><value oor:separator=";">Writer, any, visible ;</value></prop>
        <prop oor:name="OrderIndex" oor:type="xs:int"><value>700</value></prop>
      </node>
    </node>
    <node oor:name="PanelList">
      <node oor:name="LibreLexPanel" oor:op="replace">
        <prop oor:name="Title" oor:type="xs:string"><value xml:lang="en-US">Copilota legale</value></prop>
        <prop oor:name="Id" oor:type="xs:string"><value>LibreLexPanel</value></prop>
        <prop oor:name="DeckId" oor:type="xs:string"><value>LibreLexDeck</value></prop>
        <prop oor:name="ContextList"><value oor:separator=";">Writer, any, visible ;</value></prop>
        <prop oor:name="ImplementationURL" oor:type="xs:string">
          <value>private:resource/toolpanel/LibreLexPanelFactory/Panel</value>
        </prop>
        <prop oor:name="OrderIndex" oor:type="xs:int"><value>100</value></prop>
        <prop oor:name="WantsCanvas" oor:type="xs:boolean"><value>false</value></prop>
      </node>
    </node>
  </node>
</oor:component-data>
```

`extension/Factories.xcu`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Derived from LibreThinker (https://github.com/mihailthebuilder/librethinker-extension), MPL-2.0. -->
<oor:component-data oor:name="Factories" oor:package="org.openoffice.Office.UI"
    xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <node oor:name="Registered">
    <node oor:name="UIElementFactories">
      <node oor:name="LibreLexPanelFactory" oor:op="replace">
        <prop oor:name="Type"><value>toolpanel</value></prop>
        <prop oor:name="Name"><value>LibreLexPanelFactory</value></prop>
        <prop oor:name="Module"><value/></prop>
        <prop oor:name="FactoryImplementation"><value>org.librelex.extension.PanelFactory</value></prop>
      </node>
    </node>
  </node>
</oor:component-data>
```

`extension/dialogs/panel.xdl` (an empty container; controls are built in Python):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE dlg:window PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "dialog.dtd">
<dlg:window xmlns:dlg="http://openoffice.org/2000/dialog" xmlns:script="http://openoffice.org/2000/script"
            dlg:id="LibreLexPanel" dlg:left="0" dlg:top="0" dlg:width="190" dlg:height="400"
            dlg:closeable="false" dlg:moveable="false" dlg:title="LibreLex"/>
```

`extension/librelex_component.py` (the file the manifest registers; pythonloader executes it with `__file__` set):

```python
# -*- coding: utf-8 -*-
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""UNO component entry point of LibreLex-IT: registers the sidebar panel factory.

LibreOffice's pythonloader executes this file; the sibling package ``librelex_ext``
holds the real code. The package directory is put on sys.path explicitly because
the loader's own sys.path handling differs between versions.
"""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import unohelper  # noqa: E402

from librelex_ext import IMPLEMENTATION_NAME  # noqa: E402
from librelex_ext.panel import PanelFactory  # noqa: E402

g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(
    PanelFactory, IMPLEMENTATION_NAME, ("com.sun.star.ui.UIElementFactory",))
```

- [ ] **Step 4: Write the package init and `paths.py`**

`extension/librelex_ext/__init__.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""LibreLex-IT LibreOffice extension (stdlib + UNO only)."""
__version__ = "0.1.0"
PROTOCOL_VERSION = 1          # must equal librelex_core.PROTOCOL_VERSION
EXTENSION_ID = "org.librelex.extension"
IMPLEMENTATION_NAME = "org.librelex.extension.PanelFactory"
```

`extension/librelex_ext/paths.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Locations and process spec: config dir/file, uv binary, bundled core, bridge argv/env.

Mirrors ``librelex_core.config`` for the directory rule (spec §8.1) so both sides
agree on where ``config.toml`` lives. No UNO here: fully unit-testable.
"""
from __future__ import annotations

import os
import shutil
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

UV_CANDIDATES = [
    Path.home() / ".local" / "bin" / "uv",
    Path("/opt/homebrew/bin/uv"),
    Path("/usr/local/bin/uv"),
    Path.home() / ".cargo" / "bin" / "uv",
]

CONFIG_TEMPLATE = """\
# LibreLex-IT configuration (spec Appendix D). Keep this file private: it may hold API keys.
# Environment overrides: LIBRELEX_LLM_API_KEY, LIBRELEX_MCP_BEARER, LIBRELEX_CONFIG.

[llm]
preset = "openrouter"          # cliproxyapi | openrouter | ollama | custom
base_url = "https://openrouter.ai/api/v1"
api_key = ""                   # not needed in M1 (verify citations / insert norm use no LLM)
model = ""
zero_data_retention = true

[mcp_legal_it]
mode = "local"                 # local | remote
command = ["uvx", "--from", "git+https://github.com/capazme/mcp-legal-it@v2.14.0", "mcp-legal-it"]
remote_url = ""                # https://... (https mandatory unless localhost)
bearer = ""

[document]
redline_author = "librelex"    # librelex | user
verify_footnotes = true

[limits]
max_iterations = 12
turn_timeout_s = 180
tool_timeout_s = 60
session_token_ceiling = 400000

[logging]
enabled = false

[extension]
uv = ""                        # absolute path of uv when LibreOffice's PATH does not contain it
"""


class UvNotFound(Exception):
    """uv is not on PATH, not configured and not in the usual places."""


@dataclass(frozen=True)
class BridgeSpec:
    argv: list[str]
    env: dict[str, str]
    stderr_path: Path
    cwd: str


def config_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "LibreLex"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "LibreLex"
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "librelex"


def config_path() -> Path:
    override = os.environ.get("LIBRELEX_CONFIG")
    return Path(override) if override else config_dir() / "config.toml"


def ensure_private(path: Path) -> None:
    """Directory 0700 and file 0600 (POSIX); no-op on Windows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "posix":
        return
    os.chmod(path.parent, 0o700)
    if path.exists():
        os.chmod(path, 0o600)


def write_template_if_missing(path: Path | None = None) -> bool:
    """Create a commented default config.toml on first run. Returns True when written."""
    path = path or config_path()
    ensure_private(path)
    if path.exists():
        return False
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(CONFIG_TEMPLATE)
    return True


def read_config(path: Path | None = None) -> dict:
    """Best-effort read: the core validates the file, the extension only needs [extension]."""
    path = path or config_path()
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def find_uv(configured: str = "") -> str | None:
    if configured and os.access(configured, os.X_OK):
        return configured
    found = shutil.which("uv")
    if found:
        return found
    for cand in UV_CANDIDATES:
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


def repo_core_dir() -> Path:
    """core/ of a source checkout (extension/librelex_ext/paths.py → repo root)."""
    return Path(__file__).resolve().parents[2] / "core"


def core_dir(package_dir: Path) -> Path:
    """The core bundled in the installed .oxt, else the repo checkout (development)."""
    bundled = package_dir / "core"
    if (bundled / "pyproject.toml").exists():
        return bundled
    return repo_core_dir()


def bridge_spec(package_dir: Path, config: dict) -> BridgeSpec:
    """Fixed argv + environment for the core process (spec §5.2, §8.4)."""
    uv = find_uv(str(config.get("extension", {}).get("uv", "") or ""))
    if uv is None:
        raise UvNotFound(
            "uv non trovato: installa uv (https://docs.astral.sh/uv/) oppure indica il percorso "
            f"in [extension] uv = \"...\" nel file {config_path()}")
    core = core_dir(package_dir)
    cfg_dir = config_path().parent
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(Path(uv).parent), env.get("PATH", "")])
    env["UV_PROJECT_ENVIRONMENT"] = str(cfg_dir / "core-env")  # keep the .oxt directory pristine
    env["PYTHONUNBUFFERED"] = "1"
    argv = [uv, "run", "--frozen", "--project", str(core), "librelex-core"]
    return BridgeSpec(argv=argv, env=env, stderr_path=cfg_dir / "core-stderr.log", cwd=str(core))
```

- [ ] **Step 5: Run the tests and ruff**

Run: `cd extension && uv run ruff check . && uv run pytest -q`
Expected: 10 passed.

- [ ] **Step 6: Commit**

```bash
git add extension
git commit -m "feat(extension): scaffold the .oxt (manifest, description, sidebar registration) and the paths module" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 4: Bridge to the core process

**Files:**
- Create: `extension/librelex_ext/bridge.py`
- Create: `extension/tests/fake_core.py`, `extension/tests/test_bridge.py`, `extension/tests/test_bridge_real_core.py`
- Create: `core/tests/fake_legal_server.py`

**Interfaces:**
- Consumes: `paths.BridgeSpec`.
- Produces: `bridge.BridgeError`; `bridge.Bridge(spec: BridgeSpec, on_event: Callable[[dict], None])` with `start()`, `send(msg: dict)`, `is_alive() -> bool`, `stop(timeout: float = 3.0)`. Events (dicts) delivered from the reader thread: `{"kind": "message", "msg": <parsed JSON object>}`, `{"kind": "garbage", "line": str}`, `{"kind": "exit", "code": int}`. `stop()` sends `{"type": "shutdown"}` first and escalates to terminate/kill.

- [ ] **Step 1: Write the fake core and the failing unit tests**

`extension/tests/fake_core.py` (stdlib only; stands in for `librelex-core`):

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Minimal stand-in for librelex-core: hello → hello_ok; command → one doc_call → final."""
import json
import sys


def out(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    pending = None
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        msg = json.loads(line)
        t = msg.get("type")
        if t == "hello":
            out({"type": "hello_ok", "core_version": "0.0-fake", "protocol": msg["protocol"],
                 "mcp_server_version": None, "warnings": []})
        elif t == "shutdown":
            return 0
        elif t == "command":
            if msg.get("args", {}).get("crash"):
                sys.exit(3)
            pending = msg["id"]
            out({"type": "status", "request_id": pending, "text": "leggo"})
            out({"type": "doc_call", "request_id": pending, "call_id": "c1",
                 "action": "get_document_info", "args": {}})
        elif t == "doc_result":
            out({"type": "final", "request_id": pending, "text": "fatto", "cancelled": False,
                 "usage": None, "summary": {"info": msg.get("result"), "ok": msg["ok"]}})
        elif t == "cancel":
            out({"type": "final", "request_id": msg["id"], "text": "Annullato.", "cancelled": True,
                 "usage": None, "summary": {}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`extension/tests/test_bridge.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import os
import queue
import sys
from pathlib import Path

import pytest

from librelex_ext.bridge import Bridge, BridgeError
from librelex_ext.paths import BridgeSpec

FAKE = Path(__file__).with_name("fake_core.py")


def spec(tmp_path):
    return BridgeSpec(argv=[sys.executable, str(FAKE)], env=dict(os.environ),
                      stderr_path=tmp_path / "stderr.log", cwd=str(tmp_path))


def wait_for(events: queue.Queue, kind: str, timeout=10):
    while True:
        ev = events.get(timeout=timeout)
        if ev["kind"] == kind:
            return ev


def test_hello_command_doc_call_final(tmp_path):
    events: queue.Queue = queue.Queue()
    b = Bridge(spec(tmp_path), events.put)
    b.start()
    try:
        b.send({"type": "hello", "id": "h1", "protocol": 1, "extension_version": "0.1.0",
                "lo_version": "26.8", "has_markdown_filter": True})
        ok = wait_for(events, "message")["msg"]
        assert ok["type"] == "hello_ok" and ok["protocol"] == 1
        b.send({"type": "command", "id": "r1", "doc_id": "d1", "name": "insert_norm", "args": {}})
        assert wait_for(events, "message")["msg"]["type"] == "status"
        call = wait_for(events, "message")["msg"]
        assert call["type"] == "doc_call" and call["action"] == "get_document_info"
        b.send({"type": "doc_result", "id": call["request_id"], "call_id": call["call_id"],
                "ok": True, "result": {"title": "t"}})
        final = wait_for(events, "message")["msg"]
        assert final["type"] == "final" and final["summary"]["info"] == {"title": "t"}
        assert b.is_alive()
    finally:
        b.stop()
    assert not b.is_alive()
    assert wait_for(events, "exit")["code"] == 0
    assert (tmp_path / "stderr.log").exists()


def test_exit_is_reported_and_send_fails_afterwards(tmp_path):
    events: queue.Queue = queue.Queue()
    b = Bridge(spec(tmp_path), events.put)
    b.start()
    b.send({"type": "hello", "id": "h1", "protocol": 1, "extension_version": "0.1.0",
            "lo_version": "26.8", "has_markdown_filter": True})
    wait_for(events, "message")
    b.send({"type": "command", "id": "r1", "doc_id": "d1", "name": "insert_norm",
            "args": {"crash": True}})
    assert wait_for(events, "exit")["code"] == 3
    with pytest.raises(BridgeError):
        for _ in range(50):          # the pipe may take a few writes to report EPIPE
            b.send({"type": "shutdown"})


def test_unparseable_line_is_reported_as_garbage(tmp_path):
    events: queue.Queue = queue.Queue()
    s = BridgeSpec(argv=[sys.executable, "-c", "print('not json'); print('{\"type\":\"log\"}')"],
                   env=dict(os.environ), stderr_path=tmp_path / "e.log", cwd=str(tmp_path))
    b = Bridge(s, events.put)
    b.start()
    assert wait_for(events, "garbage")["line"] == "not json"
    assert wait_for(events, "message")["msg"] == {"type": "log"}
    assert wait_for(events, "exit")["code"] == 0


def test_start_failure_raises_bridge_error(tmp_path):
    s = BridgeSpec(argv=[str(tmp_path / "missing-binary")], env=dict(os.environ),
                   stderr_path=tmp_path / "e.log", cwd=str(tmp_path))
    with pytest.raises(BridgeError, match="missing-binary"):
        Bridge(s, lambda ev: None).start()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd extension && uv run pytest tests/test_bridge.py -q`
Expected: FAIL with `ModuleNotFoundError: librelex_ext.bridge`.

- [ ] **Step 3: Implement `bridge.py`**

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Stdio JSON-lines bridge to the librelex-core process (spec §5.2).

Writer side: ``send`` serialises one JSON object per line under a lock. Reader side: a
daemon thread parses stdout lines and hands events to ``on_event`` (called on the reader
thread; the panel re-posts them to the UI thread through AsyncCallback). stderr goes to a
0600 log file in the config directory. No UNO here.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from collections.abc import Callable

from librelex_ext.paths import BridgeSpec


class BridgeError(Exception):
    """The core process could not be started or written to."""


class Bridge:
    def __init__(self, spec: BridgeSpec, on_event: Callable[[dict], None]):
        self.spec = spec
        self.on_event = on_event
        self._proc: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._stderr = None

    def start(self) -> None:
        try:
            fd = os.open(str(self.spec.stderr_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            self._stderr = os.fdopen(fd, "wb")
            self._proc = subprocess.Popen(          # fixed argv, never a shell string (spec §8.4)
                self.spec.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=self._stderr, env=self.spec.env, cwd=self.spec.cwd)
        except OSError as e:
            raise BridgeError(f"impossibile avviare {self.spec.argv[0]}: {e}") from e
        self._reader = threading.Thread(target=self._read_loop, name="librelex-bridge", daemon=True)
        self._reader.start()

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def send(self, msg: dict) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise BridgeError("core non avviato")
        line = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        with self._lock:
            try:
                self._proc.stdin.write(line)
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as e:
                raise BridgeError(f"core non raggiungibile: {e}") from e

    def stop(self, timeout: float = 3.0) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            self.send({"type": "shutdown"})
        except BridgeError:
            pass
        try:
            proc.wait(timeout)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if self._reader is not None:
            self._reader.join(timeout)
        if self._stderr is not None:
            self._stderr.close()

    def _read_loop(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stdout is not None
        for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                self.on_event({"kind": "garbage", "line": line})
                continue
            if not isinstance(msg, dict):
                self.on_event({"kind": "garbage", "line": line})
                continue
            self.on_event({"kind": "message", "msg": msg})
        code = proc.wait()
        self.on_event({"kind": "exit", "code": code})
```

- [ ] **Step 4: Run the unit tests**

Run: `cd extension && uv run pytest tests/test_bridge.py -q`
Expected: 4 passed.

- [ ] **Step 5: Write the real-core integration test and the stdio fake legal server**

`core/tests/fake_legal_server.py` (run with the core's environment; reuses the in-process fake of `conftest.py` over stdio):

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Run the fake mcp-legal-it of tests/conftest.py as a stdio MCP server.

Used by the extension's integration tests as the `[mcp_legal_it] command`:
    uv run --project core python core/tests/fake_legal_server.py
Verdicts: "Cass. n. 99999/2024" is inesistente; everything else verificata.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # core/ → import tests.conftest

from tests.conftest import make_fake_legal_server  # noqa: E402

if __name__ == "__main__":
    server, _ = make_fake_legal_server(
        verdicts={"Cass. n. 99999/2024": ("inesistente", "nessuna decisione con questo numero")})
    server.run(transport="stdio", show_banner=False)
```

If `FastMCP.run` does not accept `show_banner`, drop that argument (the core sets `FASTMCP_SHOW_CLI_BANNER=false` in the subprocess env since Task 2).

`extension/tests/test_bridge_real_core.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""The real librelex-core over real pipes, with the fake legal server: no LibreOffice."""
import os
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
```

- [ ] **Step 6: Run the integration test**

Run: `cd core && uv sync && cd ../extension && uv run pytest tests/test_bridge_real_core.py -q -x`
Expected: 1 passed (the first run may take a minute while uv resolves the environment). If the fake server fails to start, inspect `tmp_path/core-stderr.log` from the pytest output directory: the core prints the mcp error text in `error.message` as `mcp-legal-it non raggiungibile: ...`.

- [ ] **Step 7: Lint and commit**

Run: `cd extension && uv run ruff check . && uv run pytest -q` and `cd core && uv run ruff check .`

```bash
git add extension/librelex_ext/bridge.py extension/tests core/tests/fake_legal_server.py
git commit -m "feat(extension): stdio bridge to librelex-core with reader thread and exit detection" -m "Includes a stdio fake of mcp-legal-it for the real-core integration test." -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 5: Session state machine and transcript rendering

**Files:**
- Create: `extension/librelex_ext/render.py`, `extension/librelex_ext/session.py`
- Create: `extension/tests/test_render.py`, `extension/tests/test_session.py`

**Interfaces:**
- Consumes: `Bridge`-like objects (`start()`, `send()`, `is_alive()`, `stop()`), an adapter object with the nine action methods (Task 6-8 define `DocumentAdapter`; tests use a fake with the same method names and return shapes).
- Produces:
  - `render.render_verify_summary(summary: dict) -> tuple[str, list[tuple[str, str]]]` (transcript text, problem items `(label, paragraph_id)`), `render.render_insert_summary(summary: dict) -> str`, `render.render_error(code: str, message: str) -> str`.
  - `session.View` protocol: `append(text)`, `set_transcript(text)`, `set_status(text)`, `set_busy(busy: bool)`, `set_problems(labels: list[str])`. `session.NullView`.
  - `session.dispatch_doc_call(adapter, action: str, args: dict) -> dict` (the wire → adapter mapping, including result wrapping).
  - `session.Session(adapter, bridge_factory, doc_id, lo_version, has_markdown_filter, config_path: str)` with `bind(view, ui_post)`, `unbind()`, `post_event(ev)` (any thread), `handle_event(ev)` (UI thread), `run_command(name, args)`, `cancel()`, `goto_problem(index)`, `shutdown()`, attributes `state` (`stopped|starting|ready|busy`), `transcript: list[str]`, `problems: list[tuple[str, str]]`.

- [ ] **Step 1: Write the failing tests**

`extension/tests/test_render.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_ext.render import render_error, render_insert_summary, render_verify_summary

SUMMARY = {
    "scope": "document", "citazioni_totali": 5, "citazioni_uniche": 4,
    "per_verdetto": {"verificata": 2, "inesistente": 1, "metadati discordanti": 1},
    "problemi": [
        {"citazione": "Cass. n. 99999/2024", "verdetto": "inesistente", "nota": "non trovata",
         "occorrenze": [{"paragraph_id": "p:3", "start": 10, "end": 29}]},
        {"citazione": "art. 13 co. 7 D.Lgs. 196/2003", "verdetto": "metadati discordanti",
         "nota": "comma non riscontrato", "occorrenze": [{"paragraph_id": "fn:1/p:0", "start": 0, "end": 5}]},
    ],
    "da_controllare_a_mano": ["Corte cost. n. 1/2020"],
    "non_interpretabili": ["art. 5"],
    "non_verificabili": [],
    "da_riprovare": ["Cass. n. 100/2021"],
    "commenti_inseriti": 2,
}


def test_verify_summary_lists_counts_problems_and_side_lists():
    text, items = render_verify_summary(SUMMARY)
    assert text.splitlines()[0] == "Verificate 4 citazioni (5 occorrenze), 2 segnalazioni inserite."
    assert "verificata: 2 · inesistente: 1 · metadati discordanti: 1" in text
    assert "- Cass. n. 99999/2024: inesistente (p:3) — non trovata" in text
    assert "Da controllare a mano: Corte cost. n. 1/2020" in text
    assert "Non interpretabili: art. 5" in text
    assert "Da riprovare (fonte non raggiungibile): Cass. n. 100/2021" in text
    assert "Non verificabili" not in text
    assert items == [("Cass. n. 99999/2024 · inesistente", "p:3"),
                     ("art. 13 co. 7 D.Lgs. 196/2003 · metadati discordanti", "fn:1/p:0")]


def test_verify_summary_with_no_problems():
    text, items = render_verify_summary({**SUMMARY, "problemi": [], "commenti_inseriti": 0,
                                         "per_verdetto": {"verificata": 4},
                                         "da_controllare_a_mano": [], "non_interpretabili": [],
                                         "da_riprovare": []})
    assert "Nessun problema rilevato." in text and items == []


def test_insert_summary_and_error():
    text = render_insert_summary({"riferimento": "art. 2043 c.c.", "url": "https://x",
                                  "bookmark": "LibreLex.norma.x", "inserted": {"from_id": "p:1", "to_id": "p:3"}})
    assert text == "Inserito art. 2043 c.c. come revisione (paragrafi p:1-p:3, segnalibro LibreLex.norma.x).\nFonte: https://x"
    assert render_error("busy", "un'altra richiesta è in corso") == "Errore (busy): un'altra richiesta è in corso"
```

`extension/tests/test_session.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_ext import PROTOCOL_VERSION
from librelex_ext.bridge import BridgeError
from librelex_ext.session import Session, dispatch_doc_call


class FakeAdapter:
    def __init__(self):
        self.calls = []
        self.selection = {"text": "", "anchor": None}

    def get_document_info(self):
        return {"title": "t", "url": "", "paragraph_count": 2, "has_selection": False,
                "cursor_paragraph": "p:0", "lo_version": "26.8", "has_markdown_filter": True}

    def read_selection(self):
        return self.selection

    def read_paragraphs(self, from_=None, to=None):
        self.calls.append(("read_paragraphs", from_, to))
        return [{"id": "p:0", "text": "a", "style": "Text body", "kind": "body"}]

    def find_text(self, query, paragraph_id=None):
        return [{"anchor": {"paragraph_id": "p:0", "start": 0, "end": 1}, "text": query}]

    def insert_markdown(self, where, markdown, undo_label, bookmark=None, author=None):
        self.calls.append(("insert_markdown", where, bookmark, author))
        return {"from_id": "p:1", "to_id": "p:2"}

    def replace_selection(self, markdown, undo_label):
        return {"from_id": "p:0", "to_id": "p:0"}

    def add_comment(self, paragraph_id, start, end, expected_text, author, text):
        self.calls.append(("add_comment", paragraph_id, author))
        return "exact"

    def remove_comments(self, author):
        return 2

    def goto(self, paragraph_id):
        self.calls.append(("goto", paragraph_id))


class FakeBridge:
    def __init__(self, fail_start=False):
        self.sent, self.started, self.stopped, self.fail_start = [], False, False, fail_start
        self.alive = False

    def start(self):
        if self.fail_start:
            raise BridgeError("impossibile avviare uv")
        self.started = self.alive = True

    def send(self, msg):
        self.sent.append(msg)

    def is_alive(self):
        return self.alive

    def stop(self, timeout=3.0):
        self.stopped, self.alive = True, False


class FakeView:
    def __init__(self):
        self.lines, self.status, self.busy, self.problems, self.transcript = [], "", None, None, None

    def append(self, text):
        self.lines.append(text)

    def set_transcript(self, text):
        self.transcript = text

    def set_status(self, text):
        self.status = text

    def set_busy(self, busy):
        self.busy = busy

    def set_problems(self, labels):
        self.problems = labels


def make(fail_start=False):
    adapter, view = FakeAdapter(), FakeView()
    bridges = []

    def factory(on_event):
        b = FakeBridge(fail_start)
        bridges.append(b)
        return b

    s = Session(adapter, factory, doc_id="d1", lo_version="26.8", has_markdown_filter=True,
                config_path="/cfg/config.toml")
    s.bind(view, s.handle_event)     # tests run everything on one thread
    return s, adapter, view, bridges


def test_dispatch_maps_actions_and_wraps_results():
    a = FakeAdapter()
    assert dispatch_doc_call(a, "read_paragraphs", {"from_": 1, "to": None}) == {
        "paragraphs": [{"id": "p:0", "text": "a", "style": "Text body", "kind": "body"}]}
    assert a.calls[-1] == ("read_paragraphs", 1, None)
    dispatch_doc_call(a, "read_paragraphs", {"from": 2, "to": 3})    # Appendix A spelling
    assert a.calls[-1] == ("read_paragraphs", 2, 3)
    assert dispatch_doc_call(a, "find_text", {"query": "a", "paragraph_id": None})["occurrences"][0]["text"] == "a"
    assert dispatch_doc_call(a, "add_comment", {"paragraph_id": "p:0", "start": 0, "end": 1,
                                                "expected_text": "a", "author": "x", "text": "t"}) == {"anchored": "exact"}
    assert dispatch_doc_call(a, "remove_comments", {"author": "x"}) == {"count": 2}
    assert dispatch_doc_call(a, "goto", {"paragraph_id": "p:0"}) == {}
    assert dispatch_doc_call(a, "get_document_info", {})["paragraph_count"] == 2
    assert dispatch_doc_call(a, "insert_markdown", {"where": "cursor", "markdown": "x",
                                                    "undo_label": "u", "bookmark": None, "author": "LibreLex"}) == {"from_id": "p:1", "to_id": "p:2"}
    with pytest.raises(Exception, match="azione sconosciuta"):
        dispatch_doc_call(a, "format_disk", {})


def test_first_command_starts_core_sends_hello_then_command():
    s, adapter, view, bridges = make()
    s.run_command("verify_citations", {"scope": "document"})
    assert s.state == "starting" and bridges[0].started
    hello = bridges[0].sent[0]
    assert hello["type"] == "hello" and hello["protocol"] == PROTOCOL_VERSION
    assert hello["lo_version"] == "26.8" and hello["has_markdown_filter"] is True
    assert view.status == "Avvio del core..."
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                               "protocol": PROTOCOL_VERSION, "mcp_server_version": None,
                                               "warnings": ["w1"]}})
    assert s.state == "busy" and view.busy is True
    cmd = bridges[0].sent[1]
    assert cmd == {"type": "command", "id": "r1", "doc_id": "d1", "name": "verify_citations",
                   "args": {"scope": "document"}}
    assert "w1" in view.lines[-1]


def test_doc_call_is_answered_with_matching_ids_and_errors_become_ok_false():
    s, adapter, view, bridges = make()
    s.run_command("insert_norm", {"reference": "art. 2043 c.c."})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    s.handle_event({"kind": "message", "msg": {"type": "doc_call", "request_id": "r1", "call_id": "c7",
                                               "action": "insert_markdown",
                                               "args": {"where": "cursor", "markdown": "m", "undo_label": "u",
                                                        "bookmark": "b", "author": "LibreLex"}}})
    assert bridges[0].sent[-1] == {"type": "doc_result", "id": "r1", "call_id": "c7", "ok": True,
                                   "result": {"from_id": "p:1", "to_id": "p:2"}}
    s.handle_event({"kind": "message", "msg": {"type": "doc_call", "request_id": "r1", "call_id": "c8",
                                               "action": "nope", "args": {}}})
    res = bridges[0].sent[-1]
    assert res["ok"] is False and "azione sconosciuta" in res["error"] and res["call_id"] == "c8"


def test_final_renders_summary_and_frees_the_session():
    s, adapter, view, bridges = make()
    s.run_command("verify_citations", {})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    s.handle_event({"kind": "message", "msg": {"type": "status", "request_id": "r1", "text": "Leggo"}})
    assert view.status == "Leggo"
    s.handle_event({"kind": "message", "msg": {"type": "progress", "request_id": "r1", "done": 3, "total": 9}})
    assert view.status == "Verificate 3 di 9"
    s.handle_event({"kind": "message", "msg": {
        "type": "final", "request_id": "r1", "text": "Verificate 1 citazioni, 1 segnalazioni inserite.",
        "cancelled": False, "usage": None,
        "summary": {"scope": "document", "citazioni_totali": 1, "citazioni_uniche": 1,
                    "per_verdetto": {"inesistente": 1},
                    "problemi": [{"citazione": "Cass. n. 9/2024", "verdetto": "inesistente", "nota": "",
                                  "occorrenze": [{"paragraph_id": "p:4", "start": 0, "end": 1}]}],
                    "da_controllare_a_mano": [], "non_interpretabili": [], "non_verificabili": [],
                    "da_riprovare": [], "commenti_inseriti": 1}}})
    assert s.state == "ready" and view.busy is False and view.status == "Pronto"
    assert view.problems == ["Cass. n. 9/2024 · inesistente"]
    s.goto_problem(0)
    assert adapter.calls[-1] == ("goto", "p:4")
    s.run_command("insert_norm", {})                       # core already running: sent directly
    assert bridges[0].sent[-1]["id"] == "r2" and s.state == "busy"


def test_busy_rejects_a_second_command_and_cancel_is_forwarded():
    s, adapter, view, bridges = make()
    s.run_command("verify_citations", {})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    n = len(bridges[0].sent)
    s.run_command("insert_norm", {})
    assert len(bridges[0].sent) == n and "in corso" in view.status
    s.cancel()
    assert bridges[0].sent[-1] == {"type": "cancel", "id": "r1", "doc_id": "d1"}
    s.handle_event({"kind": "message", "msg": {"type": "final", "request_id": "r1", "text": "Annullato.",
                                               "cancelled": True, "usage": None, "summary": {}}})
    assert s.state == "ready" and view.lines[-1] == "Annullato."


def test_error_message_and_core_exit_reset_the_state():
    s, adapter, view, bridges = make()
    s.run_command("insert_norm", {})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                               "protocol": PROTOCOL_VERSION, "warnings": []}})
    s.handle_event({"kind": "message", "msg": {"type": "error", "request_id": "r1",
                                               "code": "reference_unparsed", "message": "boh"}})
    assert s.state == "ready" and view.lines[-1] == "Errore (reference_unparsed): boh"
    s.run_command("insert_norm", {})
    s.handle_event({"kind": "exit", "code": 1})
    assert s.state == "stopped" and view.busy is False
    assert "chiuso" in view.lines[-1] and "core-stderr.log" in view.lines[-1]
    s.run_command("insert_norm", {})                        # restarts lazily
    assert len(bridges) == 2 and s.state == "starting"


def test_protocol_mismatch_and_start_failure_are_reported():
    s, adapter, view, bridges = make()
    s.run_command("insert_norm", {})
    s.handle_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "9.0.0",
                                               "protocol": 99, "warnings": []}})
    assert s.state == "stopped" and bridges[0].stopped
    assert "protocollo 99" in view.lines[-1] and "richiesto 1" in view.lines[-1]
    s2, _, view2, _ = make(fail_start=True)
    s2.run_command("insert_norm", {})
    assert s2.state == "stopped" and "impossibile avviare uv" in view2.lines[-1]


def test_events_are_buffered_while_unbound_and_replayed_on_bind():
    s, adapter, view, bridges = make()
    s.run_command("insert_norm", {})
    s.unbind()
    s.post_event({"kind": "message", "msg": {"type": "hello_ok", "core_version": "0.1.0",
                                             "protocol": PROTOCOL_VERSION, "warnings": []}})
    assert s.state == "starting"                            # nothing handled yet
    view2 = FakeView()
    s.bind(view2, s.handle_event)
    assert s.state == "busy" and view2.transcript is not None and view2.busy is True


def test_shutdown_stops_the_bridge():
    s, adapter, view, bridges = make()
    s.run_command("insert_norm", {})
    s.shutdown()
    assert bridges[0].stopped and s.state == "stopped"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd extension && uv run pytest tests/test_render.py tests/test_session.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement `render.py`**

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Plain-text (Italian) rendering of core results for the panel transcript (spec §5.1, §7.1)."""
from __future__ import annotations


def render_verify_summary(summary: dict) -> tuple[str, list[tuple[str, str]]]:
    lines = [
        f"Verificate {summary.get('citazioni_uniche', 0)} citazioni "
        f"({summary.get('citazioni_totali', 0)} occorrenze), "
        f"{summary.get('commenti_inseriti', 0)} segnalazioni inserite."
    ]
    per = summary.get("per_verdetto") or {}
    if per:
        lines.append("  " + " · ".join(f"{k}: {v}" for k, v in per.items()))
    items: list[tuple[str, str]] = []
    problems = summary.get("problemi") or []
    if problems:
        lines.append("Problemi (commenti nel documento):")
        for pr in problems:
            occ = pr.get("occorrenze") or []
            where = occ[0]["paragraph_id"] if occ else "?"
            nota = f" — {pr['nota']}" if pr.get("nota") else ""
            lines.append(f"- {pr['citazione']}: {pr['verdetto']} ({where}){nota}")
            items.append((f"{pr['citazione']} · {pr['verdetto']}", where))
    else:
        lines.append("Nessun problema rilevato.")
    for key, label in (
        ("da_controllare_a_mano", "Da controllare a mano"),
        ("non_interpretabili", "Non interpretabili"),
        ("non_verificabili", "Non verificabili automaticamente"),
        ("da_riprovare", "Da riprovare (fonte non raggiungibile)"),
    ):
        values = summary.get(key) or []
        if values:
            lines.append(f"{label}: " + "; ".join(values))
    return "\n".join(lines), items


def render_insert_summary(summary: dict) -> str:
    ins = summary.get("inserted") or {}
    rng = f"{ins.get('from_id', '?')}-{ins.get('to_id', '?')}"
    return (f"Inserito {summary.get('riferimento', '?')} come revisione "
            f"(paragrafi {rng}, segnalibro {summary.get('bookmark', '?')}).\n"
            f"Fonte: {summary.get('url', '')}")


def render_error(code: str, message: str) -> str:
    return f"Errore ({code}): {message}"
```

- [ ] **Step 4: Implement `session.py`**

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Per-document session: core lifecycle, request state and doc_call dispatch (spec §4.3, §5.2).

Everything here runs on the UI thread except ``post_event`` (reader thread), which only
forwards to the callback the panel registered. No UNO imports.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any, Protocol

from librelex_ext import PROTOCOL_VERSION, __version__
from librelex_ext.bridge import BridgeError
from librelex_ext.render import render_error, render_insert_summary, render_verify_summary


class View(Protocol):
    def append(self, text: str) -> None: ...
    def set_transcript(self, text: str) -> None: ...
    def set_status(self, text: str) -> None: ...
    def set_busy(self, busy: bool) -> None: ...
    def set_problems(self, labels: list[str]) -> None: ...


class NullView:
    def append(self, text: str) -> None: ...
    def set_transcript(self, text: str) -> None: ...
    def set_status(self, text: str) -> None: ...
    def set_busy(self, busy: bool) -> None: ...
    def set_problems(self, labels: list[str]) -> None: ...


class DocumentActionError(Exception):
    """A document action failed; reported to the core as doc_result ok=false."""


def dispatch_doc_call(adapter: Any, action: str, args: dict) -> dict:
    """Map a wire doc_call onto the adapter and wrap the result as the core expects."""
    if action == "get_document_info":
        return adapter.get_document_info()
    if action == "read_selection":
        return adapter.read_selection()
    if action == "read_paragraphs":
        from_ = args.get("from_", args.get("from"))
        return {"paragraphs": adapter.read_paragraphs(from_, args.get("to"))}
    if action == "find_text":
        return {"occurrences": adapter.find_text(args["query"], args.get("paragraph_id"))}
    if action == "insert_markdown":
        return adapter.insert_markdown(args["where"], args["markdown"], args["undo_label"],
                                       args.get("bookmark"), args.get("author"))
    if action == "replace_selection":
        return adapter.replace_selection(args["markdown"], args["undo_label"])
    if action == "add_comment":
        return {"anchored": adapter.add_comment(
            args["paragraph_id"], args["start"], args["end"], args["expected_text"],
            args["author"], args["text"])}
    if action == "remove_comments":
        return {"count": adapter.remove_comments(args["author"])}
    if action == "goto":
        adapter.goto(args["paragraph_id"])
        return {}
    raise DocumentActionError(f"azione sconosciuta: {action}")


class Session:
    def __init__(self, adapter: Any, bridge_factory: Callable[[Callable[[dict], None]], Any],
                 doc_id: str, lo_version: str, has_markdown_filter: bool, config_path: str):
        self.adapter = adapter
        self.bridge_factory = bridge_factory
        self.doc_id, self.lo_version = doc_id, lo_version
        self.has_markdown_filter, self.config_path = has_markdown_filter, config_path
        self.bridge: Any = None
        self.state = "stopped"
        self.pending: tuple[str, dict] | None = None
        self.request_id: str | None = None
        self._n = 0
        self.transcript: list[str] = []
        self.problems: list[tuple[str, str]] = []
        self.view: View = NullView()
        self._buffer: list[dict] = []
        self.ui_post: Callable[[dict], None] = self._buffer.append

    # --- panel binding -------------------------------------------------------
    def bind(self, view: View, ui_post: Callable[[dict], None]) -> None:
        self.view, self.ui_post = view, ui_post
        view.set_transcript("\n".join(self.transcript))
        view.set_problems([label for label, _ in self.problems])
        view.set_busy(self.state in ("starting", "busy"))
        buffered, self._buffer = self._buffer, []
        for ev in buffered:
            ui_post(ev)

    def unbind(self) -> None:
        self.view = NullView()
        self.ui_post = self._buffer.append

    def post_event(self, ev: dict) -> None:
        """Called from the bridge reader thread: hand the event to the UI thread."""
        self.ui_post(ev)

    # --- user actions (UI thread) -------------------------------------------
    def run_command(self, name: str, args: dict) -> None:
        if self.state == "busy":
            self.view.set_status("Richiesta in corso: attendi o premi Annulla")
            return
        if self.state == "starting":
            self.pending = (name, args)
            return
        if self.state == "stopped":
            try:
                self.bridge = self.bridge_factory(self.post_event)
                self.bridge.start()
            except BridgeError as e:
                self.bridge = None
                self._append(f"Impossibile avviare il core: {e}")
                return
            self.state = "starting"
            self.pending = (name, args)
            self.view.set_busy(True)
            self.view.set_status("Avvio del core...")
            self.bridge.send({"type": "hello", "id": "h1", "protocol": PROTOCOL_VERSION,
                              "extension_version": __version__, "lo_version": self.lo_version,
                              "has_markdown_filter": self.has_markdown_filter})
            return
        self._send_command(name, args)

    def cancel(self) -> None:
        if self.state == "busy" and self.request_id and self.bridge is not None:
            self.bridge.send({"type": "cancel", "id": self.request_id, "doc_id": self.doc_id})
            self.view.set_status("Annullamento...")

    def goto_problem(self, index: int) -> None:
        if 0 <= index < len(self.problems):
            try:
                self.adapter.goto(self.problems[index][1])
            except Exception as e:  # navigation is best effort
                self.view.set_status(f"Posizione non raggiungibile: {e}")

    def shutdown(self) -> None:
        if self.bridge is not None:
            try:
                self.bridge.stop()
            finally:
                self.bridge = None
        self.state = "stopped"
        self.pending = None
        self.request_id = None

    # --- events from the core (UI thread) -----------------------------------
    def handle_event(self, ev: dict) -> None:
        kind = ev.get("kind")
        if kind == "exit":
            was_active = self.state in ("starting", "busy")
            self.bridge = None
            self.state, self.pending, self.request_id = "stopped", None, None
            self.view.set_busy(False)
            self.view.set_status("Core non attivo")
            if was_active:
                log = os.path.join(os.path.dirname(self.config_path), "core-stderr.log")
                self._append(f"Il core si è chiuso inaspettatamente (codice {ev.get('code')}). "
                             f"Dettagli in {log}. Riprova: verrà riavviato.")
            return
        if kind == "garbage":
            return
        if kind != "message":
            return
        msg = ev["msg"]
        handler = getattr(self, f"_on_{msg.get('type', '')}", None)
        if handler is not None:
            handler(msg)

    def _on_hello_ok(self, msg: dict) -> None:
        for w in msg.get("warnings") or []:
            self._append(f"Avviso del core: {w}")
        if msg.get("protocol") != PROTOCOL_VERSION:
            self._append(f"Core incompatibile: protocollo {msg.get('protocol')}, richiesto "
                         f"{PROTOCOL_VERSION} (core {msg.get('core_version')}). Aggiorna l'estensione.")
            self.shutdown()
            self.view.set_busy(False)
            return
        self.state = "ready"
        self.view.set_status("Pronto")
        if self.pending is not None:
            name, args = self.pending
            self.pending = None
            self._send_command(name, args)
        else:
            self.view.set_busy(False)

    def _on_status(self, msg: dict) -> None:
        self.view.set_status(msg.get("text", ""))

    def _on_progress(self, msg: dict) -> None:
        self.view.set_status(f"Verificate {msg.get('done', 0)} di {msg.get('total', 0)}")

    def _on_delta(self, msg: dict) -> None:
        self._append(msg.get("text", ""))

    def _on_log(self, msg: dict) -> None:
        return

    def _on_consent_request(self, msg: dict) -> None:
        # M1 has no LLM turn; refuse defensively and say so (spec §8.2 arrives with M2).
        self._append("Richiesta di consenso non supportata in questa versione: rifiutata.")
        self.bridge.send({"type": "consent_result", "id": msg["request_id"],
                          "call_id": msg["call_id"], "decision": "deny"})

    def _on_doc_call(self, msg: dict) -> None:
        reply = {"type": "doc_result", "id": msg["request_id"], "call_id": msg["call_id"]}
        try:
            reply.update(ok=True, result=dispatch_doc_call(self.adapter, msg["action"],
                                                           msg.get("args") or {}))
        except Exception as e:
            reply.update(ok=False, error=f"{type(e).__name__}: {e}"
                         if not isinstance(e, DocumentActionError) else str(e))
        self.bridge.send(reply)

    def _on_final(self, msg: dict) -> None:
        self.state, self.request_id = "ready", None
        self.view.set_busy(False)
        self.view.set_status("Pronto")
        summary = msg.get("summary") or {}
        if msg.get("cancelled"):
            self._append(msg.get("text") or "Annullato.")
        elif "per_verdetto" in summary:
            text, items = render_verify_summary(summary)
            self.problems = items
            self.view.set_problems([label for label, _ in items])
            self._append(text)
        elif "riferimento" in summary:
            self._append(render_insert_summary(summary))
        else:
            self._append(msg.get("text") or "Completato.")

    def _on_error(self, msg: dict) -> None:
        if self.state == "busy" and msg.get("request_id") in (self.request_id, None):
            self.state, self.request_id = "ready", None
            self.view.set_busy(False)
            self.view.set_status("Pronto")
        self._append(render_error(msg.get("code", "?"), msg.get("message", "")))

    # --- helpers -------------------------------------------------------------
    def _send_command(self, name: str, args: dict) -> None:
        self._n += 1
        self.request_id = f"r{self._n}"
        self.state = "busy"
        self.view.set_busy(True)
        self.view.set_status("Invio della richiesta...")
        self.bridge.send({"type": "command", "id": self.request_id, "doc_id": self.doc_id,
                          "name": name, "args": args})

    def _append(self, text: str) -> None:
        self.transcript.append(text)
        self.view.append(text)
```

- [ ] **Step 5: Run the tests and ruff**

Run: `cd extension && uv run ruff check . && uv run pytest -q`
Expected: all passed (including Task 3-4 tests).

- [ ] **Step 6: Commit**

```bash
git add extension/librelex_ext/render.py extension/librelex_ext/session.py extension/tests/test_render.py extension/tests/test_session.py
git commit -m "feat(extension): per-document session state machine, doc_call dispatch and transcript rendering" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 6: Document adapter, reading actions, and the headless macro harness

**Files:**
- Create: `extension/librelex_ext/document.py` (reading half; Tasks 7-8 add the writing methods to the same class)
- Create: `extension/tests/headless/__init__.py`, `extension/tests/headless/conftest.py`, `extension/tests/headless/test_read.py`

**Interfaces:**
- Produces: `document.DocumentActionError`; `document.lo_version(ctx) -> str`; `document.has_markdown_filter(ctx) -> bool`; `document.DocumentAdapter(ctx, model)` with `get_document_info() -> dict`, `read_selection() -> dict`, `read_paragraphs(from_, to) -> list[dict]`, `find_text(query, paragraph_id) -> list[dict]`, `goto(paragraph_id) -> None`, plus internals used by Tasks 7-8: `_index() -> list[Entry]`, `_entry(paragraph_id) -> Entry`, `_entry_at(range) -> Entry | None`, `_offset_in_paragraph(entry, range) -> int`, `_paragraphs_of(container) -> list`, `_prefix_for(container, sample_range) -> str`, `_view_cursor()`. `Entry` has `id, para, container, kind, style, body_index`.
- Headless harness: `run_probe(soffice, name, body) -> dict` where `body` defines `def probe(ctx, out): ...` and may use the preamble helpers `prop`, `new_doc(ctx)`, `fixture_doc(ctx)`, `paragraph_texts(text)`, `redlines(doc)`, `annotations(doc)`; the fixture `soffice` skips the test when LibreOffice is absent.

Result shapes returned by the adapter are exactly the JSON the core validates (`DocInfo`, `Selection`, `Paragraph`, `Occurrence` in `core/src/librelex_core/document.py`).

- [ ] **Step 1: Write the headless harness**

`extension/tests/headless/__init__.py`: empty.

`extension/tests/headless/conftest.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Run test probes as Python macros inside `soffice --headless` (spec §9.1 item 2, §9.2).

Why macros: LibreOffice's bundled python binary and unopkg's helper are SIGKILLed when
launched from the automation harness on this Mac, but soffice itself runs and executes
`vnd.sun.star.script:` URLs. Each probe gets a fresh private profile; the macro puts the
repo's `extension/` on sys.path, imports `librelex_ext.document`, builds a fixture document
in memory, and writes a JSON evidence file that pytest reads back.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

import pytest

EXT_DIR = Path(__file__).resolve().parents[2]
CANDIDATES = [
    os.environ.get("SOFFICE", ""),
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    shutil.which("soffice") or "",
    "/opt/libreoffice26.8/program/soffice",
    "/usr/lib/libreoffice/program/soffice",
]

PREAMBLE = '''
import json, os, sys, traceback
sys.path.insert(0, {ext_dir!r})
import uno
from com.sun.star.beans import PropertyValue
from com.sun.star.text.ControlCharacter import PARAGRAPH_BREAK
from librelex_ext.document import DocumentAdapter, DocumentActionError, has_markdown_filter, lo_version

EVIDENCE = {evidence!r}


def prop(name, value):
    p = PropertyValue()
    p.Name, p.Value = name, value
    return p


def new_doc(ctx):
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    return desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, (prop("Hidden", True),))


def fixture_doc(ctx):
    """p:0 with two citations; p:1 with a footnote; a 2x2 table; p:2."""
    doc = new_doc(ctx)
    text = doc.Text
    cur = text.createTextCursor()
    text.insertString(cur, "Primo paragrafo con art. 2043 c.c. e Cass. n. 12345/2024.", False)
    text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
    text.insertString(cur, "Secondo paragrafo", False)
    fn = doc.createInstance("com.sun.star.text.Footnote")
    text.insertTextContent(cur, fn, False)
    fn.setString("Cfr. Cass. sez. III n. 12345/2024.")
    text.insertString(cur, " con nota.", False)
    text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
    table = doc.createInstance("com.sun.star.text.TextTable")
    table.initialize(2, 2)
    text.insertTextContent(cur, table, False)
    table.getCellByName("A1").setString("cella A1")
    table.getCellByName("B2").setString("cella B2 con art. 1 c.p.")
    cur.gotoEnd(False)
    text.insertString(cur, "Terzo paragrafo.", False)
    return doc


def paragraph_texts(text):
    out = []
    enum = text.createEnumeration()
    while enum.hasMoreElements():
        el = enum.nextElement()
        if el.supportsService("com.sun.star.text.Paragraph"):
            out.append([el.ParaStyleName, el.getString()])
        else:
            out.append(["<table>", ""])
    return out


def redlines(doc):
    out = []
    enum = doc.Redlines.createEnumeration()
    while enum.hasMoreElements():
        r = enum.nextElement()
        out.append([r.RedlineType, r.RedlineAuthor])
    return out


def annotations(doc):
    out = []
    enum = doc.TextFields.createEnumeration()
    while enum.hasMoreElements():
        f = enum.nextElement()
        if f.supportsService("com.sun.star.text.TextField.Annotation"):
            anchor = f.getAnchor()
            out.append({{"author": f.Author, "content": f.Content,
                         "anchor": anchor.getString() if anchor is not None else None}})
    return out
'''

RUNNER = '''

def main(*args):
    ctx = uno.getComponentContext()
    out = {}
    try:
        probe(ctx, out)
    except Exception:
        out["traceback"] = traceback.format_exc()
    finally:
        with open(EVIDENCE, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, default=str)
        ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx).terminate()


g_exportedScripts = (main,)
'''


def soffice_path() -> str | None:
    for c in CANDIDATES:
        if c and Path(c).is_file():
            return c
    return None


@pytest.fixture(scope="session")
def soffice() -> str:
    path = soffice_path()
    if path is None:
        pytest.skip("LibreOffice (soffice) not found; set SOFFICE to its path")
    return path


def run_probe(soffice: str, name: str, body: str, timeout: int = 120,
              env: dict[str, str] | None = None) -> dict:
    profile = Path(tempfile.mkdtemp(prefix="librelex-lo-"))
    scripts = profile / "user" / "Scripts" / "python"
    scripts.mkdir(parents=True)
    evidence = profile / f"{name}.json"
    macro = (PREAMBLE.format(ext_dir=str(EXT_DIR), evidence=str(evidence))
             + textwrap.dedent(body) + RUNNER)
    (scripts / f"{name}.py").write_text(macro, encoding="utf-8")
    url = f"vnd.sun.star.script:{name}.py$main?language=Python&location=user"
    proc = subprocess.Popen(
        [soffice, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--norestore",
         "--nologo", url], env={**os.environ, **(env or {})})
    try:
        proc.wait(timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
        pytest.fail(f"soffice did not finish probe {name} within {timeout}s")
    if not evidence.exists():
        pytest.fail(f"probe {name} wrote no evidence (soffice exit code {proc.returncode})")
    data = json.loads(evidence.read_text(encoding="utf-8"))
    if "traceback" in data:
        pytest.fail(f"probe {name} raised:\n{data['traceback']}")
    return data
```

Mark every headless test module with `pytestmark = pytest.mark.headless`.

- [ ] **Step 2: Write the failing headless tests for the reading actions**

`extension/tests/headless/test_read.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from tests.headless.conftest import run_probe

pytestmark = pytest.mark.headless


def test_info_paragraphs_footnotes_tables_and_find(soffice):
    out = run_probe(soffice, "read_all", '''
    def probe(ctx, out):
        doc = fixture_doc(ctx)
        a = DocumentAdapter(ctx, doc)
        out["version"] = lo_version(ctx)
        out["markdown"] = has_markdown_filter(ctx)
        out["info"] = a.get_document_info()
        out["all"] = a.read_paragraphs(None, None)
        out["first"] = a.read_paragraphs(0, 1)
        out["find_all"] = a.find_text("art. 1 c.p.", None)
        out["find_in"] = a.find_text("Cass.", "fn:1/p:0")
        out["missing"] = None
        try:
            a.find_text("x", "p:99")
        except DocumentActionError as e:
            out["missing"] = str(e)
        doc.close(True)
    ''')
    assert out["version"].startswith("26.") and out["markdown"] is True
    info = out["info"]
    assert info["paragraph_count"] == 3 and info["has_selection"] is False
    assert info["lo_version"] == out["version"] and info["has_markdown_filter"] is True
    ids = [p["id"] for p in out["all"]]
    assert ids[:3] == ["p:0", "p:1", "fn:1/p:0"]
    assert "t:0/c:A1/p:0" in ids and "t:0/c:B2/p:0" in ids and ids[-1] == "p:2"
    by_id = {p["id"]: p for p in out["all"]}
    assert by_id["p:0"]["text"].startswith("Primo paragrafo") and by_id["p:0"]["kind"] == "body"
    assert by_id["fn:1/p:0"] == {"id": "fn:1/p:0", "text": "Cfr. Cass. sez. III n. 12345/2024.",
                                 "style": by_id["fn:1/p:0"]["style"], "kind": "footnote"}
    assert by_id["t:0/c:B2/p:0"]["kind"] == "table_cell"
    assert by_id["p:2"]["text"] == "Terzo paragrafo."
    assert [p["id"] for p in out["first"]] == ["p:0"]
    assert out["find_all"] == [{"anchor": {"paragraph_id": "t:0/c:B2/p:0", "start": 13, "end": 24},
                                "text": "art. 1 c.p."}]
    assert out["find_in"][0]["anchor"] == {"paragraph_id": "fn:1/p:0", "start": 5, "end": 10}
    assert "p:99" in out["missing"]


def test_selection_and_goto(soffice):
    out = run_probe(soffice, "read_selection", '''
    def probe(ctx, out):
        doc = fixture_doc(ctx)
        a = DocumentAdapter(ctx, doc)
        out["empty"] = a.read_selection()
        a.goto("p:1")
        vc = doc.getCurrentController().getViewCursor()
        vc.goRight(8, False)          # after "Secondo "
        vc.goRight(9, True)           # select "paragrafo"
        out["sel"] = a.read_selection()
        out["info"] = a.get_document_info()
        a.goto("fn:1/p:0")
        out["fn_sel"] = a.read_selection()
        vc = doc.getCurrentController().getViewCursor()
        vc.goRight(4, True)
        out["fn_sel2"] = a.read_selection()
        doc.close(True)
    ''')
    assert out["empty"] == {"text": "", "anchor": None}
    assert out["sel"] == {"text": "paragrafo", "anchor": {"paragraph_id": "p:1", "start": 8, "end": 17}}
    assert out["info"]["has_selection"] is True and out["info"]["cursor_paragraph"] == "p:1"
    assert out["fn_sel"]["text"] == ""
    assert out["fn_sel2"] == {"text": "Cfr.", "anchor": {"paragraph_id": "fn:1/p:0", "start": 0, "end": 4}}
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `cd extension && uv run pytest tests/headless/test_read.py -q -x`
Expected: FAIL inside the macro with `ModuleNotFoundError: librelex_ext.document` reported through the evidence traceback (proves the harness itself works: profile, macro, evidence). If instead soffice is not found, the test is skipped: set `SOFFICE`.

- [ ] **Step 4: Implement the reading half of `document.py`**

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Document adapter: the nine document actions of spec §5.3 on one Writer model, over UNO.

Runs on the UI thread. Imports nothing from the package so the headless test macros can
import it alone. Ids (spec §5.3): p:<i> body paragraphs (tables not counted),
fn:<n>/p:<i> footnote paragraphs (n = 1-based footnote number in document order),
t:<t>/c:<cell>/p:<i> table-cell paragraphs.
"""
from __future__ import annotations

import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime

import uno
from com.sun.star.beans import PropertyValue
from com.sun.star.text.ControlCharacter import PARAGRAPH_BREAK

PARAGRAPH = "com.sun.star.text.Paragraph"
TABLE = "com.sun.star.text.TextTable"
ANNOTATION = "com.sun.star.text.TextField.Annotation"
PROFILE_NODE = "/org.openoffice.UserProfile/Data"


class DocumentActionError(Exception):
    """Reported to the core as doc_result ok=false."""


def prop(name, value):
    p = PropertyValue()
    p.Name, p.Value = name, value
    return p


def _config_access(ctx, nodepath, update=False):
    provider = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.configuration.ConfigurationProvider", ctx)
    service = ("com.sun.star.configuration.ConfigurationUpdateAccess" if update
               else "com.sun.star.configuration.ConfigurationAccess")
    return provider.createInstanceWithArguments(service, (prop("nodepath", nodepath),))


def lo_version(ctx) -> str:
    try:
        return str(_config_access(ctx, "/org.openoffice.Setup/Product").getByName(
            "ooSetupVersionAboutBox"))
    except Exception:
        return ""


def has_markdown_filter(ctx) -> bool:
    try:
        ff = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.document.FilterFactory", ctx)
        return bool(ff.hasByName("Markdown") or ff.hasByName("Markdown (Writer)"))
    except Exception:
        return False


class Entry:
    __slots__ = ("id", "para", "container", "kind", "style", "body_index")

    def __init__(self, id, para, container, kind, body_index):
        self.id, self.para, self.container = id, para, container
        self.kind, self.body_index = kind, body_index
        self.style = para.ParaStyleName

    def as_dict(self) -> dict:
        return {"id": self.id, "text": self.para.getString(), "style": self.style, "kind": self.kind}


def _paragraphs_of(container) -> list:
    """Paragraph elements of an XText, tables skipped."""
    out = []
    enum = container.createEnumeration()
    while enum.hasMoreElements():
        el = enum.nextElement()
        if el.supportsService(PARAGRAPH):
            out.append(el)
    return out


class DocumentAdapter:
    def __init__(self, ctx, model):
        self.ctx = ctx
        self.doc = model

    # --- indexing ------------------------------------------------------------
    def _index(self) -> list[Entry]:
        entries: list[Entry] = []
        body = self.doc.getText()
        p_i = fn_n = t_i = 0
        enum = body.createEnumeration()
        while enum.hasMoreElements():
            el = enum.nextElement()
            if el.supportsService(PARAGRAPH):
                entries.append(Entry(f"p:{p_i}", el, body, "body", p_i))
                portions = el.createEnumeration()
                while portions.hasMoreElements():
                    por = portions.nextElement()
                    if por.TextPortionType == "Footnote":
                        fn_n += 1
                        fn = por.Footnote
                        for j, fp in enumerate(_paragraphs_of(fn)):
                            entries.append(Entry(f"fn:{fn_n}/p:{j}", fp, fn, "footnote", p_i))
                p_i += 1
            elif el.supportsService(TABLE):
                for name in el.getCellNames():
                    cell = el.getCellByName(name)
                    for j, cp in enumerate(_paragraphs_of(cell)):
                        entries.append(Entry(f"t:{t_i}/c:{name}/p:{j}", cp, cell, "table_cell", p_i))
                t_i += 1
        return entries

    def _entry(self, paragraph_id: str) -> Entry:
        for e in self._index():
            if e.id == paragraph_id:
                return e
        raise DocumentActionError(f"paragrafo non trovato: {paragraph_id}")

    def _entry_at(self, rng) -> Entry | None:
        """The paragraph containing the start of `rng` (same XText required)."""
        best = None
        for e in self._index():
            try:
                cmp = e.container.compareRegionStarts(e.para.getStart(), rng.getStart())
            except Exception:
                continue           # rng lives in another XText (footnote, cell, body)
            if cmp >= 0:           # paragraph starts at or before rng
                best = e
        return best

    @staticmethod
    def _offset_in_paragraph(entry: Entry, rng) -> int:
        cur = entry.container.createTextCursorByRange(rng.getStart())
        cur.gotoStartOfParagraph(True)
        return len(cur.getString())

    def _prefix_for(self, container, sample_range) -> str:
        """Id prefix ("p:", "fn:1/p:", "t:0/c:A1/p:") of the XText holding sample_range."""
        e = self._entry_at(sample_range)
        if e is None:
            raise DocumentActionError("posizione fuori dal testo del documento")
        return e.id.rsplit(":", 1)[0] + ":"

    def _view_cursor(self):
        controller = self.doc.getCurrentController()
        if controller is None:
            raise DocumentActionError("documento senza vista")
        return controller.getViewCursor()

    def _first_selection_range(self):
        sel = self.doc.getCurrentSelection()
        if sel is None or not sel.supportsService("com.sun.star.text.TextRanges") or sel.getCount() == 0:
            return None
        return sel.getByIndex(0)

    # --- reading actions -----------------------------------------------------
    def get_document_info(self) -> dict:
        entries = self._index()
        sel = self.read_selection()
        cursor = None
        try:
            e = self._entry_at(self._view_cursor().getStart())
            cursor = e.id if e else None
        except DocumentActionError:
            pass
        return {"title": self.doc.getTitle() or "", "url": self.doc.getURL() or "",
                "paragraph_count": sum(1 for e in entries if e.kind == "body"),
                "has_selection": bool(sel["text"]), "cursor_paragraph": cursor,
                "lo_version": lo_version(self.ctx),
                "has_markdown_filter": has_markdown_filter(self.ctx)}

    def read_selection(self) -> dict:
        rng = self._first_selection_range()
        if rng is None:
            return {"text": "", "anchor": None}
        text = rng.getString()
        if not text:
            return {"text": "", "anchor": None}
        entry = self._entry_at(rng)
        if entry is None:
            return {"text": text, "anchor": None}
        start = self._offset_in_paragraph(entry, rng)
        return {"text": text, "anchor": {"paragraph_id": entry.id, "start": start,
                                         "end": start + len(text)}}

    def read_paragraphs(self, from_=None, to=None) -> list[dict]:
        lo = int(from_) if from_ is not None else 0
        hi = int(to) if to is not None else None
        out = []
        for e in self._index():
            if e.body_index < lo or (hi is not None and e.body_index >= hi):
                continue
            out.append(e.as_dict())
        return out

    def find_text(self, query: str, paragraph_id=None) -> list[dict]:
        if not query:
            return []
        entries = [self._entry(paragraph_id)] if paragraph_id else self._index()
        out = []
        for e in entries:
            text, pos = e.para.getString(), 0
            while (pos := text.find(query, pos)) != -1:
                out.append({"anchor": {"paragraph_id": e.id, "start": pos, "end": pos + len(query)},
                            "text": query})
                pos += len(query)
        return out

    def goto(self, paragraph_id: str) -> None:
        entry = self._entry(paragraph_id)
        self._view_cursor().gotoRange(entry.para.getStart(), False)
```

Keep `os`, `re`, `tempfile`, `contextmanager`, `datetime`, `uno`, `PARAGRAPH_BREAK`, `PROFILE_NODE`, `ANNOTATION` imported/defined now: Tasks 7-8 use them (ruff will flag unused imports until then; add `# noqa: F401` on those lines and remove the markers in Task 8).

- [ ] **Step 5: Run the headless tests**

Run: `cd extension && uv run pytest tests/headless/test_read.py -q -x`
Expected: 2 passed (each probe starts soffice: about 5-10 s per test). If an assertion about the fixture layout fails (for example the table lands before `p:2` differently), inspect `out["all"]` in the failure output: the adapter contract (ids in document order, footnotes after their paragraph, cells with `t:/c:/p:` ids, `paragraph_count` counting body paragraphs only) is what must hold; adjust the fixture builder in `conftest.py` only if the fixture itself is not what its docstring says, and record the observed behaviour in the test docstring.

- [ ] **Step 6: Lint and commit**

Run: `cd extension && uv run ruff check . && uv run pytest -q`

```bash
git add extension/librelex_ext/document.py extension/tests/headless
git commit -m "feat(extension): document adapter reading actions and the headless macro test harness" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 7: Document adapter, writing actions (tracked Markdown insertion)

**Files:**
- Modify: `extension/librelex_ext/document.py` (add the writing methods to `DocumentAdapter`)
- Create: `extension/tests/headless/test_write.py`

**Interfaces:**
- Consumes: Task 6 internals (`_index`, `_entry`, `_entry_at`, `_prefix_for`, `_paragraphs_of`, `_view_cursor`, `_first_selection_range`, `_config_access`, `PARAGRAPH_BREAK`).
- Produces: `insert_markdown(where, markdown, undo_label, bookmark=None, author=None) -> {"from_id", "to_id"}`; `replace_selection(markdown, undo_label) -> {"from_id", "to_id"}`; internals reused by Task 8: `_identity(author)` context manager, `_undo(label)` context manager, `_recording(on: bool)` context manager.

Behaviour (spec §5.4, Assumption 1 and 2 results):
1. Target cursor: `cursor` = view cursor position (any XText: body, footnote, cell), `end` = end of body text, `after:<id>` = end of that paragraph.
2. Under `RecordChanges` and the requested identity, an empty paragraph is prepared at the target (paragraph break inserted unless the cursor already sits in an empty paragraph; a second break pushes any remainder text to the next paragraph), because the first Markdown paragraph merges into the cursor paragraph.
3. The markdown (a trailing newline enforced) goes to a 0600 file in a fresh 0700 temp dir, `insertDocumentFromURL(url, FilterName="Markdown")` at the prepared paragraph, file and dir removed in `finally`.
4. Recording is switched off for the cleanup: the trailing empty paragraph the filter leaves is removed; if the markdown starts with `#`/`##`/... or `>`, the first inserted paragraph gets `Heading N` / `Quotations` (the merge loses the first paragraph's style); the bookmark spans the inserted paragraphs (name made unique with `_2`, `_3` if taken).
5. Everything is wrapped in one undo context named `undo_label`; `RecordChanges` and the profile identity are restored in `finally`.

- [ ] **Step 1: Write the failing headless tests**

`extension/tests/headless/test_write.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from tests.headless.conftest import run_probe

pytestmark = pytest.mark.headless

MD = "**Art. 2043 c.c.**\n\n> Qualunque fatto doloso o colposo.\n> Secondo comma.\n\n*Testo vigente al 7 settembre 2026, fonte Normattiva, https://x*\n"


def test_insert_at_cursor_end_of_paragraph_is_one_tracked_insert_with_author(soffice):
    out = run_probe(soffice, "write_cursor", '''
    def probe(ctx, out):
        doc = fixture_doc(ctx)
        a = DocumentAdapter(ctx, doc)
        acc = a._profile_access(update=False)
        out["identity_before"] = [acc.getPropertyValue("givenname"), acc.getPropertyValue("sn")]
        vc = doc.getCurrentController().getViewCursor()
        a.goto("p:0")
        cur = doc.Text.createTextCursor(); cur.gotoStart(False); cur.gotoEndOfParagraph(False)
        vc.gotoRange(cur, False)
        out["record_before"] = doc.RecordChanges
        out["result"] = a.insert_markdown("cursor", %r, "LibreLex: inserisci art. 2043 c.c.",
                                          bookmark="LibreLex.norma.test", author="LibreLex")
        out["record_after"] = doc.RecordChanges
        out["paragraphs"] = paragraph_texts(doc.Text)
        out["redlines"] = redlines(doc)
        out["bookmarks"] = list(doc.Bookmarks.getElementNames())
        bm = doc.Bookmarks.getByName("LibreLex.norma.test")
        out["bookmark_text"] = bm.getAnchor().getString()
        out["undo_title"] = doc.getUndoManager().getCurrentUndoActionTitle()
        acc = a._profile_access(update=False)
        out["identity_after"] = [acc.getPropertyValue("givenname"), acc.getPropertyValue("sn")]
        out["all"] = [p["id"] for p in a.read_paragraphs(None, None)]
        doc.close(True)
    ''' % MD)
    assert out["result"] == {"from_id": "p:1", "to_id": "p:3"}
    paras = out["paragraphs"]
    assert paras[0][1].startswith("Primo paragrafo")
    assert paras[1][1] == "Art. 2043 c.c." and paras[2][0] == "Quotations"
    assert paras[2][1] == "Qualunque fatto doloso o colposo. Secondo comma." or \
        paras[2][1].startswith("Qualunque fatto doloso o colposo.")
    assert paras[3][1].startswith("Testo vigente al 7 settembre 2026")
    assert paras[4][1].startswith("Secondo paragrafo")          # no stray empty paragraph
    assert out["redlines"] and all(t == "Insert" and a == "LibreLex" for t, a in out["redlines"])
    assert out["record_before"] is False and out["record_after"] is False
    assert out["identity_after"] == out["identity_before"]
    assert "LibreLex.norma.test" in out["bookmarks"]
    assert out["bookmark_text"].startswith("Art. 2043 c.c.") and "Testo vigente" in out["bookmark_text"]
    assert out["undo_title"] == "LibreLex: inserisci art. 2043 c.c."
    assert out["all"][:5] == ["p:0", "p:1", "p:2", "p:3", "p:4"]


def test_insert_mid_paragraph_heading_style_and_end_and_no_author(soffice):
    out = run_probe(soffice, "write_variants", '''
    def probe(ctx, out):
        doc = fixture_doc(ctx)
        a = DocumentAdapter(ctx, doc)
        vc = doc.getCurrentController().getViewCursor()
        a.goto("p:0")
        vc.goRight(6, False)                     # inside "Primo |paragrafo ..."
        doc.RecordChanges = True                  # already on: must stay on afterwards
        out["mid"] = a.insert_markdown("cursor", "# Titolo\\n\\nCorpo.\\n", "LibreLex: test", None, None)
        out["record_after"] = doc.RecordChanges
        out["paragraphs"] = paragraph_texts(doc.Text)
        out["redline_authors"] = sorted(set(a for _, a in redlines(doc)))
        doc.RecordChanges = False
        out["end"] = a.insert_markdown("end", "Coda.\\n", "LibreLex: coda", "LibreLex.norma.test", "LibreLex")
        out["end2"] = a.insert_markdown("end", "Coda2.\\n", "LibreLex: coda", "LibreLex.norma.test", "LibreLex")
        out["bookmarks"] = sorted(doc.Bookmarks.getElementNames())
        out["tail"] = paragraph_texts(doc.Text)[-3:]
        out["after"] = a.insert_markdown("after:p:0", "Dopo.\\n", "LibreLex: dopo", None, None)
        out["p1"] = paragraph_texts(doc.Text)[1][1]
        doc.close(True)
    ''')
    assert out["mid"] == {"from_id": "p:1", "to_id": "p:2"}
    paras = out["paragraphs"]
    assert paras[0][1] == "Primo "
    assert paras[1] == ["Heading 1", "Titolo"] and paras[2][1] == "Corpo."
    assert paras[3][1].startswith("paragrafo con art. 2043")
    assert out["record_after"] is True
    assert out["redline_authors"] != ["LibreLex"]                # author=None keeps the user identity
    assert out["end"]["from_id"] == out["end"]["to_id"] and out["end2"]["from_id"] != out["end"]["from_id"]
    assert out["bookmarks"] == ["LibreLex.norma.test", "LibreLex.norma.test_2"]
    assert [t for _, t in out["tail"]][-2:] == ["Coda.", "Coda2."]
    assert out["after"] == {"from_id": "p:1", "to_id": "p:1"} and out["p1"] == "Dopo."


def test_insert_inside_footnote_and_replace_selection(soffice):
    out = run_probe(soffice, "write_footnote_replace", '''
    def probe(ctx, out):
        doc = fixture_doc(ctx)
        a = DocumentAdapter(ctx, doc)
        a.goto("fn:1/p:0")
        vc = doc.getCurrentController().getViewCursor()
        vc.gotoEnd(False) if hasattr(vc, "gotoEnd") else vc.goRight(34, False)
        out["fn"] = a.insert_markdown("cursor", "Nota aggiunta.\\n", "LibreLex: nota", None, "LibreLex")
        out["fn_paras"] = [p for p in a.read_paragraphs(None, None) if p["id"].startswith("fn:")]
        a.goto("p:2")
        vc = doc.getCurrentController().getViewCursor()
        vc.goRight(16, True)                     # select "Terzo paragrafo."
        out["sel"] = a.read_selection()["text"]
        out["rep"] = a.replace_selection("Paragrafo riscritto.\\n", "LibreLex: riscrivi")
        out["redlines"] = redlines(doc)
        out["tail"] = paragraph_texts(doc.Text)[-2:]
        doc.close(True)
    ''')
    assert out["fn"] == {"from_id": "fn:1/p:1", "to_id": "fn:1/p:1"}
    assert [p["text"] for p in out["fn_paras"]] == ["Cfr. Cass. sez. III n. 12345/2024.", "Nota aggiunta."]
    assert out["sel"] == "Terzo paragrafo."
    assert out["rep"]["from_id"] == "p:3" and out["rep"]["to_id"] == "p:3"
    kinds = sorted(set(t for t, _ in out["redlines"]))
    assert kinds == ["Delete", "Insert"] and all(a == "LibreLex" for _, a in out["redlines"])
    assert out["tail"][-1][1] == "Paragrafo riscritto."
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd extension && uv run pytest tests/headless/test_write.py -q -x`
Expected: FAIL with `AttributeError: 'DocumentAdapter' object has no attribute '_profile_access'` in the evidence traceback.

- [ ] **Step 3: Implement the writing half**

Add to `DocumentAdapter` in `document.py`:

```python
    # --- context managers ----------------------------------------------------
    def _profile_access(self, update: bool):
        return _config_access(self.ctx, PROFILE_NODE, update=update)

    @contextmanager
    def _identity(self, author):
        """Temporarily sign tracked changes as `author` (spec §5.4 item 3); None = user identity."""
        if not author:
            yield
            return
        acc = self._profile_access(update=True)
        original = (acc.getPropertyValue("givenname"), acc.getPropertyValue("sn"))
        acc.setPropertyValue("givenname", author)
        acc.setPropertyValue("sn", "")
        acc.commitChanges()
        try:
            yield
        finally:
            acc.setPropertyValue("givenname", original[0])
            acc.setPropertyValue("sn", original[1])
            acc.commitChanges()

    @contextmanager
    def _undo(self, label: str):
        um = self.doc.getUndoManager()
        um.enterUndoContext(label)
        try:
            yield
        finally:
            um.leaveUndoContext()

    @contextmanager
    def _recording(self, on: bool):
        before = self.doc.RecordChanges
        self.doc.RecordChanges = on
        try:
            yield
        finally:
            self.doc.RecordChanges = before

    # --- writing actions -----------------------------------------------------
    def _target(self, where: str):
        """(collapsed cursor, container XText) for `cursor` | `end` | `after:<id>`."""
        if where == "cursor":
            vc = self._view_cursor()
            container = vc.getText()
            return container.createTextCursorByRange(vc.getStart()), container
        if where == "end":
            container = self.doc.getText()
            cur = container.createTextCursor()
            cur.gotoEnd(False)
            return cur, container
        if where.startswith("after:"):
            e = self._entry(where[len("after:"):])
            return e.container.createTextCursorByRange(e.para.getEnd()), e.container
        raise DocumentActionError(f"destinazione sconosciuta: {where}")

    @staticmethod
    def _prepare_empty_paragraph(cur, container) -> None:
        """Leave `cur` at the start of an empty paragraph (the filter merges its first
        paragraph into the cursor paragraph, spec §5.4 item 1)."""
        if not cur.isStartOfParagraph():
            container.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
        if not cur.isEndOfParagraph():           # remainder text: push it to the next paragraph
            container.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
            cur.goLeft(1, False)

    @staticmethod
    def _para_index(container, cur) -> int:
        paras = _paragraphs_of(container)
        best = 0
        for i, p in enumerate(paras):
            if container.compareRegionStarts(p.getStart(), cur.getStart()) >= 0:
                best = i
        return best

    @staticmethod
    def _insert_markdown_file(cur, markdown: str) -> None:
        if not markdown.endswith("\n"):
            markdown += "\n"                     # the filter then always adds one trailing empty paragraph
        tmpdir = tempfile.mkdtemp(prefix="librelex-")          # 0700 (spec §8.4)
        path = os.path.join(tmpdir, "insert.md")
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(markdown)
            cur.insertDocumentFromURL(uno.systemPathToFileUrl(path), (prop("FilterName", "Markdown"),))
        finally:
            try:
                os.unlink(path)
            finally:
                os.rmdir(tmpdir)

    @staticmethod
    def _remove_empty_paragraph(container, para) -> None:
        """Delete `para` (empty) by removing the paragraph break that precedes it."""
        c = container.createTextCursorByRange(para.getStart())
        c.goLeft(1, True)
        c.setString("")

    @staticmethod
    def _fix_first_style(para, markdown: str) -> None:
        first = next((ln for ln in markdown.splitlines() if ln.strip()), "")
        m = re.match(r"^(#{1,6})\s+", first)
        if m:
            want = f"Heading {len(m.group(1))}"
        elif first.startswith(">"):
            want = "Quotations"
        else:
            return
        if para.ParaStyleName != want:
            para.ParaStyleName = want

    def _unique_bookmark(self, name: str) -> str:
        marks = self.doc.getBookmarks()
        if not marks.hasByName(name):
            return name
        k = 2
        while marks.hasByName(f"{name}_{k}"):
            k += 1
        return f"{name}_{k}"

    def _add_bookmark(self, container, first, last, name: str) -> None:
        bm = self.doc.createInstance("com.sun.star.text.Bookmark")
        bm.setName(self._unique_bookmark(name))
        c = container.createTextCursorByRange(first.getStart())
        c.gotoRange(last.getEnd(), True)
        container.insertTextContent(c, bm, True)

    def _insert_block(self, cur, container, markdown, bookmark, author) -> tuple[int, int]:
        """Shared by insert_markdown and replace_selection; caller holds the undo context."""
        with self._identity(author):
            with self._recording(True):
                self._prepare_empty_paragraph(cur, container)
                i0 = self._para_index(container, cur)
                n0 = len(_paragraphs_of(container))
                self._insert_markdown_file(cur, markdown)
            with self._recording(False):          # cleanup must not become Delete/Format redlines
                paras = _paragraphs_of(container)
                last = i0 + (len(paras) - n0)
                if last > i0 and paras[last].getString() == "":
                    self._remove_empty_paragraph(container, paras[last])
                    last -= 1
                    paras = _paragraphs_of(container)
                self._fix_first_style(paras[i0], markdown)
                if bookmark:
                    self._add_bookmark(container, paras[i0], paras[last], bookmark)
        return i0, last

    def insert_markdown(self, where: str, markdown: str, undo_label: str,
                        bookmark=None, author=None) -> dict:
        cur, container = self._target(where)
        prefix = self._prefix_for(container, cur)
        with self._undo(undo_label):
            i0, last = self._insert_block(cur, container, markdown, bookmark, author)
        return {"from_id": f"{prefix}{i0}", "to_id": f"{prefix}{last}"}

    def replace_selection(self, markdown: str, undo_label: str) -> dict:
        rng = self._first_selection_range()
        if rng is None or not rng.getString():
            raise DocumentActionError("nessuna selezione da sostituire")
        container = rng.getText()
        prefix = self._prefix_for(container, rng)
        with self._undo(undo_label):
            with self._identity("LibreLex"), self._recording(True):
                cur = container.createTextCursorByRange(rng)
                cur.setString("")                 # tracked deletion (spec §5.3: deletion + insertion)
                cur.collapseToEnd()
            i0, last = self._insert_block(cur, container, markdown, None, "LibreLex")
        return {"from_id": f"{prefix}{i0}", "to_id": f"{prefix}{last}"}
```

- [ ] **Step 4: Run the headless tests and iterate on the evidence**

Run: `cd extension && uv run pytest tests/headless/test_write.py -q -x`
Expected: 3 passed. Known uncertainty to settle here (spec §5.4 item 6 says "to be settled in M1"): whether the first paragraph keeps its style when inserted into an empty paragraph. The test asserts the observable contract (`Heading 1` on the first inserted paragraph, no stray empty paragraph, one author on all redlines, identity restored). If a probe fails, read the `paragraphs` dump in the failure, fix the adapter (not the assertion), and note the LibreOffice behaviour in the method's docstring.

- [ ] **Step 5: Lint and commit**

Run: `cd extension && uv run ruff check . && uv run pytest -q`

```bash
git add extension/librelex_ext/document.py extension/tests/headless/test_write.py
git commit -m "feat(extension): tracked Markdown insertion with LibreLex author, undo context and bookmark" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 8: Document adapter, comments

**Files:**
- Modify: `extension/librelex_ext/document.py` (add `add_comment`, `remove_comments`)
- Create: `extension/tests/headless/test_comments.py`

**Interfaces:**
- Consumes: Task 6-7 internals (`_entry`, `_undo`, `_recording`, `ANNOTATION`).
- Produces: `add_comment(paragraph_id, start, end, expected_text, author, text) -> "exact" | "found" | "paragraph_start"`; `remove_comments(author) -> int`.

Behaviour (spec §5.5, Assumption 3 result): anchoring is tried on the core's offsets (`exact`), then by searching the paragraph string (`found`), and the cursor text is verified against `expected_text` before insertion; when the cursor text differs (footnote anchors count as one cursor step but render as their label in `getString()`), the paragraph is searched with the document's `XSearchable` starting at the paragraph start; if nothing works the comment is anchored at the paragraph start with a `[Posizione esatta non trovata nel paragrafo] ` prefix (`paragraph_start`). After every insertion `Anchor.getString()` is compared with `expected_text`; an orphan or mismatching field is disposed and the paragraph-start fallback applies. Comments are not revisions: `RecordChanges` is off during both actions; each action has its own undo context.

- [ ] **Step 1: Write the failing headless tests**

`extension/tests/headless/test_comments.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from tests.headless.conftest import run_probe

pytestmark = pytest.mark.headless

AUTHOR = "LibreLex · verifica"


def test_exact_found_footnote_and_paragraph_start(soffice):
    out = run_probe(soffice, "comments_anchor", '''
    def probe(ctx, out):
        doc = fixture_doc(ctx)
        a = DocumentAdapter(ctx, doc)
        doc.RecordChanges = True
        p0 = a.read_paragraphs(0, 1)[0]["text"]
        s = p0.index("art. 2043 c.c.")
        out["exact"] = a.add_comment("p:0", s, s + 14, "art. 2043 c.c.", %(author)r, "commento uno")
        out["found"] = a.add_comment("p:0", 0, 5, "Cass. n. 12345/2024", %(author)r, "commento due")
        out["fn"] = a.add_comment("fn:1/p:0", 5, 33, "Cass. sez. III n. 12345/2024", %(author)r, "in nota")
        out["cell"] = a.add_comment("t:0/c:B2/p:0", 13, 24, "art. 1 c.p.", %(author)r, "in cella")
        out["lost"] = a.add_comment("p:2", 0, 3, "testo che non esiste", %(author)r, "perso")
        out["annotations"] = annotations(doc)
        out["p0_after"] = a.read_paragraphs(0, 1)[0]["text"]
        out["redlines"] = redlines(doc)
        out["record"] = doc.RecordChanges
        doc.close(True)
    ''' % {"author": AUTHOR})
    assert (out["exact"], out["found"], out["fn"], out["cell"], out["lost"]) == (
        "exact", "found", "exact", "exact", "paragraph_start")
    anchors = {c["content"]: c["anchor"] for c in out["annotations"]}
    assert anchors["commento uno"] == "art. 2043 c.c."
    assert anchors["commento due"] == "Cass. n. 12345/2024"
    assert anchors["in nota"] == "Cass. sez. III n. 12345/2024"
    assert anchors["in cella"] == "art. 1 c.p."
    lost = [c for c in out["annotations"] if c["content"].endswith("perso")][0]
    assert lost["content"].startswith("[Posizione esatta non trovata nel paragrafo] ")
    assert all(c["author"] == AUTHOR for c in out["annotations"]) and len(out["annotations"]) == 5
    assert out["p0_after"].startswith("Primo paragrafo con art. 2043 c.c.")   # text intact
    assert out["redlines"] == [] and out["record"] is True


def test_anchor_survives_footnote_label_drift(soffice):
    out = run_probe(soffice, "comments_drift", '''
    def probe(ctx, out):
        doc = new_doc(ctx)
        text = doc.Text
        cur = text.createTextCursor()
        for i in range(10):                        # ten footnotes: the last label is "10" (2 chars)
            text.insertString(cur, "x", False)
            fn = doc.createInstance("com.sun.star.text.Footnote")
            text.insertTextContent(cur, fn, False)
            fn.setString("nota %%d" %% (i + 1))
        text.insertString(cur, " poi art. 2043 c.c. fine", False)
        a = DocumentAdapter(ctx, doc)
        p = a.read_paragraphs(0, 1)[0]["text"]
        s = p.index("art. 2043 c.c.")
        out["string_offset"] = s
        out["anchored"] = a.add_comment("p:0", s, s + 14, "art. 2043 c.c.", %(author)r, "drift")
        out["annotations"] = annotations(doc)
        doc.close(True)
    ''' % {"author": AUTHOR})
    assert out["anchored"] == "exact"
    assert out["annotations"] == [{"author": AUTHOR, "content": "drift", "anchor": "art. 2043 c.c."}]


def test_remove_comments_by_author_only(soffice):
    out = run_probe(soffice, "comments_remove", '''
    def probe(ctx, out):
        doc = fixture_doc(ctx)
        a = DocumentAdapter(ctx, doc)
        a.add_comment("p:0", 20, 34, "art. 2043 c.c.", %(author)r, "mio")
        a.add_comment("p:0", 20, 34, "art. 2043 c.c.", "Avv. Rossi", "suo")
        a.add_comment("fn:1/p:0", 5, 33, "Cass. sez. III n. 12345/2024", %(author)r, "mio in nota")
        out["removed"] = a.remove_comments(%(author)r)
        out["left"] = annotations(doc)
        out["removed_again"] = a.remove_comments(%(author)r)
        out["undo_title"] = doc.getUndoManager().getCurrentUndoActionTitle()
        doc.close(True)
    ''' % {"author": AUTHOR})
    assert out["removed"] == 2 and out["removed_again"] == 0
    assert out["left"] == [{"author": "Avv. Rossi", "content": "suo", "anchor": "art. 2043 c.c."}]
    assert out["undo_title"] == "LibreLex: rimuovi commenti"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd extension && uv run pytest tests/headless/test_comments.py -q -x`
Expected: FAIL with `AttributeError: ... 'add_comment'`.

- [ ] **Step 3: Implement the comment actions**

Add to `DocumentAdapter`:

```python
    # --- comments (spec §5.5) --------------------------------------------------
    @staticmethod
    def _now_struct():
        n = datetime.now()
        dt = uno.createUnoStruct("com.sun.star.util.DateTime")
        dt.Year, dt.Month, dt.Day = n.year, n.month, n.day
        dt.Hours, dt.Minutes, dt.Seconds, dt.NanoSeconds = n.hour, n.minute, n.second, 0
        dt.IsUTC = False
        return dt

    def _make_annotation(self, author: str, content: str):
        ann = self.doc.createInstance("com.sun.star.text.textfield.Annotation")
        ann.Author = author
        ann.Content = content
        ann.DateTimeValue = self._now_struct()
        return ann

    @staticmethod
    def _dispose_quietly(field) -> None:
        try:
            field.dispose()
        except Exception:
            pass

    def _search_in_paragraph(self, entry: Entry, needle: str):
        """Range of `needle` inside entry.para found by Writer itself, or None."""
        try:
            sd = self.doc.createSearchDescriptor()
            sd.SearchString = needle
            sd.SearchCaseSensitive = True
            sd.SearchRegularExpression = False
            found = self.doc.findNext(entry.para.getStart(), sd)
            if found is None:
                return None
            # accept only a hit that starts inside this paragraph
            if entry.container.compareRegionStarts(found.getStart(), entry.para.getEnd()) < 0:
                return None
            if entry.container.compareRegionStarts(entry.para.getStart(), found.getStart()) < 0:
                return None
            return found
        except Exception:
            return None

    def _range_for(self, entry: Entry, start: int, end: int, expected: str):
        """Cursor spanning `expected` in entry.para, via offsets first, then Writer's search."""
        cur = entry.container.createTextCursorByRange(entry.para.getStart())
        cur.goRight(start, False)
        cur.goRight(end - start, True)
        if cur.getString() == expected:
            return cur
        found = self._search_in_paragraph(entry, expected)
        if found is not None:
            return entry.container.createTextCursorByRange(found)
        return None

    def add_comment(self, paragraph_id: str, start: int, end: int, expected_text: str,
                    author: str, text: str) -> str:
        entry = self._entry(paragraph_id)
        s = entry.para.getString()
        anchored = "exact"
        if not (0 <= start < end <= len(s) and s[start:end] == expected_text):
            pos = s.find(expected_text) if expected_text else -1
            if pos != -1:
                start, end, anchored = pos, pos + len(expected_text), "found"
            else:
                anchored = "paragraph_start"
        with self._undo("LibreLex: commento"), self._recording(False):
            if anchored != "paragraph_start":
                cur = self._range_for(entry, start, end, expected_text)
                if cur is not None:
                    ann = self._make_annotation(author, text)
                    try:
                        entry.container.insertTextContent(cur, ann, True)
                        anchor = ann.getAnchor()
                        ok = anchor is not None and anchor.getString() == expected_text
                    except Exception:
                        ok = False
                    if ok:
                        return anchored
                    self._dispose_quietly(ann)            # orphan rule (spec §5.5)
                anchored = "paragraph_start"
            ann = self._make_annotation(author, "[Posizione esatta non trovata nel paragrafo] " + text)
            cur = entry.container.createTextCursorByRange(entry.para.getStart())
            try:
                entry.container.insertTextContent(cur, ann, False)
            except Exception as e:
                self._dispose_quietly(ann)
                raise DocumentActionError(f"commento rifiutato da Writer: {e}") from e
        return anchored

    def remove_comments(self, author: str) -> int:
        targets = []
        enum = self.doc.getTextFields().createEnumeration()
        while enum.hasMoreElements():
            f = enum.nextElement()
            if f.supportsService(ANNOTATION) and f.Author == author:
                targets.append(f)
        with self._undo("LibreLex: rimuovi commenti"), self._recording(False):
            for f in targets:
                f.dispose()
        return len(targets)
```

Remove the `# noqa: F401` markers added in Task 6 (all imports are used now).

- [ ] **Step 4: Run the headless tests**

Run: `cd extension && uv run pytest tests/headless -q -x`
Expected: 8 passed (read, write, comments). If `findNext` never returns a hit inside a footnote or cell for the drift case, the drift test still passes through the offsets path only when the label is one character; the test with ten footnotes exists precisely to force the search path: fix the search (for example use `entry.container.createSearchDescriptor()` when the container itself is `XSearchable`) rather than weakening the assertion.

- [ ] **Step 5: Lint and commit**

Run: `cd extension && uv run ruff check . && uv run pytest -q`

```bash
git add extension/librelex_ext/document.py extension/tests/headless/test_comments.py
git commit -m "feat(extension): anchored Writer comments with verified anchors, orphan removal and removal by author" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 9: Sidebar panel, session registry and lifecycle

**Files:**
- Create: `extension/librelex_ext/layout.py` (pure: the control table), `extension/librelex_ext/registry.py`, `extension/librelex_ext/panel.py`
- Create: `extension/tests/test_layout.py`

**Interfaces:**
- Consumes: `Session`, `DocumentAdapter`, `lo_version`, `has_markdown_filter`, `paths.bridge_spec`, `paths.read_config`, `paths.write_template_if_missing`, `Bridge`.
- Produces: `layout.CONTROLS: list[Control]` (`Control(kind, name, x, y, w, h, props: dict)`), `layout.NOTICE`, `layout.ACTIONS: dict[button name, action command]`; `registry.session_for(ctx, model, factory) -> Session`, `registry.shutdown_all()`, `registry.ensure_terminate_listener(ctx)`; `panel.PanelFactory` (XUIElementFactory) and `panel.Panel` (XUIElement, XToolPanel, XSidebarPanel, XComponent, XActionListener, XItemListener, XCallback) implementing the `View` protocol.

Panel behaviour (spec §5.1, §11 M1 row):
- Controls, top to bottom: notice (fixed text), transcript (multi-line read-only edit), problems list (list box; selecting an item calls `session.goto_problem`), input line + "Invia" (disabled until M2), row "Verifica citazioni" / "Verifica selezione", row "Inserisci norma" / "Annulla", row "Ricerca" / "Redigi da modello" / "Rivedi selezione" (disabled until M2-M4), status line, usage line (empty in M1), "Impostazioni".
- "Inserisci norma": the input text is the reference when not empty, else the core falls back to the selection. "Verifica selezione" checks that a selection exists before sending. "Impostazioni": writes the config template if missing and prints the config path and the stderr log path in the transcript.
- All bridge events reach the UI thread through `queue.Queue` + `AsyncCallback`; `notify()` drains the queue into `session.handle_event`.
- Sessions live per document (`RuntimeUID`) in `registry`, survive the panel being closed and reopened (`bind`/`unbind`), and are shut down when the document is disposed or LibreOffice terminates.

- [ ] **Step 1: Write the layout table and its test**

`extension/librelex_ext/layout.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Static control table of the sidebar panel (dialog units). Pure data, unit-tested."""
from __future__ import annotations

from dataclasses import dataclass, field

NOTICE = "Le citazioni vanno sempre controllate dal professionista."
WIDTH = 190


@dataclass(frozen=True)
class Control:
    kind: str            # UnoControl<kind>Model
    name: str
    x: int
    y: int
    w: int
    h: int
    props: dict = field(default_factory=dict)


CONTROLS: list[Control] = [
    Control("FixedText", "Notice", 4, 4, 182, 16, {"Label": NOTICE, "MultiLine": True}),
    Control("Edit", "Transcript", 4, 22, 182, 150,
            {"MultiLine": True, "ReadOnly": True, "VScroll": True, "AutoVScroll": True}),
    Control("FixedText", "ProblemsLabel", 4, 174, 182, 10, {"Label": "Problemi (clic per andare al paragrafo)"}),
    Control("ListBox", "Problems", 4, 185, 182, 40, {"Dropdown": False}),
    Control("Edit", "Input", 4, 229, 142, 14, {}),
    Control("Button", "Send", 150, 229, 36, 14, {"Label": "Invia", "Enabled": False,
                                                 "HelpText": "La chat arriva con la versione M2"}),
    Control("Button", "VerifyDocument", 4, 247, 89, 16, {"Label": "Verifica citazioni"}),
    Control("Button", "VerifySelection", 97, 247, 89, 16, {"Label": "Verifica selezione"}),
    Control("Button", "InsertNorm", 4, 267, 89, 16, {"Label": "Inserisci norma"}),
    Control("Button", "Cancel", 97, 267, 89, 16, {"Label": "Annulla", "Enabled": False}),
    Control("Button", "Research", 4, 287, 58, 16, {"Label": "Ricerca", "Enabled": False}),
    Control("Button", "Draft", 66, 287, 58, 16, {"Label": "Redigi da modello", "Enabled": False}),
    Control("Button", "Review", 128, 287, 58, 16, {"Label": "Rivedi selezione", "Enabled": False}),
    Control("FixedText", "Status", 4, 307, 182, 20, {"Label": "Pronto", "MultiLine": True}),
    Control("FixedText", "Usage", 4, 329, 182, 10, {"Label": ""}),
    Control("Button", "Settings", 4, 343, 89, 16, {"Label": "Impostazioni"}),
]

# button name → action command handled by the panel
ACTIONS = {"VerifyDocument": "verify_document", "VerifySelection": "verify_selection",
           "InsertNorm": "insert_norm", "Cancel": "cancel", "Settings": "settings"}

# controls disabled while a request is running
BUSY_DISABLED = ("VerifyDocument", "VerifySelection", "InsertNorm")
```

`extension/tests/test_layout.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_ext.layout import ACTIONS, BUSY_DISABLED, CONTROLS, NOTICE, WIDTH


def test_controls_fit_the_panel_and_do_not_overlap():
    names = [c.name for c in CONTROLS]
    assert len(names) == len(set(names))
    for c in CONTROLS:
        assert 0 <= c.x and c.x + c.w <= WIDTH, c.name
    boxes = [(c.x, c.y, c.x + c.w, c.y + c.h) for c in CONTROLS]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (a, b)


def test_required_controls_and_copy():
    by = {c.name: c for c in CONTROLS}
    assert by["Notice"].props["Label"] == NOTICE == "Le citazioni vanno sempre controllate dal professionista."
    assert by["Transcript"].props["ReadOnly"] is True and by["Send"].props["Enabled"] is False
    for name in ("Research", "Draft", "Review"):
        assert by[name].props["Enabled"] is False
    assert set(ACTIONS) <= set(by) and set(BUSY_DISABLED) <= set(by)
    assert by["VerifyDocument"].props["Label"] == "Verifica citazioni"
    assert by["InsertNorm"].props["Label"] == "Inserisci norma" and by["Cancel"].props["Label"] == "Annulla"
```

Run: `cd extension && uv run pytest tests/test_layout.py -q` → expected FAIL (module missing), then create `layout.py` → PASS.

- [ ] **Step 2: Write `registry.py`**

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""One Session per open document, torn down with the document or with LibreOffice (spec §4.3)."""
from __future__ import annotations

import unohelper
from com.sun.star.frame import XTerminateListener
from com.sun.star.lang import XEventListener

_sessions: dict[str, object] = {}
_terminate_registered = False


class _ModelListener(unohelper.Base, XEventListener):
    def __init__(self, doc_id: str):
        self.doc_id = doc_id

    def disposing(self, event):
        session = _sessions.pop(self.doc_id, None)
        if session is not None:
            session.shutdown()


class _TerminateListener(unohelper.Base, XTerminateListener):
    def queryTermination(self, event):
        pass

    def notifyTermination(self, event):
        shutdown_all()

    def disposing(self, event):
        pass


def session_for(model, factory):
    """Return the live session of `model`, creating it with `factory()` on first use."""
    doc_id = model.RuntimeUID
    session = _sessions.get(doc_id)
    if session is None:
        session = factory()
        _sessions[doc_id] = session
        model.addEventListener(_ModelListener(doc_id))
    return session


def shutdown_all() -> None:
    for session in list(_sessions.values()):
        try:
            session.shutdown()
        except Exception:
            pass
    _sessions.clear()


def ensure_terminate_listener(ctx) -> None:
    global _terminate_registered
    if _terminate_registered:
        return
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    desktop.addTerminateListener(_TerminateListener())
    _terminate_registered = True
```

- [ ] **Step 3: Write `panel.py`**

```python
# -*- coding: utf-8 -*-
# Derived from LibreThinker (https://github.com/mihailthebuilder/librethinker-extension), MPL-2.0.
# This file stays under the Mozilla Public License 2.0.
"""Sidebar panel: XUIElement built on an XDL container window, controls added to the
container's own model (spec §5.1), bridge events delivered through AsyncCallback."""
import queue
from pathlib import Path

import uno
import unohelper
from com.sun.star.awt import XActionListener, XCallback, XItemListener
from com.sun.star.lang import XComponent
from com.sun.star.ui import LayoutSize, XSidebarPanel, XToolPanel, XUIElement, XUIElementFactory
from com.sun.star.ui.UIElementType import TOOLPANEL

from librelex_ext import EXTENSION_ID, layout, paths, registry
from librelex_ext.bridge import Bridge
from librelex_ext.document import DocumentAdapter, has_markdown_filter, lo_version
from librelex_ext.session import Session

PANEL_URL = "private:resource/toolpanel/LibreLexPanelFactory/Panel"
XDL_URL = f"vnd.sun.star.extension://{EXTENSION_ID}/dialogs/panel.xdl"
MAX_TRANSCRIPT = 40_000


def package_dir(ctx) -> Path:
    """Install directory of the .oxt, else the source checkout (development)."""
    try:
        pip = ctx.getValueByName("/singletons/com.sun.star.deployment.PackageInformationProvider")
        url = pip.getPackageLocation(EXTENSION_ID)
        if url:
            return Path(uno.fileUrlToSystemPath(url))
    except Exception:
        pass
    return Path(__file__).resolve().parents[1]


class PanelFactory(unohelper.Base, XUIElementFactory):
    def __init__(self, ctx):
        self.ctx = ctx

    def createUIElement(self, url, args):
        frame = parent = None
        for a in args:
            if a.Name == "Frame":
                frame = a.Value
            elif a.Name == "ParentWindow":
                parent = a.Value
        registry.ensure_terminate_listener(self.ctx)
        panel = Panel(self.ctx, frame, parent, url)
        panel.getRealInterface()
        panel.Window.Visible = True
        return panel


class Panel(unohelper.Base, XUIElement, XToolPanel, XSidebarPanel, XComponent,
            XActionListener, XItemListener, XCallback):
    def __init__(self, ctx, frame, parent, url):
        self.ctx, self.frame, self.parent, self.url = ctx, frame, parent, url
        self.window = None
        self.model = None
        self.queue: queue.Queue = queue.Queue()
        self.async_cb = ctx.ServiceManager.createInstanceWithContext(
            "com.sun.star.awt.AsyncCallback", ctx)
        self.session = None
        self._height = 0

    # --- XUIElement ------------------------------------------------------------
    def getRealInterface(self):
        if self.window is None:
            provider = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.awt.ContainerWindowProvider", self.ctx)
            self.window = provider.createContainerWindow(XDL_URL, "", self.parent, None)
            self.model = self.window.getModel()          # never setModel (spec §5.1)
            self._build_controls()
            self._height = self.window.getPosSize().Height
            self._attach_session()
        return self

    @property
    def Frame(self):
        return self.frame

    @property
    def ResourceURL(self):
        return self.url

    @property
    def Type(self):
        return TOOLPANEL

    # --- XToolPanel / XSidebarPanel --------------------------------------------
    @property
    def Window(self):
        return self.window

    def createAccessible(self, parent):
        return self

    def getHeightForWidth(self, width):
        h = self._height or 700
        return LayoutSize(h, -1, h)

    def getMinimalWidth(self):
        return 240

    # --- XComponent -------------------------------------------------------------
    def dispose(self):
        if self.session is not None:
            self.session.unbind()
            self.session = None

    def addEventListener(self, listener):
        pass

    def removeEventListener(self, listener):
        pass

    def disposing(self, event):
        pass

    # --- construction -----------------------------------------------------------
    def _build_controls(self):
        for c in layout.CONTROLS:
            m = self.model.createInstance(f"com.sun.star.awt.UnoControl{c.kind}Model")
            m.Name = c.name
            m.PositionX, m.PositionY, m.Width, m.Height = c.x, c.y, c.w, c.h
            for k, v in c.props.items():
                m.setPropertyValue(k, v)
            self.model.insertByName(c.name, m)
        for name, command in layout.ACTIONS.items():
            ctrl = self.window.getControl(name)
            ctrl.setActionCommand(command)
            ctrl.addActionListener(self)
        self.window.getControl("Problems").addItemListener(self)

    def _attach_session(self):
        model = self.frame.getController().getModel()
        ctx = self.ctx

        def make_session():
            adapter = DocumentAdapter(ctx, model)
            config = paths.read_config()

            def bridge_factory(on_event):
                return Bridge(paths.bridge_spec(package_dir(ctx), config), on_event)

            return Session(adapter, bridge_factory, doc_id=model.RuntimeUID,
                           lo_version=lo_version(ctx), has_markdown_filter=has_markdown_filter(ctx),
                           config_path=str(paths.config_path()))

        self.session = registry.session_for(model, make_session)
        self.session.bind(self, self._post)
        if not self.session.transcript:
            created = paths.write_template_if_missing()
            self.append(f"LibreLex-IT pronto. Configurazione: {paths.config_path()}"
                        + (" (creata ora con i valori predefiniti)" if created else ""))
            if not self.session.has_markdown_filter:
                self.append("Attenzione: questa versione di LibreOffice non ha il filtro Markdown "
                            "(serve 26.2 o successiva): l'inserimento di testo non funzionerà.")

    # --- bridge events: reader thread → UI thread ----------------------------------
    def _post(self, event):
        self.queue.put(event)
        self.async_cb.addCallback(self, None)

    def notify(self, data):                      # XCallback, UI thread
        if self.session is None:
            return
        while True:
            try:
                ev = self.queue.get_nowait()
            except queue.Empty:
                return
            self.session.handle_event(ev)

    # --- user actions -----------------------------------------------------------------
    def actionPerformed(self, event):           # XActionListener, UI thread
        if self.session is None:
            return
        cmd = event.ActionCommand
        if cmd == "verify_document":
            self.session.run_command("verify_citations", {"scope": "document"})
        elif cmd == "verify_selection":
            if not self.session.adapter.read_selection()["text"]:
                self.set_status("Seleziona prima il testo da verificare")
                return
            self.session.run_command("verify_citations", {"scope": "selection"})
        elif cmd == "insert_norm":
            reference = self.window.getControl("Input").getText().strip()
            self.session.run_command("insert_norm", {"reference": reference} if reference else {})
        elif cmd == "cancel":
            self.session.cancel()
        elif cmd == "settings":
            created = paths.write_template_if_missing()
            self.append(f"File di configurazione: {paths.config_path()}"
                        + (" (creato ora)" if created else "")
                        + f"\nLog del core: {paths.config_path().parent / 'core-stderr.log'}"
                        "\nModifica il file con un editor di testo e riavvia LibreOffice.")

    def itemStateChanged(self, event):          # XItemListener: problem selected
        if self.session is not None:
            self.session.goto_problem(self.window.getControl("Problems").getSelectedItemPos())

    # --- View protocol (session → controls) ---------------------------------------------
    def append(self, text):
        ctrl = self.window.getControl("Transcript")
        current = ctrl.getText()
        new = (current + ("\n" if current else "") + text)[-MAX_TRANSCRIPT:]
        ctrl.setText(new)

    def set_transcript(self, text):
        self.window.getControl("Transcript").setText(text[-MAX_TRANSCRIPT:])

    def set_status(self, text):
        self.model.getByName("Status").Label = text

    def set_busy(self, busy):
        for name in layout.BUSY_DISABLED:
            self.model.getByName(name).Enabled = not busy
        self.model.getByName("Cancel").Enabled = bool(busy)

    def set_problems(self, labels):
        self.model.getByName("Problems").StringItemList = tuple(labels)
```

- [ ] **Step 4: Static checks**

Run: `cd extension && uv run ruff check . && uv run pytest -q` (pure tests; the panel itself cannot be imported outside LibreOffice).
Then a syntax/import smoke inside soffice through the harness, appended to `extension/tests/headless/test_read.py`:

```python
def test_panel_module_imports_inside_libreoffice(soffice):
    out = run_probe(soffice, "panel_import", '''
    def probe(ctx, out):
        from librelex_ext import panel, registry
        out["urls"] = [panel.PANEL_URL, panel.XDL_URL]
        out["factory"] = type(panel.PanelFactory(ctx)).__name__
        registry.ensure_terminate_listener(ctx)
        out["pkg"] = str(panel.package_dir(ctx))
    ''')
    assert out["urls"] == ["private:resource/toolpanel/LibreLexPanelFactory/Panel",
                           "vnd.sun.star.extension://org.librelex.extension/dialogs/panel.xdl"]
    assert out["factory"] == "PanelFactory" and out["pkg"].endswith("/extension")
```

Run: `cd extension && uv run pytest tests/headless/test_read.py -q -x` → 3 passed.

- [ ] **Step 5: Commit**

```bash
git add extension/librelex_ext/layout.py extension/librelex_ext/registry.py extension/librelex_ext/panel.py extension/tests/test_layout.py extension/tests/headless/test_read.py
git commit -m "feat(extension): sidebar panel with quick actions, problem list navigation and per-document sessions" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 10: Packaging, install script, end-to-end headless test, docs and CI

**Files:**
- Create: `scripts/build_oxt.py`, `scripts/dev_install.sh`, `extension/tests/test_build_oxt.py`, `extension/tests/headless/test_e2e.py`
- Modify: `.github/workflows/ci.yml`, `README.md`, `NOTICE`, `.gitignore`

**Interfaces:**
- Produces: `python3 scripts/build_oxt.py [--out DIR]` prints the path of `LibreLex-IT-<version>.oxt` on its last stdout line and writes `<name>.sha256`; `scripts/dev_install.sh [--profile DIR]` builds and runs `unopkg add --force`.

- [ ] **Step 1: Write the build test**

`extension/tests/test_build_oxt.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_build_oxt_contains_extension_and_core(tmp_path):
    proc = subprocess.run([sys.executable, str(REPO / "scripts" / "build_oxt.py"), "--out", str(tmp_path)],
                          capture_output=True, text=True, check=True)
    oxt = Path(proc.stdout.strip().splitlines()[-1])
    assert oxt.name == "LibreLex-IT-0.1.0.oxt" and oxt.exists()
    names = set(zipfile.ZipFile(oxt).namelist())
    for required in ("META-INF/manifest.xml", "description.xml", "Sidebar.xcu", "Factories.xcu",
                     "dialogs/panel.xdl", "librelex_component.py", "librelex_ext/__init__.py",
                     "librelex_ext/panel.py", "librelex_ext/document.py",
                     "core/pyproject.toml", "core/uv.lock", "core/README.md",
                     "core/src/librelex_core/main.py", "core/src/librelex_core/protocol.py"):
        assert required in names, required
    assert not any("__pycache__" in n or n.startswith("tests/") or "/tests/" in n or n.endswith(".pyc")
                   for n in names)
    assert not any(n.startswith("core/.venv") or n == "pyproject.toml" for n in names)
    digest = hashlib.sha256(oxt.read_bytes()).hexdigest()
    assert (tmp_path / "LibreLex-IT-0.1.0.oxt.sha256").read_text().split()[0] == digest
```

Run: `cd extension && uv run pytest tests/test_build_oxt.py -q` → expected FAIL (script missing).

- [ ] **Step 2: Write `scripts/build_oxt.py`**

```python
#!/usr/bin/env python3
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Build dist/LibreLex-IT-<version>.oxt: the extension tree plus the core/ project (spec §9.3).

Stdlib only. The version is read from extension/librelex_ext/__init__.py and must match
description.xml. Prints the .oxt path as the last line.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXT = REPO / "extension"
CORE = REPO / "core"

EXT_EXCLUDE_DIRS = {"tests", "__pycache__", ".venv", ".pytest_cache", ".ruff_cache"}
EXT_EXCLUDE_FILES = {"pyproject.toml", "uv.lock", ".python-version", ".DS_Store"}
CORE_FILES = ["pyproject.toml", "uv.lock", "README.md"]


def version() -> str:
    init = (EXT / "librelex_ext" / "__init__.py").read_text(encoding="utf-8")
    v = re.search(r'^__version__ = "([^"]+)"', init, re.M).group(1)
    desc = (EXT / "description.xml").read_text(encoding="utf-8")
    dv = re.search(r'<version value="([^"]+)"', desc).group(1)
    if v != dv:
        sys.exit(f"version mismatch: __init__.py {v} vs description.xml {dv}")
    return v


def ext_files():
    for p in sorted(EXT.rglob("*")):
        rel = p.relative_to(EXT)
        if not p.is_file() or set(rel.parts[:-1]) & EXT_EXCLUDE_DIRS or rel.name in EXT_EXCLUDE_FILES:
            continue
        if rel.suffix == ".pyc":
            continue
        yield p, rel.as_posix()


def core_files():
    for name in CORE_FILES:
        yield CORE / name, f"core/{name}"
    for p in sorted((CORE / "src").rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        yield p, "core/" + p.relative_to(CORE).as_posix()


def build(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    oxt = out_dir / f"LibreLex-IT-{version()}.oxt"
    with zipfile.ZipFile(oxt, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in list(ext_files()) + list(core_files()):
            z.write(src, arc)
    digest = hashlib.sha256(oxt.read_bytes()).hexdigest()
    (out_dir / (oxt.name + ".sha256")).write_text(f"{digest}  {oxt.name}\n", encoding="utf-8")
    return oxt


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the LibreLex-IT .oxt")
    ap.add_argument("--out", type=Path, default=REPO / "dist")
    args = ap.parse_args()
    oxt = build(args.out)
    print(f"sha256: {(args.out / (oxt.name + '.sha256')).read_text().split()[0]}")
    print(oxt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Run: `cd extension && uv run pytest tests/test_build_oxt.py -q` → 1 passed.

- [ ] **Step 3: Write `scripts/dev_install.sh`**

```bash
#!/usr/bin/env bash
# Build the .oxt and install it with unopkg (spec §9.2).
#
# Run this from a Terminal, not from the automation harness: unopkg's helper process is
# killed there. Default target is your real LibreOffice profile; pass --profile DIR to use
# a private one (e.g. --profile "$PWD/spike/lo_profile"). Restart LibreOffice afterwards.
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
UNOPKG="${UNOPKG:-/Applications/LibreOffice.app/Contents/MacOS/unopkg}"
if [ ! -x "$UNOPKG" ]; then
  UNOPKG="$(command -v unopkg || true)"
fi
if [ -z "$UNOPKG" ]; then
  echo "unopkg not found: set UNOPKG=/path/to/unopkg" >&2
  exit 1
fi

PROFILE_ARGS=()
if [ "${1:-}" = "--profile" ]; then
  [ -n "${2:-}" ] || { echo "--profile needs a directory" >&2; exit 1; }
  mkdir -p "$2"
  PROFILE_ARGS=("-env:UserInstallation=file://$(cd "$2" && pwd)")
fi

OXT="$(python3 "$REPO/scripts/build_oxt.py" | tail -n 1)"
echo "built $OXT"

# ${arr[@]+"${arr[@]}"} keeps bash 3.2 (macOS) happy under set -u when the array is empty.
"$UNOPKG" ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} remove org.librelex.extension >/dev/null 2>&1 || true
"$UNOPKG" ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} add --force "$OXT"
"$UNOPKG" ${PROFILE_ARGS[@]+"${PROFILE_ARGS[@]}"} list | grep -A 4 "org.librelex.extension" || true

echo
echo "Installed. Quit LibreOffice completely and start it again, then in Writer:"
echo "  View > Sidebar > LibreLex (deck) > Copilota legale."
echo "First use runs 'uv run' on the bundled core: it needs network access once to build its environment."
```

`chmod +x scripts/dev_install.sh scripts/build_oxt.py`.

- [ ] **Step 4: Write the end-to-end headless test**

`extension/tests/headless/test_e2e.py` (the real core and the fake legal server, driven from inside soffice through `Session`, `Bridge` and `DocumentAdapter`; no panel, no AsyncCallback: the macro drains the bridge queue itself):

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""M1 exit criterion, headless: insert a norm and verify citations through the real core."""
import shutil

import pytest

from librelex_ext import paths
from tests.headless.conftest import run_probe

pytestmark = [pytest.mark.headless,
              pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")]

CORE = paths.repo_core_dir()


def test_insert_norm_and_verify_from_inside_libreoffice(soffice, tmp_path):
    cfg = tmp_path / "config.toml"
    server = CORE / "tests" / "fake_legal_server.py"
    cfg.write_text(
        "[mcp_legal_it]\nmode = \"local\"\n"
        f"command = [\"uv\", \"run\", \"--project\", \"{CORE}\", \"python\", \"{server}\"]\n",
        encoding="utf-8")
    uv_dir = str(paths.Path(shutil.which("uv")).parent)
    out = run_probe(soffice, "e2e", '''
    import os, queue
    from librelex_ext import paths
    from librelex_ext.bridge import Bridge
    from librelex_ext.session import Session

    class RecView:
        def __init__(self):
            self.lines, self.status, self.problems = [], [], None
        def append(self, t): self.lines.append(t)
        def set_transcript(self, t): pass
        def set_status(self, t): self.status.append(t)
        def set_busy(self, b): pass
        def set_problems(self, labels): self.problems = labels

    def pump(session, events, until_state="ready", timeout=180):
        import time
        deadline = time.time() + timeout
        while session.state != until_state and time.time() < deadline:
            try:
                ev = events.get(timeout=1)
            except queue.Empty:
                continue
            session.handle_event(ev)
        return session.state

    def probe(ctx, out):
        doc = new_doc(ctx)
        text = doc.Text
        cur = text.createTextCursor()
        text.insertString(cur, "Premessa. Si veda l'art. 2043 c.c. e Cass. n. 99999/2024.", False)
        adapter = DocumentAdapter(ctx, doc)
        events = queue.Queue()
        config = {"extension": {"uv": os.path.join(%(uv_dir)r, "uv")}}
        def bridge_factory(on_event):
            spec = paths.bridge_spec(paths.Path("/nonexistent-pkg"), config)
            env = dict(spec.env); env["UV_PROJECT_ENVIRONMENT"] = str(paths.repo_core_dir() / ".venv")
            return Bridge(paths.BridgeSpec(spec.argv, env, spec.stderr_path, spec.cwd), on_event)
        view = RecView()
        s = Session(adapter, bridge_factory, doc_id=doc.RuntimeUID, lo_version=lo_version(ctx),
                    has_markdown_filter=has_markdown_filter(ctx), config_path=%(cfg)r)
        s.bind(view, events.put)
        vc = doc.getCurrentController().getViewCursor()
        vc.gotoEnd(False) if hasattr(vc, "gotoEnd") else None
        c = text.createTextCursor(); c.gotoEnd(False); vc.gotoRange(c, False)
        s.run_command("insert_norm", {"reference": "art. 2043 c.c."})
        out["state_after_insert"] = pump(s, events)
        out["lines_after_insert"] = list(view.lines)
        out["paragraphs"] = paragraph_texts(text)
        out["redlines"] = redlines(doc)
        out["bookmarks"] = list(doc.Bookmarks.getElementNames())
        s.run_command("verify_citations", {"scope": "document"})
        out["state_after_verify"] = pump(s, events)
        out["lines_after_verify"] = list(view.lines)
        out["problems"] = view.problems
        out["annotations"] = annotations(doc)
        s.shutdown()
        doc.close(True)
    ''' % {"uv_dir": uv_dir, "cfg": str(cfg)}, timeout=300, env={"LIBRELEX_CONFIG": str(cfg)})
    assert out["state_after_insert"] == "ready", out["lines_after_insert"]
    assert any(line.startswith("Inserito art. 2043 c.c. come revisione") for line in out["lines_after_insert"]), out
    texts = [t for _, t in out["paragraphs"]]
    assert texts[0].startswith("Premessa.") and texts[1] == "Art. 2043 c.c."
    assert texts[2].startswith("Qualunque fatto doloso") and texts[3].startswith("Testo vigente al")
    assert out["redlines"] and all(a == "LibreLex" for _, a in out["redlines"])
    assert any(b.startswith("LibreLex.norma.") for b in out["bookmarks"])
    assert out["state_after_verify"] == "ready", out["lines_after_verify"]
    assert out["problems"] == ["Cass. n. 99999/2024 · inesistente"]
    assert [c["anchor"] for c in out["annotations"]] == ["Cass. n. 99999/2024"]
    assert out["annotations"][0]["author"] == "LibreLex · verifica"
```

Run: `cd extension && uv run pytest tests/headless/test_e2e.py -q -x` → 1 passed (the first run can take a minute for `uv run`). If the probe times out, look at the evidence: `pump` returns the state reached; the stderr log path is `<dir of LIBRELEX_CONFIG>/core-stderr.log`.

- [ ] **Step 5: CI, README, NOTICE, .gitignore**

`.github/workflows/ci.yml`, add after the `core` job:

```yaml
  extension:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv python install 3.13
      - run: uv sync --python 3.13
        working-directory: core
      - run: uv sync --python 3.13
        working-directory: extension
      - run: uv run ruff check .
        working-directory: extension
      - run: uv run pytest -q -m "not headless"
        working-directory: extension
      - run: python3 scripts/build_oxt.py --out dist
      - uses: actions/upload-artifact@v4
        with:
          name: oxt
          path: dist/
  headless:
    # Best effort until a LibreOffice 26.x Linux package is pinned: verify the URL with
    # `curl -sI` before changing LO_VERSION; the job never blocks the others.
    runs-on: ubuntu-latest
    continue-on-error: true
    env:
      LO_VERSION: "26.8.0.3"
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv python install 3.13
      - run: uv sync --python 3.13
        working-directory: core
      - run: uv sync --python 3.13
        working-directory: extension
      - name: Install LibreOffice
        run: |
          set -e
          URL="https://downloadarchive.documentfoundation.org/libreoffice/old/${LO_VERSION}/deb/x86_64/LibreOffice_${LO_VERSION}_Linux_x86-64_deb.tar.gz"
          curl -fsSL "$URL" -o lo.tar.gz
          tar xzf lo.tar.gz
          sudo dpkg -i LibreOffice_*/DEBS/*.deb
          ls /opt | grep -i libreoffice
          echo "SOFFICE=$(ls -d /opt/libreoffice*/program/soffice | head -n1)" >> "$GITHUB_ENV"
      - run: uv run pytest -q -m headless
        working-directory: extension
```

`README.md`: replace the status and layout lines with:

```markdown
Status: M1 complete (verify citations, insert norm from the sidebar; no LLM yet).

## Install (macOS, LibreOffice 26.2+)

1. Install [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`).
2. From a Terminal: `scripts/dev_install.sh` (builds `dist/LibreLex-IT-<version>.oxt` and runs `unopkg add --force`).
3. Quit and restart LibreOffice. In Writer: View > Sidebar > LibreLex > Copilota legale.
4. First click creates `~/Library/Application Support/LibreLex/config.toml` (0600). Edit `[mcp_legal_it] command`
   if you run mcp-legal-it from a local checkout; LibreOffice must be restarted after changes.

The first action runs `uv run` on the bundled core: network access is needed once to build its environment.
Logs of the core process: `~/Library/Application Support/LibreLex/core-stderr.log` (no document text).

- `core/` — the local Python process (`librelex-core`), see `core/README.md`
- `extension/` — the LibreOffice `.oxt` sources (`uv run pytest` there; headless adapter tests need `soffice`)
- `scripts/` — `build_oxt.py`, `dev_install.sh`
- `spike/` — throwaway probes from Phase 0, kept for reproducibility
```

`NOTICE`: replace the LibreThinker paragraph with the exact file list:

```
- Sidebar skeleton derived from LibreThinker
  (https://github.com/mihailthebuilder/librethinker-extension), Mozilla Public License 2.0:
  extension/Sidebar.xcu, extension/Factories.xcu, extension/librelex_ext/panel.py,
  spike/oxt/Sidebar.xcu, spike/oxt/Factory.xcu, spike/oxt/librelex_spike.py.
  Those files keep their MPL header and remain under MPL-2.0; modifications are published here.
```

`.gitignore`: add `extension/.venv/` is covered by `.venv/`; add the line `core-env/` (not needed in the repo, defensive) and nothing else.

- [ ] **Step 6: Full run and commit**

Run: `cd core && uv run ruff check . && uv run pytest -q` and `cd extension && uv run ruff check . && uv run pytest -q` (includes headless when `soffice` exists).

```bash
git add scripts extension/tests/test_build_oxt.py extension/tests/headless/test_e2e.py .github/workflows/ci.yml README.md NOTICE .gitignore
git commit -m "feat: build and install scripts for the .oxt, end-to-end headless test, CI jobs and docs" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

- [ ] **Step 7: Hand-off for the user's GUI test (spec §9.5)**

The executor cannot run `unopkg` or see the GUI. Report to the user the exact commands:

```bash
cd /Users/gpuzio/Desktop/CODE/LibreLex-IT && scripts/dev_install.sh
```

then restart LibreOffice, open a Writer document containing `art. 2043 c.c.` and `Cass. n. 99999/2024`, open View > Sidebar > LibreLex, click "Verifica citazioni" (expect one comment on the Cassazione citation and the summary in the panel), type `art. 2043 c.c.` in the input and click "Inserisci norma" (expect the article inserted as a tracked change signed LibreLex, with the provenance line). Ask for a screenshot of the panel and of the tracked changes.

---

## Self-review

**Spec coverage (M1 scope, §11 row):**
- Protocol/bridge (§4.2, §5.2): Task 4 (Bridge), Task 5 (Session, hello, cancel, doc_result ids, one request per document via the busy state).
- Lifecycle (§4.3): lazy start on first action, restart after a crash, `XTerminateListener`, per-document sessions (Task 5 state machine, Task 9 registry). Handshake checks: protocol (Task 5), Markdown filter (Task 6 `has_markdown_filter`, Task 9 warning), mcp-legal-it version (core, surfaced by the `mcp_incompatible` error and the first-connect status of Task 2).
- Sidebar panel (§5.1): Task 9 with all listed controls, M2+ buttons disabled, notice copy, AsyncCallback, model rule; menu/context-menu entries are M4 and out of scope.
- Document actions (§5.3): Tasks 6-8 cover all nine; ids per spec; `read_paragraphs` includes footnotes and cells after their body paragraph.
- Writing (§5.4): Task 7 (temp file 0700/0600, paragraph break, trailing paragraph removal, RecordChanges restore, identity switch, undo context, styles only; `replace_selection` as deletion + insertion). Item 6 (redline text never read) respected: the adapter reads redline type and author only in tests.
- Comments (§5.5): Task 8 (range anchor, verification, `exact/found/paragraph_start`, footnotes direct, orphan rule).
- Provenance (§5.6): bookmark from the core, applied in Task 7.
- Security (§8.1, §8.4, §8.5): config dir/file permissions (Tasks 2-3), fixed argv (Task 3-4), temp files (Task 7), stderr log without document text (Task 4), no sockets. Consent (§8.2) not exercised in M1; defensive `deny` handler in Task 5.
- Tests/packaging (§9): pure-Python extension tests + headless macro tests (Tasks 4-10), `build_oxt.py`, `dev_install.sh`, CI jobs (Task 10). Deviation from §9.1 item 2: the fixture is built programmatically in the macro instead of a checked-in `.odt`, and the adapter is imported from the source tree instead of an installed `.oxt`, because `unopkg` cannot run from the harness; the `.oxt` install path is exercised by the user's GUI test.
- Core follow-ups from the M1 core ledger: (a) (b) (c) Task 1; (d) partially (status line, `hello_ok` field stays null) (e) (g) banner, progress duplicate Task 2; (f) pinned in Task 2's spec edit and honoured by `dispatch_doc_call`; (h) (i) (j) remain v2 backlog, unchanged.

**Placeholder scan:** no TBD/TODO; every code step has full code; the only "verify then adjust" instructions concern LibreOffice behaviour that the headless tests observe (fixture layout, first-paragraph style, search inside footnotes), each with the rule "fix the adapter, not the assertion" and the contract to keep.

**Type/name consistency:** `Session(adapter, bridge_factory, doc_id, lo_version, has_markdown_filter, config_path)` used identically in Tasks 5, 9, 10; `bridge_factory(on_event)` returns an object with `start/send/is_alive/stop`; `dispatch_doc_call` result shapes match `core/src/librelex_core/document.py` models (`paragraphs`, `occurrences`, `anchored`, `count`, `{}`); `paths.BridgeSpec(argv, env, stderr_path, cwd)` positional order used in Tasks 4 and 10; `layout.ACTIONS` commands match `Panel.actionPerformed`; `View` methods (`append`, `set_transcript`, `set_status`, `set_busy`, `set_problems`) implemented by `Panel`, `FakeView` and `RecView`; adapter method names in `FakeAdapter` equal `DocumentAdapter`'s.

