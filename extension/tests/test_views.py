# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_ext.views import BROADCAST, ROUTES, CompositeView, panel_kind


class Rec:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def method(*args):
            self.calls.append((name, args))
        return method


def test_panel_kind_from_resource_url():
    assert panel_kind("private:resource/toolpanel/LibreLexPanelFactory/Answers") == "Answers"
    assert panel_kind("private:resource/toolpanel/LibreLexPanelFactory/Drafting") == "Drafting"
    with pytest.raises(ValueError):
        panel_kind("private:resource/toolpanel/LibreLexPanelFactory/Questions")
    with pytest.raises(ValueError):
        panel_kind("private:resource/toolpanel/LibreLexPanelFactory/Panel")


def test_composite_routes_each_call_to_the_right_panel_and_tolerates_absence():
    v = CompositeView()
    v.append("x")                                  # no panels: no error
    actions, citations, answers = Rec(), Rec(), Rec()
    v.attach("Actions", actions)
    v.attach("Citations", citations)
    v.attach("Answers", answers)
    v.append("riga")
    v.set_transcript("tutto")
    v.set_status("Pronto")
    v.set_busy(True)
    v.set_progress(3, 9)
    v.set_citations(["a", "b"])
    # set_busy is the one broadcast call: every attached panel hears it
    assert answers.calls == [("append", ("riga",)), ("set_transcript", ("tutto",)),
                             ("set_busy", (True,))]
    assert actions.calls == [("set_status", ("Pronto",)), ("set_busy", (True,)),
                             ("set_progress", (3, 9))]
    assert citations.calls == [("set_busy", (True,)), ("set_citations", (["a", "b"],))]
    v.detach("Answers")
    v.append("persa")
    assert answers.calls[-1] == ("set_busy", (True,))


def test_set_busy_reaches_every_attached_panel():
    """The busy controls of layout.BUSY_DISABLED live on Azioni and Redazione alike: routing
    the busy state to one kind would leave the other clickable mid-turn."""
    v = CompositeView()
    actions, drafting = Rec(), Rec()
    v.attach("Actions", actions)
    v.attach("Drafting", drafting)
    v.set_busy(True)
    v.set_busy(False)
    assert "set_busy" not in ROUTES
    for panel in (actions, drafting):
        assert panel.calls == [("set_busy", (True,)), ("set_busy", (False,))]


def test_routes_map_the_drafting_methods():
    for method in ("set_templates", "set_template", "set_reference", "set_partitions",
                   "set_draft_status", "set_field_values", "set_questions", "set_answer_values",
                   "set_step", "set_log", "append_log", "set_expected_partitions",
                   "set_attachments", "set_letterheads", "set_summary"):
        assert ROUTES[method] == "Drafting"


def test_composite_routes_drafting_calls():
    v = CompositeView()
    drafting = Rec()
    v.attach("Drafting", drafting)
    v.set_template({"x": 1})
    v.set_questions([])
    # I5: what the lawyer typed is state, and it travels to its own panel like the rest
    v.set_field_values({"creditore": "Alfa"}, "note")
    v.set_answer_values({"sede": "Milano"})
    assert drafting.calls == [("set_template", ({"x": 1},)),
                              ("set_questions", ([],)),
                              ("set_field_values", ({"creditore": "Alfa"}, "note")),
                              ("set_answer_values", ({"sede": "Milano"},))]


def test_consent_and_busy_are_broadcast_and_the_workbench_methods_reach_drafting():
    v = CompositeView()
    actions, drafting = Rec(), Rec()
    v.attach("Actions", actions)
    v.attach("Drafting", drafting)
    v.set_consent({"scope": "attachments"})
    v.set_step(3)
    v.append_log("Inserito: Premesse")
    v.set_log(["a"])
    v.set_expected_partitions(["· Premesse"])
    v.set_attachments(["Doc. 1 · a.pdf (10 caratteri)"])
    v.set_letterheads(["Nessuna (impaginazione del documento)", "SAPG Legal"], 1)
    v.set_summary("Riepilogo:\nok")
    v.set_questions([])
    v.set_answer_values({})
    assert actions.calls == [("set_consent", ({"scope": "attachments"},))]
    assert [c[0] for c in drafting.calls] == [
        "set_consent", "set_step", "append_log", "set_log", "set_expected_partitions",
        "set_attachments", "set_letterheads", "set_summary", "set_questions", "set_answer_values"]
    assert BROADCAST == ("set_busy", "set_consent") and "set_consent" not in ROUTES
