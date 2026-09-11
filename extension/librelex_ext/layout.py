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
    Control("FixedText", "ProblemsLabel", 4, 174, 182, 10,
            {"Label": "Problemi (clic per andare al paragrafo)"}),
    Control("ListBox", "Problems", 4, 185, 182, 40, {"Dropdown": False}),
    Control("Edit", "Input", 4, 229, 142, 14, {}),
    Control("Button", "Send", 150, 229, 36, 14, {"Label": "Invia", "Enabled": False,
                                                 "HelpText": "La chat arriva con la versione M2"}),
    Control("Button", "VerifyDocument", 4, 247, 89, 16, {"Label": "Verifica citazioni"}),
    Control("Button", "VerifySelection", 97, 247, 89, 16, {"Label": "Verifica selezione"}),
    Control("Button", "InsertNorm", 4, 267, 89, 16, {"Label": "Inserisci norma"}),
    Control("Button", "Cancel", 97, 267, 89, 16, {"Label": "Annulla", "Enabled": False}),
    Control("Button", "Research", 4, 287, 58, 16, {"Label": "Ricerca", "Enabled": False}),
    Control("Button", "Draft", 66, 287, 58, 16, {"Label": "Redigi da modello", "Enabled": False}),
    Control("Button", "Review", 128, 287, 58, 16, {"Label": "Rivedi selezione", "Enabled": False}),
    Control("FixedText", "Status", 4, 307, 182, 20, {"Label": "Pronto", "MultiLine": True}),
    Control("FixedText", "Usage", 4, 329, 182, 10, {"Label": ""}),
    Control("Button", "Settings", 4, 343, 89, 16, {"Label": "Impostazioni"}),
]

# button name → action command handled by the panel
ACTIONS = {"VerifyDocument": "verify_document", "VerifySelection": "verify_selection",
           "InsertNorm": "insert_norm", "Cancel": "cancel", "Settings": "settings"}

# controls disabled while a request is running
BUSY_DISABLED = ("VerifyDocument", "VerifySelection", "InsertNorm")
