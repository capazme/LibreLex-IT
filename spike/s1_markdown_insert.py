"""Does insertDocumentFromURL(FilterName=Markdown) insert AT THE CURSOR and get recorded as a redline?"""
import pathlib
import tempfile

import uno
from lo import PARAGRAPH_BREAK, new_writer_doc, paragraphs, prop, redlines, run_probe

MD = "# Titolo inserito\n\nParagrafo con **grassetto** e *corsivo*.\n\n> Citazione in blocco.\n\n- uno\n- due\n"


def _load_with_filter_fallback(load_fn, log):
    """Call load_fn(filter_name), trying FilterName "Markdown" first and
    falling back once to "Markdown (Writer)" if it raises. Shared by every
    call site that loads/inserts the Markdown fixture, so the fallback rule
    ("if FilterName 'Markdown' raises, catch, log, retry once with
    'Markdown (Writer)'") applies uniformly rather than only to the primary
    path. Returns (result_of_load_fn, filter_name_that_worked).
    """
    try:
        result = load_fn("Markdown")
        return result, "Markdown"
    except Exception as exc:
        log("FilterName 'Markdown' raised:", repr(exc))
        log("retrying with FilterName 'Markdown (Writer)'")
        result = load_fn("Markdown (Writer)")
        return result, "Markdown (Writer)"


def _insert_markdown_at_cursor(cur, log):
    """Insert MD at cur via insertDocumentFromURL, using the shared filter
    fallback. Returns the filter name that worked.
    """
    tmpdir = pathlib.Path(tempfile.mkdtemp())
    md = tmpdir / "insert.md"
    md.write_text(MD, encoding="utf-8")
    url = uno.systemPathToFileUrl(str(md))
    try:
        _, filter_used = _load_with_filter_fallback(
            lambda name: cur.insertDocumentFromURL(url, (prop("FilterName", name),)),
            log,
        )
    finally:
        md.unlink()
    return filter_used


def _load_scratch_markdown(desktop, log):
    """Load MD into a hidden scratch Writer doc via loadComponentFromURL,
    using the same shared filter fallback as the primary path. Returns
    (scratch_doc, filter_name_that_worked).
    """
    tmpdir = pathlib.Path(tempfile.mkdtemp())
    md = tmpdir / "insert.md"
    md.write_text(MD, encoding="utf-8")
    url = uno.systemPathToFileUrl(str(md))
    try:
        scratch, filter_used = _load_with_filter_fallback(
            lambda name: desktop.loadComponentFromURL(
                url, "_blank", 0, (prop("Hidden", True), prop("FilterName", name))
            ),
            log,
        )
    finally:
        md.unlink()
    return scratch, filter_used


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
    scratch, filter_used = _load_scratch_markdown(desktop, log)
    scratch_ctrl = scratch.CurrentController
    scratch_ctrl.select(scratch.Text)  # select everything
    transferable = scratch_ctrl.getTransferable()

    doc = new_writer_doc(ctx)
    text = doc.Text
    cur = text.createTextCursor()
    text.insertString(cur, "Primo paragrafo.", False)
    text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
    text.insertString(cur, "Terzo paragrafo.", False)

    # ViewCursor (com.sun.star.text.TextViewCursor) was observed to not
    # support gotoEndOfParagraph in this headless/Hidden-document setup (see
    # diagnostic below), unlike the brief's snippet assumed. Compute the
    # target range with a plain text cursor instead, then move the view
    # cursor onto that range: insertTransferable inserts at the view
    # cursor's position.
    cur.gotoStart(False)
    cur.gotoEndOfParagraph(False)
    log("DIAGNOSTIC: doc.CurrentController is None:", doc.CurrentController is None)
    vc = doc.CurrentController.ViewCursor
    log("DIAGNOSTIC: hasattr(ViewCursor, 'gotoEndOfParagraph'):", hasattr(vc, "gotoEndOfParagraph"))
    vc.gotoRange(cur, False)
    doc.RecordChanges = True
    doc.CurrentController.insertTransferable(transferable)
    doc.RecordChanges = False

    log("FILTER USED:", filter_used)
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
