# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_ext.render import (
    citation_label,
    render_consent,
    render_draft_status,
    render_error,
    render_field_label,
    render_insert_summary,
    render_list_summary,
    render_partitions,
    render_question_label,
    render_questions_hint,
    render_reference,
    render_riepilogo,
    render_show_text,
    render_template_notes,
    render_turn_notes,
    render_usage,
    render_verify_summary,
)

SUMMARY = {
    "scope": "document", "citazioni_totali": 5, "citazioni_uniche": 4,
    "per_verdetto": {"verificata": 2, "inesistente": 1, "metadati discordanti": 1},
    "problemi": [
        {"citazione": "Cass. n. 99999/2024", "verdetto": "inesistente", "nota": "non trovata",
         "occorrenze": [{"paragraph_id": "p:3", "start": 10, "end": 29}]},
        {"citazione": "art. 13 co. 7 D.Lgs. 196/2003", "verdetto": "metadati discordanti",
         "nota": "comma non riscontrato",
         "occorrenze": [{"paragraph_id": "fn:1/p:0", "start": 0, "end": 5}]},
    ],
    "da_controllare_a_mano": ["Corte cost. n. 1/2020"],
    "non_interpretabili": ["art. 5"],
    "non_verificabili": [],
    "da_riprovare": ["Cass. n. 100/2021"],
    "commenti_inseriti": 2,
    "elenco": [
        {"citazione": "art. 2043 c.c.", "tipo": "norma", "verdetto": "verificata", "nota": "",
         "occorrenze": [{"paragraph_id": "p:1", "start": 0, "end": 14},
                        {"paragraph_id": "p:5", "start": 0, "end": 14}]},
        {"citazione": "Cass. n. 99999/2024", "tipo": "sentenza", "verdetto": "inesistente",
         "nota": "non trovata",
         "occorrenze": [{"paragraph_id": "p:3", "start": 10, "end": 29}]},
        {"citazione": "art. 13 co. 7 D.Lgs. 196/2003", "tipo": "norma",
         "verdetto": "metadati discordanti", "nota": "comma non riscontrato",
         "occorrenze": [{"paragraph_id": "fn:1/p:0", "start": 0, "end": 5}]},
        {"citazione": "Corte cost. n. 1/2020", "tipo": "sentenza",
         "verdetto": "da controllare a mano", "nota": "",
         "occorrenze": [{"paragraph_id": "p:7", "start": 0, "end": 5}]},
    ],
}


def test_verify_summary_lists_counts_problems_and_side_lists():
    text, items = render_verify_summary(SUMMARY)
    assert text.splitlines()[0] == "Verificate 4 citazioni (5 occorrenze), 2 segnalazioni inserite."
    assert "verificata: 2 · inesistente: 1 · metadati discordanti: 1" in text
    assert "- Cass. n. 99999/2024: inesistente (p:3) — non trovata" in text
    assert "Da controllare a mano: Corte cost. n. 1/2020" in text
    assert "Non interpretabili: art. 5" in text
    assert "Da riprovare (fonte non raggiungibile): Cass. n. 100/2021" in text
    assert "Non verificabili" not in text
    assert items == [("✓ art. 2043 c.c. ×2", "p:1", "art. 2043 c.c."),
                     ("✗ Cass. n. 99999/2024", "p:3", "Cass. n. 99999/2024"),
                     ("✗ art. 13 co. 7 D.Lgs. 196/2003", "fn:1/p:0",
                      "art. 13 co. 7 D.Lgs. 196/2003"),
                     ("· Corte cost. n. 1/2020", "p:7", "Corte cost. n. 1/2020")]


def test_verify_summary_with_no_problems():
    text, items = render_verify_summary({**SUMMARY, "problemi": [], "commenti_inseriti": 0,
                                         "per_verdetto": {"verificata": 4}, "elenco": [],
                                         "da_controllare_a_mano": [], "non_interpretabili": [],
                                         "da_riprovare": []})
    assert "Nessun problema rilevato." in text and items == []


def test_citation_label_markers():
    assert citation_label("art. 2043 c.c.", "verificata", 2) == "✓ art. 2043 c.c. ×2"
    assert citation_label("x", "inesistente") == "✗ x"
    assert citation_label("x", "non trovata") == "✗ x"
    assert citation_label("x", "metadati discordanti") == "✗ x"
    assert citation_label("x", "non verificata") == "? x"
    assert citation_label("x", "non verificabile") == "· x"
    assert citation_label("x", "da controllare a mano") == "· x"
    assert citation_label("x", None, 3) == "x ×3"


def test_verify_items_cover_the_whole_elenco():
    text, items = render_verify_summary(SUMMARY)
    assert items == [("✓ art. 2043 c.c. ×2", "p:1", "art. 2043 c.c."),
                     ("✗ Cass. n. 99999/2024", "p:3", "Cass. n. 99999/2024"),
                     ("✗ art. 13 co. 7 D.Lgs. 196/2003", "fn:1/p:0",
                      "art. 13 co. 7 D.Lgs. 196/2003"),
                     ("· Corte cost. n. 1/2020", "p:7", "Corte cost. n. 1/2020")]
    assert "- Cass. n. 99999/2024: inesistente (p:3) — non trovata" in text


def test_list_summary_and_show_text():
    text, items = render_list_summary({
        "scope": "document", "citazioni_totali": 3, "citazioni_uniche": 2,
        "citazioni": [{"citazione": "art. 2043 c.c.", "tipo": "norma", "corte": None,
                       "verificabile": True,
                       "occorrenze": [{"paragraph_id": "p:0", "start": 0, "end": 1},
                                      {"paragraph_id": "p:2", "start": 0, "end": 1}]},
                      {"citazione": "TAR Lazio n. 1/2023", "tipo": "sentenza", "corte": "tar",
                       "verificabile": False,
                       "occorrenze": [{"paragraph_id": "p:1", "start": 0, "end": 1}]}],
        "non_interpretabili": ["art. 5"]})
    assert (text.splitlines()[0]
            == "Trovate 2 citazioni (3 occorrenze). Clic su una voce per il testo.")
    assert "Non interpretabili: art. 5" in text
    assert items == [("art. 2043 c.c. ×2", "p:0", "art. 2043 c.c."),
                     ("TAR Lazio n. 1/2023", "p:1", "TAR Lazio n. 1/2023")]
    shown = render_show_text({"tipo": "sentenza", "riferimento": "Cass. n. 12345/2024",
                              "titolo": "Cass. n. 12345/2024", "testo": "FATTI...",
                              "massima": "Il datore risponde.", "fonte": "Italgiure",
                              "url": "", "troncato": True})
    assert shown == (
        "— Cass. n. 12345/2024 (Italgiure) —\nMassima: Il datore risponde.\n\nFATTI...\n"
        "[testo abbreviato per il pannello]")
    shown = render_show_text({"tipo": "norma", "riferimento": "art. 2043 c.c.",
                              "titolo": "art. 2043 c.c. (Risarcimento)",
                              "testo": "Qualunque fatto", "massima": None, "fonte": "Normattiva",
                              "url": "https://x", "troncato": False})
    assert shown == "— art. 2043 c.c. (Risarcimento) (Normattiva, https://x) —\nQualunque fatto"


def test_insert_summary_and_error():
    text = render_insert_summary({
        "riferimento": "art. 2043 c.c.", "url": "https://x",
        "bookmark": "LibreLex.norma.x", "inserted": {"from_id": "p:1", "to_id": "p:3"}})
    assert text == (
        "Inserito art. 2043 c.c. come revisione (paragrafi p:1-p:3, "
        "segnalibro LibreLex.norma.x).\nFonte: https://x")
    assert (render_error("busy", "un'altra richiesta è in corso")
            == "Errore (busy): un'altra richiesta è in corso")


def test_render_usage_consent_and_notes():
    assert render_usage(
        {"input_tokens": 40072, "output_tokens": 403, "cost_usd": None},
        {"input_tokens": 40072, "output_tokens": 403},
    ) == "Turno: 40.072 + 403 token · sessione: 40.475 token"
    assert render_usage(
        {"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.0123}, None
    ) == "Turno: 10 + 5 token · costo: $0.01"
    assert render_usage(None, None) == ""
    assert render_consent({
        "scope": "paragraphs", "chars": 1234, "endpoint_host": "127.0.0.1",
        "model": "claude-sonnet-5", "zdr": True,
    }) == ("Inviare al modello claude-sonnet-5 su 127.0.0.1 (senza conservazione dati) "
           "i paragrafi letti (1.234 caratteri)?")
    assert render_turn_notes({
        "stopped": "iterations", "inserted": [{"from_id": "p:2", "to_id": "p:4"}],
        "flagged": ["Cass. n. 9/2024"], "unverified": [],
    }) == [
        "[interrotto: limite di iterazioni]", "Inserito nei paragrafi p:2-p:4",
        "Riferimenti segnalati con un commento: Cass. n. 9/2024"]
    # the core spells the turn budget "timeout" (agent/loop.py), not "time"
    assert render_turn_notes({"stopped": "timeout"}) == ["[interrotto: tempo massimo]"]
    assert render_turn_notes({"stopped": "boh"}) == ["[interrotto: boh]"]
    error_lines = render_error(
        "llm_config", "llm.model non impostato", "/cfg/config.toml"
    ).splitlines()
    assert error_lines[1].startswith("Configura la sezione [llm]")


def test_render_usage_shows_session_total_and_cost_together():
    """Fix round 1, finding 1: sessione and costo are independent, not if/elif."""
    assert render_usage(
        {"input_tokens": 10, "output_tokens": 5, "cost_usd": 0.0123},
        {"input_tokens": 1000, "output_tokens": 500},
    ) == "Turno: 10 + 5 token · sessione: 1.500 token · costo: $0.01"


def test_render_guided_drafting_copy():
    info = {"routing": {"tipo": "tool_diretto", "tool": "decreto_ingiuntivo"},
            "avvertenze": ["Bozza indicativa"]}
    assert render_template_notes(info) == (
        "Base deterministica: decreto_ingiuntivo · Bozza indicativa")
    assert render_template_notes({"routing": {"tipo": "resource"}, "avvertenze": []}) == (
        "Composizione dal modello (risorsa del catalogo)")
    # M8: a tool routing with no tool name must not render "Base deterministica: None"
    assert render_template_notes({"routing": {"tipo": "tool_diretto", "tool": None}}) == (
        "Composizione dal modello")
    assert render_template_notes({"routing": {"tipo": "tool_enhance", "tool": ""},
                                  "avvertenze": ["Bozza indicativa"]}) == (
        "Composizione dal modello · Bozza indicativa")
    assert render_reference(None) == "Caso simile: nessuno"
    assert render_reference(
        {"name": "ricorso_rossi.docx", "chars": 12345, "troncato": False}) == (
        "Caso simile: ricorso_rossi.docx (12.345 caratteri)")
    assert render_reference(
        {"name": "x.odt", "chars": 70000, "troncato": True}).endswith(", troncato)")
    assert render_partitions(
        [{"titolo": "Base: Ricorso"}, {"titolo": "Premesse in fatto"}], ["[SEDE]"]) == [
        "✓ Base: Ricorso", "✓ Premesse in fatto", "… segnaposto aperti: 1"]
    assert render_field_label(
        {"nome": "importo", "tipo": "numero", "obbligatorio": True}) == "importo * (numero)"
    assert render_field_label(
        {"nome": "provvisoria_esecuzione", "tipo": "sino", "obbligatorio": False}) == (
        "provvisoria_esecuzione (sì/no)")
    assert render_question_label(
        {"campo": "sede", "domanda": "Sede del tribunale?", "esempio": "Milano",
         "tipo": "testo"}) == "Sede del tribunale? (es. Milano)"
    assert render_question_label(
        {"campo": "d", "domanda": "Data?", "esempio": "", "tipo": "data"}) == "Data? (data)"
    assert render_questions_hint(3) == (
        "Il modello ha bisogno di 3 dati: rispondi e premi Continua.")
    assert render_riepilogo("Calcoli: CU 129,50").startswith("Riepilogo della redazione:\n")
    view = {"template": None, "started": False, "done": False, "questions": [],
            "stopped": None, "busy": False}
    assert render_draft_status(view) == "Scegli un atto"
    view["template"] = {"tipo_atto": "x"}
    assert render_draft_status(view) == "Compila i campi obbligatori"
    view.update(started=True, busy=True)
    assert render_draft_status(view) == "Redazione in corso…"
    view.update(busy=False, questions=[{"campo": "a"}])
    assert render_draft_status(view) == "In attesa delle tue risposte (pannello Domande)"
    view.update(questions=[], stopped="iterations")
    assert render_draft_status(view) == "Interrotta: premi Continua la redazione"
    view.update(stopped=None, done=True)
    assert render_draft_status(view) == "Redazione completata"
    # M6: the base-generation failure is part of the state, so the line survives a rebuild
    view.update(done=False, base_errore="strumento decreto_ingiuntivo non disponibile")
    assert render_draft_status(view) == (
        "Base non generata: strumento decreto_ingiuntivo non disponibile")
    view.update(questions=[{"campo": "a"}])
    assert render_draft_status(view) == (
        "Base non generata: strumento decreto_ingiuntivo non disponibile")
    view.update(questions=[], busy=True)
    assert render_draft_status(view) == "Redazione in corso…"       # the turn wins while it runs
    view.update(busy=False, done=True)
    assert render_draft_status(view) == "Redazione completata"      # a later turn made a base
