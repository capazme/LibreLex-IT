# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Stateful, template-guided drafting (guided drafting design §3.2, §4.2-§4.5, §5.3).

A drafting lives in ``DocSession.draft`` and advances one action at a time: ``start`` (the
lawyer picked an act and filled the template's fields), ``answer`` (the answers to the
questions the model asked) and ``continue`` (a free instruction, or a resume after an
iteration stop). The user message of every turn is rebuilt from that state, so the model
never depends on the compacted tool results of an earlier turn.

Three hooks (``chiedi_dati``, ``redazione_completata``, ``leggi_atto_riferimento``) are added
to the loop for the drafting turns only: the first two end the turn in an orderly way, the
third serves the reference act after consent. Everything else (grounding on write, consent for
document reads, limits, cancellation) is the ordinary agent turn.
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
from librelex_core.agent.state import DocSession, DraftState
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

# "[...]" of the deterministic generators and "{...}" of the published templates; the length
# cap keeps a stray bracket in the act's prose from becoming a placeholder.
PLACEHOLDER_RE = re.compile(r"\[[^\[\]\n]{1,60}\]|\{[a-z_]+\}")
_YES = ("sì", "si", "s", "true", "1", "yes")


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
    """The act text of a generator result: ``testo``, else the first ``bozza*`` key."""
    testo = result.get("testo")
    if isinstance(testo, str) and testo.strip():
        return testo
    for key, value in result.items():
        if key.startswith("bozza") and isinstance(value, str) and value.strip():
            return value
    return None


def to_markdown(text: str) -> str:
    """Plain generator text to markdown: every line becomes a paragraph of the document.

    The generators lay their acts out with single newlines, which markdown would fold into
    one paragraph; ordered lists ("1. ...") keep working, each item being its own paragraph.
    """
    return re.sub(r"\n{2,}", "\n\n", re.sub(r"(?<!\n)\n(?!\n)", "\n\n", text.strip()))


def _coerce(value: str, tipo: str) -> Any:
    if tipo == "numero":
        try:
            return float(value.replace(".", "").replace(",", "."))
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
        await emit(p.Status(request_id=request_id, text=f"Base non disponibile: {e.message}"))
        return
    try:
        result = json.loads(text)
    except json.JSONDecodeError:
        result = None
    if not isinstance(result, dict):
        await emit(p.Status(request_id=request_id,
                            text=f"Base non disponibile: {tool} non ha risposto in JSON"))
        return
    base = base_text(result)
    if base is None:
        return
    inserted = await deps.doc.insert_markdown(
        "end", to_markdown(base), BASE_UNDO.format(tipo_atto=draft.tipo_atto),
        bookmark=BASE_BOOKMARK.format(tipo_atto=draft.tipo_atto), author=WRITE_AUTHOR)
    open_placeholders = placeholders(base)
    draft.base = {
        "from_id": inserted.from_id, "to_id": inserted.to_id,
        "placeholders": open_placeholders, "tool": tool,
        "result": {k: v for k, v in result.items()
                   if k != "testo" and not k.startswith("bozza")},
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
        blocks.append(
            f"Atto di riferimento disponibile: {reference['name']} "
            f"({reference['chars']} caratteri): leggilo con leggi_atto_riferimento "
            "prima di comporre.")
    if draft.base:
        aperti = (draft.base["aperti"] if "aperti" in draft.base
                  else draft.base["placeholders"])
        blocks.append(
            f"Base deterministica già nel documento (paragrafi {draft.base['from_id']}-"
            f"{draft.base['to_id']}), segnaposto ancora aperti: "
            + (", ".join(aperti) if aperti else "nessuno"))
    else:
        blocks.append("Nessuna base deterministica: componi dal modello.")
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

HOOK_TOOLS: list[dict] = [CHIEDI_DATI_TOOL, REDAZIONE_COMPLETATA_TOOL,
                          LEGGI_ATTO_RIFERIMENTO_TOOL]


def hooks_for(session: DocSession, deps: AgentDeps) -> tuple[dict[str, Hook], list[dict]]:
    """The three drafting hooks, closed over this session and these dependencies."""
    draft = session.draft

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
        draft.riepilogo = str(args.get("riepilogo") or "")
        draft.questions = []
        return DRAFT_DONE, "done"

    async def leggi_atto_riferimento(args: dict) -> tuple[str, str | None]:
        reference = session.reference
        if reference is None:
            return NO_REFERENCE, None
        if session.consent != "document" and not session.reference_consented:
            # Once per session (design §5.3): the block names the file, and "annulla" leaves
            # the drafting to go on without the reference.
            decision = await deps.consent(p.ConsentSummary(
                scope="reference", chars=reference["chars"], endpoint_host=deps.endpoint_host,
                model=deps.model, zdr=deps.zdr, name=reference["name"]))
            if decision == "document":
                session.consent = "document"
            elif decision == "once":
                session.reference_consented = True
            else:
                return CONSENT_DENIED, None
        return wrap_data(f"atto di riferimento ({reference['name']})", reference["text"]), None

    hooks: dict[str, Hook] = {"chiedi_dati": chiedi_dati,
                              "redazione_completata": redazione_completata,
                              "leggi_atto_riferimento": leggi_atto_riferimento}
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
    deps.hooks, deps.hook_tools = hooks_for(session, deps)
    deps.registry = ToolRegistry(deps.specs, PROFILE, extra_tools=deps.hook_tools)
    outcome = await run_turn_with(
        deps, session, draft_message(session, action, message, new_answers), PROFILE, emit,
        request_id, undo_label(draft.tipo_atto))
    known = {part["from_id"] for part in draft.partitions}
    for entry in outcome.inserted:
        if entry["from_id"] in known:
            continue
        known.add(entry["from_id"])
        draft.partitions.append({"titolo": entry.get("titolo", ""),
                                 "from_id": entry["from_id"], "to_id": entry["to_id"]})
    if draft.base:
        try:
            draft.base["aperti"] = [ph for ph in draft.base["placeholders"]
                                    if await deps.doc.find_text(ph)]
        except DocumentError:
            # The document is unreachable: keep what the previous turn knew rather than
            # telling the panel every placeholder is filled.
            draft.base.setdefault("aperti", list(draft.base["placeholders"]))
    return outcome


def draft_summary(session: DocSession, outcome: TurnOutcome) -> dict[str, Any]:
    """The drafting half of the turn's ``Final.summary`` (design §4.4, §4.5)."""
    draft = session.draft
    if draft is None:
        return {"ended_by": outcome.ended_by}
    base = draft.base or {}
    return {"tipo_atto": draft.tipo_atto, "domande": draft.questions,
            "partizioni": draft.partitions,
            "segnaposto_aperti": list(base.get("aperti", [])),
            "completata": draft.done, "riepilogo": draft.riepilogo,
            "ended_by": outcome.ended_by}
