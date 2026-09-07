"""Throwaway helpers for the Phase 0 spike.

Probes run *inside* soffice's own embedded Python as a UNO macro (not
LibreOffice's bundled `Resources/python` binary, which is killed in this
environment). `spike/run.sh` concatenates this file with a probe file into a
single macro script under a private profile's `user/Scripts/python/`
directory, so a probe can call these helpers without importing this module.
"""
import os
import traceback

import uno
from com.sun.star.beans import PropertyValue
from com.sun.star.text.ControlCharacter import PARAGRAPH_BREAK  # noqa: F401  (re-exported)


def prop(name, value):
    p = PropertyValue()
    p.Name = name
    p.Value = value
    return p


def evidence_path(name):
    return os.path.join(os.environ["LIBRELEX_EVIDENCE_DIR"], name + ".txt")


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


def run_probe(fn, name):
    """Run fn(ctx, log) inside soffice, writing evidence to a file and
    always terminating the desktop so soffice exits.

    log(*parts) writes one line to the evidence file and flushes
    immediately, since headless macros have no usable stdout.
    """
    ctx = uno.getComponentContext()
    path = evidence_path(name)
    with open(path, "w", encoding="utf-8") as f:
        def log(*parts):
            f.write(" ".join(str(p) for p in parts) + "\n")
            f.flush()

        try:
            fn(ctx, log)
        except Exception:
            f.write(traceback.format_exc())
            f.flush()
        finally:
            desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
            desktop.terminate()
