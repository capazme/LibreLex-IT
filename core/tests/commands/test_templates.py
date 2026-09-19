# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
import pytest

from librelex_core.commands.templates import TemplateCatalogue, TemplateNotFound
from librelex_core.mcp.client import LegalToolsClient
from tests.conftest import make_fake_legal_server


async def test_list_flattens_the_catalogue_and_searches():
    server, calls = make_fake_legal_server()
    async with LegalToolsClient(server) as tools:
        cat = TemplateCatalogue(tools)
        out = await cat.list()
        assert out["totale"] == 3 and [m["tipo_atto"] for m in out["modelli"]] == [
            "decreto_ingiuntivo_ordinario", "atto_di_citazione", "precetto_ordinario"]
        assert out["modelli"][0]["categoria"] == "atti_introduttivi"
        await cat.list()                                    # cached
        assert calls["modelli"].count(("catalogo", {})) == 1
        hits = await cat.list("precetto")
        assert [m["tipo_atto"] for m in hits["modelli"]] == ["precetto_ordinario"]
        assert hits["query"] == "precetto"


async def test_info_types_the_fields_from_the_direct_tool_schema():
    server, _ = make_fake_legal_server()
    async with LegalToolsClient(server) as tools:
        cat = TemplateCatalogue(tools)
        info = await cat.info("decreto_ingiuntivo_ordinario", await tools.tool_specs())
        assert info["routing"] == {"tipo": "tool_diretto", "tool": "decreto_ingiuntivo",
                                   "parametri_fissi": {"tipo_credito": "ordinario"},
                                   "resource": None}
        campi = {c["nome"]: c for c in info["campi"]}
        assert [c["nome"] for c in info["campi"]] == ["creditore", "debitore", "importo",
                                                      "provvisoria_esecuzione"]
        assert campi["importo"]["tipo"] == "numero" and campi["importo"]["obbligatorio"] is True
        assert campi["provvisoria_esecuzione"]["tipo"] == "sino"
        assert campi["provvisoria_esecuzione"]["obbligatorio"] is False
        assert info["tool_calcolo"] == ["contributo_unificato", "parcella_avvocato_civile"]
        res = await cat.info("atto_di_citazione", await tools.tool_specs())
        assert res["routing"]["tipo"] == "resource" and res["routing"]["resource"] == (
            "atti://citazione")
        assert all(c["tipo"] == "testo" for c in res["campi"])
        with pytest.raises(TemplateNotFound, match="non trovato"):
            await cat.info("inesistente", [])
