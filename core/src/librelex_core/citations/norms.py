# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Norm citation extractor.

Port of VisuaLexAPI ``visualex_api/tools/citation_linker.py`` (MIT, same author),
extended with comma capture and canonical forms. State machine: the last act seen
becomes the context for bare "art. N" references that follow.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from librelex_core.citations.acts import ABBREV_PATTERN, ActType, canonical_act, resolve_act

MAX_TEXT_LENGTH = 500_000

_SUFFIX = r"(?:bis|ter|quater|quinquies|sexies|septies|octies|novies|decies)"
_ART_NUM_INNER = rf"\d+(?:\s*-\s*{_SUFFIX}|\s+{_SUFFIX})?"
_ART_NUM = rf"({_ART_NUM_INNER})"
_ART_PREFIX = r"((?:artt?\.?|articol[oi])\s+)"
_COMMA = r"(?:\s*,?\s*(?:co\.|comma|c\.)\s*(\d+))?"
_PARA_N = r"(?:\s*,?\s*n\.\s*\d+)?"
_LETT = r"(?:\s*,?\s*lett\.?\s*[a-z]\)?)?"
_PREP = r"(?:\s*,)?\s*(?:(?:del|della|dello|dell['’]|di)\s+)?"
_NUM_YEAR = r"(?:\s+n\.?\s*)?(?:\s*(\d+)\s*/\s*(\d{2,4}))?"
# "artt. N e M <atto>" / "artt. N, M e P <atto>": at least one "e"/"ed" separator so this
# never overlaps the single-article _EXPLICIT_RE below (review finding 2).
_ART_LIST_INNER = (
    rf"{_ART_NUM_INNER}(?:\s*,\s*{_ART_NUM_INNER})*\s*(?:e|ed)\s*{_ART_NUM_INNER}"
)
_ART_LIST = rf"({_ART_LIST_INNER})"
_ART_NUM_SPLIT_RE = re.compile(_ART_NUM_INNER, re.IGNORECASE)

_EXPLICIT_RE = re.compile(
    _ART_PREFIX + _ART_NUM + _COMMA + _PARA_N + _LETT + _PREP
    + r"(" + ABBREV_PATTERN + r")" + _NUM_YEAR,
    re.IGNORECASE,
)
_MULTI_ART_RE = re.compile(
    _ART_PREFIX + _ART_LIST + _COMMA + _PARA_N + _LETT + _PREP
    + r"(" + ABBREV_PATTERN + r")" + _NUM_YEAR,
    re.IGNORECASE,
)
_STANDALONE_ACT_RE = re.compile(
    r"(?:^|(?<=[\s (\"'’]))(" + ABBREV_PATTERN + r")\s+(?:n\.?\s*)?(\d+)\s*/\s*(\d{2,4})",
    re.IGNORECASE,
)
_BARE_ART_RE = re.compile(_ART_PREFIX + _ART_NUM + _COMMA, re.IGNORECASE)
# A bare article must not silently inherit the act of an unrelated, earlier citation when
# a *different* resolvable act abbreviation shows up later in the same clause (review
# finding 2, e.g. "l'art. 1414, in relazione al c.c.," must not become a D.Lgs. 231/2001
# article just because that act was mentioned in the previous sentence).
# A "." only ends the clause when followed by whitespace + a capital letter (new
# sentence) or by the end of the text; a bare "." inside an abbreviation like "c.c."
# or "art." is not a boundary.
_CLAUSE_BOUNDARY_RE = re.compile(r"\.(?=\s+[A-ZÀ-Ü]|\s*$)|[;\n]")
# No trailing \b: most abbreviations end in "." (a non-word char), so a real \b would
# require a word character right after it and never fire before a comma/period/space.
_ANY_ACT_RE = re.compile(r"\b(?:" + ABBREV_PATTERN + r")(?![A-Za-z0-9])", re.IGNORECASE)


def _act_follows_in_clause(text: str, pos: int) -> bool:
    boundary = _CLAUSE_BOUNDARY_RE.search(text, pos)
    end = boundary.start() if boundary else len(text)
    return _ANY_ACT_RE.search(text, pos, end) is not None


def expand_year(year: str) -> str:
    if len(year) == 4:
        return year
    y = int(year)
    return str(2000 + y) if y <= 30 else str(1900 + y)


@dataclass
class NormCitation:
    start: int
    end: int
    display_text: str
    article: str | None = None
    comma: str | None = None
    act: ActType | None = None
    number: str | None = None
    year: str | None = None

    def canonical(self) -> str | None:
        if self.act is None or self.article is None:
            return None
        if self.act.numbered and not (self.number and self.year):
            # A numbered act with no captured number/year cannot be resolved by
            # verifica_citazioni: rather than hand it a bare act label (which the real
            # server reports as "non trovata" on a citation that is actually valid),
            # leave canonical() unset so the citation lands in the "non interpretabili"
            # list instead of triggering a false problem comment (review finding 1).
            return None
        art = re.sub(r"\s*-\s*", "-", self.article)
        art = re.sub(rf"\s+({_SUFFIX})$", r"-\1", art)
        comma = f" co. {self.comma}" if self.comma else ""
        return f"art. {art}{comma} {canonical_act(self.act, self.number, self.year)}"


NormContext = tuple[ActType, str | None, str | None]


def _year_for(act: ActType, year: str | None) -> str | None:
    if year is None:
        return None
    return year if act.eu else expand_year(year)


def extract_norms(text: str, context: NormContext | None = None) -> list[NormCitation]:
    if not text or not text.strip() or len(text) > MAX_TEXT_LENGTH:
        return []
    found: list[NormCitation] = []
    used: list[tuple[int, int]] = []

    def overlaps(s: int, e: int) -> bool:
        return any(a < e and s < b for a, b in used)

    def register(c: NormCitation) -> None:
        if not overlaps(c.start, c.end):
            found.append(c)
            used.append((c.start, c.end))

    for m in _EXPLICIT_RE.finditer(text):
        act = resolve_act(m.group(4))
        if act is None:
            continue
        number, year = m.group(5), m.group(6)   # EU numbering kept as written (2016/679, 95/46)
        register(NormCitation(m.start(), m.end(), m.group(0), article=m.group(2).strip(),
                              comma=m.group(3), act=act, number=number, year=_year_for(act, year)))

    for m in _MULTI_ART_RE.finditer(text):
        act = resolve_act(m.group(4))
        if act is None:
            continue
        number, year = m.group(5), m.group(6)
        list_str, list_start = m.group(2), m.start(2)
        for num_m in _ART_NUM_SPLIT_RE.finditer(list_str):
            start, end = list_start + num_m.start(), list_start + num_m.end()
            register(NormCitation(start, end, num_m.group(0), article=num_m.group(0).strip(),
                                  comma=m.group(3), act=act, number=number,
                                  year=_year_for(act, year)))

    for m in _STANDALONE_ACT_RE.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        act = resolve_act(m.group(1))
        if act is None:
            continue
        register(NormCitation(m.start(), m.end(), m.group(0), act=act,
                              number=m.group(2), year=_year_for(act, m.group(3))))

    for m in _BARE_ART_RE.finditer(text):
        if overlaps(m.start(), m.end()):
            continue
        register(NormCitation(m.start(), m.end(), m.group(0),
                              article=m.group(2).strip(), comma=m.group(3)))

    found.sort(key=lambda c: c.start)
    current, cur_number, cur_year = context or (None, None, None)
    for c in found:
        if c.act is not None:
            current, cur_number, cur_year = c.act, c.number, c.year
        elif current is not None and not _act_follows_in_clause(text, c.end):
            c.act, c.number, c.year = current, cur_number, cur_year
    return found
