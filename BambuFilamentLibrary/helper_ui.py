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


def _fusion_pids():
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Fusion360.exe", "/FO", "CSV", "/NH"], capture_output=True,
                         text=True, creationflags=_NO_WINDOW, startupinfo=si).stdout
    pids = set()
    for ln in out.splitlines():
        parts = [p.strip('"') for p in ln.split('","')]
        if len(parts) > 1 and parts[0].lower().startswith("fusion360") and parts[1].isdigit():
            pids.add(int(parts[1]))
    return pids


def fusion_closing():
    """True while Fusion's process is still alive but has no visible window (it is shutting down)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
        pids = _fusion_pids()
        if not pids:
            return False
        u = ctypes.windll.user32
        seen = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def cb(h, _):
            if u.IsWindowVisible(h) and u.GetWindowTextLengthW(h):
                pid = wintypes.DWORD()
                u.GetWindowThreadProcessId(h, ctypes.byref(pid))
                if pid.value in pids:
                    seen.append(h)
                    return False
            return True
        u.EnumWindows(cb, 0)
        return not seen
    except Exception:
        return False


def wait_for_fusion_exit(poll=2, settle=5, progress=None):
    """Block until Fusion is closed, then give it a moment to finish writing its files.
    With a Progress window, it appears as soon as Fusion's window is gone (Fusion can take a while to exit)."""
    while fusion_running():
        if progress:
            if fusion_closing():
                progress.set("Fusion이 완전히 종료되기를 기다리는 중…", "Waiting for Fusion to finish closing…")
                progress.show()
            else:
                progress.hide()           # Fusion is still open (or a 'save changes?' dialog is up)
        time.sleep(poll)
    if progress:
        progress.set("Fusion 종료 확인 - 곧 시작해요…", "Fusion has closed - starting in a moment…")
        progress.show()
    time.sleep(settle)


class Progress:
    """An animated progress window (tkinter, own thread) shown while a helper works.
    set() changes the text and, with done/total, shows real progress; finish() turns it into the
    'done' message with an OK button. Falls back to plain message boxes when tkinter is not available."""

    def __init__(self, hint_ko, hint_en):
        import queue
        self.q = queue.Queue()
        self.ok = threading.Event()
        self.closed = threading.Event()
        self.ready = threading.Event()
        self.failed = False
        self.hint = "%s\n%s" % (hint_ko, hint_en)
        self.status_box = None
        threading.Thread(target=self._run, daemon=True).start()
        self.ready.wait(10)

    # ---- public (any thread)
    def set(self, ko, en, done=None, total=None):
        self.q.put(("set", ko, en, done, total))
        if self.failed and self.status_box is None:
            self.status_box = Status("%s\n%s\n\n%s" % (ko, en, self.hint))

    def show(self):
        self.q.put(("show",))

    def hide(self):
        self.q.put(("hide",))

    def finish(self, ko, en, warning=False):
        """Show the final message and block until the user clicks OK."""
        if self.failed:
            if self.status_box:
                self.status_box.close()
            info("%s\n\n%s" % (ko, en), warning)
            return
        self.q.put(("finish", ko, en, warning))
        self.closed.wait(3600)

    def close(self):
        if self.status_box:
            self.status_box.close()
            self.status_box = None
        self.q.put(("close",))

    # ---- tk thread
    def _run(self):
        try:
            import tkinter as tk
            from tkinter import ttk
            root = tk.Tk()
        except Exception:
            self.failed = True
            self.ready.set()
            return
        try:
            self._build(root, tk, ttk)
        except Exception:
            self.failed = True
            self.ready.set()
            try:
                root.destroy()
            except Exception:
                pass
            return
        self.ready.set()
        root.mainloop()
        self.closed.set()

    def _build(self, root, tk, ttk):
        root.withdraw()
        root.title(TITLE)
        root.resizable(False, False)
        root.attributes("-topmost", True)
        root.configure(bg="#ffffff")
        root.protocol("WM_DELETE_WINDOW", lambda: None)          # closes with OK only
        font = ("Malgun Gothic", 10) if sys.platform == "win32" else ("Helvetica", 12)
        big = (font[0], font[1] + 2, "bold")
        top = tk.Frame(root, bg="#ffffff", padx=18, pady=14)
        top.pack(fill="both", expand=True)
        try:
            img = tk.PhotoImage(file=os.path.join(HERE, "ui", "logo.png"))
            self._img = img.subsample(max(1, img.width() // 48))
            self._icon = img.subsample(max(1, img.width() // 32))
            root.iconphoto(True, self._icon)
            tk.Label(top, image=self._img, bg="#ffffff").grid(row=0, column=0, rowspan=3, sticky="n", padx=(0, 14))
        except Exception:
            pass
        self.lab_ko = tk.Label(top, text="", font=big, bg="#ffffff", anchor="w", justify="left", wraplength=360)
        self.lab_ko.grid(row=0, column=1, sticky="w")
        self.lab_en = tk.Label(top, text="", font=font, fg="#555555", bg="#ffffff", anchor="w", justify="left",
                               wraplength=360)
        self.lab_en.grid(row=1, column=1, sticky="w")
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("B.Horizontal.TProgressbar", troughcolor="#e8ecef", background="#00ae42",
                        bordercolor="#e8ecef", lightcolor="#00ae42", darkcolor="#00ae42")
        self.bar = ttk.Progressbar(top, style="B.Horizontal.TProgressbar", length=360, mode="indeterminate")
        self.bar.grid(row=2, column=1, sticky="we", pady=(10, 4))
        self.lab_meta = tk.Label(top, text="", font=(font[0], font[1] - 1), fg="#777777", bg="#ffffff", anchor="w")
        self.lab_meta.grid(row=3, column=1, sticky="w")
        self.lab_hint = tk.Label(top, text=self.hint, font=(font[0], font[1] - 1), fg="#b45309", bg="#ffffff",
                                 anchor="w", justify="left", wraplength=360)
        self.lab_hint.grid(row=4, column=1, sticky="w", pady=(8, 0))
        self.btn = tk.Button(top, text="확인 / OK", font=font, width=12, bg="#00ae42", fg="#ffffff",
                             activebackground="#00913a", activeforeground="#ffffff", relief="flat",
                             command=root.destroy)
        self.root, self.tk = root, tk
        self.t0 = None
        self.counts = None
        self.spin = 0
        self.bar.start(12)
        root.after(50, self._poll)
        root.after(200, self._tick)

    def _center(self):
        r = self.root
        r.update_idletasks()
        w, h = r.winfo_reqwidth(), r.winfo_reqheight()
        r.geometry("+%d+%d" % ((r.winfo_screenwidth() - w) // 2, (r.winfo_screenheight() - h) // 3))

    def _poll(self):
        import queue
        try:
            while True:
                cmd = self.q.get_nowait()
                op = cmd[0]
                if op == "set":
                    _, ko, en, done, total = cmd
                    self.lab_ko.config(text=ko)
                    self.lab_en.config(text=en)
                    if total:
                        if str(self.bar["mode"]) != "determinate":
                            self.bar.stop()
                            self.bar.config(mode="determinate", maximum=total)
                        self.bar["value"] = done or 0
                        self.counts = (done or 0, total)
                    else:
                        if str(self.bar["mode"]) != "indeterminate":
                            self.bar.config(mode="indeterminate")
                            self.bar.start(12)
                        self.counts = None
                elif op == "show":
                    if self.root.state() == "withdrawn":
                        if self.t0 is None:
                            self.t0 = time.time()
                        self._center()
                        self.root.deiconify()
                        self.root.lift()
                elif op == "hide":
                    self.root.withdraw()
                elif op == "finish":
                    _, ko, en, warning = cmd
                    self.bar.stop()
                    self.bar.grid_remove()
                    self.lab_hint.grid_remove()
                    self.lab_meta.grid_remove()
                    self.lab_ko.config(text=("⚠ " if warning else "✔ ") + ko, fg="#b45309" if warning else "#087a34")
                    self.lab_en.config(text=en)
                    self.btn.grid(row=5, column=1, sticky="e", pady=(14, 0))
                    self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
                    self._center()
                    self.root.deiconify()
                    self.root.lift()
                    self.root.focus_force()
                    self.btn.focus_set()
                    self.root.bind("<Return>", lambda e: self.root.destroy())
                    self.finished = True
                elif op == "close":
                    self.root.destroy()
                    return
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _tick(self):
        if getattr(self, "finished", False):
            return
        dots = "●○○ ○●○ ○○● ○●○".split()[self.spin % 4]
        self.spin += 1
        sec = int(time.time() - self.t0) if self.t0 else 0
        meta = "%s   경과 %d초 / %d s elapsed" % (dots, sec, sec)
        if self.counts:
            d, t = self.counts
            meta += "   ·   %d / %d (%d%%)" % (d, t, 100 * d // max(1, t))
        self.lab_meta.config(text=meta)
        self.root.after(300, self._tick)


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
