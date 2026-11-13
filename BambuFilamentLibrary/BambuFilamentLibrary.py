# Bambu Lab Filament Library for Autodesk Fusion
#
# Run it from Fusion (Shift+S > Scripts and Add-Ins > BambuFilamentLibrary > Run).
# 1. Downloads the latest official Bambu Lab color table (falls back to the bundled copy when offline).
# 2. Creates one Appearance per filament color (official hex) and one physical Material per product line
#    (density, modulus, strength, thermal values from Bambu technical data sheets) in a new design.
# 3. Adds them to Fusion Favorites so they are available in every design. Items already in Favorites are skipped.
import adsk.core, adsk.fusion, importlib, os, sys, traceback

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import bambu_data
importlib.reload(bambu_data)

ONLINE_UPDATE = True             # download the latest Bambu color table before building
ADD_TO_FAVORITES = True          # add created appearances/materials to Favorites
FAMILIES = None                  # None = all; or e.g. ("PLA", "PETG", "ABS", "ASA", "TPU")
PREFIX = "Bambu"
TEST_MODE = False                # True: build only a small sample, for checking

LOG = []


def log(*a):
    LOG.append(" ".join(str(x) for x in a))


def hex_rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def by_name(coll, name):
    """itemByName that returns None instead of raising when the name is missing."""
    try:
        return coll.itemByName(name)
    except Exception:
        return None


def props_of(obj):
    return [obj.item(i) for i in range(obj.count)]


# ---------- base asset selection ----------
APPEARANCE_CANDIDATES = {
    "glossy":      ["Plastic - Glossy (White)", "Plastic - Glossy (Black)", "Plastic - Glossy"],
    "satin":       ["Plastic - Matte (White)", "Plastic - Glossy (White)", "Plastic - Matte"],
    "matte":       ["Plastic - Matte (White)", "Plastic - Matte (Black)", "Plastic - Matte"],
    "silk":        ["Plastic - Glossy (White)", "Plastic - Glossy"],
    "sparkle":     ["Plastic - Glossy (White)", "Plastic - Glossy"],
    "metal":       ["Paint - Metallic (Silver)", "Paint - Metal Flake", "Plastic - Glossy (White)"],
    "translucent": ["Plastic - Translucent Glossy (Clear)", "Plastic - Translucent Glossy (White)",
                    "Plastic - Transparent", "Glass - Clear", "Plastic - Translucent"],
}
COLOR_IDS = ["opaque_albedo", "transparent_color", "metal_f0", "layered_diffuse", "generic_diffuse", "metal_color"]


def color_prop(appearance, translucent):
    ps = {p.id: p for p in props_of(appearance.appearanceProperties)}
    order = (["transparent_color"] + COLOR_IDS) if translucent else COLOR_IDS
    for pid in order:
        p = ps.get(pid)
        if p and adsk.core.ColorProperty.cast(p) and not p.isReadOnly:
            cp = adsk.core.ColorProperty.cast(p)
            if not cp.hasConnectedTexture:
                return cp
    for p in ps.values():   # fallback: first writable untextured color
        cp = adsk.core.ColorProperty.cast(p)
        if cp and not cp.isReadOnly and not cp.hasConnectedTexture and "spec" not in p.id.lower():
            return cp
    return None


def find_appearance(libs, style):
    byname = {}
    for lib in libs:
        try:
            for i in range(lib.appearances.count):
                a = lib.appearances.item(i)
                byname.setdefault(a.name, a)
        except Exception:
            pass
    for n in APPEARANCE_CANDIDATES[style]:
        if n in byname:
            return byname[n]
    for n in APPEARANCE_CANDIDATES[style]:          # prefix match
        for name, a in byname.items():
            if name.startswith(n):
                return a
    for name, a in byname.items():
        if name.lower().startswith("plastic"):
            return a
    return None


MATERIAL_CANDIDATES = {
    "PLA":  ["PLA", "Polylactic Acid", "PLA Plastic", "ABS Plastic"],
    "PETG": ["PETG", "PET Plastic", "Polyethylene Terephthalate", "ABS Plastic"],
    "ABS":  ["ABS Plastic", "ABS"],
    "ASA":  ["ASA", "ABS Plastic"],
    "TPU":  ["Thermoplastic Polyurethane", "TPU", "Polyurethane", "Rubber", "ABS Plastic"],
    "PC":   ["Polycarbonate", "PC Plastic", "ABS Plastic"],
    "PA":   ["Nylon 6/6", "Nylon 6", "Nylon", "Polyamide", "ABS Plastic"],
    "PET":  ["PET Plastic", "Polyethylene Terephthalate", "ABS Plastic"],
    "PPS":  ["Polyphenylene Sulfide", "PPS", "Nylon 6/6", "ABS Plastic"],
    "PVA":  ["Polyvinyl Alcohol", "PVA", "ABS Plastic"],
    "Support": ["ABS Plastic"],
}


def find_material(lib, fam):
    mats = {lib.materials.item(i).name: lib.materials.item(i) for i in range(lib.materials.count)}
    cands = MATERIAL_CANDIDATES.get(fam, ["ABS Plastic"])
    for n in cands:
        if n in mats:
            return mats[n]
    for n in cands:
        for name, m in mats.items():
            if n.lower() in name.lower():
                return m
    for name, m in mats.items():
        if "plastic" in name.lower():
            return m
    return mats[next(iter(mats))]


# ---------- physical property writing ----------
# Fusion material property unit names -> factor to multiply an SI value by
UNIT_FACTOR = {
    "KilogramPerCubicMeter": 1.0, "GramPerCubicCentimeter": 1e-3, "KilogramPerCubicCentimeter": 1e-6,
    "Pascal": 1.0, "Kilopascal": 1e-3, "Megapascal": 1e-6, "Gigapascal": 1e-9,
    "JoulePerKilogramCelsius": 1.0, "JoulePerKilogramKelvin": 1.0, "JoulePerGramCelsius": 1e-3, "JoulePerGramKelvin": 1e-3,
    "WattPerMeterKelvin": 1.0, "WattPerMeterCelsius": 1.0,
    "PerCelsius": 1.0, "PerKelvin": 1.0, "MicrometerPerMeterCelsius": 1e6, "MicrometerPerMeterKelvin": 1e6,
    "Unitless": 1.0,
}
WARNED = set()


def set_float(prop, si_value, si_unit, um):
    fp = adsk.core.FloatProperty.cast(prop)
    if not fp or fp.isReadOnly:
        return False
    v = si_value
    if fp.units:
        if fp.units in UNIT_FACTOR:
            v = si_value * UNIT_FACTOR[fp.units]
        else:
            try:
                v = um.convert(si_value, si_unit, fp.units)
            except Exception:
                if (prop.id, fp.units) not in WARNED:
                    WARNED.add((prop.id, fp.units))
                    log("  ! unknown unit", prop.id, si_unit, "->", fp.units)
                return False
    if fp.hasMultipleValues:
        fp.values = [v] * len(fp.values)
    else:
        fp.value = v
    return True


def set_physical(mat, r, um):
    E = r["youngs_mpa"] * 1e6
    nu = r["poisson"]
    targets = [  # (match keys in id/name, SI value, SI unit string)
        (("density",), r["density"] * 1000.0, "kg/m^3"),
        (("young",), E, "Pa"),
        (("poisson",), nu, ""),
        (("shear_modulus", "shear modulus"), E / (2 * (1 + nu)), "Pa"),
        (("yield",), r["yield_mpa"] * 1e6, "Pa"),
        (("tensile",), r["tensile_mpa"] * 1e6, "Pa"),
        (("thermal_conductivity", "thermal conductivity"), r["thermal_conductivity"], "W/(m*K)"),
        (("specific_heat", "specific heat"), r["specific_heat"], "J/(kg*K)"),
        (("expansion",), r["thermal_expansion"], "1/K"),
    ]
    info = {
        "physmat_Manufacturer": "Bambu Lab",
        "physmat_Comments": "%s | nozzle %s C, bed %s C, dry %s | HDT(0.45MPa) %s C | %s" % (
            r["line"], r["nozzle_c"], r["bed_c"], r["drying"], r["hdt_045_c"], r["mech_source"]),
        "structural_source": r["mech_source"],
    }
    for pid, txt in info.items():
        sp = adsk.core.StringProperty.cast(mat.materialProperties.itemById(pid))
        if sp and not sp.isReadOnly:
            try:
                sp.value = txt
            except Exception:
                pass
    done = []
    for p in props_of(mat.materialProperties):
        key = (p.id + " " + p.name).lower()
        for keys, val, unit in targets:
            if any(k in key for k in keys):
                if unit == "":
                    fp = adsk.core.FloatProperty.cast(p)
                    if fp and not fp.isReadOnly:
                        if fp.hasMultipleValues:
                            fp.values = [val] * len(fp.values)
                        else:
                            fp.value = val
                        done.append(p.id)
                elif set_float(p, val, unit, um):
                    done.append(p.id)
                break
    return done


# ---------- naming / comparison ----------
def entry_name(r):
    n = "%s %s - %s" % (PREFIX, r["line"].replace("/", "-"), r["name_en"])
    if r["name_ko"] and r["name_ko"] != r["name_en"]:
        n += " (%s)" % r["name_ko"]
    return n + " [%s]" % r["color_code"]


def material_name(r):
    return "%s %s" % (PREFIX, r["line"].replace("/", "-"))


def target_hex(r):
    h = r["hex"][0]
    if r["style"] == "translucent" and r["alpha"][0] == 0:     # "Clear"
        h = "#F4F7F8"
    return h.upper()


def read_hex(appearance):
    """Current main color of an existing (favorite) appearance, or None."""
    try:
        ps = {p.id: p for p in props_of(appearance.appearanceProperties)}
        for pid in ["transparent_color"] + COLOR_IDS:
            cp = adsk.core.ColorProperty.cast(ps.get(pid)) if ps.get(pid) else None
            if cp and not cp.hasConnectedTexture:
                c = cp.value
                return "#%02X%02X%02X" % (c.red, c.green, c.blue)
    except Exception:
        pass
    return None


def read_density(material):
    """Density of an existing (favorite) material in g/cm3, or None."""
    try:
        fp = adsk.core.FloatProperty.cast(material.materialProperties.itemById("structural_Density"))
        if fp and fp.units in UNIT_FACTOR:
            return fp.value / UNIT_FACTOR[fp.units] / 1000.0
    except Exception:
        pass
    return None


def run(context):
    app = adsk.core.Application.get()
    ui = app.userInterface
    title = "Bambu Lab Filament Library"
    try:
        data, source, notes = bambu_data.load(HERE, online=ONLINE_UPDATE)
        for n in notes:
            log("note:", n)
        if FAMILIES:
            data = [r for r in data if r["family"] in FAMILIES]
        if TEST_MODE:   # one sample per style and per family
            seen, sample = set(), []
            for r in data:
                for k in (r["style"], r["family"]):
                    if k not in seen:
                        seen.add(k)
                        if r not in sample:
                            sample.append(r)
            data = sample

        # ---- compare with Favorites
        favA, favM = app.favoriteAppearances, app.favoriteMaterials
        new_rows, stale, mats_seen = [], [], {}
        for r in data:
            mn = material_name(r)
            if mn not in mats_seen:
                fm = by_name(favM, mn)
                mats_seen[mn] = fm
                if fm:
                    d = read_density(fm)
                    if d is not None and abs(d - r["density"]) > 0.005:
                        stale.append("material    %s  (density %.2f -> %.2f)" % (mn, d, r["density"]))
            fa = by_name(favA, entry_name(r))
            if fa:
                h = read_hex(fa)
                if h and h != target_hex(r):
                    stale.append("appearance  %s  (%s -> %s)" % (entry_name(r), h, target_hex(r)))
            if not fa or not mats_seen[mn]:
                new_rows.append(r)
        n_lines = len({r["line"] for r in data})
        summary = ("Data: %s\n%d colors / %d product lines\n\n"
                   "Not yet in Favorites: %d\nAlready in Favorites: %d\nOutdated in Favorites: %d\n"
                   % (source, len(data), n_lines, len(new_rows), len(data) - len(new_rows), len(stale)))
        if notes:
            summary += "\n" + "\n".join(notes[:5]) + "\n"
        if new_rows:
            q = summary + "\nAdd the %d missing colors to Favorites now?" % len(new_rows)
        else:
            q = summary + "\nEverything is already in Favorites.\nBuild a full library design anyway (to save as a reference file)?"
        res = ui.messageBox(q, title, adsk.core.MessageBoxButtonTypes.YesNoButtonType, adsk.core.MessageBoxIconTypes.QuestionIconType)
        if res != adsk.core.DialogResults.DialogYes:
            log("Cancelled by user")
            return
        todo = new_rows if new_rows else data

        app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
        design = adsk.fusion.Design.cast(app.activeProduct)
        um = design.unitsManager

        libs = app.materialLibraries
        app_libs = [libs.item(i) for i in range(libs.count) if "appearance" in libs.item(i).name.lower()]
        mat_lib = by_name(libs, "Fusion Material Library") or next(
            (libs.item(i) for i in range(libs.count) if "material" in libs.item(i).name.lower()), None)
        log("Libraries:", [libs.item(i).name for i in range(libs.count)])

        base_app = {}
        for style in sorted({r["style"] for r in todo}):
            a = find_appearance(app_libs, style)
            if not a:
                raise Exception("No base appearance found for style " + style)
            base_app[style] = by_name(design.appearances, a.name) or design.appearances.addByCopy(a, a.name)
            log("Base appearance", style, "->", a.name)
        base_mat = {}
        for fam in sorted({r["family"] for r in todo}):
            base_mat[fam] = find_material(mat_lib, fam)
            log("Base material", fam, "->", base_mat[fam].name)

        prog = ui.createProgressDialog()
        prog.isCancelButtonShown = True
        prog.show(title, "%v / %m  " + "%p%", 0, len(todo), 0)

        made, lines_made, fav_added = 0, [], 0
        for i, r in enumerate(todo):
            if prog.wasCancelled:
                break
            prog.progressValue = i
            name = entry_name(r)

            ap = by_name(design.appearances, name) or design.appearances.addByCopy(base_app[r["style"]], name)
            cp = color_prop(ap, r["style"] == "translucent")
            rr, gg, bb = hex_rgb(target_hex(r))
            if cp:
                cp.value = adsk.core.Color.create(rr, gg, bb, 255)
            else:
                log("  ! no color property", name)
            for p in props_of(ap.appearanceProperties):
                if p.id == "surface_roughness":
                    fp = adsk.core.FloatProperty.cast(p)
                    if fp and not fp.isReadOnly:
                        fp.value = r["roughness"]

            mname = material_name(r)
            mt = by_name(design.materials, mname)
            if not mt:      # one physical material per product line (the API cannot link it to a color appearance)
                mt = design.materials.addByCopy(base_mat[r["family"]], mname)
                set_physical(mt, r, um)
                lines_made.append(mname)
                if ADD_TO_FAVORITES and not by_name(favM, mname) and favM.add(mt):
                    fav_added += 1
            if ADD_TO_FAVORITES and not by_name(favA, name) and favA.add(ap):
                fav_added += 1
            made += 1
            adsk.doEvents()
        prog.hide()

        log("Created:", made, "appearances,", len(lines_made), "materials; favorites added:", fav_added)
        report = [title, "data: " + source, "created: %d appearances, %d materials" % (made, len(lines_made)),
                  "added to Favorites: %d" % fav_added, ""]
        if stale:
            report += ["Outdated Favorites - remove them from Favorites, then run the script again to refresh:"]
            report += ["  " + s for s in stale]
        with open(os.path.join(HERE, "last_report.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(report))
        msg = ("Done.\n\n%d color appearances and %d line materials created%s.\n"
               "Save this design (e.g. 'Bambu Filament Library') if you want a reference file.\n\n"
               "Use:  Physical Material > 'Bambu <line>'  (mass, simulation)\n"
               "        Appearance > 'Bambu <line> - <color>'  (look)") % (
            made, len(lines_made), " (Favorites +%d)" % fav_added if ADD_TO_FAVORITES else "")
        if stale:
            msg += "\n\n%d Favorites entries are outdated - see last_report.txt in the script folder." % len(stale)
        ui.messageBox(msg, title)
    except Exception:
        log("ERROR", traceback.format_exc())
        ui.messageBox("Failed:\n" + traceback.format_exc(), title)
    finally:
        try:
            with open(os.path.join(HERE, "last_run_log.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(LOG))
        except Exception:
            pass
