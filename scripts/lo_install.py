# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Install (or remove) the LibreLex-IT .oxt from inside LibreOffice itself.

Run as a headless macro, not as a script:

    soffice --headless --norestore --nologo \\
        "vnd.sun.star.script:lo_install.py$main?language=Python&location=user"

with this file copied into ``<profile>/user/Scripts/python/`` and two environment
variables set: ``LIBRELEX_OXT`` (absolute path of the .oxt; empty to only remove) and
``LIBRELEX_INSTALL_RESULT`` (file where the outcome is written).

Why a macro: ``unopkg add`` registers a Python component through a helper soffice it
spawns and reaches over a named pipe; on this macOS setup that helper never answers
(``NoConnectException``), while the office itself registers extensions in-process, exactly
as Tools > Extension Manager does. ``scripts/dev_install.sh`` drives this file.
"""
import os
import traceback

import uno
import unohelper
from com.sun.star.task import XInteractionHandler
from com.sun.star.ucb import XCommandEnvironment

EXTENSION_ID = "org.librelex.extension"


class _ApproveAll(unohelper.Base, XInteractionHandler):
    """Answer every deployment question with its Approve continuation.

    The ExtensionManager asks "Extension X is about to be installed" (and, when an
    extension carries one, to accept the license) through an interaction request;
    with no handler the request counts as abort and addExtension fails.
    """

    def __init__(self, lines):
        self.lines = lines

    def handle(self, request):
        message = getattr(request.getRequest(), "Message", "")
        approve = uno.getTypeByName("com.sun.star.task.XInteractionApprove")
        for continuation in request.getContinuations():
            if continuation.queryInterface(approve) is not None:
                continuation.select()
                self.lines.append(f"approved: {message}")
                return
        self.lines.append(f"no Approve continuation for: {message}")


class _CommandEnvironment(unohelper.Base, XCommandEnvironment):
    """Approve prompts, no progress reporting: the caller has no UI."""

    def __init__(self, lines):
        self.handler = _ApproveAll(lines)

    def getInteractionHandler(self):
        return self.handler

    def getProgressHandler(self):
        return None


def _log(lines, text):
    lines.append(text)


def install(ctx, oxt_path, lines):
    manager = ctx.getValueByName("/singletons/com.sun.star.deployment.ExtensionManager")
    env = _CommandEnvironment(lines)
    try:
        existing = manager.getDeployedExtension("user", EXTENSION_ID, "", env)
    except Exception:
        existing = None
    if existing is not None:
        manager.removeExtension(EXTENSION_ID, existing.getName(), "user", None, env)
        _log(lines, f"removed previous {EXTENSION_ID} ({existing.getName()})")
    if not oxt_path:
        _log(lines, "no LIBRELEX_OXT given: removal only")
        return
    url = uno.systemPathToFileUrl(oxt_path)
    package = manager.addExtension(url, (), "user", None, env)
    _log(lines, f"installed {package.getIdentifier().Value} {package.getVersion()} "
                f"from {oxt_path}")
    registered = package.isRegistered(None, env)       # Optional<Ambiguous<boolean>>
    flag = registered.Value if registered.IsPresent else None
    _log(lines, "registered: " + ("unknown" if flag is None
                                  else "ambiguous" if flag.IsAmbiguous else str(flag.Value)))
    smgr = ctx.ServiceManager
    factory = smgr.createInstanceWithContext("org.librelex.extension.PanelFactory", ctx)
    _log(lines, f"PanelFactory instantiable: {factory is not None}")


def main(*args):
    ctx = uno.getComponentContext()
    lines = []
    ok = False
    try:
        install(ctx, os.environ.get("LIBRELEX_OXT", ""), lines)
        ok = True
    except Exception as e:
        lines.append(traceback.format_exc())
        cause = getattr(e, "Cause", None)          # UNO DeploymentException chains the real error
        depth = 0
        while cause is not None and depth < 5:
            lines.append(f"cause[{depth}]: {type(cause).__name__}: {getattr(cause, 'Message', cause)!r}")
            cause = getattr(cause, "Cause", None)
            depth += 1
    finally:
        result = os.environ.get("LIBRELEX_INSTALL_RESULT")
        if result:
            with open(result, "w", encoding="utf-8") as f:
                f.write(("OK\n" if ok else "FAILED\n") + "\n".join(lines) + "\n")
        desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
        desktop.terminate()


g_exportedScripts = (main,)
