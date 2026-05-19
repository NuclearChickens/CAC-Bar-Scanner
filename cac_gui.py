#!/usr/bin/env python3
"""Tkinter GUI for the CAC Code 39 barcode scanner.

One window, one Notebook. Tabs:
    * Scanner — the verdict banner, entry, decoded fields
    * Hours / Limits / Roster / Banned — settings, all auto-saving

Auto-fires when the entry hits 18 chars (or on Enter, which most
USB scanners emit as the keystroke suffix). Each scan is
checked against the configured policy; allowed scans flash green and
record toward the count, denied scans flash red and are not recorded.

Starts fullscreen on Linux and maximized on Windows; F11 toggles
fullscreen, Escape exits fullscreen.

Fonts and paddings scale at runtime based on screen resolution so the
UI stays large and legible on monitors from small laptops up to 4K
kiosks. The Scanner tab's verdict banner is the focal point — it
expands to fill most of the available vertical space so the
ALLOWED/DENIED status is readable from across a room.
"""
from __future__ import annotations

import os
import sys
import tkinter as tk
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import audit_log
import backup
import reset_log
import settings as settings_mod
import start_menu
from cac_decoder import BRANCHES, BARCODE_LEN, CATEGORIES, InvalidBarcode, decode
from scan_log import count_since, prune_before, record_scan


# ---------------------------------------------------------------- palette
BLACK = "#000000"
WHITE = "#ffffff"
GREEN = "#0a8a3a"
RED = "#c0392b"
LOCKED_BG = "#fce8e6"     # very light red for the locked banner
UNLOCKED_BG = "#e6f4ea"   # very light green for the unlocked banner


# ---------------------------------------------------------------- fonts
# Base point sizes designed for a 1920x1080 baseline display. App._setup_fonts
# scales each entry at runtime by App._scale (derived from actual screen
# dimensions), so the same UI stays readable on 1366x768 laptops and 4K
# kiosks alike. Tuple format: (point_size, weight, family); empty weight
# means normal weight.
_BASE_FONTS: dict[str, tuple[int, str, str]] = {
    "BANNER_HEAD":   (84, "bold", "TkDefaultFont"),
    "BANNER_DETAIL": (40, "",     "TkDefaultFont"),
    "ENTRY":         (44, "",     "TkFixedFont"),
    "VALUE_BIG":     (40, "bold", "TkFixedFont"),  # EDIPI — critical, fixed
    "VALUE":         (22, "",     "TkDefaultFont"),  # Category/Branch — reference
    "VALUE_BOLD":    (34, "bold", "TkDefaultFont"),  # Drink count — critical
    "LABEL":         (24, "bold", "TkDefaultFont"),
    "BODY":          (22, "",     "TkDefaultFont"),
    "TIP":           (16, "",     "TkDefaultFont"),
    "BUTTON":        (22, "",     "TkDefaultFont"),
    "TAB":           (26, "bold", "TkDefaultFont"),
    "SECTION":       (28, "bold", "TkDefaultFont"),
    "OPTION":        (24, "",     "TkDefaultFont"),
    "ATTRIBUTION":   (13, "",     "TkDefaultFont"),
    "LIST_BIG":      (26, "",     "TkFixedFont"),
    "LIST_MED":      (22, "",     "TkFixedFont"),
    "LIST_SMALL":    (20, "",     "TkFixedFont"),
}


def _enable_windows_dpi_awareness() -> None:
    if sys.platform != "win32":
        return
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except (ImportError, AttributeError, OSError):
        pass


def _resource_path(rel: str) -> str:
    """Resolve a path to a bundled resource.

    PyInstaller --onefile extracts ``datas`` files into a per-run temp
    directory exposed as ``sys._MEIPASS``; in a source-tree run we
    resolve relative to this module's directory instead."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)


def _set_window_icon(root: tk.Tk) -> None:
    """Set the title-bar / taskbar icon for the root window and any
    Toplevels created from it.

    Windows only — Tk's ``iconbitmap`` on Linux/macOS expects an XBM
    file and would raise on a .ico. The exe icon (the one shown by
    File Explorer) is wired up separately via BarScanner.spec, so
    skipping this on non-Windows just leaves the dev's Tk feather
    icon in place."""
    if sys.platform != "win32":
        return
    try:
        root.iconbitmap(default=_resource_path("icon.ico"))
    except tk.TclError:
        # Icon missing or unreadable — not worth blocking startup.
        pass


def _parse_expires_input(s: str) -> tuple[str | None, str | None]:
    """Parse a ban-expires field. Accepts 8 digits ``YYYYMMDD`` (preferred)
    and also tolerates ``YYYY-MM-DD``. Returns (iso_string_or_None,
    error_message_or_None); a blank input is (None, None) = permanent."""
    raw = s.strip().replace("-", "")
    if not raw:
        return None, None
    if len(raw) != 8 or not raw.isdigit():
        return None, "Expires must be 8 digits (YYYYMMDD) or blank"
    iso = f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]}"
    try:
        date.fromisoformat(iso)
    except ValueError as e:
        return None, f"Invalid date: {e}"
    return iso, None


# ================================================================== App


class App(tk.Tk):
    PLACEHOLDER = "—"
    REFRESH_MS = 60_000
    AUTO_LOCK_MS = 5 * 60 * 1000   # auto-lock settings 5 min after unlock

    def __init__(self) -> None:
        super().__init__()
        self.title("CAC Barcode Scanner")
        _set_window_icon(self)

        # Scaling: must come before fonts/styles/geometry — they all depend
        # on it. Screen dimensions are queryable as soon as Tk is up.
        self._scale = self._compute_scale()
        self._setup_fonts()
        self._configure_styles()

        self.geometry(f"{self._px(1280)}x{self._px(900)}")
        self.minsize(self._px(900), self._px(700))

        self.settings = settings_mod.load()
        self._processing = False
        self._building = True   # suppress trace_add commits during construction
        self._committing = False
        self._last_decoded_edipi: str | None = None
        self._fullscreen = False
        self._reset_state: str = "idle"      # "idle" | "first" | "second"
        self._reset_first_edipi: str | None = None
        self._settings_unlocked: bool = False
        self._unlock_authorizers: tuple[str, str] | None = None
        self._pre_edit_settings: settings_mod.Settings | None = None
        self._lockable_content_frames: list[tk.Misc] = []
        self._lock_banners: list[tuple[tk.Frame, tk.Label, ttk.Button]] = []
        self._value_labels: list[ttk.Label] = []
        self._last_root_width: int = 0
        self._auto_lock_after_id: str | None = None

        self._build_widgets()
        self._building = False

        self._reset_banner()
        self._refresh_session_label()
        self._prune_log()
        self.entry.focus_set()
        self.after(self.REFRESH_MS, self._tick)
        # Offer to add ourselves to the Start menu once, on the first
        # launch of a frozen Windows build. Deferred so the main window
        # is fully drawn before the prompt appears on top of it.
        self.after(250, self._maybe_offer_start_menu_install)

        self.bind("<F11>", self._toggle_fullscreen)
        self.bind("<Escape>", self._exit_fullscreen)
        self.bind_all("<Control-q>", lambda _e: self._on_close())
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Configure>", self._on_root_resize)

        self._start_maximized()

    # ----------------------------------------------------- scaling helpers

    def _compute_scale(self) -> float:
        """Scale factor for fonts and dimensions, derived from screen size.

        Baseline (= 1.0) is 1920x1080. Smaller screens scale down, larger
        ones scale up, clamped to a sensible range. Uses the smaller of
        the width/height ratios so nothing overflows in either dimension.

        The trailing 0.65 factor shaves ~35% off every font and padding
        so the entire home screen — verdict banner, entry, decoded grid,
        session line, footer — fits in the visible area on common WM
        setups where panels and decorations eat substantial vertical
        space. Without it the original sizing was readable in isolation
        but overflowed once the WM took its cut."""
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        raw = min(sw / 1920.0, sh / 1080.0)
        return max(0.36, min(1.6, raw * 0.65))

    def _px(self, base: int) -> int:
        """Scale a pixel value (padding, spacing, fixed dimension)."""
        return max(1, int(round(base * self._scale)))

    def _fpt(self, base: int) -> int:
        """Scale a font point size, with an 8pt floor for legibility."""
        return max(8, int(round(base * self._scale)))

    def _setup_fonts(self) -> None:
        """Materialize each base font as a self.F_<NAME> attribute."""
        for name, (size, weight, family) in _BASE_FONTS.items():
            scaled = self._fpt(size)
            font = (family, scaled, weight) if weight else (family, scaled)
            setattr(self, f"F_{name}", font)

    def _configure_styles(self) -> None:
        style = ttk.Style(self)
        style.configure(
            "TButton", font=self.F_BUTTON, padding=(self._px(32), self._px(16))
        )
        style.configure("TEntry", padding=self._px(14))
        style.configure(
            "TNotebook.Tab",
            font=self.F_TAB,
            padding=(self._px(40), self._px(20)),
        )
        style.configure("TCheckbutton", font=self.F_BODY, padding=self._px(6))
        style.configure("TRadiobutton", font=self.F_OPTION, padding=self._px(8))
        style.configure("TLabelframe.Label", font=self.F_SECTION)
        style.configure(
            "TSpinbox",
            font=self.F_VALUE_BOLD,
            padding=self._px(10),
            arrowsize=self._px(32),
        )

    def _on_root_resize(self, event: tk.Event) -> None:
        """Update wraplengths when the root window resizes so every
        variable-text label wraps to the available width — no string is
        ever cut off horizontally on any monitor size."""
        if event.widget is not self:
            return
        width = event.width
        if width == self._last_root_width:
            return
        self._last_root_width = width
        if hasattr(self, "banner_detail"):
            self.banner_detail.configure(
                wraplength=max(self._px(400), int(width * 0.92))
            )
        for lbl in self._value_labels:
            # Decoded values share the row two-up, so each gets ~half the
            # width minus its label column.
            lbl.configure(wraplength=max(self._px(280), int(width * 0.42)))
        # Full-width text rows: session line, footer status, and the
        # bottom tip line. Each can carry runtime-generated strings
        # (error messages, session descriptions) of unbounded length.
        full_width = max(self._px(300), int(width * 0.95))
        if hasattr(self, "session_lbl"):
            self.session_lbl.configure(wraplength=full_width)
        if hasattr(self, "status_lbl"):
            self.status_lbl.configure(wraplength=full_width)
        if hasattr(self, "_tip_lbl"):
            self._tip_lbl.configure(
                wraplength=max(self._px(200), int(width * 0.7))
            )

    def _on_scanner_tab_resize(self, event: tk.Event) -> None:
        """Size the banner row to a generous fraction of the tab so the
        verdict dominates the screen on any display, while still leaving
        enough room for the decoded section to render its full content."""
        if not hasattr(self, "_scanner_tab") or event.widget is not self._scanner_tab:
            return
        # Banner targets ~36% of the tab height — enough to dominate the
        # screen without starving the decoded section below. Floor and
        # ceiling clamps protect tiny and giant displays alike.
        target = max(self._px(260), min(self._px(900), int(event.height * 0.36)))
        self._scanner_tab.rowconfigure(0, minsize=target)

    # ---------------------------------------------------- platform sizing

    def _start_maximized(self) -> None:
        """Start fullscreen on Linux, maximized on Windows."""
        if sys.platform == "win32":
            try:
                self.state("zoomed")
                return
            except tk.TclError:
                pass
        # Linux / macOS: try true fullscreen, then X11 zoomed.
        try:
            self.attributes("-fullscreen", True)
            self._fullscreen = True
            return
        except tk.TclError:
            pass
        try:
            self.attributes("-zoomed", True)
            return
        except tk.TclError:
            pass
        # Last-ditch fallback: size to screen.
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"{sw}x{sh}+0+0")

    def _toggle_fullscreen(self, _event: tk.Event | None = None) -> str:
        self._fullscreen = not self._fullscreen
        try:
            self.attributes("-fullscreen", self._fullscreen)
        except tk.TclError:
            pass
        # On Windows, when leaving fullscreen, snap back to maximized.
        if sys.platform == "win32" and not self._fullscreen:
            try:
                self.state("zoomed")
            except tk.TclError:
                pass
        return "break"

    def _exit_fullscreen(self, _event: tk.Event | None = None) -> str:
        if self._fullscreen:
            self._fullscreen = False
            try:
                self.attributes("-fullscreen", False)
            except tk.TclError:
                pass
            if sys.platform == "win32":
                try:
                    self.state("zoomed")
                except tk.TclError:
                    pass
        return "break"

    # ---------------------------------------------------------- build UI

    def _build_widgets(self) -> None:
        # Header bar — plain Tk widgets so background/foreground are
        # honored regardless of the ttk theme (some Linux themes silently
        # drop inline foreground args on ttk.Label).
        header = tk.Frame(self, bg=WHITE)
        header.pack(side="top", fill="x")
        tk.Label(
            header,
            text="CAC Barcode Scanner",
            font=self.F_SECTION,
            bg=WHITE,
            fg=BLACK,
            padx=self._px(24),
            pady=self._px(10),
            anchor="w",
        ).pack(side="left")
        tk.Label(
            header,
            text="Made by Jeremy Evans",
            font=self.F_ATTRIBUTION,
            bg=WHITE,
            fg=BLACK,
            padx=self._px(24),
            pady=self._px(10),
        ).pack(side="right")

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        self._build_scanner_tab()
        self._build_hours_tab()
        self._build_limits_tab()
        self._build_roster_tab()
        self._build_banned_tab()
        self._build_reset_tab()
        self._build_logs_tab()
        self._build_backup_tab()

        # Footer status bar — plain Tk for the same reason as the header.
        footer = tk.Frame(self, bg=WHITE)
        footer.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar()
        self.status_lbl = tk.Label(
            footer,
            textvariable=self.status_var,
            font=self.F_BODY,
            bg=WHITE,
            fg=BLACK,
            padx=self._px(20),
            pady=self._px(6),
            anchor="w",
        )
        self.status_lbl.pack(side="left")
        tk.Label(
            footer,
            text="Made by Jeremy Evans",
            font=self.F_ATTRIBUTION,
            bg=WHITE,
            fg=BLACK,
            padx=self._px(20),
            pady=self._px(6),
        ).pack(side="right")

        # Settings tabs are locked-by-default; lock state must be applied
        # AFTER every tab has registered its content frame.
        self._apply_lock_state()

    # ------------------------------------------------------- Scanner tab

    def _build_scanner_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=self._px(24))
        self.notebook.add(tab, text="Scanner")
        self._scanner_tab = tab
        tab.columnconfigure(0, weight=1)
        # Banner is the focal point. tkinter's `weight` only divides extra
        # space after each row's requested size is satisfied, so we also
        # bind below to dynamically size row 0's minsize to a percentage
        # of the actual tab height — letting the banner dominate on any
        # display without clipping the decoded section on smaller ones.
        tab.rowconfigure(0, weight=5, minsize=self._px(260))
        tab.rowconfigure(3, weight=1)
        tab.bind("<Configure>", self._on_scanner_tab_resize)

        # Verdict banner — no fixed height; expands to fill its row.
        self.banner = tk.Frame(
            tab,
            bg=WHITE,
            highlightbackground=BLACK,
            highlightcolor=BLACK,
            highlightthickness=self._px(3),
            bd=0,
        )
        self.banner.grid(row=0, column=0, sticky="nsew", pady=(0, self._px(18)))
        self.banner.columnconfigure(0, weight=1)
        self.banner.rowconfigure(0, weight=3)
        self.banner.rowconfigure(1, weight=2)
        self.banner_lbl = tk.Label(
            self.banner,
            text="Ready to scan",
            bg=WHITE,
            fg=BLACK,
            font=self.F_BANNER_HEAD,
        )
        self.banner_lbl.grid(
            row=0,
            column=0,
            sticky="s",
            padx=self._px(20),
            pady=(self._px(16), 0),
        )
        self.banner_detail = tk.Label(
            self.banner,
            text="",
            bg=WHITE,
            fg=BLACK,
            font=self.F_BANNER_DETAIL,
            wraplength=self._px(1400),
            justify="center",
        )
        self.banner_detail.grid(
            row=1,
            column=0,
            sticky="n",
            padx=self._px(20),
            pady=(self._px(8), self._px(18)),
        )

        ttk.Label(
            tab,
            text="Scan a CAC barcode:",
            font=self.F_BODY,
        ).grid(row=1, column=0, sticky="w", pady=(0, self._px(6)))

        self.input_var = tk.StringVar()
        self.entry = ttk.Entry(
            tab, textvariable=self.input_var, font=self.F_ENTRY, justify="center"
        )
        self.entry.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, self._px(18)),
            ipady=self._px(8),
        )
        self.entry.bind("<Return>", self._on_enter)
        self.input_var.trace_add("write", self._on_input_changed)

        # Decoded section uses a 2-row × 2-cell layout so the section
        # stays compact vertically — leaving more room for the verdict
        # banner — while still showing every field at a large font.
        # Top row: EDIPI (left) | Drinks count (right) — the two fields
        # the bartender actually checks. Bottom row: Category | Branch —
        # reference info shown smaller.
        result = ttk.LabelFrame(tab, text="Decoded", padding=self._px(10))
        result.grid(row=3, column=0, sticky="nsew", pady=(self._px(2), self._px(6)))
        result.columnconfigure(1, weight=2)
        result.columnconfigure(3, weight=1)

        self._values: dict[str, tk.StringVar] = {}
        self._count_label: ttk.Label | None = None
        cells = [
            # (row, label_col, value_col, label_text, key, font)
            (0, 0, 1, "EDIPI",               "edipi",    self.F_VALUE_BIG),
            (0, 2, 3, "Drinks this session", "count",    self.F_VALUE_BOLD),
            (1, 0, 1, "Category",            "category", self.F_VALUE),
            (1, 2, 3, "Branch",              "branch",   self.F_VALUE),
        ]
        for row, lcol, vcol, label_text, key, font in cells:
            row_lbl = ttk.Label(result, text=label_text + ":", font=self.F_LABEL)
            left_pad = 0 if lcol == 0 else self._px(28)
            row_lbl.grid(
                row=row,
                column=lcol,
                sticky="w",
                padx=(left_pad, self._px(12)),
                pady=self._px(4),
            )
            if key == "count":
                self._count_label = row_lbl
            var = tk.StringVar(value=self.PLACEHOLDER)
            self._values[key] = var
            value_lbl = ttk.Label(
                result,
                textvariable=var,
                font=font,
                wraplength=self._px(700),
                justify="left",
            )
            value_lbl.grid(row=row, column=vcol, sticky="w", pady=self._px(4))
            self._value_labels.append(value_lbl)

        session_frame = ttk.Frame(tab)
        session_frame.grid(row=4, column=0, sticky="ew", pady=(self._px(6), 0))
        session_frame.columnconfigure(0, weight=1)
        self.session_var = tk.StringVar()
        self.session_lbl = ttk.Label(
            session_frame, textvariable=self.session_var, font=self.F_BODY
        )
        self.session_lbl.grid(row=0, column=0, sticky="w")

        bottom = ttk.Frame(tab)
        bottom.grid(row=5, column=0, sticky="ew", pady=(self._px(12), 0))
        bottom.columnconfigure(0, weight=1)
        self._tip_lbl = ttk.Label(
            bottom,
            text="Tip: keep the input box focused. F11 toggles fullscreen, Esc exits.",
            font=self.F_TIP,
            foreground=BLACK,
        )
        self._tip_lbl.grid(row=0, column=0, sticky="ew")
        ttk.Button(bottom, text="Clear", command=self._clear).grid(
            row=0, column=1, sticky="e"
        )

    # -------------------------------------------------------- Hours tab

    def _build_hours_tab(self) -> None:
        f = self._make_lockable_tab("Hours")

        # Mode selector
        mode_frame = ttk.LabelFrame(f, text="Counting mode", padding=self._px(14))
        mode_frame.grid(row=0, column=0, sticky="ew", pady=(0, self._px(16)))

        self.tracking_mode_var = tk.StringVar(value=self.settings.tracking_mode)
        ttk.Radiobutton(
            mode_frame,
            text="Operating hours — count drinks within the current open session",
            variable=self.tracking_mode_var,
            value=settings_mod.TRACKING_HOURS,
            command=self._on_tracking_mode_changed,
        ).pack(anchor="w", pady=self._px(4))
        ttk.Radiobutton(
            mode_frame,
            text="Rolling window — count drinks scanned in the last N hours",
            variable=self.tracking_mode_var,
            value=settings_mod.TRACKING_ROLLING,
            command=self._on_tracking_mode_changed,
        ).pack(anchor="w", pady=self._px(4))

        # Hours-mode section
        self.hours_section = ttk.LabelFrame(
            f, text="Operating hours", padding=self._px(14)
        )
        self.hours_section.grid(row=1, column=0, sticky="ew", pady=(0, self._px(16)))
        self.hours_section.columnconfigure(1, weight=1)

        ttk.Label(
            self.hours_section,
            text=(
                "Only scans within the current open window count toward the\n"
                "drink limit. If Close ≤ Open the window crosses midnight\n"
                "(e.g. 20:00 → 02:30). Equal values = 24-hour day boundary."
            ),
            font=self.F_BODY,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, self._px(16)))

        ttk.Label(
            self.hours_section, text="Open  (HH:MM, 24-h):", font=self.F_LABEL
        ).grid(row=1, column=0, sticky="e", padx=(0, self._px(16)), pady=self._px(8))
        self.open_var = tk.StringVar(value=self.settings.open_time)
        ttk.Entry(
            self.hours_section,
            textvariable=self.open_var,
            width=10,
            font=self.F_VALUE_BOLD,
        ).grid(row=1, column=1, sticky="w", pady=self._px(8))

        ttk.Label(
            self.hours_section, text="Close (HH:MM, 24-h):", font=self.F_LABEL
        ).grid(row=2, column=0, sticky="e", padx=(0, self._px(16)), pady=self._px(8))
        self.close_var = tk.StringVar(value=self.settings.close_time)
        ttk.Entry(
            self.hours_section,
            textvariable=self.close_var,
            width=10,
            font=self.F_VALUE_BOLD,
        ).grid(row=2, column=1, sticky="w", pady=self._px(8))

        ttk.Button(
            self.hours_section,
            text="Reset hours to defaults",
            command=self._reset_hours,
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(self._px(20), 0))

        self.open_var.trace_add("write", lambda *_: self._commit_settings())
        self.close_var.trace_add("write", lambda *_: self._commit_settings())

        # Rolling-mode section
        self.rolling_section = ttk.LabelFrame(
            f, text="Rolling window", padding=self._px(14)
        )
        self.rolling_section.grid(row=2, column=0, sticky="ew", pady=(0, self._px(16)))
        self.rolling_section.columnconfigure(1, weight=1)

        ttk.Label(
            self.rolling_section,
            text=(
                "Count each EDIPI's drinks scanned within the last N hours.\n"
                "The window slides continuously — no open/close time applies."
            ),
            font=self.F_BODY,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, self._px(16)))

        ttk.Label(
            self.rolling_section, text="Window length (hours):", font=self.F_LABEL
        ).grid(row=1, column=0, sticky="e", padx=(0, self._px(16)), pady=self._px(8))
        self.rolling_hours_var = tk.IntVar(value=self.settings.rolling_hours)
        ttk.Spinbox(
            self.rolling_section,
            from_=settings_mod.MIN_ROLLING_HOURS,
            to=settings_mod.MAX_ROLLING_HOURS,
            textvariable=self.rolling_hours_var,
            width=6,
            font=self.F_VALUE_BOLD,
        ).grid(row=1, column=1, sticky="w", pady=self._px(8))
        self.rolling_hours_var.trace_add(
            "write", lambda *_: self._commit_settings()
        )

        self._refresh_tracking_mode_visibility()

    def _on_tracking_mode_changed(self) -> None:
        self._refresh_tracking_mode_visibility()
        self._commit_settings()

    def _refresh_tracking_mode_visibility(self) -> None:
        if self.tracking_mode_var.get() == settings_mod.TRACKING_ROLLING:
            self.hours_section.grid_remove()
            self.rolling_section.grid()
        else:
            self.hours_section.grid()
            self.rolling_section.grid_remove()

    def _reset_hours(self) -> None:
        self.open_var.set(settings_mod.DEFAULT_OPEN)
        self.close_var.set(settings_mod.DEFAULT_CLOSE)

    # -------------------------------------------------------- Limits tab

    def _build_limits_tab(self) -> None:
        f = self._make_lockable_tab("Limits")

        ttk.Label(
            f,
            text=(
                "Each EDIPI can be served at most this many drinks in a\n"
                "single operating-hours session. Once the limit is reached,\n"
                "additional scans flash red with the current count."
            ),
            font=self.F_BODY,
            justify="left",
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, self._px(16)))

        ttk.Label(f, text="Max drinks per session:", font=self.F_LABEL).grid(
            row=1, column=0, sticky="e", padx=(0, self._px(16))
        )
        self.max_var = tk.IntVar(value=self.settings.max_drinks)
        ttk.Spinbox(
            f, from_=1, to=99, textvariable=self.max_var, width=6, font=self.F_VALUE_BOLD
        ).grid(row=1, column=1, sticky="w")
        self.max_var.trace_add("write", lambda *_: self._commit_settings())

    # -------------------------------------------------------- Roster tab

    def _build_roster_tab(self) -> None:
        f = self._make_lockable_tab("Roster")
        # Make row 1 (the LabelFrames) and both columns expand to fill
        # the tab so the scrollable canvas inside each block has room.
        f.rowconfigure(1, weight=1)
        f.columnconfigure(0, weight=1)
        f.columnconfigure(1, weight=1)

        ttk.Label(
            f,
            text="Check the categories and branches that are allowed to drink.",
            font=self.F_BODY,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, self._px(12)))

        cat_frame = ttk.LabelFrame(f, text="Categories (PCC)", padding=self._px(14))
        cat_frame.grid(row=1, column=0, sticky="nsew", padx=(0, self._px(16)))
        self.cat_vars = self._build_checkbox_block(
            cat_frame, CATEGORIES, set(self.settings.allowed_categories)
        )

        br_frame = ttk.LabelFrame(f, text="Branches", padding=self._px(14))
        br_frame.grid(row=1, column=1, sticky="nsew")
        self.br_vars = self._build_checkbox_block(
            br_frame, BRANCHES, set(self.settings.allowed_branches)
        )

    def _build_checkbox_block(
        self,
        parent: ttk.LabelFrame,
        table: dict[str, str],
        initially_checked: set[str],
    ) -> dict[str, tk.IntVar]:
        # Layout: row 0 = All/None buttons (full width), row 1 = scrolling
        # canvas + scrollbar holding the actual checkboxes. Without the
        # canvas the 24 categories overflow the window when not in
        # fullscreen.
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)

        btns = ttk.Frame(parent)
        btns.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, self._px(8)))
        vars_: dict[str, tk.IntVar] = {}

        def set_all(v: int) -> None:
            for var in vars_.values():
                var.set(v)

        ttk.Button(btns, text="All", width=6, command=lambda: set_all(1)).pack(side="left")
        ttk.Button(btns, text="None", width=6, command=lambda: set_all(0)).pack(
            side="left", padx=(self._px(8), 0)
        )

        # Match the canvas background to the surrounding ttk theme so it
        # blends with the LabelFrame instead of showing a stark rectangle.
        try:
            theme_bg = ttk.Style(self).lookup("TLabelframe", "background") or ""
        except tk.TclError:
            theme_bg = ""
        canvas_kwargs: dict = {"highlightthickness": 0, "borderwidth": 0}
        if theme_bg:
            canvas_kwargs["bg"] = theme_bg
        canvas = tk.Canvas(parent, **canvas_kwargs)
        canvas.grid(row=1, column=0, sticky="nsew")

        sb = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        sb.grid(row=1, column=1, sticky="ns")
        canvas.configure(yscrollcommand=sb.set)

        inner = ttk.Frame(canvas)
        inner_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        # Inner frame width tracks the canvas viewport so checkbutton hit
        # areas span the column even though the text is short.
        def _resize_inner_to_canvas(event: tk.Event) -> None:
            canvas.itemconfigure(inner_id, width=event.width)
        canvas.bind("<Configure>", _resize_inner_to_canvas)

        # Update scrollregion whenever the inner frame's natural size
        # changes (e.g. font/theme change at runtime).
        def _update_scrollregion(_event: tk.Event) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner.bind("<Configure>", _update_scrollregion)

        # Mouse wheel: Linux uses Button-4/5, macOS/Windows use MouseWheel.
        # Bind on the canvas, the inner frame, AND each checkbox so the
        # wheel scrolls regardless of which child has the cursor.
        def _on_mousewheel(event: tk.Event) -> str:
            if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
                canvas.yview_scroll(-3, "units")
            elif getattr(event, "num", None) == 5 or getattr(event, "delta", 0) < 0:
                canvas.yview_scroll(3, "units")
            return "break"

        for w in (canvas, inner):
            w.bind("<MouseWheel>", _on_mousewheel)
            w.bind("<Button-4>", _on_mousewheel)
            w.bind("<Button-5>", _on_mousewheel)

        for i, (code, desc) in enumerate(table.items()):
            v = tk.IntVar(value=1 if code in initially_checked else 0)
            vars_[code] = v
            short = desc if len(desc) <= 46 else desc[:43] + "…"
            cb = ttk.Checkbutton(inner, variable=v, text=f"{code} — {short}")
            cb.grid(row=i, column=0, sticky="w", pady=self._px(2))
            cb.bind("<MouseWheel>", _on_mousewheel)
            cb.bind("<Button-4>", _on_mousewheel)
            cb.bind("<Button-5>", _on_mousewheel)
            v.trace_add("write", lambda *_: self._commit_settings())
        return vars_

    # -------------------------------------------------------- Banned tab

    def _build_banned_tab(self) -> None:
        f = self._make_lockable_tab("Banned")
        f.rowconfigure(1, weight=1)

        ttk.Label(
            f,
            text=(
                "DoD IDs on this list are denied regardless of any other\n"
                "rule. Bans are permanent by default. To make a ban expire,\n"
                "fill in the Expires field as YYYYMMDD (8 digits)."
            ),
            font=self.F_BODY,
            justify="left",
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, self._px(12)))

        self._bans: list[settings_mod.Ban] = list(self.settings.bans)

        self.banned_listbox = tk.Listbox(
            f,
            height=10,
            width=46,
            font=self.F_LIST_BIG,
            activestyle="none",
        )
        self.banned_listbox.grid(row=1, column=0, columnspan=3, sticky="nsew")
        sb = ttk.Scrollbar(f, orient="vertical", command=self.banned_listbox.yview)
        sb.grid(row=1, column=3, sticky="ns")
        self.banned_listbox.configure(yscrollcommand=sb.set)
        self._refresh_banned_listbox()

        ttk.Label(f, text="EDIPI (10 digits):", font=self.F_LABEL).grid(
            row=2, column=0, sticky="w", pady=(self._px(14), self._px(2))
        )
        self.ban_edipi_var = tk.StringVar()
        edipi_entry = ttk.Entry(
            f, textvariable=self.ban_edipi_var, width=14, font=self.F_VALUE_BOLD
        )
        edipi_entry.grid(row=3, column=0, sticky="w")
        edipi_entry.bind("<Return>", lambda _e: self._add_ban())

        ttk.Label(
            f,
            text="Expires (YYYYMMDD, blank = permanent):",
            font=self.F_LABEL,
        ).grid(
            row=2,
            column=1,
            columnspan=2,
            sticky="w",
            pady=(self._px(14), self._px(2)),
            padx=(self._px(16), 0),
        )
        self.ban_expires_var = tk.StringVar()
        expires_entry = ttk.Entry(
            f, textvariable=self.ban_expires_var, width=14, font=self.F_VALUE_BOLD
        )
        expires_entry.grid(row=3, column=1, sticky="w", padx=(self._px(16), 0))
        expires_entry.bind("<Return>", lambda _e: self._add_ban())

        ttk.Button(f, text="Add", command=self._add_ban).grid(
            row=3, column=2, sticky="w", padx=(self._px(16), 0)
        )
        ttk.Button(f, text="Remove selected", command=self._remove_ban).grid(
            row=4, column=0, columnspan=3, sticky="w", pady=(self._px(12), 0)
        )

    def _refresh_banned_listbox(self) -> None:
        today = date.today()
        self.banned_listbox.delete(0, "end")
        for b in self._bans:
            self.banned_listbox.insert("end", b.describe(today))

    def _add_ban(self) -> None:
        edipi = self.ban_edipi_var.get().strip()
        if not edipi.isdigit() or len(edipi) != 10:
            self._set_status("EDIPI must be exactly 10 digits", ok=False)
            return
        if any(b.edipi == edipi for b in self._bans):
            self._set_status(f"{edipi} is already banned", ok=False)
            return
        expires, err = _parse_expires_input(self.ban_expires_var.get())
        if err:
            self._set_status(err, ok=False)
            return
        self._bans.append(settings_mod.Ban(edipi=edipi, expires=expires))
        self._refresh_banned_listbox()
        self.ban_edipi_var.set("")
        self.ban_expires_var.set("")
        self._commit_settings()

    def _remove_ban(self) -> None:
        sel = self.banned_listbox.curselection()
        if not sel:
            return
        for i in reversed(sel):
            del self._bans[i]
        self._refresh_banned_listbox()
        self._commit_settings()

    # ----------------------------------------------------- settings lock

    def _make_lockable_tab(self, name: str, padding: int | None = None) -> ttk.Frame:
        """Create a settings tab whose content lives inside a lockable frame.

        Each settings tab gets a lock banner at the top and a content frame
        below; the returned frame is the content frame. Callers grid widgets
        into it exactly as they would have into the tab frame before."""
        if padding is None:
            padding = self._px(28)
        tab = ttk.Frame(self.notebook, padding=padding)
        self.notebook.add(tab, text=name)
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        self._add_lock_banner(tab, row=0)

        content = ttk.Frame(tab)
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        self._lockable_content_frames.append(content)
        return content

    def _add_lock_banner(self, parent: tk.Misc, row: int = 0) -> tk.Frame:
        """Insert a lock-status banner at ``row`` of ``parent``.

        The banner is plain Tk so background/foreground colors are honored
        regardless of the ttk theme — important on Linux where ttk themes
        often ignore inline ``foreground=`` arguments."""
        banner = tk.Frame(
            parent, bd=2, relief="solid", padx=self._px(14), pady=self._px(10)
        )
        banner.grid(row=row, column=0, sticky="ew", pady=(0, self._px(12)))
        banner.columnconfigure(0, weight=1)

        lbl = tk.Label(banner, font=self.F_LABEL, anchor="w")
        lbl.grid(row=0, column=0, sticky="w")

        btn = ttk.Button(banner)
        btn.grid(row=0, column=1, sticky="e", padx=(self._px(14), 0))

        self._lock_banners.append((banner, lbl, btn))
        return banner

    def _refresh_lock_banners(self) -> None:
        """Sync every lock banner to the current global lock state."""
        for banner, lbl, btn in self._lock_banners:
            if self._settings_unlocked:
                who = (
                    " + ".join(self._unlock_authorizers)
                    if self._unlock_authorizers
                    else "—"
                )
                banner.configure(bg=UNLOCKED_BG)
                lbl.configure(
                    text=f"UNLOCKED — authorized by {who}",
                    bg=UNLOCKED_BG,
                    fg=GREEN,
                )
                btn.configure(text="Lock", command=self._lock_settings)
            else:
                banner.configure(bg=LOCKED_BG)
                lbl.configure(
                    text="LOCKED — scan 2 CACs to enable editing.",
                    bg=LOCKED_BG,
                    fg=RED,
                )
                btn.configure(text="Unlock", command=self._open_unlock_dialog)

    def _apply_lock_state(self) -> None:
        """Enable or disable every widget in every lockable content frame."""
        enabled = self._settings_unlocked
        for content in self._lockable_content_frames:
            for child in content.winfo_children():
                self._set_subtree_state(child, enabled)
        self._refresh_lock_banners()

    def _set_subtree_state(self, widget: tk.Misc, enabled: bool) -> None:
        """Recursively set the enabled/disabled state on ``widget`` and all
        its descendants. ttk widgets use ``state(['!disabled' / 'disabled'])``;
        classic Tk widgets fall back to ``configure(state=...)``. Widgets
        without any state concept silently no-op."""
        ttk_flag = "!disabled" if enabled else "disabled"
        tk_flag = "normal" if enabled else "disabled"
        configured = False
        if hasattr(widget, "state"):
            try:
                widget.state([ttk_flag])
                configured = True
            except tk.TclError:
                configured = False
        if not configured:
            try:
                widget.configure(state=tk_flag)
            except tk.TclError:
                pass
        for child in widget.winfo_children():
            self._set_subtree_state(child, enabled)

    def _lock_settings(self) -> None:
        # Compute and log any settings changes that happened during this
        # unlock session, then log the lock event itself.
        self._cancel_auto_lock()
        if (
            self._settings_unlocked
            and self._pre_edit_settings is not None
            and self._unlock_authorizers is not None
        ):
            for change in self._diff_settings(
                self._pre_edit_settings, self.settings
            ):
                audit_log.record_change(self._unlock_authorizers, change)
            audit_log.record_lock(self._unlock_authorizers)
        self._settings_unlocked = False
        self._unlock_authorizers = None
        self._pre_edit_settings = None
        self._apply_lock_state()
        self._refresh_logs()
        self._set_status("Settings locked.", ok=True)

    def _schedule_auto_lock(self) -> None:
        """Schedule an automatic lock AUTO_LOCK_MS from now. Cancels any
        existing scheduled lock first so a fresh unlock always gets a
        full 5-minute window."""
        self._cancel_auto_lock()
        self._auto_lock_after_id = self.after(
            self.AUTO_LOCK_MS, self._auto_lock_fired
        )

    def _cancel_auto_lock(self) -> None:
        if self._auto_lock_after_id is not None:
            try:
                self.after_cancel(self._auto_lock_after_id)
            except tk.TclError:
                pass
            self._auto_lock_after_id = None

    def _auto_lock_fired(self) -> None:
        """Called by tk.after when the 5-minute window expires. If the
        user already manually locked, this is a no-op."""
        self._auto_lock_after_id = None
        if not self._settings_unlocked:
            return
        self._lock_settings()
        # Overrides the "Settings locked." message _lock_settings just set.
        self._set_status(
            "Settings auto-locked after 5 minutes of being unlocked.",
            ok=True,
        )

    def _diff_settings(
        self, old: settings_mod.Settings, new: settings_mod.Settings
    ) -> list[str]:
        """Return a list of human-readable change descriptions, one per
        differing field. Empty list if nothing changed."""
        changes: list[str] = []
        for field in (
            "tracking_mode",
            "rolling_hours",
            "open_time",
            "close_time",
            "max_drinks",
        ):
            old_v = getattr(old, field)
            new_v = getattr(new, field)
            if old_v != new_v:
                changes.append(f"{field}: {old_v} → {new_v}")

        for label, attr in (
            ("category", "allowed_categories"),
            ("branch", "allowed_branches"),
        ):
            old_set = set(getattr(old, attr))
            new_set = set(getattr(new, attr))
            added = sorted(new_set - old_set)
            removed = sorted(old_set - new_set)
            if added:
                changes.append(f"{label} enabled: {', '.join(added)}")
            if removed:
                changes.append(f"{label} disabled: {', '.join(removed)}")

        old_bans = {b.edipi: b for b in old.bans}
        new_bans = {b.edipi: b for b in new.bans}
        for e in sorted(new_bans.keys() - old_bans.keys()):
            b = new_bans[e]
            exp = f" until {b.expires}" if b.expires else " (permanent)"
            changes.append(f"ban added: {e}{exp}")
        for e in sorted(old_bans.keys() - new_bans.keys()):
            changes.append(f"ban removed: {e}")
        for e in sorted(old_bans.keys() & new_bans.keys()):
            if old_bans[e].expires != new_bans[e].expires:
                old_exp = old_bans[e].expires or "permanent"
                new_exp = new_bans[e].expires or "permanent"
                changes.append(f"ban {e}: {old_exp} → {new_exp}")
        return changes

    def _on_close(self) -> None:
        """Window-close handler. Flushes any pending audit entries by
        re-locking before destroying so changes don't escape the log
        when the user closes the window directly."""
        if self._settings_unlocked:
            self._lock_settings()
        self.destroy()

    def _open_unlock_dialog(self) -> None:
        """Show a modal Toplevel that requires 2 distinct CAC scans to
        unlock the settings widgets. Reuses the same flow as the reset
        tab's auth, but in a popup so it can be triggered from any tab."""
        if self._settings_unlocked:
            return

        dlg = tk.Toplevel(self)
        dlg.title("Unlock settings")
        dlg.transient(self)
        dlg.resizable(False, False)
        dlg.configure(padx=self._px(24), pady=self._px(24))

        flow = {"step": "first", "first_edipi": None}

        ttk.Label(
            dlg,
            text="Two distinct CACs are required to enable editing.",
            font=self.F_BODY,
        ).grid(row=0, column=0, sticky="w", pady=(0, self._px(10)))

        prompt_var = tk.StringVar(value="Scan first authorizer CAC:")
        ttk.Label(dlg, textvariable=prompt_var, font=self.F_LABEL).grid(
            row=1, column=0, sticky="w", pady=(0, self._px(6))
        )

        input_var = tk.StringVar()
        entry = ttk.Entry(
            dlg, textvariable=input_var, font=self.F_ENTRY, justify="center", width=24
        )
        entry.grid(row=2, column=0, sticky="ew", pady=(0, self._px(8)))

        auth1_var = tk.StringVar(value="")
        ttk.Label(dlg, textvariable=auth1_var, font=self.F_BODY).grid(
            row=3, column=0, sticky="w", pady=(0, self._px(6))
        )

        err_var = tk.StringVar(value="")
        tk.Label(
            dlg, textvariable=err_var, font=self.F_BODY, fg=RED
        ).grid(row=4, column=0, sticky="w", pady=(0, self._px(8)))

        ttk.Button(dlg, text="Cancel", command=dlg.destroy).grid(
            row=5, column=0, sticky="w"
        )

        # The dialog is grab_set'd so keystrokes from the barcode scanner
        # land in this entry rather than in the main window.
        dlg.grab_set()
        entry.focus_set()

        def process(raw: str) -> None:
            input_var.set("")
            try:
                decoded = decode(raw)
            except InvalidBarcode as e:
                err_var.set(f"Invalid scan: {e}")
                entry.focus_set()
                return
            err_var.set("")
            if flow["step"] == "first":
                flow["first_edipi"] = decoded.edipi
                flow["step"] = "second"
                auth1_var.set(f"Authorizer 1: {decoded.edipi}")
                prompt_var.set("Scan second authorizer CAC (must be different):")
                entry.focus_set()
                return
            if decoded.edipi == flow["first_edipi"]:
                err_var.set("Second CAC must be different from the first.")
                entry.focus_set()
                return
            edipi1 = flow["first_edipi"]
            edipi2 = decoded.edipi
            self._settings_unlocked = True
            self._unlock_authorizers = (edipi1, edipi2)
            self._pre_edit_settings = self.settings  # snapshot for diffing
            audit_log.record_unlock(edipi1, edipi2)
            self._apply_lock_state()
            self._refresh_logs()
            self._schedule_auto_lock()
            self._set_status(
                f"Settings unlocked, authorized by {edipi1} + {edipi2}. "
                f"Auto-locks in 5 minutes.",
                ok=True,
            )
            dlg.destroy()

        def on_input_changed(*_: object) -> None:
            text = input_var.get().strip().upper()
            if len(text) >= BARCODE_LEN:
                process(text[-BARCODE_LEN:])

        def on_enter(_event: tk.Event) -> str:
            text = input_var.get().strip().upper()
            if text:
                process(text)
            return "break"

        input_var.trace_add("write", on_input_changed)
        entry.bind("<Return>", on_enter)

    # -------------------------------------------------------- Reset tab

    def _build_reset_tab(self) -> None:
        f = ttk.Frame(self.notebook, padding=self._px(28))
        self.notebook.add(f, text="Reset")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1)

        ttk.Label(
            f,
            text=(
                "Wipe every EDIPI's drink count for the current window.\n"
                "Two distinct CAC scans are required to authorize the reset.\n"
                "Every reset is appended to the public log below and cannot be removed."
            ),
            font=self.F_BODY,
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, self._px(12)))

        # Action area: holds either the start button (idle) or the auth form.
        self.reset_action_frame = ttk.Frame(f)
        self.reset_action_frame.grid(row=1, column=0, sticky="ew", pady=(0, self._px(16)))
        self.reset_action_frame.columnconfigure(0, weight=1)

        self.reset_start_btn = ttk.Button(
            self.reset_action_frame,
            text="Reset drinks for the day",
            command=self._reset_start,
        )
        self.reset_start_btn.grid(row=0, column=0, sticky="w")

        self.reset_form = ttk.LabelFrame(
            self.reset_action_frame, text="Authorize reset", padding=self._px(14)
        )
        self.reset_form.columnconfigure(0, weight=1)

        self.reset_prompt_var = tk.StringVar(value="Scan first authorizer CAC:")
        ttk.Label(
            self.reset_form, textvariable=self.reset_prompt_var, font=self.F_LABEL
        ).grid(row=0, column=0, sticky="w", pady=(0, self._px(6)))

        self.reset_input_var = tk.StringVar()
        self.reset_entry = ttk.Entry(
            self.reset_form,
            textvariable=self.reset_input_var,
            font=self.F_ENTRY,
            justify="center",
        )
        self.reset_entry.grid(row=1, column=0, sticky="ew", pady=(0, self._px(8)))
        self.reset_entry.bind("<Return>", self._on_reset_enter)
        self.reset_input_var.trace_add("write", self._on_reset_input_changed)

        self.reset_authorizers_var = tk.StringVar(value="")
        ttk.Label(
            self.reset_form, textvariable=self.reset_authorizers_var, font=self.F_BODY
        ).grid(row=2, column=0, sticky="w", pady=(0, self._px(6)))

        self.reset_error_var = tk.StringVar(value="")
        ttk.Label(
            self.reset_form,
            textvariable=self.reset_error_var,
            font=self.F_BODY,
            foreground=RED,
        ).grid(row=3, column=0, sticky="w", pady=(0, self._px(8)))

        ttk.Button(
            self.reset_form, text="Cancel", command=self._reset_cancel
        ).grid(row=4, column=0, sticky="w")

        # Public log
        log_frame = ttk.LabelFrame(f, text="Public reset log", padding=self._px(14))
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.reset_log_box = tk.Listbox(
            log_frame,
            height=10,
            font=self.F_LIST_MED,
            activestyle="none",
        )
        self.reset_log_box.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.reset_log_box.yview
        )
        sb.grid(row=0, column=1, sticky="ns")
        self.reset_log_box.configure(yscrollcommand=sb.set)

        self._refresh_reset_log()

    def _refresh_reset_log(self) -> None:
        self.reset_log_box.delete(0, "end")
        entries = reset_log.list_resets()
        if not entries:
            self.reset_log_box.insert("end", "  (no resets recorded)")
            return
        for ts, e1, e2 in entries:
            local = ts.astimezone()
            self.reset_log_box.insert(
                "end", f"  {local:%Y-%m-%d %H:%M}   by {e1}  +  {e2}"
            )

    def _reset_start(self) -> None:
        self._reset_state = "first"
        self._reset_first_edipi = None
        self.reset_prompt_var.set("Scan first authorizer CAC:")
        self.reset_authorizers_var.set("")
        self.reset_error_var.set("")
        self.reset_input_var.set("")
        self.reset_start_btn.grid_remove()
        self.reset_form.grid(row=0, column=0, sticky="ew")
        self.reset_entry.focus_set()

    def _reset_cancel(self) -> None:
        self._reset_state = "idle"
        self._reset_first_edipi = None
        self.reset_input_var.set("")
        self.reset_form.grid_remove()
        self.reset_start_btn.grid(row=0, column=0, sticky="w")

    def _on_reset_input_changed(self, *_: object) -> None:
        if self._reset_state == "idle":
            return
        text = self.reset_input_var.get().strip().upper()
        if len(text) >= BARCODE_LEN:
            self._process_reset_scan(text[-BARCODE_LEN:])

    def _on_reset_enter(self, _event: tk.Event) -> str:
        if self._reset_state == "idle":
            return "break"
        text = self.reset_input_var.get().strip().upper()
        if text:
            self._process_reset_scan(text)
        return "break"

    def _process_reset_scan(self, raw: str) -> None:
        self.reset_input_var.set("")
        try:
            decoded = decode(raw)
        except InvalidBarcode as e:
            self.reset_error_var.set(f"Invalid scan: {e}")
            self.reset_entry.focus_set()
            return
        self.reset_error_var.set("")
        if self._reset_state == "first":
            self._reset_first_edipi = decoded.edipi
            self._reset_state = "second"
            self.reset_authorizers_var.set(f"Authorizer 1: {decoded.edipi}")
            self.reset_prompt_var.set(
                "Scan second authorizer CAC (must be different):"
            )
            self.reset_entry.focus_set()
            return
        if self._reset_state == "second":
            if decoded.edipi == self._reset_first_edipi:
                self.reset_error_var.set(
                    "Second CAC must be different from the first."
                )
                self.reset_entry.focus_set()
                return
            edipi1 = self._reset_first_edipi
            edipi2 = decoded.edipi
            reset_log.record_reset(edipi1, edipi2)
            self._reset_state = "idle"
            self._reset_first_edipi = None
            self.reset_form.grid_remove()
            self.reset_start_btn.grid(row=0, column=0, sticky="w")
            self._refresh_reset_log()
            self._prune_log()              # drop scans before the reset
            self._refresh_session_label()  # update banner / labels
            self._refresh_logs()
            self._set_status(
                f"Drinks reset, authorized by {edipi1} + {edipi2}.", ok=True
            )

    # --------------------------------------------------------- Logs tab

    def _build_logs_tab(self) -> None:
        f = ttk.Frame(self.notebook, padding=self._px(28))
        self.notebook.add(f, text="Logs")
        f.columnconfigure(0, weight=1)
        f.rowconfigure(2, weight=1)

        ttk.Label(
            f,
            text=(
                "Public audit log — every unlock, settings change, and drink reset.\n"
                "Entries are appended automatically; the log cannot be edited or deleted."
            ),
            font=self.F_BODY,
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, self._px(10)))

        ttk.Button(f, text="Refresh", command=self._refresh_logs).grid(
            row=1, column=0, sticky="w", pady=(0, self._px(10))
        )

        log_frame = ttk.Frame(f)
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.logs_box = tk.Listbox(
            log_frame, font=self.F_LIST_SMALL, activestyle="none"
        )
        self.logs_box.grid(row=0, column=0, sticky="nsew")
        sb = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.logs_box.yview
        )
        sb.grid(row=0, column=1, sticky="ns")
        self.logs_box.configure(yscrollcommand=sb.set)

        self._refresh_logs()

    def _refresh_logs(self) -> None:
        """Reload the Logs listbox by merging audit + reset records."""
        if not hasattr(self, "logs_box"):
            return
        self.logs_box.delete(0, "end")
        entries: list[tuple[datetime, dict]] = []
        for rec in audit_log.iter_records():
            try:
                ts = datetime.fromisoformat(rec["ts"])
                entries.append((ts, rec))
            except (KeyError, ValueError):
                continue
        for ts, e1, e2 in reset_log.list_resets():
            entries.append((ts, {"action": "reset", "authorizers": [e1, e2]}))
        entries.sort(key=lambda x: x[0], reverse=True)

        if not entries:
            self.logs_box.insert("end", "  (no log entries yet)")
            return

        for ts, rec in entries:
            local = ts.astimezone()
            action = str(rec.get("action", "?")).upper()
            auths = rec.get("authorizers")
            auths_str = " + ".join(auths) if auths else "—"
            when = f"{local:%Y-%m-%d %H:%M}"
            if action == "CHANGE":
                change = rec.get("change", "")
                line = f"  {when}  {action:<7}  {change}   (by {auths_str})"
            elif action == "LOCK" and not auths:
                line = f"  {when}  {action:<7}"
            else:
                line = f"  {when}  {action:<7}  by {auths_str}"
            self.logs_box.insert("end", line)

    # ------------------------------------------------------- Backup tab

    def _build_backup_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=self._px(28))
        self.notebook.add(tab, text="Backup")
        tab.columnconfigure(0, weight=1)

        ttk.Label(
            tab,
            text=(
                "Settings, ban list, and all logs live in:\n"
                f"    {settings_mod.SETTINGS_DIR}\n"
                "This folder is shared across every user on this PC, so all\n"
                "operators see the same configuration and scan history.\n"
                "Updating BarScanner does NOT touch this folder, so your\n"
                "configuration is preserved automatically across upgrades.\n"
                "Use the buttons below to back up or migrate to another machine."
            ),
            font=self.F_BODY,
            justify="left",
        ).grid(row=0, column=0, sticky="ew", pady=(0, self._px(18)))

        # Export — always available, no unlock required.
        export_frame = ttk.LabelFrame(tab, text="Export", padding=self._px(14))
        export_frame.grid(row=1, column=0, sticky="ew", pady=(0, self._px(18)))
        export_frame.columnconfigure(0, weight=1)
        ttk.Label(
            export_frame,
            text=(
                "Save a full backup (settings + scan/audit/reset logs) as a\n"
                "single .zip file. The exported file contains EDIPIs and\n"
                "the ban list — protect it accordingly."
            ),
            font=self.F_BODY,
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, self._px(10)))
        ttk.Button(
            export_frame,
            text="Export full backup…",
            command=self._on_export_backup,
        ).grid(row=1, column=0, sticky="w")

        # Import — gated by the same 2-CAC unlock as other settings tabs.
        # Add a lock banner at row 2 and put the import controls in a
        # content frame registered with _lockable_content_frames so the
        # existing _apply_lock_state machinery enables/disables them.
        self._add_lock_banner(tab, row=2)

        import_content = ttk.Frame(tab)
        import_content.grid(row=3, column=0, sticky="nsew")
        import_content.columnconfigure(0, weight=1)
        self._lockable_content_frames.append(import_content)

        import_frame = ttk.LabelFrame(
            import_content, text="Import", padding=self._px(14)
        )
        import_frame.grid(row=0, column=0, sticky="ew")
        import_frame.columnconfigure(0, weight=1)
        ttk.Label(
            import_frame,
            text=(
                "Replace ALL settings and logs on this machine with the\n"
                "contents of a backup .zip. The current data is overwritten\n"
                "and cannot be recovered without a backup of its own."
            ),
            font=self.F_BODY,
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, self._px(10)))
        ttk.Button(
            import_frame,
            text="Import full backup…",
            command=self._on_import_backup,
        ).grid(row=1, column=0, sticky="w")

    def _on_export_backup(self) -> None:
        default_name = f"cac_scanner_backup_{date.today():%Y-%m-%d}.zip"
        dest = filedialog.asksaveasfilename(
            parent=self,
            title="Export backup",
            defaultextension=".zip",
            filetypes=[("ZIP archive", "*.zip"), ("All files", "*.*")],
            initialfile=default_name,
        )
        if not dest:
            return
        try:
            backup.export_backup(Path(dest))
        except (OSError, backup.BackupError) as e:
            self._set_status(f"Export failed: {e}", ok=False)
            return
        audit_log.record_export(Path(dest).name)
        self._refresh_logs()
        self._set_status(f"Exported to {dest}", ok=True)

    def _on_import_backup(self) -> None:
        if not self._settings_unlocked or not self._unlock_authorizers:
            # Button is disabled in this state, but be defensive.
            self._set_status("Settings must be unlocked to import.", ok=False)
            return
        src = filedialog.askopenfilename(
            parent=self,
            title="Import backup",
            filetypes=[("ZIP archive", "*.zip"), ("All files", "*.*")],
        )
        if not src:
            return
        if not messagebox.askyesno(
            "Confirm import",
            (
                f"Replace ALL current settings and logs with the contents of:\n\n"
                f"{src}\n\n"
                "This cannot be undone. Continue?"
            ),
            parent=self,
        ):
            return
        try:
            new_settings = backup.import_backup(
                Path(src), self._unlock_authorizers
            )
        except (OSError, backup.BackupError) as e:
            self._set_status(f"Import failed: {e}", ok=False)
            return
        # Adopt the imported state in memory and refresh every view that
        # reads from settings or the logs.
        self.settings = new_settings
        self._reload_widgets_from_settings()
        self._refresh_logs()
        self._refresh_reset_log()
        self._refresh_session_label()
        self._prune_log()
        # Reset the diff baseline so locking after an import doesn't log
        # the entire imported state as a manual change.
        self._pre_edit_settings = new_settings
        self._set_status(f"Imported {Path(src).name}", ok=True)

    def _reload_widgets_from_settings(self) -> None:
        """Push self.settings into every bound StringVar/IntVar widget so
        the Hours/Limits/Roster/Banned tabs reflect the in-memory value
        after an import. Gated by self._building so the trace_add hooks
        don't fire and re-save during the refresh."""
        self._building = True
        try:
            self.tracking_mode_var.set(self.settings.tracking_mode)
            self.open_var.set(self.settings.open_time)
            self.close_var.set(self.settings.close_time)
            self.max_var.set(self.settings.max_drinks)
            self.rolling_hours_var.set(self.settings.rolling_hours)
            for code, var in self.cat_vars.items():
                var.set(1 if code in self.settings.allowed_categories else 0)
            for code, var in self.br_vars.items():
                var.set(1 if code in self.settings.allowed_branches else 0)
            self._bans = list(self.settings.bans)
            self._refresh_banned_listbox()
            self._refresh_tracking_mode_visibility()
        finally:
            self._building = False

    # --------------------------------------------------------- auto-save

    def _build_settings_from_widgets(self) -> settings_mod.Settings | None:
        try:
            settings_mod.parse_hhmm(self.open_var.get())
            settings_mod.parse_hhmm(self.close_var.get())
        except ValueError as e:
            self._set_status(f"Invalid time: {e}", ok=False)
            return None
        try:
            m = int(self.max_var.get())
            if m < 1:
                raise ValueError
        except (tk.TclError, ValueError):
            self._set_status("Max drinks must be a positive integer", ok=False)
            return None
        try:
            rolling = int(self.rolling_hours_var.get())
            if not (
                settings_mod.MIN_ROLLING_HOURS
                <= rolling
                <= settings_mod.MAX_ROLLING_HOURS
            ):
                raise ValueError
        except (tk.TclError, ValueError):
            self._set_status(
                f"Rolling hours must be between {settings_mod.MIN_ROLLING_HOURS} "
                f"and {settings_mod.MAX_ROLLING_HOURS}",
                ok=False,
            )
            return None
        tracking_mode = self.tracking_mode_var.get()
        if tracking_mode not in settings_mod.TRACKING_MODES:
            tracking_mode = settings_mod.DEFAULT_TRACKING_MODE
        return settings_mod.Settings(
            open_time=self.open_var.get().strip(),
            close_time=self.close_var.get().strip(),
            max_drinks=m,
            allowed_categories=tuple(c for c, v in self.cat_vars.items() if v.get()),
            allowed_branches=tuple(b for b, v in self.br_vars.items() if v.get()),
            bans=tuple(self._bans),
            tracking_mode=tracking_mode,
            rolling_hours=rolling,
        )

    def _commit_settings(self) -> None:
        if self._building or self._committing:
            return
        if not self._settings_unlocked:
            return
        new = self._build_settings_from_widgets()
        if new is None:
            return
        self._committing = True
        try:
            settings_mod.save(new)
            self.settings = new
            self._refresh_session_label()
            # Hours may have changed — re-trim the log to the new window.
            self._prune_log()
            self._set_status("Saved.", ok=True)
        finally:
            self._committing = False

    def _set_status(self, text: str, ok: bool) -> None:
        self.status_lbl.configure(foreground=GREEN if ok else RED)
        self.status_var.set(text)
        if ok and text:
            self.after(1800, lambda: self.status_var.set(""))

    # --------------------------------------------------------- events

    def _on_tab_changed(self, _event: tk.Event) -> None:
        # If the user switched back to the Scanner tab, return focus to the
        # entry so the scanner-keyboard input goes there.
        try:
            current = self.notebook.tab(self.notebook.select(), "text")
        except tk.TclError:
            return
        if current == "Scanner":
            self.entry.focus_set()
        elif current == "Reset" and self._reset_state != "idle":
            self.reset_entry.focus_set()
        elif current == "Logs":
            self._refresh_logs()

    def _on_input_changed(self, *_: object) -> None:
        if self._processing:
            return
        text = self.input_var.get().strip().upper()
        if len(text) >= BARCODE_LEN:
            self._process(text[-BARCODE_LEN:])

    def _on_enter(self, _event: tk.Event) -> str:
        if not self._processing:
            text = self.input_var.get().strip().upper()
            if text:
                self._process(text)
        return "break"

    def _tick(self) -> None:
        self._refresh_session_label()
        self._prune_log()
        self.after(self.REFRESH_MS, self._tick)

    def _prune_log(self) -> None:
        """Trim the scan log to the minimum retention window: anything older
        than the counting window's start (or 'now', if the bar is closed),
        further advanced by the most recent reset boundary."""
        now = datetime.now().astimezone()
        window = self.settings.current_window(now)
        cutoff = self._effective_since(window[0]) if window else now
        prune_before(cutoff)

    def _effective_since(self, window_start: datetime) -> datetime:
        """The actual lower bound for counting: the later of the window
        start and the most recent reset timestamp."""
        last = reset_log.latest_reset()
        if last is not None and last > window_start:
            return last
        return window_start

    # --------------------------------------------------------- pipeline

    def _process(self, raw: str) -> None:
        self._processing = True
        try:
            self.input_var.set("")
            try:
                decoded = decode(raw)
            except InvalidBarcode as e:
                self._show_invalid(str(e), raw)
                return

            now = datetime.now().astimezone()
            window = self.settings.current_window(now)
            in_window = window is not None
            effective_since = self._effective_since(window[0]) if in_window else None
            current_count = (
                count_since(decoded.edipi, effective_since, now)
                if effective_since is not None
                else 0
            )

            verdict = settings_mod.check_eligibility(
                edipi=decoded.edipi,
                category_code=decoded.category_code,
                category_name=decoded.category,
                branch_code=decoded.branch_code,
                branch_name=decoded.branch,
                current_count=current_count,
                settings=self.settings,
                in_session=in_window,
            )

            self._values["edipi"].set(decoded.edipi)
            self._values["category"].set(
                f"{decoded.category_code} — {decoded.category}"
            )
            self._values["branch"].set(
                f"{decoded.branch_code} — {decoded.branch}"
            )
            self._last_decoded_edipi = decoded.edipi

            if verdict.allowed:
                record_scan(decoded.edipi)
                # Discard anything from before the effective window start so
                # the log never carries more than the current counting window.
                prune_before(effective_since)  # type: ignore[arg-type]
                shown_count = verdict.new_count
                self._values["count"].set(f"{shown_count} / {self.settings.max_drinks}")
                self._set_banner(
                    GREEN,
                    f"ALLOWED — {settings_mod.ordinal(shown_count)} drink",
                    f"{decoded.category} • {decoded.branch}",
                )
            else:
                self._values["count"].set(
                    f"{current_count} / {self.settings.max_drinks}"
                )
                self._set_banner(RED, "DENIED", verdict.reason)
        finally:
            self._processing = False
            self.entry.focus_set()

    def _show_invalid(self, msg: str, raw: str) -> None:
        for var in self._values.values():
            var.set(self.PLACEHOLDER)
        self._last_decoded_edipi = None
        self._set_banner(RED, "INVALID SCAN", f"{raw!r}: {msg}")

    def _set_banner(self, color: str, headline: str, detail: str) -> None:
        self.banner.configure(bg=color)
        self.banner_lbl.configure(bg=color, fg=WHITE, text=headline)
        self.banner_detail.configure(bg=color, fg=WHITE, text=detail)

    def _reset_banner(self) -> None:
        self.banner.configure(bg=WHITE)
        self.banner_lbl.configure(bg=WHITE, fg=BLACK, text="Ready to scan")
        self.banner_detail.configure(bg=WHITE, fg=BLACK, text="")

    def _refresh_session_label(self) -> None:
        now = datetime.now().astimezone()
        window = self.settings.current_window(now)

        # Keep the per-scan count row label aligned with the mode.
        if self._count_label is not None:
            if self.settings.is_rolling:
                self._count_label.configure(
                    text=f"Drinks (last {self.settings.rolling_hours}h):"
                )
            else:
                self._count_label.configure(text="Drinks this session:")

        descr = self.settings.describe_window()
        if window is None:
            self.session_lbl.configure(foreground=RED)
            self.session_var.set(f"Hours: {descr}  •  CLOSED right now")
            return

        start, end = window
        effective = self._effective_since(start)
        local_reset = effective.astimezone() if effective > start else None
        self.session_lbl.configure(foreground=GREEN)
        if self.settings.is_rolling:
            text = f"{descr}  •  counting since {start:%a %H:%M}"
        else:
            text = (
                f"Hours: {self.settings.describe_hours()}  •  "
                f"Session: {start:%a %H:%M} → {end:%a %H:%M}"
            )
        if local_reset is not None:
            text += f"  •  reset at {local_reset:%a %H:%M}"
        self.session_var.set(text)

    def _clear(self) -> None:
        self._processing = True
        try:
            self.input_var.set("")
        finally:
            self._processing = False
        for var in self._values.values():
            var.set(self.PLACEHOLDER)
        self._last_decoded_edipi = None
        self._reset_banner()
        self.entry.focus_set()

    # ---------------------------------------------------- Machine install

    def _maybe_offer_start_menu_install(self) -> None:
        """Show the first-run install dialog at most once.

        Skipped on non-Windows, when running from source (not a frozen
        exe), when the prompt has already been shown, or when the
        all-users Start menu shortcut already exists (a sign that
        somebody already installed)."""
        if sys.platform != "win32":
            return
        if not getattr(sys, "frozen", False):
            return
        if self.settings.start_menu_prompt_shown:
            return
        if start_menu.shortcut_exists():
            self._record_start_menu_decision()
            return
        self._open_install_dialog()

    def _record_start_menu_decision(self) -> None:
        """Persist that we've prompted, so we never ask again."""
        new = replace(self.settings, start_menu_prompt_shown=True)
        try:
            settings_mod.save(new)
        except OSError:
            # If we can't persist, the worst case is we ask again next
            # launch — not worth crashing the GUI over.
            pass
        self.settings = new

    def _open_install_dialog(self) -> None:
        dlg = tk.Toplevel(self)
        dlg.title("Install for this PC?")
        dlg.transient(self)
        dlg.resizable(False, False)
        dlg.configure(padx=self._px(24), pady=self._px(24))

        ttk.Label(
            dlg,
            text="Install CAC Bar Scanner for this PC?",
            font=self.F_LABEL,
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, self._px(6)))

        ttk.Label(
            dlg,
            text=(
                "This sets up a shared folder so every operator on the\n"
                "computer sees the same configuration and scan history,\n"
                "and adds CAC Bar Scanner to the Start menu for everyone."
            ),
            font=self.F_BODY,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, self._px(16)))

        def finish(message: str, ok: bool) -> None:
            self._record_start_menu_decision()
            self._set_status(message, ok=ok)
            dlg.destroy()

        def on_install() -> None:
            # Withdraw while UAC is up so the dialog isn't stuck behind it.
            dlg.withdraw()
            res = start_menu.install_for_machine()
            if res == start_menu.InstallResult.OK:
                finish("Installed for everyone on this PC.", True)
            elif res == start_menu.InstallResult.CANCELLED:
                finish("Cancelled — no changes were made.", False)
            else:
                finish(
                    "Install failed. Try right-clicking BarScanner.exe "
                    "and choosing \"Run as administrator\".",
                    False,
                )

        def on_skip() -> None:
            finish(
                "Skipped. Run BarScanner.exe as administrator later to "
                "finish setup.",
                True,
            )

        btns = ttk.Frame(dlg)
        btns.grid(row=2, column=0, columnspan=2, sticky="ew")
        btns.columnconfigure(0, weight=1)
        btns.columnconfigure(1, weight=1)
        ttk.Button(btns, text="Install", command=on_install).grid(
            row=0, column=0, sticky="ew", padx=(0, self._px(8))
        )
        ttk.Button(btns, text="Not now", command=on_skip).grid(
            row=0, column=1, sticky="ew"
        )

        ttk.Label(
            dlg,
            text=(
                "Windows will pop up a blue \"User Account Control\" "
                "permission box — click Yes when it appears."
            ),
            font=self.F_TIP,
            justify="left",
            foreground="#555555",
            wraplength=self._px(520),
        ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(self._px(14), 0))

        # Modal: grab keystrokes (the barcode scanner is just a keyboard
        # from Tk's perspective) so a stray scan doesn't fire the wrong
        # button. Also close on Escape so a quick keyboard user can bail.
        dlg.protocol("WM_DELETE_WINDOW", on_skip)
        dlg.bind("<Escape>", lambda _e: on_skip())
        dlg.grab_set()
        # Center over the parent window.
        self.update_idletasks()
        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dlg.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dlg.winfo_height()) // 3
        dlg.geometry(f"+{max(x, 0)}+{max(y, 0)}")


def main() -> None:
    # Windows runs the registered UninstallString (BarScanner.exe --uninstall)
    # when the user picks Uninstall from the Start menu / Add-Remove Programs.
    # Handle that branch before we try to bring the GUI up.
    if start_menu.handle_uninstall_cli():
        return
    # Elevated child writing the install (ACL + shortcut + registry).
    if start_menu.handle_elevated_install_cli():
        return
    _enable_windows_dpi_awareness()
    App().mainloop()


if __name__ == "__main__":
    main()
