# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load():
    spec = importlib.util.spec_from_file_location("make_letterhead",
                                                  REPO / "scripts" / "make_letterhead.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_letterhead"] = module
    spec.loader.exec_module(module)
    return module


def test_arguments_and_macro(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRELEX_CONFIG", str(tmp_path / "config.toml"))
    m = _load()
    args = m.parse_args(["SAPG Legal", "carta.docx"])
    assert args.name == "SAPG Legal" and args.source == "carta.docx"
    assert Path(args.out) == tmp_path / "modelli"
    args = m.parse_args(["X", "c.odt", "--out", str(tmp_path / "m")])
    assert Path(args.out) == tmp_path / "m"
    macro = m.macro_text(str(REPO / "extension"))
    assert "from librelex_ext.document import make_letterhead" in macro
    assert "LIBRELEX_LH_SOURCE" in macro and "LIBRELEX_LH_RESULT" in macro
    assert "g_exportedScripts = (main,)" in macro
