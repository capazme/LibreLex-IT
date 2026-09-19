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
GRAY = 0x666666      # notice text: present but not shouting
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

KINDS = ("Actions", "Drafting", "Questions", "Citations", "Answers")
CITATIONS_H = 96
TRANSCRIPT_MIN_H = 120
TRANSCRIPT_H = 260      # initial/preferred height; the panel resizes it to fill its window
HINT_H = 18

HINT = "Clic su una voce: vai al paragrafo e mostra il testo nelle Risposte."

# guided drafting (spec §10): the model fills a fixed number of template fields / open
# questions, so the panel pre-allocates that many rows and toggles Visible per row.
FIELD_ROWS = 8
PARTITIONS_H = 48
NOTES_H = 40
QUESTION_LABEL_H = 20

# the consent block (spec §8.2), in reading order; the panel maps each name onto a wire
# decision. "Per questo documento" gets a full-width row of its own (see build): §8.2 fixes
# the wording, and 20 characters do not fit a third of the deck width.
CONSENT_BUTTONS = ("ConsentDocument", "ConsentOnce", "ConsentDeny")
CONSENT_LABELS = ("Per questo documento", "Solo stavolta", "Annulla")

# section label → its copy (the panel appends the count to "Citazioni")
SECTIONS: dict[str, str] = {
    "DocumentLabel": "Documento",
    "ReferenceLabel": "Messaggio, domanda o riferimento (es. art. 2043 c.c.)",
    "FieldsLabel": "Campi del modello",
    "NotesLabel": "Fatti e note",
    "PartitionsLabel": "Partizioni inserite",
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
    "Resume": ("Riprende la redazione dopo un'interruzione, con l'istruzione scritta qui sopra "
              "se ne dai una"),
    "Continue": "Invia le risposte al modello",
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
                                {"Label": NOTICE, "MultiLine": True, "TextColor": GRAY}))
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
                                {"Label": "", "MultiLine": True, "TextColor": GRAY,
                                 "Visible": False}))
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
        # Guided drafting (spec §10): a template search/pick row, then the fields the
        # template declares, notes, an optional reference act, and the drafting controls.
        # The eight Field/Question rows are pre-allocated and packed with no inter-row gap
        # (only Visible toggles at runtime) so the fixed control set still fits the height
        # budget the tests enforce (<=460/<=380 du); GAP separates them from neighbouring
        # sections, as elsewhere in this table.
        search_w = inner - SMALL_BUTTON_W - GAP
        controls.append(Control("Edit", "TemplateSearch", MARGIN, y, search_w, INPUT_H,
                                {"HelpText": TOOLTIPS["TemplateSearch"]}))
        button("TemplateRefresh", "Cerca", width - MARGIN - SMALL_BUTTON_W, SMALL_BUTTON_W,
               INPUT_H)
        y += INPUT_H + GAP

        controls.append(Control("ListBox", "Template", MARGIN, y, inner, INPUT_H,
                                {"Dropdown": True, "LineCount": 12,
                                 "HelpText": TOOLTIPS["Template"]}))
        y += INPUT_H + GAP
        controls.append(Control("FixedText", "TemplateNotes", MARGIN, y, inner, 20,
                                {"Label": "", "MultiLine": True, "TextColor": GRAY}))
        y += 20 + GAP

        section("FieldsLabel")
        y += SECTION_H + GAP
        for n in range(1, FIELD_ROWS + 1):
            label_w = (inner * 2) // 5
            controls.append(Control("FixedText", f"FieldLabel{n}", MARGIN, y, label_w, INPUT_H,
                                    {"Label": "", "MultiLine": False, "Visible": False}))
            controls.append(Control("Edit", f"Field{n}", MARGIN + label_w + GAP, y,
                                    inner - label_w - GAP, INPUT_H, {"Visible": False}))
            y += INPUT_H
        y += GAP

        section("NotesLabel")
        y += SECTION_H + GAP
        controls.append(Control("Edit", "Notes", MARGIN, y, inner, NOTES_H,
                                {"MultiLine": True, "VScroll": True, "AutoVScroll": True,
                                 "HelpText": TOOLTIPS["Notes"]}))
        y += NOTES_H + GAP

        controls.append(Control("FixedText", "ReferenceLabel", MARGIN, y, inner, 20,
                                {"Label": "Caso simile: nessuno", "MultiLine": True}))
        y += 20 + GAP
        button("ReferenceBrowse", "Sfoglia…", MARGIN)
        button("ReferenceClear", "Rimuovi", right, Enabled=False)
        y += BUTTON_H + GAP

        button("Start", "Avvia redazione", MARGIN, inner, Enabled=False)
        y += BUTTON_H + GAP

        section("PartitionsLabel")
        y += SECTION_H + GAP
        controls.append(Control("ListBox", "Partitions", MARGIN, y, inner, PARTITIONS_H,
                                {"Dropdown": False, "HelpText": TOOLTIPS["Partitions"]}))
        y += PARTITIONS_H + GAP

        controls.append(Control("Edit", "ResumeInput", MARGIN, y, inner, INPUT_H,
                                {"Visible": False}))
        y += INPUT_H + GAP
        button("Resume", "Continua la redazione", MARGIN, inner, Visible=False)
        y += BUTTON_H + GAP

        controls.append(Control("FixedText", "DraftStatus", MARGIN, y, inner, STATUS_H,
                                {"Label": "Scegli un atto", "MultiLine": True}))
    elif kind == "Questions":
        controls.append(Control("FixedText", "QuestionsHint", MARGIN, y, inner, 20,
                                {"Label": ("Il modello ha bisogno di questi dati: rispondi e "
                                           "premi Continua."),
                                 "MultiLine": True, "TextColor": GRAY}))
        y += 20 + GAP
        for n in range(1, FIELD_ROWS + 1):
            controls.append(Control("FixedText", f"QuestionLabel{n}", MARGIN, y, inner,
                                    QUESTION_LABEL_H,
                                    {"Label": "", "MultiLine": True, "Visible": False}))
            edit_y = y + QUESTION_LABEL_H + GAP
            controls.append(Control("Edit", f"Answer{n}", MARGIN, edit_y, inner, INPUT_H,
                                    {"Visible": False}))
            y = edit_y + INPUT_H
        y += GAP
        button("Continue", "Continua", MARGIN, inner, Visible=False)
        y += BUTTON_H + GAP
        controls.append(Control("FixedText", "QuestionsStatus", MARGIN, y, inner, LABEL_H,
                                {"Label": "Nessuna domanda in sospeso"}))
    elif kind == "Citations":
        controls.append(Control("FixedText", "CitationsHint", MARGIN, y, inner, HINT_H,
                                {"Label": HINT, "MultiLine": True, "TextColor": GRAY}))
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


CONTROLS: dict[str, list[Control]] = build_all(WIDTH)

# button name → action command handled by the panel
ACTIONS = {"VerifyDocument": "verify_document", "VerifySelection": "verify_selection",
           "InsertNorm": "insert_norm", "ShowText": "show_text",
           "ListCitations": "list_citations", "Send": "send", "Research": "research",
           "Cancel": "cancel", "Clear": "clear", "Settings": "settings",
           "ConsentDocument": "consent_document", "ConsentOnce": "consent_once",
           "ConsentDeny": "consent_deny", "TemplateRefresh": "template_search",
           "ReferenceBrowse": "reference_browse", "ReferenceClear": "reference_clear",
           "Start": "draft_start", "Resume": "draft_resume", "Continue": "draft_answer"}

# controls disabled while a request is running; the consent buttons are deliberately absent,
# since answering a consent_request is the one thing the user does while the core is busy
BUSY_DISABLED = ("VerifyDocument", "VerifySelection", "InsertNorm", "ShowText", "ListCitations",
                 "Send", "Research", "TemplateRefresh", "ReferenceBrowse", "ReferenceClear",
                 "Start", "Resume", "Continue")
