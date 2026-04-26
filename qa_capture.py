"""
QA Proof Capture - Screenshot & Screencast tool for QA teams
Requires: pip install pillow mss opencv-python numpy pywin32
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
import threading
import time
import os
import json
import datetime
import shutil
import subprocess
import sys
from pathlib import Path

# ── Dependency check & auto-install ──────────────────────────────────────────
REQUIRED = {
    "PIL": "pillow",
    "mss": "mss",
    "cv2": "opencv-python",
    "numpy": "numpy",
}

missing = []
for mod, pkg in REQUIRED.items():
    try:
        __import__(mod)
    except ImportError:
        missing.append(pkg)

if missing:
    print(f"Installing missing packages: {', '.join(missing)}")
    subprocess.check_call([sys.executable, "-m", "pip", "install", *missing, "--quiet"])

import mss
import mss.tools
import numpy as np
from PIL import Image, ImageTk, ImageDraw, ImageFont
import cv2

# ── Constants ─────────────────────────────────────────────────────────────────
APP_NAME  = "QA Proof Capture"
VERSION   = "1.0.0"
BASE_DIR  = Path.home() / "QAProofCapture"
BASE_DIR.mkdir(exist_ok=True)
SESSIONS_DIR = BASE_DIR / "sessions"
SESSIONS_DIR.mkdir(exist_ok=True)

# Colors
C_BG        = "#0F0F13"
C_SURFACE   = "#1A1A22"
C_SURFACE2  = "#22222E"
C_BORDER    = "#2E2E3E"
C_PRIMARY   = "#6C63FF"
C_PRIMARY2  = "#8B84FF"
C_SUCCESS   = "#22C55E"
C_DANGER    = "#EF4444"
C_WARNING   = "#F59E0B"
C_TEXT      = "#F1F0FF"
C_TEXT2     = "#9B9AB8"
C_RED_REC   = "#FF3B3B"

# ── Session Manager ───────────────────────────────────────────────────────────
class Session:
    def __init__(self, name: str):
        safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in name)
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.name      = name
        self.folder    = SESSIONS_DIR / f"{ts}_{safe}"
        self.folder.mkdir(parents=True, exist_ok=True)
        self.meta_file = self.folder / "session.json"
        self.items: list[dict] = []
        self._save_meta()

    def _save_meta(self):
        data = {
            "name": self.name,
            "created": datetime.datetime.now().isoformat(),
            "items": self.items
        }
        self.meta_file.write_text(json.dumps(data, indent=2))

    def add_item(self, kind: str, filename: str, note: str = ""):
        entry = {
            "kind": kind,
            "file": filename,
            "note": note,
            "time": datetime.datetime.now().strftime("%H:%M:%S"),
            "date": datetime.datetime.now().strftime("%Y-%m-%d"),
        }
        self.items.append(entry)
        self._save_meta()
        return entry

    @staticmethod
    def load_all() -> list[dict]:
        sessions = []
        for d in sorted(SESSIONS_DIR.iterdir(), reverse=True):
            mf = d / "session.json"
            if mf.exists():
                try:
                    data = json.loads(mf.read_text())
                    data["folder"] = str(d)
                    sessions.append(data)
                except Exception:
                    pass
        return sessions


# ── Annotation Canvas ─────────────────────────────────────────────────────────
class AnnotateWindow(tk.Toplevel):
    def __init__(self, parent, image: Image.Image, on_save):
        super().__init__(parent)
        self.title("Annotate Screenshot")
        self.configure(bg=C_BG)
        self.resizable(True, True)
        self.on_save = on_save

        self.orig_image = image.copy()
        self.draw_image  = image.copy()
        self.draw_layer  = ImageDraw.Draw(self.draw_image)

        self.tool     = tk.StringVar(value="pen")
        self.color    = tk.StringVar(value="#FF3B3B")
        self.size_var = tk.IntVar(value=3)
        self.text_var = tk.StringVar(value="BUG:")

        self._build_toolbar()
        self._build_canvas()
        self._bind_events()
        self._last_x = self._last_y = None

        # Scale to fit screen
        sw, sh = self.winfo_screenwidth() - 100, self.winfo_screenheight() - 180
        iw, ih = image.size
        scale  = min(sw/iw, sh/ih, 1.0)
        self.scale = scale
        self.canvas.config(width=int(iw*scale), height=int(ih*scale))
        self._refresh()
        self.grab_set()

    def _build_toolbar(self):
        bar = tk.Frame(self, bg=C_SURFACE, pady=6, padx=8)
        bar.pack(fill="x", side="top")

        tools = [("✏️ Pen","pen"), ("▭ Rect","rect"), ("➡ Arrow","arrow"), ("T Text","text"), ("⬜ Blur","blur")]
        for label, val in tools:
            b = tk.Radiobutton(bar, text=label, variable=self.tool, value=val,
                               bg=C_SURFACE, fg=C_TEXT, selectcolor=C_PRIMARY,
                               activebackground=C_SURFACE2, font=("Segoe UI", 9),
                               indicatoron=False, padx=8, pady=4, relief="flat",
                               borderwidth=0, cursor="hand2")
            b.pack(side="left", padx=2)

        tk.Label(bar, text="│", bg=C_SURFACE, fg=C_BORDER).pack(side="left", padx=6)

        colors = ["#FF3B3B","#FFD600","#22C55E","#6C63FF","#FFFFFF","#000000"]
        for c in colors:
            cb = tk.Button(bar, bg=c, width=2, height=1, relief="flat", cursor="hand2",
                           command=lambda x=c: self.color.set(x))
            cb.pack(side="left", padx=2)

        tk.Label(bar, text="Size:", bg=C_SURFACE, fg=C_TEXT2, font=("Segoe UI",9)).pack(side="left", padx=(10,2))
        tk.Spinbox(bar, from_=1, to=20, textvariable=self.size_var, width=3,
                   bg=C_SURFACE2, fg=C_TEXT, insertbackground=C_TEXT, relief="flat").pack(side="left")

        tk.Label(bar, text="Text:", bg=C_SURFACE, fg=C_TEXT2, font=("Segoe UI",9)).pack(side="left", padx=(10,2))
        tk.Entry(bar, textvariable=self.text_var, width=12,
                 bg=C_SURFACE2, fg=C_TEXT, insertbackground=C_TEXT, relief="flat").pack(side="left")

        tk.Button(bar, text="↩ Undo", bg=C_SURFACE2, fg=C_TEXT, relief="flat",
                  padx=8, cursor="hand2", command=self._undo).pack(side="right", padx=2)
        tk.Button(bar, text="💾 Save", bg=C_PRIMARY, fg=C_TEXT, relief="flat",
                  padx=10, cursor="hand2", command=self._save).pack(side="right", padx=2)

        self._history: list[Image.Image] = []

    def _build_canvas(self):
        frame = tk.Frame(self, bg=C_BG)
        frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(frame, bg="#111", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)

    def _bind_events(self):
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>",     self._on_drag)
        self.canvas.bind("<ButtonRelease-1>",self._on_release)
        self._start_x = self._start_y = 0

    def _canvas_to_img(self, x, y):
        return int(x / self.scale), int(y / self.scale)

    def _on_press(self, e):
        self._history.append(self.draw_image.copy())
        self._start_x, self._start_y = e.x, e.y
        self._last_x, self._last_y   = e.x, e.y
        if self.tool.get() == "text":
            ix, iy = self._canvas_to_img(e.x, e.y)
            try:
                font = ImageFont.truetype("arial.ttf", max(14, self.size_var.get()*4))
            except Exception:
                font = ImageFont.load_default()
            ImageDraw.Draw(self.draw_image).text((ix, iy), self.text_var.get(), fill=self.color.get(), font=font)
            self._refresh()

    def _on_drag(self, e):
        tool = self.tool.get()
        if tool == "pen" and self._last_x is not None:
            ix1,iy1 = self._canvas_to_img(self._last_x, self._last_y)
            ix2,iy2 = self._canvas_to_img(e.x, e.y)
            lw = max(1, self.size_var.get())
            ImageDraw.Draw(self.draw_image).line([ix1,iy1,ix2,iy2], fill=self.color.get(), width=lw)
            self._refresh()
        self._last_x, self._last_y = e.x, e.y

    def _on_release(self, e):
        tool = self.tool.get()
        ix1,iy1 = self._canvas_to_img(self._start_x, self._start_y)
        ix2,iy2 = self._canvas_to_img(e.x, e.y)
        lw = max(1, self.size_var.get())
        draw = ImageDraw.Draw(self.draw_image)
        if tool == "rect":
            draw.rectangle([ix1,iy1,ix2,iy2], outline=self.color.get(), width=lw)
        elif tool == "arrow":
            draw.line([ix1,iy1,ix2,iy2], fill=self.color.get(), width=lw)
            # Arrowhead
            import math
            angle = math.atan2(iy2-iy1, ix2-ix1)
            hs = 18
            for a in [angle+0.4, angle-0.4]:
                draw.line([ix2,iy2, ix2-int(hs*math.cos(a)), iy2-int(hs*math.sin(a))],
                          fill=self.color.get(), width=lw)
        elif tool == "blur":
            x1,y1,x2,y2 = sorted([ix1,ix2])[0],sorted([iy1,iy2])[0],sorted([ix1,ix2])[1],sorted([iy1,iy2])[1]
            if x2>x1 and y2>y1:
                region = self.draw_image.crop((x1,y1,x2,y2))
                blurred = region.resize((max(1,(x2-x1)//8), max(1,(y2-y1)//8)), Image.NEAREST)
                blurred = blurred.resize((x2-x1, y2-y1), Image.NEAREST)
                self.draw_image.paste(blurred, (x1,y1))
        self._refresh()

    def _refresh(self):
        w = int(self.orig_image.width  * self.scale)
        h = int(self.orig_image.height * self.scale)
        preview = self.draw_image.resize((w, h), Image.LANCZOS)
        self._tk_img = ImageTk.PhotoImage(preview)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._tk_img)

    def _undo(self):
        if self._history:
            self.draw_image = self._history.pop()
            self._refresh()

    def _save(self):
        self.on_save(self.draw_image)
        self.destroy()


# ── Screencast Recorder ───────────────────────────────────────────────────────
class Recorder:
    def __init__(self):
        self.recording = False
        self._thread   = None
        self.out_path  = None
        self._writer   = None
        self._fps      = 15

    def start(self, out_path: str, monitor_idx: int = 1):
        self.out_path  = out_path
        self.recording = True
        self._monitor  = monitor_idx
        self._thread   = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

    def stop(self) -> str:
        self.recording = False
        if self._thread:
            self._thread.join(timeout=5)
        return self.out_path

    def _record_loop(self):
        with mss.mss() as sct:
            mon = sct.monitors[min(self._monitor, len(sct.monitors)-1)]
            w, h = mon["width"], mon["height"]
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            self._writer = cv2.VideoWriter(self.out_path, fourcc, self._fps, (w, h))
            interval = 1.0 / self._fps
            while self.recording:
                t0 = time.time()
                frame = np.array(sct.grab(mon))
                frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                # Timestamp overlay
                ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                cv2.putText(frame_bgr, ts, (10, h-14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1, cv2.LINE_AA)
                self._writer.write(frame_bgr)
                elapsed = time.time() - t0
                time.sleep(max(0, interval - elapsed))
            self._writer.release()


# ── Main Application ──────────────────────────────────────────────────────────
class QACaptureApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{VERSION}")
        self.configure(bg=C_BG)
        self.geometry("980x680")
        self.minsize(820, 560)

        self.session: Session | None = None
        self.recorder = Recorder()
        self.is_recording = False
        self._rec_timer   = 0
        self._timer_job   = None
        self._screenshots: list[dict] = []

        self._build_ui()
        self._refresh_sessions()
        self._new_session_prompt()

    # ── UI Construction ────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Left sidebar
        sidebar = tk.Frame(self, bg=C_SURFACE, width=220)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)

        # Logo
        logo_frame = tk.Frame(sidebar, bg=C_SURFACE, pady=16, padx=16)
        logo_frame.pack(fill="x")
        tk.Label(logo_frame, text="🎯 QA Proof", bg=C_SURFACE, fg=C_TEXT,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w")
        tk.Label(logo_frame, text="Capture & Record", bg=C_SURFACE, fg=C_TEXT2,
                 font=("Segoe UI", 9)).pack(anchor="w")

        ttk.Separator(sidebar, orient="horizontal").pack(fill="x", padx=12)

        # Session info
        sess_frame = tk.Frame(sidebar, bg=C_SURFACE, padx=12, pady=10)
        sess_frame.pack(fill="x")
        tk.Label(sess_frame, text="ACTIVE SESSION", bg=C_SURFACE, fg=C_TEXT2,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.lbl_session = tk.Label(sess_frame, text="—", bg=C_SURFACE, fg=C_PRIMARY2,
                                    font=("Segoe UI", 10, "bold"), wraplength=180, justify="left")
        self.lbl_session.pack(anchor="w", pady=(2,0))

        btn_new_sess = tk.Button(sess_frame, text="+ New Session", bg=C_SURFACE2, fg=C_TEXT,
                                  font=("Segoe UI", 9), relief="flat", padx=8, pady=4,
                                  cursor="hand2", command=self._new_session_prompt)
        btn_new_sess.pack(anchor="w", pady=(6,0))

        ttk.Separator(sidebar, orient="horizontal").pack(fill="x", padx=12, pady=6)

        # Capture controls
        ctrl_frame = tk.Frame(sidebar, bg=C_SURFACE, padx=12, pady=4)
        ctrl_frame.pack(fill="x")
        tk.Label(ctrl_frame, text="CAPTURE", bg=C_SURFACE, fg=C_TEXT2,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0,6))

        self.btn_screenshot = self._sidebar_btn(ctrl_frame, "📷  Screenshot", C_PRIMARY, self._take_screenshot)
        self.btn_screenshot.pack(fill="x", pady=2)

        self.btn_region = self._sidebar_btn(ctrl_frame, "✂️  Region Capture", C_SURFACE2, self._capture_region)
        self.btn_region.pack(fill="x", pady=2)

        ttk.Separator(sidebar, orient="horizontal").pack(fill="x", padx=12, pady=8)

        # Recording controls
        rec_frame = tk.Frame(sidebar, bg=C_SURFACE, padx=12, pady=4)
        rec_frame.pack(fill="x")
        tk.Label(rec_frame, text="SCREENCAST", bg=C_SURFACE, fg=C_TEXT2,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0,6))

        self.btn_record = self._sidebar_btn(rec_frame, "⏺  Start Recording", C_DANGER, self._toggle_recording)
        self.btn_record.pack(fill="x", pady=2)

        self.lbl_rec_time = tk.Label(rec_frame, text="", bg=C_SURFACE, fg=C_RED_REC,
                                      font=("Segoe UI", 12, "bold"))
        self.lbl_rec_time.pack(anchor="w", pady=(4,0))

        # Monitor selector
        mon_frame = tk.Frame(rec_frame, bg=C_SURFACE)
        mon_frame.pack(fill="x", pady=(4,0))
        tk.Label(mon_frame, text="Monitor:", bg=C_SURFACE, fg=C_TEXT2,
                 font=("Segoe UI", 9)).pack(side="left")
        self.monitor_var = tk.IntVar(value=1)
        with mss.mss() as sct:
            mon_count = len(sct.monitors) - 1
        for i in range(1, max(2, mon_count+1)):
            tk.Radiobutton(mon_frame, text=str(i), variable=self.monitor_var, value=i,
                           bg=C_SURFACE, fg=C_TEXT, selectcolor=C_PRIMARY,
                           activebackground=C_SURFACE).pack(side="left", padx=2)

        ttk.Separator(sidebar, orient="horizontal").pack(fill="x", padx=12, pady=8)

        # Export
        exp_frame = tk.Frame(sidebar, bg=C_SURFACE, padx=12, pady=4)
        exp_frame.pack(fill="x")
        tk.Label(exp_frame, text="EXPORT", bg=C_SURFACE, fg=C_TEXT2,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0,6))
        self._sidebar_btn(exp_frame, "📁  Open Folder", C_SURFACE2, self._open_folder).pack(fill="x", pady=2)
        self._sidebar_btn(exp_frame, "📄  Export Report", C_SURFACE2, self._export_report).pack(fill="x", pady=2)

        # ── Shortcut hint
        hint = tk.Frame(sidebar, bg=C_SURFACE, padx=12, pady=8)
        hint.pack(side="bottom", fill="x")
        for line in ["F9 → Screenshot", "F10 → Rec Start/Stop", "F11 → Region"]:
            tk.Label(hint, text=line, bg=C_SURFACE, fg=C_TEXT2, font=("Segoe UI", 8)).pack(anchor="w")

        # ── Main content area
        main = tk.Frame(self, bg=C_BG)
        main.pack(side="left", fill="both", expand=True)

        # Tabs
        tab_bar = tk.Frame(main, bg=C_BG, pady=0)
        tab_bar.pack(fill="x")

        self.tab_var = tk.StringVar(value="gallery")
        for label, val in [("📸 Gallery", "gallery"), ("📋 Sessions", "sessions"), ("ℹ️ About", "about")]:
            b = tk.Radiobutton(tab_bar, text=label, variable=self.tab_var, value=val,
                               bg=C_BG, fg=C_TEXT2, selectcolor=C_BG, activebackground=C_BG,
                               font=("Segoe UI", 10), indicatoron=False, padx=16, pady=10,
                               relief="flat", borderwidth=0, cursor="hand2",
                               command=self._switch_tab)
            b.pack(side="left")

        ttk.Separator(main, orient="horizontal").pack(fill="x")

        # Content frames
        self.frame_gallery  = tk.Frame(main, bg=C_BG)
        self.frame_sessions = tk.Frame(main, bg=C_BG)
        self.frame_about    = tk.Frame(main, bg=C_BG)

        self._build_gallery()
        self._build_sessions_tab()
        self._build_about()
        self._switch_tab()

        # ── Global hotkeys
        self.bind_all("<F9>",  lambda e: self._take_screenshot())
        self.bind_all("<F10>", lambda e: self._toggle_recording())
        self.bind_all("<F11>", lambda e: self._capture_region())

    def _sidebar_btn(self, parent, text, bg, cmd):
        return tk.Button(parent, text=text, bg=bg, fg=C_TEXT,
                         font=("Segoe UI", 10), relief="flat",
                         pady=8, padx=10, cursor="hand2",
                         activebackground=C_SURFACE2, activeforeground=C_TEXT,
                         command=cmd)

    def _switch_tab(self):
        for f in [self.frame_gallery, self.frame_sessions, self.frame_about]:
            f.pack_forget()
        tab = self.tab_var.get()
        if tab == "gallery":
            self.frame_gallery.pack(fill="both", expand=True)
        elif tab == "sessions":
            self.frame_sessions.pack(fill="both", expand=True)
            self._refresh_sessions()
        else:
            self.frame_about.pack(fill="both", expand=True)

    # ── Gallery Tab ────────────────────────────────────────────────────────────

    def _build_gallery(self):
        # Toolbar
        toolbar = tk.Frame(self.frame_gallery, bg=C_SURFACE, pady=8, padx=12)
        toolbar.pack(fill="x")
        tk.Label(toolbar, text="Session Gallery", bg=C_SURFACE, fg=C_TEXT,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        self.lbl_count = tk.Label(toolbar, text="0 items", bg=C_SURFACE, fg=C_TEXT2,
                                   font=("Segoe UI", 9))
        self.lbl_count.pack(side="left", padx=12)
        tk.Button(toolbar, text="🗑 Clear All", bg=C_SURFACE2, fg=C_TEXT,
                  relief="flat", padx=8, pady=4, cursor="hand2",
                  command=self._clear_gallery).pack(side="right")

        # Scrollable grid
        container = tk.Frame(self.frame_gallery, bg=C_BG)
        container.pack(fill="both", expand=True)

        self.gallery_canvas = tk.Canvas(container, bg=C_BG, highlightthickness=0)
        vsb = ttk.Scrollbar(container, orient="vertical", command=self.gallery_canvas.yview)
        self.gallery_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.gallery_canvas.pack(side="left", fill="both", expand=True)

        self.gallery_inner = tk.Frame(self.gallery_canvas, bg=C_BG)
        self._gallery_window = self.gallery_canvas.create_window((0,0), window=self.gallery_inner, anchor="nw")
        self.gallery_inner.bind("<Configure>", lambda e: self.gallery_canvas.configure(
            scrollregion=self.gallery_canvas.bbox("all")))
        self.gallery_canvas.bind("<Configure>", lambda e: self.gallery_canvas.itemconfig(
            self._gallery_window, width=e.width))
        self.gallery_canvas.bind("<MouseWheel>", lambda e: self.gallery_canvas.yview_scroll(-1*(e.delta//120), "units"))

        # Note input bar
        note_bar = tk.Frame(self.frame_gallery, bg=C_SURFACE, pady=8, padx=12)
        note_bar.pack(fill="x", side="bottom")
        tk.Label(note_bar, text="Note for next capture:", bg=C_SURFACE, fg=C_TEXT2,
                 font=("Segoe UI", 9)).pack(side="left")
        self.note_var = tk.StringVar()
        tk.Entry(note_bar, textvariable=self.note_var, bg=C_SURFACE2, fg=C_TEXT,
                 insertbackground=C_TEXT, relief="flat", font=("Segoe UI",10),
                 width=40).pack(side="left", padx=8)

    def _add_gallery_item(self, thumb: Image.Image, meta: dict):
        self._screenshots.append({"thumb": thumb, "meta": meta})
        self._render_gallery()

    def _render_gallery(self):
        for w in self.gallery_inner.winfo_children():
            w.destroy()

        COLS = 3
        for i, item in enumerate(self._screenshots):
            row, col = divmod(i, COLS)
            card = tk.Frame(self.gallery_inner, bg=C_SURFACE, padx=6, pady=6,
                            relief="flat", bd=0)
            card.grid(row=row, column=col, padx=8, pady=8, sticky="nsew")
            self.gallery_inner.columnconfigure(col, weight=1)

            # Thumbnail
            thumb = item["thumb"].copy()
            thumb.thumbnail((260, 160))
            tkimg = ImageTk.PhotoImage(thumb)
            lbl_img = tk.Label(card, image=tkimg, bg=C_SURFACE, cursor="hand2")
            lbl_img.image = tkimg
            lbl_img.pack()
            lbl_img.bind("<Button-1>", lambda e, idx=i: self._preview_item(idx))

            # Kind badge
            meta = item["meta"]
            kind_color = C_SUCCESS if meta["kind"] == "screenshot" else C_DANGER
            tk.Label(card, text=meta["kind"].upper(), bg=kind_color, fg=C_TEXT,
                     font=("Segoe UI", 7, "bold"), padx=4).pack(anchor="w", pady=(4,0))

            tk.Label(card, text=meta.get("note","") or meta["file"][:30],
                     bg=C_SURFACE, fg=C_TEXT, font=("Segoe UI", 9),
                     wraplength=240, justify="left").pack(anchor="w")
            tk.Label(card, text=f"🕐 {meta['date']} {meta['time']}",
                     bg=C_SURFACE, fg=C_TEXT2, font=("Segoe UI", 8)).pack(anchor="w")

            # Action row
            acts = tk.Frame(card, bg=C_SURFACE)
            acts.pack(fill="x", pady=(4,0))
            tk.Button(acts, text="👁 Preview", bg=C_SURFACE2, fg=C_TEXT, relief="flat",
                      padx=4, pady=2, font=("Segoe UI",8), cursor="hand2",
                      command=lambda idx=i: self._preview_item(idx)).pack(side="left", padx=2)
            if meta["kind"] == "screenshot":
                tk.Button(acts, text="✏️ Annotate", bg=C_SURFACE2, fg=C_TEXT, relief="flat",
                          padx=4, pady=2, font=("Segoe UI",8), cursor="hand2",
                          command=lambda idx=i: self._annotate_item(idx)).pack(side="left", padx=2)
            tk.Button(acts, text="🗑", bg=C_SURFACE2, fg=C_DANGER, relief="flat",
                      padx=4, pady=2, font=("Segoe UI",8), cursor="hand2",
                      command=lambda idx=i: self._delete_item(idx)).pack(side="right", padx=2)

        self.lbl_count.config(text=f"{len(self._screenshots)} items")

    def _preview_item(self, idx: int):
        meta = self._screenshots[idx]["meta"]
        path = self.session.folder / meta["file"] if self.session else Path(meta["file"])
        if not path.exists():
            messagebox.showwarning("Not found", f"File not found:\n{path}")
            return
        if meta["kind"] == "screenshot":
            img = Image.open(path)
            win = tk.Toplevel(self)
            win.title(f"Preview — {meta['file']}")
            win.configure(bg=C_BG)
            sw,sh = int(self.winfo_screenwidth()*0.8), int(self.winfo_screenheight()*0.8)
            img.thumbnail((sw,sh))
            tkimg = ImageTk.PhotoImage(img)
            tk.Label(win, image=tkimg, bg=C_BG).pack(padx=10, pady=10)
            win.mainloop_image = tkimg
        else:
            os.startfile(str(path))

    def _annotate_item(self, idx: int):
        meta = self._screenshots[idx]["meta"]
        if not self.session:
            return
        path = self.session.folder / meta["file"]
        if not path.exists():
            return
        img = Image.open(path)
        def on_save(annotated: Image.Image):
            annotated.save(str(path))
            thumb = annotated.copy()
            thumb.thumbnail((260, 160))
            self._screenshots[idx]["thumb"] = thumb
            self._render_gallery()
            self.status("Annotation saved ✓")
        AnnotateWindow(self, img, on_save)

    def _delete_item(self, idx: int):
        if messagebox.askyesno("Delete", "Remove this item from the gallery?"):
            self._screenshots.pop(idx)
            self._render_gallery()

    def _clear_gallery(self):
        if messagebox.askyesno("Clear", "Remove all items from gallery view?\n(Files are kept on disk)"):
            self._screenshots.clear()
            self._render_gallery()

    # ── Sessions Tab ────────────────────────────────────────────────────────────

    def _build_sessions_tab(self):
        toolbar = tk.Frame(self.frame_sessions, bg=C_SURFACE, pady=8, padx=12)
        toolbar.pack(fill="x")
        tk.Label(toolbar, text="All Sessions", bg=C_SURFACE, fg=C_TEXT,
                 font=("Segoe UI", 12, "bold")).pack(side="left")
        tk.Button(toolbar, text="🔄 Refresh", bg=C_SURFACE2, fg=C_TEXT,
                  relief="flat", padx=8, pady=4, cursor="hand2",
                  command=self._refresh_sessions).pack(side="right")

        cols = ("Name", "Date", "Items", "Folder")
        self.sess_tree = ttk.Treeview(self.frame_sessions, columns=cols, show="headings", height=20)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background=C_SURFACE2, foreground=C_TEXT,
                        rowheight=28, fieldbackground=C_SURFACE2, borderwidth=0)
        style.configure("Treeview.Heading", background=C_SURFACE, foreground=C_TEXT2,
                        relief="flat", font=("Segoe UI",9,"bold"))
        style.map("Treeview", background=[("selected", C_PRIMARY)])

        for c, w in zip(cols, [200, 120, 60, 400]):
            self.sess_tree.heading(c, text=c)
            self.sess_tree.column(c, width=w, minwidth=50)
        self.sess_tree.pack(fill="both", expand=True, padx=8, pady=8)

        btn_row = tk.Frame(self.frame_sessions, bg=C_BG, pady=6, padx=8)
        btn_row.pack(fill="x")
        tk.Button(btn_row, text="📁 Open Folder", bg=C_SURFACE2, fg=C_TEXT,
                  relief="flat", padx=10, pady=5, cursor="hand2",
                  command=self._open_selected_session).pack(side="left", padx=4)
        tk.Button(btn_row, text="▶ Load Session", bg=C_PRIMARY, fg=C_TEXT,
                  relief="flat", padx=10, pady=5, cursor="hand2",
                  command=self._load_selected_session).pack(side="left", padx=4)

    def _refresh_sessions(self):
        if not hasattr(self, "sess_tree"):
            return
        for row in self.sess_tree.get_children():
            self.sess_tree.delete(row)
        for s in Session.load_all():
            self.sess_tree.insert("", "end", values=(
                s.get("name","—"),
                s.get("created","")[:10],
                len(s.get("items",[])),
                s.get("folder","")
            ))

    def _open_selected_session(self):
        sel = self.sess_tree.selection()
        if not sel:
            return
        folder = self.sess_tree.item(sel[0])["values"][3]
        os.startfile(folder)

    def _load_selected_session(self):
        sel = self.sess_tree.selection()
        if not sel:
            return
        messagebox.showinfo("Load Session", "Session loading: items from this session will appear in the gallery.")

    # ── About Tab ──────────────────────────────────────────────────────────────

    def _build_about(self):
        frame = tk.Frame(self.frame_about, bg=C_BG)
        frame.place(relx=0.5, rely=0.4, anchor="center")
        tk.Label(frame, text="🎯", bg=C_BG, font=("Segoe UI", 48)).pack()
        tk.Label(frame, text="QA Proof Capture", bg=C_BG, fg=C_TEXT,
                 font=("Segoe UI", 22, "bold")).pack(pady=(8,0))
        tk.Label(frame, text=f"Version {VERSION}", bg=C_BG, fg=C_TEXT2,
                 font=("Segoe UI", 11)).pack()
        tk.Label(frame, text="Screenshot & Screencast tool for QA teams",
                 bg=C_BG, fg=C_TEXT2, font=("Segoe UI", 11)).pack(pady=(4,16))

        for hotkey, desc in [("F9", "Take Screenshot"), ("F10", "Start / Stop Recording"), ("F11", "Region Capture")]:
            row = tk.Frame(frame, bg=C_SURFACE2, padx=16, pady=8)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=hotkey, bg=C_SURFACE2, fg=C_PRIMARY2,
                     font=("Segoe UI", 11, "bold"), width=6).pack(side="left")
            tk.Label(row, text=desc, bg=C_SURFACE2, fg=C_TEXT,
                     font=("Segoe UI", 10)).pack(side="left")

        tk.Label(frame, text=f"Captures saved to: {BASE_DIR}",
                 bg=C_BG, fg=C_TEXT2, font=("Segoe UI", 9)).pack(pady=(16,0))

    # ── Core Actions ───────────────────────────────────────────────────────────

    def _ensure_session(self) -> bool:
        if not self.session:
            messagebox.showwarning("No Session", "Please create a session first.")
            self._new_session_prompt()
            return self.session is not None
        return True

    def _new_session_prompt(self):
        name = simpledialog.askstring("New Session", "Enter session / test name:",
                                      initialvalue=f"QA Session {datetime.date.today()}")
        if name:
            self.session = Session(name.strip())
            self.lbl_session.config(text=name.strip())
            self._screenshots.clear()
            self._render_gallery()
            self.status(f"Session '{name}' created ✓")

    def _take_screenshot(self):
        if not self._ensure_session():
            return
        self.withdraw()
        time.sleep(0.25)
        with mss.mss() as sct:
            mon   = sct.monitors[self.monitor_var.get()]
            shot  = sct.grab(mon)
            img   = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
        self.deiconify()

        note = self.note_var.get().strip()
        ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"screenshot_{ts}.png"
        fpath = self.session.folder / fname
        img.save(str(fpath))

        meta  = self.session.add_item("screenshot", fname, note)
        thumb = img.copy()
        thumb.thumbnail((260, 160))
        self._add_gallery_item(thumb, meta)
        self.note_var.set("")
        self.status(f"Screenshot saved: {fname}")

    def _capture_region(self):
        if not self._ensure_session():
            return
        self.withdraw()
        time.sleep(0.15)
        overlay = tk.Toplevel()
        overlay.attributes("-fullscreen", True, "-alpha", 0.3, "-topmost", True)
        overlay.configure(bg="black")
        overlay.attributes("-transparentcolor", "")

        canvas = tk.Canvas(overlay, cursor="crosshair", bg="black",
                           highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        canvas.configure(bg="gray10")

        rect_id = None
        sx = sy = 0

        def on_press(e):
            nonlocal sx, sy, rect_id
            sx, sy = e.x, e.y
            rect_id = canvas.create_rectangle(sx, sy, sx, sy, outline=C_PRIMARY, width=2)

        def on_drag(e):
            canvas.coords(rect_id, sx, sy, e.x, e.y)

        def on_release(e):
            x1, y1 = min(sx, e.x), min(sy, e.y)
            x2, y2 = max(sx, e.x), max(sy, e.y)
            overlay.destroy()
            self.deiconify()
            if x2-x1 < 5 or y2-y1 < 5:
                return
            with mss.mss() as sct:
                region = {"left": x1, "top": y1, "width": x2-x1, "height": y2-y1}
                shot = sct.grab(region)
                img  = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")

            note  = self.note_var.get().strip()
            ts    = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"region_{ts}.png"
            fpath = self.session.folder / fname
            img.save(str(fpath))

            meta  = self.session.add_item("screenshot", fname, note)
            thumb = img.copy()
            thumb.thumbnail((260, 160))
            self._add_gallery_item(thumb, meta)
            self.note_var.set("")
            self.status(f"Region captured: {fname}")

        canvas.bind("<ButtonPress-1>",   on_press)
        canvas.bind("<B1-Motion>",       on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        overlay.bind("<Escape>", lambda e: [overlay.destroy(), self.deiconify()])

    def _toggle_recording(self):
        if not self._ensure_session():
            return
        if not self.is_recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _start_recording(self):
        ts    = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"recording_{ts}.mp4"
        fpath = str(self.session.folder / fname)
        self.recorder.start(fpath, self.monitor_var.get())
        self.is_recording    = True
        self._rec_timer      = 0
        self._current_rec_fn = fname
        self.btn_record.config(text="⏹  Stop Recording", bg=C_WARNING)
        self._update_timer()
        self.status("Recording started…")

    def _stop_recording(self):
        self.recorder.stop()
        self.is_recording = False
        if self._timer_job:
            self.after_cancel(self._timer_job)
        self.lbl_rec_time.config(text="")
        self.btn_record.config(text="⏺  Start Recording", bg=C_DANGER)

        note  = self.note_var.get().strip()
        fname = self._current_rec_fn
        meta  = self.session.add_item("recording", fname, note)

        # Placeholder thumb
        thumb = Image.new("RGB", (260, 160), color="#1A1A22")
        draw  = ImageDraw.Draw(thumb)
        draw.text((100, 60), "▶ VIDEO", fill="#6C63FF")
        draw.text((60, 85), fname[:30], fill="#9B9AB8")
        self._add_gallery_item(thumb, meta)
        self.note_var.set("")
        self.status(f"Recording saved: {fname}")

    def _update_timer(self):
        if self.is_recording:
            self._rec_timer += 1
            m, s = divmod(self._rec_timer, 60)
            self.lbl_rec_time.config(text=f"⏺ {m:02d}:{s:02d}")
            self._timer_job = self.after(1000, self._update_timer)

    def _open_folder(self):
        if self.session:
            os.startfile(str(self.session.folder))
        else:
            os.startfile(str(BASE_DIR))

    def _export_report(self):
        if not self.session or not self._screenshots:
            messagebox.showinfo("Export", "No items to export in current session.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".html",
            filetypes=[("HTML Report", "*.html"), ("All files", "*.*")],
            initialfile=f"QA_Report_{datetime.date.today()}.html"
        )
        if not path:
            return
        self._generate_html_report(path)
        messagebox.showinfo("Exported", f"Report saved to:\n{path}")
        os.startfile(path)

    def _generate_html_report(self, out_path: str):
        import base64

        items_html = ""
        for item in self._screenshots:
            meta  = item["meta"]
            fpath = self.session.folder / meta["file"]
            kind  = meta["kind"]
            if kind == "screenshot" and fpath.exists():
                with open(fpath, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode()
                media = f'<img src="data:image/png;base64,{b64}" style="max-width:100%;border-radius:6px">'
            else:
                media = f'<div style="padding:40px;background:#1A1A22;border-radius:6px;color:#9B9AB8;text-align:center">▶ {meta["file"]}</div>'

            badge_color = "#22C55E" if kind == "screenshot" else "#EF4444"
            items_html += f"""
            <div class="card">
              <div class="badge" style="background:{badge_color}">{kind.upper()}</div>
              {media}
              <div class="meta">
                <strong style="color:#F1F0FF">{meta.get('note') or meta['file']}</strong><br>
                <span>🕐 {meta['date']} {meta['time']}</span>
              </div>
            </div>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>QA Report — {self.session.name}</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{font-family:'Segoe UI',sans-serif;background:#0F0F13;color:#F1F0FF;padding:32px}}
  h1{{font-size:24px;margin-bottom:4px}}
  .sub{{color:#9B9AB8;margin-bottom:24px;font-size:14px}}
  .grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:20px}}
  .card{{background:#1A1A22;border-radius:10px;padding:14px;border:1px solid #2E2E3E}}
  .badge{{display:inline-block;padding:2px 10px;border-radius:20px;font-size:11px;font-weight:700;margin-bottom:10px;color:#fff}}
  .meta{{margin-top:10px;font-size:13px;color:#9B9AB8;line-height:1.6}}
  .header{{margin-bottom:28px}}
  .stat{{display:inline-block;background:#22222E;border-radius:8px;padding:10px 20px;margin-right:12px;font-size:13px}}
  .stat strong{{display:block;font-size:20px;color:#6C63FF}}
</style>
</head>
<body>
<div class="header">
  <h1>🎯 QA Proof Report</h1>
  <p class="sub">Session: {self.session.name} &nbsp;·&nbsp; Generated: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
  <div>
    <div class="stat"><strong>{len(self._screenshots)}</strong>Total Items</div>
    <div class="stat"><strong>{sum(1 for i in self._screenshots if i['meta']['kind']=='screenshot')}</strong>Screenshots</div>
    <div class="stat"><strong>{sum(1 for i in self._screenshots if i['meta']['kind']=='recording')}</strong>Recordings</div>
  </div>
</div>
<div class="grid">{items_html}</div>
</body></html>"""
        Path(out_path).write_text(html, encoding="utf-8")

    def status(self, msg: str):
        self.title(f"{APP_NAME} — {msg}")
        self.after(3000, lambda: self.title(f"{APP_NAME} v{VERSION}"))


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QACaptureApp()
    app.mainloop()
