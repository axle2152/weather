"""Screen layout, colors and fonts. Everything is designed at 1920x1080 and scaled."""

from __future__ import annotations

import pygame

from ..config import ASSETS, Config

FONT_DIR = ASSETS / "fonts"
WEIGHTS = {"regular": "Regular", "medium": "Medium", "semibold": "SemiBold", "bold": "Bold"}


def hex_rgb(value: str) -> tuple:
    v = value.lstrip("#")
    return tuple(int(v[i:i + 2], 16) for i in (0, 2, 4))


class Theme:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.w, self.h = cfg.size
        self.s = self.h / 1080.0
        self.panel = hex_rgb(cfg.display.panel_color)
        self.opacity = cfg.display.panel_opacity
        self.text = hex_rgb(cfg.display.text_color)
        self.dim = (178, 198, 218)
        self.accent = (255, 214, 92)
        self.hi = (255, 190, 120)
        self.lo = (140, 200, 255)
        self.warning = (168, 16, 24)
        self.shadow = (0, 0, 0)
        self.radius = self.px(14)
        self._fonts: dict = {}

        # Layout (1080p units, scaled): header bar, main content area, lower ticker bar.
        self.header = self.rect(48, 30, 1824, 90)
        self.content = self.rect(48, 146, 1824, 762)
        self.lower = self.rect(48, 934, 1824, 96)
        self.gap = self.px(28)

    def px(self, v: float) -> int:
        return int(round(v * self.s))

    def rect(self, x, y, w, h) -> pygame.Rect:
        x0, y0 = self.px(x), self.px(y)
        return pygame.Rect(x0, y0, self.px(x + w) - x0, self.px(y + h) - y0)

    def font(self, weight: str, size: float) -> pygame.font.Font:
        """Font by weight name and size in 1080p pixels."""
        px = max(8, int(round(size * self.s)))
        key = (weight, px)
        if key not in self._fonts:
            path = FONT_DIR / f"LibreFranklin-{WEIGHTS[weight]}.ttf"
            self._fonts[key] = pygame.font.Font(str(path), px)
        return self._fonts[key]

    def columns(self, rect: pygame.Rect, n: int) -> list:
        """Split a rect into n equal columns separated by the standard gap."""
        w = (rect.w - self.gap * (n - 1)) / n
        return [pygame.Rect(round(rect.x + i * (w + self.gap)), rect.y, round(w), rect.h) for i in range(n)]
