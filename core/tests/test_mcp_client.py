# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import json

import pytest

from librelex_core.config import McpConfig
from librelex_core.mcp.client import (
    ALLOWLIST,
    MIN_MCP_LEGAL_IT_VERSION,
    IncompatibleServer,
    LegalToolsClient,
    ToolError,
    _version_tuple,
)
from tests.conftest import make_fake_legal_server


def test_allowlist_has_26_names():
    assert len(ALLOWLIST) == 26 and "cite_law" in ALLOWLIST and "verifica_citazioni" in ALLOWLIST


def test_version_tuple():
    assert _version_tuple("2.14.0") == (2, 14, 0)
    assert _version_tuple("3.0.0rc1") == (3, 0, 0)
    assert _version_tuple("") == (0,)


async def test_connect_and_call(fake_legal):
    server, calls = fake_legal
    async with LegalToolsClient(server) as tools:
        assert tools.server_version == "2.14.0"
        out = await tools.call("cite_law", reference="art. 2043 c.c.", formato="json")
    assert json.loads(out)["articolo"] == "2043"
    assert calls["cite"] == ["art. 2043 c.c."]


async def test_old_version_without_contract_is_rejected():
    """Tool listing succeeds here (the fake server always answers it), so this exercises
    the contract-absence path (reason="contract"), not the version-floor fallback below."""
    server, _ = make_fake_legal_server(version="2.13.1", json_contract=False)
    with pytest.raises(IncompatibleServer, match="2.14.0") as e:
        async with LegalToolsClient(server):
            pass
    assert e.value.reason == "contract"


async def test_version_floor_rejects_an_old_server_when_tool_listing_fails(monkeypatch):
    """The one path with no schema to inspect: `list_tools()` itself fails (old servers,
    transport quirks), so compatibility falls back to comparing `serverInfo.version`."""
    from fastmcp import Client

    async def boom(self: Client) -> None:
        raise RuntimeError("transport does not support tool listing")

    monkeypatch.setattr(Client, "list_tools", boom)
    server, _ = make_fake_legal_server(version="2.13.1")
    client = LegalToolsClient(server)
    with pytest.raises(IncompatibleServer, match="2.14.0") as e:
        async with client:
            pass
    assert client.contract_checked is False
    assert e.value.reason == "version"


async def test_version_floor_accepts_a_new_server_when_tool_listing_fails(monkeypatch):
    from fastmcp import Client

    async def boom(self: Client) -> None:
        raise RuntimeError("transport does not support tool listing")

    monkeypatch.setattr(Client, "list_tools", boom)
    server, _ = make_fake_legal_server(version="2.14.0")
    async with LegalToolsClient(server) as client:
        assert client.contract_checked is False and client.server_version == "2.14.0"


async def test_unknown_tool_is_tool_error(fake_legal):
    server, _ = fake_legal
    async with LegalToolsClient(server) as tools:
        with pytest.raises(ToolError, match="non_esiste"):
            await tools.call("non_esiste")


def test_from_config_local_and_remote():
    local = LegalToolsClient.from_config(
        McpConfig(mode="local", command=["uvx", "x", "mcp-legal-it"]))
    assert type(local.transport).__name__ == "StdioTransport"
    remote = LegalToolsClient.from_config(
        McpConfig(mode="remote", remote_url="https://example.org/legal-it/mcp", bearer="tok"))
    assert type(remote.transport).__name__ == "StreamableHttpTransport"
    assert remote.transport.headers["Authorization"] == "Bearer tok"


def test_from_config_min_version_env_override(monkeypatch):
    monkeypatch.setenv("LIBRELEX_MIN_MCP_VERSION", "2.12.1")
    client = LegalToolsClient.from_config(
        McpConfig(mode="local", command=["uvx", "x", "mcp-legal-it"]))
    assert client.min_version == "2.12.1"


def test_from_config_min_version_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("LIBRELEX_MIN_MCP_VERSION", raising=False)
    client = LegalToolsClient.from_config(
        McpConfig(mode="local", command=["uvx", "x", "mcp-legal-it"]))
    assert client.min_version == MIN_MCP_LEGAL_IT_VERSION


def test_local_transport_silences_the_fastmcp_banner():
    from librelex_core.config import McpConfig
    client = LegalToolsClient.from_config(McpConfig())
    env = client.transport.env
    assert env["FASTMCP_SHOW_CLI_BANNER"] == "false" and env["FASTMCP_LOG_LEVEL"] == "WARNING"
    assert env["LEGAL_PROFILE"] == "full" and env["MCP_TRANSPORT"] == "stdio"


async def test_contract_present_beats_an_old_version_number():
    server, _ = make_fake_legal_server(version="2.12.1")        # unreleased checkout with formato
    async with LegalToolsClient(server) as client:
        assert client.server_version == "2.12.1" and client.contract_checked is True


async def test_missing_contract_is_refused_even_with_a_new_version():
    server, _ = make_fake_legal_server(version="2.14.0", json_contract=False)
    with pytest.raises(IncompatibleServer, match="senza il contratto JSON") as e:
        async with LegalToolsClient(server):
            pass
    assert "2.14.0" in str(e.value) and e.value.reason == "contract"


def test_has_json_contract_helper():
    from types import SimpleNamespace as T

    from librelex_core.mcp.client import has_json_contract
    ok = [
        T(name="verifica_citazioni", inputSchema={"properties": {"citazioni": {}, "formato": {}}}),
        T(name="cite_law", inputSchema={"properties": {"reference": {}, "formato": {}}}),
    ]
    assert has_json_contract(ok) is True
    assert has_json_contract(ok[:1]) is False
    no_formato = T(name="cite_law", inputSchema={"properties": {"reference": {}}})
    assert has_json_contract([no_formato, ok[0]]) is False


async def test_tool_specs_are_allowlisted_sorted_and_cached():
    server, _ = make_fake_legal_server()
    async with LegalToolsClient(server) as client:
        specs = await client.tool_specs()
        assert [s.name for s in specs] == sorted(s.name for s in specs)
        names = {s.name for s in specs}
        assert {"cite_law", "verifica_citazioni", "leggi_sentenza",
                "leggi_pronuncia_costituzionale"} <= names
        assert names <= ALLOWLIST
        cite_law_spec = next(s for s in specs if s.name == "cite_law")
        assert "formato" in cite_law_spec.input_schema["properties"]
        assert await client.tool_specs() is specs
