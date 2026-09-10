# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import re

from librelex_core.citations.acts import ABBREV_PATTERN, ABBREVIATIONS, canonical_act, resolve_act


def test_codes_resolve_case_and_dots():
    assert resolve_act("c.c.").label == "c.c."
    assert resolve_act("C.C").label == "c.c."
    assert resolve_act("cod. civ.").label == "c.c."
    assert resolve_act("c.p.c.").label == "c.p.c."
    assert resolve_act("Cost.").label == "Cost."
    assert resolve_act("xyz") is None


def test_numbered_acts():
    dlgs = resolve_act("d.lgs.")
    assert dlgs.numbered and canonical_act(dlgs, "196", "2003") == "D.Lgs. 196/2003"
    assert canonical_act(resolve_act("legge"), "241", "1990") == "L. 241/1990"
    assert canonical_act(resolve_act("d.p.r."), "445", "2000") == "D.P.R. 445/2000"


def test_eu_acts_keep_raw_numbering():
    reg = resolve_act("regolamento (ue)")
    assert reg.eu and canonical_act(reg, "2016", "679") == "regolamento UE 2016/679"
    assert canonical_act(resolve_act("gdpr"), None, None) == "GDPR"
    assert canonical_act(resolve_act("direttiva"), "95", "46") == "direttiva 95/46/CE"


def test_pattern_prefers_longest_key():
    m = re.match(ABBREV_PATTERN, "codice di procedura civile", re.IGNORECASE)
    assert m and m.group(0) == "codice di procedura civile"
    assert re.fullmatch(ABBREV_PATTERN, "d.lgs.", re.IGNORECASE)


def test_table_size_and_uniqueness():
    assert len(ABBREVIATIONS) >= 80
    assert all(k == k.lower() for k in ABBREVIATIONS)
