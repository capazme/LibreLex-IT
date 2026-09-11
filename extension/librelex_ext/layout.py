# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Static control table of the sidebar panel (dialog units). Pure data, unit-tested."""
from __future__ import annotations

from dataclasses import dataclass, field

NOTICE = "Le citazioni vanno sempre controllate dal professionista."
WIDTH = 190


@dataclass(frozen=True)
class Control:
    kind: str            # UnoControl<kind>Model
    name: str
    x: int
    y: int
    w: int
    h: int
    props: dict = field(default_factory=dict)


CONTROLS: list[Control] = [
    Control("FixedText", "Notice", 4, 4, 182, 16, {"Label": NOTICE, "MultiLine": True}),
    Control("Edit", "Transcript", 4, 22, 182, 150,
            {"MultiLine": True, "ReadOnly": True, "VScroll": True, "AutoVScroll": True}),
    Control("FixedText", "CitationsLabel", 4, 174, 182, 10,
            {"Label": "Citazioni (clic: vai al paragrafo e mostra il testo)"}),
    Control("ListBox", "Citations", 4, 185, 182, 60, {"Dropdown": False}),
    Control("Edit", "Input", 4, 249, 142, 14, {}),
    Control("Button", "Send", 150, 249, 36, 14, {"Label": "Invia", "Enabled": False,
                                                 "HelpText": "La chat arriva con la versione M2"}),
    Control("Button", "VerifyDocument", 4, 267, 89, 16, {"Label": "Verifica citazioni"}),
    Control("Button", "VerifySelection", 97, 267, 89, 16, {"Label": "Verifica selezione"}),
    Control("Button", "InsertNorm", 4, 287, 89, 16, {"Label": "Inserisci norma"}),
    Control("Button", "ShowText", 97, 287, 89, 16, {"Label": "Mostra testo"}),
    Control("Button", "ListCitations", 4, 307, 89, 16, {"Label": "Elenca citazioni"}),
    Control("Button", "Cancel", 97, 307, 89, 16, {"Label": "Annulla", "Enabled": False}),
    Control("Button", "Research", 4, 327, 58, 16, {"Label": "Ricerca", "Enabled": False}),
    Control("Button", "Draft", 66, 327, 58, 16, {"Label": "Redigi da modello", "Enabled": False}),
    Control("Button", "Review", 128, 327, 58, 16, {"Label": "Rivedi selezione", "Enabled": False}),
    Control("FixedText", "Status", 4, 347, 182, 20, {"Label": "Pronto", "MultiLine": True}),
    Control("FixedText", "Usage", 4, 369, 182, 10, {"Label": ""}),
    Control("Button", "Settings", 4, 383, 89, 16, {"Label": "Impostazioni"}),
]

# button name → action command handled by the panel
ACTIONS = {"VerifyDocument": "verify_document", "VerifySelection": "verify_selection",
           "InsertNorm": "insert_norm", "ShowText": "show_text",
           "ListCitations": "list_citations", "Cancel": "cancel", "Settings": "settings"}

# controls disabled while a request is running
BUSY_DISABLED = ("VerifyDocument", "VerifySelection", "InsertNorm", "ShowText", "ListCitations")
