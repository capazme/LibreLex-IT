# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Locations and process spec: config dir/file, uv binary, bundled core, bridge argv/env.

Mirrors ``librelex_core.config`` for the directory rule (spec §8.1) so both sides
agree on where ``config.toml`` lives. No UNO here: fully unit-testable.
"""
from __future__ import annotations

import os
import shutil
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

UV_CANDIDATES = [
    Path.home() / ".local" / "bin" / "uv",
    Path("/opt/homebrew/bin/uv"),
    Path("/usr/local/bin/uv"),
    Path.home() / ".cargo" / "bin" / "uv",
]

CONFIG_TEMPLATE = """\
# LibreLex-IT configuration (spec Appendix D). Keep this file private: it may hold API keys.
# Environment overrides: LIBRELEX_LLM_API_KEY, LIBRELEX_MCP_BEARER, LIBRELEX_CONFIG.

[llm]
preset = "openrouter"          # cliproxyapi | openrouter | ollama | custom
base_url = "https://openrouter.ai/api/v1"
api_key = ""                   # not needed in M1 (verify citations / insert norm use no LLM)
model = ""
zero_data_retention = true

[mcp_legal_it]
mode = "local"                 # local | remote
command = ["uvx", "--from", "git+https://github.com/capazme/mcp-legal-it@v2.14.0", "mcp-legal-it"]
remote_url = ""                # https://... (https mandatory unless localhost)
bearer = ""

[document]
redline_author = "librelex"    # librelex | user
verify_footnotes = true

[limits]
max_iterations = 12
turn_timeout_s = 180
tool_timeout_s = 60
session_token_ceiling = 400000

[logging]
enabled = false

[extension]
uv = ""                        # absolute path of uv when LibreOffice's PATH does not contain it
"""


class UvNotFound(Exception):
    """uv is not on PATH, not configured and not in the usual places."""


@dataclass(frozen=True)
class BridgeSpec:
    argv: list[str]
    env: dict[str, str]
    stderr_path: Path
    cwd: str


def config_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "LibreLex"
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", str(Path.home()))) / "LibreLex"
    return Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "librelex"


def config_path() -> Path:
    override = os.environ.get("LIBRELEX_CONFIG")
    return Path(override) if override else config_dir() / "config.toml"


def ensure_private(path: Path) -> None:
    """Directory 0700 and file 0600 (POSIX); no-op on Windows."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name != "posix":
        return
    os.chmod(path.parent, 0o700)
    if path.exists():
        os.chmod(path, 0o600)


def write_template_if_missing(path: Path | None = None) -> bool:
    """Create a commented default config.toml on first run. Returns True when written."""
    path = path or config_path()
    ensure_private(path)
    if path.exists():
        return False
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(CONFIG_TEMPLATE)
    return True


def read_config(path: Path | None = None) -> dict:
    """Best-effort read: the core validates the file, the extension only needs [extension]."""
    path = path or config_path()
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def find_uv(configured: str = "") -> str | None:
    if configured and os.access(configured, os.X_OK):
        return configured
    found = shutil.which("uv")
    if found:
        return found
    for cand in UV_CANDIDATES:
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return None


def repo_core_dir() -> Path:
    """core/ of a source checkout (extension/librelex_ext/paths.py → repo root)."""
    return Path(__file__).resolve().parents[2] / "core"


def core_dir(package_dir: Path) -> Path:
    """The core bundled in the installed .oxt, else the repo checkout (development)."""
    bundled = package_dir / "core"
    if (bundled / "pyproject.toml").exists():
        return bundled
    return repo_core_dir()


def bridge_spec(package_dir: Path, config: dict) -> BridgeSpec:
    """Fixed argv + environment for the core process (spec §5.2, §8.4)."""
    uv = find_uv(str(config.get("extension", {}).get("uv", "") or ""))
    if uv is None:
        raise UvNotFound(
            "uv non trovato: installa uv (https://docs.astral.sh/uv/) oppure indica il percorso "
            f"in [extension] uv = \"...\" nel file {config_path()}")
    core = core_dir(package_dir)
    cfg_dir = config_path().parent
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(Path(uv).parent), env.get("PATH", "")])
    env["UV_PROJECT_ENVIRONMENT"] = str(cfg_dir / "core-env")  # keep the .oxt directory pristine
    env["PYTHONUNBUFFERED"] = "1"
    argv = [uv, "run", "--frozen", "--project", str(core), "librelex-core"]
    return BridgeSpec(argv=argv, env=env, stderr_path=cfg_dir / "core-stderr.log", cwd=str(core))
