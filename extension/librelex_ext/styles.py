# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""The LibreLex act style canon (design §5.1) and the pattern that assigns a style to a
drafting insertion (design §5.3). Pure: no UNO here, ``document.py`` converts the property
dicts to UNO structs and creates the paragraph styles.
"""
from __future__ import annotations

import re

STYLE_PREFIX = "LibreLex "

COMMON = {
    "CharFontName": "Times New Roman",
    "CharHeight": 12.0,
    "ParaLineSpacing": ("PROP", 150),
    "ParaFirstLineIndent": 0,
    "ParaTopMargin": 0,
    "ParaBottomMargin": 0,
}

ACT_STYLES: dict[str, dict] = {
    "LibreLex Intestazione": {"ParaAdjust": "CENTER", "ParaBottomMargin": 200},
    "LibreLex Titolo atto": {"ParaAdjust": "CENTER", "CharWeight": 150.0},
    "LibreLex Sezione": {"ParaAdjust": "CENTER", "CharWeight": 150.0, "ParaTopMargin": 300},
    "LibreLex Corpo": {"ParaAdjust": "BLOCK"},
    "LibreLex Punto": {"ParaAdjust": "BLOCK", "ParaLeftMargin": 500, "ParaFirstLineIndent": -500},
    "LibreLex Ruolo parte": {"ParaAdjust": "RIGHT", "CharWeight": 150.0},
    "LibreLex Contro": {"ParaAdjust": "CENTER", "CharWeight": 150.0},
    "LibreLex Separatore": {"ParaAdjust": "CENTER"},
    "LibreLex Citazione": {
        "ParaAdjust": "BLOCK", "ParaLeftMargin": 1000, "ParaRightMargin": 1000, "CharHeight": 11.0,
    },
    "LibreLex Firma": {"ParaAdjust": "RIGHT"},
}

ORIGINS = ("heading1", "heading2", "heading3", "list", "quote", "body")

_SEPARATOR_RE = re.compile(r"^(\*\s*){3,7}$")
_ROLE_RE = re.compile(r"^- .{2,40} -$")
_SIGNATURE_DATE_RE = re.compile(r"^[A-ZÀ-Ù][a-zà-ù]+, \d{1,2} [a-z]+ \d{4}$")


def style_properties(name: str) -> dict:
    return {**COMMON, **ACT_STYLES[name]}


def act_style_for(text: str, origin: str, from_end: int) -> str:
    """The act style for one inserted paragraph (design §5.3, first match wins)."""
    stripped = text.strip()
    if origin == "heading1":
        return "LibreLex Intestazione"
    if origin == "heading2":
        return "LibreLex Titolo atto"
    if origin == "heading3":
        return "LibreLex Sezione"
    if _SEPARATOR_RE.match(stripped):
        return "LibreLex Separatore"
    if stripped.lower() == "contro":
        return "LibreLex Contro"
    if _ROLE_RE.match(stripped):
        return "LibreLex Ruolo parte"
    if origin == "list":
        return "LibreLex Punto"
    if origin == "quote":
        return "LibreLex Citazione"
    if (stripped == "[Luogo], [Data]"
            or (from_end < 5 and (stripped.startswith("Avv. ")
                                  or _SIGNATURE_DATE_RE.match(stripped)))):
        return "LibreLex Firma"
    return "LibreLex Corpo"


def list_prefix(label: str) -> str:
    """The literal text a list item's numbering is replaced with (design §5.3)."""
    digits = ""
    for ch in label:
        if not ch.isdigit():
            break
        digits += ch
    return f"{digits}. " if digits else "- "
