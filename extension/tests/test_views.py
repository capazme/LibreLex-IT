# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_ext.views import CompositeView, panel_kind


class Rec:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def method(*args):
            self.calls.append((name, args))
        return method


def test_panel_kind_from_resource_url():
    assert panel_kind("private:resource/toolpanel/LibreLexPanelFactory/Answers") == "Answers"
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
    assert answers.calls == [("append", ("riga",)), ("set_transcript", ("tutto",))]
    assert actions.calls == [("set_status", ("Pronto",)), ("set_busy", (True,)),
                             ("set_progress", (3, 9))]
    assert citations.calls == [("set_citations", (["a", "b"],))]
    v.detach("Answers")
    v.append("persa")
    assert answers.calls[-1] == ("set_transcript", ("tutto",))
