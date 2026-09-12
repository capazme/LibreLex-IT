# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""librelex-dev: run the M1 pipelines from a terminal with an in-memory document."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from librelex_core import protocol as p
from librelex_core.agent.loop import AgentDeps
from librelex_core.agent.registry import ToolRegistry
from librelex_core.agent.state import DocSession
from librelex_core.commands.chat import PROFILE as CHAT_PROFILE
from librelex_core.commands.chat import run_chat
from librelex_core.commands.insert_norm import UnparsedReference, run_insert_norm
from librelex_core.commands.list_citations import run_list_citations
from librelex_core.commands.show_text import TextUnavailable, run_show_text
from librelex_core.commands.verify_document import run_verify
from librelex_core.config import Config, ConfigError, load_config
from librelex_core.document import FakeDocument
from librelex_core.llm.client import LLMClient, LLMError
from librelex_core.mcp.client import IncompatibleServer, LegalToolsClient

ToolsFactory = Callable[[Config], LegalToolsClient]
LLMFactory = Callable[[Config], Any]


def _default_factory(cfg: Config) -> LegalToolsClient:
    return LegalToolsClient.from_config(cfg.mcp_legal_it, timeout_s=cfg.limits.tool_timeout_s)


def _default_llm(cfg: Config) -> LLMClient:
    return LLMClient(cfg.llm)


async def _emit(msg: object) -> None:
    if isinstance(msg, p.Status):
        print(f"[status] {msg.text}")
    elif isinstance(msg, p.Progress):
        print(f"[progress] {msg.done}/{msg.total}")


async def _silent(msg: object) -> None:
    """No progress output: insert-norm's stdout must be exactly the markdown."""


async def _chat_emit(msg: object) -> None:
    """Stdout carries the answer only; status lines and tool notices go to stderr."""
    if isinstance(msg, p.Delta):
        print(msg.text, end="", flush=True)
    elif isinstance(msg, p.Status):
        print(f"[status] {msg.text}", file=sys.stderr)


async def _cli_consent(summary: p.ConsentSummary) -> str:
    """Consent in the dev CLI: the file was passed on the command line, so sending it is
    what the user asked for; the panel is where the real dialog of spec §8.2 lives."""
    zdr = "sì" if summary.zdr else "no"
    print(f"[consenso] {summary.chars} caratteri ({summary.scope}) verso {summary.model} su "
          f"{summary.endpoint_host}, zero-data-retention: {zdr}", file=sys.stderr)
    return "document"


async def _check(cfg: Config, factory: ToolsFactory) -> int:
    async with factory(cfg) as tools:
        contract = "sì" if tools.contract_checked else "non verificato, versione accettata"
        print(f"mcp-legal-it {tools.server_version} raggiungibile (contratto JSON: {contract})")
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


async def _list(cfg: Config, path: Path) -> int:
    blocks = [b.strip() for b in path.read_text(encoding="utf-8").split("\n\n") if b.strip()]
    doc = FakeDocument(blocks, title=path.name)
    out = await run_list_citations(doc, "document", _emit, "cli",
                                   include_footnotes=cfg.document.verify_footnotes)
    for c in out["citazioni"]:
        print(f"{c['citazione']}  [{c['tipo']}]  x{len(c['occorrenze'])}")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


async def _show(cfg: Config, factory: ToolsFactory, reference: str) -> int:
    # _silent, not _emit: show-text's stdout must start with the title (spec §7.3 item 2).
    async with factory(cfg) as tools:
        out = await run_show_text(FakeDocument(["x"]), tools, reference, _silent, "cli")
    print(out["titolo"])
    print(f"Fonte: {out['fonte']} {out['url']}".strip())
    if out["massima"]:
        print(f"Massima:\n{out['massima']}")
    print()
    print(out["testo"])
    return 0


async def _chat(cfg: Config, factory: ToolsFactory, llm_factory: LLMFactory,
                message: str, path: Path | None) -> int:
    llm = llm_factory(cfg)
    if path is not None:
        blocks = [b.strip() for b in path.read_text(encoding="utf-8").split("\n\n") if b.strip()]
        doc = FakeDocument(blocks, title=path.name)
    else:
        doc = FakeDocument([""], title="documento vuoto")
    async with factory(cfg) as tools:
        endpoint = getattr(llm, "endpoint", None)
        deps = AgentDeps(
            llm, tools, doc, ToolRegistry(await tools.tool_specs(), CHAT_PROFILE), cfg.limits,
            _cli_consent, getattr(endpoint, "host", "") or getattr(llm, "host", ""),
            getattr(llm, "model", cfg.llm.model), cfg.llm.zero_data_retention)
        outcome = await run_chat(DocSession("cli"), message, p.DocContext(title=doc.title),
                                 deps, _chat_emit, "cli")
    print()
    u = outcome.usage
    line = f"[{u.input_tokens} + {u.output_tokens} token"
    if u.cost_usd is not None:
        line += f", {u.cost_usd:.4f} USD"
    line += "]"
    if outcome.tool_calls:
        line += f" · {outcome.tool_calls} chiamate a strumenti"
    if outcome.inserted:
        line += f" · {len(outcome.inserted)} inserimenti nel documento in memoria"
    if outcome.flagged:
        line += f" · riferimenti segnalati: {', '.join(outcome.flagged)}"
    if outcome.stopped:
        line += f" · turno interrotto ({outcome.stopped})"
    print(line)
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
    lc = sub.add_parser("list", help="list the citations of a text/markdown file, no server needed")
    lc.add_argument("file", type=Path)
    st = sub.add_parser(
        "show-text", help="print the text of one citation (norm, Cassazione, Consulta)")
    st.add_argument("reference")
    ch = sub.add_parser("chat", help="one chat turn with the configured model")
    ch.add_argument("message")
    ch.add_argument("--file", type=Path, default=None,
                    help="text/markdown file used as the open document (blank-line paragraphs)")
    return parser


def main(argv: list[str] | None = None, tools_factory: ToolsFactory = _default_factory,
         llm_factory: LLMFactory = _default_llm) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(args.config)
        if args.cmd == "check-mcp":
            return asyncio.run(_check(cfg, tools_factory))
        if args.cmd == "verify":
            return asyncio.run(_verify(cfg, tools_factory, args.file))
        if args.cmd == "insert-norm":
            return asyncio.run(_insert(cfg, tools_factory, args.reference))
        if args.cmd == "list":
            return asyncio.run(_list(cfg, args.file))
        if args.cmd == "chat":
            return asyncio.run(_chat(cfg, tools_factory, llm_factory, args.message, args.file))
        return asyncio.run(_show(cfg, tools_factory, args.reference))
    except (ConfigError, IncompatibleServer, UnparsedReference, TextUnavailable, LLMError) as e:
        print(f"errore: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # keep the CLI usable when a source is down
        print(f"errore ({type(e).__name__}): {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
