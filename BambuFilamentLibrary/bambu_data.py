"""Bambu Lab filament data: download the latest official color table and turn it into library records.

Pure Python (no Fusion imports) so it can be tested outside Fusion and shared with tools/update_library.py.

Sources
  colors : BambuStudio  resources/profiles/BBL/filament/filaments_color_codes.json  (AGPL-3.0, Bambu Lab)
  physics: Bambu Lab Technical Data Sheets, pre-parsed into tds_all.json
"""
import json, os, re, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
COLORS_URL = "https://raw.githubusercontent.com/bambulab/BambuStudio/master/resources/profiles/BBL/filament/filaments_color_codes.json"
PROFILE_URL = "https://raw.githubusercontent.com/bambulab/BambuStudio/master/resources/profiles/BBL/filament/"
# this project's repository: newest TDS values and product-line table, so users get them without a new zip
REPO_RAW = "https://raw.githubusercontent.com/mtenemy2/fusion-bambu-filament-library/main/BambuFilamentLibrary/"
UA = {"User-Agent": "Mozilla/5.0 (BambuFilamentLibrary for Fusion)"}

# Generic literature values (Bambu does not publish): Poisson, k [W/m-K], cp [J/kg-K], CTE [1/K]
GENERIC = {
    "PLA": dict(poisson=0.36, k=0.13, cp=1800, cte=68e-6), "PETG": dict(poisson=0.38, k=0.20, cp=1200, cte=60e-6),
    "ABS": dict(poisson=0.35, k=0.17, cp=1400, cte=90e-6), "ASA": dict(poisson=0.35, k=0.17, cp=1300, cte=95e-6),
    "TPU": dict(poisson=0.48, k=0.19, cp=1800, cte=150e-6), "PC": dict(poisson=0.37, k=0.20, cp=1200, cte=68e-6),
    "PA": dict(poisson=0.39, k=0.30, cp=1600, cte=40e-6), "PET": dict(poisson=0.38, k=0.25, cp=1200, cte=40e-6),
    "PPS": dict(poisson=0.36, k=0.30, cp=1000, cte=20e-6), "PVA": dict(poisson=0.40, k=0.20, cp=1600, cte=100e-6),
    "Support": dict(poisson=0.36, k=0.15, cp=1500, cte=80e-6), "Other": dict(poisson=0.36, k=0.18, cp=1500, cte=70e-6),
}
EST_MECH = {"PVA": (2000, 40, 10), "Support": (1500, 25, 5)}       # E MPa, UTS MPa, elongation % (estimates)
FAMILY_DEFAULT_TDS = {"PLA": "PLA_Basic", "PETG": "PETG_Basic", "ABS": "ABS", "ASA": "ASA", "TPU": "TPU_95A", "PC": "PC",
                      "PA": "PAHT-CF", "PET": "PET-CF", "PPS": "PPS-CF", "PVA": "PVA", "Other": "PLA_Basic"}
ROUGH = {"glossy": 0.30, "satin": 0.50, "matte": 0.75, "silk": 0.12, "sparkle": 0.35, "metal": 0.35, "translucent": 0.10}

# known product lines: (family, TDS key, Bambu Studio profile density g/cm3, appearance style, roughness)
LINES = {
    "PLA Basic": ("PLA", "PLA_Basic", 1.26, "glossy", 0.30), "PLA Matte": ("PLA", "PLA_Matte", 1.32, "matte", 0.75),
    "PLA Silk": ("PLA", "PLA_Silk", 1.32, "silk", 0.12), "PLA Silk+": ("PLA", "PLA_Silk", 1.27, "silk", 0.10),
    "PLA Tough": ("PLA", "PLA_Tough", 1.26, "glossy", 0.30), "PLA Tough+": ("PLA", "PLA_Tough", 1.21, "glossy", 0.30),
    "PLA-CF": ("PLA", "PLA-CF", 1.22, "matte", 0.85), "PLA Aero": ("PLA", "PLA_Aero", 1.21, "matte", 0.85),
    "PLA Dynamic": ("PLA", "PLA_Basic", 1.26, "glossy", 0.30), "PLA Galaxy": ("PLA", "PLA_Galaxy", 1.19, "sparkle", 0.35),
    "PLA Glow": ("PLA", "PLA_Basic", 1.26, "glossy", 0.35), "PLA Lite": ("PLA", "PLA_Basic", 1.40, "glossy", 0.40),
    "PLA Marble": ("PLA", "PLA_Marble", 1.22, "matte", 0.70), "PLA Metal": ("PLA", "PLA_Metal", 1.25, "metal", 0.35),
    "PLA Palette": ("PLA", "PLA_Basic", 1.26, "glossy", 0.30), "PLA Pure": ("PLA", "PLA_Basic", None, "glossy", 0.30),
    "PLA Sparkle": ("PLA", "PLA_Sparkle", 1.26, "sparkle", 0.35), "PLA Translucent": ("PLA", "PLA_Translucent", 1.22, "translucent", 0.10),
    "PLA Wood": ("PLA", "PLA_Wood", 1.21, "matte", 0.80),
    "PETG Basic": ("PETG", "PETG_Basic", 1.25, "glossy", 0.20), "PETG HF": ("PETG", "PETG_HF", 1.28, "glossy", 0.25),
    "PETG Matte": ("PETG", "PETG_Basic", 1.25, "matte", 0.70), "PETG Translucent": ("PETG", "PETG_Basic", 1.25, "translucent", 0.10),
    "PETG-CF": ("PETG", "PETG-CF", 1.25, "matte", 0.85),
    "ABS": ("ABS", "ABS", None, "satin", 0.50), "ABS-GF": ("ABS", "ABS-GF", 1.08, "matte", 0.80),
    "ASA": ("ASA", "ASA", 1.05, "satin", 0.50), "ASA Aero": ("ASA", "ASA_Aero", 0.99, "matte", 0.85), "ASA-CF": ("ASA", "ASA-CF", 1.02, "matte", 0.85),
    "TPU 95A": ("TPU", "TPU_95A", 1.22, "satin", 0.55), "TPU 95A HF": ("TPU", "TPU_95A_HF", 1.22, "satin", 0.55),
    "TPU 90A": ("TPU", "TPU_90A", None, "satin", 0.55), "TPU 85A": ("TPU", "TPU_85A", 1.18, "satin", 0.60),
    "TPU 75A (2.85mm)": ("TPU", "TPU_85A", None, "satin", 0.60), "TPU for AMS": ("TPU", "TPU_for_AMS", 1.26, "satin", 0.50),
    "PC": ("PC", "PC", 1.185, "glossy", 0.20), "PC FR": ("PC", "PC_FR", 1.19, "glossy", 0.25),
    "PA6-CF": ("PA", "PA6-CF", 1.10, "matte", 0.85), "PA6-GF": ("PA", "PA6-CF", 1.14, "matte", 0.80),
    "PAHT-CF": ("PA", "PAHT-CF", 1.06, "matte", 0.85), "PPA-CF": ("PA", "PAHT-CF", 1.17, "matte", 0.85),
    "PET-CF": ("PET", "PET-CF", 1.29, "matte", 0.85), "PPS-CF": ("PPS", "PPS-CF", 1.26, "matte", 0.85),
    "PVA": ("PVA", "PVA", 1.27, "satin", 0.50),
    "Support for PLA": ("Support", "Support_for_PLA", 1.30, "matte", 0.70),
    "Support for PLA/PETG": ("Support", "Support_for_PLA_PETG", 1.19, "matte", 0.70),
    "Support for ABS": ("Support", "Support_for_ABS", 1.16, "matte", 0.70),
    "Support for PA/PET": ("Support", None, 1.22, "matte", 0.70),
}
COLOR_TYPE = {"单色": "solid", "渐变色": "gradient", "多拼色": "multicolor"}


def fetch(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def tds_key(line):
    return line.replace("/", "_").replace(" ", "_").replace("(", "").replace(")", "")


def guess_family(line):
    if line.lower().startswith("support"):
        return "Support"
    t = line.replace("-", " ").split()[0].upper()
    for fam, keys in [("PETG", ["PETG"]), ("PLA", ["PLA"]), ("ABS", ["ABS"]), ("ASA", ["ASA"]), ("TPU", ["TPU", "TPE"]),
                      ("PC", ["PC"]), ("PA", ["PA", "PA6", "PA12", "PAHT", "PPA"]), ("PET", ["PET"]), ("PPS", ["PPS"]), ("PVA", ["PVA"])]:
        if t in keys:
            return fam
    return "Other"


def guess_style(line, fam):
    l = line.lower()
    for kw, st in [("translucent", "translucent"), ("silk", "silk"), ("metal", "metal"), ("galaxy", "sparkle"), ("sparkle", "sparkle"),
                   ("matte", "matte"), ("aero", "matte"), ("-cf", "matte"), ("-gf", "matte"), ("wood", "matte"), ("marble", "matte")]:
        if kw in l:
            return st
    return "satin" if fam in ("ABS", "ASA", "TPU", "PVA", "Support") else "glossy"


def profile_density(line):
    for n in (line, line.replace(" (2.85mm)", ""), line.replace("/", "-"), line.replace("/", " ")):
        try:
            d = json.loads(fetch(PROFILE_URL + urllib.parse.quote("Bambu %s @base.json" % n), timeout=10))
            v = d.get("filament_density")
            v = v[0] if isinstance(v, list) else v
            if v:
                return float(v)
        except Exception:
            pass
    return None


def clean(s):
    if not s:
        return ""
    s = re.sub(r"[^\x20-\x7e]+", " ", s)
    return re.sub(r"\s+", " ", s).replace(" C", "C").strip().replace(" - ", "-")


def line_table(lines, tds, online=True, notes=None):
    """Map every product line to (family, tds key, profile density, style, roughness); unknown lines are auto-mapped."""
    table = {}
    for line in lines:
        if line in LINES:
            fam, tkey, dens, st, rough = LINES[line]
        else:
            fam = guess_family(line)
            st = guess_style(line, fam)
            tkey, dens, rough = None, (profile_density(line) if online else None), ROUGH[st]
            if notes is not None:
                notes.append("New line auto-mapped: %s -> family %s, style %s" % (line, fam, st))
        own = tds_key(line)
        if own in tds:                       # a sheet for exactly this line is available
            tkey = own
        elif tkey is None and line not in LINES and fam != "Support":
            tkey = FAMILY_DEFAULT_TDS.get(fam)
        table[line] = (fam, tkey, dens, st, rough)
    return table


def build_records(colors, tds, online=True, notes=None):
    """colors: list from filaments_color_codes.json['data']; tds: dict from tds_all.json."""
    table = line_table(sorted({x["fila_type"] for x in colors}), tds, online, notes)
    out = []
    for x in colors:
        line = x["fila_type"]
        fam, tkey, prof_dens, style, rough = table[line]
        t = tds.get(tkey, {}) if tkey else {}
        own = bool(t) and tkey == tds_key(line)
        E, UTS, el = t.get("E"), t.get("UTS"), t.get("elong")
        est = E is None
        if est:
            E, UTS, el = EST_MECH.get(fam, (1500, 25, 5))
        dens = t.get("density") if own and t.get("density") else (prof_dens or t.get("density") or 1.24)
        if t:
            src = "Bambu %s TDS %s" % (tkey.replace("_", " "), t.get("ver") or "")
            if not own:
                src += " (nearest Bambu TDS; density from Bambu Studio profile)"
        else:
            src = "Bambu Studio profile density"
        if est:
            src += "; mechanics = generic estimate (not published by Bambu)"
        g = GENERIC[fam]
        hexes = [h[:7].upper() for h in x["fila_color"]]
        alphas = [int(h[7:9], 16) if len(h) >= 9 else 255 for h in x["fila_color"]]
        names = x.get("fila_color_name") or {}
        out.append(dict(
            line=line, family=fam, filament_id=x.get("fila_id"), color_code=x["fila_color_code"],
            name_en=(names.get("en") or "").strip(), name_ko=(names.get("ko") or "").strip(),
            color_type=COLOR_TYPE.get(x.get("fila_color_type"), x.get("fila_color_type")),
            hex=hexes, alpha=alphas, style="translucent" if min(alphas) < 255 else style, roughness=rough,
            density=dens, youngs_mpa=E, tensile_mpa=UTS, yield_mpa=UTS, elongation_pct=el,
            hdt_045_c=t.get("HDT"), vicat_c=t.get("vicat"),
            nozzle_c=clean(t.get("nozzle")), bed_c=clean(t.get("bed")), drying=clean(t.get("dry")),
            poisson=g["poisson"], thermal_conductivity=g["k"], specific_heat=g["cp"], thermal_expansion=g["cte"],
            mech_source=src, color_source="BambuStudio resources/profiles/BBL/filament/filaments_color_codes.json",
        ))
    order = list(GENERIC)
    out.sort(key=lambda r: (order.index(r["family"]), r["line"], r["color_code"]))
    return out


def apply_lines(table):
    """Merge a lines.json table {line: [family, tds key, density, style, roughness]} into LINES."""
    for line, v in (table or {}).items():
        if isinstance(v, list) and len(v) == 5 and v[0] in GENERIC and v[3] in ROUGH:
            LINES[line] = tuple(v)


def export_lines(path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({k: list(v) for k, v in sorted(LINES.items())}, f, ensure_ascii=False, indent=1)


def _remote_json(name, notes):
    try:
        return json.loads(fetch(REPO_RAW + name, timeout=15))
    except Exception as e:
        notes.append("Could not get %s from the project repository (%s); using bundled copy" % (name, e))
        return None


def load(folder=HERE, online=True):
    """Return (records, source_text, notes). Online: latest Bambu color table; offline/failure: bundled snapshot."""
    notes = []
    tds = json.load(open(os.path.join(folder, "tds_all.json"), encoding="utf-8"))
    lp = os.path.join(folder, "lines.json")
    if os.path.exists(lp):
        apply_lines(json.load(open(lp, encoding="utf-8")))
    if online:
        remote_tds = _remote_json("tds_all.json", notes)
        if isinstance(remote_tds, dict) and remote_tds:
            tds = remote_tds
        apply_lines(_remote_json("lines.json", notes))
        try:
            colors = json.loads(fetch(COLORS_URL))["data"]
            recs = build_records(colors, tds, True, notes)
            if recs:
                return recs, "online (Bambu Studio GitHub, latest)", notes
        except Exception as e:
            notes.append("Online update failed, using bundled data: %s" % e)
    recs = json.load(open(os.path.join(folder, "bambu_filaments.json"), encoding="utf-8"))
    return recs, "bundled snapshot", notes
