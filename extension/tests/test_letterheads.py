# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_ext import letterheads


def test_folder_follows_the_config_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRELEX_CONFIG", str(tmp_path / "cfg" / "config.toml"))
    assert letterheads.templates_dir() == tmp_path / "cfg" / "modelli"
    assert letterheads.slug("SAPG Legal") == "SAPG Legal"
    assert letterheads.slug(" Carta / intestata: 2025 ") == "Carta intestata 2025"
    assert letterheads.slug("///") == "modello"
    assert letterheads.template_path("SAPG Legal", tmp_path) == tmp_path / "SAPG Legal.ott"


def test_index_round_trip_listing_and_choice(tmp_path):
    assert letterheads.load_index(tmp_path) == {"templates": [], "last": None}
    (tmp_path / "SAPG Legal.ott").write_bytes(b"x")
    (tmp_path / "Vecchia.ott").write_bytes(b"x")
    letterheads.register_letterhead("SAPG Legal", "SAPG Legal.ott", tmp_path, default=True)
    letterheads.register_letterhead("Manca", "manca.ott", tmp_path)
    entries = letterheads.list_letterheads(tmp_path)
    assert [e["name"] for e in entries] == ["SAPG Legal", "Vecchia"]   # index first, strays after
    assert entries[0]["default"] is True and entries[0]["path"] == str(tmp_path / "SAPG Legal.ott")
    assert entries[1] == {"name": "Vecchia", "path": str(tmp_path / "Vecchia.ott"),
                          "default": False}
    index = letterheads.load_index(tmp_path)
    assert letterheads.initial_choice(entries, index) == "SAPG Legal"
    letterheads.remember_choice("Vecchia", tmp_path)
    assert letterheads.initial_choice(entries, letterheads.load_index(tmp_path)) == "Vecchia"
    letterheads.remember_choice(None, tmp_path)
    assert letterheads.load_index(tmp_path)["last"] is None
    letterheads.register_letterhead("SAPG Legal", "sapg2.ott", tmp_path)   # same name: updated
    assert [t["file"] for t in letterheads.load_index(tmp_path)["templates"]] == [
        "sapg2.ott", "manca.ott"]
    (tmp_path / "modelli.json").write_text("{not json", encoding="utf-8")
    assert letterheads.load_index(tmp_path) == {"templates": [], "last": None}
