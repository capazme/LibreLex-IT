# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Verification of canonical citations through mcp-legal-it's verifica_citazioni (spec §7.1)."""
from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from librelex_core.citations.extractor import Citation
from librelex_core.mcp.client import LegalToolsClient, ToolError

BATCH_SIZE = 20
CONCURRENCY = 2
RETRYABLE = "non verificata"


@dataclass
class Verdict:
    canonical: str
    verdetto: str
    nota: str
    tipo: str = ""


@dataclass
class VerificationReport:
    verdicts: dict[str, Verdict] = field(default_factory=dict)
    unverified_courts: list[str] = field(default_factory=list)
    unparsed: list[str] = field(default_factory=list)


async def _verify_batch(batch: list[str], tools: LegalToolsClient) -> dict[str, Verdict]:
    try:
        raw = await tools.call("verifica_citazioni", citazioni="\n".join(batch), archivio="tutti",
                               formato="json")
        data = json.loads(raw)
        rows = data["citazioni"]
    except (ToolError, json.JSONDecodeError, KeyError, TypeError) as e:
        return {ref: Verdict(ref, RETRYABLE, f"risposta non valida: {e}") for ref in batch}
    out: dict[str, Verdict] = {}
    for ref, row in zip(batch, rows, strict=False):
        out[ref] = Verdict(ref, row.get("verdetto", RETRYABLE), row.get("nota", ""),
                           row.get("tipo", ""))
    for ref in batch[len(rows):]:
        out[ref] = Verdict(ref, RETRYABLE, "riferimento non restituito dal server")
    return out


async def verify_citations(
    canonicals: list[str], tools: LegalToolsClient,
    progress: Callable[[int, int], Awaitable[None]] | None = None,
    batch_size: int = BATCH_SIZE, concurrency: int = CONCURRENCY,
) -> dict[str, Verdict]:
    refs = list(dict.fromkeys(canonicals))  # dedupe, keep order
    total = len(refs)
    verdicts: dict[str, Verdict] = {}
    sem = asyncio.Semaphore(concurrency)
    last_reported = -1

    async def report(done: int) -> None:
        nonlocal last_reported
        if progress and done != last_reported:
            last_reported = done
            await progress(done, total)

    async def run(batch: list[str]) -> None:
        async with sem:
            verdicts.update(await _verify_batch(batch, tools))
        await report(min(len(verdicts), total))

    batches = [refs[i:i + batch_size] for i in range(0, total, batch_size)]
    await asyncio.gather(*(run(b) for b in batches))

    retry = [r for r in refs if verdicts[r].verdetto == RETRYABLE]
    for i in range(0, len(retry), batch_size):
        verdicts.update(await _verify_batch(retry[i:i + batch_size], tools))
    if total:
        await report(total)
    return {r: verdicts[r] for r in refs}


async def verify(
    citations: list[Citation], tools: LegalToolsClient,
    progress: Callable[[int, int], Awaitable[None]] | None = None,
) -> VerificationReport:
    report = VerificationReport()
    to_verify: list[str] = []
    for c in citations:
        if c.canonical is None:
            if c.display_text not in report.unparsed:
                report.unparsed.append(c.display_text)
        elif not c.verifiable:
            if c.canonical not in report.unverified_courts:
                report.unverified_courts.append(c.canonical)
        elif c.canonical not in to_verify:
            to_verify.append(c.canonical)
    report.verdicts = (
        await verify_citations(to_verify, tools, progress=progress) if to_verify else {}
    )
    return report
