"""The lower bar: cycling current conditions, or a red crawl when a warning is in effect."""

from __future__ import annotations

import pygame

from .. import disclaimer, units


class LowerBar:
    def __init__(self, app):
        self.app = app
        self.t = app.theme
        self.text = app.text
        self.store = app.store
        self.crawl_text = ""
        self.crawl_surf = None
        self.crawl_x = None
        self.last = None

    # ---- conditions ticker ----

    def messages(self) -> list:
        o = self.store.current
        site = self.store.site
        msgs = [f"Conditions at {site.name}"]
        if o is None:
            return msgs + ["Current conditions not available", disclaimer.SHORT]
        if o.text:
            msgs.append(o.text)
        msgs.append(f"Temp: {o.temp_f}°F" if o.temp_f is not None else "Temp: N/A")
        dew = f"{o.dewpoint_f}°F" if o.dewpoint_f is not None else "N/A"
        hum = f"{o.humidity}%" if o.humidity is not None else "N/A"
        msgs.append(f"Dewpoint: {dew}     Humidity: {hum}")
        if o.wind_mph is not None:
            wind = "Calm" if o.wind_mph == 0 else f"{o.wind_dir or 'Variable'} at {o.wind_mph} MPH"
            if o.gust_mph and o.wind_mph and o.gust_mph > o.wind_mph:
                wind += f"     Gusts to {o.gust_mph} MPH"
            msgs.append(f"Winds: {wind}")
        if o.pressure_in:
            msgs.append(f"Barometric Pressure: {o.pressure_in:.2f} in"
                        + (f" and {o.pressure_trend}" if o.pressure_trend else ""))
        if o.feels_like:
            msgs.append(f"{o.feels_like[0]}: {o.feels_like[1]}°F")
        msgs.append(f"Visibility: {units.fmt_visibility(o.visibility_mi)}")
        msgs.append(disclaimer.SHORT)
        return msgs

    # ---- warnings ----

    def warnings(self) -> list:
        return [a for a in self.store.local_alerts(self.app.cfg.alerts.radius_miles)
                if a.is_warning or a.id == "test"]

    def draw(self, surf: pygame.Surface, now: float) -> None:
        bar = self.t.lower
        bg = self.app.backgrounds.current
        warns = self.warnings()
        if warns:
            surf.blit(self.app.panels.get(bg, bar, color=self.t.warning, opacity=0.92), bar)
            self._crawl(surf, bar, warns, now)
            return
        self.crawl_x = None
        surf.blit(self.app.panels.get(bg, bar), bar)
        msgs = self.messages()
        idx = int(now / self.app.cfg.display.ticker_seconds) % len(msgs)
        self.text.draw(surf, msgs[idx], "medium", 50, (bar.x + self.t.px(36), bar.centery), "midleft",
                       max_width=bar.w - self.t.px(72))

    def _crawl(self, surf, bar, warns, now):
        # The disclaimer follows every alert, so it can't scroll by unseen.
        parts = []
        for a in warns:
            parts += [a.crawl_text(self.app.tz), disclaimer.CRAWL]
        text = "      •      ".join(parts)
        if text != self.crawl_text or self.crawl_surf is None:
            self.crawl_text = text
            self.crawl_surf = self.text.render(text, "semibold", 50, (255, 255, 255))
        speed = self.t.px(170)  # pixels per second
        dt_ = 0 if self.last is None else min(0.25, now - self.last)
        self.last = now
        if self.crawl_x is None or self.crawl_x + self.crawl_surf.get_width() < bar.x:
            self.crawl_x = bar.right
            self.app.beeper.play()
        else:
            self.crawl_x -= speed * dt_
        clip = surf.get_clip()
        surf.set_clip(bar.inflate(-self.t.px(8), 0))
        surf.blit(self.crawl_surf, self.crawl_surf.get_rect(midleft=(round(self.crawl_x), bar.centery)))
        surf.set_clip(clip)
