# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Plain-text (Italian) rendering of core results for the panel transcript (spec §5.1, §7.1)."""
from __future__ import annotations

from librelex_ext.letterheads import NONE_LABEL

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


def render_error(code: str, message: str, config_path: str = "") -> str:
    text = f"Errore ({code}): {message}"
    if code == "llm_config":
        text += (f"\nConfigura la sezione [llm] (preset, api_key, model) in {config_path} "
                 "e riavvia LibreOffice.")
    return text


def _it_thousands(n: int) -> str:
    """Italian-style grouping (dot separator), independent of the process locale."""
    return f"{n:,}".replace(",", ".")


def render_usage(usage: dict | None, totals: dict | None) -> str:
    """"Turno: <in> + <out> token · sessione: <total> token[ · costo: $<cost>]" (spec §5.1).

    ``sessione`` and ``costo`` are independent: each shows whenever its own data is
    available, so both can appear on the same line (e.g. a metered preset with running
    session totals).
    """
    if usage is None:
        return ""
    parts = [f"Turno: {_it_thousands(usage.get('input_tokens', 0))} + "
             f"{_it_thousands(usage.get('output_tokens', 0))} token"]
    if totals:
        total = totals.get("input_tokens", 0) + totals.get("output_tokens", 0)
        parts.append(f"sessione: {_it_thousands(total)} token")
    cost = usage.get("cost_usd")
    if cost is not None:
        parts.append(f"costo: ${cost:.2f}")
    return " · ".join(parts)


def render_consent(summary: dict) -> str:
    conservazione = "senza conservazione dati" if summary.get("zdr") else "con conservazione dati"
    scope = summary.get("scope")
    name = (summary.get("name") or "")[:120]
    if len(summary.get("name") or "") > 120:
        name += "..."
    if scope == "attachments":
        ambito = f"gli allegati del fascicolo ({name})"
    elif scope == "reference":
        ambito = f"l'atto di riferimento ({name})"
    elif scope == "selection":
        ambito = "il testo selezionato"
    else:
        ambito = "i paragrafi letti"
    return (f"Inviare al modello {summary.get('model')} su {summary.get('endpoint_host')} "
            f"({conservazione}) {ambito} ({_it_thousands(summary.get('chars', 0))} caratteri)?")


def render_draft_consent_status(summary: dict) -> str:
    """The Redazione panel's DraftStatus line while a consent is pending (design review §5
    item 8, illustrated there for an attachments-scope request: "In attesa del tuo consenso:
    Doc. 1, Doc. 2 (24.100 caratteri)"): a one-line summary, shorter than ``render_consent``
    (which stays the text of the consent block itself, on both panels). ``ConsentSummary.name``
    is only set for the "attachments"/"reference" scopes; a plain document read during a draft
    turn ("selection"/"paragraphs") falls back to the model name, so the line never says "None".
    """
    name = summary.get("name") or summary.get("model") or ""
    chars = _it_thousands(summary.get("chars", 0))
    return f"In attesa del tuo consenso: {name} ({chars} caratteri)"


_STOP_NOTES = {
    "iterations": "[interrotto: limite di iterazioni]",
    "timeout": "[interrotto: tempo massimo]",
    "length": "[risposta troncata dal limite di lunghezza]",
    "cancelled": "[annullato]",
}


def render_turn_notes(summary: dict) -> list[str]:
    notes = []
    stopped = summary.get("stopped")
    if stopped:
        notes.append(_STOP_NOTES.get(stopped, f"[interrotto: {stopped}]"))
    for ins in summary.get("inserted") or []:
        notes.append(f"Inserito nei paragrafi {ins.get('from_id', '?')}-{ins.get('to_id', '?')}")
    flagged = summary.get("flagged") or []
    if flagged:
        notes.append("Riferimenti segnalati con un commento: " + ", ".join(flagged))
    unverified = summary.get("unverified") or []
    if unverified:
        notes.append("Riferimenti non verificati (fonte non disponibile): " + ", ".join(unverified))
    return notes


# --- guided drafting (spec §6, plan "Guided Drafting, Extension") ----------------------

_ROUTING_LABELS = {
    "tool_diretto": "Base deterministica: {tool}",
    "tool_enhance": "Base deterministica (adattata): {tool}",
    "resource": "Composizione dal modello (risorsa del catalogo)",
    "preventivo_procedura": "Preventivo: {tool}",
}

_TYPE_HINTS = {"numero": "numero", "data": "data", "sino": "sì/no"}


def render_template_notes(info: dict) -> str:
    """The routing line shown after a template is chosen: which base the core will use.

    A routing that names a tool but carries no tool name falls back to the generic line: the
    core composes from the model alone, and "Base deterministica: None" would name a
    generator that does not exist.
    """
    routing = info.get("routing") or {}
    tool = routing.get("tool")
    template = _ROUTING_LABELS.get(routing.get("tipo"), "Composizione dal modello")
    if "{tool}" in template and not tool:
        template = "Composizione dal modello"
    text = template.format(tool=tool)
    avvertenze = info.get("avvertenze") or []
    if avvertenze:
        text += " · " + "; ".join(avvertenze)
    return text


def render_reference(ref: dict | None) -> str:
    """The "Caso simile" label in the Redazione panel: none, or name, size and truncation."""
    if not ref:
        return "Caso simile: nessuno"
    suffix = ", troncato" if ref.get("troncato") else ""
    return f"Caso simile: {ref['name']} ({_it_thousands(ref['chars'])} caratteri{suffix})"


def render_partitions(partizioni: list[dict], open_placeholders: list[str]) -> list[str]:
    """The "Partizioni inserite" list, plus a trailing count of placeholders still open."""
    labels = [f"✓ {p['titolo']}" for p in partizioni]
    if open_placeholders:
        labels.append(f"… segnaposto aperti: {len(open_placeholders)}")
    return labels


def render_base_error(message: str) -> str:
    """The status (and transcript) line of a base the core could not generate."""
    return f"Base non generata: {message}"


def render_draft_status(view: dict) -> str:
    """The "DraftStatus" line: step-aware over the four Redazione panel steps (design §3).

    ``view`` is ``{**session.draft_view, "busy": session._draft_request}``; ``step`` defaults
    to 1 when absent so a session that does not yet carry it (Task 1) still renders a sane
    line. ``base_errore`` is read from the view rather than pushed once by the turn that
    reported it, so a rebuilt panel is told again; a turn that later produced a base clears
    it (the core sends the key on every draft final), and a completed drafting never shows it.

    Every line but "Scegli un atto" (nothing to do yet: step 1, no template) carries a
    "Passo N di 4 · " prefix (design review §5 item 5): a refusal (``Session._refuse_draft``)
    writes its own line straight to the view and never goes through here, so it stays
    unprefixed too.
    """
    step = view.get("step", 1)
    if step == 1:
        if not view.get("template"):
            return "Scegli un atto"
        text = "Compila i campi obbligatori e premi Avvia redazione"
    elif step == 2:
        count = len(view.get("questions") or [])
        text = ("Rispondi alla domanda e premi Continua" if count == 1
                else f"Rispondi alle {count} domande e premi Continua")
    elif step == 3:
        text = ("Redazione in corso: il modello lavora sul documento" if view.get("busy")
                else "In attesa del core")
    else:
        base_errore = view.get("base_errore")
        if base_errore and not view.get("done"):
            text = render_base_error(base_errore)
        elif view.get("done"):
            text = "Redazione completata: Verifica citazioni, poi Nuova redazione"
        elif view.get("stopped"):
            text = "Interrotta: Riprendi per continuare"
        else:
            text = "Turno concluso: Riprendi per continuare o Nuova redazione"
    return f"Passo {step} di 4 · {text}"


def render_riepilogo(riepilogo: str) -> str:
    return "Riepilogo della redazione:\n" + riepilogo


def render_questions_hint(n: int) -> str:
    return (f"Il modello ha bisogno di {n} dati: rispondi e premi Continua; "
            "una casella vuota vale come risposta non disponibile.")


# --- drafting workbench (spec §3, §4.2, plan "Drafting Workbench, Extension") -----------

EXPECTED_PARTITIONS = ("Intestazione", "Parti", "Premesse", "Diritto", "Conclusioni", "Allegati")


def render_expected_partitions(expected: list[str], partitions: list[dict]) -> list[str]:
    """The expected-partitions checklist: a name is marked found by its first five letters
    occurring in some inserted partition's title (case-insensitive, no word boundaries).
    """
    titles = " ".join((p.get("titolo") or "").lower() for p in partitions)
    marks = []
    for name in expected:
        found = name.lower()[:5] in titles
        marks.append(("✓ " if found else "· ") + name)
    return marks


def render_attachments(attachments: list[dict]) -> list[str]:
    lines = []
    for a in attachments:
        suffix = ", troncato" if a.get("troncato") else ""
        lines.append(
            f"Doc. {a['n']} · {a['name']} ({_it_thousands(a['chars'])} caratteri{suffix})")
    return lines


def render_log_insert(markdown: str) -> str:
    """The drafting log line for one inserted block: its first non-empty line, unadorned."""
    first = ""
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped:
            first = stripped.lstrip("#->* ")
            break
    if len(first) > 60:
        first = first[:60] + "…"
    return f"Inserito: {first}"


def render_summary(summary: dict) -> str:
    """The end-of-drafting summary line (design §3): riepilogo, attachments, open
    placeholders, a missing base and a stop note, each only when present.
    """
    lines = []
    riepilogo = summary.get("riepilogo")
    if riepilogo:
        lines.append("Riepilogo:\n" + riepilogo)
    allegati = summary.get("allegati")
    if allegati:
        lines.append("Allegati: " + "; ".join(f"Doc. {a['n']} {a['name']}" for a in allegati))
    aperti = summary.get("segnaposto_aperti")
    if aperti:
        lines.append("Segnaposto aperti: " + ", ".join(aperti))
    base_errore = summary.get("base_errore")
    if base_errore:
        lines.append(render_base_error(base_errore))
    stopped = summary.get("stopped")
    if stopped:
        lines.append(_STOP_NOTES.get(stopped, f"[interrotto: {stopped}]"))
    return "\n".join(lines) if lines else "Nessun riepilogo."


def render_letterhead_labels(entries: list[dict]) -> list[str]:
    return [NONE_LABEL, *(e["name"] for e in entries)]


def render_field_label(campo: dict) -> str:
    """A "Redazione" field row label: name, a mandatory marker, and a type hint."""
    label = campo["nome"]
    if campo.get("obbligatorio"):
        label += " *"
    hint = _TYPE_HINTS.get(campo.get("tipo"))
    if hint:
        label += f" ({hint})"
    return label


def render_question_label(q: dict) -> str:
    """A "Domande" question row label: the question, an example, and a type hint."""
    label = q["domanda"]
    if q.get("esempio"):
        label += f" (es. {q['esempio']})"
    hint = _TYPE_HINTS.get(q.get("tipo"))
    if hint:
        label += f" ({hint})"
    return label
