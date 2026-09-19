# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import json

import pytest

from librelex_core import cli
from librelex_core.cli import main
from librelex_core.mcp.client import LegalToolsClient
from tests.conftest import make_fake_legal_server


def _factory(verdicts=None):
    server, _ = make_fake_legal_server(verdicts=verdicts)
    return lambda cfg: LegalToolsClient(server)


def test_check_mcp(capsys):
    rc = cli.main(["check-mcp"], tools_factory=_factory())
    out = capsys.readouterr().out
    assert rc == 0 and "mcp-legal-it 2.14.0 raggiungibile (contratto JSON: sì)" in out


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


def test_chat_subcommand_streams_and_summarises(tmp_path, capsys):
    from tests.fakes import ScriptedLLM, text_turn
    f = tmp_path / "atto.txt"
    f.write_text("Testo.", encoding="utf-8")
    llm = ScriptedLLM([text_turn("Risposta.")])
    assert main(["chat", "ciao", "--file", str(f)], tools_factory=_factory(),
                llm_factory=lambda cfg: llm) == 0
    out = capsys.readouterr().out
    assert out.startswith("Risposta.") and "token" in out


def test_templates_and_template_subcommands(capsys):
    assert main(["templates"], tools_factory=_factory()) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].startswith("decreto_ingiuntivo_ordinario  atti_introduttivi")
    assert main(["templates", "precetto"], tools_factory=_factory()) == 0
    assert "precetto_ordinario" in capsys.readouterr().out
    assert main(["template", "decreto_ingiuntivo_ordinario"], tools_factory=_factory()) == 0
    out = capsys.readouterr().out
    assert "importo  numero  obbligatorio" in out and '"tool": "decreto_ingiuntivo"' in out
    assert main(["template", "boh"], tools_factory=_factory()) == 1
    assert capsys.readouterr().err.startswith("errore:")


def test_draft_subcommand_start_questions_answer_and_reference(tmp_path, capsys):
    from tests.fakes import ScriptedLLM, tool_turn
    ref = tmp_path / "ricorso_rossi.txt"
    ref.write_text("RICORSO di riferimento", encoding="utf-8")
    llm = ScriptedLLM([
        tool_turn(("chiedi_dati",
                  {"domande": [{"campo": "sede", "domanda": "Sede?", "esempio": "Milano"}]})),
        tool_turn(("leggi_atto_riferimento", {})),
        tool_turn(("insert_markdown", {"where": "end",
                                       "markdown": "## Conclusioni\n\nSi chiede."})),
        tool_turn(("redazione_completata", {"riepilogo": "Riepilogo finale."}))])
    rc = main(["draft", "--tipo", "decreto_ingiuntivo_ordinario", "--campo", "creditore=Alfa",
               "--campo", "debitore=Beta", "--campo", "importo=12000", "--note", "fattura 12",
               "--riferimento", str(ref), "--risposta", "sede=Milano"],
              tools_factory=_factory(), llm_factory=lambda cfg: llm)
    assert rc == 0
    out = capsys.readouterr().out
    assert "? sede (testo): Sede? [Milano]" in out
    assert "Riepilogo finale." in out and "completata" in out and "partizioni: 2" in out
    assert "Atto di riferimento disponibile: ricorso_rossi.txt" in llm.calls[0][0][1]["content"]
    assert "<<<DATI: atto di riferimento (ricorso_rossi.txt)>>>" in "".join(
        m["content"] for m in llm.calls[2][0] if m.get("role") == "tool")


def test_draft_subcommand_reference_consent_names_the_file(tmp_path, capsys):
    from tests.fakes import ScriptedLLM, tool_turn
    ref_text = "RICORSO di riferimento"
    ref = tmp_path / "ricorso_rossi.txt"
    ref.write_text(ref_text, encoding="utf-8")
    llm = ScriptedLLM([
        tool_turn(("chiedi_dati",
                  {"domande": [{"campo": "sede", "domanda": "Sede?", "esempio": "Milano"}]})),
        tool_turn(("leggi_atto_riferimento", {})),
        tool_turn(("insert_markdown", {"where": "end",
                                       "markdown": "## Conclusioni\n\nSi chiede."})),
        tool_turn(("redazione_completata", {"riepilogo": "Riepilogo finale."}))])
    rc = main(["draft", "--tipo", "decreto_ingiuntivo_ordinario", "--campo", "creditore=Alfa",
               "--campo", "debitore=Beta", "--campo", "importo=12000",
               "--riferimento", str(ref), "--risposta", "sede=Milano"],
              tools_factory=_factory(), llm_factory=lambda cfg: llm)
    assert rc == 0
    err = capsys.readouterr().err
    assert 'atto di riferimento "ricorso_rossi.txt"' in err
    assert f"{len(ref_text)} caratteri" in err


def test_draft_subcommand_campo_without_equals_is_a_usage_error(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["draft", "--tipo", "decreto_ingiuntivo_ordinario", "--campo", "creditore"],
             tools_factory=_factory())
    assert exc.value.code == 2
    assert "--campo/--risposta richiedono NOME=VALORE" in capsys.readouterr().err
