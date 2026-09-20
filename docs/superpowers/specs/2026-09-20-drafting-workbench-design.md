# LibreLex-IT · Drafting workbench (M3.6) design

Status: draft for review, 2026-09-20. Extends `2026-09-19-guided-drafting-design.md` (the
guided flow) and the main spec `2026-09-07-librelex-it-design.md`; where they disagree, this
document wins for the drafting panel, the case documents and the formatting of the acts.

## 1. Why

The second field test (2026-09-20, an atto di citazione in opposizione a decreto ingiuntivo
drafted through the Redazione and Domande panels) showed that the flow works and asked for
three things:

1. **Less machinery**: five stacked panels make the sidebar scroll, the consent question lives
   in another panel, the model's work is invisible while it runs, and the lawyer cannot give
   the model the documents of the case (fattura, delibera, decreto, contratto, PEC), so the
   model asks for facts the documents already contain.
2. **Real formatting**: the inserted act does not look like the firm's acts. The firm's own
   ricorso sets the canon: Times New Roman 12, line spacing 1.5, justified body, court heading
   and act title centred, section headings (PREMESSO CHE, RICORRE, INGIUNGERE, P.Q.M.) centred
   in bold capitals, party roles right-aligned in bold, "contro" centred, `* * * * *`
   separators, premesse and documents as dashed paragraphs, signature right-aligned.
3. **Letterhead**: every act must carry the firm's letterhead, and the lawyer has more than one
   (SAPG Legal, SAPG Legaltech): they must be selectable.

Verified on LibreOffice 26.8 before this design (headless spike, 2026-09-20): loading page
styles from a document with `XStyleLoader.loadStylesFromURL` carries the header text, the
footer text and the header image into the target document, and saving the result as `.ott`
keeps the image; `com.sun.star.ui.XPanel` exposes `collapse()`/`expand()` and the frame's
controller provides `XSidebarProvider`.

## 2. Goals and non-goals

Goals: one drafting panel that shows one step at a time and never needs scrolling; the case
documents given to the model as numbered attachments, read on demand, listed in the act; the
act formatted with named paragraph styles that reproduce the firm's canon; the letterhead
chosen per act from the firm's templates; the model's activity visible while it works.

Non-goals (this round): pseudonymisation of attachments (v2); scanned PDFs without a text
layer (reported, not OCRed); editing the fields of a started drafting (start a new one);
per-question skipping controls (an empty answer is a skip); Windows paths (macOS and Linux
first, as the rest of the extension).

## 3. The Redazione panel, one step at a time

The deck has four panels: Azioni, **Redazione**, Citazioni, Risposte. "Domande" is folded
into Redazione. The Redazione panel keeps a fixed height (the tallest step, about 430 dialog
units) and shows one of four **steps**; the controls of every step are pre-created and toggled
by visibility (the technique of the consent block), so no control is created at runtime.

### 3.1 Step 1 · Atto e dati

Top to bottom: the act search box and the catalogue list (as today); the routing line and the
warnings; the field rows (eight, typed, mandatory first); "Fatti e note"; **Allegati** (§4): a
list box with the numbered documents and the buttons "Aggiungi…" and "Togli"; **Caso simile**
(as today: label, Sfoglia…, Rimuovi); **Carta intestata**: a dropdown with the firm's templates
(§5.2) plus "Nessuna (impaginazione del documento)", and "Aggiungi…"; the button **Avvia
redazione**; the status line. Files can be dropped anywhere on the panel: an act-like file
(odt, docx, rtf, txt) dropped while the reference slot is empty becomes the reference, any
other file (or a second one) becomes an attachment; the status line says which.

### 3.2 Step 2 · Domande

The hint ("Il modello ha bisogno di N dati: rispondi e premi Continua; una casella vuota vale
come risposta non disponibile"), up to eight question rows (a two-line label and a box), the
**consent block** of the drafting (the same three choices as in Azioni; whichever panel is
visible answers, the session accepts the first answer), and **Continua**.

### 3.3 Step 3 · Redazione in corso

A live **activity log** (read-only multi-line box, newest line last, kept in the session so a
rebuilt panel replays it) fed by the core's `status` events of the running request and by the
partitions as they are inserted ("Inserito: Premesse in fatto"); the list of the expected
partitions of the act with a mark on the ones inserted (from the template's structure when
the routing is a generator, else the recipe's canonical list: intestazione, parti, premesse,
diritto, conclusioni, allegati); **Annulla**; the consent block again (a read during a draft
turn asks here).

### 3.4 Step 4 · Fine

The partitions inserted (click: jump), the summary of the drafting (calculations, verified
references, attachments, warnings, what is left), **Verifica citazioni** (runs the M1 pipeline
on the document), **Riprendi** (back to step 3 with a free instruction box, for "continua" or a
change), **Nuova redazione** (back to step 1, drafting state cleared, attachments and letterhead
kept).

### 3.5 Transitions and feedback

Step 1 → 3 on Avvia; 3 → 2 when the turn ends with questions; 2 → 3 on Continua; 3 → 4 on
completion; 3 → 4 with the status "Interrotta" on an interruption (iterations, timeout,
cancel), Riprendi available; an error keeps the current step and shows it in the status line.
The status line of every step names the next action. When a drafting starts, the panels
Azioni and Citazioni are collapsed through `XSidebarProvider`/`XPanel.collapse()` (best
effort: any failure is ignored) so Redazione and Risposte have the height; nothing is
re-expanded automatically.

### 3.6 Session mirror

`draft_view` gains `step` (1 to 4), `log: list[str]` (capped at 200 lines), `expected_partitions:
list[str]`, `attachments: list[{n, name, chars, kind}]`, `letterheads: list[{name, path}]`,
`letterhead: str | None` (the chosen name), and keeps the rest; `replay_drafting` restores the
step and its contents. The Risposte transcript still gets the turn separators and the summary.

## 4. Case documents ("allegati")

### 4.1 What they are

The documents of the case, numbered in the order added (Doc. 1, Doc. 2, …), given to the
model as **facts**: it reads them to fill the premesse (dates, amounts, parties, protocol
numbers) and lists them in the act's "Si allegano" section with their number and a short
description. They are distinct from the reference act (style only, §5 of the guided-drafting
design).

### 4.2 How they are read

The extension reads each file through LibreOffice in a hidden, read-only, macro-free document
(`read_reference`'s path, generalised as `read_document(ctx, url) -> {name, text, chars,
kind}`): Writer formats (odt, docx, doc, rtf, txt) through the Writer model; **PDF** through
the Draw import filter, rebuilding lines from the positioned text frames of every page (sorted
by page, then y, then x; frames on the same baseline joined with spaces, lines separated by
newlines, pages by a form-feed line `--- pagina N ---`); a PDF whose frames carry no text is
reported as "PDF senza testo (scansione): non leggibile" and refused. Each text is trimmed to
`MAX_ATTACHMENT_CHARS = 60_000` (flagged `troncato`); the set is capped at
`MAX_ATTACHMENTS = 12` and `MAX_ATTACHMENTS_CHARS = 300_000` in total; the panel refuses beyond
that with a status line. The extension keeps only `{n, name, chars, kind, troncato}`; the text
goes to the core at once.

### 4.3 Protocol and core

- `set_attachments {documenti: [{name, text, kind}]}` replaces the whole set (the panel sends
  the full list after every add or remove); the core stores `session.attachments` (numbered,
  trimmed again defensively) and answers `Final.summary {allegati: [{n, name, chars, troncato}]}`.
  A `set_attachments` resets `session.attachments_consented`.
- Consent: the first `leggi_allegato` of a session (or after the set changed) asks
  `consent_request` with `scope: "attachments"`, `name: "Doc. 1 fattura.pdf; Doc. 2 …"` (the
  names joined, cut at 200 characters), `chars: <total>`; "document" and "once" both consent
  for the current set; "deny" is remembered until the set changes. Nothing of the attachments
  is logged.
- Internal tool `leggi_allegato(numero: int)` returns the text wrapped as
  `<<<DATI: allegato N (nome)>>>`; the draft message lists the attachments ("Allegati del
  fascicolo: Doc. 1 fattura_12.pdf (12.300 caratteri); …") every turn; compaction replaces the
  read texts after the turn as for every tool result, and the model may read again.
- The recipe (`recipes/draft.md`) gains a rule and two steps: RISERVATEZZA covers the
  attachments too (they are the case's own documents: their facts are to be used; their
  personal data goes into the act only where the act needs it); step 1 becomes "read the
  attachments relevant to the facts before asking anything: a question whose answer is in a
  document is not asked"; step 5 says the "Si allegano" list is built from the attachments in
  their numbering ("- doc. N: <descrizione breve>"), plus "procura alle liti" first when the
  act needs it.
- The dev CLI: `draft --allegato FILE` (repeatable, text files only; the LibreOffice reading is
  the extension's).

## 5. Formatting and letterhead

### 5.1 The act styles

A set of named paragraph styles, prefix `LibreLex`, reproducing the firm's canon (read from the
firm's ricorso on 2026-09-20; every value adjustable in the template):

| Style | Use | Properties |
|---|---|---|
| `LibreLex Intestazione` | court heading (`TRIBUNALE DI MILANO`) | centred, capitals as written, Times New Roman 12, line spacing 150%, space after 0.2 cm |
| `LibreLex Titolo atto` | the act's title line(s) | centred, bold, 12 pt |
| `LibreLex Sezione` | PREMESSO CHE, RICORRE, INGIUNGERE, P.Q.M., CONCLUSIONI | centred, bold, 12 pt, space before 0.3 cm |
| `LibreLex Corpo` | body | justified, 12 pt, line spacing 150%, no first-line indent |
| `LibreLex Punto` | premesse, motivi, documents (dashed or numbered) | justified, hanging indent 0.5 cm, 150% |
| `LibreLex Ruolo parte` | `- ricorrente -`, `- opponente -` | right-aligned, bold |
| `LibreLex Contro` | `contro` | centred, bold |
| `LibreLex Separatore` | `* * * * *` | centred |
| `LibreLex Citazione` | quoted norm or massima | justified, indented 1 cm left and right, 11 pt |
| `LibreLex Firma` | `Avv. …`, place and date | right-aligned |

Character formatting stays inline (bold party names, italics) as the model writes it in
markdown. Numbering: `LibreLex Punto` carries no automatic numbering; the dash or the number is
part of the text, as in the firm's acts (the Markdown filter's automatic lists are converted
to text prefixes, so the act survives copy and paste into other tools).

### 5.2 Letterhead templates

The firm's letterheads are Writer templates in the user's LibreLex folder,
`~/Library/Application Support/LibreLex/modelli/<nome>.ott` (Linux: the XDG config dir), one
per letterhead, private to the machine, never in the repo. A template carries: the page style
with header and footer (logo, addresses, page number) and, optionally, the `LibreLex` act
styles adjusted by the lawyer. The index `modelli/modelli.json` lists them (`{"name", "file",
"default": bool}`) and the last choice.

**Adding a letterhead** (button "Aggiungi…" in step 1, or the CLI of §5.4): from an odt, docx
or doc file that already has the letterhead in its page style (the Legaltech relazione): the
page styles are loaded into a fresh document (`loadStylesFromURL` with `LoadPageStyles`), the
body is left empty, the `LibreLex` styles are added, and the result is saved as `.ott` under
`modelli/` with the name the lawyer gives. From a **PDF** (the SAPG diffida): the PDF is imported
in Draw; the images and text frames whose top edge lies in the top 4.5 cm of page 1 become the
header (the images anchored as they are positioned, the text lines below them, right-aligned
when their x is past the page middle), those in the bottom 4 cm become the footer (text lines
centred), the page size and margins are taken from the PDF page and the outermost frames; the
result is the same `.ott`. The lawyer can then open the template in Writer and adjust it; the
extension never rewrites an existing template.

### 5.3 Applying them

At **Avvia redazione**, before the base is inserted, the adapter's `apply_letterhead(url)`:
(1) loads the template's page styles into the document (`LoadPageStyles`, `OverwriteStyles`),
so the current page style gets the letterhead; (2) creates every `LibreLex` paragraph style
missing from the document with the §5.1 properties (a style the template already defines is
kept as it is); (3) records in the drafting state that the styles are present. With "Nessuna"
selected, only (2) runs. An empty new document therefore ends up on the firm's letterhead; a
document that already has its own letterhead keeps it when "Nessuna" is chosen.

Every insertion of a drafting (the deterministic base and the model's partitions) goes through
`_apply_act_styles` after the Markdown filter: the inserted paragraphs are restyled by
pattern, in this order, first match wins: a paragraph inserted from `# ` → `LibreLex
Intestazione`; from `## ` → `LibreLex Titolo atto`; from `### ` → `LibreLex Sezione`; a
paragraph that is only `* * * * *` (three to seven asterisks) → `LibreLex Separatore`; only
`contro`/`CONTRO` → `LibreLex Contro`; matching `^- .{2,40} -$` → `LibreLex Ruolo parte`; a
Markdown list item → `LibreLex Punto` (the list numbering is replaced by the literal `- ` or
`N. ` prefix and the list style removed); a `>` quote → `LibreLex Citazione`; a paragraph
starting with `Avv. ` or matching a place-and-date line (`^[A-ZÀ-Ù][a-zà-ù]+, \d{1,2} [a-z]+ \d{4}$`)
among the last five inserted → `LibreLex Firma`; everything else → `LibreLex Corpo`. The
deterministic base text (plain lines from the generators) gets the same heuristics on its
lines before insertion: a short line in capitals is written as `### `, the first line as `## `,
a line starting with `ILL.MO`/`TRIBUNALE`/`GIUDICE DI PACE`/`CORTE` as `# `, `Si allegano:` and
the numbered lines under it as list items, `[Luogo], [Data]` and `Avv. [LEGALE]` as signature
lines.

The recipe's style section is rewritten to match: `# ` for the court heading, `## ` for the
title, `### ` for the sections, `- ` items for premesse, motivi and documents, `> ` for norm
text, the party roles as `- ricorrente -` lines, `contro` alone, `* * * * *` between the parts,
signature lines at the end; plain text otherwise, bold for the party names.

### 5.4 Dev CLI and scripts

`scripts/make_letterhead.py NAME SOURCE [--out DIR]` builds a template from an odt/docx/doc or
a PDF (headless LibreOffice, the same code the panel uses, importable from the extension
package); `librelex-dev` is not involved (no LibreOffice in the core).

## 6. Security and data

- Attachments and reference act: read in hidden, read-only, macro-free documents closed at
  once; the texts leave the machine only after consent naming the files; never logged; the
  panel keeps names and sizes only.
- Templates: private files under the user's config dir; the extension writes only new
  templates it is asked to create and never overwrites; `modelli.json` holds names and paths.
- Drop target: one or more local `file://` URIs; anything else refused with a status line.
- The `LibreLex` styles never overwrite a style the lawyer defined in the template.

## 7. Tests

- Core: `set_attachments` and `leggi_allegato` with consent (scope, joined names, deny
  remembered until the set changes), the draft message listing, the recipe needles, the CLI
  `--allegato`.
- Extension pure: the step layout tables (four steps, one height, no overlaps), the session
  mirror (`step`, `log`, attachments, letterheads, transitions on questions, completion,
  interruption, errors), the style heuristics (`_act_style_for(paragraph)` as a pure function
  over the paragraph text and its Markdown origin), the base-text pre-formatting.
- Headless: `read_document` on odt, docx, doc, txt and on a PDF exported by Writer with a
  header image and two pages (lines rebuilt, page separators); `apply_letterhead` from an
  `.ott` built in the test (header image present in the document afterwards, `LibreLex`
  styles created, a pre-existing `LibreLex Corpo` kept); `make_letterhead` from an odt and
  from a PDF (both produce an `.ott` whose page style has a header with an image and a
  footer with text); an insertion restyled by pattern (each style found on the right
  paragraph); the e2e drafting test extended with an attachment read after consent and the
  act's paragraphs carrying the `LibreLex` styles on the letterhead's page style.
- The lawyer's field test: the step flow, the collapse of the other panels, the drop of a PDF
  attachment, the look of the act on both letterheads.

## 8. Assumptions to validate in the first task of each plan

1. `XSidebarProvider.getSidebar().getDecks()` reaches the LibreLex deck's panels from the
   panel's frame on 26.8, and `collapse()` takes effect without a re-layout call (else
   `requestLayout()`).
2. The Draw PDF import gives one text frame per word for justified text (observed on the SAPG
   diffida): the line rebuild must merge frames whose vertical centres differ by less than half
   a line height.
3. The Markdown filter's list items can be converted to plain `LibreLex Punto` paragraphs by
   setting `NumberingRules` to `None` and `ParaStyleName`, keeping the text.

## 9. Amendments

- Guided-drafting design §6.1 and §6.2: replaced by §3 here (one panel, four steps, the log,
  the attachments and letterhead controls); §5.2: the reading function generalised.
- Main spec §5.1: four panels; §5.3: `apply_letterhead`, `read_document` are adapter helpers,
  not document actions of the core; §5.4 item 5 ("only paragraph styles are applied") holds:
  the act styles are paragraph styles; §8.2: consent scope `attachments`; Appendix A:
  `set_attachments`, `Final.summary.allegati`, `leggi_allegato`.
