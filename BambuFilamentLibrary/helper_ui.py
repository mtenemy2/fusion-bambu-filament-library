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


def _ui_korean():
    try:
        if sys.platform == "win32":
            import ctypes
            return (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x12
        import locale
        return (locale.getlocale()[0] or "").lower().startswith("ko")
    except Exception:
        return True


def _dpi_aware():
    """Draw at the real screen resolution (otherwise Windows stretches the window and everything looks blurry)."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)        # per-monitor
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def _mix(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _hex(c):
    return "#%02x%02x%02x" % (int(c[0] + .5), int(c[1] + .5), int(c[2] + .5))


class _PillBar:
    """Antialiased pill-shaped progress bar drawn into a PhotoImage (tk canvases have no antialiasing).
    indeterminate: a soft gleam sweeps left to right; determinate: the fill eases toward the target value."""
    BG = (255, 255, 255)
    TRACK = (234, 238, 242)
    FILL_A = (0, 158, 60)          # Bambu green, slightly deeper on the left
    FILL_B = (38, 196, 99)
    GLEAM = (0, 174, 66)
    PERIOD = 1.7                   # seconds per sweep

    def __init__(self, tk, parent, w, h):
        import math
        self.math = math
        self.w, self.h = w, h
        self.img = tk.PhotoImage(width=w, height=h)
        self.label = tk.Label(parent, image=self.img, bg=_hex(self.BG), bd=0, highlightthickness=0)
        self.r = h / 2.0
        self.cy = h / 2.0
        self.mode = "indeterminate"
        self.gleam = 1.0           # shimmer opacity (fades out in determinate mode)
        self.shown = 0.0           # displayed fraction (eases toward target)
        self.target = 0.0
        self.t0 = time.time()
        self.last = self.t0
        self.dirty = True
        # vertical coverage of each row in the straight middle part of a pill
        self.vcov = [max(0.0, min(1.0, self.r - abs(y + .5 - self.cy) + .5)) for y in range(h)]

    def set_mode(self, mode):
        if mode != self.mode:
            self.mode = mode
            if mode == "determinate":
                self.shown = self.target = 0.0
            else:
                self.gleam = 1.0
            self.dirty = True

    def set_value(self, frac):
        self.target = max(0.0, min(1.0, frac))
        self.dirty = True

    def _cov(self, x, y, x1):
        """Coverage of pixel (x, y) by a pill spanning [0, x1]."""
        r = self.r
        px, py = x + .5, y + .5
        cx = min(max(px, r), max(r, x1 - r))
        d = self.math.hypot(px - cx, py - self.cy)
        return max(0.0, min(1.0, r - d + .5))

    def step(self):
        now = time.time()
        dt, self.last = now - self.last, now
        if self.mode == "determinate":
            k = 1.0 - self.math.exp(-dt / 0.22)          # ease-out toward the target
            self.shown += (self.target - self.shown) * k
            if abs(self.target - self.shown) < 0.0005:
                self.shown = self.target
            if self.gleam > 0:
                self.gleam = max(0.0, self.gleam - dt / 0.45)
            if not self.dirty and self.gleam == 0 and self.shown == self.target:
                return
        self.dirty = False
        self._render(now)

    def _render(self, now):
        w, h, r = self.w, self.h, self.r
        fw = self.shown * w if self.mode == "determinate" else 0.0
        fade = min(1.0, fw / h) if fw > 0 else 0.0           # very short fills fade in instead of popping
        fx1 = max(fw, h) if fw > 0 else 0.0
        # gleam: gaussian band moving left -> right with ease-in-out
        g = []
        if self.gleam > 0:
            p = ((now - self.t0) % self.PERIOD) / self.PERIOD
            p = p * p * (3 - 2 * p)
            sigma = w * 0.16
            c = -0.35 * w + p * 1.7 * w
            peak = 0.55 * self.gleam
            g = [peak * self.math.exp(-((x + .5 - c) / sigma) ** 2) for x in range(w)]
        # full-coverage color of each column
        cols = []
        for x in range(w):
            col = self.TRACK
            if g:
                col = _mix(col, self.GLEAM, g[x])
            if fw > 0 and x < fx1:
                col = _mix(col, _mix(self.FILL_A, self.FILL_B, x / max(1.0, fx1)), fade)
            cols.append(col)
        hexcols = [_hex(c) for c in cols]
        edge = int(r) + 2
        rows = []
        for y in range(h):
            vc = self.vcov[y]
            row = []
            for x in range(w):
                near_end = x < edge or x >= w - edge
                near_fill = fw > 0 and abs(x - fx1) < edge
                if not near_end and not near_fill:
                    row.append(hexcols[x] if vc >= 1.0 else _hex(_mix(self.BG, cols[x], vc)))
                    continue
                ct = self._cov(x, y, w)
                base = self.TRACK
                if g:
                    base = _mix(base, self.GLEAM, g[x])
                if fw > 0:
                    cf = min(ct, self._cov(x, y, fx1)) * fade
                    if cf > 0:
                        base = _mix(base, _mix(self.FILL_A, self.FILL_B, min(1.0, x / max(1.0, fx1))), cf / max(ct, 1e-6))
                row.append(_hex(_mix(self.BG, base, ct)))
            rows.append("{" + " ".join(row) + "}")
        self.img.put(" ".join(rows), to=(0, 0))


class Progress:
    """A progress window (tkinter, own thread) shown while a helper works after Fusion closes.
    set() changes the text and, with done/total, shows real progress; finish() turns it into the
    'done' message with an OK button. Falls back to plain message boxes when tkinter is not available."""

    def __init__(self, hint_ko, hint_en):
        import queue
        self.q = queue.Queue()
        self.closed = threading.Event()
        self.ready = threading.Event()
        self.failed = False
        self.ko = _ui_korean()
        self.hint_pair = (hint_ko, hint_en)
        self.hint = hint_ko if self.ko else hint_en
        self.status_box = None
        self.finished = False
        threading.Thread(target=self._run, daemon=True).start()
        self.ready.wait(10)

    # ---- public (any thread)
    def set(self, ko, en, done=None, total=None):
        self.q.put(("set", ko, en, done, total))
        if self.failed and self.status_box is None:
            self.status_box = Status("%s\n%s\n\n%s\n%s" % (ko, en, self.hint_pair[0], self.hint_pair[1]))

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
            _dpi_aware()
            import tkinter as tk
            root = tk.Tk()
        except Exception:
            self.failed = True
            self.ready.set()
            return
        try:
            self._build(root, tk)
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

    def _logo(self, tk, px):
        """Closest pre-rendered logo size (ui/logo_<px>.png, downscaled with a high-quality filter)."""
        sizes = [52, 65, 78, 91, 104, 130]
        best = min(sizes, key=lambda s: (s < px, abs(s - px)))
        for name in ("logo_%d.png" % best, "logo.png"):
            p = os.path.join(HERE, "ui", name)
            if os.path.exists(p):
                img = tk.PhotoImage(file=p)
                if name == "logo.png":
                    img = img.subsample(max(1, img.width() // max(1, px)))
                return img
        return None

    def _build(self, root, tk):
        S = root.winfo_fpixels("1i") / 96.0
        self.S = S
        P = lambda v: int(round(v * S))
        WHITE, INK, MUTED, SOFT = "#ffffff", "#1f2328", "#6b7280", "#9aa3ad"
        root.withdraw()
        root.title(TITLE)
        root.resizable(False, False)
        root.attributes("-topmost", True)
        root.configure(bg=WHITE)
        root.protocol("WM_DELETE_WINDOW", lambda: None)          # closes with OK only
        fam = "Malgun Gothic" if sys.platform == "win32" else "Helvetica"
        f_brand = (fam, 8, "bold")
        f_title = (fam, 12, "bold")
        f_text = (fam, 9)
        f_num = ("Segoe UI Semibold" if sys.platform == "win32" else fam, 9)
        try:
            for px in (32, 48, 64):
                p = os.path.join(HERE, "ui", "logo_%d.png" % px)
                if os.path.exists(p):
                    setattr(self, "_icon%d" % px, tk.PhotoImage(file=p))
            icons = [getattr(self, "_icon%d" % px) for px in (64, 48, 32) if hasattr(self, "_icon%d" % px)]
            if icons:
                root.iconphoto(True, *icons)
        except Exception:
            pass

        card = tk.Frame(root, bg=WHITE, padx=P(24), pady=P(22))
        card.pack(fill="both", expand=True)
        head = tk.Frame(card, bg=WHITE)
        head.pack(fill="x")
        try:
            self._img = self._logo(tk, P(52))
            if self._img:
                tk.Label(head, image=self._img, bg=WHITE, bd=0).pack(side="left", anchor="n", padx=(0, P(16)))
        except Exception:
            pass
        txt = tk.Frame(head, bg=WHITE)
        txt.pack(side="left", fill="x", expand=True)
        tk.Label(txt, text="BAMBU FILAMENT LIBRARY", font=f_brand, fg="#00a13d", bg=WHITE, anchor="w").pack(fill="x")
        self.lab_title = tk.Label(txt, text="", font=f_title, fg=INK, bg=WHITE, anchor="w", justify="left",
                                  wraplength=P(330))
        self.lab_title.pack(fill="x", pady=(P(2), 0))

        self.body = tk.Frame(card, bg=WHITE)
        self.body.pack(fill="x", pady=(P(20), 0))
        self.bar = _PillBar(tk, self.body, P(398), max(6, P(8)))
        self.bar.label.pack(anchor="w")
        row = tk.Frame(self.body, bg=WHITE)
        row.pack(fill="x", pady=(P(9), 0))
        self.lab_status = tk.Label(row, text="", font=f_text, fg=MUTED, bg=WHITE, anchor="w")
        self.lab_status.pack(side="left")
        self.lab_time = tk.Label(row, text="", font=f_num, fg=SOFT, bg=WHITE, anchor="e")
        self.lab_time.pack(side="right")
        self.lab_pct = tk.Label(row, text="", font=f_num, fg=INK, bg=WHITE, anchor="e")
        self.lab_pct.pack(side="right", padx=(0, P(8)))

        note = tk.Frame(self.body, bg="#fff7e8", padx=P(12), pady=P(8))
        note.pack(fill="x", pady=(P(18), 0))
        tk.Label(note, text=self.hint, font=f_text, fg="#9a5b13", bg="#fff7e8", anchor="w", justify="left",
                 wraplength=P(370)).pack(fill="x")

        self.done_box = tk.Frame(card, bg=WHITE)
        self.lab_msg = tk.Label(txt, text="", font=f_text, fg=MUTED, bg=WHITE, anchor="w", justify="left",
                                wraplength=P(330))           # shown under the title when finished
        self.btn = tk.Label(self.done_box, text="확인" if self.ko else "OK", font=(fam, 10, "bold"), fg=WHITE,
                            bg="#00ae42", padx=P(26), pady=P(7), cursor="hand2")
        self.btn.pack(anchor="e", pady=(P(18), 0))
        self.btn.bind("<Enter>", lambda e: self.btn.config(bg="#00913a"))
        self.btn.bind("<Leave>", lambda e: self.btn.config(bg="#00ae42"))
        self.btn.bind("<Button-1>", lambda e: root.destroy())

        self.root, self.tk = root, tk
        self.t0 = None
        self.counts = None
        root.after(50, self._poll)
        root.after(33, self._frame)
        root.after(250, self._tick)

    def _center(self):
        r = self.root
        r.update_idletasks()
        w, h = r.winfo_reqwidth(), r.winfo_reqheight()
        r.geometry("+%d+%d" % ((r.winfo_screenwidth() - w) // 2, (r.winfo_screenheight() - h) // 3))

    def _badge(self, warning):
        """Antialiased round check (or '!') badge drawn into a PhotoImage."""
        import math
        n = int(round(22 * self.S))
        img = self.tk.PhotoImage(width=n, height=n)
        bg, fg = (255, 255, 255), ((217, 119, 6) if warning else (0, 174, 66))
        c, rad = n / 2.0, n / 2.0 - 0.5
        if warning:
            segs = [((c, n * .26), (c, n * .58))]
            dots = [(c, n * .74)]
        else:
            segs = [((n * .28, n * .52), (n * .43, n * .67)), ((n * .43, n * .67), (n * .73, n * .35))]
            dots = []
        sw = max(1.6, n * .1)

        def dseg(px, py, a, b):
            ax, ay = a
            bx, by = b
            vx, vy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / (vx * vx + vy * vy)))
            return math.hypot(px - ax - t * vx, py - ay - t * vy)
        rows = []
        for y in range(n):
            row = []
            for x in range(n):
                px, py = x + .5, y + .5
                cov = max(0.0, min(1.0, rad - math.hypot(px - c, py - c) + .5))
                d = min([dseg(px, py, a, b) for a, b in segs] + [math.hypot(px - dx, py - dy) - sw * .15 for dx, dy in dots])
                mark = max(0.0, min(1.0, sw / 2 - d + .5))
                col = _mix(fg, (255, 255, 255), mark)
                row.append(_hex(_mix(bg, col, cov)))
            rows.append("{" + " ".join(row) + "}")
        img.put(" ".join(rows), to=(0, 0))
        return img

    def _poll(self):
        import queue
        try:
            while True:
                cmd = self.q.get_nowait()
                op = cmd[0]
                if op == "set":
                    _, ko, en, done, total = cmd
                    self.lab_title.config(text=ko if self.ko else en)
                    if total:
                        self.bar.set_mode("determinate")
                        self.bar.set_value((done or 0) / float(total))
                        self.counts = (done or 0, total)
                    else:
                        self.bar.set_mode("indeterminate")
                        self.counts = None
                    self._status()
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
                    self.finished = True
                    text = ko if self.ko else en
                    head, _, rest = text.partition("\n")
                    self._badge_img = self._badge(warning)
                    self.lab_title.config(text=" " + head, image=self._badge_img, compound="left",
                                          fg="#b45309" if warning else "#1f2328")
                    if rest:
                        self.lab_msg.config(text=rest)
                        self.lab_msg.pack(fill="x", pady=(int(6 * self.S), 0))
                    self.body.pack_forget()
                    self.done_box.pack(fill="x", pady=(int(14 * self.S), 0))
                    self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
                    self.root.bind("<Return>", lambda e: self.root.destroy())
                    self.root.bind("<Escape>", lambda e: self.root.destroy())
                    self._center()
                    self.root.deiconify()
                    self.root.lift()
                    self.root.focus_force()
                elif op == "close":
                    self.root.destroy()
                    return
        except queue.Empty:
            pass
        self.root.after(50, self._poll)

    def _status(self):
        if self.counts:
            d, t = self.counts
            self.lab_status.config(text=("처리 중  %d / %d" if self.ko else "Processing  %d / %d") % (d, t))
            self.lab_pct.config(text="%d%%" % (100 * d // max(1, t)))
        else:
            self.lab_status.config(text="준비 중…" if self.ko else "Preparing…")
            self.lab_pct.config(text="")

    def _frame(self):
        if self.finished:
            return
        if self.root.state() != "withdrawn":
            self.bar.step()
        self.root.after(33, self._frame)

    def _tick(self):
        if self.finished:
            return
        sec = int(time.time() - self.t0) if self.t0 else 0
        self.lab_time.config(text="%d:%02d" % (sec // 60, sec % 60))
        self.root.after(250, self._tick)


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
