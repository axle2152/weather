"""The pygame window and the slide loop."""

from __future__ import annotations

import datetime as dt
import logging
import os
import time
from collections import OrderedDict
from pathlib import Path
from zoneinfo import ZoneInfo

import pygame

from .. import APP_NAME
from ..config import Config
from ..data import DataStore
from .audio import Beeper
from .slides import SLIDES, RadarSlide
from .theme import Theme
from .ticker import LowerBar
from .widgets import Backgrounds, Icons, Panels, Text

log = logging.getLogger(__name__)

FADE_SECONDS = 1.2


class App:
    def __init__(self, cfg: Config, store: DataStore, client, headless: bool = False):
        if headless:
            os.environ["SDL_VIDEODRIVER"] = "dummy"
            os.environ["SDL_AUDIODRIVER"] = "dummy"
        pygame.init()
        self.cfg, self.store, self.headless = cfg, store, headless
        self.theme = Theme(cfg)
        flags = 0
        if cfg.display.fullscreen and not headless:
            flags |= pygame.FULLSCREEN
        elif cfg.display.borderless and not headless:
            flags |= pygame.NOFRAME
        self.screen = pygame.display.set_mode((self.theme.w, self.theme.h), flags)
        pygame.display.set_caption(f"{APP_NAME} - {store.site.name}, {store.site.state}")
        pygame.mouse.set_visible(not cfg.display.fullscreen)
        self.tz = ZoneInfo(store.site.timezone)
        self.text = Text(self.theme)
        self.panels = Panels(self.theme, cfg.display.frosted)
        self.icons = Icons(self.theme, client)
        self.backgrounds = Backgrounds(self.theme, cfg.background_dir, cfg.display.frosted)
        self.beeper = Beeper(cfg.alerts.beep and not headless)
        self.slides = {key: cls(self) for key, cls in SLIDES.items()}
        self.lower = LowerBar(self)
        self.static: OrderedDict = OrderedDict()
        self.playlist: list = []
        self.pos = -1
        self.slide_start = 0.0
        self.fade_from = None   # (old Background, start time) during a background crossfade
        self.bg_changed = time.monotonic()
        self.time_slot = self.text.width("88:88:88 PM", "medium", 50)

    # ------------------------------------------------------------ playlist

    def build_playlist(self) -> list:
        items = []
        for key in self.cfg.display.slides:
            slide = self.slides[key]
            if slide.available():
                items += [(slide, page) for page in range(slide.pages())]
        return items or [(self.slides["current"], 0)]

    def next_slide(self, now: float) -> None:
        self.pos += 1
        if self.pos >= len(self.playlist):
            self.playlist = self.build_playlist()
            self.pos = 0
            if self.cfg.display.background_seconds <= 0:
                self.change_background(now)
        self.slide_start = now

    def change_background(self, now: float) -> None:
        old = self.backgrounds.current
        if self.backgrounds.advance():
            self.fade_from = (old, now)
            self.bg_changed = now
        self.backgrounds.preload_next()

    # ------------------------------------------------------------- drawing

    def static_layer(self, slide, page, bg) -> pygame.Surface:
        """Background photo + header + the slide's panels. Rebuilt only when something changes."""
        rects = slide.layout(page)
        key = (bg.id, tuple(tuple(r) for r in rects))
        surf = self.static.get(key)
        if surf is None:
            surf = bg.sharp.copy()
            for r in [self.theme.header] + rects:
                surf.blit(self.panels.get(bg, r), r)
            self.static[key] = surf
            if len(self.static) > 16:
                self.static.popitem(last=False)
        return surf

    def draw_header(self, surf: pygame.Surface, title: str) -> None:
        h, px = self.theme.header, self.theme.px
        now = dt.datetime.now(self.tz)
        date = now.strftime("%B %d, %Y").replace(" 0", " ")
        clock = now.strftime("%H:%M:%S") if self.cfg.display.clock_24h else now.strftime("%I:%M:%S %p")
        x, cy = h.x + px(36), h.centery
        r = self.text.draw(surf, date, "medium", 50, (x, cy), "midleft")
        x = r.right + px(36)
        self.text.draw(surf, clock, "medium", 50, (x, cy), "midleft")
        x += self.time_slot + px(28)
        pygame.draw.circle(surf, (255, 255, 255), (x + px(14), cy), px(14))
        self.text.draw(surf, title, "medium", 50, (x + px(48), cy), "midleft",
                       max_width=h.right - (x + px(48)) - px(24))

    def draw_frame(self, surf: pygame.Surface, now: float, slide=None, page=None) -> None:
        if slide is None:
            slide, page = self.playlist[self.pos]
        t = now - self.slide_start
        bg = self.backgrounds.current
        surf.blit(self.static_layer(slide, page, bg), (0, 0))
        if self.fade_from:
            old_bg, start = self.fade_from
            k = (now - start) / FADE_SECONDS
            if k >= 1:
                self.fade_from = None
            else:
                old = self.static_layer(slide, page, old_bg)
                old.set_alpha(round(255 * (1 - k)))
                surf.blit(old, (0, 0))
                old.set_alpha(None)
        self.draw_header(surf, slide.title_for(page))
        try:
            slide.draw(surf, page, t)
        except Exception:
            log.exception("drawing %s failed", slide.key)
            slide.message(surf, "Temporarily unavailable")
        self.lower.draw(surf, now)

    # ---------------------------------------------------------------- loop

    def run(self) -> None:
        clock = pygame.time.Clock()
        start = time.monotonic()
        self.playlist = self.build_playlist()
        self.pos, self.slide_start = 0, start
        self.backgrounds.preload_next()
        running = True
        last_fps_log = start
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key in (pygame.K_ESCAPE, pygame.K_q):
                        running = False
                    elif event.key in (pygame.K_F11, pygame.K_f):
                        pygame.display.toggle_fullscreen()
                    elif event.key in (pygame.K_RIGHT, pygame.K_n, pygame.K_SPACE):
                        self.next_slide(time.monotonic())
                    elif event.key == pygame.K_b:
                        self.change_background(time.monotonic())
            now = time.monotonic()
            slide, page = self.playlist[self.pos]
            if now - self.slide_start >= slide.duration(page):
                self.next_slide(now)
            bs = self.cfg.display.background_seconds
            if bs > 0 and now - self.bg_changed >= bs:
                self.change_background(now)
            self.draw_frame(self.screen, now)
            pygame.display.flip()
            clock.tick(self.cfg.display.fps)
            if now - last_fps_log >= float(os.environ.get("WX_FPS_LOG_SECONDS", 30)):
                log.debug("%.1f fps", clock.get_fps())
                last_fps_log = now
        pygame.quit()

    # --------------------------------------------------------- screenshots

    def screenshots(self, folder: Path) -> list:
        """Render one picture of every slide page (used by --screenshots)."""
        folder.mkdir(parents=True, exist_ok=True)
        saved = []
        self.playlist = self.build_playlist()
        base = time.monotonic()
        for i, (slide, page) in enumerate(self.playlist):
            self.slide_start = base
            t = 2.0
            if isinstance(slide, RadarSlide):
                slide._prepare()
                t = slide.loop_seconds() - 0.1  # newest frame
            self.lower.crawl_x = None
            self.lower.last = None
            self.draw_frame(self.screen, base + t, slide, page)
            if self.lower.warnings():  # move the crawl into view for the picture
                self.lower.crawl_x = self.theme.lower.x + self.theme.px(40)
                self.lower.last = base + t
                self.draw_frame(self.screen, base + t, slide, page)
            path = folder / f"{i + 1:02d}_{slide.key}_{page + 1}.png"
            pygame.image.save(self.screen, str(path))
            saved.append(path)
        return saved
