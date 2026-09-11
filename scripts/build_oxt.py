#!/usr/bin/env python3
# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Build dist/LibreLex-IT-<version>.oxt: the extension tree plus the core/ project (spec §9.3).

Stdlib only. The version is read from extension/librelex_ext/__init__.py and must match
description.xml. Prints the .oxt path as the last line.
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
EXT = REPO / "extension"
CORE = REPO / "core"

EXT_EXCLUDE_DIRS = {"tests", "__pycache__", ".venv", ".pytest_cache", ".ruff_cache"}
EXT_EXCLUDE_FILES = {"pyproject.toml", "uv.lock", ".python-version", ".DS_Store"}
CORE_FILES = ["pyproject.toml", "uv.lock", "README.md"]


def version() -> str:
    init = (EXT / "librelex_ext" / "__init__.py").read_text(encoding="utf-8")
    v = re.search(r'^__version__ = "([^"]+)"', init, re.M).group(1)
    desc = (EXT / "description.xml").read_text(encoding="utf-8")
    dv = re.search(r'<version value="([^"]+)"', desc).group(1)
    if v != dv:
        sys.exit(f"version mismatch: __init__.py {v} vs description.xml {dv}")
    return v


def ext_files():
    for p in sorted(EXT.rglob("*")):
        rel = p.relative_to(EXT)
        if (not p.is_file() or set(rel.parts[:-1]) & EXT_EXCLUDE_DIRS
                or rel.name in EXT_EXCLUDE_FILES):
            continue
        if rel.suffix == ".pyc":
            continue
        yield p, rel.as_posix()


def core_files():
    for name in CORE_FILES:
        yield CORE / name, f"core/{name}"
    for p in sorted((CORE / "src").rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        yield p, "core/" + p.relative_to(CORE).as_posix()


def build(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    oxt = out_dir / f"LibreLex-IT-{version()}.oxt"
    with zipfile.ZipFile(oxt, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in list(ext_files()) + list(core_files()):
            z.write(src, arc)
    digest = hashlib.sha256(oxt.read_bytes()).hexdigest()
    (out_dir / (oxt.name + ".sha256")).write_text(f"{digest}  {oxt.name}\n", encoding="utf-8")
    return oxt


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the LibreLex-IT .oxt")
    ap.add_argument("--out", type=Path, default=REPO / "dist")
    args = ap.parse_args()
    oxt = build(args.out)
    print(f"sha256: {(args.out / (oxt.name + '.sha256')).read_text().split()[0]}")
    print(oxt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
