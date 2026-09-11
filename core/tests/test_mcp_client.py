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


async def test_rejects_old_server():
    server, _ = make_fake_legal_server(version="2.13.1")
    with pytest.raises(IncompatibleServer, match="2.14.0"):
        async with LegalToolsClient(server):
            pass


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
