"""Command line entry point:  python -m wxdisplay  (or  python weather.py)."""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys
from pathlib import Path

from . import APP_NAME, DISCLAIMER_CONSOLE, __version__
from .config import ROOT, load_config


def setup_logging(cache_dir: Path, verbose: bool) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)
    logfile = logging.handlers.RotatingFileHandler(cache_dir / "wxdisplay.log", maxBytes=2_000_000,
                                                   backupCount=2, encoding="utf-8")
    logfile.setFormatter(fmt)
    root.addHandler(logfile)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(prog=APP_NAME, description="Local weather display for streaming.")
    ap.add_argument("--config", help="settings file (default: config.toml, else config.example.toml)")
    ap.add_argument("--place", help='override the location: ZIP, "City, ST" or "lat, lon"')
    ap.add_argument("--resolution", help="1080p, 720p, 480p or WIDTHxHEIGHT")
    ap.add_argument("--fullscreen", action="store_true", help="run full screen")
    ap.add_argument("--windowed", action="store_true", help="run in a window")
    ap.add_argument("--check", action="store_true", help="look up the location, print what was found, and exit")
    ap.add_argument("--screenshots", metavar="FOLDER", help="save a picture of every slide and exit")
    ap.add_argument("--test-warning", action="store_true", help="show a test message in the warning crawl")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    args = ap.parse_args(argv)

    cfg = load_config(args.config)
    setup_logging(cfg.cache_dir, args.verbose)
    log = logging.getLogger(APP_NAME)
    log.warning(DISCLAIMER_CONSOLE)
    if args.place:
        cfg.location.place = args.place
    if args.resolution:
        cfg.display.resolution = args.resolution
    if args.fullscreen:
        cfg.display.fullscreen = True
    if args.windowed:
        cfg.display.fullscreen = False
    if args.test_warning:
        cfg.alerts.test_warning = True
    if not cfg.nws.contact:
        log.info("Tip: put your email or website under [nws] contact in config.toml; "
                 "the National Weather Service asks apps to include one.")

    # Imports that pull in pygame are deferred so --check works without a display.
    from .data import DataStore, Updater
    from .location import resolve_site
    from .nws import NWSClient

    client = NWSClient(cfg.nws.contact, cfg.cache_dir)
    try:
        site = resolve_site(cfg, client)
    except (LookupError, RuntimeError) as e:
        log.error("Location problem: %s", e)
        return 2
    log.info("Location: %s", site.describe())
    if args.check:
        print(site.describe())
        return 0

    from .radar import Radar
    from .render.theme import Theme

    store = DataStore(site)
    radar = None
    if "radar" in cfg.display.slides:
        theme = Theme(cfg)
        radar = Radar(cfg, site, theme.content.size, theme.s, client.session.headers["User-Agent"])
    updater = Updater(cfg, client, store, radar)

    from .render.app import App

    if args.screenshots:
        updater.run_once()
        app = App(cfg, store, client, headless=True)
        folder = Path(args.screenshots)
        if not folder.is_absolute():
            folder = ROOT / folder
        for p in app.screenshots(folder):
            print(p)
        return 0

    updater.start()
    app = App(cfg, store, client)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        updater.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
