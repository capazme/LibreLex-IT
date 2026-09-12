# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Install the built .oxt into a private profile through scripts/lo_install.py (the same
in-process path as Tools > Extension Manager) and check that a fresh LibreOffice on that
profile finds the component and the sidebar registrations (spec §9.1 item 2)."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.headless

REPO = Path(__file__).resolve().parents[3]
INSTALL_MACRO = REPO / "scripts" / "lo_install.py"

# Second LibreOffice on the installed profile: does it see the component and the .xcu contributions?
CHECK_MACRO = """
import json, os, uno
from com.sun.star.beans import PropertyValue

CONFIG = "com.sun.star.configuration.ConfigurationProvider"
ACCESS = "com.sun.star.configuration.ConfigurationAccess"


def _names(ctx, nodepath):
    prov = ctx.ServiceManager.createInstanceWithContext(CONFIG, ctx)
    p = PropertyValue()
    p.Name, p.Value = "nodepath", nodepath
    return list(prov.createInstanceWithArguments(ACCESS, (p,)).getElementNames())


def main(*args):
    ctx = uno.getComponentContext()
    smgr = ctx.ServiceManager
    out = {}
    out["factory"] = smgr.createInstanceWithContext(
        "org.librelex.extension.PanelFactory", ctx) is not None
    out["decks"] = _names(ctx, "/org.openoffice.Office.UI.Sidebar/Content/DeckList")
    out["panels"] = _names(ctx, "/org.openoffice.Office.UI.Sidebar/Content/PanelList")
    out["factories"] = _names(
        ctx, "/org.openoffice.Office.UI.Factories/Registered/UIElementFactories")
    with open(os.environ["LIBRELEX_CHECK_RESULT"], "w", encoding="utf-8") as f:
        json.dump(out, f)
    smgr.createInstanceWithContext("com.sun.star.frame.Desktop", ctx).terminate()


g_exportedScripts = (main,)
"""


def _run_headless(soffice: str, profile: Path, script_name: str, env: dict, timeout=180):
    proc = subprocess.Popen(
        [soffice, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--norestore",
         "--nologo", f"vnd.sun.star.script:{script_name}$main?language=Python&location=user"],
        env={**os.environ, **env}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        proc.wait(timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail(f"soffice did not finish {script_name} within {timeout}s")


def test_oxt_installs_and_registers_in_a_private_profile(soffice, tmp_path):
    build = [sys.executable, str(REPO / "scripts" / "build_oxt.py"), "--out", str(tmp_path)]
    out = subprocess.run(build, capture_output=True, text=True, check=True).stdout
    oxt = Path(out.strip().splitlines()[-1])
    profile = Path(tempfile.mkdtemp(prefix="librelex-install-"))
    scripts = profile / "user" / "Scripts" / "python"
    scripts.mkdir(parents=True)
    shutil.copy(INSTALL_MACRO, scripts / "librelex_install.py")
    result = profile / "install.txt"
    _run_headless(soffice, profile, "librelex_install.py",
                  {"LIBRELEX_OXT": str(oxt), "LIBRELEX_INSTALL_RESULT": str(result)})
    text = result.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "OK", text
    assert "registered: True" in text and "PanelFactory instantiable: True" in text

    # A second LibreOffice on the same profile (the user's next start) must see the
    # component and the Sidebar/Factories configuration the .xcu files contribute.
    check = profile / "check.json"
    (scripts / "librelex_check.py").write_text(CHECK_MACRO, encoding="utf-8")
    _run_headless(soffice, profile, "librelex_check.py", {"LIBRELEX_CHECK_RESULT": str(check)})
    data = json.loads(check.read_text(encoding="utf-8"))
    assert data["factory"] is True
    assert "LibreLexDeck" in data["decks"]
    assert {"LibreLexActionsPanel", "LibreLexCitationsPanel", "LibreLexAnswersPanel"} <= set(
        data["panels"])
    assert "LibreLexPanelFactory" in data["factories"]

    # --remove path: the macro without LIBRELEX_OXT uninstalls
    _run_headless(soffice, profile, "librelex_install.py",
                  {"LIBRELEX_OXT": "", "LIBRELEX_INSTALL_RESULT": str(result)})
    text = result.read_text(encoding="utf-8")
    assert text.splitlines()[0] == "OK" and "removal only" in text and "removed previous" in text
    shutil.rmtree(profile, ignore_errors=True)

