# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Stdio JSON-lines bridge to the librelex-core process (spec §5.2).

Writer side: ``send`` serialises one JSON object per line under a lock. Reader side: a
daemon thread parses stdout lines and hands events to ``on_event`` (called on the reader
thread; the panel re-posts them to the UI thread through AsyncCallback). stderr goes to a
0600 log file in the config directory. No UNO here.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from collections.abc import Callable

from librelex_ext.paths import BridgeSpec


class BridgeError(Exception):
    """The core process could not be started or written to."""


class Bridge:
    def __init__(self, spec: BridgeSpec, on_event: Callable[[dict], None]):
        self.spec = spec
        self.on_event = on_event
        self._proc: subprocess.Popen[bytes] | None = None
        self._lock = threading.Lock()
        self._reader: threading.Thread | None = None
        self._stderr = None

    def start(self) -> None:
        try:
            fd = os.open(str(self.spec.stderr_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            self._stderr = os.fdopen(fd, "wb")
            self._proc = subprocess.Popen(          # fixed argv, never a shell string (spec §8.4)
                self.spec.argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=self._stderr, env=self.spec.env, cwd=self.spec.cwd)
        except OSError as e:
            raise BridgeError(f"impossibile avviare {self.spec.argv[0]}: {e}") from e
        self._reader = threading.Thread(target=self._read_loop, name="librelex-bridge", daemon=True)
        self._reader.start()

    def is_alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def send(self, msg: dict) -> None:
        if self._proc is None or self._proc.stdin is None:
            raise BridgeError("core non avviato")
        line = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")
        with self._lock:
            try:
                self._proc.stdin.write(line)
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError, ValueError) as e:
                raise BridgeError(f"core non raggiungibile: {e}") from e

    def stop(self, timeout: float = 3.0) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            self.send({"type": "shutdown"})
        except BridgeError:
            pass
        try:
            proc.wait(timeout)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        if self._reader is not None:
            self._reader.join(timeout)
        if self._stderr is not None:
            self._stderr.close()

    def _read_loop(self) -> None:
        proc = self._proc
        assert proc is not None and proc.stdout is not None
        for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except ValueError:
                self.on_event({"kind": "garbage", "line": line})
                continue
            if not isinstance(msg, dict):
                self.on_event({"kind": "garbage", "line": line})
                continue
            self.on_event({"kind": "message", "msg": msg})
        code = proc.wait()
        self.on_event({"kind": "exit", "code": code})
