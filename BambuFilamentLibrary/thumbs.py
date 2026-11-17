"""Recolor the thumbnails of Bambu appearances in Fusion's Favorites library.

Fusion's API cannot re-render an appearance thumbnail, so every Bambu appearance keeps the white thumbnail of the
library appearance it was copied from. This module edits Favorites.adsklib (a zip package) directly: it finds each
"Bambu ... [color code]" appearance, takes its white thumbnail render and tints it with the filament's color.

Pure Python (zlib/struct only) so it runs with Fusion's bundled Python or any Python 3.
Fusion must be closed while the file is rewritten (it keeps the library in memory and saves it on exit).

CLI:  python thumbs.py [--wait-pid PID] [--library PATH] [--data bambu_filaments.json]
"""
import glob, json, os, re, shutil, struct, sys, time, zipfile, zlib

HERE = os.path.dirname(os.path.abspath(__file__))
GUID = rb"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}"


# ------------------------------------------------------------------ PNG I/O (8-bit only)
def read_png(data):
    """Return (width, height, rgb bytearray)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    pos, idat, plte, trns = 8, b"", None, None
    w = h = ctype = depth = 0
    while pos < len(data):
        ln, typ = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
            if depth != 8 or interlace:
                raise ValueError("unsupported PNG (depth %d, interlace %d)" % (depth, interlace))
        elif typ == b"PLTE":
            plte = chunk
        elif typ == b"IDAT":
            idat += chunk
        elif typ == b"IEND":
            break
    bpp = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(idat)
    stride = w * bpp
    prev = bytearray(stride)
    out = bytearray(w * h * 3)
    o = 0
    i = 0
    for _ in range(h):
        f = raw[i]
        line = bytearray(raw[i + 1:i + 1 + stride])
        i += 1 + stride
        if f == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 255
        elif f == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 255
        elif f == 3:
            for x in range(stride):
                left = line[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + ((left + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b = prev[x]
                c = prev[x - bpp] if x >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else (b if pb <= pc else c))) & 255
        prev = line
        if ctype == 3:
            for x in range(w):
                k = line[x] * 3
                out[o:o + 3] = plte[k:k + 3]
                o += 3
        elif ctype == 2:
            out[o:o + stride] = line
            o += stride
        elif ctype == 6:
            for x in range(0, stride, 4):
                out[o:o + 3] = line[x:x + 3]
                o += 3
        elif ctype in (0, 4):
            for x in range(0, stride, bpp):
                out[o:o + 3] = bytes((line[x],)) * 3
                o += 3
    return w, h, out


def write_png(w, h, rgb):
    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(rgb[y * w * 3:(y + 1) * w * 3]) for y in range(h))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


# ------------------------------------------------------------------ recoloring
def _analyze(w, h, rgb, round_object):
    """Per pixel luminance and object mask (0..1) of a white-object-on-gray render."""
    n = w * h
    L = [(rgb[3 * i] + rgb[3 * i + 1] + rgb[3 * i + 2]) / 3.0 for i in range(n)]
    mask = [0.0] * n
    for y in range(h):
        row = L[y * w:(y + 1) * w]
        border = sorted(row[:12] + row[-12:])
        bg = border[len(border) // 2]
        for x in range(w):
            v = (row[x] - bg - 18) / 30.0
            mask[y * w + x] = 0.0 if v <= 0 else (1.0 if v >= 1 else v)
    if round_object:     # sphere render: its shadowed lower half is as dark as the floor, so use a circle fit
        xs = [i % w for i in range(n) if mask[i] > 0.5]
        ys = [i // w for i in range(n) if mask[i] > 0.5]
        if xs:
            x0, x1, y0 = min(xs), max(xs), min(ys)
            r = (x1 - x0) / 2.0
            cx, cy = (x0 + x1) / 2.0, y0 + r
            for i in range(n):
                d = ((i % w - cx) ** 2 + (i // w - cy) ** 2) ** 0.5
                v = (r - d) / 1.5
                mask[i] = 0.0 if v <= 0 else (1.0 if v >= 1 else v)
    return L, mask


def _tone_table(rgb, metal):
    """256-entry table: luminance of the white render -> tinted color."""
    lin = [(c / 255.0) ** 2.2 for c in rgb]
    tab = []
    for l in range(256):
        shade = min(l / 225.0, 1.0)
        spec = max(0.0, min(1.0, (l - 238) / 17.0)) * (0.6 if metal else 0.85)
        amb = l / 255.0 * 0.10                  # keep the form readable on black
        px = []
        for c in lin:
            v = ((c * shade) ** (1 / 2.2)) * 255 * (1 - amb) + l * amb
            px.append(v * (1 - spec) + 255 * spec)
        tab.append(px)
    return tab


def recolor(w, h, rgb, hexcolor, style):
    target = tuple(int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))
    L, mask = _analyze(w, h, rgb, round_object=(style == "metal"))
    tab = _tone_table(target, style == "metal")
    translucent = style == "translucent"
    out = bytearray(rgb)
    for i in range(w * h):
        m = mask[i]
        if m <= 0.0:
            continue
        o = tab[int(L[i])]
        for k in range(3):
            v = o[k]
            if translucent:
                v = v * 0.75 + rgb[3 * i + k] * 0.25
            if m < 1.0:
                v = rgb[3 * i + k] * (1 - m) + v * m
            out[3 * i + k] = 255 if v > 255 else (0 if v < 0 else int(v))
    return out


# ------------------------------------------------------------------ Favorites.adsklib
def default_library():
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Autodesk", "Common", "Material Library")
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/Autodesk/Common/Material Library")
    libs = glob.glob(os.path.join(base, "*", "Favorites.adsklib"))
    return max(libs, key=os.path.getmtime) if libs else None


def bambu_thumbnails(z, id_map=None):
    """{color code: zip entry name of its thumbnail PNG} for Bambu appearances in the package.
    id_map {color code: asset id} comes from the Fusion script (favorites_ids.json); the asset data is partly
    compressed, so scanning it finds most but not all appearances."""
    root = z.namelist()[0].split("/")[0]
    data = z.read(root + "/AssetData/DefinitionIteratorProperties.bin")
    thumbs = {}
    for n in z.namelist():
        m = re.match(re.escape(root) + r"/Resources/([0-9A-F-]{36})/thumbnail/0/[^/]+_png$", n)
        if m:
            thumbs[m.group(1)] = n
    found = {}
    for code, gid in (id_map or {}).items():
        gid = str(gid).upper().strip("{}")
        if gid in thumbs:
            found[code] = thumbs[gid]
    for m in re.finditer(rb"\[(\d{5})\]", data):
        if b"Bambu " not in data[max(0, m.start() - 400):m.start()]:
            continue
        g = re.search(GUID, data[m.end():m.end() + 120])
        if g and g.group(0).decode() in thumbs:
            found.setdefault(m.group(1).decode(), thumbs[g.group(0).decode()])
    return found


def fusion_running():
    try:
        if sys.platform == "win32":
            import subprocess
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Fusion360.exe", "/NH"], capture_output=True, text=True).stdout
            return "Fusion360.exe" in out
        import subprocess
        return subprocess.run(["pgrep", "-f", "Autodesk Fusion"], capture_output=True).returncode == 0
    except Exception:
        return False


def patch_library(lib_path, records, log=print, id_map=None):
    by_code = {r["color_code"]: r for r in records}
    with zipfile.ZipFile(lib_path) as z:
        targets = {name: code for code, name in bambu_thumbnails(z, id_map).items() if code in by_code}
        if not targets:
            log("No Bambu appearances found in %s" % lib_path)
            return 0
        backup = lib_path + ".before-bambu-thumbnails"
        if not os.path.exists(backup):
            shutil.copy2(lib_path, backup)
        tmp = lib_path + ".tmp"
        done = 0
        with zipfile.ZipFile(tmp, "w") as zo:
            for info in z.infolist():
                data = z.read(info.filename)
                code = targets.get(info.filename)
                if code:
                    try:
                        r = by_code[code]
                        w, h, rgb = read_png(data)
                        data = write_png(w, h, recolor(w, h, rgb, r["hex"][0] if r["alpha"][0] else "#F4F7F8", r["style"]))
                        done += 1
                    except Exception as e:
                        log("  skip %s: %s" % (code, e))
                ni = zipfile.ZipInfo(info.filename, info.date_time)
                ni.compress_type, ni.external_attr, ni.create_system = info.compress_type, info.external_attr, info.create_system
                ni.flag_bits = info.flag_bits & 0x0800
                zo.writestr(ni, data)
    os.replace(tmp, lib_path)
    log("Recolored %d thumbnails in %s (backup: %s)" % (done, lib_path, backup))
    with open(os.path.join(HERE, "thumbnails_done.json"), "w", encoding="utf-8") as f:
        json.dump(sorted(set(targets.values())), f)
    return done


def main(argv):
    lib, data, wait_pid = None, os.path.join(HERE, "bambu_filaments.json"), None
    i = 0
    while i < len(argv):
        if argv[i] == "--library":
            lib = argv[i + 1]; i += 1
        elif argv[i] == "--data":
            data = argv[i + 1]; i += 1
        elif argv[i] == "--wait-pid":
            wait_pid = int(argv[i + 1]); i += 1
        i += 1
    logf = open(os.path.join(HERE, "thumbnail_log.txt"), "a", encoding="utf-8")
    log = lambda s: (print(s), logf.write(time.strftime("%Y-%m-%d %H:%M:%S ") + s + "\n"), logf.flush())
    if wait_pid:
        log("Waiting for Fusion to close ...")
        while fusion_running():
            time.sleep(3)
        time.sleep(5)          # let Fusion finish writing the library
    if fusion_running():
        log("Fusion is running - close it first.")
        return 2
    lib = lib or default_library()
    if not lib or not os.path.exists(lib):
        log("Favorites.adsklib not found")
        return 1
    records = json.load(open(data, encoding="utf-8"))
    idp = os.path.join(HERE, "favorites_ids.json")
    id_map = json.load(open(idp, encoding="utf-8")) if os.path.exists(idp) else None
    patch_library(lib, records, log, id_map)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
