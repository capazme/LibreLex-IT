# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_ext.layout import (
    ACTIONS,
    BUSY_DISABLED,
    CONSENT_BUTTONS,
    CONTROLS,
    GAP,
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
                "Draft", "ConsentText", "ConsentDocument", "ConsentOnce", "ConsentDeny", "Progress",
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
                        ("Send", "Research"), ("ShowText", "InsertNorm"),
                        ("ConsentOnce", "ConsentDeny")):
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
def test_consent_block_is_hidden_and_takes_two_rows(width):
    """Fix round 2, finding 2: "Per questo documento" (20 characters) does not fit a third of

    the deck, so it owns a full-width row and the other two share the two-column row below.
    """
    by = {c.name: c for c in build("Actions", width)}
    text = by["ConsentText"]
    assert text.kind == "FixedText" and text.h == 40           # the question is ~110 characters
    assert text.props["MultiLine"] is True and text.props["TextColor"] == GRAY
    document, once, deny = (by[name] for name in CONSENT_BUTTONS)
    assert [b.props["Label"] for b in (document, once, deny)] == ["Per questo documento",
                                                                  "Solo stavolta", "Annulla"]
    assert document.x == MARGIN and document.x + document.w == width - MARGIN   # full width
    assert once.y == deny.y == document.y + document.h + GAP     # the shared row below it
    assert once.w == deny.w == by["Send"].w                    # the standard two-column grid
    assert once.x == MARGIN and deny.x + deny.w == width - MARGIN
    assert text.y + text.h <= document.y                       # the text sits above the rows
    for name in ("ConsentText", *CONSENT_BUTTONS):             # hidden until a request lands
        assert by[name].props["Visible"] is False
    assert by["Status"].y > deny.y                             # consent block above the status


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


def test_draft_button_is_a_full_width_row_between_the_reference_buttons_and_the_consent():
    width = WIDTH
    by = {c.name: c for c in build("Actions", width)}
    draft = by["Draft"]
    assert draft.kind == "Button" and draft.props["Label"] == "Redigi da modello"
    assert draft.x == MARGIN and draft.w == width - 2 * MARGIN
    assert draft.y == by["ShowText"].y + by["ShowText"].h + GAP
    assert by["ConsentText"].y == draft.y + draft.h + GAP
    assert ACTIONS["Draft"] == "draft" and "Draft" in BUSY_DISABLED
    assert TOOLTIPS["Draft"].startswith("Redige l'atto indicato qui sopra")
    assert TOOLTIPS["Draft"].endswith("per rispondere alle domande del modello")
