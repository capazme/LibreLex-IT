# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Thin client over fastmcp for mcp-legal-it (spec §4.1, §6.2, §10)."""
from __future__ import annotations

import asyncio
import os
import re
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport

from librelex_core.config import McpConfig

MIN_MCP_LEGAL_IT_VERSION = "2.14.0"

ALLOWLIST: frozenset[str] = frozenset({
    # norms
    "cite_law", "fetch_act_index", "fetch_full_act", "verifica_citazioni", "cerca_brocardi",
    # case law
    "cerca_giurisprudenza", "cerca_giurisprudenza_unificata", "leggi_sentenza",
    "giurisprudenza_su_norma", "orientamento_su_norma", "cerca_giurisprudenza_amministrativa",
    "leggi_provvedimento_amm", "cerca_giurisprudenza_cgue", "leggi_sentenza_cgue",
    "cerca_pronuncia_costituzionale", "leggi_pronuncia_costituzionale",
    # act templates
    "genera_modello_atto", "lista_categorie_atti",
    # calculators
    "interessi_legali", "interessi_mora", "rivalutazione_monetaria", "contributo_unificato",
    "parcella_avvocato_civile", "termini_processuali_civili", "scadenza_processuale",
    "calcolo_tempo_trascorso",
})


class ToolError(Exception):
    def __init__(self, name: str, message: str):
        super().__init__(f"{name}: {message}")
        self.name, self.message = name, message


class IncompatibleServer(Exception):
    def __init__(self, found: str, required: str):
        super().__init__(f"mcp-legal-it {found or '?'} found, {required} or newer required")
        self.found, self.required = found, required


def _version_tuple(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v.split("+")[0])
    return tuple(int(n) for n in nums[:3]) or (0,)


class LegalToolsClient:
    """Connects to mcp-legal-it over fastmcp and enforces a minimum server version.

    ``min_version`` defaults to ``MIN_MCP_LEGAL_IT_VERSION`` but can be relaxed
    via the ``LIBRELEX_MIN_MCP_VERSION`` environment variable (see
    ``from_config``), which is needed while the dev CLI's live smoke test
    still targets an untagged mcp-legal-it checkout.
    """

    def __init__(self, transport: Any, *, min_version: str = MIN_MCP_LEGAL_IT_VERSION,
                 max_concurrency: int = 4, timeout_s: float = 60.0):
        self.transport = transport
        self.min_version = min_version
        self.timeout_s = timeout_s
        self._sem = asyncio.Semaphore(max_concurrency)
        self._client: Client | None = None
        self.server_version: str = ""

    @classmethod
    def from_config(cls, cfg: McpConfig, timeout_s: float = 60.0) -> LegalToolsClient:
        """Build a client from ``McpConfig``.

        The minimum accepted server version can be overridden with the
        ``LIBRELEX_MIN_MCP_VERSION`` environment variable, falling back to
        ``MIN_MCP_LEGAL_IT_VERSION`` when unset. This lets the dev CLI's live
        smoke test talk to an mcp-legal-it checkout that still declares an
        older version while the JSON-contract release is not tagged yet.
        """
        min_version = os.environ.get("LIBRELEX_MIN_MCP_VERSION", MIN_MCP_LEGAL_IT_VERSION)
        if cfg.mode == "remote":
            headers = {"Authorization": f"Bearer {cfg.bearer}"} if cfg.bearer else {}
            transport: Any = StreamableHttpTransport(cfg.remote_url, headers=headers)
        else:
            transport = StdioTransport(cfg.command[0], cfg.command[1:], env={
                "LEGAL_PROFILE": "full", "MCP_TRANSPORT": "stdio",
                # The server's CLI banner and "Starting MCP server" log line otherwise reach
                # the extension's stderr log on every start.
                "FASTMCP_SHOW_CLI_BANNER": "false", "FASTMCP_LOG_LEVEL": "WARNING",
            })
        return cls(transport, min_version=min_version, timeout_s=timeout_s)

    async def __aenter__(self) -> LegalToolsClient:
        self._client = Client(self.transport, timeout=self.timeout_s)
        await self._client.__aenter__()
        info = self._client.initialize_result.serverInfo
        self.server_version = info.version or ""
        if _version_tuple(self.server_version) < _version_tuple(self.min_version):
            await self._client.__aexit__(None, None, None)
            self._client = None
            raise IncompatibleServer(self.server_version, self.min_version)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None:
            await self._client.__aexit__(*exc)
            self._client = None

    async def call(self, name: str, **args: Any) -> str:
        """Call a tool and return its text; tool failures become ToolError."""
        if self._client is None:
            raise RuntimeError("LegalToolsClient used outside 'async with'")
        async with self._sem:
            try:
                result = await self._client.call_tool(name, args, raise_on_error=False)
            except Exception as e:  # transport-level failure
                raise ToolError(name, str(e)) from e
        if result.is_error:
            text = "".join(getattr(c, "text", "") for c in result.content) or "tool error"
            raise ToolError(name, text)
        if isinstance(result.data, str):
            return result.data
        return "".join(getattr(c, "text", "") for c in result.content)
