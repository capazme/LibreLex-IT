# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Plain-text (Italian) rendering of core results for the panel transcript (spec §5.1, §7.1)."""
from __future__ import annotations

VERDICT_MARKERS = {
    "verificata": "✓", "inesistente": "✗", "non trovata": "✗", "metadati discordanti": "✗",
    "non verificata": "?", "non verificabile": "·", "da controllare a mano": "·",
}


def citation_label(citazione: str, verdetto: str | None = None, occorrenze: int = 1) -> str:
    marker = f"{VERDICT_MARKERS.get(verdetto, '?')} " if verdetto else ""
    count = f" ×{occorrenze}" if occorrenze > 1 else ""
    return f"{marker}{citazione}{count}"


def _items(entries: list[dict], with_verdict: bool) -> list[tuple[str, str, str]]:
    items = []
    for e in entries:
        occ = e.get("occorrenze") or []
        where = occ[0]["paragraph_id"] if occ else "?"
        verdetto = e.get("verdetto") if with_verdict else None
        items.append((citation_label(e["citazione"], verdetto, len(occ)), where, e["citazione"]))
    return items


def render_verify_summary(summary: dict) -> tuple[str, list[tuple[str, str, str]]]:
    lines = [
        f"Verificate {summary.get('citazioni_uniche', 0)} citazioni "
        f"({summary.get('citazioni_totali', 0)} occorrenze), "
        f"{summary.get('commenti_inseriti', 0)} segnalazioni inserite."
    ]
    per = summary.get("per_verdetto") or {}
    if per:
        lines.append("  " + " · ".join(f"{k}: {v}" for k, v in per.items()))
    problems = summary.get("problemi") or []
    if problems:
        lines.append("Problemi (commenti nel documento):")
        for pr in problems:
            occ = pr.get("occorrenze") or []
            where = occ[0]["paragraph_id"] if occ else "?"
            nota = f" — {pr['nota']}" if pr.get("nota") else ""
            lines.append(f"- {pr['citazione']}: {pr['verdetto']} ({where}){nota}")
    else:
        lines.append("Nessun problema rilevato.")
    for key, label in (
        ("da_controllare_a_mano", "Da controllare a mano"),
        ("non_interpretabili", "Non interpretabili"),
        ("non_verificabili", "Non verificabili automaticamente"),
        ("da_riprovare", "Da riprovare (fonte non raggiungibile)"),
    ):
        values = summary.get(key) or []
        if values:
            lines.append(f"{label}: " + "; ".join(values))
    elenco = summary.get("elenco")
    if elenco:
        items = _items(elenco, True)
    else:
        items = [(f"{pr['citazione']} · {pr['verdetto']}",
                  (pr.get("occorrenze") or [{}])[0].get("paragraph_id", "?"), pr["citazione"])
                 for pr in problems]
    return "\n".join(lines), items


def render_list_summary(summary: dict) -> tuple[str, list[tuple[str, str, str]]]:
    lines = [f"Trovate {summary.get('citazioni_uniche', 0)} citazioni "
             f"({summary.get('citazioni_totali', 0)} occorrenze). Clic su una voce per il testo."]
    values = summary.get("non_interpretabili") or []
    if values:
        lines.append("Non interpretabili: " + "; ".join(values))
    return "\n".join(lines), _items(summary.get("citazioni") or [], False)


def render_show_text(summary: dict) -> str:
    source = summary.get("fonte") or "fonte ufficiale"
    if summary.get("url"):
        source = f"{source}, {summary['url']}"
    lines = [f"— {summary.get('titolo') or summary.get('riferimento', '?')} ({source}) —"]
    if summary.get("massima"):
        lines.append(f"Massima: {summary['massima']}")
        lines.append("")
    lines.append(summary.get("testo") or "(testo non disponibile)")
    if summary.get("troncato"):
        lines.append("[testo abbreviato per il pannello]")
    return "\n".join(lines)


def render_insert_summary(summary: dict) -> str:
    ins = summary.get("inserted") or {}
    rng = f"{ins.get('from_id', '?')}-{ins.get('to_id', '?')}"
    return (f"Inserito {summary.get('riferimento', '?')} come revisione "
            f"(paragrafi {rng}, segnalibro {summary.get('bookmark', '?')}).\n"
            f"Fonte: {summary.get('url', '')}")


def render_error(code: str, message: str) -> str:
    return f"Errore ({code}): {message}"
