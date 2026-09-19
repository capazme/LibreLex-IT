# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Thin client over fastmcp for mcp-legal-it (spec §4.1, §6.2, §10)."""
from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from fastmcp import Client
from fastmcp.client.transports import StdioTransport, StreamableHttpTransport

from librelex_core.config import McpConfig

MIN_MCP_LEGAL_IT_VERSION = "2.14.0"
CONTRACT_TOOLS = ("verifica_citazioni", "cite_law")

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
    # act generators the genera_modello_atto catalogue routes to (deterministic, no network)
    "decreto_ingiuntivo", "atto_di_precetto", "sollecito_pagamento", "procura_alle_liti",
    "relata_notifica_pec", "attestazione_conformita", "sfratto_morosita",
    "nota_precisazione_credito", "dichiarazione_553_cpc",
})


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict


class ToolError(Exception):
    def __init__(self, name: str, message: str):
        super().__init__(f"{name}: {message}")
        self.name, self.message = name, message


class IncompatibleServer(Exception):
    def __init__(self, found: str, required: str, reason: str = "version"):
        if reason == "contract":
            msg = (f"mcp-legal-it {found or '?'} senza il contratto JSON (formato=json): "
                   f"serve la {required} o successiva")
        else:
            msg = f"mcp-legal-it {found or '?'} found, {required} or newer required"
        super().__init__(msg)
        self.found, self.required, self.reason = found, required, reason


def _version_tuple(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v.split("+")[0])
    return tuple(int(n) for n in nums[:3]) or (0,)


def has_json_contract(tools: Iterable[Any]) -> bool:
    """True when both contract tools accept the `formato` parameter (spec §10)."""
    by_name = {getattr(t, "name", ""): t for t in tools}
    for name in CONTRACT_TOOLS:
        tool = by_name.get(name)
        if tool is None:
            return False
        schema = getattr(tool, "inputSchema", None) or {}
        if "formato" not in (schema.get("properties") or {}):
            return False
    return True


class LegalToolsClient:
    """Connects to mcp-legal-it over fastmcp and enforces the JSON contract of spec §10.

    Compatibility is decided primarily by ``list_tools()``: the server must expose
    ``verifica_citazioni`` and ``cite_law`` with a ``formato`` parameter (see
    ``has_json_contract``). When the tool listing cannot be obtained, this falls
    back to comparing ``serverInfo.version`` against ``min_version`` (which
    defaults to ``MIN_MCP_LEGAL_IT_VERSION`` but can be relaxed via the
    ``LIBRELEX_MIN_MCP_VERSION`` environment variable, see ``from_config``, needed
    while the dev CLI's live smoke test still targets an untagged mcp-legal-it
    checkout).
    """

    def __init__(self, transport: Any, *, min_version: str = MIN_MCP_LEGAL_IT_VERSION,
                 max_concurrency: int = 4, timeout_s: float = 60.0):
        self.transport = transport
        self.min_version = min_version
        self.timeout_s = timeout_s
        self._sem = asyncio.Semaphore(max_concurrency)
        self._client: Client | None = None
        self.server_version: str = ""
        self.contract_checked: bool = False
        self._specs: list[ToolSpec] | None = None
        self._initial_tools: Iterable[Any] | None = None

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
        try:
            tools = await self._client.list_tools()
        except Exception:
            tools = None
        self.contract_checked = tools is not None
        self._initial_tools = tools
        if tools is not None:
            compatible = has_json_contract(tools)
            reason = "contract"
        else:                       # no listing: fall back to the version floor
            compatible = _version_tuple(self.server_version) >= _version_tuple(self.min_version)
            reason = "version"
        if not compatible:
            await self._client.__aexit__(None, None, None)
            self._client = None
            raise IncompatibleServer(self.server_version, self.min_version, reason)
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

    async def tool_specs(self) -> list[ToolSpec]:
        """Allowlisted tool definitions from the server, sorted by name, fetched once."""
        if self._specs is None:
            if self._client is None:
                raise RuntimeError("LegalToolsClient used outside 'async with'")
            tools = self._initial_tools
            if tools is None:
                tools = await self._client.list_tools()
            self._specs = sorted(
                (ToolSpec(t.name, t.description or "", dict(t.inputSchema or {}))
                 for t in tools if t.name in ALLOWLIST), key=lambda s: s.name)
        return self._specs
