# LibreLex-IT

AI copilot for LibreOffice Writer, for Italian legal drafting, grounded on
official sources through [mcp-legal-it](https://github.com/capazme/mcp-legal-it).

Status: M1 complete (verify citations, list citations, show the text of a reference and
insert a norm from the sidebar); M2 complete (chat, Ricerca, in-panel consent and usage line
in the sidebar, see "Chat e ricerca").
Design: `docs/superpowers/specs/2026-09-07-librelex-it-design.md`.

## Install (macOS, LibreOffice 26.2+)

1. Install [uv](https://docs.astral.sh/uv/) (`curl -LsSf https://astral.sh/uv/install.sh | sh`).
2. Quit LibreOffice, then from a Terminal: `scripts/dev_install.sh` (builds `dist/LibreLex-IT-<version>.oxt` and lets a
   headless LibreOffice register it in-process through `scripts/lo_install.py`; `--remove` uninstalls, `--profile DIR`
   targets a private profile). `unopkg add` is deliberately not used: on macOS it registers Python components
   through a helper soffice reached over a named pipe, which never answers on some installs (`NoConnectException`).
   Tools > Extension Manager > Add... on the `.oxt` works too.
3. Quit and restart LibreOffice. In Writer: View > Sidebar > LibreLex.
4. First click creates `~/Library/Application Support/LibreLex/config.toml` (0600). Edit `[mcp_legal_it] command`
   if you run mcp-legal-it from a local checkout; LibreOffice must be restarted after changes.

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
keep working: only chat and *Ricerca* answer with a configuration error.

### Asking: Invia and Ricerca

Type the question in the Azioni input box, then press one of the two buttons; the answer
streams into Risposte as the model writes it, and *Annulla* (the button in the Documento
section) stops it, keeping the partial text with an `[annullato]` note.

- **Invia**: a free chat turn. The model can consult the official sources, read the document
  (with consent, see below) and, if asked to, write into it as a redline.
- **Ricerca**: the same turn restricted to case law (`cerca_*`/`leggi_*` plus `cite_law`),
  for questions like "qual è l'orientamento sulla responsabilità del custode?". It reads and
  inserts, but never comments or replaces.

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

After every chat or research turn the bottom right of Azioni shows the usage line, for example
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

The first action runs `uv run` on the bundled core: network access is needed once to build its environment.
Logs of the core process: `~/Library/Application Support/LibreLex/core-stderr.log` (no document text).

- `core/` — the local Python process (`librelex-core`), see `core/README.md`
- `extension/` — the LibreOffice `.oxt` sources (`uv run pytest` there; headless adapter tests need `soffice`)
- `scripts/` — `build_oxt.py`, `dev_install.sh`
- `spike/` — throwaway probes from Phase 0, kept for reproducibility

License: Apache-2.0 (see `NOTICE` for MPL-2.0 and MIT parts).
