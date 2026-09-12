# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_ext.layout import (
    ACTIONS,
    BUSY_DISABLED,
    CONTROLS,
    KINDS,
    MIN_WIDTH,
    NOTICE,
    TOOLTIPS,
    WIDTH,
    build,
    build_all,
    total_height,
)

EXPECTED = {
    "Actions": {"Notice", "DocumentLabel", "ListCitations", "VerifyDocument", "VerifySelection",
                "Cancel", "ReferenceLabel", "Input", "ShowText", "InsertNorm", "Progress", "Status",
                "Settings", "Usage"},
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
                        ("ShowText", "InsertNorm")):
        assert by[left].y == by[right].y and by[left].w == by[right].w
    answers = {c.name: c for c in build("Answers", WIDTH)}
    assert answers["Transcript"].props["ReadOnly"] is True
    assert answers["Clear"].props["Label"] == "Svuota"
    citations = {c.name: c for c in build("Citations", WIDTH)}
    assert citations["Citations"].props["Dropdown"] is False
