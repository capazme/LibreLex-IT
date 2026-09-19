# LibreLex-IT · Guided drafting (M3.5) design

Status: draft for review, 2026-09-19. Extends the binding spec
`docs/superpowers/specs/2026-09-07-librelex-it-design.md` (§5.1, §5.3, §6.3, §6.9, §8.2,
Appendices A and B); where the two disagree, this document wins for the drafting flow.

## 1. Why

The first field test of M3 (2026-09-19) showed two gaps:

1. The drafting flow does not fit the lawyer's work: the questions of the model arrive as
   prose in a read-only box, the answers have to be typed into a single-line field, the
   next button to press is not obvious, and turns are not separated.
2. The acts are not of the quality the same lawyer gets from the same engine in Claude Code,
   where the `genera-atto` skill and the `redattore-atti` agent of mcp-legal-it drive the
   model with a detailed recipe (catalogue first, calculators never by hand, exact legal
   formulas, verified norms, a final checklist) and the deterministic generators produce the
   base text. LibreLex gave the model a ten-line procedure and a partial tool profile.

Decisions taken with the lawyer on 2026-09-19: a guided procedure instead of a chat; the act
template decides the first fields, the model asks the rest as fields; the recipe of the plugin
is reused, not rewritten; a "similar case" (a reference act) can be given as inspiration.

## 2. Goals and non-goals

Goals:

- Draft any act of the mcp-legal-it catalogue from the sidebar with the plugin's own recipe
  and its deterministic generators, with the quality of the Claude Code flow.
- A form-like flow: choose the act, fill the fields the template declares, answer the model's
  remaining questions as fields, watch the partitions enter the document as tracked changes.
- Optional reference act ("caso simile") used for structure, style and argument, never for the
  facts of the new case, and sent only after consent.

Non-goals (v1 of this flow): pseudonymisation of the reference act (v2, `privacy-filter-it`);
acts routed to catalogue resources that mcp-legal-it has not published yet (`atti://…`), which
the model composes from the template fields as today; PDF references (LibreOffice opens them in
Draw; convert first); editing the fields of a drafting already inserted (start a new one).

## 3. Same recipe, same engine (core)

### 3.1 The recipe

`core/src/librelex_core/agent/recipes/draft.md` holds the drafting recipe, in Italian, derived
from `plugin/skills/genera-atto/SKILL.md` and `plugin/agents/redattore-atti.md` of mcp-legal-it
(provenance and the source commit noted in a header comment; the file is versioned with the
core). It keeps the plugin's rules verbatim where Writer changes nothing:

- catalogue first (`genera_modello_atto`), never draft without it;
- legal grounding: `cite_law` before quoting any norm (and the loop's grounding on write,
  §6.6, still verifies every reference at insertion);
- calculators, never hand-made arithmetic; every `tool_calcolo` of the template is called;
- completeness: all mandatory fields before generating;
- exact legal formulas from the generators, never paraphrased;
- final checklist (fields, verified references, calculators used, formulas, warnings told).

and adapts the output contract to Writer: the act text goes into the document one partition
per insertion; the calculations table, the verified references, the attachments checklist and
the warnings are reported in the panel, not in the document (the attachments list stays in the
act where the generator puts it).

The recipe is read once at import and joined to the user message of every drafting turn, so
provider caching still applies (the system prompt is unchanged). A later step, outside this
design, is an MCP prompt `redazione_atto` exposed by mcp-legal-it so the recipe is served by
the engine itself; the core will prefer it when the server offers it and fall back to the
bundled copy otherwise.

### 3.2 Deterministic base inserted by the core

When the template's routing names a direct tool (`tool_diretto`), the core, not the model:

1. calls the generator with the fields the lawyer filled plus `parametri_fissi`;
2. inserts the generator's text (the `testo` key of its result, used by the privacy and
   court-act generators, else a key starting with `bozza`, as `bozza_ricorso` of
   `decreto_ingiuntivo`; a result with neither, as the `preventivo_*` tools that return
   amounts, inserts no base and the model composes from the data) at the end of the document
   as one tracked insertion with undo label `LibreLex: base <tipo_atto>` and bookmark
   `LibreLex.atto.<tipo_atto>`;
3. records the placeholders found in it (`[SEDE]`, `[LEGALE]`, `[...]`, `{campo}`) in the
   drafting state.

The model then works on that base: it fills placeholders with `replace_text` (§4.3) and
expands the narrative partitions (facts, law, conclusions when the base has none) with
`insert_markdown where="after:<id>"` on the paragraph the base left for them, or at the end.
The exact formulas of the base are never regenerated by the model.

When the routing is `resource`, `tool_enhance` or `preventivo_procedura`, the core inserts
nothing and the model composes from the template's `campi_obbligatori`, `riferimenti_normativi`
and `istruzioni`, as the plugin's skill does, reading the catalogue resource when the server
publishes it (§3.4).

### 3.3 Profile `draft`, complete

The draft profile exposes every tool the catalogue can name, so no `istruzioni` ever points to
a tool the model cannot call: `genera_modello_atto`, `lista_categorie_atti`, `cite_law`,
`fetch_act_index`, `fetch_full_act`, `verifica_citazioni`, the 20 routing tools of
`modelli_atti.json` (the 9 court-act generators already allowlisted plus `preventivo_civile`,
`preventivo_stragiudiziale`, `preventivo_volontaria_giurisdizione`,
`genera_informativa_privacy`, `genera_informativa_cookie`, `genera_informativa_dipendenti`,
`genera_informativa_videosorveglianza`, `genera_dpa`, `genera_registro_trattamenti`,
`genera_dpia`, `genera_notifica_data_breach`) and every calculator named by a `tool_calcolo`
(counted on `modelli_atti.json` on 2026-09-19: the 8 of Appendix B plus `calcolo_hash`,
`calcolo_valore_catastale`, `compenso_ctu`, `conta_giorni`, `pignoramento_stipendio`,
`scadenze_impugnazioni`, `spese_mediazione`, `valutazione_data_breach`, `variazioni_istat`).
The allowlist grows from 35 to 55 (Appendix B regrouped as norms 5, case law 11, act
templates 2, act generators 20, calculators 17); the chat profile stays "every allowlisted
tool". Grounding sources (§6.6) are unchanged: only source-reading tools ground. Document
tools of the profile: `read_paragraphs`, `insert_markdown`, `replace_text`; internal tools:
`data_odierna`, `estrai_citazioni`, `leggi_risorsa` (§3.4), `chiedi_dati` (§4.4),
`redazione_completata` (§4.5), `leggi_atto_riferimento` (§5.3).

### 3.4 Catalogue resources

An internal tool `leggi_risorsa(uri)` reads an MCP resource of mcp-legal-it through the
fastmcp client, restricted to the `legal://` scheme, and returns its text wrapped as data. It
is what the plugin's skill does with `ReadMcpResourceTool` and gives the model the catalogue
resource (`legal://riferimenti/modelli-atti-catalogo`) and the act templates the catalogue
routes to (`legal://modelli-atti/<categoria>`, six of them, "not yet available" in the
plugin today) as soon as the server publishes them; an unknown resource comes back as an
`ERRORE:` string like any other tool failure.

## 4. The guided flow (protocol and core)

### 4.1 Deterministic commands, no model

- `list_templates` (args: `query` optional): the catalogue of `genera_modello_atto` as
  `[{tipo_atto, descrizione, categoria, tier}]`, in catalogue order, grouped by category;
  with `query`, the `cerca` mode. Cached in the core for the life of the process.
- `template_info` (args: `tipo_atto`): `campi_obbligatori`, `campi_opzionali`, `tool_calcolo`,
  `riferimenti_normativi`, `avvertenze`, `routing` (`tool_diretto` | `resource` | `tool_enhance`
  | `preventivo_procedura`) and, for a direct tool, the parameter names and types the generator
  accepts (from its schema), so the panel can label and type the fields (text, number, yes/no,
  date).

Both need mcp-legal-it and fail with `mcp_unavailable` otherwise.

### 4.2 The drafting state

`DocSession.draft: DraftState | None` (one drafting per document at a time):
`tipo_atto`, `template` (the `template_info` result), `fields` (name → value, from the panel),
`answers` (name → value, from the model's questions), `notes` (free text), `reference`
(`{name, chars, text}` | None, §5), `base` (`{from_id, to_id, placeholders}` | None),
`partitions` (`[{titolo, from_id, to_id}]`, one per insertion), `questions` (the last pending
list, §4.4), `done: bool`. It is memory only and dies with the session; a rebuilt panel gets
it back through the replay of §6.4.

### 4.3 The `draft` command, restructured

`{"type": "command", "name": "draft", "args": {...}}` with one of three shapes:

- `start`: `{"action": "start", "tipo_atto": "…", "fields": {…}, "notes": "…"}` (the reference
  act, if any, was set before with `set_reference`, §5.2). The core: resets the drafting state,
  stores the inputs, runs `template_info` if not cached, then, for a direct tool, the base
  insertion of §3.2 (consent is not needed: nothing of the document leaves the machine; the
  fields were typed by the lawyer for this purpose), then one model turn with the recipe, the
  template, the fields, the notes and, when present, the instruction to read the reference
  act. The model either asks questions (§4.4) or drafts.
- `answer`: `{"action": "answer", "answers": {…}}`: stores the answers and runs one model turn
  whose user message is "Risposte dell'utente: campo: valore; …" plus the standing reminder
  of the recipe's resume rule.
- `continue`: `{"action": "continue", "message": "…"}` (free text, optional): one more turn
  ("continua" after an iteration stop, or a free instruction such as "aggiungi la richiesta di
  provvisoria esecuzione").

Every turn of a drafting is a normal agent turn (`run_turn_with`, profile `draft`, undo label
`LibreLex: redazione <tipo_atto>`): consent for document reads, grounding on write, limits and
cancellation apply unchanged. The user message of every turn is built by the core from the
drafting state (template summary, fields, answers so far, partitions already inserted with
their titles, placeholders still open, whether a reference act is available), so the model
never depends on compacted tool results of earlier turns (the M3 review's finding 3).

New document action (spec §5.3): `replace_text` (args `query`, `replacement`, `paragraph_id`
optional, `all` default false) finds `query` (as `find_text` does) and replaces the occurrence
(or all of them) as a tracked deletion plus insertion, returning the count and the anchors.
Exposed to the model as a document tool in the `draft` and `review` profiles.

### 4.4 Structured questions

Internal tool `chiedi_dati(domande: [{campo, domanda, esempio?, tipo?}])` (tipo one of `testo`,
`numero`, `data`, `sino`, default `testo`). Calling it ends the turn: the loop stores the list in
the outcome and in `DraftState.questions`, answers the tool call with "Domande inviate
all'utente: attendi le risposte nel prossimo turno" and stops without another model call. The
`Final` carries `summary.domande`; the panel renders one field per question (§6.3). The recipe
tells the model to ask everything it needs in one call, at most 8 questions, and never to ask
what the fields or the reference act already answer.

### 4.5 Partitions and the end of a drafting

Every `insert_markdown` of a drafting turn records a partition: the title is the first heading
of the inserted markdown, else its first line trimmed to 60 characters. `Final.summary`
carries `partizioni` (the whole list) and `segnaposto_aperti` (placeholders still present in
the base, re-scanned after the turn through `find_text`). The model ends a drafting by calling
the internal tool `redazione_completata(riepilogo)` whose argument is the plain-text summary of
the recipe's output contract (calculations table, verified references, attachments checklist,
warnings); the core sets `DraftState.done`, and the panel shows the summary in Risposte and
marks the drafting as finished. A drafting interrupted by the iteration limit or cancelled is
resumed with `continue`.

## 5. The reference act ("caso simile")

### 5.1 What it is for

An earlier act of the firm, given as inspiration: structure, headings, style, recurring
formulas, argumentative moves. The recipe says explicitly that facts, names, amounts, dates and
case references of the reference are never to be reused, and that norms found in it are to be
verified with `cite_law` like any other (grounding on write still catches the rest).

### 5.2 How it reaches the core

The extension reads the file through LibreOffice itself (`loadComponentFromURL` hidden, so
`.odt`, `.docx`, `.rtf`, `.txt` work with no new dependency), extracts its paragraphs with the
existing adapter, closes it, and sends `{"type": "command", "name": "set_reference",
"args": {"name": "ricorso_rossi.docx", "text": "…"}}`; the core stores it in the drafting
state (`reference`), trimmed to 60,000 characters with a `troncato` flag, and answers with a
`Final` whose summary carries `name`, `chars`, `troncato`. `set_reference` with no `text`
clears it. The extension never keeps the file open or copies it anywhere.

### 5.3 How the model uses it

Internal tool `leggi_atto_riferimento()` (no arguments; it reads the drafting state, so the
loop executes it like a document read, with consent) returns the stored text wrapped as
`<<<DATI: atto di riferimento (nome)>>>`; the model calls it when the recipe tells it to (at
the first drafting turn, and again after a compaction if it needs the text). The first call in a
session asks consent through the existing channel with `scope: "reference"`, the file name and
the character count, unless the session consent is already "document"; "annulla" returns the
usual denial string and the drafting goes on without the reference. The consent block's text
names the file. Nothing of the reference is logged.

## 6. The guided flow in the sidebar (extension)

### 6.1 A fourth panel, "Redazione"

The deck gains a fourth panel between Azioni and Citazioni, served by the same factory
(`…/Drafting`), collapsible like the others. Controls, top to bottom, all pre-created so the
panel's height is fixed and re-flows only with the width (the technique of the consent
block: visibility toggles, no runtime control creation):

1. `TemplateSearch` (Edit): type to filter the catalogue (a `list_templates` with `query`
   after Enter or on the `TemplateRefresh` button).
2. `Template` (ListBox, dropdown): the catalogue entries as "categoria · descrizione"; the
   first selection triggers `template_info`.
3. `TemplateNotes` (FixedText, multi-line, grey): `avvertenze` and the routing in one line
   ("Base deterministica: decreto_ingiuntivo" or "Composizione dal modello").
4. Eight field rows `FieldLabelN` (FixedText) + `FieldN` (Edit), hidden until a template is
   chosen, then shown for the mandatory fields first and the optional ones after (a field
   beyond the eighth goes to the notes box, with the label listing them). Yes/no fields are
   Edits with "sì/no" in the label; dates are typed as text (the recipe normalises them).
5. `Notes` (Edit, MultiLine, 4 lines): "Fatti e note" free text.
6. Reference act row: `ReferenceLabel` ("Caso simile: nessuno" | the file name and size),
   `ReferenceBrowse` ("Sfoglia…", file picker filtered on odt/docx/rtf/txt), `ReferenceClear`
   ("Rimuovi"). The whole panel window is also a drop target for one file (`XDropTarget` on
   the container window's peer, `text/uri-list`); if the drop target cannot be registered on
   this LibreOffice the button remains the way (recorded as an assumption for the plan).
7. `Start` ("Avvia redazione"), enabled when a template is chosen and every mandatory field is
   non-empty.
8. Questions block, hidden until a `Final` carries `domande`: `QuestionsHint` (FixedText) and
   eight rows `QuestionLabelN` + `AnswerN`, plus `Continue` ("Continua") which sends `answer`.
9. `Partitions` (ListBox, not dropdown, 5 rows): the partitions inserted so far, "✓ titolo",
   plus a last entry "… segnaposto aperti: N" while any remains; clicking an entry calls
   `goto` on its first paragraph.
10. `Resume` ("Continua la redazione") with a one-line `ResumeInput` (Edit): sends `continue`
    with the optional message; shown while a drafting is started and not done.
11. `DraftStatus` (FixedText, two lines): "Scegli un atto" → "Compila i campi" → "Redazione in
    corso…" → "In attesa delle tue risposte" → "Redazione completata" | "Interrotta: premi
    Continua".

The `Draft` button of Azioni is removed (its job moved here); Azioni keeps chat, research and
the M1 actions. The consent block stays in Azioni and is used by the drafting turns too (the
status of Redazione says "Rispondi al consenso in Azioni").

### 6.2 Session and routing

`Session` gains `templates(query)`, `template(tipo_atto)`, `set_reference(path)`,
`draft_start(tipo_atto, fields, notes)`, `draft_answer(answers)`, `draft_continue(message)`;
`views.ROUTES` gains the Redazione methods (`set_templates`, `set_template`, `set_fields`,
`set_questions`, `set_partitions`, `set_reference`, `set_draft_status`); the session keeps a
`DraftView` state mirror (template list, chosen template, fields typed, questions, partitions,
reference, status) so a rebuilt panel is replayed like consent and usage today.

### 6.3 Risposte

Every turn is separated: a line "Tu: <what was sent>" (for the form: "Tu: avvio redazione
decreto_ingiuntivo_ordinario, 3 campi" / "Tu: risposte a 4 domande"), a blank line, then the
model's text starting on its own line ("LibreLex:" prefix on the first streamed chunk), and a
blank line after the notes. The system prompt tells the model to answer in plain text without
markdown markers in chat; the recipe's summary (§4.5) is plain text as well.

## 7. Security and data

- The reference act is document text of a third case: it leaves the machine only after the
  consent of §5.3 (scope "reference", with the file name and size), never logged, never
  persisted, cleared with the session. Pseudonymisation stays a v2 item and the README says so.
- Files are read through LibreOffice's own filters in a hidden document: no new parser, no new
  dependency; the file is closed right after extraction.
- The drop target accepts one local file (`file://` URIs only); anything else is ignored with a
  status line.
- `leggi_risorsa` accepts `legal://` and `atti://` URIs only; the text is wrapped as data.
- The generators of the profile are deterministic text builders; their outputs are wrapped as
  data and never ground a reference (§6.6 of the main spec).

## 8. Testing

- Core (no LibreOffice): recipe file present and containing the seven rules; `list_templates`
  and `template_info` against the fake catalogue; `draft start` with a direct tool inserts the
  base deterministically (bookmark, undo label, placeholders recorded) before the first model
  call; `chiedi_dati` ends the turn and the `Final` carries the questions; `answer` builds the
  user message from the state; partitions and open placeholders in the summary;
  `redazione_completata` sets `done`; `set_reference` and `leggi_atto_riferimento` with
  consent asked once with scope "reference"; `replace_text` on the fake document; the profile
  equals the tools the catalogue names (the plan pins the list and a test compares it with a
  copy of the catalogue's names checked into the tests).
- Extension pure tests: the Redazione layout table (no overlaps, width-independent height,
  hidden blocks), the session's draft methods and replay, the transcript separators.
- Headless: adapter `replace_text` as a tracked change; reading a `.docx` and an `.odt` fixture
  through the hidden-document path; the e2e drafting test rewritten on the new protocol: a
  decreto ingiuntivo with the base inserted by the core, one structured question answered, one
  narrative partition inserted by the stub, `redazione_completata` with a summary.
- The lawyer's field test (§9.5 of the main spec) remains the acceptance for the flow's feel,
  the drop target and the sidebar height.

## 9. Assumptions to validate in the first plan task

1. The fourth panel's fixed height (about 60 rows of controls) is acceptable in the sidebar
   with Risposte still taking the rest; if not, the questions block and the field rows are
   split into two panels ("Redazione" and "Domande").
2. `XDropTarget` can be obtained from the container window's peer inside a sidebar panel and
   delivers `text/uri-list` on macOS; otherwise the file picker is the only way.
3. `loadComponentFromURL` with `Hidden=True` on a `.docx` returns a Writer model the adapter can
   enumerate (expected: yes, same as the spike's hidden documents).

## 10. Amendments to the main spec

- §5.1: the deck has four panels; the drafting controls as in §6.1 here; the `Draft` button of
  Azioni removed.
- §5.3: new action `replace_text`.
- §6.3: `draft` profile as in §3.3 here; `review` gains `replace_text`.
- §6.9: replaced by a pointer to this document.
- §8.2: consent scope "reference" for the reference act.
- Appendix A: `list_templates`, `template_info`, `set_reference`, the three `draft` shapes,
  `Final.summary.domande/partizioni/segnaposto_aperti/riepilogo`.
- Appendix B: allowlist regrouped (act generators 20, calculators as in §3.3).
