"""Anchor a Writer comment on a character range; try the same inside a footnote."""
from lo import new_writer_doc, run_probe

BODY = "Come previsto dall'art. 2043 c.c., il danno va risarcito."
TARGET = "art. 2043 c.c."
FOOTNOTE_TEXT = "Cfr. Cass. sez. III n. 12345/2024."
FOOTNOTE_TARGET = "Cass. sez. III n. 12345/2024"


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
    text.insertTextContent(cur, ann, True)   # absorb=True -> attach to the range


def dump_fields(doc, log, label):
    log(f"--- {label} ---")
    enum = doc.TextFields.createEnumeration()
    count = 0
    while enum.hasMoreElements():
        f = enum.nextElement()
        if not f.supportsService("com.sun.star.text.TextField.Annotation"):
            continue
        count += 1
        try:
            anchor_str = f.Anchor.getString()
        except Exception as e:
            anchor_str = f"<no Anchor: {type(e).__name__}: {e}>"

        has_text_range = hasattr(f, "TextRange")
        if has_text_range:
            try:
                rng = f.TextRange.getString()
            except Exception as e:
                rng = f"<TextRange raised: {type(e).__name__}: {e}>"
        else:
            rng = "<no TextRange property>"

        log(f"author={f.Author!r} content={f.Content!r} anchor={anchor_str!r} range={rng!r}")

        # Design question: is a *range* (not just a point) recoverable from
        # the field when TextRange isn't usable? Try the getAnchor() method
        # too and log whatever text it exposes.
        if (not has_text_range) or rng.startswith("<TextRange raised"):
            try:
                a = f.getAnchor()
                log(f"  fallback f.getAnchor().getString() = {a.getString()!r}")
            except Exception as e:
                log(f"  fallback f.getAnchor() failed: {type(e).__name__}: {e}")

    if count == 0:
        log("(no annotation fields found)")


def probe(ctx, log):
    doc = new_writer_doc(ctx)
    text = doc.Text
    cur = text.createTextCursor()
    text.insertString(cur, BODY, False)

    # a footnote after the body sentence
    fn = None
    try:
        fn = doc.createInstance("com.sun.star.text.Footnote")
        text.insertTextContent(cur, fn, False)
        fn.setString(FOOTNOTE_TEXT)
        log("FOOTNOTE INSERT: ok, string =", repr(fn.getString()))
    except Exception as e:
        log("FOOTNOTE INSERT: FAILED ->", type(e).__name__, str(e)[:200])
        fn = None

    start = BODY.index(TARGET)
    anchor_on_range(text, start, len(TARGET), annotation(doc, "LibreLex · verifica", "commento nel corpo"))
    dump_fields(doc, log, "after body annotation")

    # Extra check (per amended contract): the body annotation must not have
    # replaced the anchored text; re-enumerate and confirm TARGET survives.
    body_text_now = text.getString()
    if TARGET in body_text_now:
        log("TARGET INTACT AFTER BODY ANNOTATION: yes ->", repr(body_text_now))
    else:
        log("TARGET INTACT AFTER BODY ANNOTATION: NO ->", repr(body_text_now))

    # inside the footnote
    if fn is not None:
        try:
            fcur = fn.createTextCursor()
            fcur.gotoStart(False)
            fcur.goRight(5, False)
            fcur.goRight(len(FOOTNOTE_TARGET), True)
            assert fcur.getString() == FOOTNOTE_TARGET, fcur.getString()
            fn.insertTextContent(fcur, annotation(doc, "LibreLex · verifica", "commento nella nota"), True)
            log("FOOTNOTE ANNOTATION: accepted")
        except Exception as e:
            log("FOOTNOTE ANNOTATION: rejected ->", type(e).__name__, str(e)[:200])
    else:
        log("FOOTNOTE ANNOTATION: skipped, footnote was not created")
    dump_fields(doc, log, "after footnote attempt")

    # fallback: annotate the footnote anchor in the body (the character right
    # after the footnote reference mark)
    if fn is not None:
        try:
            acur = fn.Anchor.getText().createTextCursorByRange(fn.Anchor)
            acur.goLeft(1, True)
            text.insertTextContent(acur, annotation(doc, "LibreLex · verifica", "commento sull'ancora della nota"), True)
            log("FALLBACK ANCHOR ANNOTATION: accepted")
        except Exception as e:
            log("FALLBACK ANCHOR ANNOTATION: rejected ->", type(e).__name__, str(e)[:200])
    else:
        log("FALLBACK ANCHOR ANNOTATION: skipped, footnote was not created")
    dump_fields(doc, log, "after anchor fallback")

    doc.close(True)


def main(*args):
    run_probe(probe, "s3_annotations")


g_exportedScripts = (main,)
