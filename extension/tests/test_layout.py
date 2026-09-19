# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_ext.layout import (
    ACTIONS,
    BUSY_DISABLED,
    CONSENT_BUTTONS,
    CONTROLS,
    FIELD_ROWS,
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

_FIELD_NAMES = {f"FieldLabel{n}" for n in range(1, FIELD_ROWS + 1)} | {
    f"Field{n}" for n in range(1, FIELD_ROWS + 1)}
_QUESTION_NAMES = {f"QuestionLabel{n}" for n in range(1, FIELD_ROWS + 1)} | {
    f"Answer{n}" for n in range(1, FIELD_ROWS + 1)}

EXPECTED = {
    "Actions": {"Notice", "DocumentLabel", "ListCitations", "VerifyDocument", "VerifySelection",
                "Cancel", "ReferenceLabel", "Input", "Send", "Research", "ShowText", "InsertNorm",
                "ConsentText", "ConsentDocument", "ConsentOnce", "ConsentDeny", "Progress",
                "Status", "Settings", "Usage"},
    "Drafting": {"TemplateSearch", "TemplateRefresh", "Template", "TemplateNotes", "FieldsLabel",
                 "NotesLabel", "Notes", "ReferenceLabel", "ReferenceBrowse", "ReferenceClear",
                 "Start", "PartitionsLabel", "Partitions", "ResumeInput", "Resume",
                 "DraftStatus"} | _FIELD_NAMES,
    "Questions": {"QuestionsHint", "Continue", "QuestionsStatus"} | _QUESTION_NAMES,
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
    # Names are unique within each panel (also checked per-kind by _no_overlap below); across
    # panels a name may repeat when it names an unrelated control in a different deck window,
    # as "ReferenceLabel" does for Actions (the free-text reference field) versus Drafting (the
    # reference-act status line).
    for k in KINDS:
        names = [c.name for c in build_all(WIDTH)[k]]
        assert len(names) == len(set(names))
    all_names = {c.name for k in KINDS for c in build_all(WIDTH)[k]}
    # BUSY_DISABLED now spans several panels (Drafting/Questions controls disabled while the
    # core is busy too), so its invariant is "every name is a real control", same as ACTIONS.
    assert set(ACTIONS) <= all_names and set(BUSY_DISABLED) <= all_names
    assert set(TOOLTIPS) <= all_names
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


def test_drafting_panel_rows_and_hidden_blocks():
    by = {c.name: c for c in build("Drafting", WIDTH)}
    assert by["TemplateSearch"].y == by["TemplateRefresh"].y
    assert by["TemplateRefresh"].x + by["TemplateRefresh"].w == WIDTH - MARGIN
    assert by["Template"].props["Dropdown"] is True and by["Template"].props["LineCount"] == 12
    for n in range(1, FIELD_ROWS + 1):
        label, edit = by[f"FieldLabel{n}"], by[f"Field{n}"]
        assert label.y == edit.y and label.x == MARGIN and edit.x == label.x + label.w + GAP
        assert edit.x + edit.w == WIDTH - MARGIN
        assert label.props["Visible"] is False and edit.props["Visible"] is False
    assert by["Field1"].y > by["FieldsLabel"].y and by["Notes"].props["MultiLine"] is True
    assert by["ReferenceBrowse"].y == by["ReferenceClear"].y
    assert by["ReferenceClear"].props["Enabled"] is False and by["Start"].props["Enabled"] is False
    assert by["Partitions"].props["Dropdown"] is False
    assert by["ResumeInput"].props["Visible"] is False and by["Resume"].props["Visible"] is False
    assert by["DraftStatus"].props["Label"] == "Scegli un atto"
    order = [c.name for c in build("Drafting", WIDTH)]
    assert (order.index("Start") < order.index("PartitionsLabel") < order.index("Resume")
            < order.index("DraftStatus"))
    assert total_height(build("Drafting", WIDTH)) <= 460


def test_questions_panel_rows_hidden_until_needed():
    by = {c.name: c for c in build("Questions", WIDTH)}
    for n in range(1, FIELD_ROWS + 1):
        label, edit = by[f"QuestionLabel{n}"], by[f"Answer{n}"]
        assert label.props["MultiLine"] is True and edit.y == label.y + label.h + GAP
        assert label.props["Visible"] is False and edit.props["Visible"] is False
    assert by["Continue"].props["Visible"] is False
    assert by["QuestionsStatus"].props["Label"] == "Nessuna domanda in sospeso"
    assert total_height(build("Questions", WIDTH)) <= 380


def test_actions_lost_the_draft_button_and_the_new_actions_are_wired():
    names = {c.name for c in build("Actions", WIDTH)}
    assert "Draft" not in names and "Draft" not in ACTIONS and "Draft" not in TOOLTIPS
    for name, command in (("TemplateRefresh", "template_search"),
                          ("ReferenceBrowse", "reference_browse"),
                          ("ReferenceClear", "reference_clear"), ("Start", "draft_start"),
                          ("Resume", "draft_resume"), ("Continue", "draft_answer")):
        assert ACTIONS[name] == command and name in BUSY_DISABLED and name in TOOLTIPS
    assert KINDS == ("Actions", "Drafting", "Questions", "Citations", "Answers")
