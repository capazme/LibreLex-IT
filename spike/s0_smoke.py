from lo import prop, new_writer_doc, paragraphs, run_probe


def probe(ctx, log):
    doc = new_writer_doc(ctx)
    doc.Text.insertString(doc.Text.createTextCursor(), "ciao", False)
    log("PARAGRAPHS:", list(paragraphs(doc)))

    config_provider = ctx.ServiceManager.createInstanceWithContext(
        "com.sun.star.configuration.ConfigurationProvider", ctx)
    config_access = config_provider.createInstanceWithArguments(
        "com.sun.star.configuration.ConfigurationAccess",
        (prop("nodepath", "/org.openoffice.Setup/Product"),))
    log("LO VERSION:", config_access.getByName("ooSetupVersionAboutBox"))

    doc.close(True)


def main(*args):
    run_probe(probe, "s0_smoke")


g_exportedScripts = (main,)
