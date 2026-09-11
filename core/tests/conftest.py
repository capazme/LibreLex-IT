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
                           fail_first: set[str] | None = None) -> tuple[FastMCP, dict]:
    verdicts = verdicts or {}
    articles = {"art. 2043 c.c.": ARTICLE_2043} if articles is None else articles
    fail_first = set(fail_first or ())
    calls: dict = {"verifica": [], "cite": []}
    server = FastMCP("Legal IT (fake)", version=version)

    @server.tool()
    async def verifica_citazioni(
        citazioni: str, archivio: str = "tutti", formato: str = "markdown",
    ) -> str:
        """Fake verifier."""
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
        data = {"formato": "json", "citazioni": rows, "troncato": len(refs) > 20, "limite": 20,
                "avvertenza": "La verifica accerta l'esistenza...", "errore": None}
        return json.dumps(data, ensure_ascii=False) if formato == "json" else "| tabella |"

    @server.tool()
    async def cite_law(
        reference: str, include_annotations: bool = False, formato: str = "markdown",
    ) -> str:
        """Fake norm lookup."""
        calls["cite"].append(reference)
        art = articles.get(reference)
        if art is None:
            data = {"formato": "json", "riferimento": reference, "articolo": "", "atto": {},
                    "url": "", "urn": None, "fonte": "", "testo": "",
                    "errore": f"atto '{reference}' non riconosciuto",
                    "data_consultazione": date.today().isoformat()}
        else:
            data = {"formato": "json", **art, "data_consultazione": date.today().isoformat()}
        return json.dumps(data, ensure_ascii=False) if formato == "json" else "**Fonte**: fake"

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

    return server, calls


@pytest.fixture
def fake_legal():
    return make_fake_legal_server()
