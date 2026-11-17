"""Remove every Bambu appearance and material from Fusion's Favorites (reset / uninstall).

Fusion's API can add items to Favorites but cannot remove them, so this helper runs after Fusion closes and
replaces Favorites.adsklib with an empty Favorites library. The old file is kept as a backup next to it.
Favorites that are not from this library are listed in reset_state.json; the Fusion script adds them back from
the backup the next time it runs.

Pure Python. Run by the Fusion script:  python -I reset.py --wait-pid PID [--library PATH]
Undo: close Fusion, delete Favorites.adsklib and rename the backup to Favorites.adsklib.
"""
import glob, json, os, shutil, sys, time, zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "reset_state.json")
REQUEST = os.path.join(HERE, "reset_request.json")
if HERE not in sys.path:          # run with python -I, which leaves the script folder out of sys.path
    sys.path.insert(0, HERE)
import helper_ui as ui            # noqa: E402


def default_library():
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""), "Autodesk", "Common", "Material Library")
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support/Autodesk/Common/Material Library")
    libs = glob.glob(os.path.join(base, "*", "Favorites.adsklib"))
    # newest file; on a tie the newest version folder (e.g. 5.0.0 over 4.2.3 or 2025...)
    return max(libs, key=lambda p: (int(os.path.getmtime(p)), _ver_key(os.path.basename(os.path.dirname(p))))) if libs else None


def _ver_key(folder):
    import re
    return [int(x) for x in re.findall(r"\d+", folder)] if re.match(r"^\d+\.\d+", folder) else [0]


fusion_running = ui.fusion_running     # no console window


def is_empty_library(path):
    """An empty Favorites library: a valid package whose asset table of contents is empty."""
    try:
        with zipfile.ZipFile(path) as z:
            toc = [n for n in z.namelist() if n.endswith("/AssetData/AssetTableOfContents.bin")]
            return len(toc) == 1 and z.getinfo(toc[0]).file_size == 0 and \
                not any("/Resources/" in n for n in z.namelist())
    except Exception:
        return False


def empty_template(lib):
    """Prefer an empty Favorites library made by this Fusion installation (older version folders keep one),
    then the copy bundled with the script."""
    base = os.path.dirname(os.path.dirname(lib))
    cands = sorted(glob.glob(os.path.join(base, "*", "Favorites.adsklib")), key=os.path.getmtime, reverse=True)
    cands.append(os.path.join(HERE, "empty_favorites.adsklib"))
    for c in cands:
        if os.path.abspath(c) != os.path.abspath(lib) and is_empty_library(c):
            return c
    return None


DONE = ("리셋 완료! 즐겨찾기에서 Bambu 항목을 모두 지웠어요. 이제 Fusion을 켜셔도 돼요.\n"
        "다른 즐겨찾기는 스크립트를 다음에 실행할 때 다시 추가돼요.\n\n"
        "Reset done! All Bambu items were removed from Favorites. You can open Fusion now.\n"
        "Your other favorites are added back the next time you run the script.")


CANCELLED = ("리셋이 취소되었어요. 리셋이 끝나기 전에 Fusion이 다시 켜져서 아무것도 지우지 않았어요.\n"
             "다시 하려면: 리셋 (모두 제거) → 리셋 예약 → Fusion 종료 → '리셋 완료' 창이 뜬 뒤 Fusion 켜기.\n\n"
             "Reset cancelled: Fusion was opened again before the reset ran, so nothing was removed.\n"
             "To reset: Reset (remove all) -> Schedule reset -> close Fusion -> open Fusion after the 'Reset done' box.")


def main(argv):
    if not ui.single_instance("reset"):
        return 0
    try:
        rc = _main(argv)
    except Exception as e:
        rc = 1
        try:
            open(os.path.join(HERE, "reset_log.txt"), "a", encoding="utf-8").write(
                time.strftime("%Y-%m-%d %H:%M:%S ") + "Error: %r\n" % e)
        except OSError:
            pass
    finally:
        ui.release("reset")
    if rc == 0:
        ui.info(DONE)
    elif rc == 3:
        ui.info(CANCELLED, warning=True)
    else:
        ui.info("리셋하지 못했어요. 즐겨찾기는 바뀌지 않았어요. (reset_log.txt 참고)\n\n"
                "The reset did not run; Favorites were not changed. See reset_log.txt.", warning=True)
    return rc


def _main(argv):
    lib, wait_pid = None, None
    i = 0
    while i < len(argv):
        if argv[i] == "--library":
            lib = argv[i + 1]; i += 1
        elif argv[i] == "--wait-pid":
            wait_pid = int(argv[i + 1]); i += 1
        i += 1
    logf = open(os.path.join(HERE, "reset_log.txt"), "a", encoding="utf-8")
    log = lambda s: (print(s), logf.write(time.strftime("%Y-%m-%d %H:%M:%S ") + s + "\n"), logf.flush())
    if wait_pid:
        log("Reset scheduled. Waiting for Fusion to close ...")
        ui.wait_for_fusion_exit()  # also lets Fusion finish writing the library
    if fusion_running():
        # Fusion was opened again before the reset could run: cancel it rather than wipe items installed meanwhile
        log("Fusion was opened again before the reset ran - reset cancelled, nothing changed.")
        try:
            os.remove(REQUEST)
        except OSError:
            pass
        return 3
    req = {}
    if os.path.exists(REQUEST):
        req = json.load(open(REQUEST, encoding="utf-8"))
    lib = lib or req.get("library") or default_library()
    if not lib or not os.path.exists(lib):
        log("Favorites.adsklib not found")
        return 1
    tpl = empty_template(lib)
    if not tpl:
        log("No empty Favorites library template found - nothing changed.")
        return 1
    backup = lib + ".before-bambu-reset-" + time.strftime("%Y%m%d-%H%M%S")
    shutil.copy2(lib, backup)
    tmp = lib + ".tmp"
    shutil.copyfile(tpl, tmp)          # fresh timestamp: the library must stay the newest one
    os.replace(tmp, lib)
    log("Favorites reset: %s (template %s). Backup: %s" % (lib, tpl, backup))
    # thumbnail bookkeeping refers to the old library
    for fn in ("thumbnails_done.json", "favorites_ids.json"):
        try:
            os.remove(os.path.join(HERE, fn))
        except OSError:
            pass
    keep = req.get("keep") or {"appearances": [], "materials": []}
    with open(STATE, "w", encoding="utf-8") as f:
        json.dump({"backup": backup, "library": lib, "keep": keep,
                   "restore_pending": bool(keep["appearances"] or keep["materials"]),
                   "time": time.strftime("%Y-%m-%d %H:%M:%S")}, f, ensure_ascii=False, indent=1)
    try:
        os.remove(REQUEST)
    except OSError:
        pass
    log("Done. Other favorites to restore on the next script run: %d appearances, %d materials"
        % (len(keep["appearances"]), len(keep["materials"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
