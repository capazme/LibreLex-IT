# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import os
import stat
import sys
from pathlib import Path

import pytest

from librelex_ext import EXTENSION_ID, PROTOCOL_VERSION, __version__, paths

REPO = Path(__file__).resolve().parents[2]


def test_constants():
    assert __version__ == "0.4.0" and PROTOCOL_VERSION == 1
    assert EXTENSION_ID == "org.librelex.extension"


def test_config_dir_follows_the_core_rule(monkeypatch):
    monkeypatch.setattr(sys, "platform", "darwin")
    assert paths.config_dir() == Path.home() / "Library" / "Application Support" / "LibreLex"
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/tmp/xdg")
    assert paths.config_dir() == Path("/tmp/xdg/librelex")
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", "C:/Users/x/AppData/Roaming")
    assert paths.config_dir() == Path("C:/Users/x/AppData/Roaming/LibreLex")


def test_config_path_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("LIBRELEX_CONFIG", str(tmp_path / "c.toml"))
    assert paths.config_path() == tmp_path / "c.toml"


def test_template_written_once_and_private(tmp_path, monkeypatch):
    monkeypatch.delenv("LIBRELEX_CONFIG", raising=False)
    path = tmp_path / "LibreLex" / "config.toml"
    assert paths.write_template_if_missing(path) is True
    assert paths.write_template_if_missing(path) is False
    text = path.read_text(encoding="utf-8")
    assert "[mcp_legal_it]" in text and "[extension]" in text and "api_key" in text
    if os.name == "posix":
        assert stat.S_IMODE(path.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_read_config_tolerates_missing_and_broken_files(tmp_path, monkeypatch):
    monkeypatch.setenv("LIBRELEX_CONFIG", str(tmp_path / "none.toml"))
    assert paths.read_config() == {}
    broken = tmp_path / "broken.toml"
    broken.write_text("[extension\nuv = ", encoding="utf-8")
    monkeypatch.setenv("LIBRELEX_CONFIG", str(broken))
    assert paths.read_config() == {}
    good = tmp_path / "good.toml"
    good.write_text('[extension]\nuv = "/x/uv"\n', encoding="utf-8")
    monkeypatch.setenv("LIBRELEX_CONFIG", str(good))
    assert paths.read_config()["extension"]["uv"] == "/x/uv"


def test_find_uv_prefers_configured_then_path_then_candidates(tmp_path, monkeypatch):
    fake = tmp_path / "uv"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    assert paths.find_uv(str(fake)) == str(fake)
    monkeypatch.setenv("PATH", str(tmp_path))
    assert paths.find_uv("") == str(fake)
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setattr(paths, "UV_CANDIDATES", [tmp_path / "missing", fake])
    assert paths.find_uv("") == str(fake)
    monkeypatch.setattr(paths, "UV_CANDIDATES", [])
    assert paths.find_uv("") is None


def test_core_dir_prefers_bundled_then_repo(tmp_path):
    bundled = tmp_path / "pkg" / "core"
    bundled.mkdir(parents=True)
    (bundled / "pyproject.toml").write_text("[project]\n")
    assert paths.core_dir(tmp_path / "pkg") == bundled
    assert paths.core_dir(tmp_path / "elsewhere") == paths.repo_core_dir()
    assert (paths.repo_core_dir() / "pyproject.toml").exists()


def test_bridge_spec_is_a_fixed_argv_with_private_env(tmp_path, monkeypatch):
    fake = tmp_path / "uv"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("LIBRELEX_CONFIG", str(tmp_path / "config.toml"))
    spec = paths.bridge_spec(tmp_path / "nopkg", {"extension": {"uv": str(fake)}})
    core = paths.repo_core_dir()
    assert spec.argv == [str(fake), "run", "--frozen", "--no-dev", "--project", str(core),
                         "librelex-core"]   # --no-dev: no pytest/ruff on the user's first run
    assert spec.env["UV_PROJECT_ENVIRONMENT"] == str(tmp_path / "core-env")
    assert spec.env["PYTHONUNBUFFERED"] == "1"
    assert spec.env["PATH"].split(os.pathsep)[0] == str(tmp_path)
    assert spec.stderr_path == tmp_path / "core-stderr.log"
    assert spec.cwd == str(core)


def test_bridge_spec_tolerates_a_malformed_extension_entry(tmp_path, monkeypatch):
    """A hand-edited `extension = "x"` must not raise AttributeError into a UNO listener."""
    fake = tmp_path / "uv"
    fake.write_text("#!/bin/sh\n")
    fake.chmod(0o755)
    monkeypatch.setenv("LIBRELEX_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setenv("PATH", str(tmp_path))
    assert paths.bridge_spec(tmp_path, {"extension": "x"}).argv[0] == str(fake)
    assert paths.bridge_spec(tmp_path, {"extension": ["x"]}).argv[0] == str(fake)
    assert paths.bridge_spec(tmp_path, {"extension": {"uv": None}}).argv[0] == str(fake)


def test_bridge_spec_without_uv_raises_a_readable_error(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", "/nonexistent")
    monkeypatch.setattr(paths, "UV_CANDIDATES", [])
    with pytest.raises(paths.UvNotFound, match="uv non trovato"):
        paths.bridge_spec(tmp_path, {})
