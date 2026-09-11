# mcp-legal-it Contract Check Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Accept an mcp-legal-it server by what it can do (the `formato=json` contract of spec §10) instead of by its version number, so an unreleased checkout that already carries the contract works without `LIBRELEX_MIN_MCP_VERSION`, and a released version that lacks it is still refused.

**Architecture:** `LegalToolsClient.__aenter__` lists the server's tools once after the handshake and checks that both `verifica_citazioni` and `cite_law` declare a `formato` input parameter. When the listing succeeds the schema decides; the version floor `MIN_MCP_LEGAL_IT_VERSION` is used only when the listing fails (old servers, transport quirks). The dev CLI reports the outcome.

**Tech Stack:** core only (fastmcp `Client.list_tools()` returns `mcp.types.Tool` objects with `.name` and `.inputSchema` dict).

**Spec:** `docs/superpowers/specs/2026-09-07-librelex-it-design.md` §10 ("the core requires the JSON form and refuses older servers"), §4.3 handshake.

## Global Constraints

- Core only; ruff E F I UP B line 100; Conventional Commits with trailer `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>` via several `-m` flags, no heredocs, never amend.
- `MIN_MCP_LEGAL_IT_VERSION` and the `LIBRELEX_MIN_MCP_VERSION` override keep their meaning as the fallback floor.
- Error messages in Italian for the user-facing part: a server without the contract fails with `mcp-legal-it {found} senza il contratto JSON (formato=json): serve la {required} o successiva`; the version fallback keeps today's message (`mcp-legal-it {found} found, {required} or newer required`).

---

### Task 1: Capability check in `LegalToolsClient`

**Files:**
- Modify: `core/src/librelex_core/mcp/client.py`, `core/src/librelex_core/cli.py`, `core/tests/conftest.py`
- Test: `core/tests/test_mcp_client.py`, `core/tests/test_main.py`, `core/tests/test_cli.py`

**Interfaces:**
- `make_fake_legal_server(..., json_contract: bool = True)`: when `False`, `verifica_citazioni` and `cite_law` are registered WITHOUT the `formato` parameter (they still return markdown).
- `client.has_json_contract(tools) -> bool` (module-level function `has_json_contract(tools: Iterable[Any]) -> bool`): `True` iff both `verifica_citazioni` and `cite_law` are present and each `inputSchema.get("properties", {})` contains `formato`.
- `LegalToolsClient.contract_checked: bool` (`True` when the schema decided, `False` when the version floor did); `IncompatibleServer(found, required, reason="version"|"contract")` with the messages of the Global Constraints.

- [ ] **Step 1: Failing tests**

`core/tests/conftest.py`: add the `json_contract: bool = True` parameter; when `False`, define the two tools without `formato` (same bodies, always markdown output: `"| tabella |"` and `"**Fonte**: fake"`).

`core/tests/test_mcp_client.py`, append:

```python
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
    ok = [T(name="verifica_citazioni", inputSchema={"properties": {"citazioni": {}, "formato": {}}}),
          T(name="cite_law", inputSchema={"properties": {"reference": {}, "formato": {}}})]
    assert has_json_contract(ok) is True
    assert has_json_contract(ok[:1]) is False
    assert has_json_contract([T(name="cite_law", inputSchema={"properties": {"reference": {}}}), ok[0]]) is False
```

`core/tests/test_main.py`: `test_incompatible_server_is_reported` builds its harness with a server lacking the contract: give `Harness.__init__` a `json_contract: bool = True` argument passed to `make_fake_legal_server`, and use `Harness(FakeDocument(["x"]), server_version="2.13.0", json_contract=False)`; the assertion `"2.14.0" in message` stays valid.

`core/tests/test_cli.py`: `test_check_mcp` expects the output line `mcp-legal-it 2.14.0 raggiungibile (contratto JSON: sì)`.

Run: `cd core && uv run pytest tests/test_mcp_client.py tests/test_main.py tests/test_cli.py -q` → failures (`TypeError: json_contract`, `AttributeError: contract_checked`, output mismatch).

- [ ] **Step 2: Implement**

`client.py`:

```python
CONTRACT_TOOLS = ("verifica_citazioni", "cite_law")


class IncompatibleServer(Exception):
    def __init__(self, found: str, required: str, reason: str = "version"):
        if reason == "contract":
            msg = (f"mcp-legal-it {found or '?'} senza il contratto JSON (formato=json): "
                   f"serve la {required} o successiva")
        else:
            msg = f"mcp-legal-it {found or '?'} found, {required} or newer required"
        super().__init__(msg)
        self.found, self.required, self.reason = found, required, reason


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
```

and in `__aenter__`, after reading `server_version`:

```python
        try:
            tools = await self._client.list_tools()
        except Exception:
            tools = None
        self.contract_checked = tools is not None
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
```

(initialise `self.contract_checked = False` in `__init__`; add `from collections.abc import Iterable`.)

`cli.py` `_check`: `print(f"mcp-legal-it {tools.server_version} raggiungibile (contratto JSON: {'sì' if tools.contract_checked else 'non verificato, versione accettata'})")`.

Docstrings: update the class docstring to describe the schema check first and the version floor as fallback.

- [ ] **Step 3: Run and commit**

`cd core && uv run ruff check . && uv run pytest -q` → all pass.

```bash
git add core
git commit -m "feat(core): accept mcp-legal-it by its JSON contract (formato parameter) instead of the version number" -m "Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>"
```
