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
CITATIONS_H = 64
TRANSCRIPT_H = 150
PROGRESS_H = 8
STATUS_H = 20        # two lines

# section label → its copy (the panel appends the count to "Citazioni")
SECTIONS: dict[str, str] = {
    "DocumentLabel": "Documento",
    "ReferenceLabel": "Riferimento (es. art. 2043 c.c., Cass. n. 12345/2024)",
    "CitationsLabel": "Citazioni",
    "TranscriptLabel": "Risposte",
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
    "Cancel": "Interrompe la richiesta in corso",
    "Clear": "Svuota le risposte",
    "Settings": "Percorso del file di configurazione e del log",
    "Citations": "Clic su una citazione: vai al paragrafo e mostra il testo",
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


def build(width: int) -> list[Control]:
    """The control table for a panel ``width`` dialog units wide (clamped to MIN_WIDTH).

    Only the horizontal geometry depends on the width: heights and the control set are
    fixed, so ``total_height`` is stable and the sidebar never has to reflow vertically.
    """
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
    button("ShowText", "Mostra testo", MARGIN)
    button("InsertNorm", "Inserisci norma", right)
    y += BUTTON_H + GAP

    section("CitationsLabel")
    y += SECTION_H + GAP
    controls.append(Control("ListBox", "Citations", MARGIN, y, inner, CITATIONS_H,
                            {"Dropdown": False, "HelpText": TOOLTIPS["Citations"]}))
    y += CITATIONS_H + GAP

    section("TranscriptLabel", w=inner - SMALL_BUTTON_W - GAP)
    button("Clear", "Svuota", width - MARGIN - SMALL_BUTTON_W, SMALL_BUTTON_W, SMALL_BUTTON_H)
    y += SMALL_BUTTON_H + GAP
    controls.append(Control("Edit", "Transcript", MARGIN, y, inner, TRANSCRIPT_H,
                            {"MultiLine": True, "ReadOnly": True, "VScroll": True,
                             "AutoVScroll": True}))
    y += TRANSCRIPT_H + GAP

    controls.append(Control("ProgressBar", "Progress", MARGIN, y, inner, PROGRESS_H,
                            {"Visible": False}))
    y += PROGRESS_H + GAP
    controls.append(Control("FixedText", "Status", MARGIN, y, inner, STATUS_H,
                            {"Label": "Pronto", "MultiLine": True}))
    y += STATUS_H + GAP

    button("Settings", "Impostazioni", MARGIN)
    controls.append(Control("FixedText", "Usage", right, y + 3, col, LABEL_H,
                            {"Label": "", "Align": 2}))
    return controls


def total_height(controls: list[Control]) -> int:
    """Height the panel needs for ``controls``, bottom margin included (dialog units)."""
    return max(c.y + c.h for c in controls) + MARGIN


CONTROLS: list[Control] = build(WIDTH)

# button name → action command handled by the panel
ACTIONS = {"VerifyDocument": "verify_document", "VerifySelection": "verify_selection",
           "InsertNorm": "insert_norm", "ShowText": "show_text",
           "ListCitations": "list_citations", "Cancel": "cancel", "Clear": "clear",
           "Settings": "settings"}

# controls disabled while a request is running
BUSY_DISABLED = ("VerifyDocument", "VerifySelection", "InsertNorm", "ShowText", "ListCitations")
