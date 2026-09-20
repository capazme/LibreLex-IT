# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_ext.layout import (
    ACTIONS,
    ATTACHMENTS_H,
    BUSY_DISABLED,
    BUTTON_H,
    CONSENT_BUTTONS,
    CONSENT_LABELS,
    CONTROLS,
    DRAFT_AREA_H,
    DRAFT_CONSENT,
    DRAFT_CONSENT_H,
    DRAFT_CONSENT_TEXT_H,
    DRAFT_SHARED,
    DRAFT_STEPS,
    FIELD_ROWS,
    GAP,
    GRAY,
    KINDS,
    LOG_H,
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
    "Drafting": set().union(*DRAFT_STEPS.values()) | set(DRAFT_SHARED),
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


def _drafting_groups(controls):
    by = {c.name: c for c in controls}
    for step, names in DRAFT_STEPS.items():
        yield step, [by[n] for n in (*names, *DRAFT_SHARED)]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("width", [MIN_WIDTH, WIDTH, 260])
def test_each_kind_fits_its_width_without_overlaps(kind, width):
    controls = build(kind, width)
    if kind == "Drafting":
        for _step, group in _drafting_groups(controls):
            _no_overlap(group, width)
        assert len({c.name for c in controls}) == len(controls)
    else:
        _no_overlap(controls, width)
    assert {c.name for c in controls} == EXPECTED[kind]
    assert total_height(controls) == total_height(build(kind, WIDTH))


def test_drafting_steps_share_one_area_and_the_status_sits_under_it():
    controls = build("Drafting", WIDTH)
    by = {c.name: c for c in controls}
    names = {c.name for c in controls}
    assert set().union(*DRAFT_STEPS.values()) | set(DRAFT_SHARED) == names
    for step, group in _drafting_groups(controls):
        for c in group:
            if c.name not in DRAFT_SHARED:
                assert c.y >= MARGIN and c.y + c.h <= MARGIN + DRAFT_AREA_H, (step, c.name)
    assert by["DraftStatus"].y == MARGIN + DRAFT_AREA_H + GAP
    assert total_height(controls) <= 440
    for name in (*DRAFT_STEPS[2], *DRAFT_STEPS[3], *DRAFT_STEPS[4]):
        assert by[name].props.get("Visible") is False, name        # only step 1 shows at first
    for name in ("TemplateSearch", "Template", "Notes", "Attachments", "Start", "Letterhead"):
        assert by[name].props.get("Visible", True) is True, name
    # the consent block is one block, shared by steps 2 and 3, right above the status
    assert set(DRAFT_CONSENT) <= set(DRAFT_STEPS[2]) and set(DRAFT_CONSENT) <= set(DRAFT_STEPS[3])
    text, document, once, deny = (by[n] for n in DRAFT_CONSENT)
    assert text.y == MARGIN + DRAFT_AREA_H - DRAFT_CONSENT_H and text.h == DRAFT_CONSENT_TEXT_H
    assert document.y == text.y + text.h + GAP and once.y == deny.y == document.y + BUTTON_H + GAP
    assert deny.y + deny.h <= MARGIN + DRAFT_AREA_H
    assert by["Continue"].y + by["Continue"].h <= text.y                # step 2 fits above it
    assert by["DraftCancel"].y + by["DraftCancel"].h <= text.y           # step 3 too
    assert [by[n].props["Label"] for n in DRAFT_CONSENT[1:]] == list(CONSENT_LABELS)


def test_step_one_rows():
    by = {c.name: c for c in build("Drafting", WIDTH)}
    assert by["Attachments"].props["Dropdown"] is False and by["Attachments"].h == ATTACHMENTS_H
    assert by["AttachmentAdd"].y == by["AttachmentRemove"].y
    assert by["AttachmentRemove"].props["Enabled"] is False
    assert by["ReferenceInfo"].y == by["ReferenceBrowse"].y == by["ReferenceClear"].y
    assert by["ReferenceClear"].x + by["ReferenceClear"].w == WIDTH - MARGIN
    assert by["ReferenceBrowse"].x + by["ReferenceBrowse"].w + GAP == by["ReferenceClear"].x
    assert by["ReferenceInfo"].x + by["ReferenceInfo"].w <= by["ReferenceBrowse"].x
    assert by["LetterheadLabel"].y == by["Letterhead"].y == by["LetterheadAdd"].y
    assert by["Letterhead"].props["Dropdown"] is True
    assert by["LetterheadAdd"].x + by["LetterheadAdd"].w == WIDTH - MARGIN
    assert by["Start"].props["Enabled"] is False and by["Start"].y > by["Letterhead"].y
    order = [c.name for c in build("Drafting", WIDTH) if c.name in DRAFT_STEPS[1]]
    assert order.index("Notes") < order.index("Attachments") < order.index("ReferenceInfo") \
        < order.index("Letterhead") < order.index("Start")


def test_steps_two_three_four_rows():
    by = {c.name: c for c in build("Drafting", WIDTH)}
    for n in range(1, FIELD_ROWS + 1):
        label, edit = by[f"QuestionLabel{n}"], by[f"Answer{n}"]
        assert edit.y == label.y + label.h and label.props["MultiLine"] is True
    assert by["Log"].props["ReadOnly"] is True and by["Log"].h == LOG_H
    assert by["Expected"].props["Dropdown"] is False and by["DraftCancel"].props["Enabled"] is False
    assert by["Summary"].props["ReadOnly"] is True
    assert by["VerifyAct"].props["Label"] == "Verifica citazioni"
    assert by["NewDraft"].props["Label"] == "Nuova redazione"
    assert by["Resume"].props["Label"] == "Riprendi"
    assert by["ResumeInput"].y < by["Resume"].y < by["NewDraft"].y


def test_workbench_buttons_are_wired():
    for name, command in (("AttachmentAdd", "attachment_add"),
                          ("AttachmentRemove", "attachment_remove"),
                          ("LetterheadAdd", "letterhead_add"), ("DraftCancel", "cancel"),
                          ("VerifyAct", "verify_document"), ("NewDraft", "draft_new"),
                          ("DraftConsentDocument", "consent_document"),
                          ("DraftConsentOnce", "consent_once"),
                          ("DraftConsentDeny", "consent_deny")):
        assert ACTIONS[name] == command and name in TOOLTIPS
    for name in ("AttachmentAdd", "AttachmentRemove", "LetterheadAdd", "Letterhead", "VerifyAct",
                 "NewDraft", "Start", "Resume", "Continue"):
        assert name in BUSY_DISABLED
    assert not (set(DRAFT_CONSENT) | {"DraftCancel"}) & set(BUSY_DISABLED)
    assert KINDS == ("Actions", "Drafting", "Citations", "Answers")
    with pytest.raises(ValueError):
        build("Questions", WIDTH)


def test_kinds_partition_the_controls_and_actions():
    all_names = [c.name for k in KINDS for c in build_all(WIDTH)[k]]
    assert len(all_names) == len(set(all_names))   # every control name is unique across the deck
    # BUSY_DISABLED now spans several steps of the Drafting panel (controls disabled while the
    # core is busy too), so its invariant is "every name is a real control", same as ACTIONS.
    assert set(ACTIONS) <= set(all_names) and set(BUSY_DISABLED) <= set(all_names)
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


def test_actions_lost_the_draft_button_and_the_new_actions_are_wired():
    names = {c.name for c in build("Actions", WIDTH)}
    assert "Draft" not in names and "Draft" not in ACTIONS and "Draft" not in TOOLTIPS
    for name, command in (("TemplateRefresh", "template_search"),
                          ("ReferenceBrowse", "reference_browse"),
                          ("ReferenceClear", "reference_clear"), ("Start", "draft_start"),
                          ("Resume", "draft_resume"), ("Continue", "draft_answer")):
        assert ACTIONS[name] == command and name in BUSY_DISABLED and name in TOOLTIPS
    assert KINDS == ("Actions", "Drafting", "Citations", "Answers")
