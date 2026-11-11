"""Small client for the National Weather Service API (api.weather.gov)."""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

import requests

from . import APP_NAME, REPO_URL, __version__

log = logging.getLogger(__name__)

API = "https://api.weather.gov"


class NWSClient:
    def __init__(self, contact: str, cache_dir: Path):
        ident = contact.strip() or REPO_URL
        self.session = requests.Session()
        # NWS asks every application to identify itself and give a way to reach its operator.
        self.session.headers.update({
            "User-Agent": f"({APP_NAME}/{__version__}, {ident})",
            "Accept": "application/geo+json",
        })
        self.icon_dir = cache_dir / "icons"
        self.icon_dir.mkdir(parents=True, exist_ok=True)

    def get(self, url: str, params: dict | None = None, retries: int = 3) -> dict | None:
        """GET JSON with retries. Returns None (and logs) if it can't be fetched."""
        if not url.startswith("http"):
            url = API + url
        delay = 2.0
        for attempt in range(1, retries + 1):
            try:
                r = self.session.get(url, params=params, timeout=(6, 25))
                if r.status_code == 200:
                    return r.json()
                if r.status_code == 404:
                    log.warning("NWS 404 for %s", r.url)
                    return None
                log.warning("NWS %s for %s (try %d/%d)", r.status_code, r.url, attempt, retries)
            except (requests.RequestException, ValueError) as e:
                log.warning("NWS request failed for %s: %s (try %d/%d)", url, e, attempt, retries)
            if attempt < retries:
                time.sleep(delay)
                delay *= 2
        return None

    def get_bytes(self, url: str, timeout: float = 20) -> bytes | None:
        try:
            r = self.session.get(url, timeout=(6, timeout), headers={"Accept": "*/*"})
            if r.status_code == 200:
                return r.content
            log.warning("HTTP %s for %s", r.status_code, url)
        except requests.RequestException as e:
            log.warning("Download failed for %s: %s", url, e)
        return None

    # ---- endpoints ----

    def points(self, lat: float, lon: float) -> dict | None:
        d = self.get(f"/points/{lat:.4f},{lon:.4f}")
        return d["properties"] if d else None

    def forecast(self, office: str, x: int, y: int) -> dict | None:
        d = self.get(f"/gridpoints/{office}/{x},{y}/forecast")
        return d["properties"] if d else None

    def grid_stations(self, office: str, x: int, y: int) -> list:
        d = self.get(f"/gridpoints/{office}/{x},{y}/stations")
        return d["features"] if d else []

    def station(self, station_id: str) -> dict | None:
        return self.get(f"/stations/{station_id}")

    def observations(self, station_id: str, limit: int = 4) -> list:
        d = self.get(f"/stations/{station_id}/observations", params={"limit": limit}, retries=2)
        return [f["properties"] for f in d["features"]] if d else []

    def alerts(self, **params) -> list | None:
        d = self.get("/alerts/active", params=params)
        return d["features"] if d is not None else None

    # ---- icons (cached on disk; NWS icon URLs are stable for a given condition) ----

    def icon_path_cached(self, url: str, size: str = "large") -> Path:
        """Where an NWS icon is (or would be) stored locally. Never downloads."""
        url = url.split("?")[0] + f"?size={size}"
        return self.icon_dir / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".png")

    def icon_path(self, url: str | None, size: str = "large") -> Path | None:
        """Download (once) and return the local path for an NWS icon URL."""
        if not url:
            return None
        path = self.icon_path_cached(url, size)
        if path.exists() and path.stat().st_size > 0:
            return path
        data = self.get_bytes(url.split("?")[0] + f"?size={size}")
        if not data:
            return None
        path.write_bytes(data)
        return path
