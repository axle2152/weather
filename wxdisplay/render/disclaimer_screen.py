"""First-run screen: read the disclaimer, tick the box, continue (or quit)."""

from __future__ import annotations

import pygame

from .. import disclaimer


class DisclaimerScreen:
    def __init__(self, app):
        self.app = app
        self.t = app.theme
        self.text = app.text
        t = self.t
        self.panel = t.rect(110, 50, 1700, 980)
        p = self.panel
        self.body = pygame.Rect(p.x + t.px(70), p.y + t.px(130), p.w - t.px(140), t.px(560))
        self.box = pygame.Rect(p.x + t.px(70), p.y + t.px(722), t.px(48), t.px(48))
        self.label = pygame.Rect(self.box.right + t.px(26), self.box.y - t.px(6),
                                 p.right - t.px(70) - self.box.right - t.px(26), t.px(110))
        self.ok = pygame.Rect(p.right - t.px(70) - t.px(300), p.bottom - t.px(126), t.px(300), t.px(76))
        self.quit = pygame.Rect(self.ok.x - t.px(28) - t.px(220), self.ok.y, t.px(220), t.px(76))
        self.body_size, self.body_lines = self._fit_body()

    def _fit_body(self):
        """Largest text size at which all paragraphs fit, with half-line gaps between them."""
        for size in (40, 38, 36, 34, 32, 30, 28, 26, 24, 22, 20):
            lines, height = [], 0
            lh = self.text.line_height("medium", size, 1.12)
            for i, para in enumerate(disclaimer.PARAGRAPHS):
                wrapped = self.text.wrap(para, "medium", size, self.body.w)
                lines.append(wrapped)
                height += len(wrapped) * lh + (lh // 2 if i else 0)
            if height <= self.body.h:
                return size, lines
        return size, lines

    def draw(self, surf: pygame.Surface, checked: bool, mouse) -> None:
        t, tx = self.t, self.text
        bg = self.app.backgrounds.current
        surf.blit(bg.sharp, (0, 0))
        surf.blit(self.app.panels.get(bg, self.panel, opacity=0.88), self.panel)
        tx.draw(surf, disclaimer.TITLE, "semibold", 56, (self.panel.x + t.px(70), self.panel.y + t.px(44)),
                color=t.accent, max_width=self.panel.w - t.px(140))

        y = self.body.y
        lh = tx.line_height("medium", self.body_size, 1.12)
        for i, para in enumerate(self.body_lines):
            if i:
                y += lh // 2
            for line in para:
                tx.draw(surf, line, "medium", self.body_size, (self.body.x, y))
                y += lh

        # checkbox
        pygame.draw.rect(surf, t.accent if checked else (20, 34, 50), self.box, border_radius=t.px(8))
        pygame.draw.rect(surf, (255, 255, 255), self.box, width=max(2, t.px(3)), border_radius=t.px(8))
        if checked:
            b = self.box
            pts = [(b.x + b.w * 0.22, b.y + b.h * 0.52), (b.x + b.w * 0.42, b.y + b.h * 0.72),
                   (b.x + b.w * 0.78, b.y + b.h * 0.28)]
            pygame.draw.lines(surf, (10, 20, 30), False, pts, max(3, t.px(6)))
        size, lines = tx.fit_block(disclaimer.CHECKBOX, "semibold", [36, 34, 32, 30, 28, 24, 20], self.label,
                                   spacing=1.1)
        tx.draw_lines(surf, lines, "semibold", size, self.label, spacing=1.1)

        # buttons
        hover_ok = self.ok.collidepoint(mouse)
        if checked:
            fill = (255, 226, 130) if hover_ok else t.accent
            pygame.draw.rect(surf, fill, self.ok, border_radius=t.px(12))
            tx.draw(surf, "Continue", "bold", 40, self.ok.center, "center", (10, 20, 30), shadow=False)
        else:
            pygame.draw.rect(surf, (60, 72, 86), self.ok, border_radius=t.px(12))
            tx.draw(surf, "Continue", "bold", 40, self.ok.center, "center", (140, 150, 160), shadow=False)
        if self.quit.collidepoint(mouse):
            pygame.draw.rect(surf, (40, 58, 78), self.quit, border_radius=t.px(12))
        pygame.draw.rect(surf, (255, 255, 255), self.quit, width=max(2, t.px(3)), border_radius=t.px(12))
        tx.draw(surf, "Quit", "semibold", 40, self.quit.center, "center", shadow=False)

        hint = "Space: tick the box    Enter: continue    Esc: quit    Full text: DISCLAIMER.md"
        tx.draw(surf, hint, "medium", 28, (self.panel.x + t.px(70), self.ok.centery), "midleft", t.dim,
                max_width=self.quit.x - self.panel.x - t.px(100))

    def run(self) -> bool:
        """Show the screen until the user continues (True) or quits (False)."""
        screen = self.app.screen
        clock = pygame.time.Clock()
        pygame.mouse.set_visible(True)
        checked = False
        while True:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    return False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        return False
                    if event.key == pygame.K_SPACE:
                        checked = not checked
                    elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER) and checked:
                        return True
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if self.box.collidepoint(event.pos) or self.label.collidepoint(event.pos):
                        checked = not checked
                    elif self.ok.collidepoint(event.pos) and checked:
                        return True
                    elif self.quit.collidepoint(event.pos):
                        return False
            self.draw(screen, checked, pygame.mouse.get_pos())
            pygame.display.flip()
            clock.tick(30)
