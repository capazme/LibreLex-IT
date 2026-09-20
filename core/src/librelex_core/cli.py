# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""librelex-dev: run the M1 pipelines from a terminal with an in-memory document."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from librelex_core import protocol as p
from librelex_core.agent.loop import AgentDeps, TurnOutcome
from librelex_core.agent.registry import ToolRegistry
from librelex_core.agent.state import MAX_ATTACHMENT_CHARS, MAX_REFERENCE_CHARS, DocSession
from librelex_core.commands.chat import PROFILE as CHAT_PROFILE
from librelex_core.commands.chat import run_chat
from librelex_core.commands.draft import PROFILE as DRAFT_PROFILE
from librelex_core.commands.draft import draft_summary, run_draft
from librelex_core.commands.insert_norm import UnparsedReference, run_insert_norm
from librelex_core.commands.list_citations import run_list_citations
from librelex_core.commands.show_text import TextUnavailable, run_show_text
from librelex_core.commands.templates import TemplateCatalogue, TemplateNotFound
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
    if summary.scope == "reference" and summary.name:
        what = f'atto di riferimento "{summary.name}": {summary.chars} caratteri'
    elif summary.scope == "attachments" and summary.name:
        what = f'allegati "{summary.name}": {summary.chars} caratteri'
    else:
        what = f"{summary.chars} caratteri ({summary.scope})"
    print(f"[consenso] {what} verso {summary.model} su {summary.endpoint_host}, "
          f"zero-data-retention: {zdr}", file=sys.stderr)
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


async def _with_deps(
    cfg: Config, factory: ToolsFactory, llm_factory: LLMFactory, path: Path | None, profile: str,
    body: Callable[[DocSession, AgentDeps], Awaitable[list[TurnOutcome]]],
    extra_summary: Callable[[DocSession, TurnOutcome], str] | None = None,
) -> int:
    """One or more model turns against an in-memory document: build deps for `profile`, run
    the command's `body`, then print the usage/insertions summary of each turn it returns
    (shared by chat and draft; `extra_summary` extends the line, e.g. with the drafting
    state)."""
    llm = llm_factory(cfg)
    if path is not None:
        blocks = [b.strip() for b in path.read_text(encoding="utf-8").split("\n\n") if b.strip()]
        doc = FakeDocument(blocks, title=path.name)
    else:
        doc = FakeDocument([""], title="documento vuoto")
    async with factory(cfg) as tools:
        endpoint = getattr(llm, "endpoint", None)
        specs = await tools.tool_specs()
        deps = AgentDeps(
            llm, tools, doc, ToolRegistry(specs, profile), cfg.limits,
            _cli_consent, getattr(endpoint, "host", "") or getattr(llm, "host", ""),
            getattr(llm, "model", cfg.llm.model), cfg.llm.zero_data_retention,
            catalogue=TemplateCatalogue(tools), specs=specs)
        session = DocSession("cli")
        outcomes = await body(session, deps)
        for outcome in outcomes:
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
            if extra_summary is not None:
                line += extra_summary(session, outcome)
            print(line)
    return 0


async def _chat_turn(session: DocSession, deps: AgentDeps, message: str) -> list[TurnOutcome]:
    outcome = await run_chat(
        session, message, p.DocContext(title=deps.doc.title), deps, _chat_emit, "cli")
    return [outcome]


async def _templates(cfg: Config, factory: ToolsFactory, query: str | None) -> int:
    async with factory(cfg) as tools:
        out = await TemplateCatalogue(tools).list(query)
    for m in out["modelli"]:
        print(f"{m['tipo_atto']}  {m['categoria']}  {m['descrizione']}")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


async def _template(cfg: Config, factory: ToolsFactory, tipo_atto: str) -> int:
    async with factory(cfg) as tools:
        specs = await tools.tool_specs()
        info = await TemplateCatalogue(tools).info(tipo_atto, specs)
    for c in info["campi"]:
        obbligatorio = "obbligatorio" if c["obbligatorio"] else "facoltativo"
        print(f"{c['nome']}  {c['tipo']}  {obbligatorio}")
    print(json.dumps(info, ensure_ascii=False, indent=2))
    return 0


def _parse_kv(parser: argparse.ArgumentParser, pairs: list[str]) -> dict[str, str]:
    """``--campo``/``--risposta`` values ("NOME=VALORE") as a dict, split on the first "=";
    a value with no "=" is a usage error (`parser.error`, exit 2), not a silently empty one."""
    out: dict[str, str] = {}
    for item in pairs:
        if "=" not in item:
            parser.error("--campo/--risposta richiedono NOME=VALORE")
        name, _, value = item.partition("=")
        out[name.strip()] = value
    return out


def _print_draft_turn(session: DocSession, outcome: TurnOutcome) -> None:
    """Questions or the final summary of one drafting turn, printed before its usage line."""
    summary = draft_summary(session, outcome)
    if outcome.ended_by == "questions":
        for q in summary["domande"]:
            example = f" [{q['esempio']}]" if q.get("esempio") else ""
            print(f"? {q['campo']} ({q['tipo']}): {q['domanda']}{example}")
    elif outcome.ended_by == "done":
        print(summary["riepilogo"])


def _draft_extra(session: DocSession, outcome: TurnOutcome) -> str:
    """`· domande: N`, `· partizioni: N`, `· completata` appended to a turn's usage line."""
    summary = draft_summary(session, outcome)
    parts = [f"· domande: {len(summary.get('domande') or [])}",
             f"· partizioni: {len(summary.get('partizioni') or [])}",
             f"· allegati: {len(summary.get('allegati') or [])}"]
    if summary.get("completata"):
        parts.append("· completata")
    return " " + " ".join(parts)


def _attachments_from_files(files: list[Path]) -> list[dict[str, Any]]:
    """The `--allegato` files as a session attachment set (text files only, CLI-side reading:
    the LibreOffice/PDF reading of Drafting Workbench design §4.2 is the extension's)."""
    attachments: list[dict[str, Any]] = []
    for n, path in enumerate(files, start=1):
        text = path.read_text(encoding="utf-8")
        kept = text[:MAX_ATTACHMENT_CHARS]
        attachments.append({"n": n, "name": path.name, "text": kept, "chars": len(kept),
                            "kind": "text", "troncato": len(text) > MAX_ATTACHMENT_CHARS})
    return attachments


async def _draft(
    cfg: Config, factory: ToolsFactory, llm_factory: LLMFactory, path: Path | None,
    tipo_atto: str, fields: dict[str, str], note: str, riferimento: Path | None,
    risposte: dict[str, str], allegati: list[Path],
) -> int:
    """The guided drafting from the dev CLI: a `start` turn, then an `answer` turn right after
    if `--risposta` values were given (the two-turn flow of the Redazione panel, one press)."""
    reference: dict[str, Any] | None = None
    if riferimento is not None:
        text = riferimento.read_text(encoding="utf-8")
        chars = len(text)
        reference = {"name": riferimento.name, "chars": chars,
                    "text": text[:MAX_REFERENCE_CHARS], "troncato": chars > MAX_REFERENCE_CHARS}

    async def body(session: DocSession, deps: AgentDeps) -> list[TurnOutcome]:
        if reference is not None:
            session.reference = reference
        if allegati:
            session.attachments = _attachments_from_files(allegati)
        outcomes = [await run_draft(
            session, {"action": "start", "tipo_atto": tipo_atto, "fields": fields,
                     "notes": note}, deps, _chat_emit, "cli")]
        _print_draft_turn(session, outcomes[0])
        if risposte:
            outcomes.append(await run_draft(
                session, {"action": "answer", "answers": risposte}, deps, _chat_emit, "cli"))
            _print_draft_turn(session, outcomes[-1])
        return outcomes

    return await _with_deps(cfg, factory, llm_factory, path, DRAFT_PROFILE, body, _draft_extra)


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
    tpls = sub.add_parser("templates", help="list the act templates catalogue")
    tpls.add_argument("query", nargs="?", default=None)
    tpl = sub.add_parser("template", help="details of one act template")
    tpl.add_argument("tipo_atto")
    dr = sub.add_parser("draft", help="a guided drafting turn (start, then answer if given)")
    dr.add_argument("--tipo", dest="tipo_atto", required=True, help="tipo_atto of the template")
    dr.add_argument("--campo", action="append", default=[], metavar="NOME=VALORE",
                    help="a template field, repeatable")
    dr.add_argument("--note", default="", help="free-text notes for the drafting")
    dr.add_argument("--riferimento", type=Path, default=None,
                    help="a UTF-8 text file used as the reference act")
    dr.add_argument("--risposta", action="append", default=[], metavar="CAMPO=VALORE",
                    help="an answer to a question the model asked, repeatable")
    dr.add_argument("--allegato", action="append", default=[], type=Path, metavar="FILE",
                    help="a UTF-8 text file used as a case attachment (document facts), "
                        "repeatable")
    dr.add_argument("--file", type=Path, default=None,
                    help="text/markdown file used as the open document (blank-line paragraphs)")
    return parser


def main(argv: list[str] | None = None, tools_factory: ToolsFactory = _default_factory,
         llm_factory: LLMFactory = _default_llm) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
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
            return asyncio.run(_with_deps(
                cfg, tools_factory, llm_factory, args.file, CHAT_PROFILE,
                lambda s, d: _chat_turn(s, d, args.message)))
        if args.cmd == "templates":
            return asyncio.run(_templates(cfg, tools_factory, args.query))
        if args.cmd == "template":
            return asyncio.run(_template(cfg, tools_factory, args.tipo_atto))
        if args.cmd == "draft":
            return asyncio.run(_draft(
                cfg, tools_factory, llm_factory, args.file, args.tipo_atto,
                _parse_kv(parser, args.campo), args.note, args.riferimento,
                _parse_kv(parser, args.risposta), args.allegato))
        return asyncio.run(_show(cfg, tools_factory, args.reference))
    except (ConfigError, IncompatibleServer, UnparsedReference, TextUnavailable, LLMError,
            TemplateNotFound) as e:
        print(f"errore: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # keep the CLI usable when a source is down
        print(f"errore ({type(e).__name__}): {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
