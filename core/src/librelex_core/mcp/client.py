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

# Building blocks of ALLOWLIST. `profiles.py` imports `ALLOWLIST`, `ROUTING_GENERATORS` and
# `CATALOGUE_CALCULATORS` from here rather than owning them: it already imports `ALLOWLIST`
# from this module, so the reverse (this module importing from `profiles`) would be circular.
NORMS = ("cite_law", "fetch_act_index", "fetch_full_act", "verifica_citazioni", "cerca_brocardi")
CASE_LAW_TOOLS = (
    "cerca_giurisprudenza", "cerca_giurisprudenza_unificata", "leggi_sentenza",
    "giurisprudenza_su_norma", "orientamento_su_norma", "cerca_giurisprudenza_amministrativa",
    "leggi_provvedimento_amm", "cerca_giurisprudenza_cgue", "leggi_sentenza_cgue",
    "cerca_pronuncia_costituzionale", "leggi_pronuncia_costituzionale",
)
TEMPLATES = ("genera_modello_atto", "lista_categorie_atti")
# Every routing.tool of a modelli_atti.json catalogue entry (mcp-legal-it, 2026-09-19): the
# act generators genera_modello_atto's "tool_diretto" routing can send a tipo_atto to.
ROUTING_GENERATORS = (
    "attestazione_conformita", "atto_di_precetto", "decreto_ingiuntivo", "dichiarazione_553_cpc",
    "genera_dpa", "genera_dpia", "genera_informativa_cookie", "genera_informativa_dipendenti",
    "genera_informativa_privacy", "genera_informativa_videosorveglianza",
    "genera_notifica_data_breach", "genera_registro_trattamenti", "nota_precisazione_credito",
    "preventivo_civile", "preventivo_stragiudiziale", "preventivo_volontaria_giurisdizione",
    "procura_alle_liti", "relata_notifica_pec", "sfratto_morosita", "sollecito_pagamento",
)
# The 15 names of every tool_calcolo listed in modelli_atti.json (mcp-legal-it, 2026-09-19),
# plus calcolo_hash and calcolo_tempo_trascorso (the two of Appendix B the catalogue does not
# name). CALCULATORS (spec Appendix B, used by the review profile) is a subset of this tuple.
CATALOGUE_CALCULATORS = (
    "calcolo_hash", "calcolo_tempo_trascorso", "calcolo_valore_catastale", "compenso_ctu",
    "conta_giorni", "contributo_unificato", "interessi_legali", "interessi_mora",
    "parcella_avvocato_civile", "pignoramento_stipendio", "rivalutazione_monetaria",
    "scadenza_processuale", "scadenze_impugnazioni", "spese_mediazione",
    "termini_processuali_civili", "valutazione_data_breach", "variazioni_istat",
)

ALLOWLIST: frozenset[str] = frozenset(
    NORMS + CASE_LAW_TOOLS + TEMPLATES + ROUTING_GENERATORS + CATALOGUE_CALCULATORS)


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

    async def read_resource(self, uri: str) -> str:
        """Text of an MCP resource of the server; failures become ToolError."""
        if self._client is None:
            raise RuntimeError("LegalToolsClient used outside 'async with'")
        try:
            contents = await self._client.read_resource(uri)
        except Exception as e:
            raise ToolError("leggi_risorsa", str(e)) from e
        for item in contents:
            text = getattr(item, "text", None)
            if isinstance(text, str):
                return text
        raise ToolError("leggi_risorsa", f"risorsa senza testo: {uri}")

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
