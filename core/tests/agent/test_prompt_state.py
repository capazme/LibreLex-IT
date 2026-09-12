# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_core.agent.prompt import DATA_RULE, SYSTEM_PROMPT, wrap_data
from librelex_core.agent.state import (
    HISTORY_BUDGET_TOKENS,
    DocSession,
    LimitReached,
    check_ceiling,
    estimate_tokens,
)
from librelex_core.protocol import Usage


def test_prompt_is_italian_stable_and_marks_data():
    assert "cite_law" in SYSTEM_PROMPT and "leggi_" in SYSTEM_PROMPT and DATA_RULE in SYSTEM_PROMPT
    assert "verificato" in SYSTEM_PROMPT and len(SYSTEM_PROMPT) < 6000
    assert not any(ch.isdigit() for ch in SYSTEM_PROMPT)  # no dates in the prompt
    assert wrap_data("read_paragraphs", "testo") == "<<<DATI: read_paragraphs>>>\ntesto\n<<<FINE DATI>>>"  # noqa: E501


def test_session_turns_messages_and_compaction():
    s = DocSession("d1")
    t = s.begin_turn("ciao")
    t.messages.append({"role": "assistant", "content": None,
                       "tool_calls": [{"id": "c1", "type": "function",
                                       "function": {"name": "leggi_sentenza", "arguments": "{}"}}]})
    t.tool_names["c1"] = "leggi_sentenza"
    t.messages.append({"role": "tool", "tool_call_id": "c1", "content": "x" * 8000})
    t.messages.append({"role": "assistant", "content": "fatto"})
    msgs = s.messages_for_model("SYS")
    assert msgs[0] == {"role": "system", "content": "SYS"} and msgs[1] == {"role": "user", "content": "ciao"}  # noqa: E501
    assert msgs[3]["content"] == "x" * 8000
    s.end_turn(Usage(input_tokens=100, output_tokens=20, cost_usd=0.01))
    assert s.usage.input_tokens == 100 and s.total_tokens == 120
    s.begin_turn("ancora")
    msgs = s.messages_for_model("SYS")
    assert msgs[3]["content"] == "[risultato di leggi_sentenza omesso, 2k token]"  # previous turn compacted # noqa: E501
    assert msgs[-1] == {"role": "user", "content": "ancora"}


def test_history_is_dropped_oldest_first_over_budget():
    s = DocSession("d1")
    for i in range(30):
        t = s.begin_turn(f"domanda {i}")
        t.messages.append({"role": "assistant", "content": "r" * 8000})
        s.end_turn(Usage(input_tokens=1, output_tokens=1))
    msgs = s.messages_for_model("SYS")
    assert estimate_tokens(msgs) <= HISTORY_BUDGET_TOKENS + 2500
    assert msgs[1]["content"] != "domanda 0" and msgs[-1]["content"] == "r" * 8000
    assert len(s.turns) >= 1


def test_ceiling():
    s = DocSession("d1")
    s.end_turn(Usage(input_tokens=399_000, output_tokens=2_000))
    with pytest.raises(LimitReached, match="401000"):
        check_ceiling(s, 400_000)
    check_ceiling(DocSession("d2"), 400_000)
