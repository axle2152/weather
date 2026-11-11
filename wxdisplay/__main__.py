"""Command line entry point:  python -m wxdisplay  (or  python weather.py)."""

from __future__ import annotations

import argparse
import logging
import logging.handlers
import sys
from pathlib import Path

from . import APP_NAME, __version__, disclaimer
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


def parse_args(argv):
    ap = argparse.ArgumentParser(prog=APP_NAME, description="Local weather display for streaming.")
    ap.add_argument("--config", help="settings file (default: config.toml, else config.example.toml)")
    ap.add_argument("--settings", action="store_true", help="open the settings window")
    ap.add_argument("--place", help='override the location: ZIP, "City, ST" or "lat, lon"')
    ap.add_argument("--resolution", help="1080p, 720p, 480p or WIDTHxHEIGHT")
    ap.add_argument("--fullscreen", action="store_true", help="run full screen")
    ap.add_argument("--windowed", action="store_true", help="run in a window")
    ap.add_argument("--check", action="store_true", help="look up the location, print what was found, and exit")
    ap.add_argument("--screenshots", metavar="FOLDER", help="save a picture of every slide and exit")
    ap.add_argument("--test-warning", action="store_true", help="show a test message in the warning crawl")
    ap.add_argument("--accept-disclaimer", action="store_true",
                    help="print the disclaimer and accept it here instead of on the first-run screen "
                         "(for computers with no screen)")
    ap.add_argument("--from-display", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    return ap.parse_args(argv)


def load_settings(args):
    """Settings file plus any command-line overrides."""
    cfg = load_config(args.config)
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
    return cfg


def main(argv: list | None = None) -> int:
    args = parse_args(argv)
    if args.settings:
        from .settings_window import run_settings
        return run_settings(args.config, from_display=args.from_display)

    cfg = load_settings(args)
    setup_logging(cfg.cache_dir, args.verbose)
    log = logging.getLogger(APP_NAME)
    log.warning(disclaimer.CONSOLE)
    if args.accept_disclaimer and not disclaimer.accepted():
        print(disclaimer.console_text())
        print("\n" + disclaimer.CHECKBOX)
        disclaimer.record_acceptance("--accept-disclaimer")

    from .location import resolve_site
    from .nws import NWSClient

    previous = None
    first = True
    while True:
        if not first:
            cfg = load_settings(args)
        client = NWSClient(cfg.nws.contact, cfg.cache_dir)
        try:
            site = resolve_site(cfg, client)
        except (LookupError, RuntimeError) as e:
            log.error("Location problem: %s", e)
            if previous is None:
                return 2
            log.warning("Keeping the previous settings until the problem is fixed")
            cfg, client, site = previous
        log.info("Location: %s", site.describe())
        if args.check:
            print(site.describe())
            return 0
        if first and not cfg.nws.contact:
            log.info("Tip: add your email or website as the contact in settings (press S); "
                     "the National Weather Service asks apps to include one.")
        previous = (cfg, client, site)
        result = run_display(args, cfg, client, site, first)
        if result != "reload":
            return result
        first = False


def run_display(args, cfg, client, site, first: bool):
    """Show the display until it quits ("quit"), or until the settings change ("reload")."""
    log = logging.getLogger(APP_NAME)
    from .data import DataStore, Updater
    from .radar import Radar
    from .render.app import QUIT, RELOAD, App
    from .render.theme import Theme

    store = DataStore(site)
    radar = None
    if "radar" in cfg.display.slides:
        theme = Theme(cfg)
        radar = Radar(cfg, site, theme.content.size, theme.s, client.session.headers["User-Agent"])
    updater = Updater(cfg, client, store, radar)

    if args.screenshots:
        if not disclaimer.accepted():
            print(disclaimer.console_text())
            print("\nRun  python weather.py  once to read and accept this, or add --accept-disclaimer.")
            return 3
        updater.run_once()
        app = App(cfg, store, client, headless=True)
        folder = Path(args.screenshots)
        if not folder.is_absolute():
            folder = ROOT / folder
        for p in app.screenshots(folder):
            print(p)
        return 0

    app = App(cfg, store, client, config_file=args.config)
    if first:
        if not disclaimer.accepted():
            try:
                ok = app.ask_disclaimer()
            except KeyboardInterrupt:
                ok = False
            if not ok:
                log.info("Disclaimer not accepted; exiting")
                return 0
            disclaimer.record_acceptance("first-run screen")
        if not args.config and not (ROOT / "config.toml").exists():
            log.info("No config.toml yet; opening settings so you can set your location")
            app.open_settings()
    updater.start()
    try:
        result = app.run()
    except KeyboardInterrupt:
        result = QUIT
    finally:
        updater.stop()
    return "reload" if result == RELOAD else 0


if __name__ == "__main__":
    sys.exit(main())
