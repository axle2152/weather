"""Warning beep, generated in code (no sound file needed)."""

from __future__ import annotations

import logging
import math
from array import array

import pygame

log = logging.getLogger(__name__)


class Beeper:
    def __init__(self, enabled: bool):
        self.sound = None
        if not enabled:
            return
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(frequency=44100, size=-16, channels=2)
            freq, _, channels = pygame.mixer.get_init()
            self.sound = pygame.mixer.Sound(buffer=self._tone(freq, channels))
            self.sound.set_volume(0.5)
        except pygame.error as e:
            log.warning("No audio device; warning beeps disabled (%s)", e)

    @staticmethod
    def _tone(rate: int, channels: int) -> bytes:
        """Two short 960 Hz beeps with soft edges."""
        samples = array("h")
        total = int(rate * 0.42)
        for i in range(total):
            t = i / rate
            on = (0.0 <= t < 0.16) or (0.24 <= t < 0.40)
            if on:
                local = t if t < 0.16 else t - 0.24
                env = min(1.0, local / 0.01, (0.16 - local) / 0.01)
                v = int(14000 * env * math.sin(2 * math.pi * 960 * t))
            else:
                v = 0
            samples.extend([v] * channels)
        return samples.tobytes()

    def play(self) -> None:
        if self.sound is not None:
            self.sound.play()
