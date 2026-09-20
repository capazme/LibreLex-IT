# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""The letterhead folder and its index (design §5.2): templates live under
``<config dir>/modelli/`` as ``.ott`` files, never overwritten; ``modelli.json`` names them,
marks a default and remembers the lawyer's last choice. Pure: no UNO here.
"""
from __future__ import annotations

import json
from pathlib import Path

from librelex_ext import paths

INDEX_NAME = "modelli.json"
NONE_LABEL = "Nessuna (impaginazione del documento)"


def _empty_index() -> dict:
    return {"templates": [], "last": None}


def templates_dir() -> Path:
    return paths.config_path().parent / "modelli"


def _folder(folder: Path | str | None) -> Path:
    return Path(folder) if folder else templates_dir()


def slug(name: str) -> str:
    """A filesystem-safe name: letters, digits, spaces, ``-`` and ``_`` kept, the rest
    dropped, runs of spaces collapsed, stripped; ``"modello"`` when nothing is left.
    """
    kept = "".join(ch for ch in name if ch.isalnum() or ch in " -_")
    collapsed = " ".join(kept.split(" "))
    while "  " in collapsed:
        collapsed = collapsed.replace("  ", " ")
    return collapsed.strip() or "modello"


def template_path(name: str, folder: Path | str | None = None) -> Path:
    return _folder(folder) / (slug(name) + ".ott")


def load_index(folder: Path | str | None = None) -> dict:
    path = _folder(folder) / INDEX_NAME
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_index()
    if not isinstance(data, dict):
        return _empty_index()
    templates = data.get("templates")
    templates = templates if isinstance(templates, list) else []
    last = data.get("last")
    last = last if isinstance(last, str) else None
    return {"templates": templates, "last": last}


def save_index(index: dict, folder: Path | str | None = None) -> None:
    path = _folder(folder) / INDEX_NAME
    paths.ensure_private(path)
    path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    paths.ensure_private(path)


def list_letterheads(folder: Path | str | None = None) -> list[dict]:
    """Index entries whose file exists, in index order, then the stray ``.ott`` files."""
    folder = _folder(folder)
    index = load_index(folder)
    named_files = {t.get("file") for t in index["templates"]}
    entries = []
    for t in index["templates"]:
        name, file = t.get("name"), t.get("file")
        if not name or not file or not (folder / file).exists():
            continue
        entries.append(
            {"name": name, "path": str(folder / file), "default": bool(t.get("default"))})
    strays = sorted(
        (p for p in folder.glob("*.ott") if p.name not in named_files), key=lambda p: p.name)
    entries.extend({"name": p.stem, "path": str(p), "default": False} for p in strays)
    return entries


def register_letterhead(name: str, filename: str, folder: Path | str | None = None,
                        default: bool = False) -> dict:
    folder = _folder(folder)
    index = load_index(folder)
    entry = next((t for t in index["templates"] if t.get("name") == name), None)
    if entry is None:
        entry = {"name": name, "file": filename, "default": default}
        index["templates"].append(entry)
    else:
        entry["file"] = filename
    save_index(index, folder)
    return entry


def remember_choice(name: str | None, folder: Path | str | None = None) -> None:
    folder = _folder(folder)
    index = load_index(folder)
    index["last"] = name
    save_index(index, folder)


def initial_choice(entries: list[dict], index: dict) -> str | None:
    last = index.get("last")
    if last is not None and any(e["name"] == last for e in entries):
        return last
    return next((e["name"] for e in entries if e.get("default")), None)
