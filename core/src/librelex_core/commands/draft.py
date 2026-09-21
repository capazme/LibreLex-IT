# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Stateful, template-guided drafting (guided drafting design §3.2, §4.2-§4.5, §5.3).

A drafting lives in ``DocSession.draft`` and advances one action at a time: ``start`` (the
lawyer picked an act and filled the template's fields), ``answer`` (the answers to the
questions the model asked) and ``continue`` (a free instruction, or a resume after an
iteration stop). The user message of every turn is rebuilt from that state, so the model
never depends on the compacted tool results of an earlier turn.

Four hooks (``chiedi_dati``, ``redazione_completata``, ``leggi_atto_riferimento``,
``leggi_allegato``) are added to the loop for the drafting turns only: the first two end the
turn in an orderly way, the other two serve the reference act and the case attachments after
consent. Everything else (grounding on write, consent for document reads, limits, cancellation)
is the ordinary agent turn.
"""
from __future__ import annotations

import json
import re
from typing import Any

from librelex_core import protocol as p
from librelex_core.agent.loop import (
    BAD_ARGUMENTS,
    CONSENT_DENIED,
    WRITE_AUTHOR,
    AgentDeps,
    Emit,
    Hook,
    TurnOutcome,
    run_turn_with,
)
from librelex_core.agent.prompt import load_recipe, wrap_data
from librelex_core.agent.registry import ToolRegistry
from librelex_core.agent.state import (
    MAX_REFERENCE_CHARS,
    DocSession,
    DraftState,
    attachments_chars,
    attachments_label,
)
from librelex_core.agent.textclean import clean_tool_names
from librelex_core.commands.templates import FIELD_TYPES, field_type
from librelex_core.document import DocumentError
from librelex_core.mcp.client import ToolError

PROFILE = "draft"
BASE_UNDO = "LibreLex: base {tipo_atto}"
BASE_BOOKMARK = "LibreLex.atto.{tipo_atto}"
ACTIONS = ("start", "answer", "continue")
BAD_ACTION = "azione non valida: usa start, answer o continue"
MAX_QUESTIONS = 8
TOO_MANY_QUESTIONS = "ERRORE: al massimo otto domande, le altre sono state scartate"
QUESTIONS_SENT = "Domande inviate all'utente: attendi le risposte nel prossimo turno."
DRAFT_DONE = "Redazione registrata come completata."
NO_REFERENCE = "ERRORE: nessun atto di riferimento caricato"
NO_ATTACHMENTS = "ERRORE: nessun allegato caricato"
BASE_BAD_RESPONSE = "risposta non valida del generatore"
# The four states of the deterministic base, as the user message tells them (design §3.2,
# §4.3): failed, absent, inserted, data only.
BASE_FAILED = ("Generazione della base fallita ({motivo}): componi dal modello seguendo la "
               "struttura indicata.")
BASE_NONE = "Il modello d'atto non prevede un generatore: componi dal modello."
BASE_DATA_ONLY = "Nessun testo base inserito: il generatore ha restituito solo dati (vedi sotto)."

# "[...]" of the deterministic generators and "{...}" of the published templates; the length
# cap keeps a stray bracket in the act's prose from becoming a placeholder.
PLACEHOLDER_RE = re.compile(r"\[[^\[\]\n]{1,60}\]|\{[a-z_]+\}")
_YES = ("sì", "si", "s", "true", "1", "yes")
# A dot that separates thousands: exactly three digits after it, then a non-digit or the
# end of the value ("1.234.567", "12.000"); anything else is a decimal point ("12.5").
_THOUSANDS_DOT_RE = re.compile(r"\.(?=\d{3}(?:\D|$))")
# What a lawyer types around an amount in the panel and a generator cannot parse.
_CURRENCY_RE = re.compile(r"€|\beuro\b|\beur\b", re.IGNORECASE)


def undo_label(tipo_atto: str) -> str:
    """Undo label of every model write of a drafting: one step per drafting, per act."""
    return f"LibreLex: redazione {tipo_atto}"


# --- pure helpers ------------------------------------------------------------

def placeholders(text: str) -> list[str]:
    """The placeholders of a base text, unique and in order of appearance."""
    out: list[str] = []
    for match in PLACEHOLDER_RE.finditer(text):
        if match.group(0) not in out:
            out.append(match.group(0))
    return out


def base_text(result: dict) -> str | None:
    """The act text of a generator result, or None when it carries none.

    The generators of mcp-legal-it do not agree on one name: 16 return ``testo``,
    ``decreto_ingiuntivo`` returns ``bozza_ricorso``, ``sollecito_pagamento``
    ``testo_lettera`` and the three ``preventivo_*`` ``testo_preventivo``. Order (controller
    ruling): ``testo``, then the other ``testo*`` keys sorted, then the ``bozza*`` keys
    sorted; the first one holding a non-empty string wins.
    """
    for key in _text_keys(result):
        value = result.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _text_keys(result: dict) -> list[str]:
    """The keys that may carry the act text, in the order ``base_text`` tries them."""
    others = sorted(k for k in result if k.startswith("testo") and k != "testo")
    return ["testo", *others, *sorted(k for k in result if k.startswith("bozza"))]


def _without_text(result: dict) -> dict:
    """The generator's data alone: everything that is not one of the act-text keys."""
    return {k: v for k, v in result.items() if not k.startswith(("testo", "bozza"))}


def to_markdown(text: str) -> str:
    """Plain generator text to markdown: every line becomes a paragraph of the document.

    The generators lay their acts out with single newlines, which markdown would fold into
    one paragraph; ordered lists ("1. ...") keep working, each item being its own paragraph.
    """
    return re.sub(r"\n{2,}", "\n\n", re.sub(r"(?<!\n)\n(?!\n)", "\n\n", text.strip()))


# A line the generator's plain text already wrote as markdown (a heading, a list item, a
# quote): idempotency means such a line is never touched a second time.
_ALREADY_MARKDOWN_RE = re.compile(r"^(#{1,6}\s|-\s|>\s|\d+\.\s)")
# The court/judge heading of an act (design §5.3): always the first line after the title,
# always in capitals, and never mistaken for a section heading of the body.
_COURT_PREFIXES = ("ILL.MO", "TRIBUNALE", "GIUDICE DI PACE", "CORTE", "AL SIG.", "ALL'ILL.MO")
_PAREN_LINE_RE = re.compile(r"^\(.*\)$")
_MAX_SECTION_CHARS = 40
# The "[...]" placeholders of a line ("[LUOGO], [DATA]") are not the section rule's business:
# a line whose only capitals sit inside them is a data line, not a heading (P.Q.M., PREMESSO CHE).
_BRACKET_PLACEHOLDER_RE = re.compile(r"\[[^\]]*\]")


def _is_court_heading(stripped: str) -> bool:
    return stripped.upper().startswith(_COURT_PREFIXES)


def _is_short_all_caps(stripped: str) -> bool:
    """A short, all-capitals line: a section name (PREMESSO CHE, P.Q.M.), not a body line.

    Letters inside "[...]" placeholders are ignored: a line such as "[LUOGO], [DATA]" or
    "Avv. [LEGALE]" must keep at least one letter of its own, outside the placeholders, before
    it counts as a section name.
    """
    if len(stripped) > _MAX_SECTION_CHARS:
        return False
    without_placeholders = _BRACKET_PLACEHOLDER_RE.sub("", stripped)
    letters = [ch for ch in without_placeholders if ch.isalpha()]
    return (bool(letters) and not any(ch.isdigit() for ch in without_placeholders)
            and all(ch.isupper() for ch in letters))


def base_to_markdown(text: str) -> str:
    """A generator's plain act text, pre-formatted into the markdown conventions the model and
    the act styles both read (design §5.3): every line becomes its own paragraph; the first
    non-empty line is the act's title (``## ``); a line opening with the court's name
    (``ILL.MO``, ``TRIBUNALE``, ...) is the court heading (``# ``); a short all-capitals line
    elsewhere is a section name (``### ``); the line right after the title in parentheses
    (``(Artt. 633 e ss. c.p.c.)``) stays a plain paragraph; a line that already carries a
    markdown marker (heading, list item, quote) is left exactly as it is, so the function is
    idempotent on text the model already wrote in markdown.
    """
    lines = text.strip().split("\n")
    title_idx = next((i for i, line in enumerate(lines)
                       if line.strip()
                       and not _is_court_heading(line.strip())
                       and not _ALREADY_MARKDOWN_RE.match(line.strip())), None)
    paragraphs: list[str] = []
    for i, raw in enumerate(lines):
        stripped = raw.strip()
        if not stripped:
            continue
        if _ALREADY_MARKDOWN_RE.match(stripped):
            paragraphs.append(stripped)
        elif _is_court_heading(stripped):
            paragraphs.append(f"# {stripped}")
        elif i == title_idx:
            paragraphs.append(f"## {stripped}")
        elif title_idx is not None and i == title_idx + 1 and _PAREN_LINE_RE.match(stripped):
            paragraphs.append(stripped)
        elif _is_court_heading(stripped):
            paragraphs.append(f"# {stripped}")
        elif _is_short_all_caps(stripped):
            paragraphs.append(f"### {stripped}")
        else:
            paragraphs.append(stripped)
    return "\n\n".join(paragraphs)


def parse_number(value: str) -> float:
    """An Italian number as the generators want it, tolerant of both separators.

    A comma is always the decimal point, and every dot before it separates thousands. With
    no comma, a dot followed by exactly three digits (and nothing else that is a digit) is a
    thousands separator, so "12.000" is twelve thousand; any other dot is a decimal point, so
    "12.5" is twelve and a half. A currency symbol or name the lawyer typed in the panel
    ("€ 12.000", "12.000 euro") is dropped with every space. Raises ``ValueError`` when what
    is left is not a number.
    """
    text = "".join(_CURRENCY_RE.sub("", value).split())
    if "," in text:
        return float(text.replace(".", "").replace(",", "."))
    return float(_THOUSANDS_DOT_RE.sub("", text))


def _coerce(value: str, tipo: str) -> Any:
    if tipo == "numero":
        try:
            return parse_number(value)
        except ValueError:
            # The string goes through: the generator's own error reaches the panel as a
            # "Base non disponibile" status, which says more than a guess would.
            return value
    if tipo == "sino":
        return value.strip().lower() in _YES
    return value


def coerce_args(fields: dict[str, str], parametri_fissi: dict, schema_props: dict) -> dict:
    """The panel's string fields as the generator's parameters (Italian numbers and yes/no).

    Fields the generator does not declare are dropped; the catalogue's ``parametri_fissi``
    win over anything the lawyer typed.
    """
    out: dict[str, Any] = {}
    for name, value in fields.items():
        schema = schema_props.get(name)
        if schema is None:
            continue
        out[name] = _coerce(str(value), field_type(name, schema))
    out.update(parametri_fissi)
    return out


def _lines(values: dict[str, str]) -> str:
    return "\n".join(f"- {name}: {value}" for name, value in values.items())


# --- the deterministic base ---------------------------------------------------

async def insert_base(session: DocSession, deps: AgentDeps, emit: Emit,
                      request_id: str) -> None:
    """Generate and insert the act's deterministic base before the first model call (§3.2).

    Only for a ``tool_diretto`` routing whose tool the profile exposes: the formulas of the
    generator enter the document verbatim, and the model fills the placeholders instead of
    rewriting them. Nothing of the document leaves the machine, so no consent is needed.
    """
    draft = session.draft
    if draft is None:
        return
    template = draft.template
    routing = template.get("routing") or {}
    tool = routing.get("tool")
    if routing.get("tipo") != "tool_diretto" or not tool:
        return
    if deps.tools is None or tool not in deps.registry.names:
        return
    await emit(p.Status(request_id=request_id, text=f"Genero la base con {tool}"))
    spec = next((s for s in deps.specs if s.name == tool), None)
    props = (spec.input_schema.get("properties") or {}) if spec else {}
    args = coerce_args(draft.fields, dict(routing.get("parametri_fissi") or {}), props)
    try:
        text = await deps.tools.call(tool, **args)
    except ToolError as e:
        # The panel and the model both need to know: a missing base is not an empty template
        # but a generator that refused (final review, finding 3).
        draft.base_errore = e.message
        await emit(p.Status(request_id=request_id, text=f"Base non disponibile: {e.message}"))
        return
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        result = None
    if not isinstance(result, dict):
        draft.base_errore = BASE_BAD_RESPONSE
        await emit(p.Status(request_id=request_id,
                            text=f"Base non disponibile: {tool} non ha risposto in JSON"))
        return
    base = base_text(result)
    if base is None:
        # Deterministic data without an act text (a calculator-shaped result): nothing goes
        # into the document, but the data still reaches the model (final review, finding 2).
        draft.base = {"from_id": None, "to_id": None, "placeholders": [], "tool": tool,
                      "result": _without_text(result), "inserted": False}
        await emit(p.Status(request_id=request_id, text=(
            f"Nessun testo base da {tool}: passo i dati al modello")))
        return
    inserted = await deps.doc.insert_markdown(
        "end", base_to_markdown(base), BASE_UNDO.format(tipo_atto=draft.tipo_atto),
        bookmark=BASE_BOOKMARK.format(tipo_atto=draft.tipo_atto), author=WRITE_AUTHOR)
    open_placeholders = placeholders(base)
    draft.base = {
        "from_id": inserted.from_id, "to_id": inserted.to_id,
        "placeholders": open_placeholders, "tool": tool,
        "result": _without_text(result), "inserted": True,
    }
    draft.partitions.append({"titolo": f"Base: {template.get('descrizione', '')}",
                             "from_id": inserted.from_id, "to_id": inserted.to_id})
    await emit(p.Status(request_id=request_id, text=(
        f"Inserita la base deterministica ({tool}): "
        f"{len(open_placeholders)} segnaposto da riempire")))


# --- the user message of a drafting turn --------------------------------------

def draft_message(session: DocSession, action: str, message: str = "",
                  new_answers: dict[str, str] | None = None) -> str:
    """The whole drafting state as the user message of the turn (design §4.3).

    ``new_answers`` are the answers this very turn brings in: they are already merged into
    ``draft.answers``, and are listed apart so the model sees what it just received.
    """
    draft = session.draft
    if draft is None:
        raise ValueError("nessuna redazione in corso")
    template = draft.template
    blocks: list[str] = [
        f"Redazione guidata: {template.get('descrizione', '')} "
        f"({draft.tipo_atto}, {template.get('categoria', '')})."
    ]
    if draft.fields:
        blocks.append("Campi forniti dall'utente:\n" + _lines(draft.fields))
    if draft.notes:
        blocks.append(f"Note dell'utente: {draft.notes}")
    fresh = new_answers or {}
    previous = {k: v for k, v in draft.answers.items() if k not in fresh}
    if previous:
        blocks.append("Risposte alle domande precedenti:\n" + _lines(previous))
    if action == "answer" and fresh:
        blocks.append("Risposte appena ricevute:\n" + _lines(fresh))
    if action == "continue" and message:
        blocks.append(f"Istruzione dell'utente: {message}")
    reference = session.reference
    if reference:
        limit = f"{MAX_REFERENCE_CHARS:,}".replace(",", ".")
        cut = f", troncato ai primi {limit} caratteri" if reference.get("troncato") else ""
        blocks.append(
            f"Atto di riferimento disponibile: {reference['name']} "
            f"({reference['chars']} caratteri{cut}): leggilo con leggi_atto_riferimento "
            "prima di comporre.")
    if session.attachments:
        items = []
        for a in session.attachments:
            chars = f"{a['chars']:,}".replace(",", ".")
            note = ", troncato" if a["troncato"] else ""
            items.append(f"Doc. {a['n']} {a['name']} ({chars} caratteri{note})")
        blocks.append(
            "Allegati del fascicolo: " + "; ".join(items) + ": leggi con leggi_allegato "
            "quelli che servono ai fatti; l'elenco \"Si allegano\" segue questa numerazione.")
    if draft.base_errore:
        blocks.append(BASE_FAILED.format(motivo=draft.base_errore))
    elif draft.base is None:
        blocks.append(BASE_NONE)
    elif not draft.base.get("inserted", True):
        blocks.append(BASE_DATA_ONLY)
    else:
        aperti = (draft.base["aperti"] if "aperti" in draft.base
                  else draft.base["placeholders"])
        blocks.append(
            f"Base deterministica già nel documento (paragrafi {draft.base['from_id']}-"
            f"{draft.base['to_id']}), segnaposto ancora aperti: "
            + (", ".join(aperti) if aperti else "nessuno"))
    if draft.partitions:
        blocks.append("Partizioni già inserite:\n" + "\n".join(
            f"- {part['titolo']} ({part['from_id']}-{part['to_id']})"
            for part in draft.partitions))
    else:
        blocks.append("Partizioni già inserite: nessuna")
    if draft.done:
        blocks.append("Redazione già completata in un turno precedente: agisci solo "
                      "sull'istruzione dell'utente.")
    blocks.append(wrap_data("modello d'atto", json.dumps(
        {k: v for k, v in template.items() if k != "campi"}, ensure_ascii=False)))
    if draft.base:
        blocks.append(wrap_data(f"risultato di {draft.base['tool']}",
                                json.dumps(draft.base["result"], ensure_ascii=False)))
    blocks.append(load_recipe())
    return "\n\n".join(blocks)


# --- the hooks ----------------------------------------------------------------

CHIEDI_DATI_TOOL: dict = {"type": "function", "function": {
    "name": "chiedi_dati",
    "description": "Chiede all'utente i dati mancanti come campi da compilare (al massimo "
                   "otto) e chiude il turno: le risposte arrivano nel turno successivo.",
    "parameters": {"type": "object", "properties": {
        "domande": {"type": "array", "description": "Le domande, una per campo mancante.",
                    "items": {"type": "object", "properties": {
                        "campo": {"type": "string",
                                  "description": "Nome del campo da compilare."},
                        "domanda": {"type": "string",
                                    "description": "Domanda rivolta all'utente."},
                        "esempio": {"type": "string",
                                    "description": "Esempio di risposta, se utile."},
                        "tipo": {"type": "string", "enum": list(FIELD_TYPES),
                                 "description": "Tipo del campo (default: testo)."},
                    }, "required": ["campo", "domanda"]}},
    }, "required": ["domande"]}}}

REDAZIONE_COMPLETATA_TOOL: dict = {"type": "function", "function": {
    "name": "redazione_completata",
    "description": "Segnala che l'atto è completo e consegna il riepilogo finale (calcoli, "
                   "riferimenti verificati, allegati, avvertenze) in testo semplice; "
                   "chiude il turno.",
    "parameters": {"type": "object", "properties": {
        "riepilogo": {"type": "string", "description": "Riepilogo finale in testo semplice."},
    }, "required": ["riepilogo"]}}}

LEGGI_ATTO_RIFERIMENTO_TOOL: dict = {"type": "function", "function": {
    "name": "leggi_atto_riferimento",
    "description": "Testo dell'atto di riferimento (caso simile) caricato dall'utente, da "
                   "usare per struttura e stile, mai per i fatti.",
    "parameters": {"type": "object", "properties": {}}}}

LEGGI_ALLEGATO_TOOL: dict = {"type": "function", "function": {
    "name": "leggi_allegato",
    "description": "Testo dell'allegato numero N del fascicolo (fattura, delibera, decreto, "
                   "contratto...): i fatti del caso si prendono da qui.",
    "parameters": {"type": "object", "properties": {
        "numero": {"type": "integer", "description": "Numero dell'allegato (Doc. N)."},
    }, "required": ["numero"]}}}

HOOK_TOOLS: list[dict] = [CHIEDI_DATI_TOOL, REDAZIONE_COMPLETATA_TOOL,
                          LEGGI_ATTO_RIFERIMENTO_TOOL, LEGGI_ALLEGATO_TOOL]


def hooks_for(session: DocSession, deps: AgentDeps) -> tuple[dict[str, Hook], list[dict]]:
    """The four drafting hooks, closed over this session and these dependencies."""
    draft = session.draft
    # Snapshot at hook-building time (design §1's follow-up): `deps.registry` is rebuilt with
    # the hook tools right after this call returns, so a lazy read through `deps` inside the
    # hook would pick up the wrong list; the closure keeps the one that matters here, the
    # legal/document/internal tool names the model can mangle through a proxy. The four hook
    # tools themselves (leggi_allegato and the rest) are not yet in `deps.registry` at this
    # point either, so they are added by name: a riepilogo mentioning
    # "mcp__x__y_leggi_allegato" must still clean down to "leggi_allegato".
    names = list(deps.registry.names) + [t["function"]["name"] for t in HOOK_TOOLS]

    async def chiedi_dati(args: dict) -> tuple[str, str | None]:
        domande = args.get("domande")
        if not isinstance(domande, list) or not domande or draft is None:
            return BAD_ARGUMENTS, None
        cleaned: list[dict[str, Any]] = []
        for item in domande:
            if not isinstance(item, dict):
                return BAD_ARGUMENTS, None
            campo = str(item.get("campo") or "").strip()
            domanda = str(item.get("domanda") or "").strip()
            if not campo or not domanda:
                return BAD_ARGUMENTS, None
            tipo = str(item.get("tipo") or "").strip().lower()
            cleaned.append({"campo": campo, "domanda": domanda,
                            "esempio": str(item.get("esempio") or ""),
                            "tipo": tipo if tipo in FIELD_TYPES else "testo"})
        draft.questions = cleaned[:MAX_QUESTIONS]
        extra = "" if len(cleaned) <= MAX_QUESTIONS else f"\n{TOO_MANY_QUESTIONS}"
        return QUESTIONS_SENT + extra, "questions"

    async def redazione_completata(args: dict) -> tuple[str, str | None]:
        if draft is None:
            return BAD_ARGUMENTS, None
        draft.done = True
        draft.riepilogo = clean_tool_names(str(args.get("riepilogo") or ""), names)
        draft.questions = []
        return DRAFT_DONE, "done"

    async def leggi_atto_riferimento(args: dict) -> tuple[str, str | None]:
        reference = session.reference
        if reference is None:
            return NO_REFERENCE, None
        if session.reference_denied:
            # Already refused for this file: the decision holds until another reference act
            # is loaded, so a model that asks again is answered without disturbing the
            # lawyer a second time (final review, finding 6).
            return CONSENT_DENIED, None
        if not session.reference_consented:
            # Once per reference (design §5.3, controller ruling): a file of the firm that has
            # nothing to do with the open document gets its own decision, so the consent given
            # for the document never carries over to it. The block names the file, and
            # "annulla" leaves the drafting to go on without the reference.
            decision = await deps.consent(p.ConsentSummary(
                scope="reference", chars=reference["chars"], endpoint_host=deps.endpoint_host,
                model=deps.model, zdr=deps.zdr, name=reference["name"]))
            if decision in ("document", "once"):
                session.reference_consented = True
            else:
                session.reference_denied = True
                return CONSENT_DENIED, None
        return wrap_data(f"atto di riferimento ({reference['name']})", reference["text"]), None

    async def leggi_allegato(args: dict) -> tuple[str, str | None]:
        attachments = session.attachments
        if not attachments:
            return NO_ATTACHMENTS, None
        numero = args.get("numero")
        # A real document number, not a truncated float or a bool masquerading as one
        # (``True`` is an ``int`` in Python): a model that sends "1.5" or "true" gets told its
        # arguments are wrong instead of silently reading Doc. 1 (Task 1 review, finding 4).
        if not isinstance(numero, int) or isinstance(numero, bool):
            return BAD_ARGUMENTS, None
        match = next((a for a in attachments if a["n"] == numero), None)
        if match is None:
            return (f"ERRORE: allegato {numero} inesistente "
                    f"(disponibili: 1-{len(attachments)})", None)
        if session.attachments_denied:
            # Already refused for this set: the decision holds until set_attachments replaces
            # it, same rule as the reference act (final review, finding 6).
            return CONSENT_DENIED, None
        if not session.attachments_consented:
            # One consent per set, not per document (design §4.3): the names of every
            # attachment are shown once, and reading another one of the same set asks nothing.
            decision = await deps.consent(p.ConsentSummary(
                scope="attachments", chars=attachments_chars(attachments),
                endpoint_host=deps.endpoint_host, model=deps.model, zdr=deps.zdr,
                name=attachments_label(attachments)))
            if decision in ("document", "once"):
                session.attachments_consented = True
            else:
                session.attachments_denied = True
                return CONSENT_DENIED, None
        return wrap_data(f"allegato {numero} ({match['name']})", match["text"]), None

    hooks: dict[str, Hook] = {"chiedi_dati": chiedi_dati,
                              "redazione_completata": redazione_completata,
                              "leggi_atto_riferimento": leggi_atto_riferimento,
                              "leggi_allegato": leggi_allegato}
    return hooks, list(HOOK_TOOLS)


# --- the command --------------------------------------------------------------

def _strings(value: Any) -> dict[str, str]:
    """A panel dict of fields/answers as stripped strings, empty values dropped."""
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for name, raw in value.items():
        text = str(raw).strip()
        if text:
            out[str(name)] = text
    return out


async def run_draft(session: DocSession, args: dict, deps: AgentDeps, emit: Emit,
                    request_id: str) -> TurnOutcome:
    """One turn of a drafting, for one of the three actions (design §4.3)."""
    action = str(args.get("action") or "")
    message = ""
    new_answers: dict[str, str] = {}
    if action == "start":
        tipo_atto = str(args.get("tipo_atto") or "").strip()
        if not tipo_atto:
            raise ValueError("tipo_atto mancante")
        if deps.catalogue is None:
            raise ValueError("catalogo non disponibile: mcp-legal-it non raggiungibile")
        template = await deps.catalogue.info(tipo_atto, deps.specs)
        session.draft = DraftState(tipo_atto=tipo_atto, template=template,
                                   fields=_strings(args.get("fields")),
                                   notes=str(args.get("notes") or "").strip())
        await insert_base(session, deps, emit, request_id)
    elif action == "answer":
        if session.draft is None:
            raise ValueError("nessuna redazione in corso")
        if not isinstance(args.get("answers"), dict):
            raise ValueError("risposte mancanti")
        new_answers = _strings(args.get("answers"))
        session.draft.answers.update(new_answers)
        session.draft.questions = []
    elif action == "continue":
        if session.draft is None:
            raise ValueError("nessuna redazione in corso")
        message = str(args.get("message") or "").strip()
    else:
        raise ValueError(BAD_ACTION)

    draft = session.draft
    assert draft is not None
    known = {part["from_id"] for part in draft.partitions}

    def record(entry: dict) -> None:
        """One insertion, the moment the loop makes it (design §4.5)."""
        if entry["from_id"] in known:
            return
        known.add(entry["from_id"])
        draft.partitions.append({"titolo": entry.get("titolo", ""),
                                 "from_id": entry["from_id"], "to_id": entry["to_id"]})

    deps.on_inserted = record
    deps.hooks, deps.hook_tools = hooks_for(session, deps)
    deps.registry = ToolRegistry(deps.specs, PROFILE, extra_tools=deps.hook_tools)
    # The scan runs before the message as well as after the turn: a turn cancelled after a
    # replace_text left `aperti` stale, and the next turn repairs it (final review, finding 4).
    await _rescan_placeholders(draft, deps)
    outcome = await run_turn_with(
        deps, session, draft_message(session, action, message, new_answers), PROFILE, emit,
        request_id, undo_label(draft.tipo_atto))
    for entry in outcome.inserted:      # safety net: `record` has already seen them all
        record(entry)
    await _rescan_placeholders(draft, deps)
    # A proxy the extension sits behind may hand the model tools as `mcp__<x>__<name>` (design
    # §1's follow-up): the core never changes the name it sends, but the model's own prose can
    # echo it mangled, so the chat text is cleaned once the turn is over.
    outcome.text = clean_tool_names(outcome.text, deps.registry.names)
    return outcome


async def _rescan_placeholders(draft: DraftState, deps: AgentDeps) -> None:
    """Which placeholders of the base are still in the document (design §4.4)."""
    if not draft.base or not draft.base["placeholders"]:
        return
    try:
        draft.base["aperti"] = [ph for ph in draft.base["placeholders"]
                                if await deps.doc.find_text(ph)]
    except DocumentError:
        # The document is unreachable: keep what the previous turn knew rather than telling
        # the panel every placeholder is filled.
        draft.base.setdefault("aperti", list(draft.base["placeholders"]))


def _allegati_summary(session: DocSession) -> list[dict[str, Any]]:
    return [{"n": a["n"], "name": a["name"], "chars": a["chars"]} for a in session.attachments]


def draft_summary(session: DocSession, outcome: TurnOutcome) -> dict[str, Any]:
    """The drafting half of the turn's ``Final.summary`` (design §4.4, §4.5)."""
    draft = session.draft
    if draft is None:
        return {"ended_by": outcome.ended_by, "allegati": _allegati_summary(session)}
    base = draft.base or {}
    return {"tipo_atto": draft.tipo_atto, "domande": draft.questions,
            "partizioni": draft.partitions,
            "segnaposto_aperti": list(base.get("aperti", [])),
            "base_errore": draft.base_errore,
            "completata": draft.done, "riepilogo": draft.riepilogo,
            "allegati": _allegati_summary(session),
            "ended_by": outcome.ended_by}
