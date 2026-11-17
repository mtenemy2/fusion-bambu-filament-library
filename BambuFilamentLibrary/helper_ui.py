"""Shared bits for the helpers that run after Fusion closes (thumbs.py, reset.py).

- fusion_running(): checks for Fusion without flashing a console window
- Status: a small "working..." message box that the helper closes itself when it is done
- info(): a "done - you can open Fusion now" message box
- single_instance(): only one helper of a kind runs at a time
Pure Python (ctypes), Windows message boxes; on macOS a notification is shown instead.
"""
import os, subprocess, sys, threading, time

HERE = os.path.dirname(os.path.abspath(__file__))
TITLE = "Bambu Filament Library"
_NO_WINDOW = 0x08000000           # CREATE_NO_WINDOW: tasklist must not open a console (the helper has none)


def fusion_running():
    try:
        if sys.platform == "win32":
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW            # SW_HIDE
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Fusion360.exe", "/NH"], capture_output=True,
                                 text=True, creationflags=_NO_WINDOW, startupinfo=si).stdout
            return "Fusion360.exe" in out
        return subprocess.run(["pgrep", "-f", "Autodesk Fusion"], capture_output=True).returncode == 0
    except Exception:
        return False


def wait_for_fusion_exit(poll=2, settle=5):
    """Block until Fusion is closed, then give it a moment to finish writing its files."""
    while fusion_running():
        time.sleep(poll)
    time.sleep(settle)


def _mac_notify(text):
    try:
        t = text.replace("\\", "\\\\").replace('"', '\\"')
        subprocess.run(["osascript", "-e", 'display notification "%s" with title "%s"' % (t, TITLE)])
    except Exception:
        pass


def info(text, warning=False):
    """Message box on top of other windows; returns when the user clicks OK."""
    if sys.platform != "win32":
        _mac_notify(text)
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, text, TITLE, (0x30 if warning else 0x40) | 0x40000 | 0x10000)
    except Exception:
        pass


class Status:
    """A non-blocking message box ("working, please wait"). close() removes it."""

    def __init__(self, text):
        self.title = "%s  (%d)" % (TITLE, os.getpid())
        self.thread = None
        if sys.platform != "win32":
            _mac_notify(text)
            return
        try:
            import ctypes
            box = lambda: ctypes.windll.user32.MessageBoxW(None, text, self.title, 0x40 | 0x40000 | 0x10000)
            self.thread = threading.Thread(target=box, daemon=True)
            self.thread.start()
        except Exception:
            self.thread = None

    def close(self):
        if not self.thread:
            return
        try:
            import ctypes
            u = ctypes.windll.user32
            for _ in range(50):                       # the box may still be opening
                hwnd = u.FindWindowW(None, self.title)
                if hwnd:
                    u.PostMessageW(hwnd, 0x0010, 0, 0)    # WM_CLOSE
                    break
                if not self.thread.is_alive():
                    break
                time.sleep(0.1)
            self.thread.join(2)
        except Exception:
            pass


def _pid_alive(pid):
    if sys.platform != "win32":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    try:
        import ctypes
        k = ctypes.windll.kernel32
        h = k.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        code = ctypes.c_ulong()
        k.GetExitCodeProcess(h, ctypes.byref(code))
        k.CloseHandle(h)
        return code.value == 259                     # STILL_ACTIVE
    except Exception:
        return False


def single_instance(name):
    """True if this is the only running helper called `name` (a lock file holds the pid)."""
    path = os.path.join(HERE, name + ".lock")
    try:
        old = int(open(path).read().strip() or 0)
        if old and old != os.getpid() and _pid_alive(old):
            return False
    except (OSError, ValueError):
        pass
    with open(path, "w") as f:
        f.write(str(os.getpid()))
    return True


def is_running(name):
    """True if a helper called `name` is alive (its lock file names a running process)."""
    try:
        pid = int(open(os.path.join(HERE, name + ".lock")).read().strip() or 0)
        return bool(pid) and _pid_alive(pid)
    except (OSError, ValueError):
        return False


def release(name):
    try:
        os.remove(os.path.join(HERE, name + ".lock"))
    except OSError:
        pass
