# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Shared fixtures: an in-process fake of mcp-legal-it with the JSON contract of spec §10."""
from __future__ import annotations

import json
from datetime import date

import pytest
from fastmcp import FastMCP

ARTICLE_2043 = {
    "riferimento": "art. 2043 c.c.", "articolo": "2043",
    "atto": {
        "tipo_atto": "codice civile", "data": "", "numero_atto": "", "descrizione": "codice civile",
    },
    "url": "https://www.normattiva.it/uri-res/N2Ls?"
           "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2043",
    "urn": "urn:nir:stato:regio.decreto:1942-03-16;262:2~art2043",
    "fonte": "normattiva",
    "testo": "Qualunque fatto doloso o colposo, che cagiona ad altri un danno ingiusto, obbliga "
             "colui che ha commesso il fatto a risarcire il danno.",
    "errore": None,
}


def make_fake_legal_server(verdicts: dict[str, tuple[str, str]] | None = None,
                           articles: dict[str, dict] | None = None,
                           version: str = "2.14.0",
                           fail_first: set[str] | None = None,
                           json_contract: bool = True) -> tuple[FastMCP, dict]:
    verdicts = verdicts or {}
    articles = {"art. 2043 c.c.": ARTICLE_2043} if articles is None else articles
    fail_first = set(fail_first or ())
    calls: dict = {"verifica": [], "cite": []}
    server = FastMCP("Legal IT (fake)", version=version)

    def _verifica_rows(citazioni: str) -> tuple[list[dict], list[str]]:
        refs = [r.strip() for r in citazioni.split("\n") if r.strip()]
        calls["verifica"].append(refs)
        rows = []
        for i, r in enumerate(refs[:20], start=1):
            tipo = "sentenza" if r.lower().startswith("cass") else "norma"
            verdetto, nota = verdicts.get(r, ("verificata", "Fonte: fake"))
            if r in fail_first:
                fail_first.discard(r)
                verdetto, nota = "non verificata", "Italgiure non raggiungibile"
            rows.append({"n": i, "citazione": r, "tipo": tipo, "verdetto": verdetto, "nota": nota})
        return rows, refs

    def _cite_data(reference: str) -> dict:
        calls["cite"].append(reference)
        art = articles.get(reference)
        if art is None:
            return {"formato": "json", "riferimento": reference, "articolo": "", "atto": {},
                    "url": "", "urn": None, "fonte": "", "testo": "",
                    "errore": f"atto '{reference}' non riconosciuto",
                    "data_consultazione": date.today().isoformat()}
        return {"formato": "json", **art, "data_consultazione": date.today().isoformat()}

    if json_contract:
        @server.tool()
        async def verifica_citazioni(
            citazioni: str, archivio: str = "tutti", formato: str = "markdown",
        ) -> str:
            """Fake verifier."""
            rows, refs = _verifica_rows(citazioni)
            data = {"formato": "json", "citazioni": rows, "troncato": len(refs) > 20,
                    "limite": 20, "avvertenza": "La verifica accerta l'esistenza...",
                    "errore": None}
            return json.dumps(data, ensure_ascii=False) if formato == "json" else "| tabella |"

        @server.tool()
        async def cite_law(
            reference: str, include_annotations: bool = False, formato: str = "markdown",
        ) -> str:
            """Fake norm lookup."""
            data = _cite_data(reference)
            return json.dumps(data, ensure_ascii=False) if formato == "json" else "**Fonte**: fake"
    else:
        @server.tool()
        async def verifica_citazioni(citazioni: str, archivio: str = "tutti") -> str:
            """Fake verifier, pre-JSON-contract: always markdown."""
            _verifica_rows(citazioni)
            return "| tabella |"

        @server.tool()
        async def cite_law(reference: str, include_annotations: bool = False) -> str:
            """Fake norm lookup, pre-JSON-contract: always markdown."""
            _cite_data(reference)
            return "**Fonte**: fake"

    calls.update({"sentenze": [], "consulta": []})

    @server.tool()
    async def leggi_sentenza(
        numero: int, anno: int, sezione: str = "", archivio: str = "tutti",
    ) -> str:
        """Fake Italgiure reader: 12345/2024 exists, everything else does not."""
        calls["sentenze"].append((numero, anno, sezione))
        if (numero, anno) != (12345, 2024):
            return f"Errore: nessuna sentenza n. {numero}/{anno} trovata su Italgiure"
        return ("# Cass. civ., Sez. Lavoro, sentenza n. 12345/2024\n\n"
                "**Data**: 12/03/2024\n\n## Massima\n\nIl datore di lavoro risponde del danno "
                "da demansionamento anche in assenza di dolo.\n\n## Testo\n\nFATTI DI CAUSA. "
                + "La ricorrente lamentava... " * 400)

    @server.tool()
    async def leggi_pronuncia_costituzionale(numero: int, anno: int) -> str:
        """Fake Consulta reader: 1/2020 exists."""
        calls["consulta"].append((numero, anno))
        if (numero, anno) != (1, 2020):
            return f"Errore: pronuncia n. {numero}/{anno} non trovata"
        return "# Corte costituzionale, sentenza n. 1/2020\n\nEpigrafe...\n\nRitenuto in fatto..."

    calls.update({"modelli": [], "generatori": [], "calcoli": []})

    _CATALOGO = {
        "decreto_ingiuntivo_ordinario": {
            "categoria": "atti_introduttivi",
            "descrizione": "Ricorso per decreto ingiuntivo — credito ordinario",
            "routing": {"tipo": "tool_diretto", "tool": "decreto_ingiuntivo",
                        "parametri_fissi": {"tipo_credito": "ordinario"}},
            "campi_obbligatori": ["creditore", "debitore", "importo"],
            "campi_opzionali": ["provvisoria_esecuzione"],
            "tool_calcolo": ["contributo_unificato", "parcella_avvocato_civile"],
            "riferimenti_normativi": ["artt. 633-656 c.p.c.", "DPR 115/2002"],
            "avvertenze": ["Bozza indicativa, richiede completamento con dati specifici del caso"],
        },
        "atto_di_citazione": {
            "categoria": "atti_introduttivi",
            "descrizione": "Atto di citazione ordinario",
            "routing": {"tipo": "resource", "resource": "atti://citazione", "fase": 3},
            "campi_obbligatori": ["attore", "convenuto", "oggetto"],
            "campi_opzionali": [],
            "tool_calcolo": ["contributo_unificato"],
            "riferimenti_normativi": ["art. 163 c.p.c."],
            "avvertenze": [],
        },
    }

    @server.tool()
    async def genera_modello_atto(tipo_atto: str, parametri: dict | None = None) -> dict:
        """Fake template lookup: mirrors the catalogo / cerca / lookup modes of mcp-legal-it."""
        parametri = parametri or {}
        calls["modelli"].append((tipo_atto, parametri))
        if tipo_atto == "catalogo":
            return {"totale_tipi": len(_CATALOGO), "categorie": ["atti_introduttivi"],
                    "catalogo": {"atti_introduttivi": [
                        {"tipo_atto": k, "descrizione": v["descrizione"], "tier": 1}
                        for k, v in _CATALOGO.items()]}}
        if tipo_atto == "cerca":
            query = str(parametri.get("query", "")).lower()
            hits = [{"tipo_atto": k, "descrizione": v["descrizione"],
                     "categoria": v["categoria"], "tier": 1}
                    for k, v in _CATALOGO.items() if query in (k + v["descrizione"]).lower()]
            return {"query": query, "risultati": hits, "totale": len(hits)}
        entry = _CATALOGO.get(tipo_atto)
        if entry is None:
            return {"errore": f"Tipo atto '{tipo_atto}' non trovato nel catalogo",
                    "suggerimenti": [], "nota": "Usare tipo_atto='catalogo' per l'elenco completo"}
        out = {"tipo_atto": tipo_atto, **{k: v for k, v in entry.items() if k != "routing"},
               "campi_mancanti": [c for c in entry["campi_obbligatori"] if c not in parametri]}
        routing = entry["routing"]
        if routing["tipo"] == "tool_diretto":
            out.update(tool_diretto=routing["tool"], parametri_fissi=routing["parametri_fissi"],
                       istruzioni=f"Chiamare il tool `{routing['tool']}` con i parametri indicati.")
        else:
            out.update(resource_modello=routing["resource"], disponibile_da_fase=routing["fase"],
                       istruzioni=(f"Resource `{routing['resource']}` non ancora disponibile; "
                                   "comporre l'atto manualmente seguendo la struttura e i campi "
                                   "indicati, e chiamare i tool di calcolo indicati."))
        return out

    @server.tool()
    async def lista_categorie_atti() -> dict:
        """Fake category list."""
        calls["modelli"].append(("categorie", {}))
        return {"categorie": [{"nome": "atti_introduttivi", "totale": len(_CATALOGO)}],
                "totale_atti": len(_CATALOGO)}

    @server.tool()
    async def decreto_ingiuntivo(creditore: str, debitore: str, importo: float,
                                 tipo_credito: str = "ordinario",
                                 provvisoria_esecuzione: bool = False) -> dict:
        """Fake generator: the shape of the real one (bozza, giudice, contributo unificato)."""
        calls["generatori"].append(("decreto_ingiuntivo", creditore, debitore, importo))
        giudice = "Giudice di Pace" if importo <= 10000 else "Tribunale"
        return {"tipo_atto": "ricorso_decreto_ingiuntivo", "giudice_competente": giudice,
                "importo": importo, "contributo_unificato": 129.5,
                "bozza": (f"RICORSO PER DECRETO INGIUNTIVO\n(Artt. 633 e ss. c.p.c.)\n\n"
                          f"ILL.MO SIG. {giudice.upper()} DI [SEDE]\n\n{creditore} vanta un "
                          f"credito di Euro {importo:,.2f} nei confronti di {debitore}.")}

    @server.tool()
    async def contributo_unificato(valore_causa: float, tipo_procedimento: str = "cognizione",
                                   grado: str = "primo") -> dict:
        """Fake calculator: a flat amount per band, enough to see it quoted in the draft."""
        calls["calcoli"].append(("contributo_unificato", valore_causa, tipo_procedimento))
        return {"valore_causa": valore_causa, "tipo_procedimento": tipo_procedimento,
                "contributo_unificato": 129.5 if valore_causa <= 26000 else 259.0,
                "riferimento": "DPR 115/2002, art. 13"}

    @server.tool()
    async def interessi_mora(capitale: float, data_inizio: str, data_fine: str) -> dict:
        """Fake calculator: 12% simple interest on the period, no calendar."""
        calls["calcoli"].append(("interessi_mora", capitale, data_inizio, data_fine))
        return {"capitale": capitale, "data_inizio": data_inizio, "data_fine": data_fine,
                "tasso": 12.0, "interessi": round(capitale * 0.12, 2),
                "totale": round(capitale * 1.12, 2), "riferimento": "D.Lgs. 231/2002"}

    return server, calls


@pytest.fixture
def fake_legal():
    return make_fake_legal_server()
