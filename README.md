# LibreLex-IT

AI copilot for LibreOffice Writer, for Italian legal drafting, grounded on
official sources through [mcp-legal-it](https://github.com/capazme/mcp-legal-it).

Status: M1 complete (verify citations, list citations, show the text of a reference and
insert a norm from the sidebar); M2 core in progress (chat and case-law research over a
configurable model, see "Chat e ricerca").
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

Document text is never sent without consent: the first time a turn needs to read the document,
the panel asks what is being sent (selection or paragraphs, number of characters), to whom
(endpoint host and model) and whether the routing is zero-data-retention. The choice is
session-scoped and never written to disk. Decisions inserted in the document are grounded:
a reference the model did not read with a tool is verified before the insertion and commented
when it turns out to be non-existent or inconsistent.

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
