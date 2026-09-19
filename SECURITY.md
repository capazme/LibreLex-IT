# Security policy

LibreLex-IT reads legal documents and, with the user's consent, sends parts of them to a
model provider. A security flaw here can leak a client's data, so reports are taken
seriously and handled privately.

## Reporting a vulnerability

**Do not open a public issue.** Use GitHub's private reporting:
[Report a vulnerability](https://github.com/capazme/LibreLex-IT/security/advisories/new).
The report reaches only the maintainer.

Please include the version (`extension/description.xml` or Tools > Extension Manager), the
operating system and LibreOffice version, the configuration preset in use (never the API
key), and the steps or a proof of concept. **Do not attach real client documents or real
personal data**: build the reproduction on invented text.

What to expect:

- an acknowledgement within 7 days;
- a fix or a mitigation in the next release, with credit in the changelog unless you prefer
  otherwise;
- a public advisory once the fix is out.

## Scope

Reports of these kinds are in scope:

- document text, or parts of it, leaving the machine **without** the consent step in the
  sidebar, or reaching a destination other than the configured endpoint;
- API keys or document text written to logs, temp files or the config file with permissions
  looser than `0600`;
- prompt injection through document text or tool results that leads the model to write,
  comment or delete in the document beyond what the user asked, or to bypass grounding;
- the stdio protocol between the extension and the core accepting input that executes code
  or reads files outside the document;
- the `.oxt` build or the install script executing something they should not;
- dependency vulnerabilities that are reachable from the code paths above.

Out of scope: the legal correctness of a model's answer (report it as a bug), the retention
policies of a third-party provider (see the GDPR table in the README), and vulnerabilities
in [mcp-legal-it](https://github.com/capazme/mcp-legal-it), which has its own policy.

## Supported versions

Only the latest minor release receives fixes; there is no long-term support line during the
alpha.

| Version | Supported |
|---|---|
| 0.5.x | yes |
| < 0.5 | no |

## Threat model, in short

- The core is a local process started by the extension; it talks to the model over HTTPS and
  to mcp-legal-it over MCP (a local subprocess by default, `https` mandatory in remote mode
  except for localhost).
- Secrets live in `config.toml` (created `0600`) or in environment variables, never in the
  document, the transcript or the logs.
- Document text enters the conversation only after an explicit consent in the sidebar, scoped
  to one turn or to one open document and kept in memory only.
- Everything the model writes into the document is a tracked change under its own author,
  so it can be reviewed and rejected; references it did not read from a source are verified
  before insertion.
