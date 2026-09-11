# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""librelex-dev: run the M1 pipelines from a terminal with an in-memory document."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path

from librelex_core import protocol as p
from librelex_core.commands.insert_norm import UnparsedReference, run_insert_norm
from librelex_core.commands.verify_document import run_verify
from librelex_core.config import Config, ConfigError, load_config
from librelex_core.document import FakeDocument
from librelex_core.mcp.client import IncompatibleServer, LegalToolsClient

ToolsFactory = Callable[[Config], LegalToolsClient]


def _default_factory(cfg: Config) -> LegalToolsClient:
    return LegalToolsClient.from_config(cfg.mcp_legal_it, timeout_s=cfg.limits.tool_timeout_s)


async def _emit(msg: object) -> None:
    if isinstance(msg, p.Status):
        print(f"[status] {msg.text}")
    elif isinstance(msg, p.Progress):
        print(f"[progress] {msg.done}/{msg.total}")


async def _silent(msg: object) -> None:
    """No progress output: insert-norm's stdout must be exactly the markdown."""


async def _check(cfg: Config, factory: ToolsFactory) -> int:
    async with factory(cfg) as tools:
        print(f"mcp-legal-it {tools.server_version} raggiungibile")
    return 0


async def _verify(cfg: Config, factory: ToolsFactory, path: Path) -> int:
    blocks = [b.strip() for b in path.read_text(encoding="utf-8").split("\n\n") if b.strip()]
    doc = FakeDocument(blocks, title=path.name)
    async with factory(cfg) as tools:
        summary = await run_verify(doc, tools, "document", _emit, "cli",
                                   include_footnotes=cfg.document.verify_footnotes)
    for c in doc.comments:
        first_line = c["text"].splitlines()[0]
        print(f"[commento] {c['paragraph_id']}@{c['start']}-{c['end']} "
              f"({c['anchored']}): {first_line}")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


async def _insert(cfg: Config, factory: ToolsFactory, reference: str) -> int:
    doc = FakeDocument([""])
    async with factory(cfg) as tools:
        await run_insert_norm(doc, tools, reference, _silent, "cli")
    print(doc.inserts[0]["markdown"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="librelex-dev", description="LibreLex-IT core, dev CLI")
    parser.add_argument("--config", type=Path, default=None, help="config.toml path")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check-mcp", help="handshake with mcp-legal-it")
    v = sub.add_parser("verify", help="verify the citations of a text/markdown file")
    v.add_argument("file", type=Path)
    i = sub.add_parser("insert-norm", help="print the markdown that would be inserted for a norm")
    i.add_argument("reference")
    return parser


def main(argv: list[str] | None = None, tools_factory: ToolsFactory = _default_factory) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(args.config)
        if args.cmd == "check-mcp":
            return asyncio.run(_check(cfg, tools_factory))
        if args.cmd == "verify":
            return asyncio.run(_verify(cfg, tools_factory, args.file))
        return asyncio.run(_insert(cfg, tools_factory, args.reference))
    except (ConfigError, IncompatibleServer, UnparsedReference) as e:
        print(f"errore: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # keep the CLI usable when a source is down
        print(f"errore ({type(e).__name__}): {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
