# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_ext.layout import (
    ACTIONS,
    BUSY_DISABLED,
    CONTROLS,
    MIN_WIDTH,
    NOTICE,
    SECTIONS,
    TOOLTIPS,
    WIDTH,
    build,
    total_height,
)

WIDTHS = (MIN_WIDTH, WIDTH, 260)
REQUIRED = ("Notice", "ListCitations", "VerifyDocument", "VerifySelection", "Cancel", "Input",
            "ShowText", "InsertNorm", "Citations", "Transcript", "Clear", "Progress", "Status",
            "Settings")
BUTTON_PAIRS = (("ListCitations", "VerifyDocument"), ("VerifySelection", "Cancel"),
                ("ShowText", "InsertNorm"))


@pytest.mark.parametrize("width", WIDTHS)
def test_controls_fit_the_panel_and_do_not_overlap(width):
    controls = build(width)
    names = [c.name for c in controls]
    assert len(names) == len(set(names))
    for c in controls:
        assert 0 <= c.x and c.x + c.w <= width, c.name
        assert c.w > 0 and c.h > 0, c.name
    boxes = [(c.x, c.y, c.x + c.w, c.y + c.h) for c in controls]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (a, b)


@pytest.mark.parametrize("width", WIDTHS)
def test_button_rows_are_a_two_column_grid(width):
    by = {c.name: c for c in build(width)}
    for left, right in BUTTON_PAIRS:
        a, b = by[left], by[right]
        assert a.kind == b.kind == "Button"
        assert a.y == b.y and a.h == b.h
        assert a.w == b.w == (width - 12) // 2, (left, right)
        assert a.x == 4 and b.x + b.w == width - 4


def test_height_and_control_set_do_not_depend_on_the_width():
    heights = {total_height(build(w)) for w in WIDTHS}
    assert len(heights) == 1
    names = {tuple(c.name for c in build(w)) for w in WIDTHS}
    assert len(names) == 1
    assert build(120) == build(MIN_WIDTH)        # narrower than the minimum: clamped


def test_required_controls_and_copy():
    assert CONTROLS == build(WIDTH)
    by = {c.name: c for c in CONTROLS}
    for name in REQUIRED:
        assert name in by, name
    for name in ("Send", "Research", "Draft", "Review"):     # M2/M4 add them back
        assert name not in by, name
    assert by["Notice"].props["Label"] == NOTICE
    assert NOTICE == "Le citazioni vanno sempre controllate dal professionista."
    assert by["Notice"].props["TextColor"] == 0x666666
    assert by["Transcript"].props["ReadOnly"] is True and by["Transcript"].h == 150
    assert by["Transcript"].props["VScroll"] is True
    assert by["Citations"].kind == "ListBox" and by["Citations"].h == 64
    assert by["Progress"].kind == "ProgressBar" and by["Progress"].props["Visible"] is False
    assert by["VerifyDocument"].props["Label"] == "Verifica citazioni"
    assert by["VerifySelection"].props["Label"] == "Verifica selezione"
    assert by["InsertNorm"].props["Label"] == "Inserisci norma"
    assert by["ShowText"].props["Label"] == "Mostra testo"
    assert by["ListCitations"].props["Label"] == "Elenca citazioni"
    assert by["Cancel"].props["Label"] == "Annulla"
    assert by["Clear"].props["Label"] == "Svuota"
    assert by["Settings"].props["Label"] == "Impostazioni"


def test_sections_are_bold_labels_in_order():
    by = {c.name: c for c in CONTROLS}
    assert list(SECTIONS) == ["DocumentLabel", "ReferenceLabel", "CitationsLabel",
                              "TranscriptLabel"]
    assert SECTIONS["DocumentLabel"] == "Documento"
    assert SECTIONS["ReferenceLabel"] == "Riferimento (es. art. 2043 c.c., Cass. n. 12345/2024)"
    assert SECTIONS["CitationsLabel"] == "Citazioni"
    assert SECTIONS["TranscriptLabel"] == "Risposte"
    for name, label in SECTIONS.items():
        assert by[name].kind == "FixedText" and by[name].props["Label"] == label
        assert by[name].props["FontWeight"] == 150.0, name
    tops = [by[name].y for name in SECTIONS]
    assert tops == sorted(tops)


def test_every_button_has_a_tooltip():
    by = {c.name: c for c in CONTROLS}
    assert set(TOOLTIPS) <= set(by)
    for c in CONTROLS:
        if c.kind == "Button":
            assert c.props["HelpText"] == TOOLTIPS[c.name], c.name
        if "HelpText" in c.props:                  # TOOLTIPS is the only source of copy
            assert c.props["HelpText"] == TOOLTIPS[c.name], c.name
    assert TOOLTIPS["ListCitations"] == ("Trova tutte le citazioni del documento senza "
                                         "consultare le fonti")
    assert TOOLTIPS["Clear"] == "Svuota le risposte"
    assert TOOLTIPS["Cancel"] == "Interrompe la richiesta in corso"


def test_citation_actions_are_wired_and_disabled_while_busy():
    by = {c.name: c for c in CONTROLS}
    assert set(ACTIONS) <= set(by) and set(BUSY_DISABLED) <= set(by)
    assert ACTIONS["ShowText"] == "show_text" and ACTIONS["ListCitations"] == "list_citations"
    assert ACTIONS["Clear"] == "clear"
    assert "ShowText" in BUSY_DISABLED and "ListCitations" in BUSY_DISABLED
    assert "Clear" not in BUSY_DISABLED          # clearing the answers always works
