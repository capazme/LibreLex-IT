# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""The Redazione panel's pure helpers, exercised inside LibreOffice: importing
`librelex_ext.panel` pulls in the UNO types (drop target included), so this can only run
under soffice, and the probe doubles as proof that the module still imports there."""
import pytest

from tests.headless.conftest import run_probe

pytestmark = pytest.mark.headless


def test_panel_helpers_import_inside_libreoffice_and_behave(soffice):
    out = run_probe(soffice, "panel_helpers", '''
    from librelex_ext.panel import ATTACHMENT_FILTER, LETTERHEAD_FILTER, collect_fields, file_uris
    from librelex_ext.session import drop_role
    from librelex_ext import layout

    def probe(ctx, out):
        out["fields"] = collect_fields(["creditore", "importo", "note"], [" Alfa ", "", "12.000"])
        out["uris_bytes"] = file_uris(
            b"file:///Users/x/ricorso%20rossi.docx\\r\\nfile:///y.odt\\r\\n")
        out["uris_str"] = file_uris("https://example.org/x.docx\\n")
        out["uris_none"] = file_uris(None)
        out["attachment_filter"] = list(ATTACHMENT_FILTER)
        out["letterhead_filter"] = list(LETTERHEAD_FILTER)
        out["drop_role_reference"] = drop_role("ricorso.docx", False)
        out["drop_role_attachment"] = drop_role("fattura.pdf", False)
        out["drop_role_second_act"] = drop_role("altro.docx", True)
        out["continue_y_max"] = layout.continue_y(layout.FIELD_ROWS)
        out["continue_y_zero"] = layout.continue_y(0)
    ''')
    assert out["fields"] == {"creditore": "Alfa", "note": "12.000"}
    assert out["uris_bytes"] == ["file:///Users/x/ricorso%20rossi.docx", "file:///y.odt"]
    assert out["uris_str"] == [] and out["uris_none"] == []
    assert out["attachment_filter"][1] == "*.pdf;*.odt;*.docx;*.doc;*.rtf;*.txt"
    assert out["letterhead_filter"][1] == "*.odt;*.docx;*.doc"
    assert out["drop_role_reference"] == "reference"
    assert out["drop_role_attachment"] == "attachment"
    assert out["drop_role_second_act"] == "attachment"
    assert out["continue_y_zero"] < out["continue_y_max"]


def test_assign_tab_order_survives_every_control_kind_the_panels_use(soffice):
    """F1 regression: a UNO probe showed that ``UnoControlFixedLineModel`` and
    ``UnoControlProgressBarModel`` have no ``Tabstop`` property at all, so assigning it (the
    old ``_build_controls`` did, on every model) raised ``AttributeError`` and killed the
    Redazione panel at its first FixedLine and the Azioni panel at its ProgressBar. This
    exercises the real code (``panel.assign_tab_order``, factored out of ``_build_controls``
    for exactly this) against one real ``UnoControl<Kind>Model`` per kind
    ``layout.build_all(layout.WIDTH)`` actually uses.
    """
    out = run_probe(soffice, "assign_tab_order", '''
    from librelex_ext import layout
    from librelex_ext.panel import assign_tab_order

    def probe(ctx, out):
        all_controls = [c for controls in layout.build_all(layout.WIDTH).values()
                        for c in controls]
        one_per_kind = list({c.kind: c for c in all_controls}.values())
        smgr = ctx.ServiceManager
        model = smgr.createInstanceWithContext("com.sun.star.awt.UnoControlDialogModel", ctx)
        for c in one_per_kind:
            m = model.createInstance(f"com.sun.star.awt.UnoControl{c.kind}Model")
            m.Name = c.name
            model.insertByName(c.name, m)
        assign_tab_order(model, one_per_kind)          # must not raise (F1)
        out["kinds"] = sorted(c.kind for c in one_per_kind)
        tabstop = {}
        for c in one_per_kind:
            m = model.getByName(c.name)
            info = m.getPropertySetInfo()
            tabstop[c.kind] = (bool(m.Tabstop) if info.hasPropertyByName("Tabstop") else None)
        out["tabstop"] = tabstop
    ''')
    assert set(out["kinds"]) == {"Button", "Edit", "FixedLine", "FixedText", "ListBox",
                                 "ProgressBar"}
    assert out["tabstop"]["Edit"] is True
    assert out["tabstop"]["Button"] is True
    assert out["tabstop"]["ListBox"] is True
    assert out["tabstop"]["FixedText"] is False
    assert out["tabstop"]["FixedLine"] is None          # no Tabstop property: left untouched
    assert out["tabstop"]["ProgressBar"] is None
