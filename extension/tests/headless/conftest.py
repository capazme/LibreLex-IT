# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Run test probes as Python macros inside `soffice --headless` (spec §9.1 item 2, §9.2).

Why macros: LibreOffice's bundled python binary and unopkg's helper are SIGKILLed when
launched from the automation harness on this Mac, but soffice itself runs and executes
`vnd.sun.star.script:` URLs. Each probe gets a fresh private profile; the macro puts the
repo's `extension/` on sys.path, imports `librelex_ext.document`, builds a fixture document
in memory, and writes a JSON evidence file that pytest reads back.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import textwrap
from pathlib import Path

import pytest

EXT_DIR = Path(__file__).resolve().parents[2]
CANDIDATES = [
    os.environ.get("SOFFICE", ""),
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    shutil.which("soffice") or "",
    "/opt/libreoffice26.8/program/soffice",
    "/usr/lib/libreoffice/program/soffice",
]

PREAMBLE = '''
import json, os, sys, traceback
sys.path.insert(0, {ext_dir!r})
import uno
from com.sun.star.beans import PropertyValue
from com.sun.star.text.ControlCharacter import PARAGRAPH_BREAK
from librelex_ext.document import (
    DocumentActionError, DocumentAdapter, has_markdown_filter, lo_version)

EVIDENCE = {evidence!r}


def prop(name, value):
    p = PropertyValue()
    p.Name, p.Value = name, value
    return p


def new_doc(ctx):
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    return desktop.loadComponentFromURL(
        "private:factory/swriter", "_blank", 0, (prop("Hidden", True),))


def fixture_doc(ctx):
    """p:0 with two citations; p:1 with a footnote; a 2x2 table; p:2."""
    doc = new_doc(ctx)
    text = doc.Text
    cur = text.createTextCursor()
    text.insertString(cur, "Primo paragrafo con art. 2043 c.c. e Cass. n. 12345/2024.", False)
    text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
    text.insertString(cur, "Secondo paragrafo", False)
    fn = doc.createInstance("com.sun.star.text.Footnote")
    text.insertTextContent(cur, fn, False)
    fn.setString("Cfr. Cass. sez. III n. 12345/2024.")
    text.insertString(cur, " con nota.", False)
    text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
    table = doc.createInstance("com.sun.star.text.TextTable")
    table.initialize(2, 2)
    text.insertTextContent(cur, table, False)
    table.getCellByName("A1").setString("cella A1")
    table.getCellByName("B2").setString("cella B2 con art. 1 c.p.")
    cur.gotoEnd(False)
    text.insertString(cur, "Terzo paragrafo.", False)
    return doc


def paragraph_texts(text):
    out = []
    enum = text.createEnumeration()
    while enum.hasMoreElements():
        el = enum.nextElement()
        if el.supportsService("com.sun.star.text.Paragraph"):
            out.append([el.ParaStyleName, el.getString()])
        else:
            out.append(["<table>", ""])
    return out


def redlines(doc):
    out = []
    enum = doc.Redlines.createEnumeration()
    while enum.hasMoreElements():
        r = enum.nextElement()
        out.append([r.RedlineType, r.RedlineAuthor])
    return out


def annotations(doc):
    out = []
    enum = doc.TextFields.createEnumeration()
    while enum.hasMoreElements():
        f = enum.nextElement()
        if f.supportsService("com.sun.star.text.TextField.Annotation"):
            anchor = f.getAnchor()
            out.append({{"author": f.Author, "content": f.Content,
                         "anchor": anchor.getString() if anchor is not None else None}})
    return out
'''

RUNNER = '''

def main(*args):
    ctx = uno.getComponentContext()
    out = {}
    try:
        probe(ctx, out)
    except Exception:
        out["traceback"] = traceback.format_exc()
    finally:
        with open(EVIDENCE, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, default=str)
        ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx).terminate()


g_exportedScripts = (main,)
'''


def soffice_path() -> str | None:
    for c in CANDIDATES:
        if c and Path(c).is_file():
            return c
    return None


@pytest.fixture(scope="session")
def soffice() -> str:
    path = soffice_path()
    if path is None:
        pytest.skip("LibreOffice (soffice) not found; set SOFFICE to its path")
    return path


def run_probe(soffice: str, name: str, body: str, timeout: int = 120,
              env: dict[str, str] | None = None) -> dict:
    profile = Path(tempfile.mkdtemp(prefix="librelex-lo-"))
    scripts = profile / "user" / "Scripts" / "python"
    scripts.mkdir(parents=True)
    evidence = profile / f"{name}.json"
    macro = (PREAMBLE.format(ext_dir=str(EXT_DIR), evidence=str(evidence))
             + textwrap.dedent(body) + RUNNER)
    (scripts / f"{name}.py").write_text(macro, encoding="utf-8")
    url = f"vnd.sun.star.script:{name}.py$main?language=Python&location=user"
    proc = subprocess.Popen(
        [soffice, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--norestore",
         "--nologo", url], env={**os.environ, **(env or {})})
    try:
        proc.wait(timeout)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
        pytest.fail(f"soffice did not finish probe {name} within {timeout}s")
    if not evidence.exists():
        pytest.fail(f"probe {name} wrote no evidence (soffice exit code {proc.returncode})")
    data = json.loads(evidence.read_text(encoding="utf-8"))
    if "traceback" in data:
        pytest.fail(f"probe {name} raised:\n{data['traceback']}")
    return data
