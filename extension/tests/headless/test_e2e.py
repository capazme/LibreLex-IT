# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""M1 exit criterion, headless: insert a norm and verify citations through the real core."""
import shutil

import pytest

from librelex_ext import paths
from tests.headless.conftest import run_probe

pytestmark = [pytest.mark.headless,
              pytest.mark.skipif(shutil.which("uv") is None, reason="uv not installed")]

CORE = paths.repo_core_dir()


def test_insert_norm_and_verify_from_inside_libreoffice(soffice, tmp_path):
    cfg = tmp_path / "config.toml"
    server = CORE / "tests" / "fake_legal_server.py"
    cfg.write_text(
        "[mcp_legal_it]\nmode = \"local\"\n"
        f"command = [\"uv\", \"run\", \"--project\", \"{CORE}\", \"python\", \"{server}\"]\n",
        encoding="utf-8")
    uv_dir = str(paths.Path(shutil.which("uv")).parent)
    out = run_probe(soffice, "e2e", f'''
    import os, queue
    from librelex_ext import paths
    from librelex_ext.bridge import Bridge
    from librelex_ext.session import Session

    class RecView:
        def __init__(self):
            self.lines, self.status, self.citations = [], [], None
        def append(self, t): self.lines.append(t)
        def set_transcript(self, t): pass
        def set_status(self, t): self.status.append(t)
        def set_busy(self, b): pass
        def set_citations(self, labels): self.citations = labels

    def pump(session, events, until_state="ready", timeout=180):
        import time
        deadline = time.time() + timeout
        while session.state != until_state and time.time() < deadline:
            try:
                ev = events.get(timeout=1)
            except queue.Empty:
                continue
            session.handle_event(ev)
        return session.state

    def probe(ctx, out):
        doc = new_doc(ctx)
        text = doc.Text
        cur = text.createTextCursor()
        text.insertString(cur, "Premessa. Si veda l'art. 2043 c.c. e Cass. n. 99999/2024.", False)
        adapter = DocumentAdapter(ctx, doc)
        events = queue.Queue()
        config = {{"extension": {{"uv": os.path.join({uv_dir!r}, "uv")}}}}
        def bridge_factory(on_event):
            spec = paths.bridge_spec(paths.Path("/nonexistent-pkg"), config)
            env = dict(spec.env)
            env["UV_PROJECT_ENVIRONMENT"] = str(paths.repo_core_dir() / ".venv")
            return Bridge(paths.BridgeSpec(spec.argv, env, spec.stderr_path, spec.cwd), on_event)
        view = RecView()
        s = Session(adapter, bridge_factory, doc_id=doc.RuntimeUID, lo_version=lo_version(ctx),
                    has_markdown_filter=has_markdown_filter(ctx), config_path={str(cfg)!r})
        s.bind(view, events.put)
        vc = doc.getCurrentController().getViewCursor()
        vc.gotoEnd(False) if hasattr(vc, "gotoEnd") else None
        c = text.createTextCursor(); c.gotoEnd(False); vc.gotoRange(c, False)
        s.run_command("insert_norm", {{"reference": "art. 2043 c.c."}})
        out["state_after_insert"] = pump(s, events)
        out["lines_after_insert"] = list(view.lines)
        out["paragraphs"] = paragraph_texts(text)
        out["redlines"] = redlines(doc)
        out["bookmarks"] = list(doc.Bookmarks.getElementNames())
        s.run_command("verify_citations", {{"scope": "document"}})
        out["state_after_verify"] = pump(s, events)
        out["lines_after_verify"] = list(view.lines)
        out["citations_after_verify"] = view.citations
        out["annotations"] = annotations(doc)
        s.run_command("show_text", {{"reference": "art. 2043 c.c."}})
        out["state_after_show"] = pump(s, events)
        out["shown"] = view.lines[-1]
        s.run_command("list_citations", {{"scope": "document"}})
        out["state_after_list"] = pump(s, events)
        out["citations"] = view.citations
        s.shutdown()
        doc.close(True)
    ''', timeout=300, env={"LIBRELEX_CONFIG": str(cfg)})
    assert out["state_after_insert"] == "ready", out["lines_after_insert"]
    assert any(line.startswith("Inserito art. 2043 c.c. come revisione")
               for line in out["lines_after_insert"]), out
    texts = [t for _, t in out["paragraphs"]]
    assert texts[0].startswith("Premessa.") and texts[1] == "Art. 2043 c.c."
    assert texts[2].startswith("Qualunque fatto doloso") and texts[3].startswith("Testo vigente al")
    assert out["redlines"] and all(a == "LibreLex" for _, a in out["redlines"])
    assert any(b.startswith("LibreLex.norma.") for b in out["bookmarks"])
    assert out["state_after_verify"] == "ready", out["lines_after_verify"]
    # the inserted heading "Art. 2043 c.c." is a second occurrence of the same canonical
    # reference, hence "×2"; the unique citations stay two
    assert out["citations_after_verify"] == ["✓ art. 2043 c.c. ×2", "✗ Cass. n. 99999/2024"]
    assert [c["anchor"] for c in out["annotations"]] == ["Cass. n. 99999/2024"]
    assert out["annotations"][0]["author"] == "LibreLex · verifica"
    # Mostra testo on a typed reference: the norm text arrives from the fake cite_law
    assert out["state_after_show"] == "ready", out["shown"]
    assert out["shown"].startswith("— art. 2043 c.c.") and "Qualunque fatto doloso" in out["shown"]
    # Elenca citazioni: extraction only, no tool call, no verdict markers. The inserted
    # article adds no new canonical citation, only a second occurrence of art. 2043 c.c.
    # (its heading), which is why the first label carries "×2".
    assert out["state_after_list"] == "ready", out["lines_after_verify"]
    assert out["citations"] == ["art. 2043 c.c. ×2", "Cass. n. 99999/2024"]
