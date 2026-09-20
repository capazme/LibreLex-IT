# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Strips the proxy-mangled tool-name prefixes an MCP proxy can inject in front of a tool
name (Drafting Workbench design §1's follow-up): the core never changes the names it sends
to the model, but the model may echo them back mangled as ``mcp__<token>__<token>_<name>``
or ``mcp__<token>__<name>``. This is a pure, one-shot cleanup applied to the model's prose
after the fact, never to the tool calls themselves.
"""
from __future__ import annotations

import re
from collections.abc import Iterable


def clean_tool_names(text: str, names: Iterable[str]) -> str:
    """Every proxy-mangled occurrence of a known tool name in ``text``, replaced by the bare
    name (word boundaries respected on both sides).

    ``names`` is matched longest first, so a name that happens to be a prefix of another
    never steals a match meant for the longer one. A text carrying none of these prefixes
    comes back unchanged, the very same string object, so a caller can compare with ``is``.
    """
    ordered = sorted(set(names), key=len, reverse=True)
    if not ordered:
        return text
    # The first token (the proxy's own server id) can itself carry underscores ("trade_dress"),
    # so it is matched lazily up to the literal "__" that starts the tool name, rather than
    # with a bare [A-Za-z0-9]+ that a snake_case id would break out of.
    pattern = re.compile(
        r"\bmcp__[A-Za-z0-9_]+?__(?:[A-Za-z0-9]+_)?(" +
        "|".join(re.escape(name) for name in ordered) + r")\b")
    return pattern.sub(r"\1", text)
