"""Can the author of the next tracked change be forced to 'LibreLex' without a restart?"""
from lo import PARAGRAPH_BREAK, new_writer_doc, prop, redlines, run_probe

NODE = "/org.openoffice.UserProfile/Data"


def profile_access(ctx, update):
    provider = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.configuration.ConfigurationProvider", ctx)
    service = ("com.sun.star.configuration.ConfigurationUpdateAccess" if update
               else "com.sun.star.configuration.ConfigurationAccess")
    return provider.createInstanceWithArguments(service, (prop("nodepath", NODE),))


def set_name(ctx, given, surname, log):
    acc = profile_access(ctx, update=True)
    try:
        acc.setPropertyValue("givenname", given)
        acc.setPropertyValue("sn", surname)
        acc.commitChanges()
    except Exception as exc:
        log("set_name FAILED:", repr(exc))
        log("node property names:", list(acc.getElementNames()))
        raise


def tracked_insert(doc, s):
    cur = doc.Text.createTextCursor()
    cur.gotoEnd(False)
    doc.RecordChanges = True
    doc.Text.insertControlCharacter(cur, PARAGRAPH_BREAK, False)
    doc.Text.insertString(cur, s, False)
    doc.RecordChanges = False


def redline_text(doc, log):
    """Best-effort getString() on each raw redline object, for readability
    only; the author is what this probe measures, not the text.
    """
    enum = doc.Redlines.createEnumeration()
    texts = []
    while enum.hasMoreElements():
        r = enum.nextElement()
        try:
            texts.append(r.getString())
        except Exception as exc:
            texts.append(f"<getString() failed: {type(exc).__name__}>")
    return texts


def probe(ctx, log):
    acc = profile_access(ctx, update=False)
    original = (acc.getPropertyValue("givenname"), acc.getPropertyValue("sn"))
    log("ORIGINAL PROFILE NAME:", original)

    doc = new_writer_doc(ctx)
    doc.Text.insertString(doc.Text.createTextCursor(), "Base.", False)

    # Probe A: is there a writable document property? (expected: no)
    try:
        doc.setPropertyValue("RedlineAuthor", "LibreLex-A")
        log("PROBE A: document property RedlineAuthor accepted")
    except Exception as e:
        log("PROBE A: no writable RedlineAuthor on the document:", type(e).__name__)

    tracked_insert(doc, "inserimento uno")
    log("AFTER PROBE A:", list(redlines(doc)))
    log("AFTER PROBE A getString():", redline_text(doc, log))

    # Probe B: temporary profile switch
    try:
        set_name(ctx, "LibreLex", "", log)
        tracked_insert(doc, "inserimento due")
        log("AFTER PROBE B:", list(redlines(doc)))
        log("AFTER PROBE B getString():", redline_text(doc, log))
    finally:
        set_name(ctx, *original, log=log)
    acc = profile_access(ctx, update=False)
    restored = (acc.getPropertyValue("givenname"), acc.getPropertyValue("sn"))
    log("RESTORED PROFILE NAME:", restored)

    tracked_insert(doc, "inserimento tre")
    rl_after_restore = list(redlines(doc))
    log("AFTER RESTORE:", rl_after_restore)
    log("AFTER RESTORE getString():", redline_text(doc, log))

    all_redlines = list(redlines(doc))
    authors = [a for (_, a, _) in all_redlines]
    a1 = authors[0] if len(authors) > 0 else "<missing>"
    a2 = authors[1] if len(authors) > 1 else "<missing>"
    a3 = authors[2] if len(authors) > 2 else "<missing>"
    log(f"AUTHORS: before={a1!r} during={a2!r} after={a3!r}")

    doc.close(True)


def main(*args):
    run_probe(probe, "s2_redline_author")


g_exportedScripts = (main,)
