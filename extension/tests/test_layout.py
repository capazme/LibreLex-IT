# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_ext.layout import ACTIONS, BUSY_DISABLED, CONTROLS, NOTICE, WIDTH


def test_controls_fit_the_panel_and_do_not_overlap():
    names = [c.name for c in CONTROLS]
    assert len(names) == len(set(names))
    for c in CONTROLS:
        assert 0 <= c.x and c.x + c.w <= WIDTH, c.name
    boxes = [(c.x, c.y, c.x + c.w, c.y + c.h) for c in CONTROLS]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (a, b)


def test_required_controls_and_copy():
    by = {c.name: c for c in CONTROLS}
    assert by["Notice"].props["Label"] == NOTICE
    assert NOTICE == "Le citazioni vanno sempre controllate dal professionista."
    assert by["Transcript"].props["ReadOnly"] is True and by["Send"].props["Enabled"] is False
    for name in ("Research", "Draft", "Review"):
        assert by[name].props["Enabled"] is False
    assert set(ACTIONS) <= set(by) and set(BUSY_DISABLED) <= set(by)
    assert by["VerifyDocument"].props["Label"] == "Verifica citazioni"
    assert by["InsertNorm"].props["Label"] == "Inserisci norma"
    assert by["ShowText"].props["Label"] == "Mostra testo"
    assert by["ListCitations"].props["Label"] == "Elenca citazioni"
    assert by["Cancel"].props["Label"] == "Annulla"
    assert (by["CitationsLabel"].props["Label"]
            == "Citazioni (clic: vai al paragrafo e mostra il testo)")
    assert by["Citations"].kind == "ListBox" and by["Citations"].h == 60


def test_citation_actions_are_wired_and_disabled_while_busy():
    assert ACTIONS["ShowText"] == "show_text" and ACTIONS["ListCitations"] == "list_citations"
    assert "ShowText" in BUSY_DISABLED and "ListCitations" in BUSY_DISABLED
