"""The slides. Each one says which panels it needs (drawn once, cached) and draws its content."""

from __future__ import annotations

import datetime as dt
import math
import re

import pygame

from .. import units
from ..radar import dbz_color
from .widgets import pil_to_surface, round_corners


def fmt_time(t: dt.datetime | None, tz, clock_24h: bool = False) -> str:
    if t is None:
        return "--"
    t = t.astimezone(tz)
    return t.strftime("%H:%M") if clock_24h else t.strftime("%I:%M %p").lstrip("0")


class Slide:
    key = ""
    title = ""

    def __init__(self, app):
        self.app = app
        self.t = app.theme
        self.text = app.text
        self.icons = app.icons
        self.store = app.store
        self.cfg = app.cfg

    def available(self) -> bool:
        return True

    def pages(self) -> int:
        return 1

    def duration(self, page: int) -> float:
        return self.cfg.display.slide_seconds

    def title_for(self, page: int) -> str:
        return self.title

    def layout(self, page: int) -> list:
        return [self.t.content]

    def draw(self, surf: pygame.Surface, page: int, t: float) -> None:
        pass

    # helpers
    def px(self, v: float) -> int:
        return self.t.px(v)

    def message(self, surf, text: str, rect: pygame.Rect | None = None) -> None:
        rect = rect or self.t.content
        self.text.draw(surf, text, "medium", 52, rect.center, "center", self.t.dim)

    def time(self, t: dt.datetime | None) -> str:
        return fmt_time(t, self.app.tz, self.cfg.display.clock_24h)


# --------------------------------------------------------------------- current

class CurrentConditions(Slide):
    key = "current"
    title = "Current Conditions"

    def layout(self, page):
        c, gap = self.t.content, self.t.gap
        lw = self.px(700)
        return [pygame.Rect(c.x, c.y, lw, c.h), pygame.Rect(c.x + lw + gap, c.y, c.w - lw - gap, c.h)]

    def draw(self, surf, page, t):
        left, right = self.layout(page)
        o = self.store.current
        if o is None:
            self.message(surf, "Loading current conditions…" if "current" not in self.store.updated
                         else "Current conditions are not available", self.t.content)
            return
        px, tx = self.px, self.text
        tx.draw(surf, self.store.site.name, "semibold", 58, (left.centerx, left.y + px(34)), "midtop",
                max_width=left.w - px(60))
        icon = self.icons.weather(o.icon, px(270))
        if icon:
            surf.blit(icon, icon.get_rect(midtop=(left.centerx, left.y + px(122))))
        box = pygame.Rect(left.x + px(30), left.y + px(414), left.w - px(60), px(120))
        size, lines = tx.fit_block(o.text or "Conditions Not Reported", "medium", [50, 44, 38], box)
        tx.draw_lines(surf, lines, "medium", size, box, align="center")
        temp = f"{o.temp_f}°" if o.temp_f is not None else "N/A"
        tx.draw(surf, temp, "bold", 172, (left.centerx, left.bottom - px(28)), "midbottom")

        rows = [
            ("Humidity", f"{o.humidity}%" if o.humidity is not None else "N/A"),
            ("Dewpoint", f"{o.dewpoint_f}°F" if o.dewpoint_f is not None else "N/A"),
            ("Wind", units.fmt_wind(o.wind_dir, o.wind_mph, o.gust_mph)),
            ("Pressure", (f"{o.pressure_in:.2f} in" + (f", {o.pressure_trend}" if o.pressure_trend else ""))
             if o.pressure_in else "N/A"),
            ("Visibility", units.fmt_visibility(o.visibility_mi)),
        ]
        if o.feels_like:
            rows.append((o.feels_like[0], f"{o.feels_like[1]}°F"))
        rows.append(("Observed", f"{self.time(o.time)} at {o.station.id}"))
        pad = px(34)
        rh = (right.h - 2 * pad) / len(rows)
        for i, (label, value) in enumerate(rows):
            cy = right.y + pad + rh * (i + 0.5)
            tx.draw(surf, label, "medium", 44, (right.x + px(50), cy), "midleft", self.t.dim)
            tx.draw(surf, value, "semibold", 48, (right.right - px(50), cy), "midright",
                    max_width=right.w - px(380))
            if i < len(rows) - 1:
                y = round(right.y + pad + rh * (i + 1))
                pygame.draw.line(surf, (60, 86, 110), (right.x + px(40), y), (right.right - px(40), y), 1)


# ---------------------------------------------------------- local observations

class LocalObservations(Slide):
    key = "local_obs"
    title = "Local Observations"
    ROWS = 8

    def available(self):
        return bool(self.store.observations)

    def pages(self):
        return max(1, math.ceil(len(self.store.observations) / self.ROWS))

    def draw(self, surf, page, t):
        c, px, tx = self.t.content, self.px, self.text
        rows = self.store.observations[page * self.ROWS:(page + 1) * self.ROWS]
        cols = {"city": c.x + px(44), "icon": c.x + px(560), "temp": c.x + px(790),
                "wx": c.x + px(850), "wind": c.x + px(1440)}
        hy = c.y + px(30)
        for key, label, anchor in (("city", "City", "topleft"), ("temp", "Temp", "topright"),
                                   ("wx", "Weather", "topleft"), ("wind", "Wind", "topleft")):
            tx.draw(surf, label, "semibold", 34, (cols[key], hy), anchor, self.t.accent)
        top = c.y + px(92)
        rh = (c.bottom - px(26) - top) / self.ROWS
        for i, (station, o) in enumerate(rows):
            cy = top + rh * (i + 0.5)
            tx.draw(surf, tx.ellipsize(station.name, "semibold", 46, px(480)), "semibold", 46,
                    (cols["city"], cy), "midleft")
            if o is None:
                tx.draw(surf, "No Report", "medium", 44, (cols["wx"], cy), "midleft", self.t.dim)
                continue
            icon = self.icons.weather(o.icon, px(64), nws_size="medium")
            if icon:
                surf.blit(icon, icon.get_rect(center=(cols["icon"] + px(40), cy)))
            tx.draw(surf, f"{o.temp_f}°" if o.temp_f is not None else "--", "semibold", 48,
                    (cols["temp"], cy), "midright")
            tx.draw(surf, tx.ellipsize(o.text or "--", "medium", 42, px(560)), "medium", 42,
                    (cols["wx"], cy), "midleft")
            wind = "Calm" if o.wind_mph == 0 else (
                f"{o.wind_dir or ''} {o.wind_mph}".strip() if o.wind_mph is not None else "--")
            if o.gust_mph and o.wind_mph and o.gust_mph > o.wind_mph:
                wind += f" G{o.gust_mph}"
            tx.draw(surf, wind, "medium", 42, (cols["wind"], cy), "midleft")


# --------------------------------------------------------------- 36 hour

class Forecast36(Slide):
    key = "forecast_36"
    title = "The 36 Hour Forecast"

    def available(self):
        return self.store.forecast is not None and bool(self.store.forecast.periods)

    def pages(self):
        return len(self.store.forecast.next_36_hours()) if self.available() else 1

    def draw(self, surf, page, t):
        c, px, tx = self.t.content, self.px, self.text
        periods = self.store.forecast.next_36_hours() if self.available() else []
        if page >= len(periods):
            self.message(surf, "Forecast not available")
            return
        p = periods[page]
        pad = px(56)
        tx.draw(surf, p.name, "semibold", 66, (c.x + pad, c.y + px(40)), max_width=c.w - px(420))
        stat = f"{'High' if p.is_day else 'Low'} {p.temp}°F"
        if p.pop and p.pop >= 10:
            stat += f"     {p.pop}% chance of precipitation"
        tx.draw(surf, stat, "medium", 42, (c.x + pad, c.y + px(132)), color=self.t.hi if p.is_day else self.t.lo)
        icon = self.icons.weather(p.icon, px(190))
        if icon:
            surf.blit(icon, icon.get_rect(topright=(c.right - pad, c.y + px(40))))
        box = pygame.Rect(c.x + pad, c.y + px(262), c.w - 2 * pad, c.h - px(292))
        size, lines = tx.fit_block(p.detailed, "medium", [64, 60, 56, 52, 48, 44, 40, 36], box)
        tx.draw_lines(surf, lines, "medium", size, box)


# ------------------------------------------------------------------ extended

class Extended(Slide):
    key = "extended"
    title = "The Extended Forecast"
    DAYS = 4

    def available(self):
        return self.store.forecast is not None and bool(self.store.forecast.extended(self.DAYS))

    def layout(self, page):
        return self.t.columns(self.t.content, self.DAYS)

    def draw(self, surf, page, t):
        px, tx = self.px, self.text
        days = self.store.forecast.extended(self.DAYS) if self.available() else []
        for col, (day, night) in zip(self.layout(page), days):
            x = col.centerx
            tx.draw(surf, day.name, "semibold", 54, (x, col.y + px(26)), "midtop", max_width=col.w - px(30))
            icon = self.icons.weather(day.icon, px(206))
            if icon:
                surf.blit(icon, icon.get_rect(midtop=(x, col.y + px(104))))
            box = pygame.Rect(col.x + px(18), col.y + px(330), col.w - px(36), px(104))
            size, lines = tx.fit_block(day.short, "medium", [38, 34, 30], box, spacing=1.08)
            tx.draw_lines(surf, lines[:2], "medium", size, box, spacing=1.08, align="center")
            tx.draw(surf, f"Hi {day.temp}°", "bold", 62, (x, col.y + px(452)), "midtop", self.t.hi)
            if night is not None:
                tx.draw(surf, f"Lo {night.temp}°", "bold", 62, (x, col.y + px(530)), "midtop", self.t.lo)
            tx.draw(surf, f"Winds {day.wind_dir}".strip(), "medium", 38, (x, col.y + px(630)), "midtop",
                    max_width=col.w - px(30))
            tx.draw(surf, day.wind_speed, "medium", 38, (x, col.y + px(680)), "midtop", self.t.dim,
                    max_width=col.w - px(30))


# ------------------------------------------------------------------- almanac

class AlmanacSlide(Slide):
    key = "almanac"
    title = "Almanac"

    def available(self):
        return self.store.almanac is not None

    def layout(self, page):
        c, gap = self.t.content, self.t.gap
        th = self.px(372)
        return [pygame.Rect(c.x, c.y, c.w, th), pygame.Rect(c.x, c.y + th + gap, c.w, c.h - th - gap)]

    def draw(self, surf, page, t):
        top, bottom = self.layout(page)
        px, tx, a = self.px, self.text, self.store.almanac
        cols = [top.x + px(1010), top.x + px(1520)]
        for x, day in zip(cols, a.days):
            tx.draw(surf, day.label, "semibold", 48, (x, top.y + px(24)), "midtop", self.t.accent)
            sub = day.date.strftime("%b %d").replace(" 0", " ")
            if day.daylight:
                h, m = divmod(round(day.daylight.total_seconds() / 60), 60)
                sub += f"  ·  {h}h {m}m daylight"
            tx.draw(surf, sub, "medium", 32, (x, top.y + px(82)), "midtop", self.t.dim)
        rows = [("Twilight Begins", "dawn"), ("Sunrise", "sunrise"), ("Sunset", "sunset"), ("Twilight Ends", "dusk")]
        for i, (label, attr) in enumerate(rows):
            cy = top.y + px(160) + i * px(56)
            tx.draw(surf, label, "medium", 44, (top.x + px(70), cy), "midleft", self.t.dim)
            for x, day in zip(cols, a.days):
                tx.draw(surf, self.time(getattr(day, attr)), "semibold", 46, (x, cy), "center")

        mcols = self.t.columns(pygame.Rect(bottom.x + px(40), bottom.y, bottom.w - px(80), bottom.h), 4)
        for col, moon in zip(mcols, a.moons):
            img = self.icons.moon(moon.key, px(176))
            surf.blit(img, img.get_rect(midtop=(col.centerx, bottom.y + px(22))))
            tx.draw(surf, moon.name, "medium", 38, (col.centerx, bottom.y + px(210)), "midtop", self.t.dim)
            tx.draw(surf, moon.when.strftime("%a %b %d").replace(" 0", " "), "semibold", 42,
                    (col.centerx, bottom.y + px(258)), "midtop")


# --------------------------------------------------------------------- radar

class RadarSlide(Slide):
    key = "radar"
    title = "Doppler Radar"
    LOOPS = 3
    HOLD = 1.6  # seconds to pause on the newest frame

    def __init__(self, app):
        super().__init__(app)
        self.version = -1
        self.alert_version = -1
        self.base = None
        self.frames: list = []
        self.labels = None
        self.polys = None

    def available(self):
        rf = self.store.radar
        return rf is not None and bool(rf.frames)

    def loop_seconds(self) -> float:
        return len(self.frames or self.store.radar.frames) * self.cfg.radar.frame_ms / 1000 + self.HOLD

    def duration(self, page):
        return max(self.cfg.display.slide_seconds, self.LOOPS * self.loop_seconds()) if self.available() \
            else self.cfg.display.slide_seconds

    def _prepare(self):
        rf = self.store.radar
        size = self.t.content.size
        r = self.t.radius
        if self.store.version("radar") != self.version:
            self.version = self.store.version("radar")
            self.base = round_corners(pil_to_surface(rf.basemap.resize(size)), r) if rf.basemap else None
            self.frames = []
            for when, img in rf.frames:
                if img.size != size:
                    img = img.resize(size)
                self.frames.append((when, round_corners(pil_to_surface(img, alpha=True), r)))
            self.labels = self._labels_overlay(rf)
            self.alert_version = -1
        if self.store.version("alerts") != self.alert_version:
            self.alert_version = self.store.version("alerts")
            self.polys = self._polygon_overlay(rf)

    def _labels_overlay(self, rf):
        if not rf.labels or rf.view is None:
            return None
        over = pygame.Surface(self.t.content.size, pygame.SRCALPHA)
        rad = self.px(7)
        for name, x, y, home in rf.labels:
            pygame.draw.circle(over, (0, 0, 0), (round(x), round(y)), rad + self.px(2))
            pygame.draw.circle(over, self.t.accent if home else (255, 255, 255), (round(x), round(y)), rad)
            self.text.draw(over, name, "semibold", 36 if home else 32, (x + rad + self.px(6), y), "midleft",
                           outline=True)
        return over

    def _polygon_overlay(self, rf):
        if rf.view is None:
            return None
        over = pygame.Surface(self.t.content.size, pygame.SRCALPHA)
        drew = False
        for a in reversed(self.store.alerts):  # most important drawn last (on top)
            for ring in a.polygons:
                pts = [rf.view.to_px(lon, lat) for lon, lat in ring]
                if len(pts) < 3 or all(not (0 <= x <= rf.view.width and 0 <= y <= rf.view.height) for x, y in pts):
                    continue
                fill = pygame.Surface(self.t.content.size, pygame.SRCALPHA)
                pygame.draw.polygon(fill, (*a.color, 50), pts)
                over.blit(fill, (0, 0))
                pygame.draw.lines(over, (0, 0, 0, 200), True, pts, max(2, self.px(7)))
                pygame.draw.lines(over, (*a.color, 255), True, pts, max(1, self.px(3.5)))
                drew = True
        return over if drew else None

    def frame_index(self, t: float) -> int:
        n = len(self.frames)
        step = self.cfg.radar.frame_ms / 1000
        pos = t % self.loop_seconds()
        return min(n - 1, int(pos / step))

    def draw(self, surf, page, t):
        c = self.t.content
        if not self.available():
            self.message(surf, "Radar is loading…" if "radar" not in self.store.updated else "Radar not available")
            return
        self._prepare()
        if self.base:
            surf.blit(self.base, c)
        when, frame = self.frames[self.frame_index(t)]
        surf.blit(frame, c)
        if self.polys:
            surf.blit(self.polys, c)
        if self.labels:
            surf.blit(self.labels, c)
        px, tx = self.px, self.text
        # time badge
        label = self.time(when) if when else "Latest"
        badge = pygame.Rect(c.x + px(22), c.y + px(22), px(250), px(66))
        pygame.draw.rect(surf, (0, 18, 36), badge, border_radius=px(10))
        pygame.draw.rect(surf, (255, 255, 255), badge, width=max(1, px(2)), border_radius=px(10))
        tx.draw(surf, label, "semibold", 40, badge.center, "center", shadow=False)
        # legend
        if self.store.radar.source == "iem":
            steps = [20, 25, 30, 35, 40, 45, 50, 55, 60, 65]
            bw, bh = px(30), px(20)
            lw = len(steps) * bw
            x0 = c.right - px(30) - lw - px(90)
            y0 = c.bottom - px(48)
            box = pygame.Rect(x0 - px(100), y0 - px(14), lw + px(210), bh + px(28))
            pygame.draw.rect(surf, (0, 18, 36), box, border_radius=px(8))
            tx.draw(surf, "Light", "medium", 26, (x0 - px(12), y0 + bh / 2), "midright", shadow=False)
            for i, dbz in enumerate(steps):
                pygame.draw.rect(surf, dbz_color(dbz), (x0 + i * bw, y0, bw, bh))
            tx.draw(surf, "Heavy", "medium", 26, (x0 + lw + px(12), y0 + bh / 2), "midleft", shadow=False)
        tx.draw(surf, self.store.radar.attribution, "medium", 22, (c.x + px(24), c.bottom - px(18)),
                "bottomleft", (220, 225, 230), shadow=False, outline=True)


# ----------------------------------------------------------------- bulletins

def _clean_bulletin(text: str) -> str:
    paras = [re.sub(r"\s*\n\s*", " ", p).strip() for p in re.split(r"\n\s*\n", text.strip())]
    paras = [re.sub(r"^\*\s*", "• ", p) for p in paras if p]
    return "\n".join(paras)


class Bulletins(Slide):
    key = "bulletins"
    title = "Weather Bulletin"
    MAX_ALERTS = 3
    MAX_PAGES = 4
    SIZE = 40

    def __init__(self, app):
        super().__init__(app)
        self._version = -1
        self._pages: list = []

    def _body_rect(self) -> pygame.Rect:
        c, px = self.t.content, self.px
        return pygame.Rect(c.x + px(56), c.y + px(150), c.w - px(112), c.h - px(220))

    def _build(self):
        if self.store.version("alerts") == self._version:
            return self._pages
        self._version = self.store.version("alerts")
        alerts = self.store.local_alerts(self.cfg.alerts.radius_miles)[: self.MAX_ALERTS]
        box = self._body_rect()
        per_page = max(1, box.h // self.text.line_height("medium", self.SIZE))
        pages = []
        for a in alerts:
            body = _clean_bulletin(a.description)
            if a.instruction:
                body += "\n" + _clean_bulletin(a.instruction)
            lines = self.text.wrap(body, "medium", self.SIZE, box.w)
            chunks = [lines[i:i + per_page] for i in range(0, len(lines), per_page)][: self.MAX_PAGES] or [[]]
            for n, chunk in enumerate(chunks):
                pages.append((a, chunk, n + 1, len(chunks)))
        self._pages = pages
        return pages

    def available(self):
        return bool(self.store.local_alerts(self.cfg.alerts.radius_miles))

    def pages(self):
        return max(1, len(self._build()))

    def title_for(self, page):
        pages = self._build()
        return pages[page][0].event if page < len(pages) else self.title

    def draw(self, surf, page, t):
        pages = self._build()
        if page >= len(pages):
            self.message(surf, "No active bulletins")
            return
        a, lines, n, total = pages[page]
        c, px, tx = self.t.content, self.px, self.text
        head = pygame.Rect(c.x + px(56), c.y + px(36), c.w - px(112), px(100))
        size, hl = tx.fit_block(a.headline, "semibold", [44, 40, 36, 32], head, spacing=1.05)
        tx.draw_lines(surf, hl[:2], "semibold", size, head, color=a.color, spacing=1.05)
        tx.draw_lines(surf, lines, "medium", self.SIZE, self._body_rect())
        footer_y = c.bottom - px(30)
        if a.expires:
            tx.draw(surf, f"Until {self.time(a.expires)}", "medium", 32, (c.x + px(56), footer_y),
                    "bottomleft", self.t.dim)
        if total > 1:
            tx.draw(surf, f"Page {n} of {total}", "medium", 32, (c.right - px(56), footer_y),
                    "bottomright", self.t.dim)
        tx.draw(surf, "Source: National Weather Service", "medium", 28,
                (c.centerx, footer_y), "midbottom", self.t.dim)


SLIDES = {cls.key: cls for cls in (Bulletins, CurrentConditions, LocalObservations, Forecast36,
                                   Extended, AlmanacSlide, RadarSlide)}
