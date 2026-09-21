# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Control table of the sidebar panel (dialog units), as a function of the panel width.

Pure arithmetic and pure data: no UNO import, so the whole layout is unit-tested on the dev
machine. The panel feeds the table to ``window.getModel()`` (spec §5.1) and re-applies it
when the sidebar is resized.
"""
from __future__ import annotations

from dataclasses import dataclass, field

NOTICE = "Le citazioni vanno sempre controllate dal professionista."
WIDTH = 190          # default width of the sidebar deck, used by the static CONTROLS table
MIN_WIDTH = 170      # below this the two-column button grid stops being readable

MARGIN = 4
GAP = 4
BOLD = 150.0         # com.sun.star.awt.FontWeight.BOLD, i.e. FontDescriptor.Weight

LABEL_H = 10
SECTION_H = 10
BUTTON_H = 16
SMALL_BUTTON_W = 40
SMALL_BUTTON_H = 12
NOTICE_H = 16        # two lines
REFERENCE_LABEL_H = 18   # two lines: the example makes it long
INPUT_H = 14
CONSENT_TEXT_H = 40     # four lines: model, endpoint, retention and character count
PROGRESS_H = 8
STATUS_H = 20        # two lines

KINDS = ("Actions", "Drafting", "Citations", "Answers")
CITATIONS_H = 96
TRANSCRIPT_MIN_H = 120
TRANSCRIPT_H = 260      # initial/preferred height; the panel resizes it to fill its window
HINT_H = 18

HINT = "Clic su una voce: vai al paragrafo e mostra il testo nelle Risposte."

# guided drafting (spec §10): the model fills a fixed number of template fields / open
# questions, so the panel pre-allocates that many rows and toggles Visible per row.
FIELD_ROWS = 8
NOTES_H = 30
QUESTION_LABEL_H = 20

# the consent block (spec §8.2), in reading order; the panel maps each name onto a wire
# decision. "Per questo documento" gets a full-width row of its own (see build): §8.2 fixes
# the wording, and 20 characters do not fit a third of the deck width.
CONSENT_BUTTONS = ("ConsentDocument", "ConsentOnce", "ConsentDeny")
CONSENT_LABELS = ("Per questo documento", "Solo stavolta", "Annulla")

# drafting workbench (design §3): one Redazione panel, one fixed-height area (DRAFT_AREA_H
# dialog units) shared by four steps; every step lays its controls out from y = MARGIN and
# is pre-created (Visible toggles at runtime, like the consent block above), so no control is
# ever created after the panel is built. DRAFT_STEPS lists, per step, the control names that
# belong to it; DRAFT_SHARED lists the controls every step shares (the status line, below the
# area); DRAFT_CONSENT is the drafting's own consent block (steps 2 and 3 both ask through it,
# positioned once at the bottom of the shared area).
DRAFT_AREA_H = 404
LOG_H = 200
EXPECTED_H = 80
ATTACHMENTS_H = 36
SUMMARY_H = 140
STEP_PARTITIONS_H = 60
DRAFT_CONSENT_TEXT_H = 40
DRAFT_CONSENT_H = DRAFT_CONSENT_TEXT_H + GAP + BUTTON_H + GAP + BUTTON_H
LETTERHEAD_LABEL_W = 60
REFERENCE_ROW_H = 16

DRAFT_CONSENT = ("DraftConsentText", "DraftConsentDocument", "DraftConsentOnce",
                  "DraftConsentDeny")

DRAFT_STEPS: dict[int, tuple[str, ...]] = {
    1: ("TemplateSearch", "TemplateRefresh", "Template", "TemplateNotes", "FieldsLabel",
        *(f"FieldLabel{n}" for n in range(1, FIELD_ROWS + 1)),
        *(f"Field{n}" for n in range(1, FIELD_ROWS + 1)),
        "NotesLabel", "Notes", "AttachmentsLabel", "Attachments", "AttachmentAdd",
        "AttachmentRemove", "ReferenceInfo", "ReferenceBrowse", "ReferenceClear",
        "LetterheadLabel", "Letterhead", "LetterheadAdd", "Start"),
    2: ("QuestionsHint",
        *(f"QuestionLabel{n}" for n in range(1, FIELD_ROWS + 1)),
        *(f"Answer{n}" for n in range(1, FIELD_ROWS + 1)),
        "Continue", *DRAFT_CONSENT),
    3: ("Log", "ExpectedLabel", "Expected", "DraftCancel", *DRAFT_CONSENT),
    4: ("PartitionsLabel", "Partitions", "Summary", "VerifyAct", "ResumeInput", "Resume",
        "NewDraft"),
}
DRAFT_SHARED = ("DraftStatus",)

# the two copies FieldsLabel toggles between (design review §5 item 14): no template chosen
# yet, and a template chosen (the panel writes the second back in on set_template)
FIELDS_LABEL_EMPTY = "Campi del modello: scegli prima un atto dal catalogo"
FIELDS_LABEL_CHOSEN = "Campi del modello"

# section label → its copy (the panel appends the count to "Citazioni")
SECTIONS: dict[str, str] = {
    "DocumentLabel": "Documento",
    "ReferenceLabel": "Messaggio, domanda o riferimento (es. art. 2043 c.c.)",
    "FieldsLabel": FIELDS_LABEL_EMPTY,
    "NotesLabel": "Fatti e note",
    "PartitionsLabel": "Partizioni inserite",
    "AttachmentsLabel": "Allegati del fascicolo (Doc. 1, 2, …)",
    "ExpectedLabel": "Partizioni attese",
    "LetterheadLabel": "Carta intestata",
}

# control name → HelpText shown on hover (every button has one)
TOOLTIPS: dict[str, str] = {
    "ListCitations": "Trova tutte le citazioni del documento senza consultare le fonti",
    "VerifyDocument": ("Controlla esistenza ed estremi sulle fonti ufficiali; "
                       "segnala i problemi con commenti"),
    "VerifySelection": "Come Verifica citazioni, solo sul testo selezionato",
    "ShowText": ("Mostra nel pannello il testo del riferimento scritto qui sopra "
                 "o selezionato nel documento"),
    "InsertNorm": "Inserisce il testo vigente dell'articolo al cursore, come revisione",
    "Send": "Chiedi al modello; il testo del documento viene inviato solo dopo il tuo consenso",
    "Research": ("Cerca precedenti sulla domanda scritta qui sopra (o sul testo selezionato) "
                 "e inserisce le massime al cursore come revisione"),
    "ConsentDocument": "Consente l'invio del testo per tutte le richieste di questo documento",
    "ConsentOnce": "Consente l'invio del testo solo per questa richiesta",
    "ConsentDeny": "Nega l'invio e interrompe la richiesta",
    "Cancel": "Interrompe la richiesta in corso",
    "Clear": "Svuota le risposte",
    "Settings": "Percorso del file di configurazione e del log",
    "Citations": "Clic su una citazione: vai al paragrafo e mostra il testo",
    "TemplateSearch": "Parola chiave del tipo di atto (es. ingiuntivo, precetto, privacy)",
    "TemplateRefresh": ("Filtra il catalogo dei modelli di atto con il testo scritto a sinistra "
                        "(vuoto: tutto il catalogo)"),
    "Template": "Tipo di atto da redigere: scegli e compila i campi",
    "Notes": "Fatti del caso e istruzioni per il modello, in forma libera",
    "ReferenceBrowse": ("Scegli un atto simile (odt, docx, rtf, txt) da cui il modello prende "
                        "struttura e stile, mai i fatti"),
    "ReferenceClear": "Toglie l'atto di riferimento",
    "Start": ("Avvia la redazione: la base deterministica entra subito nel documento, poi il "
              "modello chiede i dati mancanti"),
    "Partitions": "Clic su una partizione: vai al paragrafo",
    "Resume": "Riprende la redazione, con l'istruzione scritta qui sopra se ne dai una",
    "Continue": "Invia le risposte al modello",
    "AttachmentAdd": ("Aggiunge un documento del caso (pdf, odt, docx, doc, rtf, txt): il "
                      "modello lo legge per i fatti dopo il tuo consenso"),
    "AttachmentRemove": "Toglie l'allegato selezionato",
    "Attachments": "I documenti del caso, numerati come nell'atto",
    "LetterheadAdd": "Crea un modello di carta intestata da un file odt, docx o doc dello studio",
    "Letterhead": "Carta intestata su cui impaginare l'atto",
    "DraftCancel": "Interrompe la redazione in corso",
    "VerifyAct": "Controlla le citazioni dell'atto sulle fonti ufficiali",
    "NewDraft": "Torna al primo passo per un altro atto; allegati e carta intestata restano",
    "Log": "Attività del modello durante la redazione",
    "Expected": "Partizioni dell'atto: ✓ quelle già inserite",
    "DraftConsentDocument": "Consente l'invio del testo per tutta la redazione",
    "DraftConsentOnce": "Consente l'invio del testo solo per questo turno",
    "DraftConsentDeny": "Nega l'invio e interrompe la redazione",
}


@dataclass(frozen=True)
class Control:
    kind: str            # UnoControl<kind>Model
    name: str
    x: int
    y: int
    w: int
    h: int
    props: dict = field(default_factory=dict)


def build(kind: str, width: int) -> list[Control]:
    """Controls of one panel ``kind`` for a deck ``width`` dialog units wide (clamped).

    Only the horizontal geometry depends on the width: heights and the control set are
    fixed, so ``total_height`` is stable and the sidebar never has to reflow vertically.
    """
    if kind not in KINDS:
        raise ValueError(f"unknown panel kind: {kind}")
    width = max(int(width), MIN_WIDTH)
    inner = width - 2 * MARGIN
    col = (width - 12) // 2              # two-column button grid, GAP between the columns
    right = width - MARGIN - col
    controls: list[Control] = []
    y = MARGIN

    def section(name: str, height: int = SECTION_H, w: int = inner) -> None:
        controls.append(Control("FixedText", name, MARGIN, y, w, height,
                                {"Label": SECTIONS[name], "FontWeight": BOLD,
                                 "MultiLine": True}))

    def button(name: str, label: str, x: int, w: int = col, h: int = BUTTON_H,
               **props: object) -> None:
        controls.append(Control("Button", name, x, y, w, h,
                                {"Label": label, "HelpText": TOOLTIPS[name], **props}))

    if kind == "Actions":
        controls.append(Control("FixedText", "Notice", MARGIN, y, inner, NOTICE_H,
                                {"Label": NOTICE, "MultiLine": True}))
        y += NOTICE_H + GAP

        section("DocumentLabel")
        y += SECTION_H + GAP
        button("ListCitations", "Elenca citazioni", MARGIN)
        button("VerifyDocument", "Verifica citazioni", right)
        y += BUTTON_H + GAP
        button("VerifySelection", "Verifica selezione", MARGIN)
        button("Cancel", "Annulla", right, Enabled=False)
        y += BUTTON_H + GAP

        section("ReferenceLabel", REFERENCE_LABEL_H)
        y += REFERENCE_LABEL_H + GAP
        controls.append(Control("Edit", "Input", MARGIN, y, inner, INPUT_H, {}))
        y += INPUT_H + GAP
        button("Send", "Invia", MARGIN)
        button("Research", "Ricerca", right)
        y += BUTTON_H + GAP
        button("ShowText", "Mostra testo", MARGIN)
        button("InsertNorm", "Inserisci norma", right)
        y += BUTTON_H + GAP

        # Consent block (spec §8.2): it keeps its slot in the table at all times, so showing
        # it never moves the controls under it; set_consent only flips the four visibilities.
        controls.append(Control("FixedText", "ConsentText", MARGIN, y, inner, CONSENT_TEXT_H,
                                {"Label": "", "MultiLine": True, "Visible": False}))
        y += CONSENT_TEXT_H + GAP
        # the longest label ("Per questo documento") takes the whole width; the other two
        # share the standard two-column row below it
        button(CONSENT_BUTTONS[0], CONSENT_LABELS[0], MARGIN, inner, Visible=False)
        y += BUTTON_H + GAP
        button(CONSENT_BUTTONS[1], CONSENT_LABELS[1], MARGIN, Visible=False)
        button(CONSENT_BUTTONS[2], CONSENT_LABELS[2], right, Visible=False)
        y += BUTTON_H + GAP

        controls.append(Control("ProgressBar", "Progress", MARGIN, y, inner, PROGRESS_H,
                                {"Visible": False}))
        y += PROGRESS_H + GAP
        controls.append(Control("FixedText", "Status", MARGIN, y, inner, STATUS_H,
                                {"Label": "Pronto", "MultiLine": True}))
        y += STATUS_H + GAP

        button("Settings", "Impostazioni", MARGIN)
        controls.append(Control("FixedText", "Usage", right, y + 3, col, LABEL_H,
                                {"Label": "", "Align": 2}))
    elif kind == "Drafting":
        # Drafting workbench (design §3): one panel, four steps sharing DRAFT_AREA_H dialog
        # units. Every step is a self-contained block laid out from its own y = MARGIN; only
        # step 1 starts Visible, the rest toggle on as the drafting moves through its steps
        # (the technique of the consent block below). The consent block is positioned once,
        # at the bottom of the shared area, and belongs to both step 2 and step 3.
        def step1() -> list[Control]:
            y = MARGIN
            rows: list[Control] = []

            def section1(name: str) -> None:
                # FixedLine, not FixedText (design review §5 item 9): a section rule with its
                # own emphasis, so no FontWeight/TextColor is needed to read as a header.
                rows.append(Control("FixedLine", name, MARGIN, y, inner, SECTION_H,
                                    {"Label": SECTIONS[name]}))

            def button1(name: str, label: str, x: int, w: int = col, h: int = BUTTON_H,
                        **props: object) -> None:
                rows.append(Control("Button", name, x, y, w, h,
                                    {"Label": label, "HelpText": TOOLTIPS[name], **props}))

            search_w = inner - SMALL_BUTTON_W - GAP
            rows.append(Control("Edit", "TemplateSearch", MARGIN, y, search_w, INPUT_H,
                                {"HelpText": TOOLTIPS["TemplateSearch"]}))
            button1("TemplateRefresh", "Cerca", width - MARGIN - SMALL_BUTTON_W,
                    SMALL_BUTTON_W, INPUT_H)
            y += INPUT_H + GAP

            rows.append(Control("ListBox", "Template", MARGIN, y, inner, INPUT_H,
                                {"Dropdown": True, "LineCount": 12,
                                 "HelpText": TOOLTIPS["Template"]}))
            y += INPUT_H + GAP
            rows.append(Control("FixedText", "TemplateNotes", MARGIN, y, inner, 20,
                                {"Label": "", "MultiLine": True}))
            y += 20 + GAP

            section1("FieldsLabel")
            y += SECTION_H + GAP
            label_w = (inner * 2) // 5
            for n in range(1, FIELD_ROWS + 1):
                rows.append(Control("FixedText", f"FieldLabel{n}", MARGIN, y, label_w, INPUT_H,
                                    {"Label": "", "MultiLine": False, "Visible": False}))
                rows.append(Control("Edit", f"Field{n}", MARGIN + label_w + GAP, y,
                                    inner - label_w - GAP, INPUT_H, {"Visible": False}))
                y += INPUT_H
            y += GAP

            section1("NotesLabel")
            y += SECTION_H + GAP
            rows.append(Control("Edit", "Notes", MARGIN, y, inner, NOTES_H,
                                {"MultiLine": True, "VScroll": True, "AutoVScroll": True,
                                 "HelpText": TOOLTIPS["Notes"]}))
            y += NOTES_H + GAP

            section1("AttachmentsLabel")
            y += SECTION_H + GAP
            rows.append(Control("ListBox", "Attachments", MARGIN, y, inner, ATTACHMENTS_H,
                                {"Dropdown": False, "HelpText": TOOLTIPS["Attachments"]}))
            y += ATTACHMENTS_H + GAP
            button1("AttachmentAdd", "Aggiungi…", MARGIN)
            button1("AttachmentRemove", "Togli", right, Enabled=False)
            y += BUTTON_H + GAP

            ref_w = inner - 2 * (SMALL_BUTTON_W + GAP)
            rows.append(Control("FixedText", "ReferenceInfo", MARGIN, y, ref_w,
                                REFERENCE_ROW_H,
                                {"Label": "Caso simile: nessuno", "MultiLine": True}))
            rows.append(Control("Button", "ReferenceBrowse",
                                width - MARGIN - 2 * SMALL_BUTTON_W - GAP, y,
                                SMALL_BUTTON_W, INPUT_H,
                                {"Label": "Sfoglia…", "HelpText": TOOLTIPS["ReferenceBrowse"]}))
            rows.append(Control("Button", "ReferenceClear", width - MARGIN - SMALL_BUTTON_W, y,
                                SMALL_BUTTON_W, INPUT_H,
                                {"Label": "Rimuovi", "HelpText": TOOLTIPS["ReferenceClear"],
                                 "Enabled": False}))
            y += REFERENCE_ROW_H + GAP

            # LetterheadLabel is an inline row label ("Carta intestata" next to the list box
            # and the button), not a section header: FixedText, never the section1 FixedLine.
            rows.append(Control("FixedText", "LetterheadLabel", MARGIN, y,
                                LETTERHEAD_LABEL_W, INPUT_H,
                                {"Label": SECTIONS["LetterheadLabel"], "MultiLine": False}))
            lh_x = MARGIN + LETTERHEAD_LABEL_W + GAP
            lh_w = (width - MARGIN - SMALL_BUTTON_W - GAP) - lh_x
            rows.append(Control("ListBox", "Letterhead", lh_x, y, lh_w, INPUT_H,
                                {"Dropdown": True, "LineCount": 8,
                                 "HelpText": TOOLTIPS["Letterhead"]}))
            rows.append(Control("Button", "LetterheadAdd", width - MARGIN - SMALL_BUTTON_W, y,
                                SMALL_BUTTON_W, INPUT_H,
                                {"Label": "Aggiungi…", "HelpText": TOOLTIPS["LetterheadAdd"]}))
            y += INPUT_H + GAP

            button1("Start", "Avvia redazione", MARGIN, inner, Enabled=False)
            return rows

        def step2() -> list[Control]:
            y = MARGIN
            rows: list[Control] = [Control(
                "FixedText", "QuestionsHint", MARGIN, y, inner, 20,
                {"Label": ("Il modello ha bisogno di questi dati: rispondi e premi Continua; "
                           "una casella vuota vale come risposta non disponibile."),
                 "MultiLine": True, "Visible": False})]
            y += 20 + GAP
            for n in range(1, FIELD_ROWS + 1):
                rows.append(Control("FixedText", f"QuestionLabel{n}", MARGIN, y, inner,
                                    QUESTION_LABEL_H,
                                    {"Label": "", "MultiLine": True, "Visible": False}))
                y += QUESTION_LABEL_H
                rows.append(Control("Edit", f"Answer{n}", MARGIN, y, inner, INPUT_H,
                                    {"Visible": False}))
                y += INPUT_H
            y += GAP
            rows.append(Control("Button", "Continue", MARGIN, y, inner, BUTTON_H,
                                {"Label": "Continua", "HelpText": TOOLTIPS["Continue"],
                                 "Visible": False}))
            return rows

        def step3() -> list[Control]:
            y = MARGIN
            rows: list[Control] = [Control(
                "Edit", "Log", MARGIN, y, inner, LOG_H,
                {"MultiLine": True, "ReadOnly": True, "VScroll": True, "AutoVScroll": True,
                 "HelpText": TOOLTIPS["Log"], "Visible": False})]
            y += LOG_H + GAP
            rows.append(Control("FixedLine", "ExpectedLabel", MARGIN, y, inner, SECTION_H,
                                {"Label": SECTIONS["ExpectedLabel"], "Visible": False}))
            y += SECTION_H + GAP
            rows.append(Control("ListBox", "Expected", MARGIN, y, inner, EXPECTED_H,
                                {"Dropdown": False, "HelpText": TOOLTIPS["Expected"],
                                 "Visible": False}))
            y += EXPECTED_H + GAP
            rows.append(Control("Button", "DraftCancel", MARGIN, y, inner, BUTTON_H,
                                {"Label": "Annulla", "HelpText": TOOLTIPS["DraftCancel"],
                                 "Enabled": False, "Visible": False}))
            return rows

        def step4() -> list[Control]:
            y = MARGIN
            rows: list[Control] = [Control(
                "FixedLine", "PartitionsLabel", MARGIN, y, inner, SECTION_H,
                {"Label": SECTIONS["PartitionsLabel"], "Visible": False})]
            y += SECTION_H + GAP
            rows.append(Control("ListBox", "Partitions", MARGIN, y, inner, STEP_PARTITIONS_H,
                                {"Dropdown": False, "HelpText": TOOLTIPS["Partitions"],
                                 "Visible": False}))
            y += STEP_PARTITIONS_H + GAP
            rows.append(Control("Edit", "Summary", MARGIN, y, inner, SUMMARY_H,
                                {"MultiLine": True, "ReadOnly": True, "VScroll": True,
                                 "Visible": False}))
            y += SUMMARY_H + GAP
            rows.append(Control("Button", "VerifyAct", MARGIN, y, inner, BUTTON_H,
                                {"Label": "Verifica citazioni", "HelpText": TOOLTIPS["VerifyAct"],
                                 "Visible": False}))
            y += BUTTON_H + GAP
            rows.append(Control("Edit", "ResumeInput", MARGIN, y, inner, INPUT_H,
                                {"Visible": False}))
            y += INPUT_H + GAP
            rows.append(Control("Button", "Resume", MARGIN, y, inner, BUTTON_H,
                                {"Label": "Riprendi", "HelpText": TOOLTIPS["Resume"],
                                 "Visible": False}))
            y += BUTTON_H + GAP
            rows.append(Control("Button", "NewDraft", MARGIN, y, inner, BUTTON_H,
                                {"Label": "Nuova redazione", "HelpText": TOOLTIPS["NewDraft"],
                                 "Visible": False}))
            return rows

        def consent_block() -> list[Control]:
            y = MARGIN + DRAFT_AREA_H - DRAFT_CONSENT_H
            rows: list[Control] = [Control(
                "FixedText", "DraftConsentText", MARGIN, y, inner, DRAFT_CONSENT_TEXT_H,
                {"Label": "", "MultiLine": True, "Visible": False})]
            y += DRAFT_CONSENT_TEXT_H + GAP
            rows.append(Control("Button", "DraftConsentDocument", MARGIN, y, inner, BUTTON_H,
                                {"Label": CONSENT_LABELS[0],
                                 "HelpText": TOOLTIPS["DraftConsentDocument"],
                                 "Visible": False}))
            y += BUTTON_H + GAP
            rows.append(Control("Button", "DraftConsentOnce", MARGIN, y, col, BUTTON_H,
                                {"Label": CONSENT_LABELS[1],
                                 "HelpText": TOOLTIPS["DraftConsentOnce"], "Visible": False}))
            rows.append(Control("Button", "DraftConsentDeny", right, y, col, BUTTON_H,
                                {"Label": CONSENT_LABELS[2],
                                 "HelpText": TOOLTIPS["DraftConsentDeny"], "Visible": False}))
            return rows

        controls.extend(step1())
        controls.extend(step2())
        controls.extend(step3())
        controls.extend(step4())
        controls.extend(consent_block())
        controls.append(Control("FixedText", "DraftStatus", MARGIN,
                                MARGIN + DRAFT_AREA_H + GAP, inner, STATUS_H,
                                {"Label": "Scegli un atto", "MultiLine": True}))
    elif kind == "Citations":
        controls.append(Control("FixedText", "CitationsHint", MARGIN, y, inner, HINT_H,
                                {"Label": HINT, "MultiLine": True}))
        y += HINT_H + GAP
        controls.append(Control("ListBox", "Citations", MARGIN, y, inner, CITATIONS_H,
                                {"Dropdown": False, "HelpText": TOOLTIPS["Citations"]}))
    else:  # Answers
        button("Clear", "Svuota", width - MARGIN - SMALL_BUTTON_W, SMALL_BUTTON_W, SMALL_BUTTON_H)
        y += SMALL_BUTTON_H + GAP
        controls.append(Control("Edit", "Transcript", MARGIN, y, inner, TRANSCRIPT_H,
                                {"MultiLine": True, "ReadOnly": True, "VScroll": True,
                                 "AutoVScroll": True}))
    return controls


def build_all(width: int) -> dict[str, list[Control]]:
    """The control table of every panel kind, keyed by kind."""
    return {kind: build(kind, width) for kind in KINDS}


def total_height(controls: list[Control]) -> int:
    """Height the panel needs for ``controls``, bottom margin included (dialog units)."""
    return max(c.y + c.h for c in controls) + MARGIN


def continue_y(n: int) -> int:
    """PositionY (dialog units) of step 2's ``Continue`` button for ``n`` visible questions
    (design review §5 item 12): just under the last visible question row, never below the
    button's own table position (``FIELD_ROWS`` rows, the maximum step2() ever shows).
    """
    n = min(max(int(n), 0), FIELD_ROWS)
    return MARGIN + 20 + GAP + n * (QUESTION_LABEL_H + INPUT_H) + GAP


CONTROLS: dict[str, list[Control]] = build_all(WIDTH)

# button name → action command handled by the panel
ACTIONS = {"VerifyDocument": "verify_document", "VerifySelection": "verify_selection",
           "InsertNorm": "insert_norm", "ShowText": "show_text",
           "ListCitations": "list_citations", "Send": "send", "Research": "research",
           "Cancel": "cancel", "Clear": "clear", "Settings": "settings",
           "ConsentDocument": "consent_document", "ConsentOnce": "consent_once",
           "ConsentDeny": "consent_deny", "TemplateRefresh": "template_search",
           "ReferenceBrowse": "reference_browse", "ReferenceClear": "reference_clear",
           "Start": "draft_start", "Resume": "draft_resume", "Continue": "draft_answer",
           "AttachmentAdd": "attachment_add", "AttachmentRemove": "attachment_remove",
           "LetterheadAdd": "letterhead_add", "DraftCancel": "cancel",
           "VerifyAct": "verify_act", "NewDraft": "draft_new",
           "DraftConsentDocument": "consent_document", "DraftConsentOnce": "consent_once",
           "DraftConsentDeny": "consent_deny"}

# controls disabled while a request is running; the consent buttons are deliberately absent,
# since answering a consent_request is the one thing the user does while the core is busy;
# DraftCancel is likewise absent (it is enabled only while busy, like Cancel)
BUSY_DISABLED = ("VerifyDocument", "VerifySelection", "InsertNorm", "ShowText", "ListCitations",
                 "Send", "Research", "TemplateRefresh", "ReferenceBrowse", "ReferenceClear",
                 "Start", "Resume", "Continue", "AttachmentAdd", "AttachmentRemove",
                 "LetterheadAdd", "Letterhead", "VerifyAct", "NewDraft")
