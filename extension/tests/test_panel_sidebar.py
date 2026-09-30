# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""The panel never enters the sidebar's own UNO API synchronously.

``XDeck.getPanels().getByName()`` builds an ``SfxUnoPanel`` whose constructor calls
``SidebarController::CreateDeck`` and so ``CreatePanels`` again; reached from inside a
panel's construction (replay → set_step) it re-creates the panels built so far, recursively,
until LibreOffice aborts (0.7.0 field crash). Every sidebar call must therefore land in a
later main-loop turn, through ``com.sun.star.awt.AsyncCallback``.

UNO is not importable here: a meta-path finder serves stand-in modules for ``uno``,
``unohelper`` and everything under ``com.``, and the sidebar itself is a small fake that
counts what the panel does to it and when.
"""
from __future__ import annotations

import importlib
import importlib.abc
import importlib.machinery
import sys
import types
from unittest import mock

import pytest


class _FakeUnoModule(types.ModuleType):
    def __getattr__(self, attr):
        if attr.startswith("__"):
            raise AttributeError(attr)
        value = type(attr, (), {})           # any interface, struct or constant
        setattr(self, attr, value)
        return value


class _FakeUnoFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, name, path, target=None):
        if name in ("uno", "unohelper", "com") or name.startswith("com."):
            return importlib.machinery.ModuleSpec(name, self, is_package=True)
        return None

    def create_module(self, spec):
        return _FakeUnoModule(spec.name)

    def exec_module(self, module):
        pass


@pytest.fixture(scope="module")
def panel_module():
    """Import the panel under the fake UNO, then forget every module the import brought
    in (the fakes and the UNO-bound librelex_ext modules), so no other test file inherits
    them through sys.modules."""
    finder = _FakeUnoFinder()
    # test_session.py leaves plain (non-package) stand-ins for uno and com.sun.star behind,
    # under which ``import com.sun.star.awt`` cannot work: set them aside, restore them after
    parked = {name: sys.modules.pop(name) for name in list(sys.modules)
              if name in ("uno", "unohelper", "com") or name.startswith("com.")}
    sys.meta_path.insert(0, finder)
    before = set(sys.modules)
    try:
        yield importlib.import_module("librelex_ext.panel")
    finally:
        sys.meta_path.remove(finder)
        for name in set(sys.modules) - before:
            sys.modules.pop(name, None)
        sys.modules.update(parked)


class FakeSidebarPanel:
    def __init__(self, log, panel_id):
        self.log, self.panel_id = log, panel_id
        self.titles = []
        self.collapsed = False

    def setTitle(self, title):
        self.log.append(("setTitle", self.panel_id, title))
        self.titles.append(title)

    def collapse(self):
        self.log.append(("collapse", self.panel_id))
        self.collapsed = True


class FakeSidebar:
    """``frame.getController().getSidebar()`` down to the panels, logging every entry."""

    def __init__(self):
        self.log = []                        # every sidebar API call, in order
        self.panels = {}

    def getController(self):
        return self

    def getSidebar(self):
        self.log.append(("getSidebar",))
        return self

    def getDecks(self):
        return self

    def getPanels(self):
        return self

    def getByName(self, name):
        if name == "LibreLexDeck":
            return self
        return self.panels.setdefault(name, FakeSidebarPanel(self.log, name))


class FakeAsyncCallback:
    """``com.sun.star.awt.AsyncCallback``: queues (callback, data) until the test runs the
    main loop with ``run``."""

    def __init__(self):
        self.pending = []

    def addCallback(self, callback, data):
        self.pending.append((callback, data))

    def run(self):
        pending, self.pending = self.pending, []
        for callback, data in pending:
            callback.notify(data)


@pytest.fixture
def drafting_panel(panel_module):
    loop = FakeAsyncCallback()
    ctx = mock.Mock()
    ctx.ServiceManager.createInstanceWithContext.side_effect = (
        lambda name, _ctx: loop if name == "com.sun.star.awt.AsyncCallback" else mock.Mock())
    sidebar = FakeSidebar()
    panel = panel_module.Panel(ctx, sidebar, None,
                               "private:resource/toolpanel/LibreLexPanelFactory/Drafting",
                               "Drafting")
    panel.model = mock.Mock()                # every control exists; attributes are free
    panel.model.hasByName.return_value = True
    panel.window = mock.Mock()
    panel.window.getControl.return_value.getSelectedItemPos.return_value = -1   # no row
    return panel, sidebar, loop


def test_set_step_defers_the_panel_title_to_the_main_loop(drafting_panel):
    panel, sidebar, loop = drafting_panel
    panel.set_step(2)
    assert sidebar.log == [], "the sidebar API was entered from inside the panel's own call"
    loop.run()
    assert sidebar.panels["LibreLexRedazionePanel"].titles == ["Redazione · 2/4 Domande"]


def test_start_of_drafting_collapses_the_other_panels_in_a_later_callback(drafting_panel):
    panel, sidebar, loop = drafting_panel
    panel.set_step(3)                        # from the initial step 1: the drafting starts
    assert sidebar.log == []
    assert len(loop.pending) == 1
    loop.run()
    assert sidebar.panels["LibreLexRedazionePanel"].titles == ["Redazione · 3/4 In corso"]
    assert not [entry for entry in sidebar.log if entry[0] == "collapse"]
    assert len(loop.pending) == 1           # collapsing gets a separate sidebar callback
    loop.run()
    assert sidebar.panels["LibreLexActionsPanel"].collapsed
    assert sidebar.panels["LibreLexCitationsPanel"].collapsed
    assert "LibreLexAnswersPanel" not in sidebar.panels


def test_disposed_panel_drops_its_queued_sidebar_calls(drafting_panel):
    panel, sidebar, loop = drafting_panel
    panel.set_step(2)
    panel.dispose()
    loop.run()
    assert sidebar.log == []


def test_queued_sidebar_calls_never_raise_when_the_sidebar_is_gone(drafting_panel):
    panel, sidebar, loop = drafting_panel
    panel.set_step(3)

    def gone():
        raise RuntimeError("no sidebar under headless LibreOffice")

    sidebar.getSidebar = gone
    loop.run()                               # a closed panel, a headless run: still silent
    assert sidebar.panels == {}
