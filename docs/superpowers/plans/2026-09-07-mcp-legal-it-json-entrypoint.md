# mcp-legal-it: JSON output and console entry point — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `verifica_citazioni` and `cite_law` a machine-readable `formato="json"` output, declare the server version to MCP clients, and add a `mcp-legal-it` console entry point, so `librelex-core` can start the server with `uvx` and parse its results reliably.

**Architecture:** Backward-compatible additions on the mcp-legal-it repository (separate project, Git Flow). The markdown output of both tools stays byte-identical; the JSON output is built from a new structured intermediate that the markdown formatter now consumes too. A `src/cli.py` module becomes the `[project.scripts]` entry point in both `pyproject.toml` files, and `FastMCP(...)` receives the package version.

**Tech Stack:** Python ≥ 3.10, FastMCP 3.4, pytest + pytest-asyncio, `unittest.mock`, uv.

**Spec:** `/Users/gpuzio/Desktop/CODE/LibreLex-IT/docs/superpowers/specs/2026-09-07-librelex-it-design.md` (§7.1, §7.2, §10)

## Global Constraints

- Target repository: `/Users/gpuzio/Desktop/CODE/server-infra2.0/mcp-legal-it` (Git Flow: feature branches from `develop`, merged with `--no-ff`; never commit on `main` or `develop`).
- Branch: `feature/json-output-and-entrypoint`, created from an up-to-date `develop`.
- Tests: `.venv/bin/pytest tests/unit -q` must stay green; the existing markdown assertions in `tests/unit/test_legal_citations.py::TestVerificaCitazioniE2E` are the guard that markdown output did not change.
- `plugin/server/src/` is a committed **copy** of `src/` (not a symlink); every change to `src/` is mirrored there in the same commit: `rsync -a --delete --exclude __pycache__ src/ plugin/server/src/`.
- Both `pyproject.toml` (root) and `plugin/server/pyproject.toml` are edited identically; version numbers are NOT bumped here (`release.py` does it at release time; this work is a MINOR change to be listed under "Unreleased" in `CHANGELOG.md`).
- JSON responses use `json.dumps(obj, ensure_ascii=False)`; every JSON payload carries `"formato": "json"` so a client can tell the two outputs apart without guessing.
- Commits follow Conventional Commits and end with the `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` trailer; each "Commit" step means "propose the commit and wait for the user".

---

### Task 1: Feature branch

**Files:** none

- [ ] **Step 1: Create the branch from develop**

```bash
cd /Users/gpuzio/Desktop/CODE/server-infra2.0/mcp-legal-it
git checkout develop && git pull origin develop
git checkout -b feature/json-output-and-entrypoint
.venv/bin/pytest tests/unit -q 2>&1 | tail -2
```

Expected: the last line reports only passes (number may vary; no `failed`).

---

### Task 2: `verifica_citazioni(formato="json")`

**Files:**
- Modify: `src/tools/legal_citations.py` (`_verifica_citazioni_impl` at ~line 1034, tool wrapper at ~line 1090)
- Test: `tests/unit/test_legal_citations.py`

**Interfaces:**
- Produces: `_verifica_citazioni_struct(citazioni: str, archivio: str = "tutti") -> dict` with shape
  `{"formato": "json", "citazioni": [{"n": int, "citazione": str, "tipo": "norma"|"sentenza"|"non interpretabile", "verdetto": str, "nota": str}], "troncato": bool, "limite": 20, "avvertenza": str}`;
  `_verifica_citazioni_impl(citazioni, archivio="tutti", formato="markdown") -> str`;
  tool `verifica_citazioni(citazioni, archivio="tutti", formato="markdown")`.
- Verdict strings in JSON are exactly: `verificata`, `inesistente`, `non trovata`, `metadati discordanti`, `non verificabile`, `non verificata`, `non interpretabile`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_legal_citations.py` (the file already imports `patch`, `AsyncMock`, `_verifica_citazioni_impl`; add `_verifica_citazioni_struct` to the import list at line ~11):

```python
import json


class TestVerificaCitazioniJSON:
    @pytest.mark.asyncio
    async def test_struct_norma_verificata(self):
        async def fake_fetch_article(nv):
            return {"text": "Qualunque fatto doloso o colposo...", "url": "https://normattiva.it/art2043",
                    "source": "normattiva"}

        with patch("src.tools.legal_citations.fetch_article", side_effect=fake_fetch_article):
            out = await _verifica_citazioni_struct("art. 2043 c.c.")
        assert out["formato"] == "json"
        assert out["troncato"] is False and out["limite"] == 20
        c = out["citazioni"][0]
        assert c == {"n": 1, "citazione": "art. 2043 c.c.", "tipo": "norma",
                     "verdetto": "verificata", "nota": c["nota"]}
        assert "normattiva.it" in c["nota"]
        assert "esistenza" in out["avvertenza"]

    @pytest.mark.asyncio
    async def test_json_output_is_parseable_and_markdown_unchanged(self):
        async def fake_fetch_article(nv):
            return {"text": "", "url": "https://normattiva.it/x", "source": "", "error": "404"}

        with patch("src.tools.legal_citations.fetch_article", side_effect=fake_fetch_article):
            as_json = await _verifica_citazioni_impl("art. 9999 D.Lgs. 231/2001", formato="json")
            as_md = await _verifica_citazioni_impl("art. 9999 D.Lgs. 231/2001")
        data = json.loads(as_json)
        assert data["citazioni"][0]["verdetto"] == "non trovata"
        assert as_md.startswith("| # | Citazione | Tipo | Verdetto | Note/Fonte |")
        assert "non trovata" in as_md

    @pytest.mark.asyncio
    async def test_non_interpretabile_is_lowercase_in_json(self):
        out = await _verifica_citazioni_struct("una frase qualsiasi")
        c = out["citazioni"][0]
        assert c["tipo"] == "non interpretabile"
        assert c["verdetto"] == "non interpretabile"

    @pytest.mark.asyncio
    async def test_truncation_flag(self):
        async def fake_fetch_article(nv):
            return {"text": "testo", "url": "https://normattiva.it/a", "source": "normattiva"}

        refs = "\n".join(f"art. {i} c.c." for i in range(1, 23))  # 22 references
        with patch("src.tools.legal_citations.fetch_article", side_effect=fake_fetch_article):
            out = await _verifica_citazioni_struct(refs)
        assert out["troncato"] is True
        assert len(out["citazioni"]) == 20

    @pytest.mark.asyncio
    async def test_empty_input_json_error(self):
        out = await _verifica_citazioni_impl("", formato="json")
        data = json.loads(out)
        assert data["formato"] == "json" and data["citazioni"] == []
        assert "nessuna citazione" in data["errore"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_legal_citations.py::TestVerificaCitazioniJSON -q`
Expected: FAIL with `ImportError: cannot import name '_verifica_citazioni_struct'`.

- [ ] **Step 3: Implement the structured intermediate**

In `src/tools/legal_citations.py`, add `import json` to the imports, define the disclaimer once, and replace `_verifica_citazioni_impl` with:

```python
_VERIFICA_AVVERTENZA = (
    "La verifica accerta l'esistenza della fonte e la coerenza dei metadati "
    "(numero, anno, sezione, comma/lettera citati). NON verifica l'esattezza "
    "del principio di diritto o del contenuto citato."
)


async def _verifica_citazioni_struct(citazioni: str, archivio: str = "tutti") -> dict:
    """Structured result of verifica_citazioni; both output formats are built from it."""
    refs = _split_citazioni(citazioni)
    if not refs:
        return {
            "formato": "json", "citazioni": [], "troncato": False, "limite": _MAX_CITAZIONI,
            "avvertenza": _VERIFICA_AVVERTENZA,
            "errore": "nessuna citazione fornita. Inserire un riferimento per riga.",
        }

    truncated = len(refs) > _MAX_CITAZIONI
    refs = refs[:_MAX_CITAZIONI]
    tipi = [_classify_citazione(r) for r in refs]
    semaphore = asyncio.Semaphore(_MAX_CONCURRENT_VERIFICHE)

    async def _resolve_one(reference: str, tipo: str) -> tuple[str, str]:
        async with semaphore:
            try:
                if tipo == "sentenza":
                    return await _verifica_sentenza(reference, archivio)
                if tipo == "norma":
                    return await _verifica_norma(reference)
                return ("non interpretabile", "Formato non riconosciuto.")
            except Exception as exc:  # fail-safe: never crash the whole batch
                return ("non verificata", f"Errore durante la verifica: {exc}")

    results = await asyncio.gather(*(_resolve_one(r, t) for r, t in zip(refs, tipi)))
    return {
        "formato": "json",
        "citazioni": [
            {"n": i, "citazione": ref, "tipo": tipo, "verdetto": verdetto, "nota": nota}
            for i, (ref, tipo, (verdetto, nota)) in enumerate(zip(refs, tipi, results), start=1)
        ],
        "troncato": truncated,
        "limite": _MAX_CITAZIONI,
        "avvertenza": _VERIFICA_AVVERTENZA,
    }


def _format_verifica_markdown(data: dict) -> str:
    """Render the structured result exactly as the pre-JSON markdown table."""
    if data.get("errore"):
        return f"**Errore**: {data['errore']}"
    lines = [
        "| # | Citazione | Tipo | Verdetto | Note/Fonte |",
        "|---|-----------|------|----------|------------|",
    ]
    for c in data["citazioni"]:
        cit = c["citazione"].replace("|", "\\|")
        if c["tipo"] == "non interpretabile":
            tipo_label, verdetto = "Non interpretabile", "—"
        else:
            tipo_label, verdetto = c["tipo"].capitalize(), c["verdetto"]
        nota_clean = (c["nota"] or "—").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {c['n']} | {cit} | {tipo_label} | {verdetto} | {nota_clean} |")
    if data["troncato"]:
        lines.append("")
        lines.append(f"> *Verificate solo le prime {data['limite']} citazioni (limite per chiamata).*")
    lines.append("")
    lines.append(
        "> **Nota**: la verifica accerta l'**esistenza** della fonte e la coerenza "
        "dei **metadati** (numero, anno, sezione, comma/lettera citati). NON verifica "
        "l'esattezza del **principio di diritto** o del contenuto citato."
    )
    return "\n".join(lines)


async def _verifica_citazioni_impl(
    citazioni: str, archivio: str = "tutti", formato: str = "markdown"
) -> str:
    """Implementation of verifica_citazioni (testable without MCP wrapper)."""
    data = await _verifica_citazioni_struct(citazioni, archivio)
    if formato == "json":
        return json.dumps(data, ensure_ascii=False)
    return _format_verifica_markdown(data)
```

Then extend the tool wrapper signature and docstring:

```python
@mcp.tool(tags={"normativa"})
async def verifica_citazioni(citazioni: str, archivio: str = "tutti", formato: str = "markdown") -> str:
```

and add to its `Args:` block:

```
        formato: "markdown" (default, tabella leggibile) oppure "json" (oggetto con
                 chiavi formato, citazioni[n, citazione, tipo, verdetto, nota], troncato,
                 limite, avvertenza; in caso di input vuoto anche "errore"). Usare "json"
                 quando il risultato va elaborato da un programma.
```

and pass it through: `return await _verifica_citazioni_impl(citazioni, archivio, formato)`.

- [ ] **Step 4: Run the whole file**

Run: `.venv/bin/pytest tests/unit/test_legal_citations.py -q`
Expected: all pass, including the pre-existing `TestVerificaCitazioniE2E` markdown assertions (`| 1 |`, `Norma`, `verificata`, `esistenza`, `non trovata`).

- [ ] **Step 5: Mirror into the plugin copy and commit**

```bash
rsync -a --delete --exclude __pycache__ src/ plugin/server/src/
git add src/tools/legal_citations.py plugin/server/src/tools/legal_citations.py tests/unit/test_legal_citations.py
git commit -m "feat(verifica-citazioni): add formato=json structured output

The markdown table is now rendered from the same structured result, so
its text is unchanged. JSON carries lowercase tipo/verdetto values,
the truncation flag and the disclaimer, for programmatic clients."
```

---

### Task 3: `cite_law(formato="json")`

**Files:**
- Modify: `src/tools/legal_citations.py` (`_cite_law_impl` at ~line 313, tool `cite_law` at ~line 346)
- Test: `tests/unit/test_legal_citations.py`

**Interfaces:**
- Produces: `_cite_law_struct(reference: str) -> dict` with shape
  `{"formato": "json", "riferimento": str, "articolo": str, "atto": {"tipo_atto": str, "data": str, "numero_atto": str, "descrizione": str}, "url": str, "fonte": "normattiva"|"eurlex"|"", "testo": str, "errore": str|None, "data_consultazione": "YYYY-MM-DD"}`;
  `_cite_law_impl(reference, include_annotations=False, formato="markdown")`; tool `cite_law(reference, include_annotations=False, formato="markdown")`.
- In JSON mode `include_annotations` is ignored (Brocardi content is never returned as JSON; documented in the docstring).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_legal_citations.py` (add `_cite_law_struct`, `_cite_law_impl` to the import list if missing):

```python
class TestCiteLawJSON:
    @pytest.mark.asyncio
    async def test_struct_success(self, monkeypatch):
        monkeypatch.setenv("AKN_DISABLED", "1")

        async def fake_fetch_article(nv):
            return {"text": "1. Qualunque fatto doloso o colposo...", "url": "https://normattiva.it/art2043",
                    "source": "normattiva"}

        with patch("src.tools.legal_citations.fetch_article", side_effect=fake_fetch_article):
            out = await _cite_law_struct("art. 2043 c.c.")
        assert out["formato"] == "json"
        assert out["riferimento"] == "art. 2043 c.c."
        assert out["articolo"] == "2043"
        assert out["atto"]["tipo_atto"] == "codice civile"
        assert out["url"] == "https://normattiva.it/art2043"
        assert out["fonte"] == "normattiva"
        assert out["testo"].startswith("1. Qualunque")
        assert out["errore"] is None
        assert len(out["data_consultazione"]) == 10

    @pytest.mark.asyncio
    async def test_struct_unresolved_act(self):
        out = await _cite_law_struct("art. 1 atto inesistente xyz")
        assert out["testo"] == "" and out["errore"] and "non riconosciuto" in out["errore"]

    @pytest.mark.asyncio
    async def test_impl_json_and_markdown(self, monkeypatch):
        monkeypatch.setenv("AKN_DISABLED", "1")

        async def fake_fetch_article(nv):
            return {"text": "testo", "url": "https://normattiva.it/a", "source": "normattiva"}

        with patch("src.tools.legal_citations.fetch_article", side_effect=fake_fetch_article):
            as_json = await _cite_law_impl("art. 2043 c.c.", formato="json")
            as_md = await _cite_law_impl("art. 2043 c.c.")
        assert json.loads(as_json)["testo"] == "testo"
        assert as_md.startswith("**Fonte**: Normattiva — https://normattiva.it/a")
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_legal_citations.py::TestCiteLawJSON -q`
Expected: FAIL with `ImportError: cannot import name '_cite_law_struct'`.

- [ ] **Step 3: Implement**

In `src/tools/legal_citations.py` add `from datetime import date` to the imports and, right above `_cite_law_impl`:

```python
async def _cite_law_struct(reference: str) -> dict:
    """Structured article lookup (no Brocardi): the JSON face of cite_law."""
    today = date.today().isoformat()
    base = {
        "formato": "json", "riferimento": reference, "articolo": "",
        "atto": {"tipo_atto": "", "data": "", "numero_atto": "", "descrizione": ""},
        "url": "", "fonte": "", "testo": "", "errore": None, "data_consultazione": today,
    }
    article, act_name = _parse_reference(reference)
    if not act_name:
        base["errore"] = (f"impossibile interpretare il riferimento '{reference}'. "
                          "Formato atteso: 'art. <numero> <atto>'")
        return base
    act_info = _resolve_act(act_name)
    if not act_info:
        base["errore"] = _unresolved_act_error(act_name).replace("**Errore**: ", "")
        return base

    nv = _build_nv(act_info, article)
    base["articolo"] = article or ""
    base["atto"] = {
        "tipo_atto": nv.norma.tipo_atto_normalized,
        "data": act_info.get("data", ""),
        "numero_atto": act_info.get("numero_atto", ""),
        "descrizione": str(nv.norma),
    }
    try:
        result = await fetch_article(nv)
    except Exception as e:
        result = {"text": "", "url": nv.url(), "source": "", "error": str(e)}
    base["url"] = result.get("url", "") or nv.url()
    base["fonte"] = result.get("source", "") or ""
    base["testo"] = result.get("text", "") or ""
    if result.get("error"):
        base["errore"] = result["error"]
    elif not base["testo"]:
        base["errore"] = "nessun testo trovato"
    return base
```

Change `_cite_law_impl` to accept and honour `formato`:

```python
async def _cite_law_impl(reference: str, include_annotations: bool = False, formato: str = "markdown") -> str:
    """Implementation of cite_law (testable without MCP wrapper)."""
    if formato == "json":
        return json.dumps(await _cite_law_struct(reference), ensure_ascii=False)
    ...  # existing body unchanged
```

Extend the tool:

```python
@mcp.tool(tags={"normativa"})
async def cite_law(reference: str, include_annotations: bool = False, formato: str = "markdown") -> str:
```

with the docstring addition:

```
        formato: "markdown" (default) oppure "json": oggetto con riferimento, articolo,
                 atto{tipo_atto, data, numero_atto, descrizione}, url, fonte, testo,
                 errore, data_consultazione. In modalità json le annotazioni Brocardi
                 non sono incluse (include_annotations viene ignorato).
```

and `return await _cite_law_impl(reference, include_annotations, formato)`.

- [ ] **Step 4: Run the whole unit suite**

Run: `.venv/bin/pytest tests/unit -q 2>&1 | tail -2`
Expected: all pass.

- [ ] **Step 5: Mirror and commit**

```bash
rsync -a --delete --exclude __pycache__ src/ plugin/server/src/
git add src/tools/legal_citations.py plugin/server/src/tools/legal_citations.py tests/unit/test_legal_citations.py
git commit -m "feat(cite-law): add formato=json structured article output

Returns article text with act metadata, source, URL and consultation
date as JSON; markdown output and Brocardi annotations are unchanged."
```

---

### Task 4: Server version and `mcp-legal-it` console entry point

**Files:**
- Create: `src/cli.py`
- Modify: `src/server.py` (the `FastMCP(` call at line 7)
- Modify: `pyproject.toml` and `plugin/server/pyproject.toml` (`[project.scripts]`)
- Test: `tests/unit/test_cli.py`

**Interfaces:**
- Produces: console script `mcp-legal-it` → `src.cli:main`; `main(argv=None) -> None` honouring `MCP_TRANSPORT` (`stdio` default, `http`, `sse`), `MCP_HOST`, `MCP_PORT`, `MCP_PATH`; `src.server.mcp` created with `version=package_version()`; `package_version() -> str` in `src/cli.py`.
- MCP clients read the version from `initialize` → `serverInfo.version`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_cli.py`:

```python
"""Console entry point and server version."""
import re
import shutil
from unittest.mock import patch

import pytest

from src import cli


def test_package_version_matches_pyproject():
    text = open("pyproject.toml", encoding="utf-8").read()
    expected = re.search(r'^version = "([^"]+)"', text, re.M).group(1)
    assert cli.package_version() == expected


def test_main_defaults_to_stdio(monkeypatch):
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    with patch("src.cli.mcp.run") as run:
        cli.main([])
    run.assert_called_once_with(transport="stdio")


def test_main_http_reads_env(monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.setenv("MCP_HOST", "127.0.0.1")
    monkeypatch.setenv("MCP_PORT", "8123")
    monkeypatch.setenv("MCP_PATH", "/mcp")
    with patch("src.cli.mcp.run") as run:
        cli.main([])
    run.assert_called_once_with(transport="http", host="127.0.0.1", port=8123, path="/mcp")


def test_server_declares_version():
    from src.server import mcp
    assert mcp.version == cli.package_version()


@pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")
@pytest.mark.asyncio
async def test_uv_run_entry_point_handshake():
    """The exact way librelex-core starts the server: uv run --project . mcp-legal-it."""
    from fastmcp import Client
    from fastmcp.client.transports import StdioTransport

    transport = StdioTransport("uv", ["run", "--project", ".", "mcp-legal-it"],
                               env={"LEGAL_PROFILE": "normativa", "MCP_TRANSPORT": "stdio"})
    async with Client(transport, timeout=120) as client:
        info = client.initialize_result.serverInfo
        assert info.version == cli.package_version()
        names = {t.name for t in await client.list_tools()}
        assert {"cite_law", "verifica_citazioni"} <= names
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/pytest tests/unit/test_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.cli'`.

- [ ] **Step 3: Implement `src/cli.py`**

```python
"""Console entry point (`mcp-legal-it`) and package version helper."""
from __future__ import annotations

import os
import re
import sys
from importlib import metadata
from pathlib import Path


def package_version() -> str:
    """Version from installed metadata, else from the pyproject next to this package."""
    try:
        return metadata.version("mcp-legal-it")
    except metadata.PackageNotFoundError:
        pass
    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    try:
        m = re.search(r'^version = "([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M)
        if m:
            return m.group(1)
    except OSError:
        pass
    return "0.0.0"


def main(argv: list[str] | None = None) -> None:
    """Start the MCP server; transport and bind address come from the environment.

    MCP_TRANSPORT: stdio (default) | http | sse
    MCP_HOST / MCP_PORT / MCP_PATH: used by http and sse
    LEGAL_PROFILE: tool profile, read by src.server at import time
    """
    from src.server import mcp  # imported here so LEGAL_PROFILE is read after env is set

    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8000"))
    path = os.environ.get("MCP_PATH", "/mcp")
    if transport == "http":
        mcp.run(transport="http", host=host, port=port, path=path)
    elif transport == "sse":
        mcp.run(transport="sse", host=host, port=port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":  # pragma: no cover
    main(sys.argv[1:])
```

Because the tests patch `src.cli.mcp.run`, expose `mcp` at module level too: add after the imports

```python
from src.server import mcp  # noqa: E402  (module-level for patching; main() re-imports for clarity)
```

and inside `main()` keep the local import line (it resolves to the same object).

In `src/server.py` change the constructor call to pass the version:

```python
from src.cli_version import package_version  # see note below
mcp = FastMCP(
    "Legal IT",
    version=package_version(),
    instructions="""\
```

To avoid a circular import (`src.cli` imports `src.server`), move `package_version()` into a tiny module `src/cli_version.py` containing only that function (same code as above), and make `src/cli.py` import it from there: `from src.cli_version import package_version`.

- [ ] **Step 4: Register the entry point in both pyproject files**

Add to `pyproject.toml` and `plugin/server/pyproject.toml`, after `[project.optional-dependencies]`:

```toml
[project.scripts]
mcp-legal-it = "src.cli:main"
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/pip install -q -e . && .venv/bin/pytest tests/unit/test_cli.py -q`
Expected: 5 passed (the `uv` handshake test takes up to a minute on first run while uv builds the environment).

- [ ] **Step 6: Mirror and commit**

```bash
rsync -a --delete --exclude __pycache__ src/ plugin/server/src/
git add src/cli.py src/cli_version.py src/server.py pyproject.toml plugin/server/pyproject.toml plugin/server/src tests/unit/test_cli.py
git commit -m "feat(cli): add mcp-legal-it console entry point and declare server version

uvx --from git+https://github.com/capazme/mcp-legal-it@<tag> mcp-legal-it
now starts the server; MCP clients see the package version in
serverInfo.version."
```

---

### Task 5: Documentation, changelog, pull request

**Files:**
- Modify: `CHANGELOG.md` (new `## [Unreleased]` section at the top)
- Modify: `docs/tools-catalog.md` (signatures of `cite_law` and `verifica_citazioni` at lines 56 and 63)
- Modify: `CLAUDE.md` (the two tool rows in "Consultazione Normativa")
- Modify: `README.md` (setup section: the `uvx` one-liner)

- [ ] **Step 1: Changelog**

Insert after the header of `CHANGELOG.md`:

```markdown
## [Unreleased]

### Added
- `verifica_citazioni(..., formato="json")` and `cite_law(..., formato="json")`:
  structured output for programmatic clients (LibreLex-IT). Markdown output
  unchanged.
- Console entry point `mcp-legal-it` (`src.cli:main`), so the server starts
  with `uvx --from git+https://github.com/capazme/mcp-legal-it@vX.Y.Z mcp-legal-it`.
- The server now declares its package version to MCP clients
  (`serverInfo.version`).
```

- [ ] **Step 2: Catalog and CLAUDE.md**

In `docs/tools-catalog.md` replace the two signatures with
`cite_law(reference: str, include_annotations: bool = False, formato: str = "markdown")` and
`verifica_citazioni(citazioni: str, archivio: str = "tutti", formato: str = "markdown")`.
In `CLAUDE.md`, table "Consultazione Normativa", update the same two rows.
In `README.md`, under the Claude Code setup, add:

```markdown
**Opzione C — entry point (qualunque client MCP, richiede `uv`)**
```bash
uvx --from git+https://github.com/capazme/mcp-legal-it@main mcp-legal-it
```
```

- [ ] **Step 3: Full suite and commit**

Run: `.venv/bin/pytest tests/unit -q 2>&1 | tail -2`
Expected: all pass.

```bash
git add CHANGELOG.md docs/tools-catalog.md CLAUDE.md README.md
git commit -m "docs: document formato=json and the mcp-legal-it entry point"
git push -u origin feature/json-output-and-entrypoint
```

- [ ] **Step 4: Open the PR to develop**

```bash
gh pr create --base develop --title "feat: JSON output for verifica_citazioni/cite_law and console entry point" --body "$(cat <<'EOF'
Adds `formato="json"` to `verifica_citazioni` and `cite_law` (markdown unchanged),
declares the package version to MCP clients, and adds the `mcp-legal-it`
console entry point. Needed by LibreLex-IT (spec §10).

Tests: tests/unit/test_legal_citations.py (TestVerificaCitazioniJSON, TestCiteLawJSON),
tests/unit/test_cli.py (incl. a real `uv run --project . mcp-legal-it` handshake).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

After merge, the next release made with `release.py X.Y.Z --from-develop` is the
minimum version LibreLex-IT's core requires (`MIN_MCP_LEGAL_IT_VERSION` in
`core/src/librelex_core/mcp/client.py`): set that constant to the released number.
