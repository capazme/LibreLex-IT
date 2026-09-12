# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_core.config import LLMConfig
from librelex_core.llm.client import LLMClient, LLMError
from tests.fakes import chunk, mock_llm, sse


def _cfg(**kw):
    return LLMConfig(preset="custom", base_url="https://llm.example.org/v1", api_key="sk-secret",
                     model="test-model", **kw)


async def test_streams_text_and_reassembles_tool_calls_and_usage():
    body = sse([
        chunk({"role": "assistant", "content": "Cia"}),
        chunk({"content": "o. "}),
        chunk({"tool_calls": [{"index": 0, "id": "call_a", "type": "function",
                               "function": {"name": "cite_law", "arguments": "{\"refe"}}]}),
        chunk({"tool_calls": [{"index": 0,
                               "function": {"arguments": "rence\": \"art. 2043 c.c.\"}"}}]}),
        chunk({"tool_calls": [{"index": 1, "id": "call_b", "type": "function",
                               "function": {"name": "data_odierna", "arguments": "{}"}}]}),
        chunk(finish="tool_calls"),
        chunk(usage={"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150,
                    "cost": 0.0012}),
    ])
    http = mock_llm([body])
    client = LLMClient(_cfg(), http_client=http)
    deltas = []

    async def on_delta(t):
        deltas.append(t)

    tools = [{"type": "function", "function": {"name": "cite_law", "parameters": {}}}]
    turn = await client.stream([{"role": "user", "content": "ciao"}], tools, on_delta)
    assert "".join(deltas) == "Ciao. " and turn.text == "Ciao. "
    assert [(c.id, c.name, c.arguments) for c in turn.tool_calls] == [
        ("call_a", "cite_law", '{"reference": "art. 2043 c.c."}'), ("call_b", "data_odierna", "{}")]
    assert turn.finish_reason == "tool_calls"
    assert (turn.usage.input_tokens, turn.usage.output_tokens,
            turn.usage.cost_usd) == (120, 30, 0.0012)
    sent = http.calls[0]
    assert sent["model"] == "test-model" and sent["stream"] is True
    assert sent["stream_options"] == {"include_usage": True}
    assert sent["tools"][0]["function"]["name"] == "cite_law"


async def test_plain_answer_without_usage_and_openrouter_extras():
    cfg = LLMConfig(preset="openrouter", api_key="sk-x", model="m")
    http = mock_llm([sse([chunk({"content": "Sì."}), chunk(finish="stop")])])
    client = LLMClient(cfg, http_client=http)
    turn = await client.stream([{"role": "user", "content": "?"}], None, lambda t: _noop())
    assert turn.text == "Sì." and turn.tool_calls == [] and turn.usage.input_tokens == 0
    sent = http.calls[0]
    assert sent["provider"] == {"data_collection": "deny"} and sent["usage"] == {"include": True}
    assert "tools" not in sent


async def _noop():
    return None


async def test_http_errors_become_llm_error_without_secrets():
    http = mock_llm([401])
    client = LLMClient(_cfg(), http_client=http)
    with pytest.raises(LLMError) as e:
        await client.stream([{"role": "user", "content": "x"}], None, lambda t: _noop())
    assert e.value.code == "llm_http" and "401" in str(e.value) and "sk-secret" not in str(e.value)


async def test_retries_then_succeeds_on_transient_errors():
    http = mock_llm([500, 503, sse([chunk({"content": "ok"}), chunk(finish="stop")])])
    client = LLMClient(_cfg(), http_client=http)
    turn = await client.stream([{"role": "user", "content": "x"}], None, lambda t: _noop())
    assert turn.text == "ok" and len(http.calls) == 3


def test_missing_model_is_a_config_error():
    with pytest.raises(LLMError) as e:
        LLMClient(LLMConfig(preset="openrouter", api_key="k", model=""))
    assert e.value.code == "llm_config" and "model" in str(e.value)
