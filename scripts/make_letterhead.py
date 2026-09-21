#!/usr/bin/env python3
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Build a letterhead template from an odt/docx/doc file of the firm's own (design §5.2, §5.4):

    python3 scripts/make_letterhead.py NAME SOURCE [--out DIR]

SOURCE is an odt, docx or doc file; DIR defaults to the letterhead folder the extension itself
uses (``<config dir>/modelli``). The heavy lifting (``document.make_letterhead``, run inside a
hidden Writer document) needs UNO, which this plain ``python3`` process does not have, so the
work happens in a headless LibreOffice of its own: a macro is dropped into a fresh private
profile's ``user/Scripts/python/`` (the same pattern ``tests/headless/conftest.run_probe`` and
``scripts/lo_install.py`` use) and run through a ``vnd.sun.star.script:`` URL. The profile is
removed afterwards, whatever happened.

``SOFFICE`` overrides the LibreOffice binary, as in ``scripts/dev_install.sh``.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXT_DIR = REPO / "extension"
if str(EXT_DIR) not in sys.path:
    sys.path.insert(0, str(EXT_DIR))

from librelex_ext import letterheads

SOFFICE_CANDIDATES = [
    os.environ.get("SOFFICE", ""),
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    shutil.which("soffice") or "",
    "/opt/libreoffice26.8/program/soffice",
    "/usr/lib/libreoffice/program/soffice",
]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("name", help="letterhead name shown in the Redazione panel")
    parser.add_argument("source", help="source file (odt, docx or doc)")
    parser.add_argument("--default", action="store_true", help="make this the default letterhead")
    parser.add_argument("--out", default=None,
                        help="destination folder (default: the extension's own modelli/)")
    args = parser.parse_args(argv)
    args.out = args.out or str(letterheads.templates_dir())
    return args


def macro_text(ext_dir: str) -> str:
    """The Python macro run inside headless LibreOffice: reads the source and destination
    from the environment, calls ``document.make_letterhead`` and writes the outcome to
    ``LIBRELEX_LH_RESULT`` as ``OK <path>`` or ``FAILED <traceback>``."""
    return f'''# Written by scripts/make_letterhead.py: run once, then discarded.
import os
import sys
import traceback

sys.path.insert(0, {ext_dir!r})
import uno
from librelex_ext.document import make_letterhead


def main(*args):
    ctx = uno.getComponentContext()
    source = os.environ.get("LIBRELEX_LH_SOURCE", "")
    out = os.environ.get("LIBRELEX_LH_OUT", "")
    result = os.environ.get("LIBRELEX_LH_RESULT", "")
    try:
        path = make_letterhead(ctx, source, out)
        text = "OK " + path
    except Exception:
        text = "FAILED " + traceback.format_exc()
    if result:
        with open(result, "w", encoding="utf-8") as f:
            f.write(text + "\\n")
    ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx).terminate()


g_exportedScripts = (main,)
'''


def _soffice_path() -> str:
    for candidate in SOFFICE_CANDIDATES:
        if candidate and Path(candidate).is_file():
            return candidate
    print("soffice not found: set SOFFICE=/path/to/soffice", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    args = parse_args(sys.argv[1:])
    source = Path(args.source).resolve()
    if not source.is_file():
        print(f"file non trovato: {source}", file=sys.stderr)
        sys.exit(1)
    out_path = letterheads.template_path(args.name, args.out)
    if out_path.exists():
        # The adapter refuses to overwrite too (document.make_letterhead); checking here
        # first avoids paying for a whole LibreOffice startup for a failure already known.
        print(f"modello già presente: {out_path}", file=sys.stderr)
        sys.exit(1)

    soffice = _soffice_path()
    profile = Path(tempfile.mkdtemp(prefix="librelex-make-letterhead-"))
    scripts = profile / "user" / "Scripts" / "python"
    scripts.mkdir(parents=True)
    (scripts / "librelex_make_letterhead.py").write_text(
        macro_text(str(EXT_DIR)), encoding="utf-8")
    result = profile / "result.txt"
    env = {**os.environ, "LIBRELEX_LH_SOURCE": source.as_uri(), "LIBRELEX_LH_OUT": str(out_path),
          "LIBRELEX_LH_RESULT": str(result)}
    url = "vnd.sun.star.script:librelex_make_letterhead.py$main?language=Python&location=user"
    try:
        proc = subprocess.run(
            [soffice, f"-env:UserInstallation={profile.as_uri()}", "--headless", "--norestore",
             "--nologo", url], env=env, timeout=180, check=False)
        if not result.exists():
            print(f"nessun risultato da LibreOffice (uscita {proc.returncode})", file=sys.stderr)
            sys.exit(1)
        text = result.read_text(encoding="utf-8").strip()
    finally:
        shutil.rmtree(profile, ignore_errors=True)

    if not text.startswith("OK "):
        print(text, file=sys.stderr)
        sys.exit(1)
    letterheads.register_letterhead(args.name, out_path.name, args.out)
    print(text[len("OK "):])


if __name__ == "__main__":
    main()
