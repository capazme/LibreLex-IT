"""Does insertDocumentFromURL(FilterName=Markdown) insert AT THE CURSOR and get recorded as a redline?"""
import pathlib
import tempfile

import uno
from lo import PARAGRAPH_BREAK, new_writer_doc, paragraphs, prop, redlines, run_probe

MD = "# Titolo inserito\n\nParagrafo con **grassetto** e *corsivo*.\n\n> Citazione in blocco.\n\n- uno\n- due\n"


def _insert_markdown_at_cursor(cur, log):
    """Insert MD at cur via insertDocumentFromURL, trying FilterName "Markdown"
    first and falling back to "Markdown (Writer)" if it raises. Returns the
    filter name that worked.
    """
    tmpdir = pathlib.Path(tempfile.mkdtemp())
    md = tmpdir / "insert.md"
    md.write_text(MD, encoding="utf-8")
    url = uno.systemPathToFileUrl(str(md))
    try:
        try:
            cur.insertDocumentFromURL(url, (prop("FilterName", "Markdown"),))
            filter_used = "Markdown"
        except Exception as exc:
            log("FilterName 'Markdown' raised:", repr(exc))
            log("retrying with FilterName 'Markdown (Writer)'")
            cur.insertDocumentFromURL(url, (prop("FilterName", "Markdown (Writer)"),))
            filter_used = "Markdown (Writer)"
    finally:
        md.unlink()
    return filter_used


def _log_paragraphs(doc, log):
    for style, s in paragraphs(doc):
        log(f"{style!r:22s} | {s[:50]!r}")


def _log_redlines(doc, log):
    rl = list(redlines(doc))
    for t, a, s in rl:
        log(f"{t!r:10s} | {a!r:12s} | {s[:50]!r}")
        if s == "<no RedlineText>":
            # lo.py's redlines() swallows the RedlineText exception; re-probe
            # the raw redline object here to record the real cause instead of
            # guessing.
            _diagnose_redline_text(doc, log)
    return rl


def _diagnose_redline_text(doc, log):
    enum = doc.Redlines.createEnumeration()
    while enum.hasMoreElements():
        r = enum.nextElement()
        try:
            r.RedlineText.getString()
        except Exception as exc:
            log("  RedlineText diagnostic: exception =", repr(exc))
            log("  RedlineText diagnostic: dir(redline) =", dir(r))


def primary(ctx, log):
    log("=== PRIMARY: insertDocumentFromURL ===")
    doc = new_writer_doc(ctx)
    text = doc.Text
    cur = text.createTextCursor()
    text.insertString(cur, "Primo paragrafo.", False)
    text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
    text.insertString(cur, "Terzo paragrafo (era il secondo).", False)

    # cursor at the END of the first paragraph
    cur.gotoStart(False)
    cur.gotoEndOfParagraph(False)

    doc.RecordChanges = True
    filter_used = _insert_markdown_at_cursor(cur, log)
    doc.RecordChanges = False

    log("FILTER USED:", filter_used)
    log("--- paragraphs in order (style | text) ---")
    _log_paragraphs(doc, log)
    log("--- redlines (type | author | text) ---")
    rl = _log_redlines(doc, log)
    log("REDLINE COUNT:", len(rl))
    doc.close(True)


def variant(ctx, log):
    """Load the markdown into a hidden scratch doc, copy all, paste at the cursor while recording."""
    log("=== VARIANT: scratch doc + insertTransferable ===")
    desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
    tmpdir = pathlib.Path(tempfile.mkdtemp())
    md = tmpdir / "insert.md"
    md.write_text(MD, encoding="utf-8")
    scratch = desktop.loadComponentFromURL(
        uno.systemPathToFileUrl(str(md)), "_blank", 0,
        (prop("Hidden", True), prop("FilterName", "Markdown")))
    md.unlink()
    scratch_ctrl = scratch.CurrentController
    scratch_ctrl.select(scratch.Text)  # select everything
    transferable = scratch_ctrl.getTransferable()

    doc = new_writer_doc(ctx)
    text = doc.Text
    cur = text.createTextCursor()
    text.insertString(cur, "Primo paragrafo.", False)
    text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
    text.insertString(cur, "Terzo paragrafo.", False)

    # ViewCursor (com.sun.star.text.TextViewCursor) does not implement
    # XParagraphCursor, so gotoEndOfParagraph is not available on it as the
    # brief assumed. Compute the target range with a plain text cursor
    # instead, then move the view cursor onto that range: insertTransferable
    # inserts at the view cursor's position.
    cur.gotoStart(False)
    cur.gotoEndOfParagraph(False)
    vc = doc.CurrentController.ViewCursor
    vc.gotoRange(cur, False)
    doc.RecordChanges = True
    doc.CurrentController.insertTransferable(transferable)
    doc.RecordChanges = False

    log("--- VARIANT paragraphs ---")
    _log_paragraphs(doc, log)
    log("--- VARIANT redlines ---")
    rl = _log_redlines(doc, log)
    log("VARIANT REDLINE COUNT:", len(rl))
    scratch.close(True)
    doc.close(True)


def probe(ctx, log):
    primary(ctx, log)
    variant(ctx, log)


def main(*args):
    run_probe(probe, "s1_markdown_insert")


g_exportedScripts = (main,)
