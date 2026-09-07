# Phase 0 — Spike Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer the five open assumptions of the spec (§12) with reproducible evidence, and write the answers back into the spec before any product code is written.

**Architecture:** Throwaway scripts under `spike/`, run with LibreOffice's bundled Python against a headless LibreOffice started with a private profile; one tiny `.oxt` for the GUI-only sidebar question. Nothing under `spike/` is ever packaged.

**Tech Stack:** LibreOffice 26.8 (`/Applications/LibreOffice.app`), its bundled Python (`/Applications/LibreOffice.app/Contents/Resources/python`, Python 3.13 with `uno`), `unopkg`, zip.

**Spec:** `docs/superpowers/specs/2026-09-07-librelex-it-design.md` (§5.4, §5.5, §12, §13)

## Global Constraints

- LibreOffice binary: `/Applications/LibreOffice.app/Contents/MacOS/soffice`; bundled Python wrapper: `/Applications/LibreOffice.app/Contents/Resources/python` (exported as `LOPY` below).
- Every headless run uses a private profile (`-env:UserInstallation=file://<tmp dir>`) so the user's real LibreOffice profile is never touched.
- UNO socket port for the spike: `2083` on `127.0.0.1` only.
- Spike code lives in `spike/` and is committed for reproducibility, but `spike/` is excluded from the `.oxt` build (Global rule for `scripts/build_oxt.py` in later plans).
- Findings are recorded in the spec, §12, as a "Result:" line under each assumption, and §5.4/§5.5 are amended if an assumption fails.
- Commits follow Conventional Commits; type `chore(spike)`. Never commit without the user's go-ahead (CLAUDE.md rule): each "Commit" step below means "propose the commit and wait".
- The sandbox available to Claude kills LibreOffice's Python wrapper (exit 137 observed on 2026-09-07); the scripts are therefore run from the user's terminal, and their printed output is pasted back as evidence.

---

### Task 1: Spike harness (start headless LibreOffice, connect over UNO)

**Files:**
- Create: `spike/README.md`
- Create: `spike/lo.py`
- Create: `spike/run.sh`

**Interfaces:**
- Produces: `spike/lo.py` with `prop(name, value) -> PropertyValue`, `run_with_soffice(fn)` that starts soffice, connects, calls `fn(ctx)` and always terminates soffice, `new_writer_doc(ctx)` returning a hidden Writer document, `PARAGRAPH_BREAK`.

- [ ] **Step 1: Write the harness**

`spike/README.md`:

```markdown
# Phase 0 spike (throwaway)

Scripts that answer spec §12. Run each with LibreOffice's bundled Python:

    ./spike/run.sh spike/s1_markdown_insert.py

They start a headless LibreOffice with a private profile on port 2083,
run, print evidence, and shut it down. Nothing here ships.
```

`spike/run.sh`:

```bash
#!/usr/bin/env bash
# Run a spike script with LibreOffice's bundled Python (has `uno`).
set -euo pipefail
LOPY="${LOPY:-/Applications/LibreOffice.app/Contents/Resources/python}"
cd "$(dirname "$0")"
exec "$LOPY" "$(basename "$1")"
```

`spike/lo.py`:

```python
"""Throwaway helpers for the Phase 0 spike. Run with LibreOffice's bundled Python."""
import os
import subprocess
import tempfile
import time

import uno
from com.sun.star.beans import PropertyValue
from com.sun.star.text.ControlCharacter import PARAGRAPH_BREAK  # noqa: F401  (re-exported)

SOFFICE = os.environ.get("SOFFICE", "/Applications/LibreOffice.app/Contents/MacOS/soffice")
PORT = 2083


def prop(name, value):
    p = PropertyValue()
    p.Name = name
    p.Value = value
    return p


def _start(profile_dir):
    cmd = [
        SOFFICE,
        f"-env:UserInstallation=file://{profile_dir}",
        "--headless", "--norestore", "--nologo", "--nodefault",
        f"--accept=socket,host=127.0.0.1,port={PORT};urp;StarOffice.ComponentContext",
    ]
    return subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _connect(retries=60):
    local = uno.getComponentContext()
    resolver = local.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver", local)
    url = f"uno:socket,host=127.0.0.1,port={PORT};urp;StarOffice.ComponentContext"
    for _ in range(retries):
        try:
            return resolver.resolve(url)
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("soffice did not come up on port %d" % PORT)


def run_with_soffice(fn):
    """Start soffice with a private profile, call fn(ctx), always terminate soffice."""
    profile = tempfile.mkdtemp(prefix="lo_spike_profile_")
    proc = _start(profile)
    try:
        ctx = _connect()
        return fn(ctx)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def new_writer_doc(ctx):
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    return desktop.loadComponentFromURL("private:factory/swriter", "_blank", 0, (prop("Hidden", True),))


def paragraphs(doc):
    """Yield (ParaStyleName, String) for every body paragraph."""
    enum = doc.Text.createEnumeration()
    while enum.hasMoreElements():
        el = enum.nextElement()
        if el.supportsService("com.sun.star.text.Paragraph"):
            yield el.ParaStyleName, el.String


def redlines(doc):
    """Yield (type, author, text) for every tracked change in the document."""
    enum = doc.Redlines.createEnumeration()
    while enum.hasMoreElements():
        r = enum.nextElement()
        try:
            text = r.RedlineText.getString()
        except Exception:
            text = "<no RedlineText>"
        yield r.RedlineType, r.RedlineAuthor, text
```

- [ ] **Step 2: Smoke-run the harness**

`spike/s0_smoke.py`:

```python
from lo import run_with_soffice, new_writer_doc, paragraphs


def main(ctx):
    doc = new_writer_doc(ctx)
    doc.Text.insertString(doc.Text.createTextCursor(), "ciao", False)
    print("PARAGRAPHS:", list(paragraphs(doc)))
    print("LO VERSION:", ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.configuration.ConfigurationProvider", ctx).createInstanceWithArguments(
        "com.sun.star.configuration.ConfigurationAccess",
        (__import__("lo").prop("nodepath", "/org.openoffice.Setup/Product"),)).getByName("ooSetupVersionAboutBox"))
    doc.close(True)


run_with_soffice(main)
```

Run: `chmod +x spike/run.sh && ./spike/run.sh spike/s0_smoke.py`
Expected: `PARAGRAPHS: [('Standard', 'ciao')]` and `LO VERSION: 26.8.0.3` (or the installed version). If soffice does not come up, check that no other LibreOffice instance is holding port 2083.

- [ ] **Step 3: Commit**

```bash
git add spike/README.md spike/lo.py spike/run.sh spike/s0_smoke.py
git commit -m "chore(spike): add headless LibreOffice harness for the Phase 0 spike"
```

---

### Task 2: Assumption 1 — Markdown insertion at the cursor is a tracked change

**Files:**
- Create: `spike/s1_markdown_insert.py`

**Interfaces:**
- Consumes: `spike/lo.py` (`run_with_soffice`, `new_writer_doc`, `prop`, `paragraphs`, `redlines`, `PARAGRAPH_BREAK`).

- [ ] **Step 1: Write the probe**

```python
"""Does insertDocumentFromURL(FilterName=Markdown) insert AT THE CURSOR and get recorded as a redline?"""
import pathlib
import tempfile

import uno
from lo import PARAGRAPH_BREAK, new_writer_doc, paragraphs, prop, redlines, run_with_soffice

MD = "# Titolo inserito\n\nParagrafo con **grassetto** e *corsivo*.\n\n> Citazione in blocco.\n\n- uno\n- due\n"


def main(ctx):
    doc = new_writer_doc(ctx)
    text = doc.Text
    cur = text.createTextCursor()
    text.insertString(cur, "Primo paragrafo.", False)
    text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
    text.insertString(cur, "Terzo paragrafo (era il secondo).", False)

    # cursor at the END of the first paragraph
    cur.gotoStart(False)
    cur.gotoEndOfParagraph(False)

    md = pathlib.Path(tempfile.mkdtemp()) / "insert.md"
    md.write_text(MD, encoding="utf-8")

    doc.RecordChanges = True
    cur.insertDocumentFromURL(uno.systemPathToFileUrl(str(md)), (prop("FilterName", "Markdown"),))
    doc.RecordChanges = False
    md.unlink()

    print("--- paragraphs in order (style | text) ---")
    for style, s in paragraphs(doc):
        print(f"{style!r:22s} | {s[:50]!r}")
    print("--- redlines (type | author | text) ---")
    rl = list(redlines(doc))
    for t, a, s in rl:
        print(f"{t!r:10s} | {a!r:12s} | {s[:50]!r}")
    print("REDLINE COUNT:", len(rl))
    doc.close(True)


run_with_soffice(main)
```

- [ ] **Step 2: Run and record**

Run: `./spike/run.sh spike/s1_markdown_insert.py`

Expected if the assumption holds: the paragraph list shows `Primo paragrafo.`, then the Markdown paragraphs with styles `Heading 1`, `Text body`, `Quotations`, list paragraphs, then `Terzo paragrafo`; `REDLINE COUNT` ≥ 1 with type `Insert`.

Record verbatim in the spec (Task 7) which of these is true:
- (a) inserted at the cursor AND redlined → assumption 1 holds;
- (b) inserted at the cursor but `REDLINE COUNT: 0` → insertion is not tracked: the adapter must insert into a hidden scratch document, then copy the range with `XTransferable`/`insertTransferable` while recording (test that variant in Step 3);
- (c) inserted at document start/end regardless of cursor → the adapter must use a scratch document + transferable (Step 3);
- (d) exception on `FilterName` → try `"Markdown (Writer)"`, and record the exact filter name that works (`writer.xcd` lists `Markdown`, type `generic_Markdown`).

- [ ] **Step 3: Only if (b) or (c): probe the scratch-document variant**

Append to `spike/s1_markdown_insert.py` a second function and call it after `main`:

```python
def variant_transferable(ctx):
    """Load the markdown into a hidden scratch doc, copy all, paste at the cursor while recording."""
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    md = pathlib.Path(tempfile.mkdtemp()) / "insert.md"
    md.write_text(MD, encoding="utf-8")
    scratch = desktop.loadComponentFromURL(
        uno.systemPathToFileUrl(str(md)), "_blank", 0,
        (prop("Hidden", True), prop("FilterName", "Markdown")))
    md.unlink()
    scratch_ctrl = scratch.CurrentController
    scratch_ctrl.select(scratch.Text)          # select everything
    transferable = scratch_ctrl.getTransferable()

    doc = new_writer_doc(ctx)
    text = doc.Text
    cur = text.createTextCursor()
    text.insertString(cur, "Primo paragrafo.", False)
    text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
    text.insertString(cur, "Terzo paragrafo.", False)
    vc = doc.CurrentController.ViewCursor
    vc.gotoStart(False)
    vc.gotoEndOfParagraph(False)
    doc.RecordChanges = True
    doc.CurrentController.insertTransferable(transferable)
    doc.RecordChanges = False
    print("--- VARIANT paragraphs ---")
    for style, s in paragraphs(doc):
        print(f"{style!r:22s} | {s[:50]!r}")
    print("--- VARIANT redlines ---")
    rl = list(redlines(doc))
    for t, a, s in rl:
        print(f"{t!r:10s} | {a!r:12s} | {s[:50]!r}")
    print("VARIANT REDLINE COUNT:", len(rl))
    scratch.close(True)
    doc.close(True)


run_with_soffice(variant_transferable)
```

Run again and record which variant the adapter will use.

- [ ] **Step 4: Commit**

```bash
git add spike/s1_markdown_insert.py
git commit -m "chore(spike): probe Markdown insertion at the cursor under RecordChanges"
```

---

### Task 3: Assumption 2 — redline author can be set to "LibreLex"

**Files:**
- Create: `spike/s2_redline_author.py`

**Interfaces:**
- Consumes: `spike/lo.py`.
- Produces: the verified mechanism (or the fallback) for spec §5.4 item 3.

- [ ] **Step 1: Write the probe**

```python
"""Can the author of the next tracked change be forced to 'LibreLex' without a restart?"""
from lo import PARAGRAPH_BREAK, new_writer_doc, prop, redlines, run_with_soffice

NODE = "/org.openoffice.UserProfile/Data"


def profile_access(ctx, update):
    provider = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.configuration.ConfigurationProvider", ctx)
    service = ("com.sun.star.configuration.ConfigurationUpdateAccess" if update
               else "com.sun.star.configuration.ConfigurationAccess")
    return provider.createInstanceWithArguments(service, (prop("nodepath", NODE),))


def set_name(ctx, given, surname):
    acc = profile_access(ctx, update=True)
    acc.setPropertyValue("givenname", given)
    acc.setPropertyValue("sn", surname)
    acc.commitChanges()


def tracked_insert(doc, s):
    cur = doc.Text.createTextCursor()
    cur.gotoEnd(False)
    doc.RecordChanges = True
    doc.Text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
    doc.Text.insertString(cur, s, False)
    doc.RecordChanges = False


def main(ctx):
    acc = profile_access(ctx, update=False)
    original = (acc.getPropertyValue("givenname"), acc.getPropertyValue("sn"))
    print("ORIGINAL PROFILE NAME:", original)

    doc = new_writer_doc(ctx)
    doc.Text.insertString(doc.Text.createTextCursor(), "Base.", False)

    # Probe A: is there a writable document property? (expected: no)
    try:
        doc.setPropertyValue("RedlineAuthor", "LibreLex-A")
        print("PROBE A: document property RedlineAuthor accepted")
    except Exception as e:
        print("PROBE A: no writable RedlineAuthor on the document:", type(e).__name__)

    tracked_insert(doc, "inserimento uno")
    print("AFTER PROBE A:", list(redlines(doc)))

    # Probe B: temporary profile switch
    try:
        set_name(ctx, "LibreLex", "")
        tracked_insert(doc, "inserimento due")
        print("AFTER PROBE B:", list(redlines(doc)))
    finally:
        set_name(ctx, *original)
    acc = profile_access(ctx, update=False)
    print("RESTORED PROFILE NAME:", (acc.getPropertyValue("givenname"), acc.getPropertyValue("sn")))

    tracked_insert(doc, "inserimento tre")
    print("AFTER RESTORE:", list(redlines(doc)))
    doc.close(True)


run_with_soffice(main)
```

- [ ] **Step 2: Run and record**

Run: `./spike/run.sh spike/s2_redline_author.py`

Expected if the assumption holds: the second redline shows author `LibreLex`, the third shows the original author again (in a fresh headless profile the original is an empty name, rendered as `Unknown Author` or similar), and `RESTORED PROFILE NAME` equals `ORIGINAL PROFILE NAME`.

Record in the spec:
- if Probe B works: keep §5.4 item 3 as designed (`redline_author = "librelex"` default);
- if Probe B shows the old author (Writer caches the author for the session): set the default to `"user"`, and note in §5.4 that provenance lives in the undo label and the bookmark;
- if Probe A unexpectedly works: prefer it (simpler, no profile writes) and document the property.

- [ ] **Step 3: Commit**

```bash
git add spike/s2_redline_author.py
git commit -m "chore(spike): probe redline author override via UserProfile switch"
```

---

### Task 4: Assumption 3 — anchored comments in the body and in footnotes

**Files:**
- Create: `spike/s3_annotations.py`

**Interfaces:**
- Consumes: `spike/lo.py`.
- Produces: the confirmed anchoring recipe for spec §5.5, and the footnote behaviour.

- [ ] **Step 1: Write the probe**

```python
"""Anchor a Writer comment on a character range; try the same inside a footnote."""
from lo import new_writer_doc, run_with_soffice

BODY = "Come previsto dall'art. 2043 c.c., il danno va risarcito."
TARGET = "art. 2043 c.c."


def annotation(doc, author, content):
    ann = doc.createInstance("com.sun.star.text.textfield.Annotation")
    ann.Author = author
    ann.Content = content
    return ann


def anchor_on_range(text, start, length, ann):
    cur = text.createTextCursor()
    cur.gotoStart(False)
    cur.goRight(start, False)
    cur.goRight(length, True)      # expand selection over the target
    assert cur.getString() == TARGET, cur.getString()
    text.insertTextContent(cur, ann, True)   # absorb=True → attach to the range


def dump_fields(doc, label):
    print(f"--- {label} ---")
    enum = doc.TextFields.createEnumeration()
    while enum.hasMoreElements():
        f = enum.nextElement()
        if f.supportsService("com.sun.star.text.TextField.Annotation"):
            try:
                rng = f.TextRange.getString()
            except Exception as e:
                rng = f"<no TextRange: {type(e).__name__}>"
            print(f"author={f.Author!r} content={f.Content!r} anchor={f.Anchor.getString()!r} range={rng!r}")


def main(ctx):
    doc = new_writer_doc(ctx)
    text = doc.Text
    cur = text.createTextCursor()
    text.insertString(cur, BODY, False)

    # a footnote after the body sentence
    fn = doc.createInstance("com.sun.star.text.Footnote")
    text.insertTextContent(cur, fn, False)
    fn.setString("Cfr. Cass. sez. III n. 12345/2024.")

    start = BODY.index(TARGET)
    anchor_on_range(text, start, len(TARGET), annotation(doc, "LibreLex · verifica", "commento nel corpo"))
    dump_fields(doc, "after body annotation")

    # inside the footnote
    try:
        fcur = fn.createTextCursor()
        fcur.gotoStart(False)
        fcur.goRight(5, False)
        fcur.goRight(len("Cass. sez. III n. 12345/2024"), True)
        fn.insertTextContent(fcur, annotation(doc, "LibreLex · verifica", "commento nella nota"), True)
        print("FOOTNOTE ANNOTATION: accepted")
    except Exception as e:
        print("FOOTNOTE ANNOTATION: rejected ->", type(e).__name__, str(e)[:120])
    dump_fields(doc, "after footnote attempt")

    # fallback: annotate the footnote anchor in the body (the character right after the sentence)
    acur = fn.Anchor.getText().createTextCursorByRange(fn.Anchor)
    acur.goLeft(1, True)
    text.insertTextContent(acur, annotation(doc, "LibreLex · verifica", "commento sull'ancora della nota"), True)
    dump_fields(doc, "after anchor fallback")
    doc.close(True)


run_with_soffice(main)
```

- [ ] **Step 2: Run and record**

Run: `./spike/run.sh spike/s3_annotations.py`

Expected: the body annotation lists `range='art. 2043 c.c.'`; the footnote attempt prints either `accepted` (then §5.5 can drop the fallback) or `rejected` with the exception name (keep the fallback as designed). Record both outputs verbatim.

- [ ] **Step 3: Commit**

```bash
git add spike/s3_annotations.py
git commit -m "chore(spike): probe range-anchored annotations in body and footnotes"
```

---

### Task 5: Assumption 4 — Python sidebar panel updated from a worker thread

**Files:**
- Create: `spike/oxt/META-INF/manifest.xml`
- Create: `spike/oxt/description.xml`
- Create: `spike/oxt/Sidebar.xcu`
- Create: `spike/oxt/Factory.xcu`
- Create: `spike/oxt/panel.xdl`
- Create: `spike/oxt/librelex_spike.py`
- Create: `spike/build_oxt.sh`

**Interfaces:**
- Produces: a validated minimal sidebar skeleton (derived from LibreThinker, MPL-2.0) that the M1 extension plan will copy.

- [ ] **Step 1: Write the extension files**

`spike/oxt/META-INF/manifest.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="http://openoffice.org/2001/manifest">
  <manifest:file-entry manifest:media-type="application/vnd.sun.star.uno-component;type=Python"
                       manifest:full-path="librelex_spike.py"/>
  <manifest:file-entry manifest:media-type="application/vnd.sun.star.configuration-data"
                       manifest:full-path="Factory.xcu"/>
  <manifest:file-entry manifest:media-type="application/vnd.sun.star.configuration-data"
                       manifest:full-path="Sidebar.xcu"/>
</manifest:manifest>
```

`spike/oxt/description.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<description xmlns="http://openoffice.org/extensions/description/2006"
             xmlns:d="http://openoffice.org/extensions/description/2006"
             xmlns:xlink="http://www.w3.org/1999/xlink">
  <identifier value="org.librelex.spike"/>
  <version value="0.0.1"/>
  <platform value="all"/>
  <display-name><name lang="en">LibreLex spike (throwaway)</name></display-name>
  <dependencies>
    <OpenOffice.org-minimal-version value="4.1" d:name="OpenOffice.org 4.1"/>
  </dependencies>
</description>
```

`spike/oxt/Sidebar.xcu` (derived from LibreThinker, MPL-2.0):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Derived from LibreThinker (https://github.com/mihailthebuilder/librethinker-extension), MPL-2.0. -->
<oor:component-data oor:name="Sidebar" oor:package="org.openoffice.Office.UI"
    xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <node oor:name="Content">
    <node oor:name="DeckList">
      <node oor:name="LibreLexSpikeDeck" oor:op="replace">
        <prop oor:name="Title" oor:type="xs:string"><value xml:lang="en-US">LibreLex spike</value></prop>
        <prop oor:name="Id" oor:type="xs:string"><value>LibreLexSpikeDeck</value></prop>
        <prop oor:name="ContextList"><value oor:separator=";">Writer, any, visible ;</value></prop>
        <prop oor:name="OrderIndex" oor:type="xs:int"><value>700</value></prop>
      </node>
    </node>
    <node oor:name="PanelList">
      <node oor:name="LibreLexSpikePanel" oor:op="replace">
        <prop oor:name="Title" oor:type="xs:string"><value xml:lang="en-US">Streaming test</value></prop>
        <prop oor:name="Id" oor:type="xs:string"><value>LibreLexSpikePanel</value></prop>
        <prop oor:name="DeckId" oor:type="xs:string"><value>LibreLexSpikeDeck</value></prop>
        <prop oor:name="ContextList"><value oor:separator=";">Writer, any, visible ;</value></prop>
        <prop oor:name="ImplementationURL" oor:type="xs:string">
          <value>private:resource/toolpanel/LibreLexSpikeFactory/Panel</value>
        </prop>
        <prop oor:name="OrderIndex" oor:type="xs:int"><value>100</value></prop>
        <prop oor:name="WantsCanvas" oor:type="xs:boolean"><value>false</value></prop>
      </node>
    </node>
  </node>
</oor:component-data>
```

`spike/oxt/Factory.xcu`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!-- Derived from LibreThinker (https://github.com/mihailthebuilder/librethinker-extension), MPL-2.0. -->
<oor:component-data oor:name="Factories" oor:package="org.openoffice.Office.UI"
    xmlns:oor="http://openoffice.org/2001/registry" xmlns:xs="http://www.w3.org/2001/XMLSchema">
  <node oor:name="Registered">
    <node oor:name="UIElementFactories">
      <node oor:name="LibreLexSpikeFactory" oor:op="replace">
        <prop oor:name="Type"><value>toolpanel</value></prop>
        <prop oor:name="Name"><value>LibreLexSpikeFactory</value></prop>
        <prop oor:name="Module"><value/></prop>
        <prop oor:name="FactoryImplementation"><value>org.librelex.spike.PanelFactory</value></prop>
      </node>
    </node>
  </node>
</oor:component-data>
```

`spike/oxt/panel.xdl`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE dlg:window PUBLIC "-//OpenOffice.org//DTD OfficeDocument 1.0//EN" "dialog.dtd">
<dlg:window xmlns:dlg="http://openoffice.org/2000/dialog" xmlns:script="http://openoffice.org/2000/script"
            dlg:id="LibreLexSpike" dlg:left="0" dlg:top="0" dlg:width="170" dlg:height="260"
            dlg:closeable="true" dlg:moveable="true" dlg:title="LibreLex spike"/>
```

`spike/oxt/librelex_spike.py`:

```python
# -*- coding: utf-8 -*-
# Derived from LibreThinker (https://github.com/mihailthebuilder/librethinker-extension), MPL-2.0.
# This file stays under the Mozilla Public License 2.0.
"""Minimal sidebar panel: a read-only log fed by a worker thread through AsyncCallback."""
import queue
import threading
import time

import uno
import unohelper
from com.sun.star.awt import XActionListener, XCallback
from com.sun.star.lang import XComponent
from com.sun.star.ui import LayoutSize, XSidebarPanel, XToolPanel, XUIElement, XUIElementFactory
from com.sun.star.ui.UIElementType import TOOLPANEL

PANEL_URL = "private:resource/toolpanel/LibreLexSpikeFactory/Panel"
XDL_URL = "vnd.sun.star.extension://org.librelex.spike/panel.xdl"


class PanelFactory(unohelper.Base, XUIElementFactory):
    def __init__(self, ctx):
        self.ctx = ctx

    def createUIElement(self, url, args):
        frame = parent = None
        for a in args:
            if a.Name == "Frame":
                frame = a.Value
            elif a.Name == "ParentWindow":
                parent = a.Value
        panel = Panel(self.ctx, frame, parent, url)
        panel.getRealInterface()
        panel.Window.Visible = True
        return panel


class Panel(unohelper.Base, XUIElement, XToolPanel, XSidebarPanel, XComponent, XActionListener, XCallback):
    def __init__(self, ctx, frame, parent, url):
        self.ctx = ctx
        self.frame = frame
        self.parent = parent
        self.url = url
        self.window = None
        self.queue = queue.Queue()
        self.async_cb = ctx.ServiceManager.createInstanceWithContext("com.sun.star.awt.AsyncCallback", ctx)

    # --- XUIElement -------------------------------------------------------
    def getRealInterface(self):
        if self.window is None:
            provider = self.ctx.ServiceManager.createInstanceWithContext(
                "com.sun.star.awt.ContainerWindowProvider", self.ctx)
            self.window = provider.createContainerWindow(XDL_URL, "", self.parent, None)
            self._build_controls()
        return self

    @property
    def Frame(self):
        return self.frame

    @property
    def ResourceURL(self):
        return self.url

    @property
    def Type(self):
        return TOOLPANEL

    # --- XToolPanel / XSidebarPanel ----------------------------------------
    @property
    def Window(self):
        return self.window

    def createAccessible(self, parent):
        return self

    def getHeightForWidth(self, width):
        return LayoutSize(260, 260, 260)

    def getMinimalWidth(self):
        return 200

    # --- XComponent --------------------------------------------------------
    def dispose(self):
        pass

    def addEventListener(self, listener):
        pass

    def removeEventListener(self, listener):
        pass

    # --- controls ----------------------------------------------------------
    def _build_controls(self):
        smgr = self.ctx.ServiceManager
        model = smgr.createInstanceWithContext("com.sun.star.awt.UnoControlDialogModel", self.ctx)
        self.window.setModel(model)
        log = model.createInstance("com.sun.star.awt.UnoControlEditModel")
        log.Name = "Log"
        log.PositionX, log.PositionY, log.Width, log.Height = 4, 4, 160, 200
        log.MultiLine = True
        log.ReadOnly = True
        log.AutoVScroll = True
        model.insertByName("Log", log)
        btn = model.createInstance("com.sun.star.awt.UnoControlButtonModel")
        btn.Name = "Start"
        btn.PositionX, btn.PositionY, btn.Width, btn.Height = 4, 210, 60, 16
        btn.Label = "Start stream"
        model.insertByName("Start", btn)
        self.window.getControl("Start").addActionListener(self)
        self.window.getControl("Start").setActionCommand("start")

    # --- XActionListener: button click on the UI thread ---------------------
    def actionPerformed(self, event):
        if event.ActionCommand == "start":
            self.window.getControl("Log").Text = ""
            threading.Thread(target=self._worker, daemon=True).start()

    def disposing(self, event):
        pass

    def _worker(self):
        """Simulates streaming: 100 chunks over ~5 s, pushed to the UI via AsyncCallback."""
        for i in range(1, 101):
            time.sleep(0.05)
            self.queue.put(f"chunk {i}\n")
            self.async_cb.addCallback(self, None)    # schedules notify() on the UI thread
        self.queue.put("[done]\n")
        self.async_cb.addCallback(self, None)

    # --- XCallback: runs on the UI thread ------------------------------------
    def notify(self, data):
        chunks = []
        try:
            while True:
                chunks.append(self.queue.get_nowait())
        except queue.Empty:
            pass
        if chunks:
            ctrl = self.window.getControl("Log")
            ctrl.Text = ctrl.Text + "".join(chunks)


g_ImplementationHelper = unohelper.ImplementationHelper()
g_ImplementationHelper.addImplementation(PanelFactory, "org.librelex.spike.PanelFactory", ("com.sun.star.task.Job",))
```

`spike/build_oxt.sh`:

```bash
#!/usr/bin/env bash
# Build spike/librelex-spike.oxt and (re)install it in the user's LibreOffice.
set -euo pipefail
cd "$(dirname "$0")/oxt"
rm -f ../librelex-spike.oxt
zip -r -q ../librelex-spike.oxt . -x '*.DS_Store'
cd ..
UNOPKG="${UNOPKG:-/Applications/LibreOffice.app/Contents/MacOS/unopkg}"
"$UNOPKG" remove org.librelex.spike >/dev/null 2>&1 || true
"$UNOPKG" add --force librelex-spike.oxt
echo "installed; restart LibreOffice, open Writer, View > Sidebar > LibreLex spike"
```

- [ ] **Step 2: Install and test manually**

Run: `chmod +x spike/build_oxt.sh && ./spike/build_oxt.sh` (LibreOffice must be closed). Then open Writer, open the "LibreLex spike" deck, click "Start stream", and **type in the document while the log fills**.

Record in the spec:
- whether the panel appears (deck icon, panel title), and the exact LibreOffice error if not (Tools > Extension Manager shows Python tracebacks; also check `~/Library/Application Support/LibreOffice/4/user/` for `python.log` when `PYUNO_LOGLEVEL=DEBUG` is exported before launching soffice from a terminal);
- whether typing stays fluid during the 5 seconds of streaming (assumption holds) or the UI freezes (then the M1 extension plan must throttle: batch callbacks every 250 ms as WriterAgent does, and re-test);
- a screenshot of the panel mid-stream saved as `spike/evidence/s4_sidebar.png`.

- [ ] **Step 3: Commit**

```bash
git add spike/oxt spike/build_oxt.sh spike/evidence/s4_sidebar.png
git commit -m "chore(spike): minimal Python sidebar with worker-thread streaming via AsyncCallback"
```

---

### Task 6: Assumption 5 — minimum LibreOffice version with the Markdown import filter

**Files:**
- Modify: `spike/README.md` (append the finding)

- [ ] **Step 1: Check the release notes in a browser**

The TDF wiki blocks automated fetches (verified 2026-09-07: "Access Denied" from Anubis), so open these in a browser and search the page for "Markdown":

- `https://wiki.documentfoundation.org/ReleaseNotes/25.8`
- `https://wiki.documentfoundation.org/ReleaseNotes/25.2`
- `https://help.libreoffice.org/latest/en-US/text/swriter/guide/markdown.html`

Record the first version whose notes list Markdown **import** for Writer (export alone is not enough), and copy the sentence.

- [ ] **Step 2: Record**

Append to `spike/README.md`:

```markdown
## Finding 5 — Markdown import filter

First LibreOffice version with Markdown *import* in Writer: <version>, per
<URL> ("<quoted sentence>"). The extension refuses to start on older
versions (spec §4.5).
```

- [ ] **Step 3: Commit**

```bash
git add spike/README.md
git commit -m "chore(spike): record minimum LibreOffice version for Markdown import"
```

---

### Task 7: Write the findings back into the spec

**Files:**
- Modify: `docs/superpowers/specs/2026-09-07-librelex-it-design.md` (§4.5, §5.4, §5.5, §12, §13)

- [ ] **Step 1: Edit §12**

Under each of the five assumptions add a line `Result (YYYY-MM-DD): ...` quoting the evidence printed by the scripts (paragraph order, redline count and author, annotation range, sidebar behaviour, minimum version).

- [ ] **Step 2: Amend the design where an assumption failed**

- §5.4 item 1: if Task 2 ended in variant (b)/(c), replace the `insertDocumentFromURL` sentence with the scratch-document + `insertTransferable` recipe.
- §5.4 item 3: set the default of `redline_author` to what Task 3 showed works.
- §5.5: if footnote annotations were accepted, remove the fallback sentence; otherwise keep it and quote the exception.
- §4.5: replace "minimum version fixed during the spike" with the version from Task 6.
- §13: update the "Redline author" risk row with the outcome.

- [ ] **Step 3: Self-check and commit**

Run: `grep -n "fixed in the spike\|fixed during the spike\|to be fixed" docs/superpowers/specs/2026-09-07-librelex-it-design.md`
Expected: no output (every deferred item is now resolved).

```bash
git add docs/superpowers/specs/2026-09-07-librelex-it-design.md
git commit -m "docs(spec): record Phase 0 spike findings"
```
