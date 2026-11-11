"""Drawing helpers: text with shadows, word wrap, frosted panels, icons, backgrounds."""

from __future__ import annotations

import logging
import random
import threading
from collections import OrderedDict
from pathlib import Path

import pygame
from PIL import Image, ImageFilter, ImageOps

from ..config import ASSETS
from .theme import Theme

log = logging.getLogger(__name__)

IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def pil_to_surface(img: Image.Image, alpha: bool = False) -> pygame.Surface:
    mode = "RGBA" if alpha else "RGB"
    img = img.convert(mode)
    surf = pygame.image.frombytes(img.tobytes(), img.size, mode)
    return surf.convert_alpha() if alpha else surf.convert()


def rounded_mask(size: tuple, radius: int) -> pygame.Surface:
    mask = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
    return mask


def round_corners(surf: pygame.Surface, radius: int) -> pygame.Surface:
    out = rounded_mask(surf.get_size(), radius)
    out.blit(surf, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return out


# ------------------------------------------------------------------------ text

class Text:
    """Renders and caches text surfaces (with an optional soft drop shadow)."""

    def __init__(self, theme: Theme, max_items: int = 600):
        self.theme = theme
        self.cache: OrderedDict = OrderedDict()
        self.max_items = max_items

    def render(self, text: str, weight: str, size: float, color=None, shadow: bool = True,
               outline: bool = False) -> pygame.Surface:
        color = color or self.theme.text
        key = (text, weight, size, color, shadow, outline)
        surf = self.cache.get(key)
        if surf is not None:
            self.cache.move_to_end(key)
            return surf
        font = self.theme.font(weight, size)
        main = font.render(text, True, color)
        if outline:  # dark outline for labels drawn over maps
            r = max(1, self.theme.px(2.5))
            surf = pygame.Surface((main.get_width() + 2 * r, main.get_height() + 2 * r), pygame.SRCALPHA)
            dark = font.render(text, True, (0, 0, 0))
            for dx in range(-r, r + 1):
                for dy in range(-r, r + 1):
                    if dx * dx + dy * dy <= r * r:
                        surf.blit(dark, (r + dx, r + dy))
            surf.blit(main, (r, r))
        elif shadow:
            off = max(1, self.theme.px(2))
            surf = pygame.Surface((main.get_width() + off, main.get_height() + off), pygame.SRCALPHA)
            dark = font.render(text, True, (0, 0, 0))
            dark.set_alpha(150)
            surf.blit(dark, (off, off))
            surf.blit(main, (0, 0))
        else:
            surf = main
        self.cache[key] = surf
        if len(self.cache) > self.max_items:
            self.cache.popitem(last=False)
        return surf

    def draw(self, target: pygame.Surface, text: str, weight: str, size: float, pos, anchor="topleft",
             color=None, shadow=True, outline=False, max_width: int | None = None) -> pygame.Rect:
        if max_width:
            size = self.fit_size(text, weight, size, max_width)
        surf = self.render(text, weight, size, color, shadow, outline)
        rect = surf.get_rect(**{anchor: (round(pos[0]), round(pos[1]))})
        target.blit(surf, rect)
        return rect

    def width(self, text: str, weight: str, size: float) -> int:
        return self.theme.font(weight, size).size(text)[0]

    # Libre Franklin's digits have different widths ("1" is narrow), so a ticking
    # clock would wiggle. These lay digits out in equal-width slots instead.

    def _digit_cell(self, weight: str, size: float) -> int:
        font = self.theme.font(weight, size)
        return max(font.size(d)[0] for d in "0123456789")

    def tabular_width(self, text: str, weight: str, size: float) -> int:
        cell = self._digit_cell(weight, size)
        font = self.theme.font(weight, size)
        return sum(cell if ch.isdigit() else font.size(ch)[0] for ch in text)

    def draw_tabular(self, target: pygame.Surface, text: str, weight: str, size: float, pos,
                     anchor="topleft", color=None, shadow=True) -> pygame.Rect:
        """Draw text with fixed-width digits, so changing numbers don't shift the layout."""
        cell = self._digit_cell(weight, size)
        font = self.theme.font(weight, size)
        width = self.tabular_width(text, weight, size)
        height = font.get_height()
        box = pygame.Rect(0, 0, width, height)
        setattr(box, anchor, (round(pos[0]), round(pos[1])))
        x = box.x
        for ch in text:
            w = cell if ch.isdigit() else font.size(ch)[0]
            if not ch.isspace():
                surf = self.render(ch, weight, size, color, shadow)
                target.blit(surf, (x + (w - font.size(ch)[0]) // 2, box.y))
            x += w
        return box

    def fit_size(self, text: str, weight: str, size: float, max_width: int, min_size: float = 18) -> float:
        while size > min_size and self.width(text, weight, size) > max_width:
            size -= 2
        return size

    def ellipsize(self, text: str, weight: str, size: float, max_width: int) -> str:
        if self.width(text, weight, size) <= max_width:
            return text
        while text and self.width(text + "…", weight, size) > max_width:
            text = text[:-1]
        return text.rstrip() + "…"

    def wrap(self, text: str, weight: str, size: float, max_width: int) -> list:
        """Word-wrap text; blank lines in the input become paragraph breaks ("")."""
        font = self.theme.font(weight, size)
        lines = []
        for para in text.split("\n"):
            words = para.split()
            if not words:
                lines.append("")
                continue
            line = words[0]
            for w in words[1:]:
                trial = line + " " + w
                if font.size(trial)[0] <= max_width:
                    line = trial
                else:
                    lines.append(line)
                    line = w
            lines.append(line)
        return lines

    def line_height(self, weight: str, size: float, spacing: float = 1.18) -> int:
        return int(self.theme.font(weight, size).get_linesize() * spacing)

    def fit_block(self, text: str, weight: str, sizes: list, rect: pygame.Rect, spacing=1.18):
        """Largest size from `sizes` at which the wrapped text fits in rect. Returns (size, lines)."""
        for size in sizes:
            lines = self.wrap(text, weight, size, rect.w)
            if len(lines) * self.line_height(weight, size, spacing) <= rect.h:
                return size, lines
        size = sizes[-1]
        lines = self.wrap(text, weight, size, rect.w)
        fit = max(1, rect.h // self.line_height(weight, size, spacing))
        return size, lines[:fit]

    def draw_lines(self, target, lines, weight, size, rect, color=None, spacing=1.18, align="left"):
        y = rect.y
        lh = self.line_height(weight, size, spacing)
        for line in lines:
            if line:
                if align == "center":
                    self.draw(target, line, weight, size, (rect.centerx, y), "midtop", color)
                else:
                    self.draw(target, line, weight, size, (rect.x, y), "topleft", color)
            y += lh
        return y


# ---------------------------------------------------------------------- panels

class Panels:
    """Translucent panels. With `frosted`, the photo behind is blurred like frosted glass."""

    def __init__(self, theme: Theme, frosted: bool):
        self.theme, self.frosted = theme, frosted
        self.cache: OrderedDict = OrderedDict()

    def get(self, bg: "Background", rect: pygame.Rect, color=None, opacity=None) -> pygame.Surface:
        color = color or self.theme.panel
        opacity = self.theme.opacity if opacity is None else opacity
        key = (bg.id, tuple(rect), color, opacity)
        surf = self.cache.get(key)
        if surf is not None:
            return surf
        source = bg.blurred if self.frosted else bg.sharp
        base = source.subsurface(rect).copy()
        tint = pygame.Surface(rect.size, pygame.SRCALPHA)
        tint.fill((*color, round(opacity * 255)))
        base.blit(tint, (0, 0))
        surf = round_corners(base, self.theme.radius)
        border = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(border, (255, 255, 255, 52), border.get_rect(), width=max(1, self.theme.px(2)),
                         border_radius=self.theme.radius)
        surf.blit(border, (0, 0))
        self.cache[key] = surf
        if len(self.cache) > 80:
            self.cache.popitem(last=False)
        return surf


# ----------------------------------------------------------------------- icons

class Icons:
    """Weather icons (cached NWS icon files) and the moon phase pictures, scaled and rounded."""

    def __init__(self, theme: Theme, client):
        self.theme, self.client = theme, client
        self.cache: dict = {}
        self.missing = ASSETS / "not_found.png"

    def _load(self, path: Path, size: int, rounded: bool) -> pygame.Surface:
        key = (str(path), size, rounded)
        if key not in self.cache:
            try:
                img = Image.open(path).convert("RGBA")
            except Exception:
                img = Image.open(self.missing).convert("RGBA")
            img = img.resize((size, size), Image.LANCZOS)
            surf = pil_to_surface(img, alpha=True)
            self.cache[key] = round_corners(surf, max(4, size // 10)) if rounded else surf
        return self.cache[key]

    def weather(self, url: str | None, size: int, nws_size: str = "large") -> pygame.Surface | None:
        """Icon for an NWS icon URL, or None if there isn't one yet.

        Only reads the disk cache; the updater thread does the downloading.
        """
        path = self.client.icon_path_cached(url, nws_size) if url else None
        if path is None or not path.exists():
            return None
        return self._load(path, size, True)

    def moon(self, key: str, size: int) -> pygame.Surface:
        return self._load(ASSETS / "moon" / f"moon_{key}.png", size, False)


# ----------------------------------------------------------------- backgrounds

class Background:
    _next_id = 0

    def __init__(self, sharp: pygame.Surface, blurred: pygame.Surface, name: str):
        Background._next_id += 1
        self.id = Background._next_id
        self.sharp, self.blurred, self.name = sharp, blurred, name


class Backgrounds:
    """Photos from the backgrounds folder, cropped to fill the screen, rotated in turn."""

    def __init__(self, theme: Theme, folder: Path, frosted: bool):
        self.theme, self.frosted = theme, frosted
        self.files = sorted(p for p in folder.glob("*") if p.suffix.lower() in IMAGE_TYPES) if folder.exists() else []
        if not self.files:
            log.warning("No pictures in %s; using a plain gradient background", folder)
        else:
            random.shuffle(self.files)
        self.index = 0
        self.current = self._finish(self._prepare(0))
        self._pending = None
        self._thread = None

    def _prepare(self, index: int):
        """CPU-heavy part (decode, crop, blur) - safe to run on a worker thread."""
        size = (self.theme.w, self.theme.h)
        if self.files:
            path = self.files[index % len(self.files)]
            img = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
            img = ImageOps.fit(img, size, Image.LANCZOS)
            name = path.name
        else:
            img = Image.linear_gradient("L").resize(size)
            img = ImageOps.colorize(img, black=(30, 70, 110), white=(8, 20, 40))
            name = "gradient"
        blurred = img.filter(ImageFilter.GaussianBlur(radius=22 * self.theme.s)) if self.frosted else img
        return img, blurred, name

    def _finish(self, prepared) -> Background:
        img, blurred, name = prepared
        return Background(pil_to_surface(img), pil_to_surface(blurred), name)

    def preload_next(self) -> None:
        if len(self.files) < 2 or self._thread is not None:
            return
        nxt = (self.index + 1) % len(self.files)

        def work():
            self._pending = (nxt, self._prepare(nxt))
        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()

    def advance(self) -> bool:
        """Switch to the preloaded next picture if it's ready. Returns True if it changed."""
        if self._thread is None or self._thread.is_alive() or self._pending is None:
            return False
        self.index, prepared = self._pending
        self._pending, self._thread = None, None
        self.current = self._finish(prepared)
        return True
