"""Structured EPANET-MSX input model: parse, edit, validate and write ``.msx``.

The model keeps each section as a list of plain dictionaries so a UI can edit
rows in tables while the text form stays round-trippable.  Inline ``;``
comments are preserved per row.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SECTIONS = ["TITLE", "OPTIONS", "SPECIES", "COEFFICIENTS", "TERMS", "PIPES", "TANKS",
            "SOURCES", "QUALITY", "PARAMETERS", "DIFFUSIVITY", "PATTERNS", "REPORT"]

#: Column layout of every tabular section (in file order).
COLUMNS: dict[str, list[str]] = {
    "SPECIES": ["type", "name", "units", "atol", "rtol"],
    "COEFFICIENTS": ["type", "name", "value"],
    "TERMS": ["name", "expression"],
    "PIPES": ["type", "species", "expression"],
    "TANKS": ["type", "species", "expression"],
    "SOURCES": ["type", "node", "species", "strength", "pattern"],
    "QUALITY": ["scope", "id", "species", "value"],
    "PARAMETERS": ["scope", "id", "param", "value"],
    "DIFFUSIVITY": ["species", "value"],
    "PATTERNS": ["name", "multipliers"],
}
CHOICES = {
    ("SPECIES", "type"): ["BULK", "WALL"],
    ("SPECIES", "units"): ["MG", "UG", "MOLE", "MMOL", "COUNT"],
    ("COEFFICIENTS", "type"): ["PARAMETER", "CONSTANT"],
    ("PIPES", "type"): ["RATE", "EQUIL", "FORMULA"],
    ("TANKS", "type"): ["RATE", "EQUIL", "FORMULA"],
    ("SOURCES", "type"): ["CONCEN", "MASS", "SETPOINT", "FLOWPACED"],
    ("QUALITY", "scope"): ["GLOBAL", "NODE", "LINK"],
    ("PARAMETERS", "scope"): ["PIPE", "TANK"],
}
OPTION_CHOICES = {
    "AREA_UNITS": ["M2", "FT2", "CM2"],
    "RATE_UNITS": ["SEC", "MIN", "HR", "DAY"],
    "SOLVER": ["EUL", "RK5", "ROS2"],
    "COUPLING": ["NONE", "FULL"],
    "COMPILER": ["NONE", "VC", "GC"],
    "TIMESTEP": [], "ATOL": [], "RTOL": [], "SEGMENTS": [], "PECLET": [],
}
OPTION_DEFAULTS = {"AREA_UNITS": "M2", "RATE_UNITS": "HR", "SOLVER": "RK5", "COUPLING": "NONE",
                   "COMPILER": "NONE", "TIMESTEP": "300", "ATOL": "0.01", "RTOL": "0.001"}

#: Hydraulic variables available inside MSX expressions (MSX manual, Table 2.1).
HYDRAULIC_VARS = {
    "D": "pipe diameter", "Q": "pipe flow rate", "U": "pipe flow velocity", "Re": "Reynolds number",
    "Us": "pipe shear velocity", "Ff": "Darcy-Weisbach friction factor", "Av": "surface area per unit volume",
    "Kc": "pipe roughness coefficient", "Len": "pipe length",
}
FUNCTIONS = {"abs", "sgn", "sqrt", "log", "exp", "sin", "cos", "tan", "cot", "asin", "acos", "atan",
             "acot", "sinh", "cosh", "tanh", "coth", "log10", "step"}
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_NUMBER = re.compile(r"(?<![A-Za-z_])\d+\.?\d*(?:[eE][+-]?\d+)?")


@dataclass
class Issue:
    level: str  # error | warning
    section: str
    message: str

    def __str__(self) -> str:
        return f"[{self.level.upper()}] {self.section}: {self.message}"


@dataclass
class MsxModel:
    title: str = ""
    options: dict[str, str] = field(default_factory=dict)
    rows: dict[str, list[dict]] = field(default_factory=lambda: {s: [] for s in COLUMNS})
    report: list[str] = field(default_factory=list)

    # -- convenience -------------------------------------------------------
    def species(self) -> list[str]:
        return [r["name"] for r in self.rows["SPECIES"] if r.get("name")]

    def symbols(self) -> set[str]:
        names = set(self.species())
        names |= {r["name"] for r in self.rows["COEFFICIENTS"] if r.get("name")}
        names |= {r["name"] for r in self.rows["TERMS"] if r.get("name")}
        return names

    def copy(self) -> "MsxModel":
        return parse(write(self))

    # -- validation --------------------------------------------------------
    def validate(self, node_ids: set[str] | None = None, link_ids: set[str] | None = None,
                 patterns: set[str] | None = None) -> list[Issue]:
        issues: list[Issue] = []
        species = self.species()
        if not species:
            issues.append(Issue("error", "SPECIES", "no species defined"))
        seen: set[str] = set()
        known = {s.upper() for s in HYDRAULIC_VARS} | {f.upper() for f in FUNCTIONS}
        for sec in ("SPECIES", "COEFFICIENTS", "TERMS"):
            for r in self.rows[sec]:
                name = r.get("name", "")
                if not _IDENT.fullmatch(name or ""):
                    issues.append(Issue("error", sec, f"invalid name {name!r}"))
                elif name.upper() in seen:
                    issues.append(Issue("error", sec, f"duplicate name {name}"))
                elif name.upper() in known:
                    issues.append(Issue("error", sec, f"{name} clashes with a reserved MSX symbol"))
                seen.add((name or "").upper())
        for r in self.rows["COEFFICIENTS"]:
            if not _is_number(r.get("value", "")):
                issues.append(Issue("error", "COEFFICIENTS", f"{r.get('name')} has non-numeric value"))
        symbols = {s.upper() for s in self.symbols()} | known
        wall = {r["name"] for r in self.rows["SPECIES"] if r.get("type", "").upper() == "WALL"}
        for sec in ("TERMS", "PIPES", "TANKS"):
            for r in self.rows[sec]:
                expr = r.get("expression", "")
                where = r.get("name") or r.get("species")
                if not expr.strip():
                    issues.append(Issue("error", sec, f"{where}: empty expression"))
                    continue
                bad = [c for c in expr if ord(c) > 127]
                if bad:
                    issues.append(Issue("error", sec, f"{where}: non-ASCII character {''.join(set(bad))!r} "
                                        "(often a typographic dash; use '-')"))
                if expr.count("(") != expr.count(")"):
                    issues.append(Issue("error", sec, f"{where}: unbalanced parentheses"))
                stripped = _NUMBER.sub(" ", expr)
                for ident in _IDENT.findall(stripped):
                    if ident.upper() not in symbols:
                        issues.append(Issue("error", sec, f"{where}: unknown symbol {ident}"))
                if sec == "TANKS" and any(w in _IDENT.findall(stripped) for w in wall):
                    issues.append(Issue("warning", sec, f"{where}: wall species are not defined in tanks"))
        for sec in ("PIPES", "TANKS"):
            defined = [r.get("species") for r in self.rows[sec]]
            for s in species:
                if sec == "TANKS" and s in wall:
                    continue
                if s not in defined:
                    issues.append(Issue("warning" if sec == "TANKS" else "error", sec,
                                        f"species {s} has no reaction/formula (it will not change)"))
            for s in defined:
                if s not in species:
                    issues.append(Issue("error", sec, f"reaction for undefined species {s}"))
                if defined.count(s) > 1:
                    issues.append(Issue("error", sec, f"species {s} defined more than once"))
        for r in self.rows["SOURCES"]:
            if r.get("species") not in species:
                issues.append(Issue("error", "SOURCES", f"unknown species {r.get('species')}"))
            if node_ids is not None and r.get("node") not in node_ids:
                issues.append(Issue("error", "SOURCES", f"node {r.get('node')} is not in the network"))
            if patterns is not None and r.get("pattern") and r["pattern"] not in patterns \
                    and r["pattern"] not in {p["name"] for p in self.rows["PATTERNS"]}:
                issues.append(Issue("warning", "SOURCES", f"pattern {r['pattern']} not defined"))
        for r in self.rows["QUALITY"]:
            if r.get("species") not in species:
                issues.append(Issue("error", "QUALITY", f"unknown species {r.get('species')}"))
            scope = r.get("scope", "").upper()
            if scope == "NODE" and node_ids is not None and r.get("id") not in node_ids:
                issues.append(Issue("error", "QUALITY", f"node {r.get('id')} is not in the network"))
            if scope == "LINK" and link_ids is not None and r.get("id") not in link_ids:
                issues.append(Issue("error", "QUALITY", f"link {r.get('id')} is not in the network"))
        ts = self.options.get("TIMESTEP", "")
        if ts and not _is_number(ts):
            issues.append(Issue("error", "OPTIONS", "TIMESTEP must be a number of seconds"))
        return issues


def _is_number(text) -> bool:
    try:
        float(str(text))
        return True
    except ValueError:
        return False


# --------------------------------------------------------------------------
# Parsing / writing
# --------------------------------------------------------------------------
def parse(text: str) -> MsxModel:
    model = MsxModel()
    section = None
    pending_comment = ""
    title_lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("["):
            name = line.strip("[] \t").upper()
            # MSX accepts abbreviated headings such as [PIPE] or [TANK]
            section = next((s for s in SECTIONS if s == name), None) or \
                next((s for s in SECTIONS if len(name) >= 4 and s.startswith(name[:4])), name)
            continue
        body, _, comment = line.partition(";")
        body, comment = body.strip(), comment.strip()
        if not body:
            pending_comment = comment
            continue
        if section == "TITLE":
            title_lines.append(body)
        elif section == "OPTIONS":
            parts = body.split(None, 1)
            model.options[parts[0].upper()] = parts[1].strip() if len(parts) > 1 else ""
        elif section == "REPORT":
            model.report.append(body + (f"  ;{comment}" if comment else ""))
        elif section in COLUMNS:
            row = _parse_row(section, body)
            if row is None:
                continue
            if section == "PATTERNS" and model.rows["PATTERNS"] and model.rows["PATTERNS"][-1]["name"] == row["name"]:
                model.rows["PATTERNS"][-1]["multipliers"] += " " + row["multipliers"]
                continue
            row["comment"] = comment or pending_comment
            model.rows[section].append(row)
        pending_comment = ""
    model.title = "\n".join(title_lines)
    return model


def _parse_row(section: str, body: str) -> dict | None:
    cols = COLUMNS[section]
    parts = body.split()
    if section in ("TERMS",):
        name, _, expr = body.partition(" ")
        return {"name": name.strip(), "expression": expr.strip()}
    if section in ("PIPES", "TANKS"):
        p = body.split(None, 2)
        if len(p) < 3:
            return None
        return {"type": p[0].upper(), "species": p[1], "expression": p[2].strip()}
    if section == "PATTERNS":
        return {"name": parts[0], "multipliers": " ".join(parts[1:])}
    if section == "QUALITY":
        if parts and parts[0].upper() == "GLOBAL":
            return {"scope": "GLOBAL", "id": "", "species": parts[1] if len(parts) > 1 else "",
                    "value": parts[2] if len(parts) > 2 else "0"}
        return {"scope": parts[0].upper(), "id": parts[1] if len(parts) > 1 else "",
                "species": parts[2] if len(parts) > 2 else "", "value": parts[3] if len(parts) > 3 else "0"}
    row = {c: (parts[i] if i < len(parts) else "") for i, c in enumerate(cols)}
    for key in ("type", "scope"):
        if key in row:
            row[key] = row[key].upper()
    if section == "SOURCES":
        row["type"] = next((t for t in CHOICES[("SOURCES", "type")] if t.startswith(row["type"][:4])), row["type"])
    if section == "COEFFICIENTS" and row["type"].startswith("PARAM"):
        row["type"] = "PARAMETER"
    if section == "COEFFICIENTS" and row["type"].startswith("CONST"):
        row["type"] = "CONSTANT"
    return row


def write(model: MsxModel) -> str:
    out: list[str] = ["[TITLE]", model.title or "Untitled MSX model", ""]
    out.append("[OPTIONS]")
    for key, value in model.options.items():
        if str(value).strip():
            out.append(f"  {key:<11}{value}")
    out.append("")
    for section in COLUMNS:
        rows = model.rows.get(section) or []
        if not rows:
            continue
        out.append(f"[{section}]")
        for r in rows:
            if section == "QUALITY" and r.get("scope", "").upper() == "GLOBAL":
                cells = ["GLOBAL", r.get("species", ""), str(r.get("value", ""))]
            else:
                cells = [str(r.get(c, "") or "") for c in COLUMNS[section]]
                while cells and cells[-1] == "" and section not in ("TERMS", "PIPES", "TANKS"):
                    cells.pop()
            widths = [9, 10, 10, 12, 10]
            text = "  " + "".join((c + " ").ljust(widths[i]) if i < len(cells) - 1 else c for i, c in enumerate(cells))
            comment = (r.get("comment") or "").strip()
            out.append(text.rstrip() + (f"    ;{comment}" if comment else ""))
        out.append("")
    if model.report:
        out.append("[REPORT]")
        out.extend(f"  {line}" for line in model.report)
        out.append("")
    return "\n".join(out)


def blank_row(section: str, model: MsxModel | None = None) -> dict:
    species = (model.species() if model else []) or [""]
    defaults = {
        "SPECIES": {"type": "BULK", "name": "NEW", "units": "MG", "atol": "", "rtol": ""},
        "COEFFICIENTS": {"type": "CONSTANT", "name": "k", "value": "0.1"},
        "TERMS": {"name": "T", "expression": "0"},
        "PIPES": {"type": "RATE", "species": species[0], "expression": "0"},
        "TANKS": {"type": "RATE", "species": species[0], "expression": "0"},
        "SOURCES": {"type": "CONCEN", "node": "", "species": species[0], "strength": "1.0", "pattern": ""},
        "QUALITY": {"scope": "GLOBAL", "id": "", "species": species[0], "value": "0"},
        "PARAMETERS": {"scope": "PIPE", "id": "", "param": "", "value": "0"},
        "DIFFUSIVITY": {"species": species[0], "value": "1.208e-9"},
        "PATTERNS": {"name": "P1", "multipliers": "1.0"},
    }[section]
    return dict(defaults, comment="")


# --------------------------------------------------------------------------
# Templates (starting points; review coefficients for your system)
# --------------------------------------------------------------------------
TEMPLATES: dict[str, str] = {
    "Water age (MSX species)": """[TITLE]
Water age as a reacting species
[OPTIONS]
  AREA_UNITS M2
  RATE_UNITS HR
  SOLVER     EUL
  TIMESTEP   300
[SPECIES]
  BULK AGE   MG  0.01 0.001   ;age in hours (unit label only)
[PIPES]
  RATE AGE   1
[TANKS]
  RATE AGE   1
""",
    "Chlorine bulk + wall decay": """[TITLE]
Free chlorine: first-order bulk decay and mass-transfer limited wall demand
[OPTIONS]
  AREA_UNITS M2
  RATE_UNITS HR
  SOLVER     RK5
  TIMESTEP   300
  RTOL       0.001
  ATOL       0.0001
[SPECIES]
  BULK CL2   MG   ;free chlorine
[COEFFICIENTS]
  PARAMETER Kb   0.3   ;bulk decay (1/h)
  PARAMETER Kw   0.5   ;wall reaction (m/h)
[TERMS]
  Kf   1.243523e-3*U^0.33/D^0.67   ;approx. mass-transfer coefficient (m/h)
[PIPES]
  RATE CL2   -Kb*CL2 - (4/D)*Kw*Kf/(Kw+Kf)*CL2
[TANKS]
  RATE CL2   -Kb*CL2
[QUALITY]
  GLOBAL CL2 0.0
""",
    "Chlorine – TOC second-order": """[TITLE]
Chlorine consumption by organic carbon (second-order)
[OPTIONS]
  AREA_UNITS M2
  RATE_UNITS HR
  SOLVER     ROS2
  TIMESTEP   300
  RTOL       0.001
  ATOL       0.0001
[SPECIES]
  BULK CL2   MG   ;free chlorine
  BULK TOC   MG   ;total organic carbon
[COEFFICIENTS]
  PARAMETER k   0.06   ;second-order rate (L/mg/h)
  CONSTANT  Y   0.4    ;TOC consumed per unit chlorine
[PIPES]
  RATE CL2   -k*CL2*TOC
  RATE TOC   -Y*k*CL2*TOC
[TANKS]
  RATE CL2   -k*CL2*TOC
  RATE TOC   -Y*k*CL2*TOC
[QUALITY]
  GLOBAL CL2 0.0
  GLOBAL TOC 2.0
""",
    "Arsenic oxidation / adsorption (MSX manual)": """[TITLE]
Arsenic Oxidation/Adsorption Example
[OPTIONS]
  AREA_UNITS M2
  RATE_UNITS HR
  SOLVER     RK5
  TIMESTEP   360
  RTOL       0.001
  ATOL       0.0001
[SPECIES]
  BULK AS3   UG   ;Dissolved arsenite
  BULK AS5   UG   ;Dissolved arsenate
  BULK AStot UG   ;Total dissolved arsenic
  WALL AS5s  UG   ;Adsorbed arsenate
  BULK NH2CL MG   ;Monochloramine
[COEFFICIENTS]
  CONSTANT Ka   10.0   ;Arsenite oxidation rate coefficient
  CONSTANT Kb   0.1    ;Monochloramine decay rate coefficient
  CONSTANT K1   5.0    ;Arsenate adsorption coefficient
  CONSTANT K2   1.0    ;Arsenate desorption coefficient
  CONSTANT Smax 50     ;Arsenate adsorption saturation limit
[TERMS]
  Ks   K1/K2   ;Equil. adsorption coeff.
[PIPES]
  RATE    AS3    -Ka*AS3*NH2CL
  RATE    AS5    Ka*AS3*NH2CL - Av*(K1*(Smax-AS5s)*AS5 - K2*AS5s)
  RATE    NH2CL  -Kb*NH2CL
  EQUIL   AS5s   Ks*Smax*AS5/(1+Ks*AS5) - AS5s
  FORMULA AStot  AS3 + AS5
[TANKS]
  RATE    AS3    -Ka*AS3*NH2CL
  RATE    AS5    Ka*AS3*NH2CL
  RATE    NH2CL  -Kb*NH2CL
  FORMULA AStot  AS3 + AS5
""",
    "Bacterial regrowth (substrate–biomass)": """[TITLE]
Bulk bacterial growth on biodegradable organic carbon with chlorine inactivation
[OPTIONS]
  AREA_UNITS M2
  RATE_UNITS HR
  SOLVER     ROS2
  TIMESTEP   300
  RTOL       0.001
  ATOL       0.0001
[SPECIES]
  BULK BDOC  MG      ;biodegradable dissolved organic carbon
  BULK X     COUNT   ;suspended bacteria (cells/L)
  BULK CL2   MG      ;free chlorine
[COEFFICIENTS]
  PARAMETER mu  0.2     ;max growth rate (1/h)
  PARAMETER Ks  0.4     ;half-saturation (mg/L)
  CONSTANT  Yx  1.0e6   ;cells per mg BDOC
  PARAMETER kd  0.05    ;natural decay (1/h)
  PARAMETER ki  2.0     ;chlorine inactivation (L/mg/h)
  PARAMETER kb  0.2     ;chlorine bulk decay (1/h)
[TERMS]
  G    mu*BDOC/(Ks+BDOC)
[PIPES]
  RATE BDOC  -G*X/Yx
  RATE X     (G - kd - ki*CL2)*X
  RATE CL2   -kb*CL2
[TANKS]
  RATE BDOC  -G*X/Yx
  RATE X     (G - kd - ki*CL2)*X
  RATE CL2   -kb*CL2
[QUALITY]
  GLOBAL BDOC 0.5
  GLOBAL X    1000
""",
}


def template(name: str) -> MsxModel:
    model = parse(TEMPLATES[name])
    for key, value in OPTION_DEFAULTS.items():
        model.options.setdefault(key, value)
    return model
