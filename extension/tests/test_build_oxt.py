# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def test_build_oxt_contains_extension_and_core(tmp_path):
    proc = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "build_oxt.py"), "--out", str(tmp_path)],
        capture_output=True, text=True, check=True)
    oxt = Path(proc.stdout.strip().splitlines()[-1])
    assert oxt.name == "LibreLex-IT-0.3.0.oxt" and oxt.exists()
    names = set(zipfile.ZipFile(oxt).namelist())
    for required in ("META-INF/manifest.xml", "description.xml", "Sidebar.xcu", "Factories.xcu",
                     "dialogs/panel.xdl", "librelex_component.py", "librelex_ext/__init__.py",
                     "librelex_ext/panel.py", "librelex_ext/document.py",
                     "core/pyproject.toml", "core/uv.lock", "core/README.md",
                     "core/src/librelex_core/main.py", "core/src/librelex_core/protocol.py"):
        assert required in names, required
    assert not any("__pycache__" in n or n.startswith("tests/") or "/tests/" in n
                   or n.endswith(".pyc") for n in names)
    assert not any(n.startswith("core/.venv") or n == "pyproject.toml" for n in names)
    digest = hashlib.sha256(oxt.read_bytes()).hexdigest()
    assert (tmp_path / "LibreLex-IT-0.3.0.oxt.sha256").read_text().split()[0] == digest
