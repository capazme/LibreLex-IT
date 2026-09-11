# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Minimal stand-in for librelex-core: hello → hello_ok; command → one doc_call → final."""
import json
import sys


def out(msg):
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main():
    pending = None
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        msg = json.loads(line)
        t = msg.get("type")
        if t == "hello":
            out({"type": "hello_ok", "core_version": "0.0-fake", "protocol": msg["protocol"],
                 "mcp_server_version": None, "warnings": []})
        elif t == "shutdown":
            return 0
        elif t == "command":
            if msg.get("args", {}).get("crash"):
                sys.exit(3)
            pending = msg["id"]
            out({"type": "status", "request_id": pending, "text": "leggo"})
            out({"type": "doc_call", "request_id": pending, "call_id": "c1",
                 "action": "get_document_info", "args": {}})
        elif t == "doc_result":
            out({"type": "final", "request_id": pending, "text": "fatto", "cancelled": False,
                 "usage": None, "summary": {"info": msg.get("result"), "ok": msg["ok"]}})
        elif t == "cancel":
            out({"type": "final", "request_id": msg["id"], "text": "Annullato.", "cancelled": True,
                 "usage": None, "summary": {}})
    return 0


if __name__ == "__main__":
    sys.exit(main())
