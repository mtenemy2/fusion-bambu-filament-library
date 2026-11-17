"""Monthly maintainer tool for the Bambu Lab -> Fusion filament library.

What it does
  1. download the official color table from the BambuStudio repo (filaments_color_codes.json)
  2. try to download a Bambu TDS PDF for every product line that has none yet (cached in data/tds)
  3. parse all TDS PDFs -> tds_all.json (data/ and the package folder)
  4. rebuild BambuFilamentLibrary/bambu_filaments.json + .csv with the same code the Fusion script uses (bambu_data.py)
  5. compare with the previous data -> data/update_report.md (+ .json)
  6. build the shareable zip  dist/BambuFilamentLibrary_<version>.zip  (version = date of the last data change)
  7. copy the package into this PC's Fusion Scripts folder

Run:  python -I tools/update_library.py              (add --no-install to skip step 7)
"""
import csv, datetime, json, os, re, shutil, sys, urllib.parse, zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
DATA = os.path.join(ROOT, "data")
TDS_DIR = os.path.join(DATA, "tds")
LIBDIR = os.path.join(ROOT, "BambuFilamentLibrary")
DIST = os.path.join(ROOT, "dist")
FUSION_SCRIPTS = os.path.join(os.environ.get("APPDATA", ""), "Autodesk", "Autodesk Fusion 360", "API", "Scripts", "BambuFilamentLibrary")
PACKAGE_FILES = ["BambuFilamentLibrary.py", "BambuFilamentLibrary.manifest", "bambu_data.py", "bambu_filaments.json",
                 "bambu_filaments.csv", "tds_all.json", "lines.json", "thumbs.py", "README_KO.txt", "README_EN.txt", "README.md", "NOTICE.md"]
sys.path.insert(0, os.path.join(TOOLS, "pylib"))
sys.path.insert(0, LIBDIR)
import bambu_data  # noqa: E402  (shared with the Fusion script)

TDS_URL = "https://cdn.shopify.com/s/files/1/{p}/files/{pre}{name}_Technical_Data_Sheet.pdf"
SHOPIFY_PATHS = ["0380/5149", "0645/5876/0155", "0584/7236/6216"]


def parse_pdf(path):
    from pypdf import PdfReader
    t = "\n".join(p.extract_text() or "" for p in PdfReader(path).pages)
    t = re.sub(r"[ \t]+", " ", t)

    def L(label, anchor):
        m = re.search(label + r"[^\n]*?" + anchor + r" ?>? ?([\d.]+)", t)
        return float(m.group(1)) if m else None
    g = lambda p: (re.search(p, t) or [None, None])[1]
    return dict(
        density=L(r"Density", r"1183"),
        E=L(r"Young.s Modulus \(X-Y\)", r"1040") or L(r"Young.s Modulus", r"1040"),
        UTS=L(r"Tensile Strength \(X-Y\)", r"1040") or L(r"Tensile Strength", r"1040"),
        elong=L(r"Elongation Rate \(X-Y\)", r"1040") or L(r"Elongation", r"1040"),
        HDT=L(r"Heat Deflection Temperature", r"0\.45 ?MPa") or L(r"Heat Deflection Temperature", r"1\.8 ?MPa"),
        vicat=L(r"Vica\w* Softening Temperature", r"1633"),
        nozzle=g(r"Nozzle Temperature ([\d]+ ?- ?[\d]+)"), bed=g(r"Bed Temperature ([\d]+ ?- ?[\d]+)"),
        dry=g(r"Drying Settings[^\n]*?(\d+ ?.?C[^\n]{0,20}?\d+ ?h)"), ver=g(r"Data Sheet (V[\d.]+)"),
    )


def try_download_tds(line):
    """Try several file-name spellings on Bambu's CDNs. Returns the cached key or None."""
    key = bambu_data.tds_key(line)
    dest = os.path.join(TDS_DIR, key + ".pdf")
    if os.path.exists(dest):
        return key
    base = line.replace("/", "_").replace("(", "").replace(")", "")
    names = {base.replace(" ", "_"), base.replace(" ", "_").replace("+", "_Plus"), base.replace(" ", "_").replace("+", "Plus"),
             base.replace(" ", "-"), base.replace(" ", "_").replace("-", "_")}
    for name in names:
        for p in SHOPIFY_PATHS:
            for pre in ("Bambu_", "Bambus_"):
                try:
                    blob = bambu_data.fetch(TDS_URL.format(p=p, pre=pre, name=urllib.parse.quote(name)), timeout=20)
                except Exception:
                    continue
                if blob[:4] == b"%PDF":
                    with open(dest, "wb") as f:
                        f.write(blob)
                    return key
    return None


def write_csv(path, out):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        cols = ["family", "line", "color_code", "name_en", "name_ko", "hex", "color_type", "style", "density", "youngs_mpa",
                "tensile_mpa", "elongation_pct", "hdt_045_c", "nozzle_c", "bed_c", "drying", "mech_source"]
        w.writerow(cols)
        for r in out:
            w.writerow([" / ".join(r[c]) if c == "hex" else r[c] for c in cols])


def set_manifest_version(version):
    p = os.path.join(LIBDIR, "BambuFilamentLibrary.manifest")
    m = json.load(open(p, encoding="utf-8"))
    m["version"] = version
    with open(p, "w", encoding="utf-8") as f:
        json.dump(m, f, indent="\t", ensure_ascii=False)


def build_zip(version):
    os.makedirs(DIST, exist_ok=True)
    for fn in os.listdir(DIST):
        if fn.startswith("BambuFilamentLibrary_") and fn.endswith(".zip"):
            os.remove(os.path.join(DIST, fn))
    path = os.path.join(DIST, "BambuFilamentLibrary_%s.zip" % version)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for fn in PACKAGE_FILES:
            z.write(os.path.join(LIBDIR, fn), "BambuFilamentLibrary/" + fn)
    return path


def main():
    install = "--no-install" not in sys.argv
    os.makedirs(TDS_DIR, exist_ok=True)
    out_json = os.path.join(LIBDIR, "bambu_filaments.json")
    old = {r["color_code"]: r for r in json.load(open(out_json, encoding="utf-8"))} if os.path.exists(out_json) else {}

    # 1. colors
    blob = bambu_data.fetch(bambu_data.COLORS_URL, timeout=30)
    colors = json.loads(blob)["data"]
    with open(os.path.join(DATA, "filaments_color_codes.json"), "wb") as f:
        f.write(blob)
    lines = sorted({x["fila_type"] for x in colors})

    # 2. TDS for every line that lacks one
    notes = []
    for line in lines:
        key = bambu_data.tds_key(line)
        had = os.path.exists(os.path.join(TDS_DIR, key + ".pdf"))
        if try_download_tds(line) and not had:
            notes.append("New TDS downloaded for %s (%s.pdf)" % (line, key))

    # 3. parse TDS
    tds = {}
    for fn in sorted(os.listdir(TDS_DIR)):
        if fn.lower().endswith(".pdf"):
            try:
                tds[fn[:-4]] = parse_pdf(os.path.join(TDS_DIR, fn))
            except Exception as e:
                notes.append("TDS parse failed %s: %s" % (fn, e))
    for p in (os.path.join(DATA, "tds_all.json"), os.path.join(LIBDIR, "tds_all.json")):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(tds, f, indent=1)

    # 4. build (same code as the Fusion script); lines.json mirrors bambu_data.LINES for users' online refresh
    bambu_data.export_lines(os.path.join(LIBDIR, "lines.json"))
    out = bambu_data.build_records(colors, tds, True, notes)

    # 5. diff + report
    new = {r["color_code"]: r for r in out}
    added = [new[c] for c in new if c not in old]
    removed = [old[c] for c in old if c not in new]
    recolored = [(old[c], new[c]) for c in new if c in old and old[c]["hex"] != new[c]["hex"]]
    mech_keys = ("density", "youngs_mpa", "tensile_mpa", "poisson", "thermal_conductivity", "specific_heat", "thermal_expansion")
    old_lines = {r["line"]: r for r in old.values()}
    new_lines = {r["line"]: r for r in out}
    mat_changed = sorted(l for l in new_lines if l in old_lines and any(old_lines[l].get(k) != new_lines[l].get(k) for k in mech_keys))
    lines_added = sorted(set(new_lines) - set(old_lines))
    changed = bool(added or removed or recolored or mat_changed)

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    write_csv(os.path.join(LIBDIR, "bambu_filaments.csv"), out)

    # 6. package
    today = datetime.date.today().isoformat()
    version = today.replace("-", ".")
    has_zip = os.path.isdir(DIST) and any(f.endswith(".zip") for f in os.listdir(DIST))
    if changed or not has_zip:
        set_manifest_version(version)
    else:
        version = json.load(open(os.path.join(LIBDIR, "BambuFilamentLibrary.manifest"), encoding="utf-8")).get("version", version)
    zip_path = build_zip(version)

    nm = lambda r: "Bambu %s - %s [%s]" % (r["line"].replace("/", "-"), r["name_en"], r["color_code"])
    rep = ["# Bambu filament library update - %s" % today, "",
           "- colors: %d (lines: %d)" % (len(out), len(new_lines)),
           "- new colors: %d, removed: %d, recolored: %d, new lines: %d, material values changed: %d"
           % (len(added), len(removed), len(recolored), len(lines_added), len(mat_changed)),
           "- Fusion re-run needed: %s" % ("YES" if changed else "no"),
           "- shareable package: %s" % os.path.relpath(zip_path, ROOT), ""]
    if lines_added:
        rep += ["## New product lines"] + ["- %s" % l for l in lines_added] + [""]
    if added:
        rep += ["## New colors"] + ["- %s %s" % (nm(r), "/".join(r["hex"])) for r in added] + [""]
    if recolored or mat_changed:
        rep += ["## Remove these from Fusion Favorites before re-running (API cannot overwrite favorites)"]
        rep += ["- appearance: %s (%s -> %s)" % (nm(n), "/".join(o["hex"]), "/".join(n["hex"])) for o, n in recolored]
        rep += ["- material: Bambu %s" % l.replace("/", "-") for l in mat_changed] + [""]
    if removed:
        rep += ["## Removed from Bambu's list (kept in Fusion; delete manually if wanted)"] + ["- %s" % nm(r) for r in removed] + [""]
    if notes:
        rep += ["## Notes"] + ["- " + n for n in notes] + [""]
    txt = "\n".join(rep)
    with open(os.path.join(DATA, "update_report.md"), "w", encoding="utf-8") as f:
        f.write(txt)
    with open(os.path.join(DATA, "update_report.json"), "w", encoding="utf-8") as f:
        json.dump(dict(date=today, changed=changed, added=len(added), removed=len(removed), recolored=len(recolored),
                       lines_added=lines_added, materials_changed=mat_changed, notes=notes, package=zip_path),
                  f, ensure_ascii=False, indent=1)

    # social preview image with current counts (needs Pillow; skipped if missing)
    if changed:
        try:
            import subprocess
            subprocess.run([sys.executable, "-I", os.path.join(TOOLS, "make_preview.py"), out_json,
                            os.path.join(ROOT, "docs", "social-preview.png")], check=True, capture_output=True)
        except Exception as e:
            print("preview image not updated:", e)

    # 7. install on this PC
    if install and os.path.isdir(os.path.dirname(FUSION_SCRIPTS)):
        os.makedirs(FUSION_SCRIPTS, exist_ok=True)
        for fn in PACKAGE_FILES:
            shutil.copy2(os.path.join(LIBDIR, fn), os.path.join(FUSION_SCRIPTS, fn))
    sys.stdout.reconfigure(encoding="utf-8")
    print(txt)


if __name__ == "__main__":
    main()
