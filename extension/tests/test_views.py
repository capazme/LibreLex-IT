# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_ext.views import ROUTES, CompositeView, panel_kind


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
    assert panel_kind("private:resource/toolpanel/LibreLexPanelFactory/Questions") == "Questions"
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
    """The busy controls of layout.BUSY_DISABLED live on Azioni, Redazione and Domande
    alike: routing the busy state to one kind would leave the others clickable mid-turn."""
    v = CompositeView()
    actions, drafting, questions = Rec(), Rec(), Rec()
    v.attach("Actions", actions)
    v.attach("Drafting", drafting)
    v.attach("Questions", questions)
    v.set_busy(True)
    v.set_busy(False)
    assert "set_busy" not in ROUTES
    for panel in (actions, drafting, questions):
        assert panel.calls == [("set_busy", (True,)), ("set_busy", (False,))]


def test_routes_map_the_drafting_and_questions_methods():
    for method in ("set_templates", "set_template", "set_reference", "set_partitions",
                   "set_draft_status"):
        assert ROUTES[method] == "Drafting"
    assert ROUTES["set_questions"] == "Questions"


def test_composite_routes_drafting_and_questions_calls():
    v = CompositeView()
    drafting, questions = Rec(), Rec()
    v.attach("Drafting", drafting)
    v.attach("Questions", questions)
    v.set_template({"x": 1})
    v.set_questions([])
    assert drafting.calls == [("set_template", ({"x": 1},))]
    assert questions.calls == [("set_questions", ([],))]
