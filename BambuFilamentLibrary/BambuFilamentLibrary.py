# Bambu Lab Filament Library for Autodesk Fusion
#
# Run it from Fusion (Shift+S > Scripts and Add-Ins > BambuFilamentLibrary > Run).
# 1. Downloads the latest official Bambu Lab color table (falls back to the bundled copy when offline).
# 2. Creates one Appearance per filament color (official hex) and one physical Material per product line
#    (density, modulus, strength, thermal values from Bambu technical data sheets) in a new design.
# 3. Adds them to Fusion Favorites so they are available in every design. Items already in Favorites are skipped.
import adsk.core, adsk.fusion, importlib, json, os, re, sys, traceback

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
RECOLOR_THUMBNAILS = True        # offer to recolor the white Favorites thumbnails (runs after Fusion closes)
SHOW_SELECTOR = True             # show the selection window (False: add everything missing, no window)

AUTHOR = "UDTT Studio (우당탕탕 스튜디오)"
LINKS = {
    "github": "https://github.com/mtenemy2/fusion-bambu-filament-library",
    "youtube": "https://www.youtube.com/@udtt_studio",   # empty = hidden
}
DISCLAIMER = (
    "This is an unofficial, free program (not affiliated with Bambu Lab or Autodesk), provided AS IS.\n"
    "The author is not responsible for any problem caused by running it, including damage to Fusion libraries, "
    "Favorites or design files, or data loss. Back up important data first.\n\n"
    "이 프로그램은 Bambu Lab·Autodesk와 관계없는 비공식 무료 프로그램이며 있는 그대로 제공됩니다. "
    "실행으로 인해 발생하는 어떠한 문제(라이브러리·즐겨찾기·디자인 파일 손상, 데이터 손실 등)에도 제작자는 책임을 지지 않습니다.\n\n"
    "Do you agree and want to continue? / 동의하고 계속하시겠습니까?")

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


# ---------- thumbnails ----------
def favorite_ids(app):
    """{color code: asset id} of the Bambu appearances in Favorites (used to find their thumbnail files)."""
    ids = {}
    favs = app.favoriteAppearances
    for i in range(favs.count):
        a = favs.item(i)
        m = re.match(r"^%s .*\[(\d{5})\]$" % re.escape(PREFIX), a.name)
        if m:
            ids[m.group(1)] = a.id
    return ids


def helper_python():
    """Path of Fusion's bundled python executable (sys.executable is Fusion itself)."""
    import glob
    roots = {sys.prefix, sys.base_prefix, sys.exec_prefix, os.path.dirname(sys.executable or "")}
    try:
        roots.add(os.path.dirname(os.path.dirname(json.__file__)))     # .../Python/Lib/json -> .../Python
        roots.add(os.path.dirname(os.path.dirname(os.path.dirname(json.__file__))))
    except Exception:
        pass
    cands = []
    for r in roots:
        if not r:
            continue
        cands += [os.path.join(r, "python.exe"), os.path.join(r, "Python", "python.exe"),
                  os.path.join(r, "bin", "python3"), os.path.join(r, "Python", "bin", "python3")]
        cands += glob.glob(os.path.join(r, "**", "bin", "python3"), recursive=False)
    if sys.executable and "python" in os.path.basename(sys.executable).lower():
        cands.append(sys.executable)
    for p in cands:
        if os.path.isfile(p):
            return p
    log("python candidates tried:", cands)
    return None


def read_state(app, data):
    """Mark records/lines that are already in Favorites, and those whose Favorites copy is outdated."""
    favA, favM = app.favoriteAppearances, app.favoriteMaterials
    mats = {}
    for r in data:
        mn = material_name(r)
        if mn not in mats:
            fm = by_name(favM, mn)
            st = False
            if fm:
                d = read_density(fm)
                st = d is not None and abs(d - r["density"]) > 0.005
            mats[mn] = (bool(fm), st)
    colors = {}
    for r in data:
        fa = by_name(favA, entry_name(r))
        st = False
        if fa:
            h = read_hex(fa)
            st = bool(h and h != target_hex(r))
        colors[r["color_code"]] = (bool(fa), st)
    return colors, mats


def make_payload(data, source, colors_state, mats_state):
    fams, lines = [], {}
    for r in data:
        if r["family"] not in fams:
            fams.append(r["family"])
        lines.setdefault(r["line"], []).append(r)
    cols = [dict(code=r["color_code"], line=r["line"], family=r["family"], name_en=r["name_en"], name_ko=r["name_ko"],
                 hex=r["hex"], alpha=r["alpha"], style=r["style"], installed=colors_state[r["color_code"]][0],
                 stale=colors_state[r["color_code"]][1]) for r in data]
    mats = []
    for line, rs in lines.items():
        r = rs[0]
        inst, st = mats_state[material_name(r)]
        mats.append(dict(line=line, family=r["family"], density=round(r["density"], 3), E=round(r["youngs_mpa"]),
                         UTS=r["tensile_mpa"], nozzle=r["nozzle_c"], source=r["mech_source"], ncolors=len(rs),
                         installed=inst, stale=st))
    version, updated = version_info()
    return dict(source=source, families=fams, colors=cols, materials=mats,
                recolor_available=bool(RECOLOR_THUMBNAILS and helper_python()),
                version=version, updated=updated, author=AUTHOR, links=LINKS)


def version_info():
    """(version, last update date) from the manifest; the version is the release date, e.g. 2026.11.17.1."""
    try:
        with open(os.path.join(HERE, "BambuFilamentLibrary.manifest"), encoding="utf-8") as f:
            v = json.load(f).get("version", "")
    except Exception:
        return "", ""
    m = re.match(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})", v)
    return v, ("%s-%02d-%02d" % (m.group(1), int(m.group(2)), int(m.group(3))) if m else "")


def build(app, ui, title, data, codes, lines):
    """Create the selected color appearances and line materials in a new design and add them to Favorites."""
    todo = [r for r in data if r["color_code"] in codes]
    mat_rows = {}
    for r in data:
        if r["line"] in lines and r["line"] not in mat_rows:
            mat_rows[r["line"]] = r
    if not todo and not mat_rows:
        return 0, 0, 0
    favA, favM = app.favoriteAppearances, app.favoriteMaterials
    app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)
    design = adsk.fusion.Design.cast(app.activeProduct)
    um = design.unitsManager
    libs = app.materialLibraries
    app_libs = [libs.item(i) for i in range(libs.count) if "appearance" in libs.item(i).name.lower()]
    mat_lib = by_name(libs, "Fusion Material Library") or next(
        (libs.item(i) for i in range(libs.count) if "material" in libs.item(i).name.lower()), None)
    base_app = {}
    for style in sorted({r["style"] for r in todo}):
        a = find_appearance(app_libs, style)
        if not a:
            raise Exception("No base appearance found for style " + style)
        base_app[style] = by_name(design.appearances, a.name) or design.appearances.addByCopy(a, a.name)
        log("Base appearance", style, "->", a.name)
    base_mat = {}
    for fam in sorted({r["family"] for r in mat_rows.values()}):
        base_mat[fam] = find_material(mat_lib, fam)
        log("Base material", fam, "->", base_mat[fam].name)

    prog = ui.createProgressDialog()
    prog.isCancelButtonShown = True
    prog.show(title, "%v / %m  " + "%p%", 0, len(todo) + len(mat_rows), 0)
    made_a = made_m = fav_added = 0
    step = 0
    for r in todo:
        if prog.wasCancelled:
            break
        prog.progressValue = step
        step += 1
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
        made_a += 1
        if ADD_TO_FAVORITES and not by_name(favA, name) and favA.add(ap):
            fav_added += 1
        adsk.doEvents()
    for line, r in mat_rows.items():
        if prog.wasCancelled:
            break
        prog.progressValue = step
        step += 1
        mname = material_name(r)
        mt = by_name(design.materials, mname)
        if not mt:   # one physical material per product line (the API cannot link it to a color appearance)
            mt = design.materials.addByCopy(base_mat[r["family"]], mname)
            set_physical(mt, r, um)
        made_m += 1
        if ADD_TO_FAVORITES and not by_name(favM, mname) and favM.add(mt):
            fav_added += 1
        adsk.doEvents()
    prog.hide()
    log("Created:", made_a, "appearances,", made_m, "materials; favorites added:", fav_added)
    return made_a, made_m, fav_added


def schedule_thumbnail_fix(app, ui, title, ask=True):
    """Fusion cannot re-render thumbnails, so recolor them in Favorites.adsklib after Fusion closes."""
    if not RECOLOR_THUMBNAILS:
        return False
    ids = favorite_ids(app)
    if not ids:
        return False
    with open(os.path.join(HERE, "favorites_ids.json"), "w", encoding="utf-8") as f:
        json.dump(ids, f, indent=0)
    done_p = os.path.join(HERE, "thumbnails_done.json")
    done = set(json.load(open(done_p, encoding="utf-8"))) if os.path.exists(done_p) else set()
    todo = [c for c in ids if c not in done]
    if not todo:
        return False
    py = helper_python()
    if not py:
        log("thumbnail fix: bundled python not found")
        return False
    if ask:
        q = ("%d Bambu appearances in Favorites still show the white preview thumbnail.\n\n"
             "Recolor them to the real filament colors?\n\n"
             "Fusion cannot change thumbnails while it is running, so the fix runs automatically right after you\n"
             "CLOSE Fusion (about 30 seconds). Open Fusion again afterwards to see the colored thumbnails.\n"
             "A backup of the Favorites library is kept.") % len(todo)
        if ui.messageBox(q, title, adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                         adsk.core.MessageBoxIconTypes.QuestionIconType) != adsk.core.DialogResults.DialogYes:
            return False
    import subprocess
    args = [py, "-I", os.path.join(HERE, "thumbs.py"), "--wait-pid", str(os.getpid())]
    kw = dict(cwd=HERE, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
    if sys.platform == "win32":
        flags = 0x00000008 | 0x00000200 | 0x08000000                 # detached, new group, no window
        try:   # also leave Fusion's job object so the helper survives Fusion closing
            subprocess.Popen(args, creationflags=flags | 0x01000000, **kw)
        except OSError:
            subprocess.Popen(args, creationflags=flags, **kw)
    else:
        subprocess.Popen(args, start_new_session=True, **kw)
    log("thumbnail fix scheduled:", args)
    return True


def finish_message(ui, title, made_a, made_m, fav_added, scheduled, stale_n):
    msg = ("Done.\n\n%d color appearances and %d materials created (Favorites +%d).\n"
           "Save the new design (e.g. 'Bambu Filament Library') if you want a reference file.\n\n"
           "Use:  Physical Material > 'Bambu <line>'  (mass, simulation)\n"
           "        Appearance > 'Bambu <line> - <color>'  (look)") % (made_a, made_m, fav_added)
    already = made_a + made_m - fav_added
    if ADD_TO_FAVORITES and already > 0:
        msg = msg.replace("(Favorites +%d)." % fav_added,
                          "(Favorites +%d, %d were already in Favorites)." % (fav_added, already))
    if scheduled:
        msg += "\n\nThumbnails: CLOSE Fusion to recolor them (about 30 s), then open Fusion again."
    if stale_n:
        msg += "\n\n%d Favorites entries are outdated - remove them from Favorites and install again to refresh." % stale_n
    ui.messageBox(msg, title)


# ---------- selection window (HTML palette) ----------
PALETTE_ID = "BambuFilamentLibrarySelector"
EVENT_ID = "BambuFilamentLibraryInstall"
STATE = {}
HANDLERS = []


def _finish():
    app = adsk.core.Application.get()
    try:
        pal = app.userInterface.palettes.itemById(PALETTE_ID)
        if pal:
            pal.deleteMe()
    except Exception:
        pass
    try:
        app.unregisterCustomEvent(EVENT_ID)
    except Exception:
        pass
    write_log()
    adsk.terminate()


class _HTMLHandler(adsk.core.HTMLEventHandler):
    def notify(self, args):
        a = adsk.core.HTMLEventArgs.cast(args)
        try:
            if a.action == "ready":
                a.returnData = STATE["payload"]
            elif a.action == "agree":
                log("Disclaimer accepted")
                a.returnData = "OK"
            elif a.action == "open":
                url = LINKS.get(json.loads(a.data or "{}").get("which", ""), "")
                if url.startswith("https://"):      # only the fixed credit links, never a URL sent by the page
                    import webbrowser
                    webbrowser.open(url)
                a.returnData = "OK"
            elif a.action in ("install", "cancel"):
                STATE["selection"] = json.loads(a.data or "{}")
                a.returnData = "OK"
                adsk.core.Application.get().fireCustomEvent(EVENT_ID, a.action)
        except Exception:
            log("ERROR html", traceback.format_exc())


class _ClosedHandler(adsk.core.UserInterfaceGeneralEventHandler):
    def notify(self, args):
        if not STATE.get("busy"):
            _finish()


class _InstallHandler(adsk.core.CustomEventHandler):
    def notify(self, args):
        app = adsk.core.Application.get()
        ui = app.userInterface
        title = "Bambu Lab Filament Library"
        try:
            if args.additionalInfo != "install" or STATE.get("busy"):
                _finish()
                return
            STATE["busy"] = True
            sel = STATE.get("selection") or {}
            pal = ui.palettes.itemById(PALETTE_ID)
            if pal:
                pal.isVisible = False
            codes, lines = set(sel.get("colors") or []), set(sel.get("materials") or [])
            log("Selected:", len(codes), "colors,", len(lines), "materials")
            made_a, made_m, fav_added = build(app, ui, title, STATE["data"], codes, lines)
            scheduled = bool(sel.get("recolor")) and schedule_thumbnail_fix(app, ui, title, ask=False)
            stale_n = sum(1 for c in codes if STATE["colors_state"].get(c, (0, 0))[1]) + \
                sum(1 for l in lines if STATE["mats_state"].get("%s %s" % (PREFIX, l.replace("/", "-")), (0, 0))[1])
            finish_message(ui, title, made_a, made_m, fav_added, scheduled, stale_n)
        except Exception:
            log("ERROR", traceback.format_exc())
            ui.messageBox("Failed:\n" + traceback.format_exc(), title)
        finally:
            _finish()


def show_selector(app, data, source):
    ui = app.userInterface
    colors_state, mats_state = read_state(app, data)
    STATE.update(data=data, colors_state=colors_state, mats_state=mats_state, busy=False,
                 payload=json.dumps(make_payload(data, source, colors_state, mats_state), ensure_ascii=False))
    old = ui.palettes.itemById(PALETTE_ID)
    if old:
        old.deleteMe()
    try:
        app.unregisterCustomEvent(EVENT_ID)
    except Exception:
        pass
    ev = app.registerCustomEvent(EVENT_ID)
    h_inst = _InstallHandler()
    ev.add(h_inst)
    html = os.path.join(HERE, "ui", "selector.html").replace("\\", "/")
    pal = ui.palettes.add(PALETTE_ID, "Bambu Lab Filament Library", html, True, True, True, 780, 860, True)
    pal.dockingState = adsk.core.PaletteDockingStates.PaletteDockStateFloating
    h_html, h_close = _HTMLHandler(), _ClosedHandler()
    pal.incomingFromHTML.add(h_html)
    pal.closed.add(h_close)
    HANDLERS.extend([h_inst, h_html, h_close])
    adsk.autoTerminate(False)


def write_log():
    try:
        with open(os.path.join(HERE, "last_run_log.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(LOG))
    except Exception:
        pass


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
        if SHOW_SELECTOR:
            try:
                show_selector(app, data, source)
                write_log()
                return
            except Exception:
                log("selector window failed, using simple dialogs:", traceback.format_exc())
        # ---- simple fallback: everything not yet in Favorites
        colors_state, mats_state = read_state(app, data)
        codes = {c for c, (inst, _) in colors_state.items() if not inst}
        lines = {r["line"] for r in data if not mats_state[material_name(r)][0]}
        version, updated = version_info()
        if ui.messageBox(DISCLAIMER, "%s  v%s (%s)" % (title, version, updated),
                         adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                         adsk.core.MessageBoxIconTypes.WarningIconType) != adsk.core.DialogResults.DialogYes:
            log("Disclaimer declined")
            write_log()
            return
        q = "Data: %s\n%d colors / %d materials not yet in Favorites.\n\nAdd them now?" % (source, len(codes), len(lines))
        if (codes or lines) and ui.messageBox(q, title, adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                                               adsk.core.MessageBoxIconTypes.QuestionIconType) == adsk.core.DialogResults.DialogYes:
            made_a, made_m, fav_added = build(app, ui, title, data, codes, lines)
            finish_message(ui, title, made_a, made_m, fav_added, False, 0)
        schedule_thumbnail_fix(app, ui, title, ask=True)
        write_log()
    except Exception:
        log("ERROR", traceback.format_exc())
        write_log()
        ui.messageBox("Failed:\n" + traceback.format_exc(), title)
