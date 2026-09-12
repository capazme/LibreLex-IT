# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_ext.layout import (
    ACTIONS,
    BUSY_DISABLED,
    CONSENT_BUTTONS,
    CONTROLS,
    GRAY,
    KINDS,
    MARGIN,
    MIN_WIDTH,
    NOTICE,
    SECTIONS,
    TOOLTIPS,
    WIDTH,
    build,
    build_all,
    total_height,
)

EXPECTED = {
    "Actions": {"Notice", "DocumentLabel", "ListCitations", "VerifyDocument", "VerifySelection",
                "Cancel", "ReferenceLabel", "Input", "Send", "Research", "ShowText", "InsertNorm",
                "ConsentText", "ConsentDocument", "ConsentOnce", "ConsentDeny", "Progress",
                "Status", "Settings", "Usage"},
    "Citations": {"CitationsHint", "Citations"},
    "Answers": {"Clear", "Transcript"},
}


def _no_overlap(controls, width):
    names = [c.name for c in controls]
    assert len(names) == len(set(names))
    for c in controls:
        assert 0 <= c.x and c.x + c.w <= width, c.name
    boxes = [(c.x, c.y, c.x + c.w, c.y + c.h) for c in controls]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (a, b)


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("width", [MIN_WIDTH, WIDTH, 260])
def test_each_kind_fits_its_width_without_overlaps(kind, width):
    controls = build(kind, width)
    _no_overlap(controls, width)
    assert {c.name for c in controls} == EXPECTED[kind]
    assert total_height(controls) == total_height(build(kind, WIDTH))   # width-independent height


def test_kinds_partition_the_controls_and_actions():
    all_names = [c.name for k in KINDS for c in build_all(WIDTH)[k]]
    assert len(all_names) == len(set(all_names))
    assert set(ACTIONS) <= set(all_names) and set(BUSY_DISABLED) <= set(EXPECTED["Actions"])
    assert set(TOOLTIPS) <= set(all_names)
    assert set(CONTROLS) == set(KINDS)
    with pytest.raises(ValueError):
        build("Chat", WIDTH)


def test_copy_and_button_rows():
    by = {c.name: c for c in build("Actions", WIDTH)}
    assert by["Notice"].props["Label"] == NOTICE
    assert by["Progress"].props["Visible"] is False
    for left, right in (("ListCitations", "VerifyDocument"), ("VerifySelection", "Cancel"),
                        ("Send", "Research"), ("ShowText", "InsertNorm")):
        assert by[left].y == by[right].y and by[left].w == by[right].w
    answers = {c.name: c for c in build("Answers", WIDTH)}
    assert answers["Transcript"].props["ReadOnly"] is True
    assert answers["Clear"].props["Label"] == "Svuota"
    citations = {c.name: c for c in build("Citations", WIDTH)}
    assert citations["Citations"].props["Dropdown"] is False


def test_reference_label_asks_for_a_message_a_question_or_a_reference():
    assert SECTIONS["ReferenceLabel"] == "Messaggio, domanda o riferimento (es. art. 2043 c.c.)"
    by = {c.name: c for c in build("Actions", WIDTH)}
    assert by["ReferenceLabel"].props["Label"] == SECTIONS["ReferenceLabel"]
    assert by["Send"].props["Label"] == "Invia" and by["Research"].props["Label"] == "Ricerca"
    assert by["Input"].y < by["Send"].y < by["ShowText"].y      # input, then chat, then norms


@pytest.mark.parametrize("width", [MIN_WIDTH, WIDTH, 260])
def test_consent_block_is_hidden_and_its_three_buttons_share_one_row(width):
    by = {c.name: c for c in build("Actions", width)}
    text = by["ConsentText"]
    assert text.kind == "FixedText" and text.h == 30
    assert text.props["MultiLine"] is True and text.props["TextColor"] == GRAY
    buttons = [by[name] for name in CONSENT_BUTTONS]
    assert [b.props["Label"] for b in buttons] == ["Per questo documento", "Solo stavolta",
                                                   "Annulla"]
    assert len({b.y for b in buttons}) == 1 and len({b.w for b in buttons}) == 1
    assert text.y + text.h <= buttons[0].y                     # the text sits above the row
    assert buttons[0].x == MARGIN and buttons[-1].x + buttons[-1].w == width - MARGIN
    for name in ("ConsentText", *CONSENT_BUTTONS):             # hidden until a request lands
        assert by[name].props["Visible"] is False
    assert by["Status"].y > buttons[0].y                       # consent block above the status


def test_new_buttons_are_wired_and_only_the_right_ones_are_busy_disabled():
    assert ACTIONS["Send"] == "send" and ACTIONS["Research"] == "research"
    assert [ACTIONS[name] for name in CONSENT_BUTTONS] == ["consent_document", "consent_once",
                                                           "consent_deny"]
    assert "Send" in BUSY_DISABLED and "Research" in BUSY_DISABLED
    # the consent buttons are the only ones the user presses while a request runs
    assert not set(CONSENT_BUTTONS) & set(BUSY_DISABLED)
    assert "Chiedi al modello" in TOOLTIPS["Send"]
    assert TOOLTIPS["Send"].endswith("solo dopo il tuo consenso")
    assert TOOLTIPS["Research"].startswith("Cerca precedenti sulla domanda scritta qui sopra")
    for name in (*ACTIONS, "Citations"):                       # every command has a tooltip
        assert name in TOOLTIPS
