# Three Native Sidebar Panels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single tall sidebar panel with three native panels in the LibreLex deck ("Azioni", "Citazioni", "Risposte"), each collapsible through the sidebar's own title bar, with "Risposte" taking the height left over, so the panel is compact and intuitive (the user's request of 2026-09-11 after seeing 0.2.0).

**Architecture:** One deck, three `Sidebar.xcu` panels served by the same `PanelFactory` (resource URL suffix `Actions` | `Citations` | `Answers`). One `Session` per document (unchanged); a per-document `PanelSet` (registry) owns the bridge event queue and the `AsyncCallback` and binds the session once to a `CompositeView` that fans View calls out to whichever panels are currently alive. Each panel builds only its own controls from `layout.build(kind, width)`. No core change.

**Tech Stack:** as before (LibreOffice Python 3.13, stdlib + uno; awt controls on the container window's model; XDL container with `withtitlebar="false"`).

**Spec:** `docs/superpowers/specs/2026-09-07-librelex-it-design.md` §5.1 (amended in Task 1), §7.3.

## Global Constraints

- Extension only: stdlib + `uno`/`unohelper`; all UNO calls on the UI thread; controls added to each container window's own model (never `setModel`); the XDL keeps `dlg:withtitlebar="false"` (a title bar turns the container into a floating window, fixed in 8b68f1b).
- Panel copy Italian, plain text; the notice `Le citazioni vanno sempre controllate dal professionista.` stays visible (top of "Azioni").
- Verdict markers, text cache, `select_citation`, `clear_transcript`, `set_progress` semantics unchanged (spec §7.3); comments in the document still only for problems.
- Extension version `0.3.0` (`extension/librelex_ext/__init__.py` and `extension/description.xml`); core untouched (0.2.0); `PROTOCOL_VERSION` stays 1.
- Tooling and commits as in the previous plans (ruff E F I UP B line 100; Conventional Commits with trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` via several `-m` flags, no heredocs, never amend; never run LibreOffice's bundled python or `unopkg`; headless tests only through `extension/tests/headless/conftest.py` and `scripts/lo_install.py`).

---

## File structure

```
extension/
├── Sidebar.xcu                       # deck LibreLexDeck + panels Actions/Citations/Answers (MPL header kept)
├── librelex_ext/layout.py            # build(kind, width), total_height, ACTIONS, BUSY_DISABLED, KINDS
├── librelex_ext/views.py             # panel_kind(url), CompositeView (pure Python)
├── librelex_ext/registry.py          # PanelSet (queue + AsyncCallback + CompositeView) per document
├── librelex_ext/panel.py             # PanelFactory by kind, Panel(kind): controls, listeners, view methods, Answers resize
├── librelex_ext/__init__.py, description.xml   # 0.3.0
└── tests/test_layout.py, tests/test_views.py, tests/test_build_oxt.py, tests/headless/test_read.py
README.md, docs/superpowers/specs/2026-09-07-librelex-it-design.md (§5.1)
```

---

### Task 1: Sidebar registration, per-kind layout, composite view (pure parts)

**Files:**
- Modify: `extension/Sidebar.xcu`, `extension/librelex_ext/layout.py`, `extension/librelex_ext/__init__.py`, `extension/description.xml`, `docs/superpowers/specs/2026-09-07-librelex-it-design.md` (§5.1)
- Create: `extension/librelex_ext/views.py`
- Test: `extension/tests/test_layout.py`, `extension/tests/test_views.py`, `extension/tests/test_build_oxt.py` (0.3.0)

**Interfaces:**
- `layout.KINDS = ("Actions", "Citations", "Answers")`; `layout.build(kind: str, width: int) -> list[Control]` (unknown kind → `ValueError`); `layout.build_all(width) -> dict[str, list[Control]]`; `layout.total_height(controls) -> int`; `layout.CONTROLS = build_all(WIDTH)`; `layout.ACTIONS` and `layout.BUSY_DISABLED` unchanged in content; `layout.TRANSCRIPT_MIN_H = 120`, `layout.TRANSCRIPT_H = 260` (initial/preferred height of the transcript in "Answers").
- Control sets per kind (names are unique across kinds):
  - Actions: `Notice`, `DocumentLabel`, `ListCitations`, `VerifyDocument`, `VerifySelection`, `Cancel`, `ReferenceLabel`, `Input`, `ShowText`, `InsertNorm`, `Progress` (hidden until a `progress` event), `Status`, `Settings`, `Usage`.
  - Citations: `CitationsHint` (gray FixedText, two lines: `Clic su una voce: vai al paragrafo e mostra il testo nelle Risposte.`), `Citations` (ListBox, height `CITATIONS_H = 96`).
  - Answers: `Clear` (small button, right-aligned, top), `Transcript` (Edit multiline read-only VScroll, height `TRANSCRIPT_H`, resized by the panel to fill its window).
- `views.panel_kind(url: str) -> str`: the segment after the last `/` of the resource URL (`private:resource/toolpanel/LibreLexPanelFactory/Answers` → `"Answers"`), `ValueError` when not in `KINDS`.
- `views.CompositeView`: `attach(kind, panel)`, `detach(kind)`, `panels: dict[str, object]`; View methods route: `append`/`set_transcript` → `Answers`; `set_status`/`set_busy`/`set_progress` → `Actions`; `set_citations` → `Citations`; a missing panel makes the call a no-op.

Sidebar.xcu (replace the `PanelList` node; the deck node stays):

```xml
    <node oor:name="PanelList">
      <node oor:name="LibreLexActionsPanel" oor:op="replace">
        <prop oor:name="Title" oor:type="xs:string"><value xml:lang="en-US">Azioni</value></prop>
        <prop oor:name="Id" oor:type="xs:string"><value>LibreLexActionsPanel</value></prop>
        <prop oor:name="DeckId" oor:type="xs:string"><value>LibreLexDeck</value></prop>
        <prop oor:name="ContextList"><value oor:separator=";">Writer, any, visible ;</value></prop>
        <prop oor:name="ImplementationURL" oor:type="xs:string">
          <value>private:resource/toolpanel/LibreLexPanelFactory/Actions</value>
        </prop>
        <prop oor:name="OrderIndex" oor:type="xs:int"><value>100</value></prop>
        <prop oor:name="WantsCanvas" oor:type="xs:boolean"><value>false</value></prop>
      </node>
      <node oor:name="LibreLexCitationsPanel" oor:op="replace">
        ... Title "Citazioni", Id LibreLexCitationsPanel, ImplementationURL .../Citations, OrderIndex 200 ...
      </node>
      <node oor:name="LibreLexAnswersPanel" oor:op="replace">
        ... Title "Risposte", Id LibreLexAnswersPanel, ImplementationURL .../Answers, OrderIndex 300 ...
      </node>
    </node>
```

(Write the three nodes out in full; the "..." above only abbreviates the repeated properties.)

- [ ] **Step 1: Failing tests**

`extension/tests/test_layout.py` (rewrite):

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_ext.layout import (
    ACTIONS, BUSY_DISABLED, CONTROLS, KINDS, MIN_WIDTH, NOTICE, TOOLTIPS, WIDTH, build, build_all,
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
    assert answers["Transcript"].props["ReadOnly"] is True and answers["Clear"].props["Label"] == "Svuota"
    citations = {c.name: c for c in build("Citations", WIDTH)}
    assert citations["Citations"].props["Dropdown"] is False
```

`extension/tests/test_views.py`:

```python
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
    assert actions.calls == [("set_status", ("Pronto",)), ("set_busy", (True,)), ("set_progress", (3, 9))]
    assert citations.calls == [("set_citations", (["a", "b"],))]
    v.detach("Answers")
    v.append("persa")
    assert answers.calls[-1] == ("set_transcript", ("tutto",))
```

`extension/tests/test_build_oxt.py`: expect `LibreLex-IT-0.3.0.oxt`.

Run: `cd extension && uv run pytest tests/test_layout.py tests/test_views.py tests/test_build_oxt.py -q` → failures.

- [ ] **Step 2: Implement**

`layout.py`: keep the constants and helpers; replace `build(width)` with:

```python
KINDS = ("Actions", "Citations", "Answers")
CITATIONS_H = 96
TRANSCRIPT_MIN_H = 120
TRANSCRIPT_H = 260
HINT_H = 18
SECTIONS = {"DocumentLabel": "Documento",
            "ReferenceLabel": "Riferimento (es. art. 2043 c.c., Cass. n. 12345/2024)"}
HINT = "Clic su una voce: vai al paragrafo e mostra il testo nelle Risposte."


def build(kind: str, width: int) -> list[Control]:
    """Controls of one panel kind for a deck ``width`` dialog units wide (clamped)."""
    if kind not in KINDS:
        raise ValueError(f"unknown panel kind: {kind}")
    width = max(int(width), MIN_WIDTH)
    inner = width - 2 * MARGIN
    col = (width - 12) // 2
    right = width - MARGIN - col
    controls: list[Control] = []
    y = MARGIN

    def section(name, height=SECTION_H, w=inner): ...   # as today
    def button(name, label, x, w=col, h=BUTTON_H, **props): ...   # as today

    if kind == "Actions":
        Notice; DocumentLabel; ListCitations/VerifyDocument; VerifySelection/Cancel;
        ReferenceLabel; Input; ShowText/InsertNorm; Progress (Visible False); Status;
        Settings + Usage                      # same geometry rules as the current build()
    elif kind == "Citations":
        controls.append(Control("FixedText", "CitationsHint", MARGIN, y, inner, HINT_H,
                                {"Label": HINT, "MultiLine": True, "TextColor": GRAY}))
        y += HINT_H + GAP
        controls.append(Control("ListBox", "Citations", MARGIN, y, inner, CITATIONS_H,
                                {"Dropdown": False, "HelpText": TOOLTIPS["Citations"]}))
    else:  # Answers
        button("Clear", "Svuota", width - MARGIN - SMALL_BUTTON_W, SMALL_BUTTON_W, SMALL_BUTTON_H)
        y += SMALL_BUTTON_H + GAP
        controls.append(Control("Edit", "Transcript", MARGIN, y, inner, TRANSCRIPT_H,
                                {"MultiLine": True, "ReadOnly": True, "VScroll": True,
                                 "AutoVScroll": True}))
    return controls


def build_all(width: int) -> dict[str, list[Control]]:
    return {kind: build(kind, width) for kind in KINDS}


CONTROLS = build_all(WIDTH)
```

`views.py`:

```python
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Routing between one Session and the sidebar panels of its document (no UNO)."""
from __future__ import annotations

from librelex_ext.layout import KINDS

ROUTES = {"append": "Answers", "set_transcript": "Answers", "set_status": "Actions",
          "set_busy": "Actions", "set_progress": "Actions", "set_citations": "Citations"}


def panel_kind(url: str) -> str:
    kind = url.rsplit("/", 1)[-1]
    if kind not in KINDS:
        raise ValueError(f"unknown panel resource: {url}")
    return kind


class CompositeView:
    """The Session's single View; each call reaches the panel of that kind, if alive."""

    def __init__(self) -> None:
        self.panels: dict[str, object] = {}

    def attach(self, kind: str, panel: object) -> None:
        self.panels[kind] = panel

    def detach(self, kind: str) -> None:
        self.panels.pop(kind, None)

    def _call(self, method: str, *args) -> None:
        panel = self.panels.get(ROUTES[method])
        if panel is not None:
            getattr(panel, method)(*args)

    def append(self, text: str) -> None: self._call("append", text)
    def set_transcript(self, text: str) -> None: self._call("set_transcript", text)
    def set_status(self, text: str) -> None: self._call("set_status", text)
    def set_busy(self, busy: bool) -> None: self._call("set_busy", busy)
    def set_progress(self, done: int, total) -> None: self._call("set_progress", done, total)
    def set_citations(self, labels: list[str]) -> None: self._call("set_citations", labels)
```

(ruff wants one statement per line: write the six methods on two lines each.)

Version 0.3.0 in `__init__.py` and `description.xml`. Spec §5.1: replace the "Controls:" bullet's first sentence with "Registered as a sidebar deck "LibreLex" with three panels (Azioni, Citazioni, Risposte) served by one factory; each panel is collapsible through the sidebar's own title bar and "Risposte" takes the remaining height; controls: ..." keeping the control list.

- [ ] **Step 3: Run and commit**

`cd extension && uv run ruff check . && uv run pytest -q -m "not headless"` → pass (panel.py is not imported by these tests).

```bash
git add extension docs/superpowers/specs/2026-09-07-librelex-it-design.md
git commit -m "feat(extension): three sidebar panels registered, per-kind layout and composite view" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

### Task 2: PanelSet, Panel by kind, Answers auto-height, probes and docs

**Files:**
- Modify: `extension/librelex_ext/registry.py`, `extension/librelex_ext/panel.py`, `extension/tests/headless/test_read.py`, `README.md`

**Interfaces:**
- `registry.PanelSet(ctx, session)` (uno, `XCallback`): attributes `session`, `composite: CompositeView`; `post(event)` (any thread: `queue.put` + `AsyncCallback.addCallback(self, None)`); `notify(data)` (UI thread: drain the queue into `session.handle_event`). Created once per document by `registry.panel_set_for(ctx, model, make_session) -> PanelSet`, which calls `session_for(model, make_session)` and, the first time, `session.bind(panel_set.composite, panel_set.post)`. `shutdown_all` and the model listener unchanged (they shut the session down; the PanelSet is dropped with it).
- `panel.PanelFactory.createUIElement(url, args)`: `kind = views.panel_kind(url)`; unknown kinds raise (the sidebar only asks for the three registered URLs).
- `panel.Panel(ctx, frame, parent, url, kind)`: builds `layout.build(kind, width)` into its container window's model (same XDL for all three); registers `XActionListener` only for the buttons it has (`layout.ACTIONS` filtered by `model.hasByName`), the `XItemListener` only when it has `Citations`; `getRealInterface` obtains the `PanelSet` (`registry.panel_set_for`), sets `self.session = panel_set.session`, `panel_set.composite.attach(kind, self)` and replays the state for its kind (Answers: `set_transcript("\n".join(session.transcript))`; Citations: `set_citations([label for label, _, _ in session.citations])`; Actions: `set_busy(session.state in ("starting", "busy"))`). `dispose()` → `composite.detach(kind)` (no draining: the PanelSet keeps delivering events to the session while no panel is shown).
- The first-run banner (`LibreLex-IT pronto. Configurazione: ...` and the Markdown-filter warning) moves into `make_session` right after the `Session` is created (it is created once per document, whichever panel opens first).
- View methods: every Panel implements all six View methods; each is a no-op when its control is absent (`self.model.hasByName(name)` guard), so a misrouted call can never raise inside a UNO listener.
- Heights: Actions and Citations answer `LayoutSize(h, h, h)` from `total_height(build(kind, width_du))` converted to pixels (fallback as today); Answers answers `LayoutSize(min_px, -1, pref_px)` (`TRANSCRIPT_MIN_H + SMALL_BUTTON_H + 3*MARGIN` and `TRANSCRIPT_H + ...` converted) and implements `com.sun.star.awt.XWindowListener` on its container window: `windowResized` converts the window's `getPosSize().Height` to dialog units and sets the `Transcript` model `Height` to fill the panel below the `Clear` button (minimum `TRANSCRIPT_MIN_H`); `windowMoved`/`windowShown`/`windowHidden`/`disposing` are no-ops. `getMinimalWidth` unchanged for all kinds.
- Actions panel `actionPerformed` keeps today's commands; `Clear` lives in Answers and calls `session.clear_transcript()`; the Citations panel's `itemStateChanged` calls `session.select_citation(pos)`.

- [ ] **Step 1: Headless probes (failing first)** — in `extension/tests/headless/test_read.py`:
  - `test_panel_module_imports_inside_libreoffice`: assert `panel.XDL_URL` unchanged and that `views.panel_kind` accepts the three registered URLs read from `Sidebar.xcu` (parse the file with `xml.etree` in the test and check every `ImplementationURL` value ends with a kind in `layout.KINDS`).
  - Rework the `panel_uv_and_banner` probe for the new structure: build a `PanelSet` through `registry.panel_set_for(ctx, doc, make_session)` with the real `make_session` factored out of `panel.py` into a module-level function `panel.make_session_factory(ctx, model)` (returns the zero-argument factory) so the probe can call it; attach two `FakeCtrl`-based stand-ins for the Answers and Actions panels (objects exposing the six View methods and recording calls); assert: uv-not-found → the session transcript gets `Impossibile avviare il core: uv non trovato...`; detaching and re-attaching a new Answers stand-in replays the transcript exactly once (`count("LibreLex-IT pronto") == 1`); a `bridge_spec` failure (monkeypatched to raise `ValueError`) leaves `session.state == "stopped"` with a readable transcript line. Keep the existing assertions' meaning.
  - `test_registry.py`: unchanged (session teardown); add an assertion that `registry.panel_set_for(ctx, doc, factory)` returns the same object twice for the same document.

- [ ] **Step 2: Implement** `registry.PanelSet`, `panel.py` refactor (`Panel(kind)`, per-kind listeners and view methods, Answers `XWindowListener`, `PanelFactory` by kind, `make_session_factory`), README ("tre pannelli: Azioni, Citazioni, Risposte; ogni pannello si apre e chiude dal suo titolo").

- [ ] **Step 3: Run** `cd extension && uv run ruff check . && uv run pytest -q` (headless included).

- [ ] **Step 4: Commit**

```bash
git add extension README.md
git commit -m "feat(extension): Azioni, Citazioni and Risposte as native sidebar panels sharing one session" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```

---

## Self-review

- Spec §5.1 (amended): deck with three panels, collapsible natively, Answers fills the remaining height → Tasks 1-2. §7.3 behaviour untouched (session/render unchanged).
- Names consistent: `layout.build(kind, width)`, `build_all`, `KINDS`, `views.panel_kind`, `views.CompositeView.attach/detach`, `registry.PanelSet(ctx, session)` with `post`/`notify`/`composite`, `registry.panel_set_for(ctx, model, make_session)`, `panel.make_session_factory(ctx, model)`, `Panel(ctx, frame, parent, url, kind)`.
- The only unverifiable part headless is the sidebar geometry (LayoutSize with Maximum -1 and the resize listener): the user's screenshot closes it.
