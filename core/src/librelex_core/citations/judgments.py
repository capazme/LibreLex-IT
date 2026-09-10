# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Judgment citation extractor (Cassazione, Consulta, Consiglio di Stato, TAR, CGUE)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Court = Literal["cassazione", "corte_costituzionale", "consiglio_di_stato", "tar", "cgue"]

# Optional fragments shared by the court patterns. Named groups: sez, ssuu, dyear, num, year.
# The year may come after the number ("n. 12345/2024", "n. 999 del 2021") or from a date
# written before it ("12 marzo 2024, n. 12345"); a match with neither is discarded.
_SEZ = (
    r"(?:sez(?:\.|ione|ioni)?\s*"
    r"(?P<sez>unite|un\.?|lav\.?|lavoro|trib\.?|tributaria|[ivxIVX]+|\d+)\s*,?\s*"
    r"|(?P<ssuu>ss\.?\s*uu\.?)\s*,?\s*)?"
)
_DATE = r"(?:\d{1,2}\s+[a-zà]+\s+(?P<dyear>(?:19|20)\d{2})\s*,?\s*)?"
_TIPO = r"(?:sent(?:\.|enza)|ord(?:\.|inanza))?\s*,?\s*"
_NUM = r"(?:n\.?\s*)?(?P<num>\d{1,6})(?:\s*(?:/|\s+del\s+)\s*(?P<year>(?:19|20)\d{2}))?"

_CASS_RE = re.compile(
    r"\bcass(?:\.|azione)?\s*(?:civ\.?|pen\.?|civile|penale)?\s*,?\s*"
    + _SEZ + _DATE + _TIPO + _NUM,
    re.IGNORECASE,
)
_COST_RE = re.compile(
    r"\b(?:corte\s+cost(?:\.|ituzionale)?|c\.\s*cost\.)\s*,?\s*" + _DATE + _TIPO + _NUM,
    re.IGNORECASE,
)
_CDS_RE = re.compile(
    r"\b(?:cons(?:\.|iglio)\s+(?:di\s+)?stato|c\.?\s?d\.?\s?s\.?)\s*,?\s*"
    r"(?:(?:ad\.?\s*plen\.?|adunanza\s+plenaria)\s*,?\s*)?" + _SEZ + _DATE + _TIPO + _NUM,
    re.IGNORECASE,
)
# Case-sensitive on purpose: the seat is one or more capitalised words
# ("Lazio", "Lombardia Milano").
_TAR_RE = re.compile(
    r"\b[Tt]\.?[Aa]\.?[Rr]\.?\s+(?P<seat>[A-ZÀ-Ü][\w'’-]+(?:\s+[A-ZÀ-Ü][\w'’-]+)*)\s*,?\s*"
    + _SEZ + _DATE + _TIPO + _NUM,
)
_CGUE_RE = re.compile(
    r"\b(?:cgue|c\.g\.u\.e\.|corte\s+di\s+giustizia(?:\s+(?:ue|dell['’]unione\s+europea))?)\s*,?\s*"
    + _DATE + r"(?:causa\s+)?(?P<num>[CT]-\d{1,4})/(?P<year>\d{2})",
    re.IGNORECASE,
)


def _norm_section(sez: str | None, ssuu: str | None) -> str | None:
    if ssuu:
        return "un."
    if not sez:
        return None
    s = sez.lower().rstrip(".")
    if s in ("unite", "un"):
        return "un."
    if s in ("lav", "lavoro"):
        return "lav."
    if s in ("trib", "tributaria"):
        return "trib."
    return s.upper() if re.fullmatch(r"[ivx]+", s) else s


@dataclass
class JudgmentCitation:
    start: int
    end: int
    display_text: str
    court: Court
    number: str
    year: str
    section: str | None = None
    seat: str | None = None

    @property
    def verifiable_v1(self) -> bool:
        return self.court == "cassazione"

    def canonical(self) -> str:
        sez = f" sez. {self.section}" if self.section else ""
        if self.court == "cassazione":
            return f"Cass.{sez} n. {self.number}/{self.year}"
        if self.court == "corte_costituzionale":
            return f"Corte cost. n. {self.number}/{self.year}"
        if self.court == "consiglio_di_stato":
            return f"Cons. Stato{sez} n. {self.number}/{self.year}"
        if self.court == "tar":
            return f"TAR {self.seat} n. {self.number}/{self.year}"
        return f"CGUE causa {self.number}/{self.year}"


def _collect(found: list[JudgmentCitation], used: list[tuple[int, int]],
             m: re.Match[str], court: Court) -> None:
    gd = m.groupdict()
    year = gd.get("year") or gd.get("dyear")
    if year is None:
        return
    number = m.group("num")
    if court == "cgue":
        number = number.upper()
    c = JudgmentCitation(m.start(), m.end(), m.group(0), court, number, year,
                         section=_norm_section(gd.get("sez"), gd.get("ssuu")),
                         seat=(gd.get("seat") or "").strip() or None)
    if not any(a < c.end and c.start < b for a, b in used):
        found.append(c)
        used.append((c.start, c.end))


def extract_judgments(text: str) -> list[JudgmentCitation]:
    if not text:
        return []
    found: list[JudgmentCitation] = []
    used: list[tuple[int, int]] = []
    for pattern, court in ((_CASS_RE, "cassazione"), (_COST_RE, "corte_costituzionale"),
                           (_CDS_RE, "consiglio_di_stato"), (_TAR_RE, "tar"), (_CGUE_RE, "cgue")):
        for m in pattern.finditer(text):
            _collect(found, used, m, court)  # type: ignore[arg-type]
    found.sort(key=lambda c: c.start)
    return found
