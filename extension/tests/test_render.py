# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
from librelex_ext.render import render_error, render_insert_summary, render_verify_summary

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
    assert items == [("Cass. n. 99999/2024 · inesistente", "p:3"),
                     ("art. 13 co. 7 D.Lgs. 196/2003 · metadati discordanti", "fn:1/p:0")]


def test_verify_summary_with_no_problems():
    text, items = render_verify_summary({**SUMMARY, "problemi": [], "commenti_inseriti": 0,
                                         "per_verdetto": {"verificata": 4},
                                         "da_controllare_a_mano": [], "non_interpretabili": [],
                                         "da_riprovare": []})
    assert "Nessun problema rilevato." in text and items == []


def test_insert_summary_and_error():
    text = render_insert_summary({
        "riferimento": "art. 2043 c.c.", "url": "https://x",
        "bookmark": "LibreLex.norma.x", "inserted": {"from_id": "p:1", "to_id": "p:3"}})
    assert text == (
        "Inserito art. 2043 c.c. come revisione (paragrafi p:1-p:3, "
        "segnalibro LibreLex.norma.x).\nFonte: https://x")
    assert (render_error("busy", "un'altra richiesta è in corso")
            == "Errore (busy): un'altra richiesta è in corso")
