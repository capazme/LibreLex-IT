# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import json

from librelex_core import cli
from librelex_core.cli import main
from librelex_core.mcp.client import LegalToolsClient
from tests.conftest import make_fake_legal_server


def _factory(verdicts=None):
    server, _ = make_fake_legal_server(verdicts=verdicts)
    return lambda cfg: LegalToolsClient(server)


def test_check_mcp(capsys):
    rc = cli.main(["check-mcp"], tools_factory=_factory())
    assert rc == 0 and "2.14.0" in capsys.readouterr().out


def test_verify_file(tmp_path, capsys):
    f = tmp_path / "atto.txt"
    f.write_text("Vedi art. 2043 c.c.\n\nE Cass. n. 99999/2024.\n", encoding="utf-8")
    rc = cli.main(
        ["verify", str(f)],
        tools_factory=_factory({"Cass. n. 99999/2024": ("inesistente", "no")}),
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "p:1" in out and "inesistente" in out
    summary = json.loads(out[out.index("{"):])
    assert summary["commenti_inseriti"] == 1


def test_insert_norm(capsys):
    rc = cli.main(["insert-norm", "art. 2043 c.c."], tools_factory=_factory())
    out = capsys.readouterr().out
    assert rc == 0 and out.startswith("**Art. 2043 c.c.**")


def test_insert_norm_unknown(capsys):
    server, _ = make_fake_legal_server(articles={})
    rc = cli.main(
        ["insert-norm", "art. 1 c.c."], tools_factory=lambda cfg: LegalToolsClient(server)
    )
    assert rc == 1 and "non riconosciuto" in capsys.readouterr().err


def test_list_and_show_text_subcommands(tmp_path, capsys):
    f = tmp_path / "atto.txt"
    f.write_text(
        "Vedi art. 2043 c.c. e Cass. n. 12345/2024.\n\nAncora art. 2043 c.c.", encoding="utf-8")
    assert main(["list", str(f)], tools_factory=_factory()) == 0
    out = capsys.readouterr().out
    assert "art. 2043 c.c.  [norma]  x2" in out and "Cass. n. 12345/2024  [sentenza]  x1" in out
    assert main(["show-text", "Cass. n. 12345/2024"], tools_factory=_factory()) == 0
    out = capsys.readouterr().out
    assert out.startswith("Cass. n. 12345/2024") and "Massima:" in out and "Fonte: Italgiure" in out
    assert main(["show-text", "TAR Lazio n. 1/2023"], tools_factory=_factory()) == 1
    assert "non disponibile" in capsys.readouterr().err
