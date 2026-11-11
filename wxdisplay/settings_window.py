"""The settings window (Tkinter, which comes with Python).

Runs as its own program (python weather.py --settings) so it never appears in the
picture being displayed or streamed. Saving writes config.toml; a running display
notices the change and restarts itself with the new settings.
"""

from __future__ import annotations

import copy
import queue
import re
import sys
import threading
from pathlib import Path

from . import geo
from .config import ALL_SLIDES, RESOLUTIONS, ROOT, Config, load_config, save_config

try:
    import tkinter as tk
    from tkinter import colorchooser, filedialog, messagebox, ttk
except ImportError:  # pragma: no cover - depends on how Python was installed
    tk = None

SLIDE_NAMES = {
    "bulletins": "Weather Bulletins (only shown when there's an alert)",
    "current": "Current Conditions",
    "local_obs": "Local Observations",
    "forecast_36": "The 36 Hour Forecast",
    "extended": "The Extended Forecast",
    "almanac": "Almanac",
    "radar": "Doppler Radar",
}
STATION_RE = re.compile(r"^[A-Z0-9]{3,5}$")
ZONE_RE = re.compile(r"^[A-Z]{2}[CZ]\d{3}$")
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
PAD = 8


class SettingsWindow:
    def __init__(self, root: "tk.Tk", cfg: Config, save_path: Path, from_display: bool):
        self.root, self.cfg, self.save_path, self.from_display = root, cfg, save_path, from_display
        self.jobs: queue.Queue = queue.Queue()
        root.title("Weather Display Settings")
        root.minsize(720, 600)

        outer = ttk.Frame(root, padding=PAD)
        outer.pack(fill="both", expand=True)
        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill="both", expand=True)
        self._location_tab()
        self._display_tab()
        self._slides_tab()
        self._observations_tab()
        self._radar_tab()
        self._alerts_tab()

        bar = ttk.Frame(outer, padding=(0, PAD, 0, 0))
        bar.pack(fill="x")
        self.status = ttk.Label(bar, text="", foreground="#1a5e20")
        self.status.pack(side="left", fill="x", expand=True)
        ttk.Button(bar, text="Close", command=self.close).pack(side="right")
        ttk.Button(bar, text="Save", command=self.save, default="active").pack(side="right", padx=(0, PAD))
        root.bind("<Control-s>", lambda e: self.save())
        root.protocol("WM_DELETE_WINDOW", self.close)

        self.saved_state = self._raw_state()
        root.after(100, self._poll_jobs)

    # ------------------------------------------------------------ helpers

    def _tab(self, title: str) -> "ttk.Frame":
        frame = ttk.Frame(self.tabs, padding=PAD * 2)
        frame.columnconfigure(1, weight=1)
        self.tabs.add(frame, text=title)
        return frame

    def _row(self, parent, row: int, label: str, widget, hint: str = "") -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="nw", padx=(0, PAD * 2), pady=(PAD, 0))
        widget.grid(row=row, column=1, sticky="w", pady=(PAD, 0))
        if hint:
            ttk.Label(parent, text=hint, foreground="#666666", wraplength=520, justify="left").grid(
                row=row + 1, column=1, sticky="w")

    def _spin(self, parent, var, lo, hi, step=1, width=7):
        return ttk.Spinbox(parent, textvariable=var, from_=lo, to=hi, increment=step, width=width)

    def _color_picker(self, parent, var):
        frame = ttk.Frame(parent)
        swatch = tk.Label(frame, width=4, relief="solid", borderwidth=1)
        swatch.pack(side="left")
        ttk.Entry(frame, textvariable=var, width=10).pack(side="left", padx=PAD)

        def refresh(*_):
            if COLOR_RE.match(var.get().strip()):
                swatch.configure(background=var.get().strip())
        var.trace_add("write", refresh)
        refresh()

        def choose():
            rgb, hexval = colorchooser.askcolor(color=var.get() if COLOR_RE.match(var.get()) else None,
                                               parent=self.root, title="Choose a color")
            if hexval:
                var.set(hexval.upper())
        ttk.Button(frame, text="Choose…", command=choose).pack(side="left")
        return frame

    def _run_in_background(self, work, done) -> None:
        """Run work() on a thread; call done(result_or_exception) back on the Tk thread."""
        def target():
            try:
                result = work()
            except Exception as e:  # shown to the user, not raised
                result = e
            self.jobs.put((done, result))
        threading.Thread(target=target, daemon=True).start()

    def _poll_jobs(self) -> None:
        while not self.jobs.empty():
            done, result = self.jobs.get()
            done(result)
        self.root.after(100, self._poll_jobs)

    def _set_status(self, text: str, error: bool = False) -> None:
        self.status.configure(text=text, foreground="#b00020" if error else "#1a5e20")

    # --------------------------------------------------------------- tabs

    def _location_tab(self) -> None:
        f = self._tab("Location")
        c = self.cfg
        self.place = tk.StringVar(value=c.location.place)
        self.name = tk.StringVar(value=c.location.name)
        self.contact = tk.StringVar(value=c.nws.contact)
        self._row(f, 0, "Location", ttk.Entry(f, textvariable=self.place, width=40),
                  'A ZIP code, "City, ST", or "latitude, longitude". Anywhere in the US.')
        check = ttk.Frame(f)
        self.check_btn = ttk.Button(check, text="Check location", command=self.check_location)
        self.check_btn.pack(side="left")
        ttk.Label(check, text="Looks up the forecast office, radar and nearby cities.",
                  foreground="#666666").pack(side="left", padx=PAD)
        check.grid(row=2, column=1, sticky="w", pady=(PAD, 0))
        self.check_result = ttk.Label(f, text="", wraplength=540, justify="left")
        self.check_result.grid(row=3, column=1, sticky="w", pady=(PAD, 0))
        self._row(f, 4, "Name on screen", ttk.Entry(f, textvariable=self.name, width=30),
                  "Leave blank to use the name the National Weather Service gives the location.")
        self._row(f, 6, "Your contact", ttk.Entry(f, textvariable=self.contact, width=40),
                  "Email address or website. The National Weather Service asks every app to include "
                  "a way to reach the person running it. It's only sent to the NWS.")

    def _display_tab(self) -> None:
        f = self._tab("Display")
        d = self.cfg.display
        self.resolution = tk.StringVar(value=d.resolution)
        self.fullscreen = tk.BooleanVar(value=d.fullscreen)
        self.borderless = tk.BooleanVar(value=d.borderless)
        self.clock_24h = tk.BooleanVar(value=d.clock_24h)
        self.frosted = tk.BooleanVar(value=d.frosted)
        self.fps = tk.StringVar(value=str(d.fps))
        self.slide_seconds = tk.StringVar(value=_num(d.slide_seconds))
        self.ticker_seconds = tk.StringVar(value=_num(d.ticker_seconds))
        self.backgrounds = tk.StringVar(value=d.backgrounds)
        self.background_seconds = tk.StringVar(value=_num(d.background_seconds))
        self.panel_color = tk.StringVar(value=d.panel_color)
        self.text_color = tk.StringVar(value=d.text_color)
        self.opacity = tk.DoubleVar(value=round(d.panel_opacity * 100))

        self._row(f, 0, "Resolution", ttk.Combobox(f, textvariable=self.resolution, width=12,
                                                   values=list(RESOLUTIONS)),
                  'Or type a size like "1600x900".')
        checks = ttk.Frame(f)
        for text, var in (("Full screen", self.fullscreen), ("Window without a title bar", self.borderless),
                          ("24-hour clock", self.clock_24h)):
            ttk.Checkbutton(checks, text=text, variable=var).pack(anchor="w")
        self._row(f, 2, "Window", checks)
        self._row(f, 3, "Frames per second", self._spin(f, self.fps, 10, 60, 5),
                  "30 is smooth; 60 is smoother but uses more of the computer.")
        self._row(f, 5, "Seconds per slide", self._spin(f, self.slide_seconds, 3, 120))
        self._row(f, 6, "Seconds per ticker line", self._spin(f, self.ticker_seconds, 2, 30),
                  "How long each line of current conditions stays in the bottom bar.")

        bgf = ttk.Frame(f)
        ttk.Entry(bgf, textvariable=self.backgrounds, width=34).pack(side="left")
        ttk.Button(bgf, text="Browse…", command=self.browse_backgrounds).pack(side="left", padx=PAD)
        self._row(f, 8, "Background photos", bgf, "A folder of .jpg or .png pictures.")
        self._row(f, 10, "Change photo every", self._spin(f, self.background_seconds, 0, 3600, 30),
                  "Seconds. 0 = change after each full cycle of slides.")
        self._row(f, 12, "Panels", ttk.Checkbutton(f, text="Frosted glass (blur the photo behind panels)",
                                                    variable=self.frosted))
        self._row(f, 13, "Panel color", self._color_picker(f, self.panel_color))
        op = ttk.Frame(f)
        label = ttk.Label(op, width=5)
        ttk.Scale(op, from_=0, to=100, variable=self.opacity, length=220,
                  command=lambda v: label.configure(text=f"{round(float(v))}%")).pack(side="left")
        label.configure(text=f"{round(self.opacity.get())}%")
        label.pack(side="left", padx=PAD)
        self._row(f, 14, "Panel opacity", op)
        self._row(f, 15, "Text color", self._color_picker(f, self.text_color))

    def _slides_tab(self) -> None:
        f = self._tab("Slides")
        ttk.Label(f, text="Which slides to show, in order. Double-click a slide to show or hide it.",
                  wraplength=600).grid(row=0, column=0, columnspan=2, sticky="w")
        enabled = [s for s in self.cfg.display.slides if s in ALL_SLIDES]
        self.slide_order = [(s, True) for s in enabled] + [(s, False) for s in ALL_SLIDES if s not in enabled]
        self.slide_list = ttk.Treeview(f, columns=("name", "shown"), show="headings", selectmode="browse",
                                       height=len(ALL_SLIDES))
        self.slide_list.heading("name", text="Slide")
        self.slide_list.heading("shown", text="Shown")
        self.slide_list.column("name", width=380)
        self.slide_list.column("shown", width=70, anchor="center")
        self.slide_list.tag_configure("hidden", foreground="#888888")
        self.slide_list.grid(row=1, column=0, sticky="nw", pady=PAD)
        self.slide_list.bind("<Double-Button-1>", lambda e: self.toggle_slide())
        buttons = ttk.Frame(f)
        buttons.grid(row=1, column=1, sticky="nw", padx=PAD, pady=PAD)
        ttk.Button(buttons, text="Show / hide", command=self.toggle_slide).pack(fill="x")
        ttk.Button(buttons, text="Move up", command=lambda: self.move_slide(-1)).pack(fill="x", pady=(PAD, 0))
        ttk.Button(buttons, text="Move down", command=lambda: self.move_slide(1)).pack(fill="x", pady=(PAD, 0))
        self._refresh_slides()

    def _observations_tab(self) -> None:
        f = self._tab("Observations")
        o = self.cfg.observations
        self.primary = tk.StringVar(value=o.primary)
        self.obs_mode = tk.StringVar(value="custom" if o.stations else "auto")
        self.obs_count = tk.StringVar(value=str(o.count))
        self.obs_radius = tk.StringVar(value=_num(o.radius_miles))
        self._row(f, 0, "Current Conditions station", ttk.Entry(f, textvariable=self.primary, width=10),
                  "A station ID such as KATL. Leave blank to use the nearest station.")
        ttk.Separator(f).grid(row=2, column=0, columnspan=2, sticky="ew", pady=PAD * 2)
        ttk.Label(f, text="Local Observations cities").grid(row=3, column=0, sticky="nw")
        modes = ttk.Frame(f)
        modes.grid(row=3, column=1, sticky="w")
        ttk.Radiobutton(modes, text="Pick automatically", value="auto", variable=self.obs_mode,
                        command=self._obs_mode_changed).pack(anchor="w")
        auto = ttk.Frame(modes, padding=(24, 4, 0, 4))
        auto.pack(anchor="w")
        ttk.Label(auto, text="How many").pack(side="left")
        self.count_spin = self._spin(auto, self.obs_count, 3, 16, width=4)
        self.count_spin.pack(side="left", padx=(4, 16))
        ttk.Label(auto, text="Within (miles)").pack(side="left")
        self.radius_spin = self._spin(auto, self.obs_radius, 25, 300, 5, width=5)
        self.radius_spin.pack(side="left", padx=4)
        ttk.Radiobutton(modes, text="Choose my own", value="custom", variable=self.obs_mode,
                        command=self._obs_mode_changed).pack(anchor="w", pady=(PAD, 0))

        own = ttk.Frame(f, padding=(24, 4, 0, 0))
        own.grid(row=4, column=1, sticky="w")
        self.station_tree = ttk.Treeview(own, columns=("id", "name"), show="headings", height=8,
                                         selectmode="browse")
        self.station_tree.heading("id", text="Station")
        self.station_tree.heading("name", text="Name on screen")
        self.station_tree.column("id", width=90)
        self.station_tree.column("name", width=220)
        self.station_tree.grid(row=0, column=0, rowspan=4, sticky="nw")
        for sid, name in o.stations.items():
            self.station_tree.insert("", "end", values=(sid, name))
        side = ttk.Frame(own, padding=(PAD, 0, 0, 0))
        side.grid(row=0, column=1, sticky="nw")
        self.own_buttons = [
            ttk.Button(side, text="Remove", command=self.remove_station),
            ttk.Button(side, text="Move up", command=lambda: self.move_station(-1)),
            ttk.Button(side, text="Move down", command=lambda: self.move_station(1)),
            ttk.Button(side, text="Start from automatic picks", command=self.fill_auto_stations),
        ]
        for b in self.own_buttons:
            b.pack(fill="x", pady=(0, 4))
        add = ttk.Frame(own, padding=(0, PAD, 0, 0))
        add.grid(row=4, column=0, columnspan=2, sticky="w")
        self.new_id, self.new_name = tk.StringVar(), tk.StringVar()
        ttk.Label(add, text="Station").pack(side="left")
        self.new_id_entry = ttk.Entry(add, textvariable=self.new_id, width=7)
        self.new_id_entry.pack(side="left", padx=4)
        ttk.Label(add, text="Name").pack(side="left", padx=(8, 0))
        self.new_name_entry = ttk.Entry(add, textvariable=self.new_name, width=18)
        self.new_name_entry.pack(side="left", padx=4)
        self.add_button = ttk.Button(add, text="Add", command=self.add_station)
        self.add_button.pack(side="left", padx=4)
        self.own_widgets = [self.station_tree, *self.own_buttons, self.new_id_entry, self.new_name_entry,
                            self.add_button]
        self._obs_mode_changed()

    def _radar_tab(self) -> None:
        f = self._tab("Radar")
        r = self.cfg.radar
        self.radar_source = tk.StringVar(value=r.source)
        self.zoom = tk.DoubleVar(value=r.zoom)
        self.center = tk.StringVar(value=r.center)
        self.frames = tk.StringVar(value=str(r.frames))
        self.frame_ms = tk.StringVar(value=str(r.frame_ms))
        self.min_dbz = tk.StringVar(value=_num(r.min_dbz))
        self.counties = tk.BooleanVar(value=r.counties)
        self.interstates = tk.BooleanVar(value=r.interstates)
        src = ttk.Frame(f)
        ttk.Radiobutton(src, text="Iowa Environmental Mesonet (recommended)", value="iem",
                        variable=self.radar_source).pack(anchor="w")
        ttk.Radiobutton(src, text="National Weather Service loop image", value="nws",
                        variable=self.radar_source).pack(anchor="w")
        self._row(f, 0, "Radar source", src)
        zf = ttk.Frame(f)
        zl = ttk.Label(zf, width=5, text=f"{self.zoom.get():.1f}")
        ttk.Scale(zf, from_=6.0, to=10.0, variable=self.zoom, length=260,
                  command=lambda v: zl.configure(text=f"{float(v):.1f}")).pack(side="left")
        zl.pack(side="left", padx=PAD)
        self._row(f, 1, "Zoom", zf, "Bigger is closer in: about 7 shows several states, 9 a metro area.")
        self._row(f, 3, "Center the map on", ttk.Entry(f, textvariable=self.center, width=30),
                  "Leave blank to center on your location.")
        self._row(f, 5, "Frames in the loop", self._spin(f, self.frames, 1, 12),
                  "Five minutes apart.")
        self._row(f, 7, "Time per frame (ms)", self._spin(f, self.frame_ms, 50, 2000, 50))
        self._row(f, 8, "Hide echoes weaker than", self._spin(f, self.min_dbz, 0, 40),
                  "dBZ. Filters out ground clutter and bugs; light snow can be as low as 10.")
        lines = ttk.Frame(f)
        ttk.Checkbutton(lines, text="County lines", variable=self.counties).pack(anchor="w")
        ttk.Checkbutton(lines, text="Interstates", variable=self.interstates).pack(anchor="w")
        self._row(f, 10, "Map shows", lines)
        self.labels_text = tk.Text(f, width=34, height=4, font="TkDefaultFont")
        self.labels_text.insert("1.0", "\n".join(r.labels))
        self._row(f, 11, "Extra city labels", self.labels_text,
                  'One per line, like "Peachtree City, GA". Big cities are labeled automatically.')

    def _alerts_tab(self) -> None:
        f = self._tab("Alerts")
        a = self.cfg.alerts
        self.alert_radius = tk.StringVar(value=_num(a.radius_miles))
        self.beep = tk.BooleanVar(value=a.beep)
        self.test_warning = tk.BooleanVar(value=a.test_warning)
        self.extra_zones = tk.StringVar(value=", ".join(a.extra_zones))
        self._row(f, 0, "Storm warnings within", self._spin(f, self.alert_radius, 5, 200, 5),
                  "Miles. Warnings for your own county and zone always count.")
        opts = ttk.Frame(f)
        ttk.Checkbutton(opts, text="Beep when the warning crawl starts", variable=self.beep).pack(anchor="w")
        ttk.Checkbutton(opts, text="Show a test message in the warning crawl",
                        variable=self.test_warning).pack(anchor="w")
        self._row(f, 2, "Warning crawl", opts)
        self._row(f, 3, "Also watch these zones", ttk.Entry(f, textvariable=self.extra_zones, width=34),
                  "NWS zone or county codes separated by commas, e.g. GAC089, GAZ044.")
        ttk.Label(f, text="This display is for entertainment only and is not an official warning source. "
                          "Get warnings from NOAA Weather Radio, Wireless Emergency Alerts, local media and "
                          "weather.gov. See DISCLAIMER.md.",
                  wraplength=600, foreground="#8a4b00", justify="left").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(PAD * 3, 0))

    # ------------------------------------------------------------ actions

    def browse_backgrounds(self) -> None:
        current = Path(self.backgrounds.get())
        start = current if current.is_absolute() else ROOT / current
        folder = filedialog.askdirectory(parent=self.root, initialdir=str(start if start.exists() else ROOT),
                                         title="Folder of background photos")
        if folder:
            p = Path(folder)
            try:
                self.backgrounds.set(str(p.resolve().relative_to(ROOT.resolve())).replace("\\", "/"))
            except ValueError:
                self.backgrounds.set(str(p))

    def _refresh_slides(self, select: int | None = None) -> None:
        self.slide_list.delete(*self.slide_list.get_children())
        for i, (key, on) in enumerate(self.slide_order):
            self.slide_list.insert("", "end", iid=str(i), values=(SLIDE_NAMES[key], "Yes" if on else "No"),
                                   tags=() if on else ("hidden",))
        if select is not None:
            self.slide_list.selection_set(str(select))
            self.slide_list.see(str(select))

    def _selected_slide(self) -> int | None:
        sel = self.slide_list.selection()
        return int(sel[0]) if sel else None

    def toggle_slide(self) -> None:
        i = self._selected_slide()
        if i is not None:
            key, on = self.slide_order[i]
            self.slide_order[i] = (key, not on)
            self._refresh_slides(i)

    def move_slide(self, step: int) -> None:
        i = self._selected_slide()
        if i is None or not 0 <= i + step < len(self.slide_order):
            return
        self.slide_order[i], self.slide_order[i + step] = self.slide_order[i + step], self.slide_order[i]
        self._refresh_slides(i + step)

    def _obs_mode_changed(self) -> None:
        custom = self.obs_mode.get() == "custom"
        for w in self.own_widgets:
            if isinstance(w, ttk.Treeview):
                continue
            w.configure(state="normal" if custom else "disabled")
        for w in (self.count_spin, self.radius_spin):
            w.configure(state="disabled" if custom else "normal")

    def add_station(self) -> None:
        sid = self.new_id.get().strip().upper()
        if not STATION_RE.match(sid):
            self._set_status("Station IDs look like KATL (3 to 5 letters or digits).", error=True)
            return
        self.station_tree.insert("", "end", values=(sid, self.new_name.get().strip() or sid))
        self.new_id.set("")
        self.new_name.set("")
        self._set_status("")

    def remove_station(self) -> None:
        for item in self.station_tree.selection():
            self.station_tree.delete(item)

    def move_station(self, step: int) -> None:
        sel = self.station_tree.selection()
        if sel:
            item = sel[0]
            self.station_tree.move(item, "", self.station_tree.index(item) + step)

    def _lookup_site(self, auto_stations: bool):
        """Resolve the location the way the display would (runs on a worker thread)."""
        from .location import resolve_site
        from .nws import NWSClient
        cfg = copy.deepcopy(self.cfg)
        cfg.location.place = self.place.get().strip()
        cfg.location.name = self.name.get().strip()
        cfg.observations.primary = self.primary.get().strip().upper()
        cfg.observations.stations = {} if auto_stations else self._stations()
        try:
            cfg.observations.count = int(self.obs_count.get())
            cfg.observations.radius_miles = float(self.obs_radius.get())
        except ValueError:
            pass
        return resolve_site(cfg, NWSClient(self.contact.get(), cfg.cache_dir))

    def check_location(self) -> None:
        try:
            place = geo.lookup_place(self.place.get())
        except LookupError as e:
            self.check_result.configure(text=str(e), foreground="#b00020")
            return
        self.check_result.configure(text=f"Found {place.label}. Asking the National Weather Service…",
                                    foreground="#444444")
        self.check_btn.configure(state="disabled")

        def done(result):
            self.check_btn.configure(state="normal")
            if isinstance(result, Exception):
                self.check_result.configure(text=f"Couldn't finish the lookup: {result}", foreground="#b00020")
                return
            s = result
            cities = ", ".join(st.name for st in s.stations[: self.cfg.observations.count])
            self.check_result.configure(foreground="#1a5e20", text=(
                f"{s.name}, {s.state}  ({s.lat:.3f}, {s.lon:.3f})\n"
                f"Forecast office {s.office}  ·  Radar {s.radar}  ·  {s.timezone}\n"
                f"Current conditions from {s.primary.id} ({s.primary.name})\n"
                f"Local Observations: {cities}"))
        self._run_in_background(lambda: self._lookup_site(self.obs_mode.get() == "auto"), done)

    def fill_auto_stations(self) -> None:
        self._set_status("Looking up nearby stations…")

        def done(result):
            if isinstance(result, Exception):
                self._set_status(f"Couldn't look up stations: {result}", error=True)
                return
            self.station_tree.delete(*self.station_tree.get_children())
            for st in result.stations[: int(self.obs_count.get() or 8)]:
                self.station_tree.insert("", "end", values=(st.id, st.name))
            self._set_status("Filled in the automatic picks. Edit them, then Save.")
        self._run_in_background(lambda: self._lookup_site(True), done)

    def _stations(self) -> dict:
        out = {}
        for item in self.station_tree.get_children():
            sid, name = self.station_tree.item(item, "values")
            out[str(sid).upper()] = str(name)
        return out

    # ----------------------------------------------------- collect / save

    def _raw_state(self) -> tuple:
        """Everything the user can change, for noticing unsaved edits."""
        names = [n for n, v in vars(self).items() if isinstance(v, tk.Variable)]
        values = tuple((n, getattr(self, n).get()) for n in sorted(names) if n not in ("new_id", "new_name"))
        return values + (tuple(self.slide_order), tuple(self._stations().items()),
                         self.labels_text.get("1.0", "end").strip())

    def collect(self) -> tuple[Config | None, list]:
        """Build a Config from the form. Returns (config, errors)."""
        errors = []
        cfg = copy.deepcopy(self.cfg)

        def number(var, label, lo, hi, kind=float):
            try:
                value = kind(float(var.get()))
            except ValueError:
                errors.append(f"{label} must be a number.")
                return lo
            if not lo <= value <= hi:
                errors.append(f"{label} must be between {lo} and {hi}.")
            return value

        def place_ok(text, label):
            try:
                geo.lookup_place(text)
            except LookupError as e:
                errors.append(f"{label}: {e}")

        cfg.location.place = self.place.get().strip()
        place_ok(cfg.location.place, "Location")
        cfg.location.name = self.name.get().strip()
        cfg.nws.contact = self.contact.get().strip()

        d = cfg.display
        d.resolution = self.resolution.get().strip()
        if d.resolution.lower() not in RESOLUTIONS:
            m = re.fullmatch(r"(\d+)\s*x\s*(\d+)", d.resolution.lower())
            if not m or int(m.group(1)) < 640 or int(m.group(2)) < 360:
                errors.append('Resolution should be 1080p, 720p, 480p or a size like "1600x900".')
            else:
                d.resolution = f"{m.group(1)}x{m.group(2)}"
        d.fullscreen, d.borderless = self.fullscreen.get(), self.borderless.get()
        d.clock_24h, d.frosted = self.clock_24h.get(), self.frosted.get()
        d.fps = number(self.fps, "Frames per second", 10, 60, int)
        d.slide_seconds = number(self.slide_seconds, "Seconds per slide", 3, 120)
        d.ticker_seconds = number(self.ticker_seconds, "Seconds per ticker line", 2, 30)
        d.backgrounds = self.backgrounds.get().strip() or "backgrounds"
        d.background_seconds = number(self.background_seconds, "Change photo every", 0, 86400)
        for var, label in ((self.panel_color, "Panel color"), (self.text_color, "Text color")):
            if not COLOR_RE.match(var.get().strip()):
                errors.append(f"{label} should look like #001829.")
        d.panel_color, d.text_color = self.panel_color.get().strip(), self.text_color.get().strip()
        d.panel_opacity = round(round(self.opacity.get()) / 100, 2)
        d.slides = [k for k, on in self.slide_order if on]
        if not d.slides:
            errors.append("Turn on at least one slide.")

        o = cfg.observations
        o.primary = self.primary.get().strip().upper()
        if o.primary and not STATION_RE.match(o.primary):
            errors.append("The Current Conditions station should look like KATL.")
        o.count = number(self.obs_count, "How many cities", 3, 16, int)
        o.radius_miles = number(self.obs_radius, "Cities within (miles)", 25, 300)
        o.stations = self._stations() if self.obs_mode.get() == "custom" else {}
        if self.obs_mode.get() == "custom" and not o.stations:
            errors.append('Add at least one city under "Choose my own", or pick automatically.')

        r = cfg.radar
        r.source = self.radar_source.get()
        r.zoom = round(float(self.zoom.get()), 1)
        r.center = self.center.get().strip()
        if r.center:
            place_ok(r.center, "Radar center")
        r.frames = number(self.frames, "Frames in the loop", 1, 12, int)
        r.frame_ms = number(self.frame_ms, "Time per frame", 50, 2000, int)
        r.min_dbz = number(self.min_dbz, "Hide echoes weaker than", 0, 40)
        r.counties, r.interstates = self.counties.get(), self.interstates.get()
        r.labels = [line.strip() for line in self.labels_text.get("1.0", "end").splitlines() if line.strip()]
        for label in r.labels:
            place_ok(label, "Radar label")

        a = cfg.alerts
        a.radius_miles = number(self.alert_radius, "Storm warnings within", 5, 200)
        a.beep, a.test_warning = self.beep.get(), self.test_warning.get()
        a.extra_zones = [z.strip().upper() for z in re.split(r"[,\s]+", self.extra_zones.get()) if z.strip()]
        bad = [z for z in a.extra_zones if not ZONE_RE.match(z)]
        if bad:
            errors.append(f"These don't look like NWS zone codes: {', '.join(bad)} (e.g. GAC089 or GAZ044).")
        return (None if errors else cfg), errors

    def save(self) -> bool:
        cfg, errors = self.collect()
        if errors:
            messagebox.showerror("Please fix these settings", "\n\n".join(errors), parent=self.root)
            return False
        try:
            path = save_config(cfg, self.save_path)
        except OSError as e:
            messagebox.showerror("Couldn't save", str(e), parent=self.root)
            return False
        self.cfg = cfg
        self.saved_state = self._raw_state()
        if self.from_display:
            self._set_status("Saved. The display will restart with the new settings in a few seconds.")
        else:
            self._set_status(f"Saved to {path.name}.")
        return True

    def close(self) -> None:
        if self._raw_state() != self.saved_state:
            answer = messagebox.askyesnocancel("Unsaved changes", "Save your changes before closing?",
                                               parent=self.root)
            if answer is None or (answer and not self.save()):
                return
        self.root.destroy()


def _num(value: float) -> str:
    return str(int(value)) if float(value).is_integer() else str(value)


def run_settings(config: str | None = None, from_display: bool = False) -> int:
    if tk is None:
        print("The settings window needs Tkinter. It comes with Python from python.org; "
              "on Linux, install your distribution's python3-tk package.")
        return 1
    if sys.platform == "win32":  # crisp text on high-DPI screens
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    cfg = load_config(config)
    save_path = Path(config) if config else ROOT / "config.toml"
    root = tk.Tk()
    style = ttk.Style(root)
    if sys.platform.startswith("linux") and "clam" in style.theme_names():
        style.theme_use("clam")
    SettingsWindow(root, cfg, save_path, from_display)
    root.lift()
    root.attributes("-topmost", True)  # appear in front of a full-screen display...
    root.after(600, lambda: root.attributes("-topmost", False))  # ...without staying on top
    root.focus_force()
    root.mainloop()
    return 0
