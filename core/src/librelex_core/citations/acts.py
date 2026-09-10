# Copyright 2026 Guglielmo Puzio. Licensed under the Apache License, Version 2.0.
"""Curated table of Italian/EU act abbreviations → canonical labels accepted by cite_law."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ActType:
    key: str
    label: str
    numbered: bool
    eu: bool = False


CC = ActType("codice_civile", "c.c.", False)
CP = ActType("codice_penale", "c.p.", False)
CPC = ActType("codice_procedura_civile", "c.p.c.", False)
CPP = ActType("codice_procedura_penale", "c.p.p.", False)
COST = ActType("costituzione", "Cost.", False)
PRELEGGI = ActType("preleggi", "preleggi", False)
DISP_ATT_CC = ActType("disp_att_cc", "disp. att. c.c.", False)
DISP_ATT_CPC = ActType("disp_att_cpc", "disp. att. c.p.c.", False)
DLGS = ActType("decreto_legislativo", "D.Lgs.", True)
DL = ActType("decreto_legge", "D.L.", True)
LEGGE = ActType("legge", "L.", True)
DPR = ActType("dpr", "D.P.R.", True)
RD = ActType("regio_decreto", "R.D.", True)
DM = ActType("decreto_ministeriale", "D.M.", True)
DPCM = ActType("dpcm", "D.P.C.M.", True)
LR = ActType("legge_regionale", "L.R.", True)
GDPR = ActType("gdpr", "GDPR", False, eu=True)
REG_UE = ActType("regolamento_ue", "regolamento UE", True, eu=True)
DIR_UE = ActType("direttiva_ue", "direttiva", True, eu=True)
TFUE = ActType("tfue", "TFUE", False, eu=True)
TUE = ActType("tue", "TUE", False, eu=True)
CDFUE = ActType("cdfue", "CDFUE", False, eu=True)
TUF = ActType("tuf", "TUF", False)
TUB = ActType("tub", "TUB", False)
TUIR = ActType("tuir", "TUIR", False)
TUEL = ActType("tuel", "TUEL", False)
CDS = ActType("codice_strada", "codice della strada", False)
COD_CONS = ActType("codice_consumo", "codice del consumo", False)
CPA = ActType("codice_processo_amministrativo", "codice del processo amministrativo", False)
CCII = ActType("codice_crisi", "codice della crisi d'impresa e dell'insolvenza", False)
CAD = ActType("cad", "codice dell'amministrazione digitale", False)
COD_PRIVACY = ActType("codice_privacy", "D.Lgs. 196/2003", False)
COD_CONTRATTI = ActType("codice_contratti", "codice dei contratti pubblici", False)
COD_ASSIC = ActType("codice_assicurazioni", "codice delle assicurazioni private", False)
COD_PROP_IND = ActType("codice_proprieta_industriale", "codice della proprietà industriale", False)
COD_TERZO = ActType("codice_terzo_settore", "codice del Terzo settore", False)
L_FALL = ActType("legge_fallimentare", "legge fallimentare", False)
STAT_LAV = ActType("statuto_lavoratori", "L. 300/1970", False)
TU_EDILIZIA = ActType("tu_edilizia", "D.P.R. 380/2001", False)
TU_IMMIGRAZIONE = ActType("tu_immigrazione", "D.Lgs. 286/1998", False)
TU_SICUREZZA = ActType("tu_sicurezza", "D.Lgs. 81/2008", False)
D231 = ActType("d231", "D.Lgs. 231/2001", False)

ABBREVIATIONS: dict[str, ActType] = {
    # codes
    "c.c.": CC, "cc": CC, "cod. civ.": CC, "codice civile": CC,
    "c.p.": CP, "cp": CP, "cod. pen.": CP, "codice penale": CP,
    "c.p.c.": CPC, "cpc": CPC, "cod. proc. civ.": CPC,
    "codice di procedura civile": CPC,
    "c.p.p.": CPP, "cpp": CPP, "cod. proc. pen.": CPP,
    "codice di procedura penale": CPP,
    "cost.": COST, "cost": COST, "costituzione": COST,
    "carta costituzionale": COST,
    "preleggi": PRELEGGI, "disp. prel. c.c.": PRELEGGI,
    "disp. att. c.c.": DISP_ATT_CC, "disp. att. c.p.c.": DISP_ATT_CPC,
    # numbered national acts
    "d.lgs.": DLGS, "d.lgs": DLGS, "dlgs": DLGS, "d. lgs.": DLGS, "d.lg.": DLGS,
    "decreto legislativo": DLGS, "decreto legislativo n.": DLGS,
    "d.l.": DL, "dl": DL, "decreto legge": DL, "decreto-legge": DL, "d.-l.": DL,
    "l.": LEGGE, "legge": LEGGE, "legge n.": LEGGE, "l. n.": LEGGE,
    "d.p.r.": DPR, "dpr": DPR,
    "decreto del presidente della repubblica": DPR,
    "r.d.": RD, "rd": RD, "regio decreto": RD,
    "d.m.": DM, "dm": DM, "decreto ministeriale": DM,
    "d.p.c.m.": DPCM, "dpcm": DPCM,
    "l.r.": LR, "legge regionale": LR,
    # EU
    "gdpr": GDPR, "rgpd": GDPR,
    "regolamento (ue)": REG_UE, "regolamento ue": REG_UE, "reg. (ue)": REG_UE,
    "reg. ue": REG_UE,
    "regolamento (ce)": REG_UE, "regolamento ce": REG_UE, "reg. (ce)": REG_UE,
    "direttiva": DIR_UE, "dir.": DIR_UE, "direttiva (ue)": DIR_UE,
    "direttiva ue": DIR_UE,
    "tfue": TFUE, "t.f.u.e.": TFUE, "tue": TUE, "t.u.e.": TUE,
    "cdfue": CDFUE,
    "carta dei diritti fondamentali dell'unione europea": CDFUE,
    # testi unici and named acts
    "tuf": TUF, "t.u.f.": TUF, "tub": TUB, "t.u.b.": TUB, "tuir": TUIR,
    "t.u.i.r.": TUIR,
    "tuel": TUEL, "t.u.e.l.": TUEL,
    "c.d.s.": CDS, "cds": CDS, "codice della strada": CDS,
    "cod. cons.": COD_CONS, "codice del consumo": COD_CONS,
    "c.p.a.": CPA, "cpa": CPA, "codice del processo amministrativo": CPA,
    "ccii": CCII, "c.c.i.i.": CCII, "codice della crisi": CCII,
    "codice della crisi d'impresa e dell'insolvenza": CCII,
    "cad": CAD, "c.a.d.": CAD,
    "codice dell'amministrazione digitale": CAD,
    "codice privacy": COD_PRIVACY, "cod. privacy": COD_PRIVACY,
    "codice della privacy": COD_PRIVACY,
    "codice in materia di protezione dei dati personali": COD_PRIVACY,
    "codice dei contratti pubblici": COD_CONTRATTI,
    "codice appalti": COD_CONTRATTI,
    "cod. ass.": COD_ASSIC, "codice delle assicurazioni": COD_ASSIC,
    "codice delle assicurazioni private": COD_ASSIC,
    "c.p.i.": COD_PROP_IND, "cpi": COD_PROP_IND,
    "codice della proprietà industriale": COD_PROP_IND,
    "cts": COD_TERZO, "codice del terzo settore": COD_TERZO,
    "l. fall.": L_FALL, "l.f.": L_FALL, "legge fallimentare": L_FALL,
    "stat. lav.": STAT_LAV, "statuto dei lavoratori": STAT_LAV,
    "t.u. edilizia": TU_EDILIZIA, "testo unico edilizia": TU_EDILIZIA,
    "t.u. immigrazione": TU_IMMIGRAZIONE, "testo unico immigrazione": TU_IMMIGRAZIONE,
    "t.u. sicurezza": TU_SICUREZZA, "testo unico sicurezza": TU_SICUREZZA,
    "d.lgs. 231": D231, "decreto 231": D231,
}

# Longest keys first so "codice di procedura civile" wins over "codice civile" etc.
ABBREV_PATTERN: str = "|".join(
    re.escape(k) for k in sorted(ABBREVIATIONS, key=len, reverse=True)
)


def resolve_act(abbrev: str) -> ActType | None:
    key = re.sub(r"\s+", " ", abbrev.strip().lower())
    for candidate in (key, key.rstrip("."), key + "."):
        if candidate in ABBREVIATIONS:
            return ABBREVIATIONS[candidate]
    return None


def canonical_act(act: ActType, number: str | None, year: str | None) -> str:
    """Label as cite_law expects; EU acts keep raw numbering (year/number or number/year)."""
    if not act.numbered:
        return act.label
    if act.eu:
        raw = f"{number}/{year}" if number and year else (number or year or "")
        if act is DIR_UE:
            return (
                f"direttiva {raw}/CE"
                if raw and not raw.upper().endswith(("CE", "UE"))
                else f"direttiva {raw}"
            )
        return f"{act.label} {raw}".strip()
    if number and year:
        return f"{act.label} {number}/{year}"
    return act.label
