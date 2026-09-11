# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""The per-document session registry against a real Writer document (spec §4.3).

Regression test for the whole-branch review findings C1/I1: ``session_for`` used to register a
``com.sun.star.lang.XEventListener``, which pyuno rejects on a TextDocument
(``CannotConvertException``), so the first panel open on a document raised and the session of a
closed document was never torn down. This probe calls the *real* ``registry.session_for``.
"""
import pytest

from tests.headless.conftest import run_probe

pytestmark = pytest.mark.headless


def test_session_for_registers_on_a_real_document_and_tears_it_down_on_close(soffice):
    out = run_probe(soffice, "registry_session", '''
    def probe(ctx, out):
        import time

        from librelex_ext import registry

        calls = []

        class FakeSession:
            def shutdown(self):
                calls.append("shutdown")

        doc = new_doc(ctx)
        doc_id = doc.RuntimeUID
        first = registry.session_for(doc, FakeSession)      # must not raise (C1)
        second = registry.session_for(doc, FakeSession)     # one session per RuntimeUID
        out["reused"] = first is second
        out["registered"] = doc_id in registry._sessions
        out["shutdown_before_close"] = len(calls)
        doc.close(True)
        for _ in range(100):                                # OnUnload, then disposing
            if calls:
                break
            time.sleep(0.02)
        out["shutdown_after_close"] = len(calls)
        out["still_registered"] = doc_id in registry._sessions
    ''')
    assert out["reused"] is True and out["registered"] is True
    assert out["shutdown_before_close"] == 0
    assert out["shutdown_after_close"] == 1       # exactly once: OnUnload pops, disposing no-ops
    assert out["still_registered"] is False
