<div align="center">

# LibreLex-IT

**AI copilot for LibreOffice Writer, built for Italian legal drafting and grounded on official sources.**

[![CI](https://github.com/capazme/LibreLex-IT/actions/workflows/ci.yml/badge.svg)](https://github.com/capazme/LibreLex-IT/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/capazme/LibreLex-IT?include_prereleases&label=release)](https://github.com/capazme/LibreLex-IT/releases)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![LibreOffice 26.2+](https://img.shields.io/badge/LibreOffice-26.2%2B-18A303?logo=libreoffice&logoColor=white)](https://www.libreoffice.org/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](core/pyproject.toml)

</div>

> **In breve (italiano).** LibreLex-IT è un'estensione per LibreOffice Writer pensata per chi
> redige atti: verifica le citazioni normative e giurisprudenziali contro le fonti ufficiali
> (Normattiva, Italgiure, Consulta, Giustizia amministrativa, EUR-Lex) tramite
> [mcp-legal-it](https://github.com/capazme/mcp-legal-it), inserisce il testo vigente delle
> norme, risponde a domande e cerca giurisprudenza, e redige atti da modello lasciando i calcoli
> (interessi, rivalutazione, contributo unificato, compensi) ai calcolatori e non al modello.
> Tutto ciò che il modello scrive nel documento è una revisione tracciata e verificata; il testo
> del documento non lascia la macchina senza il tuo consenso esplicito. Licenza Apache-2.0.
> La documentazione è in inglese.

<!-- screenshot: Writer with the LibreLex sidebar (Azioni, Citazioni, Risposte) open on a sample act -->

## Why LibreLex

- **Grounded, not guessed.** Every norm or judgment the model writes into the document is
  checked against the official source before insertion; a reference it did not read from a
  source is verified, and commented when it turns out non-existent or inconsistent.
- **Redlines, not overwrites.** Insertions are tracked changes under a `librelex` author,
  problems are Writer comments anchored to the text, everything is undoable.
- **Consent first.** Document text never leaves the machine without an explicit choice in the
  sidebar, which says what is sent, to whom and whether the routing is zero-data-retention.
  Local models through Ollama keep everything on the machine.
- **Free software on free software.** LibreOffice, Apache-2.0, and an
  [open MCP server](https://github.com/capazme/mcp-legal-it) for the legal sources.

**Status:** alpha, version 0.5.0. Milestones M1 (citations), M2 (chat and research) and
M3 (template-guided drafting) are shipped; M3.5 (guided drafting with a deterministic base) is
in design. Developed and tested on macOS; the config paths exist for Linux
(`~/.config/librelex`) and Windows (`%APPDATA%\LibreLex`) but installs there are untested,
reports welcome. Design: [`docs/superpowers/specs/2026-09-07-librelex-it-design.md`](docs/superpowers/specs/2026-09-07-librelex-it-design.md).

## What it does

| Command (sidebar) | What happens | Needs a model |
|---|---|---|
| **Verifica citazioni** / *Verifica selezione* | Checks every citation against the official sources, comments the problematic ones | no |
| **Elenca citazioni** | Lists the references of the document, no network | no |
| **Mostra testo** | Shows the current text of a norm or judgment in the Risposte panel | no |
| **Inserisci norma** | Inserts the text in force of an article as a redline with provenance | no |
| **Invia** | A chat turn: the model can consult the sources, read the document (with consent) and write into it as a redline | yes |
| **Ricerca** | The same turn restricted to case-law search; reads and inserts, never rewrites | yes |
| **Redigi da modello** | Template-guided drafting: looks the act up, asks for the missing data, computes the amounts with the calculators, inserts the act section by section | yes |

## Quickstart (macOS, LibreOffice 26.2+)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh          # 1. uv, once
git clone https://github.com/capazme/LibreLex-IT.git && cd LibreLex-IT
scripts/dev_install.sh                                    # 2. builds the .oxt and registers it (LibreOffice closed)
```

Restart LibreOffice, open Writer, then **View > Sidebar > LibreLex**. The deterministic
commands work right away; chat, research and drafting need an `[llm]` section in the config
file (see below). A prebuilt `.oxt` for every version is on the
[Releases](https://github.com/capazme/LibreLex-IT/releases) page: Tools > Extension Manager >
Add… installs it too.

## Install, in detail

1. Install [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`).
2. Quit LibreOffice, then from a Terminal: `scripts/dev_install.sh` (builds `dist/LibreLex-IT-<version>.oxt` and lets a
   headless LibreOffice register it in-process through `scripts/lo_install.py`; `--remove` uninstalls, `--profile DIR`
   targets a private profile). `unopkg add` is deliberately not used: on macOS it registers Python components
   through a helper soffice reached over a named pipe, which never answers on some installs (`NoConnectException`).
   Tools > Extension Manager > Add... on the `.oxt` works too.
3. Quit and restart LibreOffice. In Writer: View > Sidebar > LibreLex.
4. First click creates `~/Library/Application Support/LibreLex/config.toml` (0600). Edit `[mcp_legal_it] command`
   if you run mcp-legal-it from a local checkout; LibreOffice must be restarted after changes.

The first action runs `uv run` on the bundled core: network access is needed once to build its environment.
Logs of the core process: `~/Library/Application Support/LibreLex/core-stderr.log` (no document text).

## Chat e ricerca

The chat and the case-law research need a model: put an `[llm]` section in
`~/Library/Application Support/LibreLex/config.toml` (0600, see the spec Appendix D).

```toml
[llm]
preset = "openrouter"          # cliproxyapi | openrouter | ollama | custom
api_key = "sk-or-..."          # or the LIBRELEX_LLM_API_KEY environment variable
model = "anthropic/claude-sonnet-4.5"
zero_data_retention = true     # OpenRouter: routes only to providers that do not retain data
```

- **OpenRouter** (`preset = "openrouter"`): `base_url` and the accounting headers are set by
  the preset; `zero_data_retention = true` adds `provider.data_collection = "deny"` to every
  request, so the prompt only reaches providers that declare no retention.
- **CLIProxyAPI** (`preset = "cliproxyapi"`, `http://127.0.0.1:8317/v1`): a local proxy that
  exposes a consumer subscription as an OpenAI-compatible endpoint. For prototyping only, see
  the matrix below.
- **Ollama** (`preset = "ollama"`, `http://localhost:11434/v1`): the model runs on the machine,
  no `api_key` needed; document text still goes through the consent dialog, labelled as local.

Without a configured `[llm]` the deterministic commands (verify, list, show text, insert norm)
keep working: only chat, *Ricerca* and *Redigi da modello* answer with a configuration error.

### Asking: Invia, Ricerca and Redigi da modello

Type the question in the Azioni input box, then press one of the three buttons; the answer
streams into Risposte as the model writes it, and *Annulla* (the button in the Documento
section) stops it, keeping the partial text with an `[annullato]` note.

- **Invia**: a free chat turn. The model can consult the official sources, read the document
  (with consent, see below) and, if asked to, write into it as a redline.
- **Ricerca**: the same turn restricted to case law (`cerca_*`/`leggi_*` plus `cite_law`),
  for questions like "qual è l'orientamento sulla responsabilità del custode?". It reads and
  inserts, but never comments or replaces.
- **Redigi da modello**: template-guided drafting. Name the act in the input box ("decreto
  ingiuntivo per la fattura n. 12/2025 di 12.000 euro") and press the button: the model looks
  the template up in mcp-legal-it, reads the document (with consent), asks in Risposte for the
  data it still needs, and stops. Type the answers in the same box and press the button again:
  it computes the amounts (interests, revaluation, contributo unificato, fees) with the
  calculators and inserts the act at the end of the document one section at a time, each as a
  redline, leaving `[...]` where nobody supplied a value. The session keeps the thread until the
  document is closed, so "continua" resumes a drafting cut by the iteration limit.

Text written into the document is grounded: a reference the model did not read from a source
is verified before the insertion and commented when it turns out to be non-existent or
inconsistent.

### Consent for the document text

Document text is never sent without consent. The first time a turn needs to read the document,
the Azioni panel shows a consent block above the status line, saying what is being sent
(the selection or the paragraphs read, with the number of characters), to whom (endpoint host
and model) and whether the routing is zero-data-retention, with three choices:

- **Per questo documento**: consent for every later turn on that document, until it is closed.
  It is kept in memory only, never written to disk.
- **Solo stavolta**: consent for the current turn only; the next one asks again.
- **Annulla**: nothing is sent. The model is told the user refused and answers without the
  text (it can still work on what it finds in the official sources).

The question comes after the read and before the text enters the conversation, so refusing
means nothing has left the machine. The consent block stays usable while the core is busy:
answering it is the one thing to do while a turn is running.

### Token cost per turn

After every chat, research or drafting turn the bottom right of Azioni shows the usage line, for example
`Turno: 12.480 + 320 token · sessione: 41.900 token`, with `· costo: $0.04` when the provider
reports it. The turn count is the whole request, not just the question: the system prompt, the
tool schemas (about 7k token of them), the earlier turns and every tool result of the current
one (the norm texts, the document paragraphs, a judgment can be 8k token) are resent at each
model call, and a turn that uses tools calls the model once per round. A turn inside a long
thread therefore costs several times the first one. The core keeps this bounded by shortening
the tool results of past turns to a one-line placeholder, and by dropping the oldest turns
once the history exceeds its budget. *Svuota* in Risposte empties the panel, not the
conversation: the history lives in the core and goes away when the document is closed. Past
`[limits] session_token_ceiling` (400.000 token by default) the core refuses further turns and
asks for the document to be closed and reopened.

Providers with prompt caching (Anthropic and OpenAI models, also through OpenRouter) bill a
prefix they have already seen at a fraction of the input price, with no configuration needed.
It pays off most inside a single turn, where the model is called again after each tool result
and the prefix only grows; between turns the discount is partial, since shortening the old tool
results rewrites the prefix and invalidates the cache.

### Providers and GDPR

The lawyer is the data controller; the provider that receives the prompt is a processor under
art. 28 GDPR and needs a data processing agreement (DPA).

| Provider | Retention | DPA | Note |
|---|---|---|---|
| OpenRouter, ZDR routing (`zero_data_retention = true`) | none declared by the routed providers | OpenRouter's terms, plus the policy of the provider actually routed to | The provider changes per request: check which ones your model is routed to |
| Anthropic API through OpenRouter | per Anthropic's commercial terms (no training, limited retention) | yes, Anthropic's commercial API has one | The contractual chain passes through OpenRouter: verify it covers your processing |
| CLIProxyAPI over a consumer subscription | per the consumer terms of the subscription, usually training on the content | no | **Prototyping only**: never with client data |
| Ollama, local model | none, nothing leaves the machine | not needed, no processor involved | Quality and context window depend on the local model |

Rule of thumb: with real client data use a provider you have a DPA with, keep
`zero_data_retention = true`, or stay local with Ollama.

## Usage

The LibreLex deck has three panels: **Azioni** (buttons, progress and status), **Citazioni**
(the references found in the document) and **Risposte** (the answers). Each panel opens and
closes from its own title bar, like every other sidebar panel, and Risposte takes the height
the other two leave.

- **Verifica citazioni** (or *Verifica selezione*): checks every citation of the document
  (or of the selection) against the official sources and comments the problematic ones in
  the document; Citazioni shows each reference with its verdict (✓ verified,
  ✗ problem, ? not verified, · to be checked by hand).
- **Elenca citazioni**: lists the references of the document without consulting any source
  (no network); clicking an entry in Citazioni jumps to its first occurrence and shows its
  text in Risposte.
- **Mostra testo**: shows in Risposte the text of the reference typed in the input box, or
  of the one selected in the document; nothing is written into the document.

## How it works

```
LibreOffice Writer ──UNO──▶ extension/ (sidebar, redlines, comments; stdlib only)
                                │ JSON lines over stdio
                                ▼
                          core/ (librelex-core: citation pipelines, agent loop, consent)
                                │ MCP                      │ OpenAI-compatible API
                                ▼                          ▼
                          mcp-legal-it              the model you configure
                          (official sources)        (OpenRouter, Ollama, ...)
```

The extension runs inside LibreOffice's own Python and stays stdlib-only; everything that
needs dependencies lives in the core, a local process started with `uv run` from the bundled
`core/` tree. The legal sources are never scraped by the model: they come through the tools
of mcp-legal-it, and the model only sees what those tools return.

## Repository layout

- `core/` — the local Python process (`librelex-core`), see [`core/README.md`](core/README.md)
- `extension/` — the LibreOffice `.oxt` sources (`uv run pytest` there; headless adapter tests need `soffice`)
- `scripts/` — `build_oxt.py`, `dev_install.sh`, `lo_install.py`
- `docs/superpowers/` — design specs and implementation plans, the source of truth for scope
- `spike/` — throwaway probes from Phase 0, kept for reproducibility

## Contributing and security

Contributions are welcome: bug reports, act templates and citation patterns, docs, tests on
Linux and Windows. Read [CONTRIBUTING.md](CONTRIBUTING.md) for the dev setup and the
conventions, and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Never attach a real client document
to an issue: use invented facts and names.

Security issues go through the private channel in [SECURITY.md](SECURITY.md), not the issue
tracker. Release notes: [CHANGELOG.md](CHANGELOG.md).

## License

Apache-2.0, see [`LICENSE`](LICENSE). The sidebar registration files derived from
[LibreThinker](https://github.com/mihailthebuilder/librethinker-extension) keep their MPL-2.0
header and the citation extractors ported from VisuaLexAPI are MIT: [`NOTICE`](NOTICE) lists them.
